"""Browse what is on the Deck and send picked items on demand.

The watcher only ever sends media captured *while it is on*, which is the
right default but leaves everything older unreachable.  This module backs
the full-screen picker that gets it back: list what exists, hand the UI a
thumbnail for each, and queue whatever the user chose - already-sent
items included, since re-sending is a deliberate act here.

Thumbnails are the reason this is cheap: Steam already writes a 200px
JPEG next to every screenshot, so the grid costs a few kilobytes per
tile instead of a megabyte.  Clips have no such thumbnail, so one frame
is pulled with ffmpeg the first time and cached.
"""

import base64
import glob
import os
import re
import subprocess
import threading
import time

from . import captions

THUMB_MAX = 64 * 1024        # skip anything absurd rather than blow up the UI
POSTER_SIZE = "320:-2"       # clip posters: wide enough to read, small enough to fly
INDEX_TTL = 30               # seconds an index is reused while paging


class Gallery:
    def __init__(self, home: str, state_dir: str, resolver, log=None):
        self.home = home
        self.poster_dir = os.path.join(state_dir, "posters")
        self.resolver = resolver
        self.log = log or (lambda *a: None)
        # Scanning is the expensive half on a Deck with thousands of
        # screenshots (a stat per file, a directory walk per clip), so the
        # sorted index is built once and reused while the user pages
        # through it.  Thumbnails are fetched per tile, not here.
        self._lock = threading.Lock()
        self._index = {}         # kind -> (built_at, [items])

    # ------------------------------------------------------------- listing

    def _screenshots(self):
        for d in glob.glob(os.path.join(
                self.home, ".steam/steam/userdata/*/760/remote/*/screenshots")):
            for f in glob.glob(os.path.join(d, "*.jpg")):
                if os.path.isfile(f):
                    yield f

    def _clips(self):
        for root in glob.glob(os.path.join(
                self.home, ".steam/steam/userdata/*/gamerecordings/clips")):
            for d in glob.glob(os.path.join(root, "*")):
                if os.path.isdir(d):
                    yield d

    def _clip_mpd(self, clip_dir: str):
        """The DASH manifest, or None.

        Some clip folders hold only a `clip.pb` bookmark pointing into the
        background-recording timeline - no fragments of their own. The
        sender cannot export those, so the picker must not offer them.
        """
        found = glob.glob(os.path.join(clip_dir, "**", "session.mpd"),
                          recursive=True)
        return found[0] if found else None

    def _clip_seconds(self, clip_dir: str) -> int:
        mpd = self._clip_mpd(clip_dir)
        if not mpd:
            return 0
        try:
            with open(mpd, encoding="utf-8", errors="replace") as f:
                return captions.parse_mpd_duration(f.read(4096))
        except OSError:
            return 0

    def _clip_mtime(self, clip_dir: str) -> float:
        """Newest file inside - the top dir's own mtime lags behind."""
        newest = 0.0
        for root, _, files in os.walk(clip_dir):
            for f in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
        return newest

    def list(self, offset: int = 0, limit: int = 60, kind: str = "all",
             refresh: bool = False, appids: str = "") -> dict:
        """Newest first, paginated. `kind` is all | images | clips.

        Only the requested slice gets its game name resolved, so paging
        stays cheap no matter how big the library is.  `appids` is a
        comma-separated filter - a list rather than one id because a
        non-Steam game reaches us under two of them (see `games`).
        """
        items = self._get_index(kind, refresh)
        if appids:
            wanted = set(appids.split(","))
            items = [i for i in items if i["appid"] in wanted]
        total = len(items)
        page = [dict(i) for i in items[offset:offset + limit]]
        for it in page:
            it["game"] = self._name(it["appid"])
        return {"total": total, "offset": offset, "items": page}

    def _name(self, appid: str) -> str:
        return self.resolver.resolve(appid) if appid else "Steam Deck"

    def games(self, kind: str = "all") -> list:
        """Every game with media, most recent first, with counts.

        Grouped by NAME, not by appid: a non-Steam shortcut reaches us
        under two different ids - screenshots use the low 24 bits, clips a
        64-bit form - so keying on the id alone listed the same game
        twice.  Each entry therefore carries every id it answers to.
        """
        by_name = {}
        for it in self._get_index(kind, False):
            name = self._name(it["appid"])
            g = by_name.setdefault(name, {"game": name, "appids": [],
                                          "count": 0, "when": it["when"]})
            if it["appid"] not in g["appids"]:
                g["appids"].append(it["appid"])
            g["count"] += 1
            g["when"] = max(g["when"], it["when"])
        out = sorted(by_name.values(), key=lambda g: g["when"], reverse=True)
        for g in out:
            g["ids"] = ",".join(g["appids"])
        return out

    def _get_index(self, kind: str, refresh: bool):
        now = time.time()
        with self._lock:
            built, items = self._index.get(kind, (0, None))
            if items is not None and not refresh and now - built < INDEX_TTL:
                return items
        items = self._build_index(kind)
        with self._lock:
            self._index[kind] = (now, items)
        return items

    def _build_index(self, kind: str):
        items = []
        if kind in ("all", "images"):
            for f in self._screenshots():
                try:
                    st = os.stat(f)
                except OSError:
                    continue
                appid = captions.appid_from_path(f) or ""
                items.append({
                    "id": f,
                    "kind": "image",
                    "when": int(st.st_mtime),
                    "bytes": st.st_size,
                    "appid": appid,
                    "seconds": 0,
                    "sendable": True,
                })
        if kind in ("all", "clips"):
            for d in self._clips():
                cid = os.path.basename(d)
                m = captions.CLIP_ID_RE.match(cid)
                # Shown even when it holds no fragments: Steam's own media
                # view lists it, so quietly dropping it here would read as
                # a missing clip rather than an unsendable one.
                items.append({
                    "id": d,
                    "kind": "clip",
                    "when": int(self._clip_mtime(d)),
                    "bytes": 0,          # the raw DASH size means nothing to a user
                    "appid": m.group(1) if m else "",
                    "seconds": self._clip_seconds(d),
                    "sendable": bool(self._clip_mpd(d)),
                })

        items.sort(key=lambda i: i["when"], reverse=True)
        return items

    # ---------------------------------------------------------- thumbnails

    def thumbnail(self, item_id: str) -> str:
        """A data: URI for one item, or "" when it cannot be made."""
        try:
            path = self._thumb_path(item_id)
            if not path or os.path.getsize(path) > THUMB_MAX:
                return ""
            with open(path, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        except Exception as e:
            self.log("thumbnail failed for %s: %s" % (os.path.basename(item_id), e))
            return ""

    def _thumb_path(self, item_id: str):
        if os.path.isdir(item_id):
            return self._clip_poster(item_id)
        # Steam writes one next to the screenshot; fall back to the original
        # (a Deck screenshot is ~100 KB, still under THUMB_MAX).
        side = os.path.join(os.path.dirname(item_id), "thumbnails",
                            os.path.basename(item_id))
        return side if os.path.isfile(side) else item_id

    def _clip_poster(self, clip_dir: str):
        """One frame from the clip, generated once and cached."""
        os.makedirs(self.poster_dir, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(clip_dir))
        out = os.path.join(self.poster_dir, safe + ".jpg")
        if os.path.isfile(out) and os.path.getsize(out) > 0:
            return out
        mpd = self._clip_mpd(clip_dir)
        if not mpd:
            return None
        # Frame zero is often a fade-in or a loading screen, which makes a
        # useless black tile, so seek a third of the way in.  Some DASH
        # manifests refuse to seek at all ("Error when loading first
        # fragment"), so fall back to the opening frame rather than
        # showing no thumbnail.
        seek = max(1, self._clip_seconds(clip_dir) // 3)
        for args in ([" -ss", str(seek)], []):
            cmd = ["ffmpeg", "-y", "-loglevel", "error"]
            if args:
                cmd += ["-ss", str(seek)]
            cmd += ["-i", mpd, "-frames:v", "1",
                    "-vf", "scale=" + POSTER_SIZE, "-q:v", "6", out]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=60,
                                   cwd=os.path.dirname(mpd))
                if r.returncode == 0 and os.path.getsize(out) > 0:
                    return out
            except Exception as e:
                self.log("poster failed for %s: %s"
                         % (os.path.basename(clip_dir), e))
        try:
            os.unlink(out)
        except OSError:
            pass
        return None

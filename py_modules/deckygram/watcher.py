"""Watch Steam screenshot and recording folders, send new media to Telegram.

Runs as a daemon thread. inotify is used directly through ctypes because
SteamOS ships no inotify-tools and the plugin must stay dependency-free.

What is watched
  - per-game screenshot dirs   userdata/*/760/remote/<appid>/screenshots
  - Steam recording clips      userdata/*/gamerecordings/clips  (DASH dirs)

New screenshot/game folders appearing later are picked up automatically.
Events are debounced, a periodic full scan catches anything missed, and
files that fail to send stay unrecorded so the next cycle retries them.
Files that already existed when the plugin is first enabled are marked as
seen so nobody gets their entire screenshot history dumped into Telegram.

Clips are DASH fragments (session.mpd + .m4s); they are remuxed to MP4
with ffmpeg -c copy (no re-encode) before sending, exactly like pressing
"export" in the Steam UI - but automatic.
"""

import ctypes
import ctypes.util
import glob
import os
import re
import select
import shutil
import struct
import subprocess
import tempfile
import threading
import time

from . import tg

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_IGNORED = 0x00008000
EVENT_FMT = "iIII"
EVENT_SIZE = struct.calcsize(EVENT_FMT)

MEDIA_EXT = tg.IMAGE_EXT | tg.VIDEO_EXT
SETTLE_SEC = 3          # wait after last write before sending
CLIP_SETTLE_SEC = 30    # clips: recording may still be in progress
FULL_SCAN_SEC = 600     # safety net for missed events
CLIP_SCAN_SEC = 10      # clips are dirs, not files - poll instead of inotify
RETRY_SEC = 30          # backoff before retrying a failed send


class Watcher:
    def __init__(self, home, state_dir, settings_getter, resolver, notify=None, log=None):
        """settings_getter() -> dict with token/chat_id/toggles/quality.
        notify(kind, title, body) is called after each successful send.
        """
        self.home = home
        self.state_dir = state_dir
        self.get_settings = settings_getter
        self.resolver = resolver
        self.notify = notify or (lambda *a: None)
        self.log = log or (lambda *a: None)

        self.sent_path = os.path.join(state_dir, "sent.list")
        self.clips_path = os.path.join(state_dir, "clips_done.list")
        self.stats_path = os.path.join(state_dir, "stats.txt")
        self._sent = self._load(self.sent_path)
        self._clips_done = self._load(self.clips_path)

        self._pending = {}          # path -> last event time
        self._clip_retry_at = {}    # clip_id -> not-before timestamp
        self._wd_to_dir = {}
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.status = {"running": False, "watching": 0,
                       "sent": self._load_sent_count(),
                       "failed": 0, "last_sent": "", "last_error": "",
                       "current": "", "progress": -1}

    def _load_sent_count(self):
        try:
            with open(self.stats_path, encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def _bump_sent(self):
        self.status["sent"] += 1
        try:
            with self._lock:
                with open(self.stats_path, "w", encoding="utf-8") as f:
                    f.write(str(self.status["sent"]))
        except OSError:
            pass

    def _clip_duration(self, clip_dir):
        """Seconds, read from the DASH manifest's mediaPresentationDuration.

        The manifest is a small XML file; a regex read is far cheaper than
        spawning ffprobe and this runs on every status poll.
        """
        mpds = glob.glob(os.path.join(clip_dir, "**", "session.mpd"),
                         recursive=True)
        if not mpds:
            return 0
        try:
            text = open(mpds[0], encoding="utf-8", errors="replace").read(4096)
        except OSError:
            return 0
        m = re.search(
            r'mediaPresentationDuration="PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?"',
            text)
        if not m:
            return 0
        h, mi, s = (float(x) if x else 0 for x in m.groups())
        return int(h * 3600 + mi * 60 + s)

    def queue_info(self):
        """What is waiting to go out, split by kind, with sizes.

        Image sizes are exact.  Clip sizes are an ESTIMATE of what will
        actually be uploaded (duration x configured bitrate + audio),
        because the raw DASH recording on disk is far larger than the
        compressed file we send.
        """
        img_n = img_b = 0
        for f in self._collect_media():
            if f in self._sent:
                continue
            img_n += 1
            try:
                img_b += os.path.getsize(f)
            except OSError:
                pass

        s = self.get_settings()
        vbr = int(s.get("video_bitrate", 2_000_000))
        clip_n = clip_b = 0
        for d in self._all_clip_dirs():
            if os.path.basename(d) in self._clips_done:
                continue
            clip_n += 1
            dur = self._clip_duration(d)
            if dur > 0:
                est = dur * (vbr + 96_000) // 8
                clip_b += min(est, tg.SIZE_TARGET)

        return {
            "queued": img_n + clip_n,
            "queued_images": img_n,
            "queued_images_bytes": img_b,
            "queued_clips": clip_n,
            "queued_clips_bytes": clip_b,
        }

    # ------------------------------------------------------------ state files

    def _load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        except OSError:
            return set()

    def _record(self, path, item):
        with self._lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(item + "\n")

    # -------------------------------------------------------------- discovery

    def _screenshot_dirs(self):
        return glob.glob(os.path.join(
            self.home, ".steam/steam/userdata/*/760/remote/*/screenshots"))

    def _clip_roots(self):
        return glob.glob(os.path.join(
            self.home, ".steam/steam/userdata/*/gamerecordings/clips"))

    def _watch_roots(self):
        # Parents are watched too so newly created game folders get added.
        roots = set(self._screenshot_dirs())
        roots.update(glob.glob(os.path.join(
            self.home, ".steam/steam/userdata/*/760/remote")))
        roots.update(self._clip_roots())
        return roots

    def _collect_media(self):
        out = []
        for d in self._screenshot_dirs():
            for f in glob.glob(os.path.join(d, "*")):
                if os.path.isfile(f) and os.path.splitext(f)[1].lower() in tg.IMAGE_EXT:
                    out.append(f)
        return out

    def seed_existing(self):
        """Mark everything currently on disk as already sent (first run)."""
        n = 0
        for f in self._collect_media():
            if f not in self._sent:
                self._sent.add(f)
                self._record(self.sent_path, f)
                n += 1
        for d in self._all_clip_dirs():
            cid = os.path.basename(d)
            if cid not in self._clips_done:
                self._clips_done.add(cid)
                self._record(self.clips_path, cid)
                n += 1
        return n

    def _all_clip_dirs(self):
        out = []
        for root in self._clip_roots():
            out.extend(d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d))
        return out

    # ---------------------------------------------------------------- captions

    def _caption_for(self, path):
        m = re.search(r"/760/remote/(\d+)/screenshots/", path)
        appid = m.group(1) if m else ""
        name = self.resolver.resolve(appid) if appid else os.path.splitext(
            os.path.basename(path))[0]
        try:
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        except OSError:
            when = time.strftime("%Y-%m-%d %H:%M")
        return "%s · %s" % (name, when)

    def _clip_caption(self, clip_id):
        m = re.match(r"clip_(\d+)_(\d{8})_(\d{6})", clip_id)
        if not m:
            return "Steam Deck clip"
        name = self.resolver.resolve(m.group(1))
        d, t = m.group(2), m.group(3)
        return "%s · %s-%s-%s %s:%s" % (name, d[:4], d[4:6], d[6:8], t[:2], t[2:4])

    # ---------------------------------------------------------------- deleting

    def _delete_media(self, path):
        """Remove a sent screenshot/video from the Deck to free space.

        Screenshots keep a thumbnail next to them
        (.../screenshots/thumbnails/<same name>) - remove that too so the
        Steam media gallery does not show a broken entry.
        """
        try:
            os.unlink(path)
            thumb = os.path.join(os.path.dirname(path), "thumbnails",
                                 os.path.basename(path))
            if os.path.isfile(thumb):
                os.unlink(thumb)
            self.log("deleted after send: %s" % os.path.basename(path))
        except OSError as e:
            self.log("delete failed: %s - %s" % (os.path.basename(path), e))

    def _delete_clip(self, clip_dir):
        try:
            shutil.rmtree(clip_dir)
            self.log("clip deleted after send: %s" % os.path.basename(clip_dir))
        except OSError as e:
            self.log("clip delete failed: %s - %s" % (os.path.basename(clip_dir), e))

    # ----------------------------------------------------------------- sending

    def _send_file(self, path, caption):
        s = self.get_settings()

        def prog(pct):
            self.status["progress"] = pct

        def phase(name):
            label = "Encoding" if name == "encoding" else "Sending"
            self.status["current"] = "%s: %s" % (label, caption)

        tg.send_media(s["token"], s["chat_id"], path, caption,
                      bitrate=int(s.get("video_bitrate", 2_000_000)),
                      fps=int(s.get("video_fps", 30)),
                      maxh=int(s.get("video_maxh", 600)),
                      progress=prog, phase=phase)

    def _process_file(self, path):
        if path in self._sent or not os.path.isfile(path):
            return
        s = self.get_settings()
        ext = os.path.splitext(path)[1].lower()
        if ext in tg.IMAGE_EXT and not s.get("send_screenshots", True):
            return
        # Still being written (full scan can discover a file mid-write,
        # unlike the IN_CLOSE_WRITE inotify path): come back later.
        try:
            if time.time() - os.path.getmtime(path) < SETTLE_SEC:
                self._pending[path] = time.time()
                return
        except OSError:
            return
        caption = self._caption_for(path)
        self.status["current"] = "Sending: %s" % caption
        try:
            self._send_file(path, caption)
            self._sent.add(path)
            self._record(self.sent_path, path)
            self._bump_sent()
            self.status["last_sent"] = caption
            self.log("sent: %s" % os.path.basename(path))
            if s.get("notify_on_send", True):
                self.notify("sent", "Sent to Telegram", caption)
            if s.get("delete_after_send"):
                self._delete_media(path)
        except tg.Unsendable as e:
            self._sent.add(path)
            self._record(self.sent_path, path)
            self.log("skipped (%s): %s" % (e, os.path.basename(path)))
        except Exception as e:
            self.status["failed"] += 1
            self.status["last_error"] = str(e)
            # Re-queue with a short backoff so a Wi-Fi hiccup recovers in
            # ~30 s instead of waiting for the 10-minute full scan.
            self._pending[path] = time.time() + RETRY_SEC
            self.log("failed (retry in %ds): %s - %s"
                     % (RETRY_SEC, os.path.basename(path), e))
        finally:
            self.status["current"] = ""
            self.status["progress"] = -1

    def retry_now(self):
        """Manual retry: make every unsent item eligible immediately."""
        now = time.time() - SETTLE_SEC
        n = 0
        for f in self._collect_media():
            if f not in self._sent:
                self._pending[f] = now
                n += 1
        self._clip_retry_at = {}
        self.status["last_error"] = ""
        return n

    def skip_queued(self):
        """Manual pass: mark everything currently waiting as handled."""
        n = 0
        for f in list(self._pending):
            del self._pending[f]
        for f in self._collect_media():
            if f not in self._sent:
                self._sent.add(f)
                self._record(self.sent_path, f)
                n += 1
        for d in self._all_clip_dirs():
            cid = os.path.basename(d)
            if cid not in self._clips_done:
                self._clips_done.add(cid)
                self._record(self.clips_path, cid)
                n += 1
        self.status["last_error"] = ""
        return n

    def _process_clip(self, clip_dir):
        clip_id = os.path.basename(clip_dir)
        if clip_id in self._clips_done:
            return
        if time.time() < self._clip_retry_at.get(clip_id, 0):
            return   # backing off after a failure
        s = self.get_settings()
        if not s.get("send_clips", True):
            return
        try:
            if time.time() - os.path.getmtime(clip_dir) < CLIP_SETTLE_SEC:
                return  # still recording; next scan will retry
        except OSError:
            return
        mpds = glob.glob(os.path.join(clip_dir, "**", "session.mpd"), recursive=True)
        if not mpds:
            self._clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)
            return

        # Hopeless clips (too long to ever fit under the 50 MB bot limit,
        # ~30+ minutes) are rejected up front, before spending a GB-scale
        # remux on them.
        dur = self._clip_duration(clip_dir)
        if dur > 0 and tg.SIZE_TARGET * 8 // dur - 128_000 < 400_000:
            self._clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)
            self.log("clip skipped up front (too long: %ds): %s" % (dur, clip_id))
            if s.get("notify_on_send", True):
                self.notify("skipped", "Clip not sent",
                            "Too long to fit under Telegram's 50 MB bot limit")
            return

        # Remux target lives on disk (state dir), NOT /tmp: SteamOS /tmp is
        # tmpfs, and a long recording remuxed into RAM would fight the
        # running game for memory.
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False,
                                          dir=self.state_dir)
        tmp.close()
        caption = self._clip_caption(clip_id)
        try:
            self.status["current"] = "Exporting clip: %s" % caption
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", mpds[0],
                 "-c", "copy", tmp.name],
                capture_output=True, timeout=600, cwd=os.path.dirname(mpds[0]))
            if r.returncode != 0 or os.path.getsize(tmp.name) == 0:
                self.log("clip remux failed: %s" % clip_id)
                return
            self.status["current"] = "Encoding & sending: %s" % caption
            self._send_file(tmp.name, caption)
            self._clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)
            self._bump_sent()
            self.status["last_sent"] = caption
            self.log("clip sent: %s" % clip_id)
            if s.get("notify_on_send", True):
                self.notify("sent", "Clip sent to Telegram", caption)
            if s.get("delete_after_send"):
                self._delete_clip(clip_dir)
        except tg.Unsendable as e:
            self._clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)
            self.log("clip skipped (%s): %s" % (e, clip_id))
            if s.get("notify_on_send", True):
                self.notify("skipped", "Clip not sent",
                            "Too long to fit under Telegram's 50 MB bot limit")
        except Exception as e:
            self.status["failed"] += 1
            self.status["last_error"] = str(e)
            self._clip_retry_at[clip_id] = time.time() + RETRY_SEC * 2
            self.log("clip failed (retry in %ds): %s - %s" % (RETRY_SEC * 2, clip_id, e))
        finally:
            self.status["current"] = ""
            self.status["progress"] = -1
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    def _full_scan(self):
        for f in self._collect_media():
            if f not in self._sent:
                self._pending[f] = time.time()
        for d in self._all_clip_dirs():
            if os.path.basename(d) not in self._clips_done:
                self._process_clip(d)

    # -------------------------------------------------------------- main loop

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        # "Only while on": whatever exists when the watcher starts counts as
        # already handled, so media captured while sending was paused (or
        # before setup) is never delivered late.
        n = self.seed_existing()
        if n:
            self.log("seeded %d items captured while paused" % n)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.status["running"] = False

    def _run(self):
        libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6",
                           use_errno=True)
        fd = libc.inotify_init()
        if fd < 0:
            self.log("inotify_init failed; falling back to polling only")
            fd = None

        def add_watches():
            if fd is None:
                return
            mask = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE
            for d in self._watch_roots():
                if d in self._wd_to_dir.values():
                    continue
                wd = libc.inotify_add_watch(fd, d.encode(), mask)
                if wd >= 0:
                    self._wd_to_dir[wd] = d
            self.status["watching"] = len(self._wd_to_dir)

        add_watches()
        self.status["running"] = True
        self.log("watching %d folders" % self.status["watching"])
        last_scan = 0.0
        last_clip_scan = 0.0
        last_rewatch = time.time()

        while not self._stop.is_set():
            timeout = 2.0
            if fd is not None:
                r, _, _ = select.select([fd], [], [], timeout)
                if r:
                    data = os.read(fd, 65536)
                    off = 0
                    while off + EVENT_SIZE <= len(data):
                        wd, mask, cookie, length = struct.unpack_from(EVENT_FMT, data, off)
                        name = data[off + EVENT_SIZE: off + EVENT_SIZE + length].split(b"\0")[0]
                        off += EVENT_SIZE + length
                        if mask & IN_IGNORED:
                            # Watched dir was deleted; drop the stale entry so
                            # add_watches() can re-register it when it returns.
                            self._wd_to_dir.pop(wd, None)
                            last_rewatch = 0
                            continue
                        base = self._wd_to_dir.get(wd)
                        if not base:
                            continue
                        full = os.path.join(base, name.decode("utf-8", "replace"))
                        if os.path.isdir(full):
                            last_rewatch = 0  # new folder: re-scan watches soon
                        elif os.path.splitext(full)[1].lower() in MEDIA_EXT:
                            self._pending[full] = time.time()
            else:
                time.sleep(timeout)

            now = time.time()

            ready = [p for p, t in self._pending.items() if now - t >= SETTLE_SEC]
            for p in ready:
                del self._pending[p]
                self._process_file(p)

            # Clips are directories full of DASH fragments, so inotify on the
            # clip root only tells us "a folder appeared" - poll them on a
            # short interval instead of waiting for the big full scan.
            if now - last_clip_scan > CLIP_SCAN_SEC:
                for d in self._all_clip_dirs():
                    self._process_clip(d)
                last_clip_scan = now

            if now - last_rewatch > 60:
                add_watches()
                last_rewatch = now
            if now - last_scan > FULL_SCAN_SEC:
                self._full_scan()
                last_scan = now

        if fd is not None:
            os.close(fd)

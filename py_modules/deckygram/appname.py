"""Resolve a Steam appid to a human-readable game name.

Lookup order:
  1. appmanifest_<appid>.acf   - installed Steam games
  2. shortcuts.vdf             - non-Steam shortcuts (emulators, launchers)
  3. Steam store API           - uninstalled games; results are cached

Non-Steam shortcut ids appear in three different shapes, all handled here:
  - the value stored in shortcuts.vdf         e.g. 2307312975
  - screenshot folder name = low 24 bits      e.g. 8834383
  - clip folder name = 64-bit with the appid in the high 32 bits
                                              e.g. 9909833769295020032

This is used for notification captions, so it must never raise: on any
failure it returns the appid string unchanged.
"""

import glob
import json
import os
import re
import urllib.request

from .tg import _SSL_CTX

_STORE_API = "https://store.steampowered.com/api/appdetails?appids=%s&filters=basic"


def id_matches(raw: int, want: int) -> bool:
    """Does a shortcuts.vdf appid match a folder id in any of its 3 shapes?

    raw  - the 32-bit value stored in shortcuts.vdf
    want - the id taken from a media folder name, which is either the
           same value, its low 24 bits (screenshot folders), or a 64-bit
           number carrying the appid in the high 32 bits (clip folders).
    """
    return (raw == want
            or (raw & 0xFFFFFF) == want
            or (want >> 32) == raw)


def shortcut_name_from_vdf(data: bytes, want: int):
    """Scan binary shortcuts.vdf content for the entry matching `want`.

    Binary VDF: integer entries are prefixed with type byte 0x02,
    strings with 0x01.  Splitting on the typed key is reliable.
    """
    for chunk in data.split(b"\x02appid\x00")[1:]:
        if len(chunk) < 4:
            continue
        raw = int.from_bytes(chunk[:4], "little")
        if not id_matches(raw, want):
            continue
        m = re.search(rb"\x01[Aa]pp[Nn]ame\x00([^\x00]*)\x00", chunk)
        if m and m.group(1):
            return m.group(1).decode("utf-8", "replace")
    return None


class AppNameResolver:
    def __init__(self, home: str, cache_path: str):
        self.home = home
        self.cache_path = cache_path
        self._cache = self._load_cache()

    def _load_cache(self) -> dict:
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False)
            os.replace(tmp, self.cache_path)
        except OSError:
            pass

    def resolve(self, appid: str) -> str:
        if not appid:
            return "Steam Deck"
        if appid in self._cache:
            return self._cache[appid]

        try:
            want = int(appid)
        except ValueError:
            return appid

        # Screenshots taken from the Steam client itself (big picture etc.)
        if want == 7:
            return "Steam"

        name = (self._from_appmanifest(appid)
                or self._from_shortcuts(want)
                or self._from_store(appid, want))
        if name:
            self._cache[appid] = name
            self._save_cache()
            return name
        return appid

    def _from_appmanifest(self, appid: str):
        patterns = (
            os.path.join(self.home, ".steam/steam/steamapps/appmanifest_%s.acf" % appid),
            os.path.join(self.home, ".local/share/Steam/steamapps/appmanifest_%s.acf" % appid),
            "/run/media/*/steamapps/appmanifest_%s.acf" % appid,
        )
        for pat in patterns:
            for path in glob.glob(pat):
                try:
                    text = open(path, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                m = re.search(r"\"name\"\s+\"([^\"]+)\"", text)
                if m:
                    return m.group(1)
        return None

    def _from_shortcuts(self, want: int):
        pat = os.path.join(self.home, ".steam/steam/userdata/*/config/shortcuts.vdf")
        for path in glob.glob(pat):
            try:
                data = open(path, "rb").read()
            except OSError:
                continue
            name = shortcut_name_from_vdf(data, want)
            if name:
                return name
        return None

    def _from_store(self, appid: str, want: int):
        # Shortcut ids never exist on the store; only ask for plausible ones.
        if want >= 10_000_000:
            return None
        try:
            req = urllib.request.Request(
                _STORE_API % appid, headers={"User-Agent": "deckygram"})
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
                payload = json.load(resp)
            entry = payload.get(appid) or {}
            if entry.get("success") and entry.get("data", {}).get("name"):
                return entry["data"]["name"]
        except Exception:
            pass
        return None

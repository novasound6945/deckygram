"""Update check against GitHub releases.

ZIP is our primary install path, and ZIP installs have no update channel
of their own - so the plugin checks the latest GitHub release itself (at
most every 6 hours, in a background thread, never blocking status polls)
and the UI shows a one-line notice when a newer version exists.
"""

import json
import os
import shutil
import threading
import time
import urllib.request

from .tg import _SSL_CTX

LATEST_URL = ("https://api.github.com/repos/novasound6945/deckygram"
              "/releases/latest")
CHECK_EVERY = 6 * 3600
# Where Decky's "Install plugin from ZIP file" browser starts, so the
# download lands where the user is about to look.
DOWNLOAD_DIRS = ("~/Downloads", "~/Desktop", "~")


def _parse(ver: str):
    """'v0.1.2' -> (0, 1, 2); tolerant of junk."""
    out = []
    for part in ver.strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out or [0])


class UpdateChecker:
    def __init__(self, current_version: str, log=None):
        self.current = current_version
        self.log = log or (lambda *a: None)
        self._last = 0.0
        self._busy = False
        self.state = {"update_available": False, "latest": "", "url": ""}

    def poke(self):
        """Called from status polls: refresh in the background when stale."""
        now = time.time()
        if self._busy or now - self._last < CHECK_EVERY:
            return
        self._busy = True
        threading.Thread(target=self._check, daemon=True).start()

    def download(self) -> dict:
        """Fetch the new release's ZIP to a folder the user can browse to.

        Decky can install from a local ZIP but has no way to fetch one, and
        driving Game Mode's browser to a download is miserable. The backend
        already speaks HTTPS, so it just saves the file and tells the UI
        where it went.
        """
        url = self.state.get("zip_url")
        if not url:
            return {"ok": False, "error": "no download for this release"}
        target_dir = next(
            (os.path.expanduser(d) for d in DOWNLOAD_DIRS
             if os.path.isdir(os.path.expanduser(d))), os.path.expanduser("~"))
        name = "Deckygram-%s.zip" % (self.state.get("latest") or "latest")
        path = os.path.join(target_dir, name)
        tmp = path + ".part"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "deckygram"})
            with urllib.request.urlopen(req, timeout=120, context=_SSL_CTX) as r, \
                    open(tmp, "wb") as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(tmp) == 0:
                raise OSError("empty download")
            os.replace(tmp, path)
            self.log("downloaded update to %s" % path)
            return {"ok": True, "path": path, "dir": target_dir, "name": name}
        except Exception as e:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            self.log("update download failed: %r" % (e,))
            return {"ok": False, "error": str(e)[:200]}

    def _check(self):
        try:
            req = urllib.request.Request(
                LATEST_URL, headers={"User-Agent": "deckygram",
                                     "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=10,
                                        context=_SSL_CTX) as resp:
                data = json.load(resp)
            tag = data.get("tag_name", "")
            if tag and _parse(tag) > _parse(self.current):
                # Prefer the versioned asset so the saved file says which
                # release it is; fall back to the constant-name one.
                assets = {a.get("name"): a.get("browser_download_url")
                          for a in data.get("assets", [])}
                zip_url = (assets.get("Deckygram-%s.zip" % tag)
                           or assets.get("Deckygram.zip") or "")
                self.state = {
                    "update_available": True,
                    "latest": tag,
                    "url": data.get("html_url", ""),
                    "zip_url": zip_url,
                }
                self.log("update available: %s (running %s)"
                         % (tag, self.current))
            else:
                self.state = {"update_available": False, "latest": tag,
                              "url": "", "zip_url": ""}
            self._last = time.time()
        except Exception as e:
            # Offline or rate-limited: try again in an hour, stay quiet.
            self._last = time.time() - CHECK_EVERY + 3600
            self.log("update check failed: %r" % (e,))
        finally:
            self._busy = False

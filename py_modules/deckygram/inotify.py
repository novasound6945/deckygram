"""Minimal inotify wrapper over ctypes.

SteamOS ships no inotify-tools and the plugin must stay dependency-free,
so the syscalls are called straight from libc.  If inotify cannot be set
up at all the watcher falls back to pure polling (Inotify.active False).
"""

import ctypes
import ctypes.util
import os
import select
import struct
import time

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_IGNORED = 0x00008000
_EVENT_FMT = "iIII"
_EVENT_SIZE = struct.calcsize(_EVENT_FMT)
_MASK = IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE


class Event:
    __slots__ = ("base", "name", "ignored")

    def __init__(self, base, name, ignored):
        self.base = base          # watched dir (None once the watch died)
        self.name = name          # entry name inside it
        self.ignored = ignored    # True: the watched dir itself went away


class Inotify:
    def __init__(self, log=None):
        self.log = log or (lambda *a: None)
        self._wd_to_dir = {}
        self._fd = None
        try:
            libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6",
                               use_errno=True)
            fd = libc.inotify_init()
            if fd >= 0:
                self._libc = libc
                self._fd = fd
            else:
                self.log("inotify_init failed; falling back to polling only")
        except Exception as e:
            self.log("inotify unavailable (%s); polling only" % e)

    @property
    def watched(self) -> int:
        return len(self._wd_to_dir)

    def watch(self, path: str) -> None:
        if self._fd is None or path in self._wd_to_dir.values():
            return
        wd = self._libc.inotify_add_watch(self._fd, path.encode(), _MASK)
        if wd >= 0:
            self._wd_to_dir[wd] = path

    def poll(self, timeout: float):
        """Block up to `timeout` sec; return a list of Events (may be empty)."""
        if self._fd is None:
            time.sleep(timeout)
            return []
        r, _, _ = select.select([self._fd], [], [], timeout)
        if not r:
            return []
        data = os.read(self._fd, 65536)
        events = []
        off = 0
        while off + _EVENT_SIZE <= len(data):
            wd, mask, _cookie, length = struct.unpack_from(_EVENT_FMT, data, off)
            name = data[off + _EVENT_SIZE: off + _EVENT_SIZE + length].split(b"\0")[0]
            off += _EVENT_SIZE + length
            if mask & IN_IGNORED:
                # Watched dir was deleted; drop the stale entry so a later
                # watch() can re-register it.
                self._wd_to_dir.pop(wd, None)
                events.append(Event(None, "", True))
                continue
            base = self._wd_to_dir.get(wd)
            if base:
                events.append(Event(base, name.decode("utf-8", "replace"), False))
        return events

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

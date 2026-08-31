"""Queue and statistics state.

Owns everything the watcher remembers between ticks and restarts:
  - which files/clips were already handled (sent.list / clips_done.list)
  - the lifetime sent counter (stats.txt - survives reinstalls only if the
    runtime dir does, but at least survives plugin restarts)
  - the in-memory pending queue with its settle/burst logic

take_ready() is deliberately free of filesystem access so the batching
rules can be unit-tested.
"""

import os
import threading
import time


class QueueState:
    def __init__(self, state_dir: str):
        self.sent_path = os.path.join(state_dir, "sent.list")
        self.clips_path = os.path.join(state_dir, "clips_done.list")
        self.stats_path = os.path.join(state_dir, "stats.txt")
        self.sent = self._load(self.sent_path)
        self.clips_done = self._load(self.clips_path)
        self.sent_count = self._load_sent_count()

        self.lock = threading.Lock()
        self.pending = {}        # path -> earliest-send timestamp base
        self.no_album = set()    # paths that failed as an album once
        self.clip_retry_at = {}  # clip_id -> not-before timestamp

    # ------------------------------------------------------------ list files

    def _load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        except OSError:
            return set()

    def _record(self, path, item):
        with self.lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(item + "\n")

    def mark_sent(self, path: str) -> None:
        if path not in self.sent:
            self.sent.add(path)
            self._record(self.sent_path, path)

    def mark_clip_done(self, clip_id: str) -> None:
        if clip_id not in self.clips_done:
            self.clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)

    # --------------------------------------------------------------- counter

    def _load_sent_count(self):
        try:
            with open(self.stats_path, encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except (OSError, ValueError):
            return 0

    def bump_sent(self) -> int:
        self.sent_count += 1
        try:
            with self.lock:
                with open(self.stats_path, "w", encoding="utf-8") as f:
                    f.write(str(self.sent_count))
        except OSError:
            pass
        return self.sent_count

    # ------------------------------------------------------------- the queue

    def queue(self, path: str, at: float = None) -> None:
        with self.lock:
            self.pending[path] = time.time() if at is None else at

    def clear_pending(self) -> None:
        with self.lock:
            self.pending.clear()

    def take_ready(self, now: float, settle_sec: float, image_exts) -> list:
        """Pop and return every pending path whose settle window has passed.

        Burst-friendly: while ANY image is still inside its settle window,
        ready images are held back too, so a run of screenshots lands in
        one batch (-> one Telegram album, one ping).  Non-image files are
        never held by the image burst.
        """
        def is_img(p):
            return os.path.splitext(p)[1].lower() in image_exts

        with self.lock:
            img_settling = any(
                now - t < settle_sec and is_img(p)
                for p, t in self.pending.items())
            ready = []
            for p, t in list(self.pending.items()):
                if now - t < settle_sec:
                    continue
                if img_settling and is_img(p):
                    continue
                ready.append(p)
                del self.pending[p]
        return ready

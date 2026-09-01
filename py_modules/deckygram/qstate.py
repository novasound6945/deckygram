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
        self.stalled_path = os.path.join(state_dir, "stalled.list")
        self.stats_path = os.path.join(state_dir, "stats.txt")
        self.delete_path = os.path.join(state_dir, "delete_after_send.list")
        self.sent = self._load(self.sent_path)
        self.clips_done = self._load(self.clips_path)
        self.sent_count = self._load_sent_count()

        self.lock = threading.Lock()
        self.pending = {}        # path -> earliest-send timestamp base
        self.no_album = set()    # paths that failed as an album once
        self.clip_retry_at = {}  # clip_id -> not-before timestamp
        self.attempts = {}       # item -> failed send count
        # Picked by hand in the gallery: send these even though they are
        # already in `sent` / `clips_done`.  Deliberately not persisted -
        # a forced send is a one-off, not a standing instruction.
        self.forced = set()
        # Items we stopped retrying automatically.  Persisted, because a
        # plugin restart seeds everything on disk as "already handled" -
        # without this list, media held back by a broken setup would be
        # written off silently instead of waiting for "Retry now".
        self.gave_up = self._load(self.stalled_path)
        # Asked to be deleted, but not yet - they were queued or in flight
        # when the user pressed delete in the gallery. Persisted: the
        # instruction has to survive a restart, or a plugin reload between
        # the press and the send would silently drop it.
        self.delete_when_sent = self._load(self.delete_path)

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
        self._forget(path)

    def mark_clip_done(self, clip_id: str) -> None:
        if clip_id not in self.clips_done:
            self.clips_done.add(clip_id)
            self._record(self.clips_path, clip_id)
        self._forget(clip_id)

    def force(self, item: str) -> None:
        """Mark an item as chosen by hand, so the sent-already guard yields."""
        with self.lock:
            self.forced.add(item)

    def is_forced(self, item: str) -> bool:
        return item in self.forced

    def unforce(self, item: str) -> None:
        """Clear the one-off flag once the item is settled.

        Clips need this explicitly: their persisted key is the folder
        NAME while the queue and this flag use the full PATH, so
        mark_clip_done() alone cannot clear it - and a forced clip whose
        flag survives is re-sent on every ten-second scan, forever.
        """
        with self.lock:
            self.forced.discard(item)

    def _forget(self, item: str) -> None:
        """Drop retry bookkeeping for an item that is now settled."""
        was_stalled = item in self.gave_up
        with self.lock:
            self.attempts.pop(item, None)
            self.gave_up.discard(item)
            self.forced.discard(item)
        if was_stalled:
            self._rewrite_stalled()

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

    # ---------------------------------------------------------- retry budget

    def note_attempt(self, item: str) -> int:
        """Count one failed send of `item`; returns the running total."""
        with self.lock:
            n = self.attempts.get(item, 0) + 1
            self.attempts[item] = n
            return n

    def give_up(self, item: str) -> None:
        """Stop retrying automatically - but keep the item queued.

        Nothing is marked as sent, so the media survives; only the timer
        stops.  "Retry now" (or a repaired setup) revives it.
        """
        new = item not in self.gave_up
        with self.lock:
            self.gave_up.add(item)
            self.pending.pop(item, None)
        if new:
            self._record(self.stalled_path, item)

    # ------------------------------------------------- delete-after-send

    def want_delete(self, item: str) -> None:
        """Remember to delete `item` once it has been sent."""
        if item in self.delete_when_sent:
            return
        with self.lock:
            self.delete_when_sent.add(item)
        self._record(self.delete_path, item)

    def wants_delete(self, item: str) -> bool:
        return item in self.delete_when_sent

    def prune_delete_promises(self, exists=os.path.exists) -> int:
        """Drop promises whose media is gone. Returns how many.

        A promise is kept until the item is sent, which is right - but if
        the file leaves by some other route (Steam's own media tab, the
        desktop, a card swap) nothing would ever clear it, and the list
        would grow forever with names that mean nothing.
        """
        dead = [i for i in list(self.delete_when_sent) if not exists(i)]
        if not dead:
            return 0
        with self.lock:
            for item in dead:
                self.delete_when_sent.discard(item)
        self._rewrite(self.delete_path, self.delete_when_sent)
        return len(dead)

    def delete_done(self, item: str) -> None:
        """The deletion happened (or the item is gone): forget the promise."""
        if item not in self.delete_when_sent:
            return
        with self.lock:
            self.delete_when_sent.discard(item)
        self._rewrite(self.delete_path, self.delete_when_sent)

    def forget_item(self, item: str) -> None:
        """Drop every trace of an item that is gone from the Deck.

        Deleting the file does not by itself take it out of the queue, the
        stalled list, or the retry bookkeeping. A pending entry is
        harmless - it is discarded when the file turns out to be missing -
        but a stalled one is not: it keeps counting towards "N items gave
        up" and keeps its line in stalled.list, pointing at nothing, for
        as long as the plugin lives.
        """
        with self.lock:
            self.pending.pop(item, None)
            self.no_album.discard(item)
            self.clip_retry_at.pop(os.path.basename(item), None)
            self.delete_when_sent.discard(item)
        self._rewrite(self.delete_path, self.delete_when_sent)
        # attempts / gave_up / forced, and rewrites stalled.list if needed
        self._forget(item)

    def _rewrite(self, path, items) -> None:
        with self.lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    for item in sorted(items):
                        f.write(item + "\n")
            except OSError:
                pass

    def revive_all(self) -> None:
        """Manual retry: forget the retry budget for everything."""
        with self.lock:
            self.attempts.clear()
            self.gave_up.clear()
        self._rewrite_stalled()

    def _rewrite_stalled(self) -> None:
        with self.lock:
            try:
                with open(self.stalled_path, "w", encoding="utf-8") as f:
                    for item in sorted(self.gave_up):
                        f.write(item + "\n")
            except OSError:
                pass

    def stalled(self) -> int:
        return len(self.gave_up)

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

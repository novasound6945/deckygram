"""Watch Steam screenshot and recording folders, send new media to Telegram.

Runs as a daemon thread.  This module is the orchestrator: folder
discovery, the inotify/poll loop and the public control surface
(start/stop, queue_info, retry, skip).  The pieces live next door:

  inotify.py   raw inotify wrapper (ctypes; polling fallback)
  qstate.py    sent/clip bookkeeping, counters, the pending queue
  sender.py    actual sending: albums, clip remux+encode, retries
  captions.py  caption strings and clip-manifest parsing

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

import glob
import os
import threading
import time

from . import media
from .inotify import Inotify
from .qstate import QueueState
from .sender import Sender, SETTLE_SEC

MEDIA_EXT = media.IMAGE_EXT | media.VIDEO_EXT
FULL_SCAN_SEC = 600     # safety net for missed events
CLIP_SCAN_SEC = 10      # clips are dirs, not files - poll instead of inotify


class Watcher:
    def __init__(self, home, state_dir, settings_getter, resolver, notify=None, log=None):
        """settings_getter() -> dict with token/chat_id/toggles/quality.
        notify(kind, title, body) is called after each successful send.
        """
        self.home = home
        self.get_settings = settings_getter
        self.log = log or (lambda *a: None)

        self.qs = QueueState(state_dir)
        self.status = {"running": False, "watching": 0,
                       "sent": self.qs.sent_count,
                       "failed": 0, "last_sent": "", "last_error": "",
                       "current": "", "progress": -1,
                       "setup_broken": "", "stalled": 0}
        self.sender = Sender(self.qs, state_dir, settings_getter, resolver,
                             notify=notify, log=self.log, status=self.status)
        self.status["ffmpeg_ok"] = self.sender.ffmpeg_ok

        self._thread = None
        self._stop = threading.Event()
        self._qcache = (0.0, None)   # (timestamp, last queue_info result)

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
                if os.path.isfile(f) and os.path.splitext(f)[1].lower() in media.IMAGE_EXT:
                    out.append(f)
        return out

    def _all_clip_dirs(self):
        out = []
        for root in self._clip_roots():
            out.extend(d for d in glob.glob(os.path.join(root, "*")) if os.path.isdir(d))
        return out

    def seed_existing(self):
        """Mark everything currently on disk as already sent (first run).

        Items that previously ran out of retries are the one exception:
        they were captured while sending was ON and we promised to keep
        them, so they are re-queued instead of being written off.
        """
        n = held = 0
        for f in self._collect_media():
            if f in self.qs.sent:
                continue
            if f in self.qs.gave_up:
                self.qs.queue(f, 0)      # eligible immediately
                held += 1
                continue
            self.qs.mark_sent(f)
            n += 1
        for d in self._all_clip_dirs():
            cid = os.path.basename(d)
            if cid in self.qs.clips_done or cid in self.qs.gave_up:
                continue
            self.qs.mark_clip_done(cid)
            n += 1
        if held:
            self.log("%d item(s) kept from a failed send - retrying" % held)
        return n

    # ------------------------------------------------------------- UI surface

    def queue_info(self):
        """What is waiting to go out, split by kind, with sizes.

        Cached for a few seconds: the UI polls every 2 s and this walks
        every screenshot dir - on a Deck with years of screenshots that
        is real work we should not repeat per poll.

        Image sizes are exact.  Clip sizes are an ESTIMATE of what will
        actually be uploaded (duration x configured bitrate + audio),
        because the raw DASH recording on disk is far larger than the
        compressed file we send.
        """
        now = time.time()
        ts, cached = self._qcache
        if cached is not None and now - ts < 4:
            return dict(cached)

        img_n = img_b = 0
        for f in self._collect_media():
            if f in self.qs.sent:
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
            if os.path.basename(d) in self.qs.clips_done:
                continue
            clip_n += 1
            dur = self.sender.clip_duration(d)
            if dur > 0:
                est = dur * (vbr + 96_000) // 8
                clip_b += min(est, self.sender.destination().size_target())

        result = {
            "queued": img_n + clip_n,
            "queued_images": img_n,
            "queued_images_bytes": img_b,
            "queued_clips": clip_n,
            "queued_clips_bytes": clip_b,
        }
        self._qcache = (now, result)
        return dict(result)

    def retry_now(self):
        """Manual retry: make every unsent item eligible immediately.

        Also forgives the retry budget and any suspended setup, so this
        one button covers "I fixed my bot" as well as "try again now".
        """
        self.qs.revive_all()
        self.sender.clear_broken()
        now = time.time() - SETTLE_SEC
        n = 0
        with self.qs.lock:
            for f in self._collect_media():
                if f not in self.qs.sent:
                    self.qs.pending[f] = now
                    n += 1
        self.qs.clip_retry_at = {}
        self.status["last_error"] = ""
        self.status["stalled"] = 0
        return n

    def skip_queued(self):
        """Manual pass: mark everything currently waiting as handled."""
        n = 0
        self.qs.clear_pending()
        self.qs.revive_all()
        self.status["stalled"] = 0
        for f in self._collect_media():
            if f not in self.qs.sent:
                self.qs.mark_sent(f)
                n += 1
        for d in self._all_clip_dirs():
            cid = os.path.basename(d)
            if cid not in self.qs.clips_done:
                self.qs.mark_clip_done(cid)
                n += 1
        self.status["last_error"] = ""
        return n

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
        if not self.sender.ffmpeg_ok:
            self.log("ffmpeg/ffprobe not found - clip sending disabled")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.status["running"] = False

    def _full_scan(self):
        with self.qs.lock:
            for f in self._collect_media():
                if f not in self.qs.sent:
                    self.qs.pending[f] = time.time()
        for d in self._all_clip_dirs():
            if os.path.basename(d) not in self.qs.clips_done:
                self.sender.process_clip(d)

    def _run(self):
        ino = Inotify(log=self.log)

        def add_watches():
            for d in self._watch_roots():
                ino.watch(d)
            self.status["watching"] = ino.watched

        add_watches()
        self.status["running"] = True
        self.log("watching %d folders" % self.status["watching"])
        last_scan = 0.0
        last_clip_scan = 0.0
        last_rewatch = time.time()

        while not self._stop.is_set():
          # One bad iteration must never kill the whole watcher: log and
          # keep looping.  (The UI would otherwise show "running" forever
          # over a dead thread.)
          try:
            for ev in ino.poll(2.0):
                if ev.ignored:
                    last_rewatch = 0
                    continue
                full = os.path.join(ev.base, ev.name)
                if os.path.isdir(full):
                    last_rewatch = 0  # new folder: re-scan watches soon
                elif os.path.splitext(full)[1].lower() in MEDIA_EXT:
                    self.qs.queue(full)

            now = time.time()
            # Suspended (rejected bot/chat, or a 429 cooldown): keep
            # watching and queueing, just do not call Telegram.
            if not self.sender.blocked():
                ready = self.qs.take_ready(now, SETTLE_SEC, media.IMAGE_EXT)
                self.sender.process_batch(ready)

                # Clips are directories full of DASH fragments, so inotify on
                # the clip root only tells us "a folder appeared" - poll them
                # on a short interval instead of waiting for the full scan.
                if now - last_clip_scan > CLIP_SCAN_SEC:
                    for d in self._all_clip_dirs():
                        self.sender.process_clip(d)
                    last_clip_scan = now
            self.status["stalled"] = self.qs.stalled()

            if now - last_rewatch > 60:
                add_watches()
                last_rewatch = now
            if now - last_scan > FULL_SCAN_SEC:
                self._full_scan()
                last_scan = now
          except Exception as e:
            self.log("watch loop error (continuing): %r" % (e,))
            time.sleep(2)

        self.status["running"] = False
        ino.close()

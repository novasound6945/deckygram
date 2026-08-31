"""Sending pipeline: screenshots (single + albums) and recorded clips.

Owns everything between "this path is ready" and "it arrived in Telegram
/ it permanently cannot": captions, albums, clip remux, retry backoff
bookkeeping, delete-after-send and user notifications.

State lives in QueueState; UI-visible progress goes into the shared
status dict owned by the Watcher.
"""

import glob
import os
import shutil
import subprocess
import tempfile
import time

from . import captions, destinations, media
from .errors import SetupBroken, Unsendable

SETTLE_SEC = 3          # wait after last write before sending
CLIP_SETTLE_SEC = 30    # clips: recording may still be in progress
RETRY_SEC = 30          # backoff before retrying a failed send
MAX_ATTEMPTS = 5        # give up (but keep the item) after this many tries
RECHECK_SEC = 600       # re-test a broken setup this often


class Sender:
    def __init__(self, qs, state_dir, settings_getter, resolver,
                 notify=None, log=None, status=None):
        self.qs = qs
        self.state_dir = state_dir
        self.get_settings = settings_getter
        self.resolver = resolver
        self.notify = notify or (lambda *a: None)
        self.log = log or (lambda *a: None)
        self.status = status if status is not None else {}
        # SteamOS ships ffmpeg, but never assume: if it is missing, clips
        # would otherwise fail-and-retry forever.  Screenshots do not need
        # it, so we just disable the clip pipeline and say why.
        self.ffmpeg_ok = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
        # Set when the destination rejects the bot/chat/webhook itself.
        # Sending is then suspended (retrying cannot help) until the user
        # fixes it; we re-test every RECHECK_SEC so a bot unblocked inside
        # Telegram - which changes no setting here - recovers on its own.
        self._broken_at = 0.0
        self._paused_until = 0.0    # honours a 429's retry_after

    @staticmethod
    def _friendly(e):
        """Turn raw exception text into something a user can act on."""
        msg = str(e)
        low = msg.lower()
        if "urlopen" in low or "timed out" in low or "getaddrinfo" in low \
                or "connection" in low or "unreachable" in low:
            return "Network error - will retry automatically"
        return msg[:200]

    # ------------------------------------------------------- failure handling

    def blocked(self):
        """True while sending is suspended (broken setup or a 429 cooldown)."""
        now = time.time()
        if now < self._paused_until:
            return True
        if self._broken_at and now - self._broken_at < RECHECK_SEC:
            return True
        return False

    def clear_broken(self):
        """Called when the token/chat changes - give it another go at once."""
        self._broken_at = 0.0
        self.status["setup_broken"] = ""

    def _note_failure(self, e):
        """Record a failed send; returns True if it was a fatal setup error."""
        self.status["failed"] += 1
        if isinstance(e, SetupBroken):
            first = not self.status.get("setup_broken")
            self.status["setup_broken"] = str(e)[:200]
            self.status["last_error"] = str(e)[:200]
            self._broken_at = time.time()
            self.log("destination rejected this setup: %s "
                     "(sending suspended, re-checking in %ds)" % (e, RECHECK_SEC))
            if first:
                # Tell the user once, not every 30 seconds.
                self.notify("broken", "Deckygram needs setting up again",
                            "%s" % e)
            return True
        retry_after = getattr(e, "retry_after", 0)
        if retry_after:
            self._paused_until = time.time() + retry_after + 1
            self.log("rate limited; pausing %ds" % retry_after)
        self.status["last_error"] = self._friendly(e)
        return False

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

    def destination(self):
        """Current destination, rebuilt each time so settings edits apply."""
        return destinations.build(self.get_settings())

    def _send_file(self, path, caption):
        s = self.get_settings()

        def prog(pct):
            self.status["progress"] = pct

        def phase(name):
            label = "Encoding" if name == "encoding" else "Sending"
            self.status["current"] = "%s: %s" % (label, caption)

        # Bitrate and frame height come from the destination's preset;
        # only the frame rate is a plain setting.
        self.destination().send(path, caption,
                                fps=int(s.get("video_fps", 30)),
                                progress=prog, phase=phase)

    def process_file(self, path):
        if path in self.qs.sent or not os.path.isfile(path):
            return
        s = self.get_settings()
        ext = os.path.splitext(path)[1].lower()
        if ext in media.IMAGE_EXT and not s.get("send_screenshots", True):
            return
        # Still being written (full scan can discover a file mid-write,
        # unlike the IN_CLOSE_WRITE inotify path): come back later.
        try:
            if time.time() - os.path.getmtime(path) < SETTLE_SEC:
                self.qs.queue(path)
                return
        except OSError:
            return
        caption = captions.caption_for(path, self.resolver)
        self.status["current"] = "Sending: %s" % caption
        try:
            self._send_file(path, caption)
            self.qs.mark_sent(path)
            self.qs.bump_sent()
            self.status["sent"] = self.qs.sent_count
            self.status["last_sent"] = caption
            self.log("sent: %s" % os.path.basename(path))
            if s.get("notify_on_send", True):
                self.notify("sent", "Sent", caption)
            if s.get("delete_after_send"):
                self._delete_media(path)
        except Unsendable as e:
            self.qs.mark_sent(path)
            self.log("skipped (%s): %s" % (e, os.path.basename(path)))
        except Exception as e:
            fatal = self._note_failure(e)
            tries = self.qs.note_attempt(path)
            if fatal or tries >= MAX_ATTEMPTS:
                # Stop hammering.  The file is NOT marked sent: it stays in
                # the queue so "Retry now" (or a fixed setup) can still
                # deliver it.
                self.qs.give_up(path)
                self.log("giving up after %d attempts: %s - %s"
                         % (tries, os.path.basename(path), e))
            else:
                # Re-queue with a short backoff so a Wi-Fi hiccup recovers in
                # ~30 s instead of waiting for the 10-minute full scan.
                self.qs.queue(path, time.time() + RETRY_SEC)
                self.log("failed (attempt %d/%d, retry in %ds): %s - %s"
                         % (tries, MAX_ATTEMPTS, RETRY_SEC,
                            os.path.basename(path), e))
        finally:
            self.status["current"] = ""
            self.status["progress"] = -1

    def process_batch(self, paths):
        """Send a tick's worth of ready files.

        Screenshots from the SAME game are grouped into Telegram albums
        (up to 10) so a burst produces one notification instead of ten.
        Anything that is not a groupable screenshot goes through the
        normal one-by-one path.
        """
        if not paths:
            return
        s = self.get_settings()
        groups = {}     # appid -> [paths]
        singles = []
        for p in paths:
            if not os.path.isfile(p):
                continue
            appid = captions.appid_from_path(p)
            if (appid and os.path.splitext(p)[1].lower() in media.IMAGE_EXT
                    and s.get("send_screenshots", True)
                    and p not in self.qs.sent
                    and p not in self.qs.no_album):
                groups.setdefault(appid, []).append(p)
            else:
                singles.append(p)

        for appid, files in groups.items():
            files.sort()
            if len(files) < 2:
                singles.extend(files)
                continue
            for i in range(0, len(files), 10):
                self._send_album(appid, files[i:i + 10], s)

        for p in singles:
            self.process_file(p)

    def _send_album(self, appid, files, s):
        caption = captions.album_caption(appid, self.resolver, len(files))
        self.status["current"] = "Sending album: %s" % caption
        try:
            self.destination().send_album(files, caption)
            for p in files:
                self.qs.mark_sent(p)
                self.qs.bump_sent()
                if s.get("delete_after_send"):
                    self._delete_media(p)
            self.status["sent"] = self.qs.sent_count
            self.status["last_sent"] = caption
            self.log("album sent: %s" % caption)
            if s.get("notify_on_send", True):
                self.notify("sent", "Sent", caption)
        except Exception as e:
            # Fall back to per-file sends (with their own retry) next tick.
            fatal = self._note_failure(e)
            with self.qs.lock:
                for p in files:
                    self.qs.no_album.add(p)
                    if not fatal:
                        self.qs.pending[p] = time.time() + RETRY_SEC
            self.log("album failed (%s)%s" %
                     (e, "" if fatal else " - will retry individually"))
        finally:
            self.status["current"] = ""

    # ------------------------------------------------------------------- clips

    def clip_duration(self, clip_dir):
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
        return captions.parse_mpd_duration(text)

    def process_clip(self, clip_dir):
        if not self.ffmpeg_ok:
            return
        clip_id = os.path.basename(clip_dir)
        if clip_id in self.qs.clips_done:
            return
        if time.time() < self.qs.clip_retry_at.get(clip_id, 0):
            return   # backing off after a failure
        s = self.get_settings()
        if not s.get("send_clips", True):
            return
        # Steam writes fragments into SUBdirectories, which does not bump
        # the top dir's mtime - judge "still being written" by the newest
        # file anywhere inside the clip.
        newest = 0
        try:
            for root, _, files in os.walk(clip_dir):
                for f in files:
                    try:
                        m = os.path.getmtime(os.path.join(root, f))
                        if m > newest:
                            newest = m
                    except OSError:
                        pass
        except OSError:
            return
        if newest == 0 or time.time() - newest < CLIP_SETTLE_SEC:
            return  # still being written; next scan will retry
        mpds = glob.glob(os.path.join(clip_dir, "**", "session.mpd"), recursive=True)
        if not mpds:
            self.qs.mark_clip_done(clip_id)
            return

        # Hopeless clips (too long to ever fit under the 50 MB bot limit,
        # ~30+ minutes) are rejected up front, before spending a GB-scale
        # remux on them.
        dur = self.clip_duration(clip_dir)
        if self.destination().hopeless(dur):
            self.qs.mark_clip_done(clip_id)
            self.log("clip skipped up front (too long: %ds): %s" % (dur, clip_id))
            if s.get("notify_on_send", True):
                self.notify("skipped", "Clip not sent",
                            "Too long to fit the upload limit")
            return

        # Remux target lives on disk (state dir), NOT /tmp: SteamOS /tmp is
        # tmpfs, and a long recording remuxed into RAM would fight the
        # running game for memory.
        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False,
                                          dir=self.state_dir)
        tmp.close()
        caption = captions.clip_caption(clip_id, self.resolver)
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
            self.qs.mark_clip_done(clip_id)
            self.qs.bump_sent()
            self.status["sent"] = self.qs.sent_count
            self.status["last_sent"] = caption
            self.log("clip sent: %s" % clip_id)
            if s.get("notify_on_send", True):
                self.notify("sent", "Clip sent", caption)
            if s.get("delete_after_send"):
                self._delete_clip(clip_dir)
        except Unsendable as e:
            self.qs.mark_clip_done(clip_id)
            self.log("clip skipped (%s): %s" % (e, clip_id))
            if s.get("notify_on_send", True):
                self.notify("skipped", "Clip not sent",
                            "Too long to fit the upload limit")
        except Exception as e:
            fatal = self._note_failure(e)
            tries = self.qs.note_attempt(clip_id)
            if fatal or tries >= MAX_ATTEMPTS:
                self.qs.give_up(clip_id)
                # Far future: only an explicit "Retry now" revives it.
                self.qs.clip_retry_at[clip_id] = time.time() + 10 ** 9
                self.log("clip: giving up after %d attempts: %s - %s"
                         % (tries, clip_id, e))
            else:
                self.qs.clip_retry_at[clip_id] = time.time() + RETRY_SEC * 2
                self.log("clip failed (attempt %d/%d, retry in %ds): %s - %s"
                         % (tries, MAX_ATTEMPTS, RETRY_SEC * 2, clip_id, e))
        finally:
            self.status["current"] = ""
            self.status["progress"] = -1
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

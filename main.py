"""Deckygram - send Steam Deck screenshots and clips straight to Telegram.

Backend entry point.  All heavy lifting lives in py_modules/deckygram; this
class only wires settings, the watcher thread and the frontend together.
"""

import asyncio
import json
import os

import decky
from deckygram import destinations, discord, media, tg
from deckygram.appname import AppNameResolver
from deckygram.gallery import Gallery
from deckygram.pairing import PairingServer
from deckygram.updates import UpdateChecker
from deckygram.watcher import Watcher

SETTINGS_FILE = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")


def _plugin_version() -> str:
    try:
        with open(os.path.join(decky.DECKY_PLUGIN_DIR, "package.json"),
                  encoding="utf-8") as f:
            return json.load(f).get("version", "?")
    except Exception:
        return "?"

DEFAULTS = {
    # Telegram is the default destination; Discord is opt-in and needs
    # only a webhook URL (no bot, no token).
    "destination": "telegram",
    "token": "",
    "chat_id": "",
    "webhook_url": "",
    "enabled": False,
    "send_screenshots": True,
    "send_clips": True,
    "notify_on_send": True,
    # How much of the size budget to spend on quality vs length; the
    # bitrate ceiling and frame height come from this (see media.PRESETS).
    "clip_preset": "balanced",
    "video_fps": 30,
    "delete_after_send": False,

}


class Plugin:
    # ------------------------------------------------------------- settings

    def _load(self) -> dict:
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        try:
            os.chmod(SETTINGS_FILE, 0o600)   # the bot token lives here
        except OSError:
            pass

    async def get_settings(self) -> dict:
        s = self._load()
        # Never hand the full secrets to the UI; show enough to recognise them.
        if s["token"]:
            s["token_hint"] = s["token"][:8] + "..." + s["token"][-4:]
        else:
            s["token_hint"] = ""
        url = s.get("webhook_url") or ""
        # A webhook URL ends with its own credential, so only the channel
        # id half is safe to echo back.
        s["webhook_hint"] = url.rsplit("/", 1)[0] + "/..." if url else ""
        # Both credentials are kept side by side, so the UI can offer a
        # straight switch instead of making people pair again.
        s["has_telegram"] = bool(s["token"] and s["chat_id"])
        s["has_discord"] = discord.valid_url(url)
        s.pop("token")
        s.pop("webhook_url", None)
        return s

    async def forget_destination(self, dest: str) -> dict:
        """Erase one destination's stored credentials.

        The bot token and webhook URL sit on the Deck until removed, so
        there has to be a way to remove them - handing the Deck on, or
        just retiring a bot.  If the destination being erased is the
        active one, fall back to whatever is still set up.
        """
        s = self._load()
        if dest == destinations.TELEGRAM:
            s["token"] = ""
            s["chat_id"] = ""
        elif dest == destinations.DISCORD:
            s["webhook_url"] = ""
        else:
            return {"ok": False, "error": "unknown destination"}

        if s.get("destination") == dest:
            other = (destinations.DISCORD if dest == destinations.TELEGRAM
                     else destinations.TELEGRAM)
            s["destination"] = (other if destinations.build(
                dict(s, destination=other)).configured() else dest)
        self._save(s)
        self.watcher.sender.clear_broken()
        self._apply_enabled(s)
        decky.logger.info("forgot %s credentials" % dest)
        return {"ok": True}

    async def set_destination(self, dest: str) -> dict:
        """Switch between destinations that are already set up."""
        s = self._load()
        if dest not in (destinations.TELEGRAM, destinations.DISCORD):
            return {"ok": False, "error": "unknown destination"}
        probe = dict(s, destination=dest)
        if not destinations.build(probe).configured():
            return {"ok": False, "error": "that destination is not set up yet"}
        s["destination"] = dest
        self._save(s)
        self.watcher.sender.clear_broken()
        self._apply_enabled(s)
        decky.logger.info("destination switched to %s" % dest)
        return {"ok": True, "destination": dest}

    async def save_settings(self, patch: dict) -> dict:
        s = self._load()
        for k, v in patch.items():
            if k in DEFAULTS and k not in ("token", "webhook_url"):
                s[k] = v
        self._save(s)
        self._apply_enabled(s)
        return await self.get_settings()

    async def set_webhook(self, url: str) -> dict:
        """Store a Discord webhook URL after proving it works."""
        url = (url or "").strip()
        if not discord.valid_url(url):
            return {"ok": False, "error": "that does not look like a Discord "
                                          "webhook URL"}
        try:
            discord.send_test(url)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        s = self._load()
        s["webhook_url"] = url
        s["destination"] = "discord"
        self._save(s)
        self.watcher.sender.clear_broken()
        self._apply_enabled(s)
        return {"ok": True}

    # ----------------------------------------------------------- onboarding

    async def set_token(self, token: str) -> dict:
        token = token.strip()
        try:
            me = tg.get_me(token)
        except tg.TelegramError as e:
            return {"ok": False, "error": str(e)}
        s = self._load()
        s["token"] = token
        self._save(s)
        self.watcher.sender.clear_broken()   # a new token deserves a new try
        return {"ok": True, "bot_username": me.get("username", "")}

    async def detect_chat(self) -> dict:
        s = self._load()
        if not s["token"]:
            return {"ok": False, "error": "no token"}
        try:
            found = tg.detect_chat_id(s["token"])
        except tg.TelegramError as e:
            return {"ok": False, "error": str(e)}
        if not found:
            return {"ok": False, "error": "no message yet"}
        chat_id, name = found
        s["chat_id"] = chat_id
        self._save(s)
        self.watcher.sender.clear_broken()
        return {"ok": True, "chat_id": chat_id, "name": name}

    async def send_test(self) -> dict:
        dest = destinations.build(self._load())
        if not dest.configured():
            return {"ok": False, "error": "not configured"}
        try:
            dest.test()
            # A working test means whatever was objected to is fixed.
            self.watcher.sender.clear_broken()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # --------------------------------------------------------- phone pairing

    def _accept_token(self, token: str) -> str:
        """Validate + store a token coming from the pairing page."""
        me = tg.get_me(token)          # raises TelegramError when invalid
        s = self._load()
        s["token"] = token.strip()
        self._save(s)
        self.watcher.sender.clear_broken()
        return me.get("username", "")

    def _accept_webhook(self, url: str) -> None:
        """Validate + store a webhook URL coming from the pairing page."""
        url = (url or "").strip()
        if not discord.valid_url(url):
            raise ValueError("that does not look like a Discord webhook URL")
        discord.send_test(url)          # raises when Discord refuses it
        s = self._load()
        s["webhook_url"] = url
        s["destination"] = "discord"
        self._save(s)
        self.watcher.sender.clear_broken()
        self._apply_enabled(s)

    async def start_pairing(self, mode: str = "telegram") -> dict:
        return self.pairing.start(mode)

    async def get_pairing(self) -> dict:
        return dict(self.pairing.state)

    async def stop_pairing(self) -> dict:
        self.pairing.stop()
        return {"ok": True}

    # -------------------------------------------------------------- control

    async def set_enabled(self, enabled: bool) -> dict:
        s = self._load()
        s["enabled"] = bool(enabled)
        self._save(s)
        self._apply_enabled(s)
        return {"ok": True, "enabled": s["enabled"]}

    def _apply_enabled(self, s: dict) -> None:
        ready = bool(s["enabled"] and destinations.build(s).configured())
        if ready:
            self.watcher.start()
        else:
            self.watcher.stop()

    # -------------------------------------------------------------- gallery

    async def gallery_list(self, offset: int = 0, limit: int = 30,
                           kind: str = "all", refresh: bool = False,
                           appids: str = "") -> dict:
        try:
            r = self.gallery.list(offset, limit, kind, refresh, appids)
            qs = self.watcher.qs
            dest = destinations.build(self._load())
            for it in r["items"]:
                # What has already gone out, so nobody re-sends by accident.
                it["sent"] = (os.path.basename(it["id"]) in qs.clips_done
                              if it["kind"] == "clip" else it["id"] in qs.sent)
                # And what cannot go out at all under the current settings -
                # better to show that before it is picked than to skip it
                # afterwards with a toast.
                it["too_long"] = (it["kind"] == "clip"
                                  and dest.hopeless(it.get("seconds", 0)))
            return r
        except Exception as e:
            decky.logger.info("gallery list failed: %s" % e)
            return {"total": 0, "offset": 0, "items": []}

    async def gallery_games(self, kind: str = "all") -> list:
        try:
            return self.gallery.games(kind)
        except Exception as e:
            decky.logger.info("gallery games failed: %s" % e)
            return []

    async def gallery_thumb(self, item_id: str) -> str:
        return self.gallery.thumbnail(item_id)

    # One batch's worth. The UI caps picks at the same number; this is the
    # backstop, since a queue of hundreds would mean hours of encoding.
    MAX_PICKS = 20

    async def gallery_send(self, item_ids: list) -> dict:
        """Queue hand-picked items, bypassing the only-while-on rule."""
        w = self.watcher
        n = 0
        for item in (item_ids or [])[:self.MAX_PICKS]:
            if not os.path.exists(item):
                continue
            # A clip folder holding only a bookmark has nothing to export;
            # the UI greys these out, but do not trust the UI for it.
            if os.path.isdir(item) and not self.gallery._clip_mpd(item):
                continue
            w.qs.force(item)
            if os.path.isdir(item):
                w.qs.clip_retry_at.pop(os.path.basename(item), None)
            else:
                w.qs.queue(item, 0)      # eligible immediately
            n += 1
        # The picker is useful even with sending paused, so make sure the
        # loop is actually running to pick these up.
        s = self._load()
        if n and destinations.build(s).configured():
            w.start()
        decky.logger.info("gallery: queued %d hand-picked item(s)" % n)
        return {"count": n}

    async def retry_queue(self) -> dict:
        return {"count": self.watcher.retry_now()}

    async def skip_queue(self) -> dict:
        return {"count": self.watcher.skip_queued()}

    async def get_status(self) -> dict:
        self.updates.poke()
        st = dict(self.watcher.status)
        st["version"] = self.version
        st.update(self.updates.state)
        try:
            st.update(self.watcher.queue_info())
        except Exception:
            st["queued"] = 0
        s = self._load()
        dest = destinations.build(s)
        st["configured"] = dest.configured()
        st["destination"] = s.get("destination", "telegram")
        st["max_clip_seconds"] = dest.max_clip_seconds()
        st["enabled"] = s["enabled"]
        return st

    # ------------------------------------------------------------ lifecycle

    def _notify(self, kind: str, title: str, body: str) -> None:
        try:
            asyncio.run_coroutine_threadsafe(
                decky.emit("deckygram_event", kind, title, body), self.loop)
        except Exception:
            pass

    async def _main(self):
        self.loop = asyncio.get_event_loop()
        home = decky.DECKY_USER_HOME
        state_dir = decky.DECKY_PLUGIN_RUNTIME_DIR
        os.makedirs(state_dir, exist_ok=True)
        media.TMP_DIR = state_dir  # keep ffmpeg temp files off the RAM-backed /tmp
        resolver = AppNameResolver(home, os.path.join(state_dir, "appnames.json"))
        self.watcher = Watcher(
            home=home,
            state_dir=state_dir,
            settings_getter=self._load,
            resolver=resolver,
            notify=self._notify,
            log=decky.logger.info,
        )
        self.gallery = Gallery(home, state_dir, resolver, log=decky.logger.info)
        self.pairing = PairingServer(self._accept_token, self._accept_webhook,
                                     log=decky.logger.info)
        self.version = _plugin_version()
        self.updates = UpdateChecker(self.version, log=decky.logger.info)
        self._apply_enabled(self._load())
        decky.logger.info("Deckygram loaded")

    async def _unload(self):
        self.watcher.stop()
        self.pairing.stop()
        decky.logger.info("Deckygram unloaded")

    async def _uninstall(self):
        pass

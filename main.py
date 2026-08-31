"""Deckygram - send Steam Deck screenshots and clips straight to Telegram.

Backend entry point.  All heavy lifting lives in py_modules/deckygram; this
class only wires settings, the watcher thread and the frontend together.
"""

import asyncio
import json
import os

import decky
from deckygram import tg
from deckygram.appname import AppNameResolver
from deckygram.pairing import PairingServer
from deckygram.watcher import Watcher

SETTINGS_FILE = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")

DEFAULTS = {
    "token": "",
    "chat_id": "",
    "enabled": False,
    "send_screenshots": True,
    "send_clips": True,
    "notify_on_send": True,
    "video_bitrate": 2_000_000,
    "video_fps": 30,
    "video_maxh": 600,
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
        # Never hand the full token to the UI; show enough to recognise it.
        if s["token"]:
            s["token_hint"] = s["token"][:8] + "..." + s["token"][-4:]
        else:
            s["token_hint"] = ""
        s.pop("token")
        return s

    async def save_settings(self, patch: dict) -> dict:
        s = self._load()
        for k, v in patch.items():
            if k in DEFAULTS and k != "token":
                s[k] = v
        self._save(s)
        self._apply_enabled(s)
        return await self.get_settings()

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
        return {"ok": True, "chat_id": chat_id, "name": name}

    async def send_test(self) -> dict:
        s = self._load()
        if not (s["token"] and s["chat_id"]):
            return {"ok": False, "error": "not configured"}
        try:
            tg.api_call(s["token"], "sendMessage",
                        {"chat_id": s["chat_id"],
                         "text": "Deckygram connected. Screenshots will arrive here."},
                        timeout=15)
            return {"ok": True}
        except tg.TelegramError as e:
            return {"ok": False, "error": str(e)}

    # --------------------------------------------------------- phone pairing

    def _accept_token(self, token: str) -> str:
        """Validate + store a token coming from the pairing page."""
        me = tg.get_me(token)          # raises TelegramError when invalid
        s = self._load()
        s["token"] = token.strip()
        self._save(s)
        return me.get("username", "")

    async def start_pairing(self) -> dict:
        return self.pairing.start()

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
        ready = bool(s["enabled"] and s["token"] and s["chat_id"])
        if ready:
            self.watcher.start()
        else:
            self.watcher.stop()

    async def retry_queue(self) -> dict:
        return {"count": self.watcher.retry_now()}

    async def skip_queue(self) -> dict:
        return {"count": self.watcher.skip_queued()}

    async def get_status(self) -> dict:
        st = dict(self.watcher.status)
        try:
            st.update(self.watcher.queue_info())
        except Exception:
            st["queued"] = 0
        s = self._load()
        st["configured"] = bool(s["token"] and s["chat_id"])
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
        tg.TMP_DIR = state_dir   # keep ffmpeg temp files off the RAM-backed /tmp
        resolver = AppNameResolver(home, os.path.join(state_dir, "appnames.json"))
        self.watcher = Watcher(
            home=home,
            state_dir=state_dir,
            settings_getter=self._load,
            resolver=resolver,
            notify=self._notify,
            log=decky.logger.info,
        )
        self.pairing = PairingServer(self._accept_token, log=decky.logger.info)
        self._apply_enabled(self._load())
        decky.logger.info("Deckygram loaded")

    async def _unload(self):
        self.watcher.stop()
        self.pairing.stop()
        decky.logger.info("Deckygram unloaded")

    async def _uninstall(self):
        pass

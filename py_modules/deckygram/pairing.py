"""Phone pairing: get the bot token onto the Deck without typing it.

The token lives on the user's phone (BotFather chat), and typing 46
characters with the on-screen keyboard is miserable.  So the plugin opens
a tiny one-shot web page on the Deck's LAN address; the user opens it on
their phone, pastes the token there, and the page then deep-links them
straight to their new bot to press START.

Security posture: LAN only, random nonce in the path, single use, dies
after 10 minutes or on success.  The token travels one hop over the local
network and is stored with mode 600 on the Deck.
"""

import html
import http.server
import secrets
import socket
import threading
import time
import urllib.parse

from . import tg

TIMEOUT_SEC = 600

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deckygram</title>
<style>
 body {{ font-family: sans-serif; background:#1a2332; color:#eee;
        display:flex; justify-content:center; padding:24px 16px; }}
 .card {{ max-width:420px; width:100%; }}
 h2 {{ margin:0 0 4px; }} .sub {{ color:#8fa3bf; margin:0 0 20px; }}
 ol {{ padding-left:20px; line-height:1.7; color:#cdd9ea; }}
 input {{ width:100%; box-sizing:border-box; font-size:16px; padding:14px;
         border-radius:8px; border:1px solid #3a4a63; background:#0e1520;
         color:#eee; margin:12px 0; }}
 button, a.btn {{ display:block; width:100%; box-sizing:border-box; text-align:center;
   font-size:17px; padding:14px; border-radius:8px; border:0; cursor:pointer;
   background:#2ea6ff; color:#fff; text-decoration:none; font-weight:600; }}
 .err {{ color:#ff7a7a; margin-top:10px; }}
 .ok {{ color:#7aff9e; }}
 code {{ background:#0e1520; padding:1px 5px; border-radius:4px; }}
 a.btn2 {{ display:block; width:100%; box-sizing:border-box; text-align:center;
   font-size:15px; padding:12px; border-radius:8px; margin:10px 0 4px;
   background:#22314a; color:#9fc3ff; text-decoration:none; font-weight:600;
   border:1px solid #3a4a63; }}
</style></head><body><div class="card">{body}</div></body></html>"""

_FORM = """
<h2>Deckygram</h2>
<p class="sub">Steam Deck pairing / 스팀덱 연결</p>
<ol>
 <li>Open <b>@BotFather</b>'s profile below, tap the big
     <b>Open App</b> button, then choose <b>New bot</b>
     (or just send <code>/newbot</code> in chat)<br>
     아래 버튼으로 <b>@BotFather</b> 프로필을 열고, 큰
     <b>앱 열기</b> 버튼 &rarr; <b>New bot</b> 을 선택하세요
     (채팅으로 <code>/newbot</code> 도 가능)
     <a class="btn2" target="_blank" rel="noopener"
        href="https://t.me/BotFather?profile">Open @BotFather / 봇파더 열기</a></li>
 <li>Fill in the form / 폼을 채웁니다:<br>
     &bull; <b>Bot Name</b> - anything, duplicates fine
     / <b>이름</b>은 아무거나, 중복 가능<br>
     &bull; <b>Username</b> - must <b>end in &quot;bot&quot;</b> and be
     unused by anyone; if taken, try another. e.g. <code>mydeck_shot_bot</code><br>
     &nbsp;&nbsp;<b>아이디</b>는 반드시 <b>bot으로 끝나야</b> 하고 전 세계에서
     유일해야 합니다. 중복이면 다른 이름으로. 예: <code>mydeck_shot_bot</code></li>
 <li>Tap <b>Create Bot</b>, then long-press the token it shows and copy it<br>
     <b>Create Bot</b>을 누르고, 표시된 토큰을 길게 눌러 복사하세요</li>
</ol>
<form method="post">
 <input name="token" placeholder="123456789:ABC..." autocomplete="off">
 <button type="submit">Connect / 연결</button>
</form>
{extra}
"""

_DONE = """
<h2 class="ok">Token accepted! / 토큰 확인 완료!</h2>
<p class="sub">One last step / 마지막 한 단계</p>
<ol>
 <li>Tap the button below to open your bot<br>아래 버튼으로 봇을 엽니다</li>
 <li>Press <b>START</b> in the chat / 대화에서 <b>시작</b>을 누릅니다</li>
 <li>Go back to the Deck - it will finish by itself<br>
     덱으로 돌아가면 자동으로 마무리됩니다</li>
</ol>
<a class="btn" target="_blank" rel="noopener" href="https://t.me/{bot}">Open @{bot}</a>
"""


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class PairingServer:
    """One-shot LAN token intake. State machine: waiting -> done | expired."""

    def __init__(self, on_token, log=None):
        self.on_token = on_token          # callback(token) -> bot_username (or raise)
        self.log = log or (lambda *a: None)
        self._httpd = None
        self._thread = None
        self.state = {"status": "idle", "url": "", "bot_username": "", "error": ""}

    def start(self) -> dict:
        self.stop()
        nonce = secrets.token_urlsafe(6)
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, code, html):
                data = _PAGE.format(body=html).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.rstrip("/") != "/" + nonce:
                    self._reply(404, "<h2>Not found</h2>")
                    return
                self._reply(200, _FORM.format(extra=""))

            def do_POST(self):
                if self.path.rstrip("/") != "/" + nonce:
                    self._reply(404, "<h2>Not found</h2>")
                    return
                length = int(self.headers.get("Content-Length", 0) or 0)
                form = urllib.parse.parse_qs(
                    self.rfile.read(length).decode("utf-8", "replace"))
                token = (form.get("token") or [""])[0].strip()
                try:
                    bot = outer.on_token(token)
                except Exception as e:
                    self._reply(200, _FORM.format(
                        extra='<p class="err">Invalid token / 잘못된 토큰: %s</p>'
                              % html.escape(str(e))))
                    return
                outer.state.update(status="done", bot_username=bot)
                self._reply(200, _DONE.format(bot=bot))
                threading.Thread(target=outer.stop, daemon=True).start()

            def log_message(self, *args):
                pass

        self._httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        port = self._httpd.server_address[1]
        url = "http://%s:%d/%s" % (_lan_ip(), port, nonce)
        self.state = {"status": "waiting", "url": url, "bot_username": "", "error": ""}

        def serve():
            deadline = time.time() + TIMEOUT_SEC
            self._httpd.timeout = 5
            while self._httpd and time.time() < deadline \
                    and self.state["status"] == "waiting":
                try:
                    self._httpd.handle_request()
                except Exception:
                    break
            if self.state["status"] == "waiting":
                self.state["status"] = "expired"
            self.log("pairing server stopped (%s)" % self.state["status"])

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()
        self.log("pairing server at %s" % url)
        return dict(self.state)

    def stop(self):
        httpd, self._httpd = self._httpd, None
        if httpd:
            try:
                httpd.server_close()
            except Exception:
                pass

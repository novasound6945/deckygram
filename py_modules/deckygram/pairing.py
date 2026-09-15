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
import secrets
import socket
import threading
import time
import urllib.parse

from . import tg

TIMEOUT_SEC = 600
MAX_HEADER = 64 * 1024   # a pairing request is tiny; anything larger is junk
MAX_BODY = 64 * 1024

# Spoken over a socket rather than through http.server, which is not
# always there: Decky's prerelease loader ships a trimmed Python and
# importing it took the whole plugin down with ModuleNotFoundError
# (reported 2026-09-15).  What this needs of HTTP is one GET, one POST
# and a Content-Length, so the dependency was not worth the risk.


def _read_request(conn):
    """(method, path, body) from one request, or None if unusable."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk or len(data) > MAX_HEADER:
            return None
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    lines = head.decode("latin-1", "replace").split("\r\n")
    try:
        method, path, _ = lines[0].split(" ", 2)
    except ValueError:
        return None
    length = 0
    for line in lines[1:]:
        key, _, value = line.partition(":")
        if key.strip().lower() == "content-length":
            try:
                length = min(int(value.strip()), MAX_BODY)
            except ValueError:
                length = 0
    body = rest
    while len(body) < length:
        chunk = conn.recv(4096)
        if not chunk:
            break
        body += chunk
    return method, path, body[:length]


def _send(conn, code, body_html):
    data = _PAGE.format(body=body_html).encode("utf-8")
    head = ("HTTP/1.1 %d %s\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n\r\n"
            % (code, "OK" if code == 200 else "Not Found", len(data)))
    conn.sendall(head.encode("latin-1") + data)

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

_FORM_DISCORD = """
<h2>Deckygram</h2>
<p class="sub">Discord webhook / 디스코드 웹훅 연결</p>
<ol>
 <li>In Discord, open the <b>server</b> and <b>channel</b> you want your
     screenshots posted to. It can be a server with only you in it -
     making one is free.<br>
     디스코드에서 스크린샷을 받을 <b>서버</b>와 <b>채널</b>을 엽니다.
     나 혼자만 있는 서버여도 되고, 서버 만들기는 무료입니다.</li>
 <li>Channel name &rarr; <b>Edit Channel</b> &rarr; <b>Integrations</b>
     &rarr; <b>Webhooks</b> &rarr; <b>New Webhook</b><br>
     채널 이름 &rarr; <b>채널 편집</b> &rarr; <b>연동</b> &rarr;
     <b>웹후크</b> &rarr; <b>새 웹후크</b></li>
 <li>Tap <b>Copy Webhook URL</b> and paste it below<br>
     <b>웹후크 URL 복사</b>를 누르고 아래에 붙여넣으세요</li>
</ol>
<form method="post">
 <input name="webhook" placeholder="https://discord.com/api/webhooks/..."
        autocomplete="off">
 <button type="submit">Connect / 연결</button>
</form>
<p class="sub" style="margin-top:14px">Anyone with this URL can post to
that channel, so treat it like a password. It is stored only on your Deck.<br>
이 URL을 가진 사람은 누구나 해당 채널에 글을 올릴 수 있으니 비밀번호처럼
다루세요. 덱에만 저장됩니다.</p>
{extra}
"""

_DONE_DISCORD = """
<h2 class="ok">Connected! / 연결 완료!</h2>
<p class="sub">A test message should be waiting in your channel.<br>
채널에 테스트 메시지가 도착해 있을 겁니다.</p>
<ol>
 <li>Go back to the Deck - it is already set up<br>
     덱으로 돌아가면 설정이 끝나 있습니다</li>
</ol>
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
    """One-shot LAN secret intake. State machine: waiting -> done | expired.

    Serves the Telegram walkthrough by default; `mode="discord"` serves
    the webhook one instead.  Both exist for the same reason: the secret
    lives on the phone and is far too long to retype on the Deck.
    """

    def __init__(self, on_token, on_webhook=None, log=None):
        self.on_token = on_token          # callback(token) -> bot_username (or raise)
        self.on_webhook = on_webhook      # callback(url) -> None (or raise)
        self.log = log or (lambda *a: None)
        self._sock = None
        self._thread = None
        self.state = {"status": "idle", "url": "", "bot_username": "",
                      "mode": "telegram", "error": ""}

    def start(self, mode: str = "telegram") -> dict:
        self.stop()
        nonce = secrets.token_urlsafe(6)
        outer = self
        discord_mode = mode == "discord"

        def handle(conn):
            """One request, one reply, connection closed."""
            req = _read_request(conn)
            if not req:
                return
            method, path, body = req
            if path.split("?")[0].rstrip("/") != "/" + nonce:
                _send(conn, 404, "<h2>Not found</h2>")
                return
            form = _FORM_DISCORD if discord_mode else _FORM
            if method != "POST":
                _send(conn, 200, form.format(extra=""))
                return
            fields = urllib.parse.parse_qs(body.decode("utf-8", "replace"))
            if discord_mode:
                secret = (fields.get("webhook") or [""])[0].strip()
                accept, label = outer.on_webhook, "webhook"
            else:
                secret = (fields.get("token") or [""])[0].strip()
                accept, label = outer.on_token, "token"
            try:
                result = accept(secret)
            except Exception as e:
                note = ('<p class="err">Invalid token / 잘못된 토큰: %s</p>'
                        if label == "token" else
                        '<p class="err">Could not use that webhook / '
                        '웹훅을 사용할 수 없습니다: %s</p>') % html.escape(str(e))
                _send(conn, 200, form.format(extra=note))
                return
            if discord_mode:
                outer.state.update(status="done", bot_username="")
                _send(conn, 200, _DONE_DISCORD)
            else:
                outer.state.update(status="done", bot_username=result)
                _send(conn, 200, _DONE.format(bot=result))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", 0))
        sock.listen(8)
        sock.settimeout(1)
        self._sock = sock
        port = sock.getsockname()[1]
        url = "http://%s:%d/%s" % (_lan_ip(), port, nonce)
        self.state = {"status": "waiting", "url": url, "bot_username": "",
                      "mode": mode, "error": ""}

        def serve():
            deadline = time.time() + TIMEOUT_SEC
            while self._sock is sock and time.time() < deadline \
                    and self.state["status"] == "waiting":
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    # A phone on a flaky network must not hold the one
                    # socket open forever; the next request can wait.
                    conn.settimeout(15)
                    handle(conn)
                except Exception as e:
                    self.log("pairing request failed: %r" % (e,))
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
            if self.state["status"] == "waiting":
                self.state["status"] = "expired"
            self.stop()
            self.log("pairing server stopped (%s)" % self.state["status"])

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()
        self.log("pairing server at %s" % url)
        return dict(self.state)

    def stop(self):
        sock, self._sock = self._sock, None
        if sock:
            try:
                sock.close()
            except OSError:
                pass

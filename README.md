<div align="center">

<img src="assets/logo.png" width="120" alt="Deckygram logo"/>

# Deckygram

**Steam Deck screenshots & clips → your Telegram (or Discord), instantly.**
**스팀덱 스크린샷과 클립을 찍는 순간 텔레그램(또는 디스코드)으로.**

[![Latest release](https://img.shields.io/github/v/release/novasound6945/deckygram?label=release&color=2ea6ff)](https://github.com/novasound6945/deckygram/releases/latest)
[![Build](https://github.com/novasound6945/deckygram/actions/workflows/build.yml/badge.svg)](https://github.com/novasound6945/deckygram/actions)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)
[![Decky](https://img.shields.io/badge/Decky-plugin-6f42c1)](https://decky.xyz)

🇺🇸 [English](#english) · 🇰🇷 [한국어](#한국어)

<table><tr>
<td><img src="docs/panel-main-en.jpg" alt="Deckygram panel in Game Mode" width="360"/></td>
<td><img src="docs/panel-wizard-qr.jpg" alt="QR pairing wizard" width="360"/></td>
<td><img src="docs/telegram-arrival.jpg" alt="Screenshots arriving in Telegram as an album" width="250"/></td>
</tr><tr>
<td align="center"><sub>Quick Access panel / 퀵 액세스 패널</sub></td>
<td align="center"><sub>QR pairing — scan with your phone / 폰으로 찍는 QR 페어링</sub></td>
<td align="center"><sub>…and they arrive as an album / 앨범으로 도착!</sub></td>
</tr></table>

<sub>UI follows your Steam language — shown here in English and 한국어.</sub>

</div>

---

## English

### ✨ What it does

| | |
|---|---|
| ⚡ **Instant** | A screenshot reaches your phone seconds after you press the button — inotify, not polling. |
| 🎮 **Game-aware captions** | Every photo arrives titled with the game's name — Steam games, non-Steam shortcuts (emulators!), even uninstalled ones. |
| 🎬 **Clips without exporting** | Steam's recorded clips are picked up automatically and remuxed losslessly — no manual export step. |
| 🪶 **Light on your game** | Video is compressed on the Deck's hardware H.265 encoder (~7 % CPU). Temp files stay off the RAM-backed `/tmp`. |
| 🔒 **No cloud, no account** | Media goes straight from your Deck to **your own** Telegram bot. Nothing in between. |
| 💬 **Discord too** | Prefer sharing in a Discord channel? Pick it in the wizard and paste a webhook URL — no bot to create. |
| 🖼️ **Pick from the gallery** | A full-screen picker for everything already on the Deck — including anything from before you installed it. Filter by kind or game, select, press X. |
| 📵 **Offline-safe** | Taken offline? Queued and delivered automatically when you're back online. |
| 🧹 **Optional cleanup** | Sent media can be deleted from the Deck to free space. |

### 📦 Install

**Easiest — install from URL.** In Decky settings ⚙️ enable
**Developer mode**, then **Developer → Install plugin from URL** and
paste this (it always points at the newest release):

```
https://github.com/novasound6945/deckygram/releases/latest/download/Deckygram.zip
```

**Or from a ZIP file** — then **Developer → Install plugin from ZIP file**:

> 📥 **Download: [Latest release →](https://github.com/novasound6945/deckygram/releases/latest)** (`Deckygram-vX.Y.Z.zip`)
<sub>(or unpack it into `~/homebrew/plugins/` and restart Decky Loader)</sub>

> ⚠️ **Restart Decky afterwards.** Plugins installed from a URL or a ZIP
> do not appear until Decky restarts, and it does not prompt you
> ([decky-loader#527](https://github.com/SteamDeckHomebrew/decky-loader/issues/527)).
> Use **Settings ⚙️ → Reload/Restart Decky**, or just reboot. Nothing
> works until you do — this is the most common "it didn't install" report.

Then open **Deckygram** in the Quick Access menu (…) — the setup wizard
takes it from there.

### 📱 Setup — bring your phone

The wizard first asks **where media should go**. You only set up the one
you pick. Either way there is no typing on the Deck: it shows a **QR
code**, and the page that opens on your phone takes the secret from
there.

**Telegram** (default, and the fuller option):

1. Scan the QR with your phone — a small page opens on your local network.
2. It walks you through creating a bot with **@BotFather**
   (display name = anything; username must be unique and end in `bot`).
3. Paste the token **on your phone**, tap your bot, press **START**.
4. The Deck finishes by itself. Take a screenshot — it's on your phone.

**Discord** (no bot at all):

1. Scan the QR — the page shows you where the webhook lives.
2. In Discord: channel name → **Edit Channel → Integrations → Webhooks →
   New Webhook → Copy Webhook URL**. A server with only you in it is fine,
   and making one is free.
3. Paste the URL **on your phone**. That's it — a test message proves it
   works and the Deck is set up.

Only media captured **while sending is ON** is sent automatically. Your
existing gallery is never touched — but you can reach into it any time
with **Send from the gallery…**, at the top of the panel: a full-screen
picker with filters for kind and game. **A** picks, **X** sends, **Y**
clears, **L1/R1** page. Up to 20 at a time.

<sub>Discord uploads are capped by the server's tier (10 MB on a free
server, and it follows the **server**, not your Nitro), so clips are
encoded harder and anything over ~3 minutes is skipped. Screenshots are
nowhere near the limit.</sub>

### ⚙️ Good to know

- **Requirements**: a Steam Deck on stock SteamOS — nothing to install
  separately. Clips are picked up whenever Steam saves one — **background
  recording and manual (on-demand) recording both work**; just don't leave
  Settings → Game Recording on *Never record*. `ffmpeg` ships with
  SteamOS; if it's ever missing, the plugin says so and screenshots keep
  working.
- Screenshot bursts arrive as **one album** (one notification), not a
  ping per shot.
- Clips are compressed to fit, so length and quality trade against each
  other. **Clip quality** picks where on that curve you sit — on the
  default, Telegram takes clips up to ~12 minutes and Discord ~2m20s;
  anything longer is skipped up front with a toast.
  <details><summary>What each <b>Clip quality</b> preset gives you</summary>

  | Preset | Bitrate ceiling | Height | Telegram | Discord |
  |---|---|---|---|---|
  | Quality first | 3 Mbps | 800p (480p) | up to 6m07s | up to 1m13s |
  | **Balanced** | 2 Mbps | 600p (480p) | up to 11m54s | up to 2m22s |
  | Length first | 1.2 Mbps | 480p (360p) | up to 19m10s | up to 3m50s |

  Heights in brackets are what Discord uses — its budget is a ninth of
  Telegram's, so the frame has to come down further to spend the bitrate
  well. The ceiling only binds on short clips; longer ones are limited by
  the size budget instead.
  </details>
- Failed sends retry automatically (30 s backoff, up to 5 attempts).
  After that Deckygram stops trying but **keeps the media** — press
  **Retry now** once the problem is fixed. If Telegram rejects the bot
  itself (token regenerated, bot deleted or blocked), sending is
  suspended and the panel offers **Set up again**.
- The plugin checks GitHub for new releases. The update button
  **downloads the ZIP onto the Deck** (into `~/Downloads`), so updating is
  just Decky → Developer → Install plugin from ZIP file, then a restart —
  no browsing to a download page in Game Mode.
- UI follows your Steam language (English / 한국어 today — PRs welcome).

### 🔧 Troubleshooting

| Symptom | Check |
|---|---|
| Installed it, but Deckygram isn't in the menu | **Restart Decky.** URL and ZIP installs only appear after a restart, with no prompt ([decky-loader#527](https://github.com/SteamDeckHomebrew/decky-loader/issues/527)). |
| Pairing page won't open on the phone | Phone and Deck must be on the **same Wi-Fi**; router "AP/client isolation" blocks it. Use *Type the token manually* as fallback. |
| "Invalid token" | Copy the whole token from BotFather (`123456:ABC...`), no spaces. |
| "no message yet" | Open your bot in Telegram and press **START**, then tap detect again. |
| Clips never send | Settings → **Game Recording** must not be on *Never record* (background or manual recording both work) — and a clip only exists once you **save/stop** it. Clips longer than the limit shown under **Clip quality** are skipped (toast shown). |
| "Telegram rejected this bot" | The token was regenerated, the bot deleted, or you blocked it in Telegram. Press **Set up again**; queued media is kept and goes out once it works. |
| "Discord rejected this webhook" | The webhook or its channel was deleted. Make a new webhook and press **Change destination**. |
| Discord clips get skipped | A free server caps uploads at 10 MB, so clips over ~3 minutes can't fit. Boosting the server raises the cap. |
| Anything else | Logs live in `~/homebrew/logs/Deckygram/` — attach the newest file to a GitHub issue along with the version shown in the panel. |

---

## 한국어

### ✨ 뭐 하는 플러그인인가요

| | |
|---|---|
| ⚡ **즉시 전송** | 스크린샷 버튼을 누르면 몇 초 안에 폰에 도착합니다 — 폴링이 아니라 inotify 감시. |
| 🎮 **게임 이름 캡션** | 모든 사진에 게임 이름이 붙어서 옵니다 — 스팀 게임, 비스팀 바로가기(에뮬레이터!), 지운 게임까지. |
| 🎬 **클립 내보내기 불필요** | 스팀 녹화 클립을 자동으로 감지해 무손실로 변환·전송합니다. 수동 내보내기 없음. |
| 🪶 **게임에 부담 없음** | 영상은 덱의 하드웨어 H.265 인코더로 압축(CPU 약 7%). 임시 파일도 램(/tmp)이 아닌 디스크에. |
| 🔒 **클라우드·계정 없음** | 미디어는 덱에서 **내 소유의** 텔레그램 봇으로 직행합니다. 중간에 아무것도 없습니다. |
| 💬 **디스코드도 지원** | 디스코드 채널에서 공유하시나요? 마법사에서 고르고 웹훅 URL만 붙여넣으면 됩니다 — 봇 만들 필요 없습니다. |
| 🖼️ **갤러리에서 골라 보내기** | 기기에 있는 모든 미디어를 전체 화면으로 — 설치 전에 찍은 것도 포함. 종류·게임으로 걸러 고르고 X 버튼으로 전송. |
| 📵 **오프라인 안전** | 오프라인일 때 찍은 건 대기해 두었다가 온라인 복귀 시 자동 전송됩니다. |
| 🧹 **선택적 정리** | 보낸 미디어를 덱에서 자동 삭제해 공간을 확보할 수 있습니다. |

### 📦 설치

**가장 쉬운 방법 — URL로 설치.** Decky 설정 ⚙️ 에서 **개발자 모드**를
켜고, **개발자 → URL에서 플러그인 설치**에 아래 주소를 붙여넣으세요
(항상 최신 릴리스를 가리킵니다):

```
https://github.com/novasound6945/deckygram/releases/latest/download/Deckygram.zip
```

**또는 ZIP 파일로** — 받은 뒤 **개발자 → ZIP 파일에서 플러그인 설치**:

> 📥 **다운로드: [최신 릴리스 →](https://github.com/novasound6945/deckygram/releases/latest)** (`Deckygram-vX.Y.Z.zip`)
<sub>(또는 `~/homebrew/plugins/` 에 직접 풀고 Decky Loader 재시작)</sub>

> ⚠️ **설치 후 Decky를 반드시 재시작하세요.** URL이나 ZIP으로 설치한
> 플러그인은 Decky를 재시작하기 전까지 목록에 나타나지 않는데, 안내
> 메시지도 뜨지 않습니다
> ([decky-loader#527](https://github.com/SteamDeckHomebrew/decky-loader/issues/527)).
> **설정 ⚙️ → Decky 다시 불러오기/재시작**을 하거나 재부팅하세요.
> 재시작 전까지는 아무것도 동작하지 않습니다 — "설치가 안 된다"는
> 문의의 대부분이 이것입니다.

설치 후 퀵 액세스 메뉴(…)에서 **Deckygram** 을 열면 설정 마법사가
안내합니다.

### 📱 설정 — 폰만 있으면 됩니다

마법사가 **어디로 보낼지** 먼저 묻습니다. **선택한 쪽만 설정**하면
됩니다. 어느 쪽이든 덱에서 타이핑할 일은 없습니다 — **QR 코드**를
띄우고, 폰에서 열린 페이지가 값을 받아옵니다.

**텔레그램** (기본값, 기능이 더 많은 쪽):

1. 폰으로 QR을 찍으면 같은 네트워크의 안내 페이지가 열립니다.
2. **@BotFather** 로 봇 만드는 과정을 단계별로 안내합니다
   (대표 이름은 아무거나, 아이디는 중복 불가·`bot`으로 끝나야 함).
3. 토큰을 **폰에서** 붙여넣고, 내 봇을 열어 **시작**을 누릅니다.
4. 나머지는 덱이 알아서 끝냅니다. 스샷 한 장 찍어보세요 — 폰에 와 있습니다.

**디스코드** (봇 자체가 필요 없음):

1. QR을 찍으면 웹훅을 어디서 만드는지 안내합니다.
2. 디스코드에서: 채널 이름 → **채널 편집 → 연동 → 웹후크 → 새 웹후크
   → 웹후크 URL 복사**. 나 혼자만 있는 서버여도 되고, 서버 만들기는
   무료입니다.
3. URL을 **폰에서** 붙여넣으면 끝입니다 — 테스트 메시지로 확인까지
   하고 덱 설정이 마무리됩니다.

**전송이 켜져 있는 동안** 찍은 것만 자동으로 보냅니다. 기존 갤러리는
건드리지 않지만, 패널 맨 위의 **갤러리에서 보내기…** 로 언제든 꺼내
보낼 수 있습니다 — 종류·게임 필터가 있는 전체 화면 목록입니다.
**A** 선택, **X** 전송, **Y** 전체해제, **L1/R1** 페이지 이동.
한 번에 최대 20개.

<sub>디스코드 업로드 용량은 서버 등급을 따릅니다(무료 서버 10MB, 내
Nitro가 아니라 **서버** 기준). 그래서 클립을 더 세게 압축하고 약 3분이
넘으면 건너뜁니다. 스크린샷은 한도 근처에도 가지 않습니다.</sub>

### ⚙️ 알아두면 좋은 것

- **요구사항**: 순정 SteamOS 스팀덱이면 끝 — 따로 설치할 게 없습니다.
  클립은 스팀이 저장하는 순간 감지합니다 — **백그라운드 녹화, 수동
  녹화 모두 지원**하며, 설정 → 게임 녹화가 *녹화 안 함*으로만 되어
  있지 않으면 됩니다. `ffmpeg`는 SteamOS에 기본 포함이며, 혹시 없으면
  플러그인이 알려주고 스크린샷 전송은 계속 동작합니다.
- 연속 스크린샷은 **앨범 하나**(알림 1번)로 도착합니다 — 장마다
  울리지 않습니다.
- 클립은 용량에 맞춰 압축되므로 길이와 화질이 서로 맞바꿔집니다.
  **클립 화질** 설정으로 그 지점을 고릅니다 — 기본값 기준 텔레그램은
  약 12분, 디스코드는 약 2분 20초까지 보내고, 더 길면 처음부터
  건너뛰며 토스트로 알려줍니다.
  <details><summary><b>클립 화질</b> 프리셋별 실제 값</summary>

  | 프리셋 | 비트레이트 상한 | 해상도 | 텔레그램 | 디스코드 |
  |---|---|---|---|---|
  | 화질 우선 | 3 Mbps | 800p (480p) | 6분 07초까지 | 1분 13초까지 |
  | **균형** | 2 Mbps | 600p (480p) | 11분 54초까지 | 2분 22초까지 |
  | 길이 우선 | 1.2 Mbps | 480p (360p) | 19분 10초까지 | 3분 50초까지 |

  괄호 안은 디스코드에서 쓰는 해상도입니다. 예산이 텔레그램의 9분의 1이라
  같은 비트레이트를 제대로 쓰려면 화면을 더 줄여야 합니다. 상한은 짧은
  클립에서만 걸리고, 긴 클립은 용량 예산이 먼저 제한합니다.
  </details>
- 전송 실패는 30초 간격으로 **최대 5회** 자동 재시도합니다. 그 뒤에는
  시도를 멈추지만 **미디어는 보관**하므로, 문제를 해결한 뒤
  **[지금 재시도]**를 누르면 전송됩니다. 텔레그램이 봇 자체를 거부하면
  (토큰 재발급·봇 삭제·차단) 전송을 중단하고 **다시 설정하기** 버튼을
  표시합니다.
- 새 릴리스가 나오면 업데이트 버튼이 표시되고, 누르면 **ZIP을 덱에
  내려받습니다**(`~/Downloads`). 그다음 Decky → 개발자 → ZIP 파일에서
  플러그인 설치로 고르고 재시작하면 끝입니다 — 게임 모드 브라우저로
  다운로드 페이지를 헤맬 필요가 없습니다.
- UI는 스팀 언어를 따라갑니다 (현재 영어/한국어 — 번역 PR 환영).

### 🔧 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 설치했는데 메뉴에 Deckygram이 없음 | **Decky를 재시작하세요.** URL·ZIP 설치는 재시작 후에야 목록에 나타나며 안내도 뜨지 않습니다 ([decky-loader#527](https://github.com/SteamDeckHomebrew/decky-loader/issues/527)). |
| 폰에서 페어링 페이지가 안 열림 | 폰과 덱이 **같은 와이파이**여야 합니다. 공유기의 "AP 격리/기기 간 통신 차단"이 막을 수 있어요. 안 되면 *토큰 직접 입력*으로. |
| "잘못된 토큰" | BotFather가 준 토큰 전체(`123456:ABC...`)를 공백 없이 복사했는지 확인. |
| "아직 메시지가 없습니다" | 텔레그램에서 내 봇을 열어 **시작**을 누른 뒤 다시 감지. |
| 클립이 전혀 안 옴 | 설정 → **게임 녹화**가 *녹화 안 함*이면 안 됩니다(백그라운드·수동 녹화 모두 지원). 클립은 **저장/녹화 종료**해야 생깁니다. **클립 화질** 설정에 표시된 길이를 넘는 클립은 건너뜁니다(토스트 표시). |
| "텔레그램이 이 봇을 거부했습니다" | 토큰이 재발급되었거나, 봇을 삭제했거나, 텔레그램에서 봇을 차단한 경우입니다. **다시 설정하기**를 누르세요. 대기 중이던 미디어는 보관되어 있다가 정상화되면 전송됩니다. |
| "디스코드가 이 웹훅을 거부했습니다" | 웹훅이나 해당 채널이 삭제된 경우입니다. 웹훅을 새로 만든 뒤 **보낼 곳 바꾸기**를 누르세요. |
| 디스코드에서 클립이 계속 건너뛰어짐 | 무료 서버는 업로드가 10MB로 제한되어 약 3분이 넘는 클립은 담을 수 없습니다. 서버를 부스트하면 한도가 올라갑니다. |
| 그 외 | 로그는 `~/homebrew/logs/Deckygram/` 에 있습니다 — 최신 파일과 패널의 버전을 GitHub 이슈에 첨부해 주세요. |

---

<details>
<summary><b>Development / 개발</b></summary>

```bash
npm install
npm run build        # builds dist/index.js
```

Backend is dependency-free Python (stdlib only) in `py_modules/deckygram/`:

| module | job |
|---|---|
| `watcher.py` | folder discovery, the inotify/poll loop, and the control surface (start/stop, queue stats, retry, skip) |
| `sender.py` | the send pipeline: albums, clip remux, retry budget, failure classification, delete-after-send |
| `qstate.py` | what was sent, what stalled, the pending queue and its burst/settle rules — persisted |
| `captions.py` | caption strings and DASH manifest parsing (pure functions) |
| `gallery.py` | the picker: index, per-page listing, thumbnails and cached clip posters |
| `destinations.py` | picks Telegram or Discord; nothing above this layer names a service |
| `tg.py` / `discord.py` | the two backends — Bot API, and webhook uploads |
| `media.py` | ffprobe + the HEVC→H.264→x264 encode ladder, to a size budget the caller passes in |
| `net.py` | TLS context and multipart uploads |
| `pairing.py` | one-shot LAN pairing page (nonce path, 10-min lifetime), Telegram and Discord walkthroughs |
| `appname.py` | appid → game name (appmanifest, shortcuts.vdf incl. 24/64-bit id forms, store API, cached) |

Tests live in `tests/` (stdlib `unittest`) and run in CI. Locally:

```bash
python3 -m unittest discover -s tests -t .
```

Releases: bump `package.json`, then push a `v*` tag — CI builds and
attaches `Deckygram.zip`.

Notes: the bot token and webhook URL are stored mode-600 in Decky's
settings dir and never returned to the UI in full. Telegram compresses
inline photos; originals stay on the Deck unless delete-after-send is
enabled.

</details>

---

<div align="center">
<sub>
Built by <a href="https://github.com/novasound6945">novasound6945</a> together with
<b>Claude (Fable 5)</b> by Anthropic — designed, written and field-tested on a
real Steam Deck in one long pair-programming session.<br>
<a href="https://github.com/novasound6945">novasound6945</a>가 Anthropic의
<b>Claude (Fable 5)</b>와 함께 만들었습니다 — 실제 스팀덱 위에서 설계·구현·검증한
페어 프로그래밍의 결과물입니다.
</sub>
</div>

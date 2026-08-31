<div align="center">

<img src="assets/logo.png" width="120" alt="Deckygram logo"/>

# Deckygram

**Steam Deck screenshots & clips → your Telegram, instantly.**
**스팀덱 스크린샷과 클립을 찍는 순간 텔레그램으로.**

[![Latest release](https://img.shields.io/github/v/release/novasound6945/deckygram?label=release&color=2ea6ff)](https://github.com/novasound6945/deckygram/releases/latest)
[![Build](https://github.com/novasound6945/deckygram/actions/workflows/build.yml/badge.svg)](https://github.com/novasound6945/deckygram/actions)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)](LICENSE)
[![Decky](https://img.shields.io/badge/Decky-plugin-6f42c1)](https://decky.xyz)

[English](#english) · [한국어](#한국어)

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
| 📵 **Offline-safe** | Taken offline? Queued and delivered automatically when you're back online. |
| 🧹 **Optional cleanup** | Sent media can be deleted from the Deck to free space. |

### 📦 Install (ZIP)

1. Download **`Deckygram-vX.Y.Z.zip`** from the [**latest release**](https://github.com/novasound6945/deckygram/releases/latest).
2. In Decky settings ⚙️ enable **Developer mode**, then
   **Developer → Install plugin from ZIP file** and pick the zip.
   <sub>(or unpack it into `~/homebrew/plugins/` and restart Decky Loader)</sub>
3. Open **Deckygram** in the Quick Access menu (…) — the setup wizard
   takes it from there.

### 📱 Setup — bring your phone

No typing on the Deck. The wizard shows a **QR code**:

1. Scan it with your phone — a small page opens on your local network.
2. It walks you through creating a bot with **@BotFather**
   (display name = anything; username must be unique and end in `bot`).
3. Paste the token **on your phone**, tap your bot, press **START**.
4. The Deck finishes by itself. Take a screenshot — it's on your phone.

Only media captured **while sending is ON** is sent. Your existing
gallery is never touched.

### ⚙️ Good to know

- Clips too long to fit Telegram's 50 MB bot limit (~30 min+) are
  skipped up front — you'll get a toast.
- Failed sends retry automatically (30 s backoff); the panel also has
  **Retry now** / **Skip queued** buttons.
- UI follows your Steam language (English / 한국어 today — PRs welcome).

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
| 📵 **오프라인 안전** | 오프라인일 때 찍은 건 대기해 두었다가 온라인 복귀 시 자동 전송됩니다. |
| 🧹 **선택적 정리** | 보낸 미디어를 덱에서 자동 삭제해 공간을 확보할 수 있습니다. |

### 📦 설치 (ZIP)

1. [**최신 릴리스**](https://github.com/novasound6945/deckygram/releases/latest)에서 **`Deckygram-vX.Y.Z.zip`** 을 내려받습니다.
2. Decky 설정 ⚙️ 에서 **개발자 모드**를 켜고,
   **개발자 → ZIP 파일에서 플러그인 설치**로 zip을 선택합니다.
   <sub>(또는 `~/homebrew/plugins/` 에 직접 풀고 Decky Loader 재시작)</sub>
3. 퀵 액세스 메뉴(…)에서 **Deckygram** 을 열면 설정 마법사가
   안내합니다.

### 📱 설정 — 폰만 있으면 됩니다

덱에서 타이핑할 일이 없습니다. 마법사가 **QR 코드**를 띄웁니다:

1. 폰으로 QR을 찍으면 같은 네트워크의 안내 페이지가 열립니다.
2. **@BotFather** 로 봇 만드는 과정을 단계별로 안내합니다
   (대표 이름은 아무거나, 아이디는 중복 불가·`bot`으로 끝나야 함).
3. 토큰을 **폰에서** 붙여넣고, 내 봇을 열어 **시작**을 누릅니다.
4. 나머지는 덱이 알아서 끝냅니다. 스샷 한 장 찍어보세요 — 폰에 와 있습니다.

**전송이 켜져 있는 동안** 찍은 것만 보냅니다. 기존 갤러리는 절대
건드리지 않습니다.

### ⚙️ 알아두면 좋은 것

- 텔레그램 봇 한도(50MB)에 맞출 수 없는 긴 클립(약 30분+)은 처음부터
  건너뛰고 토스트로 알려줍니다.
- 전송 실패는 30초 간격으로 자동 재시도되고, 패널에
  **지금 재시도** / **건너뛰기** 버튼도 있습니다.
- UI는 스팀 언어를 따라갑니다 (현재 영어/한국어 — 번역 PR 환영).

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
| `watcher.py` | inotify watch loop, debounce, clip polling, retry backoff, delete-after-send, queue stats |
| `tg.py` | Bot API (stdlib multipart), HEVC→H.264→x264 encode ladder with live progress, pre-flight length check |
| `pairing.py` | one-shot LAN pairing page (nonce path, 10-min lifetime) with the BotFather walkthrough |
| `appname.py` | appid → game name (appmanifest, shortcuts.vdf incl. 24/64-bit id forms, store API, cached) |

Releases: push a `v*` tag — CI builds and attaches `Deckygram.zip`.

Notes: the bot token is stored mode-600 in Decky's settings dir and never
returned to the UI in full. Telegram compresses inline photos; originals
stay on the Deck unless delete-after-send is enabled.

</details>

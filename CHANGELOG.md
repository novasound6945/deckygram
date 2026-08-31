# Changelog

All notable changes to Deckygram. / Deckygram의 주요 변경 사항입니다.

## v0.3.0

### Added / 추가
- **Send from the gallery.** A full-screen picker for everything already
  on the Deck — including media from before Deckygram was installed,
  which the watcher can never reach on its own. Thumbnail grid, filters
  for kind and game, paging, multi-select, and X to send.
  **갤러리에서 보내기.** 기기에 있는 모든 미디어를 전체 화면에서 골라
  보냅니다 — 설치 전에 찍은 것까지. 감시 기능만으로는 닿을 수 없던
  것들입니다. 썸네일 그리드, 종류·게임 필터, 페이징, 다중 선택,
  X 버튼으로 전송.
- **Switch destinations without pairing again.** Both credentials are
  kept side by side, so moving between Telegram and Discord is one press.
  A setup can also be erased, which was not possible before.
  **재설정 없이 목적지 전환.** 양쪽 자격증명을 함께 보관하므로 텔레그램과
  디스코드를 버튼 한 번으로 오갑니다. 설정 삭제도 가능해졌습니다.

### Fixed / 수정
- A clip picked in the gallery was re-sent on every ten-second scan, each
  time re-encoding and re-uploading it. The flag that lets a pick bypass
  the already-sent guard is keyed by path while clips are recorded by
  folder name, so settling one never cleared it.
  갤러리에서 고른 클립이 10초마다 재전송되며 매번 재인코딩·재업로드되던
  문제. 강제 플래그는 경로로, 완료 기록은 폴더 이름으로 관리되어 플래그가
  풀리지 않았습니다.
- Clip thumbnails fall back to the opening frame when a DASH manifest
  refuses to seek, and one that cannot be made at all shows a placeholder
  instead of spinning forever.
  DASH 매니페스트 탐색이 실패하는 클립의 썸네일 폴백, 생성 불가 시
  무한 스피너 대신 대체 아이콘 표시.
- The version line at the bottom of the panel was clipped: SteamOS
  scrolls only as far as the focused element, and a plain text row cannot
  take focus.
  패널 하단 버전 표시가 잘리던 문제. 스팀은 포커스 가능한 요소까지만
  스크롤합니다.
- The gallery lays itself out for the current UI scale rather than
  assuming 1280 px wide, so the tile grid reflows instead of overflowing.
  갤러리가 UI 배율에 맞춰 타일 열 수를 조정합니다.

## v0.2.1

### Added / 추가
- **Clip quality presets.** A clip has a fixed size budget, so quality and
  length trade against each other; rather than ask for numbers nobody can
  judge, there are now three points on that curve — *Quality first*,
  *Balanced* (default) and *Length first*. The panel shows the longest
  clip the current choice will take.
  **클립 화질 프리셋.** 클립은 용량 상한이 정해져 있어 화질과 길이가 서로
  맞바꿔집니다. 숫자를 직접 고르게 하는 대신 *화질 우선* / *균형*(기본) /
  *길이 우선* 세 가지를 제공하며, 현재 설정으로 보낼 수 있는 최대 길이를
  패널에 표시합니다.

| Preset / 프리셋 | Bitrate | Height | Telegram | Discord |
|---|---|---|---|---|
| Quality first / 화질 우선 | 3 Mbps | 800p (480p) | 6m07s | 1m13s |
| **Balanced / 균형** | 2 Mbps | 600p (480p) | 11m54s | 2m22s |
| Length first / 길이 우선 | 1.2 Mbps | 480p (360p) | 19m10s | 3m50s |

- Short clips now get a **higher bitrate**. The old fixed 2 Mbps cap left
  quality on the table: at a minute, Telegram's budget affords about
  6 Mbps, so the ceiling was raised (to 3 Mbps — beyond that H.265 stops
  paying for itself on an 800p capture).
  짧은 클립에 **더 높은 비트레이트**를 씁니다. 기존 2Mbps 고정은 여유
  예산을 놀리고 있었습니다(1분이면 텔레그램은 약 6Mbps까지 가능).

### Changed / 변경
- The status section lists **what's queued above what's being worked on**,
  so reading it top to bottom follows the media instead of jumping back.
  While a clip is encoding, the panel says so — it is not stuck.
  상태 영역에서 **대기 항목을 작업 중보다 위에** 배치했습니다. 클립을
  인코딩하는 중에는 그 사실을 안내합니다 — 멈춘 게 아닙니다.

### Fixed / 수정
- **The documented clip limit was wrong.** The README said Telegram took
  clips up to ~30 minutes; measured, the real cutoff was ~12 minutes. The
  figures now come from the same maths the plugin uses.
  **문서의 클립 길이 한계가 틀렸습니다.** README에 텔레그램 약 30분까지로
  적혀 있었으나 실제로는 약 12분이었습니다. 이제 플러그인이 쓰는 계산과
  같은 값을 표기합니다.

## v0.2.0

### Added / 추가
- **Discord as an alternative destination.** The setup wizard now starts
  by asking where media should go; you only set up the one you pick, so
  choosing Discord skips the Telegram bot flow entirely. A webhook URL is
  the whole credential — no bot, no account setup — and the phone pairing
  page takes it from your phone the same way it takes a bot token.
  Telegram remains the default and the recommended option.
  **디스코드를 대안 목적지로 추가.** 마법사가 어디로 보낼지 먼저 묻고,
  **선택한 쪽만 설정**하면 됩니다 — 디스코드를 고르면 텔레그램 봇 과정을
  건너뜁니다. 웹훅 URL 하나가 전부이고(봇도 계정 설정도 없음), 폰
  페어링 페이지가 토큰과 같은 방식으로 폰에서 가져옵니다. 기본값과
  권장은 계속 텔레그램입니다.
- Clips work on Discord too, encoded to that server's tighter budget
  (9 MB, 480p); anything over roughly three minutes is skipped with a
  toast, as it cannot fit at watchable quality.
  디스코드에서도 클립을 보냅니다. 더 빡빡한 예산(9MB, 480p)에 맞춰
  인코딩하며, 약 3분이 넘으면 볼 만한 화질로 담을 수 없어 건너뜁니다.

### Removed / 제거
- **Screenshots in original quality.** Measured on hardware, the gain was
  96,865 vs 80,133 bytes at identical resolution — real but too small to
  justify a toggle most people would never touch.
  **스크린샷 원본 화질 옵션을 제거했습니다.** 실측 결과 같은 해상도에서
  96,865 대 80,133바이트로, 차이는 있지만 토글을 유지할 만큼은
  아니었습니다.

### Fixed / 수정
- Every HTTP request now sends a real User-Agent. Discord's Cloudflare
  edge rejects urllib's default outright (403, error 1010), so webhook
  sends failed until this was set.
  모든 HTTP 요청이 제대로 된 User-Agent를 보냅니다. 디스코드의
  Cloudflare가 urllib 기본값을 차단(403, 오류 1010)해서 웹훅 전송이
  실패하던 문제입니다.
- Documented that **URL and ZIP installs need a Decky restart** before
  the plugin appears — Decky does not prompt, and reloading the frontend
  does not help ([decky-loader#527](https://github.com/SteamDeckHomebrew/decky-loader/issues/527)).
  **URL·ZIP 설치 후 Decky 재시작이 필요하다**는 점을 문서에 명시했습니다.

## v0.1.6

### Changed / 변경
- **Sending failures no longer retry forever.** Each item now gets up to
  **5 attempts**; after that it stops trying and the panel says so. The
  media is *not* written off — it stays on the Deck and in the queue, so
  **Retry now** (or a repaired setup) still delivers it, even across a
  restart.
  **전송 실패 시 무한 재시도하지 않습니다.** 항목당 **최대 5회**까지만
  시도하고, 이후에는 중단하고 패널에 표시합니다. 미디어는 버려지지 않고
  기기와 대기열에 그대로 남아, **[지금 재시도]**를 누르거나 설정을
  고치면 (재시작 후에도) 전송됩니다.
- **Telegram's own rejections are told apart from network errors.** A
  revoked token, a deleted bot, a blocked bot or a missing chat now
  suspends sending immediately — retrying cannot fix those — and shows a
  **Telegram rejected this bot** warning with a *Set up again* button.
  Recovery is automatic: it re-tests every 10 minutes, and any successful
  setup step clears it.
  **텔레그램의 거부와 네트워크 오류를 구분합니다.** 토큰 재발급, 봇 삭제,
  봇 차단, 대화 없음은 재시도로 해결되지 않으므로 즉시 전송을 중단하고
  **다시 설정하기** 버튼과 함께 경고를 표시합니다. 10분마다 자동으로
  재확인하며, 설정을 고치면 바로 복구됩니다.
- Rate limiting (429) now honours the wait Telegram asks for instead of
  retrying straight into it.
  전송 제한(429)에 걸리면 텔레그램이 요청한 대기 시간을 지킵니다.

## v0.1.5

### Added / 추가
- **Screenshots in original quality** — a new toggle (off by default) that
  sends screenshots as files instead of photos, so Telegram cannot
  re-compress them. Measured on a Deck screenshot: 96,865 bytes as a file
  vs 80,133 bytes as a photo, both at the full 1280x800 — the difference
  is real but modest, so the photo grid remains the default.
  **스크린샷 원본 화질** — 스크린샷을 사진이 아닌 파일로 보내 텔레그램의
  재압축을 막는 토글(기본 꺼짐). 실측: 같은 스크린샷이 파일로는
  96,865바이트, 사진으로는 80,133바이트(둘 다 1280×800 그대로)로,
  차이는 있지만 크지 않아 기본값은 사진 전송을 유지합니다.

### Fixed / 수정
- Turning sending off and on again left the plugin **watching nothing**:
  the inotify watch table was never reset, so no folder was re-registered
  while the panel still reported "Watching N folders". New screenshots
  were only picked up by the 10-minute safety scan.
  전송을 껐다 켜면 **감시가 하나도 등록되지 않던 문제**. 패널에는
  "폴더 N곳 감시 중"으로 보이지만 실제로는 10분 주기 전체 스캔에만
  의존하고 있었습니다.
- Queue counts said "1 screenshots"; now "1 screenshot(s)".
  대기 항목 개수의 영문 복수형 표기 수정.
- The phone pairing page opened scrolled past its own instructions.
  폰 페어링 페이지가 안내문을 지나쳐 스크롤된 채 열리던 문제.

### Changed / 변경
- Clip documentation no longer claims background recording is required —
  **manual recording works too**; only *Never record* prevents clips.
  클립 안내를 수정했습니다. 백그라운드 녹화뿐 아니라 **수동 녹화도
  지원**하며, *녹화 안 함*으로 설정된 경우에만 클립이 생기지 않습니다.
- The backend was split into focused modules (`watcher` orchestration,
  `sender`, `qstate`, `captions`, `inotify`) and now ships with 45 unit
  tests that run in CI. No behaviour change intended.
  백엔드를 역할별 모듈로 분리하고 단위 테스트 45개를 CI에 연결했습니다.
  동작 변경은 없습니다.

## v0.1.4

- README: English and Korean screenshots, one-line download link, flag
  icons on the language nav.
- Published wizard screenshots were sanitized: they had contained a
  scannable pairing QR and the Deck's LAN address.

## v0.1.3

### Added / 추가
- Screenshot bursts are delivered as a **single album** (one notification
  instead of one per shot).
  연속 스크린샷을 **앨범 하나**로 전송 (알림도 1번).
- **Update check** — the panel shows a button when a newer release exists,
  since ZIP installs have no update channel of their own.
  **업데이트 확인** — 새 릴리스가 있으면 패널에 버튼이 표시됩니다.
- Status section: what is being worked on (Encoding / Sending with a
  percentage), what is queued (images and clips, with sizes), plus
  **Retry now**, **Skip all** and **Refresh**.
  상태 섹션: 현재 작업(인코딩/전송 + 퍼센트), 전송 대기 항목(이미지·클립,
  용량 포함), **지금 재시도** / **모두 건너뛰기** / **새로고침** 버튼.
- Sent counter persists across restarts.
  보낸 개수가 재시작 후에도 유지됩니다.

### Fixed / 수정
- Failed sends retry after 30 s instead of waiting for the 10-minute scan.
  전송 실패 시 10분 스캔을 기다리지 않고 30초 뒤 재시도합니다.
- Clip conversion no longer runs in RAM-backed `/tmp`.
  클립 변환이 램 디스크(`/tmp`)가 아닌 실제 디스크에서 이루어집니다.
- Recorded clips could be picked up mid-write; a clip is now judged
  finished by the newest file anywhere inside it.
  녹화 중인 클립을 전송하려던 문제 수정.
- Chat detection no longer misses a `/start` buried behind a backlog.
  채팅 감지가 밀린 메시지에 묻힌 `/start`를 놓치지 않습니다.

## v0.1.0 – v0.1.2

First public releases: instant screenshot and clip delivery with
game-name captions, QR phone pairing, hardware H.265 compression,
delete-after-send, English/Korean UI.
최초 공개 릴리스: 게임 이름 캡션과 함께 스크린샷·클립 즉시 전송, QR 폰
페어링, 하드웨어 H.265 압축, 전송 후 삭제, 영어·한국어 UI.

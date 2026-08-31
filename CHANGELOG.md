# Changelog

All notable changes to Deckygram. / Deckygram의 주요 변경 사항입니다.

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

# Changelog

All notable changes to Deckygram. / Deckygram의 주요 변경 사항입니다.

## v0.7.2

### Fixed / 수정

- Clips were broken on Decky Loader v3.2.9 even though the plugin
  loaded: no thumbnails in the gallery, and no clip could be exported or
  sent. Decky's loader is packed with PyInstaller, which points
  `LD_LIBRARY_PATH` at its own unpacked libraries, and every ffmpeg we
  started inherited it - loading Decky's older libstdc++ instead of the
  one it was built against. External commands now run with the system
  environment restored.
  Decky Loader v3.2.9에서 플러그인은 로드되지만 클립이 동작하지 않던
  문제. 갤러리 썸네일이 뜨지 않고 클립을 내보내거나 전송할 수도
  없었습니다. Decky 로더는 PyInstaller로 묶여 있어 `LD_LIBRARY_PATH`가
  자기 라이브러리를 가리키는데, 우리가 띄우는 ffmpeg가 그걸 물려받아
  시스템 라이브러리 대신 Decky의 낡은 libstdc++를 집었습니다. 이제 외부
  명령은 시스템 환경으로 되돌려 실행합니다.

- Silent notifications were never silent. `playSound: false` is dropped
  on the way to Steam, which picks the sound from a table keyed on the
  notification type rather than from anything a plugin passes, so the
  toast rang whatever the setting said. It borrows a type registered as
  silent now, and looks exactly the same.
  무음 알림이 실제로는 무음이 아니었습니다. `playSound: false`는 스팀으로
  전달되는 과정에서 버려지고, 스팀은 플러그인이 넘긴 값이 아니라 알림
  종류별 표를 보고 소리를 정합니다. 설정과 무관하게 소리가 났습니다. 이제
  소리 없는 종류를 사용하며, 토스트 모양은 그대로입니다.

### Changed / 변경

- Clip tiles use the thumbnail Steam already writes beside each clip
  instead of decoding a frame, which is four times quicker and gives a
  tile to clips whose fragments are unusable. A poster that cannot be
  made now says why in the log rather than leaving a blank tile.
  클립 타일이 프레임을 디코딩하는 대신 스팀이 클립마다 만들어 두는
  썸네일을 씁니다. 4배 빠르고, 조각이 깨진 클립도 타일이 생깁니다.
  포스터를 만들지 못하면 빈 타일로 두지 않고 이유를 로그에 남깁니다.

## v0.7.1

### Fixed / 수정

- **Decky Loader v3.2.9 compatibility - update to this if you have
  updated Decky.** The plugin imported `http.server`, which that build
  no longer ships, so it failed to start at all. The pairing page is
  served over a plain socket now and needs no such module. inotify also
  falls back to polling if `ctypes` is ever missing, rather than taking
  the plugin down with it.
  **Decky Loader v3.2.9 대응 — Decky를 업데이트했다면 이 버전으로
  올리세요.** `http.server`를 가져다 썼는데 해당 빌드에는 들어 있지 않아
  플러그인이 아예 시작되지 않았습니다. 이제 페어링 페이지를 소켓으로
  직접 제공해 그 모듈이 필요 없습니다. `ctypes`가 없는 경우에도 inotify가
  폴링으로 내려갈 뿐 플러그인을 죽이지 않습니다.

- The queue said a minute of video weighed under a megabyte when the
  bitrate was set to "as recorded".
  비트레이트가 "원본 그대로"일 때 1분짜리 영상이 1MB 미만으로 표시되던
  문제.

### Added / 추가

- A resolution ceiling: 800p, 720p, 600p or 480p. Lower is often the
  better trade for something watched on a phone.
  해상도 상한 선택(800p / 720p / 600p / 480p). 폰으로 볼 영상이라면
  낮추는 쪽이 대체로 이득입니다.

## v0.7.0

### Changed / 변경

- Clip quality is a bitrate and a frame rate now, instead of
  quality/balanced/reach. Pick from as recorded / 7.5 / 6 / 3.75 Mbps
  and 30 / 60 fps; the panel shows how long the choice holds and what a
  60-second clip weighs. Old settings map to as recorded / 6 / 3.75.
  클립 화질이 프리셋 대신 비트레이트와 프레임 수가 됐습니다. 원본 그대로
  / 7.5 / 6 / 3.75 Mbps, 30 / 60 fps 중에서 고르면 몇 초까지 유지되는지,
  60초 클립이 몇 MB인지 표시됩니다. 기존 설정은 각각 원본 그대로 / 6 /
  3.75로 이어집니다.

- Clips are capped at 800p, the Deck's own height. Only docked
  recordings are affected.
  클립을 덱 화면 높이인 800p로 제한합니다. 독에 연결해 녹화한 경우에만
  영향이 있습니다.

### Added / 추가

- 60 fps clips.
  60fps 전송.

- The gallery's options menu acts on the tile under the cursor when
  nothing is selected.
  갤러리 옵션 메뉴가, 선택한 항목이 없으면 커서 위의 항목에 동작합니다.

### Fixed / 수정

- The cursor no longer jumps to the top of the panel after using a
  dropdown.
  드롭다운을 쓴 뒤 커서가 패널 맨 위로 튀지 않습니다.

- A 30 fps recording sent at 60 fps is no longer padded with duplicate
  frames.
  30fps 녹화를 60fps로 보낼 때 프레임을 복제하지 않습니다.

## v0.6.2

### Added / 추가

- **Silent notifications.** Sends happen while you are playing, and with
  background recording on, that means the notification chime lands in
  whatever is being recorded. The toast still appears - seeing that a
  clip went out is the useful part - it just makes no sound. Steam's own
  interface sounds are separate and stay where they belong, under
  Settings > Audio > Enable UI Sounds.
  **알림 소리 끄기.** 전송은 게임하는 도중에 일어나고, 백그라운드 녹화가
  켜져 있으면 그 알림음이 녹화 영상에 그대로 들어갑니다. 토스트는 그대로
  표시됩니다. 클립이 나갔다는 걸 보는 건 유용하니까요. 소리만 나지
  않습니다. 스팀 자체 UI 사운드는 별개이며 설정 → 오디오 → UI 사운드
  사용에서 끕니다.

## v0.6.1

### Added / 추가

- **Clips are found when the recordings folder has been moved.** Steam's
  Settings > Game Recording can put recordings on an SD card, and it
  moves the whole tree when you do - clips, timelines and the clip index
  all follow. Only the default location under `userdata` was ever
  looked at, so those clips were invisible. The configured folder is now
  read from Steam's own settings, and the old location keeps being
  watched too, because recordings made before the move stay where they
  were. Screenshots are unaffected either way: that setting covers
  recordings only.
  **녹화 폴더를 옮겨도 클립을 찾습니다.** 스팀 설정 → 게임 녹화에서
  녹화 위치를 SD카드로 지정할 수 있는데, 이때 클립·타임라인·클립 인덱스가
  전부 함께 옮겨갑니다. 그동안 `userdata` 기본 위치만 봤기 때문에 그
  클립들이 보이지 않았습니다. 이제 스팀 설정에서 지정된 폴더를 직접 읽고,
  기존 위치도 계속 감시합니다. 옮기기 전에 녹화한 클립은 원래 자리에
  남기 때문입니다. 스크린샷은 어느 쪽이든 영향이 없습니다. 그 설정은
  녹화에만 적용됩니다.

### Fixed / 수정

- **A clip Steam failed to save is skipped instead of erroring.** When
  saving a clip fails partway, Steam can leave the folder behind with a
  readable manifest and an empty `init-stream0.m4s`. ffmpeg then refused
  it once a minute, forever. Such a clip is now recognised as having no
  usable video and set aside for good.
  **스팀이 저장에 실패한 클립을 오류 대신 건너뜁니다.** 클립 저장이 중간에
  실패하면 스팀이 폴더만 남기고 `init-stream0.m4s`를 빈 파일로 두는
  경우가 있습니다. 그러면 ffmpeg가 1분마다 계속 거부했습니다. 이제 쓸 수
  있는 영상이 없는 클립으로 판단해 한 번만 건너뜁니다.

## v0.6.0

### Added / 추가

- **An options menu in the gallery, on the ☰ button.** Deleting had no
  shortcut - you had to walk to a button. Pick what you want, press ☰,
  and choose from there. The menu also carries the new preview.
  **갤러리에 ☰ 버튼으로 여는 옵션 메뉴.** 삭제에 단축키가 없어 버튼까지
  이동해야 했습니다. 항목을 고른 뒤 ☰를 누르면 거기서 바로 선택할 수
  있습니다. 새로 추가된 미리보기도 이 메뉴에 있습니다.

- **Preview, for looking at one item large.** Clips show their still
  frame; playback and trimming are where this is headed. The window
  sizes itself to the screen, so it is not cut off at the bottom on a
  Deck's own resolution.
  **항목 하나를 크게 보는 미리보기.** 클립은 정지 화면으로 보여줍니다.
  재생과 편집이 다음 목표입니다. 창이 화면 크기에 맞춰지므로 덱 해상도
  에서 아래가 잘리지 않습니다.

- **A picked item that cannot be sent now shows a red ✕, not a blue ✓,**
  and an item waiting to be deleted after its upload says so. Selecting
  something unsendable looked exactly like selecting something sendable.
  **전송할 수 없는 항목을 고르면 파란 ✓ 대신 빨간 ✕가 표시되고,**
  전송 후 삭제를 기다리는 항목은 그 사실을 알려줍니다. 전에는 전송
  가능한 것을 고른 것과 구분이 되지 않았습니다.

- **Send screenshots as files, keeping the original.** Telegram re-encodes
  anything sent as a photo, so a screenshot arrived as a JPEG built from
  your PNG. The new toggle sends it as a file instead - the same choice
  the Telegram app offers - and the bytes arrive untouched. Off by
  default, because a photo still previews inline in the chat and a file
  does not. Discord has no such switch: a webhook upload was always the
  original. A screenshot too large for Telegram's photo endpoint now goes
  as a file rather than being rejected.
  **스크린샷을 원본 파일로 보내는 선택지.** 텔레그램은 사진으로 받은
  것을 다시 인코딩하기 때문에, PNG로 찍은 스크린샷이 JPEG로 도착했습니다.
  새 옵션을 켜면 파일로 보내 원본 그대로 도착합니다. 텔레그램 앱의 "파일로
  보내기"와 같습니다. 기본값은 꺼짐입니다. 사진으로 보내야 대화창에서
  바로 보이기 때문입니다. 디스코드는 웹훅 업로드가 원래부터 원본이라 이
  옵션이 없습니다. 텔레그램 사진 한도를 넘는 큰 스크린샷도 이제 거절되지
  않고 파일로 전송됩니다.

### Fixed / 수정

- **A clip could arrive three seconds long.** Clips were exported by
  handing Steam's `session.mpd` manifest to ffmpeg. A clip that covers
  only part of a recording session carries its offset into that
  session's timeline - `<Period start="PT27.739S">` - and ffmpeg honours
  it by writing a single fragment: three seconds, exit code 0, a
  perfectly valid file, so nothing downstream could tell. Background
  recording hits this constantly, since a rolling buffer is always
  longer than the slice you keep, but it is the slicing that does it and
  not the mode: a manual recording trimmed to a window breaks the same
  way. Fragments are now joined directly and the manifest is read only
  for its duration - which is then checked against the exported file, so
  a truncated export can never be sent again. Verified across 74 clips
  on a Steam Deck: the three affected (two background, one manual) went
  from 3 s to their full length, the other 71 were unchanged.
  **클립이 3초짜리로 도착하던 문제.** 클립을 내보낼 때 스팀의
  `session.mpd` 매니페스트를 ffmpeg에 넘겼는데, 녹화 세션의 일부만
  잘라낸 클립에는 세션 타임라인상의 시작 오프셋
  (`<Period start="PT27.739S">`)이 들어 있습니다. ffmpeg가 이를 존중해
  조각 하나만 기록했고, 결과물이 3초짜리 정상 파일이라 이후 어디에서도
  걸러지지 않았습니다. 백그라운드 녹화는 버퍼가 늘 잘라낸 구간보다 길어
  거의 항상 해당되지만, 원인은 녹화 모드가 아니라 잘라냄 자체입니다.
  수동 녹화도 구간을 잘라내면 똑같이 깨집니다. 이제 조각을 직접
  이어붙이고 매니페스트는 길이를 읽는 데만 쓰며, 그 길이를 결과물과
  대조하므로 짧게 잘린 클립은 전송되지 않습니다. 스팀덱에서 클립 74개로
  검증했습니다. 해당 3개(백그라운드 2, 수동 1)는 3초에서 원래 길이로
  복구됐고 나머지 71개는 그대로입니다.

## v0.5.1

### Fixed / 수정

- **A deleted clip stayed in the gallery until you hit refresh.** The list
  was rebuilt from disk the moment the delete was requested - but Steam
  had not deleted anything yet, so the clip was read straight back in.
  Screenshots happened to survive this because their deletion lands in a
  few hundred milliseconds; a clip, whose fallback removal waits out a
  grace period, came back every time. Deleted items now leave the grid on
  the request itself, so it no longer depends on timing at all.
  **삭제한 클립이 새로고침 전까지 갤러리에 남아 있던 문제.** 삭제를
  요청한 즉시 목록을 디스크에서 다시 읽는데, 그 시점엔 스팀이 아직 지우지
  않아 그대로 다시 읽혔습니다. 스크린샷은 삭제가 빨라 우연히 넘어갔고,
  폴백까지 유예가 있는 클립은 매번 되살아났습니다. 이제 요청 시점에
  목록에서 빠지므로 타이밍에 기대지 않습니다.

### Changed / 변경

- Media that cannot be deleted yet, because it is in the middle of being
  sent, now says so on the tile: **deleting after send**. Greyed out with
  no explanation, it read as a delete that had failed.
  전송 중이라 아직 지울 수 없는 항목에 **"전송 후 삭제 예정"**을
  표시합니다. 설명 없이 회색으로만 두면 삭제가 실패한 것처럼 보입니다.

## v0.5.0

### Added / 추가

- **Delete media from the gallery.** Pick what you want gone and press
  Delete: it is removed from the Deck and from Steam's media list in one
  go. The gallery already had multi-select, per-game and per-kind filters,
  which makes clearing out a year of screenshots a good deal less tedious
  than doing it one tile at a time.
  **갤러리에서 미디어 삭제.** 지울 것을 골라 삭제를 누르면 기기와 스팀
  미디어 목록에서 함께 사라집니다. 갤러리에는 다중 선택과 게임·종류
  필터가 이미 있어서, 한 장씩 지우는 것보다 훨씬 수월합니다.

  Deleting is permanent, so it is a button you have to aim at - no gamepad
  shortcut - and it asks once, with the count, before doing anything.
  되돌릴 수 없는 동작이라 컨트롤러 단축키를 두지 않았고, 개수를 보여주는
  확인 창을 한 번 거칩니다.

- **Anything mid-send is deleted after it lands, not now.** Delete
  something that is queued or uploading and the send finishes first, then
  the file goes. Pulling a file out from under its own upload would just
  fail the send, and one selection can hold both kinds at once - the
  result says which was which ("3 deleted · 2 after sending").
  **전송 중이거나 대기 중인 항목은 전송이 끝난 뒤 삭제됩니다.** 업로드
  도중에 파일을 치우면 그 전송이 실패하기 때문입니다. 한 번의 선택에 두
  종류가 섞일 수 있고, 결과를 구분해 알려줍니다("3개 삭제 · 2개는 전송 후
  삭제"). 이 예약은 저장되므로 그 사이 플러그인이 재시작되어도 잊히지
  않습니다.

- **A tidy-up button** in the panel: clears entries Steam still lists for
  media that is gone, refreshes its media list, and removes leftover
  working files.
  패널에 **정리 버튼**. 스팀 목록에 남은 유령 항목을 지우고, 목록을 새로
  읽게 하고, 남은 임시 파일을 치웁니다.

### Changed / 변경

- **Media picked in the gallery is never auto-deleted**, even with
  delete-after-sending on. The gallery is for reaching into what is
  already on the Deck; losing an old screenshot because you shared it is
  a poor surprise. Pressing Delete is of course still a request to delete.
  **갤러리에서 고른 미디어는 자동삭제되지 않습니다**(자동삭제가 켜져
  있어도). 공유했다고 옛 스크린샷이 사라지는 건 당황스러운 결과니까요.
  물론 삭제 버튼을 누르는 건 별개입니다.
- A clip Steam saved as a bookmark has no video in it and cannot be sent -
  but that is the kind of clip most worth deleting, so it can be picked
  now. Picked, it shows a red cross rather than the blue tick, because a
  blue tick promises a send that will not happen.
  영상이 없는 북마크 클립은 보낼 수 없지만 오히려 가장 지우고 싶은
  대상이라, 이제 선택할 수 있습니다. 선택하면 파란 체크가 아니라 **빨간
  X**로 표시됩니다 — 파란 체크는 "이건 나갑니다"라는 약속이니까요.
- The gallery keeps up with what leaves the Deck: anything sent or deleted
  while it is open drops out of your selection and out of the list.
  갤러리가 기기 상태를 따라갑니다. 열어둔 사이에 전송·삭제된 항목은
  선택에서도 목록에서도 빠집니다.

### Fixed / 수정

- Cached clip posters were never removed, so every clip ever deleted left
  one behind for good. Swept at startup and by the tidy button.
  삭제된 클립의 썸네일 캐시가 정리되지 않고 계속 쌓이던 문제. 시작할
  때와 정리 버튼으로 치웁니다.
- Deleting an item left its queue, retry and stalled bookkeeping behind.
  A stalled entry kept counting towards "N items gave up" and kept its
  line on disk, naming a file that no longer existed.
  항목을 삭제해도 대기열·재시도·중단 기록이 남아, 없는 파일이 "N개
  중단됨"으로 계속 세어지던 문제.
- The English and Korean descriptions of delete-after-sending were missing
  the sentence the other eight languages had, about gallery picks being
  exempt.
  "보낸 뒤 삭제" 설명에서 영어·한국어만 갤러리 예외 문장이 빠져 있던 문제.

## v0.4.1

### Fixed / 수정

- **Deleting after sending left broken tiles in Steam's Media tab.** The
  file went, Steam's own record of it did not, and the grid drew a warning
  triangle where the picture used to be - permanently, surviving restarts.
  Reported by a user; it turned out to be four separate problems stacked
  on each other, and all four are fixed:
  **전송 후 자동삭제가 스팀 미디어 탭에 깨진 타일을 남기던 문제.** 파일은
  지워지는데 스팀이 가진 기록은 남아, 사진이 있던 자리에 경고 삼각형이
  떴습니다. 재시작해도 사라지지 않았습니다. 사용자 제보로 시작해 파보니
  네 가지 원인이 겹쳐 있었고, 모두 수정했습니다.

  | | |
  |---|---|
  | Steam is asked to delete, instead of being told afterwards | Its list only forgets an entry when it deleted the file itself; going behind its back left the entry pointing at nothing. 스팀은 자기가 지웠을 때만 목록에서 뺍니다 |
  | Delete calls are serialised | Five at once came back three successes and two silent failures. 다섯 건을 동시에 던지면 두 건이 조용히 실패했습니다 |
  | The screenshot list is refreshed after a delete | Clips live in a store the grid watches; screenshots come from a cache only the deleting code updates. 클립과 스크린샷의 구조가 달랐습니다 |
  | Entries orphaned by earlier versions are swept on load | So a Deck that already collected broken tiles comes back clean. 이미 쌓인 것도 정리됩니다 |

- **The same clip could be delivered several times.** Telegram accepts a
  large upload and can still answer 504; that was read as failure and the
  clip was sent again. One 43 MB clip arrived five times. A timeout or a
  5xx *after* the upload is now treated as "outcome unknown": the media is
  kept, nothing is resent, and the panel says to check the chat first. A
  connection that never reached the server still retries as before.
  **같은 클립이 여러 번 도착하던 문제.** 텔레그램은 큰 파일을 다 받고도
  504를 돌려줄 수 있는데, 이를 실패로 보고 다시 보냈습니다(43MB 클립이
  5번 도착). 이제 **업로드를 마친 뒤의** 타임아웃·5xx는 "결과 불명"으로
  보고 재전송하지 않으며, 채팅을 먼저 확인하도록 안내합니다. 서버에 닿지도
  못한 경우는 지금처럼 자동 재시도합니다.

- **Abandoned compression temp files piled up.** Stopping the plugin
  mid-encode orphaned the working file; 254 MB of them were found on one
  Deck. They are cleared at startup and by the new tidy button.
  **인코딩 중 중단되면 임시 파일이 쌓이던 문제** (한 기기에서 254MB 발견).
  시작할 때와 정리 버튼으로 치웁니다.

- **Upload timeouts scale with the payload.** A flat ten minutes was sized
  for a 45 MB clip and applied to 200 KB screenshots too, so a slow moment
  at the server left the panel on "Sending" for what looked like a freeze.
  A screenshot now gives up after about a minute and moves on to its retry.
  **업로드 타임아웃이 크기에 비례합니다.** 45MB 클립 기준의 10분 고정값이
  200KB 스크린샷에도 걸려, 서버가 느려지면 멈춘 것처럼 보였습니다.

### Added / 추가

- **A tidy-up button** in the panel: clears entries Steam still lists for
  media that is gone, refreshes its media list, and removes leftover temp
  files. The automatic cleanup runs at the right moments; this is for when
  you want it now.
  패널에 **정리 버튼**을 추가했습니다. 스팀 목록에 남은 유령 항목을 지우고,
  목록을 새로 읽게 하고, 남은 임시 파일을 치웁니다.

### Changed / 변경

- **Media picked in the gallery is never deleted**, even with delete-after-
  sending on. The gallery is for reaching into what is already on the Deck;
  having an old screenshot vanish because you shared it is a poor surprise.
  The setting still applies to everything sent automatically.
  **갤러리에서 직접 고른 미디어는 삭제하지 않습니다** (자동삭제가 켜져
  있어도). 갤러리는 기기에 이미 있는 것을 꺼내 보는 곳인데, 공유했다고
  옛 스크린샷이 사라지는 건 당황스러운 결과입니다. 자동 전송분에는 설정이
  그대로 적용됩니다.
- The gallery keeps up with what leaves the Deck: anything sent or deleted
  while it is open is greyed out and drops out of your selection, so you
  cannot queue the same shot twice or get stuck with a pick you cannot
  clear.
  갤러리가 기기 상태를 따라갑니다. 열어둔 사이에 전송·삭제된 항목은 회색
  처리되고 선택에서도 빠져, 같은 것을 두 번 보내거나 해제할 수 없는 선택에
  갇히는 일이 없습니다.
- The "send test message" button is gone from the panel; the setup wizard
  still sends one.
  패널의 "테스트 메시지 보내기" 버튼을 제거했습니다(설정 마법사의 테스트는
  유지).

## v0.4.0

### Added / 추가
- **Eight more UI languages**, bringing the total to ten: Deutsch,
  Français, Русский, Português (BR), Polski, Türkçe, 简体中文 and 繁體中文,
  alongside English and 한국어. There is nothing to switch on — the panel
  and the gallery follow your Steam language, and anything not on the list
  still falls back to English.
  **UI 언어 8종 추가** — 기존 영어·한국어에 독일어, 프랑스어, 러시아어,
  포르투갈어(브라질), 폴란드어, 터키어, 중국어 간체·번체가 더해져 총
  10개 언어를 지원합니다. 설정할 것은 없습니다. 패널과 갤러리가 스팀
  언어를 그대로 따라가며, 목록에 없는 언어는 영어로 표시됩니다.

  Most Steam Decks are not in English-speaking hands: after the US, UK and
  Canada, the largest populations are in China, Russia, Germany, Brazil,
  Poland, Turkey and France. Every one of them was reading a plugin in a
  language they had not chosen.
  스팀덱 사용자의 다수는 영어권이 아닙니다. 미국·영국·캐나다 다음으로
  큰 시장이 중국, 러시아, 독일, 브라질, 폴란드, 터키, 프랑스인데, 이들
  모두가 자신이 고르지 않은 언어로 플러그인을 보고 있었습니다.

  Simplified and Traditional Chinese are separate translations rather than
  one converted at runtime, because the terminology differs beyond the
  script — a token is 令牌 in one and 權杖 in the other.
  중국어는 간체·번체를 각각 번역했습니다. 글자만 다른 것이 아니라 용어가
  달라서입니다 — token이 한쪽은 令牌, 다른 쪽은 權杖입니다.

### Fixed / 수정
- Locale matching accepts both the tags Steam reports (`pt-BR`) and its own
  language names (`brazilian`), and normalises `zh_TW` to `zh-TW`. Full
  tags are matched before the bare language, so Traditional Chinese no
  longer collapses into Simplified.
  스팀이 보고하는 태그(`pt-BR`)와 자체 명칭(`brazilian`)을 모두 인식하고
  `zh_TW` 같은 표기도 정규화합니다. 전체 태그를 먼저 대조하므로 중국어
  번체가 간체로 잘못 빠지지 않습니다.

### Internal / 내부
- Translations are covered by tests: every dictionary must carry exactly
  the English key set and the same `{placeholders}` per key. With ten
  languages, a missing key is invisible to us and shows up only as stray
  English on someone else's Deck, and a translated placeholder renders as
  a literal `{n}`.
  번역을 테스트로 강제합니다. 모든 사전이 영어와 키 집합·플레이스홀더가
  정확히 일치해야 합니다. 언어가 10개가 되면 키 누락은 우리 화면에
  보이지 않고 남의 기기에서만 영어로 새어 나오며, 플레이스홀더를 같이
  번역하면 화면에 `{n}`이 그대로 찍힙니다.

## v0.3.1

### Changed / 변경
- **The update button now downloads the ZIP** to the Deck rather than
  opening a web page. Decky can install from a local file but cannot
  fetch one, and driving Game Mode's browser to a download was the
  worst part of updating. It lands in `~/Downloads`, the button says so,
  and it sits at the top of the panel where you cannot miss it — install
  from Decky → Developer → Install plugin from ZIP file, then restart.
  **업데이트 버튼이 웹페이지 대신 ZIP을 직접 내려받습니다**(`~/Downloads`).
  Decky는 로컬 ZIP 설치는 되지만 다운로드는 못 하고, 게임 모드
  브라우저로 받는 게 업데이트에서 가장 번거로운 부분이었습니다. 버튼은
  패널 맨 위에 표시됩니다.

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

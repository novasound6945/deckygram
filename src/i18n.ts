/**
 * Tiny i18n: follows the Steam client's UI language automatically.
 *
 * Steam exposes its locale list on window.LocalizationManager; we fall back
 * to navigator.language outside the Steam context. Unknown languages get
 * English. Adding a language = adding one object below.
 */

type Dict = Record<string, string>;

const en: Dict = {
  setup: "Setup",
  pair_with_phone: "Set up with your phone (recommended)",
  pair_desc:
    "Open this address in your phone's browser. It walks you through creating the bot and takes the token straight from your phone - no typing on the Deck.",
  pair_waiting: "Waiting for your phone...",
  pair_expired: "Pairing timed out. Start again.",
  pair_manual: "Type the token manually instead",
  back_to_main: "Back (keep current setup)",
  step1_label: "1. Create a bot",
  step1_desc:
    "In Telegram open @BotFather and send /newbot. It asks two names: first a display name (shown at the top of the chat - anything goes, duplicates fine), then a username (the unique @handle - must end in \"bot\"; if taken, try another). Paste the token it gives you below.",
  bot_token: "Bot token",
  checking: "Checking...",
  validate_token: "Validate token",
  invalid_token: "Invalid token: ",
  step2_label: "2. Say hi to your bot",
  step2_desc: "Open @{bot} in Telegram and send /start. Then tap the button below.",
  looking: "Looking...",
  detect_chat: "Detect my chat",
  no_message_yet:
    "No message yet - open @{bot} in Telegram and send /start, then tap again.",
  connected_to: "Connected to {name}",
  error_prefix: "Error: ",
  sending: "Sending...",
  send_test_step: "3. Send test message",
  send_failed: "Send failed: ",
  test_sent: "Test message sent!",
  loading: "Loading...",
  send_to_telegram: "Send to Telegram",
  watching_folders: "Watching {n} folders",
  paused: "Paused",
  what_to_send: "What to send",
  screenshots: "Screenshots",
  recorded_clips: "Recorded clips",
  notify_toggle: "Show a toast for each send",
  only_new_note:
    "Only media captured while sending is ON gets sent - anything taken while paused stays on the Deck. If you're offline, sends are retried automatically once you're back online. Clips too long to fit under Telegram's 50 MB bot limit are skipped (you'll get a toast).",
  delete_after: "Delete from Deck after sending",
  delete_after_desc:
    "Frees space once media is safely in Telegram. Removed items disappear from the Steam gallery.",
  status: "Status",
  version: "Version",
  update_available: "Update available: {v}",
  open_release: "Open download page",
  ffmpeg_missing: "ffmpeg not found on this system - clip sending is disabled (screenshots still work)",
  now_working: "Working on",
  queued: "Waiting to send",
  queue_images: "{n} screenshots ({size})",
  queue_clips: "{n} clips (~{size})",
  idle: "Idle",
  refresh: "Refresh",
  retry_now: "Retry now",
  skip_queued: "Skip all",
  sent: "Sent",
  last_sent: "Last sent",
  last_error: "Last error",
  send_test: "Send test message",
  failed_prefix: "Failed: ",
  rerun_setup: "Re-run setup",
  no_token: "no token",
};

const ko: Dict = {
  setup: "설정",
  pair_with_phone: "폰으로 설정하기 (권장)",
  pair_desc:
    "폰 브라우저로 이 주소를 여세요. 봇 만드는 과정을 안내하고, 토큰도 폰에서 바로 붙여넣습니다 - 덱에서 입력할 필요가 없습니다.",
  pair_waiting: "폰에서 입력을 기다리는 중...",
  pair_expired: "시간이 지났습니다. 다시 시작하세요.",
  pair_manual: "토큰을 직접 입력할래요",
  back_to_main: "돌아가기 (기존 설정 유지)",
  step1_label: "1. 봇 만들기",
  step1_desc:
    "텔레그램에서 @BotFather 에게 /newbot 을 보내세요. 이름을 두 번 묻습니다: 먼저 대표 이름(대화방 상단에 뜨는 이름 - 아무거나, 중복 가능), 다음 아이디(유일해야 하는 @주소 - 반드시 \"bot\"으로 끝나야 하며, 중복이면 다른 것으로 재시도). 받은 토큰을 아래에 붙여넣으세요.",
  bot_token: "봇 토큰",
  checking: "확인 중...",
  validate_token: "토큰 확인",
  invalid_token: "잘못된 토큰: ",
  step2_label: "2. 봇에게 인사하기",
  step2_desc: "텔레그램에서 @{bot} 을 열어 /start 를 보낸 뒤, 아래 버튼을 누르세요.",
  looking: "찾는 중...",
  detect_chat: "내 대화 찾기",
  no_message_yet:
    "아직 메시지가 없습니다 - @{bot} 에게 /start 를 보낸 뒤 다시 누르세요.",
  connected_to: "{name} 님과 연결됨",
  error_prefix: "오류: ",
  sending: "보내는 중...",
  send_test_step: "3. 테스트 메시지 보내기",
  send_failed: "전송 실패: ",
  test_sent: "테스트 메시지를 보냈습니다!",
  loading: "불러오는 중...",
  send_to_telegram: "텔레그램으로 보내기",
  watching_folders: "폴더 {n}곳 감시 중",
  paused: "일시정지됨",
  what_to_send: "보낼 항목",
  screenshots: "스크린샷",
  recorded_clips: "녹화 클립",
  notify_toggle: "전송 결과 알림 표시",
  only_new_note:
    "전송이 켜져 있는 동안 찍은 것만 보냅니다 - 꺼져 있는 동안 찍은 미디어는 기기에만 남습니다. 오프라인이면 온라인 복귀 후 자동으로 재시도해 보냅니다. 텔레그램 봇 한도(50MB)에 맞출 수 없는 긴 클립은 건너뛰며, 토스트로 알려드립니다.",
  delete_after: "보낸 뒤 기기에서 삭제",
  delete_after_desc:
    "텔레그램에 안전히 전송된 미디어를 지워 공간을 확보합니다. 스팀 갤러리에서도 사라집니다.",
  status: "상태",
  version: "버전",
  update_available: "업데이트 있음: {v}",
  open_release: "다운로드 페이지 열기",
  ffmpeg_missing: "이 시스템에 ffmpeg가 없어 클립 전송이 비활성화되었습니다 (스크린샷은 정상 동작)",
  now_working: "작업 중",
  queued: "전송 대기",
  queue_images: "스크린샷 {n}장 ({size})",
  queue_clips: "클립 {n}개 (약 {size})",
  idle: "대기 없음",
  refresh: "새로고침",
  retry_now: "지금 재시도",
  skip_queued: "모두 건너뛰기",
  sent: "보냄",
  last_sent: "마지막 전송",
  last_error: "마지막 오류",
  send_test: "테스트 메시지 보내기",
  failed_prefix: "실패: ",
  rerun_setup: "설정 다시 하기",
  no_token: "토큰 없음",
};

const LANGS: Record<string, Dict> = { en, ko, koreana: ko };

function steamLanguage(): string {
  try {
    const lm = (window as any).LocalizationManager;
    const loc = lm?.m_rgLocalesToUse?.[0];
    if (typeof loc === "string" && loc) return loc;
  } catch {
    /* not in Steam context */
  }
  return (navigator.language || "en").toLowerCase();
}

function pick(): Dict {
  const lang = steamLanguage().toLowerCase();
  if (LANGS[lang]) return LANGS[lang];
  const short = lang.split(/[-_]/)[0];
  return LANGS[short] ?? en;
}

const table = pick();

/** t("watching_folders", { n: 5 }) - {placeholders} are substituted. */
export function t(key: string, vars?: Record<string, string | number>): string {
  let s = table[key] ?? en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      s = s.split(`{${k}}`).join(String(v));
    }
  }
  return s;
}

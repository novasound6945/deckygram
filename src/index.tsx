import {
  ButtonItem,
  DropdownItem,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  Field,
  staticClasses,
  findModuleExport,
} from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
  routerHook,
  toaster,
} from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaTelegramPlane } from "react-icons/fa";
import qrcode from "qrcode-generator";
import { GalleryPage } from "./Gallery";
import { t } from "./i18n";

const GALLERY_ROUTE = "/deckygram/gallery";

/** URL -> QR image (GIF data URL). White quiet zone so phone cameras lock on. */
function QrImage({ text, loading }: { text: string; loading?: boolean }) {
  const src = useMemo(() => {
    try {
      const qr = qrcode(0, "M");
      // While waiting, render a decoy QR so the layout doesn't jump.
      qr.addData(text || "https://example.invalid/loading-placeholder");
      qr.make();
      return qr.createDataURL(5, 4);
    } catch {
      return "";
    }
  }, [text]);
  if (!src) return null;
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "8px 0" }}>
      <div style={{ position: "relative", width: 150, height: 150 }}>
        <img
          src={src}
          style={{
            width: "100%", height: "100%", imageRendering: "pixelated",
            filter: loading ? "blur(6px) brightness(0.55)" : "none",
            transition: "filter 0.25s",
          }}
        />
        {loading && (
          <span style={{
            position: "absolute", inset: 0, display: "flex",
            alignItems: "center", justifyContent: "center",
            color: "#fff", fontWeight: 600, fontSize: "0.95em",
            textShadow: "0 1px 4px rgba(0,0,0,0.8)",
          }}>
            {t("loading")}
          </span>
        )}
      </div>
    </div>
  );
}

// ---- backend callables -----------------------------------------------------

type Settings = {
  token_hint: string;
  webhook_hint: string;
  has_telegram: boolean;
  has_discord: boolean;
  chat_id: string;
  enabled: boolean;
  send_screenshots: boolean;
  send_clips: boolean;
  clip_preset: ClipPreset;
  notify_on_send: boolean;
  delete_after_send: boolean;
};

type Status = {
  running: boolean;
  watching: number;
  sent: number;
  failed: number;
  last_sent: string;
  last_error: string;
  current: string;
  progress: number;
  queued: number;
  queued_images: number;
  queued_images_bytes: number;
  queued_clips: number;
  queued_clips_bytes: number;
  configured: boolean;
  destination: Destination;
  max_clip_seconds: number;
  enabled: boolean;
  version: string;
  ffmpeg_ok: boolean;
  setup_broken: string;
  stalled: number;
  update_available: boolean;
  latest: string;
  url: string;
};

const CLIP_PRESETS = ["quality", "balanced", "reach"] as const;
type ClipPreset = (typeof CLIP_PRESETS)[number];

/** "6m 07s" / "73s" — the longest clip the current preset will take. */
function humanMinutes(seconds: number): string {
  if (!seconds) return "-";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return s ? `${m}m ${String(s).padStart(2, "0")}s` : `${m}m`;
}

function humanSize(bytes: number): string {
  if (!bytes) return "0 B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1048576).toFixed(1) + " MB";
  return (bytes / 1073741824).toFixed(2) + " GB";
}

function queueSummary(st: Status): string {
  const parts: string[] = [];
  if (st.queued_images > 0) {
    parts.push(t("queue_images", { n: st.queued_images, size: humanSize(st.queued_images_bytes) }));
  }
  if (st.queued_clips > 0) {
    parts.push(t("queue_clips", { n: st.queued_clips, size: humanSize(st.queued_clips_bytes) }));
  }
  return parts.join(" · ");
}

type Pairing = {
  status: "idle" | "waiting" | "done" | "expired";
  url: string;
  bot_username: string;
  mode: Destination;
};

type Destination = "telegram" | "discord";

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[patch: Partial<Settings>], Settings>("save_settings");
const setToken = callable<[token: string], { ok: boolean; bot_username?: string; error?: string }>("set_token");
const detectChat = callable<[], { ok: boolean; chat_id?: string; name?: string; error?: string }>("detect_chat");
const sendTest = callable<[], { ok: boolean; error?: string }>("send_test");
const setEnabled = callable<[enabled: boolean], { ok: boolean; enabled: boolean }>("set_enabled");
const getStatus = callable<[], Status>("get_status");
const startPairing = callable<[mode: Destination], Pairing>("start_pairing");
const setWebhook = callable<[url: string], { ok: boolean; error?: string }>("set_webhook");
const setDestination = callable<
  [dest: Destination], { ok: boolean; error?: string }
>("set_destination");
const forgetDestination = callable<
  [dest: Destination], { ok: boolean; error?: string }
>("forget_destination");
type DownloadResult = {
  ok: boolean; path?: string; dir?: string; name?: string; error?: string;
};
const downloadUpdate = callable<[], DownloadResult>("download_update");
const getPairing = callable<[], Pairing>("get_pairing");
const stopPairing = callable<[], { ok: boolean }>("stop_pairing");
const retryQueue = callable<[], { count: number }>("retry_queue");
const skipQueue = callable<[], { count: number }>("skip_queue");
const findLibraryOrphans =
  callable<[urls: string[]], { orphans: string[] }>("find_library_orphans");
const findMissingClips =
  callable<[ids: string[]], { missing: string[] }>("find_missing_clips");
const cleanupTemps =
  callable<[], { count: number; bytes: number }>("cleanup_temps");
const uiLog = callable<[msg: string], { ok: boolean }>("ui_log");

// ---- Steam library cleanup -------------------------------------------------

/** One row of Steam's own screenshot index. */
interface SteamShot {
  strGameID: string;
  hHandle: number;
  strUrl: string;
}

/**
 * Steam's clip store, if we can still find it.
 *
 * Clips are not in any SteamClient API. Steam's own Media tab deletes one
 * by calling DeleteClip on this store, which drops the entry, tells the
 * client over GameRecording.DeleteClip, and refreshes the grid - which is
 * why deleting from inside Steam makes the tile vanish at once. Removing
 * the folder ourselves does none of that, so the tile stays until Steam
 * restarts.
 *
 * This reaches into minified internals, so it is written to fail quietly:
 * if a Steam update moves it, clip deletion still works, the tile just
 * lingers as it did before.
 */
function getClipStore(): any {
  // Steam parks the game-recording store on the window as g_GRS; that is
  // how its own code reaches it. Deliberately not cached: the store is
  // replaced when Steam's UI reloads, and a stale reference would silently
  // stop working.
  const g = (window as any).g_GRS;
  if (g && typeof g.DeleteClip === "function") return g;
  try {
    return findModuleExport(
      (e: any) => e && typeof e.DeleteClip === "function" && e.m_clips,
    ) ?? null;
  } catch {
    return null;
  }
}

/**
 * Let Steam delete a clip, so its own list updates.
 *
 * Steam removes an entry from g_GRS only when the client reports the
 * files were deleted. If the backend removed the folder first, this call
 * answers FileNotFound and the tile stays until Steam restarts - so the
 * backend now waits a few seconds for this instead, and cleans up itself
 * only if Steam did not.
 */
/**
 * Steam's delete calls must not overlap.
 *
 * A burst of screenshots produces a burst of delete events, and firing
 * them together loses some: five sent at once came back three succeeded,
 * two `bSuccess:false` (measured 2026-09-01). The same thing bit the
 * index sweep earlier. So everything that talks to Steam about deleting
 * goes through this one chain, one at a time.
 */
let deleteChain: Promise<unknown> = Promise.resolve();
function serialised<T>(fn: () => Promise<T>): Promise<T | undefined> {
  const next = deleteChain.then(fn, fn).catch(() => undefined);
  deleteChain = next;
  return next as Promise<T | undefined>;
}

/**
 * Steam's media grid reads screenshots through react-query.
 *
 * Clips live in the g_GRS store, so removing one there updates the grid
 * at once. Screenshots do not: DeleteLocalScreenshots removes the file
 * and the index, but the grid keeps drawing from its cached query until
 * whoever deleted it edits that cache - which is what Steam's own delete
 * menu does. Nothing else refreshes it, which is why a deleted shot left
 * a warning tile while a deleted clip vanished cleanly.
 *
 * The client is not exported anywhere, but it sits on a context a few
 * levels up from any rendered element, and the same one serves this
 * context. Invalidating the "screenshots" queries makes the grid refetch.
 */
function findQueryClient(): any {
  const els = document.querySelectorAll("*");
  const limit = Math.min(els.length, 40);
  for (let i = 0; i < limit; i++) {
    const el = els[i] as any;
    const key = Object.keys(el).find(
      (k) => k.startsWith("__reactFiber$") || k.startsWith("__reactContainer$"),
    );
    if (!key) continue;
    let f = el[key];
    for (let d = 0; f && d < 400; d++) {
      const v = f.memoizedProps?.value;
      if (v && typeof v === "object" && typeof v.getQueryCache === "function") {
        return v;
      }
      f = f.return;
    }
  }
  return null;
}

/** Make Steam's media grid re-read its screenshot list. */
function refreshSteamScreenshotList(): void {
  // Not cached: Steam replaces the client when its UI reloads, and a dead
  // reference would fail silently - the exact failure this fixes.
  const qc = findQueryClient();
  if (!qc) return;
  try {
    qc.invalidateQueries({ queryKey: ["screenshots"] });
  } catch {
    try {
      qc.invalidateQueries(["screenshots"]);   // older react-query shape
    } catch {
      /* the list still corrects itself next time Steam builds it */
    }
  }
}

/**
 * Let Steam delete a screenshot, so its own list updates.
 *
 * Steam's Media tab uses the plural DeleteLocalScreenshots, grouped by
 * game id - deleting the file behind its back is what leaves the warning
 * tiles. `tail` is "<appid>/screenshots/<name>.jpg", enough to find the
 * entry in Steam's list.
 */
async function deleteScreenshotViaSteam(tail: string): Promise<boolean> {
  const api = (window as any)?.SteamClient?.Screenshots;
  if (!api?.GetAllLocalScreenshots || !api?.DeleteLocalScreenshots) {
    uiLog("shot delete: no Screenshots API").catch(() => {});
    return false;
  }
  try {
    const all: SteamShot[] = await api.GetAllLocalScreenshots();
    const hit = all?.find((s) => s.strUrl?.endsWith(tail));
    if (!hit) {
      uiLog(`shot delete: ${tail} not in Steam's list of ${all?.length ?? 0}`)
        .catch(() => {});
      return false;
    }
    const r = await api.DeleteLocalScreenshots(
      [{ gameID: hit.strGameID, rgHandles: [hit.hHandle] }],
    );
    uiLog(`shot delete ${tail}: ${JSON.stringify(r)}`).catch(() => {});
    if (r?.bSuccess) refreshSteamScreenshotList();
    return !!r?.bSuccess;
  } catch (e) {
    uiLog(`shot delete ${tail} threw: ${e}`).catch(() => {});
    return false;   // the backend's fallback removes the file shortly
  }
}

async function deleteClipViaSteam(clipId: string): Promise<void> {
  const store = getClipStore();
  if (!store) return;
  try {
    await store.DeleteClip(clipId);
  } catch {
    /* the backend's fallback removes the folder shortly */
  }
}

/**
 * Drop clips Steam still lists whose folder is gone.
 *
 * Unlike screenshots, clips have no index on disk: Steam builds g_GRS from
 * the clips folder when the media view opens and drops it when you leave,
 * so a stale entry cannot outlive that view. Nothing to clean up on load,
 * then - this only matters while the store is live, which is exactly when
 * a stale entry would be on screen.
 */
async function pruneBrokenClips(): Promise<number> {
  const store = getClipStore();
  const clips = store?.m_clips;
  const ids: string[] = clips?.keys ? Array.from(clips.keys()) : [];
  if (!ids.length) return 0;      // media view closed; nothing is listed

  const { missing } = await findMissingClips(ids);
  if (!missing?.length) return 0;

  let n = 0;
  for (const id of missing) {
    try {
      // Serialised, for the same reason the screenshot sweep is.
      await store.DeleteClip(id);
      n++;
    } catch {
      /* keep going; one bad id should not stop the sweep */
    }
  }
  return n;
}

/**
 * Drop index entries whose picture is gone.
 *
 * Deleting the file is not enough: Steam keeps its own list, and the media
 * grid draws a tile with a warning triangle wherever an entry has no file
 * behind it. Deleting a screenshot after sending left exactly that (user
 * report, 2026-08-31). Only the client can mend the list, and only from
 * here - the backend has no access to SteamClient.
 *
 * Runs on every plugin load, so a Deck that already collected broken tiles
 * is cleaned up on the next start rather than needing anything from the
 * user. Steam caches this list for the lifetime of its UI, though, so the
 * tiles themselves only disappear once the UI reloads.
 *
 * Clips need no equivalent: Steam enumerates the clips folder rather than
 * indexing it, so removing a clip folder leaves nothing behind.
 */
async function pruneBrokenLibraryEntries(): Promise<number> {
  const api = (window as any)?.SteamClient?.Screenshots;
  if (!api?.GetAllLocalScreenshots || !api?.DeleteLocalScreenshot) return 0;

  const all: SteamShot[] = await api.GetAllLocalScreenshots();
  if (!all?.length) return 0;

  const { orphans } = await findLibraryOrphans(all.map((s) => s.strUrl));
  if (!orphans?.length) return 0;

  const dead = new Set(orphans);
  let n = 0;
  for (const s of all) {
    if (!dead.has(s.strUrl)) continue;
    try {
      // One at a time. Firing these together drops all but one on the
      // floor - measured on hardware: three orphans, three calls issued
      // in a plain loop, one entry actually removed.
      await api.DeleteLocalScreenshot(s.strGameID, s.hHandle);
      n++;
    } catch {
      /* one stubborn entry should not stop the rest */
    }
  }
  if (n) refreshSteamScreenshotList();
  return n;
}

// ---- setup wizard ----------------------------------------------------------

/** Explanatory text tucked under a button, inside the same row. */
const destBlurb: React.CSSProperties = {
  fontSize: "0.75em",
  lineHeight: 1.4,
  color: "#8b929a",
  padding: "0 16px 10px",
};

/** Separates one destination choice from the next. */
const destBlurbDivider: React.CSSProperties = {
  borderBottom: "1px solid rgba(255,255,255,0.1)",
  marginBottom: 10,
};

function SetupWizard({ onDone, onCancel, settings }: {
  onDone: () => void;
  onCancel?: () => void;
  settings?: Settings | null;
}) {
  const [step, setStep] = useState<"where" | "pair" | "token" | "chat" | "test">("where");
  const [dest, setDest] = useState<Destination>("telegram");
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [tokenInput, setTokenInput] = useState("");
  const [botName, setBotName] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  // Phone pairing: start the LAN page, then poll until the phone delivers
  // a valid token. The phone page also walks the user through /start, so
  // we try chat detection automatically before falling back to step 2.
  useEffect(() => {
    if (step !== "pair") return;
    let alive = true;
    startPairing(dest).then((p) => { if (alive) setPairing(p); });
    const timer = setInterval(async () => {
      const p = await getPairing();
      if (!alive) return;
      setPairing(p);
      if (p.status === "done") {
        clearInterval(timer);
        // Discord is finished the moment the webhook is accepted - the
        // page already sent a test message through it.
        if (dest === "discord") {
          onDone();
          return;
        }
        setBotName(p.bot_username);
        const r = await detectChat();
        if (r.ok) {
          setMsg(t("connected_to", { name: r.name || "you" }));
          setStep("test");
        } else {
          setStep("chat");
        }
      }
    }, 2000);
    return () => { alive = false; clearInterval(timer); stopPairing(); };
  }, [step, dest]);

  /** Already paired? Just switch. Otherwise start the pairing flow. */
  const choose = async (d: Destination, ready: boolean) => {
    if (ready) {
      const r = await setDestination(d);
      if (r.ok) { onDone(); return; }
      setMsg(t("error_prefix") + (r.error ?? ""));
      return;
    }
    setDest(d);
    setStep("pair");
  };

  const submitWebhook = async () => {
    setBusy(true);
    setMsg("");
    const r = await setWebhook(tokenInput);
    setBusy(false);
    if (r.ok) onDone();
    else setMsg(t("error_prefix") + (r.error ?? ""));
  };

  const submitToken = async () => {
    setBusy(true);
    setMsg("");
    const r = await setToken(tokenInput);
    setBusy(false);
    if (r.ok) {
      setBotName(r.bot_username ?? "");
      setStep("chat");
    } else {
      setMsg(t("invalid_token") + (r.error ?? ""));
    }
  };

  const tryDetect = async () => {
    setBusy(true);
    setMsg("");
    const r = await detectChat();
    setBusy(false);
    if (r.ok) {
      setStep("test");
      setMsg(t("connected_to", { name: r.name || "you" }));
    } else if (r.error === "no message yet") {
      setMsg(t("no_message_yet", { bot: botName }));
    } else {
      setMsg(t("error_prefix") + (r.error ?? ""));
    }
  };

  const doTest = async () => {
    setBusy(true);
    const r = await sendTest();
    setBusy(false);
    if (r.ok) {
      toaster.toast({ title: "Deckygram", body: t("test_sent") });
      onDone();
    } else {
      setMsg(t("send_failed") + (r.error ?? ""));
    }
  };

  return (
    <PanelSection title={t("setup")}>
      {step === "where" && (
        <>
          <PanelSectionRow>
            <Field label={t("where_label")} description={t("where_desc")} />
          </PanelSectionRow>
          {/* A button draws a separator under itself, which cut each
              choice away from its own description. Suppress it there and
              let the description carry the separator instead, so the line
              lands BETWEEN the two destinations. */}
          {/* A destination that is already set up switches straight over;
              only a fresh one starts the pairing flow. */}
          <PanelSectionRow>
            <div>
              <ButtonItem
                layout="below"
                bottomSeparator="none"
                onClick={() => choose("telegram", !!settings?.has_telegram)}
              >
                {t(settings?.has_telegram ? "dest_telegram_ready" : "dest_telegram")}
              </ButtonItem>
              <div style={{ ...destBlurb, ...destBlurbDivider }}>
                {t("dest_telegram_desc")}
              </div>
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <div>
              <ButtonItem
                layout="below"
                bottomSeparator="none"
                onClick={() => choose("discord", !!settings?.has_discord)}
              >
                {t(settings?.has_discord ? "dest_discord_ready" : "dest_discord")}
              </ButtonItem>
              <div style={destBlurb}>{t("dest_discord_desc")}</div>
            </div>
          </PanelSectionRow>
        </>
      )}
      {step === "pair" && (
        <>
          <PanelSectionRow>
            <Field
              label={t("pair_with_phone")}
              description={dest === "discord" ? t("pair_desc_discord") : t("pair_desc")}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <QrImage text={pairing?.url ?? ""} loading={!pairing?.url} />
          </PanelSectionRow>
          <PanelSectionRow>
            <Field
              label={pairing?.status === "expired" ? t("pair_expired") : t("pair_waiting")}
              description={pairing?.url ? (
                <span style={{ fontSize: "1.1em", fontWeight: 600, userSelect: "text" }}>
                  {pairing.url}
                </span>
              ) : "..."}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setStep("token")}>
              {t(dest === "discord" ? "pair_manual_dc" : "pair_manual")}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {step === "token" && (
        <>
          <PanelSectionRow>
            <Field
              label={dest === "discord" ? t("webhook_label") : t("step1_label")}
              description={dest === "discord" ? t("webhook_desc") : t("step1_desc")}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label={dest === "discord" ? t("webhook_url") : t("bot_token")}
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy || tokenInput.length < 20}
              onClick={dest === "discord" ? submitWebhook : submitToken}
            >
              {busy ? t("checking")
                    : t(dest === "discord" ? "validate_webhook" : "validate_token")}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {step === "chat" && (
        <>
          <PanelSectionRow>
            <Field label={t("step2_label")} description={t("step2_desc", { bot: botName })} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={tryDetect}>
              {busy ? t("looking") : t("detect_chat")}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {step === "test" && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={doTest}>
            {busy ? t("sending") : t("send_test_step")}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {msg && (
        <PanelSectionRow>
          <Field description={msg} />
        </PanelSectionRow>
      )}
      {onCancel && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={onCancel}>
            {t("back_to_main")}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}

// ---- main panel ------------------------------------------------------------

function Content() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [showWizard, setShowWizard] = useState(false);
  // Which destination's "forget" button is armed, if any.
  const [forgetArmed, setForgetArmed] = useState<Destination | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [updateMsg, setUpdateMsg] = useState("");
  const [tidying, setTidying] = useState(false);

  const refresh = async () => {
    const [s, st] = await Promise.all([getSettings(), getStatus()]);
    setSettings(s);
    setStatus(st);
    setShowWizard(!st.configured);
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(() => { getStatus().then(setStatus); }, 2000);
    return () => clearInterval(timer);
  }, []);

  if (!settings) return <PanelSection title={t("loading")} />;

  if (showWizard) {
    return (
      <SetupWizard
        settings={settings}
        onDone={refresh}
        onCancel={status?.configured ? () => setShowWizard(false) : undefined}
      />
    );
  }

  // Which service is configured decides a handful of labels and limits.
  // Everything else in the panel is identical, so this stays one panel.
  const onDiscord = status?.destination === "discord";
  const activeDest: Destination = onDiscord ? "discord" : "telegram";

  const patch = async (p: Partial<Settings>) => {
    setSettings(await saveSettings(p));
  };

  return (
    <>
      <PanelSection>
        {/* Top of the panel, in order of how often you act on it: a new
            version (rare but time-sensitive), then the picker (the reason
            you opened this), then everything else. */}
        {status?.update_available ? (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={downloading}
              description={updateMsg || t("update_hint")}
              onClick={async () => {
                setDownloading(true);
                setUpdateMsg(t("update_downloading"));
                const r: DownloadResult = await downloadUpdate()
                  .catch((e) => ({ ok: false, error: String(e) }));
                setDownloading(false);
                setUpdateMsg(r.ok
                  ? t("update_saved", { name: r.name ?? "", dir: r.dir ?? "" })
                  : t("update_failed") + (r.error ?? ""));
              }}
            >
              {downloading
                ? t("update_downloading")
                : t("update_available", { v: status.latest })}
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => {
              Navigation.CloseSideMenus();
              Navigation.Navigate(GALLERY_ROUTE);
            }}
          >
            {t("open_gallery")}
          </ButtonItem>
        </PanelSectionRow>
        {status?.setup_broken ? (
          <>
            <PanelSectionRow>
              <Field
                label={t(onDiscord ? "setup_broken_dc" : "setup_broken")}
                description={t(onDiscord ? "setup_broken_desc_dc" : "setup_broken_desc",
                               { why: status.setup_broken })}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={() => setShowWizard(true)}>
                {t("setup_broken_fix")}
              </ButtonItem>
            </PanelSectionRow>
          </>
        ) : null}
        <PanelSectionRow>
          <ToggleField
            label={t(onDiscord ? "send_to_discord" : "send_to_telegram")}
            description={status?.running ? t("watching_folders", { n: status.watching }) : t("paused")}
            checked={settings.enabled}
            onChange={async (v) => { await setEnabled(v); refresh(); }}
          />
        </PanelSectionRow>
        {status && status.ffmpeg_ok === false ? (
          <PanelSectionRow>
            <Field description={t("ffmpeg_missing")} />
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <Field description={t(onDiscord ? "only_new_note_dc" : "only_new_note")} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={t("what_to_send")}>
        <PanelSectionRow>
          <ToggleField label={t("screenshots")} checked={settings.send_screenshots}
            onChange={(v) => patch({ send_screenshots: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label={t("recorded_clips")} checked={settings.send_clips}
            onChange={(v) => patch({ send_clips: v })} />
        </PanelSectionRow>
        {settings.send_clips ? (
          <PanelSectionRow>
            <DropdownItem
              label={t("clip_preset")}
              description={t("clip_preset_desc", {
                len: humanMinutes(status?.max_clip_seconds ?? 0),
              })}
              rgOptions={CLIP_PRESETS.map((p) => ({ data: p, label: t(`preset_${p}`) }))}
              selectedOption={settings.clip_preset}
              onChange={(o) => patch({ clip_preset: o.data as ClipPreset })}
            />
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ToggleField label={t("notify_toggle")} checked={settings.notify_on_send}
            onChange={(v) => patch({ notify_on_send: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label={t("delete_after")}
            description={t(onDiscord ? "delete_after_desc_dc" : "delete_after_desc")}
            checked={settings.delete_after_send}
            onChange={(v) => patch({ delete_after_send: v })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={t("status")}>
        {/* Queue first, then what is being worked on: the queue is what
            the item currently sending came out of, so reading top to
            bottom follows the media rather than jumping back. */}
        {status && status.queued > 0 ? (
          <>
            <PanelSectionRow>
              <Field label={t("queued")} description={queueSummary(status)} />
            </PanelSectionRow>
            {status.stalled > 0 ? (
              <PanelSectionRow>
                <Field description={t("stalled", { n: status.stalled, max: 5 })} />
              </PanelSectionRow>
            ) : null}
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={async () => {
                await retryQueue();
                getStatus().then(setStatus);
              }}>
                {t("retry_now")}
              </ButtonItem>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={async () => {
                await skipQueue();
                getStatus().then(setStatus);
              }}>
                {t("skip_queued")}
              </ButtonItem>
            </PanelSectionRow>
          </>
        ) : null}
        <PanelSectionRow>
          <Field
            label={t("now_working")}
            description={
              status?.current
                ? status.current + (status.progress >= 0 ? ` (${status.progress}%)` : "")
                : t("idle")
            }
          />
        </PanelSectionRow>
        {/* Encoding a clip takes a little while and reports its own
            percentage; without a word here the panel looks stuck. */}
        {status?.current?.startsWith("Encoding") ? (
          <PanelSectionRow>
            <Field description={t("encoding_note")} />
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => getStatus().then(setStatus)}>
            {t("refresh")}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label={t("sent")} description={String(status?.sent ?? 0)} />
        </PanelSectionRow>
        {status?.last_sent ? (
          <PanelSectionRow>
            <Field label={t("last_sent")} description={status.last_sent} />
          </PanelSectionRow>
        ) : null}
        {status?.last_error ? (
          <PanelSectionRow>
            <Field label={t("last_error")} description={status.last_error} />
          </PanelSectionRow>
        ) : null}
        {/* Steam only rebuilds its media list at certain moments, so the
            automatic sweeps can be a beat behind what you are looking at.
            This runs the same cleanup on demand, which is the reliable
            way to get a tidy Media tab right now. */}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            description={t("tidy_desc")}
            disabled={tidying}
            onClick={async () => {
              setTidying(true);
              try {
                const shots = (await serialised(pruneBrokenLibraryEntries)) ?? 0;
                const clips = (await serialised(pruneBrokenClips)) ?? 0;
                const temps = await cleanupTemps().catch(() => ({ count: 0, bytes: 0 }));
                // Always, not just when something was pruned: the usual
                // reason to press this is a list that went stale, which
                // needs no orphan to exist.
                refreshSteamScreenshotList();
                const n = shots + clips + temps.count;
                toaster.toast({
                  title: "Deckygram",
                  body: n ? t("tidy_done", { n }) : t("tidy_clean"),
                });
              } finally {
                setTidying(false);
              }
            }}>
            {tidying ? t("tidy_running") : t("tidy_media")}
          </ButtonItem>
        </PanelSectionRow>
        {/* Both credentials are kept side by side, so switching is one
            press. Down here with the other setup controls: you switch
            rarely, if ever. Hidden until the other side actually exists. */}
        {(onDiscord ? settings.has_telegram : settings.has_discord) && (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={async () => {
                await setDestination(onDiscord ? "telegram" : "discord");
                refresh();
              }}
            >
              {t(onDiscord ? "switch_to_telegram" : "switch_to_discord")}
            </ButtonItem>
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setShowWizard(true)}>
            {`${t("rerun_setup")} (${onDiscord
              ? settings.webhook_hint || t("no_webhook")
              : settings.token_hint || t("no_token")})`}
          </ButtonItem>
        </PanelSectionRow>
        {/* The token and webhook stay on the Deck until removed, so give
            people a way to remove them. Two presses, because it cannot be
            undone.

            Steam scrolls only far enough to show the FOCUSED element, and
            a Field cannot take focus - so anything unfocusable at the end
            of the panel is unreachable and gets clipped. Carrying the
            version on the last button keeps it visible. */}
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={async () => {
              if (forgetArmed !== activeDest) { setForgetArmed(activeDest); return; }
              await forgetDestination(activeDest);
              setForgetArmed(null);
              refresh();
            }}
            description={t("version") + " v" + (status?.version ?? "?")}
          >
            {forgetArmed === activeDest
              ? t("forget_confirm")
              : t(onDiscord ? "forget_discord" : "forget_telegram")}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // Clear any broken tiles left behind before this version, or by a
  // previous session. Failure here must never keep the plugin from
  // loading, so it is fire-and-forget.
  serialised(pruneBrokenLibraryEntries);

  // A send may have been followed by a delete. Sweep once things settle,
  // rather than after each item in a burst.
  let sweep: ReturnType<typeof setTimeout> | undefined;
  const sweepSoon = () => {
    if (sweep) clearTimeout(sweep);
    sweep = setTimeout(() => {
      serialised(pruneBrokenLibraryEntries);
      serialised(pruneBrokenClips);
    }, 30_000);
  };

  const listener = addEventListener<[kind: string, title: string, body: string]>(
    "deckygram_event",
    (kind, title, body) => {
      // Not a message for the user: the backend is handing us the id of a
      // clip it just removed so Steam can be told to drop it too.
      if (kind === "clip_delete") {
        serialised(() => deleteClipViaSteam(title));
        return;
      }
      if (kind === "media_delete") {
        serialised(() => deleteScreenshotViaSteam(title));
        return;
      }
      toaster.toast({ title, body });
      if (kind === "sent") sweepSoon();
    },
  );

  // The picker needs room the Quick Access panel does not have, so it
  // lives as its own full-screen route.
  routerHook.addRoute(GALLERY_ROUTE, GalleryPage, { exact: true });

  return {
    name: "Deckygram",
    titleView: <div className={staticClasses.Title}>Deckygram</div>,
    content: <Content />,
    icon: <FaTelegramPlane />,
    onDismount() {
      if (sweep) clearTimeout(sweep);
      removeEventListener("deckygram_event", listener);
      routerHook.removeRoute(GALLERY_ROUTE);
    },
  };
});

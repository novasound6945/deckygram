import {
  ButtonItem,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  ToggleField,
  Field,
  staticClasses,
} from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  callable,
  definePlugin,
  toaster,
} from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaTelegramPlane } from "react-icons/fa";
import qrcode from "qrcode-generator";
import { t } from "./i18n";

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
  chat_id: string;
  enabled: boolean;
  send_screenshots: boolean;
  send_clips: boolean;
  original_quality: boolean;
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
  enabled: boolean;
  version: string;
  ffmpeg_ok: boolean;
  update_available: boolean;
  latest: string;
  url: string;
};

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
};

const getSettings = callable<[], Settings>("get_settings");
const saveSettings = callable<[patch: Partial<Settings>], Settings>("save_settings");
const setToken = callable<[token: string], { ok: boolean; bot_username?: string; error?: string }>("set_token");
const detectChat = callable<[], { ok: boolean; chat_id?: string; name?: string; error?: string }>("detect_chat");
const sendTest = callable<[], { ok: boolean; error?: string }>("send_test");
const setEnabled = callable<[enabled: boolean], { ok: boolean; enabled: boolean }>("set_enabled");
const getStatus = callable<[], Status>("get_status");
const startPairing = callable<[], Pairing>("start_pairing");
const getPairing = callable<[], Pairing>("get_pairing");
const stopPairing = callable<[], { ok: boolean }>("stop_pairing");
const retryQueue = callable<[], { count: number }>("retry_queue");
const skipQueue = callable<[], { count: number }>("skip_queue");

// ---- setup wizard ----------------------------------------------------------

function SetupWizard({ onDone, onCancel }: { onDone: () => void; onCancel?: () => void }) {
  const [step, setStep] = useState<"pair" | "token" | "chat" | "test">("pair");
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
    startPairing().then((p) => { if (alive) setPairing(p); });
    const timer = setInterval(async () => {
      const p = await getPairing();
      if (!alive) return;
      setPairing(p);
      if (p.status === "done") {
        clearInterval(timer);
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
  }, [step]);

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
      {step === "pair" && (
        <>
          <PanelSectionRow>
            <Field label={t("pair_with_phone")} description={t("pair_desc")} />
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
              {t("pair_manual")}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {step === "token" && (
        <>
          <PanelSectionRow>
            <Field label={t("step1_label")} description={t("step1_desc")} />
          </PanelSectionRow>
          <PanelSectionRow>
            <TextField
              label={t("bot_token")}
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy || tokenInput.length < 20} onClick={submitToken}>
              {busy ? t("checking") : t("validate_token")}
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
        onDone={refresh}
        onCancel={status?.configured ? () => setShowWizard(false) : undefined}
      />
    );
  }

  const patch = async (p: Partial<Settings>) => {
    setSettings(await saveSettings(p));
  };

  return (
    <>
      <PanelSection>
        {status?.update_available ? (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => { if (status.url) Navigation.NavigateToExternalWeb(status.url); }}
            >
              {t("update_available", { v: status.latest })} — {t("open_release")}
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ToggleField
            label={t("send_to_telegram")}
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
          <Field description={t("only_new_note")} />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={t("what_to_send")}>
        <PanelSectionRow>
          <ToggleField label={t("screenshots")} checked={settings.send_screenshots}
            onChange={(v) => patch({ send_screenshots: v })} />
        </PanelSectionRow>
        {settings.send_screenshots ? (
          <PanelSectionRow>
            <ToggleField
              label={t("original_quality")}
              description={t("original_quality_desc")}
              checked={settings.original_quality}
              onChange={(v) => patch({ original_quality: v })}
            />
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ToggleField label={t("recorded_clips")} checked={settings.send_clips}
            onChange={(v) => patch({ send_clips: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField label={t("notify_toggle")} checked={settings.notify_on_send}
            onChange={(v) => patch({ notify_on_send: v })} />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label={t("delete_after")}
            description={t("delete_after_desc")}
            checked={settings.delete_after_send}
            onChange={(v) => patch({ delete_after_send: v })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={t("status")}>
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
        {status && status.queued > 0 ? (
          <>
            <PanelSectionRow>
              <Field label={t("queued")} description={queueSummary(status)} />
            </PanelSectionRow>
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
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={async () => {
            const r = await sendTest();
            toaster.toast({
              title: "Deckygram",
              body: r.ok ? t("test_sent") : (t("failed_prefix") + (r.error ?? "")),
            });
          }}>
            {t("send_test")}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setShowWizard(true)}>
            {t("rerun_setup")} ({settings.token_hint || t("no_token")})
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <Field label={t("version")} description={"v" + (status?.version ?? "?")} />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  const listener = addEventListener<[kind: string, title: string, body: string]>(
    "deckygram_event",
    (_kind, title, body) => {
      toaster.toast({ title, body });
    },
  );

  return {
    name: "Deckygram",
    titleView: <div className={staticClasses.Title}>Deckygram</div>,
    content: <Content />,
    icon: <FaTelegramPlane />,
    onDismount() {
      removeEventListener("deckygram_event", listener);
    },
  };
});

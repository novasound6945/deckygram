import {
  Focusable,
  DialogButton,
  Dropdown,
  Spinner,
  GamepadButton,
  ConfirmModal,
  showModal,
} from "@decky/ui";
import {
  addEventListener, callable, removeEventListener, toaster,
} from "@decky/api";
import { useEffect, useRef, useState } from "react";
import { t } from "./i18n";

// ---- backend ---------------------------------------------------------------

export type MediaItem = {
  id: string;
  kind: "image" | "clip";
  when: number;
  bytes: number;
  seconds: number;
  game: string;
  sent: boolean;
  too_long: boolean;
  sendable: boolean;
};

type Page = { total: number; offset: number; items: MediaItem[] };

export type GameEntry = { ids: string; game: string; count: number };

const galleryList = callable<
  [offset: number, limit: number, kind: string, refresh: boolean, appids: string], Page
>("gallery_list");
const galleryGames = callable<[kind: string], GameEntry[]>("gallery_games");
const galleryThumb = callable<[id: string], string>("gallery_thumb");
const gallerySend = callable<[ids: string[]], { count: number }>("gallery_send");
const galleryDelete = callable<
  [ids: string[]],
  { deleted: number; deferred: number; gone: number; failed: number }
>("gallery_delete");

const PAGE = 30;      // fills two screens of tiles; a page loads in a blink
const THUMB_PARALLEL = 6;
// Each pick becomes a send, and a clip becomes an encode too. Twenty is
// plenty for one batch and keeps a stray "select page" from queueing an
// hour of work.
const MAX_PICKS = 20;

const KINDS = ["all", "images", "clips"] as const;
type Kind = (typeof KINDS)[number];

// SteamOS draws its own bars over the route: the status bar on top and the
// button-legend footer at the bottom. Inset by both or the page's own
// header and action row end up underneath them.
const HEADER_OFFSET = 40;
const FOOTER_OFFSET = 48;

// SteamOS's UI-scale setting changes the CSS viewport (it zooms via
// devicePixelRatio - at the default the page sees 1067x667, not
// 1280x800), so the grid must decide its own column count rather than
// assume one. auto-fill with a minimum keeps tiles a sane size and fits
// as many as the current scale allows.
const TILE_MIN = 165;
const TILE_ASPECT = "16 / 10";   // matches the Deck's 1280x800 capture

// ---- helpers ---------------------------------------------------------------

/** Date first, but today's shots only need a time - most of a page is
    usually one session, and the repeated date is pure noise. */
function when(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  const clock = `${p(d.getHours())}:${p(d.getMinutes())}`;
  const now = new Date();
  const sameDay = d.getFullYear() === now.getFullYear()
    && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  if (sameDay) return clock;
  const sameYear = d.getFullYear() === now.getFullYear();
  const date = `${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  return sameYear ? `${date} ${clock}` : `${d.getFullYear()}-${date}`;
}

function clipLength(sec: number): string {
  if (!sec) return "";
  return sec >= 60 ? `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}` : `${sec}s`;
}

/** Fetch thumbnails a few at a time so a page never floods the bridge.
 *
 *  Only the current page is kept: these are base64 strings, and holding
 *  every page walked through would grow to megabytes on a library of a
 *  few hundred items. Turning back re-fetches, which costs milliseconds.
 */
function useThumbnails(items: MediaItem[]) {
  const [thumbs, setThumbs] = useState<Record<string, string>>({});

  useEffect(() => {
    let alive = true;
    setThumbs({});
    const todo = items.map((i) => i.id);
    const wanted = new Set(todo);

    const worker = async () => {
      while (alive) {
        const id = todo.shift();
        if (!id) return;
        const data = await galleryThumb(id).catch(() => "");
        if (!alive) return;
        setThumbs((prev) => {
          // A late arrival from the page we just left must not linger.
          if (!wanted.has(id)) return prev;
          // Record the failure too ("") - otherwise a tile whose
          // thumbnail cannot be made spins for as long as you look at it.
          return { ...prev, [id]: data };
        });
      }
    };
    for (let i = 0; i < THUMB_PARALLEL; i++) void worker();
    return () => { alive = false; };
  }, [items]);

  return thumbs;
}

// ---- tile ------------------------------------------------------------------

/** Steam's own focus treatment: a white ring and a nudge in scale. The
    default thin border is easy to lose track of when moving fast across
    thirty tiles. */
const TILE_FOCUS_CSS = `
.dg-tile { transition: transform .12s ease, box-shadow .12s ease; }
.dg-tile:focus, .dg-tile:focus-within {
  outline: none;
  transform: scale(1.045);
  box-shadow: 0 0 0 3px #fff, 0 6px 18px rgba(0,0,0,.55);
  z-index: 1;
}`;

function Tile({ item, thumb, picked, onToggle }: {
  item: MediaItem; thumb?: string; picked: boolean; onToggle: () => void;
}) {
  // Selectable even when it cannot be sent: a clip with no video in it is
  // precisely the kind of thing you want to delete, and the send path
  // skips these anyway. "Not sendable" is a statement about sending.
  return (
    <Focusable
      className="dg-tile"
      onActivate={onToggle}
      style={{
        width: "100%", borderRadius: 6, overflow: "hidden",
        background: "#1a2332",
        outline: picked
          ? (item.sendable ? "3px solid #2ea6ff" : "3px solid #d93b3b")
          : "3px solid transparent",
        opacity: !item.sendable ? 0.4 : (item.sent && !picked ? 0.72 : 1),
      }}
    >
      <div style={{
        position: "relative", width: "100%", aspectRatio: TILE_ASPECT,
        background: "#0e1520", display: "flex",
        alignItems: "center", justifyContent: "center",
      }}>
        {thumb === undefined
          ? <Spinner style={{ width: 24, height: 24 }} />
          : thumb
            ? <img src={thumb} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            : <span style={{ color: "#54606e", fontSize: "1.6em" }}>
                {item.kind === "clip" ? "🎬" : "🖼"}
              </span>}
        {item.kind === "clip" && (
          // Amber when the clip cannot fit under the current Clip quality
          // setting: it would be skipped, and finding that out after
          // picking it is a waste of everyone's time.
          <span style={{
            position: "absolute", right: 6, bottom: 6, padding: "1px 6px",
            borderRadius: 4, fontSize: "0.75em",
            background: item.too_long ? "rgba(120,60,0,0.85)" : "rgba(0,0,0,0.7)",
            color: item.too_long ? "#ffc266" : undefined,
          }}>
            {item.too_long ? "⚠ " : "▶ "}{clipLength(item.seconds)}
          </span>
        )}
        {/* Blue tick means "this is going out". Something that cannot be
            sent is still worth picking - to delete it - but saying it the
            same way would promise a send that never happens, so it gets a
            red cross instead: picked, but not for sending. */}
        {picked && (
          <span style={{
            position: "absolute", left: 6, top: 6, width: 22, height: 22,
            borderRadius: "50%",
            background: item.sendable ? "#2ea6ff" : "#d93b3b", color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.8em", fontWeight: 700,
          }}>{item.sendable ? "✓" : "✕"}</span>
        )}
        {/* Already delivered once. Most of the library will be in this
            state, so it has to be a whisper - a dot and a slight dim -
            rather than a badge on every tile. */}
        {item.sent && !picked && (
          <span
            title={t("gallery_sent_badge")}
            style={{
              position: "absolute", left: 7, top: 7, width: 9, height: 9,
              borderRadius: "50%", background: "#7aff9e",
              boxShadow: "0 0 0 2px rgba(0,0,0,0.55)",
            }}
          />
        )}
      </div>
      <div style={{ padding: "4px 7px 5px" }}>
        <div style={{
          fontSize: "0.75em", fontWeight: 600, whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis", lineHeight: 1.3,
        }}>{item.game}</div>
        <div style={{ fontSize: "0.68em", color: "#8b929a", lineHeight: 1.3 }}>
          {item.sendable ? when(item.when) : t("gallery_not_exportable")}
        </div>
      </div>
    </Focusable>
  );
}

// ---- page ------------------------------------------------------------------

export function GalleryPage() {
  const [kind, setKind] = useState<Kind>("all");
  const [appids, setAppids] = useState("");       // "" = every game
  // Kept alongside the ids: deriving the label from the first result meant
  // the button forgot which game it was filtering whenever the filter
  // returned nothing.
  const [gameName, setGameName] = useState("");
  const [games, setGames] = useState<GameEntry[] | null>(null);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  // Sent from here this session: the backend's "sent" flag lags behind.
  const [justQueued, setJustQueued] = useState<Set<string>>(new Set());
  // Deleted while this list was open. The page is a snapshot taken when
  // you walked in, so without this the watcher can send and delete a shot
  // behind your back and its tile still invites you to send it again.
  const [gone, setGone] = useState<Set<string>>(new Set());

  useEffect(() => {
    // The backend names what it deleted by its tail ("<appid>/screenshots/
    // <name>.jpg") or a clip's folder name; item ids here are full paths.
    const l = addEventListener<[kind: string, what: string, body: string]>(
      "deckygram_event",
      (kind, what) => {
        if (kind !== "media_delete" && kind !== "clip_delete") return;
        setGone((prev) => new Set(prev).add(what));
        // Drop it from the selection too. Marking it unpickable while it
        // stays selected strands it: the tile refuses to toggle, so the
        // count never comes down and it rides along on the next send.
        setPicked((prev) => {
          if (![...prev].some((id) => id.endsWith(what))) return prev;
          const next = new Set(prev);
          for (const id of prev) {
            if (id.endsWith(what)) next.delete(id);
          }
          return next;
        });
      },
    );
    return () => removeEventListener("deckygram_event", l);
  }, []);

  const isGone = (id: string) => {
    for (const tail of gone) {
      if (tail && id.endsWith(tail)) return true;
    }
    return false;
  };
  const [busy, setBusy] = useState(false);
  const gridRef = useRef<HTMLDivElement | null>(null);

  /** Navigating here leaves focus behind in the panel that opened us, so
      the first stick input goes nowhere useful. Put it on the first tile
      once the page has rendered - which is also the right place after a
      page turn or a filter change. */
  useEffect(() => {
    if (!page?.items.length) return;
    const id = setTimeout(() => {
      const first = gridRef.current?.querySelector<HTMLElement>(".dg-tile");
      first?.focus();
    }, 60);
    return () => clearTimeout(id);
  }, [page]);

  const load = (off: number, k = kind, refresh = false, app = appids) => {
    setPage(null);
    galleryList(off, PAGE, k, refresh, app).then((p) => {
      setPage(p);
      setOffset(p.offset);
    });
  };

  useEffect(() => { load(0, kind, false, appids); }, [kind, appids]);

  /** Changing what you are looking at drops the picks: keeping selections
      you can no longer see is how people send the wrong thing. */
  const changeView = (next: () => void) => {
    setPicked(new Set());
    setOffset(0);
    next();
  };

  // The dropdown needs its options up front, so the game list is fetched
  // alongside the first page rather than when the menu opens. It is one
  // pass over an index that is already built.
  useEffect(() => {
    let alive = true;
    setGames(null);
    galleryGames(kind).then((g) => { if (alive) setGames(g); });
    return () => { alive = false; };
  }, [kind]);

  const toggle = (id: string) => setPicked((prev) => {
    // Gone from the Deck while you were looking: nothing left to act on.
    // Something merely on its way stays selectable - you may well want to
    // delete what you just queued, and re-queueing an item that is already
    // in the queue is a no-op, so blocking it only cost the delete.
    if (isGone(id)) return prev;
    const next = new Set(prev);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (next.size >= MAX_PICKS) return prev;    // at the cap; ignore
      next.add(id);
    }
    return next;
  });

  const send = async () => {
    setBusy(true);
    const queued = [...picked];
    const r = await gallerySend(queued).catch(() => ({ count: 0 }));
    setBusy(false);
    setPicked(new Set());
    // Mark them here and now. The backend has only queued them, so the
    // index still lists them as unsent for a while, and without this you
    // can pick the same shot again and queue it twice. Marking beats
    // removing: the tiles keep their places, so paging and focus do not
    // shuffle under you mid-selection.
    setJustQueued((prev) => {
      const next = new Set(prev);
      for (const id of queued) next.add(id);
      return next;
    });
    toaster.toast({ title: "Deckygram", body: t("gallery_queued", { n: r.count }) });
  };

  /** Delete what is picked, once the user has said so twice. */
  const runDelete = async () => {
    setBusy(true);
    const ids = [...picked];
    const r = await galleryDelete(ids).catch(
      () => ({ deleted: 0, deferred: 0, gone: 0, failed: ids.length }));
    setBusy(false);
    setPicked(new Set());
    // Grey them out first: the deferred ones stay on the Deck until their
    // send finishes, and leaving those selectable invites a second delete.
    setJustQueued((prev) => {
      const next = new Set(prev);
      for (const id of ids) next.add(id);
      return next;
    });
    // Then rebuild the page. Greying alone was the wrong call: what you
    // deleted is still sitting there, and "it only goes away if I hit
    // refresh" is a bug however it is rationalised. The churn this was
    // meant to avoid needs a live selection, and the selection has just
    // been cleared.
    load(offset, kind, true, appids);
    const parts: string[] = [];
    if (r.deleted) parts.push(t("gallery_deleted", { n: r.deleted }));
    if (r.deferred) parts.push(t("gallery_delete_after_send", { n: r.deferred }));
    if (r.failed) parts.push(t("gallery_delete_failed", { n: r.failed }));
    toaster.toast({
      title: "Deckygram",
      body: parts.join(" · ") || t("gallery_delete_nothing"),
    });
  };

  const confirmDelete = () => {
    if (!picked.size) return;
    showModal(
      <ConfirmModal
        bDestructiveWarning
        strTitle={t("gallery_delete_title")}
        strDescription={t("gallery_delete_body", { n: picked.size })}
        strOKButtonText={t("gallery_delete")}
        onOK={() => { void runDelete(); }}
      />,
    );
  };

  const total = page?.total ?? 0;
  const pageNo = Math.floor(offset / PAGE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const thumbs = useThumbnails(page?.items ?? []);

  // Picks survive paging (the set is keyed by path, not by position), but
  // that is only reassuring if you can see it: say how many are held
  // elsewhere, and offer one button to let them all go.
  const pickedTooLong = (page?.items ?? [])
    .filter((i) => picked.has(i.id) && i.too_long).length;
  // Clips each cost an encode and a big upload, so say how many are in
  // the batch - "30 picked" reads very differently at 2 clips vs 28.
  const pickedClips = (page?.items ?? [])
    .filter((i) => picked.has(i.id) && i.kind === "clip").length;
  // These can be picked so they can be deleted, but sending skips them.
  // Without saying so, picking three and being told two were queued reads
  // as a bug.
  const pickedUnsendable = (page?.items ?? [])
    .filter((i) => picked.has(i.id) && !i.sendable && !isGone(i.id)).length;
  // Already on their way, so not candidates for "select page" either.
  const sendableOnPage = (page?.items ?? [])
    .filter((i) => i.sendable && !justQueued.has(i.id) && !isGone(i.id));
  const onThisPage = sendableOnPage.filter((i) => picked.has(i.id)).length;
  const elsewhere = picked.size - onThisPage;
  // "all picked" also holds when the cap stopped us short of the page.
  const pageAllPicked = sendableOnPage.length > 0
    && (onThisPage === sendableOnPage.length || picked.size >= MAX_PICKS);

  const togglePage = () => setPicked((prev) => {
    const next = new Set(prev);
    for (const it of page?.items ?? []) {
      // Cannot be sent, or already queued from here: never auto-picked.
      if (!it.sendable || justQueued.has(it.id) || isGone(it.id)) continue;
      if (pageAllPicked) {
        next.delete(it.id);
      } else if (next.size < MAX_PICKS) {
        next.add(it.id);
      }
    }
    return next;
  });

  return (
    // The route area sits under SteamOS's header, so the content needs to
    // start below it or the title is clipped.
    // Header and footer are pinned; only the grid scrolls. Steam's scroll
    // follows the focused element, so anything unfocusable (the title, the
    // count, the page buttons) would otherwise be impossible to scroll
    // back to once you had moved past it.  Absolute rather than height:100%
    // because the route's parent does not give a resolvable height.
    <div style={{
      position: "absolute", left: 0, right: 0,
      top: HEADER_OFFSET, bottom: FOOTER_OFFSET,
      display: "flex", flexDirection: "column", color: "#dfe3e6",
    }}>
    {/* Kept deliberately short: every pixel here is a row of tiles the
        user cannot see. */}
    <style>{TILE_FOCUS_CSS}</style>
    <div style={{ flexShrink: 0, padding: "10px 32px 0" }}>
      {/* At a large UI scale the viewport narrows to ~850px; without
          these the title and blurb wrap to two lines each and swallow a
          row of tiles. Truncate instead. */}
      <div style={{
        display: "flex", alignItems: "baseline", gap: 14, marginBottom: 10,
        whiteSpace: "nowrap",
      }}>
        <h1 style={{ margin: 0, fontSize: "1.25em", flexShrink: 0 }}>
          {t("gallery_title")}
        </h1>
        <span style={{
          color: "#8b929a", fontSize: "0.85em",
          overflow: "hidden", textOverflow: "ellipsis", minWidth: 0,
        }}>
          {/* Button prompts live in SteamOS's own footer legend; repeating
              them here was just noise. */}
          {busy
            ? t("sending")
            : picked.size > 0
            ? t("gallery_picked", { n: picked.size }) +
              (picked.size >= MAX_PICKS ? " (" + t("gallery_pick_cap", { max: MAX_PICKS }) + ")" : "") +
              (pickedClips > 2 ? " · " + t("gallery_picked_clips", { n: pickedClips }) : "") +
              (elsewhere > 0 ? " · " + t("gallery_picked_elsewhere", { n: elsewhere }) : "") +
              (pickedTooLong > 0 ? " · " + t("gallery_too_long_warn", { n: pickedTooLong }) : "") +
              (pickedUnsendable > 0
                ? " · " + t("gallery_pick_delete_only", { n: pickedUnsendable }) : "")
            : t("gallery_subtitle")}
        </span>
      </div>

      <Focusable flow-children="horizontal"
        style={{ display: "flex", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
        {/* Kind and game are two filters of the same shape, so they read
            better as a matching pair than as three toggles plus a
            button. */}
        <div style={{ minWidth: 190 }}>
          <Dropdown
            rgOptions={KINDS.map((k) => ({ data: k, label: t(`gallery_kind_${k}`) }))}
            selectedOption={kind}
            onChange={(o) => changeView(() => {
              setKind(o.data as Kind);
              setGames(null);
            })}
          />
        </div>
        {/* Same control as the kind filter so the two read as a pair.
            Games load on first open, not with the page. */}
        <div style={{ minWidth: 260 }}>
          <Dropdown
            rgOptions={[
              { data: "", label: t("gallery_all_games") },
              ...(games ?? []).map((g) => ({
                data: g.ids, label: `${g.game} (${g.count})`,
              })),
            ]}
            selectedOption={appids}
            strDefaultLabel={gameName || t("gallery_all_games")}
            onChange={(o) => changeView(() => {
              setAppids(o.data as string);
              setGameName(o.data
                ? String(o.label).replace(/ \(\d+\)$/, "")
                : "");
            })}
          />
        </div>
        {/* Actions, not filters: pushed away from both. */}
        <div style={{ flex: 1 }} />
        {/* Deliberately a button and not a gamepad shortcut. Sending the
            wrong thing is embarrassing; deleting it is permanent, so this
            one has to be aimed at, and then confirmed. */}
        <DialogButton
          disabled={!picked.size || busy}
          onClick={confirmDelete}
          style={{ width: "auto", minWidth: 110, padding: "8px 14px" }}
        >
          {picked.size ? t("gallery_delete_n", { n: picked.size })
                       : t("gallery_delete")}
        </DialogButton>
        <DialogButton
          onClick={() => { setGames(null); load(offset, kind, true, appids); }}
          style={{ width: "auto", minWidth: 110, padding: "8px 14px" }}
        >
          {t("refresh")}
        </DialogButton>
      </Focusable>
    </div>

    {/* Only this scrolls; the header above and the bar below stay put.
        The vertical padding is not decoration: Steam scrolls a focused
        tile just barely into view, so without breathing room at each end
        the first and last rows sit flush against the header and the bar
        and read as clipped. */}
    <div style={{
      flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 32px 14px",
      scrollPaddingTop: 10, scrollPaddingBottom: 14,
    }}>
      {!page ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 60 }}>
          <Spinner style={{ width: 48, height: 48 }} />
        </div>
      ) : page.items.length === 0 ? (
        // Say why it is empty and offer the way out, rather than leaving a
        // blank screen with a filter the user may have forgotten setting.
        <Focusable flow-children="vertical" style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          gap: 14, padding: "48px 0", color: "#8b929a",
        }}>
          <div>{appids || kind !== "all" ? t("gallery_empty_filtered") : t("gallery_empty")}</div>
          {(appids || kind !== "all") && (
            <DialogButton
              onClick={() => changeView(() => {
                setAppids(""); setGameName(""); setKind("all");
              })}
              style={{ width: "auto", minWidth: 180, padding: "8px 16px" }}
            >
              {t("gallery_show_everything")}
            </DialogButton>
          )}
        </Focusable>
      ) : (
        // Sending is a gamepad button, not a control on screen: reaching
        // one would mean travelling past every tile. The footer legend
        // advertises it as soon as something is picked.
        <Focusable
          ref={gridRef}
          preferredFocus
          flow-children="grid"
          onSecondaryButton={() => { if (picked.size) void send(); }}
          onSecondaryActionDescription={
            picked.size ? t("gallery_send", { n: picked.size }) : undefined}
          onOptionsButton={() => setPicked(new Set())}
          onOptionsActionDescription={picked.size ? t("gallery_clear_all") : undefined}
          // Bumpers page through the library without leaving the grid.
          onButtonDown={(e: any) => {
            const b = e?.detail?.button;
            if (b === GamepadButton.BUMPER_LEFT && offset > 0) {
              load(Math.max(0, offset - PAGE));
            } else if (b === GamepadButton.BUMPER_RIGHT && offset + PAGE < total) {
              load(offset + PAGE);
            }
          }}
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(auto-fill, minmax(${TILE_MIN}px, 1fr))`,
            gap: 14, marginBottom: 22, alignItems: "start",
          }}
        >
          {page.items.map((it) => (
            <Tile key={it.id}
              item={{
                ...it,
                sent: it.sent || justQueued.has(it.id) || isGone(it.id),
                sendable: it.sendable && !isGone(it.id),
              }}
              thumb={thumbs[it.id]}
              picked={picked.has(it.id)} onToggle={() => toggle(it.id)} />
          ))}
        </Focusable>
      )}

    </div>

      {/* Paging and select-page only. Sending lives on X (and clearing on
          Y), advertised in SteamOS's footer legend - a send button down
          here would sit behind thirty tiles of travel, which is exactly
          the trip the button was meant to save. */}
      <Focusable flow-children="horizontal"
        style={{
          display: "flex", gap: 10, alignItems: "center", flexWrap: "nowrap",
          flexShrink: 0, padding: "10px 32px 14px",
          borderTop: "1px solid rgba(255,255,255,0.08)",
        }}>
        <DialogButton
          disabled={offset <= 0}
          onClick={() => load(Math.max(0, offset - PAGE))}
          style={{ width: "auto", minWidth: 100, padding: "8px 14px", whiteSpace: "nowrap" }}
        >
          {t("gallery_prev")}
        </DialogButton>
        <span style={{ color: "#8b929a", textAlign: "center", whiteSpace: "nowrap" }}>
          {t("gallery_page", { p: pageNo, of: pages, n: total })}
        </span>
        <DialogButton
          disabled={offset + PAGE >= total}
          onClick={() => load(offset + PAGE)}
          style={{ width: "auto", minWidth: 100, padding: "8px 14px", whiteSpace: "nowrap" }}
        >
          {t("gallery_next")}
        </DialogButton>
        <div style={{ flex: 1 }} />
        {/* Picking thirty tiles one at a time is the obvious tedium here. */}
        <DialogButton
          disabled={!page?.items.length}
          onClick={togglePage}
          style={{ width: "auto", minWidth: 130, padding: "8px 14px",
                   whiteSpace: "nowrap" }}
        >
          {t(pageAllPicked ? "gallery_deselect_page" : "gallery_select_page")}
        </DialogButton>
      </Focusable>
    </div>
  );
}

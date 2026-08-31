# Deckygram — working rules for AI-assisted development

This project is pair-programmed with Claude. Rules below are binding for
any AI session working in this repo.

## 🔒 Pre-publish audit (MANDATORY before every push / release)

Never push or release without checking that **no sensitive information**
reaches the public repo:

1. **Grep the full history**, not just the working tree, for:
   - Telegram bot tokens (`\d+:AA[A-Za-z0-9_-]+`) and chat ids
   - private LAN addresses (`192.168.`, hostnames of home machines)
   - passwords, API keys, OAuth secrets (`GOCSPX`, `gho_`, `rmm_`, ...)
   - SMB / SSH credentials
   ```bash
   git grep -I "<pattern>" $(git rev-list --all)
   ```
2. **Check commit authors** (`git log --format='%an <%ae>' | sort -u`) —
   no private email addresses beyond the intended public one.
3. Secrets live only in Decky's settings dir on the device (mode 600),
   never in this repo — keep it that way.
3-1. **No Claude session URLs in commit messages.** `Co-Authored-By:
   Claude ...` is welcome; `Claude-Session: https://claude.ai/...`
   trailers are NOT — they point at a private working conversation and
   do not belong in public history. (Removed from all history on
   2026-08-31; keep it out.)
4. If something sensitive ever lands in history: rewrite history
   (filter-repo) and rotate the leaked credential **before** pushing.

## Conventions

- **Batch pushes.** Commit locally as work lands, but push to GitHub in
  meaningful batches, not after every small change (owner's preference —
  also keeps CI runs and notification noise down).

- Backend stays **stdlib-only** Python; frontend deps are kept minimal.
- The zip layout must keep a single top-level `Deckygram/` folder.
- User-visible strings go through `src/i18n.ts` (English + 한국어).
- Toast/log strings from the backend are English (backend cannot see the
  Steam UI language).
- Releases: bump `package.json` version FIRST, then tag `v*` (same number)
  → CI attaches `Deckygram-vX.Y.Z.zip`.  A stale package.json makes the
  panel advertise our own current release as an "update".
- Attribution: this project is built with **Claude (Fable 5)** — keep the
  credit line at the bottom of README.md.

## Tech debt — pay BEFORE adding features

- `watcher.py` has grown past 550 lines and mixes four concerns.
  **Before the next feature lands**, split it: watch loop / inotify,
  sender (file+clip processing), queue/stats, captions.  Do not split
  "for cleanliness" while the code is freshly field-tested — split when
  you're about to touch it anyway.
- Pure logic has no unit tests yet (`appname` id-form conversions,
  `tg` bitrate/size math are ideal candidates).  Add them together with
  the split, and wire into CI.

## Update-checker lifecycle

- Our own GitHub release check exists ONLY because ZIP installs have no
  update channel. Decky's updater matches installed plugins against the
  STORE list **by name** (`store.tsx: checkForPluginUpdates`), so once
  Deckygram is in the official store, even ZIP-sideloaded installs get
  store update offers — remove `updates.py` and the panel row then.

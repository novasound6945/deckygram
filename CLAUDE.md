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
1-1. **Screenshots and images are data too.** A QR code in a screenshot
   is scannable; the wizard shots leaked the pairing URL (LAN IP + nonce)
   both as a QR and as plain text (caught 2026-08-31). Before publishing
   any screenshot, check it for QR codes, tokens, addresses, and account
   details — sanitize with a decoy QR / example address, and if an
   original already reached history, replace the blob everywhere
   (filter-branch --tree-filter, drop refs/original, reflog expire,
   gc --prune=now, force-push).
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

## Backend layout & tests

- Backend modules (split 2026-08-31, keep the boundaries):
  `watcher.py` orchestration/discovery/loop · `sender.py` send pipeline ·
  `qstate.py` queue+stats state · `captions.py` caption/manifest parsing
  (pure) · `inotify.py` ctypes wrapper · `tg.py` Bot API+encoding ·
  `appname.py` appid→name · `pairing.py` · `updates.py`.
- Unit tests live in `tests/` (stdlib `unittest`, no fs/network beyond
  tempdirs) and run in CI. When adding logic, put the pure part in a
  testable function and cover it — the batching rules, size math and
  vdf id-matching are the model to follow.
- Run locally (this PC has no Python):
  `docker run --rm -v C:\deckygram:/w -w /w python:3.12-alpine python -m unittest discover -s tests -t .`

## Update-checker lifecycle

- Our own GitHub release check exists ONLY because ZIP installs have no
  update channel. Decky's updater matches installed plugins against the
  STORE list **by name** (`store.tsx: checkForPluginUpdates`), so once
  Deckygram is in the official store, even ZIP-sideloaded installs get
  store update offers — remove `updates.py` and the panel row then.

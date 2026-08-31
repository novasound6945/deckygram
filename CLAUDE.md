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
3-1. **No Claude trailers in commit messages at all.** Neither
   `Co-Authored-By: Claude ...` nor `Claude-Session: https://claude.ai/...`
   belongs in this history. The session URL points at a private working
   conversation. The co-author trailer is parsed by GitHub, which then
   shows Claude on the commit and in the repository's contributor list —
   the owner does not want that, and attribution already lives where it
   was chosen: the credit line at the bottom of README.md. (Both removed
   from all history on 2026-08-31; keep them out.)
4. If something sensitive ever lands in history: rewrite history
   (filter-repo) and rotate the leaked credential **before** pushing.

## Conventions

- **Push only when releasing.** Commit locally as work lands, but do not
  push to GitHub until a release is actually going out — then push `main`
  and the `v*` tag together. Development history stays on the machine;
  what the public sees is releases (owner's rule, 2026-08-31). It also
  keeps CI runs and notification noise down.

- **One commit per release.** History was rewritten on 2026-08-31 to hold
  exactly one commit per released version, each carrying that release's
  tree. Keep it that way: work locally in as many commits as you like,
  then squash them into the release commit before tagging, listing the
  original subjects in the body so the reasoning survives.

- **Only `main` exists on the remote.** A public repo cannot hide a
  branch, so feature and backup branches live locally and are never
  pushed.

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
  `appname.py` appid→name · `pairing.py` · `updates.py` ·
  `library.py` which of Steam's media entries have no file behind them.

- **Deleting media: ask Steam, do not do it yourself.** Steam keeps its own
  record of screenshots and clips and only forgets an entry when it deleted
  the file itself; removing the file first leaves an entry pointing at
  nothing, which the media grid draws as a broken tile. The backend asks
  the frontend (the only side that can reach Steam) and sweeps up after a
  grace period if Steam did not. Two things that are easy to get wrong and
  cost a night each: **delete calls must not overlap** (five at once lost
  two, silently), and **screenshots need their react-query cache
  invalidated** afterwards or the grid keeps drawing the old list - clips
  do not, because they live in a store the grid watches.
- Unit tests live in `tests/` (stdlib `unittest`, no fs/network beyond
  tempdirs) and run in CI. When adding logic, put the pure part in a
  testable function and cover it — the batching rules, size math and
  vdf id-matching are the model to follow.
- Run locally (this PC has no Python):
  `docker run --rm -v C:\deckygram:/w -w /w python:3.12-alpine python -m unittest discover -s tests -t .`

## Distribution: GitHub only, permanently

The Decky store will not take this plugin. Its submission policy states,
under *"AI", LLMs and so on*: **"We do not accept any plugin that uses
any LLM based code… Any LLM focused plugins will be rejected outright and
there will be no appeals."** The stated reason is GPL-licence and
attribution concerns about model training data, so it targets
LLM-*written* code, not just plugins that call an LLM at runtime.
Deckygram is written with Claude and says so in the README. Removing that
credit to slip past the rule is not on the table.

Consequences for anyone working here:

- `updates.py` and the panel's update button are **permanent core
  features**, not a stopgap until store listing. They are the only update
  path users get, so treat regressions there as serious.
- The install story is the README's URL/ZIP flow. Keep the Decky-restart
  warning prominent; it is the most common failure report.
- Do not spend effort on store-submission prerequisites.

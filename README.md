# Deckygram

Send Steam Deck screenshots and recorded clips straight to your Telegram
the moment you take them - captioned with the game's name.

## Install

Until the plugin lands in the Decky store:

1. Grab `Deckygram.zip` from the
   [latest release](https://github.com/novasound6945/deckygram/releases/latest).
2. In Decky settings, enable **Developer mode**, then use
   **Developer → Install plugin from ZIP** (or unpack the zip into
   `~/homebrew/plugins/` yourself and restart Decky Loader).
3. Open Deckygram from the Quick Access menu - the setup wizard does the
   rest (bring your phone).

- **Instant**: watches Steam's screenshot and recording folders with
  inotify; a screenshot reaches your phone seconds after you press the
  button.
- **Game-aware captions**: resolves the game name for Steam games,
  non-Steam shortcuts (emulators!) and even uninstalled games.
- **Clips without exporting**: Steam's recorded clips are stored as DASH
  fragments; the plugin remuxes them to MP4 losslessly and sends them -
  no manual export step.
- **Fast, light video**: clips are compressed with the Deck's hardware
  H.265 encoder end to end (~7 % CPU), capped at 50 MB for Telegram's
  bot limit.
- **No cloud, no account**: media goes directly from your Deck to your
  own Telegram bot. Nothing else sees it.
- **Optional cleanup**: sent media can be deleted from the Deck
  automatically to free space.

## Setup

The plugin walks you through everything in the Quick Access menu:

1. Message **@BotFather** in Telegram, send `/newbot`, and paste the bot
   token into the plugin.
2. Send `/start` to your new bot, then tap **Detect my chat**.
3. Tap **Send test message**. Done.

Media that already existed before you enable the plugin is never sent -
only new screenshots and clips from that point on.

## Development

```bash
npm install       # or pnpm i
npm run build     # builds dist/index.js
```

Backend is dependency-free Python (stdlib only) in `py_modules/telegram_sender/`:

| module       | job |
|--------------|-----|
| `watcher.py` | inotify watch loop, debounce, clip remux, retry, delete-after-send |
| `tg.py`      | Telegram Bot API (stdlib multipart), video compression via VAAPI H.265 with H.264/x264 fallback |
| `appname.py` | appid → game name (appmanifest, shortcuts.vdf incl. 24-bit/64-bit shortcut id forms, store API, cached) |

`main.py` wires settings + the watcher to the Decky frontend
(`src/index.tsx`).

## Notes

- Telegram compresses photos it displays inline; originals stay on the
  Deck (unless delete-after-send is on).
- Videos longer than what fits in 50 MB at watchable quality are skipped.
- The bot token is stored with mode 600 in Decky's settings dir and is
  never shown back to the UI in full.

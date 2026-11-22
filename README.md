# Ultra Stalker for Windows (v2)

The Ultra Stalker interface — the same one as the website — as a Windows program,
by **Ahmed L-HadarY**.

What the program adds over the website:

- **Direct connections.** A small local server on `127.0.0.1` runs the website's relay
  code inside the program, so portals, Xtream and M3U servers are reached from this
  computer's own connection. Channels open as quickly as in VLC, and lines that refuse
  cloud servers work.
- **Every core for the Ultra engine.** The local server sends the cross-origin isolation
  headers, so the in-app FFmpeg engine (AC-3, E-AC-3, MP2, HEVC, 4K) runs multi-threaded.
- **A real window.** The gold top bar is the title bar; the Windows buttons sit inside it.
- **VLC inside.** VLC ships with the program and is one of the player engines:
  whatever the browser can't play smoothly (AC-3, MP2, HEVC, 4K 50 fps) plays in VLC,
  drawn inside the player window, with the program's own controls driving it.
- **Open in VLC** still hands the channel to a separate VLC when wanted.

## What 2.6 adds

- **Next episode.** A button (and the N key) next to the 10-second buttons; when an
  episode ends, a 10-second countdown plays the next one (also the first episode of
  the next season). Cancel or Play now.
- **Speed** (Settings, or `[` `]`): ½ to 2× — VLC uses its own steps (½ · 1 · 1.5 · 2).
- **Sleep timer** (Settings): stops playback after 15 / 30 / 60 / 90 minutes.
- **Shortcuts:** Space, ← →, ↑ ↓, mouse wheel = volume, PgUp/PgDn, F, M, N, `[` `]`,
  0–9 (jump to 0–90 %), S, R, P. The list is in Settings.
- **Pictures (S)** go to *Pictures\Ultra Stalker*: VLC saves its own; the browser
  player sends the frame; the Ultra engine's picture is taken from the window.
- **Recording live channels (R)** to *Videos\Ultra Stalker* (.ts). The bytes the player
  is already receiving through the local server are copied — no second connection to
  the line. A recording stops with the channel.
- **Mini player (P):** the same window, small, in the screen's corner and above every
  other window, with its own title bar. Works with every engine, VLC included.
- **Updates by itself:** each version that passes the installed self-test on `v2` is
  published as a GitHub release (installer, blockmap, `latest.yml`). The program checks
  20 s after starting and every 4 hours, downloads in the background and offers
  "Restart now"; otherwise it installs when the program closes.
- **Remembers:** the window's size and place, and opens the last live channel at start
  (Settings → Program to turn it off).
- **No adult content:** adult / +18 / XXX / "censored" categories, channels, movies and
  series are removed from categories, lists (also "All"), search and favorites, and
  can't be played (`app/adult-filter.js`).
- Controls hide after 3 seconds in full screen with VLC too: the program watches the
  mouse over VLC's picture window, and VLC's picture grows to the whole player while
  the controls are hidden. New 10-second icons.
- The program no longer reloads the page when the window crosses 1100 px.

## Player and browsing fixes (2.5.1)

- Settings opens picture, buffer and engine controls; audio/subtitles have their own button.
- Back/forward 10-second buttons and arrow keys accumulate rapid presses, including
  while VLC or the Ultra engine is still seeking. Seeks stay inside the video's duration.
- A visible, draggable gold scrollbar is available in the left category list.
- Player/animation class changes no longer rescan the category wall. VLC status
  reads cannot overlap, and paused playback keeps its last time without queued timeouts.

The desktop bundle applies `patches/desktop-ui.patch` to the pinned shared web
interface and embeds `app/seek-controller.js`. The web deployment is unchanged.
`npm test` includes browser checks using installed Chrome (Windows/macOS) or
`/usr/bin/chromium` (Linux; override with `US_CHROME_PATH`). Providers and VLC are
test doubles; native VLC playback and paused status are also checked in Windows CI.

## Server file cleaner and checker (2.5.0)

Open **Import Servers** in the sidebar or on Home, then choose a TXT, JSON, M3U
or M3U8 server file. The same tool as the desktop/mobile website removes duplicate
subscriptions and checks Stalker Portal, Xtream and M3U accounts through this
computer's local relay. A working result requires actual media bytes, not just a
successful login; account expiry and failed checks appear beside each result.

Stop/recheck at any time, download the cleaned file or only working subscriptions,
and add selected or all working servers without replacing saved sources or Favorites.
Files up to 5 MB / 1,000 subscriptions are supported.

Saved sources, favorites and settings stay on the computer. The receiver backup
(save / restore) works exactly as on the website.

## Build

```
npm ci
ULTRASTALKER_DIR=../UltraStalker npm run dist      # needs Windows (or CI)
```

The workflow also downloads the official VLC for Windows (videolan.org) into `vlc/`,
which the installer carries. Without it, an installed VLC is used.

`npm run bundle` copies `web/` and `worker/src/index.js` from the UltraStalker
repository into `bundle/`. The GitHub workflow builds the installer on every push to
`v2` and keeps it as the run's artifact.

The Windows workflow pins the shared interface to tested commit
`5dec24a6ff21091b162d3655ba92f8d73c7672af`, which includes Import Servers.
Use that revision (or a newer compatible checkout) for local builds too. Bundling
rejects older web sources that lack the cleaner/checker. `npm test` checks import,
deduplication, exports and actual stream verification through the desktop relay
using in-memory test providers; it does not contact real subscriptions.

## Layout

- `app/main.js` — window, title bar, downloads, single instance
- `app/vlc.js` — VLC inside the window: starts VLC with its remote-control port, draws
  it into a borderless window kept over the player, reads tracks and stream info
- `app/preload.cjs` — the only thing the page can ask of the program (`usNative.vlc`)
- `app/server.js` — local server: interface + relay (`/p`, `/ticket`, `/play`, `/health`);
  `/tmdb/…` goes to the online relay, which keeps the TMDB key
- `app/desktop-app.css` — the few things that differ from the website
- `scripts/bundle-web.mjs` — collects the interface for the installer
- `tests/server.test.js` — local server checks

The earlier PySide6 program is kept unchanged on the `main`, `new-ui` and
`desktop-windows-stability` branches.


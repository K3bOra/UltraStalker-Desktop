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


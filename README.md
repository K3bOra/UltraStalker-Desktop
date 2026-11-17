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

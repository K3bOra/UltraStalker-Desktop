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
- **Open in VLC** hands the channel to VLC when it is installed.

Saved sources, favorites and settings stay on the computer. The receiver backup
(save / restore) works exactly as on the website.

## Build

```
npm ci
ULTRASTALKER_DIR=../UltraStalker npm run dist      # needs Windows (or CI)
```

`npm run bundle` copies `web/` and `worker/src/index.js` from the UltraStalker
repository into `bundle/`. The GitHub workflow builds the installer on every push to
`v2` and keeps it as the run's artifact.

## Layout

- `app/main.js` — window, title bar, downloads, single instance
- `app/server.js` — local server: interface + relay (`/p`, `/ticket`, `/play`, `/health`);
  `/tmdb/…` goes to the online relay, which keeps the TMDB key
- `app/desktop-app.css` — the few things that differ from the website
- `scripts/bundle-web.mjs` — collects the interface for the installer
- `tests/server.test.js` — local server checks

The earlier PySide6 program is kept unchanged on the `main`, `new-ui` and
`desktop-windows-stability` branches.

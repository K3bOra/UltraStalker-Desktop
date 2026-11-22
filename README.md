# Ultra Stalker for Android TV

The Ultra Stalker interface — the same as the website and the Windows program — on
Android TV, Google TV, TV boxes and Fire TV, by **Ahmed L-HadarY**. Everything works
with the remote: arrows, OK and Back.

- **A local server inside the app** (`relay/`, Kotlin): the website's relay (`/p`,
  `/ticket`, `/play`) and the interface's files on `127.0.0.1`, so portals, Xtream and
  M3U servers are reached directly from the home connection.
- **VLC inside** (libVLC): the page's player drives it through `window.usNative.vlc`,
  exactly like the Windows program; VLC's picture is a view kept over the player area,
  the gold controls stay the page's own.
- **The remote** (`tv-web/tv.js`): a gold focus moves to the nearest card, button or
  category in the arrow's direction; OK opens; Back closes menus, controls, the
  player, panels, then goes back a page. In the player: ← → 10 seconds, ↑ ↓ channel
  (live), OK pause/play and controls. Media keys and channel keys work too.
- **The interface** comes from `UltraStalker-Desktop` `v2` (`npm run bundle`): the
  program's player (next episode, speed, sleep timer), the adult filter and its features.

## Build

```
# in UltraStalker-Desktop (v2):  ULTRASTALKER_DIR=../UltraStalker npm run bundle
node scripts/make-site.mjs ../UltraStalker-Desktop
./gradlew :relay:test :app:assembleRelease      # → app/build/outputs/apk/release
```

The GitHub workflow does all of this on every push to `android-tv` and keeps the APK
as the run's artifact. The APK is signed with `signing/ultrastalker-tv.jks`, so a new
version installs over the old one.

## Tests

- `relay/src/test` — the relay on the JVM against a fake portal (Stalker sign-in and
  links, ranges, HLS rewriting, headers).
- `tests/remote.test.js` — the TV's server (`./gradlew :relay:serve`) with Chrome at
  1280 px, driven by arrow keys, OK and Back; VLC and the provider are fakes.

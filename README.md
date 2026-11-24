# Ultra Stalker for Android TV

A native Android TV app (Kotlin, Compose for TV, libVLC) by **Ahmed L-HadarY**, for
Android TV, Google TV, TV boxes and Fire TV. Black and gold, made for the remote.

- **Servers**: Stalker portals (MAC), Xtream Codes lines and M3U playlists
  (`relay/src/main/kotlin/.../core`, plain Kotlin, the same rules as the website).
- **Live TV, movies, series**: categories on the left, channels or posters on the right;
  a category opens when the remote rests on it. Seasons and episodes, "last watched",
  resume where you stopped.
- **Player** (libVLC): live — ▲ ▼ change channel, OK / ◀ the channel list, number keys
  jump to a channel; movies — ◀ ▶ 10 seconds (hold for a minute), OK the controls
  (pause, audio, subtitles, picture size, next episode). The next episode plays by itself.
- **Backups**: the receiver's or the website's backup ZIP, a `profiles.json` or a
  `portals.txt`, sent from a phone by scanning a QR code (same Wi-Fi), or opened from
  the TV's storage.
- **No adult content**: adult folders, channels and titles are removed everywhere.
- Portal streams go through a small relay inside the app (`relay/`) that asks the
  portal for a fresh link each time; Xtream and M3U streams go straight to VLC.

## Build

```
./gradlew :relay:test :app:testDebugUnitTest -Proborazzi.test.record=true :app:assembleRelease
```

Screens are saved in `app/build/screens`. The APK is signed with
`signing/ultrastalker-tv.jks`, so a new version installs over the old one. The GitHub
workflow builds and tests every push to `android-tv` and publishes the APK at
https://github.com/K3bOra/UltraStalker-Desktop/releases/download/tv-latest/UltraStalker-TV.apk

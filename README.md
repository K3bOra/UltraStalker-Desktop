# Ultra Stalker Desktop

Developer / Author: **Ahmed L-HadarY**

Independent Windows application derived from the functional behavior of Ultra Stalker 8.4.1. The desktop codebase is isolated from Enigma2 and contains no Enigma2 imports.
The official 8.4.1 package is tracked as a behavioral/reference artifact; this repository does not claim byte-for-byte source parity because the original 8.4.1 source bytes are not part of this workspace.

## Implemented sources
- Stalker/MAG: handshake/profile, adaptive portal endpoints, full Live list with paginated fallback, Live/VOD/Series categories, VOD-backed Series compatibility, episodes, create_link, and token refresh.
- Xtream: authentication, Live, VOD, Series, episodes, URL-safe stream construction.
- M3U: playlist parsing, Live/Movies/Series classification, episode grouping/sorting, stable item identity, and token-rotation-safe rehydration.

## Desktop features
- Saved Profiles/Login with Windows Credential Manager for provider secrets. Stalker MAC, Xtream password, M3U URL, TMDb key, and credential-bearing Stalker/Xtream endpoint URLs are never intentionally persisted in plaintext metadata. A successful connection can continue session-only if secure persistence is unavailable; no plaintext fallback is used.
- Automatic upgrade migration moves legacy plaintext profile/TMDb secrets into Windows Credential Manager before scrubbing the old JSON fields; secure Vault values take precedence over stale plaintext copies.
- Home / Live / Movies / Series.
- Category and item browser with stale-request cancellation.
- Series episodes and Next Episode selection.
- Global search.
- Favorites.
- History / Continue Watching / Resume.
- SQLite catalog cache and per-source state isolation, with schema version 1, downgrade protection, corruption-safe connection cleanup, and read-only integrity diagnostics.
- Optional TMDb metadata.
- Source fallback handling.
- Bundled mpv playback with Pause/Resume, Seek, Volume, Audio and Subtitle track cycling.
- Crash logging and sanitized diagnostics bundle. Metadata-corruption markers contain only file name, size, SHA256, and error class; damaged profile/settings contents and the SQLite database are never included.
- Build fingerprinting, provenance, Build ID, installer SHA256, and About/Build Info.
- One-command Windows build pipeline using PyInstaller + Inno Setup.
- Windows release packaging explicitly includes the WinVault keyring backend and its `pywin32-ctypes` bridge; the packaged self-test verifies the real Credential Manager backend end-to-end.

## Release rule
A source-level pass is not called Final. The release pipeline must pass the packaged Windows build self-test, while later installed `--self-test` runs write only to Local AppData so they cannot mutate the fingerprinted payload. The real authorized-source checks remain in `WINDOWS_ACCEPTANCE.md`. Final installer identity is recorded in `release/FINAL_RELEASE.json`.

## Frozen source provenance
The Windows release pipeline verifies `SOURCE_FREEZE.json` before dependency resolution. The portable provenance and final release manifest record both the frozen source-tree SHA256 and the freeze-manifest SHA256. The release bundle includes the exact verified `SOURCE_FREEZE.json`; any intentional source change requires a new complete regression, clean-room validation, and regenerated freeze manifest.

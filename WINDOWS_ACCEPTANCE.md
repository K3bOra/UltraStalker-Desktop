# Ultra Stalker Desktop - Windows Acceptance Gate

Developer: Ahmed L-HadarY  
Reference behavior: Ultra Stalker 8.4.1  
Target: Windows x64 (Windows 10 1809 or later / Windows 11)

A build is not a final release until every mandatory item below passes on Windows.

## Build and install
- Run `build_windows.bat` from a clean checkout/folder.
- Static release gate and all unit tests pass.
- PyInstaller produces `dist/UltraStalkerDesktop/UltraStalkerDesktop.exe`.
- Verified bundled `mpv.exe` is present.
- Release pipeline `--self-test-build` passes SQLite, mpv, Windows Credential Manager, and the real Windows Qt platform, and writes the fingerprinted build report beside the packaged EXE.
- Installed `--self-test` writes a fresh runtime report only to `%LOCALAPPDATA%\UltraStalker\diagnostics\SELF_TEST.json`, must not modify the fingerprinted build `SELF_TEST.json` beside the EXE, and must pass the read-only user-database integrity check (`ok` or first-run `not_created`).
- Inno Setup creates exactly one installer.
- The build pipeline silently installs that exact Setup into an isolated `%TEMP%` directory, verifies every fingerprinted installed file, runs the installed runtime self-test with sandboxed AppData, proves the installed payload stays byte-identical, and silently uninstalls it.
- `release/INSTALLER_SMOKE_TEST.json` exists and is bound to the same installer SHA256, Build ID, and portable provenance as the final release.
- `release/FINAL_RELEASE.json` exists and contains the installer SHA256 and Build ID.
- Installer completes as a standard user without requiring administrator rights.
- On first start after upgrading an older build, legacy plaintext Stalker MAC / Xtream password / M3U URL / TMDb API key values are migrated to Windows Credential Manager and scrubbed from JSON only after verified secure writes.
- A pre-existing newer Windows Credential Manager value must win over any stale plaintext legacy value during migration.
- `profiles.json` must not contain Stalker MACs, Xtream passwords, M3U URLs, or credential-bearing endpoint user-info/token query values after migration/save. If secure profile persistence fails after a successful connection, the source remains usable for that process as a clearly labeled session-only connection with no plaintext fallback.
- Windows packaged self-test reports `keyring.backends.Windows.WinVaultKeyring` as the credential backend and confirms credential probe cleanup.
- Run `release/VERIFY_INSTALLED.ps1` after installation. It must pass installed EXE/mpv hashes, run the safe runtime `--self-test`, prove the immutable build `SELF_TEST.json` was not modified, and verify the runtime report is written only under `%LOCALAPPDATA%\UltraStalker\diagnostics`.
- Automated installer smoke test performs an in-place second install as an upgrade, preserves sandboxed Roaming/Local AppData sentinels, removes a seeded obsolete `_internal` runtime file, and re-runs installed runtime verification.
- Upgrade over the same AppId preserves user profiles/history/favorites/settings.
- Silent uninstall removes application files while automated smoke verification proves sandboxed user data is preserved.

## Profile and source flows
Use only user-authorized sources.

### Stalker/MAG
- Add MAC profile and reconnect from saved profile.
- Handshake/profile succeeds.
- Live categories and multi-page channel lists load.
- Movies and Series load.
- Series episodes load and sort correctly.
- `create_link` resolves and playback starts.
- A long-running session can recover from one expired token.

### Xtream
- Login with username/password and reconnect from saved profile.
- Live / Movies / Series categories and items load.
- Series episodes play.
- Credentials containing reserved URL characters still produce valid stream URLs.

### M3U
- Playlist loads and groups appear.
- Live / Movies / Series classification matches the playlist/provider structure.
- Series episode names such as `S01E02`, `1x02`, and `Season 1 Episode 2` group and sort correctly.
- Channel/media IDs remain stable across playlist reorder/token rotation when identity metadata is unchanged.
- Saved favorite/history movie and episode items rehydrate to the current stream URL.

## Playback
- Live, movie, and episode playback starts in bundled mpv.
- Pause / Resume works.
- Seek -30s / +30s works for seekable media.
- Volume controls work.
- Audio track cycling works where multiple tracks exist.
- Subtitle track cycling works where subtitles exist.
- Stop is responsive.
- Failed primary source tries a valid fallback source.
- A failed/stalled IPC command does not freeze the UI indefinitely.

## Persistence
- SQLite `PRAGMA user_version` is 1 for this release; opening a newer future schema with this older build fails safely instead of modifying it.
- If `profiles.json` or `settings.json` is malformed, save/delete operations do not overwrite it. A safe corruption marker records only SHA256/size/error type.
- Favorites survive application restart.
- History survives application restart.
- Resume starts only when a useful previous position exists.
- Completed episodes are not selected as Next Episode.
- Different source profiles do not share cache/history/favorites accidentally.
- Long-lived history/favorite payloads do not duplicate resolved stream credentials.

## UI and stability
- Single-click category selection loads the category.
- Rapid category switching does not let stale responses overwrite the latest view.
- Rapid repeated Connect attempts cannot mix profiles/adapters.
- Closing during a large catalog operation cancels pagination after the current network request.
- No `QThread destroyed while thread is still running` crash appears.

## Diagnostics and release identity
- About shows version, developer, reference, and Build ID.
- Diagnostics ZIP is created successfully.
- Diagnostics contains no profile JSON, settings JSON, database, MAC, portal URL, tokens, or passwords. It may include safe profile/settings corruption markers containing only file name, size, SHA256, and error type.
- Diagnostics/runtime self-test reports the read-only SQLite integrity status without copying the database.
- Reported Build ID matches `FINAL_RELEASE.json`.
- Installer SHA256 matches `FINAL_RELEASE.json`.

Only after the mandatory Windows checks pass should the build be promoted from Release Candidate to Final.

## Frozen source provenance
- Confirm the release bundle contains `SOURCE_FREEZE.json`.
- `VERIFY_RELEASE.ps1` must confirm its SHA256 matches `FINAL_RELEASE.json`.
- `source_tree_sha256` must match between `SOURCE_FREEZE.json`, portable `provenance.json`, and `FINAL_RELEASE.json`.
- A source change after freeze must stop the Windows bootstrap before dependency resolution.

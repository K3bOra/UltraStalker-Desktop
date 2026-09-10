# 8.4.1 -> Desktop mapping

## Behavioral alignment target from Ultra Stalker 8.4.1
- Portal normalization
- Authentication / handshake behavior
- MAC profile semantics
- Catalog parsing
- Live category/channel loading
- VOD category/movie loading
- Series/seasons/episodes loading
- create_link / stream URL behavior
- Source fallback policy
- Search / Favorites / History / Resume
- Cache semantics and source isolation
- TMDb metadata / artwork

## Replace completely
- Enigma2 Screen / Session classes
- ActionMap / remote-key bindings
- eServiceReference and Enigma2 player integration
- Enigma2 config APIs
- Enigma2 filesystem paths
- opkg installer/dependencies
- image-specific restart/reboot behavior

## Desktop equivalents
- Screens -> PySide6 widgets
- Player -> mpv backend
- Settings -> AppData + local structured storage
- Remote keys -> keyboard/controller actions
- Enigma2 service events -> Qt signals/events

## Provenance boundary
The official Ultra Stalker 8.4.1 package is tracked by artifact name and SHA256. The original 8.4.1 source bytes are not available in this workspace, so this desktop implementation records behavioral-reference provenance and does not claim byte-for-byte source parity.

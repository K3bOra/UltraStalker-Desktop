# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# PyInstaller's official PySide6 hooks discover only the Qt modules/plugins
# actually imported by the application. Avoid collect_all('PySide6'), which
# would drag unused WebEngine/QML/etc. into a simple QtWidgets desktop app.
keyring_data, keyring_bins, keyring_hidden = collect_all('keyring')
# WinVault is selected explicitly at runtime, so keep its dynamic backend and
# pywin32-ctypes bridge explicit too. The packaged self-test still verifies
# the real Windows Credential Manager end-to-end.
keyring_hidden = sorted(set(keyring_hidden + [
    'keyring.backends.Windows',
    'win32ctypes.pywin32.pywintypes',
    'win32ctypes.pywin32.win32cred',
]))

a = Analysis(
    ['ultrastalker_desktop/main.py'],
    pathex=['.'],
    binaries=keyring_bins,
    datas=keyring_data,
    hiddenimports=keyring_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='UltraStalkerDesktop',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='resources/version_info.txt',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='UltraStalkerDesktop',
)

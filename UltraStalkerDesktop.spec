# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# PyInstaller's official PySide6 hooks discover only the Qt modules/plugins
# actually imported by the application. Avoid collect_all('PySide6'), which
# would drag unused QML/etc. into the app. Qt WebEngine is collected by its
# own hook because the cinematic interface imports QtWebEngineWidgets.
import os
from pathlib import Path

# The cinematic interface: local page, styles, script and bundled fonts.
# mock.js is a development stand-in for the Python bridge and is not shipped.
ui_data = [
    (str(path), str(Path('ultrastalker_desktop/ui/app') / path.relative_to('ultrastalker_desktop/ui/app').parent).replace(os.sep, '/'))
    for path in sorted(Path('ultrastalker_desktop/ui/app').rglob('*'))
    if path.is_file() and path.name != 'mock.js'
]
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
    datas=keyring_data + ui_data,
    hiddenimports=keyring_hidden + [
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebChannel',
        'PySide6.QtSvg',
    ],
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

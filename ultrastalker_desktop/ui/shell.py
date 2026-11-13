"""Main window: the cinematic web interface plus the in-app player.

The interface is a local page (ui/app) rendered by Qt WebEngine. It talks to
``Bridge`` through QWebChannel. Video never runs in the web page: mpv/VLC draw
into native child windows placed either over the live preview box or full
window (``PlayerView``).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow, QWidget

from ultrastalker_desktop import __version__
from ultrastalker_desktop.player.mpv_backend import MPVBackend
from ultrastalker_desktop.player.vlc_backend import VLCBackend
from ultrastalker_desktop.runtime import local_data_dir, resource_candidates
from ultrastalker_desktop.storage import database as db
from ultrastalker_desktop.ui.bridge import Bridge
from ultrastalker_desktop.ui.player_view import PlayerView, VideoSurface

log = logging.getLogger(__name__)


def app_dir() -> Path:
    return Path(__file__).resolve().parent / "app"


class _Page(QWebEnginePage):
    """Keep the window on the local interface; nothing navigates it elsewhere."""

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if not is_main_frame:
            return True
        if url.isLocalFile() and Path(url.toLocalFile()).resolve().parent == app_dir().resolve():
            return True
        if url.scheme() in ("http", "https") and nav_type == QWebEnginePage.NavigationTypeLinkClicked:
            QDesktopServices.openUrl(url)
        return False

    def createWindow(self, _type):
        return None

    def javaScriptConsoleMessage(self, level, message, line, source):
        if level == QWebEnginePage.ErrorMessageLevel:
            log.debug("UI script error at line %s: %s", line, str(message)[:200])


class _Central(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.shell = shell

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.shell._layout()


class ShellWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ultra Stalker")
        self.resize(1500, 900)
        self.setMinimumSize(1180, 700)
        self._was_maximized = False
        for icon in resource_candidates("UltraStalker.ico") + resource_candidates("assets/UltraStalker.ico"):
            if icon.is_file():
                self.setWindowIcon(QIcon(str(icon)))
                break
        self.setStyleSheet("QMainWindow, QWidget#central { background: #030807; }")

        self.central = _Central(self)
        self.central.setObjectName("central")
        self.setCentralWidget(self.central)

        self.bridge = Bridge(host=self)

        profile_dir = local_data_dir() / "web"
        self.profile = QWebEngineProfile("UltraStalkerUI", self)
        self.profile.setPersistentStoragePath(str(profile_dir / "storage"))
        self.profile.setCachePath(str(profile_dir / "cache"))
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.setHttpCacheMaximumSize(400 * 1024 * 1024)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

        self.view = QWebEngineView(self.central)
        self.page = _Page(self.profile, self.view)
        self.page.setBackgroundColor(QColor("#030807"))
        s = self.page.settings()
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        s.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        s.setAttribute(QWebEngineSettings.ErrorPageEnabled, False)
        self.view.setPage(self.page)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)

        self.channel = QWebChannel(self.page)
        self.channel.registerObject("bridge", self.bridge)
        self.page.setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(str(app_dir() / "index.html")))

        self.player = PlayerView(self._backend, self.central)
        self.player.on_progress_save = self._save_progress
        self.player.on_finished = self._finished
        self.player.closed.connect(self._player_closed)
        self.player.failed.connect(lambda msg: self.bridge.emit_event("player", state="error", message=msg))

        self.preview = VideoSurface(self.central)
        self.preview.hide()
        self.preview_backend = None
        self.preview_gen = 0
        self._layout()
        QTimer.singleShot(0, self._dark_title_bar)

    # ------------------------------------------------------------------ window
    def _layout(self):
        r = self.central.rect()
        self.view.setGeometry(r)
        self.player.setGeometry(r)

    def _dark_title_bar(self):
        if os.name != "nt":
            return
        try:
            import ctypes

            hwnd = int(self.winId())
            value = ctypes.c_int(1)
            for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                    break
            color = ctypes.c_int(0x00070803)  # DWMWA_CAPTION_COLOR, BGR of #030807
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
        except Exception:
            pass

    def toggle_window_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized() if self._was_maximized else self.showNormal()
            return False
        self._was_maximized = self.isMaximized()
        self.showFullScreen()
        return True

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F11:
            self.toggle_window_fullscreen()
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ players
    def _backend(self):
        choice = str(self.bridge.settings.get("player") or "mpv").lower()
        mpv, vlc = MPVBackend(), VLCBackend()
        order = [vlc, mpv] if choice == "vlc" else [mpv, vlc]
        for b in order:
            try:
                if b._exe():
                    return b
            except Exception:
                continue
        return order[0]  # its play() explains what is missing

    def start_playback(self, item, view, urls, start, source_key):
        self.stop_preview()
        self._source_key = source_key
        self.player.start(item, view, urls, start, source_key)

    def stop_playback(self, silent=False):
        self.stop_preview()
        if self.player.isVisible():
            self.player.close_player(silent=True)

    def _player_closed(self):
        self.view.setFocus()
        self.bridge.emit_event("player", state="closed")

    def _save_progress(self, item, pos, dur):
        try:
            db.update_progress(self._source_key, item, pos, dur)
        except Exception as exc:
            log.warning("Progress save failed: %s", type(exc).__name__)

    def _finished(self, item):
        if (item.kind or "") == "episode":
            self.bridge.play_next_episode(item)

    # live preview box -------------------------------------------------
    def _rect(self, rect):
        try:
            return QRect(int(rect["x"]), int(rect["y"]), max(1, int(rect["w"])), max(1, int(rect["h"])))
        except Exception:
            return None

    def start_preview(self, item, view, urls, rect):
        if self.player.isVisible():
            return
        r = self._rect(rect)
        if r is None:
            return
        self.stop_preview(hide=False)
        self.preview_gen += 1
        gen = self.preview_gen
        self.preview.setGeometry(r)
        self.preview.show()
        self.preview.raise_()
        backend = self._backend()
        backend.embed_wid = int(self.preview.winId())
        self.preview_backend = backend

        def task():
            try:
                backend.play_candidates(urls, 0, should_cancel=lambda: gen != self.preview_gen)
            except Exception:
                if gen == self.preview_gen:
                    self.bridge.on_gui(lambda: self._preview_failed(gen))

        self.player.pool.submit(task)

    def _preview_failed(self, gen):
        if gen != self.preview_gen:
            return
        self.stop_preview()
        self.bridge.emit_event("player", state="preview-error", message="This channel did not open.")

    def move_preview(self, rect):
        r = self._rect(rect)
        if r is not None and self.preview.isVisible():
            self.preview.setGeometry(r)

    def stop_preview(self, hide=True):
        self.preview_gen += 1
        b, self.preview_backend = self.preview_backend, None
        if b is not None:
            self.player.pool.submit(b.stop)
        if hide:
            self.preview.hide()

    # ------------------------------------------------------------------ close
    def closeEvent(self, e):
        try:
            self.stop_preview()
            self.player.shutdown()
            self.bridge.shutdown()
        finally:
            super().closeEvent(e)

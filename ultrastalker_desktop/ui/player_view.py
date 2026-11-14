"""Full-window player: the video renders inside the app, with an on-screen control bar.

mpv (or VLC) draws into ``PlayerView.video`` through its native window id. The
control bar is a native child placed above it and auto-hides while playing.
All player IPC runs on a worker thread so a stalled stream never freezes the UI.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QByteArray, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

log = logging.getLogger(__name__)

_ICONS = {
    "back": '<path d="M15 5l-7 7 7 7" fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "play": '<path d="M7 4.5v15l12.5-7.5z" fill="{c}"/>',
    "pause": '<rect x="6" y="4.5" width="4.2" height="15" rx="1.2" fill="{c}"/><rect x="13.8" y="4.5" width="4.2" height="15" rx="1.2" fill="{c}"/>',
    "rew": '<path d="M11.5 6.5 4.5 12l7 5.5zM19.5 6.5 12.5 12l7 5.5z" fill="{c}"/>',
    "fwd": '<path d="M12.5 6.5 19.5 12l-7 5.5zM4.5 6.5 11.5 12l-7 5.5z" fill="{c}"/>',
    "next": '<path d="M5 5.5v13l9.5-6.5z" fill="{c}"/><rect x="16" y="5.5" width="3" height="13" rx="1" fill="{c}"/>',
    "audio": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="{c}"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a8.5 8.5 0 0 1 0 12" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round"/>',
    "subs": '<rect x="3" y="5.5" width="18" height="13" rx="3" fill="none" stroke="{c}" stroke-width="2"/><path d="M7 14.5h4M13 14.5h4M7 11h10" stroke="{c}" stroke-width="2" stroke-linecap="round"/>',
    "full": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>',
    "vol_down": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="{c}"/><path d="M15 12h5" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>',
    "vol_up": '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="{c}"/><path d="M15 12h5M17.5 9.5v5" stroke="{c}" stroke-width="2.2" stroke-linecap="round"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2" fill="{c}"/>',
}


def svg_icon(name: str, color: str = "#f1f5f3", size: int = 24) -> QIcon:
    from PySide6.QtSvg import QSvgRenderer

    body = _ICONS[name].replace("{c}", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    icon = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p, QRectF(0, 0, size * scale, size * scale))
        p.end()
        pm.setDevicePixelRatio(scale)
        icon.addPixmap(pm)
    return icon


STRINGS = {
    "ar": {"back": "رجوع (Esc)", "audio": "تراك الصوت (A)", "subs": "الترجمة (S)", "rew": "رجوع 10 ثواني (←)",
           "play": "تشغيل / إيقاف مؤقت (مسافة)", "fwd": "تقديم 30 ثانية (→)", "next": "الحلقة اللي بعدها (N)",
           "vdown": "وطّي الصوت (↓)", "vup": "علّي الصوت (↑)", "full": "ملء الشاشة (F)", "ends": "ينتهي", "live": "مباشر",
           "opening": "جاري الفتح…", "failed": "القناة أو الفيلم مفتحش. جرّب تاني أو اختار حاجة تانية.",
           "days": ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]},
    "en": {"back": "Back (Esc)", "audio": "Audio track (A)", "subs": "Subtitles (S)", "rew": "Back 10s (←)",
           "play": "Play / pause (Space)", "fwd": "Forward 30s (→)", "next": "Next episode (N)",
           "vdown": "Volume down (↓)", "vup": "Volume up (↑)", "full": "Full screen (F)", "ends": "Ends", "live": "LIVE",
           "opening": "Opening…", "failed": "This stream could not be opened. Try again or pick another.",
           "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
}


def clock(sec: float) -> str:
    sec = max(0, int(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


OSD_QSS = """
QFrame#osd {
  background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0c1a15, stop:1 #040a08);
  border-top: 2px solid qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #35d39b, stop:1 #e0464f);
}
QFrame#topbar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #050b09, stop:1 #0a1511); }
QLabel { color: #f1f5f3; background: transparent; font-family: "Cairo", "Segoe UI"; }
QLabel#title { font-size: 21px; font-weight: 800; }
QLabel#meta { color: #9fb2aa; font-size: 13px; }
QLabel#time { color: #f1f5f3; font-size: 14px; font-weight: 700; }
QLabel#clock { color: #f1f5f3; font-size: 22px; font-weight: 800; }
QLabel#ends { color: #9fb2aa; font-size: 12px; }
QLabel#live { color: #fff; background: #e0464f; border-radius: 6px; padding: 2px 10px; font-weight: 900; font-size: 12px; }
QLabel#status { color: #35d39b; font-size: 13px; font-weight: 700; }
QToolButton { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); border-radius: 22px; padding: 8px; }
QToolButton:hover { background: rgba(53,211,155,0.22); border-color: #35d39b; }
QToolButton:pressed { background: rgba(53,211,155,0.35); }
QToolButton#main { background: #1fa874; border: 1px solid #5ff0bb; border-radius: 28px; }
QToolButton#main:hover { background: #29bf86; }
QWidget#ctrlrow { background: transparent; }
QLabel#poster { background: #0b1714; border: 1px solid rgba(255,255,255,0.16); border-radius: 10px; }
QLabel#chip { color: #dfe8e4; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.14); border-radius: 7px; padding: 2px 9px; font-size: 11.5px; font-weight: 700; }
QLabel#bigclock { color: #ffffff; font-size: 30px; font-weight: 900; }
QLabel#date { color: #35d39b; font-size: 12.5px; font-weight: 700; }
QToolButton#round { border-radius: 20px; }
QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.16); border-radius: 3px; }
QSlider::sub-page:horizontal { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1fa874, stop:1 #35d39b); border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #ffffff; border: 2px solid #35d39b; }
"""


class _Video(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#000000"))
        self.setPalette(pal)


class VideoSurface(_Video):
    """Bare native surface used for the live preview box."""


class PlayerView(QWidget):
    closed = Signal()
    failed = Signal(str)
    _ui = Signal(object)

    def __init__(self, backend_factory, parent=None):
        super().__init__(parent)
        self.backend_factory = backend_factory
        self.backend = None
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="us-player")
        self.generation = 0
        self.item = None
        self.view = {}
        self.source_key = ""
        self.live = False
        self.position = 0.0
        self.duration = 0.0
        self.paused = False
        self.volume = 100
        self._polling = False
        self._last_save = 0.0
        self._last_cursor = QPoint()
        self._seeking = False
        self.playing = False
        self.on_progress_save = None  # callable(item, pos, dur) set by the shell
        self.on_finished = None       # callable(item) set by the shell (autoplay next)
        self._ui.connect(lambda fn: fn())

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(OSD_QSS)
        pal = self.palette(); pal.setColor(self.backgroundRole(), QColor("#000")); self.setPalette(pal); self.setAutoFillBackground(True)

        self.video = _Video(self)
        # Create the video's native window first so the control bars, created
        # after it, always stack above the picture.
        self._video_wid = int(self.video.winId())
        self.lang = "ar"
        self.top = QFrame(self); self.top.setObjectName("topbar"); self.top.setAttribute(Qt.WA_NativeWindow, True)
        tl = QHBoxLayout(self.top); tl.setContentsMargins(22, 10, 22, 10)
        self.btn_back = self._btn("back", "", self.close_player, 40); self.btn_back.setObjectName("round")
        self.status = QLabel(""); self.status.setObjectName("status")
        self.top_title = QLabel(""); self.top_title.setObjectName("meta")
        tl.addWidget(self.btn_back); tl.addSpacing(12); tl.addWidget(self.top_title); tl.addSpacing(10); tl.addWidget(self.status); tl.addStretch(1)

        self.osd = QFrame(self); self.osd.setObjectName("osd"); self.osd.setAttribute(Qt.WA_NativeWindow, True)
        outer = QHBoxLayout(self.osd); outer.setContentsMargins(26, 16, 26, 16); outer.setSpacing(20)
        self.poster = QLabel(); self.poster.setObjectName("poster"); self.poster.setFixedSize(104, 156); self.poster.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.poster, 0, Qt.AlignVCenter)
        ol = QVBoxLayout(); ol.setSpacing(8); outer.addLayout(ol, 1)
        row1 = QHBoxLayout(); row1.setSpacing(14)
        info = QVBoxLayout(); info.setSpacing(2)
        self.title = QLabel(""); self.title.setObjectName("title")
        self.meta = QLabel(""); self.meta.setObjectName("meta")
        chips = QHBoxLayout(); chips.setSpacing(6); chips.setContentsMargins(0, 4, 0, 0)
        self.chip_labels = [QLabel("") for _ in range(4)]
        for c in self.chip_labels:
            c.setObjectName("chip"); c.hide(); chips.addWidget(c)
        chips.addStretch(1)
        info.addWidget(self.title); info.addWidget(self.meta); info.addLayout(chips)
        self.live_badge = QLabel("LIVE"); self.live_badge.setObjectName("live")
        clk = QVBoxLayout(); clk.setSpacing(0)
        self.clock = QLabel(""); self.clock.setObjectName("bigclock"); self.clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.date = QLabel(""); self.date.setObjectName("date"); self.date.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ends = QLabel(""); self.ends.setObjectName("ends"); self.ends.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        clk.addWidget(self.clock); clk.addWidget(self.date); clk.addWidget(self.ends)
        row1.addLayout(info, 1); row1.addWidget(self.live_badge, 0, Qt.AlignTop); row1.addLayout(clk)
        ol.addLayout(row1)
        # media controls and the timeline keep left-to-right order in both languages
        self.timeline = QWidget(); self.timeline.setLayoutDirection(Qt.LeftToRight); self.timeline.setObjectName("ctrlrow")
        row2 = QHBoxLayout(self.timeline); row2.setSpacing(14); row2.setContentsMargins(0, 0, 0, 0)
        self.t_pos = QLabel("00:00"); self.t_pos.setObjectName("time")
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0, 1000); self.slider.setFocusPolicy(Qt.NoFocus)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.slider.sliderReleased.connect(self._slider_seek)
        self.t_left = QLabel("-00:00"); self.t_left.setObjectName("time")
        row2.addWidget(self.t_pos); row2.addWidget(self.slider, 1); row2.addWidget(self.t_left)
        ol.addWidget(self.timeline)
        self.controls = QWidget(); self.controls.setLayoutDirection(Qt.LeftToRight); self.controls.setObjectName("ctrlrow")
        row3 = QHBoxLayout(self.controls); row3.setSpacing(12); row3.setContentsMargins(0, 0, 0, 0)
        self.btn_audio = self._btn("audio", "", lambda: self._control(self._cycle_audio))
        self.btn_subs = self._btn("subs", "", lambda: self._control(self._cycle_subs))
        self.btn_rew = self._btn("rew", "", lambda: self.seek(-10))
        self.btn_play = self._btn("pause", "", self.toggle_pause, 56); self.btn_play.setObjectName("main")
        self.btn_fwd = self._btn("fwd", "", lambda: self.seek(30))
        self.btn_next = self._btn("next", "", self._next)
        self.btn_vdown = self._btn("vol_down", "", lambda: self.change_volume(-10))
        self.vol_label = QLabel("100%"); self.vol_label.setObjectName("time")
        self.btn_vup = self._btn("vol_up", "", lambda: self.change_volume(10))
        self.btn_full = self._btn("full", "", self.toggle_fullscreen)
        row3.addWidget(self.btn_audio); row3.addWidget(self.btn_subs); row3.addStretch(1)
        for b in (self.btn_rew, self.btn_play, self.btn_fwd, self.btn_next):
            row3.addWidget(b)
        row3.addStretch(1)
        row3.addWidget(self.btn_vdown); row3.addWidget(self.vol_label); row3.addWidget(self.btn_vup); row3.addSpacing(8); row3.addWidget(self.btn_full)
        ol.addWidget(self.controls)
        self.set_language("ar")

        self.hide_timer = QTimer(self); self.hide_timer.setSingleShot(True); self.hide_timer.setInterval(3500)
        self.hide_timer.timeout.connect(self._auto_hide)
        self.cursor_timer = QTimer(self); self.cursor_timer.setInterval(200); self.cursor_timer.timeout.connect(self._watch_cursor)
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(1000); self.poll_timer.timeout.connect(self._poll)
        self.hide()

    # ------------------------------------------------------------------ layout
    def set_language(self, lang):
        self.lang = "en" if lang == "en" else "ar"
        L = STRINGS[self.lang]
        for b, k in ((self.btn_back, "back"), (self.btn_audio, "audio"), (self.btn_subs, "subs"), (self.btn_rew, "rew"),
                     (self.btn_play, "play"), (self.btn_fwd, "fwd"), (self.btn_next, "next"), (self.btn_vdown, "vdown"),
                     (self.btn_vup, "vup"), (self.btn_full, "full")):
            b.setToolTip(L[k])
        self.live_badge.setText(L["live"])
        rtl = self.lang == "ar"
        self.osd.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        self.top.setLayoutDirection(Qt.RightToLeft if rtl else Qt.LeftToRight)
        align = (Qt.AlignLeft if rtl else Qt.AlignRight) | Qt.AlignAbsolute | Qt.AlignVCenter
        for lab in (self.clock, self.date, self.ends):
            lab.setAlignment(align)
        self.timeline.setLayoutDirection(Qt.LeftToRight)
        self.controls.setLayoutDirection(Qt.LeftToRight)
        side = (Qt.AlignRight if rtl else Qt.AlignLeft) | Qt.AlignAbsolute | Qt.AlignVCenter
        for lab in (self.title, self.meta, self.top_title):
            lab.setAlignment(side)

    def _set_poster(self, data: bytes | None):
        from PySide6.QtGui import QImage, QPainterPath
        img = QImage()
        if not data or not img.loadFromData(data):
            self.poster.setPixmap(QPixmap()); self.poster.setText("▶"); return
        dpr = self.devicePixelRatioF() or 1.0
        w, h = int(self.poster.width() * dpr), int(self.poster.height() * dpr)
        scaled = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        pm = QPixmap(w, h); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(0, 0, w, h, 10 * dpr, 10 * dpr)
        p.setClipPath(path); p.drawImage((w - scaled.width()) // 2, (h - scaled.height()) // 2, scaled); p.end()
        pm.setDevicePixelRatio(dpr)
        self.poster.setText(""); self.poster.setPixmap(pm)

    def _load_poster(self, url, gen):
        def task():
            try:
                import requests
                r = requests.get(url, timeout=6)
                if r.ok and len(r.content) < 6_000_000:
                    return r.content
            except Exception:
                return None
            return None
        def done(fut):
            try:
                data = fut.result()
            except Exception:
                data = None
            self._ui.emit(lambda: gen == self.generation and self._set_poster(data))
        self.pool.submit(task).add_done_callback(done)

    def _stream_info(self, b, gen):
        """Resolution / codecs shown as small chips, like the receiver's info bar (mpv only)."""
        if not hasattr(b, "command"):
            return
        def task():
            get = lambda name: b.command("get_property", name)
            w, h = get("width"), get("height")
            vc, ac, fps = get("video-format"), get("audio-codec-name"), get("container-fps")
            out = []
            if w and h:
                out.append(f"{int(w)}×{int(h)}")
            if vc:
                out.append(str(vc).upper()[:10])
            if ac:
                out.append(str(ac).upper()[:8])
            try:
                if fps and float(fps) > 1:
                    out.append(f"{round(float(fps))} FPS")
            except (TypeError, ValueError):
                pass
            return out
        def done(fut):
            try:
                chips = fut.result()
            except Exception:
                return
            self._ui.emit(lambda: gen == self.generation and self._set_chips(chips))
        self.pool.submit(task).add_done_callback(done)

    def _set_chips(self, chips):
        for i, c in enumerate(self.chip_labels):
            if i < len(chips):
                c.setText(chips[i]); c.show()
            else:
                c.hide()

    def _btn(self, icon, tip, fn, size=44):
        b = QToolButton(self); b.setIcon(svg_icon(icon)); b.setIconSize(QSize(int(size * 0.5), int(size * 0.5)))
        b.setFixedSize(size, size); b.setToolTip(tip); b.setFocusPolicy(Qt.NoFocus); b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h = self.width(), self.height()
        self.video.setGeometry(0, 0, w, h)
        self.top.setGeometry(0, 0, w, 64)
        osd_h = 196
        self.osd.setGeometry(0, h - osd_h, w, osd_h)

    def show_osd(self):
        self.top.show(); self.osd.show(); self.top.raise_(); self.osd.raise_()
        self.setCursor(Qt.ArrowCursor)
        self.hide_timer.start()

    def _auto_hide(self):
        if self.paused or self._seeking or not self.isVisible():
            self.hide_timer.start(); return
        if self.osd.geometry().contains(self.mapFromGlobal(QCursor.pos())):
            self.hide_timer.start(); return
        self.top.hide(); self.osd.hide(); self.setCursor(Qt.BlankCursor)

    def _watch_cursor(self):
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            if self.rect().contains(self.mapFromGlobal(pos)):
                self.show_osd()

    # ------------------------------------------------------------------ lifecycle
    def start(self, item, view, urls, start, source_key):
        self.stop_backend()
        self.generation += 1
        gen = self.generation
        self.item, self.view, self.source_key = item, dict(view or {}), source_key
        self.live = (item.kind or "") == "live"
        self.position, self.duration, self.paused = float(start or 0), 0.0, False
        self.playing = False
        self.title.setText(self.view.get("title") or item.title)
        bits = [x for x in (self.view.get("year"), ("★ " + self.view["rating"]) if self.view.get("rating") else "") if x]
        if item.season is not None and item.episode is not None:
            bits.insert(0, f"S{int(item.season):02d} · E{int(item.episode):02d}")
        self.meta.setText("   ".join(bits))
        for w in (self.timeline, self.btn_rew, self.btn_fwd):
            w.setVisible(not self.live)
        self.live_badge.setVisible(self.live)
        self.btn_next.setVisible(item.kind == "episode")
        self.btn_play.setIcon(svg_icon("pause"))
        self.status.setText(STRINGS[self.lang]["opening"])
        self.top_title.setText(self.view.get("title") or item.title)
        self.ends.setText("")
        self._set_chips([])
        self._set_poster(None)
        if str(self.view.get("poster") or "").startswith(("http://", "https://")):
            self._load_poster(self.view["poster"], gen)
        self._tick_clock()
        self.show(); self.raise_(); self.setFocus(); self.show_osd()
        self.cursor_timer.start(); self.poll_timer.start()
        backend = self.backend_factory()
        backend.embed_wid = self._video_wid
        self.top.raise_(); self.osd.raise_()
        try:
            backend.set_volume  # mpv keeps the last volume for the next launch
            if hasattr(backend, "volume"):
                backend.volume = self.volume
        except Exception:
            pass
        self.backend = backend

        def task():
            try:
                backend.play_candidates(urls, start, should_cancel=lambda: gen != self.generation)
            except Exception as exc:
                if gen == self.generation:
                    msg = str(exc) if "not found" in str(exc).lower() else STRINGS[self.lang]["failed"]
                    self._ui.emit(lambda: self._failed(gen, msg))
                return
            self._ui.emit(lambda: self._started(gen))

        self.pool.submit(task)

    def _started(self, gen):
        if gen != self.generation:
            return
        self.playing = True
        self.status.setText("")
        if self.backend is not None:
            QTimer.singleShot(1500, lambda: gen == self.generation and self.backend is not None and self._stream_info(self.backend, gen))

    def _failed(self, gen, msg):
        if gen != self.generation:
            return
        self.close_player(silent=True)
        self.failed.emit(msg)

    def stop_backend(self):
        self.generation += 1
        b, self.backend = self.backend, None
        if b is not None:
            self.pool.submit(b.stop)

    def close_player(self, silent=False):
        if not self.isVisible() and self.backend is None:
            return
        self._save_progress(force=True)
        self.cursor_timer.stop(); self.poll_timer.stop(); self.hide_timer.stop()
        self.stop_backend()
        win = self.window()
        if win.isFullScreen() and getattr(win, "_was_maximized", None) is not None:
            win.showMaximized() if win._was_maximized else win.showNormal()
        self.hide()
        self.closed.emit()

    def shutdown(self):
        self.close_player(silent=True)
        self.pool.shutdown(wait=False, cancel_futures=False)

    # ------------------------------------------------------------------ polling
    def _tick_clock(self):
        now = time.localtime()
        self.clock.setText(time.strftime("%H:%M", now))
        self.date.setText(f"{STRINGS[self.lang]['days'][now.tm_wday]} {now.tm_mday}/{now.tm_mon}")

    def _poll(self):
        self._tick_clock()
        b = self.backend
        if self._polling or b is None:
            return
        self._polling = True
        gen = self.generation

        def task():
            try:
                alive = b.process is not None and b.process.poll() is None
                pos, dur = b.progress() if alive else (0.0, 0.0)
                return alive, pos, dur
            except Exception:
                return True, None, None

        def done(fut):
            self._polling = False
            try:
                alive, pos, dur = fut.result()
            except Exception:
                return
            self._ui.emit(lambda: self._progress(gen, alive, pos, dur))

        self.pool.submit(task).add_done_callback(done)

    def _progress(self, gen, alive, pos, dur):
        if gen != self.generation or not self.isVisible():
            return
        if not alive:
            if not self.playing:
                return  # still starting: the process is not up yet
            finished = self.item
            near_end = self.duration and self.position > self.duration - 90
            self.close_player(silent=True)
            if near_end and finished is not None and self.on_finished:
                self.on_finished(finished)
            return
        if pos is None or (not dur and self.duration > 0 and not self.live):
            return  # a slow IPC answer; keep the last known position
        self.position, self.duration = float(pos or 0), float(dur or 0)
        if not self.live and self.duration > 0:
            if not self._seeking:
                self.slider.setValue(int(1000 * self.position / self.duration))
            self.t_pos.setText(clock(self.position))
            self.t_left.setText("-" + clock(self.duration - self.position))
            self.ends.setText(STRINGS[self.lang]["ends"] + " " + time.strftime("%H:%M", time.localtime(time.time() + self.duration - self.position)))
        self._save_progress()

    def _save_progress(self, force=False):
        if self.live or self.item is None or not self.on_progress_save or self.position <= 0:
            return
        now = time.monotonic()
        if not force and now - self._last_save < 5:
            return
        self._last_save = now
        item, pos, dur = self.item, self.position, self.duration
        self.pool.submit(lambda: self.on_progress_save(item, pos, dur))

    # ------------------------------------------------------------------ controls
    def _control(self, fn, done=None):
        b, gen = self.backend, self.generation
        if b is None:
            return

        def task():
            if gen != self.generation:
                return None
            return fn(b)

        def finished(fut):
            try:
                value = fut.result()
            except Exception as exc:
                log.debug("Player control failed: %s", type(exc).__name__)
                return
            if done is not None:
                self._ui.emit(lambda: gen == self.generation and done(value))

        self.pool.submit(task).add_done_callback(finished)
        self.show_osd()

    def toggle_pause(self):
        def done(paused):
            self.paused = bool(paused)
            self.btn_play.setIcon(svg_icon("play" if self.paused else "pause"))
        self._control(lambda b: b.toggle_pause(), done)

    def seek(self, seconds):
        if self.live:
            return
        self.position = max(0.0, self.position + seconds)
        self._control(lambda b: b.seek(seconds))

    def _slider_seek(self):
        self._seeking = False
        if self.duration > 0:
            target = self.duration * self.slider.value() / 1000.0
            delta = target - self.position
            self.position = target
            self._control(lambda b: b.seek(delta))

    def change_volume(self, delta):
        self.volume = max(0, min(100, self.volume + delta))
        self.vol_label.setText(f"{self.volume}%")
        v = self.volume
        self._control(lambda b: b.set_volume(v))

    def _cycle_audio(self, b):
        return b.cycle_audio_track()

    def _cycle_subs(self, b):
        return b.cycle_subtitle_track()

    def _next(self):
        if self.item is not None and self.on_finished:
            item = self.item
            self.close_player(silent=True)
            self.on_finished(item)

    def toggle_fullscreen(self):
        win = self.window()
        if win.isFullScreen():
            win.showMaximized() if getattr(win, "_was_maximized", False) else win.showNormal()
        else:
            win._was_maximized = win.isMaximized()
            win.showFullScreen()
        self.show_osd()

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            if self.window().isFullScreen():
                self.toggle_fullscreen()
            else:
                self.close_player()
        elif k in (Qt.Key_Space, Qt.Key_P, Qt.Key_MediaPlay, Qt.Key_MediaPause, Qt.Key_MediaTogglePlayPause):
            self.toggle_pause()
        elif k == Qt.Key_Left:
            self.seek(-10)
        elif k == Qt.Key_Right:
            self.seek(30)
        elif k == Qt.Key_Up:
            self.change_volume(5)
        elif k == Qt.Key_Down:
            self.change_volume(-5)
        elif k in (Qt.Key_F, Qt.Key_F11):
            self.toggle_fullscreen()
        elif k == Qt.Key_A:
            self._control(self._cycle_audio)
        elif k == Qt.Key_S:
            self._control(self._cycle_subs)
        elif k == Qt.Key_N:
            self._next()
        elif k in (Qt.Key_Backspace, Qt.Key_MediaStop):
            self.close_player()
        else:
            super().keyPressEvent(e)
            return
        self.show_osd()

    def mouseDoubleClickEvent(self, e):
        self.toggle_fullscreen()

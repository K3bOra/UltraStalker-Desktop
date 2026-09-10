from __future__ import annotations
import logging
from PySide6.QtCore import Qt,QThread,Signal,QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import *
from ultrastalker_desktop import __version__,AUTHOR
from ultrastalker_desktop.core.models import Profile,profile_identity
from ultrastalker_desktop.core.adapters import make_adapter
from ultrastalker_desktop.storage.profiles import save_profile,load_profiles,delete_profile
from ultrastalker_desktop.storage.database import toggle_favorite,favorites,add_history,update_progress,history,resume_point,next_episode,episode_tracking_key,history_progress_label
from ultrastalker_desktop.storage.settings import load_settings,save_settings
from ultrastalker_desktop.player.mpv_backend import MPVBackend
from ultrastalker_desktop.support_bundle import create_support_bundle,sanitize_text
from ultrastalker_desktop.core.tmdb import TMDbClient
from ultrastalker_desktop.core.artwork import ArtworkCache
from ultrastalker_desktop.runtime import release_info

ULTRASTALKER_QSS = r"""
QMainWindow, QWidget#appPage { background: #070c14; color: #f6f8fb; }
QWidget { color: #f6f8fb; font-family: "Segoe UI"; font-size: 14px; }
QFrame#topBar, QFrame#panel, QFrame#loginCard, QFrame#heroPanel, QFrame#playerBar {
    background: #0d1522; border: 1px solid #1d2a3b; border-radius: 14px;
}
QFrame#heroPanel {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #111d31, stop:0.52 #0d2740, stop:1 #07101c);
    border: 1px solid #244a69;
}
QLabel#brand { color: #ffffff; font-size: 25px; font-weight: 800; letter-spacing: 1px; }
QLabel#heroBrand { color: #ffffff; font-size: 42px; font-weight: 900; letter-spacing: 2px; }
QLabel#heroSubtitle { color: #9db5ca; font-size: 16px; }
QLabel#eyebrow { color: #3cc7ff; font-size: 12px; font-weight: 800; letter-spacing: 2px; }
QLabel#screenTitle { color: #ffffff; font-size: 28px; font-weight: 800; }
QLabel#muted, QLabel#contextPill, QLabel#statusText { color: #91a2b5; }
QLabel#contextPill {
    background: #111f31; border: 1px solid #28415d; border-radius: 12px;
    padding: 7px 12px; font-size: 12px; font-weight: 700;
}
QLabel#countPill {
    color: #d6ecff; background: #10263a; border: 1px solid #1d5277;
    border-radius: 10px; padding: 5px 9px; font-size: 11px; font-weight: 800;
}
QLabel#sectionLabel { color: #8fa4b8; font-size: 12px; font-weight: 800; letter-spacing: 1px; }
QLabel#infoTitle { color: #ffffff; font-size: 18px; font-weight: 800; }
QLabel#artwork {
    background: #09111d; border: 1px solid #203149; border-radius: 12px;
}
QPushButton {
    background: #111b2a; color: #eaf2f8; border: 1px solid #26354a;
    border-radius: 10px; padding: 10px 15px; font-weight: 650;
}
QPushButton:hover { background: #17263a; border-color: #3d658d; }
QPushButton:pressed { background: #0d75ad; border-color: #56c9ff; }
QPushButton:focus { border: 2px solid #38bdf8; }
QPushButton:disabled { color: #556274; background: #0a111b; border-color: #17202d; }
QPushButton#primaryButton {
    background: #0788c8; border: 1px solid #29b6f6; color: white; font-weight: 800;
}
QPushButton#primaryButton:hover { background: #0a9fe7; }
QPushButton#dangerButton { background: #26151b; border-color: #5a2936; color: #ffb9c4; }
QPushButton#menuCard {
    text-align: center; padding: 16px 8px; font-size: 15px; font-weight: 800;
    min-height: 112px; background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #0b1726, stop:1 #07111d);
    border: 1px solid #2c8fc0; border-radius: 14px;
}
QPushButton#menuCard:hover, QPushButton#menuCard:focus {
    background: #102a42; border: 2px solid #39c4ff; color: #ffffff;
}
QPushButton#subCard {
    min-height: 58px; background: #0e1827; border: 1px solid #213149;
    font-weight: 750; text-align: left; padding-left: 18px;
}
QLineEdit, QComboBox {
    background: #09111d; color: #f4f7fb; border: 1px solid #263750;
    border-radius: 10px; padding: 9px 12px; min-height: 24px; selection-background-color: #168ccc;
}
QLineEdit:focus, QComboBox:focus { border: 2px solid #2fbdf4; }
QComboBox QAbstractItemView { background: #0c1522; border: 1px solid #2a3c55; selection-background-color: #116b9d; }
QListWidget {
    background: #09111d; border: 1px solid #1c2b3e; border-radius: 11px;
    padding: 6px; outline: 0;
}
QListWidget::item { min-height: 36px; padding: 7px 10px; margin: 2px; border-radius: 7px; color: #c8d5e1; }
QListWidget::item:hover { background: #101f31; color: #ffffff; }
QListWidget::item:selected { background: #087fba; color: white; font-weight: 800; }
QSplitter::handle { background: #070c14; width: 8px; }
QScrollBar:vertical { background: #09111d; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2a3d55; min-height: 32px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QStatusBar { background: #050911; color: #7f91a5; border-top: 1px solid #182435; }
QMessageBox, QInputDialog { background: #0d1522; }
"""

class Worker(QThread):
    done=Signal(object);failed=Signal(str)
    def __init__(self,fn):super().__init__();self.fn=fn
    def run(self):
        try:self.done.emit(self.fn())
        except Exception as e:
            logging.getLogger(__name__).warning('Worker task failed: %s', type(e).__name__)
            message=sanitize_text(str(e)).strip() or type(e).__name__
            self.failed.emit(message)

class UltraStalkerWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('Ultra Stalker Desktop '+__version__);self.resize(1440,860);self.setMinimumSize(1120,680);self.adapter=None;self.profile=None;self.source_key='';self.player=MPVBackend();self.current_kind='';self.current_items=[];self.current_playing=None;self.workers=[];self.browser_history=[];self.request_generation=0;self.play_request_generation=0;self.connection_generation=0;self.volume=100;self.volume_generation=0;self.closing=False;self.progress_poll_active=False;self.last_progress=(0.0,0.0)
        self.setStyleSheet(ULTRASTALKER_QSS)
        self.settings=load_settings();self.tmdb=TMDbClient(self.settings.get('tmdb_api_key',''));self.artwork=ArtworkCache();self.artwork_generation=0
        self.stack=QStackedWidget();self.setCentralWidget(self.stack);self.login=self._login();self.home=self._home();self.browser=self._browser();[self.stack.addWidget(x) for x in (self.login,self.home,self.browser)]
        self.poll=QTimer(self);self.poll.setInterval(5000);self.poll.timeout.connect(self.poll_progress);self.poll.start();self.statusBar().showMessage('Ultra Stalker Desktop '+__version__+' • '+AUTHOR);self._sync_context()

    def title(self,t):
        x=QLabel(t);x.setObjectName('screenTitle');x.setAlignment(Qt.AlignLeft|Qt.AlignVCenter);return x

    def _brand_block(self,subtitle='WINDOWS EDITION'):
        box=QWidget();layout=QVBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        eyebrow=QLabel(subtitle);eyebrow.setObjectName('eyebrow')
        brand=QLabel('ULTRA STALKER');brand.setObjectName('brand')
        layout.addWidget(eyebrow);layout.addWidget(brand);return box

    def _page(self):
        p=QWidget();p.setObjectName('appPage');return p

    def _login(self):
        p=self._page();outer=QVBoxLayout(p);outer.setContentsMargins(70,48,70,48);outer.setSpacing(24)
        top=QFrame();top.setObjectName('topBar');tl=QHBoxLayout(top);tl.setContentsMargins(24,15,24,15);tl.addWidget(self._brand_block('SECURE PROFILE CONNECTION'));tl.addStretch();ver=QLabel('v'+__version__);ver.setObjectName('contextPill');tl.addWidget(ver);outer.addWidget(top)
        outer.addStretch(1)
        card=QFrame();card.setObjectName('loginCard');card.setMaximumWidth(920);cl=QVBoxLayout(card);cl.setContentsMargins(34,30,34,30);cl.setSpacing(14)
        title=self.title('Connect to your source');cl.addWidget(title);sub=QLabel('Stalker / MAG, Xtream Codes or M3U');sub.setObjectName('muted');cl.addWidget(sub)
        top_fields=QHBoxLayout();self.saved=QComboBox();self.saved.addItem('Saved profiles…',None)
        for x in load_profiles():self.saved.addItem(x.name,x)
        self.saved.currentIndexChanged.connect(lambda _:self.fill_profile(self.saved.currentData()) if self.saved.currentData() else None);top_fields.addWidget(self.saved,2)
        self.type=QComboBox();self.type.addItems(['stalker','xtream','m3u']);top_fields.addWidget(self.type,1);cl.addLayout(top_fields)
        self.name=QLineEdit();self.name.setPlaceholderText('Profile name');self.url=QLineEdit();self.url.setPlaceholderText('Portal / Server / M3U URL');self.mac=QLineEdit();self.mac.setPlaceholderText('MAC for Stalker');self.user=QLineEdit();self.user.setPlaceholderText('Username for Xtream');self.password=QLineEdit();self.password.setPlaceholderText('Password for Xtream');self.password.setEchoMode(QLineEdit.Password)
        for x in [self.name,self.url,self.mac,self.user,self.password]:x.setMinimumHeight(42);cl.addWidget(x)
        row=QHBoxLayout();row.setSpacing(10);b=QPushButton('CONNECT');b.setObjectName('primaryButton');b.setMinimumHeight(46);b.clicked.connect(self.connect_profile);row.addWidget(b,2);d=QPushButton('DELETE SAVED PROFILE');d.setObjectName('dangerButton');d.setMinimumHeight(46);d.clicked.connect(self.delete_selected_profile);row.addWidget(d,1);self.back_home=QPushButton('BACK TO HOME');self.back_home.setMinimumHeight(46);self.back_home.setEnabled(False);self.back_home.clicked.connect(self.return_home);row.addWidget(self.back_home,1);cl.addLayout(row)
        center=QHBoxLayout();center.addStretch();center.addWidget(card,1);center.addStretch();outer.addLayout(center);outer.addStretch(2);return p

    def fill_profile(self,p):self.type.setCurrentText(p.source_type);self.name.setText(p.name);self.url.setText(p.m3u_url or p.portal_url);self.mac.setText(p.mac);self.user.setText(p.username);self.password.setText(p.password)
    def refresh_profiles(self):
        self.saved.blockSignals(True);self.saved.clear();self.saved.addItem('Saved profiles…',None)
        for x in load_profiles():self.saved.addItem(x.name,x)
        self.saved.blockSignals(False);self.saved.setCurrentIndex(0)
    def delete_selected_profile(self):
        p=self.saved.currentData()
        if not p:
            QMessageBox.information(self,'Profiles','Select a saved profile first.');return
        if QMessageBox.question(self,'Profiles',f'Delete saved profile \"{p.name}\"?')!=QMessageBox.Yes:return
        try:
            delete_profile(p.name);self.refresh_profiles();self.busy('Deleted saved profile • '+p.name)
        except Exception as e:
            QMessageBox.warning(self,'Profiles','Could not delete profile.\n\n'+(sanitize_text(str(e)).strip() or type(e).__name__))

    def _home(self):
        p=self._page();l=QVBoxLayout(p);l.setContentsMargins(40,28,40,26);l.setSpacing(12)
        top=QHBoxLayout();top.setContentsMargins(4,0,4,0);top.addWidget(self._brand_block());top.addStretch();self.home_profile=QLabel('NO ACTIVE PROFILE');self.home_profile.setObjectName('contextPill');top.addWidget(self.home_profile);l.addLayout(top)
        hero=QFrame();hero.setObjectName('heroPanel');hero.setMinimumHeight(250);hl=QHBoxLayout(hero);hl.setContentsMargins(30,28,30,28);copy=QVBoxLayout();ey=QLabel('ULTRA STALKER • WINDOWS');ey.setObjectName('eyebrow');copy.addWidget(ey);hb=QLabel('YOUR ENTERTAINMENT\nIN ONE PLACE');hb.setObjectName('heroBrand');copy.addWidget(hb);hs=QLabel('The Ultra Stalker experience, rebuilt for desktop with the same dark cinematic identity and more room to breathe.');hs.setObjectName('heroSubtitle');hs.setWordWrap(True);hs.setMaximumWidth(680);copy.addWidget(hs);copy.addStretch();hl.addLayout(copy,3);self.home_status=QLabel('READY');self.home_status.setObjectName('contextPill');self.home_status.setAlignment(Qt.AlignCenter);self.home_status.setMinimumWidth(150);hl.addWidget(self.home_status,0,Qt.AlignBottom);l.addWidget(hero)
        row=QHBoxLayout();row.setSpacing(10)
        cards=[('LIVE TV\nWatch live channels',self.open_kind,'live'),('MOVIES\nBrowse movie library',self.open_kind,'movies'),('SERIES\nExplore TV series',self.open_kind,'series'),('CONTINUE\nResume watching',self.open_history,None),('FAVORITES\nYour saved content',self.open_favorites,None),('SEARCH\nFind content quickly',self._focus_home_search,None),('SETTINGS\nPortal & player settings',self.open_settings,None)]
        for text,fn,arg in cards:
            b=QPushButton(text);b.setObjectName('menuCard');b.setMinimumWidth(105)
            if arg is None:b.clicked.connect(fn)
            else:b.clicked.connect(lambda _,kind=arg,callback=fn:callback(kind))
            row.addWidget(b,1)
        l.addLayout(row)
        section=QHBoxLayout();label=QLabel('CONTINUE WATCHING');label.setObjectName('eyebrow');section.addWidget(label);section.addStretch();hint=QLabel('Enter / double-click to open  •  Esc / Back to return');hint.setObjectName('muted');section.addWidget(hint);l.addLayout(section)
        lower=QFrame();lower.setObjectName('panel');ll=QHBoxLayout(lower);ll.setContentsMargins(16,14,16,14);self.search=QLineEdit();self.search.setPlaceholderText('Search Live, Movies and Series');self.search.setMinimumHeight(44);self.search.returnPressed.connect(self.global_search);ll.addWidget(self.search,1);history_btn=QPushButton('OPEN HISTORY');history_btn.clicked.connect(self.open_history);ll.addWidget(history_btn);profiles=QPushButton('PROFILES');profiles.clicked.connect(self.show_profiles);ll.addWidget(profiles);l.addWidget(lower);l.addStretch();return p

    def _focus_home_search(self):
        self.search.setFocus();self.search.selectAll();self.busy('Search ready')

    def _browser(self):
        p=self._page();v=QVBoxLayout(p);v.setContentsMargins(30,24,30,24);v.setSpacing(12)
        top=QFrame();top.setObjectName('topBar');th=QHBoxLayout(top);th.setContentsMargins(16,10,18,10);back=QPushButton('‹  BACK');back.setMinimumWidth(105);back.clicked.connect(self.browser_back);th.addWidget(back);self.btitle=self.title('Browser');th.addWidget(self.btitle,1);self.browser_context=QLabel('BROWSE');self.browser_context.setObjectName('contextPill');th.addWidget(self.browser_context);v.addWidget(top)
        split=QSplitter(Qt.Horizontal)
        cat_panel=QFrame();cat_panel.setObjectName('panel');cl=QVBoxLayout(cat_panel);cl.setContentsMargins(12,14,12,12);lab=QLabel('CATEGORIES');lab.setObjectName('sectionLabel');cl.addWidget(lab);self.categories=QListWidget();self.categories.setMinimumWidth(240);self.categories.setMaximumWidth(360);cl.addWidget(self.categories,1);split.addWidget(cat_panel)
        items_panel=QFrame();items_panel.setObjectName('panel');il=QVBoxLayout(items_panel);il.setContentsMargins(12,14,12,12);ih=QHBoxLayout();self.items_heading=QLabel('CONTENT');self.items_heading.setObjectName('sectionLabel');ih.addWidget(self.items_heading);ih.addStretch();self.browser_count=QLabel('0 ITEMS');self.browser_count.setObjectName('countPill');ih.addWidget(self.browser_count);il.addLayout(ih);self.items=QListWidget();self.items.setMinimumWidth(390);self.items.setUniformItemSizes(True);il.addWidget(self.items,1);split.addWidget(items_panel)
        detail_panel=QFrame();detail_panel.setObjectName('panel');dl=QVBoxLayout(detail_panel);dl.setContentsMargins(14,14,14,14);dl.setSpacing(12);lab=QLabel('NOW SELECTED');lab.setObjectName('sectionLabel');dl.addWidget(lab);self.backdrop_view=QLabel();self.backdrop_view.setObjectName('artwork');self.backdrop_view.setFixedHeight(230);self.backdrop_view.setMinimumWidth(410);self.backdrop_view.setAlignment(Qt.AlignCenter);self.backdrop_view.hide();dl.addWidget(self.backdrop_view);details=QHBoxLayout();self.poster_view=QLabel();self.poster_view.setObjectName('artwork');self.poster_view.setFixedSize(150,220);self.poster_view.setAlignment(Qt.AlignCenter);self.poster_view.hide();details.addWidget(self.poster_view);self.info=QLabel('Select an item to see details');self.info.setObjectName('muted');self.info.setWordWrap(True);self.info.setAlignment(Qt.AlignTop|Qt.AlignLeft);details.addWidget(self.info,1);dl.addLayout(details);dl.addStretch();split.addWidget(detail_panel)
        split.setStretchFactor(0,1);split.setStretchFactor(1,2);split.setStretchFactor(2,2);split.setSizes([260,520,560]);v.addWidget(split,1)
        self.categories.itemClicked.connect(self.load_category);self.categories.itemActivated.connect(self.load_category);self.items.itemDoubleClicked.connect(self.activate_item);self.items.itemSelectionChanged.connect(self.show_info)
        player=QFrame();player.setObjectName('playerBar');pv=QVBoxLayout(player);pv.setContentsMargins(12,10,12,10);pv.setSpacing(8);r=QHBoxLayout();r.setSpacing(8)
        for text,fn,name in [('FAVORITE',self.favorite,''),('PLAY / OPEN',self.play_selected,'primaryButton'),('PAUSE / RESUME',self.pause_resume,''),('STOP',self.stop_playback,''),('BACK',self.browser_back,'')]:
            b=QPushButton(text);b.setObjectName(name);b.clicked.connect(fn);r.addWidget(b,1)
        pv.addLayout(r);controls=QHBoxLayout();controls.setSpacing(8)
        for text,fn in [('SEEK -30s',lambda:self.seek_by(-30)),('SEEK +30s',lambda:self.seek_by(30)),('VOL -',lambda:self.adjust_volume(-10)),('VOL +',lambda:self.adjust_volume(10)),('AUDIO',self.cycle_audio),('SUBTITLES',self.cycle_subtitle),('FULLSCREEN',self.toggle_fullscreen)]:
            b=QPushButton(text);b.clicked.connect(fn);controls.addWidget(b,1)
        pv.addLayout(controls);v.addWidget(player);return p

    def _sync_context(self):
        profile_text=('CONNECTED  •  '+self.profile.name+'  •  '+self.profile.source_type.upper()) if self.profile else 'NO ACTIVE PROFILE'
        if hasattr(self,'home_profile'):self.home_profile.setText(profile_text)
        if hasattr(self,'home_status'):self.home_status.setText('ONLINE' if self.profile else 'READY')
        if hasattr(self,'browser_context'):self.browser_context.setText((self.current_kind or 'BROWSE').upper())

    def busy(self,t):
        self.statusBar().showMessage(t)
        if hasattr(self,'home_status') and self.stack.currentWidget() is self.home:self.home_status.setText(str(t).upper()[:38])
    def _worker_relevant(self,w):
        if self.closing:return False
        active=getattr(w,'active_callback',None)
        try:return True if active is None else bool(active())
        except Exception:return False
    def _invoke_worker_callback(self,w,name,*args):
        callback=getattr(w,name,None)
        if not callback:return True
        try:
            callback(*args);return True
        except Exception as exc:
            # A GUI callback is application code, not provider data. Keep the
            # exception text out of logs anyway because callbacks may touch
            # storage/network helpers whose messages can contain local paths.
            logging.getLogger(__name__).warning('Worker %s callback failed: %s',name,type(exc).__name__)
            try:self.busy('Background task callback failed')
            except Exception:pass
            return False
    def _worker_done(self,data):
        w=self.sender()
        if w in self.workers and self._worker_relevant(w):
            self._invoke_worker_callback(w,'ok_callback',data)
    def _worker_failed(self,message):
        w=self.sender()
        if w in self.workers and self._worker_relevant(w):
            self._invoke_worker_callback(w,'error_callback',message)
            QMessageBox.warning(self,'Ultra Stalker',message)
    def _worker_finished(self):
        w=self.sender()
        if w in self.workers:
            # Cleanup callbacks always run on the MainWindow thread, even when
            # the worker became stale and its result/error was intentionally
            # ignored. This prevents flags such as progress_poll_active from
            # being stranded forever after navigation or cancellation.
            self._invoke_worker_callback(w,'cleanup_callback')
            self.workers.remove(w)
        if w:w.deleteLater()
        if self.closing and not self.workers:QTimer.singleShot(0,self.close)
    def work(self,fn,ok,active=None,error=None,cleanup=None):
        if self.closing:return None
        w=Worker(fn);w.ok_callback=ok;w.active_callback=active;w.error_callback=error;w.cleanup_callback=cleanup;self.workers.append(w)
        # Connect worker signals to QObject-bound MainWindow methods. Qt can then
        # queue delivery to the GUI thread instead of relying on the ambiguous
        # affinity of plain Python lambdas invoked from QThread.run().
        w.done.connect(self._worker_done);w.failed.connect(self._worker_failed);w.finished.connect(self._worker_finished);w.start()
    def show_profiles(self):
        # Profile switching is a navigation boundary: preserve current progress,
        # cancel stale catalog/play callbacks, and stop playback before exposing
        # credentials for another source. The active profile itself remains in
        # memory so Back to Home can return without forcing a reconnect.
        self.request_generation+=1;self.play_request_generation+=1;self.save_progress();self.player.stop();self.current_playing=None;self.browser_history.clear();self.back_home.setEnabled(self.profile is not None);self.stack.setCurrentWidget(self.login);self.busy('Profiles')
    def return_home(self):
        if not self.profile:return
        # Leaving the profile screen is an explicit cancellation boundary for
        # any in-flight replacement login. A late successful connection must
        # never switch profiles after the user has returned Home.
        self.connection_generation+=1
        self.stack.setCurrentWidget(self.home);self._sync_context();self.busy('Connected • '+self.profile.name)

    def connect_profile(self):
        import re
        t=self.type.currentText();name=self.name.text().strip() or 'Default';url=self.url.text().strip();mac=self.mac.text().strip();user=self.user.text().strip();password=self.password.text()
        if not url:
            QMessageBox.warning(self,'Profile','Portal / server URL is required.');return
        if t=='stalker' and not re.fullmatch(r'[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}',mac):
            QMessageBox.warning(self,'Profile','Enter a valid Stalker MAC address, for example 00:1A:79:XX:XX:XX.');return
        if t=='xtream' and (not user or not password):
            QMessageBox.warning(self,'Profile','Xtream username and password are required.');return
        p=Profile(name,t,url,mac,user,password,url if t=='m3u' else '')
        adapter=make_adapter(p);self.connection_generation+=1;generation=self.connection_generation;self.busy('Connecting…')
        def task():
            try:
                adapter.connect()
            except Exception:
                if generation!=self.connection_generation:return False
                raise
            return generation==self.connection_generation
        def connected(ok):
            if not ok or generation!=self.connection_generation:return
            # Persist only after this attempt has won the UI generation race.
            # A stale connection worker must never overwrite a newer profile.
            persisted=True
            try:
                save_profile(p)
            except Exception as e:
                persisted=False
                QMessageBox.warning(
                    self,'Profile',
                    'Connected, but the profile could not be saved securely.\n\n'
                    'You can use it for this session only. Nothing was saved in plaintext.\n\n'+
                    (sanitize_text(str(e)).strip() or type(e).__name__)
                )
            if generation!=self.connection_generation:return
            self.request_generation+=1;self.play_request_generation+=1;self.save_progress();self.player.stop();self.current_playing=None
            self.profile=p;self.source_key=profile_identity(p);self.adapter=adapter
            if persisted:self.refresh_profiles()
            self.back_home.setEnabled(True);self.stack.setCurrentWidget(self.home);self._sync_context()
            self.busy('Connected • '+p.name+(' • session only' if not persisted else ''))
        self.work(task,connected,active=lambda:generation==self.connection_generation,error=lambda _message:self.busy('Connection failed'))
    def open_kind(self,k):
        if not self.adapter:return
        self.request_generation+=1;generation=self.request_generation
        self.browser_history.clear();self.current_kind=k;self.btitle.setText(k.title());self.items_heading.setText(k.upper());self.browser_context.setText(k.upper());self.categories.clear();self.items.clear();self.browser_count.setText('0 ITEMS');self.stack.setCurrentWidget(self.browser)
        adapter=self.adapter;cancelled=lambda:generation!=self.request_generation or self.closing or adapter is not self.adapter;self.work(lambda:adapter.categories(k,cancelled=cancelled),lambda rows:self.set_categories(rows) if not cancelled() else None,active=lambda:not cancelled(),error=lambda _message:self.busy('Could not load categories'))
    def set_categories(self,rows):
        self.categories.clear();a=QListWidgetItem('All');a.setData(Qt.UserRole,'');self.categories.addItem(a)
        for c in rows:x=QListWidgetItem(c.title);x.setData(Qt.UserRole,c.id);self.categories.addItem(x)
        self.categories.setCurrentRow(0);self.load_category(a)
    def load_category(self,row):
        cid=row.data(Qt.UserRole) or '';kind=self.current_kind;adapter=self.adapter;self.request_generation+=1;generation=self.request_generation;self.busy('Loading…')
        cancelled=lambda:generation!=self.request_generation or self.closing or kind!=self.current_kind or adapter is not self.adapter;self.work(lambda:adapter.items(kind,cid,cancelled=cancelled),lambda rows:self.set_items(rows) if not cancelled() else None,active=lambda:not cancelled(),error=lambda _message:self.busy('Could not load items'))
    def set_items(self,rows):self.current_items=rows;self.render(rows);self.busy(str(len(rows))+' items')
    def render(self,rows):
        self.items.clear()
        for m in rows:
            suffix=(f'  ({m.year})' if m.year else '')
            if m.kind=='episode' and m.season is not None:suffix=f'  S{m.season:02d}E{(m.episode or 0):02d}'
            x=QListWidgetItem(m.title+suffix);x.setData(Qt.UserRole,m);self.items.addItem(x)
        if hasattr(self,'browser_count'):self.browser_count.setText(str(len(rows))+' ITEMS')
    def filter_items(self,q):
        q=q.strip().lower();self.render([x for x in self.current_items if q in x.title.lower()] if q else self.current_items);self.stack.setCurrentWidget(self.browser)
    def global_search(self):
        q=self.search.text().strip().lower()
        if not q or not self.adapter:return
        self.request_generation+=1;generation=self.request_generation;adapter=self.adapter;query_text=self.search.text().strip();self.busy('Searching Live, Movies and Series…')
        cancelled=lambda:generation!=self.request_generation or self.closing or adapter is not self.adapter
        def task():
            out=[]
            for k in ('live','movies','series'):
                if cancelled():break
                try:
                    out.extend([x for x in adapter.items(k,'',cancelled=cancelled) if q in x.title.lower()])
                except Exception as exc:
                    # Search is best-effort across independent catalogs. Record only
                    # the exception class so provider URLs/credentials never enter logs.
                    logging.getLogger(__name__).warning('Search section %s failed: %s', k, type(exc).__name__)
            return out
        def done(rows):
            if generation!=self.request_generation or adapter is not self.adapter:return
            self.browser_history.clear();self.current_items=rows;self.categories.clear();self.btitle.setText('Search • '+query_text);self.items_heading.setText('SEARCH RESULTS');self.browser_context.setText('SEARCH');self.render(rows);self.stack.setCurrentWidget(self.browser);self.busy(str(len(rows))+' results')
        self.work(task,done,active=lambda:generation==self.request_generation and adapter is self.adapter)
    def selected(self):x=self.items.currentItem();return x.data(Qt.UserRole) if x else None
    def _selection_marker(self,m=None):
        m=m or self.selected()
        return (self.source_key,m.kind,str(m.id),str(m.series_id or ''),m.title) if m else None
    def _clear_artwork(self):
        self.poster_view.clear();self.poster_view.hide();self.backdrop_view.clear();self.backdrop_view.hide()
    def _set_artwork(self,label,data,backdrop=False):
        if not data:return
        pix=QPixmap()
        if not pix.loadFromData(data):return
        mode=Qt.KeepAspectRatio if not backdrop else Qt.KeepAspectRatioByExpanding
        pix=pix.scaled(label.size(),mode,Qt.SmoothTransformation);label.setPixmap(pix);label.show()
    def _load_selected_artwork(self,marker,generation):
        if self.closing or generation!=self.artwork_generation or self._selection_marker()!=marker:return
        m=self.selected()
        if not m:return
        urls={'poster':m.poster,'backdrop':m.backdrop}
        urls={k:v for k,v in urls.items() if v}
        if not urls:return
        def active():return generation==self.artwork_generation and self._selection_marker()==marker
        def task():return {k:self.artwork.fetch(v) for k,v in urls.items()}
        def done(rows):
            if not active():return
            self._set_artwork(self.poster_view,rows.get('poster'),False);self._set_artwork(self.backdrop_view,rows.get('backdrop'),True)
        self.work(task,done,active=active)
    def show_info(self):
        if self.closing:return
        m=self.selected();self.artwork_generation+=1;generation=self.artwork_generation;self._clear_artwork()
        if not m:self.info.setText('');return
        marker=self._selection_marker(m)
        meta=[]
        if m.year:meta.append(str(m.year))
        if m.rating:meta.append('Rating '+str(m.rating))
        heading=m.title+('  •  '+'  •  '.join(meta) if meta else '')
        self.info.setText(heading+'\n\n'+(m.description or 'No description available.'))
        # Delay artwork work slightly so fast keyboard/list navigation does not
        # spawn downloads for every item merely passed over.
        QTimer.singleShot(120,lambda:self._load_selected_artwork(marker,generation))
        if m.kind in ('movies','series') and self.tmdb.key and (not m.description or not m.rating or not m.poster or not m.backdrop or not m.year):
            def is_current():return generation==self.artwork_generation and self._selection_marker()==marker
            def done(meta):
                cur=self.selected()
                if not meta or not is_current():return
                if not cur.description:cur.description=str(meta.get('description') or '')
                if not cur.rating and meta.get('rating') is not None:cur.rating=str(round(float(meta['rating']),1))
                if not cur.year:cur.year=str(meta.get('year') or '')
                if not cur.poster:cur.poster=str(meta.get('poster') or '')
                if not cur.backdrop:cur.backdrop=str(meta.get('backdrop') or '')
                meta=[]
                if cur.year:meta.append(str(cur.year))
                if cur.rating:meta.append('Rating '+str(cur.rating))
                heading=cur.title+('  •  '+'  •  '.join(meta) if meta else '')
                self.info.setText(heading+'\n\n'+(cur.description or 'No description available.'))
                self._load_selected_artwork(marker,generation)
            self.work(lambda:self.tmdb.search(m.title,m.kind,m.year),done,active=is_current)
    def activate_item(self,_):
        m=self.selected()
        if m and m.kind=='series':
            snapshot=(self.btitle.text(),self.current_kind,list(self.current_items),self.categories.currentRow());adapter=self.adapter;self.request_generation+=1;generation=self.request_generation
            def done(rows):
                if generation!=self.request_generation or adapter is not self.adapter:return
                if rows:self.browser_history.append(snapshot)
                self.set_episodes(m,rows)
            cancelled=lambda:generation!=self.request_generation or self.closing or adapter is not self.adapter
            self.work(lambda:adapter.series_episodes(m,cancelled=cancelled),done,active=lambda:not cancelled(),error=lambda _message:self.busy('Could not load episodes'))
        else:self.play_selected()
    def set_episodes(self,series,rows):
        if not rows:QMessageBox.information(self,'Series','No episodes returned by source.');return
        try:watched=next_episode(self.source_key,series.id)
        except Exception as exc:
            logging.getLogger(__name__).warning('Episode tracking unavailable: %s',type(exc).__name__);watched=set()
        rows.sort(key=lambda x:((x.season or 0),(x.episode or 0),x.title.casefold()));self.current_items=rows;self.btitle.setText(series.title+' • Episodes');self.render(rows)
        for i,x in enumerate(rows):
            if episode_tracking_key(x) in watched:
                item=self.items.item(i);item.setText('✓ '+item.text())
        next_idx=next((i for i,x in enumerate(rows) if episode_tracking_key(x) not in watched),0);self.items.setCurrentRow(next_idx);self.busy('Next episode selected')
    def browser_back(self):
        # Cancel catalog/episode/artwork callbacks targeting the screen being
        # left before restoring the previous browser state or Home.
        self.request_generation+=1;self.artwork_generation+=1
        if self.browser_history:
            title,kind,rows,category_row=self.browser_history.pop()
            self.current_kind=kind;self.current_items=rows;self.btitle.setText(title);self.render(rows)
            if 0 <= category_row < self.categories.count():self.categories.setCurrentRow(category_row)
            self.busy(str(len(rows))+' items');return
        self.stack.setCurrentWidget(self.home);self._sync_context()
    def play_selected(self):
        m=self.selected()
        if not m:return
        if m.kind=='series':self.activate_item(None);return
        self.save_progress();self.current_playing=None;self.last_progress=(0.0,0.0);self.play_request_generation+=1;generation=self.play_request_generation;adapter=self.adapter;source_key=self.source_key;self.busy('Preparing stream…')
        def task():
            cancelled=lambda:generation!=self.play_request_generation or self.closing or adapter is not self.adapter
            try:pos,dur=resume_point(source_key,m)
            except Exception as exc:
                logging.getLogger(__name__).warning('Resume state unavailable: %s',type(exc).__name__);pos,dur=0.0,0.0
            start=pos if dur and pos>30 and pos<dur-60 else 0
            urls=adapter.stream_candidates(m,cancelled=cancelled)
            if not urls:raise RuntimeError('Source returned no playable URL')
            chosen=self.player.play_candidates(urls,start,should_cancel=lambda:generation!=self.play_request_generation)
            try:add_history(source_key,m,start,dur)
            except Exception as exc:logging.getLogger(__name__).warning('Playback history unavailable: %s',type(exc).__name__)
            return chosen,start,dur
        def started(result):
            if generation!=self.play_request_generation:return
            if adapter is not self.adapter:return
            _chosen,start,dur=result
            self.current_playing=m;self.last_progress=(float(start or 0),float(dur or 0));self.busy('Playing • '+m.title);self._apply_volume_async()
        self.work(task,started,active=lambda:generation==self.play_request_generation and adapter is self.adapter,error=lambda _message:self.busy('Playback failed'))
    def _playback_active(self):
        return bool(self.current_playing and self.player.process and self.player.process.poll() is None)
    def _player_control(self,fn,done=None,error_status='Player control failed'):
        if not self._playback_active():return
        generation=self.play_request_generation;process=self.player.process;item=self.current_playing
        def active():
            return (not self.closing and generation==self.play_request_generation and
                    process is self.player.process and item is self.current_playing and
                    process is not None and process.poll() is None)
        def task():
            if not active():return None
            return fn()
        self.work(task,done or (lambda _value:None),active=active,error=lambda _message:self.busy(error_status))
    def _apply_volume_async(self):
        if not self._playback_active():return
        self.volume_generation+=1;volume_generation=self.volume_generation;value=self.volume
        generation=self.play_request_generation;process=self.player.process;item=self.current_playing
        def active():
            return (not self.closing and volume_generation==self.volume_generation and
                    generation==self.play_request_generation and process is self.player.process and
                    item is self.current_playing and process is not None and process.poll() is None)
        def task():
            if not active():return None
            return self.player.set_volume(value)
        self.work(task,lambda _value:None,active=active,error=lambda _message:self.busy('Volume control failed'))
    def pause_resume(self):
        self._player_control(self.player.toggle_pause,lambda paused:self.busy('Paused' if paused else 'Playing'))
    def seek_by(self,seconds):
        status=('Forward ' if seconds>0 else 'Back ')+str(abs(int(seconds)))+'s'
        self._player_control(lambda:self.player.seek(seconds),lambda _value:self.busy(status))
    def adjust_volume(self,delta):
        self.volume=max(0,min(100,self.volume+int(delta)));self.busy('Volume • '+str(self.volume)+'%')
        self._apply_volume_async()
    def toggle_fullscreen(self):
        self._player_control(self.player.toggle_fullscreen,lambda state:self.busy('Fullscreen • '+('On' if state else 'Off')))
    def cycle_audio(self):
        self._player_control(self.player.cycle_audio_track,lambda track:self.busy('Audio track • '+str(track if track is not None else 'unchanged')))
    def cycle_subtitle(self):
        self._player_control(self.player.cycle_subtitle_track,lambda track:self.busy('Subtitle track • '+str(track if track is not None else 'unchanged')))
    def stop_playback(self):
        self.play_request_generation+=1;self.save_progress();self.player.stop();self.current_playing=None;self.last_progress=(0.0,0.0);self.busy('Playback stopped')
    def poll_progress(self):
        # Timer-driven IPC belongs off the UI thread. A stalled mpv pipe should
        # never freeze navigation every five seconds. Only one poll may be in
        # flight and stale playback generations are discarded on completion.
        if self.progress_poll_active or not self._playback_active() or not self.profile:return
        self.progress_poll_active=True;generation=self.play_request_generation;item=self.current_playing;source_key=self.source_key
        def task():
            try:return self.player.progress()
            except Exception as exc:
                logging.getLogger(__name__).warning('Progress poll failed: %s', type(exc).__name__);return None
        def done(value):
            if not value or generation!=self.play_request_generation or self.current_playing is not item:return
            try:
                p,d=value
                self.last_progress=(float(p or 0),float(d or 0))
                if p>0:update_progress(source_key,item,p,d)
            except Exception as exc:
                logging.getLogger(__name__).warning('Progress poll save failed: %s', type(exc).__name__)
        def cleanup():self.progress_poll_active=False
        self.work(task,done,cleanup=cleanup)
    def save_progress(self):
        if not self.current_playing or not self.profile:return
        try:
            # Never perform mpv IPC synchronously from the GUI thread. The
            # background poll refreshes this snapshot every five seconds; using
            # it here keeps Stop/Profile/Close responsive even if mpv's pipe is
            # stalled. At worst resume trails playback by one poll interval.
            p,d=self.last_progress
            if p>0:update_progress(self.source_key,self.current_playing,p,d)
        except Exception as exc:
            # Persistence failure must not block navigation. Do not log exception
            # text because a third-party backend could include a sensitive URL.
            logging.getLogger(__name__).warning('Progress save failed: %s', type(exc).__name__)
    def favorite(self):
        m=self.selected()
        if not m:return
        try:self.busy(('Added to' if toggle_favorite(self.source_key,m) else 'Removed from')+' favorites')
        except Exception as exc:
            logging.getLogger(__name__).warning('Favorite update unavailable: %s',type(exc).__name__);self.busy('Favorites unavailable')
    def open_favorites(self):
        if not self.profile:return
        try:rows=favorites(self.source_key)
        except Exception as exc:
            logging.getLogger(__name__).warning('Favorites unavailable: %s',type(exc).__name__);self.busy('Favorites unavailable');return
        self.browser_history.clear();self.categories.clear();self.btitle.setText('Favorites');self.items_heading.setText('FAVORITES');self.browser_context.setText('FAVORITES');self.current_items=rows;self.render(self.current_items);self.stack.setCurrentWidget(self.browser)
    def open_history(self):
        if not self.profile:return
        try:rows=history(self.source_key)
        except Exception as exc:
            logging.getLogger(__name__).warning('History unavailable: %s',type(exc).__name__);self.busy('History unavailable');return
        self.browser_history.clear();self.categories.clear();self.btitle.setText('History / Continue Watching');self.items_heading.setText('CONTINUE WATCHING');self.browser_context.setText('HISTORY');self.current_items=[x[0] for x in rows];self.render(self.current_items)
        for i,(media,position,duration) in enumerate(rows):
            row=self.items.item(i)
            if not row:continue
            status='Recently played' if media.kind=='live' else history_progress_label(position,duration)
            row.setText(row.text()+'  •  '+status)
        self.stack.setCurrentWidget(self.browser)
    def show_about(self):
        info=release_info();build=str(info.get('build_id') or 'development');reference=str(info.get('reference') or 'Ultra Stalker 8.4.1')
        QMessageBox.information(self,'About Ultra Stalker Desktop','Ultra Stalker Desktop '+__version__+'\nDeveloper: '+AUTHOR+'\nBuild ID: '+build+'\nReference: '+reference)
    def export_diagnostics(self):
        try:
            path=create_support_bundle()
            QMessageBox.information(self,'Diagnostics','Support bundle created.\n\n'+str(path)+'\n\nProfiles and credentials are not included.')
            self.busy('Diagnostics bundle created')
        except Exception as e:
            QMessageBox.warning(self,'Diagnostics','Could not create diagnostics bundle.\n\n'+(sanitize_text(str(e)).strip() or type(e).__name__))
    def open_settings(self):
        key,ok=QInputDialog.getText(self,'Settings','TMDb API key (optional):',QLineEdit.Password,self.settings.get('tmdb_api_key',''))
        if not ok:return
        updated=dict(self.settings);updated['tmdb_api_key']=key.strip()
        try:
            save_settings(updated)
        except Exception as e:
            QMessageBox.warning(self,'Settings','Could not save settings securely.\n\n'+(sanitize_text(str(e)).strip() or type(e).__name__));return
        self.settings=updated;self.tmdb=TMDbClient(key.strip());self.busy('Settings saved')
    def closeEvent(self,e):
        first_close=not self.closing;self.closing=True
        if first_close:
            # Shutdown invalidates every pending UI/network generation, not just
            # playback. Delayed artwork timers and stale catalog/login callbacks
            # must never start or commit work after close has begun.
            self.poll.stop();self.connection_generation+=1;self.request_generation+=1;self.artwork_generation+=1;self.play_request_generation+=1
            self.save_progress();self.player.stop();self.current_playing=None
        if self.workers:
            for w in list(self.workers):w.requestInterruption()
            self.hide();e.ignore();return
        super().closeEvent(e)

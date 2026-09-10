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
        super().__init__();self.setWindowTitle('Ultra Stalker Desktop '+__version__);self.resize(1280,760);self.adapter=None;self.profile=None;self.source_key='';self.player=MPVBackend();self.current_kind='';self.current_items=[];self.current_playing=None;self.workers=[];self.browser_history=[];self.request_generation=0;self.play_request_generation=0;self.connection_generation=0;self.volume=100;self.volume_generation=0;self.closing=False;self.progress_poll_active=False;self.last_progress=(0.0,0.0)
        self.settings=load_settings();self.tmdb=TMDbClient(self.settings.get('tmdb_api_key',''));self.artwork=ArtworkCache();self.artwork_generation=0
        self.stack=QStackedWidget();self.setCentralWidget(self.stack);self.login=self._login();self.home=self._home();self.browser=self._browser();[self.stack.addWidget(x) for x in (self.login,self.home,self.browser)]
        self.poll=QTimer(self);self.poll.setInterval(5000);self.poll.timeout.connect(self.poll_progress);self.poll.start();self.statusBar().showMessage('Ultra Stalker Desktop '+__version__+' • '+AUTHOR)
    def title(self,t):
        x=QLabel(t);f=x.font();f.setPointSize(19);f.setBold(True);x.setFont(f);x.setAlignment(Qt.AlignCenter);return x
    def _login(self):
        p=QWidget();l=QVBoxLayout(p);l.setContentsMargins(220,50,220,50);l.addWidget(self.title('Ultra Stalker Desktop'));self.saved=QComboBox();self.saved.addItem('Saved profiles…',None)
        for x in load_profiles():self.saved.addItem(x.name,x)
        self.saved.currentIndexChanged.connect(lambda _:self.fill_profile(self.saved.currentData()) if self.saved.currentData() else None);l.addWidget(self.saved)
        self.type=QComboBox();self.type.addItems(['stalker','xtream','m3u']);self.name=QLineEdit();self.name.setPlaceholderText('Profile name');self.url=QLineEdit();self.url.setPlaceholderText('Portal / Server / M3U URL');self.mac=QLineEdit();self.mac.setPlaceholderText('MAC for Stalker');self.user=QLineEdit();self.user.setPlaceholderText('Username for Xtream');self.password=QLineEdit();self.password.setPlaceholderText('Password for Xtream');self.password.setEchoMode(QLineEdit.Password)
        for x in [self.type,self.name,self.url,self.mac,self.user,self.password]:x.setMinimumHeight(36);l.addWidget(x)
        row=QHBoxLayout();b=QPushButton('Connect');b.setMinimumHeight(44);b.clicked.connect(self.connect_profile);row.addWidget(b);d=QPushButton('Delete Saved Profile');d.setMinimumHeight(44);d.clicked.connect(self.delete_selected_profile);row.addWidget(d);self.back_home=QPushButton('Back to Home');self.back_home.setMinimumHeight(44);self.back_home.setEnabled(False);self.back_home.clicked.connect(self.return_home);row.addWidget(self.back_home);l.addLayout(row);l.addStretch();return p
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
        p=QWidget();l=QVBoxLayout(p);l.setContentsMargins(80,60,80,60);l.addWidget(self.title('Home'));row=QHBoxLayout()
        for t in ['Live','Movies','Series']:
            b=QPushButton(t);b.setMinimumSize(210,110);b.clicked.connect(lambda _,k=t.lower():self.open_kind(k));row.addWidget(b)
        l.addLayout(row);row2=QHBoxLayout()
        for text,fn in [('Favorites',self.open_favorites),('History / Continue',self.open_history),('Settings',self.open_settings),('Diagnostics',self.export_diagnostics),('About',self.show_about)]:b=QPushButton(text);b.setMinimumHeight(60);b.clicked.connect(fn);row2.addWidget(b)
        l.addLayout(row2);self.search=QLineEdit();self.search.setPlaceholderText('Search Live, Movies and Series');self.search.returnPressed.connect(self.global_search);l.addWidget(self.search);b=QPushButton('Profiles');b.clicked.connect(self.show_profiles);l.addWidget(b);return p
    def _browser(self):
        p=QWidget();v=QVBoxLayout(p);self.btitle=self.title('Browser');v.addWidget(self.btitle)
        self.backdrop_view=QLabel();self.backdrop_view.setFixedHeight(145);self.backdrop_view.setAlignment(Qt.AlignCenter);self.backdrop_view.hide();v.addWidget(self.backdrop_view)
        split=QSplitter();self.categories=QListWidget();self.items=QListWidget();split.addWidget(self.categories);split.addWidget(self.items);split.setStretchFactor(1,3);v.addWidget(split)
        self.categories.itemClicked.connect(self.load_category);self.categories.itemActivated.connect(self.load_category);self.items.itemDoubleClicked.connect(self.activate_item);self.items.itemSelectionChanged.connect(self.show_info)
        details=QHBoxLayout();self.poster_view=QLabel();self.poster_view.setFixedSize(145,205);self.poster_view.setAlignment(Qt.AlignCenter);self.poster_view.hide();details.addWidget(self.poster_view)
        self.info=QLabel('');self.info.setWordWrap(True);self.info.setAlignment(Qt.AlignTop|Qt.AlignLeft);details.addWidget(self.info,1);v.addLayout(details)
        r=QHBoxLayout()
        for text,fn in [('Favorite',self.favorite),('Play / Open',self.play_selected),('Pause / Resume',self.pause_resume),('Stop',self.stop_playback),('Back',self.browser_back)]:b=QPushButton(text);b.clicked.connect(fn);r.addWidget(b)
        v.addLayout(r);controls=QHBoxLayout()
        for text,fn in [('Seek -30s',lambda:self.seek_by(-30)),('Seek +30s',lambda:self.seek_by(30)),('Volume -',lambda:self.adjust_volume(-10)),('Volume +',lambda:self.adjust_volume(10)),('Audio Track',self.cycle_audio),('Subtitle Track',self.cycle_subtitle),('Fullscreen',self.toggle_fullscreen)]:b=QPushButton(text);b.clicked.connect(fn);controls.addWidget(b)
        v.addLayout(controls);return p
    def busy(self,t):self.statusBar().showMessage(t)
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
        self.stack.setCurrentWidget(self.home);self.busy('Connected • '+self.profile.name)

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
            self.back_home.setEnabled(True);self.stack.setCurrentWidget(self.home)
            self.busy('Connected • '+p.name+(' • session only' if not persisted else ''))
        self.work(task,connected,active=lambda:generation==self.connection_generation,error=lambda _message:self.busy('Connection failed'))
    def open_kind(self,k):
        if not self.adapter:return
        self.request_generation+=1;generation=self.request_generation
        self.browser_history.clear();self.current_kind=k;self.btitle.setText(k.title());self.categories.clear();self.items.clear();self.stack.setCurrentWidget(self.browser)
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
            self.browser_history.clear();self.current_items=rows;self.categories.clear();self.btitle.setText('Search • '+query_text);self.render(rows);self.stack.setCurrentWidget(self.browser);self.busy(str(len(rows))+' results')
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
        self.info.setText((m.description or '')+('   Rating: '+m.rating if m.rating else ''))
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
                self.info.setText((cur.description or '')+('   Rating: '+cur.rating if cur.rating else ''))
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
        self.stack.setCurrentWidget(self.home)
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
        self.browser_history.clear();self.categories.clear();self.btitle.setText('Favorites');self.current_items=rows;self.render(self.current_items);self.stack.setCurrentWidget(self.browser)
    def open_history(self):
        if not self.profile:return
        try:rows=history(self.source_key)
        except Exception as exc:
            logging.getLogger(__name__).warning('History unavailable: %s',type(exc).__name__);self.busy('History unavailable');return
        self.browser_history.clear();self.categories.clear();self.btitle.setText('History / Continue Watching');self.current_items=[x[0] for x in rows];self.render(self.current_items)
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

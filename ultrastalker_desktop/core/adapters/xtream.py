from __future__ import annotations
from urllib.parse import quote
import threading
from .base import SourceAdapter
from ultrastalker_desktop.core.models import Category,MediaItem
from ultrastalker_desktop.core.http import make_session,safe_request_error,request_timeout

class XtreamAdapter(SourceAdapter):
    def __init__(self,url,username,password,timeout=15):
        self.base=url.strip().rstrip('/')
        if not self.base.startswith(('http://','https://')): self.base='http://'+self.base
        if self.base.lower().endswith('/player_api.php'):
            self.base=self.base[:-len('/player_api.php')].rstrip('/')
        self.username=username; self.password=password; self.timeout=timeout; self.http=make_session(); self.auth={}; self._request_lock=threading.RLock()
    def _segment(self,value): return quote(str(value),safe='')
    def _stream_url(self,kind,item_id,ext): return f'{self.base}/{kind}/{self._segment(self.username)}/{self._segment(self.password)}/{self._segment(item_id)}.{self._segment(ext)}'
    @staticmethod
    def _rows(value): return value if isinstance(value,list) else []
    @staticmethod
    def _artwork_value(value):
        if isinstance(value,list):value=next((x for x in value if x), '')
        return str(value or '')
    def _api(self,action=None,**extra):
        p={'username':self.username,'password':self.password};
        if action:p['action']=action
        p.update(extra)
        try:
            with self._request_lock:
                r=self.http.get(self.base+'/player_api.php',params=p,timeout=request_timeout(self.timeout)); r.raise_for_status(); return r.json()
        except Exception as exc:
            raise RuntimeError(safe_request_error(exc,'Xtream request failed')) from None
    def connect(self):
        self.auth=self._api(); ai=self.auth.get('user_info',{}) if isinstance(self.auth,dict) else {}
        if str(ai.get('auth','0'))!='1': raise RuntimeError('Xtream authentication failed')
        return True
    def categories(self,kind,cancelled=None):
        if cancelled and cancelled():return []
        action={'live':'get_live_categories','movies':'get_vod_categories','series':'get_series_categories'}[kind]
        rows=self._rows(self._api(action)); out=[]
        for x in rows:
            if cancelled and cancelled():
                return []
            if not isinstance(x,dict) or not x.get('category_name'):
                continue
            out.append(Category(str(x.get('category_id','')),str(x.get('category_name','')),kind,x))
        return out
    def items(self,kind,category_id='',cancelled=None):
        if cancelled and cancelled():return []
        action={'live':'get_live_streams','movies':'get_vod_streams','series':'get_series'}[kind]
        extra={'category_id':category_id} if category_id else {}; rows=self._rows(self._api(action,**extra)); out=[]
        for x in rows:
            if cancelled and cancelled():
                return []
            if not isinstance(x,dict):
                continue
            title=str(x.get('name') or x.get('title') or '').strip()
            raw_id=x.get('stream_id') if x.get('stream_id') is not None else x.get('series_id')
            mid=str(raw_id if raw_id is not None else '').strip()
            # A single malformed provider row must not poison the whole catalog,
            # but it also must never become a synthetic playable item with an
            # empty id/URL. Skip only the unusable row and preserve the rest.
            if not title or not mid:
                continue
            backdrop=self._artwork_value(x.get('backdrop_path') or x.get('backdrop') or x.get('background'))
            out.append(MediaItem(mid,title,kind,str(category_id),poster=self._artwork_value(x.get('stream_icon') or x.get('cover')),description=str(x.get('plot') or ''),year=str(x.get('year') or ''),rating=str(x.get('rating') or ''),series_id=str(x.get('series_id') or ''),raw=x,backdrop=backdrop))
        return out
    @staticmethod
    def _b64(value):
        import base64,binascii
        text=str(value or '')
        try:
            decoded=base64.b64decode(text,validate=True).decode('utf-8')
            return decoded if decoded.strip() else text
        except (binascii.Error,ValueError,UnicodeDecodeError):
            return text
    def short_epg(self,item,cancelled=None):
        if cancelled and cancelled():return []
        if (item.kind or '').lower()!='live':return []
        js=self._api('get_short_epg',stream_id=item.id,limit=4)
        rows=js.get('epg_listings') if isinstance(js,dict) else []
        out=[]
        for x in rows if isinstance(rows,list) else []:
            if not isinstance(x,dict):continue
            row=self._epg_row(self._b64(x.get('title')),x.get('start_timestamp'),x.get('stop_timestamp'),self._b64(x.get('description')))
            if row:out.append(row)
        return out[:6]
    def series_episodes(self,item,cancelled=None):
        if cancelled and cancelled():return []
        data=self._api('get_series_info',series_id=item.series_id or item.id); out=[]
        if cancelled and cancelled():return []
        eps=data.get('episodes',{}) if isinstance(data,dict) else {}
        if isinstance(eps,dict):
            groups=list(eps.items())
        elif isinstance(eps,list):
            # A few Xtream-compatible panels flatten episodes into one list and
            # put the season on each row. Accept that shape without weakening
            # the normal dict-of-seasons path.
            groups=[(None,eps)]
        else:
            groups=[]
        for season,rows in groups:
            if cancelled and cancelled():
                return []
            if not isinstance(rows,list):
                continue
            for x in rows:
                if cancelled and cancelled():
                    return []
                if not isinstance(x,dict):
                    continue
                raw_eid=x.get('id') if x.get('id') is not None else x.get('episode_num')
                eid=str(raw_eid if raw_eid is not None else '').strip()
                if not eid:
                    continue
                title=str(x.get('title') or f'Episode {x.get("episode_num","")}').strip() or f'Episode {eid}'
                ext=str(x.get('container_extension') or 'mp4'); url=self._stream_url('series',eid,ext)
                info=x.get('info') if isinstance(x.get('info'),dict) else {}
                backdrop=self._artwork_value(info.get('backdrop_path') or item.backdrop)
                season_value=season if season is not None else x.get('season')
                out.append(MediaItem(eid,title,'episode',item.category_id,url,poster=self._artwork_value(info.get('movie_image') or item.poster),series_id=item.id,season=int(season_value) if str(season_value).isdigit() else None,episode=int(x.get('episode_num')) if str(x.get('episode_num','')).isdigit() else None,raw=x,backdrop=backdrop))
        return out
    def resolve_stream(self,item,cancelled=None):
        if cancelled and cancelled(): return ''
        if item.kind=='live': ext=str(item.raw.get('container_extension') or 'ts'); return self._stream_url('live',item.id,ext)
        if item.kind=='movies': ext=str(item.raw.get('container_extension') or 'mp4'); return self._stream_url('movie',item.id,ext)
        if item.kind=='episode':
            ext=str(item.raw.get('container_extension') or item.raw.get('container_ext') or 'mp4')
            return self._stream_url('series',item.id,ext)
        if item.stream_url:return item.stream_url
        return ''

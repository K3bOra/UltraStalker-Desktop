from __future__ import annotations
import logging, re, urllib.parse, threading
import requests
from .base import SourceAdapter
from ultrastalker_desktop.core.models import Category, MediaItem
from ultrastalker_desktop.core.http import make_session,safe_request_error,request_timeout

class StalkerError(RuntimeError): pass

class StalkerAdapter(SourceAdapter):
    def __init__(self, portal_url:str, mac:str, timeout:int=15):
        raw=portal_url.strip().rstrip('/')
        if not raw.startswith(('http://','https://')): raw='http://'+raw
        self.endpoint=''
        lower=raw.lower()
        # Accept both user-facing MAG portal URLs (.../c/) and direct
        # middleware endpoints. Keep an explicit endpoint as the first choice.
        if lower.endswith('/portal.php') or lower.endswith('/server/load.php'):
            self.endpoint=raw
            if lower.endswith('/portal.php'):
                self.base=raw[:-len('/portal.php')]
            else:
                self.base=raw[:-len('/server/load.php')]
        elif lower.endswith('/c'):
            self.base=raw[:-2].rstrip('/')
        else:
            self.base=raw
        self.mac=mac.strip().upper(); self.timeout=timeout; self.http=make_session(); self.token=''; self._request_lock=threading.RLock()

    def _headers(self):
        h={
            'User-Agent':'Mozilla/5.0 (QtEmbedded; U; Linux; C)',
            'Accept':'*/*',
            'Connection':'Keep-Alive',
            'X-User-Agent':'Model: MAG254; Link: Ethernet',
            'Referer':self.base.rstrip('/')+'/c/',
            'Cookie':f'mac={urllib.parse.quote(self.mac)}; stb_lang=en; timezone=GMT',
        }
        if self.token: h['Authorization']='Bearer '+self.token
        return h

    def _candidates(self):
        b=self.base
        # A user-facing .../stalker_portal/c/ URL maps naturally to
        # .../stalker_portal/server/load.php.  Prefer that before portal.php so
        # a normal Ministra entrypoint does not pay an unnecessary failed probe.
        if b.lower().endswith('/stalker_portal'):
            raw=[b+'/server/load.php',b+'/portal.php']
        else:
            raw=[b+'/portal.php',b+'/server/load.php',b+'/stalker_portal/server/load.php']
        out=[]
        for ep in raw:
            if ep not in out:out.append(ep)
        return out

    def _get(self, params, allow_unauth=False, _refresh=True):
        with self._request_lock:
            return self._get_locked(params,allow_unauth=allow_unauth,_refresh=_refresh)

    def _get_locked(self, params, allow_unauth=False, _refresh=True):
        last=None
        eps=([self.endpoint] if self.endpoint else [])+[x for x in self._candidates() if x!=self.endpoint]
        for ep in eps:
            if not ep: continue
            host_reachable=False
            try:
                action=str(params.get('action') or '')
                methods=('get','post')
                for method in methods:
                    if method=='get':
                        r=self.http.get(ep,params=params,headers=self._headers(),timeout=request_timeout(self.timeout))
                    else:
                        # Some middleware forks answer the same load.php API only
                        # when form-encoded. POST is a narrow fallback for a 405
                        # or a successful-but-non-JSON GET, never an unconditional
                        # duplicate request.
                        r=self.http.post(ep,data=params,headers=self._headers(),timeout=request_timeout(self.timeout))
                    host_reachable=True
                    if r.status_code in (401,403) and self.token and not allow_unauth and _refresh and action!='handshake':
                        self.token=''
                        self.endpoint=ep
                        self.connect()
                        return self._get(params,allow_unauth=False,_refresh=False)
                    if method=='get' and r.status_code==405:
                        continue
                    r.raise_for_status()
                    try:
                        data=r.json()
                    except ValueError:
                        if method=='get':
                            continue
                        raise
                    if isinstance(data,dict):
                        self.endpoint=ep; return data.get('js',data)
                    if isinstance(data,list):
                        self.endpoint=ep; return data
                    if method=='get':
                        continue
                last='Portal request failed (invalid response)'
            except Exception as e:
                last=safe_request_error(e,'Portal request failed')
                # Every candidate points at the same host. If DNS, TCP or TLS
                # connection establishment itself failed, changing only the URL
                # path cannot recover and would multiply the timeout. HTTP/path
                # failures still continue to the next compatible endpoint.
                if (not host_reachable and
                    isinstance(e,(requests.exceptions.ConnectionError, requests.exceptions.SSLError))):
                    break
        raise StalkerError(str(last or 'Portal request failed'))

    def connect(self):
        js=self._get({'type':'stb','action':'handshake','JsHttpRequest':'1-xml'},True)
        if isinstance(js,dict): self.token=str(js.get('token') or '')
        if not self.token: raise StalkerError('Handshake returned no token')
        try:
            self._get({'type':'stb','action':'get_profile','hd':'1','ver':'ImageDescription: 0.2.18-r23-pub-254','num_banks':'2','stb_type':'MAG254','client_type':'STB','image_version':'218','video_out':'hdmi','JsHttpRequest':'1-xml'})
        except Exception as exc:
            # Some middleware omits/restricts get_profile after a valid handshake.
            # Connection remains usable; never log portal response/URL details.
            logging.getLogger(__name__).debug('Optional Stalker profile probe failed: %s', type(exc).__name__)
        return True

    def _ensure(self):
        if not self.token: self.connect()

    @staticmethod
    def _extract_rows(js):
        if isinstance(js, list):
            return js
        if isinstance(js, dict):
            rows = js.get('data') or js.get('items') or js.get('results') or []
            return rows if isinstance(rows, list) else []
        return []

    def categories(self, kind, cancelled=None):
        if cancelled and cancelled(): return []
        self._ensure(); kind=kind.lower()
        typ={'live':'itv','movies':'vod','series':'series'}.get(kind,kind)

        def fetch(category_type):
            rows=[]; last=None; successful=False
            for action in ('get_genres','get_categories'):
                try:
                    js=self._get({'type':category_type,'action':action,'JsHttpRequest':'1-xml'})
                    successful=True
                    rows=self._extract_rows(js)
                    if rows: break
                except Exception as exc:
                    last=exc
            return rows,successful,last

        rows,successful,last=fetch(typ)
        # Portals that model shows as VOD rows with is_series=1 commonly do not
        # implement type=series category actions either.  Reuse the VOD category
        # shelf so selecting a category can still reach the series item fallback.
        if kind=='series' and not rows:
            vod_rows,vod_success,vod_last=fetch('vod')
            successful=successful or vod_success
            if vod_rows: rows=vod_rows
            if vod_last is not None: last=vod_last
        # An empty but valid response is not a transport failure.  Raise only if
        # every compatible category request failed outright.
        if not rows and not successful and last is not None: raise last
        out=[]; seen=set()
        for x in rows:
            if not isinstance(x,dict): continue
            cid=str(x.get('id') or x.get('genre_id') or x.get('category_id') or '')
            title=str(x.get('title') or x.get('name') or x.get('category_name') or '').strip()
            key=(cid,title.casefold())
            if title and key not in seen:
                seen.add(key); out.append(Category(cid,title,kind,x))
        return out

    def _ordered_pages(self, typ, extra=None, max_pages=200, cancelled=None):
        extra=dict(extra or {}); out=[]; seen=set(); total=None; empty_or_repeat=0
        first_error=None
        # Stalker/Ministra deployments disagree in the wild about whether the
        # first page should be addressed as p=0 or p=1. Probe p=0 first, then
        # continue 1..N. If p=0 aliases p=1, tolerate that single duplicate and
        # continue to p=2 instead of truncating the catalog.
        pages=[0]+list(range(1,max_pages))
        for page in pages:
            if cancelled and cancelled(): break
            params={'type':typ,'action':'get_ordered_list','p':str(page),'JsHttpRequest':'1-xml'}
            params.update(extra)
            try:
                js=self._get(params)
            except Exception as exc:
                if page==0:
                    first_error=exc
                    continue
                raise
            if cancelled and cancelled(): break
            rows=self._extract_rows(js)
            if isinstance(js,dict):
                try:
                    total=int(js.get('total_items') or js.get('total') or 0) or total
                except (TypeError, ValueError):
                    pass
            if not rows:
                if page==0:
                    # p=0 may be unsupported while p=1 is valid.
                    continue
                break
            added=0
            for row in rows:
                if not isinstance(row,dict): continue
                identity=str(row.get('id') or row.get('ch_id') or row.get('movie_id') or row.get('series_id') or '')
                if not identity:
                    identity=repr(sorted(row.items()))[:500]
                if identity in seen: continue
                seen.add(identity); out.append(row); added+=1
            if total and len(out)>=total: break
            if added==0:
                empty_or_repeat+=1
                if empty_or_repeat>=2: break
            else:
                empty_or_repeat=0
        if not out and first_error is not None:
            raise first_error
        return out

    def items(self, kind, category_id='', cancelled=None):
        if cancelled and cancelled(): return []
        self._ensure(); kind=kind.lower(); typ={'live':'itv','movies':'vod','series':'series'}.get(kind,kind)

        # Series needs a wider compatibility ladder because some Ministra
        # deployments expose shows only through VOD (is_series=1) and may reject
        # the dedicated type=series API entirely.
        if kind=='series':
            rows=[]; successful=False; last=None
            series_attempts=[{'category':category_id}] if category_id else [{}]
            if category_id: series_attempts.append({'genre':category_id})
            for extra in series_attempts:
                try:
                    candidate=self._ordered_pages('series',extra,cancelled=cancelled)
                    successful=True
                    if candidate:
                        rows=candidate; break
                except Exception as exc:
                    last=exc
            if not rows:
                vod_attempts=[{'category':category_id}] if category_id else [{}]
                if category_id: vod_attempts.append({'genre':category_id})
                for extra in vod_attempts:
                    try:
                        candidate=self._ordered_pages('vod',extra,cancelled=cancelled)
                        successful=True
                        filtered=[x for x in candidate if self._truthy(x.get('is_series'))]
                        if filtered:
                            rows=filtered; break
                    except Exception as exc:
                        last=exc
            if not rows and not successful and last is not None:
                raise last
        else:
            extra={}
            if category_id:
                extra['genre' if kind=='live' else 'category']=category_id
            rows=None
            if kind=='live' and not category_id:
                # Prefer the complete channel action for the All view/search.
                # A portal that does not implement it falls back to pagination.
                try:
                    js=self._get({'type':'itv','action':'get_all_channels','JsHttpRequest':'1-xml'})
                    all_rows=self._extract_rows(js)
                    if all_rows:
                        rows=all_rows
                except Exception:
                    rows=None
            if rows is None:
                rows=self._ordered_pages(typ,extra,cancelled=cancelled)
            # A few non-standard VOD middleware forks accept the ITV-style
            # ``genre`` parameter. Use it only as an empty-result fallback.
            if category_id and kind=='movies' and not rows:
                rows=self._ordered_pages(typ,{'genre':category_id},cancelled=cancelled)
            if kind=='movies':
                # Keep VOD-backed series out of the movie shelf.
                rows=[x for x in rows if not self._truthy(x.get('is_series'))]

        out=[]
        for x in rows:
            title=str(x.get('name') or x.get('title') or '').strip()
            if not title: continue
            mid=str(x.get('id') or x.get('ch_id') or x.get('movie_id') or x.get('series_id') or title)
            cmd=str(x.get('cmd') or x.get('url') or '')
            poster=str(x.get('screenshot_uri') or x.get('poster') or x.get('logo') or '')
            out.append(MediaItem(mid,title,kind,str(category_id),cmd if cmd.startswith(('http://','https://')) else '',cmd,poster,str(x.get('description') or x.get('descr') or ''),str(x.get('year') or ''),str(x.get('rating') or ''),str((x.get('series_id') or mid) if kind=='series' else ''),raw=x))
        return out

    @staticmethod
    def _int_or_none(*values):
        for value in values:
            if value is None or isinstance(value, (dict, list, tuple)):
                continue
            text=str(value).strip()
            if text.isdigit():
                return int(text)
            match=re.search(r'\d+',text)
            if match:
                return int(match.group(0))
        return None

    @staticmethod
    def _truthy(value):
        return str(value or '').strip().lower() in ('1','true','yes','on')

    def _episode_from_row(self,row,parent,series_id,default_season=None,default_episode=None):
        if not isinstance(row,dict): return None
        if self._truthy(row.get('is_season')): return None
        season=self._int_or_none(row.get('season'),row.get('season_number'),default_season)
        episode=self._int_or_none(
            row.get('episode'),row.get('episode_num'),row.get('series_number'),
            row.get('series') if not isinstance(row.get('series'),(dict,list,tuple)) else None,
            default_episode,
        )
        title=str(row.get('name') or row.get('title') or '').strip()
        if not title:
            title=('Episode '+str(episode)) if episode is not None else 'Episode'
        eid=str(row.get('id') or row.get('episode_id') or row.get('file_id') or '')
        if not eid:
            eid=f'{series_id}:{season or 0}:{episode or 0}:{title}'
        cmd=str(row.get('cmd') or row.get('url') or '')
        poster=str(row.get('screenshot_uri') or row.get('poster') or parent.poster or '')
        return MediaItem(
            eid,title,'episode',parent.category_id,
            cmd if cmd.startswith(('http://','https://')) else '',cmd,poster,
            str(row.get('description') or row.get('descr') or parent.description or ''),
            series_id=str(series_id),season=season,episode=episode,raw=row,
        )

    def _embedded_series_episodes(self,item):
        embedded=(item.raw or {}).get('series')
        if not isinstance(embedded,list) or not embedded:
            return []
        sid=item.series_id or item.id
        out=[]

        def walk(value,season_hint=None):
            if isinstance(value,list):
                for index,child in enumerate(value,1):
                    walk(child,season_hint)
                return
            if not isinstance(value,dict):
                return
            local_season=self._int_or_none(value.get('season'),value.get('season_number'),season_hint)
            nested=value.get('episodes')
            if isinstance(nested,list):
                for index,child in enumerate(nested,1):
                    if isinstance(child,dict):
                        ep=self._episode_from_row(child,item,sid,local_season,index)
                        if ep: out.append(ep)
                return
            nested=value.get('series')
            if isinstance(nested,list):
                for index,child in enumerate(nested,1):
                    if isinstance(child,dict):
                        ep=self._episode_from_row(child,item,sid,local_season,index)
                        if ep: out.append(ep)
                return
            ep=self._episode_from_row(value,item,sid,local_season,len(out)+1)
            if ep: out.append(ep)

        walk(embedded)
        return out

    def _rows_to_episodes(self,item,rows,series_id,default_season=None):
        out=[]
        for index,row in enumerate(rows,1):
            ep=self._episode_from_row(row,item,series_id,default_season,index)
            if ep: out.append(ep)
        return out

    def series_episodes(self,item,cancelled=None):
        if cancelled and cancelled(): return []
        self._ensure()
        sid=item.series_id or item.id

        embedded=self._embedded_series_episodes(item)
        if embedded:
            return embedded

        # Dedicated series APIs first. Different Stalker forks use movie_id or
        # series_id for the parent relation, so preserve both established paths.
        attempts=[
          ('series',{'movie_id':sid,'season_id':'0','episode_id':'0'}),
          ('vod',{'series_id':sid})]
        last_error=None; successful_attempt=False
        for typ,extra in attempts:
            if cancelled and cancelled(): return []
            try:
                rows=self._ordered_pages(typ,extra,max_pages=100,cancelled=cancelled)
                if cancelled and cancelled(): return []
                successful_attempt=True
                eps=self._rows_to_episodes(item,rows,sid)
                if eps:return eps
            except Exception as exc:
                last_error=exc

        # Ministra VOD-backed series: first request returns season shells using
        # movie_id + season_id=0. Each shell is then expanded with its provider
        # season id. If the portal skips shells and returns episodes directly,
        # the same branch handles that too.
        if cancelled and cancelled(): return []
        try:
            rows=self._ordered_pages('vod',{
                'movie_id':sid,'season_id':'0','episode_id':'0'
            },max_pages=100,cancelled=cancelled)
            if cancelled and cancelled(): return []
            successful_attempt=True
            shells=[x for x in rows if isinstance(x,dict) and self._truthy(x.get('is_season'))]
            if shells:
                eps=[]
                for shell in shells:
                    if cancelled and cancelled(): return []
                    provider_season=str(shell.get('id') or shell.get('season_id') or '').strip()
                    if not provider_season: continue
                    season_no=self._int_or_none(shell.get('season_number'),shell.get('season'),shell.get('name'))
                    child_rows=self._ordered_pages('vod',{
                        'movie_id':sid,'season_id':provider_season,'episode_id':'0'
                    },max_pages=100,cancelled=cancelled)
                    eps.extend(self._rows_to_episodes(item,child_rows,sid,season_no))
                if eps:return eps
            else:
                eps=self._rows_to_episodes(item,rows,sid)
                if eps:return eps
        except Exception as exc:
            last_error=exc

        if not successful_attempt and last_error is not None:
            raise last_error
        return []

    def short_epg(self, item, cancelled=None):
        if cancelled and cancelled(): return []
        if (item.kind or '').lower()!='live': return []
        self._ensure()
        ch=str((item.raw or {}).get('id') or item.id or '')
        if not ch: return []
        js=self._get({'type':'itv','action':'get_short_epg','ch_id':ch,'size':'4','JsHttpRequest':'1-xml'})
        out=[]
        for x in self._extract_rows(js):
            if not isinstance(x,dict): continue
            row=self._epg_row(x.get('name') or x.get('title'),x.get('start_timestamp'),x.get('stop_timestamp'),x.get('descr') or x.get('description'))
            if row: out.append(row)
        return out[:6]

    def _rehydrate_playable(self, item, cancelled=None):
        """Recover a fresh provider command for persisted/cache snapshots."""
        if cancelled and cancelled():
            return item
        if item.stream_url or item.command:
            return item
        if item.kind == 'episode':
            parent = MediaItem(
                str(item.series_id or ''), item.title, 'series', item.category_id,
                series_id=str(item.series_id or '')
            )
            episodes = self.series_episodes(parent, cancelled=cancelled)
            # Numbered episodes must match by season/episode before provider id.
            # Several VOD-backed Stalker portals reuse the same container id for
            # every episode and select the actual file through ``series=``.
            if item.season is not None and item.episode is not None:
                for current in episodes:
                    if cancelled and cancelled():
                        return item
                    if current.season == item.season and current.episode == item.episode:
                        return current
            for current in episodes:
                if cancelled and cancelled():
                    return item
                if str(current.id) == str(item.id):
                    return current
            return item
        if item.kind in ('live', 'movies'):
            for current in self.items(item.kind, '', cancelled=cancelled):
                if cancelled and cancelled():
                    return item
                if str(current.id) == str(item.id):
                    return current
        return item

    def rehydrate_item(self, item, cancelled=None):
        return self._rehydrate_playable(item, cancelled=cancelled)

    def resolve_stream(self,item,cancelled=None):
        if cancelled and cancelled(): return ''
        if item.stream_url.startswith(('http://','https://')): return item.stream_url
        cmd=item.command.strip()
        if not cmd:
            item = self._rehydrate_playable(item, cancelled=cancelled)
            if item.stream_url.startswith(('http://','https://')):
                return item.stream_url
            cmd = item.command.strip()
        if cmd.startswith(('http://','https://')): return cmd
        if not cmd:
            return ''
        if cancelled and cancelled(): return ''
        self._ensure()
        if cancelled and cancelled(): return ''
        typ='itv' if item.kind=='live' else 'vod'
        series_value='0'
        if item.kind=='episode':
            raw_series=(item.raw or {}).get('series')
            series_value=str(raw_series or item.episode or '0')
        js=self._get({'type':typ,'action':'create_link','cmd':cmd,'series':series_value,'forced_storage':'0','disable_ad':'0','download':'0','JsHttpRequest':'1-xml'})
        value=''
        if isinstance(js,dict): value=str(js.get('cmd') or js.get('url') or '')
        elif isinstance(js,str): value=js
        value=value.strip()
        # MAG portals often return ffmpeg <url>
        value=re.sub(r'^(?:ffmpeg|ffrt|auto)\s+','',value,flags=re.I).strip()
        m=re.search(r'(https?://\S+)',value)
        return m.group(1) if m else value

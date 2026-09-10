from __future__ import annotations

import hashlib
import re
import threading
from urllib.parse import urlsplit, urlunsplit

from .base import SourceAdapter
from ultrastalker_desktop.core.models import Category, MediaItem
from ultrastalker_desktop.core.http import make_session, safe_request_error, request_timeout


class M3UValidationError(RuntimeError):
    pass


class M3UAdapter(SourceAdapter):
    _MOVIE_GROUP_WORDS = (
        'movie', 'movies', 'vod', 'film', 'films', 'cinema', 'أفلام', 'افلام',
    )
    _SERIES_GROUP_WORDS = (
        'series', 'serial', 'tv show', 'tv shows', 'shows', 'مسلسل', 'مسلسلات',
    )
    _EPISODE_PATTERNS = (
        re.compile(r'(?i)\bS(?P<season>\d{1,3})\s*[-._ ]?\s*E(?P<episode>\d{1,4})\b'),
        re.compile(r'(?i)\b(?P<season>\d{1,3})\s*x\s*(?P<episode>\d{1,4})\b'),
        re.compile(
            r'(?i)\bseason\s*(?P<season>\d{1,3})\s*[-._ :]*\s*'
            r'(?:episode|ep)\s*(?P<episode>\d{1,4})\b'
        ),
    )

    def __init__(self, url, timeout=20):
        self.url = url
        self.timeout = timeout
        self._items: list[MediaItem] = []
        self._series_items: list[MediaItem] = []
        self._episodes_by_series: dict[str, list[MediaItem]] = {}
        self.http = make_session()
        self._request_lock = threading.RLock()

    def connect(self):
        try:
            with self._request_lock:
                r = self.http.get(self.url, timeout=request_timeout(self.timeout))
                r.raise_for_status()
                self._parse(r.text)
                if not self._items:
                    raise M3UValidationError('M3U playlist contains no playable entries')
            return True
        except M3UValidationError:
            raise
        except Exception as exc:
            raise RuntimeError(safe_request_error(exc, 'M3U request failed')) from None

    @staticmethod
    def _attr(line: str, name: str) -> str:
        m = re.search(rf'{re.escape(name)}="([^"]*)"', line, re.I)
        return m.group(1).strip() if m else ''

    @staticmethod
    def _stable_url_identity(url: str) -> str:
        # Signed M3U URLs commonly rotate query tokens. IDs must not rotate with
        # them, so use scheme/host/path only as a duplicate-label tie-breaker.
        try:
            p = urlsplit(url)
            host = (p.hostname or '').lower()
            if p.port:
                host += ':' + str(p.port)
            return urlunsplit((p.scheme.lower(), host, p.path, '', ''))
        except Exception:
            return str(url).split('?', 1)[0].split('#', 1)[0]

    @classmethod
    def _stable_id(cls, group: str, name: str, tvg_id: str, url: str, used: set[str]) -> str:
        # Prefer provider-supplied tvg-id. If unavailable, group + display name
        # stays stable across playlist reorder and rotating stream tokens.
        base = '\x1f'.join((group, tvg_id or name)).encode('utf-8', 'surrogatepass')
        candidate = hashlib.sha256(base).hexdigest()[:24]
        if candidate not in used:
            return candidate
        # Only duplicate labels/IDs need URL as a deterministic tie-breaker.
        tied = base + b'\x1f' + cls._stable_url_identity(url).encode('utf-8', 'surrogatepass')
        return hashlib.sha256(tied).hexdigest()[:24]

    @classmethod
    def _logical_entry_key(cls, group: str, name: str, tvg_id: str, url: str) -> tuple[str, ...]:
        """Identity used only to coalesce obvious M3U mirrors in one refresh.

        A provider-supplied tvg-id is the strongest signal within a group. Without
        one, require the same normalized URL path as well as label/group so two
        genuinely different channels that share a display name remain distinct.
        Query tokens are ignored because they commonly rotate.
        """
        if tvg_id:
            return ('tvg', group.casefold(), tvg_id.casefold())
        return ('label-url', group.casefold(), name.casefold(), cls._stable_url_identity(url))

    @staticmethod
    def _path_kind(url: str) -> str:
        try:
            segments = [x.casefold() for x in urlsplit(url).path.split('/') if x]
        except Exception:
            return ''
        # URL path is stronger evidence than provider-written group text.
        if 'series' in segments:
            return 'episode'
        if 'movie' in segments or 'vod' in segments:
            return 'movies'
        if 'live' in segments:
            return 'live'
        return ''

    @classmethod
    def _group_kind(cls, group: str) -> str:
        text = (group or '').casefold()
        # Series first because labels such as "VOD Series" contain a movie-ish
        # VOD marker but are more specifically series collections.
        if any(word.casefold() in text for word in cls._SERIES_GROUP_WORDS):
            return 'episode'
        if any(word.casefold() in text for word in cls._MOVIE_GROUP_WORDS):
            return 'movies'
        return 'live'

    @classmethod
    def _classify_kind(cls, url: str, group: str) -> str:
        return cls._path_kind(url) or cls._group_kind(group)

    @classmethod
    def _episode_identity(cls, title: str) -> tuple[str, int | None, int | None]:
        clean = (title or '').strip()
        for pattern in cls._EPISODE_PATTERNS:
            match = pattern.search(clean)
            if not match:
                continue
            season = int(match.group('season'))
            episode = int(match.group('episode'))
            # Most IPTV naming places SxxExx after the series title. Prefer the
            # prefix so an episode subtitle does not accidentally become part of
            # the synthetic series identity. If the marker starts the title, use
            # the remaining text instead.
            base = clean[:match.start()].strip(' -._[]()')
            if not base:
                base = clean[match.end():].strip(' -._[]()')
            return (base or clean, season, episode)
        return clean, None, None

    @staticmethod
    def _series_id(group: str, title: str) -> str:
        material = ('series\x1f' + group + '\x1f' + title).encode('utf-8', 'surrogatepass')
        return hashlib.sha256(material).hexdigest()[:24]

    def _build_series_index(self) -> None:
        grouped: dict[str, tuple[str, str, list[MediaItem]]] = {}
        for item in self._items:
            if item.kind != 'episode':
                continue
            series_title, season, episode = self._episode_identity(item.title)
            sid = self._series_id(item.category_id, series_title)
            item.series_id = sid
            item.season = season
            item.episode = episode
            if sid not in grouped:
                grouped[sid] = (series_title, item.category_id, [])
            grouped[sid][2].append(item)

        self._series_items = []
        self._episodes_by_series = {}
        for sid, (title, category, episodes) in grouped.items():
            episodes.sort(
                key=lambda x: (
                    x.season is None,
                    x.season if x.season is not None else 10**9,
                    x.episode is None,
                    x.episode if x.episode is not None else 10**9,
                    x.title.casefold(),
                )
            )
            poster = next((x.poster for x in episodes if x.poster), '')
            self._series_items.append(
                MediaItem(
                    sid,
                    title,
                    'series',
                    category_id=category,
                    poster=poster,
                    series_id=sid,
                    raw={'m3u_synthetic_series': True},
                )
            )
            self._episodes_by_series[sid] = episodes

    def _parse(self, text):
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        pending = None
        self._items = []
        self._series_items = []
        self._episodes_by_series = {}
        used: set[str] = set()
        logical_items: dict[tuple[str, ...], MediaItem] = {}
        for line in lines:
            if line.startswith('#EXTINF:'):
                name = line.split(',', 1)[1].strip() if ',' in line else 'Channel'
                group = self._attr(line, 'group-title') or 'Other'
                logo = self._attr(line, 'tvg-logo')
                tvg_id = self._attr(line, 'tvg-id')
                pending = (name, group, logo, tvg_id)
            elif not line.startswith('#'):
                if not line.lower().startswith(('http://', 'https://')):
                    pending = None
                    continue
                if pending:
                    name, group, logo, tvg_id = pending
                else:
                    # Basic M3U files are allowed to contain bare URLs without
                    # EXTINF metadata. Keep them playable instead of declaring
                    # a valid minimalist playlist empty.
                    name, group, logo, tvg_id = f'Stream {len(self._items) + 1}', 'Other', '', ''
                logical_key = self._logical_entry_key(group, name, tvg_id, line)
                existing = logical_items.get(logical_key)
                if existing is not None:
                    # Keep one logical item and retain mirrors only in memory. The
                    # shared media_snapshot sanitizer deliberately drops this raw
                    # field before Favorites/History/cache persistence.
                    if line != existing.stream_url:
                        raw = dict(existing.raw or {})
                        mirrors = list(raw.get('fallback_urls') or [])
                        if line not in mirrors:
                            mirrors.append(line)
                        raw['fallback_urls'] = mirrors
                        existing.raw = raw
                    pending = None
                    continue
                stable = self._stable_id(group, name, tvg_id, line, used)
                used.add(stable)
                kind = self._classify_kind(line, group)
                item = MediaItem(stable, name, kind, group, line, poster=logo)
                self._items.append(item)
                logical_items[logical_key] = item
                pending = None
        self._build_series_index()

    def categories(self, kind, cancelled=None):
        if cancelled and cancelled():
            return []
        source = self._series_items if kind == 'series' else [x for x in self._items if x.kind == kind]
        seen = []
        for item in source:
            if item.category_id not in seen:
                seen.append(item.category_id)
        return [Category(x, x, kind) for x in seen]

    def items(self, kind, category_id='', cancelled=None):
        if cancelled and cancelled():
            return []
        source = self._series_items if kind == 'series' else [x for x in self._items if x.kind == kind]
        return [x for x in source if not category_id or x.category_id == category_id]

    @staticmethod
    def _unique_title_match(rows: list[MediaItem], item: MediaItem) -> MediaItem | None:
        """Return a safe metadata fallback only when the match is unambiguous.

        Provider group names can change between playlist refreshes, which changes
        our synthetic IDs.  Persisted favorites/history should survive that move,
        but never at the cost of guessing between duplicate channel/movie names.
        """
        title = (item.title or '').strip().casefold()
        if not title:
            return None
        matches = [x for x in rows if (x.title or '').strip().casefold() == title]
        if len(matches) == 1:
            return matches[0]
        # If duplicate display names exist, the old category is useful only when
        # it still identifies exactly one current entry.  Otherwise fail closed.
        category = (item.category_id or '').strip().casefold()
        if category:
            narrowed = [
                x for x in matches
                if (x.category_id or '').strip().casefold() == category
            ]
            if len(narrowed) == 1:
                return narrowed[0]
        return None

    def series_episodes(self, item: MediaItem, cancelled=None) -> list[MediaItem]:
        if cancelled and cancelled():
            return []
        sid = item.series_id or item.id
        rows = self._episodes_by_series.get(sid)
        if rows is not None:
            return list(rows)
        # A provider may rename/move the M3U group while keeping the same show.
        # Rehydrate by title only when exactly one current synthetic series fits.
        current = self._unique_title_match(self._series_items, item)
        if current:
            return list(self._episodes_by_series.get(current.series_id or current.id, []))
        return []

    def _current_item(self, item: MediaItem) -> MediaItem | None:
        for current in self._items:
            if current.id == item.id:
                return current
        candidates = [x for x in self._items if x.kind == item.kind]
        if item.kind == 'episode':
            exact = [
                x for x in candidates
                if (x.title or '').strip().casefold() == (item.title or '').strip().casefold()
                and (item.season is None or x.season == item.season)
                and (item.episode is None or x.episode == item.episode)
            ]
            if len(exact) == 1:
                return exact[0]
        return self._unique_title_match(candidates, item)

    def rehydrate_item(self, item, cancelled=None):
        if cancelled and cancelled():
            return item
        return self._current_item(item) or item

    def resolve_stream(self, item, cancelled=None):
        if cancelled and cancelled():
            return ''
        if item.stream_url:
            return item.stream_url
        # Persisted favorites/history rehydrate against the current playlist;
        # this also restores in-memory fallback mirrors without ever persisting
        # their signed/tokenized URLs.
        current = self._current_item(item)
        return current.stream_url if current else ''

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import threading
import weakref

from .base import SourceAdapter
from ultrastalker_desktop.core.models import Category, MediaItem, media_snapshot
from ultrastalker_desktop.storage.database import cache_get, cache_set, cache_delete, cache_delete_prefix


@dataclass
class _FlightState:
    lock: threading.Lock
    refs: int = 0


@dataclass
class _NamespaceState:
    lock: threading.RLock
    generation: int = 0


class CachedAdapter(SourceAdapter):
    """SQLite-backed catalog cache with per-key request coalescing.

    Multiple UI/background requests for the same cold catalog share one
    provider call. Different keys remain independent, so a slow Movies request
    never blocks Live or Series. Namespace generations are shared across
    adapter instances so a superseded session can neither surface nor persist
    stale catalog data after a newer connection wins.
    """

    _namespaces_guard = threading.Lock()
    _namespaces = weakref.WeakValueDictionary()

    def __init__(self, inner, namespace):
        self.inner = inner
        self.ns = namespace
        self._flight_guard = threading.Lock()
        self._flights: dict[str, _FlightState] = {}
        with self._namespaces_guard:
            state = self._namespaces.get(namespace)
            if state is None:
                state = _NamespaceState(threading.RLock())
                self._namespaces[namespace] = state
            self._namespace_state = state
        with state.lock:
            # Snapshot the namespace epoch at construction. make_adapter() then
            # calls connect(), which advances it. Test/dev adapters that operate
            # without connect remain valid only until another instance connects.
            self._connected_generation = state.generation

    def connect(self):
        result = self.inner.connect()
        # Preserve the historical behavior: any completed connect attempt
        # invalidates the namespace, even when the provider reports False.
        # Generation prevents an older in-flight request from writing stale
        # rows after this deletion finishes.
        with self._namespace_state.lock:
            self._namespace_state.generation += 1
            self._connected_generation = self._namespace_state.generation
            cache_delete_prefix(self.ns + ':')
        return result

    @staticmethod
    def _is_cancelled(cancelled) -> bool:
        try:
            return bool(cancelled and cancelled())
        except Exception:
            # Cancellation hooks are advisory. A broken hook must not corrupt
            # cache coordination or strand waiters on a flight lock.
            return False

    def _is_current(self) -> bool:
        with self._namespace_state.lock:
            return self._connected_generation == self._namespace_state.generation

    def _decode_cached(self, key, raw, decode):
        try:
            return decode(raw)
        except (TypeError, ValueError, KeyError):
            # Cache payloads survive application upgrades. If a previous schema
            # no longer maps to today's dataclasses, drop only that disposable
            # row and refetch from the provider instead of failing the screen.
            with self._namespace_state.lock:
                cache_delete(key)
            return None

    @contextmanager
    def _flight(self, key: str, cancelled=None):
        """Acquire a short-lived per-key single-flight lock.

        Waiting is interruptible so navigating away does not leave a cancelled
        worker blocked behind a slow provider call. Reference counting prevents
        a third caller from creating a second lock while an existing waiter is
        about to acquire the first one.
        """
        with self._flight_guard:
            state = self._flights.get(key)
            if state is None:
                state = _FlightState(threading.Lock())
                self._flights[key] = state
            state.refs += 1

        acquired = False
        try:
            while not acquired:
                if self._is_cancelled(cancelled):
                    yield False
                    return
                acquired = state.lock.acquire(timeout=0.05)
            yield True
        finally:
            if acquired:
                state.lock.release()
            with self._flight_guard:
                state.refs -= 1
                if state.refs == 0 and self._flights.get(key) is state:
                    del self._flights[key]

    def _cache_read(self, key):
        # Serialize the tiny read with reconnect invalidation so a request can
        # never observe an old cache entry after generation advancement.
        with self._namespace_state.lock:
            return cache_get(key)

    def _fetch_rows(self, key, cancelled, fetch, decode, encode, ttl):
        # Once another adapter instance has connected for the same namespace,
        # this instance is obsolete. Fail closed rather than surfacing the new
        # session's cache through an old provider object.
        if not self._is_current() or self._is_cancelled(cancelled):
            return []

        raw = self._cache_read(key)
        if raw is not None:
            decoded = self._decode_cached(key, raw, decode)
            if decoded is not None:
                return decoded

        with self._flight(key, cancelled) as acquired:
            if not acquired or not self._is_current() or self._is_cancelled(cancelled):
                return []

            # The first caller may have filled the cache while we waited.
            raw = self._cache_read(key)
            if raw is not None:
                decoded = self._decode_cached(key, raw, decode)
                if decoded is not None:
                    return decoded

            with self._namespace_state.lock:
                generation = self._namespace_state.generation

            rows = fetch()

            # Navigation cancellation or a newer connection makes these rows
            # stale for both presentation and persistence.
            if self._is_cancelled(cancelled):
                return []
            with self._namespace_state.lock:
                if (
                    generation != self._namespace_state.generation
                    or self._connected_generation != self._namespace_state.generation
                ):
                    return []
                cache_set(key, encode(rows), ttl)
            return rows

    def categories(self, kind, cancelled=None):
        key = f'{self.ns}:categories:{kind}'
        return self._fetch_rows(
            key,
            cancelled,
            lambda: self.inner.categories(kind, cancelled=cancelled),
            lambda raw: [Category(**x) for x in raw],
            lambda rows: [asdict(x) for x in rows],
            300,
        )

    def items(self, kind, category_id='', cancelled=None):
        key = f'{self.ns}:items:{kind}:{category_id}'
        return self._fetch_rows(
            key,
            cancelled,
            lambda: self.inner.items(kind, category_id, cancelled=cancelled),
            lambda raw: [MediaItem(**x) for x in raw],
            lambda rows: [media_snapshot(x, keep_safe_artwork=True) for x in rows],
            180,
        )

    def series_episodes(self, item, cancelled=None):
        series_id = str(item.series_id or item.id or '')
        key = f'{self.ns}:episodes:{series_id}'
        return self._fetch_rows(
            key,
            cancelled,
            lambda: self.inner.series_episodes(item, cancelled=cancelled),
            lambda raw: [MediaItem(**x) for x in raw],
            lambda rows: [media_snapshot(x, keep_safe_artwork=True) for x in rows],
            180,
        )

    def short_epg(self, item, cancelled=None):
        fn = getattr(self.inner, 'short_epg', None)
        return fn(item, cancelled=cancelled) if fn else []

    def resolve_stream(self, item, cancelled=None):
        return self.inner.resolve_stream(item, cancelled=cancelled)

    def stream_candidates(self, item, cancelled=None):
        return self.inner.stream_candidates(item, cancelled=cancelled)

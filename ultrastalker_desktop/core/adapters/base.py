from __future__ import annotations

import re
from abc import ABC, abstractmethod

from ultrastalker_desktop.core.models import Category, MediaItem


class SourceAdapter(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def categories(self, kind: str, cancelled=None) -> list[Category]: ...

    @abstractmethod
    def items(self, kind: str, category_id: str = '', cancelled=None) -> list[MediaItem]: ...

    def series_episodes(self, item: MediaItem, cancelled=None) -> list[MediaItem]:
        return []

    @abstractmethod
    def resolve_stream(self, item: MediaItem, cancelled=None) -> str: ...

    def rehydrate_item(self, item: MediaItem, cancelled=None) -> MediaItem:
        """Return a fresh provider item when long-lived/cache state was sanitized.

        Persistent and short-lived snapshots intentionally discard transport
        commands and fallback URLs. Adapters that can recover the current row
        should override this hook so source fallback remains functional without
        ever persisting signed/tokenized URLs to disk.
        """
        return item

    @staticmethod
    def _normalize_candidate(value) -> str:
        if isinstance(value, dict):
            value = value.get('url') or value.get('cmd') or ''
        if not isinstance(value, str):
            return ''
        value = value.strip()
        value = re.sub(r'^(?:ffmpeg|ffrt|auto)\s+', '', value, flags=re.I).strip()
        m = re.search(r'https?://[^\s"\']+', value)
        return m.group(0) if m else ''

    def stream_candidates(self, item: MediaItem, cancelled=None) -> list[str]:
        if cancelled and cancelled():
            return []
        fresh = self.rehydrate_item(item, cancelled=cancelled)
        if cancelled and cancelled():
            return []
        primary = self.resolve_stream(fresh, cancelled=cancelled)
        if cancelled and cancelled():
            return []
        raw = fresh.raw or {}
        extras = raw.get('fallback_urls') or raw.get('sources') or []
        if isinstance(extras, str):
            extras = [extras]
        out = []
        for value in [primary] + list(extras if isinstance(extras, list) else []):
            if cancelled and cancelled():
                return []
            url = self._normalize_candidate(value)
            if url and url not in out:
                out.append(url)
        return out

"""JSON bridge between the cinematic web interface and the desktop core.

The page calls ``call('{"id":1,"method":"items","args":["movies","12"]}')``
through QWebChannel and receives the answer on the ``reply`` signal. Provider
work runs on a small thread pool; results hop back to the GUI thread before
they reach the page. Nothing that leaves this module carries stream URLs,
commands, passwords or tokens: the page only ever sees opaque item refs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, Signal, Slot

from ultrastalker_desktop import __version__, AUTHOR
from ultrastalker_desktop.core.adapters import make_adapter
from ultrastalker_desktop.core import cloud_catalog
from ultrastalker_desktop.core.models import MediaItem, Profile, profile_identity
from ultrastalker_desktop.storage import database as db
from ultrastalker_desktop.storage.profiles import delete_profile, load_profiles, save_profile
from ultrastalker_desktop.storage.settings import load_settings, save_settings
from ultrastalker_desktop.support_bundle import sanitize_text

log = logging.getLogger(__name__)

MAC_RE = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")
KINDS = ("live", "movies", "series")
UI_SETTINGS = ("ui_language", "player", "tmdb_language", "autoplay_next", "live_preview", "last_profile")


class BridgeError(RuntimeError):
    """Error whose message is safe to show in the interface."""


def _host(url: str) -> str:
    m = re.match(r"^(?:[a-z]+://)?([^/:?#@]+(?::\d+)?)", (url or "").strip(), re.I)
    return m.group(1) if m else ""


def _mask_mac(mac: str) -> str:
    mac = (mac or "").upper()
    return mac[:8] + ":••:••:" + mac[-2:] if MAC_RE.fullmatch(mac) else ""


class Bridge(QObject):
    reply = Signal(str)
    push = Signal(str)
    _to_gui = Signal(object)

    def __init__(self, host=None, adapter_factory=make_adapter, workers: int = 6):
        super().__init__()
        self.host = host
        self.adapter_factory = adapter_factory
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="us-bridge")
        self.metadata_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="us-tmdb")
        self.catalog_request = 0
        self.preview_request = 0
        self.play_request = 0
        self.adapter = None
        self.profile: Profile | None = None
        self.source_key = ""
        self.generation = 0
        self.refs: dict[str, MediaItem] = {}
        self._episodes: list[MediaItem] = []
        self._refs_lock = threading.Lock()
        self.closing = False
        try:
            self.settings = load_settings()
        except Exception as exc:
            log.warning("Settings unavailable: %s", type(exc).__name__)
            self.settings = {}
        self._tmdb = None
        self._to_gui.connect(self._run_on_gui)

    # ------------------------------------------------------------------ plumbing
    @Slot(object)
    def _run_on_gui(self, fn):
        try:
            fn()
        except Exception as exc:  # never let a callback kill the event loop
            log.warning("Bridge GUI callback failed: %s", type(exc).__name__)

    def on_gui(self, fn):
        self._to_gui.emit(fn)

    def emit_event(self, kind: str, **data):
        data["type"] = kind
        self.push.emit(json.dumps(data, ensure_ascii=False))

    def _answer(self, rid, ok, payload):
        if self.closing:
            return
        body = {"id": rid, "ok": ok}
        body["data" if ok else "error"] = payload
        text = json.dumps(body, ensure_ascii=False, default=str)
        self.on_gui(lambda: self.reply.emit(text))

    @Slot(str)
    def call(self, message: str):
        try:
            msg = json.loads(message)
            rid = msg.get("id")
            name = str(msg.get("method") or "")
            args = msg.get("args") or []
            if not isinstance(args, list):
                return
        except Exception:
            return
        fn = getattr(self, "api_" + name, None)
        if not callable(fn) or not re.fullmatch(r"[a-z_]+", name):
            self._answer(rid, False, "Unknown action")
            return
        if name.startswith("ui_"):
            # Interface actions touch Qt widgets: run them right here.
            try:
                self._answer(rid, True, fn(*args))
            except Exception as exc:
                self._answer(rid, False, self._safe_error(exc))
            return

        if name in ("items", "preview", "play"):
            counter = {"items": "catalog_request", "preview": "preview_request", "play": "play_request"}[name]
            request = getattr(self, counter) + 1
            setattr(self, counter, request)
            if name == "play" and len(args) == 1:
                args.append(False)
            if name == "items" and len(args) == 1:
                args.append("")
            args.append(request)

        def task():
            try:
                self._answer(rid, True, fn(*args))
            except Exception as exc:
                self._answer(rid, False, self._safe_error(exc))

        pool = self.metadata_pool if name in ("poster", "details") else self.pool
        pool.submit(task)

    @staticmethod
    def _safe_error(exc) -> str:
        if isinstance(exc, (BridgeError, cloud_catalog.CatalogError)):
            return str(exc)
        text = sanitize_text(str(exc) or "").strip()
        log.warning("Bridge action failed: %s", type(exc).__name__)
        return text[:300] or type(exc).__name__

    def shutdown(self):
        self.closing = True
        self.generation += 1
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.metadata_pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ items
    def _ref(self, item: MediaItem) -> str:
        material = "\x1f".join([
            self.source_key, item.kind or "", item.id or "", item.series_id or "",
            str(item.season or ""), str(item.episode or ""), item.title or "",
        ])
        ref = hashlib.sha1(material.encode("utf-8", "surrogatepass")).hexdigest()[:20]
        with self._refs_lock:
            self.refs[ref] = item
        return ref

    def item(self, ref) -> MediaItem:
        with self._refs_lock:
            it = self.refs.get(str(ref or ""))
        if it is None:
            raise BridgeError("This item is no longer available. Open the list again.")
        return it

    def view(self, item: MediaItem, **extra) -> dict:
        raw = item.raw or {}
        out = {
            "ref": self._ref(item),
            "title": item.title,
            "kind": item.kind,
            "poster": item.poster if item.poster.startswith(("http://", "https://")) else "",
            "backdrop": item.backdrop if (item.backdrop or "").startswith(("http://", "https://")) else "",
            "year": (item.year or "")[:4],
            "rating": self._rating(item.rating),
            "description": (item.description or "")[:900],
        }
        alts = [u for u in (raw.get("_poster_alts") or []) if isinstance(u, str) and u.startswith(("http://", "https://"))]
        if alts and out["poster"]:
            out["poster_alt"] = alts[0]
        if item.season is not None:
            out["season"] = item.season
        if item.episode is not None:
            out["episode"] = item.episode
        num = raw.get("number") or raw.get("num")
        if item.kind == "live" and num:
            out["number"] = str(num)
        if item.kind == "live":
            out["epg"] = bool(raw.get("epg_channel_id") or raw.get("xmltv_id") or raw.get("tv_archive") or raw.get("use_http_tmp_link") is not None)
            out["archive"] = str(raw.get("tv_archive") or raw.get("archive") or "") in ("1", "true", "True")
        out.update(extra)
        return out

    @staticmethod
    def _rating(value) -> str:
        try:
            v = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return ""
        if v <= 0:
            return ""
        if v > 10:
            v = v / 10.0
        return f"{v:.1f}"

    def _require(self):
        if not self.adapter:
            raise BridgeError("Connect to a source first.")
        return self.adapter, self.generation

    def _cancelled(self, generation):
        return lambda: self.closing or generation != self.generation

    # ------------------------------------------------------------------ app
    def artwork_context(self, url):
        adapter = self.adapter
        inner = getattr(adapter, "inner", adapter)
        source = self.source_key
        if inner is None or not hasattr(inner, "_headers") or not hasattr(inner, "base"):
            return None, ""
        try:
            target, portal = urlsplit(url), urlsplit(inner.base)
            if target.username is not None:
                return None, ""
            target_origin = (target.scheme, target.hostname, target.port or (443 if target.scheme == "https" else 80))
            portal_origin = (portal.scheme, portal.hostname, portal.port or (443 if portal.scheme == "https" else 80))
            if target_origin == portal_origin:
                return inner._headers(), source
        except ValueError:
            pass
        return None, ""

    def api_hello(self):
        return {
            "version": __version__,
            "author": AUTHOR,
            "settings": {k: self.settings.get(k) for k in UI_SETTINGS},
            "has_tmdb_key": bool(self.settings.get("tmdb_api_key")),
            "profiles": self.api_profiles(),
            "connected": self._connected_view(),
        }

    def _connected_view(self):
        if not self.profile:
            return None
        return {"name": self.profile.name, "type": self.profile.source_type,
                "host": _host(self.profile.m3u_url or self.profile.portal_url)}

    # ------------------------------------------------------------------ profiles
    def api_profiles(self):
        out = []
        for p in load_profiles():
            out.append({
                "name": p.name,
                "type": p.source_type,
                "host": _host(p.m3u_url or p.portal_url),
                "mac": _mask_mac(p.mac) if p.source_type == "stalker" else "",
                "user": p.username if p.source_type == "xtream" else "",
                "active": bool(self.profile and self.profile.name == p.name),
            })
        return out

    def _find_profile(self, name) -> Profile:
        for p in load_profiles():
            if p.name == name:
                return p
        raise BridgeError("Profile not found.")

    def api_profile(self, name):
        p = self._find_profile(name)
        return {"name": p.name, "type": p.source_type, "url": p.m3u_url or p.portal_url,
                "mac": p.mac, "username": p.username, "has_password": bool(p.password)}

    def _profile_from(self, data: dict) -> Profile:
        t = str(data.get("type") or "stalker").lower()
        if t not in ("stalker", "xtream", "m3u"):
            raise BridgeError("Choose Stalker, Xtream or M3U.")
        name = str(data.get("name") or "").strip()[:60]
        url = str(data.get("url") or "").strip()
        mac = str(data.get("mac") or "").strip().upper()
        user = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        if not url:
            raise BridgeError("The portal / server address is required.")
        if t == "stalker" and not MAC_RE.fullmatch(mac):
            raise BridgeError("Enter a valid MAC address, for example 00:1A:79:XX:XX:XX.")
        if t == "xtream" and not user:
            raise BridgeError("Xtream needs a username and password.")
        original = str(data.get("original") or "").strip()
        if t == "xtream" and not password and (original or name):
            try:
                password = self._find_profile(original or name).password
            except BridgeError:
                password = ""
        if t == "xtream" and not password:
            raise BridgeError("Xtream needs a username and password.")
        return Profile(name or _host(url) or "Source", t, url, mac if t == "stalker" else "",
                       user if t == "xtream" else "", password if t == "xtream" else "",
                       url if t == "m3u" else "")

    def api_profile_save(self, data, connect=True):
        p = self._profile_from(dict(data or {}))
        original = str((data or {}).get("original") or "").strip()
        result = {"saved": False, "connected": None}
        if connect:
            result["connected"] = self._connect(p)
        try:
            save_profile(p)
            if original and original != p.name:
                delete_profile(original)
            result["saved"] = True
        except Exception as exc:
            log.warning("Profile save failed: %s", type(exc).__name__)
            result["save_error"] = "Connected for this session only — the profile could not be saved securely."
        result["profiles"] = self.api_profiles()
        return result

    def api_profile_delete(self, name):
        delete_profile(str(name))
        if self.profile and self.profile.name == name:
            self.api_disconnect()
        return self.api_profiles()

    # ------------------------------------------------------------------ connection
    def api_cloud_page(self, kind, server=None, after=None):
        return cloud_catalog.page(kind, server, after)

    def api_cloud_connect(self, kind, server, account, label):
        profile = cloud_catalog.profile(kind, server, account, label)
        return self._connect(profile, remember_profile=False)

    def _connect(self, p: Profile, *, remember_profile=True):
        adapter = self.adapter_factory(p)
        self.generation += 1
        generation = self.generation
        adapter.connect()
        if generation != self.generation:
            raise BridgeError("A newer connection replaced this one.")
        if self.host is not None:
            self.on_gui(lambda: generation == self.generation and self.host.stop_playback(silent=True))
        self.adapter, self.profile, self.source_key = adapter, p, profile_identity(p)
        with self._refs_lock:
            self.refs.clear()
        self._episodes = []
        if remember_profile and self.settings.get("last_profile") != p.name:
            try:
                merged = dict(self.settings, last_profile=p.name)
                save_settings(merged)
                self.settings = merged
            except Exception as exc:
                log.debug("Could not remember last source: %s", type(exc).__name__)
        return self._connected_view()

    def api_connect(self, name):
        return self._connect(self._find_profile(name))

    def api_disconnect(self):
        self.generation += 1
        if self.host is not None:
            self.on_gui(lambda: self.host.stop_playback(silent=True))
        self.adapter = self.profile = None
        self.source_key = ""
        with self._refs_lock:
            self.refs.clear()
        self._episodes = []
        return True

    # ------------------------------------------------------------------ catalog
    def api_categories(self, kind):
        if kind not in KINDS:
            raise BridgeError("Unknown section.")
        adapter, gen = self._require()
        rows = adapter.categories(kind, cancelled=self._cancelled(gen))
        return [{"id": c.id, "title": c.title} for c in rows if c.title]

    def api_items(self, kind, category_id="", request=None):
        if kind not in KINDS:
            raise BridgeError("Unknown section.")
        adapter, gen = self._require()
        cancelled = lambda: self._cancelled(gen)() or (request is not None and request != self.catalog_request)
        rows = adapter.items(kind, str(category_id or ""), cancelled=cancelled)
        if cancelled():
            raise BridgeError("Catalog request replaced.")
        return [self.view(x) for x in rows]

    def api_episodes(self, ref):
        series = self.item(ref)
        adapter, gen = self._require()
        rows = adapter.series_episodes(series, cancelled=self._cancelled(gen))
        try:
            watched = db.next_episode(self.source_key, series.id)
        except Exception:
            watched = set()
        rows.sort(key=lambda x: ((x.season or 0), (x.episode or 0), x.title.casefold()))
        self._episodes = list(rows)
        seasons: dict[int, list] = {}
        for x in rows:
            seasons.setdefault(int(x.season or 1), []).append(
                self.view(x, watched=db.episode_tracking_key(x) in watched))
        nxt = next((e["ref"] for s in sorted(seasons) for e in seasons[s] if not e["watched"]), None)
        return {"seasons": [{"season": s, "episodes": seasons[s]} for s in sorted(seasons)], "next": nxt}

    def api_epg(self, ref):
        item = self.item(ref)
        adapter, gen = self._require()
        try:
            rows = adapter.short_epg(item, cancelled=self._cancelled(gen))
        except Exception as exc:
            log.debug("EPG unavailable: %s", type(exc).__name__)
            rows = []
        return {"now": int(time.time()), "rows": rows}

    def _tmdb_client(self):
        from ultrastalker_desktop.core.tmdb import RichTMDb
        from ultrastalker_desktop.core.builtin_credentials import builtin_api_credentials

        key = (self.settings.get("tmdb_api_key") or "").strip() or builtin_api_credentials().get("TMDB_API_KEY", "")
        lang = self.settings.get("tmdb_language") or self.settings.get("ui_language") or "ar"
        if self._tmdb is None or self._tmdb.key != key or self._tmdb.language != lang[:2]:
            self._tmdb = RichTMDb(key, lang)
        return self._tmdb

    def api_poster(self, ref):
        item = self.item(ref)
        if item.kind == "live":
            return ""
        tmdb_id = str((item.raw or {}).get("tmdb_id") or (item.raw or {}).get("tmdb") or "")
        return self._tmdb_client().poster(item.title, item.kind, item.year, tmdb_id if tmdb_id.isdigit() else "")

    def api_details(self, ref):
        item = self.item(ref)
        base = self.view(item)
        if item.kind == "live":
            return base
        tmdb_id = str((item.raw or {}).get("tmdb_id") or (item.raw or {}).get("tmdb") or "")
        meta = self._tmdb_client().lookup(item.title, "series" if item.kind in ("series", "episode") else "movies",
                                          item.year, tmdb_id if tmdb_id.isdigit() else "")
        if meta:
            base["tmdb"] = meta
            if meta.get("poster"):
                if base["poster"] and base["poster"] != meta["poster"]:
                    base["poster_alt"] = base["poster"]
                base["poster"] = meta["poster"]
            base["backdrop"] = meta.get("backdrop") or base["backdrop"]
            if not base["description"]:
                base["description"] = meta.get("overview", "")
            base["rating"] = base["rating"] or (f"{meta['rating']:.1f}" if meta.get("rating") else "")
            base["year"] = base["year"] or meta.get("year", "")
        try:
            base["favorite"] = self._is_favorite(item)
            pos, dur = db.resume_point(self.source_key, item)
            if dur and 30 < pos < dur - 60:
                base["resume"] = {"position": pos, "duration": dur, "label": db.history_progress_label(pos, dur)}
        except Exception:
            pass
        return base

    def api_search(self, query):
        q = str(query or "").strip().casefold()
        if len(q) < 2:
            return {k: [] for k in KINDS}
        adapter, gen = self._require()
        out = {}
        for kind in KINDS:
            try:
                rows = adapter.items(kind, "", cancelled=self._cancelled(gen))
            except Exception as exc:
                log.debug("Search skipped %s: %s", kind, type(exc).__name__)
                rows = []
            hits = [x for x in rows if q in (x.title or "").casefold()]
            hits.sort(key=lambda x: (not x.title.casefold().startswith(q), len(x.title)))
            out[kind] = [self.view(x) for x in hits[:60]]
        return out

    # ------------------------------------------------------------------ library
    def _is_favorite(self, item):
        key = db.media_key(item)
        return any(db.media_key(x) == key for x in db.favorites(self.source_key))

    def api_favorite(self, ref):
        self._require()
        return {"favorite": bool(db.toggle_favorite(self.source_key, self.item(ref)))}

    def api_favorites(self):
        self._require()
        out = {k: [] for k in KINDS}
        for x in db.favorites(self.source_key):
            out.setdefault(x.kind if x.kind in KINDS else "movies", []).append(self.view(x))
        return out

    def api_history(self, limit=40):
        self._require()
        out = []
        for item, pos, dur in db.history(self.source_key, int(limit)):
            pct = int(100 * pos / dur) if dur else 0
            out.append(self.view(item, position=pos, duration=dur, percent=max(0, min(100, pct)),
                                 progress=db.history_progress_label(pos, dur)))
        return out

    # ------------------------------------------------------------------ settings
    def api_settings_save(self, data):
        data = dict(data or {})
        merged = dict(self.settings)
        for k in UI_SETTINGS:
            if k in data:
                merged[k] = data[k]
        if "tmdb_api_key" in data:
            merged["tmdb_api_key"] = str(data.get("tmdb_api_key") or "").strip()
        save_settings(merged)
        self.settings = merged
        if any(k in data for k in ("tmdb_api_key", "tmdb_language", "ui_language")):
            self._tmdb = None
        return {k: merged.get(k) for k in UI_SETTINGS} | {"has_tmdb_key": bool(merged.get("tmdb_api_key"))}

    def api_clear_cache(self):
        """Forget saved catalog lists (all sources) and the page's image cache."""
        try:
            db.cache_delete_prefix("")
        except Exception as exc:
            log.warning("Cache clear failed: %s", type(exc).__name__)
        if self.host is not None:
            self.on_gui(lambda: self.host.clear_web_cache())
        return True

    # ------------------------------------------------------------------ playback
    def api_play(self, ref, from_start=False, request=None):
        item = self.item(ref)
        adapter, gen = self._require()
        source_key = self.source_key
        cancelled = lambda: self._cancelled(gen)() or (request is not None and request != self.play_request)
        if item.kind == "series":
            raise BridgeError("Choose an episode first.")
        start = 0.0
        dur = 0.0
        if not from_start and item.kind != "live":
            try:
                pos, dur = db.resume_point(source_key, item)
                if dur and 30 < pos < dur - 60:
                    start = pos
            except Exception:
                pass
        urls = adapter.stream_candidates(item, cancelled=cancelled)
        if cancelled():
            return {"started": False}
        if not urls:
            raise BridgeError("The source returned no playable link for this item.")
        try:
            db.add_history(source_key, item, start, dur)
        except Exception as exc:
            log.warning("History unavailable: %s", type(exc).__name__)
        view = self.view(item)
        if self.host is not None:
            self.on_gui(lambda: not cancelled() and self.host.start_playback(item, view, urls, start, source_key))
        return {"started": True, "title": item.title}

    def play_next_episode(self, item: MediaItem):
        """Called by the player when an episode ends: start the following one."""
        if self.settings.get("autoplay_next") is False or not self._episodes:
            return
        key = db.media_key(item)
        idx = next((i for i, x in enumerate(self._episodes) if db.media_key(x) == key), None)
        if idx is None or idx + 1 >= len(self._episodes):
            return
        ref = self._ref(self._episodes[idx + 1])

        def task():
            try:
                self.api_play(ref, True)
                self.emit_event("toast", message=self._episodes[idx + 1].title)
            except Exception as exc:
                message = self._safe_error(exc)
                self.on_gui(lambda: self.emit_event("toast", message=message, error=True))

        self.pool.submit(task)

    def api_preview(self, ref, rect, request=None):
        """Live preview inside column 3; rect is the video box in CSS pixels."""
        item = self.item(ref)
        adapter, gen = self._require()
        cancelled = lambda: self._cancelled(gen)() or (request is not None and request != self.preview_request)
        urls = adapter.stream_candidates(item, cancelled=cancelled)
        if cancelled():
            return {"started": False}
        if not urls:
            raise BridgeError("The source returned no playable link for this channel.")
        view = self.view(item)
        if self.host is not None and gen == self.generation:
            self.on_gui(lambda: not cancelled() and self.host.start_preview(item, view, urls, rect))
        return {"started": True}

    def api_ui_preview_rect(self, rect):
        if self.host is not None:
            self.host.move_preview(rect)
        return True

    def api_ui_stop_preview(self):
        self.preview_request += 1
        if self.host is not None:
            self.host.stop_preview()
        return True

    def api_ui_fullscreen(self):
        if self.host is not None:
            return self.host.toggle_window_fullscreen()
        return False

    def api_ui_open_url(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        url = str(url or "")
        if url.startswith("https://www.youtube.com/watch?v="):
            QDesktopServices.openUrl(QUrl(url))
            return True
        return False

    def api_ui_minimize(self):
        if self.host is not None:
            self.host.showMinimized()
        return True

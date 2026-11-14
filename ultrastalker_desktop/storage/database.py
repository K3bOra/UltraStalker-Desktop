from __future__ import annotations

from pathlib import Path
from contextlib import closing
import json
import os
import sqlite3
import threading
import time

from ultrastalker_desktop.core.models import MediaItem, media_snapshot

APP_DIR = Path(os.getenv("APPDATA") or (Path.home() / ".ultrastalker")) / "UltraStalker"
DB = APP_DIR / "ultrastalker.db"
SCHEMA_VERSION = 1
_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DBS: set[str] = set()
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS favorites(
    source TEXT,
    item_id TEXT,
    title TEXT,
    kind TEXT,
    payload TEXT,
    PRIMARY KEY(source,item_id)
);
CREATE TABLE IF NOT EXISTS history(
    source TEXT,
    item_id TEXT,
    title TEXT,
    kind TEXT,
    position REAL DEFAULT 0,
    duration REAL DEFAULT 0,
    watched_at REAL,
    payload TEXT,
    PRIMARY KEY(source,item_id)
);
CREATE TABLE IF NOT EXISTS cache(
    key TEXT PRIMARY KEY,
    payload TEXT,
    expires REAL
);
CREATE INDEX IF NOT EXISTS idx_history_source_watched
    ON history(source, watched_at DESC);
CREATE INDEX IF NOT EXISTS idx_cache_expires
    ON cache(expires);
"""


def _database_identity() -> str:
    return str(Path(DB).resolve(strict=False))


def _ensure_schema(c, identity: str) -> None:
    with _SCHEMA_LOCK:
        if identity in _INITIALIZED_DBS:
            return
        current_version = int(c.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SCHEMA_VERSION:
            raise sqlite3.DatabaseError(
                f"Database schema version {current_version} is newer than supported version {SCHEMA_VERSION}."
            )
        # journal_mode is persistent for the database and may require a write
        # lock. Do it once per DB/process rather than on every History/Favorite
        # read. Schema DDL likewise belongs to initialization, not hot paths.
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(_SCHEMA_SQL)
        if current_version < SCHEMA_VERSION:
            # v1 establishes the baseline schema. Future versions must add
            # explicit migration steps before raising SCHEMA_VERSION.
            c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        # Cache entries are disposable. Prune expired rows once per process/DB
        # at initialization so a read-heavy session does not retain old cache
        # forever merely because no new cache_set happens.
        c.execute("delete from cache where expires<?", (time.time(),))
        # Finish initialization before publishing the in-process initialized
        # marker. If schema/pruning/commit fails, the next connection retries.
        c.commit()
        _INITIALIZED_DBS.add(identity)


def conn():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    identity = _database_identity()
    existed = Path(DB).exists()
    if not existed:
        # Recover cleanly if the DB was removed/recreated while this process is
        # alive instead of trusting an initialization record for a vanished file.
        with _SCHEMA_LOCK:
            _INITIALIZED_DBS.discard(identity)
    c = sqlite3.connect(DB, timeout=5.0)
    try:
        c.row_factory = sqlite3.Row
        # These are connection-local and intentionally remain on every handle.
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=5000")
        _ensure_schema(c, identity)
        return c
    except Exception:
        c.close()
        raise


def integrity_check(path: Path | str | None = None) -> tuple[bool, str, str | None]:
    """Read-only SQLite quick-check for diagnostics.

    Missing database files are a valid first-run state. The helper never calls
    ``conn()`` so it cannot create schema, prune cache, or otherwise mutate the
    user's database while support diagnostics are being collected.
    """
    db_path = Path(path) if path is not None else Path(DB)
    if not db_path.exists():
        return True, "not_created", None
    try:
        with closing(sqlite3.connect(str(db_path), timeout=5.0)) as c:
            c.execute("PRAGMA query_only=ON")
            rows = c.execute("PRAGMA quick_check").fetchall()
        messages = [str(row[0]) for row in rows if row]
        if messages and all(message.lower() == "ok" for message in messages):
            return True, "ok", None
        return False, "corrupt", "; ".join(messages[:5]) or "quick_check returned no result"
    except Exception as exc:
        return False, "error", str(exc) or type(exc).__name__


def media_key(item: MediaItem) -> str:
    """Stable per-profile media key that avoids cross-kind/id collisions.

    Numbered episodes are keyed by parent series + season + episode. Some
    Stalker/Ministra portals reuse one container/movie id for every episode and
    vary only the ``series=`` index during ``create_link``. Using provider id
    alone would make one episode overwrite another in History/Favorites.
    Unnumbered episodes still fall back to the provider id.
    """
    if item.kind == "episode" and item.series_id:
        if item.season is not None and item.episode is not None:
            return f"episode:{item.series_id}:se:{item.season}:{item.episode}"
        return f"episode:{item.series_id}:id:{item.id}"
    return f"{item.kind}:{item.id}"


def _legacy_media_key(item: MediaItem) -> str | None:
    """Return the pre-RC episode key used before S/E collision hardening."""
    if item.kind == "episode" and item.series_id:
        return f"episode:{item.series_id}:{item.id}"
    return None


def _migrate_legacy_episode_key(c, table: str, source: str, item: MediaItem) -> None:
    legacy = _legacy_media_key(item)
    current = media_key(item)
    if not legacy or legacy == current:
        return
    # Table name is internal/constant, never caller-controlled SQL. If a current
    # row already exists, discard the legacy duplicate; otherwise rename it in
    # place so timestamps/progress/favorite state survive development upgrades.
    if table not in {"history", "favorites"}:
        raise ValueError("Unsupported migration table")
    exists = c.execute(
        f"select 1 from {table} where source=? and item_id=?", (source, current)
    ).fetchone()
    if exists:
        c.execute(f"delete from {table} where source=? and item_id=?", (source, legacy))
    else:
        c.execute(
            f"update {table} set item_id=? where source=? and item_id=?",
            (current, source, legacy),
        )


def _payload(item):
    # Favorites/history are long-lived; shared snapshot sanitization removes
    # transport URLs/commands, signed artwork and opaque provider payloads.
    # Plain artwork links (no query string, no user info) are kept so the
    # Home shelves can show posters and channel logos.
    return json.dumps(media_snapshot(item, keep_safe_artwork=True), ensure_ascii=False)


def _recover_item_from_key(row) -> MediaItem:
    """Recover the minimum safe identity from a storage key.

    A malformed/legacy payload must never turn the composite database key into
    a provider ID.  Numbered episode keys carry enough information to rehydrate
    by series/season/episode; ordinary media keys carry the original provider ID.
    """
    key = str(row["item_id"] or "")
    title = str(row["title"] or "")
    kind = str(row["kind"] or "")
    prefix = f"{kind}:"

    if kind == "episode" and key.startswith("episode:"):
        rest = key[len("episode:"):]
        # Current key: episode:<series_id>:se:<season>:<episode>
        parts = rest.split(":")
        if len(parts) >= 4 and parts[-3] == "se":
            series_id = ":".join(parts[:-3])
            try:
                season = int(parts[-2])
                episode = int(parts[-1])
            except (TypeError, ValueError):
                season = episode = None
            if series_id and season is not None and episode is not None:
                return MediaItem(
                    "", title, "episode", series_id=series_id,
                    season=season, episode=episode,
                )
        # Current unnumbered key: episode:<series_id>:id:<provider_id>
        if ":id:" in rest:
            series_id, provider_id = rest.rsplit(":id:", 1)
            if series_id and provider_id:
                return MediaItem(provider_id, title, "episode", series_id=series_id)
        # Legacy key: episode:<series_id>:<provider_id>. Series/provider IDs in
        # supported adapters are opaque but do not use this storage delimiter.
        legacy = rest.rsplit(":", 1)
        if len(legacy) == 2 and all(legacy):
            return MediaItem(legacy[1], title, "episode", series_id=legacy[0])

    if key.startswith(prefix):
        provider_id = key[len(prefix):]
        if provider_id:
            return MediaItem(provider_id, title, kind)

    # Fail closed on identity: keep the row displayable, but use an empty ID so
    # adapters cannot mistake an opaque/composite storage key for a provider ID.
    return MediaItem("", title, kind)


def _item(row):
    try:
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict):
            raise ValueError("stored media payload is not an object")
        return MediaItem(**payload)
    except Exception:
        return _recover_item_from_key(row)


def _safe_float(value) -> float:
    try:
        number = float(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    # SQLite can contain NaN/inf values through external edits. Treat them as
    # unusable progress rather than letting them poison resume calculations/UI.
    import math
    return number if math.isfinite(number) else 0.0


def toggle_favorite(source, item):
    key = media_key(item)
    with closing(conn()) as c:
        _migrate_legacy_episode_key(c, "favorites", source, item)
        r = c.execute(
            "select 1 from favorites where source=? and item_id=?", (source, key)
        ).fetchone()
        if r:
            c.execute("delete from favorites where source=? and item_id=?", (source, key))
            value = False
        else:
            c.execute(
                "insert or replace into favorites values(?,?,?,?,?)",
                (source, key, item.title, item.kind, _payload(item)),
            )
            value = True
        c.commit()
        return value


def favorites(source):
    with closing(conn()) as c:
        rows = c.execute(
            "select * from favorites where source=? order by title collate nocase", (source,)
        ).fetchall()
    return [_item(x) for x in rows]


def add_history(source, item, position=0, duration=0):
    key = media_key(item)
    with closing(conn()) as c:
        _migrate_legacy_episode_key(c, "history", source, item)
        c.execute(
            "insert or replace into history values(?,?,?,?,?,?,?,?)",
            (
                source,
                key,
                item.title,
                item.kind,
                float(position or 0),
                float(duration or 0),
                time.time(),
                _payload(item),
            ),
        )
        c.commit()


def update_progress(source, item, position, duration):
    key = media_key(item) if isinstance(item, MediaItem) else str(item)
    with closing(conn()) as c:
        if isinstance(item, MediaItem):
            _migrate_legacy_episode_key(c, "history", source, item)
        c.execute(
            "update history set position=?,duration=?,watched_at=? where source=? and item_id=?",
            (float(position or 0), float(duration or 0), time.time(), source, key),
        )
        c.commit()


def history(source, limit=100):
    with closing(conn()) as c:
        rows = c.execute(
            "select * from history where source=? order by watched_at desc limit ?",
            (source, int(limit)),
        ).fetchall()
    return [(_item(x), _safe_float(x["position"]), _safe_float(x["duration"])) for x in rows]


def resume_point(source, item):
    key = media_key(item) if isinstance(item, MediaItem) else str(item)
    with closing(conn()) as c:
        r = c.execute(
            "select position,duration from history where source=? and item_id=?", (source, key)
        ).fetchone()
        if not r and isinstance(item, MediaItem):
            legacy = _legacy_media_key(item)
            if legacy and legacy != key:
                r = c.execute(
                    "select position,duration from history where source=? and item_id=?",
                    (source, legacy),
                ).fetchone()
    return (_safe_float(r["position"]), _safe_float(r["duration"])) if r else (0.0, 0.0)


def is_completed(position, duration) -> bool:
    """Return True when playback is far enough through to count as watched."""
    try:
        position = max(0.0, float(position or 0))
        duration = max(0.0, float(duration or 0))
    except (TypeError, ValueError):
        return False
    return (duration > 0 and position >= max(60.0, duration * 0.85)) or (
        duration <= 0 and position >= 20 * 60
    )


def _clock(seconds) -> str:
    try:
        total = max(0, int(float(seconds or 0)))
    except (TypeError, ValueError):
        total = 0
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def history_progress_label(position, duration) -> str:
    """Human-readable Continue Watching status used by the desktop UI."""
    try:
        position = max(0.0, float(position or 0))
        duration = max(0.0, float(duration or 0))
    except (TypeError, ValueError):
        position = duration = 0.0
    if position <= 0:
        return "Started"
    if duration > 0:
        pct = max(0, min(100, int(round((position / duration) * 100))))
        if is_completed(position, duration):
            return f"Watched • {pct}%"
        return f"Continue • {pct}% • {_clock(position)} / {_clock(duration)}"
    return f"Continue • {_clock(position)}"


def episode_tracking_key(item) -> str:
    """Stable completion key for a series episode.

    Season/episode numbers are preferred when both exist. Providers that omit
    numbering fall back to their stable episode ID so one unnumbered episode
    can never mark every other unnumbered episode as watched.
    """
    if isinstance(item, MediaItem):
        season, episode, item_id = item.season, item.episode, item.id
    else:
        item = item or {}
        season, episode, item_id = item.get("season"), item.get("episode"), item.get("id")
    if season is not None and episode is not None:
        return f"se:{season}:{episode}"
    return f"id:{item_id or ''}"

def watched_episodes(source, series_id):
    with closing(conn()) as c:
        rows = c.execute(
            "select position,duration,payload from history where source=? and kind='episode' order by watched_at desc",
            (source,),
        ).fetchall()
    watched = set()
    for row in rows:
        try:
            x = json.loads(row["payload"])
            if str(x.get("series_id") or "") != str(series_id):
                continue
            position = float(row["position"] or 0)
            duration = float(row["duration"] or 0)
            # Treat an episode as completed only near its end. If duration is
            # unavailable, require substantial viewing rather than a mere open.
            if is_completed(position, duration):
                watched.add(episode_tracking_key(x))
        except Exception:
            pass
    return watched


def next_episode(source, series_id):
    # Compatibility alias used by existing UI code.
    return watched_episodes(source, series_id)


def cache_delete_prefix(prefix):
    prefix = str(prefix)
    with closing(conn()) as c:
        # Prefixes are data, not SQL patterns. LIKE would treat % and _ inside a
        # namespace as wildcards and could delete unrelated cache rows.
        c.execute("delete from cache where substr(key,1,?)=?", (len(prefix), prefix))
        c.commit()


def cache_get(key):
    with closing(conn()) as c:
        r = c.execute("select payload,expires from cache where key=?", (key,)).fetchone()
        if not r:
            return None
        if float(r["expires"]) < time.time():
            c.execute("delete from cache where key=?", (key,))
            c.commit()
            return None
        try:
            return json.loads(r["payload"])
        except Exception:
            # Corrupt/legacy cache rows are disposable. Remove them immediately so
            # every subsequent read does not repeat the same decode failure.
            c.execute("delete from cache where key=?", (key,))
            c.commit()
            return None


def cache_delete(key):
    with closing(conn()) as c:
        c.execute("delete from cache where key=?", (str(key),))
        c.commit()


def cache_set(key, value, ttl=300):
    with closing(conn()) as c:
        c.execute("delete from cache where expires<?", (time.time(),))
        c.execute(
            "insert or replace into cache values(?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl),
        )
        c.commit()

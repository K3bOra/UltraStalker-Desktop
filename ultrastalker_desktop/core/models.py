from dataclasses import dataclass, field
from typing import Any
import hashlib
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

@dataclass
class Profile:
    name: str
    source_type: str = "stalker"
    portal_url: str = ""
    mac: str = ""
    username: str = ""
    password: str = ""
    m3u_url: str = ""

@dataclass
class Category:
    id: str
    title: str
    kind: str
    raw: dict[str, Any] = field(default_factory=dict)

@dataclass
class MediaItem:
    id: str
    title: str
    kind: str
    category_id: str = ""
    stream_url: str = ""
    command: str = ""
    poster: str = ""
    description: str = ""
    year: str = ""
    rating: str = ""
    series_id: str = ""
    season: int | None = None
    episode: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    backdrop: str = ""


_M3U_VOLATILE_QUERY_KEYS = {
    "password", "passwd", "pass", "token", "key", "api_key", "apikey",
    "auth", "authorization", "signature", "sig", "expires", "expiry", "exp",
}


def _canonical_endpoint(source: str, value: str) -> str:
    """Canonical endpoint used only for opaque local state identity.

    It deliberately removes known rotating M3U secret query parameters and
    normalizes common Stalker entry-point aliases so the same source does not
    lose Favorites/History merely because the user pasted another equivalent URL.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "http://" + raw
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.rstrip("/")

    scheme = (parts.scheme or "http").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    path = parts.path.rstrip("/")

    if source == "stalker":
        lower = path.lower()
        for suffix in ("/portal.php", "/server/load.php", "/c"):
            if lower.endswith(suffix):
                path = path[:-len(suffix)].rstrip("/")
                break
        query = ""
    elif source == "xtream":
        if path.lower().endswith("/player_api.php"):
            path = path[:-len("/player_api.php")].rstrip("/")
        query = ""
    elif source == "m3u":
        # Keep account/source-discriminating non-secret parameters (e.g. username,
        # type/output) while discarding rotating or credential query values.
        safe_pairs = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.casefold() not in _M3U_VOLATILE_QUERY_KEYS
        ]
        query = urlencode(sorted(safe_pairs), doseq=True)
    else:
        query = parts.query

    return urlunsplit((scheme, host, path, query, ""))


def profile_identity(profile: Profile) -> str:
    """Opaque state/cache identity; never exposes credentials in storage keys."""
    source = (profile.source_type or "").strip().lower()
    endpoint = _canonical_endpoint(source, profile.m3u_url or profile.portal_url)
    material = "\x1f".join([
        source,
        endpoint,
        (profile.mac or "").strip().upper(),
        (profile.username or "").strip(),
    ]).encode("utf-8", "surrogatepass")
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f"{source}:{digest}"


_SAFE_PROVIDER_RAW_KEYS = {
    "id", "ch_id", "movie_id", "stream_id", "series_id", "episode_id",
    "episode_num", "season", "category_id", "container_extension",
    "container_ext",
}


def safe_artwork_url(value: str) -> str:
    """Return only cache-safe remote artwork URLs.

    Provider artwork URLs with query strings/user-info can carry signed tokens
    or account identifiers. Those are intentionally not persisted to SQLite.
    The live in-memory item may still use them during the current session.
    """
    raw = str(value or "").strip()
    if not raw or len(raw) > 4096:
        return ""
    try:
        parts = urlsplit(raw)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"}:
        return ""
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    return raw


def media_snapshot(item: MediaItem, *, keep_safe_artwork: bool = False) -> dict[str, Any]:
    """Serialize display/state metadata without transport secrets.

    This is shared by the short-lived catalog cache and long-lived
    Favorites/History so neither path accidentally persists stream commands,
    signed URLs, provider tokens, or opaque raw payloads.
    """
    data = dict(item.__dict__)
    data["stream_url"] = ""
    data["command"] = ""
    if keep_safe_artwork:
        data["poster"] = safe_artwork_url(data.get("poster", ""))
        data["backdrop"] = safe_artwork_url(data.get("backdrop", ""))
    else:
        data["poster"] = ""
        data["backdrop"] = ""
    raw = dict(item.raw or {})
    data["raw"] = {key: raw[key] for key in _SAFE_PROVIDER_RAW_KEYS if key in raw}
    return data

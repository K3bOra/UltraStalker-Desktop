from __future__ import annotations

import logging
import threading

from ultrastalker_desktop.storage.database import cache_get, cache_set
from ultrastalker_desktop.core.http import make_session, request_timeout

_MISS = {"_ultrastalker_tmdb_miss": True}


class TMDbClient:
    def __init__(self, api_key=""):
        self.key = (api_key or "").strip()
        self.http = make_session(retries=1)
        self._request_lock = threading.RLock()

    def search(self, title, kind="movies", year=""):
        if not self.key or not title:
            return None
        cache_key = "tmdb:" + kind + ":" + title.lower() + ":" + str(year)
        cached = cache_get(cache_key)
        if isinstance(cached, dict) and cached.get("_ultrastalker_tmdb_miss") is True:
            return None
        if cached is not None:
            return cached

        typ = "tv" if kind in ("series", "episode") else "movie"
        params = {"api_key": self.key, "query": title}
        if year and str(year).isdigit():
            params["first_air_date_year" if typ == "tv" else "year"] = year
        try:
            with self._request_lock:
                r = self.http.get(
                    "https://api.themoviedb.org/3/search/" + typ,
                    params=params,
                    timeout=request_timeout(8, 4),
                )
                r.raise_for_status()
                rows = r.json().get("results", [])
                x = rows[0] if rows else None
            if x:
                x = {
                    "poster": "https://image.tmdb.org/t/p/w500" + x["poster_path"] if x.get("poster_path") else "",
                    "backdrop": "https://image.tmdb.org/t/p/w780" + x["backdrop_path"] if x.get("backdrop_path") else "",
                    "rating": x.get("vote_average"),
                    "description": x.get("overview") or "",
                    "year": str(x.get("release_date") or x.get("first_air_date") or "")[:4],
                }
                cache_set(cache_key, x, 86400)
                return x

            # Cache a negative result explicitly. cache_get(None) is also the
            # miss signal used by the generic cache API, so storing JSON null
            # would otherwise cause identical no-result searches to hit TMDb
            # repeatedly while navigating the same title.
            cache_set(cache_key, dict(_MISS), 86400)
            return None
        except Exception as exc:
            # TMDb is optional enrichment. Log only the exception type because
            # request errors may contain the API-key-bearing URL.
            logging.getLogger(__name__).debug(
                "TMDb enrichment failed: %s", type(exc).__name__
            )
            return None


_IMG = "https://image.tmdb.org/t/p/"
_TITLE_NOISE = None


def clean_title(title: str) -> tuple[str, str]:
    """Strip provider decorations ("EN| Title (2019) 4K [MULTI]") -> (title, year)."""
    import re

    global _TITLE_NOISE
    if _TITLE_NOISE is None:
        _TITLE_NOISE = re.compile(
            r"\b(4k|uhd|fhd|hd|sd|hevc|x26[45]|h\.?26[45]|1080p|720p|2160p|multi|vostfr|dubbed|subbed|"
            r"multi[- ]?sub|dolby|vision|atmos|hdr10?\+?|web[- ]?dl|bluray|remux|imax)\b",
            re.I,
        )
    raw = str(title or "")
    raw = re.sub(r"^\s*[A-Z0-9]{2,4}\s*[|:\-]\s*", "", raw)  # "EN| " / "AR - " / "4K| "
    raw = _TITLE_NOISE.sub(" ", raw)
    year = ""
    m = re.search(r"[\(\[]\s*(19[3-9]\d|20[0-2]\d)\s*[\)\]]", raw) or re.search(r"(?:^|\s|-)(19[3-9]\d|20[0-2]\d)\s*$", raw)
    if m:
        year = m.group(1)
        raw = raw[: m.start()] + " " + raw[m.end():]
    raw = re.sub(r"[\[\(][^\]\)]*[\]\)]", " ", raw)
    raw = re.sub(r"\s*[|•]\s*.*$", "", raw)
    raw = re.sub(r"\s{2,}", " ", raw).strip(" -_.:|")
    return raw or str(title or "").strip(), year


class RichTMDb:
    """Details used by the cinematic screens: backdrop, logo, cast, genres, trailer.

    Optional enrichment only: every failure returns None and nothing that
    carries the API key is ever logged.
    """

    def __init__(self, api_key: str = "", language: str = "en"):
        self.key = (api_key or "").strip()
        self.language = (language or "en")[:2]
        self.http = make_session(retries=1)
        self._lock = threading.RLock()

    def _get(self, path, **params):
        params["api_key"] = self.key
        with self._lock:
            r = self.http.get("https://api.themoviedb.org/3" + path, params=params, timeout=request_timeout(8, 4))
        r.raise_for_status()
        return r.json()

    def lookup(self, title: str, kind: str = "movies", year: str = "", tmdb_id: str = ""):
        if not self.key or not (title or tmdb_id):
            return None
        typ = "tv" if kind in ("series", "episode") else "movie"
        name, guessed_year = clean_title(title)
        year = str(year or guessed_year or "")[:4]
        cache_key = f"tmdb2:{typ}:{self.language}:{tmdb_id or name.lower()}:{year}"
        cached = cache_get(cache_key)
        if isinstance(cached, dict):
            return None if cached.get("_ultrastalker_tmdb_miss") else cached
        try:
            tid = str(tmdb_id or "").strip()
            if not tid:
                params = {"query": name, "include_adult": "false", "language": self.language}
                if year.isdigit():
                    params["first_air_date_year" if typ == "tv" else "year"] = year
                rows = self._get("/search/" + typ, **params).get("results") or []
                if not rows and year:
                    params.pop("first_air_date_year", None); params.pop("year", None)
                    rows = self._get("/search/" + typ, **params).get("results") or []
                if not rows:
                    cache_set(cache_key, dict(_MISS), 86400)
                    return None
                tid = str(rows[0].get("id"))
            d = self._get(
                f"/{typ}/{tid}",
                language=self.language,
                append_to_response="credits,images,videos,release_dates,content_ratings",
                include_image_language=f"{self.language},en,null",
                include_video_language=f"{self.language},en,null",
            )
            overview = d.get("overview") or ""
            if not overview and self.language != "en":
                try:
                    overview = self._get(f"/{typ}/{tid}", language="en").get("overview") or ""
                except Exception:
                    overview = ""
            logos = (d.get("images") or {}).get("logos") or []
            logos.sort(key=lambda x: (x.get("iso_639_1") not in (self.language, "en"), -(x.get("vote_average") or 0)))
            logo = next((x.get("file_path") for x in logos if str(x.get("file_path", "")).endswith(".png")), "") or (logos[0].get("file_path") if logos else "")
            vids = [v for v in (d.get("videos") or {}).get("results") or [] if v.get("site") == "YouTube"]
            vids.sort(key=lambda v: (v.get("type") != "Trailer", not v.get("official")))
            cast = []
            for c in ((d.get("credits") or {}).get("cast") or [])[:12]:
                cast.append({
                    "name": c.get("name") or "",
                    "role": c.get("character") or "",
                    "photo": (_IMG + "w185" + c["profile_path"]) if c.get("profile_path") else "",
                })
            cert = ""
            if typ == "movie":
                for r in (d.get("release_dates") or {}).get("results") or []:
                    if r.get("iso_3166_1") in ("US", "GB", "EG"):
                        cert = next((x.get("certification") for x in r.get("release_dates") or [] if x.get("certification")), "")
                        if cert:
                            break
            else:
                cert = next((r.get("rating") for r in (d.get("content_ratings") or {}).get("results") or [] if r.get("iso_3166_1") in ("US", "GB") and r.get("rating")), "")
            out = {
                "tmdb_id": tid,
                "type": typ,
                "title": d.get("title") or d.get("name") or name,
                "original_title": d.get("original_title") or d.get("original_name") or "",
                "tagline": d.get("tagline") or "",
                "overview": overview,
                "year": str(d.get("release_date") or d.get("first_air_date") or "")[:4],
                "rating": round(float(d.get("vote_average") or 0), 1),
                "votes": int(d.get("vote_count") or 0),
                "runtime": int(d.get("runtime") or ((d.get("episode_run_time") or [0])[0] if d.get("episode_run_time") else 0) or 0),
                "genres": [g.get("name") for g in d.get("genres") or [] if g.get("name")][:4],
                "countries": [c.get("name") for c in d.get("production_countries") or [] if c.get("name")][:2]
                or list(d.get("origin_country") or [])[:2],
                "language": (d.get("original_language") or "").upper(),
                "seasons": int(d.get("number_of_seasons") or 0),
                "episodes": int(d.get("number_of_episodes") or 0),
                "certification": cert,
                "poster": (_IMG + "w500" + d["poster_path"]) if d.get("poster_path") else "",
                "backdrop": (_IMG + "w1280" + d["backdrop_path"]) if d.get("backdrop_path") else "",
                "logo": (_IMG + "w500" + logo) if logo else "",
                "trailer": ("https://www.youtube.com/watch?v=" + vids[0]["key"]) if vids else "",
                "cast": cast,
            }
            cache_set(cache_key, out, 7 * 86400)
            return out
        except Exception as exc:
            logging.getLogger(__name__).debug("TMDb details failed: %s", type(exc).__name__)
            return None

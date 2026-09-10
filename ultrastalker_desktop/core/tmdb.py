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

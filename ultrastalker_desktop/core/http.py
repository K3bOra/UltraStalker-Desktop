from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ultrastalker_desktop import __version__


def safe_request_error(exc: Exception, prefix: str = "Network request failed") -> str:
    """Return an error message that never echoes request URLs or credentials."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status is not None:
        return f"{prefix} (HTTP {status})"
    return f"{prefix} ({exc.__class__.__name__})"



def request_timeout(read_timeout: float, connect_timeout: float = 5.0) -> tuple[float, float]:
    """Return a bounded (connect, read) timeout tuple for requests.

    Portal hosts should fail relatively quickly when DNS/TCP/TLS connection
    establishment is impossible, while catalog/playlist reads still keep their
    existing larger budget.
    """
    read = max(0.1, float(read_timeout))
    connect = max(0.1, min(float(connect_timeout), read))
    return (connect, read)

def make_session(retries: int = 2, backoff: float = 0.25) -> requests.Session:
    """Create a bounded GET retry session for transient portal/network failures."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "HEAD")),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session = requests.Session()
    session.headers.update({"User-Agent": f"UltraStalkerDesktop/{__version__}"})
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

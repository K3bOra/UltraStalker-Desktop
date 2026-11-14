"""Read the official Ultra Stalker sources catalog over HTTPS."""
from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urlsplit

import requests

from ultrastalker_desktop import __version__
from ultrastalker_desktop.core.http import make_session, request_timeout
from ultrastalker_desktop.core.models import Profile


ENDPOINT = "https://ultrastalker-catalog-v2.k3borazz0.workers.dev/v2/"
PAGE_BYTES = 32768
IDENTIFIER = re.compile(r"[a-f0-9]{32}")
MAC = re.compile(r"(?:[a-f0-9]{2}:){5}[a-f0-9]{2}", re.IGNORECASE)


class CatalogError(RuntimeError):
    pass


def _id(value: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise CatalogError("Invalid catalog selection.")
    return value


def _path(kind, server=None):
    if kind not in ("portal", "xtream"):
        raise CatalogError("Unknown catalog type.")
    return f"{kind}/servers" + (f"/{_id(server)}/accounts" if server else "")


def _request(path, *, after=None, select=False):
    try:
        with make_session(retries=1) as session, session.request(
            "POST" if select else "GET",
            ENDPOINT + path,
            headers={"Accept": "application/json", "User-Agent": f"UltraStalkerDesktop/{__version__}"},
            params={"after": after} if after else None,
            data=b"{}" if select else None,
            timeout=request_timeout(12, 5),
            allow_redirects=False,
            stream=True,
        ) as response:
            if response.status_code != 200:
                raise CatalogError(f"Catalog unavailable (HTTP {response.status_code}).")
            data = bytearray()
            for chunk in response.iter_content(8192):
                data.extend(chunk)
                if len(data) > PAGE_BYTES:
                    raise CatalogError("Invalid catalog response.")
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError
        return payload
    except (requests.RequestException, ValueError) as exc:
        raise CatalogError("Could not read the Ultra Stalker catalog.") from exc


def page(kind, server=None, after=None):
    cursor = _id(after) if after else None
    response = _request(_path(kind, server), after=cursor)
    items = response.get("items")
    if not isinstance(items, list) or len(items) > 50:
        raise CatalogError("Invalid catalog page.")
    rows = []
    previous = cursor or ""
    for item in items:
        if not isinstance(item, dict):
            raise CatalogError("Invalid catalog entry.")
        identifier = _id(item.get("id"))
        label = item.get("server_name") or item.get("label")
        if identifier <= previous or not isinstance(label, str) or not label.strip():
            raise CatalogError("Invalid catalog entry.")
        row = {"id": identifier, "label": label.strip()[:80]}
        try:
            row["expiry"] = date.fromisoformat(str(item.get("expires_on"))).isoformat()
        except ValueError:
            pass
        rows.append(row)
        previous = identifier
    next_id = response.get("next")
    if next_id is not None and (not rows or _id(next_id) != previous):
        raise CatalogError("Invalid catalog cursor.")
    return {"items": rows, "next": next_id}


def profile(kind, server, account, label):
    payload = _request(f"{_path(kind, _id(server))}/{_id(account)}", select=True)
    data = payload.get("connection")
    if not isinstance(data, dict):
        raise CatalogError("The catalog returned no connection.")
    url = data.get("url")
    try:
        parsed = urlsplit(url if isinstance(url, str) else "")
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username is not None:
            raise ValueError
    except ValueError as exc:
        raise CatalogError("Invalid catalog source address.") from exc
    name = str(label or parsed.hostname).strip()[:60] or parsed.hostname
    if kind == "portal":
        mac = data.get("mac")
        if not isinstance(mac, str) or not MAC.fullmatch(mac):
            raise CatalogError("Invalid catalog portal account.")
        return Profile(name, "stalker", url, mac=mac.upper())
    username, password = data.get("username"), data.get("password")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment or not all(
        isinstance(value, str) and value for value in (username, password)
    ):
        raise CatalogError("Invalid catalog Xtream account.")
    return Profile(name, "xtream", url, username=username, password=password)

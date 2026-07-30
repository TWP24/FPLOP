"""FPL public API client with on-disk caching.

No auth needed for any of these endpoints. Cache is keyed by endpoint and
expires after `ttl` seconds so repeated CLI runs don't hammer the API.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://fantasy.premierleague.com/api"
CACHE = Path(__file__).resolve().parent.parent / ".cache"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) fplm/1.0"


def _cache_path(key: str) -> Path:
    return CACHE / f"{key.replace('/', '_')}.json"


def fetch(endpoint: str, key: str | None = None, ttl: int = 3600) -> Any:
    """GET an FPL endpoint, using the disk cache when it is fresh enough."""
    key = key or endpoint.strip("/")
    path = _cache_path(key)
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return json.loads(path.read_text())

    resp = requests.get(f"{BASE}/{endpoint.strip('/')}/", headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def bootstrap(ttl: int = 3600) -> dict:
    """Players, teams, gameweeks, phases (the monthly buckets), scoring config."""
    return fetch("bootstrap-static", ttl=ttl)


def fixtures(ttl: int = 3600) -> list[dict]:
    """All 380 fixtures with FPL's own difficulty ratings attached."""
    return fetch("fixtures", ttl=ttl)


def entry_picks(entry_id: int, event: int, ttl: int = 600) -> dict:
    """A specific manager's squad for a gameweek — used to seed `optimise --from-squad`."""
    return fetch(f"entry/{entry_id}/event/{event}/picks", key=f"picks_{entry_id}_{event}", ttl=ttl)


def league_standings(league_id: int, ttl: int = 600) -> dict:
    """Classic league standings — used to size the field in the win-probability model."""
    return fetch(f"leagues-classic/{league_id}/standings", key=f"league_{league_id}", ttl=ttl)


def clear_cache() -> int:
    """Delete every cached response. Returns the number of files removed."""
    if not CACHE.exists():
        return 0
    files = list(CACHE.glob("*.json"))
    for f in files:
        f.unlink()
    return len(files)

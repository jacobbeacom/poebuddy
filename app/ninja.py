"""poe.ninja economy data: live prices for cost-aware recommendations.

Second network exception besides pobb.in (see README). Fetches the PoE2
currency-exchange overview, caches it on disk for `ninja.cache_hours`, and
degrades to None on any failure -- reports render fully without prices.

Endpoint notes (unofficial-but-public surface, no SLA):
  index-state:  /poe2/api/data/index-state          -> league discovery
  currency:     /poe2/api/economy/exchange/current/overview
                    ?league=<name>&type=Currency
`lines[].primaryValue` is the item's value in Divine Orbs;
`core.rates` gives exalted/chaos per divine for display conversion.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from app.settings import SETTINGS

NCFG = SETTINGS["ninja"]
BASE = "https://poe.ninja/poe2/api"
CACHE_PATH = Path(SETTINGS["paths"]["qdrant_path"]).parent / "ninja_prices.json"
UA = {"User-Agent": "poebuddy/0.1 (personal research tool)"}


def _discover_league(session: requests.Session) -> str:
    resp = session.get(f"{BASE}/data/index-state", headers=UA, timeout=10)
    resp.raise_for_status()
    leagues = resp.json().get("economyLeagues", [])
    for lg in leagues:
        if lg.get("indexed"):
            return lg["name"]
    if leagues:
        return leagues[0]["name"]
    raise ValueError("poe.ninja returned no PoE2 leagues")


def _fetch() -> dict:
    session = requests.Session()
    league = NCFG["league"]
    if league == "auto":
        league = _discover_league(session)
    resp = session.get(
        f"{BASE}/economy/exchange/current/overview",
        params={"league": league, "type": "Currency"},
        headers=UA, timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    names = {i["id"]: i["name"] for i in data.get("items", [])}
    prices = {}
    for line in data.get("lines", []):
        name = names.get(line["id"])
        val = line.get("primaryValue")
        if name and isinstance(val, (int, float)) and val > 0:
            prices[name] = float(val)
    return {
        "league": league,
        "fetched_at": time.time(),
        "fetched_at_text": time.strftime("%Y-%m-%d %H:%M"),
        "rates": data.get("core", {}).get("rates", {}),  # per 1 divine
        "prices": prices,  # item name -> value in divines
    }


def get_prices() -> dict | None:
    """Cached price sheet, or None when disabled/unreachable."""
    if not NCFG.get("enabled", True):
        return None
    if CACHE_PATH.exists():
        try:
            cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            age_h = (time.time() - cached.get("fetched_at", 0)) / 3600
            if age_h < NCFG["cache_hours"] and cached.get("prices"):
                return cached
        except Exception:  # noqa: BLE001 -- corrupt cache: refetch
            pass
    try:
        data = _fetch()
    except Exception:  # noqa: BLE001 -- offline/blocked: degrade gracefully
        return None
    try:
        CACHE_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:  # noqa: BLE001 -- cache write is best-effort
        pass
    return data


def price_text(sheet: dict, item: str, qty: int = 1) -> str | None:
    """Human cost like '≈12 ex' / '≈0.3 div', or None if unpriced."""
    div = sheet["prices"].get(item)
    if div is None:
        return None
    total = div * qty
    if total >= 0.5:
        return f"≈{total:.1f} div"
    ex_per_div = sheet["rates"].get("exalted")
    if ex_per_div:
        ex = total * ex_per_div
        return f"≈{ex:.0f} ex" if ex >= 1 else "<1 ex"
    return f"≈{total:.3f} div"

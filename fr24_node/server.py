"""Nearest-aircraft fetch for the fr24 widget.

Reads a Flightradar24 feeder's local ``flights.json`` (fr24feed serves it
on port 8754), keeps aircraft that have a position fix and a callsign,
and returns the one nearest the cell's home point. "Nearest" combines
ground distance with altitude, the altitude counted ``ALT_WEIGHT`` times
over, so a low aircraft 12 km out beats an airliner passing overhead at
38,000 ft (which ranks like one ~35 km out on the ground). Cached per
``(node_url, home_lat, home_lon)`` for 5 minutes in the plugin's data_dir,
which is the widget's update cadence.

Each ``flights.json`` value is a positional array. The fields we read:

    [0] Mode S hex   [1] lat   [2] lon   [3] track (deg)   [4] altitude (ft)
    [5] ground speed (kt)   [6] squawk   [10] last seen (unix s)
    [15] vertical rate (ft/min)   [16] callsign

A position of ``0, 0`` means the feeder hasn't decoded one yet.

The winner is then looked up on adsbdb.com: its Mode S hex gives the
manufacturer and type, its callsign the airline and route. Both are
optional extras, so a miss or an outage only leaves them off the card.
Answers are kept on disk well beyond the 5-minute cycle (an airframe's
type never changes, a flight number's route rarely does).

An airline callsign (three letters then a digit, ``DAL2825``) also fetches
that airline's logo from soaringsymbols.org, as SVG, kept for 180 days.
It reaches the client as a ``data:`` URI for an ``<img>``, so the render
needs no network of its own and nothing in the SVG can run.
"""

from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import json
import math
import re
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from app.net_guard import BlockedURLError, assert_operator_url
from app.plugin_http import fetch_json, fetch_text

CACHE_TTL_S = 300
# The composer gives fetch() 6 s in all. The feeder is on the LAN and
# answers in milliseconds, so 3 s is generous for it, and the adsbdb and
# logo lookups run side by side in what's left.
HTTP_TIMEOUT_S = 3
LOOKUP_TIMEOUT_S = 2.5
USER_AGENT = "tesserae/0.1 (+fr24)"

ADSBDB = "https://api.adsbdb.com/v0"
# How long an adsbdb answer is reused: (found, not found). A transient
# failure (timeout, 5xx) isn't kept at all, so the next cycle retries.
AIRCRAFT_TTL_S = (30 * 86400, 7 * 86400)
ROUTE_TTL_S = (86400, 86400)
_HEX_RE = re.compile(r"^[0-9a-f]{6}$")
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{2,8}$")

LOGOS = "https://soaringsymbols.org/api/airlines"
LOGO_TTL_S = (180 * 86400, 7 * 86400)
LOGO_MAX_BYTES = 64 * 1024
# ICAO airline designator at the head of a callsign: DAL2825 → DAL. A tail
# number (N9880Q) doesn't match, so GA traffic never asks for a logo.
_AIRLINE_RE = re.compile(r"^([A-Z]{3})\d")
# The feeder keeps an aircraft listed for a while after it was last heard.
# Anything this much older than the newest report has left the area.
STALE_S = 120

FT_TO_KM = 0.0003048
EARTH_RADIUS_KM = 6371.0
# How much more a km of altitude counts than a km of ground distance when
# ranking. 1 would be true slant range, which lets cruise traffic overhead
# win over a low aircraft a few km away.
ALT_WEIGHT = 3.0

IDX_HEX, IDX_LAT, IDX_LON, IDX_TRACK, IDX_ALT, IDX_SPEED, IDX_SQUAWK = range(7)
IDX_SEEN = 10
IDX_VRATE = 15
IDX_CALLSIGN = 16


def _cached(path: Path) -> dict[str, Any] | None:
    if not path.exists() or time.time() - path.stat().st_mtime >= CACHE_TTL_S:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def fetch(
    options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]
) -> dict[str, Any]:
    del settings
    url = str(options.get("node_url") or "").strip()
    if not url:
        return {"error": "Set the radar node's flights.json address in the cell editor."}
    try:
        home_lat = float(options.get("home_lat"))
        home_lon = float(options.get("home_lon"))
    except (TypeError, ValueError):
        return {"error": "Latitude and longitude need to be numbers."}
    if not (-90 <= home_lat <= 90 and -180 <= home_lon <= 180):
        return {"error": "Latitude or longitude is out of range."}

    data_dir = Path(ctx["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{url}|{home_lat:.5f}|{home_lon:.5f}".encode()).hexdigest()[:16]
    cache_path = data_dir / f"nearest_{key}.json"
    cached = _cached(cache_path)
    if cached is not None:
        return cached

    try:
        assert_operator_url(url)
        payload = fetch_json(
            url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_S, retries=0
        )
    except BlockedURLError:
        return {"error": "That radar node address isn't allowed."}
    except json.JSONDecodeError:
        return {"error": "The radar node didn't return flight data."}
    except (urllib.error.URLError, TimeoutError, OSError):
        return {"error": "Can't reach the radar node right now."}
    if not isinstance(payload, dict):
        return {"error": "The radar node didn't return flight data."}

    result: dict[str, Any] = {"updated": int(time.time())}
    nearest = nearest_aircraft(payload, home_lat, home_lon)
    if nearest is None:
        result["empty"] = True
    else:
        nearest.update(_lookups(nearest["hex"], nearest["callsign"], data_dir / "adsbdb"))
        result["aircraft"] = nearest
    with contextlib.suppress(OSError):
        cache_path.write_text(json.dumps(result), encoding="utf-8")
    return result


def nearest_aircraft(
    payload: dict[str, Any], home_lat: float, home_lon: float
) -> dict[str, Any] | None:
    """The tracked aircraft with the lowest altitude-weighted range from
    home, among those with a callsign, a position fix and a recent report.
    ``None`` when nothing qualifies."""
    rows = [_parse(v) for v in payload.values()]
    rows = [r for r in rows if r is not None]
    if not rows:
        return None
    newest = max(r["seen"] for r in rows)
    best: dict[str, Any] | None = None
    best_score = math.inf
    for r in rows:
        if newest - r["seen"] > STALE_S:
            continue
        ground = _haversine_km(home_lat, home_lon, r["lat"], r["lon"])
        r["ground_km"] = round(ground, 2)
        score = math.hypot(ground, ALT_WEIGHT * r["altitude_ft"] * FT_TO_KM)
        if best is None or score < best_score:
            best, best_score = r, score
    return best


def _parse(row: Any) -> dict[str, Any] | None:
    """One ``flights.json`` array → the fields the widget uses, or ``None``
    when it has no callsign or no position fix."""
    if not isinstance(row, list) or len(row) <= IDX_CALLSIGN:
        return None
    callsign = str(row[IDX_CALLSIGN] or "").strip()
    if not callsign:
        return None
    try:
        lat = float(row[IDX_LAT])
        lon = float(row[IDX_LON])
        alt = float(row[IDX_ALT] or 0)
        seen = int(row[IDX_SEEN] or 0)
    except (TypeError, ValueError):
        return None
    if lat == 0 and lon == 0:
        return None
    return {
        "callsign": callsign,
        "hex": str(row[IDX_HEX] or ""),
        "lat": lat,
        "lon": lon,
        "altitude_ft": max(0, round(alt)),
        "track": _num(row[IDX_TRACK]),
        "speed_kt": _num(row[IDX_SPEED]),
        "squawk": str(row[IDX_SQUAWK] or ""),
        "vrate_fpm": _num(row[IDX_VRATE]),
        "seen": seen,
    }


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------
# adsbdb.com lookups for the winning aircraft.
# ----------------------------------------------------------------------


def _lookups(hex_code: str, callsign: str, cache_dir: Path) -> dict[str, Any]:
    """``{"model": ..., "route": ..., "logo": ...}`` for whichever lookups
    came back. The requests run in parallel, each in a copy of this context
    so the host's per-widget network allowlist still applies in the thread."""
    hex_code = hex_code.lower()
    callsign = callsign.upper()
    jobs = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        if _HEX_RE.match(hex_code):
            jobs["model"] = pool.submit(
                contextvars.copy_context().run,
                _adsbdb,
                f"aircraft/{hex_code}",
                cache_dir / f"aircraft_{hex_code}.json",
                AIRCRAFT_TTL_S,
                _model,
            )
        if _CALLSIGN_RE.match(callsign):
            jobs["route"] = pool.submit(
                contextvars.copy_context().run,
                _adsbdb,
                f"callsign/{callsign}",
                cache_dir / f"route_{callsign}.json",
                ROUTE_TTL_S,
                _route,
            )
        airline = _AIRLINE_RE.match(callsign)
        if airline:
            jobs["logo"] = pool.submit(
                contextvars.copy_context().run, _logo, airline.group(1), cache_dir.parent / "logos"
            )
    out: dict[str, Any] = {}
    for name, job in jobs.items():
        value = job.result()
        if value:
            out[name] = value
    return out


def _adsbdb(path: str, cache_path: Path, ttls: tuple[int, int], shape: Any) -> Any:
    """One adsbdb GET, shaped by ``shape(response)``. Returns ``None`` on a
    miss or a failure. Hits and 404 misses are cached for their TTL."""
    if cache_path.exists():
        try:
            entry = json.loads(cache_path.read_text(encoding="utf-8"))
            ttl = ttls[0] if entry.get("value") else ttls[1]
            if time.time() - cache_path.stat().st_mtime < ttl:
                return entry.get("value")
        except (json.JSONDecodeError, OSError, AttributeError):
            pass
    try:
        payload = fetch_json(
            f"{ADSBDB}/{path}",
            headers={"User-Agent": USER_AGENT},
            timeout=LOOKUP_TIMEOUT_S,
            retries=0,
        )
    except urllib.error.HTTPError as err:
        if err.code != 404:
            return None
        payload = None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    response = payload.get("response") if isinstance(payload, dict) else None
    value = shape(response) if isinstance(response, dict) else None
    with contextlib.suppress(OSError):
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"value": value}), encoding="utf-8")
    return value


def _logo(icao: str, cache_dir: Path) -> str | None:
    """The airline's logo as an SVG ``data:`` URI, or ``None``. A hit is
    kept as ``<ICAO>.svg``, a 404 as an empty ``<ICAO>.miss``."""
    hit = cache_dir / f"{icao}.svg"
    miss = cache_dir / f"{icao}.miss"
    svg: str | None = None
    with contextlib.suppress(OSError):
        if time.time() - hit.stat().st_mtime < LOGO_TTL_S[0]:
            svg = hit.read_text(encoding="utf-8")
    if svg is None:
        with contextlib.suppress(OSError):
            if time.time() - miss.stat().st_mtime < LOGO_TTL_S[1]:
                return None
        try:
            svg = fetch_text(
                f"{LOGOS}/{icao}/icon.svg",
                headers={"User-Agent": USER_AGENT},
                timeout=LOOKUP_TIMEOUT_S,
            )
        except urllib.error.HTTPError as err:
            if err.code == 404:
                with contextlib.suppress(OSError):
                    cache_dir.mkdir(parents=True, exist_ok=True)
                    miss.touch()
            return None
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
        if "<svg" not in svg or len(svg.encode()) > LOGO_MAX_BYTES:
            return None
        with contextlib.suppress(OSError):
            cache_dir.mkdir(parents=True, exist_ok=True)
            hit.write_text(svg, encoding="utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode("ascii")


def _model(response: dict[str, Any]) -> dict[str, Any] | None:
    ac = response.get("aircraft")
    if not isinstance(ac, dict):
        return None
    out = {
        "manufacturer": _text(ac.get("manufacturer")),
        "type": _text(ac.get("type")),
        "icao_type": _text(ac.get("icao_type")),
        "registration": _text(ac.get("registration")),
        "owner": _text(ac.get("registered_owner")),
    }
    return out if out["manufacturer"] or out["type"] else None


def _route(response: dict[str, Any]) -> dict[str, Any] | None:
    fr = response.get("flightroute")
    if not isinstance(fr, dict):
        return None
    airline = fr.get("airline") if isinstance(fr.get("airline"), dict) else {}
    origin = _airport(fr.get("origin"))
    destination = _airport(fr.get("destination"))
    if origin is None or destination is None:
        return None
    return {
        "airline": _text(airline.get("name")),
        "flight_iata": _text(fr.get("callsign_iata")),
        "origin": origin,
        "destination": destination,
    }


def _airport(a: Any) -> dict[str, str] | None:
    if not isinstance(a, dict):
        return None
    code = _text(a.get("iata_code")) or _text(a.get("icao_code"))
    if not code:
        return None
    return {
        "code": code,
        "icao": _text(a.get("icao_code")),
        "name": _text(a.get("name")),
        "city": _text(a.get("municipality")),
    }


def _text(v: Any) -> str:
    return v.strip() if isinstance(v, str) else ""

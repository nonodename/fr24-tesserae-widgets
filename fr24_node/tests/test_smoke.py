"""fr24 smoke: the composer renders the nearest aircraft from a faked feeder
response at every supported size, and the selection rules hold."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

from plugins.fr24 import server as fr24_server

HOME = (45.000, -95.000)

# Shaped like a real fr24feed flights.json: positional arrays keyed by hex.
_FLIGHTS = {
    # No position fix yet.
    "a39294": [
        "a39294",
        0,
        0,
        351.9,
        0,
        149,
        "0000",
        0,
        "",
        "",
        1794085065,
        "",
        "",
        "",
        False,
        0,
        "SKW123",
    ],
    # No callsign.
    "a12ade": [
        "a12ade",
        45.001,
        -94.999,
        43.4,
        1850,
        106,
        "1200",
        0,
        "",
        "",
        1794085073,
        "",
        "",
        "",
        False,
        -256,
        "",
    ],
    # Almost overhead but at cruise.
    "a5e74c": [
        "a5e74c",
        45.000,
        -95.005,
        298.7,
        38000,
        344,
        "6530",
        0,
        "",
        "",
        1794085066,
        "",
        "",
        "",
        False,
        -64,
        "UAL88",
    ],
    # ~12 km out, low: the winner.
    "a35d79": [
        "a35d79",
        44.900,
        -95.066,
        114.8,
        3275,
        211,
        "2666",
        0,
        "",
        "",
        1794085073,
        "",
        "",
        "",
        False,
        0,
        "DAL2594",
    ],
    # Close and low, but last heard long ago.
    "ac0096": [
        "ac0096",
        44.990,
        -94.996,
        347.2,
        900,
        86,
        "1200",
        0,
        "",
        "",
        1794084500,
        "",
        "",
        "",
        False,
        0,
        "N123AB",
    ],
    # Further out.
    "abfe1c": [
        "abfe1c",
        44.770,
        -95.000,
        159.9,
        7125,
        286,
        "2435",
        0,
        "",
        "",
        1794085073,
        "",
        "",
        "",
        False,
        2880,
        "DAL1036",
    ],
}


_AIRCRAFT = {
    "response": {
        "aircraft": {
            "type": "A321-211",
            "icao_type": "A321",
            "manufacturer": "Airbus",
            "mode_s": "A35D79",
            "registration": "N301DN",
            "registered_owner": "DELTA AIR LINES INC",
        }
    }
}
_ROUTE = {
    "response": {
        "flightroute": {
            "callsign": "DAL2594",
            "callsign_iata": "DL2594",
            "airline": {"name": "Delta Air Lines", "icao": "DAL"},
            "origin": {
                "iata_code": "ATL",
                "icao_code": "KATL",
                "municipality": "Atlanta",
                "name": "Hartsfield Jackson",
            },
            "destination": {
                "iata_code": "MSP",
                "icao_code": "KMSP",
                "municipality": "Minneapolis",
                "name": "MSP Intl",
            },
        }
    }
}


_SVG = '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path fill="#98002e" d="M0 0h24v24z"/></svg>'


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *a) -> bool:
        return False


def _fake_urlopen(routes: dict[str, object]):
    """urlopen stand-in answering by URL: a dict is served as JSON, a str
    as-is, an int raises that HTTP status, and an exception is raised."""

    def urlopen(req, timeout=None):
        url = req.full_url
        for fragment, answer in routes.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                if isinstance(answer, int):
                    raise urllib.error.HTTPError(url, answer, "status", {}, None)
                if isinstance(answer, str):
                    return _FakeResp(answer.encode())
                return _FakeResp(json.dumps(answer).encode())
        raise AssertionError(f"unexpected request to {url}")

    return urlopen


_ALL_FOUND = {
    "flights.json": _FLIGHTS,
    "aircraft/a35d79": _AIRCRAFT,
    "callsign/DAL2594": _ROUTE,
    "airlines/DAL/icon.svg": _SVG,
}
_OPTS = {
    "node_url": "http://192.0.2.10:8754/flights.json",
    "home_lat": HOME[0],
    "home_lon": HOME[1],
}


def _fetch(tmp_path, routes):
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen(routes)):
        return fr24_server.fetch(_OPTS, {}, ctx={"data_dir": str(tmp_path)})


def test_nearest_prefers_low_slant_range_with_callsign() -> None:
    best = fr24_server.nearest_aircraft(_FLIGHTS, *HOME)
    assert best is not None
    assert best["callsign"] == "DAL2594"
    assert best["altitude_ft"] == 3275
    assert best["seen"] == 1794085073


def test_nearest_none_when_nothing_qualifies() -> None:
    only_unusable = {k: _FLIGHTS[k] for k in ("a39294", "a12ade")}
    assert fr24_server.nearest_aircraft(only_unusable, *HOME) is None


def test_fetch_reports_unreachable_node(tmp_path) -> None:
    out = _fetch(tmp_path, {"flights.json": OSError("no route")})
    assert out == {"error": "Can't reach the radar node right now."}


def test_fetch_adds_model_and_route(tmp_path) -> None:
    ac = _fetch(tmp_path, _ALL_FOUND)["aircraft"]
    assert ac["model"]["manufacturer"] == "Airbus"
    assert ac["model"]["type"] == "A321-211"
    assert ac["route"]["airline"] == "Delta Air Lines"
    assert ac["route"]["origin"]["code"] == "ATL"
    assert ac["route"]["destination"]["city"] == "Minneapolis"


def test_lookup_misses_are_cached_and_skipped(tmp_path) -> None:
    misses = {"flights.json": _FLIGHTS, "aircraft/": 404, "callsign/": 404, "airlines/": 404}
    ac = _fetch(tmp_path, misses)["aircraft"]
    assert ac["callsign"] == "DAL2594"
    assert "model" not in ac and "route" not in ac and "logo" not in ac
    # A 404 is remembered: a later cycle (past the 5-minute result cache)
    # doesn't ask adsbdb again.
    for f in tmp_path.glob("nearest_*.json"):
        f.unlink()
    ac = _fetch(tmp_path, {"flights.json": _FLIGHTS})["aircraft"]
    assert "model" not in ac and "route" not in ac


def test_lookup_outage_is_not_cached(tmp_path) -> None:
    down = {
        "flights.json": _FLIGHTS,
        "adsbdb": TimeoutError("slow"),
        "soaringsymbols": TimeoutError("slow"),
    }
    ac = _fetch(tmp_path, down)["aircraft"]
    assert "model" not in ac and "route" not in ac
    for f in tmp_path.glob("nearest_*.json"):
        f.unlink()
    ac = _fetch(tmp_path, _ALL_FOUND)["aircraft"]
    assert ac["route"]["origin"]["code"] == "ATL"
    assert ac["logo"].startswith("data:image/svg+xml;base64,")


def test_logo_is_cached(tmp_path) -> None:
    first = _fetch(tmp_path, _ALL_FOUND)["aircraft"]["logo"]
    for f in tmp_path.glob("nearest_*.json"):
        f.unlink()
    # No route for the logo URL now: a second fetch would raise.
    no_logo_server = {k: v for k, v in _ALL_FOUND.items() if "airlines" not in k}
    assert _fetch(tmp_path, no_logo_server)["aircraft"]["logo"] == first


def test_tail_number_skips_logo(tmp_path) -> None:
    ga = {
        "a3cf88": [
            "a3cf88",
            45.001,
            -94.999,
            318.9,
            2650,
            124,
            "6523",
            0,
            "",
            "",
            1794085073,
            "",
            "",
            "",
            False,
            0,
            "N3447S",
        ]
    }
    routes = {"flights.json": ga, "aircraft/": 404, "callsign/": 404}
    ac = _fetch(tmp_path, routes)["aircraft"]
    assert ac["callsign"] == "N3447S" and "logo" not in ac


@pytest.mark.parametrize("size", ["xs", "sm", "md", "lg"])
def test_fr24_renders(client: FlaskClient, size: str) -> None:
    with patch("urllib.request.urlopen", side_effect=_fake_urlopen(_ALL_FOUND)):
        resp = client.get(f"/_test/render?plugin=fr24&size={size}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'data-plugin="fr24"' in body
    assert "DAL2594" in body
    assert "Delta Air Lines" in body

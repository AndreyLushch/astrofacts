import warnings

import pytest

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient

from astrofacts import ephemeris
from astrofacts.schema import SCHEMA_VERSION, DayFacts
from astrofacts.service import create_app


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_day(client):
    r = client.get("/day", params={"date": "2026-10-23", "tz": "Europe/Moscow"})
    assert r.status_code == 200
    facts = DayFacts.model_validate(r.json())
    assert facts.schema_version == SCHEMA_VERSION
    assert facts.meta.lookahead_hours == 0
    assert len(facts.signs) == 12


def test_lookahead_is_a_request_parameter_and_part_of_cache_key(client):
    plain = client.get("/day", params={"date": "2026-10-23", "tz": "Europe/Moscow"}).json()
    ahead = client.get("/day", params={"date": "2026-10-23", "tz": "Europe/Moscow", "lookahead": "6"}).json()
    assert ahead["meta"]["lookahead_hours"] == 6
    assert len(ahead["moon"]["aspects"]) > len(plain["moon"]["aspects"])
    assert any(a["when"]["beyond_day"] for a in ahead["moon"]["aspects"])
    assert not any(a["when"]["beyond_day"] for a in plain["moon"]["aspects"])


def test_repeated_request_is_served_from_cache(client):
    params = {"date": "2026-11-05", "tz": "Europe/Moscow"}
    before = client.get("/health").json()["cache"]
    first = client.get("/day", params=params).json()
    second = client.get("/day", params=params).json()
    after = client.get("/health").json()["cache"]
    assert first == second
    assert (after["misses"] - before["misses"], after["hits"] - before["hits"]) == (1, 1)


def test_schema_version_mismatch_is_a_clear_error(client):
    r = client.get("/day", params={"date": "2026-10-23", "tz": "UTC", "schema": str(SCHEMA_VERSION + 1)})
    assert r.status_code == 409
    assert r.json()["error"] == "schema_version_mismatch"
    assert r.json()["supported_schema_versions"] == [SCHEMA_VERSION]
    ok = client.get("/day", params={"date": "2026-10-23", "tz": "UTC", "schema": str(SCHEMA_VERSION)})
    assert ok.status_code == 200


@pytest.mark.parametrize("params, code", [
    ({"tz": "UTC"}, "missing_parameter"),
    ({"date": "2026-10-23"}, "missing_parameter"),
    ({"date": "23.10.2026", "tz": "UTC"}, "invalid_date"),
    ({"date": "1700-01-01", "tz": "UTC"}, "date_out_of_range"),
    ({"date": "2026-10-23", "tz": "Europe/Nowhere"}, "unknown_timezone"),
    ({"date": "2026-10-23", "tz": "UTC", "lookahead": "many"}, "invalid_lookahead"),
    ({"date": "2026-10-23", "tz": "UTC", "lookahead": "-1"}, "invalid_lookahead"),
    ({"date": "2026-10-23", "tz": "UTC", "lookahead": "nan"}, "invalid_lookahead"),
    ({"date": "2026-10-23", "tz": "UTC", "lookahead": "100"}, "invalid_lookahead"),
])
def test_bad_requests(client, params, code):
    r = client.get("/day", params=params)
    assert r.status_code == 422
    assert r.json()["error"] == code and r.json()["detail"]


def test_edges_of_ephemeris_range(client):
    for day in ("1800-02-01", "2399-11-30"):
        assert client.get("/day", params={"date": day, "tz": "Europe/Moscow"}).status_code == 200


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["schema_version"] == SCHEMA_VERSION
    assert body["config_hash"] and body["tzdata_version"]


def test_service_does_not_start_without_ephemeris_files(tmp_path, monkeypatch):
    monkeypatch.setenv(ephemeris.EPHE_ENV, str(tmp_path))
    with pytest.raises(ephemeris.EphemerisError):
        with TestClient(create_app()):
            pass

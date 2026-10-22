"""The endpoints against fake services: requests to VictoriaMetrics, checks, errors."""

import pytest

from support import (
    DEG_C,
    HUMIDITY,
    NOTE,
    OBJECT,
    PERCENT,
    STORE_H,
    STORE_T,
    TEMPERATURE,
    FakeServices,
    sample,
)

BASE = "/tsapi/stores"


# --- writing -------------------------------------------------------------


def test_write_one_sample(api, services):
    response = api.post(f"{BASE}/{STORE_T}/samples", json=sample())
    assert response.status_code == 200, response.text
    assert response.json() == {"written": 1}
    (request,) = services.vm_requests("/api/v1/import")
    # The store is never taken from the body: VictoriaMetrics sets it.
    assert FakeServices.form(request)["extra_label"] == [f"ifdd_store={STORE_T}"]
    (line,) = FakeServices.imported(request)
    assert line == {
        "metric": {
            "__name__": "temperature",
            "ifdd_id": OBJECT,
            "ifdd_property": TEMPERATURE,
            "ifdd_unit": DEG_C,
        },
        "values": [21.5],
        "timestamps": [1792653300250],
    }


def test_batch_groups_samples_per_series(api, services):
    samples = [
        sample(time="2026-10-22T07:00:00Z", value=20),
        sample(time="2026-10-22T07:15:00Z", value=21),
        sample(name="humidity", ifdd_property=HUMIDITY, ifdd_unit=PERCENT,
               time="2026-10-22T07:00:00Z", value=55),
    ]
    response = api.post(f"{BASE}/{STORE_T}/samples/batch", json={"samples": samples})
    assert response.json() == {"written": 3}
    (request,) = services.vm_requests("/api/v1/import")
    lines = FakeServices.imported(request)
    assert [(l["metric"]["__name__"], l["values"]) for l in lines] == [
        ("temperature", [20.0, 21.0]),
        ("humidity", [55.0]),
    ]


def test_a_bad_sample_refuses_the_whole_batch(api, services):
    samples = [sample(), sample(value=500), sample(ifdd_unit=PERCENT)]
    response = api.post(f"{BASE}/{STORE_T}/samples/batch", json={"samples": samples})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "samples[1]" in detail and "above 120" in detail
    assert "samples[2]" in detail and "not applicable" in detail
    assert "samples[0]" not in detail
    assert not services.vm_requests("/api/v1/import")


def test_batch_limit(api, services):
    from ifdd.ts.core.config import get_settings

    get_settings().IFDD_TS_MAX_ITEMS = 2
    response = api.post(f"{BASE}/{STORE_T}/samples/batch", json={"samples": [sample()] * 3})
    assert response.status_code == 422
    assert "more than 2" in response.json()["detail"]
    assert not services.requests


def test_empty_batch_is_refused(api):
    assert api.post(f"{BASE}/{STORE_T}/samples/batch", json={"samples": []}).status_code == 422


@pytest.mark.parametrize(
    "change, message",
    [
        ({"time": "2026-10-22T09:15:00"}, "no offset"),
        ({"time": "2026-10-22T09:15:00.0001Z"}, "finer than a millisecond"),
        ({"value": "21.5"}, "valid number"),
        ({"name": "__name__"}, "name must be"),
        ({"name": "1st"}, "name must be"),
        ({"ifdd_id": "breaker-0001"}, "absolute http"),
        ({"ifdd_unit": "https://unit/v1/unit/DEG C"}, "absolute http"),
        ({"extra": "label"}, "Extra inputs"),
    ],
)
def test_invalid_bodies(api, services, change, message):
    response = api.post(f"{BASE}/{STORE_T}/samples", json=sample(**change))
    assert response.status_code == 422
    assert message in response.text
    assert not services.vm_requests("/api/v1/import")


def test_nan_is_refused(api, services):
    body = '{"name":"temperature","ifdd_id":"%s","ifdd_property":"%s","ifdd_unit":"%s",' \
           '"time":"2026-10-22T07:00:00Z","value":NaN}' % (OBJECT, TEMPERATURE, DEG_C)
    response = api.post(f"{BASE}/{STORE_T}/samples", content=body,
                        headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert not services.vm_requests("/api/v1/import")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"ifdd_property": "https://elsewhere/v1/ns/temperature"}, "not below the type service"),
        ({"ifdd_property": TEMPERATURE + "X"}, "defines no property"),
        ({"ifdd_unit": PERCENT}, "not applicable"),
        ({"value": -61}, "below -60"),
    ],
)
def test_vocabulary_checks(api, services, change, message):
    response = api.post(f"{BASE}/{STORE_T}/samples", json=sample(**change))
    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert not services.vm_requests("/api/v1/import")


def test_property_without_rules_takes_any_unit(api, services):
    body = sample(ifdd_property=NOTE, ifdd_unit="https://unit/v1/unit/anything", value=1e9)
    assert api.post(f"{BASE}/{STORE_T}/samples", json=body).status_code == 200


def test_type_service_down_is_502(api, services):
    services.down.add("type")
    response = api.post(f"{BASE}/{STORE_T}/samples", json=sample())
    assert response.status_code == 502
    assert not services.vm_requests("/api/v1/import")


def test_victoriametrics_down_is_502(api, services):
    services.down.add("vm")
    response = api.post(f"{BASE}/{STORE_T}/samples", json=sample())
    assert response.status_code == 502
    assert "VictoriaMetrics" in response.json()["detail"]


def test_invalid_store_name_is_422(api, services):
    response = api.post(f"{BASE}/Temperature/samples", json=sample())
    assert response.status_code == 422
    assert not services.requests


def test_there_is_no_put(api):
    assert api.put(f"{BASE}/{STORE_T}/samples", json=sample()).status_code == 405


# --- reading -------------------------------------------------------------


def _line(name="temperature", unit=DEG_C, prop=TEMPERATURE, store=STORE_T, points=()):
    return {
        "metric": {"__name__": name, "ifdd_id": OBJECT, "ifdd_property": prop,
                   "ifdd_unit": unit, "ifdd_store": store},
        "values": [v for _, v in points],
        "timestamps": [t for t, _ in points],
    }


def test_range_returns_raw_samples_with_store_filter(api, services):
    services.export_lines = [_line(points=[(1792653300250, 21.5), (1792654200000, 22.0)])]
    response = api.get(
        f"{BASE}/{STORE_T}/samples/range",
        params={"ifdd_id": OBJECT, "start": "2026-10-22T00:00:00Z", "end": "2026-10-23T00:00:00Z"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "store": STORE_T, "name": "temperature", "ifdd_id": OBJECT,
            "ifdd_property": TEMPERATURE, "ifdd_unit": DEG_C,
            "samples": [
                {"time": "2026-10-22T07:15:00.250+00:00", "value": 21.5},
                {"time": "2026-10-22T07:30:00.000+00:00", "value": 22.0},
            ],
        }
    ]
    (request,) = services.vm_requests("/api/v1/export")
    form = FakeServices.form(request)
    assert form["extra_label"] == [f"ifdd_store={STORE_T}"]
    assert form["match[]"] == [f'{{ifdd_id="{OBJECT}"}}']
    assert (form["start"], form["end"]) == (["1792627200.000"], ["1792713600.000"])


def test_range_limit(api, services):
    from ifdd.ts.core.config import get_settings

    get_settings().IFDD_TS_MAX_ITEMS = 1
    services.export_lines = [_line(points=[(1, 1.0), (2, 2.0)])]
    response = api.get(f"{BASE}/{STORE_T}/samples/range",
                       params={"ifdd_id": OBJECT, "start": "1970-01-01T00:00:00Z"})
    assert response.status_code == 422
    assert "shorten the range" in response.json()["detail"]


def test_range_start_after_end(api):
    response = api.get(f"{BASE}/{STORE_T}/samples/range", params={
        "ifdd_id": OBJECT, "start": "2026-10-23T00:00:00Z", "end": "2026-10-22T00:00:00Z"})
    assert response.status_code == 422


def test_latest_sample(api, services):
    services.series_data = [_line()["metric"]]
    services.export_lines = [_line(points=[(1792653300250, 21.5), (1792654200000, 22.0)])]
    response = api.get(f"{BASE}/{STORE_T}/samples", params={
        "ifdd_id": OBJECT, "ifdd_property": TEMPERATURE, "at": "2026-10-22T08:00:00Z"})
    assert response.status_code == 200, response.text
    assert response.json()["time"] == "2026-10-22T07:30:00.000+00:00"
    assert response.json()["value"] == 22.0
    # The first window is enough: one hour before "at".
    (export,) = services.vm_requests("/api/v1/export")
    form = FakeServices.form(export)
    assert form["end"] == ["1792656000.000"] and form["start"] == ["1792652400.000"]
    for request in services.vm_requests("/api/v1/series") + [export]:
        assert FakeServices.form(request)["extra_label"] == [f"ifdd_store={STORE_T}"]


def test_latest_sample_widens_the_window(api, services):
    services.series_data = [_line()["metric"]]
    services.export_lines = []
    response = api.get(f"{BASE}/{STORE_T}/samples", params={
        "ifdd_id": OBJECT, "ifdd_property": TEMPERATURE, "max_age": 7200})
    assert response.status_code == 404
    starts = [FakeServices.form(r)["start"][0] for r in services.vm_requests("/api/v1/export")]
    assert len(starts) == 2  # one hour, then max_age


def test_latest_sample_ambiguous_and_missing(api, services):
    services.series_data = [_line()["metric"], _line(unit="https://unit/v1/unit/K")["metric"]]
    params = {"ifdd_id": OBJECT, "ifdd_property": TEMPERATURE}
    response = api.get(f"{BASE}/{STORE_T}/samples", params=params)
    assert response.status_code == 422 and "give name and ifdd_unit" in response.text
    services.series_data = []
    assert api.get(f"{BASE}/{STORE_T}/samples", params=params).status_code == 404


def test_latest_sample_needs_id_and_property(api):
    assert api.get(f"{BASE}/{STORE_T}/samples", params={"ifdd_id": OBJECT}).status_code == 422


def test_series(api, services):
    services.series_data = [_line()["metric"]]
    response = api.get(f"{BASE}/{STORE_T}/series", params={"name": "temperature"})
    assert response.json() == [{"store": STORE_T, "name": "temperature", "ifdd_id": OBJECT,
                                "ifdd_property": TEMPERATURE, "ifdd_unit": DEG_C}]
    (request,) = services.vm_requests("/api/v1/series")
    form = FakeServices.form(request)
    assert form["match[]"] == ['{__name__="temperature"}']
    assert form["extra_label"] == [f"ifdd_store={STORE_T}"]


def test_series_filter_values_are_quoted(api, services):
    api.get(f"{BASE}/{STORE_T}/series", params={"ifdd_id": OBJECT})
    (request,) = services.vm_requests("/api/v1/series")
    assert FakeServices.form(request)["match[]"] == [f'{{ifdd_id="{OBJECT}"}}']
    response = api.get(f"{BASE}/{STORE_T}/series", params={"ifdd_id": 'x"}'})
    assert response.status_code == 422


def test_series_limit(api, services):
    from ifdd.ts.core.config import get_settings

    get_settings().IFDD_TS_MAX_ITEMS = 1
    services.series_data = [_line()["metric"], _line(name="t2")["metric"]]
    assert api.get(f"{BASE}/{STORE_T}/series").status_code == 422


def test_stores_lists_only_valid_names(api, services):
    services.store_values = [STORE_H, STORE_T, "not-a-store"]
    assert api.get(BASE).json() == [STORE_H, STORE_T]

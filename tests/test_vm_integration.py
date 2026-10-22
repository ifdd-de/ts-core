"""Against a real VictoriaMetrics (IFDD_TEST_VM_URL), started with
``-dedup.minScrapeInterval=1ms`` like the ifdd-ts template.

Each test uses its own object IRI, so tests do not see each other's series
in a shared database. The type service is the fake of support.py.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from support import DEG_C, HUMIDITY, PERCENT, STORE_H, STORE_T, TEMPERATURE, sample, settings


def _flush(vm_url):
    import httpx

    httpx.get(vm_url.rstrip("/") + "/internal/force_flush", timeout=10)
    time.sleep(1)


@pytest.fixture
def live(vm_url, services):
    """The application with the real VictoriaMetrics and the fake type service."""
    import httpx

    from ifdd.ts.core import create_app, http

    app = create_app(settings(IFDD_TS_VM_URL=vm_url))
    real = httpx.AsyncClient()
    fake = httpx.AsyncClient(transport=httpx.MockTransport(services.handle))

    class Router(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.url.host == "type":
                return await fake._transport.handle_async_request(request)
            return await real._transport.handle_async_request(request)

    http.set_client(httpx.AsyncClient(transport=Router()))
    with TestClient(app) as client:
        yield client


def _object():
    return f"https://rest/products/{uuid.uuid4()}"


def test_stores_are_kept_apart(live, vm_url):
    obj = _object()
    t = sample(ifdd_id=obj, time="2026-10-22T07:00:00Z", value=21)
    h = sample(ifdd_id=obj, name="humidity", ifdd_property=HUMIDITY, ifdd_unit=PERCENT,
               time="2026-10-22T07:00:00Z", value=55)
    assert live.post(f"/tsapi/stores/{STORE_T}/samples", json=t).status_code == 200
    assert live.post(f"/tsapi/stores/{STORE_H}/samples", json=h).status_code == 200
    _flush(vm_url)
    params = {"ifdd_id": obj, "start": "2026-10-22T00:00:00Z", "end": "2026-10-23T00:00:00Z"}
    in_t = live.get(f"/tsapi/stores/{STORE_T}/samples/range", params=params).json()
    in_h = live.get(f"/tsapi/stores/{STORE_H}/samples/range", params=params).json()
    assert [s["name"] for s in in_t] == ["temperature"]
    assert [s["name"] for s in in_h] == ["humidity"]
    assert in_t[0]["store"] == STORE_T and in_t[0]["samples"][0]["value"] == 21


def test_a_store_label_in_the_body_cannot_redirect_a_write(live, vm_url):
    import httpx

    obj = _object()
    # Even a raw import naming another store is overridden by extra_label;
    # the API never sends one, this checks the database behaviour it relies on.
    line = ('{"metric":{"__name__":"temperature","ifdd_id":"%s","ifdd_store":"%s"},'
            '"values":[1],"timestamps":[1792653300000]}' % (obj, STORE_H))
    httpx.post(vm_url.rstrip("/") + "/api/v1/import", params={"extra_label": f"ifdd_store={STORE_T}"},
               content=line.encode(), timeout=10)
    _flush(vm_url)
    params = {"ifdd_id": obj, "start": "2026-10-22T00:00:00Z", "end": "2026-10-23T00:00:00Z"}
    assert live.get(f"/tsapi/stores/{STORE_H}/samples/range", params=params).json() == []
    assert len(live.get(f"/tsapi/stores/{STORE_T}/samples/range", params=params).json()) == 1


def test_same_time_twice_keeps_the_larger_value(live, vm_url):
    obj = _object()
    for value in (21.0, 25.0, 23.0):
        body = sample(ifdd_id=obj, time="2026-10-22T07:00:00Z", value=value)
        assert live.post(f"/tsapi/stores/{STORE_T}/samples", json=body).status_code == 200
    _flush(vm_url)
    params = {"ifdd_id": obj, "start": "2026-10-22T07:00:00Z", "end": "2026-10-22T07:00:00Z"}
    (series,) = live.get(f"/tsapi/stores/{STORE_T}/samples/range", params=params).json()
    assert series["samples"] == [{"time": "2026-10-22T07:00:00.000+00:00", "value": 25.0}]


def test_batch_latest_series_and_stores(live, vm_url):
    obj = _object()
    now = int(time.time())
    times = [now - 3 * 86400, now - 7200, now - 60]
    samples = [
        sample(ifdd_id=obj, time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)), value=float(i))
        for i, t in enumerate(times)
    ]
    response = live.post(f"/tsapi/stores/{STORE_T}/samples/batch", json={"samples": samples})
    assert response.json() == {"written": 3}
    _flush(vm_url)

    params = {"ifdd_id": obj, "ifdd_property": TEMPERATURE}
    latest = live.get(f"/tsapi/stores/{STORE_T}/samples", params=params).json()
    assert latest["value"] == 2.0
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
    older = live.get(f"/tsapi/stores/{STORE_T}/samples", params={**params, "at": at}).json()
    assert older["value"] == 1.0
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 86400))
    oldest = live.get(f"/tsapi/stores/{STORE_T}/samples", params={**params, "at": at}).json()
    assert oldest["value"] == 0.0
    # Not found in the other store, nor before the first sample.
    assert live.get(f"/tsapi/stores/{STORE_H}/samples", params=params).status_code == 404
    response = live.get(f"/tsapi/stores/{STORE_T}/samples",
                        params={**params, "at": at, "max_age": 3600})
    assert response.status_code == 404

    series = live.get(f"/tsapi/stores/{STORE_T}/series", params={"ifdd_id": obj}).json()
    assert series == [{"store": STORE_T, "name": "temperature", "ifdd_id": obj,
                       "ifdd_property": TEMPERATURE, "ifdd_unit": DEG_C}]
    assert STORE_T in live.get("/tsapi/stores").json()


def test_range_bounds_are_included(live, vm_url):
    obj = _object()
    for t in ("2026-10-22T07:00:00.001Z", "2026-10-22T07:00:00.002Z", "2026-10-22T07:00:00.003Z"):
        live.post(f"/tsapi/stores/{STORE_T}/samples", json=sample(ifdd_id=obj, time=t))
    _flush(vm_url)
    params = {"ifdd_id": obj, "start": "2026-10-22T07:00:00.001Z",
              "end": "2026-10-22T07:00:00.002Z"}
    (series,) = live.get(f"/tsapi/stores/{STORE_T}/samples/range", params=params).json()
    assert [s["time"] for s in series["samples"]] == [
        "2026-10-22T07:00:00.001+00:00", "2026-10-22T07:00:00.002+00:00"]

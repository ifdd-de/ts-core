"""Test helpers: settings, a vocabulary, fakes of VictoriaMetrics and type."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx

TYPE_URL = "https://type/v1"
UNIT_URL = "https://unit/v1"
VM_URL = "http://vm.test:8428"
NAMESPACE = f"{TYPE_URL}/climate.ops.example.ifdd.de/"
TEMPERATURE = NAMESPACE + "temperature"
HUMIDITY = NAMESPACE + "relativeHumidity"
NOTE = NAMESPACE + "note"
DEG_C = f"{UNIT_URL}/unit/DEG_C"
PERCENT = f"{UNIT_URL}/unit/PERCENT_RH"
OBJECT = "https://rest/products/breaker-0001"
STORE_T = "temperature.ops.example.ifdd.de"
STORE_H = "humidity.ops.example.ifdd.de"

# Like the examples of the type template: a context with own term names and
# CURIEs; the bounds are given as CURIE keys.
VOCABULARY = {
    "@context": {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "sh": "http://www.w3.org/ns/shacl#",
        "qudt": "http://qudt.org/schema/qudt/",
        "owl": "http://www.w3.org/2002/07/owl#",
        "applicableUnit": {"@id": "qudt:applicableUnit", "@type": "@id", "@container": "@set"},
    },
    "@graph": [
        {"@id": NAMESPACE, "@type": "owl:Ontology"},
        {
            "@id": TEMPERATURE,
            "@type": "rdf:Property",
            "applicableUnit": [DEG_C],
            "sh:minInclusive": -60,
            "sh:maxInclusive": 120,
        },
        {
            "@id": HUMIDITY,
            "@type": "rdf:Property",
            "applicableUnit": [PERCENT],
            "sh:minInclusive": 0,
            "sh:maxInclusive": 100,
        },
        # A property without units and bounds: nothing to check.
        {"@id": NOTE, "@type": "rdf:Property"},
    ],
}


def settings(**overrides):
    from ifdd.ts.core.config import CoreSettings

    values = {
        "IFDD_TS_API_AUTH_ENABLED": False,
        "IFDD_TS_VM_URL": VM_URL,
        "IFDD_TYPE_URL": TYPE_URL,
    }
    values.update(overrides)
    return CoreSettings(**values)


def sample(**overrides):
    """A valid sample body for the temperature store."""
    body = {
        "name": "temperature",
        "ifdd_id": OBJECT,
        "ifdd_property": TEMPERATURE,
        "ifdd_unit": DEG_C,
        "time": "2026-10-22T09:15:00.250+02:00",
        "value": 21.5,
    }
    body.update(overrides)
    return body


class FakeServices:
    """VictoriaMetrics and the type service behind one mock transport.

    ``requests`` records every request; ``export_lines``, ``series_data``
    and ``store_values`` are the answers of the read endpoints; ``down``
    lets every call to that service fail.
    """

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.export_lines: list[dict] = []
        self.series_data: list[dict] = []
        self.store_values: list[str] = []
        self.vocabulary = VOCABULARY
        self.down: set[str] = set()

    def install(self):
        from ifdd.ts.core import http

        http.set_client(httpx.AsyncClient(transport=httpx.MockTransport(self.handle)))

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url.startswith(TYPE_URL):
            if "type" in self.down:
                raise httpx.ConnectError("type is down")
            if url.split("?")[0] == NAMESPACE:
                return httpx.Response(200, json=self.vocabulary)
            return httpx.Response(404, text="not found")
        if "vm" in self.down:
            raise httpx.ConnectError("vm is down")
        path = request.url.path
        if path == "/api/v1/import":
            return httpx.Response(204)
        if path == "/api/v1/export":
            body = "\n".join(json.dumps(line) for line in self.export_lines)
            return httpx.Response(200, text=body)
        if path == "/api/v1/series":
            return httpx.Response(200, json={"status": "success", "data": self.series_data})
        if path.startswith("/api/v1/label/ifdd_store/values"):
            return httpx.Response(200, json={"status": "success", "data": self.store_values})
        return httpx.Response(404)

    def vm_requests(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]

    @staticmethod
    def form(request: httpx.Request) -> dict:
        """Query and form parameters of a request."""
        values = parse_qs(request.url.query.decode())
        if request.content and request.headers.get("content-type", "").startswith(
            "application/x-www-form-urlencoded"
        ):
            for key, items in parse_qs(request.content.decode()).items():
                values.setdefault(key, []).extend(items)
        return values

    @staticmethod
    def imported(request: httpx.Request) -> list[dict]:
        return [json.loads(line) for line in request.content.decode().splitlines() if line]

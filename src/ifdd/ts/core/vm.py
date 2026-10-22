"""The calls to VictoriaMetrics.

Every call that reads or writes samples passes ``extra_label=ifdd_store=<store>``.
VictoriaMetrics then sets the label on every imported sample (overriding a
label of the same name in the body) and adds it as a required filter to
every read. That parameter is the only thing that keeps the stores apart; a
test in this package fails without it.

Endpoints used (checked against VictoriaMetrics v1.153.0):

==================================  ======================================
``POST /api/v1/import``             write samples (JSON lines)
``POST /api/v1/export``             raw samples of matching series (JSON lines)
``POST /api/v1/series``             label sets of matching series
``GET /api/v1/label/.../values``    values of ``ifdd_store``
==================================  ======================================

Times are passed as seconds with three decimals; ``start`` and ``end`` of
``export`` both include their bounds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, Optional

import httpx

from .config import get_settings
from .http import get_client
from .stores import STORE_LABEL
from .times import vm_time

# The labels of a series besides the store (series contract of ifdd-ts).
SERIES_LABELS = ("ifdd_id", "ifdd_property", "ifdd_unit")


class VMUnavailable(RuntimeError):
    """VictoriaMetrics could not be reached or refused a call (HTTP 502)."""


@dataclass(frozen=True)
class SeriesKey:
    """The identity of a series within a store."""

    name: str
    ifdd_id: str
    ifdd_property: str
    ifdd_unit: str

    @classmethod
    def from_metric(cls, metric: dict) -> "SeriesKey":
        """From the label set VictoriaMetrics returns."""
        return cls(
            name=metric.get("__name__", ""),
            ifdd_id=metric.get("ifdd_id", ""),
            ifdd_property=metric.get("ifdd_property", ""),
            ifdd_unit=metric.get("ifdd_unit", ""),
        )

    def metric(self) -> dict:
        """The label set to write (without the store, which the API sets)."""
        return {
            "__name__": self.name,
            "ifdd_id": self.ifdd_id,
            "ifdd_property": self.ifdd_property,
            "ifdd_unit": self.ifdd_unit,
        }


def _quote(value: str) -> str:
    """A label value as a quoted string of a series selector."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def selector(
    name: Optional[str] = None,
    ifdd_id: Optional[str] = None,
    ifdd_property: Optional[str] = None,
    ifdd_unit: Optional[str] = None,
) -> str:
    """A series selector of the given labels; without any, all series with ``ifdd_id``."""
    matchers = []
    if name:
        matchers.append(f"__name__={_quote(name)}")
    for label, value in (("ifdd_id", ifdd_id), ("ifdd_property", ifdd_property),
                         ("ifdd_unit", ifdd_unit)):
        if value:
            matchers.append(f"{label}={_quote(value)}")
    if not matchers:
        matchers.append('ifdd_id!=""')
    return "{" + ",".join(matchers) + "}"


def _store_filter(store: str) -> str:
    return f"{STORE_LABEL}={store}"


async def _call(method: str, path: str, **kwargs) -> httpx.Response:
    settings = get_settings()
    url = settings.IFDD_TS_VM_URL.rstrip("/") + path
    try:
        response = await get_client().request(
            method, url, timeout=settings.IFDD_TS_VM_TIMEOUT, **kwargs
        )
    except httpx.HTTPError as error:
        raise VMUnavailable(f"VictoriaMetrics {path}: {error!r}") from None
    if response.status_code >= 400:
        raise VMUnavailable(
            f"VictoriaMetrics {path}: HTTP {response.status_code} {response.text[:300]}"
        )
    return response


async def import_samples(store: str, samples: Iterable[tuple[SeriesKey, int, float]]) -> int:
    """Write samples to a store.

    Args:
        store: The store; set as label on every sample.
        samples: (series, time in ms, value) triples.

    Returns:
        The number of samples sent.
    """
    lines: dict[SeriesKey, dict] = {}
    count = 0
    for key, timestamp, value in samples:
        line = lines.setdefault(key, {"metric": key.metric(), "values": [], "timestamps": []})
        line["values"].append(value)
        line["timestamps"].append(timestamp)
        count += 1
    body = "\n".join(json.dumps(line, separators=(",", ":")) for line in lines.values())
    await _call(
        "POST",
        "/api/v1/import",
        params={"extra_label": _store_filter(store)},
        content=body.encode(),
        headers={"Content-Type": "application/stream+json"},
    )
    return count


async def export(store: str, match: str, start: int, end: int) -> list[tuple[SeriesKey, list[tuple[int, float]]]]:
    """Raw samples of the matching series of a store in ``[start, end]`` (ms).

    Returns:
        Per series its key and its (time in ms, value) pairs, sorted by time.
    """
    response = await _call(
        "POST",
        "/api/v1/export",
        data={
            "match[]": match,
            "start": vm_time(start),
            "end": vm_time(end),
            "extra_label": _store_filter(store),
        },
    )
    result = []
    for line in response.text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        points = sorted(zip(item.get("timestamps", []), item.get("values", [])))
        result.append((SeriesKey.from_metric(item.get("metric", {})), points))
    result.sort(key=lambda entry: (entry[0].name, entry[0].ifdd_id, entry[0].ifdd_property,
                                   entry[0].ifdd_unit))
    return result


async def series(store: str, match: str, start: int, end: int, limit: int) -> list[SeriesKey]:
    """The series of a store that match and have samples in ``[start, end]`` (ms).

    At most ``limit`` series are returned.
    """
    response = await _call(
        "POST",
        "/api/v1/series",
        data={
            "match[]": match,
            "start": vm_time(start),
            "end": vm_time(end),
            "limit": str(limit),
            "extra_label": _store_filter(store),
        },
    )
    keys = {SeriesKey.from_metric(metric) for metric in response.json().get("data", [])}
    return sorted(keys, key=lambda k: (k.name, k.ifdd_id, k.ifdd_property, k.ifdd_unit))


async def store_names(start: int, end: int) -> list[str]:
    """The values of ``ifdd_store`` with samples in ``[start, end]`` (ms)."""
    response = await _call(
        "GET",
        f"/api/v1/label/{STORE_LABEL}/values",
        params={"start": vm_time(start), "end": vm_time(end)},
    )
    return sorted(response.json().get("data", []))

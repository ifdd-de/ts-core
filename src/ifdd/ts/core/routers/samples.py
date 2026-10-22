"""Stores, series and samples.

Every endpoint below ``/stores/{store}`` first checks, in this order: a
valid token (401), a valid store name (422), the role (403) and a store
pattern of the client that matches the store (403).
"""

from __future__ import annotations

import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Path, Query

from .. import schemas, vm
from ..auth import token_claims
from ..config import get_settings
from ..errors import InvalidRequest, NotFound
from ..openapi import error_responses
from ..stores import Access, Forbidden, check_store_name, is_store_name
from ..times import format_time, parse_time
from ..vocabulary import VocabularyError, rule_for

router = APIRouter(prefix="/stores")

DAY_MS = 86_400_000
# Windows in which the latest sample is searched, smallest first.
LATEST_WINDOWS_MS = (3_600_000, DAY_MS, 30 * DAY_MS, 366 * DAY_MS)

StorePath = Annotated[
    str,
    Path(
        description="Name of the store, e.g. `temperature.ops.example.ifdd.de`.",
        examples=[schemas.EXAMPLE_STORE],
    ),
]
NameQuery = Annotated[Optional[str], Query(description="Metric name.")]
IdQuery = Annotated[Optional[str], Query(description="Full IRI of the object.")]
PropertyQuery = Annotated[Optional[str], Query(description="Full IRI of the property.")]
UnitQuery = Annotated[Optional[str], Query(description="Full IRI of the unit.")]
StartQuery = Annotated[
    Optional[str],
    Query(description="ISO 8601 with offset; default: `IFDD_TS_DEFAULT_RANGE_DAYS` before `end`."),
]
EndQuery = Annotated[Optional[str], Query(description="ISO 8601 with offset; default: now.")]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _check(value: Optional[str], check, label: str) -> Optional[str]:
    if value is None:
        return None
    try:
        return check(value)
    except ValueError as error:
        raise InvalidRequest(f"{label}: {error}") from None


def _filters(name, ifdd_id, ifdd_property, ifdd_unit) -> str:
    return vm.selector(
        name=_check(name, schemas.check_name, "name"),
        ifdd_id=_check(ifdd_id, schemas.check_iri, "ifdd_id"),
        ifdd_property=_check(ifdd_property, schemas.check_iri, "ifdd_property"),
        ifdd_unit=_check(ifdd_unit, schemas.check_iri, "ifdd_unit"),
    )


def _range(start: Optional[str], end: Optional[str]) -> tuple[int, int]:
    end_ms = parse_time(end) if end is not None else _now_ms()
    if start is not None:
        start_ms = parse_time(start)
    else:
        start_ms = max(0, end_ms - get_settings().IFDD_TS_DEFAULT_RANGE_DAYS * DAY_MS)
    if start_ms > end_ms:
        raise InvalidRequest("start is after end")
    return start_ms, end_ms


def _series_out(store: str, key: vm.SeriesKey) -> dict:
    return {"store": store, "name": key.name, "ifdd_id": key.ifdd_id,
            "ifdd_property": key.ifdd_property, "ifdd_unit": key.ifdd_unit}


async def readable_store(store: StorePath, claims: dict = Depends(token_claims)) -> str:
    """Dependency: the store, if the client may read it."""
    check_store_name(store)
    Access.from_token(claims).require_read(store)
    return store


async def writable_store(store: StorePath, claims: dict = Depends(token_claims)) -> str:
    """Dependency: the store, if the client may write to it."""
    check_store_name(store)
    Access.from_token(claims).require_write(store)
    return store


async def _check_vocabulary(samples: list[schemas.SampleIn]) -> None:
    """Check every sample against the type service; 422 with all problems."""
    problems = []
    for index, sample in enumerate(samples):
        try:
            rule = await rule_for(sample.ifdd_property)
            rule.check(sample.ifdd_unit, sample.value)
        except VocabularyError as error:
            problems.append(f"samples[{index}]: {error}")
    if problems:
        shown = problems[:20]
        if len(problems) > len(shown):
            shown.append(f"... and {len(problems) - len(shown)} more")
        raise VocabularyError("; ".join(shown))


@router.get(
    "",
    tags=["stores"],
    response_model=list[str],
    summary="Stores the client may read",
    responses={
        200: {"content": {"application/json": {"example": [schemas.EXAMPLE_STORE]}}},
        **error_responses(401, 403, 422, 502),
    },
)
async def list_stores(
    start: StartQuery = None,
    end: EndQuery = None,
    claims: dict = Depends(token_claims),
) -> list[str]:
    """List the stores with samples in the time range that the client may read.

    Needs the read role. Stores without a matching store pattern are left
    out silently.
    """
    access = Access.from_token(claims)
    role = get_settings().IFDD_TS_ROLE_READ
    if role not in access.roles:
        raise Forbidden(f"Insufficient permissions. Role {role} required.")
    start_ms, end_ms = _range(start, end)
    names = await vm.store_names(start_ms, end_ms)
    return [name for name in names if is_store_name(name) and access.may_use(name)]


@router.get(
    "/{store}/series",
    tags=["series"],
    response_model=list[schemas.SeriesOut],
    summary="Series of a store",
    responses=error_responses(401, 403, 422, 502),
)
async def list_series(
    store: str = Depends(readable_store),
    name: NameQuery = None,
    ifdd_id: IdQuery = None,
    ifdd_property: PropertyQuery = None,
    ifdd_unit: UnitQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
) -> list[dict]:
    """List the series of a store with samples in the time range.

    All filters are optional and exact. More than `IFDD_TS_MAX_ITEMS`
    series answer 422: narrow the filters.
    """
    match = _filters(name, ifdd_id, ifdd_property, ifdd_unit)
    start_ms, end_ms = _range(start, end)
    limit = get_settings().IFDD_TS_MAX_ITEMS
    keys = await vm.series(store, match, start_ms, end_ms, limit + 1)
    if len(keys) > limit:
        raise InvalidRequest(f"more than {limit} series match; narrow the filters")
    return [_series_out(store, key) for key in keys]


@router.get(
    "/{store}/samples",
    tags=["samples"],
    response_model=schemas.SampleOut,
    summary="The latest sample of a series at a time",
    responses=error_responses(401, 403, 404, 422, 502),
)
async def latest_sample(
    ifdd_id: Annotated[str, Query(description="Full IRI of the object.")],
    ifdd_property: Annotated[str, Query(description="Full IRI of the property.")],
    store: str = Depends(readable_store),
    name: NameQuery = None,
    ifdd_unit: UnitQuery = None,
    at: Annotated[
        Optional[str], Query(description="ISO 8601 with offset; default: now.")
    ] = None,
    max_age: Annotated[
        Optional[int],
        Query(ge=1, description="Search at most this many seconds before `at`; "
              "default: `IFDD_TS_LOOKBACK_DAYS`."),
    ] = None,
) -> dict:
    """Return the last sample at or before `at` of exactly one series.

    `ifdd_id` and `ifdd_property` are required; give `name` and `ifdd_unit`
    too if several series share them (422 names the candidates). 404 if the
    series has no sample in the searched time.
    """
    match = _filters(name, ifdd_id, ifdd_property, ifdd_unit)
    at_ms = parse_time(at) if at is not None else _now_ms()
    settings = get_settings()
    lookback = max_age * 1000 if max_age else settings.IFDD_TS_LOOKBACK_DAYS * DAY_MS
    oldest = max(0, at_ms - lookback)
    keys = await vm.series(store, match, oldest, at_ms, 2)
    if len(keys) > 1:
        names = ", ".join(f"{k.name} [{k.ifdd_unit}]" for k in keys)
        raise InvalidRequest(f"several series match ({names}, ...); give name and ifdd_unit")
    if not keys:
        raise NotFound("no sample of this series in the searched time")
    windows = [w for w in LATEST_WINDOWS_MS if w < lookback] + [lookback]
    for window in windows:
        found = await vm.export(store, match, max(0, at_ms - window), at_ms)
        points = [point for _, series_points in found for point in series_points]
        if points:
            key = found[0][0]
            timestamp, value = max(points)
            return {**_series_out(store, key), "time": format_time(timestamp), "value": value}
    raise NotFound("no sample of this series in the searched time")


@router.get(
    "/{store}/samples/range",
    tags=["samples"],
    response_model=list[schemas.SeriesSamples],
    summary="Raw samples of the series of an object in a time range",
    responses=error_responses(401, 403, 422, 502),
)
async def sample_range(
    ifdd_id: Annotated[str, Query(description="Full IRI of the object.")],
    start: Annotated[str, Query(description="ISO 8601 with offset (included).")],
    store: str = Depends(readable_store),
    end: Annotated[
        Optional[str], Query(description="ISO 8601 with offset (included); default: now.")
    ] = None,
    name: NameQuery = None,
    ifdd_property: PropertyQuery = None,
    ifdd_unit: UnitQuery = None,
) -> list[dict]:
    """Return every stored sample of the matching series in `[start, end]`.

    The values are the stored ones, not interpolated. More than
    `IFDD_TS_MAX_ITEMS` samples in total answer 422: shorten the range.
    """
    match = _filters(name, ifdd_id, ifdd_property, ifdd_unit)
    start_ms, end_ms = _range(start, end)
    found = await vm.export(store, match, start_ms, end_ms)
    limit = get_settings().IFDD_TS_MAX_ITEMS
    total = sum(len(points) for _, points in found)
    if total > limit:
        raise InvalidRequest(f"{total} samples match, more than {limit}; shorten the range")
    return [
        {
            **_series_out(store, key),
            "samples": [{"time": format_time(t), "value": v} for t, v in points],
        }
        for key, points in found
    ]


@router.post(
    "/{store}/samples",
    tags=["samples"],
    response_model=schemas.Written,
    summary="Write one sample",
    responses=error_responses(401, 403, 422, 502),
)
async def write_sample(
    sample: schemas.SampleIn,
    store: str = Depends(writable_store),
) -> dict:
    """Append one sample to a series of the store.

    Needs the write role. The property, unit and value are checked against
    the vocabulary in the type service. A sample with the same series and
    time as a stored one does not replace it; the time series database keeps
    the larger value (see the introduction).
    """
    await _check_vocabulary([sample])
    key = vm.SeriesKey(sample.name, sample.ifdd_id, sample.ifdd_property, sample.ifdd_unit)
    written = await vm.import_samples(store, [(key, sample.milliseconds, sample.value)])
    return {"written": written}


@router.post(
    "/{store}/samples/batch",
    tags=["samples"],
    response_model=schemas.Written,
    summary="Write a list of samples",
    responses=error_responses(401, 403, 422, 502),
)
async def write_batch(
    batch: schemas.BatchIn,
    store: str = Depends(writable_store),
) -> dict:
    """Append up to `IFDD_TS_MAX_ITEMS` samples, of one or several series.

    Every sample is checked first; one bad sample refuses the whole list
    (422, naming each problem by its index), and nothing is written.
    """
    limit = get_settings().IFDD_TS_MAX_ITEMS
    if len(batch.samples) > limit:
        raise InvalidRequest(f"{len(batch.samples)} samples, more than {limit}; split the list")
    await _check_vocabulary(batch.samples)
    written = await vm.import_samples(
        store,
        (
            (vm.SeriesKey(s.name, s.ifdd_id, s.ifdd_property, s.ifdd_unit), s.milliseconds, s.value)
            for s in batch.samples
        ),
    )
    return {"written": written}

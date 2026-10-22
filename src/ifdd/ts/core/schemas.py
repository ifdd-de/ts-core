"""Request and response bodies.

A series is named by four labels (the series contract of ifdd-ts):

=================  ================================================
``name``           metric name, only for people, e.g. ``temperature``
``ifdd_id``        full IRI of the object in ifdd-be
``ifdd_property``  full IRI of the property in the type service
``ifdd_unit``      full IRI of the unit in the unit service
=================  ================================================

The store is part of the path and set by the API. No further labels are
accepted, which keeps the number of series bounded.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .times import TimeError, parse_time

NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
IRI = re.compile(r"^https?://[^\s\"<>\\^`{|}]+$")
MAX_IRI_LENGTH = 2048

EXAMPLE_ID = "https://rest/products/3f2b6c1e-0a4d-4f7e-9b1a-2c5d8e7f6a90"
EXAMPLE_PROPERTY = "https://type/v1/climate.ops.example.ifdd.de/temperature"
EXAMPLE_UNIT = "https://unit/v1/unit/DEG_C"
EXAMPLE_STORE = "temperature.ops.example.ifdd.de"
EXAMPLE_TIME = "2026-10-22T09:15:00.000+00:00"

NameField = Annotated[
    str,
    Field(
        description="Metric name, only for people (letters, digits, `_`; not starting "
        "with a digit or `__`).",
        examples=["temperature"],
    ),
]
IdField = Annotated[
    str, Field(description="Full IRI of the object in ifdd-be.", examples=[EXAMPLE_ID])
]
PropertyField = Annotated[
    str,
    Field(
        description="Full IRI of the property in a vocabulary of the type service.",
        examples=[EXAMPLE_PROPERTY],
    ),
]
UnitField = Annotated[
    str,
    Field(description="Full IRI of the unit in the unit service.", examples=[EXAMPLE_UNIT]),
]


def check_name(value: str) -> str:
    """A metric name the API accepts."""
    if not NAME.match(value) or value.startswith("__"):
        raise ValueError(
            "name must be letters, digits and '_', not start with a digit or '__'"
        )
    return value


def check_iri(value: str) -> str:
    """An absolute http(s) IRI without spaces or characters that need escaping."""
    if len(value) > MAX_IRI_LENGTH or not IRI.match(value):
        raise ValueError("must be an absolute http(s) IRI without spaces")
    return value


class SeriesLabels(BaseModel):
    """The labels that name a series within a store."""

    model_config = ConfigDict(extra="forbid")

    name: NameField
    ifdd_id: IdField
    ifdd_property: PropertyField
    ifdd_unit: UnitField

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return check_name(value)

    @field_validator("ifdd_id", "ifdd_property", "ifdd_unit")
    @classmethod
    def _iri(cls, value: str) -> str:
        return check_iri(value)


class SampleIn(SeriesLabels):
    """One sample to write."""

    time: str = Field(
        description="ISO 8601 with offset, at most millisecond precision.",
        examples=[EXAMPLE_TIME],
    )
    value: float = Field(
        strict=True, allow_inf_nan=False, description="The value (a finite number).",
        examples=[21.5],
    )

    @field_validator("time")
    @classmethod
    def _time(cls, value: str) -> str:
        try:
            parse_time(value)
        except TimeError as error:
            raise ValueError(str(error)) from None
        return value

    @property
    def milliseconds(self) -> int:
        """The time in milliseconds since the epoch."""
        return parse_time(self.time)


class BatchIn(BaseModel):
    """Several samples to write at once, for one or more series."""

    model_config = ConfigDict(extra="forbid")

    samples: list[SampleIn] = Field(min_length=1, description="The samples, in any order.")


class SeriesOut(BaseModel):
    """A series of a store."""

    store: str = Field(examples=[EXAMPLE_STORE])
    name: str = Field(examples=["temperature"])
    ifdd_id: str = Field(examples=[EXAMPLE_ID])
    ifdd_property: str = Field(examples=[EXAMPLE_PROPERTY])
    ifdd_unit: str = Field(examples=[EXAMPLE_UNIT])


class Point(BaseModel):
    """Time and value of one sample."""

    time: str = Field(examples=[EXAMPLE_TIME])
    value: float = Field(examples=[21.5])


class SampleOut(SeriesOut):
    """One sample with its series."""

    time: str = Field(examples=[EXAMPLE_TIME])
    value: float = Field(examples=[21.5])


class SeriesSamples(SeriesOut):
    """A series with its samples, sorted by time."""

    samples: list[Point]


class Written(BaseModel):
    """The answer to a write."""

    written: int = Field(description="Number of samples sent to the time series database.")


class WhoAmI(BaseModel):
    """What the API reads from the access token."""

    preferred_username: str | None = Field(
        default=None, examples=["service-account-ifdd-ts-ingest"]
    )
    client_roles: list[str] = Field(examples=[["ifdd_ts_ro", "ifdd_ts_rw"]])
    store_patterns: list[str] = Field(examples=[["ifdd.de"]])

"""Check samples against the vocabularies of the type service.

Every sample names its property with a full IRI (label ``ifdd_property``).
Before a sample is written, the API looks the property up in the vocabulary
of its namespace in the type service and checks:

* the property is below ``IFDD_TYPE_URL`` and the vocabulary defines it as an
  ``rdf:Property``;
* the unit (label ``ifdd_unit``) is one of its ``qudt:applicableUnit``, if the
  vocabulary lists any (without a list the unit is not checked);
* the value lies within ``sh:minInclusive`` and ``sh:maxInclusive``, where
  the vocabulary gives them.

The namespace of a property is its IRI up to the last ``/`` or ``#``; the
type service answers the namespace IRI with the vocabulary document
(``index.jsonld``). Vocabularies are read with a JSON-LD processor, so
prefixes and term names in the document do not matter; contexts must be
inline (a vocabulary that loads a remote context is refused). A vocabulary is
kept for ``IFDD_TS_VOCABULARY_CACHE_TTL`` seconds; failures are not kept.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import httpx
from cachetools import TTLCache
from pyld import jsonld

from .config import get_settings
from .http import get_client

RDF_TYPE_PROPERTY = "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property"
QUDT_APPLICABLE_UNIT = "http://qudt.org/schema/qudt/applicableUnit"
SH_MIN_INCLUSIVE = "http://www.w3.org/ns/shacl#minInclusive"
SH_MAX_INCLUSIVE = "http://www.w3.org/ns/shacl#maxInclusive"


class VocabularyError(ValueError):
    """A sample does not fit the vocabulary (HTTP 422)."""


class VocabularyUnavailable(RuntimeError):
    """The vocabulary could not be read (HTTP 502)."""


@dataclass(frozen=True)
class PropertyRule:
    """What the vocabulary says about one property."""

    iri: str
    units: frozenset[str]
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    def check(self, unit: str, value: float) -> None:
        """Raise :class:`VocabularyError` if unit or value do not fit."""
        if self.units and unit not in self.units:
            raise VocabularyError(
                f"unit {unit!r} is not applicable to {self.iri!r}; "
                f"use one of {sorted(self.units)}"
            )
        if self.minimum is not None and value < self.minimum:
            raise VocabularyError(f"value {value} of {self.iri!r} is below {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise VocabularyError(f"value {value} of {self.iri!r} is above {self.maximum}")


_cache: Optional[TTLCache] = None


def reset_cache() -> None:
    """Forget all vocabularies (for tests)."""
    global _cache
    _cache = None


def _get_cache() -> TTLCache:
    global _cache
    if _cache is None:
        _cache = TTLCache(maxsize=256, ttl=get_settings().IFDD_TS_VOCABULARY_CACHE_TTL)
    return _cache


def namespace_of(iri: str) -> str:
    """The IRI up to and including its last ``/`` or ``#``.

    Raises:
        VocabularyError: The IRI is not below ``IFDD_TYPE_URL``.
    """
    base = get_settings().IFDD_TYPE_URL.rstrip("/") + "/"
    if not iri.startswith(base) or len(iri) == len(base):
        raise VocabularyError(f"property {iri!r} is not below the type service {base}")
    cut = max(iri.rfind("/"), iri.rfind("#"))
    if cut < len(base) - 1 or cut == len(iri) - 1:
        raise VocabularyError(f"{iri!r} does not name a property in a vocabulary")
    return iri[: cut + 1]


def _no_remote_contexts(url, options=None):
    raise jsonld.JsonLdError(
        f"remote context {url!r}: vocabularies must define their context inline",
        "jsonld.LoadDocumentError",
    )


def _number(values) -> Optional[float]:
    """The first numeric ``@value`` of an expanded property, or None."""
    for value in values or ():
        raw = value.get("@value") if isinstance(value, dict) else None
        if isinstance(raw, bool):
            continue
        try:
            number = float(raw)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def parse_vocabulary(document: dict) -> dict[str, PropertyRule]:
    """The properties of a vocabulary document, by IRI.

    Raises:
        VocabularyUnavailable: The document is not valid JSON-LD.
    """
    try:
        nodes = jsonld.expand(document, {"documentLoader": _no_remote_contexts})
    except jsonld.JsonLdError as error:
        if "remote context" in str(getattr(error, "code", "")):
            raise VocabularyUnavailable(
                "the vocabulary loads a remote context; vocabularies must define "
                "their context inline"
            ) from None
        raise VocabularyUnavailable(f"the vocabulary is not valid JSON-LD: {error}") from None
    rules = {}
    for node in nodes:
        if RDF_TYPE_PROPERTY not in node.get("@type", ()) or "@id" not in node:
            continue
        units = frozenset(
            unit["@id"] for unit in node.get(QUDT_APPLICABLE_UNIT, ()) if "@id" in unit
        )
        rules[node["@id"]] = PropertyRule(
            iri=node["@id"],
            units=units,
            minimum=_number(node.get(SH_MIN_INCLUSIVE)),
            maximum=_number(node.get(SH_MAX_INCLUSIVE)),
        )
    return rules


async def _load(namespace: str) -> dict[str, PropertyRule]:
    settings = get_settings()
    url = namespace.rstrip("#")
    try:
        response = await get_client().get(
            url,
            headers={"Accept": "application/ld+json, application/json"},
            timeout=settings.IFDD_TS_VOCABULARY_TIMEOUT,
        )
    except httpx.HTTPError as error:
        raise VocabularyUnavailable(f"vocabulary {url}: {error!r}") from None
    if response.status_code == 404:
        raise VocabularyError(f"the type service has no vocabulary {namespace!r}")
    if response.status_code != 200:
        raise VocabularyUnavailable(f"vocabulary {url}: HTTP {response.status_code}")
    try:
        document = response.json()
    except ValueError:
        raise VocabularyUnavailable(f"vocabulary {url}: not JSON") from None
    if not isinstance(document, dict):
        raise VocabularyUnavailable(f"vocabulary {url}: not a JSON-LD document")
    return parse_vocabulary(document)


async def rule_for(property_iri: str) -> PropertyRule:
    """The rule of a property, from the (cached) vocabulary of its namespace.

    Raises:
        VocabularyError: Not below the type service, no such vocabulary, or
            the vocabulary does not define the property.
        VocabularyUnavailable: The type service could not be read.
    """
    namespace = namespace_of(property_iri)
    cache = _get_cache()
    rules = cache.get(namespace)
    if rules is None:
        rules = await _load(namespace)
        cache[namespace] = rules
    rule = rules.get(property_iri)
    if rule is None:
        raise VocabularyError(f"the vocabulary {namespace!r} defines no property {property_iri!r}")
    return rule

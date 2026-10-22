import pytest

from ifdd.ts.core import vocabulary
from ifdd.ts.core.config import configure
from ifdd.ts.core.vocabulary import (
    VocabularyError,
    VocabularyUnavailable,
    namespace_of,
    parse_vocabulary,
    rule_for,
)
from support import DEG_C, HUMIDITY, NAMESPACE, NOTE, PERCENT, TEMPERATURE, TYPE_URL, VOCABULARY, settings


@pytest.fixture(autouse=True)
def _settings():
    configure(settings())


def test_namespace_of_slash_and_hash():
    assert namespace_of(TEMPERATURE) == NAMESPACE
    assert namespace_of(f"{TYPE_URL}/ns#prop") == f"{TYPE_URL}/ns#"


@pytest.mark.parametrize(
    "iri",
    [
        "https://elsewhere/v1/ns/prop",  # not below the type service
        "https://type/v10/ns/prop",  # only a common prefix
        f"{TYPE_URL}/ns/",  # a namespace, not a property
        f"{TYPE_URL}/",
    ],
)
def test_iris_outside_the_type_service_are_refused(iri):
    with pytest.raises(VocabularyError):
        namespace_of(iri)


def test_parse_reads_units_and_bounds_through_any_prefixes():
    rules = parse_vocabulary(VOCABULARY)
    assert rules[TEMPERATURE].units == {DEG_C}
    assert (rules[TEMPERATURE].minimum, rules[TEMPERATURE].maximum) == (-60, 120)
    assert rules[HUMIDITY].units == {PERCENT}
    assert rules[NOTE].units == frozenset() and rules[NOTE].minimum is None
    assert NAMESPACE not in rules  # the ontology node is no property


def test_typed_literal_bounds():
    document = {
        "@graph": [
            {
                "@id": TEMPERATURE,
                "@type": "http://www.w3.org/1999/02/22-rdf-syntax-ns#Property",
                "http://www.w3.org/ns/shacl#maxInclusive": {
                    "@value": "40.5",
                    "@type": "http://www.w3.org/2001/XMLSchema#decimal",
                },
            }
        ]
    }
    assert parse_vocabulary(document)[TEMPERATURE].maximum == 40.5


def test_remote_contexts_are_refused():
    with pytest.raises(VocabularyUnavailable, match="inline"):
        parse_vocabulary({"@context": "https://elsewhere/context.jsonld", "@id": TEMPERATURE})


def test_checks():
    rule = parse_vocabulary(VOCABULARY)[TEMPERATURE]
    rule.check(DEG_C, 21.5)
    rule.check(DEG_C, -60)
    rule.check(DEG_C, 120)
    with pytest.raises(VocabularyError, match="not applicable"):
        rule.check(PERCENT, 21.5)
    with pytest.raises(VocabularyError, match="below"):
        rule.check(DEG_C, -60.1)
    with pytest.raises(VocabularyError, match="above"):
        rule.check(DEG_C, 120.1)
    parse_vocabulary(VOCABULARY)[NOTE].check("https://unit/v1/unit/anything", 1e300)


async def test_rule_for_loads_once_and_caches(services):
    services.install()
    await rule_for(TEMPERATURE)
    await rule_for(HUMIDITY)
    assert len(services.requests) == 1
    assert str(services.requests[0].url) == NAMESPACE


async def test_unknown_property_and_vocabulary(services):
    services.install()
    with pytest.raises(VocabularyError, match="defines no property"):
        await rule_for(NAMESPACE + "pressure")
    with pytest.raises(VocabularyError, match="no vocabulary"):
        await rule_for(f"{TYPE_URL}/other.ops.example.ifdd.de/x")


async def test_failures_are_not_cached(services):
    services.install()
    services.down.add("type")
    with pytest.raises(VocabularyUnavailable):
        await rule_for(TEMPERATURE)
    services.down.clear()
    assert (await rule_for(TEMPERATURE)).units == {DEG_C}
    assert vocabulary._get_cache().currsize == 1

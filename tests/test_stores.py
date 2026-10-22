import pytest

from ifdd.ts.core.stores import Access, Forbidden, StoreNameError, check_store_name, is_store_name, matches
from support import settings


@pytest.mark.parametrize(
    "name", ["ops.example", "temperature.ops.example.ifdd.de", "a-1.b2", "x.y.z"]
)
def test_valid_store_names(name):
    assert is_store_name(name)


@pytest.mark.parametrize(
    "name", ["single", "Upper.case", "-x.y", "x-.y", "x..y", "x.y.", ".x.y", "x_y.z", ""]
)
def test_invalid_store_names(name):
    assert not is_store_name(name)
    with pytest.raises(StoreNameError):
        check_store_name(name)


def test_patterns_match_at_label_boundaries():
    assert matches("temperature.ops.example.ifdd.de", "ops.example.ifdd.de")
    assert matches("ops.example.ifdd.de", "ops.example.ifdd.de")
    assert not matches("xops.example.ifdd.de", "ops.example.ifdd.de")
    assert not matches("example.ifdd.de", "ops.example.ifdd.de")


def _access(roles):
    from ifdd.ts.core.config import configure

    configure(settings(IFDD_TS_API_AUTH_ENABLED=True))
    return Access.from_token({"resource_access": {"ifdd-ts-api": {"roles": roles}}})


def test_roles_and_patterns_are_split_at_the_dot():
    access = _access(["ifdd_ts_ro", "Temperature.Ops.Example.ifdd.de"])
    assert access.roles == {"ifdd_ts_ro"}
    assert access.patterns == ("temperature.ops.example.ifdd.de",)


def test_roles_of_other_clients_do_not_count():
    from ifdd.ts.core.config import configure

    configure(settings(IFDD_TS_API_AUTH_ENABLED=True))
    access = Access.from_token(
        {"resource_access": {"ifddtest": {"roles": ["ifdd_ts_ro", "ifdd.de"]}}}
    )
    assert not access.roles and not access.patterns


def test_read_needs_role_and_pattern():
    access = _access(["ifdd_ts_ro", "temperature.ops.example.ifdd.de"])
    access.require_read("temperature.ops.example.ifdd.de")
    with pytest.raises(Forbidden, match="no store pattern"):
        access.require_read("humidity.ops.example.ifdd.de")
    with pytest.raises(Forbidden, match="ifdd_ts_rw"):
        access.require_write("temperature.ops.example.ifdd.de")


def test_root_opens_every_store():
    access = _access(["ifdd_ts_rw", "ifdd.de"])
    access.require_write("humidity.ops.example.ifdd.de")
    assert not access.can_read("humidity.ops.example.ifdd.de")

import pytest

from ifdd.ts.core.times import TimeError, format_time, parse_time, vm_time


def test_offset_and_z_give_the_same_instant():
    assert parse_time("2026-10-22T09:15:00+02:00") == parse_time("2026-10-22T07:15:00Z")


def test_milliseconds_are_kept():
    assert parse_time("1970-01-01T00:00:01.250Z") == 1250


@pytest.mark.parametrize(
    "value",
    [
        "2026-10-22T09:15:00",  # no offset
        "2026-10-22",  # date only, no offset
        "2026-10-22T09:15:00.0001Z",  # finer than a millisecond
        "1969-12-31T23:59:59Z",  # before the epoch
        "yesterday",
        "",
    ],
)
def test_refused_times(value):
    with pytest.raises(TimeError):
        parse_time(value)


def test_non_string_is_refused():
    with pytest.raises(TimeError):
        parse_time(1790000000)


def test_answers_are_utc_with_three_decimals():
    assert format_time(1250) == "1970-01-01T00:00:01.250+00:00"
    assert format_time(parse_time("2026-10-22T09:15:00+02:00")) == "2026-10-22T07:15:00.000+00:00"


def test_round_trip():
    ms = parse_time("2026-10-22T07:15:00.007Z")
    assert parse_time(format_time(ms)) == ms


def test_vm_time_is_exact():
    assert vm_time(1792662284007) == "1792662284.007"
    assert vm_time(0) == "0.000"

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from pycuf.values import parse_bool, parse_date, parse_datetime, parse_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("111", Decimal(111)),
        ("3.14", Decimal("3.14")),
        ("-123.456E+10", Decimal("-123.456E+10")),
        (" 12.5 ", Decimal("12.5")),
        (".5", Decimal("0.5")),
        ("65800.0000000009", Decimal("65800.0000000009")),
    ],
)
def test_numbers(text: str, expected: Decimal) -> None:
    assert parse_number(text) == (expected, False)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "1_000", "1.000,50", "١٢", "12,5", "", "x"])
def test_invalid_numbers(text: str) -> None:
    assert parse_number(text)[0] is None


def test_decimal_comma_is_opt_in() -> None:
    assert parse_number("12,5", decimal_comma=True) == (Decimal("12.5"), True)
    assert parse_number("1.000,5", decimal_comma=True)[0] is None


def test_dates() -> None:
    assert parse_date("2006-10-30") == (dt.date(2006, 10, 30), False)
    assert parse_date("3-5-2024") == (None, False)
    assert parse_date("3-5-2024", dutch=True) == (dt.date(2024, 5, 3), True)
    assert parse_date("2006-02-30")[0] is None


def test_datetimes() -> None:
    assert parse_datetime("2003-01-31T15:58:00")[0] == dt.datetime(2003, 1, 31, 15, 58)
    assert parse_datetime("2003-01-31")[0] == dt.datetime(2003, 1, 31)
    assert parse_datetime("2003-01-31T15:58:00.123456789")[0] == dt.datetime(
        2003, 1, 31, 15, 58, 0, 123456
    )
    assert parse_datetime("3-5-2024 13:10:29", dutch=True) == (
        dt.datetime(2024, 5, 3, 13, 10, 29),
        True,
    )
    assert parse_datetime("2003-01-31T15:58:00+01:00")[0] is None


def test_booleans() -> None:
    assert parse_bool("1") is True
    assert parse_bool("0") is False
    assert parse_bool("true") is True
    assert parse_bool("ja") is None

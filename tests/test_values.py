from __future__ import annotations

import datetime as dt
import decimal
from decimal import Decimal

import pytest

from pycuf.values import (
    MAX_DECIMALS,
    NUMBER_MAX,
    NUMBER_MIN,
    in_range,
    is_number,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_number,
)


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


@pytest.mark.parametrize(
    "text",
    [
        "1.7976931348623157E+308",
        "-1.7976931348623157E+308",
        "2.2250738585072014E-308",
        "0E+1000000000000",  # zero: magnitude and decimals both fine
        pytest.param("0." + "0" * MAX_DECIMALS, id="max-decimals"),
        pytest.param("9" * 300 + "." + "9" * MAX_DECIMALS, id="long"),
    ],
)
def test_numbers_at_the_edges_of_the_range(text: str) -> None:
    value, _ = parse_number(text)
    assert value == Decimal(text) and in_range(value)


@pytest.mark.parametrize(
    "text",
    [
        "1.7976931348623158E+308",
        "1e309",
        "-1e309",
        "2.2250738585072013E-308",
        "1e-1000100",  # used to become 0 in calculations, silently
        "1e1000000",  # used to overflow in validation
        "1e999999999999999999999999",  # used to raise InvalidOperation
        "0e-1000000000000",  # used to blow up CSV and Arrow exports
        pytest.param("0." + "0" * (MAX_DECIMALS + 1), id="too-many-decimals"),
        pytest.param("1." + "0" * 2000, id="one-with-too-many-decimals"),
        pytest.param("9" * 5000, id="too-large"),
    ],
)
def test_numbers_out_of_range(text: str) -> None:
    assert parse_number(text) == (None, False)
    assert is_number(text)


def test_number_parsing_ignores_the_callers_context() -> None:
    with decimal.localcontext(prec=3, Emax=3, Emin=-3) as ctx:
        ctx.traps[decimal.InvalidOperation] = False
        assert parse_number("123456789.125") == (Decimal("123456789.125"), False)
        assert parse_number("1e999999999999999999999999") == (None, False)  # not NaN
        assert parse_number("1e-400") == (None, False)
        assert in_range(NUMBER_MAX) and in_range(-NUMBER_MIN)


def test_is_number() -> None:
    assert is_number(" 1e999 ") and not is_number("x") and not is_number("12,5")
    assert is_number("12,5", decimal_comma=True)


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

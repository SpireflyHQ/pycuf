from __future__ import annotations

import dataclasses
import decimal
from decimal import Decimal

import pytest

from pycuf.policy import (
    DEFAULT,
    ERP,
    PRESETS,
    USAGE_RULES,
    Policy,
    _PolicyChanges,
    resolve_policy,
)


def test_presets() -> None:
    assert DEFAULT is USAGE_RULES == Policy()
    assert PRESETS["erp"] is ERP and ERP.labour == "erp"
    assert resolve_policy("schema").zero_factor == "zero"
    assert resolve_policy(None, ERP) is ERP


def test_replace_validates_and_converts() -> None:
    p = ERP.replace(abs_tol="0.05")  # type: ignore[arg-type]
    assert p.abs_tol == Decimal("0.05") and p.labour == "erp"
    assert hash(p) == hash(ERP.replace(abs_tol=Decimal("0.05")))
    with pytest.raises(ValueError, match="labour='ERP'"):
        Policy(labour="ERP")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="float"):
        Policy(abs_tol=0.05)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=">= 0"):
        Policy(rel_tol=Decimal(-1))
    with pytest.raises(ValueError, match="< 1"):
        Policy(rel_tol=Decimal(1))
    with pytest.raises(dataclasses.FrozenInstanceError):
        ERP.labour = "spec"  # type: ignore[misc]


def test_changes_typeddict_matches_fields() -> None:
    assert set(_PolicyChanges.__annotations__) == {f.name for f in dataclasses.fields(Policy)}


def test_resolve_errors() -> None:
    with pytest.raises(ValueError, match="'epr'"):
        resolve_policy("epr")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        resolve_policy(42)  # type: ignore[arg-type]


def test_rounding_accepts_decimal_constants() -> None:
    assert Policy(rounding=decimal.ROUND_HALF_EVEN).rounding == "ROUND_HALF_EVEN"


def test_agrees() -> None:
    p = Policy()
    assert p.agrees(Decimal("100.00"), Decimal("100.004"))
    assert not p.agrees(Decimal("100.00"), Decimal("100.015"))
    assert Policy(rounding="ROUND_HALF_UP", abs_tol=Decimal(0)).agrees(
        Decimal("125.95"), Decimal("125.945")
    )
    assert not Policy(rounding="ROUND_HALF_EVEN", abs_tol=Decimal(0)).agrees(
        Decimal("125.95"), Decimal("125.945")
    )
    assert Policy(rel_tol=Decimal("0.01")).agrees(Decimal(1000), Decimal(1009))


@pytest.mark.parametrize(
    ("stated", "computed", "agrees"),
    [
        ("100.00", "100.004", True),  # two decimals: rounded to cents
        ("100.00", "100.005", False),  # half up: 100.01
        ("-100.00", "-100.005", False),  # half up is away from zero: -100.01
        ("100.0", "100.04", True),  # one decimal
        ("100.0", "100.05", False),
        ("100", "100.000", True),  # no decimals: compared as written
        ("100", "100.4", False),  # not rounded to whole units
        ("1E+2", "100.4", False),
        ("1E+2", "100", True),
    ],
)
def test_rounding_to_stated_decimals(stated: str, computed: str, agrees: bool) -> None:
    exact = Policy(abs_tol=Decimal(0))
    assert exact.agrees(Decimal(stated), Decimal(computed)) is agrees


def test_integer_stated_values_use_the_tolerance() -> None:
    assert Policy().agrees(Decimal("100"), Decimal("100.004"))
    assert not Policy().agrees(Decimal("100"), Decimal("100.4"))

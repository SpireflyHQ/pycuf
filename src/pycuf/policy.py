"""Calculation policies: how to interpret the CUF-XML calculation rules.

CUF-XML's calculation rules are ambiguous in places, and real exporters and importers read them
differently. A :class:`Policy` makes every interpretation explicit. It is an immutable value:
pass it to :meth:`CufFile.totals <pycuf.CufFile.totals>` or :func:`pycuf.validate`, give it
to :func:`pycuf.read` as the file's default, or derive a variant with :meth:`Policy.replace`::

    import pycuf
    from pycuf.policy import ERP

    cuf = pycuf.read("begroting.xml")
    cuf.totals()                       # the default policy (the 2006 usage rules)
    cuf.totals(policy="schema")        # a preset, by name
    cuf.totals(policy=ERP.replace(abs_tol=Decimal("0.05")))

=================  ===========================================================================
Preset             Meaning
=================  ===========================================================================
``usage-rules``    The "Gebruikersregels CUF 4003" (2006); the default (:data:`USAGE_RULES`)
``schema``         The literal reading of the 4.003 schema comments (:data:`SCHEMA`)
``erp``            Labour resource lines as ERP importers read them (:data:`ERP`)
=================  ===========================================================================
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final, Literal, Self, TypedDict, Unpack, get_args

from ._numeric import context

__all__ = [
    "DEFAULT",
    "ERP",
    "PRESETS",
    "SCHEMA",
    "USAGE_RULES",
    "EstimateStyle",
    "LabourRule",
    "Policy",
    "PresetName",
    "ResourceBasis",
    "ResourceRule",
    "Rounding",
    "ZeroFactorRule",
    "resolve_policy",
]

ZeroFactorRule = Literal["one", "zero"]
"""What a factor written as ``0`` means: ``"one"`` (ignore it) or ``"zero"`` (literally 0)."""
EstimateStyle = Literal["auto", "traditional", "element"]
"""Whether ``DOORREKEN_HOEVEELHEID`` multiplies: ``"element"`` yes, ``"traditional"`` no,
``"auto"`` yes when the file contains such multipliers (reported as ``CUF7005``)."""
LabourRule = Literal["spec", "erp"]
"""How labour resource lines are priced: the specification's formula, or ERP practice."""
ResourceBasis = Literal["total", "per-unit"]
"""Whether a resource line's ``HOEVEELHEID`` is for the whole estimate line (``"total"``) or per
unit of the estimate line (``"per-unit"``)."""
ResourceRule = Literal["fallback", "ignore", "prefer"]
"""When resource (MAMO) lines price their estimate line: only when the line states no prices
itself (``"fallback"``), never (``"ignore"``) or whenever there are resource lines
(``"prefer"``)."""
Rounding = Literal["ROUND_HALF_UP", "ROUND_HALF_EVEN"]
"""Rounding mode for comparing computed with stated values (``decimal`` constants work too)."""
PresetName = Literal["usage-rules", "schema", "erp"]
"""Names of the presets in :data:`PRESETS`."""


def _choice(field: str, value: object, alias: object) -> None:
    allowed = get_args(alias)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(
            f"Policy.{field}={value!r} is not valid; choose from {', '.join(map(repr, allowed))}"
        )


def _decimal(field: str, value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise TypeError(
            f"Policy.{field} must be a Decimal, int or str, not {type(value).__name__} "
            "(floats would bring binary rounding into money checks)"
        )
    try:
        result = Decimal(value)
    except decimal.InvalidOperation:
        raise ValueError(f"Policy.{field}={value!r} is not a number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"Policy.{field} must be a finite number >= 0, got {value!r}")
    return result


_COMPARE_PRECISION = 80
"""Digits for comparing stated with computed values (inputs may carry more digits than results)."""


class _PolicyChanges(TypedDict, total=False):
    zero_factor: ZeroFactorRule
    estimate_style: EstimateStyle
    labour: LabourRule
    resources: ResourceRule
    resource_basis: ResourceBasis
    abs_tol: Decimal | int | str
    rel_tol: Decimal | int | str
    rounding: Rounding


@dataclass(frozen=True, slots=True, kw_only=True)
class Policy:
    """How to interpret the CUF-XML calculation rules; immutable, see :meth:`replace`.

    Attributes:
        zero_factor: What a factor written as ``0`` means (``HOEVEELHEID_FACTOR``,
            ``PRIJS_FACTOR``, ``DOORREKEN_HOEVEELHEID``). The 2006 usage rules say "empty or 0
            counts as 1" (``"one"``); the schema comments only mention empty (``"zero"`` reads a 0
            literally). An empty or missing factor always counts as 1.
        estimate_style: Whether a bundle's ``DOORREKEN_HOEVEELHEID`` multiplies everything
            beneath it. ``"element"``: yes, as both specification texts say. ``"traditional"``:
            no, the multipliers are ignored (as some importers do). ``"auto"``: ``"element"``
            when any bundle has a multiplier, else ``"traditional"``; the outcome is reported.
        labour: How labour (``LOON``) resource lines are priced. ``"spec"``:
            hours = ``HOEVEELHEID × UUR_NORM``, labour = hours × ``UUR_TARIEF × PRIJS_FACTOR``.
            ``"erp"``: ``HOEVEELHEID`` already is the number of hours (``UUR_NORM`` counts as 1
            when empty) and ``PRIJS`` is the hourly rate when ``UUR_TARIEF`` is empty, which is
            how ERP importers read them according to Bakker & Spees.
        resources: When resource (MAMO) lines price their estimate line. The specification
            makes the estimate line leading and resource lines informative, but some exporters
            only price the resource lines. ``"fallback"``: use the resource lines when the line
            states no hours or unit prices itself (reported as ``CUF5006``). ``"ignore"``: never.
            ``"prefer"``: whenever the line has resource lines.
        resource_basis: What a resource line's quantity refers to. ``"total"`` (the usage rules:
            "the total of the resource lines usually equals the estimate line", and production
            rates give the resource's total quantity): the resource lines add up to the line's
            costs. ``"per-unit"`` (one sentence of the schema: the resource totals "form the unit
            prices" of the line): they add up to the line's unit prices, so they are multiplied
            by the line's quantity.
        abs_tol: Absolute tolerance for stated-against-computed checks.
        rel_tol: Relative tolerance (``math.isclose`` semantics: values agree when
            ``|a - b| <= max(rel_tol × max(|a|, |b|), abs_tol)``).
        rounding: Rounding mode used to round a computed value to the precision of the stated
            value before comparing.
    """

    zero_factor: ZeroFactorRule = "one"
    estimate_style: EstimateStyle = "auto"
    labour: LabourRule = "spec"
    resources: ResourceRule = "fallback"
    resource_basis: ResourceBasis = "total"
    abs_tol: Decimal = Decimal("0.01")
    rel_tol: Decimal = Decimal(0)
    rounding: Rounding = "ROUND_HALF_UP"

    def __post_init__(self) -> None:
        _choice("zero_factor", self.zero_factor, ZeroFactorRule)
        _choice("estimate_style", self.estimate_style, EstimateStyle)
        _choice("labour", self.labour, LabourRule)
        _choice("resources", self.resources, ResourceRule)
        _choice("resource_basis", self.resource_basis, ResourceBasis)
        _choice("rounding", self.rounding, Rounding)
        object.__setattr__(self, "abs_tol", _decimal("abs_tol", self.abs_tol))
        object.__setattr__(self, "rel_tol", _decimal("rel_tol", self.rel_tol))
        if self.rel_tol >= 1:
            raise ValueError(f"Policy.rel_tol must be < 1, got {self.rel_tol}")

    def replace(self, **changes: Unpack[_PolicyChanges]) -> Self:
        """Return a copy with some fields changed (validated like the constructor)."""
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]

    def agrees(self, stated: Decimal, computed: Decimal) -> bool:
        """Whether a stated value agrees with a computed one under this policy's tolerances.

        When ``stated`` is written with decimals, ``computed`` is first rounded to as many
        decimals with :attr:`rounding`. A stated value without decimals (``100``, ``1E+2``) is
        compared as written: exporters drop trailing zeros, so ``100`` usually means 100.00.
        The result does not depend on your decimal context; non-finite values never agree.
        """
        if not (stated.is_finite() and computed.is_finite()):
            return False
        exponent = stated.as_tuple().exponent
        assert isinstance(exponent, int)
        with context() as ctx:
            ctx.prec = _COMPARE_PRECISION
            if exponent < 0 and computed:  # rounding never changes a zero
                # quantize fails unless every digit of its result fits the precision
                ctx.prec = max(ctx.prec, computed.adjusted() - exponent + 2)
                computed = computed.quantize(Decimal(1).scaleb(exponent), rounding=self.rounding)
            diff = abs(stated - computed)
            return diff <= max(self.rel_tol * max(abs(stated), abs(computed)), self.abs_tol)


USAGE_RULES: Final = Policy()
"""The 2006 usage rules ("Gebruikersregels CUF 4003"): the default."""
SCHEMA: Final = Policy(zero_factor="zero", resources="ignore")
"""The literal reading of the 4.003 schema comments: a factor of 0 is 0, resource lines are only
informative."""
ERP: Final = Policy(labour="erp")
"""Labour resource lines as ERP importers read them (``HOEVEELHEID`` = hours, ``PRIJS`` = rate)."""
DEFAULT: Final = USAGE_RULES
"""The policy used when none is given."""
PRESETS: Final[Mapping[PresetName, Policy]] = MappingProxyType(
    {"usage-rules": USAGE_RULES, "schema": SCHEMA, "erp": ERP}
)
"""The presets by name; anywhere a policy is accepted, its name is accepted too."""


def resolve_policy(policy: Policy | PresetName | None, default: Policy = DEFAULT) -> Policy:
    """Turn a policy argument into a :class:`Policy` (``None`` → ``default``, names → presets)."""
    if policy is None:
        return default
    if isinstance(policy, Policy):
        return policy
    if isinstance(policy, str):
        try:
            return PRESETS[policy]
        except KeyError:
            names = ", ".join(map(repr, PRESETS))
            raise ValueError(f"unknown policy preset {policy!r}; choose from {names}") from None
    raise TypeError(f"policy must be a Policy or a preset name, not {type(policy).__name__}")

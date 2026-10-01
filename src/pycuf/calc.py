"""Computing costs from the CUF-XML formulas, and checking stated totals against them.

The formulas are those of the CUF-XML 4.003 schema and its usage rules; wherever the two disagree
or are silent, the :class:`~pycuf.policy.Policy` decides. All arithmetic is exact
:class:`decimal.Decimal` arithmetic; nothing is rounded except when comparing a computed value
with a stated one.

Estimate line (``BEGROTINGSREGEL``)::

    Q              = HOEVEELHEID × HOEVEELHEID_FACTOR
    hours          = Q × UUR_NORM
    labour         = Q × UUR_NORM × UUR_TARIEF
    material       = Q × MATERIAALPRIJS          (equipment, subcontracting, other alike)

Resource line (``MAMO_REGEL``), with the default ``labour="spec"``::

    LOON:          hours = HOEVEELHEID × UUR_NORM, labour = hours × UUR_TARIEF × PRIJS_FACTOR
    other types:   amount = HOEVEELHEID × PRIJS × PRIJS_FACTOR

Bundle (``BUNDELING``): its stated totals are the sum of its direct children, where a child
bundle counts with its own ``DOORREKEN_HOEVEELHEID`` and the bundle's own multiplier is *not*
included. The estimate (``BEGROTING``) is the sum of its direct children in the same way.

Missing or empty numbers count as 0, missing or empty factors as 1, a factor of 0 as the policy
says.
"""

from __future__ import annotations

import decimal
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from .findings import Finding, FindingCollector
from .models import COST_FIELDS, Bundle, Costs, CostType, Line, ResourceLine, StatedTotals
from .policy import Policy

if TYPE_CHECKING:
    from .reader import CufFile

__all__ = ["Totals", "check_totals", "compute"]

_ZERO = Decimal(0)
_ONE = Decimal(1)
_DUTCH = {
    "hours": "UREN",
    "labour": "LOONKOSTEN",
    "material": "MATERIAALKOSTEN",
    "equipment": "MATERIEELKOSTEN",
    "subcontracting": "ONDERAANNEMING",
    "other": "OVERIGE_KOSTEN",
}
_VAT_ITEM = re.compile(r"\b(btw|vat|omzetbelasting)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True, kw_only=True)
class Totals:
    """Computed costs of a CUF file under one policy.

    Look up any node with ``totals[node]``: for an estimate line its costs before multipliers,
    for a bundle the sum of its direct children (the figure its stated totals should show).
    :meth:`extended` gives a node's contribution to the estimate, with every multiplier applied.

    Attributes:
        policy: The policy used.
        estimate_style: The resolved estimate style (never ``"auto"``).
        style_inferred: Whether the style was inferred (``policy.estimate_style == "auto"``).
        estimate: The computed estimate totals (excluding markups and VAT).
        findings: What applying the policy involved (``CUF7005``, ``CUF7006``, ``CUF5006``).
    """

    policy: Policy
    estimate_style: Literal["traditional", "element"]
    style_inferred: bool
    estimate: Costs
    findings: tuple[Finding, ...] = ()
    _costs: Mapping[Bundle | Line, Costs] = field(default_factory=dict, repr=False)
    _multipliers: Mapping[Bundle | Line, Decimal] = field(default_factory=dict, repr=False)
    _resources: Mapping[ResourceLine, Costs] = field(default_factory=dict, repr=False)
    _from_resources: frozenset[Line] = field(default_factory=frozenset, repr=False)

    def __getitem__(self, node: Bundle | Line) -> Costs:
        try:
            return self._costs[node]
        except KeyError:
            raise KeyError(
                "node does not belong to the file these totals were computed for"
            ) from None

    def multiplier(self, node: Bundle | Line) -> Decimal:
        """The product of the multipliers applied to ``node``'s costs in :meth:`extended`.

        For a bundle this includes its own ``DOORREKEN_HOEVEELHEID``; for a line, those of its
        enclosing bundles. Always 1 with ``estimate_style="traditional"``.
        """
        return self._multipliers[node]

    def extended(self, node: Bundle | Line) -> Costs:
        """``node``'s contribution to the estimate: its costs times :meth:`multiplier`."""
        return self[node] * self.multiplier(node)

    def resource(self, resource: ResourceLine) -> Costs:
        """Costs of one resource line (informative; see the policy's ``resources`` rule)."""
        return self._resources[resource]

    def priced_by_resources(self, line: Line) -> bool:
        """Whether ``line``'s costs were taken from its resource lines."""
        return line in self._from_resources


class _Calculator:
    def __init__(self, policy: Policy, findings: FindingCollector) -> None:
        self.policy = policy
        self.findings = findings
        self.costs: dict[Bundle | Line, Costs] = {}
        self.multipliers: dict[Bundle | Line, Decimal] = {}
        self.resources: dict[ResourceLine, Costs] = {}
        self.from_resources: set[Line] = set()
        self.zero_factors: dict[str, tuple[int, object]] = {}
        self.fallbacks = 0
        self.first_fallback: Line | None = None
        self.element = False

    def factor(self, value: Decimal | None, where: object, name: str) -> Decimal:
        if value is None:
            return _ONE
        if value == 0 and self.policy.zero_factor == "one":
            count, first = self.zero_factors.get(name, (0, where))
            self.zero_factors[name] = (count + 1, first)
            return _ONE
        return value

    def resource(self, r: ResourceLine) -> Costs:
        q = r.quantity or _ZERO
        factor = self.factor(r.price_factor, r, "PRIJS_FACTOR")
        if r.cost_type is CostType.LABOUR:
            if self.policy.labour == "erp":
                hours = q * (r.hours_per_unit if r.hours_per_unit is not None else _ONE)
                rate = r.hourly_rate if r.hourly_rate is not None else r.price
            else:
                hours = q * (r.hours_per_unit or _ZERO)
                rate = r.hourly_rate
            c = Costs(hours=hours, labour=hours * (rate or _ZERO) * factor)
        elif r.cost_type is None:
            c = Costs()
        else:
            amount = q * (r.price or _ZERO) * factor
            c = Costs(**{_FIELD[r.cost_type]: amount})
        self.resources[r] = c
        return c

    def line(self, ln: Line, multiplier: Decimal) -> Costs:
        resource_costs = [self.resource(r) for r in ln.resources]
        rule = self.policy.resources
        use_resources = bool(ln.resources) and (
            rule == "prefer" or (rule == "fallback" and not ln.priced)
        )
        q = (ln.quantity or _ZERO) * self.factor(ln.quantity_factor, ln, "HOEVEELHEID_FACTOR")
        if use_resources:
            total = sum(resource_costs, Costs())
            c = total * q if self.policy.resource_basis == "per-unit" else total
            self.from_resources.add(ln)
            if rule == "fallback":
                self.fallbacks += 1
                self.first_fallback = self.first_fallback or ln
        else:
            hours = q * (ln.hours_per_unit or _ZERO)
            c = Costs(
                hours=hours,
                labour=hours * (ln.hourly_rate or _ZERO),
                material=q * (ln.material_price or _ZERO),
                equipment=q * (ln.equipment_price or _ZERO),
                subcontracting=q * (ln.subcontract_price or _ZERO),
                other=q * (ln.other_price or _ZERO),
            )
        self.costs[ln] = c
        self.multipliers[ln] = multiplier
        return c

    def own_multiplier(self, b: Bundle) -> Decimal:
        if not self.element:
            return _ONE
        return self.factor(b.multiplier, b, "DOORREKEN_HOEVEELHEID")

    def children(self, children: Iterable[Bundle | Line], multiplier: Decimal) -> Costs:
        total = Costs()
        for child in children:
            if isinstance(child, Line):
                total = total + self.line(child, multiplier)
            else:
                own = self.own_multiplier(child)
                inner = self.children(child.children, multiplier * own)
                self.costs[child] = inner
                self.multipliers[child] = multiplier * own
                total = total + inner * own
        return total


_FIELD: Mapping[CostType, str] = {
    CostType.LABOUR: "labour",
    CostType.MATERIAL: "material",
    CostType.EQUIPMENT: "equipment",
    CostType.SUBCONTRACTING: "subcontracting",
    CostType.OTHER: "other",
}


PRECISION = 60
"""Decimal precision (significant digits) of the computations; far beyond any real estimate, so
results are exact."""


def compute(cuf: CufFile, policy: Policy) -> Totals:
    """Compute the costs of every node of ``cuf`` under ``policy``."""
    with decimal.localcontext(prec=PRECISION):
        return _compute(cuf, policy)


def _compute(cuf: CufFile, policy: Policy) -> Totals:
    findings = FindingCollector(max_per_code=None, max_total=None)
    calc = _Calculator(policy, findings)
    with_multiplier = [b for b in cuf.bundles if b.multiplier is not None]
    style = policy.estimate_style
    if style == "auto":
        style = "element" if with_multiplier else "traditional"
    calc.element = style == "element"
    estimate = calc.children(cuf.estimate.children, _ONE)
    if with_multiplier:
        first = with_multiplier[0]
        how = "applied" if calc.element else "ignored (estimate_style='traditional')"
        findings.add(
            "CUF7005",
            f"{len(with_multiplier)} bundle(s) have a DOORREKEN_HOEVEELHEID; multipliers {how}",
            line=first.raw.line if first.raw else None,
            path=first.raw.path if first.raw else None,
        )
    for name, (count, first_node) in calc.zero_factors.items():
        raw = getattr(first_node, "raw", None)
        findings.add(
            "CUF7006",
            f"{name} 0 counted as 1 ({count:,} time(s)); pass a policy with zero_factor='zero' "
            "to read it as 0",
            line=raw.line if raw else None,
            path=f"{raw.path}@{name}" if raw else None,
        )
    if calc.fallbacks and calc.first_fallback is not None:
        raw = calc.first_fallback.raw
        findings.add(
            "CUF5006",
            f"{calc.fallbacks:,} estimate line(s) state no prices themselves and were priced from "
            "their resource lines",
            line=raw.line if raw else None,
            path=raw.path if raw else None,
        )
    return Totals(
        policy=policy,
        estimate_style=style,
        style_inferred=policy.estimate_style == "auto",
        estimate=estimate,
        findings=findings.snapshot(),
        _costs=calc.costs,
        _multipliers=calc.multipliers,
        _resources=calc.resources,
        _from_resources=frozenset(calc.from_resources),
    )


# ---------------------------------------------------------------------------- checks
def _fmt(value: Decimal) -> str:
    """Plain notation without trailing zeros (``4404.820000`` → ``4404.82``)."""
    return format(value.normalize(), "f")


def _compare(
    label: str,
    stated: StatedTotals,
    computed: Costs,
    policy: Policy,
    raw: object,
    code: str,
    findings: FindingCollector,
) -> bool:
    """Compare stated with computed totals; return whether the stated totals were all zero."""
    present = [(n, v) for n, v in stated.items() if v is not None]
    if not present:
        return False
    if all(v == 0 for _, v in present) and any(v != 0 for _, v in computed.items()):
        return True
    line = getattr(raw, "line", None)
    path = getattr(raw, "path", None)
    for name, value in present:
        assert value is not None
        actual = getattr(computed, name)
        if not policy.agrees(value, actual):
            findings.add(
                code,
                f"{label} {_DUTCH[name]} is {_fmt(value)}, computed {_fmt(actual)} "
                f"(difference {_fmt(value - actual)})",
                line=line,
                path=f"{path}@{_DUTCH[name]}" if path else None,
                value=str(value),
            )
    return False


def check_totals(cuf: CufFile, totals: Totals, findings: FindingCollector) -> None:
    """Check stated totals, resource lines and the contract sum against ``totals``."""
    with decimal.localcontext(prec=PRECISION):
        _check_totals(cuf, totals, findings)


def _check_totals(cuf: CufFile, totals: Totals, findings: FindingCollector) -> None:
    policy = totals.policy
    zero_nodes = 0
    first_zero: object = None
    for b in cuf.bundles:
        label = f"BUNDELING {b.code!r}" if b.code else f"BUNDELING #{b.seq}"
        if _compare(label, b.stated, totals[b], policy, b.raw, "CUF5001", findings):
            zero_nodes += 1
            first_zero = first_zero or b.raw
    est = cuf.estimate
    if _compare("BEGROTING", est.stated, totals.estimate, policy, est.raw, "CUF5002", findings):
        zero_nodes += 1
        first_zero = first_zero or est.raw
    if zero_nodes:
        findings.add(
            "CUF5003",
            f"{zero_nodes:,} bundle(s)/estimate state only zero totals although their lines have "
            "costs (the exporter apparently does not fill them)",
            line=getattr(first_zero, "line", None),
            path=getattr(first_zero, "path", None),
        )
    _check_resources(cuf, totals, findings)
    _check_contract_sum(cuf, totals, findings)


def _close(a: Decimal, b: Decimal, policy: Policy) -> bool:
    return abs(a - b) <= max(policy.rel_tol * max(abs(a), abs(b)), policy.abs_tol)


def _check_resources(cuf: CufFile, totals: Totals, findings: FindingCollector) -> None:
    policy = totals.policy
    for ln in cuf.lines:
        if not ln.resources or not ln.priced or totals.priced_by_resources(ln):
            continue
        summed = sum((totals.resource(r) for r in ln.resources), Costs())
        if policy.resource_basis == "per-unit":
            factor = ln.quantity_factor
            if factor is None or (factor == 0 and policy.zero_factor == "one"):
                factor = _ONE
            summed = summed * ((ln.quantity or _ZERO) * factor)
        line_costs = totals[ln]
        diffs = [
            f"{_DUTCH[n]} {_fmt(getattr(line_costs, n))} vs {_fmt(getattr(summed, n))}"
            for n in COST_FIELDS
            if not _close(getattr(line_costs, n), getattr(summed, n), policy)
        ]
        if diffs:
            raw = ln.raw
            label = f"BEGROTINGSREGEL {ln.code!r}" if ln.code else f"BEGROTINGSREGEL #{ln.seq}"
            findings.add(
                "CUF5004",
                f"{label}: line and resource lines differ ({'; '.join(diffs)}); "
                "the line is leading",
                line=raw.line if raw else None,
                path=raw.path if raw else None,
            )


def _check_contract_sum(cuf: CufFile, totals: Totals, findings: FindingCollector) -> None:
    tail = cuf.tail
    if tail is None or tail.contract_sum is None:
        return
    direct = totals.estimate.total
    items = [i for i in tail.items if i.amount is not None]
    all_items = direct + sum((i.amount for i in items if i.amount is not None), _ZERO)
    without_vat = direct + sum(
        (
            i.amount
            for i in items
            if i.amount is not None and not _VAT_ITEM.search(i.description or "")
        ),
        _ZERO,
    )
    policy = totals.policy
    if policy.agrees(tail.contract_sum, all_items) or policy.agrees(tail.contract_sum, without_vat):
        return
    raw = tail.raw
    findings.add(
        "CUF5005",
        f"AANNEEMSOM is {_fmt(tail.contract_sum)}; computed direct costs {_fmt(direct)} plus the "
        f"tail items make {_fmt(without_vat)} (CUF does not say which tail items count)",
        line=raw.line if raw else None,
        path=f"{raw.path}@AANNEEMSOM" if raw else None,
        value=str(tail.contract_sum),
    )

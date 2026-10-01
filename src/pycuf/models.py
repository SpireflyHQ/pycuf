"""The typed, English-named data model of a CUF file.

All classes are frozen, slotted, keyword-only dataclasses. Every object keeps the
:class:`~pycuf.raw.RawElement` it was built from in ``raw`` (the parsed text of every attribute),
and ``extra`` exposes attributes that CUF-XML 4.003 does not define (vendor extensions). The Dutch
name of every attribute is listed in the glossary of the documentation and in
:data:`pycuf.spec.ELEMENTS`.

Numbers are :class:`decimal.Decimal` and ``None`` when the attribute is absent, empty or invalid
(an invalid value is reported as a finding; the raw text stays in ``raw``). The spec's defaults
("empty counts as 0", "an empty factor counts as 1") are applied when computing, never here, so
the model shows what the file says.

The tree nodes (:class:`Bundle`, :class:`Line`, :class:`ResourceLine`, :class:`QuantityLine`)
compare by identity, so they can be used as dictionary keys (for example to look up computed
costs).
"""

from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import TypeAlias

from ._numeric import in_context
from .raw import RawElement
from .spec import ELEMENTS

__all__ = [
    "Bundle",
    "CostType",
    "Costs",
    "Estimate",
    "Line",
    "Node",
    "Project",
    "QuantityLine",
    "ResourceLine",
    "SortCode",
    "SortCodeEntry",
    "SortCodeScheme",
    "StatedTotals",
    "Tail",
    "TailItem",
]

_ZERO = Decimal(0)
_EMPTY: Mapping[str, str] = MappingProxyType({})


def _extra(raw: RawElement | None) -> Mapping[str, str]:
    if raw is None:
        return _EMPTY
    spec = ELEMENTS.get(raw.tag)
    known = spec.attributes if spec is not None else {}
    extra = {k: v for k, v in raw.attributes.items() if k not in known}
    return MappingProxyType(extra) if extra else _EMPTY


class CostType(enum.StrEnum):
    """The five cost types of CUF-XML (``KOSTENSOORT``); the value is the Dutch code."""

    LABOUR = "LOON"
    MATERIAL = "MATERIAAL"
    EQUIPMENT = "MATERIEEL"
    SUBCONTRACTING = "ONDERAANNEMING"
    OTHER = "OVERIG"


@dataclass(frozen=True, slots=True, kw_only=True)
class Costs:
    """A cost breakdown: labour hours plus the amounts of the five cost types.

    Supports ``+``, multiplication by a number and :meth:`get`; :attr:`total` is the sum of the
    five amounts (hours are not money). The arithmetic runs in pycuf's own decimal context, so
    your context does not change the results.
    """

    hours: Decimal = _ZERO
    labour: Decimal = _ZERO
    material: Decimal = _ZERO
    equipment: Decimal = _ZERO
    subcontracting: Decimal = _ZERO
    other: Decimal = _ZERO

    @property
    @in_context
    def total(self) -> Decimal:
        """Labour + material + equipment + subcontracting + other."""
        return self.labour + self.material + self.equipment + self.subcontracting + self.other

    def get(self, cost_type: CostType) -> Decimal:
        """Amount of one cost type."""
        return getattr(self, _COST_FIELD[cost_type])  # type: ignore[no-any-return]

    @in_context
    def __add__(self, other: Costs) -> Costs:
        if not isinstance(other, Costs):
            return NotImplemented
        return Costs(
            hours=self.hours + other.hours,
            labour=self.labour + other.labour,
            material=self.material + other.material,
            equipment=self.equipment + other.equipment,
            subcontracting=self.subcontracting + other.subcontracting,
            other=self.other + other.other,
        )

    @in_context
    def __mul__(self, factor: Decimal | int) -> Costs:
        if not isinstance(factor, (Decimal, int)):
            return NotImplemented
        return Costs(
            hours=self.hours * factor,
            labour=self.labour * factor,
            material=self.material * factor,
            equipment=self.equipment * factor,
            subcontracting=self.subcontracting * factor,
            other=self.other * factor,
        )

    __rmul__ = __mul__

    def items(self) -> Iterator[tuple[str, Decimal]]:
        """Yield ``(name, value)`` for hours and the five cost types."""
        for name in COST_FIELDS:
            yield name, getattr(self, name)


COST_FIELDS: tuple[str, ...] = (
    "hours",
    "labour",
    "material",
    "equipment",
    "subcontracting",
    "other",
)
"""The fields of :class:`Costs`, in CUF order (UREN, LOONKOSTEN, …, OVERIGE_KOSTEN)."""

_COST_FIELD: Mapping[CostType, str] = {
    CostType.LABOUR: "labour",
    CostType.MATERIAL: "material",
    CostType.EQUIPMENT: "equipment",
    CostType.SUBCONTRACTING: "subcontracting",
    CostType.OTHER: "other",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class StatedTotals:
    """Totals as written on a bundle or the estimate (``UREN`` … ``OVERIGE_KOSTEN``).

    A field is ``None`` when the attribute is absent, empty or invalid. These are control totals:
    CUF-XML says the estimate lines are leading, and real files often carry wrong or zero totals,
    so compare them with computed totals instead of trusting them.
    """

    hours: Decimal | None = None
    labour: Decimal | None = None
    material: Decimal | None = None
    equipment: Decimal | None = None
    subcontracting: Decimal | None = None
    other: Decimal | None = None

    @property
    def present(self) -> bool:
        """Whether at least one total is written."""
        return any(getattr(self, name) is not None for name in COST_FIELDS)

    @property
    @in_context
    def total(self) -> Decimal | None:
        """Sum of the five amounts that are written (``None`` if none is)."""
        values = [getattr(self, n) for n in COST_FIELDS[1:] if getattr(self, n) is not None]
        return sum(values, _ZERO) if values else None

    def as_costs(self) -> Costs:
        """The totals as :class:`Costs`, with missing values as 0."""
        return Costs(**{n: getattr(self, n) or _ZERO for n in COST_FIELDS})

    def items(self) -> Iterator[tuple[str, Decimal | None]]:
        """Yield ``(name, value)`` for hours and the five cost types."""
        for name in COST_FIELDS:
            yield name, getattr(self, name)


@dataclass(frozen=True, slots=True, kw_only=True)
class SortCode:
    """A sort code assigned to a node (``SORTEERCODE``).

    Attributes:
        scheme: Name of the sort-code scheme (``SORTERING``), e.g. ``PLANCODE``.
        value: The code (``WAARDE``).
    """

    scheme: str | None
    value: str | None
    raw: RawElement | None = field(default=None, repr=False, compare=False)

    @property
    def extra(self) -> Mapping[str, str]:
        """Attributes not defined in CUF-XML 4.003."""
        return _extra(self.raw)


@dataclass(frozen=True, slots=True, kw_only=True)
class SortCodeEntry:
    """One code in a sort-code scheme's table (``SORTEERCODE_REGEL``)."""

    code: str | None
    description: str | None = None
    unit: str | None = None
    reference_quantity: Decimal | None = None
    raw: RawElement | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SortCodeScheme:
    """A sort-code scheme declared in the file (``SORTEERCODES``).

    Attributes:
        name: Name of the scheme (``SORTERING``), e.g. ``PLANCODE`` or ``bwcarb``.
        purpose: What the scheme is for (``FUNCTIE``), meant to be shown to users.
        entries: The scheme's code table (often empty).
    """

    name: str | None
    purpose: str | None = None
    entries: tuple[SortCodeEntry, ...] = ()
    raw: RawElement | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Project:
    """General project data (``PROJECTGEGEVENS``)."""

    cuf_version: str | None = None
    software_house: str | None = None
    estimate_date: dt.date | None = None
    number: str | None = None
    name: str | None = None
    estimator: str | None = None
    client: str | None = None
    address: str | None = None
    start_date: dt.date | None = None
    currency: str | None = None
    euro_rate: Decimal | None = None
    notes: str | None = None
    raw: RawElement | None = field(default=None, repr=False, compare=False)

    @property
    def extra(self) -> Mapping[str, str]:
        """Attributes not defined in CUF-XML 4.003 (vendor extensions)."""
        return _extra(self.raw)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class QuantityLine:
    """A quantity take-off line (``HOEVEELHEDENSTAAT_REGEL``); informative only."""

    seq: int
    room: str | None = None
    description: str | None = None
    count: Decimal | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    factor_1: Decimal | None = None
    factor_2: Decimal | None = None
    raw: RawElement | None = field(default=None, repr=False)

    @property
    @in_context
    def product(self) -> Decimal | None:
        """Product of the numbers that are filled in (``None`` if none is).

        Take-off software usually multiplies count, dimensions and factors; the result is
        informative and does not change any quantity.
        """
        values = [
            v
            for v in (
                self.count,
                self.length,
                self.width,
                self.height,
                self.factor_1,
                self.factor_2,
            )
            if v is not None
        ]
        if not values:
            return None
        result = Decimal(1)
        for v in values:
            result *= v
        return result


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class ResourceLine:
    """A resource line (``MAMO_REGEL``): one cost type of an estimate line, broken down.

    Resource lines are informative: when they disagree with their estimate line, the estimate
    line is leading.

    Attributes:
        cost_type: The interpreted cost type, ``None`` if the code is missing or unknown.
        cost_type_code: ``KOSTENSOORT`` as written.
    """

    seq: int
    line_seq: int
    cost_type: CostType | None
    cost_type_code: str | None = None
    code: str | None = None
    description: str | None = None
    unit: str | None = None
    quantity: Decimal | None = None
    count_unit: str | None = None
    count: Decimal | None = None
    duration_unit: str | None = None
    duration: Decimal | None = None
    production_unit: str | None = None
    production: Decimal | None = None
    price: Decimal | None = None
    price_factor: Decimal | None = None
    factor_code: str | None = None
    hours_per_unit: Decimal | None = None
    hourly_rate: Decimal | None = None
    hourly_rate_code: str | None = None
    ean_code: str | None = None
    article_group: str | None = None
    order_unit: str | None = None
    quantity_per_order_unit: Decimal | None = None
    supplier_code: str | None = None
    comment: str | None = None
    quantity_lines: tuple[QuantityLine, ...] = ()
    sort_codes: tuple[SortCode, ...] = ()
    raw: RawElement | None = field(default=None, repr=False)

    @property
    def extra(self) -> Mapping[str, str]:
        """Attributes not defined in CUF-XML 4.003 (vendor extensions)."""
        return _extra(self.raw)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Line:
    """An estimate line (``BEGROTINGSREGEL``): a quantity priced per cost type.

    Attributes:
        seq: Position among all estimate lines of the file (0-based, document order).
        bundle_seq: ``seq`` of the enclosing bundle, ``None`` directly under the estimate.
        depth: Number of enclosing bundles.
        provisional_sum: ``STELPOST``; ``None`` when not written.
        vat_rate: ``BTW`` percentage (19, 21, 9, …).
    """

    seq: int
    bundle_seq: int | None = None
    depth: int = 0
    code: str | None = None
    description: str | None = None
    unit: str | None = None
    quantity: Decimal | None = None
    count_unit: str | None = None
    count: Decimal | None = None
    duration_unit: str | None = None
    duration: Decimal | None = None
    production_unit: str | None = None
    production: Decimal | None = None
    quantity_factor: Decimal | None = None
    factor_code: str | None = None
    hours_per_unit: Decimal | None = None
    hourly_rate: Decimal | None = None
    hourly_rate_code: str | None = None
    material_price: Decimal | None = None
    equipment_price: Decimal | None = None
    subcontract_price: Decimal | None = None
    other_price: Decimal | None = None
    provisional_sum: bool | None = None
    vat_rate: Decimal | None = None
    ean_code: str | None = None
    article_group: str | None = None
    order_unit: str | None = None
    quantity_per_order_unit: Decimal | None = None
    supplier_code: str | None = None
    comment: str | None = None
    resources: tuple[ResourceLine, ...] = ()
    quantity_lines: tuple[QuantityLine, ...] = ()
    sort_codes: tuple[SortCode, ...] = ()
    raw: RawElement | None = field(default=None, repr=False)

    @property
    def priced(self) -> bool:
        """Whether the line itself states hours or a unit price for any cost type."""
        return any(
            v is not None
            for v in (
                self.hours_per_unit,
                self.material_price,
                self.equipment_price,
                self.subcontract_price,
                self.other_price,
            )
        )

    @property
    def is_text(self) -> bool:
        """Whether this is a text line: no quantity, no prices and no resource lines.

        Exporters use such lines for headings and remarks (IBIS marks them with an ``stk``
        sort code).
        """
        return self.quantity is None and not self.priced and not self.resources

    @property
    def extra(self) -> Mapping[str, str]:
        """Attributes not defined in CUF-XML 4.003 (vendor extensions)."""
        return _extra(self.raw)


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class Bundle:
    """A bundle (``BUNDELING``): a chapter, paragraph or element grouping lines and bundles.

    Attributes:
        seq: Position among all bundles of the file (0-based, document order).
        parent_seq: ``seq`` of the enclosing bundle, ``None`` at the top level.
        depth: Nesting level (1 = directly under the estimate).
        multiplier: ``DOORREKEN_HOEVEELHEID``. When written, the bundle is an *element* and all
            costs beneath it are multiplied by it.
        reference_quantity: ``TERUGDEEL_HOEVEELHEID``, for computing a unit rate (informative).
        stated: The totals as written (excluding the bundle's own multiplier).
        children: Bundles and estimate lines, in document order.
    """

    seq: int
    parent_seq: int | None = None
    depth: int = 1
    code: str | None = None
    coding_method: str | None = None
    description: str | None = None
    unit: str | None = None
    reference_quantity: Decimal | None = None
    multiplier: Decimal | None = None
    stated: StatedTotals = field(default_factory=StatedTotals)
    comment: str | None = None
    children: tuple[Bundle | Line, ...] = ()
    quantity_lines: tuple[QuantityLine, ...] = ()
    sort_codes: tuple[SortCode, ...] = ()
    raw: RawElement | None = field(default=None, repr=False)

    @property
    def bundles(self) -> tuple[Bundle, ...]:
        """Direct child bundles."""
        return tuple(c for c in self.children if isinstance(c, Bundle))

    @property
    def lines(self) -> tuple[Line, ...]:
        """Direct child estimate lines."""
        return tuple(c for c in self.children if isinstance(c, Line))

    @property
    def extra(self) -> Mapping[str, str]:
        """Attributes not defined in CUF-XML 4.003 (vendor extensions)."""
        return _extra(self.raw)


Node: TypeAlias = Bundle | Line
"""A node of the estimate tree."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Estimate:
    """The estimate (``BEGROTING``): direct costs, excluding markups and VAT.

    Attributes:
        stated: The totals as written.
        children: Top-level bundles and estimate lines, in document order.
    """

    stated: StatedTotals = field(default_factory=StatedTotals)
    children: tuple[Bundle | Line, ...] = ()
    raw: RawElement | None = field(default=None, repr=False, compare=False)

    @property
    def bundles(self) -> tuple[Bundle, ...]:
        """Top-level bundles."""
        return tuple(c for c in self.children if isinstance(c, Bundle))

    @property
    def lines(self) -> tuple[Line, ...]:
        """Estimate lines directly under the estimate (not in a bundle)."""
        return tuple(c for c in self.children if isinstance(c, Line))


@dataclass(frozen=True, slots=True, kw_only=True)
class TailItem:
    """One tail item (``VRIJE_GROOTHEID``), e.g. overheads, profit and risk or the VAT amount."""

    description: str | None = None
    amount: Decimal | None = None
    raw: RawElement | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class Tail:
    """The tail (``STAARTGEGEVENS``): markups and the contract sum.

    Attributes:
        contract_sum: ``AANNEEMSOM``, the contract sum including markups and excluding VAT.
        items: The tail items as written. CUF does not say which of them add up to the
            contract sum (a VAT amount is often listed too).
    """

    contract_sum: Decimal | None = None
    items: tuple[TailItem, ...] = ()
    raw: RawElement | None = field(default=None, repr=False, compare=False)

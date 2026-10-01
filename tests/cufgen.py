"""Synthetic CUF-XML files for the tests.

:func:`make_estimate` builds a random but reproducible estimate (bundles, lines, resource lines,
quantity take-off lines, sort codes, a tail) and :meth:`Estimate.expected` computes its totals
independently of pycuf, from the CUF-XML formulas. :func:`write` renders it as CUF-XML in one of
several dialects that reproduce what real exporters do:

==================  ===========================================================================
``standard``        UTF-8, ``x-schema:CufSchema.xml``, every required attribute, ISO dates
``ibis``            windows-1252 with € and ï, ``xmlns:Ibis``, ``BTW=""`` on every line,
                    ``INZET="1"``/``HOEVEELHEID_FACTOR="1"``, text lines marked with an ``stk`` code,
                    no ``OVERIGE_KOSTEN`` on bundles
``forum``           no XML declaration, namespace ``x-schema:Forum CUF-XML-schema4003.xsd``
``dataviewers``     ``d-m-yyyy`` dates, empty ``VALUTA``, ``STELPOST="0"``, totals ``0``, no tail
``bakkerspees``     lines directly under the estimate, resource lines with vendor attributes,
                    ``<SORTEERCODE ACTI=.. NACA=..>``, no tail
==================  ===========================================================================

Everything here is made up; no real estimate is used.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from xml.sax.saxutils import quoteattr

__all__ = ["Bundle", "Estimate", "Line", "Resource", "make_estimate", "write"]

D = Decimal
COSTS = ("hours", "labour", "material", "equipment", "subcontracting", "other")
DUTCH_TOTALS = (
    "UREN",
    "LOONKOSTEN",
    "MATERIAALKOSTEN",
    "MATERIEELKOSTEN",
    "ONDERAANNEMING",
    "OVERIGE_KOSTEN",
)
UNITS = ("m2", "m3", "m1", "st", "kg", "pst", "uur")
WORDS = (
    "metselwerk", "beton", "bekisting", "wapening", "kozijn", "dakbedekking", "isolatie",
    "stucwerk", "tegelwerk", "schilderwerk", "fundering", "riolering", "gevelsteen", "voegwerk",
)  # fmt: skip


def _money(rng: random.Random, lo: int, hi: int, places: int = 2) -> Decimal:
    scale = 10**places
    return D(rng.randint(lo * scale, hi * scale)) / scale


@dataclass
class Resource:
    cost_type: str  # LOON, MATERIAAL, MATERIEEL, ONDERAANNEMING, OVERIG
    quantity: Decimal
    price: Decimal | None = None
    price_factor: Decimal | None = None
    hours_per_unit: Decimal | None = None
    hourly_rate: Decimal | None = None
    description: str = "middel"

    def costs(self) -> dict[str, Decimal]:
        """Resource-line costs per the CUF-XML formulas (factor empty or 0 counts as 1)."""
        out = dict.fromkeys(COSTS, D(0))
        factor = self.price_factor or D(1)
        if self.cost_type == "LOON":
            hours = self.quantity * (self.hours_per_unit or 0)
            out["hours"] = hours
            out["labour"] = hours * (self.hourly_rate or 0) * factor
        else:
            key = {
                "MATERIAAL": "material",
                "MATERIEEL": "equipment",
                "ONDERAANNEMING": "subcontracting",
                "OVERIG": "other",
            }[self.cost_type]
            out[key] = self.quantity * (self.price or 0) * factor
        return out


@dataclass
class Line:
    code: str
    description: str
    unit: str
    quantity: Decimal | None
    quantity_factor: Decimal | None = None
    hours_per_unit: Decimal | None = None
    hourly_rate: Decimal | None = None
    material_price: Decimal | None = None
    equipment_price: Decimal | None = None
    subcontract_price: Decimal | None = None
    other_price: Decimal | None = None
    vat: Decimal = Decimal(21)
    resources: list[Resource] = field(default_factory=list)
    take_off: list[tuple[Decimal, Decimal, Decimal]] = field(default_factory=list)
    sort_codes: dict[str, str] = field(default_factory=dict)
    text: bool = False

    def costs(self) -> dict[str, Decimal]:
        """Line costs per the CUF-XML formulas, before any bundle multiplier."""
        q = (self.quantity or D(0)) * (self.quantity_factor or D(1))
        hours = q * (self.hours_per_unit or 0)
        return {
            "hours": hours,
            "labour": hours * (self.hourly_rate or 0),
            "material": q * (self.material_price or 0),
            "equipment": q * (self.equipment_price or 0),
            "subcontracting": q * (self.subcontract_price or 0),
            "other": q * (self.other_price or 0),
        }


@dataclass
class Bundle:
    code: str
    description: str
    unit: str = "pst"
    multiplier: Decimal | None = None
    reference_quantity: Decimal | None = None
    children: list[Bundle | Line] = field(default_factory=list)
    sort_codes: dict[str, str] = field(default_factory=dict)

    def costs(self) -> dict[str, Decimal]:
        """Totals of the direct children (what the bundle's own attributes should state)."""
        total = dict.fromkeys(COSTS, D(0))
        for child in self.children:
            c = child.costs() if isinstance(child, Line) else child.extended()
            for k in COSTS:
                total[k] += c[k]
        return total

    def extended(self) -> dict[str, Decimal]:
        """Totals including this bundle's own multiplier (what the parent adds up)."""
        factor = self.multiplier or D(1)
        return {k: v * factor for k, v in self.costs().items()}


@dataclass
class Estimate:
    children: list[Bundle | Line]
    project_name: str = "Voorbeeldproject Woningbouw"
    project_number: str = "2026-001"
    schemes: dict[str, str] = field(default_factory=dict)
    tail: list[tuple[str, Decimal]] = field(default_factory=list)

    def expected(self) -> dict[str, Decimal]:
        """Estimate totals per the CUF-XML formulas."""
        total = dict.fromkeys(COSTS, D(0))
        for child in self.children:
            c = child.costs() if isinstance(child, Line) else child.extended()
            for k in COSTS:
                total[k] += c[k]
        return total

    def direct_costs(self) -> Decimal:
        e = self.expected()
        return sum((e[k] for k in COSTS[1:]), D(0))

    def contract_sum(self) -> Decimal:
        return self.direct_costs() + sum((amount for _, amount in self.tail), D(0))

    def walk(self) -> list[Bundle | Line]:
        out: list[Bundle | Line] = []

        def visit(children: list[Bundle | Line]) -> None:
            for c in children:
                out.append(c)
                if isinstance(c, Bundle):
                    visit(c.children)

        visit(self.children)
        return out

    def lines(self) -> list[Line]:
        return [n for n in self.walk() if isinstance(n, Line)]

    def bundles(self) -> list[Bundle]:
        return [n for n in self.walk() if isinstance(n, Bundle)]


def make_estimate(
    seed: int = 0,
    *,
    n_bundles: int = 3,
    depth: int = 2,
    lines_per_bundle: int = 3,
    elements: bool = False,
    resources: bool = False,
    loose_lines: int = 0,
) -> Estimate:
    """Build a reproducible random estimate.

    Args:
        seed: Random seed.
        n_bundles: Number of top-level bundles.
        depth: Bundle nesting depth.
        lines_per_bundle: Estimate lines per innermost bundle.
        elements: Give bundles a ``DOORREKEN_HOEVEELHEID`` (an element estimate).
        resources: Give lines resource (MAMO) lines whose costs equal the line's unit prices.
        loose_lines: Number of estimate lines directly under the estimate.
    """
    rng = random.Random(seed)
    counter = [0]

    def line() -> Line:
        counter[0] += 1
        word = rng.choice(WORDS)
        ln = Line(
            code=f"{counter[0]:06d}",
            description=f"{word} {counter[0]}",
            unit=rng.choice(UNITS),
            quantity=_money(rng, 1, 400, 3),
            quantity_factor=rng.choice([None, D("1.05"), D("1.10"), D(1)]),
            hours_per_unit=_money(rng, 0, 3, 3),
            hourly_rate=_money(rng, 40, 70),
            material_price=_money(rng, 0, 250),
            equipment_price=rng.choice([None, _money(rng, 0, 30)]),
            subcontract_price=rng.choice([None, None, _money(rng, 0, 90)]),
            other_price=rng.choice([None, None, _money(rng, 0, 15)]),
            vat=rng.choice([D(21), D(9), D(0)]),
            sort_codes={"PLANCODE": rng.choice(["100-10", "200-10", "300-20"])},
        )
        if rng.random() < 0.4:
            ln.take_off = [
                (_money(rng, 1, 5, 0), _money(rng, 1, 20, 2), _money(rng, 1, 5, 2))
                for _ in range(rng.randint(1, 3))
            ]
        if resources:  # resource quantities are totals for the line (the default policy)
            q = (ln.quantity or D(0)) * (ln.quantity_factor or D(1))
            ln.resources = [
                Resource("LOON", q, hours_per_unit=ln.hours_per_unit, hourly_rate=ln.hourly_rate),
                Resource("MATERIAAL", q, price=ln.material_price),
            ]
            for kind, price in (
                ("MATERIEEL", ln.equipment_price),
                ("ONDERAANNEMING", ln.subcontract_price),
                ("OVERIG", ln.other_price),
            ):
                if price is not None:
                    ln.resources.append(Resource(kind, q, price=price))
        return ln

    def bundle(level: int, path: str) -> Bundle:
        counter[0] += 1
        b = Bundle(
            code=path,
            description=f"{rng.choice(WORDS)} (element {path})",
            unit=rng.choice(["m2", "st", "pst"]),
            multiplier=_money(rng, 1, 12, 0) if elements else None,
            reference_quantity=_money(rng, 1, 100, 0),
        )
        if level < depth:
            b.children = [bundle(level + 1, f"{path}.{i + 1}") for i in range(2)]
            if rng.random() < 0.5:
                b.children.append(line())  # a line next to sub-bundles
        else:
            b.children = [line() for _ in range(lines_per_bundle)]
        return b

    children: list[Bundle | Line] = [bundle(1, str(i + 1)) for i in range(n_bundles)]
    children.extend(line() for _ in range(loose_lines))
    est = Estimate(
        children=children,
        schemes={"PLANCODE": "Planningscode voor de werkvoorbereiding"},
    )
    direct = est.direct_costs()
    est.tail = [
        ("Algemene bedrijfskosten", (direct * D("0.06")).quantize(D("0.01"))),
        ("Winst en risico", (direct * D("0.03")).quantize(D("0.01"))),
    ]
    return est


# ------------------------------------------------------------------------------- writer
def _num(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


def _attrs(pairs: list[tuple[str, str | None]]) -> str:
    return "".join(f" {k}={quoteattr(v)}" for k, v in pairs if v is not None)


def write(
    est: Estimate,
    dialect: str = "standard",
    *,
    totals: str = "correct",
) -> bytes:
    """Render ``est`` as CUF-XML.

    Args:
        est: The estimate.
        dialect: ``standard``, ``ibis``, ``forum``, ``dataviewers`` or ``bakkerspees``.
        totals: Stated totals on bundles and the estimate: ``correct``, ``zero``, ``absent``
            (bundles only; the estimate's are required) or ``wrong`` (labour off by 100).
    """
    if dialect not in ("standard", "ibis", "forum", "dataviewers", "bakkerspees"):
        raise ValueError(dialect)
    if dialect == "dataviewers":
        totals = "zero"
    ibis = dialect == "ibis"
    out: list[str] = []
    w = out.append
    if dialect == "ibis":
        w('<?xml version="1.0" encoding="Windows-1252" standalone="yes"?>\n')
    elif dialect != "forum":
        w('<?xml version="1.0" encoding="UTF-8"?>\n')
    ns = "x-schema:Forum CUF-XML-schema4003.xsd" if dialect == "forum" else "x-schema:CufSchema.xml"
    extra_ns = ' xmlns:Ibis="http://www.brinkgroep.nl/ibis/xml"' if ibis else ""
    created = "1-10-2026 10:15:00" if dialect == "dataviewers" else "2026-10-01T10:15:00"
    w(f'<CUF xmlns="{ns}"{extra_ns} AANMAAKDATUMTIJD="{created}">\n')
    house = {"ibis": "BRINK", "dataviewers": "DV-CD", "bakkerspees": "Bakker & Spees"}.get(dialect)
    w(
        "  <PROJECTGEGEVENS"
        + _attrs(
            [
                ("CUF_VERSIE", "4.003"),
                ("SYSTEEMHUIS", house),
                ("AANMAAKDATUM", "1-10-2026" if dialect == "dataviewers" else "2026-10-01"),
                ("PROJECTNUMMER", est.project_number),
                ("PROJECTNAAM", est.project_name + (" – €" if ibis else "")),
                ("CALCULATOR", "J. de Calculator"),
                ("VALUTA", "" if dialect == "dataviewers" else "EUR"),
                ("EURO_KOERS", "1"),
                ("VRIJE_TEKST", "Revisie 2\nFictieve begroting" if dialect == "standard" else None),
            ]
        )
        + "/>\n"
    )
    for name, purpose in est.schemes.items():
        w(f"  <SORTEERCODES{_attrs([('SORTERING', name), ('FUNCTIE', purpose)])}/>\n")
    if ibis:
        w('  <SORTEERCODES SORTERING="stk" FUNCTIE="Tekstregels"/>\n')

    def stated(costs: dict[str, Decimal], *, bundle: bool) -> list[tuple[str, str | None]]:
        if totals == "absent" and bundle:
            return []
        pairs: list[tuple[str, str | None]] = []
        for dutch, key in zip(DUTCH_TOTALS, COSTS, strict=True):
            if ibis and bundle and dutch == "OVERIGE_KOSTEN":
                continue
            value = costs[key]
            if totals == "zero":
                value = D(0)
            elif totals == "wrong" and key == "labour":
                value += 100
            pairs.append((dutch, _num(value)))
        return pairs

    def sort_codes(codes: dict[str, str], indent: str) -> None:
        for scheme, value in codes.items():
            if dialect == "bakkerspees":
                w(f'{indent}<SORTEERCODE ACTI="{value}" NACA="1"/>\n')
            else:
                w(f"{indent}<SORTEERCODE{_attrs([('SORTERING', scheme), ('WAARDE', value)])}/>\n")

    def emit_line(ln: Line, indent: str) -> None:
        q_factor = ln.quantity_factor if not ibis else (ln.quantity_factor or D(1))
        pairs: list[tuple[str, str | None]] = [
            ("CODE", ln.code),
            ("OMSCHRIJVING", ln.description + (" geïsoleerd" if ibis else "")),
            ("HOEVEELHEID_EENHEID", ln.unit),
            ("HOEVEELHEID", _num(ln.quantity)),
            ("INZET", "1" if ibis else None),
            ("HOEVEELHEID_FACTOR", _num(q_factor)),
            ("UUR_NORM", _num(ln.hours_per_unit)),
            ("UUR_TARIEF", _num(ln.hourly_rate)),
            ("MATERIAALPRIJS", _num(ln.material_price)),
            ("MATERIEELPRIJS", _num(ln.equipment_price)),
            ("ONDERAANNEMINGSPRIJS", _num(ln.subcontract_price)),
            ("OVERIGE_KOSTEN", _num(ln.other_price)),
            ("STELPOST", "0" if dialect == "dataviewers" else None),
            ("BTW", "" if ibis else _num(ln.vat)),
        ]
        if dialect == "bakkerspees":
            pairs.append(("WERKBESCHRIJVING", f"Werkbeschrijving van {ln.description}"))
        w(f"{indent}<BEGROTINGSREGEL{_attrs(pairs)}>\n")
        for count, length, width in ln.take_off:
            w(
                f"{indent}  <HOEVEELHEDENSTAAT_REGEL"
                + _attrs(
                    [
                        ("RUIMTE_NAAM", "begane grond"),
                        ("AANTAL", _num(count)),
                        ("LENGTE", _num(length)),
                        ("BREEDTE", _num(width)),
                    ]
                )
                + "/>\n"
            )
        for r in ln.resources:
            rp: list[tuple[str, str | None]] = [
                ("KOSTENSOORT", r.cost_type),
                ("OMSCHRIJVING", r.description),
                ("HOEVEELHEID", _num(r.quantity)),
                ("PRIJS", _num(r.price)),
                ("PRIJS_FACTOR", _num(r.price_factor)),
                ("UUR_NORM", _num(r.hours_per_unit)),
                ("UUR_TARIEF", _num(r.hourly_rate)),
            ]
            if dialect == "bakkerspees":
                rp.append(("KOSTPRIJS", _num(r.price)))
            w(f"{indent}  <MAMO_REGEL{_attrs(rp)}/>\n")
        sort_codes(ln.sort_codes, indent + "  ")
        w(f"{indent}</BEGROTINGSREGEL>\n")

    def emit_text_line(text: str, indent: str) -> None:
        w(f'{indent}<BEGROTINGSREGEL OMSCHRIJVING={quoteattr(text)} BTW="">\n')
        w(f'{indent}  <SORTEERCODE SORTERING="stk" WAARDE="&quot;"/>\n')
        w(f"{indent}</BEGROTINGSREGEL>\n")

    def emit_bundle(b: Bundle, indent: str) -> None:
        pairs: list[tuple[str, str | None]] = [
            ("CODE", b.code),
            ("CODERING_METHODE", "NLSFB"),
            ("OMSCHRIJVING", b.description),
            ("EENHEID", b.unit),
            ("TERUGDEEL_HOEVEELHEID", _num(b.reference_quantity)),
            ("DOORREKEN_HOEVEELHEID", _num(b.multiplier)),
            *stated(b.costs(), bundle=True),
        ]
        w(f"{indent}<BUNDELING{_attrs(pairs)}>\n")
        if ibis:
            emit_text_line(f"Toelichting bij {b.description}", indent + "  ")
        for child in b.children:
            if isinstance(child, Bundle):
                emit_bundle(child, indent + "  ")
            else:
                emit_line(child, indent + "  ")
        sort_codes(b.sort_codes, indent + "  ")
        w(f"{indent}</BUNDELING>\n")

    w(f"  <BEGROTING{_attrs(stated(est.expected(), bundle=False))}>\n")
    if dialect == "bakkerspees":
        for ln in est.lines():  # flat: every line directly under the estimate
            emit_line(ln, "    ")
    else:
        for child in est.children:
            if isinstance(child, Bundle):
                emit_bundle(child, "    ")
            else:
                emit_line(child, "    ")
    w("  </BEGROTING>\n")
    if dialect not in ("dataviewers", "bakkerspees"):
        w(f'  <STAARTGEGEVENS AANNEEMSOM="{_num(est.contract_sum())}">\n')
        for description, amount in est.tail:
            w(
                f"    <VRIJE_GROOTHEID{_attrs([('OMSCHRIJVING', description), ('BEDRAG', _num(amount))])}/>\n"
            )
        w("  </STAARTGEGEVENS>\n")
    w("</CUF>\n")
    text = "".join(out)
    if ibis:
        return text.replace("\n", "\r\n").encode("cp1252")
    return text.encode("utf-8")

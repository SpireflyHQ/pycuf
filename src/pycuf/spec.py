"""The CUF-XML 4.003 catalogue: every element and attribute, with types and English names.

This is pycuf's machine-readable description of the format. It drives the structure checks in
:mod:`pycuf.validate`, the mapping from Dutch attribute names to the English attributes of
:mod:`pycuf.models`, and the generated glossary in the documentation. It is written from the
CUF-XML 4.003 schema (Forum Systeemhuizen Bouw, now maintained by Ketenstandaard Bouw en
Techniek) and its usage rules ("Gebruikersregels CUF 4003"), in pycuf's own words.

Data types follow Microsoft XDR, which the 4.003 schema uses: ``number``, ``date``,
``datetime``, ``boolean``, ``string`` and ``enum`` (a closed list of values).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

__all__ = [
    "ELEMENTS",
    "SOFTWARE_HOUSES",
    "SUPPORTED_VERSIONS",
    "VERSION",
    "AttributeSpec",
    "ElementSpec",
    "ValueType",
]

ValueType = Literal["string", "number", "date", "datetime", "boolean", "enum"]

VERSION = "4.003"
"""The CUF-XML version this catalogue describes (the latest; there is no newer one)."""
SUPPORTED_VERSIONS = frozenset({"4.000", "4.001", "4.002", "4.003"})
"""``CUF_VERSIE`` values pycuf reads as CUF-XML (4.000–4.002 differ only in details)."""

#: The 4.003 list of software houses (``SYSTEEMHUIS``); real files also carry other values.
SOFTWARE_HOUSES = frozenset(
    [
        "ADMICOM",
        "ARKEY",
        "BRINK",
        "CTB",
        "DUNCAN",
        "ENK",
        "KOOIJMAN",
        "KPD",
        "KRAAN",
        "NCCWCASA",
        "PIRAMIDE",
        "PLUSINTEGRATION",
        "SCAB",
        "SETZ",
        "STABIPLAN",
        "TWEESNOEKEN",
        "VANENBURG",
        "VANMEIJEL",
        "VMV",
    ]
)

#: Currency codes allowed by the 4.003 schema (``VALUTA``), including pre-euro currencies.
CURRENCIES = frozenset(
    [
        "AWG",
        "AUD",
        "BHD",
        "BEF",
        "BGL",
        "CAD",
        "CNY",
        "CYP",
        "DKK",
        "DEM",
        "EGP",
        "GBP",
        "ESK",
        "EUR",
        "PHP",
        "FIM",
        "FRF",
        "GRD",
        "HKD",
        "HUF",
        "IEP",
        "ISK",
        "ILS",
        "INR",
        "IDR",
        "ITL",
        "JPY",
        "KES",
        "KWD",
        "LTL",
        "LUF",
        "MAD",
        "MWK",
        "MTL",
        "MXN",
        "ANG",
        "NLG",
        "NZD",
        "NOK",
        "UAH",
        "OMR",
        "ATS",
        "PKR",
        "PLN",
        "PTE",
        "QAR",
        "ROL",
        "RUB",
        "SAR",
        "SGD",
        "SIT",
        "SKK",
        "ESP",
        "LKR",
        "SRG",
        "THB",
        "CZK",
        "TND",
        "TRL",
        "AED",
        "USD",
        "ZWD",
        "ZAR",
        "SEK",
        "CHF",
    ]
)

COST_TYPES = frozenset({"LOON", "MATERIAAL", "MATERIEEL", "ONDERAANNEMING", "OVERIG"})


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    """One attribute of a CUF-XML element.

    Attributes:
        name: The Dutch attribute name as written in files (``HOEVEELHEID_FACTOR``).
        type: XDR data type.
        field: Name of the corresponding attribute in :mod:`pycuf.models` (``quantity_factor``).
        description: Short English description.
        required: Whether CUF-XML 4.003 requires the attribute.
        values: Allowed values for ``enum`` attributes.
    """

    name: str
    type: ValueType
    field: str
    description: str
    required: bool = False
    values: frozenset[str] | None = None


@dataclass(frozen=True, slots=True)
class ElementSpec:
    """One CUF-XML element.

    Attributes:
        name: The Dutch element name (``BEGROTINGSREGEL``).
        model: Name of the class in :mod:`pycuf.models` (``Line``).
        description: Short English description.
        attributes: Attribute specifications by Dutch name, in schema order.
        children: Allowed child elements: name → ``(min, max)`` occurrences (``max`` ``None`` =
            unbounded).
        ordered: Whether children must appear in the listed order (only ``CUF``).
    """

    name: str
    model: str
    description: str
    attributes: Mapping[str, AttributeSpec]
    children: Mapping[str, tuple[int, int | None]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    ordered: bool = False


def _a(
    name: str,
    type_: ValueType,
    field_: str,
    description: str,
    *,
    required: bool = False,
    values: frozenset[str] | None = None,
) -> AttributeSpec:
    return AttributeSpec(name, type_, field_, description, required, values)


def _e(
    name: str,
    model: str,
    description: str,
    attributes: list[AttributeSpec],
    children: dict[str, tuple[int, int | None]] | None = None,
    *,
    ordered: bool = False,
) -> ElementSpec:
    return ElementSpec(
        name,
        model,
        description,
        MappingProxyType({a.name: a for a in attributes}),
        MappingProxyType(children or {}),
        ordered,
    )


# ---------------------------------------------------------------- shared attribute groups
def _line_quantities(*, mamo: bool = False) -> list[AttributeSpec]:
    target = "estimate line" if mamo else "parent bundle"
    return [
        _a("HOEVEELHEID_EENHEID", "string", "unit", "Unit of the quantity (m2, m3, st, kg, …)."),
        _a("HOEVEELHEID", "number", "quantity", "Quantity; empty or missing counts as 0."),
        _a("AANTAL_EENHEID", "string", "count_unit", "Unit of the count (often pieces)."),
        _a(
            "AANTAL",
            "number",
            "count",
            "Number deployed, for time-bound costs (count × duration = quantity; informative).",
        ),
        _a("INZET_EENHEID", "string", "duration_unit", "Unit of the duration (weeks, days, …)."),
        _a("INZET", "number", "duration", "Length of the period deployed (informative)."),
        _a("PRODUCTIE_EENHEID", "string", "production_unit", "Unit of the production rate."),
        _a(
            "PRODUCTIE",
            "number",
            "production",
            f"Production rate relative to the {target} (informative).",
        ),
    ]


def _article() -> list[AttributeSpec]:
    return [
        _a("EAN_CODE", "string", "ean_code", "EAN (GTIN) barcode of the article."),
        _a("ARTIKELGROEP", "string", "article_group", "Article group code."),
        _a("BESTELEENHEID", "string", "order_unit", "Unit in which the article is ordered."),
        _a(
            "HOEVEELHEIDPEREENHEID",
            "number",
            "quantity_per_order_unit",
            "Number of units per order unit.",
        ),
        _a("LEVERANCIERSCODE", "string", "supplier_code", "Supplier code."),
        _a("COMMENTAAR", "string", "comment", "Free-text comment."),
    ]


def _totals(*, required: bool) -> list[AttributeSpec]:
    return [
        _a("UREN", "number", "hours", "Total labour hours.", required=required),
        _a("LOONKOSTEN", "number", "labour", "Total labour costs.", required=required),
        _a("MATERIAALKOSTEN", "number", "material", "Total material costs.", required=required),
        _a(
            "MATERIEELKOSTEN",
            "number",
            "equipment",
            "Total equipment (plant) costs.",
            required=required,
        ),
        _a(
            "ONDERAANNEMING",
            "number",
            "subcontracting",
            "Total subcontracting costs.",
            required=required,
        ),
        _a("OVERIGE_KOSTEN", "number", "other", "Total other costs.", required=required),
    ]


_QTY_LINE = {"HOEVEELHEDENSTAAT_REGEL": (0, None)}
_SORT = {"SORTEERCODE": (0, None)}

#: Every element of CUF-XML 4.003 by Dutch name.
ELEMENTS: Mapping[str, ElementSpec] = MappingProxyType(
    {
        e.name: e
        for e in (
            _e(
                "CUF",
                "CufFile",
                "The document: project data, sort-code schemes, the estimate and the tail.",
                [
                    _a(
                        "AANMAAKDATUMTIJD",
                        "datetime",
                        "created",
                        "Date and time the CUF file was written.",
                        required=True,
                    )
                ],
                {
                    "PROJECTGEGEVENS": (1, 1),
                    "SORTEERCODES": (0, None),
                    "BEGROTING": (1, 1),
                    "STAARTGEGEVENS": (1, 1),
                },
                ordered=True,
            ),
            _e(
                "PROJECTGEGEVENS",
                "Project",
                "General data about the project and the estimate.",
                [
                    _a(
                        "CUF_VERSIE",
                        "enum",
                        "cuf_version",
                        "CUF-XML version of the file; always 4.003 for this version.",
                        required=True,
                        values=frozenset({VERSION}),
                    ),
                    _a(
                        "SYSTEEMHUIS",
                        "enum",
                        "software_house",
                        "Vendor of the software that wrote the file.",
                        values=SOFTWARE_HOUSES,
                    ),
                    _a(
                        "AANMAAKDATUM",
                        "date",
                        "estimate_date",
                        "Date the estimate was created in the estimating software.",
                        required=True,
                    ),
                    _a("PROJECTNUMMER", "string", "number", "Project number."),
                    _a("PROJECTNAAM", "string", "name", "Project name."),
                    _a("CALCULATOR", "string", "estimator", "Person who made the estimate."),
                    _a("OPDRACHTGEVER", "string", "client", "Client who commissions the work."),
                    _a("ADRESGEGEVENS", "string", "address", "Location of the building site."),
                    _a("PROJECTSTARTDATUM", "date", "start_date", "Start date of construction."),
                    _a(
                        "VALUTA",
                        "enum",
                        "currency",
                        "Currency of all amounts (ISO 4217 code).",
                        required=True,
                        values=CURRENCIES,
                    ),
                    _a(
                        "EURO_KOERS",
                        "number",
                        "euro_rate",
                        "Units of the currency that equal one euro.",
                    ),
                    _a("VRIJE_TEKST", "string", "notes", "Additional free text."),
                ],
            ),
            _e(
                "SORTEERCODES",
                "SortCodeScheme",
                "Declares one sort-code scheme used in the estimate, optionally with its codes.",
                [
                    _a(
                        "SORTERING",
                        "string",
                        "name",
                        "Name of the scheme (PLANCODE, ADMICODE, …).",
                        required=True,
                    ),
                    _a("FUNCTIE", "string", "purpose", "What the scheme is used for."),
                ],
                {"SORTEERCODE_REGEL": (0, None)},
            ),
            _e(
                "SORTEERCODE_REGEL",
                "SortCodeEntry",
                "One code of a sort-code scheme.",
                [
                    _a("CODE", "string", "code", "The sort code."),
                    _a("OMSCHRIJVING", "string", "description", "Description of the code."),
                    _a("EENHEID", "string", "unit", "Unit of the reference quantity."),
                    _a(
                        "TERUGDEEL_HOEVEELHEID",
                        "number",
                        "reference_quantity",
                        "Quantity of this code in the estimate, for unit rates (informative).",
                    ),
                ],
            ),
            _e(
                "SORTEERCODE",
                "SortCode",
                "Assigns a sort code of one scheme to a bundle, line or resource line.",
                [
                    _a(
                        "SORTERING",
                        "string",
                        "scheme",
                        "Name of the scheme the code belongs to.",
                        required=True,
                    ),
                    _a("WAARDE", "string", "value", "The sort code."),
                ],
            ),
            _e(
                "HOEVEELHEDENSTAAT_REGEL",
                "QuantityLine",
                "A quantity take-off line explaining where a quantity comes from (informative).",
                [
                    _a("RUIMTE_NAAM", "string", "room", "Room or location of the measured part."),
                    _a("OMSCHRIJVING", "string", "description", "Description of the measurement."),
                    _a("AANTAL", "number", "count", "Number of times the part occurs."),
                    _a("LENGTE", "number", "length", "Length."),
                    _a("BREEDTE", "number", "width", "Width."),
                    _a("HOOGTE", "number", "height", "Height."),
                    _a("FACTOR_1", "number", "factor_1", "Multiplier, e.g. a unit conversion."),
                    _a("FACTOR_2", "number", "factor_2", "Second multiplier."),
                ],
            ),
            _e(
                "MAMO_REGEL",
                "ResourceLine",
                "A resource line (MAMO): breaks an estimate line down into one cost type.",
                [
                    _a(
                        "KOSTENSOORT",
                        "enum",
                        "cost_type",
                        "Cost type: LOON, MATERIAAL, MATERIEEL, ONDERAANNEMING or OVERIG.",
                        required=True,
                        values=COST_TYPES,
                    ),
                    _a("CODE", "string", "code", "Resource code."),
                    _a("OMSCHRIJVING", "string", "description", "Description of the resource."),
                    *_line_quantities(mamo=True),
                    _a("PRIJS", "number", "price", "Unit price (cost types other than LOON)."),
                    _a(
                        "PRIJS_FACTOR",
                        "number",
                        "price_factor",
                        "Multiplier on the price or hourly rate (1.10 = 10% surcharge).",
                    ),
                    _a("FACTORCODE", "string", "factor_code", "Code of the price factor."),
                    _a("UUR_NORM", "number", "hours_per_unit", "Labour hours per unit (LOON)."),
                    _a("UUR_TARIEF", "number", "hourly_rate", "Hourly rate (LOON)."),
                    _a("UUR_TARIEFCODE", "string", "hourly_rate_code", "Code of the hourly rate."),
                    *_article(),
                ],
                {**_QTY_LINE, **_SORT},
            ),
            _e(
                "BEGROTINGSREGEL",
                "Line",
                "An estimate line: a quantity with unit prices for up to five cost types.",
                [
                    _a("CODE", "string", "code", "Line code (does not define the hierarchy)."),
                    _a("OMSCHRIJVING", "string", "description", "Description of the work."),
                    *_line_quantities(),
                    _a(
                        "HOEVEELHEID_FACTOR",
                        "number",
                        "quantity_factor",
                        "Multiplier on the quantity (1.10 = 10% waste); empty counts as 1.",
                    ),
                    _a("FACTORCODE", "string", "factor_code", "Code of the quantity factor."),
                    _a("UUR_NORM", "number", "hours_per_unit", "Labour hours per unit."),
                    _a("UUR_TARIEF", "number", "hourly_rate", "Hourly rate."),
                    _a("UUR_TARIEFCODE", "string", "hourly_rate_code", "Code of the hourly rate."),
                    _a("MATERIAALPRIJS", "number", "material_price", "Material price per unit."),
                    _a("MATERIEELPRIJS", "number", "equipment_price", "Equipment price per unit."),
                    _a(
                        "ONDERAANNEMINGSPRIJS",
                        "number",
                        "subcontract_price",
                        "Subcontracting price per unit.",
                    ),
                    _a("OVERIGE_KOSTEN", "number", "other_price", "Other costs per unit."),
                    _a(
                        "STELPOST",
                        "boolean",
                        "provisional_sum",
                        "Whether the line is a provisional sum (stelpost).",
                    ),
                    _a(
                        "BTW",
                        "number",
                        "vat_rate",
                        "VAT percentage for the line and everything below it.",
                        required=True,
                    ),
                    *_article(),
                ],
                {**_QTY_LINE, "MAMO_REGEL": (0, None), **_SORT},
            ),
            _e(
                "BUNDELING",
                "Bundle",
                "A bundle: groups lines and bundles (chapter, paragraph or element).",
                [
                    _a("CODE", "string", "code", "Bundle code (does not define the hierarchy)."),
                    _a(
                        "CODERING_METHODE",
                        "string",
                        "coding_method",
                        "Coding system of the code (NLSFB, Bouwdelen, …).",
                    ),
                    _a("OMSCHRIJVING", "string", "description", "Description of the bundle."),
                    _a(
                        "EENHEID",
                        "string",
                        "unit",
                        "Unit of the reference quantity and multiplier.",
                    ),
                    _a(
                        "TERUGDEEL_HOEVEELHEID",
                        "number",
                        "reference_quantity",
                        "Quantity of the bundle, for a unit rate (informative).",
                    ),
                    _a(
                        "DOORREKEN_HOEVEELHEID",
                        "number",
                        "multiplier",
                        "Element quantity that multiplies all costs below; empty counts as 1.",
                    ),
                    *_totals(required=False),
                    _a("COMMENTAAR", "string", "comment", "Free-text comment."),
                ],
                {"BUNDELING": (0, None), "BEGROTINGSREGEL": (0, None), **_QTY_LINE, **_SORT},
            ),
            _e(
                "BEGROTING",
                "Estimate",
                "The estimate: direct costs excluding markups and VAT, as a tree of bundles.",
                _totals(required=True),
                {"BUNDELING": (0, None), "BEGROTINGSREGEL": (0, None)},
            ),
            _e(
                "STAARTGEGEVENS",
                "Tail",
                "The tail (staart): markups and the contract sum.",
                [
                    _a(
                        "AANNEEMSOM",
                        "number",
                        "contract_sum",
                        "Contract sum including markups, excluding VAT.",
                        required=True,
                    )
                ],
                {"VRIJE_GROOTHEID": (0, None)},
            ),
            _e(
                "VRIJE_GROOTHEID",
                "TailItem",
                "One tail item, such as overheads, profit and risk, or the VAT amount.",
                [
                    _a("OMSCHRIJVING", "string", "description", "Name of the tail item."),
                    _a("BEDRAG", "number", "amount", "Amount of the tail item.", required=True),
                ],
            ),
        )
    }
)

"""Normalized tables for analysis and export.

Every table has a fixed schema (column names and logical types). Computed columns (``hours``,
``labour`` … ``total``) depend on the calculation policy; they use the file's policy unless another
one is given (``Tables(cuf, policy="erp")``, ``cuf.export(dir, policy="erp")``).

=====================  ======================================================================
Table                  Rows
=====================  ======================================================================
``project``            one row: file and project data, stated and computed estimate totals
``bundles``            bundles (``BUNDELING``), with stated and computed totals
``lines``              estimate lines (``BEGROTINGSREGEL``), with computed costs
``resource_lines``     resource lines (``MAMO_REGEL``), with computed costs
``quantity_lines``     quantity take-off lines (``HOEVEELHEDENSTAAT_REGEL``)
``sort_codes``         effective sort codes of bundles, lines and resource lines
``sort_code_schemes``  declared sort-code schemes (``SORTEERCODES``)
``sort_code_entries``  the code tables of the schemes (``SORTEERCODE_REGEL``)
``tail_items``         tail items (``VRIJE_GROOTHEID``)
=====================  ======================================================================

Rows are joined by synthetic keys, because codes in real files are neither unique nor
mandatory: ``lines.bundle_seq`` → ``bundles.seq``, ``resource_lines.line_seq`` → ``lines.seq``,
and ``owner_type``/``owner_seq`` for quantity lines and sort codes.

Logical types: ``string``, ``int64``, ``bool``, ``date``, ``timestamp`` and ``number``. A
``number`` is a :class:`decimal.Decimal` in Python and ``decimal128(28, 15)`` in Arrow: 13 integer
digits and 15 decimals, which holds every value seen in real CUF files exactly.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .models import COST_FIELDS, Bundle, Costs, Line, ResourceLine
from .policy import Policy, PresetName

if TYPE_CHECKING:
    from .calc import Totals
    from .reader import CufFile

__all__ = ["NUMBER", "TABLES", "Column", "ExportFormat", "OnInexact", "Table", "Tables"]

Row = tuple[Any, ...]
ExportFormat = Literal["csv", "jsonl", "parquet"]
OnInexact = Literal["raise", "null", "round"]
"""What Arrow-based exports do with a number that does not fit ``decimal128(28, 15)`` exactly
(more than 15 decimals, or 13 integer digits): raise ``ValueError`` (default), write null, or
round half-even to 15 decimals."""

NUMBER = (28, 15)
"""Arrow precision and scale of ``number`` columns."""

_MAX_PLAIN = 2_000
"""Most characters CSV and JSONL spend on one number. Every number pycuf reads fits (at most 309
integer digits and 1,074 decimals); only computed values from absurd inputs, such as nested
multipliers of 1E+300, can exceed it."""


@dataclass(frozen=True, slots=True)
class Column:
    """A table column: name and logical type."""

    name: str
    type: str


def _cols(spec: str) -> tuple[Column, ...]:
    out = []
    for item in spec.split():
        name, _, typ = item.partition(":")
        out.append(Column(name, typ or "string"))
    return tuple(out)


_N = "number"
_COSTS = " ".join(f"{name}:{_N}" for name in COST_FIELDS) + f" total:{_N}"
_STATED = " ".join(f"stated_{name}:{_N}" for name in COST_FIELDS)
_ARTICLE = f"ean_code article_group order_unit quantity_per_order_unit:{_N} supplier_code comment"
_QTY = (
    f"unit quantity:{_N} count_unit count:{_N} duration_unit duration:{_N} "
    f"production_unit production:{_N}"
)

#: Schema of every table.
TABLES: dict[str, tuple[Column, ...]] = {
    "project": _cols(
        "file cuf_version software_house created:timestamp encoding namespace "
        "number name estimator client address estimate_date:date start_date:date currency "
        f"euro_rate:{_N} notes contract_sum:{_N} {_STATED} {_COSTS} estimate_style "
        "bundle_count:int64 line_count:int64"
    ),
    "bundles": _cols(
        "seq:int64 parent_seq:int64 depth:int64 path code coding_method description unit "
        f"reference_quantity:{_N} multiplier:{_N} {_STATED} {_COSTS} "
        f"applied_multiplier:{_N} extended_total:{_N} comment xml_line:int64"
    ),
    "lines": _cols(
        "seq:int64 bundle_seq:int64 depth:int64 path code description "
        f"{_QTY} quantity_factor:{_N} factor_code hours_per_unit:{_N} hourly_rate:{_N} "
        f"hourly_rate_code material_price:{_N} equipment_price:{_N} subcontract_price:{_N} "
        f"other_price:{_N} provisional_sum:bool vat_rate:{_N} {_ARTICLE} "
        f"is_text:bool resource_count:int64 priced_by_resources:bool {_COSTS} "
        f"applied_multiplier:{_N} extended_total:{_N} xml_line:int64"
    ),
    "resource_lines": _cols(
        "seq:int64 line_seq:int64 cost_type code description "
        f"{_QTY} price:{_N} price_factor:{_N} factor_code hours_per_unit:{_N} "
        f"hourly_rate:{_N} hourly_rate_code {_ARTICLE} {_COSTS} xml_line:int64"
    ),
    "quantity_lines": _cols(
        "seq:int64 owner_type owner_seq:int64 room description "
        f"count:{_N} length:{_N} width:{_N} height:{_N} factor_1:{_N} factor_2:{_N} "
        f"product:{_N} xml_line:int64"
    ),
    "sort_codes": _cols("owner_type owner_seq:int64 scheme value inherited:bool"),
    "sort_code_schemes": _cols("seq:int64 name purpose entry_count:int64"),
    "sort_code_entries": _cols(
        f"scheme_seq:int64 scheme code description unit reference_quantity:{_N}"
    ),
    "tail_items": _cols(f"seq:int64 description amount:{_N}"),
}


def _costs(c: Costs) -> Row:
    return (c.hours, c.labour, c.material, c.equipment, c.subcontracting, c.other, c.total)


def _line_no(node: Any) -> int | None:
    raw = getattr(node, "raw", None)
    return raw.line if raw is not None else None


class Table:
    """One normalized table: its schema plus rows built from the file.

    With ``pycuf[arrow]`` installed a table implements the Arrow PyCapsule interface
    (``__arrow_c_stream__``, ``__arrow_c_array__``, ``__arrow_c_schema__``), so
    ``polars.DataFrame(table)``, ``pyarrow.table(table)`` and DuckDB consume it directly.
    """

    def __init__(self, tables: Tables, name: str) -> None:
        if name not in TABLES:
            raise KeyError(f"unknown table {name!r}; choose from {', '.join(TABLES)}")
        self._tables = tables
        self.name = name
        self.columns: tuple[Column, ...] = TABLES[name]
        self._arrow: dict[str, Any] = {}

    @property
    def column_names(self) -> tuple[str, ...]:
        """Names of the columns."""
        return tuple(c.name for c in self.columns)

    def rows(self) -> Iterator[Row]:
        """Yield rows as tuples of Python values (``Decimal``, ``date``, ``str``, ``int`` …)."""
        return self._tables._rows(self.name)

    def dicts(self) -> Iterator[dict[str, Any]]:
        """Yield rows as dictionaries."""
        names = self.column_names
        for row in self.rows():
            yield dict(zip(names, row, strict=True))

    def __len__(self) -> int:
        return sum(1 for _ in self.rows())

    def _batch(self, on_inexact: OnInexact = "raise") -> Any:
        batch = self._arrow.get(on_inexact)
        if batch is None:
            from ._arrow import build_batch  # noqa: PLC0415

            batch = self._arrow[on_inexact] = build_batch(
                self.name, self.columns, list(self.rows()), on_inexact
            )
        return batch

    def __arrow_c_schema__(self) -> object:
        from ._arrow import schema  # noqa: PLC0415

        return schema(self.columns).__arrow_c_schema__()

    def __arrow_c_array__(self, requested_schema: object | None = None) -> tuple[object, object]:
        """Arrow PyCapsule array (one record batch); ``requested_schema`` is ignored."""
        return self._batch().__arrow_c_array__()  # type: ignore[no-any-return]

    def __arrow_c_stream__(self, requested_schema: object | None = None) -> object:
        """Arrow PyCapsule stream (one record batch); ``requested_schema`` is ignored."""
        from ._arrow import stream  # noqa: PLC0415

        return stream(self.columns, self._batch()).__arrow_c_stream__()

    def to_arrow(self, on_inexact: OnInexact = "raise") -> Any:
        """The table as a nanoarrow struct array (needs ``pycuf[arrow]``)."""
        return self._batch(on_inexact)

    def to_polars(self, on_inexact: OnInexact = "raise") -> Any:
        """Return a polars DataFrame (needs ``pycuf[polars]``; no pyarrow)."""
        from ._arrow import to_polars  # noqa: PLC0415

        return to_polars(self._batch(on_inexact))

    def to_pandas(self, on_inexact: OnInexact = "raise") -> Any:
        """Return a pandas DataFrame with Arrow-backed dtypes (needs ``pycuf[pandas]``)."""
        from ._arrow import to_pandas  # noqa: PLC0415

        return to_pandas(self.columns, self._batch(on_inexact))

    def __repr__(self) -> str:
        return f"<Table {self.name!r} columns={len(self.columns)}>"


class Tables:
    """All normalized tables of a :class:`~pycuf.CufFile` (see the module documentation).

    Args:
        cuf: The file.
        policy: Policy for the computed columns (default: the file's policy).
    """

    def __init__(self, cuf: CufFile, policy: Policy | PresetName | None = None) -> None:
        self._cuf = cuf
        self.totals: Totals = cuf.totals(policy=policy)
        """The computed totals behind the computed columns."""

    @property
    def names(self) -> tuple[str, ...]:
        """Table names."""
        return tuple(TABLES)

    def __getitem__(self, name: str) -> Table:
        return Table(self, name)

    def __iter__(self) -> Iterator[str]:
        return iter(TABLES)

    def __len__(self) -> int:
        return len(TABLES)

    # ------------------------------------------------------------------ rows
    def _path(self, node: Bundle | Line) -> str:
        parts = [b.code or b.description or f"#{b.seq}" for b in self._cuf.ancestors(node)]
        if isinstance(node, Bundle):
            parts.append(node.code or node.description or f"#{node.seq}")
        return " / ".join(parts)

    def _rows(self, name: str) -> Iterator[Row]:
        cuf = self._cuf
        totals = self.totals
        if name == "project":
            p = cuf.project
            tail = cuf.tail
            yield (
                cuf.name, p.cuf_version, p.software_house, cuf.created,
                cuf.encoding.effective, cuf.namespace, p.number, p.name, p.estimator, p.client,
                p.address, p.estimate_date, p.start_date, p.currency, p.euro_rate, p.notes,
                tail.contract_sum if tail else None,
                *(v for _, v in cuf.estimate.stated.items()), *_costs(totals.estimate),
                totals.estimate_style, len(cuf.bundles), len(cuf.lines),
            )  # fmt: skip
        elif name == "bundles":
            for b in cuf.bundles:
                yield (
                    b.seq, b.parent_seq, b.depth, self._path(b), b.code, b.coding_method,
                    b.description, b.unit, b.reference_quantity, b.multiplier,
                    *(v for _, v in b.stated.items()), *_costs(totals[b]),
                    totals.multiplier(b), totals.extended(b).total, b.comment, _line_no(b),
                )  # fmt: skip
        elif name == "lines":
            for ln in cuf.lines:
                yield (
                    ln.seq, ln.bundle_seq, ln.depth, self._path(ln), ln.code, ln.description,
                    ln.unit, ln.quantity, ln.count_unit, ln.count, ln.duration_unit, ln.duration,
                    ln.production_unit, ln.production, ln.quantity_factor, ln.factor_code,
                    ln.hours_per_unit, ln.hourly_rate, ln.hourly_rate_code, ln.material_price,
                    ln.equipment_price, ln.subcontract_price, ln.other_price, ln.provisional_sum,
                    ln.vat_rate, ln.ean_code, ln.article_group, ln.order_unit,
                    ln.quantity_per_order_unit, ln.supplier_code, ln.comment, ln.is_text,
                    len(ln.resources), totals.priced_by_resources(ln), *_costs(totals[ln]),
                    totals.multiplier(ln), totals.extended(ln).total, _line_no(ln),
                )  # fmt: skip
        elif name == "resource_lines":
            for r in cuf.resource_lines:
                yield (
                    r.seq, r.line_seq, r.cost_type_code, r.code, r.description, r.unit,
                    r.quantity, r.count_unit, r.count, r.duration_unit, r.duration,
                    r.production_unit, r.production, r.price, r.price_factor, r.factor_code,
                    r.hours_per_unit, r.hourly_rate, r.hourly_rate_code, r.ean_code,
                    r.article_group, r.order_unit, r.quantity_per_order_unit, r.supplier_code,
                    r.comment, *_costs(totals.resource(r)), _line_no(r),
                )  # fmt: skip
        elif name == "quantity_lines":
            for owner_type, owner in self._owners():
                for q in owner.quantity_lines:
                    yield (
                        q.seq, owner_type, owner.seq, q.room, q.description, q.count, q.length,
                        q.width, q.height, q.factor_1, q.factor_2, q.product, _line_no(q),
                    )  # fmt: skip
        elif name == "sort_codes":
            for owner_type, owner in self._owners():
                own = {c.scheme for c in owner.sort_codes}
                for scheme, value in cuf.sort_codes(owner).items():
                    yield (owner_type, owner.seq, scheme, value, scheme not in own)
        elif name == "sort_code_schemes":
            for i, s in enumerate(cuf.sort_code_schemes):
                yield (i, s.name, s.purpose, len(s.entries))
        elif name == "sort_code_entries":
            for i, s in enumerate(cuf.sort_code_schemes):
                for e in s.entries:
                    yield (i, s.name, e.code, e.description, e.unit, e.reference_quantity)
        elif name == "tail_items":
            if cuf.tail is not None:
                for i, item in enumerate(cuf.tail.items):
                    yield (i, item.description, item.amount)
        else:  # pragma: no cover - guarded by Table
            raise KeyError(name)

    def _owners(self) -> Iterator[tuple[str, Bundle | Line | ResourceLine]]:
        for b in self._cuf.bundles:
            yield "bundle", b
        for ln in self._cuf.lines:
            yield "line", ln
        for r in self._cuf.resource_lines:
            yield "resource_line", r

    # ---------------------------------------------------------------- export
    def export(
        self,
        directory: str | os.PathLike[str],
        *,
        format: ExportFormat = "csv",
        tables: Iterable[str] | None = None,
        on_inexact: OnInexact = "raise",
    ) -> list[str]:
        """Write tables to ``directory`` (one file per table); return the written paths.

        ``csv`` and ``jsonl`` need no dependencies (numbers are written as exact strings in plain
        notation, dates in ISO 8601); ``parquet`` needs ``pycuf[parquet]``. A computed number
        whose plain notation would take more than 2,000 characters (only absurd inputs produce
        one) raises ``ValueError`` naming the table, column and row.
        """
        names = _names(tables)
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        if format == "parquet":
            from ._arrow import write_parquet  # noqa: PLC0415

            return [
                write_parquet(self[n].columns, self[n]._batch(on_inexact), out / f"{n}.parquet")
                for n in names
            ]
        if format not in ("csv", "jsonl"):
            raise ValueError("format must be 'csv', 'jsonl' or 'parquet'")
        paths = []
        for n in names:
            path = out / f"{n}.{format}"
            cols = [c.name for c in TABLES[n]]
            convert = _csv_value if format == "csv" else _json_value
            rows = (
                [_cell(n, col, i, v, convert) for col, v in zip(cols, row, strict=True)]
                for i, row in enumerate(self._rows(n))
            )
            with path.open("w", encoding="utf-8", newline="") as fh:
                if format == "csv":
                    writer = csv.writer(fh)
                    writer.writerow(cols)
                    writer.writerows(rows)
                else:
                    for values in rows:
                        record = dict(zip(cols, values, strict=True))
                        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            paths.append(str(path))
        return paths

    def to_polars(
        self, tables: Iterable[str] | None = None, *, on_inexact: OnInexact = "raise"
    ) -> dict[str, Any]:
        """Return polars DataFrames by table name (needs ``pycuf[polars]``; no pyarrow)."""
        return {n: self[n].to_polars(on_inexact) for n in _names(tables)}

    def to_pandas(
        self, tables: Iterable[str] | None = None, *, on_inexact: OnInexact = "raise"
    ) -> dict[str, Any]:
        """Return pandas DataFrames with Arrow-backed dtypes (needs ``pycuf[pandas]``)."""
        return {n: self[n].to_pandas(on_inexact) for n in _names(tables)}


def _names(tables: Iterable[str] | None) -> Sequence[str]:
    names = list(TABLES) if tables is None else list(tables)
    for n in names:
        if n not in TABLES:
            raise KeyError(f"unknown table {n!r}; choose from {', '.join(TABLES)}")
    return names


def _cell(table: str, column: str, row: int, v: Any, convert: Callable[[Any], Any]) -> Any:
    try:
        return convert(v)
    except ValueError as exc:
        raise ValueError(f"table {table!r}, column {column!r}, row {row}: {exc}") from None


def _plain(v: Decimal) -> str:
    """``v`` in plain notation, exactly; ``ValueError`` instead of an absurdly long string."""
    _, digits, exponent = v.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError(f"{v} is not a finite number")
    integer = 1 if v.is_zero() else max(len(digits) + exponent, 1)
    length = integer + max(-exponent, 0) + 2  # sign and decimal point
    if length > _MAX_PLAIN:
        raise ValueError(
            f"{v} would take {length:,} characters in plain notation (at most {_MAX_PLAIN:,})"
        )
    return format(v, "f")


def _csv_value(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, Decimal):
        return _plain(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def _json_value(v: Any) -> Any:
    if isinstance(v, Decimal):
        return _plain(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v

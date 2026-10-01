"""Arrow interoperability via nanoarrow (``pycuf[arrow]``), and polars/pandas/Parquet on top.

Each table becomes one record batch, built once from raw buffers: numbers as
``decimal128(28, 15)`` (16-byte little-endian integers computed exactly from the ``Decimal``
digits, independent of the caller's decimal context; no float anywhere), dates as ``date32``,
timestamps as ``timestamp[us]``, with validity bitmaps. ``requested_schema`` is ignored, as the
Arrow PyCapsule interface allows; consumers cast themselves.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Context, Decimal
from pathlib import Path
from typing import Any

from ._optional import require
from .tables import NUMBER, Column, OnInexact, Row

__all__ = ["build_batch", "schema", "stream", "to_pandas", "to_polars", "write_parquet"]

_EPOCH = dt.date(1970, 1, 1).toordinal()
_EPOCH_DT = dt.datetime(1970, 1, 1)
_ROUND = Context(prec=80, rounding=ROUND_HALF_EVEN)


def _na() -> Any:
    return require("nanoarrow", "arrow")


def _type(na: Any, col: Column) -> Any:
    if col.type == "number":
        return na.decimal128(*NUMBER)
    return {
        "string": na.string(),
        "int64": na.int64(),
        "date": na.date32(),
        "timestamp": na.timestamp("us"),
        "bool": na.bool_(),
    }[col.type]


def schema(columns: Sequence[Column]) -> Any:
    """Nanoarrow struct schema for ``columns``."""
    na = _na()
    return na.struct({c.name: _type(na, c) for c in columns})


def _unscaled(v: Decimal, scale: int) -> int | None:
    """The exact unscaled integer of ``v`` at ``scale``, or ``None`` if it needs more decimals."""
    sign, digits, exp = v.as_tuple()
    assert isinstance(exp, int)
    n = int("".join(map(str, digits)) or "0")
    shift = exp + scale
    if shift >= 0:
        n *= 10**shift
    else:
        n, rem = divmod(n, int(10 ** (-shift)))
        if rem:
            return None
    return -n if sign else n


def _validity(values: Sequence[Any]) -> tuple[bytes | None, int]:
    nulls = 0
    bits = bytearray((len(values) + 7) // 8)
    for i, v in enumerate(values):
        if v is None:
            nulls += 1
        else:
            bits[i >> 3] |= 1 << (i & 7)
    return (bytes(bits) if nulls else None), nulls


def _decimal_column(
    na: Any, table: str, col: Column, values: list[Decimal | None], policy: OnInexact
) -> Any:
    precision, scale = NUMBER
    limit = 10**precision
    out = bytearray(16 * len(values))
    for i, v in enumerate(values):
        if v is None:
            continue
        where = f"table {table!r}, column {col.name!r}, row {i}"
        if not v.is_finite():
            raise ValueError(f"{where}: {v} is not a finite number")
        n = _unscaled(v, scale)
        if n is None and policy == "round":
            n = _unscaled(v.quantize(Decimal(1).scaleb(-scale), context=_ROUND), scale)
        if n is None or not -limit < n < limit:
            if policy == "null":
                values[i] = None
                continue
            raise ValueError(
                f"{where}: value {v} does not fit decimal128{NUMBER} exactly; pass "
                "on_inexact='null' or 'round' to export anyway"
            )
        out[16 * i : 16 * i + 16] = n.to_bytes(16, "little", signed=True)
    validity, nulls = _validity(values)
    return na.c_array_from_buffers(
        na.decimal128(precision, scale), len(values), [validity, bytes(out)], null_count=nulls
    )


def _column(na: Any, table: str, col: Column, values: list[Any], policy: OnInexact) -> Any:
    if col.type == "number":
        return _decimal_column(na, table, col, values, policy)
    if col.type == "date":
        days = [None if v is None else v.toordinal() - _EPOCH for v in values]
        return na.c_array(days, na.date32())
    if col.type == "timestamp":
        micros = [
            None if v is None else (v - _EPOCH_DT) // dt.timedelta(microseconds=1) for v in values
        ]
        return na.c_array(micros, na.timestamp("us"))
    return na.c_array(values, _type(na, col))


def build_batch(
    table: str, columns: Sequence[Column], rows: Sequence[Row], on_inexact: OnInexact = "raise"
) -> Any:
    """Build one nanoarrow struct array (a record batch) from ``rows``."""
    if on_inexact not in ("raise", "null", "round"):
        raise ValueError("on_inexact must be 'raise', 'null' or 'round'")
    na = _na()
    cols = [list(c) for c in zip(*rows, strict=True)] if rows else [[] for _ in columns]
    children = [_column(na, table, c, v, on_inexact) for c, v in zip(columns, cols, strict=True)]
    return na.c_array_from_buffers(schema(columns), len(rows), [None], children=children)


def stream(columns: Sequence[Column], batch: Any) -> Any:
    """A fresh nanoarrow ``CArrayStream`` over ``batch``."""
    na = _na()
    from nanoarrow.c_array_stream import CArrayStream  # noqa: PLC0415

    return CArrayStream.from_c_arrays([batch], na.c_schema(schema(columns)), validate=False)


def to_polars(batch: Any) -> Any:
    """A polars DataFrame from ``batch`` (no pyarrow needed)."""
    pl = require("polars", "polars")
    return pl.DataFrame(batch)


def to_pandas(columns: Sequence[Column], batch: Any) -> Any:
    """A pandas DataFrame with ``ArrowDtype`` columns (needs pandas + pyarrow)."""
    pd = require("pandas", "pandas")
    pa = require("pyarrow", "pandas")
    table = pa.table(stream(columns, batch))
    return table.to_pandas(types_mapper=pd.ArrowDtype)


def write_parquet(columns: Sequence[Column], batch: Any, path: Path) -> str:
    """Write ``batch`` as a Parquet file (needs ``pycuf[parquet]``)."""
    pa = require("pyarrow", "parquet")
    pq = require("pyarrow.parquet", "parquet")
    pq.write_table(pa.table(stream(columns, batch)), str(path))
    return str(path)

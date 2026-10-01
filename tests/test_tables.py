from __future__ import annotations

import csv
import datetime as dt
import decimal
import json
from decimal import Decimal
from pathlib import Path

import cufgen
import pytest

import pycuf
from pycuf.tables import TABLES, Tables


@pytest.fixture
def cuf(estimate: cufgen.Estimate) -> pycuf.CufFile:
    return pycuf.read(cufgen.write(estimate))


def test_schemas_match_rows(cuf: pycuf.CufFile) -> None:
    for name in TABLES:
        table = cuf.tables[name]
        for row in table.rows():
            assert len(row) == len(table.columns), name


def test_contents(cuf: pycuf.CufFile, estimate: cufgen.Estimate) -> None:
    lines = list(cuf.tables["lines"].dicts())
    assert len(lines) == len(estimate.lines())
    total = sum(r["extended_total"] for r in lines)
    assert total == cuf.totals().estimate.total
    project = next(cuf.tables["project"].dicts())
    assert project["created"] == dt.datetime(2026, 10, 1, 10, 15)
    assert project["line_count"] == len(lines)
    codes = list(cuf.tables["sort_codes"].dicts())
    assert {c["scheme"] for c in codes} == {"PLANCODE"}
    assert len(cuf.tables["tail_items"]) == 2
    assert cuf.tables["bundles"].column_names[:3] == ("seq", "parent_seq", "depth")
    with pytest.raises(KeyError):
        cuf.tables["nope"]


def test_inherited_sort_codes() -> None:
    cuf = pycuf.read(cufgen.write(cufgen.make_estimate(3), "ibis"))
    rows = list(cuf.tables["sort_codes"].dicts())
    assert any(r["scheme"] == "stk" and not r["inherited"] for r in rows)


def test_policy_dependent_columns(tmp_path: Path) -> None:
    cuf = pycuf.read(cufgen.write(cufgen.make_estimate(5, elements=True)))
    a = next(cuf.tables["project"].dicts())["total"]
    b = next(Tables(cuf, policy=pycuf.Policy(estimate_style="traditional"))["project"].dicts())
    assert a > b["total"]
    (path,) = cuf.export(
        tmp_path, tables=["project"], policy=pycuf.Policy(estimate_style="traditional")
    )
    assert str(b["total"]) in Path(path).read_text(encoding="utf-8")


def test_csv_and_jsonl_export(cuf: pycuf.CufFile, tmp_path: Path) -> None:
    paths = cuf.export(tmp_path / "csv")
    assert len(paths) == len(TABLES)
    with (tmp_path / "csv" / "lines.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert sum(Decimal(r["total"]) for r in rows) == cuf.totals().estimate.total
    cuf.export(tmp_path / "jl", format="jsonl", tables=["project"])
    record = json.loads((tmp_path / "jl" / "project.jsonl").read_text(encoding="utf-8"))
    assert record["created"] == "2026-10-01T10:15:00"
    with pytest.raises(ValueError, match="format"):
        cuf.export(tmp_path, format="xlsx")  # type: ignore[arg-type]
    with pytest.raises(KeyError):
        cuf.export(tmp_path, tables=["nope"])


def _doc(lines: str) -> bytes:
    return (
        '<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">'
        '<PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>'
        f"<BEGROTING>{lines}</BEGROTING></CUF>"
    ).encode()


def test_plain_numbers_are_exact_and_bounded(tmp_path: Path) -> None:
    edge = "1.7976931348623157E+308"
    cuf = pycuf.read(_doc(f'<BEGROTINGSREGEL BTW="21" HOEVEELHEID="1" MATERIAALPRIJS="{edge}"/>'))
    (path,) = cuf.export(tmp_path / "edge", tables=["lines"])
    with Path(path).open(encoding="utf-8") as fh:
        price = next(csv.DictReader(fh))["material_price"]
    assert len(price) == 309 and Decimal(price) == Decimal(edge)
    lines = '<BEGROTINGSREGEL BTW="21" HOEVEELHEID="1E+300" MATERIAALPRIJS="1E+300"/>'
    for _ in range(40):
        lines = f'<BUNDELING DOORREKEN_HOEVEELHEID="1E+300">{lines}</BUNDELING>'
    absurd = pycuf.read(_doc(lines))  # multipliers make 1E+12000
    for fmt in ("csv", "jsonl"):
        with pytest.raises(
            ValueError, match=r"'lines', column 'applied_multiplier', row 0: 1E\+12000"
        ):
            absurd.export(tmp_path / fmt, format=fmt, tables=["lines"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0E-1000000000000", 0),
        ("0E+1000000000000", 0),
        ("1.500", 1_500_000_000_000_000),
        ("-15E-1", -1_500_000_000_000_000),
        ("9999999999999.999999999999999", 10**28 - 1),
        ("10000000000000", None),
        ("1E-16", None),
        ("1E+1000000000000", None),
        ("1E-1000000000000", None),
        pytest.param("9" * 5000, None, id="long"),
    ],
)
def test_arrow_unscaled_checks_digits_first(value: str, expected: int | None) -> None:
    from pycuf._arrow import _unscaled

    assert _unscaled(Decimal(value), 15, 28) == expected


@pytest.mark.extras
def test_round_policy_names_values_too_large_to_round() -> None:
    pytest.importorskip("nanoarrow")
    quantity = "1" * 100 + "." + "5" * 20  # inexact and far too large; rounding raised bare
    cuf = pycuf.read(_doc(f'<BEGROTINGSREGEL BTW="21" HOEVEELHEID="{quantity}"/>'))
    with pytest.raises(ValueError, match="table 'lines', column 'quantity', row 0"):
        cuf.tables["lines"].to_arrow(on_inexact="round")


@pytest.mark.extras
def test_arrow_consumers(cuf: pycuf.CufFile) -> None:
    pa = pytest.importorskip("pyarrow")
    pl = pytest.importorskip("polars")
    lines = cuf.tables["lines"]
    table = pa.table(lines)
    assert str(table.schema.field("total").type) == "decimal128(28, 15)"
    assert sum(table.column("total").to_pylist()) == cuf.totals().estimate.total
    assert pa.table(lines, schema=table.schema).num_rows == table.num_rows
    assert pa.record_batch(lines).num_rows == table.num_rows
    df = pl.DataFrame(lines)
    assert df["total"].sum() == cuf.totals().estimate.total
    assert pl.DataFrame(lines).height == df.height  # re-consumable
    empty = pa.table(cuf.tables["sort_code_entries"])
    assert empty.num_rows == 0


@pytest.mark.extras
def test_duckdb(cuf: pycuf.CufFile) -> None:
    duckdb = pytest.importorskip("duckdb")
    lines = cuf.tables["lines"]  # noqa: F841 - found by DuckDB's replacement scan
    first = duckdb.sql("select sum(total) from lines").fetchone()
    second = duckdb.sql("select count(*) from lines").fetchone()
    assert first is not None and first[0] == cuf.totals().estimate.total
    assert second is not None and second[0] == len(cuf.lines)


@pytest.mark.extras
def test_pandas_and_parquet(cuf: pycuf.CufFile, tmp_path: Path) -> None:
    pytest.importorskip("pandas")
    pq = pytest.importorskip("pyarrow.parquet")
    df = cuf.to_pandas(["bundles"])["bundles"]
    assert str(df["total"].dtype) == "decimal128(28, 15)[pyarrow]"
    (path,) = cuf.export(tmp_path, format="parquet", tables=["lines"])
    assert pq.read_table(path).num_rows == len(cuf.lines)
    frames = cuf.to_polars(["lines", "project"])
    assert set(frames) == {"lines", "project"}


@pytest.mark.extras
def test_exactness_and_inexact_policy() -> None:
    pa = pytest.importorskip("pyarrow")
    xml = b"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <BEGROTING UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="-1234567.1234567890123456789" MATERIEELKOSTEN="0"
                 ONDERAANNEMING="0" OVERIGE_KOSTEN="0"/>
      <STAARTGEGEVENS AANNEEMSOM="65800.0000000009"/></CUF>"""
    cuf = pycuf.read(xml)
    project = cuf.tables["project"]
    with pytest.raises(ValueError, match="stated_material"):
        pa.table(project)
    with decimal.localcontext(prec=6):
        rounded = pa.table(project.to_arrow(on_inexact="round"))
        nulled = pa.table(project.to_arrow(on_inexact="null"))
    assert rounded.column("stated_material")[0].as_py() == Decimal("-1234567.123456789012346")
    assert rounded.column("contract_sum")[0].as_py() == Decimal("65800.0000000009")
    assert nulled.column("stated_material")[0].as_py() is None


def test_missing_extra_message(cuf: pycuf.CufFile, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    real = importlib.import_module

    def fake(name: str, *args: object) -> object:
        if name.startswith("nanoarrow"):
            raise ImportError(name)
        return real(name, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(importlib, "import_module", fake)
    with pytest.raises(pycuf.MissingExtraError, match=r"pycuf\[arrow\]"):
        cuf.tables["lines"].to_arrow()

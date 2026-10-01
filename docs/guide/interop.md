# Interoperability

pycuf turns every CUF file into the same set of **normalized tables** with fixed schemas. They
can be written to CSV or JSONL with the standard library, or handed to Arrow-based tools:
pyarrow, polars, DuckDB, pandas and Parquet.

```python
cuf = pycuf.read("begroting.xml")
cuf.export("out/")  # one CSV file per table, no dependencies
```

## The tables

| Table | Rows |
|---|---|
| `project` | one row: file and project data, stated and computed estimate totals |
| `bundles` | bundles, with stated and computed totals |
| `lines` | estimate lines, with computed costs |
| `resource_lines` | resource (MAMO) lines, with computed costs |
| `quantity_lines` | quantity take-off lines |
| `sort_codes` | effective sort codes of bundles, lines and resource lines (`inherited` flags codes from above) |
| `sort_code_schemes` | declared sort-code schemes |
| `sort_code_entries` | the code tables of the schemes |
| `tail_items` | tail items (markups) |

Column names and types are listed in the [table schemas](../reference/tables.md). Rows are joined
by synthetic keys, because codes in real files are neither unique nor mandatory:
`lines.bundle_seq` → `bundles.seq`, `resource_lines.line_seq` → `lines.seq`, and
`owner_type`/`owner_seq` for quantity lines and sort codes. `path` shows the bundle codes from
the top (`21 / 21.1`).

Computed columns (`hours` … `total`, `applied_multiplier`, `extended_total`) depend on the
[policy](calculation.md); they use the file's policy unless you pass another one:

```python
from pycuf.tables import Tables

tables = Tables(cuf, policy="erp")
cuf.export("out/", policy="erp")
```

```python
lines = cuf.tables["lines"]
lines.column_names  # ('seq', 'bundle_seq', 'depth', 'path', 'code', …)
for row in lines.rows():  # tuples of Python values (Decimal, date, str, int, bool)
    ...
for row in lines.dicts():
    ...
```

## CSV and JSONL (no dependencies)

```python
cuf.export("out/", format="csv")
cuf.export("out/", format="jsonl", tables=["lines", "bundles"])
```

Numbers are written as exact strings (`3612.16`, never `3612.1600000001`), dates in ISO 8601,
missing values as empty CSV fields or JSON `null`, booleans as `true`/`false`. Files are UTF-8.

## Arrow, DuckDB, polars, pandas

With `pycuf[arrow]` (nanoarrow, about 3 MB) every table implements the
[Arrow PyCapsule interface](https://arrow.apache.org/docs/format/CDataInterface/PyCapsuleInterface.html),
so Arrow-aware libraries read it directly, without pyarrow:

```python
import duckdb, polars as pl, pyarrow as pa

lines = cuf.tables["lines"]
pa.table(lines)  # pyarrow ≥ 14
pl.DataFrame(lines)  # polars ≥ 1.3, no pyarrow needed
duckdb.sql("select path, sum(total) from lines group by path").show()  # duckdb ≥ 1.1
```

DuckDB's replacement scan resolves the table name in the SQL to the Python variable of that name.

| Method | Needs |
|---|---|
| `cuf.to_polars(tables=None)` | `pycuf[polars]` (no pyarrow) |
| `cuf.to_pandas(tables=None)` | `pycuf[pandas]`; columns are `pd.ArrowDtype`, so decimals stay exact |
| `cuf.export(dir, format="parquet")` | `pycuf[parquet]` |
| `cuf.tables[name].to_arrow()` | `pycuf[arrow]` |

## Exact decimals

Numbers are `decimal.Decimal` in Python and **`decimal128(28, 15)`** in Arrow: 13 integer digits
and 15 decimals. CUF-XML gives numbers no precision; real files carry up to 5 decimals in inputs
and up to 14 digits of floating-point noise in totals (`65800.0000000009`), which all fit
exactly. A value that does not fit is **not rounded**: Arrow export raises `ValueError` naming the
table, column and row. Pass `on_inexact="round"` (half-even to 15 decimals) or `"null"` to export
anyway.

!!! tip "Computing with scale-15 decimals"
    Sums stay exact in pyarrow, polars and DuckDB. Products of two scale-15 columns need care:
    pyarrow needs a `decimal256` cast, DuckDB's result type `DECIMAL(38,30)` overflows around
    10⁸ (cast one side, e.g. `quantity::DECIMAL(20,5)`), and pyarrow's decimal `sum` does not
    detect overflow. DuckDB's `.df()` turns decimals into floats.

## Why pandas is optional

pandas with pyarrow takes about 250 MB installed, more than the AWS Lambda limit for unzipped
code. pycuf therefore keeps its core free of dependencies and builds Arrow data with the small
nanoarrow, which already lets polars and DuckDB read the tables without pyarrow. Install pandas
when you want it.

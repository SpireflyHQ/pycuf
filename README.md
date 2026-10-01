# 🧱 pycuf

[![CI status](https://github.com/SpireflyHQ/pycuf/actions/workflows/ci.yml/badge.svg)](https://github.com/SpireflyHQ/pycuf/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pycuf)](https://pypi.org/project/pycuf/)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/pycuf)](https://pypi.org/project/pycuf/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/SpireflyHQ/pycuf/blob/main/LICENSE)

**Read, check and analyse CUF-XML construction cost estimates in plain Python.**

CUF-XML (*Calculatie Uitwissel Formaat*, "estimate exchange format") is how Dutch construction
software passes a cost estimate, a *begroting*, from one program to the next: from estimating
packages such as Ibis, Kraan, Bakker & Spees CIVIEL and Matrix to ERP systems such as AFAS, Exact
and 4PS. pycuf reads CUF-XML 4.003 files into one clean, typed model with English names,
computes their costs with exact decimals, tells you precisely what is wrong with a file instead of
refusing it, and turns it into tables for your spreadsheet, dataframe or database. No runtime
dependencies, no upload to anyone's server.

## 🧭 Table of contents

- [Why pycuf](#-why-pycuf)
- [Installation](#-installation)
- [Quickstart](#-quickstart)
  - [1. Read the file](#1-read-the-file)
  - [2. Compute the totals](#2-compute-the-totals)
  - [3. Validate it](#3-validate-it)
  - [4. Or use the command line](#4-or-use-the-command-line)
- [More examples](#-more-examples)
  - [Choose how to read the rules](#choose-how-to-read-the-rules)
  - [Walk the tree](#walk-the-tree)
  - [Export to tables](#export-to-tables)
  - [Query with DuckDB, polars or pandas](#query-with-duckdb-polars-or-pandas)
  - [Files that need a little help](#files-that-need-a-little-help)
- [What is CUF-XML?](#-what-is-cuf-xml)
- [Documentation](#-documentation)
- [Contributing](#-contributing)
- [License and attribution](#-license-and-attribution)

## ✨ Why pycuf

A begroting leaves Ibis as Windows-1252 with an empty `BTW` on every line. The official example
file declares a namespace with spaces in it. Another exporter writes dates as `3-5-2024`, and the
totals at the top of a file often do not match the lines underneath. The specification itself
comes in two texts that disagree. pycuf was built for exactly these files.

- **One typed model, in English.** `BEGROTINGSREGEL` becomes `Line`, `HOEVEELHEID` becomes
  `quantity`, `MAMO_REGEL` becomes `ResourceLine`. The raw layer keeps every element and
  attribute as parsed, vendor extensions included.
- **Lenient reading, honest reporting.** pycuf does not refuse a file because of bad data. Every
  problem becomes a graded finding with a stable code, such as `CUF5001 WARNING`, so nothing is
  silently guessed or dropped.
- **Exact money.** Every number is a `decimal.Decimal`, never a `float`, and costs are computed at
  60 significant digits.
- **Explicit calculation rules.** Where CUF-XML is ambiguous, a *policy* makes the choice
  visible, with presets for the official usage rules, the literal schema and ERP practice.
- **Checks the totals for you.** pycuf recomputes every bundle and the estimate from the lines
  and compares the result with the stated totals, within a tolerance you choose.
- **Tables everywhere.** Nine normalized tables, written to CSV or JSONL with the standard library,
  or handed to Arrow, polars, pandas, DuckDB and Parquet.
- **Lightweight and safe.** Pure, fully typed Python with zero runtime dependencies. No DTDs, no
  entity expansion, no network access, and limits on size and depth.

## 📦 Installation

pycuf needs Python 3.11 or newer.

```console
pip install pycuf
```

The core has no dependencies. Add an extra for each optional feature you need:

| Extra | Adds | Install |
|---|---|---|
| `cli` | the `pycuf` command line | `pip install "pycuf[cli]"` |
| `arrow` | Arrow streams for DuckDB, pyarrow and friends (nanoarrow) | `pip install "pycuf[arrow]"` |
| `polars` | `to_polars()`, without pyarrow | `pip install "pycuf[polars]"` |
| `pandas` | `to_pandas()` with Arrow-backed types | `pip install "pycuf[pandas]"` |
| `parquet` | Parquet export | `pip install "pycuf[parquet]"` |
| `all` | everything above | `pip install "pycuf[all]"` |

Using uv? `uv add pycuf` works the same way, for example `uv add "pycuf[cli,polars]"`.

## 🚀 Quickstart

Download the two sample files into an empty folder. They hold the same small, made-up estimate
for a housing project: `begroting.xml` is a tidy file, and `begroting-ibis.xml` is written the way
Ibis writes it, with one extra surprise in its totals.

```console
curl -L -O https://raw.githubusercontent.com/SpireflyHQ/pycuf/main/examples/begroting.xml \
        -O https://raw.githubusercontent.com/SpireflyHQ/pycuf/main/examples/begroting-ibis.xml
```

Your own exports work exactly the same way.

### 1. Read the file

```python
import pycuf

cuf = pycuf.read("begroting.xml")
print(cuf.project.number, cuf.project.name)
print(
    len(cuf.bundles),
    "bundles,",
    len(cuf.lines),
    "lines,",
    len(cuf.resource_lines),
    "resource lines",
)

for line in cuf.lines[:3]:
    print(line.code, line.description, line.quantity, line.unit, line.material_price)
```

```text
2026-001 Voorbeeldproject Woningbouw
9 bundles, 12 lines, 42 resource lines
000003 wapening 3 326.836 kg 239.38
000004 stucwerk 4 360.23 m2 68.88
000006 riolering 6 163.004 kg 119.12
```

The Dutch names stay in the file; in Python you get English ones (`HOEVEELHEID` is `quantity`,
`MATERIAALPRIJS` is `material_price`). The Ibis file opens just as easily, Windows-1252 and all:

```python
ibis = pycuf.read("begroting-ibis.xml")
print(ibis.encoding.effective, ibis.project.software_house, ibis.project.name)
```

```text
cp1252 BRINK Voorbeeldproject Woningbouw – €
```

### 2. Compute the totals

```python
totals = cuf.totals()
print(totals.estimate.total)
print(totals.estimate.hours, "hours of labour")

bundle = cuf.bundles[0]
print(bundle.code, bundle.description, totals[bundle].total)
```

```text
769240.4340286860
5120.38296190 hours of labour
1 beton (element 1) 360184.72901480
```

Every amount is an exact `Decimal`, computed from quantities, hour norms, rates and prices with
the formulas from the CUF-XML specification. The total is the direct cost of the work, before
markups and VAT.

### 3. Validate it

```python
report = pycuf.validate("begroting-ibis.xml")
print(report.ok, len(report.findings), "findings")
for finding in report.findings[:4]:
    print(finding.code, finding.severity, finding.line, finding.message)
```

Here is the surprise: in the Ibis file, every bundle claims €100 more labour than its lines add
up to. pycuf recomputes each one and catches all of them, and it also notices the empty `BTW`
(VAT) attribute that Ibis leaves on every line:

```text
True 12 findings
CUF5002 WARNING 6 BEGROTING LOONKOSTEN is 301077.313035186, computed 300977.313035186 (difference 100)
CUF5001 WARNING 7 BUNDELING '1' LOONKOSTEN is 158710.5947748, computed 158610.5947748 (difference 100)
CUF3017 WARNING 8 BEGROTINGSREGEL has an empty value for the required attribute BTW (21 times; first at line 8)
CUF5001 WARNING 11 BUNDELING '1.1' LOONKOSTEN is 100932.4429188, computed 100832.4429188 (difference 100)
```

`report.ok` is still `True`: wrong control totals are warnings, not errors, because the estimate
lines are what counts. Every finding has a stable code, a severity (`ERROR`, `WARNING` or `INFO`)
and, where possible, a line number. The
[finding-code reference](https://spireflyhq.github.io/pycuf/reference/codes/) explains each one.

### 4. Or use the command line

With `pycuf[cli]` installed:

```console
$ pycuf validate begroting.xml
begroting.xml: 0 error(s), 0 warning(s), 1 info
  line 3:2 INFO CUF3001 CUF_VERSIE is 4.003 ['4.003']

$ pycuf info begroting-ibis.xml
file               begroting-ibis.xml
cuf version        4.003
software house     BRINK
created            2026-10-01T10:15:00
encoding           cp1252
project            2026-001 – Voorbeeldproject Woningbouw – €
...

$ pycuf totals begroting-ibis.xml --depth 1
begroting-ibis.xml  (traditional estimate, policy usage-rules)
bundle                                                  total       labour     material    subcontr.
----------------------------------------------------------------------------------------------------
1 beton (element 1)                                360,184.73   158,610.59   149,219.78    26,527.98  ≠ stated by +100.00
2 tegelwerk (element 2)                            278,790.21   106,385.24   161,213.89         0.00  ≠ stated by +100.00
3 voegwerk (element 3)                             130,265.49    35,981.48    84,665.94     3,029.15  ≠ stated by +100.00
----------------------------------------------------------------------------------------------------
BEGROTING                                          769,240.43   300,977.31   395,099.61    29,557.13  ≠ stated by +100.00
hours                                                 5120.38
contract sum (stated, excl. VAT)                   838,472.07
```

`pycuf validate` exits with 0 when the file is fine, 1 for warnings (with `--strict`), 2 for
errors and 3 when pycuf itself could not do its job, so it slots straight into scripts and CI.
`pycuf export` writes the tables, and `pycuf codes` lists every finding code.

## 🧰 More examples

### Choose how to read the rules

The CUF-XML schema and the official usage rules disagree in a few places. Take a line with
`HOEVEELHEID_FACTOR="0"`: the usage rules say a factor of 0 counts as 1, the literal schema says
0 is 0. pycuf follows the usage rules by default and lets you pick:

```python
toy = b"""<?xml version="1.0" encoding="UTF-8"?>
<CUF AANMAAKDATUMTIJD="2026-10-01T10:15:00">
  <PROJECTGEGEVENS CUF_VERSIE="4.003" PROJECTNUMMER="1" PROJECTNAAM="Schuurtje"/>
  <BEGROTING>
    <BEGROTINGSREGEL OMSCHRIJVING="metselwerk" HOEVEELHEID="10" HOEVEELHEID_FACTOR="0" MATERIAALPRIJS="50" BTW="21"/>
  </BEGROTING>
</CUF>"""

shed = pycuf.read(toy)
print(shed.totals().estimate.total)  # usage rules: a factor of 0 counts as 1
print(shed.totals(policy="schema").estimate.total)  # the literal schema: 0 is 0
print(shed.findings[0])
```

```text
500
0
line 2:0 ERROR CUF3010 CUF lacks the required element STAARTGEGEVENS
```

The toy file is far from complete, and pycuf still reads it, while listing everything it lacks.
The presets are `"usage-rules"` (the default), `"schema"` and `"erp"`; a
[`Policy`](https://spireflyhq.github.io/pycuf/guide/calculation/#policies) can change any single
choice, such as the tolerance for checking stated totals.

### Walk the tree

Bundles nest to any depth, and sort codes on a bundle apply to everything beneath it:

```python
line = cuf.lines[0]
print([b.code for b in cuf.ancestors(line)], cuf.sort_codes(line))
print(totals.extended(line).total)  # the line's share of the estimate, multipliers applied
```

```text
['1', '1.1'] {'PLANCODE': '200-10'}
132655.65640060
```

### Export to tables

pycuf turns a file into nine normalized tables, such as `bundles`, `lines` and
`resource_lines`, with fixed columns and the computed costs next to the stated ones:

```python
cuf.export("out/")  # one CSV file per table, standard library only; also format="jsonl"
cuf.export("out/", format="parquet")  # pycuf[parquet]
frames = cuf.to_polars()  # pycuf[polars]: a dict of DataFrames
```

Numbers are written as exact strings (`3612.16`, never `3612.1600000001`) and dates in ISO 8601.

### Query with DuckDB, polars or pandas

Tables speak the Arrow PyCapsule interface, so Arrow-aware tools read them directly, without
pyarrow (needs `pycuf[arrow]`):

```python
import duckdb

lines = cuf.tables["lines"]
duckdb.sql("""
    select path, count(*) as lines, round(sum(total), 2) as total
    from lines group by path order by path
""").show()
```

```text
┌─────────┬───────┬───────────────┐
│  path   │ lines │     total     │
│ varchar │ int64 │ decimal(38,2) │
├─────────┼───────┼───────────────┤
│ 1 / 1.1 │     2 │     219087.20 │
│ 1 / 1.2 │     2 │     141097.53 │
│ 2 / 2.1 │     2 │     139688.14 │
│ 2 / 2.2 │     2 │     139102.07 │
│ 3 / 3.1 │     2 │      49022.04 │
│ 3 / 3.2 │     2 │      81243.45 │
└─────────┴───────┴───────────────┘
```

`pl.DataFrame(lines)` works the same way in polars, and `cuf.to_pandas()` (needs
`pycuf[pandas]`) gives a dict of pandas DataFrames whose decimal columns stay exact.

### Files that need a little help

```python
# no XML declaration, but really Windows-1252
cuf = pycuf.read("old.xml", encoding="cp1252")

# a bare "&" in SYSTEEMHUIS="Bakker & Spees", or stray control characters
cuf = pycuf.read("export.xml", repair={"bare-ampersand", "control-chars"})

# strict parsing: no decimal commas, no 3-5-2024 dates, no true/false booleans
cuf = pycuf.read("begroting.xml", lenient=())
```

Repairs are opt-in and every repair shows up as a finding, so you always know what was changed.

<details>
<summary><b>Go deeper: the raw layer and vendor attributes</b></summary>

```python
line = ibis.lines[0]
line.raw.get("BTW")  # '' – the attribute's text, as parsed
line.raw.line, line.raw.path  # where it sits in the file
line.extra  # attributes that CUF-XML 4.003 does not define, such as vendor extensions
ibis.raw.iter("MAMO_REGEL")  # walk the raw tree yourself
```

</details>

## 📐 What is CUF-XML?

CUF was created by Forum Systeemhuizen Bouw, an association of Dutch construction software
vendors. Version 4.000 moved it to XML, and 4.003, with its usage rules of 2006, is still the
latest version. Since the end of 2021 it has been maintained, as-is, by
[Ketenstandaard Bouw en Techniek](https://ketenstandaard.nl/cuf-xml).

A CUF-XML file is a tree of Dutch elements. These are the ones you will meet most:

| CUF-XML | In English | In pycuf |
|---|---|---|
| `BEGROTING` | the cost estimate | `Estimate` |
| `BUNDELING` | a bundle of lines, such as a building element | `Bundle` |
| `BEGROTINGSREGEL` | an estimate line: quantity, hour norm, unit prices | `Line` |
| `MAMO_REGEL` | a resource line that breaks one cost type down | `ResourceLine` |
| `SORTEERCODE` | a sort code, such as a planning or NL-SfB code | `SortCode` |
| `STAARTGEGEVENS` | the tail: markups and the contract sum (`AANNEEMSOM`) | `Tail` |

pycuf reads CUF-XML 4.000 to 4.003 and knows the dialects of Ibis, Bakker & Spees, Dataviewers,
the Forum's own example file and others. The
[format guide](https://spireflyhq.github.io/pycuf/guide/format/) explains the differences, and
the [glossary](https://spireflyhq.github.io/pycuf/reference/glossary/) maps every Dutch element
and attribute to its English name.

## 📚 Documentation

The full documentation lives at **<https://spireflyhq.github.io/pycuf/>**:

- [Reading CUF files](https://spireflyhq.github.io/pycuf/guide/reading/): the data model, the
  raw layer, encodings and lenient parsing
- [Calculating](https://spireflyhq.github.io/pycuf/guide/calculation/): the formulas,
  multipliers, resource lines and policies
- [Validation](https://spireflyhq.github.io/pycuf/guide/validation/) and the
  [finding codes](https://spireflyhq.github.io/pycuf/reference/codes/)
- [Interoperability](https://spireflyhq.github.io/pycuf/guide/interop/), the
  [table schemas](https://spireflyhq.github.io/pycuf/reference/tables/) and the
  [command line](https://spireflyhq.github.io/pycuf/reference/cli/)
- [Security](https://spireflyhq.github.io/pycuf/security/) and
  [versioning](https://spireflyhq.github.io/pycuf/versioning/)

Release notes are in the [changelog](https://github.com/SpireflyHQ/pycuf/blob/main/CHANGELOG.md).
For questions, see [SUPPORT.md](https://github.com/SpireflyHQ/pycuf/blob/main/SUPPORT.md).

## 🤝 Contributing

Contributions are very welcome, especially reports of files from software that pycuf does not
handle well yet: use the
[file compatibility report](https://github.com/SpireflyHQ/pycuf/issues/new?template=file_compatibility.yml).
Start with [CONTRIBUTING.md](https://github.com/SpireflyHQ/pycuf/blob/main/CONTRIBUTING.md) for
the development setup, and [ARCHITECTURE.md](https://github.com/SpireflyHQ/pycuf/blob/main/ARCHITECTURE.md)
for a map of the code.

> **Never attach a real begroting** to an issue or pull request. Estimates contain confidential
> prices and names. The exporting software and its version, the finding codes and a small,
> anonymised snippet are all we need.

Security problems are reported privately, as described in
[SECURITY.md](https://github.com/SpireflyHQ/pycuf/blob/main/SECURITY.md).

## 📄 License and attribution

pycuf is released under the [MIT license](https://github.com/SpireflyHQ/pycuf/blob/main/LICENSE).
If you use it in research or professional work, you can cite it with
[CITATION.cff](https://github.com/SpireflyHQ/pycuf/blob/main/CITATION.cff).

The CUF-XML specification documents are not bundled; pycuf describes the format in its own
words. The sample files are synthetic: every project, price and name in them is made up.

pycuf is an independent open-source project. It is not affiliated with or endorsed by
Ketenstandaard Bouw en Techniek, Forum Systeemhuizen Bouw or any software vendor, and a clean
pycuf report does not guarantee that another program will import a file the way you expect.

# pycuf

**Read, check and analyse CUF-XML construction cost estimates in Python.**

CUF-XML (*Calculatie Uitwissel Formaat*) is the Dutch exchange format for construction cost
estimates (*begrotingen*). Estimating software such as Ibis, Kraan, Bakker & Spees CIVIEL and
Matrix writes it; ERP systems such as AFAS, Exact and 4PS read it. pycuf reads every CUF-XML 4.x
file into one typed model, computes its costs under an explicit, configurable policy, tells you
precisely what is wrong with a file, and exports normalized tables.

```python
import pycuf

cuf = pycuf.read("begroting.xml")
print(cuf.project.name, cuf.totals().estimate.total)
for finding in cuf.validate().findings:
    print(finding)
```

## Features

- **Zero runtime dependencies.** The core uses only the standard library (`pyexpat`, `decimal`,
  `csv`, `json`) and is pure, fully typed Python. Arrow, polars, pandas, Parquet and the command
  line are optional extras.
- **Made for real files.** Windows-1252 and UTF-8, namespaces that are not valid URIs, empty
  required attributes, Dutch dates, decimal commas, vendor attributes (Ibis, Bakker & Spees) and
  missing sections: pycuf reads them and reports each one as a coded finding instead of refusing
  the file.
- **Exact numbers.** Every number is a `decimal.Decimal` with its original text kept next to it;
  computations run at 60 significant digits, so totals are exact.
- **Explicit calculation rules.** CUF-XML's rules are ambiguous in places. A
  [policy](guide/calculation.md) makes every interpretation explicit, with presets for the
  official usage rules, the literal schema and ERP practice.
- **Honest checks.** Real files often carry wrong control totals. pycuf recomputes every bundle
  and compares, with tolerances you choose. See [Validation](guide/validation.md).
- **Normalized tables** for CSV, JSONL, Arrow, polars, pandas, DuckDB and Parquet. See
  [Interoperability](guide/interop.md).
- **Safe with untrusted files.** No DTDs, no entity expansion, no network access, size and depth
  limits. See [Security](security.md).

## Installation

```bash
pip install pycuf                 # core, no dependencies
pip install "pycuf[cli,polars]"   # with the command line and polars
```

| Extra | Adds |
|---|---|
| `cli` | the `pycuf` command line (Typer) |
| `arrow` | Arrow PyCapsule export for DuckDB, pyarrow and friends (nanoarrow) |
| `polars` | `to_polars()`, without pyarrow |
| `pandas` | `to_pandas()` with Arrow-backed types |
| `parquet` | Parquet export |
| `all` | everything above |

## Where to next

- [Getting started](getting-started.md): a ten-minute tutorial with the sample files.
- [Reading CUF files](guide/reading.md): the data model, the raw layer, encodings, lenient parsing.
- [Calculating](guide/calculation.md): totals, multipliers, resource lines and policies.
- [Validation](guide/validation.md) and the [finding codes](reference/codes.md).
- [Interoperability](guide/interop.md) and the [command line](reference/cli.md).
- [The CUF-XML format](guide/format.md): history, the two specification texts and vendor dialects.
- [Glossary](reference/glossary.md): every Dutch element and attribute with its English name.

pycuf is an independent open-source project. It is not affiliated with or endorsed by
Ketenstandaard Bouw en Techniek, Forum Systeemhuizen Bouw or any software vendor.

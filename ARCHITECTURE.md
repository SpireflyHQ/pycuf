# Architecture

This document describes the high-level architecture of pycuf. Read it to find your way around the
code; the [user documentation](https://spireflyhq.github.io/pycuf/) explains what the library
does, and [CONTRIBUTING.md](CONTRIBUTING.md) explains how to work on it.

## Bird's-eye view

pycuf reads a CUF-XML file (a Dutch construction cost estimate), builds a typed model, computes
costs under an explicit policy, checks the file, and exports normalized tables. CUF files are
small, come from untrusted sources and from software that does not follow the specification. So
the library:

1. reads the whole input (path, bytes or stream) with a size limit;
2. works out the encoding and transcodes what Expat cannot decode itself;
3. parses the XML with a hardened `pyexpat` parser into a lossless raw tree, without namespace
   processing (real files carry namespaces that are not valid URIs);
4. builds the English-named model from the raw tree, checking structure and values against the
   CUF-XML 4.003 catalogue and reporting every irregularity as a coded finding;
5. computes costs on demand under a `Policy` and checks stated totals against them;
6. exports normalized tables.

```text
input ─► _source ─► _encoding ─► _xml (raw tree) ─► _build (+ spec) ─► models ─► CufFile
                                                                                   │
                         policy ─► calc (Totals, total checks) ◄───────────────────┤
                                       │                                           │
                                       └─► validate (report)      tables / _arrow ◄┘
```

## Code map

All library code lives in `src/pycuf/`. Modules starting with `_` are internal.

- `_source.py`: input sources (paths, bytes, streams) and the size limit.
- `_encoding.py`: BOM and XML-declaration sniffing, transcoding (windows-1252 and others), and the
  opt-in byte-level repairs.
- `_xml.py`: the hardened parser on top of `pyexpat`. It refuses DOCTYPE/ENTITY declarations,
  enforces depth and attribute-size limits, and builds `RawElement` trees with line numbers and
  paths.
- `raw.py`: `RawElement`, the lossless record of an element exactly as written.
- `spec.py`: the CUF-XML 4.003 catalogue: every element and attribute with type, cardinality,
  English field name and description. It drives the checks, the model mapping and the glossary.
- `_build.py`: builds the model from raw elements, with the structure, value and sort-code checks.
- `values.py`: strict parsers for numbers, dates and booleans (plus the opt-in lenient forms).
- `models.py`: the typed, English-named data model (`Bundle`, `Line`, `ResourceLine`, `Costs`, …).
- `reader.py`: `pycuf.read()` and `CufFile` (navigation, sort-code inheritance, entry points for
  totals, validation and tables).
- `policy.py`: `Policy`, the presets and `resolve_policy()`.
- `calc.py`: the cost formulas (`compute()` → `Totals`) and the checks of stated totals, resource
  lines and the contract sum.
- `findings.py`: `Finding`, `Severity`, the `CODES` registry and `FindingCollector`.
- `validate.py`: `pycuf.validate()` and `ValidationReport`.
- `tables.py`, `_arrow.py`: normalized tables and their exports (CSV, JSONL, Arrow, polars,
  pandas, Parquet).
- `cli.py`, `__main__.py`: the Typer command line.
- `_optional.py`: lazy imports of optional extras, with an install hint when one is missing.

Outside the package:

- `tests/`: the pytest suite. `tests/cufgen.py` builds synthetic estimates with independently
  computed totals and writes them in the dialects of real exporters, so most tests build their
  input instead of reading fixture files. `tests/test_corpus.py` runs against a private corpus
  of real files when one is available.
- `scripts/`: generators for the reference pages and the example files.
- `examples/`: synthetic sample files for the README quickstart (generated).
- `docs/`: the documentation site (Zensical, configured in `zensical.toml`).
- `noxfile.py`: developer tasks (`uvx nox -l`).

## Invariants

These hold everywhere; a change that breaks one needs a very good reason.

- **No runtime dependencies in the core.** Only the standard library is imported at module import
  time. Optional libraries (nanoarrow, polars, pandas, pyarrow, Typer) are imported lazily through
  `_optional.py`, and CI tests the wheel without any of them.
- **Never refuse a file for data problems.** Data problems become findings with a stable
  `CUF<nnnn>` code and a severity. Only input that is not CUF-XML at all, malformed XML and
  security violations raise exceptions.
- **No silent coercion.** Numbers are `decimal.Decimal`, never `float`. Parsed values keep their
  raw text, and anything pycuf could not parse is reported. Lenient parsing and repairs are
  reported too.
- **The model shows what the file says.** Defaults of the calculation rules are applied in
  `calc.py`, never in the model, and stated totals are never overwritten by computed ones.
- **Interpretations are explicit.** Every ambiguous calculation rule is a `Policy` field; results
  record the policy they used.
- **Exact arithmetic.** Computations run in a local decimal context of 60 digits; Arrow export
  converts decimals from their digits, independent of the caller's context.
- **Hostile input is expected.** DOCTYPE and ENTITY declarations are refused, there is no parser
  "recover" mode, and size, depth and attribute length are limited.

## Cross-cutting concerns

- **Generated code.** `docs/reference/codes.md`, `tables.md`, `glossary.md` and `examples/*.xml`
  are generated; CI fails when they are stale. Regenerate with `uvx nox -s generate`.
- **Identity of nodes.** Tree nodes are frozen dataclasses with `eq=False`, so they hash by
  identity and can key the computed results in `Totals`. Two parsed copies of the same file have
  different nodes.
- **Aggregated findings.** Problems exporters make on every element (empty `BTW`, vendor
  attributes) are tallied in `_build.py` and reported once with a count and the first location.

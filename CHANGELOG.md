# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Until 1.0 the public API may
change in minor releases. Finding codes are stable: a code is never renumbered or reused.

## [Unreleased]

## [0.1.0] - 2026-10-01

Initial release.

### Added

- **Reading CUF-XML 4.000–4.003** with `pycuf.read()` into a typed, English-named model
  (project, sort-code schemes, estimate tree of bundles and lines, resource and quantity
  take-off lines, tail), with the raw text of every element and attribute kept in `raw` and
  vendor attributes in `extra`.
- Tolerant reading of real exporter output: Windows-1252 and other declared encodings,
  namespaces that are not valid URIs, empty required attributes, decimal commas and d-m-yyyy
  dates (opt-out), Bakker & Spees attribute-style sort codes, legacy `SC1`–`SC6` attributes, and
  opt-in repairs for bare ampersands and control characters.
- **Calculation** of every bundle, line and resource line with exact `Decimal` arithmetic in
  pycuf's own decimal context, independent of the caller's (`CufFile.totals()`), under an
  immutable, validated `Policy` with the presets `usage-rules` (default), `schema` and `erp`.
- **Validation** (`pycuf.validate()`, `CufFile.validate()`) with graded findings and stable
  `CUF<nnnn>` codes: encoding, XML, structure and values, sort codes, stated totals against
  computed totals, resource lines and the contract sum.
- **Normalized tables** exported to CSV and JSONL without dependencies, and to Arrow (PyCapsule
  interface), polars, pandas, DuckDB and Parquet through extras.
- The `pycuf` command line (`info`, `totals`, `validate`, `export`, `codes`) with the `cli` extra.
- Hardened parsing: DOCTYPE/ENTITY declarations refused, size and depth limits, no recover mode,
  and numbers limited to the XDR range (zero or magnitudes from `2.2250738585072014E-308` to
  `1.7976931348623157E+308`, at most 1,074 decimals; others are `CUF3018`), so a short attribute
  cannot make calculations or exports enormous.
- Synthetic sample files in `examples/`.

[Unreleased]: https://github.com/SpireflyHQ/pycuf/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SpireflyHQ/pycuf/releases/tag/v0.1.0

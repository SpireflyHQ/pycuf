# Versioning and compatibility

pycuf follows [Semantic Versioning 2.0](https://semver.org/spec/v2.0.0.html). Every release is
listed in the [changelog](https://github.com/SpireflyHQ/pycuf/blob/main/CHANGELOG.md).

## Before 1.0

Until version 1.0 the API can still change. pycuf keeps changes predictable:

| Release | May contain |
|---|---|
| patch (`0.y.Z`) | bug fixes and documentation only |
| minor (`0.Y.0`) | new features, and breaking changes to the public API, each listed in the changelog with a migration note |

From 1.0 on, breaking changes need a new major version.

## What the public API is

These are covered by the compatibility promise:

- the names exported by the `pycuf` package (`pycuf.__all__`), the public modules
  `pycuf.policy`, `pycuf.tables` and `pycuf.spec`, and everything documented in the
  [API reference](reference/api.md);
- the [finding codes](reference/codes.md): a code is never renumbered, reused or given a new
  meaning. Changing a code's default severity is a listed change;
- the meaning of the [policy presets](guide/calculation.md#presets): a changed interpretation
  becomes a new preset or a new option value, and the default policy only changes in a major
  release;
- the [table schemas](reference/tables.md): column names and types. New columns may be added;
- the command line: commands, options, exit codes and the JSON layouts, versioned by
  `schema_version`.

These are **not** covered and may change in any release: modules and names starting with an
underscore (`pycuf._xml`, `pycuf._build`, …), the exact wording of finding messages, and the
order of findings with the same severity and line.

## Supported Python versions

pycuf supports the CPython versions that are not yet end-of-life, starting at 3.11. A Python
version is dropped in a minor release after its end of life.

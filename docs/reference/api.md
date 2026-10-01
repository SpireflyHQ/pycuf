# API reference

Generated from the docstrings with [mkdocstrings](https://mkdocstrings.github.io/). Everything
listed under `pycuf.<module>` is also importable from the top-level package where noted:
`pycuf.read`, `pycuf.validate`, `pycuf.CufFile`, `pycuf.ValidationReport`, `pycuf.Totals`,
`pycuf.Policy`, the model classes, `pycuf.Finding`, `pycuf.Severity`, `pycuf.CODES`,
`pycuf.RawElement` and the exceptions. Import `pycuf.policy`, `pycuf.tables` and
`pycuf.spec` for the presets, table schemas and the format catalogue.

| Page section | Contents |
|---|---|
| [Reading](#pycuf.reader.read) | `read()`, `CufFile` |
| [Policies](#pycuf.policy) | `Policy`, presets, `resolve_policy()` |
| [Calculating](#pycuf.calc.Totals) | `Totals` |
| [Validation](#pycuf.validate.validate) | `validate()`, `ValidationReport` |
| [Findings](#pycuf.findings) | `Finding`, `Severity`, `CODES`, `CodeInfo` |
| [Data model](#pycuf.models) | `Estimate`, `Bundle`, `Line`, `ResourceLine`, `Costs`, … |
| [Raw elements](#pycuf.raw.RawElement) | `RawElement` |
| [Tables](#pycuf.tables) | `Tables`, `Table`, `Column`, `TABLES` |
| [Format catalogue](#pycuf.spec) | `ELEMENTS`, `ElementSpec`, `AttributeSpec` |
| [Exceptions](#pycuf.errors) | `PycufError` and subclasses |

::: pycuf.reader.read
    options:
      heading: "pycuf.read"

::: pycuf.reader.CufFile
    options:
      heading: "pycuf.CufFile"

::: pycuf.policy
    options:
      show_root_full_path: true

::: pycuf.calc.Totals
    options:
      heading: "pycuf.Totals"

::: pycuf.validate.validate
    options:
      heading: "pycuf.validate"

::: pycuf.validate.ValidationReport
    options:
      heading: "pycuf.ValidationReport"

::: pycuf.findings
    options:
      show_root_full_path: true

::: pycuf.models
    options:
      show_root_full_path: true

::: pycuf.raw.RawElement

::: pycuf.tables
    options:
      show_root_full_path: true

::: pycuf.spec
    options:
      show_root_full_path: true
      members: [ELEMENTS, ElementSpec, AttributeSpec, VERSION, SUPPORTED_VERSIONS, SOFTWARE_HOUSES]

::: pycuf.errors
    options:
      show_root_full_path: true

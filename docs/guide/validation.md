# Validation

```python
report = pycuf.validate("begroting.xml")  # or: cuf.validate()
report.ok  # no ERROR findings
for finding in report.findings:  # most severe first, then in file order
    print(finding.code, finding.severity, finding.line, finding.message)
```

Validation never raises on data problems. `pycuf.validate()` even turns malformed XML,
forbidden constructs and exceeded limits into an `ERROR` finding (`CUF2001`–`CUF2003`); only
input that is not CUF-XML at all raises `NotCufError`.

## Layers

| Layer | Checks | Codes |
|---|---|---|
| L1 | input and character encoding | `CUF1xxx` |
| L2 | XML well-formedness and security | `CUF2xxx` |
| L3 | structure and values against CUF-XML 4.003: required elements and attributes, places, order, numbers, dates, code lists | `CUF3xxx` |
| L4 | sort codes: declared, used, in the declared table | `CUF4xxx` |
| L5 | stated totals, resource lines and the contract sum against computed values | `CUF5xxx` |
| L6 | data quality, lenient parsing and how the policy was applied | `CUF7xxx` |

L1–L4 run while reading (`cuf.findings`). L5 needs a [policy](calculation.md) and runs in
`validate()`.

## Findings

A [`Finding`](../reference/api.md#pycuf.findings.Finding) has a stable `code`, a `severity`
(`ERROR`, `WARNING` or `INFO`), a `message`, and where possible the `line`, `column`, element
`path` (`/CUF/BEGROTING[1]/BUNDELING[2]@LOONKOSTEN`) and the offending raw `value`. The
[finding-code reference](../reference/codes.md) lists every code.

Problems that exporters make on every element are reported once with a count, for example
"BEGROTINGSREGEL has an empty value for the required attribute BTW (458 times; first at line 29)".

## Stated totals

Bundles and the estimate state their totals (`UREN`, `LOONKOSTEN`, …). CUF-XML calls them
control totals: the estimate lines are leading. In practice they are often wrong. Of the public
sample files studied for pycuf, three out of five carried wrong or all-zero totals. So pycuf
compares each stated value with the computed one:

- a difference beyond the policy's tolerance is `CUF5001` (bundle) or `CUF5002` (estimate);
- a bundle or estimate stating only zeros while its lines have costs is reported once, as
  `CUF5003`, because some exporters never fill them in.

The contract sum (`AANNEEMSOM`) is compared with the computed direct costs plus the tail items,
with and without items that look like VAT (`CUF5005`, INFO): CUF does not say which tail items
count.

## Severity overrides and limits

```python
pycuf.validate(
    path,
    severity_overrides={
        "CUF3017": None,  # silence
        "CUF5002": pycuf.Severity.ERROR,
    },
)  # escalate
```

Unknown codes raise `ValueError`, so a typo does not silently do nothing. `max_findings_per_code`
(default 100) and `max_findings` (10 000) cap the report; `report.counts` still counts every
occurrence and `report.suppressed` says how many were dropped.

## JSON

`report.to_dict()` / `report.to_json()` give a stable layout, versioned by `schema_version`,
including the policy used.

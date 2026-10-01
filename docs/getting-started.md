# Getting started

This tutorial takes about ten minutes. You will read a CUF file, look inside it, compute its costs,
find out what is wrong with a second file, and export the result as tables. You need Python 3.11
or newer.

## 1. Install pycuf and get two sample files

```console
pip install "pycuf[cli]"
curl -L -O https://raw.githubusercontent.com/SpireflyHQ/pycuf/main/examples/begroting.xml \
        -O https://raw.githubusercontent.com/SpireflyHQ/pycuf/main/examples/begroting-ibis.xml
```

Both files hold the same small, made-up estimate (*begroting*) for a housing project.
`begroting.xml` is tidy; `begroting-ibis.xml` is written the way Ibis writes CUF-XML, Windows-1252
and all, and its stated totals contain a mistake.

## 2. Take a first look

```console
$ pycuf info begroting.xml
```

The command shows the project, the software that wrote the file, how many bundles and lines it
has, and its totals as written (*stated*) and as computed by pycuf. In this file they agree.

## 3. Read the file in Python

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
```

```text
2026-001 Voorbeeldproject Woningbouw
9 bundles, 12 lines, 42 resource lines
```

An estimate is a tree. *Bundles* (`BUNDELING`) group *estimate lines* (`BEGROTINGSREGEL`) and
other bundles; each line has a quantity and unit prices for up to five cost types. pycuf gives
every Dutch element and attribute an English name, listed in the
[glossary](reference/glossary.md):

```python
for line in cuf.lines[:3]:
    print(line.code, line.description, line.quantity, line.unit, line.material_price)

line = cuf.lines[0]
print([b.code for b in cuf.ancestors(line)], cuf.sort_codes(line))
```

```text
000003 wapening 3 326.836 kg 239.38
000004 stucwerk 4 360.23 m2 68.88
000006 riolering 6 163.004 kg 119.12
['1', '1.1'] {'PLANCODE': '200-10'}
```

## 4. Compute the costs

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

Every amount is an exact `Decimal`, computed from quantities, hour norms, rates and prices with the
formulas of the CUF-XML specification: the direct costs of the work, before markups and VAT.
[Calculating](guide/calculation.md) explains the formulas and the *policies* that settle the
places where the specification is ambiguous.

## 5. Check a file

Now the second file:

```python
report = pycuf.validate("begroting-ibis.xml")
print(report.ok, len(report.findings), "findings")
for finding in report.findings[:4]:
    print(finding.code, finding.severity, finding.line, finding.message)
```

```text
True 12 findings
CUF5002 WARNING 6 BEGROTING LOONKOSTEN is 301077.313035186, computed 300977.313035186 (difference 100)
CUF5001 WARNING 7 BUNDELING '1' LOONKOSTEN is 158710.5947748, computed 158610.5947748 (difference 100)
CUF3017 WARNING 8 BEGROTINGSREGEL has an empty value for the required attribute BTW (21 times; first at line 8)
CUF5001 WARNING 11 BUNDELING '1.1' LOONKOSTEN is 100932.4429188, computed 100832.4429188 (difference 100)
```

Every bundle states €100 more labour than its lines add up to, and every line has an empty `BTW`
(VAT) attribute. Both are warnings: the file is still usable, because the estimate lines are what
counts. Each finding has a stable code; the [finding codes](reference/codes.md) explain them all.
The same check on the command line:

```console
$ pycuf totals begroting-ibis.xml --depth 1
$ pycuf validate begroting-ibis.xml
```

## 6. Export tables

```python
cuf.export("out/")  # one CSV file per table: project, bundles, lines, resource_lines, …
```

Open `out/lines.csv` in a spreadsheet: one row per estimate line, with its bundle path and its
computed costs. With `pycuf[polars]` installed, `cuf.to_polars()` gives the same tables as polars
DataFrames, and with `pycuf[arrow]` DuckDB can query them directly; see
[Interoperability](guide/interop.md).

## What next

- [Reading CUF files](guide/reading.md): the data model, the raw layer, encodings and lenient
  parsing.
- [Calculating](guide/calculation.md): formulas, element estimates, resource lines and policies.
- [Validation](guide/validation.md): every layer of checks, severities and overrides.
- [The CUF-XML format](guide/format.md): history, the two specification texts and what real
  exporters do.

# Reading CUF files

```python
import pycuf

cuf = pycuf.read("begroting.xml")  # a path, bytes or a binary file object
```

`read()` reads the whole file (CUF files are small), checks it on the way and returns a
[`CufFile`](../reference/api.md#pycuf.reader.CufFile). It only raises when the input cannot be
read at all: not CUF-XML (`NotCufError`), malformed XML (`XmlSyntaxError`), a DTD
(`ForbiddenConstructError`) or an exceeded limit (`LimitExceededError`). Everything else becomes a
[finding](validation.md).

## The data model

```text
CufFile
├── created, encoding, namespace, raw
├── project          Project          (PROJECTGEGEVENS)
├── sort_code_schemes  SortCodeScheme (SORTEERCODES) → entries: SortCodeEntry
├── estimate         Estimate         (BEGROTING) → stated totals, children
│   └── children     Bundle | Line    (BUNDELING | BEGROTINGSREGEL), in document order
│       Bundle  → children, quantity_lines, sort_codes, stated, multiplier
│       Line    → resources: ResourceLine (MAMO_REGEL), quantity_lines, sort_codes
└── tail             Tail | None      (STAARTGEGEVENS) → contract_sum, items: TailItem
```

All names are English; the [glossary](../reference/glossary.md) maps every Dutch element and
attribute to its class and field. The classes are frozen dataclasses. Numbers are
`decimal.Decimal`, dates `datetime.date` / `datetime.datetime`, and every value is `None` when
the attribute is absent, empty or invalid. The specification's defaults ("empty counts as 0",
"an empty factor counts as 1") are applied when [calculating](calculation.md), never in the
model, so the model shows exactly what the file says.

```python
for line in cuf.lines:  # every estimate line, in document order
    print(line.code, line.description, line.quantity, line.unit, line.material_price)

bundle = cuf.bundles[0]
bundle.children  # bundles and lines inside it
bundle.stated.labour  # the LOONKOSTEN as written (a control total)
bundle.multiplier  # DOORREKEN_HOEVEELHEID, if any
```

Flat views (`cuf.bundles`, `cuf.lines`, `cuf.resource_lines`, `cuf.quantity_lines`) list every
node in document order; `node.seq` is its position. `Line.bundle_seq` and `Bundle.parent_seq`
point to the enclosing bundle.

### Numbers

CUF-XML numbers are XDR `number`s: digits with an optional sign, decimal point and exponent
(`-123.456E+10`), in the range of a double. pycuf reads zero and magnitudes from
`2.2250738585072014E-308` to `1.7976931348623157E+308`, with at most 1,074 decimals (enough to
write any double exactly). Anything else, such as `1e999` or `0e-1000000000000`, is an invalid
value: `CUF3018` ("outside the supported range"), `None` in the model, the text in `raw`. A
short attribute can therefore never make a calculation or an export enormous.

### Navigating the tree

```python
cuf.parent(line)  # the enclosing bundle (None at the top level)
cuf.ancestors(line)  # all enclosing bundles, outermost first
for node in cuf.walk():  # every bundle and line, depth first
    ...
cuf.sort_codes(line)  # {'PLANCODE': '200-10', 'ADMICODE': 'A10.002'}
```

`sort_codes()` returns the *effective* sort codes: CUF-XML says a sort code on a bundle applies to
everything beneath it unless a lower node has its own code for the same scheme. Pass
`inherited=False` for the node's own codes only.

Text lines (headings and remarks without a quantity or prices) have `line.is_text == True`.

## The raw layer and vendor extensions

Every model object keeps its `RawElement` in `.raw`: the element with all its attributes
(including vendor extensions) as parsed, its line number and its path. Values are the parsed
text, not the bytes: references such as `&amp;` are resolved, XML turns line breaks and tabs
inside attribute values into spaces, and comments and processing instructions are not kept.

```python
line.raw.get("BTW")  # '' – the raw text
line.raw.line, line.raw.path  # 812, '/CUF/BEGROTING[1]/BUNDELING[3]/BEGROTINGSREGEL[7]'
line.extra  # {'WERKBESCHRIJVING': '…'} – attributes CUF-XML lacks
cuf.raw.iter("MAMO_REGEL")  # walk the raw tree yourself
```

Attributes that CUF-XML 4.003 does not define are reported once per element and attribute
(`CUF3012`) and are always available in `extra` and `raw`. Elements it does not define are
reported (`CUF3011`) and kept in the raw tree.

## Encodings and namespaces

Files declare their encoding in the XML declaration; Ibis writes `Windows-1252`, others UTF-8.
pycuf honours the declaration, including bytes that Windows-1252 does not define. A file without
a declaration is read as UTF-8; if it is really Windows-1252, pass `encoding="cp1252"`.

The default namespace of CUF files varies by producer (`x-schema:CufSchema.xml`,
`x-schema:Forum CUF-XML-schema4003.xsd`, or none) and some are not even valid URIs. pycuf
ignores namespaces and matches elements by name; `cuf.namespace` and `cuf.namespaces` record what
was declared.

## Lenient parsing

By default `read()` accepts three common deviations and reports each acceptance:

| Option | Accepts | Finding |
|---|---|---|
| `"decimal-comma"` | `12,5` as 12.5 | `CUF7003` |
| `"dmy-date"` | `3-5-2024` and `3-5-2024 13:10:29` | `CUF7002` |
| `"textual-boolean"` | `true` and `false` (exactly so) as 1 and 0 | `CUF7004` |

Pass `lenient=()` to read strictly; such values are then reported as invalid (`CUF3018`,
`CUF3019`, `CUF3020`) and left `None`. Negative quantities and prices on estimate and resource
lines are valid (omitted work, proceeds from salvaged material) but reported as `CUF7001` (INFO).

## Repairs

Some exporters write XML that is not well-formed. Two opt-in repairs fix the common cases, and
each repair is reported:

```python
cuf = pycuf.read(path, repair={"bare-ampersand", "control-chars"})
```

`bare-ampersand` escapes an `&` that starts no entity (as in `SYSTEEMHUIS="Bakker & Spees"`);
`control-chars` removes characters XML forbids.

## Options of `read()`

| Option | Default | Meaning |
|---|---|---|
| `policy` | `"usage-rules"` | default [calculation policy](calculation.md) of the file |
| `lenient` | both | accepted deviations (see above) |
| `encoding` | as declared | override the declared encoding |
| `repair` | none | opt-in repairs (see above) |
| `severity_overrides` | none | change or silence finding codes |
| `max_findings_per_code`, `max_findings` | 100, 10 000 | finding limits |
| `max_size`, `max_depth`, `max_attribute_size` | 256 MiB, 64, 1 Mi | [safety limits](../security.md) |

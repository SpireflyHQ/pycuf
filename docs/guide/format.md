# The CUF-XML format

CUF stands for *Calculatie Uitwissel Formaat*, "estimate exchange format". It carries a
construction cost estimate (*begroting*) between estimating packages, and from estimating to
post-calculation, project administration, planning and ERP.

## History and status

- **Forum Systeemhuizen Bouw**, an association of Dutch construction software vendors, created
  CUF. Before XML, CUF 3.000 (January 2000) was a text format in which numbers were multiplied by
  100 or 1000 and text fields had a fixed maximum length.
- **CUF-XML 4.000** moved to XML; **4.003** (working-group decisions of 2003, usage rules July 2006) replaced the six sort-code
  attributes `SC1`–`SC6` with `SORTEERCODE` elements and added `DOORREKEN_HOEVEELHEID`. The Forum
  declared the format public ("public domain") for non-members.
- At the end of 2021 **Ketenstandaard Bouw en Techniek** took over maintenance "as-is". 4.003 is
  still the latest version.

pycuf reads CUF-XML 4.000–4.003 (older 4.x files are read as 4.003 and reported as `CUF3002`;
their `SC1`–`SC6` attributes become sort codes). The pre-XML CUF 3 and older formats are not
supported: no specification or example of them is publicly available, and no current software
reads them.

## Two specification texts

1. **The schema** (`cufSchema.xml`, 4.003). It is a Microsoft XDR schema, not a W3C XSD, and its
   comments contain the functional description and the formulas. Ketenstandaard also made an XSD
   for its participants, available in its Semantic Treehouse environment.
2. **The usage rules** ("Gebruikersregels CUF 4003", July 2006), published by Ketenstandaard. They
   tighten several rules.

They disagree in a few places, which pycuf handles with [policies](calculation.md#policies):

| Topic | Schema | Usage rules | pycuf default |
|---|---|---|---|
| Factor written as 0 | (only "empty counts as 1") | "empty or 0 counts as 1" | 1 (`zero_factor="one"`) |
| `AANNEEMSOM` | "gross total" | excluding VAT | excluding VAT |
| Resource quantities | totals "form the unit prices" | resource totals usually equal the line | totals for the line |

There is no attribute saying whether a file is a *traditional* estimate or an *element* estimate,
and the Forum's own 2006 review notes that the styles have conflicting calculation rules.

## Structure

```text
CUF                       @AANMAAKDATUMTIJD
├── PROJECTGEGEVENS       project data, CUF_VERSIE, VALUTA, SYSTEEMHUIS, …
├── SORTEERCODES*         declares a sort-code scheme, optionally with SORTEERCODE_REGEL codes
├── BEGROTING             six stated totals
│   ├── BUNDELING*        nested to any depth, with stated totals and DOORREKEN_HOEVEELHEID
│   │   └── …
│   └── BEGROTINGSREGEL*  quantity, unit prices per cost type, BTW
│       ├── MAMO_REGEL*            one cost type broken down
│       ├── HOEVEELHEDENSTAAT_REGEL*   quantity take-off
│       └── SORTEERCODE*
└── STAARTGEGEVENS        AANNEEMSOM, with VRIJE_GROOTHEID tail items
```

All data is in attributes, and every number is written with a decimal point and no thousands
separator (the XDR `number` type also allows an exponent). The [glossary](../reference/glossary.md)
lists every element and attribute.

## What real exporters do

The format leaves room, and exporters use it. These are the quirks pycuf knows about, each with
its finding code:

| Exporter | Quirk | pycuf |
|---|---|---|
| Ibis (Brink, `SYSTEEMHUIS="BRINK"`) | `encoding="Windows-1252"`, `xmlns:Ibis` | decoded correctly |
| Ibis | empty required `BTW` on every line | `CUF3017`, once with a count |
| Ibis | text lines marked with an `stk` sort code | `Line.is_text` |
| Ibis | wrong bundle totals in some versions; staart items folded into estimate totals | `CUF5001`/`CUF5002` |
| Ibis Infra | `Ibis:BEGROTINGTYPE`, `Ibis:AANDUIDING` attributes; line breaks in descriptions | `extra`, `CUF3012` |
| Forum example file | namespace `x-schema:Forum CUF-XML-schema4003.xsd` (not a valid URI) | ignored, read normally |
| Dataviewers | `d-m-yyyy` dates, empty `VALUTA`, `STELPOST="0"`, no `STAARTGEGEVENS`, zero totals | `CUF7002`, `CUF3017`, `CUF3010`, `CUF5003` |
| Bakker & Spees CIVIEL | lines directly under `BEGROTING`; `WERKBESCHRIJVING`, `KOSTPRIJS`, `FACTOR` attributes | `extra`, `CUF3012` |
| Bakker & Spees | `<SORTEERCODE ACTI="17" NACA="1"/>` | read as sort codes `ACTI` and `NACA`, `CUF3025` |
| Bakker & Spees, ERP importers | labour resource lines with hours in `HOEVEELHEID` and the rate in `PRIJS` | `policy="erp"` |
| AFAS, others | zero estimate totals; sort codes used without a `SORTEERCODES` declaration | `CUF5003`, `CUF4001` |
| Open Calc Studio | writes its own `<Calculatie>` format as ".cuf" | `NotCufError` with a hint |

Found another one? Please open a
[file compatibility report](https://github.com/SpireflyHQ/pycuf/issues/new?template=file_compatibility.yml),
with an anonymised snippet only.

## Licence and trademarks

Data file formats are not protected as computer programs. In *SAS Institute v World Programming*
(C-406/10, 2012) the EU Court of Justice held that neither a program's functionality nor the
programming language and data file format it uses are a form of expression of the program, so
the Software Directive (then 91/250/EEC, now 2009/24/EC) does not protect them. The Court left
open protection of a language or file format as a work under the general copyright directive
(2001/29/EC) if it is its author's own intellectual creation, and held that copying elements
described in a manual can infringe the manual's copyright. pycuf therefore does not bundle the
specification documents; it describes the format in its own words. This is a summary, not legal
advice. "Forum CUF XML" was registered as a Benelux trademark by Forum Systeemhuizen
Bouw. pycuf is an independent project, not affiliated with or endorsed by Ketenstandaard or the
Forum.

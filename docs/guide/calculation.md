# Calculating

```python
totals = cuf.totals()  # under the file's policy (the usage rules by default)
totals.estimate  # Costs(hours=…, labour=…, material=…, …)
totals.estimate.total  # direct costs, excluding markups and VAT
totals[bundle]  # a bundle's costs: the sum of its direct children
totals[line]  # a line's costs, before multipliers
totals.extended(line)  # its contribution to the estimate, multipliers applied
totals.resource(resource_line)  # a resource line's costs
```

`Costs` holds labour `hours` plus the five cost types of CUF-XML: `labour` (loon), `material`
(materiaal), `equipment` (materieel), `subcontracting` (onderaanneming) and `other` (overig).
`total` is the sum of the five amounts. All arithmetic is exact `Decimal` arithmetic at 60
significant digits in pycuf's own decimal context: your context's precision, rounding, exponent
limits and traps change nothing, also when you read `total`, `extended()` or a table inside it.
Real estimates need fewer than 30 digits; a result that would need more than 60 (only absurd
inputs produce one) is rounded half-even to 60. Numbers in a file are limited to the
[range pycuf reads](reading.md#numbers), so no calculation can overflow or silently become 0.

## The formulas

**Estimate line** (`BEGROTINGSREGEL`), with `Q = HOEVEELHEID × HOEVEELHEID_FACTOR`:

| Cost | Formula |
|---|---|
| hours | `Q × UUR_NORM` |
| labour | `Q × UUR_NORM × UUR_TARIEF` |
| material, equipment, subcontracting, other | `Q × MATERIAALPRIJS`, `× MATERIEELPRIJS`, `× ONDERAANNEMINGSPRIJS`, `× OVERIGE_KOSTEN` |

`AANTAL × INZET` and `PRODUCTIE` are informative and never change a cost.

**Resource line** (`MAMO_REGEL`): labour (`LOON`) hours = `HOEVEELHEID × UUR_NORM`, labour =
hours × `UUR_TARIEF × PRIJS_FACTOR`; other cost types `HOEVEELHEID × PRIJS × PRIJS_FACTOR`.

**Bundle** (`BUNDELING`): the sum of its direct children. A child bundle counts with its own
`DOORREKEN_HOEVEELHEID`; the bundle's own multiplier is *not* included, because that is what its
stated totals show. The **estimate** is the sum of its direct children in the same way.

Missing or empty numbers count as 0, missing or empty factors as 1.

## Policies

The two specification texts (the 4.003 schema comments and the 2006 usage rules) disagree in
places, and exporters and importers read them differently. A
[`Policy`](../reference/api.md#pycuf.policy.Policy) makes every choice explicit:

| Field | Default | Choices |
|---|---|---|
| `zero_factor` | `"one"` | what a factor written as `0` means: ignore it (usage rules) or literally 0 |
| `estimate_style` | `"auto"` | whether `DOORREKEN_HOEVEELHEID` multiplies: `"element"`, `"traditional"` (ignore) or `"auto"` (when present) |
| `labour` | `"spec"` | labour resource lines: the spec formula, or `"erp"` (`HOEVEELHEID` is hours, `PRIJS` the rate) |
| `resources` | `"fallback"` | price a line from its resource lines when it states no prices itself, `"ignore"` them, or `"prefer"` them |
| `resource_basis` | `"total"` | a resource line's quantity is for the whole line, or `"per-unit"` of the line |
| `abs_tol`, `rel_tol` | `0.01`, `0` | tolerances for checking stated totals (`math.isclose` semantics) |
| `rounding` | `"ROUND_HALF_UP"` | rounding of a computed value to the stated precision before comparing |

### Presets

| Name | Constant | Meaning |
|---|---|---|
| `"usage-rules"` | `pycuf.policy.USAGE_RULES` | the 2006 "Gebruikersregels CUF 4003"; the default |
| `"schema"` | `pycuf.policy.SCHEMA` | the literal schema: a factor of 0 is 0, resource lines are only informative |
| `"erp"` | `pycuf.policy.ERP` | labour resource lines as ERP importers read them |

```python
from decimal import Decimal
from pycuf.policy import ERP

cuf.totals(policy="schema")  # a preset by name
cuf.totals(policy=ERP.replace(abs_tol=Decimal("0.05")))  # a preset with one field changed
pycuf.read(path, policy="erp")  # the file's default from then on
```

Policies are immutable and hashable: `replace()` returns a validated copy, and `cuf.totals()`
caches one result per policy. Every result records the policy it used (`totals.policy`) and the
resolved estimate style (`totals.estimate_style`).

### Element estimates

In an *element estimate* (elementenbegroting) bundles are building elements with a quantity,
`DOORREKEN_HOEVEELHEID`, that multiplies all costs beneath them: a façade element of 100 m² whose
lines are priced per m². With `estimate_style="auto"` pycuf applies the multipliers whenever a
file contains them and reports it (`CUF7005`). `totals.multiplier(node)` gives the product of the
multipliers applied to a node.

### Resource lines

CUF-XML makes the estimate line leading and its resource (MAMO) lines informative. Some exporters
only price the resource lines, so with `resources="fallback"` a line without prices of its own is
priced from its resource lines (reported as `CUF5006`). When a line has both, pycuf checks that
they agree (`CUF5004`).

### Why these defaults?

The defaults follow the 2006 usage rules, which Ketenstandaard publishes as the rules for 4.003
and which AFAS also documents ("leeg of 0 … is dus 1"). Each alternative exists because a real
exporter or importer behaves that way; the [format guide](format.md) has the details.

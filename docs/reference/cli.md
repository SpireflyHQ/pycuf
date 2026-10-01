# Command line

```bash
pip install "pycuf[cli]"
```

The `pycuf` command is always installed, but needs the `cli` extra (Typer). Without it, it prints
the install hint and exits with code 3. `python -m pycuf` works the same way.

| Command | Purpose |
|---|---|
| `pycuf info FILE` | summarise a file: project, software, counts, computed and stated totals |
| `pycuf totals FILE` | computed totals per bundle, marking stated totals that differ |
| `pycuf validate FILE…` | validate files and report every finding |
| `pycuf export FILE -o DIR` | export the normalized tables to a directory |
| `pycuf codes` | list all finding codes with their default severity |

`pycuf --version` prints the version; every command has `--help`. The commands that compute take
`--policy usage-rules|schema|erp`; all reading commands take `--encoding` and `--strict-parsing`
(no decimal commas or d-m-yyyy dates).

## `pycuf info`

```console
$ pycuf info examples/begroting.xml
file               examples/begroting.xml
cuf version        4.003
software house     -
created            2026-10-01T10:15:00
encoding           utf-8
project            2026-001 – Voorbeeldproject Woningbouw
client             -
estimator          J. de Calculator
currency           EUR
bundles            9
lines              12
resource lines     42
sort code schemes  PLANCODE
estimate style     traditional
computed           hours=5120.3829619, labour=300977.313035186, material=395099.61479, equipment=37273.1567575, subcontracting=29557.1276, other=6333.221846, total=769240.434028686
stated             hours=5120.3829619, labour=300977.313035186, material=395099.61479, equipment=37273.1567575, subcontracting=29557.1276, other=6333.221846
contract sum       838472.074028686
findings           1
```

`--output json` gives the same as a JSON object (`schema_version` 1).

## `pycuf totals`

```console
$ pycuf totals examples/begroting-ibis.xml --depth 1
examples/begroting-ibis.xml  (traditional estimate, policy usage-rules)
bundle                                                  total       labour     material    subcontr.
----------------------------------------------------------------------------------------------------
1 beton (element 1)                                360,184.73   158,610.59   149,219.78    26,527.98  ≠ stated by +100.00
2 tegelwerk (element 2)                            278,790.21   106,385.24   161,213.89         0.00  ≠ stated by +100.00
3 voegwerk (element 3)                             130,265.49    35,981.48    84,665.94     3,029.15  ≠ stated by +100.00
----------------------------------------------------------------------------------------------------
BEGROTING                                          769,240.43   300,977.31   395,099.61    29,557.13  ≠ stated by +100.00
hours                                                 5120.38
contract sum (stated, excl. VAT)                   838,472.07
```

| Option | Meaning |
|---|---|
| `--depth N` | show bundles up to level N (default: all) |
| `--policy NAME` | calculation policy preset |
| `--output text\|json` | output format |

## `pycuf validate`

```console
$ pycuf validate examples/begroting-ibis.xml
examples/begroting-ibis.xml: 0 error(s), 11 warning(s), 1 info
  line 6 WARNING CUF5002 BEGROTING LOONKOSTEN is 301077.313035186, computed 300977.313035186 (difference 100) ['301077.3130351860']
  line 7 WARNING CUF5001 BUNDELING '1' LOONKOSTEN is 158710.5947748, computed 158610.5947748 (difference 100) ['158710.59477480']
  line 8:6 WARNING CUF3017 BEGROTINGSREGEL has an empty value for the required attribute BTW (21 times; first at line 8)
  …
```

| Option | Meaning |
|---|---|
| `--strict` | exit with 1 when there are warnings |
| `--max-findings N` | keep at most N findings per code |
| `--repair NAME` | opt-in repair: `control-chars`, `bare-ampersand` (repeatable) |
| `--output text\|json` | output format |

Exit codes: **0** no errors, **1** warnings (only with `--strict`), **2** errors, **3** pycuf could
not do its job (unreadable input, usage error, missing extra). That makes `pycuf validate` easy to
use in scripts and CI.

## `pycuf export`

```console
$ pycuf export examples/begroting.xml -o out/ -f parquet -t lines -t bundles
out/lines.parquet
out/bundles.parquet
```

| Option | Meaning |
|---|---|
| `-o, --out DIR` | output directory (created if needed) |
| `-f, --format csv\|jsonl\|parquet` | file format (default `csv`; Parquet needs `pycuf[parquet]`) |
| `-t, --table NAME` | table to export (repeatable; default all) |

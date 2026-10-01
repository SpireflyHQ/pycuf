"""Command-line interface (``pycuf[cli]``).

Exit codes: 0 ok · 1 warnings (only with ``--strict``) · 2 errors · 3 tool failure.
"""

from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Annotated, Any

import typer

from . import __version__
from .errors import PycufError
from .findings import CODES, Severity
from .models import Bundle, Costs, StatedTotals
from .reader import read as _read
from .validate import validate as _validate

app: typer.Typer = typer.Typer(
    name="pycuf",
    help="Read, check and analyse CUF-XML construction cost estimates.",
    no_args_is_help=True,
    add_completion=False,
)

FilesArg = Annotated[list[Path], typer.Argument(exists=True, dir_okay=False, readable=True)]
FileArg = Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]
EncodingOpt = Annotated[
    str | None, typer.Option("--encoding", help="Override the declared encoding.")
]
RepairOpt = Annotated[
    list[str] | None,
    typer.Option("--repair", help="Opt-in repair: control-chars, bare-ampersand (repeatable)."),
]
StrictParsingOpt = Annotated[
    bool,
    typer.Option("--strict-parsing", help="Do not accept decimal commas or d-m-yyyy dates."),
]


class OutputFormat(str, Enum):
    """Output format."""

    text = "text"
    json = "json"


class ExportFormat(str, Enum):
    """Export file format."""

    csv = "csv"
    jsonl = "jsonl"
    parquet = "parquet"


class PolicyName(str, Enum):
    """Calculation policy preset."""

    usage_rules = "usage-rules"
    schema = "schema"
    erp = "erp"


PolicyOpt = Annotated[PolicyName, typer.Option("--policy", help="Calculation policy preset.")]


def _fail(message: str) -> typer.Exit:
    typer.echo(f"pycuf: {message}", err=True)
    return typer.Exit(3)


def _fail_exc(path: Path, exc: Exception) -> typer.Exit:
    msg = str(exc)
    return _fail(msg if msg.startswith(str(path)) else f"{path}: {msg}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"pycuf {__version__}")
        raise typer.Exit


def _lenient(strict: bool) -> tuple[str, ...]:
    return () if strict else ("decimal-comma", "dmy-date")


def _num(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}"


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Read, check and analyse CUF-XML construction cost estimates."""


@app.command()
def info(
    file: FileArg,
    policy: PolicyOpt = PolicyName.usage_rules,
    output: OutputFormat = OutputFormat.text,
    encoding: EncodingOpt = None,
    repair: RepairOpt = None,
    strict_parsing: StrictParsingOpt = False,
) -> None:
    """Summarise FILE: project, software, counts, computed and stated totals."""
    try:
        cuf = _read(
            file,
            policy=policy.value,
            encoding=encoding,
            repair=repair or (),
            lenient=_lenient(strict_parsing),  # type: ignore[arg-type]
        )
        totals = cuf.totals()
        report = cuf.validate()
    except PycufError as exc:
        raise _fail_exc(file, exc) from None
    p = cuf.project
    data: dict[str, Any] = {
        "schema_version": 1,
        "file": str(file),
        "cuf_version": p.cuf_version,
        "software_house": p.software_house,
        "created": cuf.created.isoformat() if cuf.created else None,
        "encoding": cuf.encoding.effective,
        "project": " – ".join(x for x in (p.number, p.name) if x) or None,
        "client": p.client,
        "estimator": p.estimator,
        "currency": p.currency,
        "bundles": len(cuf.bundles),
        "lines": len(cuf.lines),
        "resource_lines": len(cuf.resource_lines),
        "sort_code_schemes": [s.name for s in cuf.sort_code_schemes],
        "estimate_style": totals.estimate_style,
        "computed": {k: _num(v) for k, v in totals.estimate.items()}
        | {"total": _num(totals.estimate.total)},
        "stated": {k: _num(v) for k, v in cuf.estimate.stated.items()},
        "contract_sum": _num(cuf.tail.contract_sum) if cuf.tail else None,
        "findings": {
            "errors": len(report.errors),
            "warnings": len(report.warnings),
            "info": len(report.findings) - len(report.errors) - len(report.warnings),
        },
    }
    if output is OutputFormat.json:
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    width = max(len(k) for k in data)
    for k, v in data.items():
        if k == "schema_version":
            continue
        if isinstance(v, dict):
            shown = ", ".join(f"{a}={b}" for a, b in v.items() if b is not None)
            if k == "findings":
                shown = ", ".join(f"{b} {a}" for a, b in v.items())
        elif isinstance(v, list):
            shown = ", ".join(str(x) for x in v)
        else:
            shown = "-" if v is None else v
        typer.echo(f"{k.replace('_', ' '):<{width}}  {shown}")


@app.command()
def validate(
    files: FilesArg,
    policy: PolicyOpt = PolicyName.usage_rules,
    output: OutputFormat = OutputFormat.text,
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with 1 when there are warnings.")
    ] = False,
    max_findings: Annotated[
        int, typer.Option("--max-findings", help="Keep at most N findings per code.")
    ] = 100,
    encoding: EncodingOpt = None,
    repair: RepairOpt = None,
    strict_parsing: StrictParsingOpt = False,
) -> None:
    """Validate FILES: structure, values, sort codes and stated against computed totals."""
    worst = 0
    reports = []
    for f in files:
        try:
            report = _validate(
                f,
                policy=policy.value,
                encoding=encoding,
                repair=repair or (),
                lenient=_lenient(strict_parsing),  # type: ignore[arg-type]
                max_findings_per_code=max_findings,
            )
        except PycufError as exc:
            raise _fail_exc(f, exc) from None
        reports.append(report)
        sev = report.max_severity
        if sev is Severity.ERROR:
            worst = max(worst, 2)
        elif sev is Severity.WARNING and strict:
            worst = max(worst, 1)
    if output is OutputFormat.json:
        payload = [r.to_dict() for r in reports]
        typer.echo(
            json.dumps(payload if len(payload) > 1 else payload[0], indent=2, ensure_ascii=False)
        )
    else:
        for report in reports:
            typer.echo(str(report))
    raise typer.Exit(worst)


@app.command()
def totals(
    file: FileArg,
    policy: PolicyOpt = PolicyName.usage_rules,
    depth: Annotated[
        int, typer.Option("--depth", "-d", help="Show bundles up to this level (0 = all).")
    ] = 0,
    output: OutputFormat = OutputFormat.text,
    encoding: EncodingOpt = None,
    strict_parsing: StrictParsingOpt = False,
) -> None:
    """Show the computed totals of FILE per bundle, marking stated totals that differ."""
    try:
        cuf = _read(
            file,
            policy=policy.value,
            encoding=encoding,
            lenient=_lenient(strict_parsing),  # type: ignore[arg-type]
        )
        result = cuf.totals()
    except PycufError as exc:
        raise _fail_exc(file, exc) from None
    shown = [b for b in cuf.bundles if depth <= 0 or b.depth <= depth]
    if output is OutputFormat.json:
        rows = [
            {
                "seq": b.seq,
                "depth": b.depth,
                "code": b.code,
                "description": b.description,
                "multiplier": _num(result.multiplier(b)),
                "computed": {k: _num(v) for k, v in result[b].items()},
                "stated": {k: _num(v) for k, v in b.stated.items()},
            }
            for b in shown
        ]
        payload = {
            "schema_version": 1,
            "file": str(file),
            "estimate_style": result.estimate_style,
            "estimate": {k: _num(v) for k, v in result.estimate.items()},
            "bundles": rows,
        }
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    typer.echo(f"{file}  ({result.estimate_style} estimate, policy {policy.value})")
    header = f"{'bundle':<46} {'total':>14} {'labour':>12} {'material':>12} {'subcontr.':>12}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for b in shown:
        typer.echo(_bundle_row(b, result[b]))
    typer.echo("-" * len(header))
    e = result.estimate
    mark = _mark(cuf.estimate.stated, e)
    typer.echo(
        f"{'BEGROTING':<46} {_money(e.total):>14} {_money(e.labour):>12} "
        f"{_money(e.material):>12} {_money(e.subcontracting):>12}{mark}"
    )
    typer.echo(f"{'hours':<46} {e.hours.quantize(Decimal('0.01')):>14}")
    if cuf.tail is not None and cuf.tail.contract_sum is not None:
        typer.echo(f"{'contract sum (stated, excl. VAT)':<46} {_money(cuf.tail.contract_sum):>14}")


def _mark(stated: StatedTotals, computed: Costs) -> str:
    """Mark a difference between the stated and computed total of the cost types stated."""
    names = [n for n, v in stated.items() if v is not None and n != "hours"]
    if not names:
        return ""
    written = sum((getattr(stated, n) for n in names), Decimal(0))
    actual = sum((getattr(computed, n) for n in names), Decimal(0))
    if abs(written - actual) < Decimal("0.01"):
        return ""
    return f"  ≠ stated by {written - actual:+,.2f}"


def _bundle_row(b: Bundle, costs: Costs) -> str:
    label = "  " * (b.depth - 1) + " ".join(x for x in (b.code, b.description) if x)
    if len(label) > 46:
        label = label[:45] + "…"
    return (
        f"{label:<46} {_money(costs.total):>14} {_money(costs.labour):>12} "
        f"{_money(costs.material):>12} {_money(costs.subcontracting):>12}"
        f"{_mark(b.stated, costs)}"
    )


@app.command()
def export(
    file: FileArg,
    out: Annotated[Path, typer.Option("--out", "-o", help="Output directory.")],
    fmt: Annotated[ExportFormat, typer.Option("--format", "-f")] = ExportFormat.csv,
    tables: Annotated[
        list[str] | None, typer.Option("--table", "-t", help="Table to export (repeatable).")
    ] = None,
    policy: PolicyOpt = PolicyName.usage_rules,
    encoding: EncodingOpt = None,
    strict_parsing: StrictParsingOpt = False,
) -> None:
    """Export the normalized tables of FILE to a directory."""
    try:
        cuf = _read(
            file,
            policy=policy.value,
            encoding=encoding,
            lenient=_lenient(strict_parsing),  # type: ignore[arg-type]
        )
        paths = cuf.export(out, format=fmt.value, tables=tables)
    except (PycufError, KeyError, ImportError, ValueError) as exc:
        raise _fail_exc(file, exc) from None
    for p in paths:
        typer.echo(p)


@app.command()
def codes(output: OutputFormat = OutputFormat.text) -> None:
    """List all finding codes with their default severity."""
    if output is OutputFormat.json:
        typer.echo(
            json.dumps(
                [
                    {"code": c.code, "severity": c.severity.name, "title": c.title}
                    for c in CODES.values()
                ],
                indent=2,
            )
        )
        return
    for c in CODES.values():
        typer.echo(f"{c.code}  {c.severity.name:<7}  {c.title}")

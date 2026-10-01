"""Validation: everything pycuf notices about a CUF file, in one report.

=====  ==========================================================================================
Layer  Checks
=====  ==========================================================================================
L1     input and character encoding (``CUF1xxx``)
L2     XML well-formedness and security (``CUF2xxx``; fatal problems become a finding here)
L3     structure and values against CUF-XML 4.003 (``CUF3xxx``)
L4     sort codes: declared, used, in the declared table (``CUF4xxx``)
L5     stated totals, resource lines and the contract sum against computed values (``CUF5xxx``)
L6     data quality, lenient parsing and how the policy was applied (``CUF7xxx``)
=====  ==========================================================================================

L1–L4 and part of L6 happen while reading (:attr:`pycuf.CufFile.findings`); L5 needs a
:class:`~pycuf.policy.Policy` and runs here.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from . import _xml
from ._source import DEFAULT_MAX_SIZE, SourceLike
from .calc import check_totals
from .errors import ForbiddenConstructError, LimitExceededError, XmlSyntaxError
from .findings import Finding, FindingCollector, Severity
from .policy import DEFAULT, Policy, PresetName, resolve_policy

if TYPE_CHECKING:
    from .reader import CufFile, Leniency

__all__ = ["ValidationReport", "validate"]

SCHEMA_VERSION = 1
"""Version of the JSON layout of :meth:`ValidationReport.to_dict`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationReport:
    """Result of :func:`validate` or :meth:`pycuf.CufFile.validate`.

    Attributes:
        name: The file that was validated.
        findings: Findings, most severe first, then in file order.
        counts: Occurrences per code, including findings suppressed by limits.
        suppressed: Number of findings dropped because of limits.
        policy: The calculation policy used (``None`` when the file could not be read).
        estimate_style: The resolved estimate style (``None`` when not computed).
        stats: Counts of what the file contains.
    """

    name: str
    findings: tuple[Finding, ...]
    counts: Mapping[str, int]
    suppressed: int
    policy: Policy | None
    estimate_style: Literal["traditional", "element"] | None
    stats: Mapping[str, int]

    @property
    def errors(self) -> tuple[Finding, ...]:
        """Findings with severity ERROR."""
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        """Findings with severity WARNING."""
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        """``True`` when there are no ERROR findings."""
        return not self.errors

    @property
    def max_severity(self) -> Severity | None:
        """Highest severity among the findings."""
        return max((f.severity for f in self.findings), default=None)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dictionary (layout versioned by ``schema_version``)."""
        policy = None
        if self.policy is not None:
            policy = {
                "zero_factor": self.policy.zero_factor,
                "estimate_style": self.policy.estimate_style,
                "labour": self.policy.labour,
                "resources": self.policy.resources,
                "resource_basis": self.policy.resource_basis,
                "abs_tol": str(self.policy.abs_tol),
                "rel_tol": str(self.policy.rel_tol),
                "rounding": self.policy.rounding,
            }
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "ok": self.ok,
            "max_severity": self.max_severity.name if self.max_severity else None,
            "policy": policy,
            "estimate_style": self.estimate_style,
            "stats": dict(self.stats),
            "counts": dict(self.counts),
            "suppressed": self.suppressed,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, **kwargs: Any) -> str:
        """Return :meth:`to_dict` as JSON (keyword arguments go to :func:`json.dumps`)."""
        kwargs.setdefault("ensure_ascii", False)
        return json.dumps(self.to_dict(), **kwargs)

    def __str__(self) -> str:
        head = (
            f"{self.name}: {len(self.errors)} error(s), {len(self.warnings)} warning(s), "
            f"{len(self.findings) - len(self.errors) - len(self.warnings)} info"
        )
        return "\n".join([head, *(f"  {f}" for f in self.findings)])


def _sorted(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    indexed = list(enumerate(findings))
    indexed.sort(key=lambda p: (-p[1].severity, p[1].line if p[1].line is not None else 0, p[0]))
    return tuple(f for _, f in indexed)


def validate_file(
    cuf: CufFile,
    *,
    policy: Policy | PresetName | None = None,
    severity_overrides: Mapping[str, Severity | None] | None = None,
) -> ValidationReport:
    """Validate an already read file (see :meth:`pycuf.CufFile.validate`)."""
    from .reader import check_overrides  # noqa: PLC0415

    overrides = check_overrides(severity_overrides)
    totals = cuf.totals(policy=policy)
    read = cuf._collector
    collector = FindingCollector(
        max_per_code=read.max_per_code,
        max_total=read.max_total,
        overrides={**read.overrides, **overrides},
    )
    collector.extend(cuf.findings)
    collector.extend(totals.findings)
    check_totals(cuf, totals, collector)
    counts: Counter[str] = Counter(read.counts)
    for code, n in collector.counts.items():
        counts[code] = max(counts[code], n)
    return ValidationReport(
        name=cuf.name,
        findings=_sorted(collector),
        counts=dict(counts),
        suppressed=read.suppressed + collector.suppressed,
        policy=totals.policy,
        estimate_style=totals.estimate_style,
        stats={
            "bundles": len(cuf.bundles),
            "lines": len(cuf.lines),
            "resource_lines": len(cuf.resource_lines),
            "quantity_lines": len(cuf.quantity_lines),
            "sort_code_schemes": len(cuf.sort_code_schemes),
        },
    )


def validate(
    source: SourceLike,
    *,
    policy: Policy | PresetName = DEFAULT,
    lenient: Iterable[Leniency] = ("decimal-comma", "dmy-date"),
    encoding: str | None = None,
    repair: Iterable[str] = (),
    severity_overrides: Mapping[str, Severity | None] | None = None,
    max_findings_per_code: int | None = 100,
    max_findings: int | None = 10_000,
    max_size: int | None = DEFAULT_MAX_SIZE,
    max_depth: int = _xml.DEFAULT_MAX_DEPTH,
    max_attribute_size: int = _xml.DEFAULT_MAX_ATTRIBUTE_SIZE,
) -> ValidationReport:
    """Read and validate a CUF file: ``read(source, ...).validate()``, plus fatal problems.

    Malformed XML, forbidden constructs and exceeded limits do not raise here: they become an
    ``ERROR`` finding (``CUF2001``–``CUF2003``) in an otherwise empty report. Input that is not
    CUF-XML at all still raises :class:`~pycuf.errors.NotCufError`.

    Args:
        source: Path, bytes or binary file object.
        policy: Calculation policy or preset name (see :mod:`pycuf.policy`).
        lenient: Deviations to accept (see :func:`pycuf.read`).
        encoding: Override the declared encoding.
        repair: Opt-in repairs (see :func:`pycuf.read`).
        severity_overrides: Change severities per code, or silence codes with ``None``.
        max_findings_per_code: Keep at most this many findings per code.
        max_findings: Keep at most this many findings in total.
        max_size: Refuse inputs larger than this many bytes.
        max_depth: Maximum XML nesting depth.
        max_attribute_size: Maximum length of one attribute value.
    """
    from .reader import check_overrides, read  # noqa: PLC0415

    resolved = resolve_policy(policy)
    try:
        cuf = read(
            source,
            policy=resolved,
            lenient=lenient,
            encoding=encoding,
            repair=repair,
            severity_overrides=severity_overrides,
            max_findings_per_code=max_findings_per_code,
            max_findings=max_findings,
            max_size=max_size,
            max_depth=max_depth,
            max_attribute_size=max_attribute_size,
        )
    except (XmlSyntaxError, LimitExceededError) as exc:
        code = (
            "CUF2002"
            if isinstance(exc, ForbiddenConstructError)
            else "CUF2003"
            if isinstance(exc, LimitExceededError)
            else "CUF2001"
        )
        fc = FindingCollector(overrides=check_overrides(severity_overrides))
        fc.add(
            code,
            str(exc),
            line=getattr(exc, "line", None),
            column=getattr(exc, "column", None),
        )
        if isinstance(source, (str, os.PathLike)):
            name: object = os.fspath(source)
        else:
            name = getattr(source, "name", "<input>")
        return ValidationReport(
            name=str(name),
            findings=_sorted(fc),
            counts=fc.counts,
            suppressed=0,
            policy=resolved,
            estimate_style=None,
            stats={},
        )
    return cuf.validate()

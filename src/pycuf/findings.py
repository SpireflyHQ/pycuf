"""Graded, coded findings.

Every problem pycuf notices in a file is reported as a :class:`Finding` with a stable code
(``CUF<nnnn>``), a :class:`Severity` and the location where it occurred. Codes are grouped:

========  ==============================================
``1xxx``  input and character encoding
``2xxx``  XML well-formedness and security
``3xxx``  structure and values (against CUF-XML 4.003)
``4xxx``  sort codes (SORTEERCODES / SORTEERCODE)
``5xxx``  stated totals against computed totals
``7xxx``  data quality, conventions and lenient parsing
========  ==============================================

:data:`CODES` documents every code. Codes are never renumbered or reused.
"""

from __future__ import annotations

import enum
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

__all__ = ["CODES", "CodeInfo", "Finding", "FindingCollector", "Severity"]


class Severity(enum.IntEnum):
    """How serious a finding is. Ordered: ``INFO < WARNING < ERROR``."""

    INFO = 10
    """Notable, but neither wrong nor likely to affect analysis."""
    WARNING = 20
    """Likely a data problem, or something that affects analysis."""
    ERROR = 30
    """Violates the CUF-XML 4.003 specification."""

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class CodeInfo:
    """Documentation of a finding code."""

    code: str
    severity: Severity
    title: str


def _c(code: str, severity: Severity, title: str) -> CodeInfo:
    return CodeInfo(code, severity, title)


_E, _W, _I = Severity.ERROR, Severity.WARNING, Severity.INFO

#: Registry of all finding codes with their default severity.
CODES: Mapping[str, CodeInfo] = {
    c.code: c
    for c in (
        # 1xxx input & encoding
        _c("CUF1001", _I, "Byte-order mark present"),
        _c("CUF1002", _I, "No XML declaration; encoding assumed to be UTF-8"),
        _c("CUF1004", _I, "Encoding overridden by the caller"),
        _c("CUF1006", _W, "Bytes undefined in the encoding kept as Latin-1 characters"),
        _c("CUF1010", _W, "Repair: XML-illegal control characters removed"),
        _c("CUF1012", _W, "Repair: bare ampersands escaped"),
        _c("CUF1013", _W, "Data after the end of the document ignored"),
        # 2xxx XML & security
        _c("CUF2001", _E, "XML is not well-formed"),
        _c("CUF2002", _E, "Forbidden construct (DOCTYPE/ENTITY)"),
        _c("CUF2003", _E, "Safety limit exceeded"),
        # 3xxx structure & values
        _c("CUF3001", _I, "CUF version"),
        _c("CUF3002", _W, "CUF version is not 4.003"),
        _c("CUF3010", _E, "Required element missing"),
        _c("CUF3011", _W, "Element not defined in CUF-XML 4.003"),
        _c("CUF3012", _I, "Attribute not defined in CUF-XML 4.003 (vendor extension)"),
        _c("CUF3013", _E, "Element not allowed in this place"),
        _c("CUF3014", _E, "Element occurs more often than allowed"),
        _c("CUF3015", _E, "Element out of order"),
        _c("CUF3016", _E, "Required attribute missing"),
        _c("CUF3017", _W, "Required attribute is empty"),
        _c("CUF3018", _E, "Invalid number"),
        _c("CUF3019", _E, "Invalid date or date-time"),
        _c("CUF3020", _E, "Invalid boolean"),
        _c("CUF3021", _E, "Value not in the allowed code list"),
        _c("CUF3022", _I, "Software house (SYSTEEMHUIS) not in the 4.003 list"),
        _c("CUF3023", _W, "Text content inside an element ignored"),
        _c("CUF3024", _I, "Legacy sort-code attribute (SC1–SC6) read as a sort code"),
        _c("CUF3025", _I, "Sort codes written as attributes read as sort codes"),
        # 4xxx sort codes
        _c("CUF4001", _W, "Sort code used but its SORTERING is not declared in SORTEERCODES"),
        _c("CUF4002", _I, "SORTERING declared but never used"),
        _c("CUF4003", _W, "SORTERING declared more than once"),
        _c("CUF4004", _I, "Sort code value not in the declared code table"),
        # 5xxx totals
        _c("CUF5001", _W, "Bundle total differs from the computed total"),
        _c("CUF5002", _W, "Estimate total differs from the computed total"),
        _c("CUF5003", _I, "Stated totals are all zero although the lines have costs"),
        _c("CUF5004", _W, "Resource lines do not add up to their estimate line"),
        _c("CUF5005", _I, "Contract sum differs from direct costs plus tail items"),
        _c("CUF5006", _I, "Estimate line priced from its resource lines"),
        # 7xxx data quality & lenient parsing
        _c("CUF7001", _I, "Negative quantity or price"),
        _c("CUF7002", _W, "Non-ISO date accepted"),
        _c("CUF7003", _W, "Decimal comma accepted"),
        _c("CUF7005", _I, "Element estimate: bundles with DOORREKEN_HOEVEELHEID"),
        _c("CUF7006", _I, "Factor 0 interpreted as 1"),
    )
}


@dataclass(frozen=True, slots=True, kw_only=True)
class Finding:
    """One observation about a CUF file.

    Attributes:
        code: Stable code, e.g. ``"CUF5001"``; see :data:`CODES`.
        severity: Severity after overrides.
        message: Human-readable English message.
        line: 1-based line number of the element (``None`` if not applicable).
        column: 0-based column number.
        path: Element path, e.g. ``/CUF/BEGROTING/BUNDELING[2]/BEGROTINGSREGEL[1]@BTW``.
        value: The offending raw value, if any.
    """

    code: str
    severity: Severity
    message: str
    line: int | None = None
    column: int | None = None
    path: str | None = None
    value: str | None = None

    @property
    def title(self) -> str:
        """The generic title of the code (see :data:`CODES`)."""
        return CODES[self.code].title

    def __str__(self) -> str:
        where = (
            f"line {self.line}" + (f":{self.column}" if self.column is not None else "")
            if self.line is not None
            else "-"
        )
        val = f" [{self.value!r}]" if self.value is not None else ""
        return f"{where} {self.severity.name} {self.code} {self.message}{val}"

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable dictionary."""
        return {
            "code": self.code,
            "severity": self.severity.name,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "path": self.path,
            "value": self.value,
        }


@dataclass(slots=True)
class FindingCollector:
    """Collects findings with per-code and overall limits; counts what it suppresses.

    Args:
        max_per_code: Keep at most this many findings per code (``None`` = unlimited).
        max_total: Keep at most this many findings overall (``None`` = unlimited).
        overrides: Severity per code, replacing the default severity. Mapping a code to
            ``None`` silences it.
    """

    max_per_code: int | None = 100
    max_total: int | None = 10_000
    overrides: Mapping[str, Severity | None] = field(default_factory=dict)
    _items: list[Finding] = field(default_factory=list)
    _counts: Counter[str] = field(default_factory=Counter)
    _keys: set[tuple[object, ...]] = field(default_factory=set)

    def add(
        self,
        code: str,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        path: str | None = None,
        value: str | None = None,
        severity: Severity | None = None,
    ) -> None:
        """Record a finding (counted even when suppressed by a limit)."""
        info = CODES[code]
        key = (code, line, path, value, message)
        if key in self._keys:
            return
        if code in self.overrides:
            sev = self.overrides[code]
            if sev is None:
                return
        else:
            sev = severity or info.severity
        self._counts[code] += 1
        if self.max_per_code is not None and self._counts[code] > self.max_per_code:
            return
        if self.max_total is not None and len(self._items) >= self.max_total:
            return
        self._keys.add(key)
        if value is not None and len(value) > 200:
            value = value[:200] + "…"
        self._items.append(
            Finding(
                code=code,
                severity=sev,
                message=message,
                line=line,
                column=column,
                path=path,
                value=value,
            )
        )

    def extend(self, findings: Iterable[Finding]) -> None:
        """Add already-built findings (respecting limits and overrides)."""
        for f in findings:
            self.add(
                f.code,
                f.message,
                line=f.line,
                column=f.column,
                path=f.path,
                value=f.value,
                severity=f.severity if f.code not in self.overrides else None,
            )

    @property
    def counts(self) -> Mapping[str, int]:
        """Number of occurrences per code, including suppressed ones."""
        return dict(self._counts)

    @property
    def suppressed(self) -> int:
        """Number of findings dropped because of limits."""
        return sum(self._counts.values()) - len(self._items)

    def __iter__(self) -> Iterator[Finding]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def snapshot(self) -> tuple[Finding, ...]:
        """Return the findings collected so far."""
        return tuple(self._items)

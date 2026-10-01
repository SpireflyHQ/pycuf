"""Reading CUF files: :func:`read` and :class:`CufFile`."""

from __future__ import annotations

import datetime as dt
import os
from collections.abc import Iterable, Iterator, Mapping
from typing import TYPE_CHECKING, Any, Literal, get_args

from . import _xml
from ._build import build
from ._encoding import (
    REPAIRS,
    EncodingInfo,
    check_encoding_name,
    prepare,
    repair_bytes,
    sniff_encoding,
)
from ._source import DEFAULT_MAX_SIZE, SourceLike, read_source
from .calc import Totals, compute
from .errors import NotCufError
from .findings import CODES, Finding, FindingCollector, Severity
from .models import (
    Bundle,
    Estimate,
    Line,
    Project,
    QuantityLine,
    ResourceLine,
    SortCodeScheme,
    Tail,
)
from .policy import DEFAULT, Policy, PresetName, resolve_policy
from .raw import RawElement

if TYPE_CHECKING:
    from .tables import Tables
    from .validate import ValidationReport

__all__ = ["CufFile", "Leniency", "read"]

Leniency = Literal["decimal-comma", "dmy-date"]
"""Deviations from CUF-XML that :func:`read` accepts (each acceptance is reported):
``"decimal-comma"`` reads ``12,5`` as 12.5 (``CUF7003``); ``"dmy-date"`` reads ``d-m-yyyy``
dates (``CUF7002``)."""
LENIENCIES: frozenset[str] = frozenset(get_args(Leniency))


class CufFile:
    """A CUF file that has been read: the typed model plus the findings of reading it.

    Use :func:`pycuf.read` to create one. The whole file is held in memory (CUF files are
    small). Nothing is computed when reading: :meth:`calculate` and :meth:`check` apply a
    :class:`~pycuf.Policy` afterwards, so the same file can be evaluated under several policies.

    Attributes:
        name: Path of the file, or ``<bytes>`` / ``<stream>``.
        created: ``AANMAAKDATUMTIJD``, when the CUF file was written.
        project: Project data (``PROJECTGEGEVENS``); empty when the element is missing.
        sort_code_schemes: Declared sort-code schemes (``SORTEERCODES``), in file order.
        estimate: The estimate tree (``BEGROTING``); empty when the element is missing.
        tail: The tail (``STAARTGEGEVENS``), ``None`` when the element is missing.
        encoding: How the bytes were decoded.
        namespace: The default namespace as written (``x-schema:CufSchema.xml`` …), if any.
        namespaces: All namespace declarations of the root element (prefix → URI).
        raw: The root :class:`~pycuf.raw.RawElement`: the file exactly as written.
        bundles: All bundles in document order (``bundles[b.seq] is b``).
        lines: All estimate lines in document order (``lines[ln.seq] is ln``).
        resource_lines: All resource (MAMO) lines in document order.
        quantity_lines: All quantity take-off lines in document order.
    """

    def __init__(
        self,
        *,
        name: str,
        root: RawElement,
        encoding: EncodingInfo,
        namespaces: Mapping[str, str],
        findings: FindingCollector,
        policy: Policy,
        lenient: frozenset[str],
    ) -> None:
        built = build(
            root,
            findings,
            decimal_comma="decimal-comma" in lenient,
            dutch_dates="dmy-date" in lenient,
        )
        self.name: str = name
        self.raw: RawElement = root
        self.encoding: EncodingInfo = encoding
        self.namespaces: Mapping[str, str] = dict(namespaces)
        self.namespace: str | None = namespaces.get("")
        self.created: dt.datetime | None = built.created
        self.project: Project = built.project
        self.sort_code_schemes: tuple[SortCodeScheme, ...] = built.sort_code_schemes
        self.estimate: Estimate = built.estimate
        self.tail: Tail | None = built.tail
        self.bundles: tuple[Bundle, ...] = tuple(built.bundles)
        self.lines: tuple[Line, ...] = tuple(built.lines)
        self.resource_lines: tuple[ResourceLine, ...] = tuple(built.resource_lines)
        self.quantity_lines: tuple[QuantityLine, ...] = tuple(built.quantity_lines)
        self.policy: Policy = policy
        """The default policy for :meth:`totals` and :meth:`validate` (from :func:`read`)."""
        self._parents: dict[Any, Any] = built.parents
        self._collector = findings
        self._totals: dict[Policy, Totals] = {}

    # ------------------------------------------------------------------ findings
    @property
    def findings(self) -> tuple[Finding, ...]:
        """Findings of reading the file: encoding, XML, structure, values and sort codes.

        Totals are not checked when reading; see :meth:`check` and :func:`pycuf.validate`.
        """
        return self._collector.snapshot()

    # ---------------------------------------------------------------- navigation
    def parent(self, node: Bundle | Line | ResourceLine) -> Bundle | Line | None:
        """The bundle (or, for a resource line, the estimate line) that contains ``node``.

        ``None`` for nodes directly under the estimate.
        """
        try:
            return self._parents[node]  # type: ignore[no-any-return]
        except KeyError:
            raise ValueError("node does not belong to this file") from None

    def ancestors(self, node: Bundle | Line | ResourceLine) -> tuple[Bundle, ...]:
        """The enclosing bundles of ``node``, outermost first."""
        chain: list[Bundle] = []
        current = self.parent(node)
        while current is not None:
            if isinstance(current, Bundle):
                chain.append(current)
            current = self.parent(current)
        return tuple(reversed(chain))

    def walk(self) -> Iterator[Bundle | Line]:
        """Yield every bundle and estimate line in document order (depth first)."""

        def visit(children: Iterable[Bundle | Line]) -> Iterator[Bundle | Line]:
            for child in children:
                yield child
                if isinstance(child, Bundle):
                    yield from visit(child.children)

        return visit(self.estimate.children)

    def scheme(self, name: str) -> SortCodeScheme | None:
        """The declared sort-code scheme called ``name`` (``SORTERING``), if any."""
        return next((s for s in self.sort_code_schemes if s.name == name), None)

    def sort_codes(
        self, node: Bundle | Line | ResourceLine, *, inherited: bool = True
    ) -> dict[str, str | None]:
        """Sort codes of ``node`` by scheme name.

        CUF-XML says that a sort code on a bundle or line applies to everything beneath it,
        unless a lower node has its own code for the same scheme. With ``inherited=True`` (the
        default) the result contains those effective codes; otherwise only the node's own.
        """
        chain: list[Any] = [node]
        if inherited:
            current = self.parent(node)
            while current is not None:
                chain.append(current)
                current = self.parent(current)
        result: dict[str, str | None] = {}
        for owner in chain:  # nearest first: a lower node overrides its ancestors
            for code in owner.sort_codes:
                if code.scheme is not None and code.scheme not in result:
                    result[code.scheme] = code.value
        return result

    # ---------------------------------------------------------------- computing
    def totals(self, *, policy: Policy | PresetName | None = None) -> Totals:
        """Compute the costs of every node under ``policy`` (default: :attr:`policy`).

        Results are cached per policy. See :class:`~pycuf.calc.Totals` and
        :mod:`pycuf.policy`.
        """
        resolved = resolve_policy(policy, self.policy)
        totals = self._totals.get(resolved)
        if totals is None:
            totals = self._totals[resolved] = compute(self, resolved)
        return totals

    def validate(
        self,
        *,
        policy: Policy | PresetName | None = None,
        severity_overrides: Mapping[str, Severity | None] | None = None,
    ) -> ValidationReport:
        """Check the file: the findings of reading it plus stated totals against computed ones.

        Args:
            policy: The policy for computing (default: :attr:`policy`).
            severity_overrides: Change the severity of finding codes, or silence them with
                ``None`` (applied on top of those given to :func:`read`).
        """
        from .validate import validate_file  # noqa: PLC0415

        return validate_file(self, policy=policy, severity_overrides=severity_overrides)

    # ------------------------------------------------------------------ tables
    @property
    def tables(self) -> Tables:
        """Normalized tables of this file (see :mod:`pycuf.tables`)."""
        from .tables import Tables  # noqa: PLC0415

        return Tables(self)

    def export(
        self,
        directory: str | os.PathLike[str],
        *,
        policy: Policy | PresetName | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Write the normalized tables to ``directory``; see :meth:`Tables.export`.

        ``policy`` selects the policy of the computed columns (default: :attr:`policy`).
        """
        from .tables import Tables  # noqa: PLC0415

        return Tables(self, policy).export(directory, **kwargs)

    def to_polars(
        self,
        tables: Iterable[str] | None = None,
        *,
        policy: Policy | PresetName | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Polars DataFrames by table name; see :meth:`Tables.to_polars`."""
        from .tables import Tables  # noqa: PLC0415

        return Tables(self, policy).to_polars(tables, **kwargs)

    def to_pandas(
        self,
        tables: Iterable[str] | None = None,
        *,
        policy: Policy | PresetName | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Pandas DataFrames by table name; see :meth:`Tables.to_pandas`."""
        from .tables import Tables  # noqa: PLC0415

        return Tables(self, policy).to_pandas(tables, **kwargs)

    def __repr__(self) -> str:
        return (
            f"<CufFile {self.name!r} version={self.project.cuf_version!r} "
            f"bundles={len(self.bundles)} lines={len(self.lines)}>"
        )


def read(
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
) -> CufFile:
    """Read a CUF-XML file.

    The file is read completely and checked on the way; data problems never raise but become
    :attr:`CufFile.findings`. Nothing is computed yet: call :meth:`CufFile.totals` or
    :meth:`CufFile.validate`.

    Args:
        source: Path, bytes or binary file object.
        policy: The file's default calculation policy, a :class:`~pycuf.policy.Policy` or a
            preset name (``"usage-rules"``, ``"schema"``, ``"erp"``).
        lenient: Deviations to accept, each reported as a finding: ``"decimal-comma"``
            (``12,5``) and ``"dmy-date"`` (``d-m-yyyy``). Pass ``()`` for strict parsing; values
            that cannot be read are then reported as invalid.
        encoding: Override the declared encoding (e.g. ``"cp1252"`` for a file that has none).
        repair: Opt-in fix-ups of malformed XML, each reported as a finding:
            ``"control-chars"`` (remove XML-illegal control characters) and ``"bare-ampersand"``
            (escape ``&`` that starts no entity, as in ``Bakker & Spees``).
        severity_overrides: Change the severity of finding codes, or silence them with ``None``.
        max_findings_per_code: Keep at most this many findings per code.
        max_findings: Keep at most this many findings in total.
        max_size: Refuse inputs larger than this many bytes (``None`` = no limit).
        max_depth: Maximum XML nesting depth.
        max_attribute_size: Maximum length of one attribute value.

    Returns:
        A :class:`CufFile`.

    Raises:
        NotCufError: The input is not CUF-XML (another XML format, or not XML at all).
        XmlSyntaxError: The XML is not well-formed.
        ForbiddenConstructError: The XML contains a DOCTYPE or ENTITY declaration.
        LimitExceededError: A safety limit was exceeded.
        ValueError: An option has an invalid value.
    """
    resolved = resolve_policy(policy)
    lenient_set = frozenset(lenient)
    if unknown := lenient_set - LENIENCIES:
        raise ValueError(
            f"unknown lenient option(s) {sorted(unknown)}; choose from {sorted(LENIENCIES)}"
        )
    repairs = frozenset(repair)
    if unknown_repairs := repairs - REPAIRS:
        raise ValueError(
            f"unknown repair(s) {sorted(unknown_repairs)}; choose from {sorted(REPAIRS)}"
        )
    if encoding is not None:
        check_encoding_name(encoding)
    findings = FindingCollector(
        max_per_code=max_findings_per_code,
        max_total=max_findings,
        overrides=check_overrides(severity_overrides),
    )
    src = read_source(source, max_size=max_size)
    data = src.data
    _check_xml_like(src.name, data)
    info = sniff_encoding(data[:4096], encoding)
    if info.bom is not None:
        findings.add("CUF1001", f"byte-order mark ({info.bom})")
    if not info.has_declaration:
        findings.add("CUF1002", "no XML declaration; the encoding is assumed to be UTF-8")
    if encoding is not None:
        findings.add("CUF1004", f"encoding overridden: read as {info.effective}", value=encoding)
    if repairs:
        data = repair_bytes(data, repairs, findings)
    data, expat_encoding = prepare(data, info, findings)
    parsed = _xml.parse_xml(
        data,
        encoding=expat_encoding,
        findings=findings,
        max_depth=max_depth,
        max_attribute_size=max_attribute_size,
    )
    root = parsed.root
    if root.tag != "CUF":
        hint = ""
        if root.tag == "Calculatie":
            hint = " (this looks like Open Calc Studio's own format, which is not CUF-XML)"
        raise NotCufError(f"{src.name}: root element is <{root.name}>, not <CUF>{hint}")
    return CufFile(
        name=src.name,
        root=root,
        encoding=info,
        namespaces=parsed.namespaces,
        findings=findings,
        policy=resolved,
        lenient=lenient_set,
    )


def check_overrides(
    overrides: Mapping[str, Severity | None] | None,
) -> dict[str, Severity | None]:
    """Validate ``severity_overrides``: known codes, ``Severity`` or ``None`` values."""
    result = dict(overrides or {})
    for code, severity in result.items():
        if code not in CODES:
            raise ValueError(f"unknown finding code {code!r} in severity_overrides")
        if severity is not None and not isinstance(severity, Severity):
            raise TypeError(
                f"severity_overrides[{code!r}] must be a Severity or None, not {severity!r}"
            )
    return result


def _check_xml_like(name: str, data: bytes) -> None:
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
    if not head:
        raise NotCufError(f"{name}: the input is empty")
    if head[:1] != b"<" and not head.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00<", b"<\x00")):
        raise NotCufError(
            f"{name}: not XML. CUF-XML files start with '<'; the pre-XML CUF 3.000 and older "
            "formats are not supported"
        )

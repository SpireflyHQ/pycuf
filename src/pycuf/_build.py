"""Build the typed model from raw elements, checking structure and values on the way.

Structure and value problems become findings; nothing is refused. Problems that exporters make
systematically (an empty required ``BTW`` on every line, a vendor attribute on every element) are
reported once per element and attribute, with a count and the first location.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .findings import FindingCollector
from .models import (
    COST_FIELDS,
    Bundle,
    CostType,
    Estimate,
    Line,
    Project,
    QuantityLine,
    ResourceLine,
    SortCode,
    SortCodeEntry,
    SortCodeScheme,
    StatedTotals,
    Tail,
    TailItem,
)
from .raw import RawElement
from .spec import (
    ELEMENTS,
    SUPPORTED_VERSIONS,
    VERSION,
    AttributeSpec,
    ElementSpec,
)
from .values import (
    MAX_DECIMALS,
    NUMBER_MAX,
    NUMBER_MIN,
    is_number,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_number,
)

__all__ = ["Built", "build"]

_LEGACY_SORT = re.compile(r"SC[1-6]")
_LEGACY_SORT_OWNERS = frozenset({"BUNDELING", "BEGROTINGSREGEL", "MAMO_REGEL"})
_RANGE = f"0 or ±{NUMBER_MIN} to ±{NUMBER_MAX}, at most {MAX_DECIMALS:,} decimals"


@dataclass(slots=True)
class Built:
    """Everything the builder produces."""

    created: dt.datetime | None
    project: Project
    sort_code_schemes: tuple[SortCodeScheme, ...]
    estimate: Estimate
    tail: Tail | None
    bundles: list[Bundle] = field(default_factory=list)
    lines: list[Line] = field(default_factory=list)
    resource_lines: list[ResourceLine] = field(default_factory=list)
    quantity_lines: list[QuantityLine] = field(default_factory=list)
    parents: dict[Any, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _Tally:
    count: int = 0
    line: int | None = None
    column: int | None = None
    path: str | None = None
    value: str | None = None


class _Builder:
    def __init__(
        self, findings: FindingCollector, *, decimal_comma: bool, dutch_dates: bool
    ) -> None:
        self.findings = findings
        self.decimal_comma = decimal_comma
        self.dutch_dates = dutch_dates
        self.tallies: dict[tuple[str, str, str], _Tally] = {}
        self.bundles: list[Bundle] = []
        self.lines: list[Line] = []
        self.resource_lines: list[ResourceLine] = []
        self.quantity_lines: list[QuantityLine] = []
        self.parents: dict[Any, Any] = {}

    # ------------------------------------------------------------ findings helpers
    def tally(self, code: str, el: RawElement, attribute: str, value: str | None = None) -> None:
        """Count an aggregated finding (reported in :meth:`flush`)."""
        key = (code, el.tag, attribute)
        t = self.tallies.get(key)
        if t is None:
            self.tallies[key] = _Tally(1, el.line, el.column, f"{el.path}@{attribute}", value)
        else:
            t.count += 1

    def flush(self) -> None:
        messages = {
            "CUF3012": "{el} has attribute {attr}, which CUF-XML 4.003 does not define",
            "CUF3016": "{el} lacks the required attribute {attr}",
            "CUF3017": "{el} has an empty value for the required attribute {attr}",
            "CUF3024": "{el} uses the legacy attribute {attr}; read as a sort code of that scheme",
            "CUF3025": "{el} carries its sort codes as attributes ({attr}); read as one sort code "
            "per attribute",
            "CUF7003": "{el}@{attr} uses a decimal comma",
        }
        for (code, tag, attr), t in self.tallies.items():
            msg = messages[code].format(el=tag, attr=attr)
            if t.count > 1:
                msg += f" ({t.count:,} times; first at line {t.line})"
            self.findings.add(code, msg, line=t.line, column=t.column, path=t.path, value=t.value)

    # ------------------------------------------------------------- structure checks
    def check_element(self, el: RawElement) -> ElementSpec | None:
        """Check attributes and children of ``el`` against the catalogue."""
        spec = ELEMENTS.get(el.tag)
        if spec is None:
            return None
        for name, value in el.attributes.items():
            if name in spec.attributes:
                continue
            if el.tag in _LEGACY_SORT_OWNERS and _LEGACY_SORT.fullmatch(name):
                self.tally("CUF3024", el, name)
                continue
            self.tally("CUF3012", el, name, value)
        for attr in spec.attributes.values():
            if not attr.required:
                continue
            written = el.attributes.get(attr.name)
            if written is None:
                self.tally("CUF3016", el, attr.name)
            elif not written.strip():
                self.tally("CUF3017", el, attr.name)
        if el.text is not None:
            self.findings.add(
                "CUF3023",
                f"{el.tag} contains text, which CUF-XML does not use; ignored",
                line=el.line,
                column=el.column,
                path=el.path,
                value=el.text,
            )
        self.check_children(el, spec)
        return spec

    def check_children(self, el: RawElement, spec: ElementSpec) -> None:
        counts: dict[str, int] = {}
        order = list(spec.children)
        last_rank = -1
        for child in el.children:
            if child.tag not in ELEMENTS:
                self.findings.add(
                    "CUF3011",
                    f"element {child.name} is not defined in CUF-XML 4.003; kept in raw only",
                    line=child.line,
                    column=child.column,
                    path=child.path,
                )
                continue
            if child.tag not in spec.children:
                self.findings.add(
                    "CUF3013",
                    f"{child.tag} is not allowed inside {el.tag}; ignored",
                    line=child.line,
                    column=child.column,
                    path=child.path,
                )
                continue
            counts[child.tag] = counts.get(child.tag, 0) + 1
            limit = spec.children[child.tag][1]
            if limit is not None and counts[child.tag] == limit + 1:
                self.findings.add(
                    "CUF3014",
                    f"{child.tag} occurs more than {limit} time(s) in {el.tag}; "
                    "only the first is used",
                    line=child.line,
                    column=child.column,
                    path=child.path,
                )
            if spec.ordered:
                rank = order.index(child.tag)
                if rank < last_rank:
                    self.findings.add(
                        "CUF3015",
                        f"{child.tag} comes after {order[last_rank]} in {el.tag}; expected order "
                        f"is {', '.join(order)}",
                        line=child.line,
                        column=child.column,
                        path=child.path,
                    )
                last_rank = max(last_rank, rank)
        for tag, (minimum, _) in spec.children.items():
            if counts.get(tag, 0) < minimum:
                self.findings.add(
                    "CUF3010",
                    f"{el.tag} lacks the required element {tag}",
                    line=el.line,
                    column=el.column,
                    path=el.path,
                )

    # ---------------------------------------------------------------- value parsing
    def values(self, el: RawElement, spec: ElementSpec) -> dict[str, Any]:
        """Parse every known attribute of ``el``; return model field → value."""
        out: dict[str, Any] = {}
        for attr in spec.attributes.values():
            raw = el.attributes.get(attr.name)
            out[attr.field] = None if raw is None else self.value(el, attr, raw)
        return out

    def value(self, el: RawElement, attr: AttributeSpec, raw: str) -> Any:
        if not raw.strip():
            return None
        kind = attr.type

        def report(code: str, message: str) -> None:
            self.findings.add(
                code,
                f"{el.tag}@{attr.name} {message}",
                line=el.line,
                column=el.column,
                path=f"{el.path}@{attr.name}",
                value=raw,
            )

        if kind == "string":
            return raw
        if kind == "number":
            number, comma = parse_number(raw, decimal_comma=self.decimal_comma)
            if number is None and is_number(raw, decimal_comma=self.decimal_comma):
                report("CUF3018", f"is outside the supported range ({_RANGE})")
            elif number is None:
                report("CUF3018", "is not a valid number")
            elif comma:
                self.tally("CUF7003", el, attr.name, raw)
            return number
        if kind == "date":
            day, lenient = parse_date(raw, dutch=self.dutch_dates)
            if day is None:
                report("CUF3019", "is not a valid date (expected YYYY-MM-DD)")
            elif lenient:
                report("CUF7002", f"is not in ISO 8601 format; read as {day.isoformat()}")
            return day
        if kind == "datetime":
            moment, lenient = parse_datetime(raw, dutch=self.dutch_dates)
            if moment is None:
                report("CUF3019", "is not a valid date-time (expected YYYY-MM-DDThh:mm:ss)")
            elif lenient:
                report("CUF7002", f"is not in ISO 8601 format; read as {moment.isoformat()}")
            return moment
        if kind == "boolean":
            flag = parse_bool(raw)
            if flag is None:
                report("CUF3020", "is not a valid boolean (0 or 1)")
            return flag
        # enum
        text = raw.strip()
        assert attr.values is not None
        if text in attr.values:
            return text
        if attr.name == "SYSTEEMHUIS":
            self.findings.add(
                "CUF3022",
                f"software house {text!r} is not in the 4.003 list",
                line=el.line,
                column=el.column,
                path=f"{el.path}@{attr.name}",
                value=raw,
            )
        elif attr.name != "CUF_VERSIE":  # the version is reported with the version findings
            report("CUF3021", f"value {text!r} is not allowed")
        return text

    def sort_codes(self, el: RawElement) -> tuple[SortCode, ...]:
        codes: list[SortCode] = []
        for c in el.children:
            if c.tag != "SORTEERCODE":
                continue
            if "SORTERING" not in c.attributes and set(c.attributes) - {"WAARDE"}:
                # Bakker & Spees writes <SORTEERCODE ACTI="17" NACA="1"/>: one code per attribute
                self.tally("CUF3025", c, "+".join(sorted(c.attributes)))
                codes.extend(
                    SortCode(scheme=name, value=value, raw=c)
                    for name, value in c.attributes.items()
                    if name != "WAARDE"
                )
                continue
            if self.check_element(c) is not None:
                codes.append(SortCode(scheme=c.get("SORTERING"), value=c.get("WAARDE"), raw=c))
        if el.tag in _LEGACY_SORT_OWNERS:
            codes.extend(
                SortCode(scheme=name, value=value, raw=None)
                for name, value in el.attributes.items()
                if _LEGACY_SORT.fullmatch(name)
            )
        return tuple(codes)

    def quantity_lines_of(self, el: RawElement) -> tuple[QuantityLine, ...]:
        out = []
        for c in el.children:
            if c.tag != "HOEVEELHEDENSTAAT_REGEL":
                continue
            spec = self.check_element(c)
            assert spec is not None
            q = QuantityLine(seq=len(self.quantity_lines), raw=c, **self.values(c, spec))
            self.quantity_lines.append(q)
            out.append(q)
        return tuple(out)

    # ------------------------------------------------------------------- the tree
    def resource(self, el: RawElement, line_seq: int) -> ResourceLine:
        spec = self.check_element(el)
        assert spec is not None
        values = self.values(el, spec)
        code = values.pop("cost_type")
        cost_type = CostType(code) if code in CostType._value2member_map_ else None
        r = ResourceLine(
            seq=len(self.resource_lines),
            line_seq=line_seq,
            cost_type=cost_type,
            cost_type_code=el.get("KOSTENSOORT"),
            quantity_lines=self.quantity_lines_of(el),
            sort_codes=self.sort_codes(el),
            raw=el,
            **values,
        )
        self.resource_lines.append(r)
        return r

    def line(self, el: RawElement, bundle_seq: int | None, depth: int) -> Line:
        spec = self.check_element(el)
        assert spec is not None
        seq = len(self.lines)
        self.lines.append(None)  # type: ignore[arg-type]  # reserve the seq
        resources = tuple(self.resource(c, seq) for c in el.children if c.tag == "MAMO_REGEL")
        line = Line(
            seq=seq,
            bundle_seq=bundle_seq,
            depth=depth,
            resources=resources,
            quantity_lines=self.quantity_lines_of(el),
            sort_codes=self.sort_codes(el),
            raw=el,
            **self.values(el, spec),
        )
        self.lines[seq] = line
        for r in resources:
            self.parents[r] = line
        return line

    def bundle(self, el: RawElement, parent_seq: int | None, depth: int) -> Bundle:
        spec = self.check_element(el)
        assert spec is not None
        seq = len(self.bundles)
        self.bundles.append(None)  # type: ignore[arg-type]  # reserve the seq (pre-order)
        values = self.values(el, spec)
        stated = StatedTotals(**{name: values.pop(name) for name in COST_FIELDS})
        children: list[Bundle | Line] = []
        for c in el.children:
            if c.tag == "BUNDELING":
                children.append(self.bundle(c, seq, depth + 1))
            elif c.tag == "BEGROTINGSREGEL":
                children.append(self.line(c, seq, depth))
        b = Bundle(
            seq=seq,
            parent_seq=parent_seq,
            depth=depth,
            stated=stated,
            children=tuple(children),
            quantity_lines=self.quantity_lines_of(el),
            sort_codes=self.sort_codes(el),
            raw=el,
            **values,
        )
        self.bundles[seq] = b
        for child in children:
            self.parents[child] = b
        return b

    def estimate(self, el: RawElement | None) -> Estimate:
        if el is None:
            return Estimate()
        spec = self.check_element(el)
        assert spec is not None
        values = self.values(el, spec)
        stated = StatedTotals(**{name: values[name] for name in COST_FIELDS})
        children: list[Bundle | Line] = []
        for c in el.children:
            if c.tag == "BUNDELING":
                children.append(self.bundle(c, None, 1))
            elif c.tag == "BEGROTINGSREGEL":
                children.append(self.line(c, None, 0))
        for child in children:
            self.parents[child] = None
        return Estimate(stated=stated, children=tuple(children), raw=el)

    def project(self, el: RawElement | None) -> Project:
        if el is None:
            return Project()
        spec = self.check_element(el)
        assert spec is not None
        return Project(raw=el, **self.values(el, spec))

    def scheme(self, el: RawElement) -> SortCodeScheme:
        spec = self.check_element(el)
        assert spec is not None
        entries = []
        for c in el.children:
            if c.tag != "SORTEERCODE_REGEL":
                continue
            entry_spec = self.check_element(c)
            assert entry_spec is not None
            entries.append(SortCodeEntry(raw=c, **self.values(c, entry_spec)))
        values = self.values(el, spec)
        return SortCodeScheme(raw=el, entries=tuple(entries), **values)

    def tail(self, el: RawElement | None) -> Tail | None:
        if el is None:
            return None
        spec = self.check_element(el)
        assert spec is not None
        items = []
        for c in el.children:
            if c.tag != "VRIJE_GROOTHEID":
                continue
            item_spec = self.check_element(c)
            assert item_spec is not None
            items.append(TailItem(raw=c, **self.values(c, item_spec)))
        return Tail(raw=el, items=tuple(items), **self.values(el, spec))


def _first(children: Sequence[RawElement], tag: str) -> RawElement | None:
    return next((c for c in children if c.tag == tag), None)


def build(
    root: RawElement,
    findings: FindingCollector,
    *,
    decimal_comma: bool = False,
    dutch_dates: bool = False,
) -> Built:
    """Build the model of a CUF document whose root element is ``root`` (already checked)."""
    b = _Builder(findings, decimal_comma=decimal_comma, dutch_dates=dutch_dates)
    root_spec = b.check_element(root)
    assert root_spec is not None
    created = b.values(root, root_spec)["created"]
    project = b.project(_first(root.children, "PROJECTGEGEVENS"))
    schemes = tuple(b.scheme(c) for c in root.children if c.tag == "SORTEERCODES")
    estimate = b.estimate(_first(root.children, "BEGROTING"))
    tail = b.tail(_first(root.children, "STAARTGEGEVENS"))
    _check_version(project, findings)
    _check_sort_codes(schemes, b, findings)
    b.flush()
    return Built(
        created=created,
        project=project,
        sort_code_schemes=schemes,
        estimate=estimate,
        tail=tail,
        bundles=b.bundles,
        lines=b.lines,
        resource_lines=b.resource_lines,
        quantity_lines=b.quantity_lines,
        parents=b.parents,
    )


def _check_version(project: Project, findings: FindingCollector) -> None:
    version = project.cuf_version
    raw = project.raw
    where: Mapping[str, Any] = (
        {"line": raw.line, "column": raw.column, "path": f"{raw.path}@CUF_VERSIE"} if raw else {}
    )
    if version is None:
        return  # missing/empty: reported as CUF3016/CUF3017
    findings.add("CUF3001", f"CUF_VERSIE is {version}", value=version, **where)
    if version != VERSION:
        known = "an older 4.x version" if version in SUPPORTED_VERSIONS else "not a known version"
        findings.add(
            "CUF3002",
            f"CUF_VERSIE {version} is {known}; read as {VERSION}",
            value=version,
            **where,
        )


def _check_sort_codes(
    schemes: tuple[SortCodeScheme, ...], b: _Builder, findings: FindingCollector
) -> None:
    declared: dict[str, SortCodeScheme] = {}
    for s in schemes:
        if s.name is None:
            continue
        if s.name in declared:
            findings.add(
                "CUF4003",
                f"SORTERING {s.name!r} is declared more than once",
                line=s.raw.line if s.raw else None,
                path=s.raw.path if s.raw else None,
                value=s.name,
            )
        else:
            declared[s.name] = s
    used: dict[str, SortCode] = {}
    values: dict[str, set[str]] = {}
    owners: list[Sequence[SortCode]] = [x.sort_codes for x in b.bundles]
    owners += [x.sort_codes for x in b.lines]
    owners += [x.sort_codes for x in b.resource_lines]
    for codes in owners:
        for c in codes:
            if c.scheme is None:
                continue
            used.setdefault(c.scheme, c)
            if c.value is not None:
                values.setdefault(c.scheme, set()).add(c.value)
    for name, first in used.items():
        if name not in declared and not _LEGACY_SORT.fullmatch(name):
            findings.add(
                "CUF4001",
                f"sort codes of scheme {name!r} are used but the scheme is not declared",
                line=first.raw.line if first.raw else None,
                path=first.raw.path if first.raw else None,
                value=name,
            )
    for name, s in declared.items():
        if name not in used:
            findings.add(
                "CUF4002",
                f"SORTERING {name!r} is declared but no node uses it",
                line=s.raw.line if s.raw else None,
                path=s.raw.path if s.raw else None,
                value=name,
            )
        elif s.entries:
            table = {e.code for e in s.entries if e.code is not None}
            for value in sorted(values.get(name, set()) - table):
                findings.add(
                    "CUF4004",
                    f"sort code {value!r} of scheme {name!r} is not in the declared code table",
                    line=s.raw.line if s.raw else None,
                    path=s.raw.path if s.raw else None,
                    value=value,
                )

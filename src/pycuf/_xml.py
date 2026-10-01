"""Hardened XML parsing on top of the standard library's ``pyexpat``.

Security properties (see docs/security.md):

- DOCTYPE, ENTITY, notation and external-entity declarations raise
  :class:`~pycuf.errors.ForbiddenConstructError`. CUF-XML never uses a DTD, so this blocks
  entity-expansion and external-entity attacks before any expansion happens. Expat itself never
  opens files or network connections, and parameter-entity parsing is disabled.
- Element depth and attribute-value size are limited.
- No "recover" mode: malformed XML raises :class:`~pycuf.errors.XmlSyntaxError` with a position.

Namespace processing is deliberately off. Real files declare default namespaces such as
``x-schema:Forum CUF-XML-schema4003.xsd`` that are not valid URIs (libxml2 refuses them), and the
namespace carries no meaning in CUF-XML; elements are matched by local name. ``xmlns``
declarations are recorded separately and removed from the attributes.
"""

from __future__ import annotations

import pyexpat
from dataclasses import dataclass, field
from typing import Final

from .errors import ForbiddenConstructError, LimitExceededError, XmlSyntaxError
from .findings import FindingCollector
from .raw import RawElement

__all__ = ["DEFAULT_MAX_ATTRIBUTE_SIZE", "DEFAULT_MAX_DEPTH", "ParsedXml", "parse_xml"]

DEFAULT_MAX_DEPTH: Final = 64
"""Default maximum element nesting depth (AFAS documents imports up to 15 bundle levels)."""
DEFAULT_MAX_ATTRIBUTE_SIZE: Final = 1024 * 1024
"""Default maximum length of one attribute value (1 Mi characters)."""


@dataclass(slots=True)
class ParsedXml:
    """The root element plus document-level facts."""

    root: RawElement
    namespaces: dict[str, str] = field(default_factory=dict)
    """``xmlns`` declarations of the root element: prefix (``""`` = default) → URI as written."""


def parse_xml(
    data: bytes,
    *,
    encoding: str | None,
    findings: FindingCollector,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_attribute_size: int = DEFAULT_MAX_ATTRIBUTE_SIZE,
) -> ParsedXml:
    """Parse ``data`` into a tree of :class:`RawElement`.

    Args:
        data: The document bytes.
        encoding: Encoding Expat must use instead of the declared one (``None`` = as declared).
        findings: Collector for non-fatal problems (data after the document).
        max_depth: Maximum element nesting depth.
        max_attribute_size: Maximum length of one attribute value.
    """
    parser = pyexpat.ParserCreate(encoding)
    parser.ordered_attributes = True
    parser.buffer_text = True
    parser.SetParamEntityParsing(pyexpat.XML_PARAM_ENTITY_PARSING_NEVER)

    stack: list[_Frame] = []
    namespaces: dict[str, str] = {}
    result: list[RawElement] = []

    def forbidden(*_: object) -> None:
        raise ForbiddenConstructError(
            "DOCTYPE/ENTITY declarations are not allowed in CUF-XML (refused for security)",
            line=parser.CurrentLineNumber,
            column=parser.CurrentColumnNumber,
        )

    def start(name: str, attrs: list[str]) -> None:
        if len(stack) >= max_depth:
            raise LimitExceededError(
                f"element nesting deeper than {max_depth} at line {parser.CurrentLineNumber}"
            )
        attributes: dict[str, str] = {}
        for i in range(0, len(attrs), 2):
            key, value = attrs[i], attrs[i + 1]
            if len(value) > max_attribute_size:
                raise LimitExceededError(
                    f"attribute {key!r} longer than {max_attribute_size:,} characters "
                    f"(line {parser.CurrentLineNumber})"
                )
            if key == "xmlns" or key.startswith("xmlns:"):
                if not stack:
                    namespaces[key[6:]] = value
                continue
            attributes[key] = value
        local = name[name.find(":") + 1 :]
        if stack:
            parent = stack[-1]
            index = parent.counter.get(local, 0) + 1
            parent.counter[local] = index
            path = f"{parent.path}/{local}[{index}]"
        else:
            path = f"/{local}"
        stack.append(
            _Frame(name, attributes, path, parser.CurrentLineNumber, parser.CurrentColumnNumber)
        )

    def chars(data: str) -> None:
        if stack and data.strip():
            stack[-1].text.append(data)

    def end(_name: str) -> None:
        f = stack.pop()
        element = RawElement(
            f.name,
            f.attributes,
            f.children,
            f.line,
            f.column,
            f.path,
            "".join(f.text).strip() or None,
        )
        if stack:
            stack[-1].children.append(element)
        else:
            result.append(element)

    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.UnparsedEntityDeclHandler = forbidden
    parser.NotationDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden  # type: ignore[assignment]
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars

    try:
        parser.Parse(data, True)
    except pyexpat.ExpatError as exc:
        if not result:
            raise _error(exc) from None
        findings.add(
            "CUF1013",
            f"ignored data after the end of the document ({pyexpat.ErrorString(exc.code)})",
            line=exc.lineno,
            column=exc.offset,
        )
    if not result:
        raise XmlSyntaxError("no root element found", line=1, column=0)
    return ParsedXml(result[0], namespaces)


class _Frame:
    """An open element while parsing."""

    __slots__ = ("attributes", "children", "column", "counter", "line", "name", "path", "text")

    def __init__(
        self, name: str, attributes: dict[str, str], path: str, line: int, column: int
    ) -> None:
        self.name = name
        self.attributes = attributes
        self.path = path
        self.line = line
        self.column = column
        self.children: list[RawElement] = []
        self.text: list[str] = []
        self.counter: dict[str, int] = {}


def _error(exc: pyexpat.ExpatError) -> XmlSyntaxError:
    msg = pyexpat.ErrorString(exc.code)
    codes = pyexpat.errors.codes
    hint = ""
    if exc.code == codes[pyexpat.errors.XML_ERROR_INVALID_TOKEN]:
        hint = (
            " (an XML-illegal control character, a bare '&' or a wrong encoding is the usual "
            "cause; see the encoding= and repair= options of pycuf.read)"
        )
    elif exc.code == codes[pyexpat.errors.XML_ERROR_UNDEFINED_ENTITY]:
        hint = " (unescaped '&'? see repair={'bare-ampersand'})"
    elif exc.code == codes[pyexpat.errors.XML_ERROR_NO_ELEMENTS]:
        hint = " (empty or truncated file?)"
    elif exc.code in (
        codes[pyexpat.errors.XML_ERROR_UNCLOSED_TOKEN],
        codes[pyexpat.errors.XML_ERROR_TAG_MISMATCH],
    ):
        hint = " (truncated file?)"
    return XmlSyntaxError(
        f"XML not well-formed: {msg} at line {exc.lineno}, column {exc.offset}{hint}",
        line=exc.lineno,
        column=exc.offset,
    )

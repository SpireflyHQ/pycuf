"""Lossless raw elements: exactly what the file contains.

The raw layer keeps every element and attribute as written, including elements and attributes
that CUF-XML 4.003 does not define (vendor extensions such as ``Ibis:AANDUIDING`` or Bakker &
Spees' ``WERKBESCHRIJVING``). The typed model (:mod:`pycuf.models`) is built from it, and every
model object keeps a reference to its :class:`RawElement` in ``raw``.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from typing import ClassVar

__all__ = ["RawElement"]


class RawElement:
    """One XML element with its attributes and child elements.

    Attributes:
        tag: Element name without namespace prefix (``BEGROTINGSREGEL``).
        name: Element name as written, including a prefix if there was one (``Ibis:X``).
        attributes: Attribute values by name as written (prefixes kept, ``xmlns`` declarations
            removed), in document order. Entities are resolved and attribute-value normalisation
            has been applied by the XML parser.
        children: Child elements in document order.
        line: 1-based line of the start tag.
        column: 0-based column of the start tag.
        path: Location such as ``/CUF/BEGROTING/BUNDELING[2]``; indices count same-named siblings.
        text: Non-whitespace text content, if any (CUF-XML elements have none).
    """

    __slots__ = ("attributes", "children", "column", "line", "name", "path", "tag", "text")

    def __init__(
        self,
        name: str,
        attributes: Mapping[str, str],
        children: Sequence[RawElement],
        line: int,
        column: int,
        path: str,
        text: str | None = None,
    ) -> None:
        i = name.find(":")
        self.name: str = name
        self.tag: str = name[i + 1 :] if i >= 0 else name
        self.attributes: Mapping[str, str] = MappingProxyType(dict(attributes))
        self.children: Sequence[RawElement] = tuple(children)
        self.line: int = line
        self.column: int = column
        self.path: str = path
        self.text: str | None = text

    def get(self, name: str, default: str | None = None) -> str | None:
        """Return the raw value of attribute ``name``."""
        return self.attributes.get(name, default)

    def find(self, tag: str) -> RawElement | None:
        """Return the first child with local name ``tag``."""
        return next((c for c in self.children if c.tag == tag), None)

    def findall(self, tag: str) -> tuple[RawElement, ...]:
        """Return all children with local name ``tag``."""
        return tuple(c for c in self.children if c.tag == tag)

    def iter(self, tag: str | None = None) -> Iterator[RawElement]:
        """Iterate over this element and all descendants (optionally only those named ``tag``)."""
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            yield from child.iter(tag)

    def to_dict(self) -> dict[str, object]:
        """Return a plain ``dict``: the attributes plus ``"children"`` (a list of dicts)."""
        out: dict[str, object] = {"tag": self.name, **self.attributes}
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        if self.text is not None:
            out["text"] = self.text
        return out

    def __repr__(self) -> str:
        return f"RawElement({self.name!r}, line={self.line}, attributes={dict(self.attributes)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RawElement):
            return NotImplemented
        return (
            self.name == other.name
            and dict(self.attributes) == dict(other.attributes)
            and list(self.children) == list(other.children)
            and self.text == other.text
        )

    __hash__: ClassVar[None]  # type: ignore[assignment]  # compares by value; not hashable

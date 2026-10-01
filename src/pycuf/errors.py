"""Exceptions raised by pycuf.

pycuf never refuses a file because of *data* problems: those become findings (see
:mod:`pycuf.findings`). Exceptions are reserved for input that cannot be read at all: not CUF-XML,
malformed XML, forbidden constructs, exceeded limits and missing extras.
"""

from __future__ import annotations

__all__ = [
    "ForbiddenConstructError",
    "LimitExceededError",
    "MissingExtraError",
    "NotCufError",
    "PycufError",
    "XmlSyntaxError",
]


class PycufError(Exception):
    """Base class for all pycuf errors."""


class NotCufError(PycufError):
    """The input is not a CUF-XML file (for example another XML format or the pre-XML CUF 3)."""


class XmlSyntaxError(PycufError):
    """The XML is not well-formed.

    Attributes:
        line: 1-based line number of the error (``None`` if unknown).
        column: 0-based column of the error (``None`` if unknown).
    """

    def __init__(self, message: str, *, line: int | None = None, column: int | None = None) -> None:
        super().__init__(message)
        self.line = line
        self.column = column


class ForbiddenConstructError(XmlSyntaxError):
    """The XML contains a construct pycuf refuses for security reasons (DOCTYPE, ENTITY).

    CUF-XML never uses a DTD; refusing them blocks entity-expansion ("billion laughs") and
    external-entity (XXE) attacks.
    """


class LimitExceededError(PycufError):
    """A configured safety limit (input size, nesting depth, attribute size) was exceeded."""


class MissingExtraError(PycufError, ImportError):
    """An optional dependency is needed; the message says which extra to install."""

"""Strict, non-coercing value parsers for CUF-XML attribute values.

CUF-XML 4.003 uses the Microsoft XDR data types. The parsers follow their definitions:

- ``number``: an optionally signed decimal with an optional exponent (``111``, ``3.14``,
  ``-123.456E+10``); the CUF specification adds "a decimal point if needed, no thousands
  separator". Parsed into :class:`decimal.Decimal`, never ``float``.
- ``date``: ``YYYY-MM-DD``. ``dateTime``: ``YYYY-MM-DD`` with an optional ``Thh:mm:ss[.fff…]``
  and no time zone.
- ``boolean``: ``0`` or ``1``.

Each parser returns ``None`` when a value cannot be interpreted exactly; the caller reports a
finding and keeps the raw text. Lenient variants (decimal comma, Dutch ``d-m-yyyy`` dates) are
opt-in and tell the caller that they were needed, so it can report that too.
"""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal

__all__ = ["parse_bool", "parse_date", "parse_datetime", "parse_number"]

_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)
_NUMBER_COMMA = re.compile(r"[+-]?(?:[0-9]+(?:,[0-9]*)?|,[0-9]+)", re.ASCII)
_ISO_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", re.ASCII)
_ISO_DATETIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"(?:T([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.([0-9]{1,9}))?)?)?",
    re.ASCII,
)
_DUTCH_DATETIME = re.compile(
    r"([0-9]{1,2})-([0-9]{1,2})-([0-9]{4})(?:[ T]([0-9]{1,2}):([0-9]{2})(?::([0-9]{2}))?)?",
    re.ASCII,
)
_ISO_SPACE_DATETIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2}) ([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?", re.ASCII
)


def parse_number(text: str, *, decimal_comma: bool = False) -> tuple[Decimal | None, bool]:
    """Parse an XDR ``number``.

    Surrounding whitespace is allowed. ``NaN``, ``Infinity``, grouping separators, underscores and
    non-ASCII digits are rejected.

    Args:
        text: The attribute value.
        decimal_comma: Also accept a comma as the decimal separator (``12,5``), which CUF-XML
            forbids but some exporters write.

    Returns:
        ``(value, used_comma)``; ``value`` is ``None`` when the text is not a valid number.
    """
    s = text.strip()
    if _NUMBER.fullmatch(s):
        return Decimal(s), False
    if decimal_comma and _NUMBER_COMMA.fullmatch(s):
        return Decimal(s.replace(",", ".")), True
    return None, False


def parse_date(text: str, *, dutch: bool = False) -> tuple[dt.date | None, bool]:
    """Parse an XDR ``date`` (``YYYY-MM-DD``).

    Args:
        text: The attribute value.
        dutch: Also accept ``d-m-yyyy`` and ``dd-mm-yyyy`` (written by some exporters).

    Returns:
        ``(date, used_dutch_format)``; ``date`` is ``None`` when invalid.
    """
    s = text.strip()
    m = _ISO_DATE.fullmatch(s)
    if m:
        return _date(m.group(1), m.group(2), m.group(3)), False
    if dutch:
        m = _DUTCH_DATETIME.fullmatch(s)
        if m and m.group(4) is None:
            return _date(m.group(3), m.group(2), m.group(1)), True
    return None, False


def parse_datetime(text: str, *, dutch: bool = False) -> tuple[dt.datetime | None, bool]:
    """Parse an XDR ``dateTime`` (``YYYY-MM-DD[Thh:mm[:ss[.fff…]]]``, no time zone).

    Fractional seconds beyond microseconds are truncated (Python's resolution).

    Args:
        text: The attribute value.
        dutch: Also accept ``d-m-yyyy [h:mm[:ss]]`` and ``YYYY-MM-DD hh:mm[:ss]``.

    Returns:
        ``(datetime, used_lenient_format)``; ``datetime`` is ``None`` when invalid.
    """
    s = text.strip()
    m = _ISO_DATETIME.fullmatch(s)
    if m:
        y, mo, d, h, mi, sec, frac = m.groups()
        micro = int((frac or "0")[:6].ljust(6, "0"))
        return _datetime(y, mo, d, h or "0", mi or "0", sec or "0", micro), False
    if dutch:
        m = _DUTCH_DATETIME.fullmatch(s)
        if m:
            d, mo, y, h, mi, sec = m.groups()
            return _datetime(y, mo, d, h or "0", mi or "0", sec or "0", 0), True
        m = _ISO_SPACE_DATETIME.fullmatch(s)
        if m:
            y, mo, d, h, mi, sec = m.groups()
            return _datetime(y, mo, d, h, mi, sec or "0", 0), True
    return None, False


def parse_bool(text: str) -> bool | None:
    """Parse an XDR ``boolean`` (``0``/``1``; ``true``/``false`` are accepted as well)."""
    s = text.strip().lower()
    if s in ("1", "true"):
        return True
    if s in ("0", "false"):
        return False
    return None


def _date(year: str, month: str, day: str) -> dt.date | None:
    try:
        return dt.date(int(year), int(month), int(day))
    except ValueError:
        return None


def _datetime(
    year: str, month: str, day: str, hour: str, minute: str, second: str, micro: int
) -> dt.datetime | None:
    try:
        return dt.datetime(
            int(year), int(month), int(day), int(hour), int(minute), int(second), micro
        )
    except ValueError:
        return None

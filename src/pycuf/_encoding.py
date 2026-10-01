"""Character-encoding detection, transcoding for Expat, and opt-in byte-level repairs."""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from typing import Literal

from .findings import FindingCollector

__all__ = [
    "REPAIRS",
    "EncodingInfo",
    "Repair",
    "check_encoding_name",
    "prepare",
    "repair_bytes",
    "sniff_encoding",
]

Repair = Literal["control-chars", "bare-ampersand"]
"""Opt-in repairs: remove XML-illegal control characters, escape ``&`` that starts no entity."""
REPAIRS: frozenset[str] = frozenset({"control-chars", "bare-ampersand"})

_BOMS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_DECL = re.compile(rb"^\s*<\?xml\b[^>]*?\bencoding\s*=\s*([\"'])([A-Za-z][A-Za-z0-9._-]*)\1")
_HAS_DECL = re.compile(rb"^\s*<\?xml\b")
# XML 1.0 forbids C0 controls except TAB, LF, CR
_CONTROL = bytes([*range(9), 11, 12, *range(14, 32)])
_BARE_AMP = re.compile(rb"&(?!(?:[A-Za-z_:][A-Za-z0-9._:-]*|#[0-9]+|#x[0-9A-Fa-f]+);)")
#: Encodings Expat decodes itself (Python codec names).
_EXPAT_NATIVE = frozenset({"utf-8", "utf-16", "utf-16-le", "utf-16-be", "iso8859-1", "ascii"})
_SURROGATE = re.compile("[\udc80-\udcff]")


def check_encoding_name(name: str) -> str:
    """Return Python's canonical codec name or raise ``ValueError`` for unknown encodings."""
    try:
        return codecs.lookup(name).name
    except LookupError:
        raise ValueError(f"unknown encoding {name!r}") from None


def _canonical(name: str) -> str:
    try:
        return codecs.lookup(name).name
    except LookupError:
        return name.lower()


@dataclass(frozen=True, slots=True)
class EncodingInfo:
    """How the bytes of a file are decoded.

    Attributes:
        bom: Encoding indicated by a byte-order mark, if any.
        declared: Encoding named in the XML declaration (as written), if any.
        has_declaration: Whether an XML declaration is present.
        effective: Canonical Python codec name used for decoding.
        override: Encoding forced by the caller, if any.
    """

    bom: str | None
    declared: str | None
    has_declaration: bool
    effective: str
    override: str | None = None


def sniff_encoding(head: bytes, override: str | None = None) -> EncodingInfo:
    """Determine the encoding from the BOM and the XML declaration (XML 1.0 Appendix F)."""
    bom = next((enc for mark, enc in _BOMS if head.startswith(mark)), None)
    body = head
    if bom is not None:
        mark = next(m for m, e in _BOMS if e == bom)
        body = head[len(mark) :]
        if not bom.startswith("utf-8"):
            body = body[:4096].decode(bom, errors="ignore").encode("ascii", errors="ignore")
    elif head[:4] in (b"<\x00?\x00", b"\x00<\x00?"):
        enc = "utf-16-le" if head[0] == 0x3C else "utf-16-be"
        text = head[:4096].decode(enc, errors="ignore").encode("ascii", errors="ignore")
        m = _DECL.match(text)
        effective = _canonical(override) if override else enc
        return EncodingInfo(None, m.group(2).decode() if m else None, True, effective, override)
    m = _DECL.match(body)
    declared = m.group(2).decode("ascii") if m else None
    has_decl = bool(_HAS_DECL.match(body))
    if override:
        effective = _canonical(override)
    elif bom is not None:
        effective = bom
    elif declared:
        effective = _canonical(declared)
    else:
        effective = "utf-8"
    return EncodingInfo(bom, declared, has_decl, effective, override)


def repair_bytes(data: bytes, repairs: frozenset[str], findings: FindingCollector) -> bytes:
    """Apply opt-in repairs (ASCII-compatible encodings only) and report each one."""
    if "control-chars" in repairs:
        cleaned = data.translate(None, _CONTROL)
        if removed := len(data) - len(cleaned):
            findings.add("CUF1010", f"removed {removed:,} XML-illegal control character(s)")
        data = cleaned
    if "bare-ampersand" in repairs:
        data, escaped = _BARE_AMP.subn(b"&amp;", data)
        if escaped:
            findings.add("CUF1012", f"escaped {escaped:,} bare '&' character(s) as '&amp;'")
    return data


def prepare(
    data: bytes, info: EncodingInfo, findings: FindingCollector
) -> tuple[bytes, str | None]:
    """Return ``(bytes_for_expat, expat_encoding)``.

    Encodings Expat supports natively are passed through unchanged. Everything else Python knows
    (windows-1252, UTF-32, …) is transcoded to UTF-8 here, and Expat is told to read UTF-8. Bytes
    the codec does not define (such as 0x81 in windows-1252) are kept as the code point of the same
    value, as ISO-8859-1 would, and reported once.
    """
    effective = info.effective
    if info.override is None and effective in _EXPAT_NATIVE:
        return data, None
    if effective in _EXPAT_NATIVE:
        return data, effective
    try:
        codec = codecs.lookup(effective).name
    except LookupError:
        return data, "utf-8"
    if codec in _EXPAT_NATIVE:
        return data, codec
    text = data.decode(codec, errors="surrogateescape")
    if info.bom is not None and text.startswith("﻿"):
        text = text[1:]
    if _SURROGATE.search(text):
        undefined = len(_SURROGATE.findall(text))
        findings.add(
            "CUF1006",
            f"{undefined:,} byte(s) are undefined in {codec}; kept as the Latin-1 character of "
            "the same value",
        )
        text = _SURROGATE.sub(lambda m: chr(ord(m.group()) - 0xDC00), text)
    return text.encode("utf-8"), "utf-8"

from __future__ import annotations

import pytest

import pycuf
from pycuf import ForbiddenConstructError, LimitExceededError

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE CUF [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>
<CUF AANMAAKDATUMTIJD="&b;"/>"""
XXE = b"""<?xml version="1.0"?>
<!DOCTYPE CUF [<!ENTITY x SYSTEM "file:///etc/passwd">]><CUF A="&x;"/>"""


@pytest.mark.parametrize("data", [BILLION_LAUGHS, XXE, b"<!DOCTYPE CUF><CUF/>"])
def test_doctype_is_refused(data: bytes) -> None:
    with pytest.raises(ForbiddenConstructError):
        pycuf.read(data)


@pytest.mark.parametrize("data", [BILLION_LAUGHS, XXE])
def test_validate_reports_forbidden_construct(data: bytes) -> None:
    report = pycuf.validate(data)
    assert not report.ok and report.findings[0].code == "CUF2002"


def test_depth_limit() -> None:
    nested = b"<BUNDELING>" * 70 + b"</BUNDELING>" * 70
    xml = b"<CUF><BEGROTING>" + nested + b"</BEGROTING></CUF>"
    with pytest.raises(LimitExceededError):
        pycuf.read(xml)
    assert len(pycuf.read(xml, max_depth=100).bundles) == 70
    assert pycuf.validate(xml).findings[0].code == "CUF2003"


def test_size_limits() -> None:
    xml = b'<CUF A="' + b"x" * 5000 + b'"/>'
    with pytest.raises(LimitExceededError):
        pycuf.read(xml, max_attribute_size=1000)
    with pytest.raises(LimitExceededError):
        pycuf.read(xml, max_size=100)


def test_malformed_becomes_finding() -> None:
    report = pycuf.validate(b"<CUF><BEGROTING></CUF>")
    assert report.findings[0].code == "CUF2001" and report.findings[0].line == 1


DOC = (
    b'<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">'
    b'<PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/></CUF>'
)


@pytest.mark.parametrize("tail", [b"\x00" * 64, b"\r\n\x1a", b" \x00\r\n"])
def test_padding_after_the_document_is_a_warning(tail: bytes) -> None:
    cuf = pycuf.read(DOC + tail)
    assert [f.code for f in cuf.findings if f.code == "CUF1013"] == ["CUF1013"]


@pytest.mark.parametrize("tail", [b"junk", b"<!-- unclosed", b"<?invalid", b"\xff", b"<CUF/>"])
def test_other_data_after_the_document_is_malformed(tail: bytes) -> None:
    with pytest.raises(pycuf.XmlSyntaxError):
        pycuf.read(DOC + tail)
    assert pycuf.validate(DOC + tail).findings[0].code == "CUF2001"

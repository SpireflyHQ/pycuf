from __future__ import annotations

import codecs
import datetime as dt
import io
from decimal import Decimal
from pathlib import Path
from typing import Any

import cufgen
import pytest

import pycuf
from pycuf import CostType, NotCufError, XmlSyntaxError


def codes(cuf: pycuf.CufFile) -> set[str]:
    return {f.code for f in cuf.findings}


def test_every_dialect_reads(dialect: str, estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate, dialect))
    assert len(cuf.lines) == len(estimate.lines()) + (
        len(cuf.bundles) if dialect == "ibis" else 0  # one text line per bundle
    )
    assert cuf.project.cuf_version == "4.003"
    assert (cuf.project.name or "").startswith("Voorbeeldproject")


def test_sources(tmp_path: Path, estimate: cufgen.Estimate) -> None:
    data = cufgen.write(estimate)
    path = tmp_path / "begroting.xml"
    path.write_bytes(data)
    for source in (data, bytearray(data), path, str(path), io.BytesIO(data)):
        assert len(pycuf.read(source).lines) == len(estimate.lines())
    with pytest.raises(TypeError, match="binary"):
        pycuf.read(io.StringIO("<CUF/>"))  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        pycuf.read(tmp_path / "missing.xml")


def test_model_values(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate))
    first = estimate.lines()[0]
    line = cuf.lines[0]
    assert line.code == first.code
    assert line.quantity == first.quantity
    assert line.material_price == first.material_price
    assert line.vat_rate == first.vat
    assert cuf.created == dt.datetime(2026, 10, 1, 10, 15)
    assert cuf.project.estimate_date == dt.date(2026, 10, 1)
    assert cuf.project.notes == "Revisie 2\nFictieve begroting"  # &#10; survives normalisation
    assert {r.cost_type for r in line.resources} >= {CostType.LABOUR, CostType.MATERIAL}
    assert cuf.lines[line.seq] is line
    assert cuf.tail is not None and len(cuf.tail.items) == 2


def test_tree_navigation(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate))
    deep = max(cuf.lines, key=lambda ln: ln.depth)
    chain = cuf.ancestors(deep)
    assert len(chain) == deep.depth
    assert cuf.parent(deep) is chain[-1]
    assert deep.bundle_seq == chain[-1].seq
    assert next(iter(cuf.walk())) is cuf.estimate.children[0]
    loose = cuf.estimate.lines
    assert loose and cuf.parent(loose[0]) is None and loose[0].depth == 0
    assert cuf.parent(deep.resources[0]) is deep if deep.resources else True
    other = pycuf.read(cufgen.write(estimate))
    with pytest.raises(ValueError, match="does not belong"):
        cuf.parent(other.lines[0])


def test_sort_code_inheritance() -> None:
    xml = b"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <SORTEERCODES SORTERING="PLAN"/><SORTEERCODES SORTERING="ADMI"/>
      <BEGROTING UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="0" MATERIEELKOSTEN="0"
                 ONDERAANNEMING="0" OVERIGE_KOSTEN="0">
        <BUNDELING CODE="1"><SORTEERCODE SORTERING="PLAN" WAARDE="A"/>
          <SORTEERCODE SORTERING="ADMI" WAARDE="X"/>
          <BEGROTINGSREGEL CODE="r1" BTW="21"><SORTEERCODE SORTERING="PLAN" WAARDE="B"/>
          </BEGROTINGSREGEL>
          <BEGROTINGSREGEL CODE="r2" BTW="21"/>
        </BUNDELING>
      </BEGROTING>
      <STAARTGEGEVENS AANNEEMSOM="0"/>
    </CUF>"""
    cuf = pycuf.read(xml)
    r1, r2 = cuf.lines
    assert cuf.sort_codes(r1) == {"PLAN": "B", "ADMI": "X"}
    assert cuf.sort_codes(r2) == {"PLAN": "A", "ADMI": "X"}
    assert cuf.sort_codes(r1, inherited=False) == {"PLAN": "B"}
    assert {f.code for f in cuf.findings} == {"CUF1002", "CUF3001"}


def test_ibis_quirks(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate, "ibis"))
    assert cuf.encoding.declared == "Windows-1252"
    assert cuf.encoding.effective == "cp1252"
    assert cuf.project.name and cuf.project.name.endswith("– €")
    assert "geïsoleerd" in (next(ln for ln in cuf.lines if not ln.is_text).description or "")
    assert cuf.namespaces == {
        "": "x-schema:CufSchema.xml",
        "Ibis": "http://www.brinkgroep.nl/ibis/xml",
    }
    btw = [f for f in cuf.findings if f.code == "CUF3017"]
    assert len(btw) == 1 and "times" in btw[0].message
    assert all(ln.vat_rate is None for ln in cuf.lines)
    text = [ln for ln in cuf.lines if ln.is_text]
    assert len(text) == len(cuf.bundles)
    assert cuf.sort_codes(text[0])["stk"] == '"'


def test_forum_namespace_with_spaces(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate, "forum"))
    assert cuf.namespace == "x-schema:Forum CUF-XML-schema4003.xsd"
    assert "CUF1002" in codes(cuf)


def test_dataviewers_quirks(estimate: cufgen.Estimate) -> None:
    data = cufgen.write(estimate, "dataviewers")
    cuf = pycuf.read(data)
    assert cuf.created == dt.datetime(2026, 10, 1, 10, 15)
    assert cuf.tail is None
    assert {"CUF3010", "CUF7002", "CUF3022", "CUF3017"} <= codes(cuf)
    assert cuf.lines[0].provisional_sum is False
    strict = pycuf.read(data, lenient=())
    assert strict.created is None and "CUF3019" in codes(strict)


def test_bakkerspees_quirks() -> None:
    cuf = pycuf.read(cufgen.write(cufgen.make_estimate(2, resources=True), "bakkerspees"))
    assert not cuf.bundles and cuf.estimate.lines
    assert cuf.lines[0].extra["WERKBESCHRIJVING"].startswith("Werkbeschrijving")
    assert any("KOSTPRIJS" in r.extra for r in cuf.resource_lines)
    assert set(cuf.sort_codes(cuf.lines[0])) == {"ACTI", "NACA"}
    assert {"CUF3025", "CUF3012", "CUF4001"} <= codes(cuf)
    assert "CUF3016" not in codes(cuf)


def test_structure_findings() -> None:
    xml = b"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <BEGROTING UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="0" MATERIEELKOSTEN="0"
                 ONDERAANNEMING="0" OVERIGE_KOSTEN="0">
        <BEGROTINGSREGEL BTW="21" HOEVEELHEID="abc" STELPOST="ja">tekst
          <MAMO_REGEL KOSTENSOORT="ARBEID"/><VENDOR/>
        </BEGROTINGSREGEL>
        <STAARTGEGEVENS AANNEEMSOM="0"/>
      </BEGROTING>
      <PROJECTGEGEVENS CUF_VERSIE="4.002" AANMAAKDATUM="2026-01-01" VALUTA="XYZ"/>
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
    </CUF>"""
    cuf = pycuf.read(xml)
    found = codes(cuf)
    assert {"CUF3010", "CUF3011", "CUF3013", "CUF3014", "CUF3015"} <= found
    assert {"CUF3018", "CUF3020", "CUF3021", "CUF3023", "CUF3002"} <= found
    assert cuf.lines[0].quantity is None and cuf.lines[0].raw is not None
    assert cuf.lines[0].raw.get("HOEVEELHEID") == "abc"
    assert cuf.resource_lines[0].cost_type is None
    assert cuf.resource_lines[0].cost_type_code == "ARBEID"
    finding = next(f for f in cuf.findings if f.code == "CUF3018")
    assert finding.line == 4
    assert finding.path == "/CUF/BEGROTING[1]/BEGROTINGSREGEL[1]@HOEVEELHEID"


@pytest.mark.parametrize("text", ["1e1000000", "1e-1000100", "1e999999999999999999999999"])
def test_numbers_out_of_range_become_findings(text: str) -> None:
    xml = f"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <BEGROTING><BEGROTINGSREGEL BTW="21" HOEVEELHEID="{text}" MATERIAALPRIJS="1"/></BEGROTING>
    </CUF>""".encode()
    cuf = pycuf.read(xml)
    assert cuf.lines[0].quantity is None and cuf.lines[0].raw is not None
    assert cuf.lines[0].raw.get("HOEVEELHEID") == text
    finding = next(f for f in cuf.findings if f.code == "CUF3018")
    assert "outside the supported range" in finding.message and finding.value == text
    report = pycuf.validate(xml)
    assert not report.ok and report.counts["CUF3018"] == 1


def test_legacy_sort_attributes() -> None:
    xml = b"""<CUF AANMAAKDATUMTIJD="2001-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.000" AANMAAKDATUM="2001-01-01" VALUTA="NLG"/>
      <BEGROTING UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="0" MATERIEELKOSTEN="0"
                 ONDERAANNEMING="0" OVERIGE_KOSTEN="0">
        <BEGROTINGSREGEL BTW="19" SC1="A10" SC2="P3"/>
      </BEGROTING>
      <STAARTGEGEVENS AANNEEMSOM="0"/>
    </CUF>"""
    cuf = pycuf.read(xml)
    assert cuf.sort_codes(cuf.lines[0]) == {"SC1": "A10", "SC2": "P3"}
    assert {"CUF3024", "CUF3002"} <= codes(cuf)
    assert "CUF3012" not in codes(cuf)


def test_not_cuf() -> None:
    with pytest.raises(NotCufError, match="Open Calc Studio"):
        pycuf.read(b'<?xml version="1.0"?><Calculatie version="4.003"/>')
    with pytest.raises(NotCufError, match="not XML"):
        pycuf.read(b"CUF3000 fixed width record")
    with pytest.raises(NotCufError, match="empty"):
        pycuf.read(b"  ")


def test_malformed_xml() -> None:
    with pytest.raises(XmlSyntaxError) as exc:
        pycuf.read(b"<CUF>\n<BEGROTING></CUF>")
    assert exc.value.line == 2


def test_encoding_override_and_undefined_bytes() -> None:
    body = '<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00" X="€"/>'
    with pytest.raises(XmlSyntaxError, match="encoding"):
        pycuf.read(body.encode("cp1252"))
    cuf = pycuf.read(body.encode("cp1252"), encoding="cp1252")
    assert cuf.raw.get("X") == "€" and "CUF1004" in codes(cuf)
    odd = b'<?xml version="1.0" encoding="windows-1252"?><CUF A="\x81"/>'
    assert "CUF1006" in codes(pycuf.read(odd))


def test_repairs() -> None:
    xml = b'<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00"><PROJECTGEGEVENS SYSTEEMHUIS="A & B\x01"/></CUF>'
    with pytest.raises(XmlSyntaxError):
        pycuf.read(xml)
    cuf = pycuf.read(xml, repair={"bare-ampersand", "control-chars"})
    assert cuf.project.software_house == "A & B"
    assert {"CUF1010", "CUF1012"} <= codes(cuf)


@pytest.mark.parametrize(
    ("codec", "name"),
    [
        ("utf-16", "UTF-16"),
        ("utf-16-be", "UTF-16"),
        ("utf-32", "UTF-32"),
        ("iso2022_jp", "ISO-2022-JP"),
    ],
)
@pytest.mark.parametrize("repair", ["bare-ampersand", "control-chars"])
def test_repairs_never_change_valid_text(codec: str, name: str, repair: str) -> None:
    value = "日本 … &amp; B" if codec == "iso2022_jp" else "A … Ħ &amp; B"
    text = f'<?xml version="1.0" encoding="{name}"?><CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00" X="{value}"/>'
    data = text.encode(codec)
    if codec == "utf-16-be":
        data = b"\xfe\xff" + data
    cuf = pycuf.read(data, repair={repair})
    assert cuf.raw.get("X") == value.replace("&amp;", "&")
    assert not {"CUF1010", "CUF1012"} & codes(cuf)


@pytest.mark.parametrize("codec", ["utf-16", "utf-32"])
def test_repairs_in_wide_encodings(codec: str) -> None:
    name = codec.upper()
    text = f'<?xml version="1.0" encoding="{name}"?><CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00" X="A & B\x01"/>'
    cuf = pycuf.read(text.encode(codec), repair={"bare-ampersand", "control-chars"})
    assert cuf.raw.get("X") == "A & B"
    assert {"CUF1010", "CUF1012"} <= codes(cuf)


def test_utf32_byte_orders_and_invalid_input() -> None:
    text = (
        '<?xml version="1.0" encoding="UTF-32"?><CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00" X="€"/>'
    )
    for data in (
        codecs.BOM_UTF32_BE + text.encode("utf-32-be"),
        text.encode("utf-32-be"),
        text.encode("utf-32-le"),
    ):
        assert pycuf.read(data).raw.get("X") == "€"
    truncated = codecs.BOM_UTF32_LE + text.encode("utf-32-le") + b"\x00"
    with pytest.raises(XmlSyntaxError, match="not valid utf-32-le"):
        pycuf.read(truncated)
    surrogate = codecs.BOM_UTF32_LE + text.replace("€", "\ud800").encode(
        "utf-32-le", "surrogatepass"
    )
    for data in (truncated, surrogate, b"\x00\x00<\x00\x00\x00C\x00"):
        report = pycuf.validate(data)
        assert [f.code for f in report.findings] == ["CUF2001"]


def test_option_validation() -> None:
    with pytest.raises(ValueError, match="lenient"):
        pycuf.read(b"<CUF/>", lenient=["commas"])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="repair"):
        pycuf.read(b"<CUF/>", repair=["all"])
    with pytest.raises(ValueError, match="unknown finding code"):
        pycuf.read(b"<CUF/>", severity_overrides={"CUF9999": None})
    with pytest.raises(ValueError, match="encoding"):
        pycuf.read(b"<CUF/>", encoding="klingon")
    with pytest.raises(ValueError, match="preset"):
        pycuf.read(b"<CUF/>", policy="epr")  # type: ignore[arg-type]


def test_severity_overrides(estimate: cufgen.Estimate) -> None:
    data = cufgen.write(estimate, "ibis")
    quiet = pycuf.read(data, severity_overrides={"CUF3017": None, "CUF3001": None})
    assert not quiet.findings
    loud = pycuf.read(data, severity_overrides={"CUF3017": pycuf.Severity.ERROR})
    assert next(f for f in loud.findings if f.code == "CUF3017").severity is pycuf.Severity.ERROR


def test_finding_limits() -> None:
    lines = "".join(f'<BEGROTINGSREGEL BTW="21" HOEVEELHEID="x{i}"/>' for i in range(50))
    xml = f'<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00"><BEGROTING>{lines}</BEGROTING></CUF>'
    cuf = pycuf.read(xml.encode(), max_findings_per_code=10)
    assert sum(f.code == "CUF3018" for f in cuf.findings) == 10
    assert cuf._collector.counts["CUF3018"] == 50


def test_quantity_line_product() -> None:
    q = pycuf.QuantityLine(seq=0, count=Decimal(2), length=Decimal("3.5"), width=Decimal(4))
    assert q.product == Decimal(28)
    assert pycuf.QuantityLine(seq=1).product is None


@pytest.mark.parametrize("codec", ["utf-8-sig", "utf-16", "utf-32"])
def test_unicode_encodings(codec: str) -> None:
    text = '<?xml version="1.0" encoding="{}"?><CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00" X="€ë"/>'
    name = {"utf-8-sig": "UTF-8", "utf-16": "UTF-16", "utf-32": "UTF-32"}[codec]
    cuf = pycuf.read(text.format(name).encode(codec))
    assert cuf.raw.get("X") == "€ë"
    assert "CUF1001" in codes(cuf)


def test_raw_layer(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate, "ibis"))
    raw = cuf.raw
    assert raw.tag == raw.name == "CUF"
    begroting = raw.find("BEGROTING")
    assert begroting is not None and begroting.findall("BUNDELING")
    assert len(list(raw.iter("BEGROTINGSREGEL"))) == len(cuf.lines)
    assert raw.find("NOPE") is None
    line = cuf.lines[0].raw
    assert line is not None and line.get("BTW") == "" and line.path.startswith("/CUF/")
    assert line.to_dict()["tag"] == "BEGROTINGSREGEL"
    assert raw == pycuf.read(cufgen.write(estimate, "ibis")).raw
    assert "RawElement('CUF'" in repr(raw)


def test_streams_returning_short_reads(estimate: cufgen.Estimate) -> None:
    data = cufgen.write(estimate)

    class Raw(io.RawIOBase):  # a pipe or socket: at most 80 bytes per read
        def __init__(self) -> None:
            self.buffer = io.BytesIO(data)

        def readable(self) -> bool:
            return True

        def readinto(self, b: Any) -> int:
            chunk = self.buffer.read(min(len(b), 80))
            b[: len(chunk)] = chunk
            return len(chunk)

    assert len(pycuf.read(Raw()).lines) == len(pycuf.read(data).lines)
    with pytest.raises(pycuf.LimitExceededError):
        pycuf.read(Raw(), max_size=1000)

    class Empty(io.RawIOBase):  # non-blocking, nothing available yet
        def readable(self) -> bool:
            return True

        def readinto(self, b: Any) -> None:
            return None

    with pytest.raises(BlockingIOError):
        pycuf.read(Empty())


def test_quantity_lines_follow_document_order() -> None:
    xml = b"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <BEGROTING><BUNDELING>
        <HOEVEELHEDENSTAAT_REGEL OMSCHRIJVING="1 bundle, before"/>
        <BEGROTINGSREGEL BTW="21">
          <HOEVEELHEDENSTAAT_REGEL OMSCHRIJVING="2 line"/>
          <MAMO_REGEL KOSTENSOORT="MATERIAAL">
            <HOEVEELHEDENSTAAT_REGEL OMSCHRIJVING="3 resource"/>
          </MAMO_REGEL>
          <HOEVEELHEDENSTAAT_REGEL OMSCHRIJVING="4 line, after"/>
        </BEGROTINGSREGEL>
        <HOEVEELHEDENSTAAT_REGEL OMSCHRIJVING="5 bundle, after"/>
      </BUNDELING></BEGROTING></CUF>"""
    cuf = pycuf.read(xml)
    assert [q.description for q in cuf.quantity_lines] == [
        "1 bundle, before",
        "2 line",
        "3 resource",
        "4 line, after",
        "5 bundle, after",
    ]
    assert all(cuf.quantity_lines[q.seq] is q for q in cuf.quantity_lines)
    assert [q.description for q in cuf.lines[0].quantity_lines] == ["2 line", "4 line, after"]


def test_textual_booleans_and_negative_amounts() -> None:
    xml = b"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <BEGROTING>
        <BEGROTINGSREGEL BTW="21" STELPOST="true" HOEVEELHEID="-2" MATERIAALPRIJS="5"/>
        <BEGROTINGSREGEL BTW="21" STELPOST="TrUe" HOEVEELHEID="-1" MATERIAALPRIJS="-0"/>
      </BEGROTING></CUF>"""
    cuf = pycuf.read(xml)
    assert [ln.provisional_sum for ln in cuf.lines] == [True, None]
    found = {f.code: f for f in cuf.findings}
    assert "CUF7004" in found and "CUF3020" in found
    assert "(2 times" in found["CUF7001"].message  # aggregated; -0 is not negative
    strict = pycuf.read(xml, lenient=())
    assert strict.lines[0].provisional_sum is None
    assert "CUF7004" not in codes(strict) and "CUF3020" in codes(strict)

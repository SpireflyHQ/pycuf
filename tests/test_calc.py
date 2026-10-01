from __future__ import annotations

import decimal
from decimal import Decimal

import cufgen
import pytest

import pycuf
from pycuf.models import COST_FIELDS
from pycuf.policy import ERP, SCHEMA, Policy


def assert_costs(costs: pycuf.Costs, expected: dict[str, Decimal]) -> None:
    for name in COST_FIELDS:
        assert getattr(costs, name) == expected[name], name


def test_traditional_totals_match_generator(estimate: cufgen.Estimate, dialect: str) -> None:
    if dialect == "bakkerspees":
        estimate = cufgen.make_estimate(7)  # flat dialect: no bundles to multiply anyway
    cuf = pycuf.read(cufgen.write(estimate, dialect))
    totals = cuf.totals()
    assert totals.estimate_style == "traditional"
    assert_costs(totals.estimate, estimate.expected())


def test_bundle_totals(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate))
    totals = cuf.totals()
    for gen, bundle in zip(estimate.bundles(), cuf.bundles, strict=True):
        assert_costs(totals[bundle], gen.costs())
        assert totals.multiplier(bundle) == 1
    assert not [f for f in cuf.validate().findings if f.code.startswith("CUF5")]


def test_element_estimate(element_estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(element_estimate))
    totals = cuf.totals()
    assert totals.estimate_style == "element" and totals.style_inferred
    assert_costs(totals.estimate, element_estimate.expected())
    for gen, bundle in zip(element_estimate.bundles(), cuf.bundles, strict=True):
        assert_costs(totals[bundle], gen.costs())  # excludes the bundle's own multiplier
    assert sum((totals.extended(ln) for ln in cuf.lines), pycuf.Costs()).total == (
        totals.estimate.total
    )
    assert "CUF7005" in {f.code for f in totals.findings}
    report = cuf.validate()
    assert not [f for f in report.findings if f.code in ("CUF5001", "CUF5002")]
    ignored = cuf.totals(policy=Policy(estimate_style="traditional"))
    assert ignored.estimate.total < totals.estimate.total
    assert all(ignored.multiplier(b) == 1 for b in cuf.bundles)


def xml(lines: str, bundle_attrs: str = "", totals: str = "") -> bytes:
    stated = totals or (
        'UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="0" MATERIEELKOSTEN="0" '
        'ONDERAANNEMING="0" OVERIGE_KOSTEN="0"'
    )
    return f"""<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">
      <PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>
      <BEGROTING {stated}><BUNDELING CODE="B" {bundle_attrs}>{lines}</BUNDELING></BEGROTING>
      <STAARTGEGEVENS AANNEEMSOM="0"/></CUF>""".encode()


def test_zero_factor_policy() -> None:
    cuf = pycuf.read(
        xml(
            '<BEGROTINGSREGEL BTW="21" HOEVEELHEID="10" HOEVEELHEID_FACTOR="0" MATERIAALPRIJS="2"/>'
        )
    )
    assert cuf.totals().estimate.material == 20
    assert "CUF7006" in {f.code for f in cuf.totals().findings}
    assert cuf.totals(policy="schema").estimate.material == 0


def test_line_formula() -> None:
    cuf = pycuf.read(
        xml(
            '<BEGROTINGSREGEL BTW="21" HOEVEELHEID="2.5" HOEVEELHEID_FACTOR="1.10" '
            'UUR_NORM="0.5" UUR_TARIEF="40" MATERIAALPRIJS="3" MATERIEELPRIJS="1" '
            'ONDERAANNEMINGSPRIJS="4" OVERIGE_KOSTEN="0.5" AANTAL="2" INZET="5"/>'
        )
    )
    c = cuf.totals()[cuf.lines[0]]
    q = Decimal("2.75")
    assert c.hours == q * Decimal("0.5")
    assert c.labour == q * Decimal("0.5") * 40
    assert (c.material, c.equipment, c.subcontracting, c.other) == (q * 3, q, q * 4, q / 2)
    assert c.total == c.labour + q * Decimal("8.5")  # AANTAL × INZET is informative only


def test_resources_fallback_and_labour_rules() -> None:
    lines = (
        '<BEGROTINGSREGEL BTW="21" HOEVEELHEID="100">'
        '<MAMO_REGEL KOSTENSOORT="LOON" HOEVEELHEID="50" PRIJS="45"/>'
        '<MAMO_REGEL KOSTENSOORT="MATERIAAL" HOEVEELHEID="100" PRIJS="2" PRIJS_FACTOR="1.1"/>'
        "</BEGROTINGSREGEL>"
    )
    cuf = pycuf.read(xml(lines))
    spec = cuf.totals()
    assert spec.priced_by_resources(cuf.lines[0])
    assert spec.estimate.labour == 0 and spec.estimate.material == Decimal("220.0")
    assert "CUF5006" in {f.code for f in spec.findings}
    erp = cuf.totals(policy=ERP)
    assert erp.estimate.hours == 50 and erp.estimate.labour == 2250
    assert cuf.totals(policy=SCHEMA).estimate.total == 0
    per_unit = cuf.totals(policy=Policy(resource_basis="per-unit"))
    assert per_unit.estimate.material == Decimal("22000.0")


def test_spec_labour_resource() -> None:
    lines = (
        '<BEGROTINGSREGEL BTW="21" HOEVEELHEID="1">'
        '<MAMO_REGEL KOSTENSOORT="LOON" HOEVEELHEID="10" UUR_NORM="2" UUR_TARIEF="30" '
        'PRIJS_FACTOR="1.5"/></BEGROTINGSREGEL>'
    )
    cuf = pycuf.read(xml(lines))
    r = cuf.totals().resource(cuf.resource_lines[0])
    assert (r.hours, r.labour) == (20, 900)


def test_resource_mismatch_is_reported(estimate: cufgen.Estimate) -> None:
    lines = (
        '<BEGROTINGSREGEL CODE="x" BTW="21" HOEVEELHEID="10" MATERIAALPRIJS="5">'
        '<MAMO_REGEL KOSTENSOORT="MATERIAAL" HOEVEELHEID="10" PRIJS="4"/></BEGROTINGSREGEL>'
    )
    cuf = pycuf.read(xml(lines))
    assert cuf.totals().estimate.material == 50  # the line is leading
    assert "CUF5004" in {f.code for f in cuf.validate().findings}
    preferred = cuf.totals(policy=Policy(resources="prefer"))
    assert preferred.estimate.material == 40


def test_stated_totals_checks(estimate: cufgen.Estimate) -> None:
    wrong = pycuf.read(cufgen.write(estimate, totals="wrong")).validate()
    assert {"CUF5001", "CUF5002"} <= {f.code for f in wrong.findings}
    zero = pycuf.read(cufgen.write(estimate, totals="zero")).validate()
    found = [f.code for f in zero.findings]
    assert "CUF5003" in found and "CUF5001" not in found
    absent = pycuf.read(cufgen.write(estimate, totals="absent")).validate()
    assert "CUF5001" not in {f.code for f in absent.findings}


def test_tolerance() -> None:
    stated = (
        'UREN="0" LOONKOSTEN="0" MATERIAALKOSTEN="10.004" MATERIEELKOSTEN="0" '
        'ONDERAANNEMING="0" OVERIGE_KOSTEN="0"'
    )
    cuf = pycuf.read(
        xml('<BEGROTINGSREGEL BTW="21" HOEVEELHEID="1" MATERIAALPRIJS="10"/>', totals=stated)
    )
    assert "CUF5002" not in {f.code for f in cuf.validate().findings}
    strict = cuf.validate(policy=Policy(abs_tol=Decimal(0)))
    assert "CUF5002" in {f.code for f in strict.findings}


def test_contract_sum(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate))
    assert "CUF5005" not in {f.code for f in cuf.validate().findings}
    data = cufgen.write(estimate).replace(b'AANNEEMSOM="', b'AANNEEMSOM="1')
    assert "CUF5005" in {f.code for f in pycuf.read(data).validate().findings}


def test_exact_regardless_of_caller_context(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate))
    with decimal.localcontext(prec=6):
        low = cuf.totals(policy=Policy(abs_tol=Decimal("0.02"))).estimate
    assert low.total == sum(estimate.expected()[k] for k in COST_FIELDS[1:])


def test_totals_cache_and_foreign_nodes(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate), policy="erp")
    assert cuf.totals() is cuf.totals(policy=ERP)
    assert cuf.totals().policy is ERP
    other = pycuf.read(cufgen.write(estimate))
    with pytest.raises(KeyError):
        cuf.totals()[other.lines[0]]

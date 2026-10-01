from __future__ import annotations

import json

import cufgen
import pytest

import pycuf
from pycuf import Severity


def test_report_shape(estimate: cufgen.Estimate) -> None:
    report = pycuf.validate(cufgen.write(estimate, "dataviewers"), policy="erp")
    assert not report.ok and report.errors
    assert report.max_severity is Severity.ERROR
    severities = [f.severity for f in report.findings]
    assert severities == sorted(severities, reverse=True)
    data = json.loads(report.to_json())
    assert data["schema_version"] == 1 and data["policy"]["labour"] == "erp"
    assert data["stats"]["lines"] == len(estimate.lines())
    assert "CUF3010" in str(report)


def test_clean_file(estimate: cufgen.Estimate) -> None:
    report = pycuf.validate(cufgen.write(estimate))
    assert report.ok and not report.warnings
    assert {f.code for f in report.findings} == {"CUF3001"}


def test_overrides_on_validate(estimate: cufgen.Estimate) -> None:
    cuf = pycuf.read(cufgen.write(estimate, totals="wrong"))
    report = cuf.validate(severity_overrides={"CUF5001": None, "CUF5002": Severity.ERROR})
    codes = {f.code: f.severity for f in report.findings}
    assert "CUF5001" not in codes and codes["CUF5002"] is Severity.ERROR


def test_finding_str_and_dict() -> None:
    f = pycuf.Finding(code="CUF3018", severity=Severity.ERROR, message="bad", line=3, value="x")
    assert str(f) == "line 3 ERROR CUF3018 bad ['x']"
    assert f.to_dict()["severity"] == "ERROR" and f.title == "Invalid number"


def test_limits_never_change_the_verdict() -> None:
    report = pycuf.validate(b"<CUF/>", max_findings=1)
    assert len(report.findings) == 1 and report.suppressed == 4
    assert not report.ok and report.max_severity is Severity.ERROR
    assert report.severity_counts == {"ERROR": 4, "WARNING": 0, "INFO": 1}
    assert report.to_dict()["ok"] is False
    assert str(report).startswith("<bytes>: 4 error(s), 0 warning(s), 1 info (4 not listed")
    quiet = pycuf.validate(b"<CUF/>", max_findings_per_code=0)
    assert not quiet.findings and not quiet.ok
    silenced = pycuf.validate(
        b"<CUF/>", max_findings=1, severity_overrides={"CUF3010": None, "CUF3016": None}
    )
    assert silenced.ok and silenced.severity_counts["ERROR"] == 0


def test_late_error_after_many_harmless_findings() -> None:
    attrs = " ".join(f'X{i}="v"' for i in range(100))
    data = (
        '<CUF AANMAAKDATUMTIJD="2026-01-01T00:00:00">'
        '<PROJECTGEGEVENS CUF_VERSIE="4.003" AANMAAKDATUM="2026-01-01" VALUTA="EUR"/>'
        f"<BEGROTING><BEGROTINGSREGEL {attrs}/></BEGROTING></CUF>"
    ).encode()
    report = pycuf.validate(data, max_findings=100)
    assert report.counts["CUF3016"] and not report.ok


def test_negative_limits_are_refused() -> None:
    with pytest.raises(ValueError, match="max_findings"):
        pycuf.validate(b"<CUF/>", max_findings=-1)

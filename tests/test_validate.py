from __future__ import annotations

import json

import cufgen

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

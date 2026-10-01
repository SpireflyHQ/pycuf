from __future__ import annotations

import json
from pathlib import Path

import cufgen
import pytest

typer_testing = pytest.importorskip("typer.testing")
pytestmark = pytest.mark.extras

from pycuf.cli import app  # noqa: E402

runner = typer_testing.CliRunner()


@pytest.fixture
def files(tmp_path: Path, estimate: cufgen.Estimate) -> dict[str, Path]:
    out = {}
    for name, data in {
        "ok": cufgen.write(estimate),
        "bad": cufgen.write(estimate, "dataviewers"),
        "wrong": cufgen.write(estimate, totals="wrong"),
    }.items():
        out[name] = tmp_path / f"{name}.xml"
        out[name].write_bytes(data)
    return out


def test_info(files: dict[str, Path]) -> None:
    result = runner.invoke(app, ["info", str(files["ok"])])
    assert result.exit_code == 0 and "estimate style" in result.output
    data = json.loads(runner.invoke(app, ["info", str(files["ok"]), "--output", "json"]).output)
    assert data["cuf_version"] == "4.003" and data["computed"]["total"]


def test_validate_exit_codes(files: dict[str, Path]) -> None:
    assert runner.invoke(app, ["validate", str(files["ok"])]).exit_code == 0
    assert runner.invoke(app, ["validate", str(files["bad"])]).exit_code == 2
    assert runner.invoke(app, ["validate", str(files["wrong"])]).exit_code == 0
    assert runner.invoke(app, ["validate", "--strict", str(files["wrong"])]).exit_code == 1
    out = runner.invoke(app, ["validate", "--output", "json", str(files["ok"]), str(files["bad"])])
    assert len(json.loads(out.output)) == 2


def test_totals_and_export(files: dict[str, Path], tmp_path: Path) -> None:
    result = runner.invoke(app, ["totals", str(files["wrong"]), "--depth", "1"])
    assert result.exit_code == 0 and "≠ stated" in result.output
    data = json.loads(runner.invoke(app, ["totals", str(files["ok"]), "--output", "json"]).output)
    assert data["bundles"] and data["estimate_style"] == "traditional"
    result = runner.invoke(
        app, ["export", str(files["ok"]), "-o", str(tmp_path / "out"), "-t", "lines"]
    )
    assert result.exit_code == 0 and (tmp_path / "out" / "lines.csv").exists()


def test_failures_and_codes(tmp_path: Path) -> None:
    other = tmp_path / "other.xml"
    other.write_bytes(b"<Calculatie/>")
    result = runner.invoke(app, ["info", str(other)])
    assert result.exit_code == 3
    assert "CUF5001" in runner.invoke(app, ["codes"]).output
    assert json.loads(runner.invoke(app, ["codes", "--output", "json"]).output)[0]["code"]
    assert "pycuf" in runner.invoke(app, ["--version"]).output

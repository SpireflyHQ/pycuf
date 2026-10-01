"""Project metadata stays consistent.

A pre-release (``0.2.0rc1``) uses the CHANGELOG section and CITATION version of the release it
leads to.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_PRE = re.compile(r"(a|b|rc|\.dev)[0-9]+$")


def _release(version: str) -> str:
    """The release a version leads to: ``0.2.0rc1`` → ``0.2.0`` (final versions unchanged)."""
    return _PRE.sub("", version)


def test_citation_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*"?([^"\n]+)"?', citation, re.MULTILINE)
    assert match is not None
    assert match.group(1) == _release(pyproject["project"]["version"])


def test_changelog_has_current_version() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = _release(pyproject["project"]["version"])
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog

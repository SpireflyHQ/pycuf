"""Shared fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import cufgen
import pytest

DIALECTS = ("standard", "ibis", "forum", "dataviewers", "bakkerspees")
CORPUS = Path(os.environ.get("PYCUF_CORPUS", Path(__file__).parent / "corpus"))


@pytest.fixture(scope="session")
def estimate() -> cufgen.Estimate:
    return cufgen.make_estimate(7, resources=True, loose_lines=1)


@pytest.fixture(scope="session")
def element_estimate() -> cufgen.Estimate:
    return cufgen.make_estimate(11, elements=True)


@pytest.fixture(params=DIALECTS)
def dialect(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def corpus_files() -> list[Path]:
    """Real CUF files from the private corpus (never committed; see CONTRIBUTING.md)."""
    if not CORPUS.is_dir():
        return []
    return sorted(p for p in CORPUS.iterdir() if p.suffix.lower() in (".xml", ".cuf", ".txt"))

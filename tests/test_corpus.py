"""Real CUF files from a private corpus.

Real estimates contain client data and commercially sensitive prices, so they are never committed.
Put files in ``tests/corpus/`` (git-ignored) or point ``PYCUF_CORPUS`` at a directory; without
them these tests are skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import corpus_files

import pycuf

FILES = corpus_files()
pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not FILES, reason="no private corpus (set PYCUF_CORPUS)"),
]


@pytest.mark.parametrize("path", FILES, ids=[p.name for p in FILES])
def test_reads_and_validates(path: Path) -> None:
    cuf = pycuf.read(path)
    assert cuf.lines
    report = cuf.validate()
    assert report.stats["lines"] == len(cuf.lines)
    assert not [f for f in report.findings if f.code.startswith("CUF2")]
    rows = list(cuf.tables["lines"].rows())
    assert len(rows) == len(cuf.lines)

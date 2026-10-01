"""The Python examples in the README and the tutorial print exactly the output they show.

Every ```python block that is directly followed by a ```text block is run, in document order and
in one namespace, in a folder holding the example files; its stdout must equal the text block.
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "docs" / "getting-started.md"]
_PAIR = re.compile(r"```python\n((?:(?!```).)*?)```[ \t]*\n+```text\n((?:(?!```).)*?)```", re.S)


def _pairs(path: Path) -> list[tuple[str, str]]:
    return _PAIR.findall(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_examples_print_what_they_show(
    doc: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pairs = _pairs(doc)
    assert pairs, f"no python/text example pairs in {doc.name}"
    if any("duckdb" in code for code, _ in pairs):
        pytest.importorskip("duckdb")
        pytest.importorskip("nanoarrow")
    for name in ("begroting.xml", "begroting-ibis.xml"):
        shutil.copy(ROOT / "examples" / name, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    namespace: dict[str, object] = {}
    for code, expected in pairs:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(code, str(doc), "exec"), namespace)
        assert out.getvalue().rstrip() == expected.rstrip(), code

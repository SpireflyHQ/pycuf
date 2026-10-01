"""Generate the synthetic sample files in ``examples/`` (used by the README quickstart).

uv run python scripts/gen_examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import cufgen  # noqa: E402


def main() -> None:
    est = cufgen.make_estimate(2026, n_bundles=3, depth=2, lines_per_bundle=2, resources=True)
    good = cufgen.write(est)
    (ROOT / "examples" / "begroting.xml").write_bytes(good)
    (ROOT / "examples" / "begroting-ibis.xml").write_bytes(
        cufgen.write(est, "ibis", totals="wrong")
    )
    for path in sorted((ROOT / "examples").glob("*.xml")):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

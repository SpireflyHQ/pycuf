"""Property tests: generated estimates read back with exactly the expected totals."""

from __future__ import annotations

import contextlib
import random

import cufgen
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import pycuf
from pycuf.models import COST_FIELDS


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    seed=st.integers(0, 10_000),
    depth=st.integers(1, 3),
    elements=st.booleans(),
    dialect=st.sampled_from(["standard", "ibis", "forum"]),
)
def test_totals_roundtrip(seed: int, depth: int, elements: bool, dialect: str) -> None:
    est = cufgen.make_estimate(seed, depth=depth, elements=elements, n_bundles=2, loose_lines=1)
    cuf = pycuf.read(cufgen.write(est, dialect))
    computed = cuf.totals().estimate
    expected = est.expected()
    assert all(getattr(computed, k) == expected[k] for k in COST_FIELDS)
    report = cuf.validate()
    assert report.ok
    assert not [f for f in report.findings if f.code.startswith("CUF5")]


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(0, 10_000))
def test_order_does_not_change_totals(seed: int) -> None:
    est = cufgen.make_estimate(seed)
    before = pycuf.read(cufgen.write(est)).totals().estimate
    random.Random(seed).shuffle(est.children)
    after = pycuf.read(cufgen.write(est)).totals().estimate
    assert before == after


@settings(max_examples=200, deadline=None)
@given(data=st.binary(max_size=300))
def test_arbitrary_bytes_only_raise_pycuf_errors(data: bytes) -> None:
    with contextlib.suppress(pycuf.PycufError, ValueError):
        pycuf.read(b"<CUF>" + data + b"</CUF>")

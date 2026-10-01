"""The decimal context pycuf computes in, whatever the caller's own context is.

``decimal`` arithmetic takes its precision, rounding, exponent limits and traps from the current
context, which belongs to the caller. Every pycuf computation that a caller can reach (totals,
derived properties, comparisons, formatting) therefore runs in a copy of :data:`CONTEXT`.
"""

from __future__ import annotations

import decimal
import functools
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import ParamSpec, TypeVar

__all__ = ["CONTEXT", "PRECISION", "context", "in_context"]

PRECISION = 60
"""Significant digits of the computations; real estimates need fewer than 30, so results are
exact."""

CONTEXT = decimal.Context(
    prec=PRECISION,
    rounding=decimal.ROUND_HALF_EVEN,
    Emin=decimal.MIN_EMIN,
    Emax=decimal.MAX_EMAX,
    capitals=1,
    clamp=0,
    flags=[],
    traps=[decimal.InvalidOperation, decimal.DivisionByZero, decimal.Overflow],
)
"""Precision :data:`PRECISION`, half-even rounding and the widest exponent range: the bounded
inputs (see :func:`pycuf.values.in_range`) can neither overflow nor underflow."""

_P = ParamSpec("_P")
_R = TypeVar("_R")


def context() -> AbstractContextManager[decimal.Context]:
    """Run the ``with`` block in a fresh copy of :data:`CONTEXT`."""
    return decimal.localcontext(CONTEXT)


def in_context(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """Decorate ``func`` to run in a fresh copy of :data:`CONTEXT`."""

    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        with decimal.localcontext(CONTEXT):
            return func(*args, **kwargs)

    return wrapper

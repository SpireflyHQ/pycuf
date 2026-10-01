"""pycuf: read, check and analyse CUF-XML construction cost estimates.

CUF-XML (*Calculatie Uitwissel Formaat*) is the Dutch exchange format for construction cost
estimates (begrotingen), version 4.003. pycuf reads it into a typed model, computes costs under
an explicit :class:`~pycuf.policy.Policy`, reports every problem as a coded finding, and exports
normalized tables. The core has no dependencies outside the standard library.

Example:
    >>> import pycuf
    >>> cuf = pycuf.read("begroting.xml")                     # doctest: +SKIP
    >>> totals = cuf.totals()                                   # doctest: +SKIP
    >>> totals.estimate.total                                   # doctest: +SKIP
    Decimal('8562.175')
    >>> for finding in cuf.validate().findings:                 # doctest: +SKIP
    ...     print(finding)
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

from . import policy
from .calc import Totals
from .errors import (
    ForbiddenConstructError,
    LimitExceededError,
    MissingExtraError,
    NotCufError,
    PycufError,
    XmlSyntaxError,
)
from .findings import CODES, Finding, Severity
from .models import (
    Bundle,
    Costs,
    CostType,
    Estimate,
    Line,
    Project,
    QuantityLine,
    ResourceLine,
    SortCode,
    SortCodeEntry,
    SortCodeScheme,
    StatedTotals,
    Tail,
    TailItem,
)
from .policy import Policy
from .raw import RawElement
from .reader import CufFile, read
from .validate import ValidationReport, validate

try:
    __version__ = _version("pycuf")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

__all__ = [
    "CODES",
    "Bundle",
    "CostType",
    "Costs",
    "CufFile",
    "Estimate",
    "Finding",
    "ForbiddenConstructError",
    "LimitExceededError",
    "Line",
    "MissingExtraError",
    "NotCufError",
    "Policy",
    "Project",
    "PycufError",
    "QuantityLine",
    "RawElement",
    "ResourceLine",
    "Severity",
    "SortCode",
    "SortCodeEntry",
    "SortCodeScheme",
    "StatedTotals",
    "Tail",
    "TailItem",
    "Totals",
    "ValidationReport",
    "XmlSyntaxError",
    "__version__",
    "policy",
    "read",
    "validate",
]

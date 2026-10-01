"""Input sources: paths, bytes and binary streams, read completely with a size limit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TypeAlias, cast

from .errors import LimitExceededError

__all__ = ["DEFAULT_MAX_SIZE", "Source", "SourceLike", "read_source"]

SourceLike: TypeAlias = "str | os.PathLike[str] | bytes | bytearray | memoryview | BinaryIO"
"""What :func:`pycuf.read` accepts: a path, the raw bytes, or a binary file object."""

DEFAULT_MAX_SIZE = 256 * 1024 * 1024
"""Default input size limit (256 MiB). Real CUF files are rarely larger than a few megabytes."""


@dataclass(frozen=True, slots=True)
class Source:
    """The complete content of an input, with a display name."""

    name: str
    data: bytes


def read_source(source: SourceLike, *, max_size: int | None = DEFAULT_MAX_SIZE) -> Source:
    """Read ``source`` completely.

    Args:
        source: Path, raw bytes or a binary file object (opened in ``"rb"`` mode). Streams are
            read from their current position and never closed.
        max_size: Refuse inputs larger than this many bytes (``None`` = unlimited).

    Raises:
        FileNotFoundError: The path does not exist.
        LimitExceededError: The input is larger than ``max_size``.
        TypeError: ``source`` is of an unsupported type, or a text stream.
    """
    if isinstance(source, (bytes, bytearray, memoryview)):
        data = bytes(source)
        name = "<bytes>"
    elif isinstance(source, (str, os.PathLike)):
        path = Path(source)
        name = str(path)
        if not path.is_file():
            raise FileNotFoundError(name)
        if max_size is not None and path.stat().st_size > max_size:
            raise LimitExceededError(
                f"{name}: file is larger than the limit of {max_size:,} bytes "
                "(pass a larger max_size if this file is legitimate)"
            )
        data = path.read_bytes()
    elif hasattr(source, "read"):
        stream = source
        name = str(getattr(stream, "name", "<stream>"))
        chunk = stream.read(-1 if max_size is None else max_size + 1)
        if not isinstance(cast("object", chunk), bytes):
            raise TypeError("pycuf needs a binary stream; open the file in 'rb' mode")
        data = chunk
    else:
        raise TypeError(f"unsupported source type {type(source).__name__}")
    if max_size is not None and len(data) > max_size:
        raise LimitExceededError(
            f"{name}: input is larger than the limit of {max_size:,} bytes "
            "(pass a larger max_size if this input is legitimate)"
        )
    return Source(name, data)

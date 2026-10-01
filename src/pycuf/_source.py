"""Input sources: paths, bytes and binary streams, read completely with a size limit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, TypeAlias, cast

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
        BlockingIOError: ``source`` is a non-blocking stream without data available.
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
        with path.open("rb") as fh:  # the file may have grown since stat()
            data = _read_all(fh, name, max_size)
    elif hasattr(source, "read"):
        name = str(getattr(source, "name", "<stream>"))
        data = _read_all(source, name, max_size)
    else:
        raise TypeError(f"unsupported source type {type(source).__name__}")
    if max_size is not None and len(data) > max_size:
        raise LimitExceededError(
            f"{name}: input is larger than the limit of {max_size:,} bytes "
            "(pass a larger max_size if this input is legitimate)"
        )
    return Source(name, data)


def _read_all(stream: Any, name: str, max_size: int | None) -> bytes:
    """Read ``stream`` to its end, but never more than ``max_size + 1`` bytes.

    Raw (unbuffered) streams such as pipes and sockets may return fewer bytes than asked for
    before the end, so this reads until ``read`` returns ``b""``.
    """
    chunks: list[bytes] = []
    total = 0
    while max_size is None or total <= max_size:
        want = -1 if max_size is None else max_size + 1 - total
        chunk = stream.read(want)
        if chunk is None:
            raise BlockingIOError(f"{name}: the non-blocking stream has no data available")
        if not isinstance(cast("object", chunk), bytes):
            raise TypeError("pycuf needs a binary stream; open the file in 'rb' mode")
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)

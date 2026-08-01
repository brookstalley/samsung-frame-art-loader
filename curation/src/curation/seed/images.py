"""Measuring an image file, using only what the standard library can read.

Everything the catalogue records about a file is taken **from the file**, never
from the index that points at it. The index carries its own copy of each master's
pixel size, and a copy is a value that can drift from what it describes — the
file is the thing a render is actually made from, so it is the thing measured.

Only JPEG is understood, and that is enough: every master and every finished
render the 2024 pipeline produced is one. A file this cannot read is reported
rather than guessed at, because a wrong size here would be recorded as a fact
about the image and would silently misjudge whether it is large enough for the
wall.
"""

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Final

#: How much of a file to hash at a time. Masters run to tens of megabytes and
#: there is no reason to hold one in memory to identify it.
_CHUNK_BYTES: Final[int] = 1024 * 1024

#: The algorithm, carried in the value. A hash with no algorithm beside it cannot
#: be re-derived once the algorithm changes, and the column exists precisely to
#: be compared against a later re-derivation.
_ALGORITHM: Final[str] = "sha256"

#: Frame markers whose payload begins with the image's height and width. The
#: excluded three sit inside the same numeric range and mean something else
#: entirely — Huffman table, arithmetic conditioning, restart interval.
_SIZE_FRAMES: Final[frozenset[int]] = frozenset(set(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC})

#: Markers that stand alone: they carry no length field, so a reader that tried
#: to skip a payload after one would lose its place in the stream.
_STANDALONE: Final[frozenset[int]] = frozenset({0x01, *range(0xD0, 0xD8)})


@dataclass(frozen=True, slots=True)
class ImageFacts:
    """What a file itself says about the image it holds."""

    width: int
    height: int
    byte_size: int
    content_hash: str


def read_image_facts(path: Path) -> ImageFacts | None:
    """Measure the image at `path`, or return None if it cannot be read as one.

    A zero-length file returns None with everything else: it is the 2024
    pipeline's known download failure, indistinguishable from a good file by
    name, and it has no dimensions to find either.
    """
    try:
        byte_size = path.stat().st_size
    except OSError:
        return None
    if byte_size <= 0:
        return None
    try:
        with path.open("rb") as stream:
            size = _jpeg_dimensions(stream)
            if size is None:
                return None
            stream.seek(0)
            content_hash = _digest(stream)
    except OSError:
        return None
    return ImageFacts(width=size[0], height=size[1], byte_size=byte_size, content_hash=content_hash)


def _digest(stream: BinaryIO) -> str:
    digest = hashlib.new(_ALGORITHM)
    while chunk := stream.read(_CHUNK_BYTES):
        digest.update(chunk)
    return f"{_ALGORITHM}:{digest.hexdigest()}"


def _jpeg_dimensions(stream: BinaryIO) -> tuple[int, int] | None:
    """Walk the segment headers to the frame that states the image's size."""
    if stream.read(2) != b"\xff\xd8":
        return None
    while True:
        marker = _next_marker(stream)
        if marker is None:
            return None
        if marker in _SIZE_FRAMES:
            # Length, then one byte of sample precision, then height and width.
            if len(stream.read(3)) != 3:
                return None
            payload = stream.read(4)
            if len(payload) != 4:
                return None
            height, width = struct.unpack(">HH", payload)
            return (width, height) if width and height else None
        if marker in _STANDALONE:
            continue
        header = stream.read(2)
        if len(header) != 2:
            return None
        length = struct.unpack(">H", header)[0]
        if length < 2:
            return None
        stream.seek(length - 2, 1)


def _next_marker(stream: BinaryIO) -> int | None:
    """The next segment marker, skipping the fill bytes that may precede one."""
    while True:
        byte = stream.read(1)
        if not byte:
            return None
        if byte != b"\xff":
            continue
        while byte == b"\xff":
            byte = stream.read(1)
            if not byte:
                return None
        if byte != b"\x00":
            return byte[0]

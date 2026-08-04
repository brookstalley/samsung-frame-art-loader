"""Refuse to start an acquisition that could fill the disk.

Disk-full is the one failure every acquisition path shares, and it is the failure
worth preventing rather than catching, because the thing it takes down is not the
fetch. `catalogue.sqlite` lives on the same device as the image tree; a full disk
during a write is the classic SQLite corruption story, and the catalogue is the
one asset in this product that cannot be re-derived from anywhere.

**So the guard protects the catalogue, not the fetch.** It does not try to predict
how large a work will be — a tiled fetch does not know until it has walked the
grid, and a guess that ran low would refuse good work while a guess that ran high
would pass right before the failure. It asserts a floor of free space that must
still be there afterwards, and refuses to begin when the floor is already breached.

A refusal is a recorded outcome for that work rather than a crash: the run
continues, the source records a failed fetch, and the operator sees a symptom the
runbook already maps to free disk space.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SpaceCheck:
    """What the filesystem reported, and whether that is enough to proceed."""

    free_bytes: int
    required_bytes: int

    @property
    def sufficient(self) -> bool:
        return self.free_bytes >= self.required_bytes

    @property
    def shortfall_bytes(self) -> int:
        return max(0, self.required_bytes - self.free_bytes)


class NotEnoughSpace(RuntimeError):
    """There is not enough headroom to begin, and the message says how much short."""


def check_free_space(path: Path, *, required_bytes: int) -> SpaceCheck:
    """Report free space on the filesystem holding `path`.

    Walks up to the nearest existing ancestor rather than requiring the directory
    to exist: the first acquisition on a fresh deployment is asked about a tree
    nothing has created yet, and answering "no space" because the folder is absent
    would be a wrong answer to the question asked.
    """
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    usage = shutil.disk_usage(target)
    return SpaceCheck(free_bytes=usage.free, required_bytes=required_bytes)


def require_free_space(path: Path, *, required_bytes: int) -> SpaceCheck:
    """Raise `NotEnoughSpace` unless the floor is clear, and say by how much."""
    check = check_free_space(path, required_bytes=required_bytes)
    if not check.sufficient:
        raise NotEnoughSpace(
            f"{_gib(check.free_bytes)} free where {_gib(check.required_bytes)} is required "
            f"({_gib(check.shortfall_bytes)} short); acquisition would risk the catalogue on the same disk."
        )
    return check


def _gib(value: int) -> str:
    """Bytes as the operator reads them — the runbook remedy is stated in GB."""
    return f"{value / (1024**3):.2f} GiB"

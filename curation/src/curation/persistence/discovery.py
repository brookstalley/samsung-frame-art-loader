"""The persistence contract over the pre-acceptance pipeline's records.

The counterpart to `catalogue.py`, and a `Protocol` for the same reason: the
service above binds to what the pipeline can be asked, not to how one file
answers. The two contracts are separate because the concerns are, but they are
served by one open file — acceptance promotes a candidate's instances into a
work's sources, and that has to commit as one transaction.

Implementations own persistence and nothing else: no validation, no derived
values, no state-machine opinion. Every rule about what a valid run or candidate
looks like belongs to the service layer, which is the only caller.
"""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from curation.persistence.discovery_records import (
    CandidateImage,
    CandidateWork,
    DiscoveryRun,
    ResolveRunWork,
    RunKind,
    RunStatus,
    SpendRecord,
)


class DiscoveryStore(Protocol):
    """Everything the pre-acceptance pipeline can be asked of its storage."""

    # -- atomicity ------------------------------------------------------------

    def transaction(self) -> AbstractContextManager[None]:
        """Group several writes so they commit together or not at all.

        The same capability the catalogue store offers, and against the same open
        file: acceptance writes on both sides of the pipeline boundary, and a
        promotion interrupted halfway leaves a candidate marked accepted with no
        work to show for it.
        """
        ...

    def close(self) -> None:
        """Release the file. Every store over the same file is closed with it."""
        ...

    # -- runs -----------------------------------------------------------------

    def add_run(self, run: DiscoveryRun) -> None:
        """Persist a run. Raises if the id is already present."""
        ...

    def get_run(self, run_id: str) -> DiscoveryRun | None:
        """Return the run, or None if no such id is stored."""
        ...

    def update_run(self, run: DiscoveryRun) -> None:
        """Overwrite a stored run with this one. Raises if the id is absent."""
        ...

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        """Return matching runs newest first, which is the order they are read in."""
        ...

    # -- candidate works ------------------------------------------------------

    def add_candidate_work(self, work: CandidateWork) -> None:
        """Persist a proposed work. Raises if the id is already present."""
        ...

    def get_candidate_work(self, candidate_work_id: str) -> CandidateWork | None:
        """Return the proposed work, or None if no such id is stored."""
        ...

    def update_candidate_work(self, work: CandidateWork) -> None:
        """Overwrite a stored proposal with this one. Raises if the id is absent."""
        ...

    def list_candidate_works(self, run_id: str) -> Sequence[CandidateWork]:
        """Return a run's proposals in a stable order."""
        ...

    def list_candidate_works_by_dedup_key(self, work_dedup_key: str) -> Sequence[CandidateWork]:
        """Return every proposal ever made for this work identity, across runs.

        This is the read behind work-scoped suppression, so it deliberately spans
        runs: a work declined in March must not come back in April.
        """
        ...

    # -- candidate images -----------------------------------------------------

    def add_candidate_image(self, image: CandidateImage) -> None:
        """Persist an image instance. Raises if the id is already present."""
        ...

    def get_candidate_image(self, candidate_image_id: str) -> CandidateImage | None:
        """Return the instance, or None if no such id is stored."""
        ...

    def update_candidate_image(self, image: CandidateImage) -> None:
        """Overwrite a stored instance with this one. Raises if the id is absent."""
        ...

    def list_candidate_images(self, candidate_work_id: str) -> Sequence[CandidateImage]:
        """Return a work's instances in a stable order, the selected one first."""
        ...

    # -- spend ----------------------------------------------------------------

    def add_spend_record(self, record: SpendRecord) -> None:
        """Persist a cost. Raises if the id is already present."""
        ...

    def list_spend_records(
        self,
        *,
        run_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[SpendRecord]:
        """Return matching costs newest first. Bounds are inclusive of `since`, exclusive of `until`."""
        ...

    # -- resolve-run coverage -------------------------------------------------

    def add_coverage(self, coverage: ResolveRunWork) -> None:
        """Record that a resolve run covers a work. Raises if the pair is already present."""
        ...

    def list_coverage_by_run(self, resolve_run_id: str) -> Sequence[ResolveRunWork]:
        """Return the works a resolve run covers, which is its scope."""
        ...

    def list_coverage_by_work(self, candidate_work_id: str) -> Sequence[ResolveRunWork]:
        """Return every resolve run that has ever covered this work.

        The read behind the double-spend guard: a work is refused to a new
        resolve run while any run covering it is still live.
        """
        ...

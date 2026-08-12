"""Reading a document a job wrote to say it ran, and saying how old it is.

The shared parser behind the health panel — the product's only alerting surface —
so a branch here that nothing exercises is a branch of the one thing that tells an
operator anything at all.

**The units are the point of most of this file.** The panel's whole service is
converting an age into something a person reads without doing arithmetic, and
`observability-strategy.md` names the target wording outright. A boundary that
moved by a factor of sixty would still produce a plausible sentence, which is
exactly the kind of wrong nothing notices.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from curation import observations
from curation.manifest import heartbeat
from curation.persistence import backup


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 seconds ago"),
        (1, "1 second ago"),
        (2, "2 seconds ago"),
        (89, "89 seconds ago"),
        # The boundaries themselves, from both sides. A unit table is read in
        # order, so an off-by-one here reports 90 minutes as an hour and a half
        # of hours as two days — plausible either way, which is why each edge is
        # named rather than sampled.
        (90, "2 minutes ago"),
        (60 * 60, "60 minutes ago"),
        (90 * 60 - 1, "90 minutes ago"),
        (90 * 60, "2 hours ago"),
        (48 * 3600 - 1, "48 hours ago"),
        (48 * 3600, "2 days ago"),
        (4 * 86400, "4 days ago"),
    ],
)
def test_an_age_reads_in_the_unit_a_person_reads_it_in(seconds, expected):
    assert observations.ago(seconds) == expected


def test_the_singular_is_only_ever_reachable_in_seconds():
    """A panel reading "1 days ago" is a panel someone stops trusting.

    **And the plural rule is more general than the thresholds it serves, which is
    worth stating rather than discovering.** Each unit hands over at 90 of the one
    below — 90 seconds reads better than "2 minutes" for the same instant — so the
    minute, hour and day bands all *begin* at a rounded 2 and "1 minute" is
    unreachable by construction. Asserted here so the dead branch is a recorded
    property of the thresholds rather than something a later reader takes for a
    bug, and so that lowering a threshold to 60 turns this red and prompts the
    singular to be checked for real.
    """
    assert observations.in_words(1) == "1 second"
    assert observations.in_words(60) == "60 seconds"
    for band_starts_at in (90, 90 * 60, 48 * 3600):
        assert observations.in_words(band_starts_at).startswith("2 "), band_starts_at


def test_a_document_stamped_ahead_of_this_clock_says_so():
    """Two planes whose clocks disagree is the quiet fault this surface states.

    Folded into zero it reads as "just now" — the most reassuring possible
    rendering of a machine that does not agree with this one about what time it
    is. The magnitude is reported and the direction is named.
    """
    assert observations.in_words(-300) == "5 minutes in the future"
    assert observations.ago(-300) == "5 minutes in the future"
    # Never "ago", which would be the same sentence a correct reading produces.
    assert "ago" not in observations.ago(-300)


def test_the_direction_is_asked_of_the_number_not_of_the_phrase():
    """`ago` must not decide by grepping its own output for "in the future".

    A sentence that reads itself starts saying "ago" the day that wording is
    reworded, and the failure is silent.
    """
    assert observations.ago(-1).endswith("in the future")
    assert observations.ago(1).endswith("ago")


class TestWhatObserveFinds:
    def test_a_path_with_nothing_at_it_is_absent_rather_than_a_problem(self, tmp_path):
        seen = observations.observe(tmp_path / "nothing.json", key="reported_at")
        assert seen.absent is True
        assert seen.problem is None
        assert seen.at is None and seen.age_seconds is None

    def test_a_document_that_will_not_parse_is_a_problem_rather_than_absent(self, tmp_path):
        """Nothing has ever run is normal; a file that will not parse is a fault.

        Collapsing them hides the second behind the first, which on this surface
        means an operator reads a corrupt heartbeat as a plane that has not
        started yet.
        """
        path = tmp_path / "broken.json"
        path.write_text("{not json at all", encoding="utf-8")

        seen = observations.observe(path, key="reported_at")

        assert seen.absent is False
        assert seen.problem is not None
        assert seen.contents is None

    def test_a_document_that_is_not_utf8_is_a_problem_rather_than_an_exception(self, tmp_path):
        """The one malformation that used to take the health panel down with it.

        A reader can catch a document mid-write, and bytes that are not UTF-8
        raise `UnicodeDecodeError` — a `ValueError`, not a `JSONDecodeError`, so
        it escaped the catch, escaped `HealthService.observe`, and reached the
        browser as a 500. The panel that exists to report that a document is
        unreadable is the one thing that must not fail on an unreadable document.
        """
        path = tmp_path / "mid-write.json"
        path.write_bytes(b'{"reported_at": "\xff\xfe not utf-8"}')

        seen = observations.observe(path, key="reported_at")

        assert seen.absent is False
        assert seen.problem is not None
        assert seen.contents is None

    def test_a_document_that_is_not_an_object_is_refused_by_name(self, tmp_path):
        """Valid JSON is not the same as a document. A bare list parses fine."""
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

        seen = observations.observe(path, key="reported_at")

        assert seen.problem == "it does not hold a JSON object."
        assert seen.contents is None

    def test_a_document_missing_its_key_keeps_what_it_does_say(self, tmp_path):
        """The file is real, so dropping its contents would report it as unwritten."""
        path = tmp_path / "no-key.json"
        path.write_text(json.dumps({"tv_connected": False}), encoding="utf-8")

        seen = observations.observe(path, key="reported_at")

        assert seen.absent is False
        assert seen.contents == {"tv_connected": False}
        assert "reported_at" in seen.problem

    def test_a_timestamp_that_is_not_a_string_is_no_timestamp(self, tmp_path):
        path = tmp_path / "numeric.json"
        path.write_text(json.dumps({"reported_at": 1754400000}), encoding="utf-8")

        assert observations.observe(path, key="reported_at").at is None

    def test_a_naive_timestamp_is_read_as_utc(self, tmp_path):
        """The alternative makes the reported age wrong by the machine's offset.

        Wrong quietly: a plane that last reported an hour ago reads as current on
        a machine seven zones over, which is the panel confidently saying the one
        thing it exists to disprove.
        """
        path = tmp_path / "naive.json"
        moment = datetime(2026, 8, 5, 12, 0, 0)
        path.write_text(json.dumps({"reported_at": moment.isoformat()}), encoding="utf-8")

        seen = observations.observe(path, key="reported_at", now=moment.replace(tzinfo=UTC))

        assert seen.age_seconds == 0


class TestTheTwoReadings:
    """Both callers share the parse and differ only in filename, key and sentence."""

    def test_the_heartbeat_and_the_backup_read_different_keys(self, tmp_path):
        """A receipt spelling the other one's key is a reading that never ages.

        Both ends of the backup's contract are ours, unlike the heartbeat's, so
        this cannot drift across planes — but it can drift across chunks, and the
        reader shipped a chunk before the writer.
        """
        stamped = json.dumps({"reported_at": datetime.now(UTC).isoformat()})
        path = tmp_path / backup.BACKUP_RECEIPT_FILENAME
        path.write_text(stamped, encoding="utf-8")

        reading = backup.read(path)

        assert reading.completed_at is None
        assert backup.COMPLETED_AT_KEY in reading.problem

    def test_a_stale_backup_is_stated_in_days(self, tmp_path):
        path = tmp_path / backup.BACKUP_RECEIPT_FILENAME
        path.write_text(
            json.dumps({"completed_at": (datetime.now(UTC) - timedelta(days=6)).isoformat()}),
            encoding="utf-8",
        )

        assert "6 days ago" in backup.read(path).describe()

    def test_a_stale_heartbeat_is_stated_in_days_too(self, tmp_path):
        path = heartbeat.heartbeat_path_in(tmp_path, "a-wall")
        path.write_text(
            json.dumps({"reported_at": (datetime.now(UTC) - timedelta(days=4)).isoformat()}),
            encoding="utf-8",
        )

        assert "4 days ago" in heartbeat.read(path).describe()

    @pytest.mark.parametrize("reading", [heartbeat, backup])
    def test_neither_reading_ever_states_a_verdict(self, reading, tmp_path):
        """Never a green dot, in any of the three states either can be in.

        A word like healthy, ok, fine or degraded appearing here is the panel
        judging rather than reporting — and a verdict computed from a file that
        may simply be young is how a health surface starts lying.
        """
        path = tmp_path / "doc.json"
        sentences = [reading.read(path).describe()]
        path.write_text("{broken", encoding="utf-8")
        sentences.append(reading.read(path).describe())
        key = heartbeat.REPORTED_AT_KEY if reading is heartbeat else backup.COMPLETED_AT_KEY
        path.write_text(json.dumps({key: datetime.now(UTC).isoformat()}), encoding="utf-8")
        sentences.append(reading.read(path).describe())

        for sentence in sentences:
            lowered = sentence.lower()
            assert not any(word in lowered for word in ("healthy", "unhealthy", "degraded", " ok", "fine", "stale"))

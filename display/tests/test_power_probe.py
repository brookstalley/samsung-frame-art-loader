"""The power probe is the instrument a measurement chunk depends on, so it is tested.

**Two reasons, and the second is the one that matters.**

The first is the reason `test_tools.py` exists at all: a tool nothing imports is a
tool the suite, the linter and the type checker all agree is fine, right up until
the operator runs it at the set with the daemon stopped — the most expensive place
this product has to find a defect, and here the *only* place, since the sitting it
serves cannot be repeated cheaply.

The second is that this tool has two guards which exist to stop harm rather than to
be convenient, and neither is exercised by running it:

- **it refuses to send a power key without `--i-am-at-the-set`**, because it presses
  power on a real television and one measurement is deliberately taken from the
  television state — the state `nonfunctional-requirements.md` § The television
  belongs to whoever is using it forbids shipped code to press at, legitimate here
  only because somebody is standing in front of the set; and
- **it refuses to write the art channel's token file**, because both channels
  rewrite whatever token file they are handed on every successful open, so sharing
  one is how a measurement sitting ends with a wall that cannot reach its own
  television — at the daemon's next reconnect, long after the run that caused it.

A guard enforced only by its docstring is a guard enforced by whoever read most
carefully that day. **The foreign library is stubbed at the seam, not skipped**: what
is under test is this tool's own wiring and its refusals, which have nothing to do
with whether a television is on the network.
"""

import asyncio
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"


@pytest.fixture
def probe_module(monkeypatch):
    """The tool, imported the way `test_tools.py` imports its sibling."""
    monkeypatch.syspath_prepend(str(TOOLS))
    monkeypatch.delitem(sys.modules, "power_probe", raising=False)

    import power_probe as module

    return module


@pytest.fixture
def deployment(monkeypatch, tmp_path):
    """A hermetic `.env` road, for the same reason `test_tools.py` has one.

    `display.config.load` calls `load_dotenv()`, which reads the repo-root `.env` —
    gitignored, absent in CI, and present with different contents on the Pi and on
    a developer's machine. A test that depended on it would pass on exactly one
    machine and say nothing about the code on any other.
    """
    from display import config

    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for name, value in (
        ("ART_ROOT", str(tmp_path)),
        ("WALL_ID", "living-room"),
        ("TV_ADDRESS", "10.0.0.2"),
        ("LATITUDE", "45.68"),
        ("LONGITUDE", "-111.04"),
        ("LOCATION_NAME", "Bozeman"),
    ):
        monkeypatch.setenv(name, value)
    return tmp_path


def _next_scripted(values, *, cycle):
    """Take the next scripted answer, and decide what happens past the end.

    **Neither mode may run out**, because the settling loop's sample count is a
    property of its own timing rather than of anything under test — and `Probe.read`
    reports every exception as an unreadable reading, so a double that raised when
    exhausted would surface a broken test as a plausible-looking `UNKNOWN`.

    The two modes model the two things a set can be doing:

    - **hold** (default) repeats the last value, which is a set that has settled;
    - **cycle** starts the sequence again, which is a set that has *not* — the only
      way to test the never-settled report deterministically, since a holding
      double reaches three identical samples the moment the script runs dry, and
      that arrives sooner the faster the loop spins.
    """
    if not values:
        return None
    if len(values) == 1 and not cycle:
        return values[0]
    value = values.pop(0)
    if cycle:
        values.append(value)
    return value


class FakeArt:
    """The art channel, answering a scripted sequence of art-mode readings.

    A *sequence* rather than a value, because what this tool measures is a
    transition: a double that answered consistently could not express the
    intermediate state the whole exercise is looking for, and a test built on one
    would pass while the tool reported only where the set ended up.
    """

    def __init__(self, modes, *, alive=True, cycle=False):
        self._modes = list(modes)
        self._alive = alive
        self._cycle = cycle
        self.closed = False

    async def get_artmode(self):
        value = _next_scripted(self._modes, cycle=self._cycle)
        if isinstance(value, Exception):
            raise value
        return value

    def is_alive(self):
        return self._alive

    async def close(self):
        self.closed = True


class FakeRemote:
    """The remote-control channel, recording what was sent to it and nothing else."""

    def __init__(self):
        self.sent = []
        self.closed = False

    async def send_command(self, command):
        self.sent.append(command)

    async def send_commands(self, commands):
        self.sent.extend(commands)

    async def close(self):
        self.closed = True


def wire(monkeypatch, module, *, power_states, art_modes, alive=True, cycle=False):
    """Stand the two channels and the REST endpoint up in memory.

    Patched on `Probe` rather than injected, because the tool's constructor is its
    CLI: giving it a seam for tests to pass fakes through would be a seam no real
    invocation uses, which is the shape of a fixture that cannot fail.
    """
    art = FakeArt(art_modes, alive=alive, cycle=cycle)
    remote = FakeRemote()
    states = list(power_states)

    async def open_(self):
        return None

    async def device_info(self):
        value = _next_scripted(states, cycle=cycle)
        if isinstance(value, Exception):
            raise value
        return {"device": {"PowerState": value, "name": "The Frame", "modelName": "24_PONTUSM_FTV"}}

    async def art_channel(self):
        self._art = art
        return art

    async def remote_channel(self):
        self._remote = remote
        return remote

    monkeypatch.setattr(module.Probe, "open", open_)
    monkeypatch.setattr(module.Probe, "device_info", device_info)
    monkeypatch.setattr(module.Probe, "_art_channel", art_channel)
    monkeypatch.setattr(module.Probe, "_remote_channel", remote_channel)
    return art, remote


FAST = ["--sample-interval", "0", "--settle", "5"]


class TestItRefusesToPressWithoutTheOperator:
    """The guard between this tool and an unattended press."""

    def test_a_click_without_the_flag_is_refused(self, probe_module, deployment):
        with pytest.raises(SystemExit) as exit_:
            probe_module.main(["--click"])
        assert exit_.value.code == 2

    def test_a_hold_without_the_flag_is_refused(self, probe_module, deployment):
        with pytest.raises(SystemExit) as exit_:
            probe_module.main(["--hold", "3"])
        assert exit_.value.code == 2

    def test_the_refusal_names_the_flag_and_says_why(self, probe_module, deployment, capsys):
        with pytest.raises(SystemExit):
            probe_module.main(["--click"])
        complaint = capsys.readouterr().err
        assert "--i-am-at-the-set" in complaint
        assert "television state" in complaint, "it refused without saying which state makes this dangerous"

    def test_nothing_is_sent_when_the_flag_is_missing(self, probe_module, deployment, monkeypatch):
        """The refusal is not merely a message — no key reaches the channel."""
        _, remote = wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])
        with pytest.raises(SystemExit):
            probe_module.main(["--click"])
        assert remote.sent == []

    def test_the_two_gestures_may_not_be_measured_in_one_run(self, probe_module, deployment, capsys):
        """Timing two transitions in one window would attribute the second to the first."""
        with pytest.raises(SystemExit):
            probe_module.main(["--click", "--hold", "3", "--i-am-at-the-set"])
        assert "one per run" in capsys.readouterr().err


class TestItWillNotWriteTheWallsOwnToken:
    """The other harm-preventing guard: the daemon's pairing is not the probe's to spend."""

    def test_the_derived_remote_token_file_is_not_the_art_channels(self, probe_module, deployment):
        args = probe_module.main.__globals__["argparse"].Namespace(
            host=None,
            port=None,
            client_name=None,
            timeout=None,
            remote_token_file=None,
            art_token_file=None,
        )
        parser = probe_module.argparse.ArgumentParser()
        assert probe_module._settings_into(args, parser)
        assert args.remote_token_file != args.art_token_file
        assert args.art_token_file is not None, "it did not find the deployment's own token file"

    def test_it_refuses_when_told_to_share_one_file(self, probe_module, deployment, capsys):
        shared = deployment / "token_file"
        with pytest.raises(SystemExit):
            probe_module.main(
                [
                    "--remote-token-file",
                    str(shared),
                    "--art-token-file",
                    str(shared),
                ]
            )
        complaint = capsys.readouterr().err
        assert "must not be the art channel's token file" in complaint

    def test_it_refuses_with_no_set_to_probe(self, probe_module, monkeypatch, capsys):
        """No fallback address. Naming one here would point the instrument at a wall nobody asked about."""
        from display import config

        monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
        monkeypatch.delenv("TV_ADDRESS", raising=False)
        monkeypatch.delenv("ART_ROOT", raising=False)
        with pytest.raises(SystemExit):
            probe_module.main([])
        assert "TV_ADDRESS" in capsys.readouterr().err


class TestItReadsTheThreeStatesApart:
    """The mapping Chunk 25 will implement, checked here so the sitting can trust the report."""

    @pytest.mark.parametrize(
        ("power", "art", "expected"),
        [
            ("standby", "off", "DARK"),
            ("on", "off", "TELEVISION"),
            ("on", "on", "ART"),
        ],
    )
    def test_each_state_comes_from_its_own_pair_of_readings(
        self, probe_module, deployment, monkeypatch, capsys, power, art, expected
    ):
        wire(monkeypatch, probe_module, power_states=[power], art_modes=[art])
        assert probe_module.main([*FAST]) == 0
        assert f"→ {expected}" in capsys.readouterr().out

    def test_dark_does_not_depend_on_the_art_channel_answering(self, probe_module, deployment, monkeypatch, capsys):
        """In the dark state the art channel is commonly unreachable, and `standby` still means dark."""
        wire(monkeypatch, probe_module, power_states=["standby"], art_modes=[RuntimeError("no channel")])
        assert probe_module.main([*FAST]) == 0
        assert "→ DARK" in capsys.readouterr().out

    def test_an_unreadable_power_state_is_unknown_and_never_a_guess(self, probe_module, deployment, monkeypatch, capsys):
        wire(monkeypatch, probe_module, power_states=[RuntimeError("unreachable")], art_modes=["on"])
        assert probe_module.main([*FAST]) == 0
        printed = capsys.readouterr().out
        assert "→ UNKNOWN" in printed
        assert "ART" not in printed.split("→")[1], "art mode on the art channel was taken as the answer"

    def test_a_lit_set_whose_art_mode_is_unreadable_is_unknown_not_television(
        self, probe_module, deployment, monkeypatch, capsys
    ):
        """`on` plus an unreadable art reading is the *ambiguous* case, and ambiguity is not television.

        This is the one that matters downstream: `TELEVISION` and `UNKNOWN` are both
        states a press is refused at, but reporting one as the other would put a
        measured cell in the table that was never measured.
        """
        wire(monkeypatch, probe_module, power_states=["on"], art_modes=[RuntimeError("dropped")])
        assert probe_module.main([*FAST]) == 0
        assert "→ UNKNOWN" in capsys.readouterr().out


class TestItReportsWhatATransitionDid:
    def test_a_read_only_run_sends_nothing_and_says_so(self, probe_module, deployment, monkeypatch, capsys):
        _, remote = wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])
        assert probe_module.main([*FAST]) == 0
        assert remote.sent == []
        assert "no gesture asked for" in capsys.readouterr().out

    def test_a_click_reaches_the_remote_channel(self, probe_module, deployment, monkeypatch, capsys):
        _, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        assert len(remote.sent) == 1
        assert "KEY_POWER click" in capsys.readouterr().out

    def test_a_hold_is_sent_as_press_sleep_release(self, probe_module, deployment, monkeypatch, capsys):
        """Three frames, not one — the library's own framing, so the sitting measures what ships."""
        _, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--hold", "3", "--i-am-at-the-set"]) == 0
        assert len(remote.sent) == 3
        assert "held 3" in capsys.readouterr().out

    def test_it_reports_the_moment_the_readings_hold_still(self, probe_module, deployment, monkeypatch, capsys):
        wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        assert "settled at" in capsys.readouterr().out

    def test_a_transition_that_never_settles_is_a_finding_not_a_silence(self, probe_module, deployment, monkeypatch, capsys):
        """A set that keeps moving must be reported as such, or the table gets a number it never had.

        `cycle=True` is what makes this deterministic: a set that alternates never
        produces three identical consecutive samples, however many times the loop
        gets to ask, so the assertion does not depend on the window's length.
        """
        wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on"],
            art_modes=["off", "on"],
            cycle=True,
        )
        assert probe_module.main(["--sample-interval", "0", "--settle", "0.05", "--click", "--i-am-at-the-set"]) == 0
        assert "NEVER SETTLED" in capsys.readouterr().out

    def test_an_intermediate_state_is_named_rather_than_collapsed(self, probe_module, deployment, monkeypatch, capsys):
        """The two-press finding *is* an intermediate state, so a report that hid one would rebuild the sketch."""
        wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on", "on"],
            art_modes=["off", "off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        printed = capsys.readouterr().out
        assert "intermediate states seen: TELEVISION" in printed

    def test_the_set_not_having_moved_yet_is_latency_and_not_a_transition(self, probe_module, deployment, monkeypatch, capsys):
        """A press the set answers slowly must not be reported as a visit to where it started.

        The sweep found this branch undefended. It matters because the *point* of
        the intermediate list is the two-press finding — a state genuinely passed
        through — and a report that also listed the starting state would put a
        transition in the table that never happened, on the exact cells where the
        set is slowest and the operator is most reliant on the tool.
        """
        wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "standby", "standby", "on"],
            art_modes=["off", "off", "off", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        printed = capsys.readouterr().out
        assert "intermediate states seen: none" in printed, "the state it started in was listed as one it passed through"

    def test_a_dead_art_channel_is_distinguished_from_one_never_opened(self, probe_module, deployment, monkeypatch, capsys):
        wire(
            monkeypatch,
            probe_module,
            power_states=["on", "on", "on", "on"],
            art_modes=["on", "on", "on", "on"],
            alive=False,
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        assert "DEAD" in capsys.readouterr().out

    def test_skipping_the_art_channel_says_it_was_not_asked(self, probe_module, deployment, monkeypatch, capsys):
        art, _ = wire(monkeypatch, probe_module, power_states=["on"], art_modes=[])
        assert probe_module.main([*FAST, "--no-art-channel"]) == 0
        printed = capsys.readouterr().out
        assert "not asked" in printed, "a skipped reading was reported as a failed one"
        assert not art.closed, "the art channel was opened despite --no-art-channel"
        assert "summary:" not in printed, "a read-only run reported on a transition it never made"

    def test_an_art_channel_never_opened_is_not_reported_as_dead(self, probe_module, deployment, monkeypatch, capsys):
        """Three states, not two: alive, dead, and never asked.

        The sweep found this one undefended, and it is the same
        two-meanings-in-one-value fault this plane has paid for before: collapsing
        "never opened" into "dead" would answer the *does the art channel survive a
        power transition* question with a confident no, on a run that never opened a
        channel to find out.
        """
        art, _ = wire(monkeypatch, probe_module, power_states=["standby", "on"], art_modes=[])
        assert probe_module.main([*FAST, "--no-art-channel", "--click", "--i-am-at-the-set"]) == 0
        printed = capsys.readouterr().out
        assert "never opened" in printed
        assert "DEAD" not in printed, "a channel nobody opened was reported as having died"


class TestItAlwaysClosesWhatItOpened:
    """One close path for both channels — the rule `daemon.py` carries a `finally` for.

    This set has been observed refusing a *new* art-channel connection for minutes
    after a client went away without closing, and the next connection is the daemon
    the operator is about to restart. A probe that leaked a channel would cost the
    wall the minutes right after the sitting, which is when somebody is watching to
    see whether it worked.
    """

    def test_both_channels_close_on_the_happy_path(self, probe_module, deployment, monkeypatch):
        art, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        assert art.closed and remote.closed

    def test_both_channels_close_when_the_run_raises(self, probe_module, deployment, monkeypatch):
        art, remote = wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])

        async def exploding_press(self):
            await self._art_channel()
            await self._remote_channel()
            raise RuntimeError("the set refused the key")

        monkeypatch.setattr(probe_module.Probe, "press", exploding_press)
        with pytest.raises(RuntimeError):
            probe_module.main([*FAST, "--click", "--i-am-at-the-set"])
        assert art.closed, "the art channel outlived a crash"
        assert remote.closed, "the remote channel outlived a crash"


class TestTheStateMappingItself:
    """`Reading.observed` as a unit, away from the CLI."""

    def reading(self, module, power, art):
        return module.Reading(
            at=0.0,
            power_state=power,
            power_seconds=0.0,
            power_error=None,
            art_mode=art,
            art_seconds=0.0,
            art_error=None,
        )

    def test_an_unrecognised_power_state_is_unknown(self, probe_module):
        assert self.reading(probe_module, "warming-up", "on").observed == "UNKNOWN"

    def test_settling_compares_raw_readings_not_the_mapped_state(self, probe_module):
        """Two different raw pairs both mapping to UNKNOWN are not the same reading.

        Settling on the mapped state would call a set still moving between two
        unreadable conditions "settled", and hand the table a time that means
        nothing.
        """
        first = self.reading(probe_module, None, "on")
        second = self.reading(probe_module, "warming-up", "on")
        assert first.observed == second.observed == "UNKNOWN"
        assert first.key != second.key

    def test_the_line_shows_the_raw_pair_beside_the_verdict(self, probe_module):
        """UNKNOWN is where the interesting failures live, so the report never hides the inputs."""
        line = self.reading(probe_module, "on", "off").line(0.0)
        assert "on" in line and "off" in line and "TELEVISION" in line


class TestTheIntermediateReport:
    def test_a_state_visited_twice_is_reported_twice(self, probe_module):
        """television → art → television has visited television twice, and the second visit is the finding."""
        before = probe_module.Reading(
            at=0.0, power_state="on", power_seconds=0.0, power_error=None, art_mode="off", art_seconds=0.0, art_error=None
        )

        def sample(power, art):
            return probe_module.Reading(
                at=0.0, power_state=power, power_seconds=0.0, power_error=None, art_mode=art, art_seconds=0.0, art_error=None
            )

        samples = [sample("on", "on"), sample("on", "off"), sample("standby", "off")]
        assert probe_module._intermediate(before, samples) == ["ART", "TELEVISION"]

    def test_a_transition_with_no_middle_reports_none(self, probe_module):
        before = probe_module.Reading(
            at=0.0, power_state="standby", power_seconds=0.0, power_error=None, art_mode="off", art_seconds=0.0, art_error=None
        )
        samples = [
            probe_module.Reading(
                at=0.0, power_state="on", power_seconds=0.0, power_error=None, art_mode="on", art_seconds=0.0, art_error=None
            )
        ]
        assert probe_module._intermediate(before, samples) == []


def test_the_tool_is_importable_and_its_entry_point_is_callable(probe_module):
    """The check `test_tools.py` was written for: a tool nothing imports is a tool nothing checks."""
    assert callable(probe_module.main)
    assert asyncio.iscoroutinefunction(probe_module.run)

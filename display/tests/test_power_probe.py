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
from samsungtvws.command import SamsungTVSleepCommand

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

    **It models the library's silent reopen, and that is not decoration.** The real
    `get_artmode` goes through `_send_art_request` → `start_listening()`, which
    reopens a closed channel without saying so — so a double whose `is_alive()` was a
    fixed flag made the "did the channel survive the press?" report untestable, and a
    review found the tool asking the question in the one way that cannot answer it.
    Here a dead channel answers `is_alive()` falsely *once*, then repairs itself on
    the read, exactly as the library does.
    """

    def __init__(self, modes, *, alive=True, cycle=False, dies_after=None):
        self._modes = list(modes)
        self._alive = alive
        self._cycle = cycle
        #: Reads after which the channel is found closed; `None` never dies.
        self._dies_after = dies_after
        self._reads = 0
        self.closed = False
        self.reopened = False

    async def get_artmode(self):
        self._reads += 1
        if not self._alive:
            # The library repairs it on the way to the read, which is the behaviour
            # that makes a post-hoc liveness check meaningless.
            self._alive = True
            self.reopened = True
        value = _next_scripted(self._modes, cycle=self._cycle)
        if isinstance(value, Exception):
            raise value
        return value

    def is_alive(self):
        if self._dies_after is not None and self._reads >= self._dies_after:
            self._alive = False
            self._dies_after = None
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


def wire(
    monkeypatch,
    module,
    *,
    power_states,
    art_modes,
    alive=True,
    cycle=False,
    dies_after=None,
    real_art=False,
    real_remote=False,
):
    """Stand the two channels and the REST endpoint up in memory.

    Patched on `Probe` rather than injected, because the tool's constructor is its
    CLI: giving it a seam for tests to pass fakes through would be a seam no real
    invocation uses, which is the shape of a fixture that cannot fail.

    **`real_art` and `real_remote` leave a channel's own opener in place**, because
    two of the properties worth testing live *in* those methods — the token passed by
    value, and the refusal to share a token file — and a test that replaced them
    would be testing the replacement. The review found the second of those defects
    precisely because every test stubbed the seam that chooses the token file.
    """
    art = FakeArt(art_modes, alive=alive, cycle=cycle, dies_after=dies_after)
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
    if not real_art:
        monkeypatch.setattr(module.Probe, "_art_channel", art_channel)
    if not real_remote:
        monkeypatch.setattr(module.Probe, "_remote_channel", remote_channel)
    return art, remote


FAST = ["--sample-interval", "0", "--settle", "5"]


def _payload(frame):
    """One frame reduced to (command, target), so a test can name what reached the set.

    Read off the library's own objects rather than matched as a string, which keeps the
    assertion about what will actually go out. A `SamsungTVSleepCommand` is the pause
    inside a hold and raises on both `as_dict` and `get_payload`, so it is reported as
    `("sleep", seconds)` — its duration is the operator's `--hold` value and worth
    asserting, since a hold with the wrong pause measures the wrong gesture.
    """
    if isinstance(frame, SamsungTVSleepCommand):
        return ("sleep", frame.delay)
    params = frame.params
    return (params["Cmd"], params["DataOfCmd"])


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

    def test_press_itself_refuses_not_only_the_command_line(self, probe_module, deployment):
        """The guard has to hold for a caller that never went through argparse.

        The CLI check fires first on every real invocation, which is why the sweep found
        the guard inside `press` undefended — every test reached the outer one. But the
        CLI is not the only way in: anything constructing a `Namespace` and calling
        `press` bypasses it entirely, and `press` is the only place a key is ever sent,
        so it is the only place that can promise one was not.
        """
        args = probe_module.argparse.Namespace(
            host="10.0.0.2",
            port=8002,
            client_name="tvpi",
            timeout=10.0,
            remote_token_file=deployment / "remote",
            art_token_file=deployment / "art",
            key_press_delay=0.0,
            hold=None,
            click=True,
            i_am_at_the_set=False,
            art_channel=True,
        )
        probe = probe_module.Probe(args)
        with pytest.raises(probe_module.ProbeRefusal, match="--i-am-at-the-set"):
            asyncio.run(probe.press())


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
        probe_module._settings_into(args, parser)
        assert args.remote_token_file != args.art_token_file
        assert args.art_token_file is not None, "it did not find the deployment's own token file"

    def test_it_refuses_when_told_to_share_one_file(self, probe_module, deployment, monkeypatch, capsys):
        """The refusal fires on the path a *careful* operator takes: every flag supplied.

        This is the shape of the bug the review found. The check used to live in
        `_settings_into`, which returns early once all five settings are given — so
        the fully explicit invocation was the single path that skipped it. It now
        lives in `_remote_channel`, the only place a remote channel is constructed
        and therefore the only place that can promise anything about its token file.
        """
        shared = deployment / "token_file"
        shared.write_text("a-token\n")
        wire(monkeypatch, probe_module, power_states=["standby", "on"], art_modes=["off", "on"], real_remote=True)
        assert (
            probe_module.main(
                [
                    *FAST,
                    "--host",
                    "10.0.0.2",
                    "--port",
                    "8002",
                    "--client-name",
                    "tvpi",
                    "--timeout",
                    "10",
                    "--remote-token-file",
                    str(shared),
                    "--art-token-file",
                    str(shared),
                    "--click",
                    "--i-am-at-the-set",
                ]
            )
            == 2
        )
        assert "refusing to give the remote-control channel the art channel's token file" in capsys.readouterr().out

    def test_the_art_channel_is_never_handed_a_path_to_write(self, probe_module, deployment, monkeypatch):
        """The claim "it never writes TV_TOKEN_FILE" is enforced here, not asserted in prose.

        `_check_for_token` runs on every successful open and rewrites `token_file` in
        `"w"` mode, so a channel merely *pointed* at the deployment's file is a writer
        of it. The token therefore goes by value. This test drives the real
        construction rather than the stub, because the seam where the token file is
        chosen is exactly the seam every other test replaces.
        """
        token = deployment / "token_file"
        token.write_text("the-wall-token\n")
        built = {}

        class Recorder:
            def __init__(self, **kwargs):
                built.update(kwargs)

            async def start_listening(self):
                return None

            async def get_artmode(self):
                return "on"

            def is_alive(self):
                return True

            async def close(self):
                return None

        monkeypatch.setattr(probe_module, "SamsungTVAsyncArt", Recorder)
        wire(monkeypatch, probe_module, power_states=["on"], art_modes=[], real_art=True)
        assert probe_module.main([*FAST, "--art-token-file", str(token)]) == 0

        assert built["token_file"] is None, "the art channel was given a path it could write"
        assert built["token"] == "the-wall-token", "the token was not passed by value"
        assert token.read_text() == "the-wall-token\n", "the deployment's token file was modified"

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

    def test_a_refusing_art_channel_names_daemon_contention_as_a_possible_cause(
        self, probe_module, deployment, monkeypatch, capsys
    ):
        """The ambiguity has to be named where it appears, because the transcript is evidence.

        The art channel refuses for two different reasons — the set's state, which is
        what the sitting measures, and another client already holding the slot, which
        means somebody forgot to stop the daemon. They look identical in the output, and
        *that output is what Chunk 25's fake gets built from*: a fake modelled on a
        contention refusal would encode it as a fact about the television and make every
        test past it vacuous.
        """
        wire(monkeypatch, probe_module, power_states=["on"], art_modes=[RuntimeError("refused")])
        assert probe_module.main([*FAST]) == 0
        printed = capsys.readouterr().out
        assert "the art channel did not answer" in printed
        assert "another client holding the slot" in printed
        assert "systemctl stop display.service" in printed

    def test_a_readable_art_channel_does_not_warn_about_contention(self, probe_module, deployment, monkeypatch, capsys):
        """Otherwise the hint prints on every run and stops meaning anything."""
        wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])
        assert probe_module.main([*FAST]) == 0
        assert "did not answer" not in capsys.readouterr().out

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

    def test_a_click_sends_exactly_one_KEY_POWER_click(self, probe_module, deployment, monkeypatch, capsys):
        """**Which key, and which command** — not merely that something was sent.

        Counting frames leaves a swap to `KEY_VOLUP`, or a `Press` where a `Click`
        belongs, entirely undefended: the suite stayed green over both. What reaches
        the set is the one thing about this tool that a wrong answer makes dangerous.
        """
        _, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        assert [_payload(frame) for frame in remote.sent] == [("Click", "KEY_POWER")]
        assert "KEY_POWER click" in capsys.readouterr().out

    def test_a_hold_sends_press_then_a_sleep_then_release(self, probe_module, deployment, monkeypatch, capsys):
        """Three frames in that order, and the sleep carries the operator's duration.

        The library's own framing rather than hand-rolled frames, so the sitting
        measures what the product will ship — and the *order* matters, since a release
        that arrived first would leave KEY_POWER held.
        """
        _, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )
        assert probe_module.main([*FAST, "--hold", "3", "--i-am-at-the-set"]) == 0
        assert [_payload(frame) for frame in remote.sent] == [
            ("Press", "KEY_POWER"),
            ("sleep", 3.0),
            ("Release", "KEY_POWER"),
        ]
        assert "held 3" in capsys.readouterr().out

    def test_a_press_that_fails_reports_the_two_causes_and_keeps_the_readings(
        self, probe_module, deployment, monkeypatch, capsys
    ):
        """The two failures the sitting is asked to record must not arrive as a traceback.

        `UnauthorizedError` and `ConnectionFailure` are exactly what Chunk 24 sends the
        operator to look for, and they surface at press time because the library opens
        the channel inside `send_commands`. An unhandled one would take the readings
        above it down with it — and those readings are the run's evidence.
        """
        _, remote = wire(monkeypatch, probe_module, power_states=["standby"], art_modes=["off"])

        async def refuse(_command):
            raise RuntimeError("UnauthorizedError-ish")

        monkeypatch.setattr(remote, "send_command", refuse)
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 1
        printed = capsys.readouterr().out
        assert "the press FAILED" in printed
        assert "UnauthorizedError" in printed and "ConnectionFailure" in printed
        assert "→ DARK" in printed, "the failure took the readings with it"
        assert "nothing was sent, so it is unchanged" in printed

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

    def test_a_channel_the_press_killed_is_reported_even_though_the_library_reopened_it(
        self, probe_module, deployment, monkeypatch, capsys
    ):
        """The review's sharpest finding, and it went to Chunk 24's actual deliverable.

        `get_artmode` reaches `start_listening()`, which reopens a dead channel without
        a word — so a post-hoc `is_alive()` reads `True` whether or not the press killed
        it, and the run would answer *does the art channel survive a power transition?*
        with a confident yes it had no evidence for. `FakeArt` now models the reopen, so
        a tool that asked afterwards instead of before fails here.
        """
        art, _ = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on"],
            art_modes=["off", "on"],
            dies_after=1,
        )
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        printed = capsys.readouterr().out
        assert "FOUND CLOSED" in printed, "a channel the press killed was reported as having survived"
        assert art.reopened, "the double did not model the library's silent reopen, so this proves nothing"

    def test_a_channel_that_stayed_up_is_reported_as_having_survived(self, probe_module, deployment, monkeypatch, capsys):
        """The other half — otherwise the test above passes against a tool that always cries wolf."""
        wire(monkeypatch, probe_module, power_states=["standby", "on"], art_modes=["off", "on"])
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 0
        printed = capsys.readouterr().out
        assert "alive at every sample" in printed
        assert "FOUND CLOSED" not in printed

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

    def test_both_channels_close_when_a_press_is_refused_by_the_set(self, probe_module, deployment, monkeypatch):
        """A reported failure is still a failure: the channels do not outlive it."""
        art, remote = wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])

        async def refuse(_command):
            raise RuntimeError("the set refused the key")

        monkeypatch.setattr(remote, "send_command", refuse)
        assert probe_module.main([*FAST, "--click", "--i-am-at-the-set"]) == 1
        assert art.closed, "the art channel outlived a failed press"
        assert remote.closed, "the remote channel outlived a failed press"

    def test_both_channels_close_when_something_unhandled_raises(self, probe_module, deployment, monkeypatch):
        """The `finally` earns its keep on the path nobody anticipated.

        Driven through a failure the tool does *not* handle, because the handled ones
        now return cleanly — and a test that only exercised those would say nothing
        about the case `daemon.py` grew its own `finally` for, where an exception once
        skipped a close and turned one crash into a daemon that could not reach its
        own television.
        """
        art, remote = wire(
            monkeypatch,
            probe_module,
            power_states=["standby", "on", "on", "on"],
            art_modes=["off", "on", "on", "on"],
        )

        async def exploding_watch(*_args, **_kwargs):
            raise RuntimeError("something nobody planned for")

        monkeypatch.setattr(probe_module, "_watch", exploding_watch)
        with pytest.raises(RuntimeError):
            probe_module.main([*FAST, "--click", "--i-am-at-the-set"])
        assert art.closed, "the art channel outlived a crash"
        assert remote.closed, "the remote channel outlived a crash"

    def test_a_close_that_fails_is_said_out_loud_and_does_not_mask_the_run(self, probe_module, deployment, monkeypatch, capsys):
        """A failed close is the beginning of the next connection's trouble.

        The next connection is the daemon the operator is about to restart, so a
        silently swallowed close failure is the one thing they most need told. It is
        reported rather than raised, because raising here would replace the real
        outcome with the failed attempt to tidy up.
        """
        art, _ = wire(monkeypatch, probe_module, power_states=["on"], art_modes=["on"])

        async def bad_close():
            raise OSError("socket already gone")

        monkeypatch.setattr(art, "close", bad_close)
        assert probe_module.main([*FAST]) == 0
        printed = capsys.readouterr().out
        assert "closing the art channel raised" in printed
        assert "socket already gone" in printed


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

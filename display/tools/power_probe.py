"""Measure what a power key does to this set, one gesture at a time.

**This is Chunk 24's instrument, and Chunk 24 is a measurement chunk.** Everything
downstream of it sends a power key to a television, and nobody has measured what
the keys do: `platform-and-dependency-findings.md` records two presses from one
starting state, never tested press-and-hold, and labels its own transitions *a
sketch*. That was fine while the display plane held no power verb. It is the whole
risk now, because the state the map is missing is the **television** one — a press
sent there is the interruption `nonfunctional-requirements.md` § The television
belongs to whoever is using it exists to prevent, and it is the one state whose
readings are identical to dark's on the art channel.

**Why a tool and not a REPL.** The table Chunk 24 has to fill is three starting
states × two gestures, and every cell wants the same four things: the readings
before, the readings after, *how long they took to settle*, and whether the art
channel survived. Settling time is the one a REPL cannot give you — by the time a
human has typed the next call, the transition being timed is over. A wrong
settling time is not a harmless gap either: a policy that reads too early sees the
state it was trying to leave, which is a wall that acts on a stale answer.

**It will not press anything without `--i-am-at-the-set`.** This sends real keys
to a real television, and one of the measurements is deliberately taken *from the
television state* — the state the norm forbids shipped code to press at. That is
legitimate here and only here: the operator is standing in front of the set,
watching what happens, and that is the entire difference between a measurement and
the interruption. A run with no gesture flag reads and reports, which is always
safe.

**Stop the daemon first, and let it stop.**

    ssh <pi> sudo systemctl stop display.service

The daemon holds the art channel, and this set has been observed refusing a *new*
art-channel connection for minutes after a client went away without closing — so a
probe run alongside the daemon contends for the slot, and a probe run after a
`SIGKILL` may not get one at all. `deploy/display.service` allows 90 s to stop for
that reason; wait for it, and start the unit again afterwards or the wall stays
wherever the last press left it.

**It never writes `TV_TOKEN_FILE`, and that is enforced rather than promised.**
Both channels call `_check_for_token` on every successful open, which rewrites the
`token_file` they were given in `"w"` mode whenever the set returns a token — so a
probe merely *pointed* at the daemon's file is a writer of it, and could leave the
deployment holding a token minted for a different endpoint. Two different measures,
because the two channels need different things:

- **the art channel is given its token by value** (`token=`, `token_file=None`), so
  the library has no path to write back to. That is why the claim above is true;
- **the remote channel gets a file of its own**, `--remote-token-file`, because it
  has a token to keep across runs. `_remote_channel` refuses to open if that path
  is the art channel's — the check lives there rather than at the argument layer,
  since that is the only place that can actually promise it.

The first open under the probe's own file may raise a pairing prompt on the screen:
**accept it, and note that it happened** — that is one of the questions the sitting
owes, and an unattended daemon meeting its first prompt is a daemon that stops.

Read the state, which is always safe and needs no flag:

    cd display && uv run python tools/power_probe.py

Measure a gesture, from whatever state the set is in now:

    cd display && uv run python tools/power_probe.py --click --i-am-at-the-set
    cd display && uv run python tools/power_probe.py --hold 3 --i-am-at-the-set

Skip the art channel when only the REST reading is wanted — which is also how to
find out whether the art channel opens at all in a given state, since a run
*with* it reports that as a datum rather than failing:

    cd display && uv run python tools/power_probe.py --no-art-channel

The set's address and client name come from this deployment's `.env`, the same
road `__main__` takes; `--host` overrides it for a set that is not this wall's.
Record what comes out in `samsung-tv-state-findings.md`, with the date — a reading
whose provenance is unrecorded is what let the previous sketch be mistaken for
measurement. The banner prints that provenance so a pasted transcript carries it.

The reference deployment's actual paths are in `deploy/README.md` § Measuring what
the power keys do, which is where machine-specific values belong — this file must
not name them, per the deployment-values norm.
"""

import argparse
import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws.async_remote import SamsungTVWSAsyncRemote
from samsungtvws.async_rest import SamsungTVAsyncRest
from samsungtvws.remote import SendRemoteKey

#: How long to keep sampling after a gesture before giving up on it settling.
#: Generous on purpose: the point of the exercise is to find out what the real
#: number is, and a default that truncates the answer would confirm whatever the
#: author already believed.
DEFAULT_SETTLE_SECONDS = 45.0

#: Seconds between samples while watching a transition.
DEFAULT_SAMPLE_INTERVAL = 1.0

#: How many identical consecutive samples count as settled. Three rather than two
#: because this set has been seen reporting an intermediate state that persists
#: for one sample — `PowerState` reaching `on` before the art app is up is exactly
#: that — and a two-sample rule would call the intermediate state the destination.
STABLE_SAMPLES = 3


class Reading:
    """One observation of the set, with what each half cost to obtain.

    Latency is carried per-half rather than for the pair because the two come off
    different transports — REST on 8001, the art channel on the websocket — and the
    downstream timeout budget is per-call. A single combined number would hide
    which of the two is the slow one.
    """

    def __init__(
        self,
        *,
        at: float,
        power_state: str | None,
        power_seconds: float,
        power_error: str | None,
        art_mode: str | None,
        art_seconds: float,
        art_error: str | None,
        art_channel_was_closed: bool = False,
    ) -> None:
        self.at = at
        self.power_state = power_state
        self.power_seconds = power_seconds
        self.power_error = power_error
        self.art_mode = art_mode
        self.art_seconds = art_seconds
        self.art_error = art_error
        #: Whether the art channel was found closed when this sample went to read it —
        #: which the library then silently repaired. The only honest evidence that a
        #: power transition killed the channel, since after the read it is alive again.
        self.art_channel_was_closed = art_channel_was_closed

    @property
    def observed(self) -> str:
        """The product's own vocabulary for this pair of readings.

        The mapping Chunk 25 will implement, stated here so the sitting can check
        it against the set rather than the other way round: `standby`/`off` is
        dark, `on`/`off` is television, `on`/`on` is art mode. **Anything this
        cannot read is `UNKNOWN`, never a guess** — and `UNKNOWN` is what the two
        interesting failures look like, which is why the report prints the raw
        pair beside it.
        """
        if self.power_state is None:
            return "UNKNOWN"
        if self.power_state == "standby":
            # The art channel's answer is not consulted: in this state it is
            # commonly unreachable, and dark is what `standby` means whether or
            # not a websocket could be opened to confirm it.
            return "DARK"
        if self.power_state == "on":
            if self.art_mode == "on":
                return "ART"
            if self.art_mode == "off":
                return "TELEVISION"
            return "UNKNOWN"
        return "UNKNOWN"

    @property
    def key(self) -> tuple[str | None, str | None]:
        """What "the same reading twice" means, for settling.

        The raw pair rather than `observed`, deliberately: two different raw pairs
        can both map to `UNKNOWN`, and treating those as one state would report a
        transition as settled while it was still moving.
        """
        return (self.power_state, self.art_mode)

    def line(self, origin: float) -> str:
        parts = [f"t+{self.at - origin:5.1f}s"]
        power = self.power_error or (self.power_state or "-")
        art = self.art_error or (self.art_mode or "-")
        parts.append(f"PowerState {power:<12} ({self.power_seconds:4.2f}s)")
        parts.append(f"get_artmode {art:<12} ({self.art_seconds:4.2f}s)")
        parts.append(f"→ {self.observed}")
        return "  ".join(parts)


class ProbeRefusal(RuntimeError):
    """The tool declining to do something harmful, from the place that would do it.

    Distinct from a library failure so the report can tell the operator "I did not
    do that, and here is why" rather than showing them a transport error. Raised
    rather than returned because every one of these means the run must not continue
    on the path it was on.
    """


def _token_value(path: Path | None) -> str | None:
    """The token as a string, so the channel wanting it need not be given the file.

    Absent or unreadable is `None`, which is the same thing the library does with a
    missing file — an unpaired channel that will prompt. **Unreadable is not fatal
    on purpose**: the sitting can legitimately want a fresh pairing, and the operator
    is standing at the set to accept it.
    """
    if path is None:
        return None
    try:
        contents = path.read_text().splitlines()
    except OSError:
        return None
    return contents[0].strip() if contents and contents[0].strip() else None


def _refuse_a_shared_token_file(remote: Path | None, art: Path | None) -> None:
    """Refuse to hand the remote channel the file the art channel depends on.

    Both channels rewrite their token file in `"w"` mode on every successful open, so
    one path shared between them is how a measurement sitting ends with a wall that
    cannot reach its own television — a cost paid at the daemon's next reconnect,
    long after the run that caused it.
    """
    if remote is None:
        raise ProbeRefusal("no token file for the remote-control channel; pass --remote-token-file")
    if art is not None and remote.resolve() == art.resolve():
        raise ProbeRefusal(
            f"refusing to give the remote-control channel the art channel's token file ({remote}). "
            "Both channels rewrite whatever they are given, and the daemon depends on that file. "
            "Give the remote channel its own with --remote-token-file."
        )


class Probe:
    """The two channels and the REST endpoint, opened as late as possible.

    Both channels close on one path, in `run`'s `finally`. That is not tidiness:
    this set has been observed refusing art-channel connections for minutes after
    a client went away without closing, and `daemon.py` carries a `finally` for
    exactly that reason after an exception once turned one crash into a daemon that
    could not reach its own television. A second channel is a second way to
    reproduce it, so it gets the same single lifetime.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._session: aiohttp.ClientSession | None = None
        self._rest: SamsungTVAsyncRest | None = None
        self._art: SamsungTVAsyncArt | None = None
        self._remote: SamsungTVWSAsyncRemote | None = None
        #: The raw reply behind the most recent reading, so the report can name the
        #: set without asking it a second question. Not a cache: nothing reads it
        #: to decide anything, only to print what the last real call returned.
        self.last_device_info: Any = None

    async def open(self) -> None:
        self._session = aiohttp.ClientSession()
        self._rest = SamsungTVAsyncRest(
            host=self._args.host,
            session=self._session,
            port=self._args.rest_port,
            timeout=self._args.timeout,
        )

    async def close(self) -> None:
        """Best-effort, and never silent about a failure.

        Closing runs while something has already gone wrong, so a failure here must
        not replace the real error with a tidier one — but it is *said out loud*
        rather than swallowed, exactly as `samsung.py`'s `_quietly_close` does. A
        close that failed is the beginning of the next connection's trouble, and an
        operator restarting the daemon afterwards needs to know it happened.
        """
        for label, closing in (("art", self._art), ("remote", self._remote)):
            if closing is not None:
                try:
                    await closing.close()
                # prawduct:allow prawduct/broad-except -- every way a websocket close can
                # fail arrives here, and the report is the same for all of them; raising
                # would replace the real failure with the failed attempt to tidy up.
                except Exception as exc:
                    print(f"warning: closing the {label} channel raised {_named(exc)}")
        if self._session is not None:
            try:
                await self._session.close()
            # prawduct:allow prawduct/broad-except -- as above, for the HTTP session.
            except Exception as exc:
                print(f"warning: closing the HTTP session raised {_named(exc)}")

    async def device_info(self) -> dict[str, Any]:
        return await self._rest.rest_device_info()

    async def _art_channel(self) -> SamsungTVAsyncArt:
        """Open the art channel once, on demand, **without ever writing its token file.**

        The token is passed by *value*. `_check_for_token` runs on every successful
        open and calls `_set_token`, which writes `token_file` in `"w"` mode whenever
        the set returns a token — so handing this channel the deployment's path would
        make the probe a writer of the file the wall depends on. Passing `token=` with
        `token_file=None` keeps that write in memory: `_set_token` falls through to
        `self.token = token` when there is no file. The tool's claim that it never
        writes `TV_TOKEN_FILE` is enforced here rather than asserted in prose.

        Constructed in a worker thread because `SamsungTVAsyncArt.__init__` is
        blocking — it makes a REST call for the model year, and on a 2024-or-later
        set with an empty token file it opens and closes the remote-control channel
        to mint a token. `samsung.py`'s `_construct` carries the same note and the
        same reason.
        """
        if self._art is None:
            token = _token_value(self._args.art_token_file)

            def build() -> SamsungTVAsyncArt:
                return SamsungTVAsyncArt(
                    host=self._args.host,
                    port=self._args.port,
                    name=self._args.client_name,
                    token=token,
                    token_file=None,
                    timeout=self._args.timeout,
                )

            art = await asyncio.to_thread(build)
            await art.start_listening()
            self._art = art
        return self._art

    async def _remote_channel(self) -> SamsungTVWSAsyncRemote:
        """Open the remote-control channel once, on demand, under its own token file.

        **The one invariant this tool has is enforced here, not at the argparse
        layer.** An earlier version checked it while parsing arguments and returned
        early when every setting was supplied explicitly — so the fully explicit
        invocation, the one a careful operator reaches for, was the single path that
        skipped the check. A guard belongs where the harm happens: this is the only
        place a remote channel is ever constructed, so it is the only place that can
        promise the wall's own token file is not the one being handed over.

        Unlike the art channel this one *does* take a file, because it has a token of
        its own to keep across runs and no other client depends on it.
        """
        if self._remote is None:
            _refuse_a_shared_token_file(self._args.remote_token_file, self._args.art_token_file)
            self._remote = SamsungTVWSAsyncRemote(
                host=self._args.host,
                port=self._args.port,
                name=self._args.client_name,
                token_file=str(self._args.remote_token_file),
                timeout=self._args.timeout,
                key_press_delay=self._args.key_press_delay,
            )
        return self._remote

    async def read(self) -> Reading:
        """One sample of both halves, each timed and each failing independently.

        Neither failure aborts the other. A run whose art channel will not open in
        the dark state is not a broken run — *that is one of the findings*, and a
        probe that raised there would report nothing about the state it was asked
        to describe.
        """
        at = time.monotonic()

        power_state: str | None = None
        power_error: str | None = None
        started = time.monotonic()
        try:
            info = await self.device_info()
            self.last_device_info = info
            device = info.get("device", {}) if isinstance(info, dict) else {}
            raw = device.get("PowerState")
            power_state = raw if isinstance(raw, str) else None
            if power_state is None:
                power_error = "no PowerState in reply"
        # prawduct:allow prawduct/broad-except -- every transport failure is a datum
        # here rather than a crash: an unreachable set is one of the states this tool
        # exists to describe, and raising would report nothing about it.
        except Exception as exc:
            power_error = _named(exc)
        power_seconds = time.monotonic() - started

        art_mode: str | None = None
        art_error: str | None = None
        started = time.monotonic()
        channel_was_closed = False
        if self._args.art_channel:
            try:
                art = await self._art_channel()
                # **Sampled BEFORE the read, and this is the whole answer to "does the
                # art channel survive a power transition?"** `get_artmode` goes through
                # `_send_art_request` → `start_listening()`, which reopens a dead
                # channel without a word — so asking `is_alive()` afterwards reports
                # `True` whether or not the press killed it, and the one question
                # Chunk 24 most needs answered would be answered wrongly, confidently,
                # from a green run.
                channel_was_closed = not art.is_alive()
                raw = await art.get_artmode()
                art_mode = raw if isinstance(raw, str) else None
                if art_mode is None:
                    art_error = "unreadable reply"
            # prawduct:allow prawduct/broad-except -- every transport failure is a datum
            # here rather than a crash; a probe that raised would report nothing about
            # the state it was asked to describe.
            except Exception as exc:
                art_error = _named(exc)
        else:
            art_error = "not asked"
        art_seconds = time.monotonic() - started

        return Reading(
            at=at,
            power_state=power_state,
            power_seconds=power_seconds,
            power_error=power_error,
            art_mode=art_mode,
            art_seconds=art_seconds,
            art_error=art_error,
            art_channel_was_closed=channel_was_closed,
        )

    async def press(self) -> str:
        """Send the gesture, and say what was sent.

        `SendRemoteKey.power()` is a `Click`; `hold` is press, sleep, release, and
        comes back as a *list* for `send_commands`. Both are the library's own
        framing rather than this tool's, so what the sitting measures is what the
        product will send.

        **The operator refusal is enforced here as well as at the CLI**, for the
        reason `_remote_channel` gives about its own invariant: this is the only
        place a key is ever sent, so it is the only place that can promise one was
        not sent. The argparse check stays because it gives a better message before
        anything is opened; this one is what makes the promise true.
        """
        if not self._args.i_am_at_the_set:
            raise ProbeRefusal(
                "refusing to send a power key without --i-am-at-the-set. This reaches a real "
                "television, and one measurement is taken from the television state, which shipped "
                "code may never press at."
            )
        remote = await self._remote_channel()
        if self._args.hold is not None:
            # A hold is three frames — press, sleep, release — and a connection dropped
            # between them leaves KEY_POWER pressed and never released. **The failure is
            # allowed to propagate unchanged**, deliberately: it comes from the set, and
            # `run` reports set failures with the two causes the sitting has to tell
            # apart. An earlier version wrapped it in `ProbeRefusal`, which is this
            # tool *declining* — that gave the hold a different exit code from the
            # identical click failure and skipped the coaching lines, on the more
            # dangerous of the two gestures. `run` adds what is specific to a hold.
            await remote.send_commands(SendRemoteKey.hold("KEY_POWER", self._args.hold))
            return f"KEY_POWER held {self._args.hold}s"
        await remote.send_command(SendRemoteKey.power())
        return "KEY_POWER click"

    def art_channel_verdict(self, samples: list["Reading"], origin: float) -> str:
        """What can honestly be said about the art channel surviving the transition.

        **Not `is_alive()` after the fact**, which is the trap: every read reopens a
        dead channel, so a post-hoc check reports survival unconditionally. The
        evidence is whether any sample *found* it closed on its way to read — that is
        observed before the repair, and it is the only thing here that answers the
        question Chunk 24 asked.

        Four outcomes, deliberately distinct: never opened, found closed at a named
        moment, alive throughout, and — the honest gap — opened but never re-read, so
        nothing was observed either way.
        """
        if self._art is None:
            return "never opened, so nothing to say about whether it survived"
        closed = [sample for sample in samples if sample.art_channel_was_closed]
        if closed:
            first = closed[0]
            # Measured from the run's own origin, the same zero every sample line above
            # uses. It read `samples[0].at` once, which put two different zeros in one
            # timing transcript — on an instrument whose entire output is timings, and
            # whose readings become dated rows somebody later reasons about.
            return f"FOUND CLOSED at t+{first.at - origin:.1f}s — it had to reconnect"
        if not samples:
            return "opened, but nothing was read after the press, so this run says nothing"
        return "alive at every sample taken after the press"


def _named(exc: Exception) -> str:
    """An exception as one short phrase, in the spirit of `samsung.py`'s helper.

    **In the spirit of, not identical to** — it strips the message where the original
    does not, so the two are not interchangeable and this docstring used to claim a
    parity it did not have. Kept separate rather than shared: the plane's helper is
    private to a module this tool deliberately does not import, since the instrument
    must not depend on the seam it is measuring for.

    The type name is kept even when there is a message, because the library raises
    several distinct failures with overlapping prose — `UnauthorizedError` and
    `ConnectionFailure` are the pair this sitting most needs to tell apart.
    """
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


async def _watch(probe: Probe, seconds: float, interval: float, origin: float) -> list[Reading]:
    """Sample until the readings hold still, or until the window runs out.

    Returns every sample rather than the last one: the *intermediate* states are
    the interesting part of this measurement. The two-press finding in
    `platform-and-dependency-findings.md` is precisely an intermediate state that
    somebody noticed, and a probe that reported only where the set ended up would
    have reproduced the sketch it exists to replace.
    """
    samples: list[Reading] = []
    settled_at: float | None = None
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        reading = await probe.read()
        samples.append(reading)
        print(f"  {reading.line(origin)}")

        if len(samples) >= STABLE_SAMPLES:
            recent = samples[-STABLE_SAMPLES:]
            if all(sample.key == recent[0].key for sample in recent):
                settled_at = recent[0].at
                print(f"  ← settled at t+{settled_at - origin:.1f}s after {len(samples)} samples")
                break

        await asyncio.sleep(interval)

    if settled_at is None:
        print(f"  ← NEVER SETTLED within {seconds:.0f}s — record this, it is a finding")

    return samples


def _now() -> str:
    """Wall clock for the transcript, since `t+` offsets are monotonic and undateable."""
    return datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def _name_the_likely_contention(before: Reading) -> None:
    """Say when a refusal is probably the daemon, not the set's state.

    **The reason this is worth printing rather than merely documenting three times.**
    The art channel refuses for two quite different causes — the state the set is in,
    which is what this sitting measures, and another client already holding the slot,
    which is an artefact of forgetting to stop the daemon. In the transcript they look
    identical, and *that transcript is what Chunk 25's fake gets built from*: a fake
    modelled on a contention refusal would encode "the art channel cannot be opened
    in this state" as a fact about the television, and every test past it would be
    vacuous. Naming the ambiguity where it appears is much cheaper than discovering it
    from the fake's behaviour later.

    Deliberately a hint and not a verdict — nothing here can tell the two apart, which
    is precisely why the operator has to.
    """
    if before.art_error and before.art_error not in {"not asked", "unreadable reply"}:
        print(f"  ! the art channel did not answer ({before.art_error}).")
        print("    This is EITHER the set's state OR another client holding the slot — they look the same.")
        print("    Confirm `systemctl stop display.service` completed before recording this as a state finding.")


async def run(args: argparse.Namespace) -> int:
    probe = Probe(args)
    try:
        await probe.open()

        # **Provenance first, because the transcript IS the measurement.** These lines
        # become dated rows in `samsung-tv-state-findings.md`, and that document's own
        # header format carries the wall clock and the set's version fields — a reading
        # whose provenance is unrecorded is what let the previous sketch be mistaken
        # for measurement. The token paths are here too: the operator has a
        # `_probe_remote` file to know about and to clean up afterwards.
        print(f"run at:  {_now()}")
        print(f"set:     {args.host} (websocket :{args.port}, REST :{args.rest_port}) as client {args.client_name!r}")
        print(f"tokens:  remote {args.remote_token_file}")
        print(f"         art    {args.art_token_file} (read only — this tool never writes it)")

        origin = time.monotonic()
        before = await probe.read()

        # The set's identity comes out of the reading that was going to happen
        # anyway rather than a REST call of its own. Two reasons, and the second is
        # why it is worth the reordering: an extra round trip is the smaller one,
        # and a banner that read the set separately would report a reachable set
        # microseconds before the first *measured* reading says otherwise — two
        # answers to one question, on the surface whose whole job is to be trusted.
        device = probe.last_device_info.get("device", {}) if isinstance(probe.last_device_info, dict) else {}
        if device:
            print(f"         {device.get('name', '?')} / {device.get('modelName', '?')}")
            print(
                f"         firmware {device.get('firmwareVersion', '?')}, "
                f"API {probe.last_device_info.get('version', '?')}, "
                f"token support {device.get('TokenAuthSupport', '?')}"
            )
        else:
            print(f"         could not read device info: {before.power_error or 'no device block in reply'}")

        print("\nbefore:")
        print(f"  {before.line(origin)}")
        _name_the_likely_contention(before)

        if args.hold is None and not args.click:
            print("\nno gesture asked for, so nothing was sent.")
            print("add --click or --hold SECONDS, with --i-am-at-the-set, to measure a transition.")
            return 0

        try:
            sent = await probe.press()
        except ProbeRefusal:
            # **This tool declining is not the set refusing, and must not be dressed as
            # one.** Re-raised past the handler below so it reaches `main`'s own reporting:
            # coaching the operator to accept a pairing prompt when the actual cause is a
            # token path they passed would send them to the television to fix an argument.
            raise
        # The two failures the sitting is asked to record arrive here — `UnauthorizedError`
        # when the set refused this client, `ConnectionFailure` when the connect timed
        # out on a prompt nobody accepted. Reported rather than raised, because a
        # traceback would take the readings above with it and those are the run's
        # evidence. prawduct:allow prawduct/broad-except -- the report is the same for
        # any way a press can fail, and the exception's own name carries the difference.
        except Exception as exc:
            print(f"\nthe press FAILED: {_named(exc)}")
            print("  Record which of these it was — the two are different operator actions:")
            print("    UnauthorizedError  the set refused this client. Accept the pairing prompt on screen.")
            print("    ConnectionFailure  the connect timed out — often the same prompt, unaccepted.")
            if args.hold is not None:
                # A hold is three frames and this failure gives no way to know how many
                # went out, so the caution is stated as the uncertainty it is rather than
                # as a claim. It matters more than the click's equivalent: a press frame
                # delivered without its release leaves the button held on a real set.
                print("  This was a HOLD, so it may have failed between frames: if the press")
                print("  frame went out and the release did not, KEY_POWER is still held.")
                print("  CHECK THE SET before measuring anything else.")
            else:
                print(f"  The set was {before.observed} and nothing was sent, so it is unchanged.")
            return 1

        print(f"\nsent: {sent}  (from {before.observed})")
        print("after:")
        samples = await _watch(probe, args.settle, args.sample_interval, origin)

        print("\nsummary:")
        print(f"  {before.observed} --[{sent}]--> {samples[-1].observed if samples else '?'}")
        intermediate = _intermediate(before, samples)
        print(f"  intermediate states seen: {', '.join(intermediate) if intermediate else 'none'}")
        print(f"  art channel: {probe.art_channel_verdict(samples, origin)}")
        print("\nAlso record, because nothing here can see it: what the panel showed,")
        print("whether the Apple TV woke, and which input the set settled on.")
        print("\nWhen the sitting is over: sudo systemctl start display.service —")
        print("the wall stays wherever the last press left it until the daemon is back.")
        return 0
    finally:
        # The one close path, for both channels and the HTTP session. See Probe's
        # docstring: a client that goes away without closing costs the next
        # connection minutes on this set, and that next connection is the daemon.
        await probe.close()


def _intermediate(before: Reading, samples: list[Reading]) -> list[str]:
    """The states passed through, in order, excluding where it started and ended.

    Deduplicated **adjacently rather than globally**, and this is the whole
    subtlety: a set that goes television → art → television has visited television
    twice, the second visit is the interesting one, and any rule that removed
    states merely for equalling the starting state would erase it. So the only
    things dropped are a *leading* run where the set had not moved yet, and the
    final state, which is the destination the summary line already names.
    """
    seen: list[str] = []
    for sample in samples:
        state = sample.observed
        if not seen or seen[-1] != state:
            seen.append(state)

    # A leading run equal to where it started is latency, not a transition: the
    # key had been sent but the set had not answered it yet.
    while seen and seen[0] == before.observed:
        seen.pop(0)

    return seen[:-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", help="the set's address; defaults to TV_ADDRESS from this deployment's .env")
    parser.add_argument("--port", type=int, help="websocket port; defaults to TV_PORT")
    parser.add_argument("--rest-port", type=int, default=8001, help="REST port, where PowerState is read (default 8001)")
    parser.add_argument("--client-name", help="pairing name; defaults to TV_CLIENT_NAME")
    parser.add_argument("--timeout", type=float, help="per-call timeout; defaults to TV_CONNECT_TIMEOUT_SECONDS")
    parser.add_argument(
        "--remote-token-file",
        type=Path,
        help="where the remote-control channel's token lives. NEVER the daemon's TV_TOKEN_FILE: both "
        "channels rewrite whatever file they are given, so sharing one risks the wall's own pairing. "
        "Defaults beside the deployment's, with a distinct name.",
    )
    parser.add_argument(
        "--art-token-file",
        type=Path,
        default=None,
        help="the file the art channel's token is READ from; defaults to this deployment's "
        "TV_TOKEN_FILE. It is only ever read: the value is passed to the channel by value, so the "
        "library has no path to write back to.",
    )
    parser.add_argument(
        "--click",
        action="store_true",
        help="send one KEY_POWER click and time what follows",
    )
    parser.add_argument(
        "--hold",
        type=float,
        metavar="SECONDS",
        help="hold KEY_POWER for this long (press, sleep, release) and time what follows",
    )
    parser.add_argument(
        "--i-am-at-the-set",
        action="store_true",
        help="required before anything is sent. This presses power on a real television, and one of "
        "the measurements is taken from the television state — legitimate only with somebody watching.",
    )
    parser.add_argument(
        "--no-art-channel",
        dest="art_channel",
        action="store_false",
        help="read PowerState only. Useful where opening the art channel is itself in question; "
        "note that a normal run reports a refusal as a datum rather than failing.",
    )
    parser.add_argument("--settle", type=float, default=DEFAULT_SETTLE_SECONDS, help="how long to watch for settling")
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL, help="seconds between samples")
    parser.add_argument("--key-press-delay", type=float, default=1.0, help="the library's per-command delay (default 1s)")
    args = parser.parse_args(argv)

    if args.click and args.hold is not None:
        parser.error("--click and --hold are two different gestures; measure one per run so the timings mean something")

    if args.hold is not None and args.hold <= 0:
        # A non-positive hold is not a shorter hold, it is a different gesture: the
        # library sleeps for the value between press and release, so zero or negative
        # sends both frames back to back and measures a click while the transcript
        # says "held". A table cell filled from that run records the wrong gesture.
        parser.error(f"--hold takes a positive number of seconds; {args.hold} would measure a click and label it a hold")

    if (args.click or args.hold is not None) and not args.i_am_at_the_set:
        parser.error(
            "refusing to send a power key without --i-am-at-the-set. This reaches a real television, "
            "and one measurement is taken from the television state, which shipped code may never press at. "
            "Run with no gesture flag to read the state safely."
        )

    _settings_into(args, parser)

    try:
        return asyncio.run(run(args))
    except ProbeRefusal as refusal:
        # The tool declining, from the place that would have done the harm. Reported
        # as one line rather than a traceback: every one of these is a thing the
        # operator can fix, and the frames above it are this file's, not theirs.
        print(f"\n{refusal}")
        return 2


def _settings_into(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Fill what the operator did not give from this deployment's `.env`.

    The same road `__main__` takes, so on the machine that owns the wall the short
    invocation is both convenient and correct. **Nothing falls back to a literal
    address**: this file naming one would point the instrument at a wall nobody
    asked about, and the deployment-values norm forbids it besides.
    """
    # **This function fills gaps and enforces nothing.** An earlier version checked the
    # shared-token-file invariant here and returned early when every setting was
    # supplied explicitly, which made the fully explicit invocation — the one a careful
    # operator reaches for — the single path that skipped the check. The invariant now
    # lives in `_remote_channel`, the only place that can actually promise it.
    #
    # `art_token_file` is deliberately absent from this condition. It may legitimately
    # stay `None` — an art channel with no token prompts, which is a state the sitting
    # is allowed to want — so it must not be the thing that forces an `.env` read.
    if args.host and args.port and args.client_name and args.timeout and args.remote_token_file:
        return

    # Imported here rather than at module scope, like label_preview.py: reading a
    # deployment's settings is not something a tool should do merely by being
    # imported, and the suite drives `main` without an `.env` in front of it.
    from display.config import load  # noqa: PLC0415

    settings = None
    try:
        settings = load()
    # prawduct:allow prawduct/broad-except -- every way an .env can be unreadable
    # arrives here, and one printed line plus the refusal below answers all of
    # them. Not swallowed: the reason is printed, and a run with no other source
    # for the address still refuses rather than guessing one.
    except Exception as exc:
        print(f"could not read this deployment's settings: {exc}")

    if settings is not None:
        args.host = args.host or settings.tv_address
        args.port = args.port or settings.tv_port
        args.client_name = args.client_name or settings.tv_client_name
        args.timeout = args.timeout or settings.tv_connect_timeout_seconds
        # Beside the deployment's token file and never it. A sibling path keeps the
        # two together for whoever is cleaning up after the sitting, without
        # letting this tool's opens rewrite the file the wall depends on.
        args.remote_token_file = args.remote_token_file or settings.tv_token_file.with_name(
            settings.tv_token_file.name + "_probe_remote"
        )
        args.art_token_file = args.art_token_file or settings.tv_token_file

    if not args.host:
        parser.error("no set to probe: set TV_ADDRESS in .env, or pass --host")
    if not args.port:
        args.port = 8002
    if not args.client_name:
        parser.error("no client name: set TV_CLIENT_NAME in .env, or pass --client-name")
    if not args.timeout:
        args.timeout = 10.0
    if not args.remote_token_file:
        parser.error("no --remote-token-file, and no .env to derive one beside; pass it explicitly")


if __name__ == "__main__":
    raise SystemExit(main())

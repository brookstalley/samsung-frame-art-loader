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

**It never writes `TV_TOKEN_FILE`.** Both the art and the remote-control channel
rewrite whatever token file they are given, in `"w"` mode, on every successful
open — so a probe sharing the daemon's file could hand the wall a token minted for
a different endpoint and leave the deployment unable to reach its own television.
The probe therefore keeps its own, `--remote-token-file`, defaulting beside the
deployment's rather than on top of it. The first open under it may raise a pairing
prompt on the screen: **accept it, and note that it happened** — that is one of the
questions the sitting owes, and an unattended daemon meeting its first prompt is a
daemon that stops.

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
measurement.
"""

import argparse
import asyncio
import contextlib
import time
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
    ) -> None:
        self.at = at
        self.power_state = power_state
        self.power_seconds = power_seconds
        self.power_error = power_error
        self.art_mode = art_mode
        self.art_seconds = art_seconds
        self.art_error = art_error

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
        for closing in (self._art, self._remote):
            if closing is not None:
                with contextlib.suppress(Exception):  # noqa: BLE001 -- see the class docstring
                    await closing.close()
        if self._session is not None:
            with contextlib.suppress(Exception):  # noqa: BLE001
                await self._session.close()

    async def device_info(self) -> dict[str, Any]:
        return await self._rest.rest_device_info()

    async def _art_channel(self) -> SamsungTVAsyncArt:
        """Open the art channel once, on demand.

        Constructed in a worker thread because `SamsungTVAsyncArt.__init__` is
        blocking — it makes a REST call for the model year, and on a 2024-or-later
        set with an empty token file it opens and closes the remote-control channel
        to mint a token. `samsung.py`'s `_construct` carries the same note and the
        same reason.
        """
        if self._art is None:

            def build() -> SamsungTVAsyncArt:
                return SamsungTVAsyncArt(
                    host=self._args.host,
                    port=self._args.port,
                    name=self._args.client_name,
                    token_file=str(self._args.art_token_file) if self._args.art_token_file else None,
                    timeout=self._args.timeout,
                )

            art = await asyncio.to_thread(build)
            await art.start_listening()
            self._art = art
        return self._art

    async def _remote_channel(self) -> SamsungTVWSAsyncRemote:
        """Open the remote-control channel once, on demand, under its own token.

        Its own token file rather than the deployment's, for the reason in this
        module's docstring: both channels rewrite whatever file they are handed, so
        sharing one risks the wall's own pairing to save a file.
        """
        if self._remote is None:
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
        except Exception as exc:  # noqa: BLE001 -- every transport failure is a datum here, not a crash
            power_error = _named(exc)
        power_seconds = time.monotonic() - started

        art_mode: str | None = None
        art_error: str | None = None
        started = time.monotonic()
        if self._args.art_channel:
            try:
                art = await self._art_channel()
                raw = await art.get_artmode()
                art_mode = raw if isinstance(raw, str) else None
                if art_mode is None:
                    art_error = "unreadable reply"
            except Exception as exc:  # noqa: BLE001 -- see above
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
        )

    async def press(self) -> str:
        """Send the gesture, and say what was sent.

        `SendRemoteKey.power()` is a `Click`; `hold` is press, sleep, release, and
        comes back as a *list* for `send_commands`. Both are the library's own
        framing rather than this tool's, so what the sitting measures is what the
        product will send.
        """
        remote = await self._remote_channel()
        if self._args.hold is not None:
            await remote.send_commands(SendRemoteKey.hold("KEY_POWER", self._args.hold))
            return f"KEY_POWER held {self._args.hold}s"
        await remote.send_command(SendRemoteKey.power())
        return "KEY_POWER click"

    async def art_channel_alive(self) -> bool | None:
        """Whether the art channel is still up, for the survives-a-transition question.

        `None` when the channel was never opened, which is not the same as "it
        died" and must not be reported as though it were.
        """
        if self._art is None:
            return None
        return bool(self._art.is_alive())


def _named(exc: Exception) -> str:
    """An exception as one short phrase, matching `samsung.py`'s helper.

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
        print(f"  {reading.line(origin)}")  # noqa: T201 -- the report is this tool's output

        if len(samples) >= STABLE_SAMPLES:
            recent = samples[-STABLE_SAMPLES:]
            if all(sample.key == recent[0].key for sample in recent):
                settled_at = recent[0].at
                print(f"  ← settled at t+{settled_at - origin:.1f}s after {len(samples)} samples")  # noqa: T201
                break

        await asyncio.sleep(interval)

    if settled_at is None:
        print(f"  ← NEVER SETTLED within {seconds:.0f}s — record this, it is a finding")  # noqa: T201

    return samples


async def run(args: argparse.Namespace) -> int:
    probe = Probe(args)
    try:
        await probe.open()

        print(f"set: {args.host} (websocket :{args.port}, REST :{args.rest_port}) as client {args.client_name!r}")  # noqa: T201

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
            print(f"     {device.get('name', '?')} / {device.get('modelName', '?')}")  # noqa: T201
        else:
            print(f"     could not read device info: {before.power_error or 'no device block in reply'}")  # noqa: T201

        print("\nbefore:")  # noqa: T201
        print(f"  {before.line(origin)}")  # noqa: T201

        if args.hold is None and not args.click:
            print("\nno gesture asked for, so nothing was sent.")  # noqa: T201
            print("add --click or --hold SECONDS, with --i-am-at-the-set, to measure a transition.")  # noqa: T201
            return 0

        sent = await probe.press()
        print(f"\nsent: {sent}  (from {before.observed})")  # noqa: T201
        print("after:")  # noqa: T201
        samples = await _watch(probe, args.settle, args.sample_interval, origin)

        alive = await probe.art_channel_alive()
        print("\nsummary:")  # noqa: T201
        print(f"  {before.observed} --[{sent}]--> {samples[-1].observed if samples else '?'}")  # noqa: T201
        intermediate = _intermediate(before, samples)
        print(f"  intermediate states seen: {', '.join(intermediate) if intermediate else 'none'}")  # noqa: T201
        if alive is None:
            print("  art channel: never opened, so nothing to say about whether it survived")  # noqa: T201
        else:
            print(f"  art channel after the transition: {'alive' if alive else 'DEAD — it must reconnect'}")  # noqa: T201
        print("\nAlso record, because nothing here can see it: what the panel showed,")  # noqa: T201
        print("whether the Apple TV woke, and which input the set settled on.")  # noqa: T201
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
        help="the token the art channel presents; defaults to this deployment's TV_TOKEN_FILE, which "
        "the art channel already owns. Reading it is safe — it is the remote channel's writes that "
        "must be kept off it.",
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

    if (args.click or args.hold is not None) and not args.i_am_at_the_set:
        parser.error(
            "refusing to send a power key without --i-am-at-the-set. This reaches a real television, "
            "and one measurement is taken from the television state, which shipped code may never press at. "
            "Run with no gesture flag to read the state safely."
        )

    if not _settings_into(args, parser):
        return 2

    return asyncio.run(run(args))


def _settings_into(args: argparse.Namespace, parser: argparse.ArgumentParser) -> bool:
    """Fill what the operator did not give from this deployment's `.env`.

    The same road `__main__` takes, so on the machine that owns the wall the short
    invocation is both convenient and correct. **Nothing falls back to a literal
    address**: this file naming one would point the instrument at a wall nobody
    asked about, and the deployment-values norm forbids it besides.
    """
    # `art_token_file` is deliberately absent from this condition. It may legitimately
    # stay `None` — an art channel with no token prompts, which is a state the sitting
    # is allowed to want — so it must not be the thing that forces an `.env` read.
    if args.host and args.port and args.client_name and args.timeout and args.remote_token_file:
        return True

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
        print(f"could not read this deployment's settings: {exc}")  # noqa: T201

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

    if args.remote_token_file is not None and args.art_token_file is not None and args.remote_token_file == args.art_token_file:
        # The one invariant this tool has, checked rather than merely documented.
        # Both channels rewrite their token file on every successful open, so
        # pointing them at one path is how a measurement sitting ends with a wall
        # that cannot reach its own television — a cost paid at the daemon's next
        # reconnect, long after the run that caused it.
        parser.error(
            "--remote-token-file must not be the art channel's token file: both channels rewrite "
            "whatever they are given, and the daemon depends on that file. Give the remote channel its own."
        )

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

    return True


if __name__ == "__main__":
    raise SystemExit(main())

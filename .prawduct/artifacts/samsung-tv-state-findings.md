# Samsung Frame: what the set does in each state it can be in

**What this is.** A television that answers every question and performs none of
the work is the hardest kind of dependency to build against, and this set is one
in a state it spends most of its life in. This document records what was
*observed* — which calls work, which are accepted and ignored, and which state
each belongs to — so that the display plane's behaviour follows evidence rather
than the library's vocabulary.

**Set under test:** `QN50LS03DAFXZA` / `24_PONTUSM_FTV`, a 2024 panel, wired,
API version `5.0.1.0`, `remote 1.0`, `version 2.0.25`. Reached at
`TV_ADDRESS:8002` for both websocket channels and `:8001` for REST.

**Every row below was measured on 2026-08-07 unless it says otherwise.** Rows
marked *not observed* are gaps, deliberately left visible rather than filled in
by inference.

## The states

The set's own vocabulary and the library's disagree, and both disagree with what
the set can actually do. These are the names this product uses.

| Name here | How you get there | REST `PowerState` | `get_artmode` |
|---|---|---|---|
| **Dark** | The set is switched off at the remote; the panel shows nothing | `standby` | `off` |
| **Television** | Somebody is watching something | `on` | `off` |
| **Art mode** | The wall is showing art — the deployment's normal condition | `on` | `on` |
| **Unreachable** | Power cut, network down | no answer | no answer |

**`PowerState` says whether the panel is lit, and nothing else.** It reports
`standby` for a set whose art channel opens in 2.4 seconds and serves uploads,
deletions, listings and brightness changes without complaint; it reports `on` for
a set showing a television channel. **It does not discriminate art mode** —
`get_artmode` is the only thing that does, and the library's `on()` and
`in_artmode()` are built on `PowerState`, which is why they mislead.

> **Art mode was first observed over the API on 2026-08-07**, and `get_artmode`
> is a real discriminator after all: it answered `on` for the first time with the
> set in art mode, having answered `off` in both other states. The earlier
> readings were not a broken flag — they were the television and dark states,
> which `PowerState` cannot tell from art mode and `get_artmode` can.
>
> **`PowerState` still says only whether the panel is lit.** It reads `on` for
> art mode and for somebody watching a channel alike, so it distinguishes those
> two from `standby` and nothing more. Gate on `get_artmode` or on nothing.

## What works in each state

| Capability | Dark | Television | Art mode |
|---|---|---|---|
| REST device info (`:8001`) | works, instant | works | works *(2026-08-06)* |
| Art channel opens (`start_listening`) | works, 2.4 s | works, 2.4 s | works, 4.5 s construct *(2026-08-06)* |
| Remote-control channel opens | works, 1.5 s | works, 1.4 s | works *(2026-08-06)* |
| `available` (list content) | works — 96 items | works — 96 items | works |
| `get_current` | answers, **means nothing** | answers, **means nothing** | answers, **means nothing** |
| `get_device_info`, `get_api_version` | works | works | works |
| `get_brightness` / `set_brightness` | works | works (read) | works |
| `upload` | works | not tried | works — 39 in one pass |
| `delete` / `delete_list` | works — 41 removed in one call | not tried | works |
| `set_slideshow_status` | works | not tried | works |
| **`select_image`** | **accepted and ignored** | **switches the set into art mode and takes the screen** | works; `image_selected` at +0.49 s and +1.04 s |
| **`set_artmode('on')`** | **accepted and ignored** | not tried | n/a |
| `get_slideshow_status.current_content_id` | not tried | not tried | **empty while the slideshow is off** |
| `get_auto_rotation_status` | **never answers** (`AssertionError`) | **never answers** | **never answers** |
| Wake-on-LAN to the advertised MAC | **no effect** | n/a | n/a |

**The television state is read-identical to the dark one.** Every question
answers the same way, in the same time, with the same values — including
`get_artmode: off`. Nothing a daemon can *read* tells those two apart except
`PowerState`; `get_artmode` is what separates both of them from art mode.

### The finding that matters

**In the dark state the set accepts `select_image`, returns no error, emits no
event, and goes on displaying what it was displaying.** Confirmed over twelve
seconds and repeated attempts, with not one of `image_selected`,
`slideshow_image_changed`, `auto_rotation_image_changed` firing — nor even the
outer `d2d_service_message` that wraps them.

Everything else a daemon does in a rotation succeeds in this state. So a rotation
loop that trusts return values reports a moving wall, indefinitely, at a panel
that is dark — and the one plane that would notice, the label renderer, would
caption pictures nobody can see. This is why the display plane treats "the set
took it and displayed nothing" as its own outcome rather than as a failure to
show one work.

### Selecting an image takes the screen from somebody watching television

**Measured 2026-08-07, with the operator watching a programme and the display
daemon rotating on its normal interval.** The rotation came due, `select_image`
was sent, and the set **switched itself into art mode** — `image_selected` came
back with `is_shown: "Yes"`, the daemon truthfully logged `showing Landscape with
Two Poplars`, and the person watching lost the picture they were watching.

This was listed here as *not tried, because it would take the screen off whoever
is watching*. It does exactly that. It is the likeliest complaint this product
could cause in a household, and it is not rare — somebody watching television is
a daily occurrence.

**It is prevented as of 2026-08-07.** The daemon had not consulted art mode before
selecting, by a deliberate decision that reading it "before every selection would
cost one call on every rotation that is about to succeed" — a trade priced against
a wasted call, with the cost on the other side unmeasured. Measured, it is a
television that grabs itself back from its owner every few minutes. The plane now
asks `get_artmode` before every selection and declines unless it says `on`; see
`nonfunctional-requirements.md` § "The television belongs to whoever is using
it".

**The asymmetry is worth holding on to**, because it decides what a fix can rely
on: `select_image` moves the set from *television* into art mode, and does **not**
move it from *dark* into art mode, where it is accepted and ignored. So the call
is not a general "wake into art mode" — the panel has to already be lit. The
matching `get_artmode` readings are the discriminator a fix would gate on: `on`
in art mode, `off` in both the states where selecting is wrong.

### `get_current_artwork` does not describe the wall

**It reports the art-store slot, and no reader on this firmware answers "what is
displayed".** Its replies carry `"content_type": "artstore"`, and it named the
same id — `SAM-F0222` — across every observation ever made here: dark,
television, and art mode, before and after selections that visibly changed the
picture. Measured 2026-08-07 in art mode: the wall changed to the requested
image, `image_selected` fired at +1.04 s with `is_shown: "Yes"`, and 37 seconds
of polling `get_current` never moved off `SAM-F0222`.

**It was briefly adopted as the confirming read, on 2026-08-06, and it is worth
recording why that looked right.** In the dark state it *agrees* with the failure
— it reports a wall that is not changing, because it never changes. So the one
state it was tested against is the one where a value that means nothing is
indistinguishable from a value that means everything. The cost was a day, and a
wall that parked on a single picture the first time the set was in art mode: the
cursor only advances on a confirmed show, so the daemon re-selected the same work
on every backoff step.

**The only sound confirmation is the `image_selected` event**, which carries both
halves the question needs — *which* image, and `is_shown` — and which does not
fire at all in the dark state. It is emitted for a redundant selection too, so
re-showing the picture already on the wall confirms normally, which is what the
restart path depends on.

### The dark state cannot be left in software

Two exits were tried and neither works:

- **`set_artmode('on')`** returns cleanly and changes nothing. Fifteen seconds
  later `get_artmode` still says `off` and `PowerState` still says `standby`.
- **Wake-on-LAN** to `wifiMac` had no effect at broadcast or unicast, ports 9 and
  7. The set reports `networkType: wired` and advertises no wired MAC, so the
  packet is reaching an interface that is not listening.

`KEY_POWER` over the remote-control channel **works, and this document was wrong
to call it untried** — `platform-and-dependency-findings.md` § Waking the set
records it measured, needing *two* presses from standby: the first brings
`PowerState` to `'on'` with no art app running, the second brings the art app up.
That is the same two-step this document's own state table implies, since the
middle state is the television one. Corrected 2026-08-07 rather than re-measured;
if it is ever re-run, record it in one place and link the other.

**So the dark state can be left in software after all** — by `KEY_POWER`, not by
anything on the art channel. What this section's two bullets establish is
narrower and still holds: `set_artmode('on')` and Wake-on-LAN do not do it.

## The remote-control channel, read off the library rather than measured

Recorded 2026-08-17 as Chunk 24's `verify-api` step, **before anything is sent to
the set** — which is the order the chunk requires, and it earned its keep: the
reading found a way to break the art channel's pairing that no amount of
measurement at the panel would have attributed correctly.

Everything in this section is read off `samsungtvws` 3.0.5 source
(`async_remote.py`, `async_connection.py`, `connection.py`, `remote.py`). It is
therefore **certain about the client and silent about the set** — what the Frame
*does* with these frames is still Chunk 24's hardware sitting.

**The two channels are the same class with a different endpoint.**
`SamsungTVWSAsyncRemote` and `SamsungTVAsyncArt` both descend from
`SamsungTVWSBaseConnection`; the remote one passes `endpoint="samsung.remote.control"`.
So everything this repo already knows about the art channel's lifetime, its
`open()` failure modes and its refusal-to-connect behaviour applies unchanged.

**A press is one frame, and press-and-hold is three.** `SendRemoteKey.power()` is
exactly `click("KEY_POWER")` — `{"Cmd": "Click", "DataOfCmd": "KEY_POWER",
"Option": "false", "TypeOfRemote": "SendRemoteKey"}`. A hold is
`SendRemoteKey.hold(key, seconds)`, which returns a **list** — press, a
`SamsungTVSleepCommand`, release — for `send_commands`. So the hold gesture Chunk
24 must measure is available and needs no custom framing. (`hold_key` is the same
thing deprecated; do not use it.)

**The channel opens itself on first send.** `send_commands` begins `if not
self.is_alive(): self.connection = await self.open()`. Chunk 25's "opened lazily
and only when a press is owed" is therefore the library's own behaviour rather
than something to build — but the consequence is that **pairing failures surface
at press time, not at startup**, inside whatever the daemon was doing when the
schedule came due.

**`key_press_delay` defaults to 1 second and is charged after every command**,
including the last (`_send_command` sleeps `delay` once the payload is sent). A
click costs a second; a 3-second hold costs five. That is the budget the press-
then-confirm sequence sits on top of, and it is a constructor argument.

**`open()` distinguishes its failures, and the product should keep them apart:**
`MS_CHANNEL_UNAUTHORIZED` raises `UnauthorizedError` — the set refused this
client; `MS_CHANNEL_TIMEOUT` raises `ConnectionFailure` and the library's own log
line reads *"connection not accepted on TV, or token missing/incorrect"*, which is
the pairing prompt nobody walked over to accept.

### The shared token file will clobber the art channel's pairing

This is the finding. The websocket URL is

```
wss://{host}:{port}/api/v2/channels/{app}?name={name}&token={token}
```

— `app` differs between the two channels, **`name` and `token` do not**. And
`_check_for_token`, which runs on every successful `open()`, hands any token in
the connect response to `_set_token`, which does `open(self.token_file, "w")`.
**Whichever channel connects last overwrites the file for both.**

### This product has been opening the remote-control channel all along

Found while writing the section above, and it reverses half of it. `SamsungTVAsyncArt.__init__`
ends with `self.get_token()`, whose body builds a **synchronous `SamsungTVWS`** —
the remote-control channel. And `SamsungTVWS.__init__` is not inert:

```python
year = self._get_rest_api().get_model_year()
if not self.token:
    self.token = self._get_token()
if not self.token and year >= 24:   # initialize token now for 2024+ tv's
    try:
        self.open()
        self.close()
    except Exception:
        ...
```

**This set is `24_PONTUSM_FTV`, so `year >= 24` holds.** Two consequences:

- **A REST call for the model year on every art-client construction**, and
  therefore on every reconnect. That is the unconditional blocking cost, and
  `samsung.py`'s `_construct` docstring named the conditional half instead —
  corrected 2026-08-17 in the same pass as this section.
- **On a first pairing — an empty token file — the library opens and closes the
  remote-control channel itself, and does it without passing `name`**, so under
  the default `SamsungTvRemote` rather than under `tvpi`. The token it mints there
  is written to `TV_TOKEN_FILE`, and the art channel then presents that token as
  `tvpi` on the art endpoint.

**So the shape the section above worried about is one this product may already
depend on.** If a fresh pairing of this deployment ever ran that branch, then a
token minted on the *remote* endpoint under *one* name is being honoured on the
*art* endpoint under *another* — which would mean the token is scoped to the
device, not to the name and not to the endpoint, and would put
`config.py`'s "the set issues a token per client name" in real tension with a
deployment that works.

**Not concluded, because the premise is unverified:** the reference deployment's
token file may predate this code path entirely, carried over from the 2024 loader,
in which case the branch has never run here and proves nothing. Which it is,
nobody has checked. That is now a question for the sitting rather than a claim.

The corrected pair of hazards, then:

- **Name mismatch is real but is not new.** `SamsungTVWSAsyncRemote`'s default
  `name` is `"SamsungTvRemote"`, which is not this product's `client_name` — but
  the library already mixes exactly those two identities against one token file
  during a first pairing. So constructing the remote channel naively is *the
  status quo* rather than a novel break, and matching the name is tidiness with a
  plausible safety argument behind it, not the fix this section originally
  claimed.
- Even with the names matched, **nothing establishes whether the Frame mints one
  token per client name or one per name-and-endpoint.** If it is per-endpoint, two
  channels sharing one file overwrite each other on alternate opens, and the
  symptom is an unattended daemon that trips a pairing prompt intermittently
  forever.

  This repo does already assert the first half. `config.py`'s
  `DEFAULT_TV_CLIENT_NAME` comment states that **the set issues a token per client
  name**, which is why changing the name costs a pairing prompt — and that claim is
  load-bearing enough that the cutover was designed around it, continuing as `tvpi`
  rather than arriving as a stranger. Taken at face value it makes a shared file
  safe once the names match: both channels would present and be issued the same
  token, and each rewrite would write the same bytes.
  **It is not enough, because it answers a question nobody asked of two
  endpoints.** What it was written about is renaming a client, and every
  observation behind it was made with one channel open — this product has never
  opened two. "Keyed by name" and "keyed by name *only*" are different claims, and
  the comment can be entirely right about the first while saying nothing about the
  second.

- **The rewrite race is the hazard that survives, and it is the real one.** Both
  channels call `_check_for_token` on every successful open and both write the
  same path in `"w"` mode. A long-lived remote channel reconnecting while the art
  channel holds the same file is a case nothing above covers and nothing in this
  product has ever exercised — the library's own use of the remote channel is one
  open and close at construction, before the art channel exists.

**So the conservative design is still a separate token file for the remote
channel** — but for the second reason rather than the first. It cannot participate
in the rewrite race at all, which is the property worth having, and it costs at
most one pairing acceptance. **The moment to spend that is Chunk 24's sitting**,
when the operator is already at the set: an unattended daemon meeting its first
pairing prompt is a daemon that stops.

Whether the two channels *could* safely share one file is a measurement, and it is
in § What is still owed. It stays an optimisation: two files risk nothing, and the
evidence that sharing is safe is suggestive rather than settled.

## The library keeps ONE handler per event, not a list

Read off `samsungtvws`' own source rather than measured: `set_callback` is a
plain dict assignment. **A second subscriber to an event does not join the first,
it replaces it.**

This matters far more for `image_selected` than the sentence suggests, because
that event is how a selection is confirmed and confirmation is the only honest
account of the wall this product has. A newcomer registering for it silently
unseats the confirmation handler; every rotation then falls to its timeout and is
reported as a wall that would not move, while the newcomer works perfectly. There
is no error, no log line, and the symptom points at the television rather than at
the code that caused it.

**Closed structurally on 2026-08-07** rather than left as a warning to remember.
The television seam registers one handler and fans out through
`TvClient.observe_selections`: the pending selection is resolved first, then each
observer is called in isolation, so one that raises costs neither another
observer nor the socket's reader task. Anything wanting this event subscribes
there. A second *distinct* event is safe to register directly — that is another
`set_callback` line and its own handler.

**Not verified against the set.** The fan-out shipped with the constraint read
from library source and its behaviour pinned by unit tests over the handler; no
live television has confirmed that both a confirmation and an observer see the
same announcement. Chunk 13A's Done-when step 0b owes exactly that.

## Two library semantics that will mislead you

**`in_artmode()` and `on()` are not capability tests.** Both derive from REST
`PowerState == 'on'` (`async_art.py`), so both return `False` for a set that is
serving uploads, deletions and brightness changes perfectly well. Anything gating
work on them gates on whether the panel is lit, which is a different question
from whether the set will do what you ask.

**`get_brightness` advertises a range the set does not enforce.** It reports
`min: '0', max: '10'`, and the set accepts `-4` and reads it straight back as
`-4`. The deployment's `TV_MIN_BRIGHTNESS=-4` — carried forward from the 2024
plane without evidence — is therefore correct, and the advertised minimum should
not be used to clamp anything.

## Smaller observations

- **`available()` lists one image once per category it belongs to**, so a count of
  rows is not a count of images: a single uploaded work appeared twice, under
  `MY-C0002` and `MY-C0004`. Anything counting images must deduplicate by
  `content_id`.
- **The uploaded and art-store categories share one list.** `MY-*` ids are
  uploads, `SAM-*` are the store's. A set with nothing of ours on it still
  reports 96 items and still displays one of them.
- **`get_auto_rotation_status` has never answered on this set**, in either state
  it has been asked in. The library asserts on the empty reply. Nothing in this
  product depends on it; `set_slideshow_status(duration=0)` is what disables the
  set's own rotation, and that works.

## The art channel can refuse to open, and it is not about art mode

`start_listening()` failed repeatedly on 2026-08-07 **with the set in art mode
and serving everything else** — alternating between hanging to the 30 s ceiling
and raising `ConnectionFailure: {'event': 'ms.channel.timeOut'}`. It cleared on
its own after a couple of minutes' quiet.

What preceded it was heavy connection churn: about twenty open-and-close cycles
in three minutes from a polling probe, then a daemon **killed with SIGKILL**, so
its websocket was never closed from the set's side. The likeliest reading is a
small cap on concurrent art-channel clients, with abandoned ones held until they
time out — which would mean every failed attempt, itself holding a slot for 30 s,
makes the next one likelier to fail. Retrying harder is the wrong response.

**This retires a claim two artifacts used to carry**, that `ms.channel.timeOut`
is the signature of a set that is not in art mode. It is not: it has now been
seen in art mode, and the dark state opens the channel in 2.4 s. `samsung.py`'s
connect path no longer names art mode in its timeout message either — it used to
send the reader to the remote control for a fault that clears by waiting, and now
reports what has been observed instead.

**Unquantified**, and worth knowing before the Pi runs `Restart=always`: how many
clients the set allows, and how long an abandoned one is held. A daemon that
crash-loops could lock itself out of its own television.

## What is still owed

1. **The concurrent-client limit** described in the section above.
2. **Whether a set moved into art mode by `select_image` returns to the
   programme** when the viewer presses the source or power key, or whether they
   have to navigate back — i.e. how expensive the interruption above actually is
   to recover from.
3. **Whether the Frame mints one token per client name or one per name-and-
   endpoint** — the question § The shared token file will clobber the art
   channel's pairing leaves open, and which `config.py`'s
   `DEFAULT_TV_CLIENT_NAME` comment answers only halfway, having been written
   about renaming one client rather than about opening two channels. Answering it
   only ever buys the right to share one token file; the two-file design is safe
   without it, so this is an optimisation and not a blocker. **Cheap to fold into
   Chunk 24's sitting** — open both channels under one name and one file, then
   reconnect the art channel and see whether it is still authorised.
4. **Whether this deployment's token file was ever minted by the library's own
   first-pairing branch**, or carried over from the 2024 loader — the premise
   § This product has been opening the remote-control channel all along needs
   before it can conclude anything about token scope. Answerable without the set,
   by whoever knows the provenance of the file on the Pi; if that branch did run
   here, `config.py`'s per-client-name claim needs revisiting rather than citing.
5. **The whole of Chunk 24's transitions table**, which is what that chunk exists
   to fill: three starting states × click and hold, the `PowerState` and
   `get_artmode` readings after each, **how long they take to settle**, whether a
   press from dark wakes the Apple TV over CEC and leaves the Frame on its input,
   whether art mode reaches dark in one press or two, and whether the art channel
   survives a power transition or must reconnect. Nothing above answers any of
   these — the section above is the client half, read off source, and these are
   the set.

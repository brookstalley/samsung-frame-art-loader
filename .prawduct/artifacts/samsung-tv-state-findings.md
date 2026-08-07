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
could cause in a household, it is not rare — somebody watching television is a
daily occurrence — and **nothing in the display plane currently prevents it**: the
daemon does not consult art mode before selecting, by a deliberate decision that
reading it "before every selection would cost one call on every rotation that is
about to succeed". That trade was priced against a wasted call. The real price is
a television that grabs itself back from its owner every few minutes.

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

`KEY_POWER` over the remote-control channel is **untried**. The channel opens in
this state, so it is the remaining candidate; what it wakes the set *to* — art
or a source — is unknown.

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
connect path still names art mode in its timeout message; that message is a
plausible guess offered to an operator, not a diagnosis, and the honest version
of it is that the set accepted a socket and then said nothing.

**Unquantified**, and worth knowing before the Pi runs `Restart=always`: how many
clients the set allows, and how long an abandoned one is held. A daemon that
crash-loops could lock itself out of its own television.

## What is still owed

1. **Whether `KEY_POWER` lights the panel**, and what it lights it to.
2. **The concurrent-client limit** described in the section above.
3. **Whether a set moved into art mode by `select_image` returns to the
   programme** when the viewer presses the source or power key, or whether they
   have to navigate back — i.e. how expensive the interruption above actually is
   to recover from.

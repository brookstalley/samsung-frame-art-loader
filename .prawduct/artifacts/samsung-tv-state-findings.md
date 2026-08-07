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
| **Art mode** | The wall is showing art — the deployment's normal condition | **not observed** | **not observed** |
| **Unreachable** | Power cut, network down | no answer | no answer |

**`PowerState` says whether the panel is lit, and nothing else.** It reports
`standby` for a set whose art channel opens in 2.4 seconds and serves uploads,
deletions, listings and brightness changes without complaint; it reports `on` for
a set showing a television channel. **It does not discriminate art mode** —
`get_artmode` is the only thing that does, and the library's `on()` and
`in_artmode()` are built on `PowerState`, which is why they mislead.

> **Art mode has never been observed over the API on this set.** `get_artmode`
> has answered `off` on every occasion it has been asked, in both states above.
> A run on 2026-08-06 passed nine checks with `PowerState: "on"` and was recorded
> as being in art mode, but that reading is now known not to establish it — the
> television state produces the same value. **So the art-mode row above is empty
> on purpose, and everything this product believes about art mode rests on the
> `image_selected` event observed firing at +2.15 s in that run.** Confirming it
> is the first thing to do at the set.

## What works in each state

| Capability | Dark | Television | Art mode |
|---|---|---|---|
| REST device info (`:8001`) | works, instant | works | works *(2026-08-06)* |
| Art channel opens (`start_listening`) | works, 2.4 s | works, 2.4 s | works, 4.5 s construct *(2026-08-06)* |
| Remote-control channel opens | works, 1.5 s | works, 1.4 s | works *(2026-08-06)* |
| `available` (list content) | works — 96 items | works — 96 items | works |
| `get_current` | works | works | **not observed** |
| `get_device_info`, `get_api_version` | works | works | works |
| `get_brightness` / `set_brightness` | works | works (read) | works |
| `upload` | works | not tried | works |
| `delete` / `delete_list` | works — 41 removed in one call | not tried | works |
| `set_slideshow_status` | works | not tried | works |
| **`select_image`** | **accepted and ignored** | **not tried — it would take the screen off whoever is watching** | `image_selected` at +2.15 s *(2026-08-06)* |
| **`set_artmode('on')`** | **accepted and ignored** | not tried | n/a |
| `get_auto_rotation_status` | **never answers** (`AssertionError`) | **never answers** | **never answers** *(2026-08-06)* |
| Wake-on-LAN to the advertised MAC | **no effect** | n/a | n/a |

**The television state is read-identical to the dark one.** Every question
answers the same way, in the same time, with the same values — including
`get_artmode: off`. Nothing a daemon can *read* tells these two apart except
`PowerState`, and nothing tells either of them from art mode except `get_artmode`,
which has never yet said `on`.

### The finding that matters

**In the dark state the set accepts `select_image`, returns no error, emits no
event, and goes on displaying what it was displaying.** Confirmed over twelve
seconds and repeated attempts, with `get_current` unchanged throughout and not
one of `image_selected`, `slideshow_image_changed`, `auto_rotation_image_changed`
firing — nor even the outer `d2d_service_message` that wraps them.

Everything else a daemon does in a rotation succeeds in this state. So a rotation
loop that trusts return values reports a moving wall, indefinitely, at a panel
that is dark — and the one plane that would notice, the label renderer, would
caption pictures nobody can see. **This is why a selection is confirmed by
reading `get_current` back**, and why the display plane treats "the set took it
and displayed nothing" as its own outcome rather than as a failure to show one
work.

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

## What is still owed

1. **Art mode itself, at all.** `get_artmode` has never returned `on` here. Until
   it does, the state this product is built for is one nobody has confirmed the
   set reports, and every capability in that column is inference from a single
   run whose art-mode reading is now known not to establish art mode.
2. **`get_current` after a selection in art mode** — the confirming read the
   display plane now depends on. It is proven to *catch* a wall that is not
   changing; that it *agrees* on one that is has never been observed. If it does
   not, the failure is loud rather than silent — every rotation reports
   `rotation.wall_unchanged` and the wall stops — but it stops the wall.
3. **What `select_image` does to somebody watching television.** Not tried on
   purpose: the plausible outcomes are that it is ignored, as in the dark state,
   or that it takes the screen away from a person mid-programme. The second is
   the one worth knowing about, and it is the likeliest source of a complaint
   this product could cause in a household.
4. **Whether `KEY_POWER` lights the panel**, and what it lights it to.

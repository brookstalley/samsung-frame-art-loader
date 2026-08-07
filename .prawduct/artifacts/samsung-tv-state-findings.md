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
| **Art mode** | The wall is showing art — the deployment's normal condition | `on` *(2026-08-06)* | not observed |
| **Television** | Somebody is watching something | not observed | not observed |
| **Unreachable** | Power cut, network down | no answer | no answer |

**"Standby" is not a state of the art service.** The REST endpoint reports
`standby` for a set whose art channel opens in 2.4 seconds and serves uploads,
deletions, listings and brightness changes without complaint. Read it as *the
panel is not lit*, never as *the set is unavailable*.

## What works in each state

| Capability | Dark | Art mode | Television |
|---|---|---|---|
| REST device info (`:8001`) | works, instant | works | not observed |
| Art channel opens (`start_listening`) | works, 2.4 s | works, 4.5 s construct *(2026-08-06)* | not observed |
| Remote-control channel opens | works, 1.5 s | works | not observed |
| `available` (list content) | works — 96 items | works | not observed |
| `get_current` | works | not observed | not observed |
| `get_device_info`, `get_api_version` | works | works | not observed |
| `get_brightness` / `set_brightness` | works | works | not observed |
| `upload` | works | works | not observed |
| `delete` / `delete_list` | works — 41 removed in one call | works | not observed |
| `set_slideshow_status` | works | works | not observed |
| **`select_image`** | **accepted and ignored** | works; `image_selected` at +2.15 s *(2026-08-06)* | not observed |
| **`set_artmode('on')`** | **accepted and ignored** | n/a | not observed |
| `get_auto_rotation_status` | **never answers** (`AssertionError`) | **never answers** *(2026-08-06)* | not observed |
| Wake-on-LAN to the advertised MAC | **no effect** | n/a | n/a |

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

1. **The art-mode column**, measured rather than inferred — in particular
   `get_current` after a selection, which is the confirming read the display
   plane now depends on. It is proven to catch the dark state; that it agrees
   promptly on a healthy one rests on the `image_selected` timing from
   2026-08-06 and has not been observed directly.
2. **The television column**, entirely. What a daemon rotating the wall does to
   somebody watching a film is unknown, and it is the state most likely to
   produce a complaint.
3. **Whether `KEY_POWER` lights the panel**, and what it lights it to.

# Platform and Dependency Findings

Recorded 2026-07-19, during recovery of this project from the Raspberry Pi SD
card. The project had been cold since 2024-08-19 (last boot) and its last commit
was 2024-08-02. Everything below was verified against the card or against
upstream repositories on 2026-07-19 — it is not recalled from the original work.

## Target hardware

- **Raspberry Pi 4 Model B.** Confirmed by the user.
- **Waveshare 6 inch HD e-Paper HAT** — IT8951 controller, 1448x1072, 16-level
  greyscale. Note this is *not* the display the existing index was rendered for:
  `label_file` entries in `all.json` carry `_w648_h480`, a smaller panel.
- Samsung Frame TV, reached over the LAN.

## Python target: 3.13 — superseded as a product-wide decision

> **SUPERSEDED 2026-07-20. Read this section as the DISPLAY plane's target only.**
> When it was written the product was one process, so "target 3.13" was
> product-wide. It is not any more: the two-plane split (2026-07-19) gave the
> curation plane its own interpreter, and **the curation plane runs Python 3.14**
> on a uv-managed standalone build, with `3tears` left unmodified. See
> `operational-spec.md` § The Curation Interpreter and `project-preferences.md`,
> which records the version per plane.
>
> **The "3.14 was rejected" bullet below is retired and must not be cited.** Its
> two stated risks were both checked and did not hold: aarch64 wheels for
> opencv/scikit-image/numpy/scipy on 3.14 were verified against the PyPI JSON API
> on 2026-07-20, and the source-built Cython concern applies to the e-paper driver,
> which lives on the display plane and is exactly why that plane stays on 3.13.
>
> Everything else here — the driver-stack bounds and the Cython reasoning — still
> stands and still governs the display plane. **The unverified-build warning does
> not: it was discharged on 2026-08-04** and is struck below, where the build is
> recorded as done on 3.13/aarch64.

**Decision (display plane): target Python 3.13.** ~~Fall back to 3.12 if the
IT8951 build fails.~~ **The fallback contingency is discharged, 2026-08-04:** the
build did not fail. 3.12 remains a floor — nothing requires dropping it — but it is
no longer a landing site this decision is prepared to use.

Rationale:

- Raspberry Pi OS Trixie (Debian 13) ships Python 3.13 as the system Python, so
  3.13 keeps the development machine and the Pi identical.
- Nothing in the driver stack declares an upper bound. `omni-epd` requires
  `>=3.7`; `IT8951` requires `>=3.8`. The often-quoted "3.7 to 3.10" ceiling is
  stale — that was omni-epd 0.3.5, and 0.4.0 raised it to 3.11.
- `IT8951` compiles its Cython extensions from `.pyx` **sources** at install
  time rather than shipping pre-generated C. A current Cython should therefore
  emit 3.13-compatible C even though the repository itself is frozen.
- 3.14 was rejected: it adds real risk (source-built Cython extensions, possibly
  lagging aarch64 wheels for opencv/scikit-image) against a driver last touched
  in 2023, and buys nothing.

~~**This is unverified and must be proven early.**~~ **Verified 2026-08-04 on the
target hardware — the assumption resolved positively and is closed.** It had said
the evidence was from Python 3.12, not 3.13 — the recovered venv was
`.venv/lib/python3.12/` with a working `IT8951-1.0.0` built into
`build/lib.linux-aarch64-cpython-312`.

A throwaway `uv` project on a freshly built Raspberry Pi OS Trixie card
(Python 3.13.5, aarch64) installed `IT8951[rpi]` from the pinned
`9f136139378f74e17d9972d7165dc6ae53a2568e` under PEP 517 build isolation. It
built, and `import IT8951` succeeds. Installing pinned `omni-epd 0.4.1` over it
leaves `it8951==1.0.0` in place rather than re-resolving it.

**The two risks this section deliberately keeps apart both closed, and only one
was ever real:**

- **The build-isolation risk did not exist.** The premise was a 2023-era
  `setup.py` importing Cython at module scope without declaring it to PEP 517. At
  the pinned commit the project *does* declare
  `requires = ["setuptools", "wheel", "Cython"]`, so isolation was never going to
  fail on it. No remediation was needed: no build-requires override, no vendoring,
  no re-pin.
- **The interpreter risk was real and is now answered.** A current Cython does
  emit 3.13-compatible C for those `.pyx` sources on aarch64. **The fallback to
  3.12 is discharged** — struck at the decision line above; 3.12 stays a floor.

**What actually blocks a rebuilt Pi is a system package nobody declared.**
Without `python3-dev`, the install fails — but *not* in IT8951. It fails building
`rpi-gpio`, a dependency of the `[rpi]` extra, with
`fatal error: Python.h: No such file or directory`, which sends a reader hunting
in the wrong package entirely. `requirements.txt` documents an apt line for the
label's Cairo/Pango stack and `python3-dev` is absent from it; that file's own
comment observes that a dependency nothing declares is one nobody installs until
an import fails, which is what this is.

**`Cython` is unpinned in that `build-requires`,** so a future Cython that stops
emitting compatible C would break the build with nothing in this repository
having changed. **Closed for the display plane 2026-08-07** by
`[tool.uv] build-constraint-dependencies` holding it at `>=3.0,<4`;
`requirements.txt` has no equivalent mechanism and stays exposed, which is one
more reason that install path is retired rather than maintained.

**`Pins.POWER` is confirmed absent from the installed package** — checked by
attribute on the built module, not inferred from reading the abandoned checkout
below. If the 6 inch HD needs HAT power control, that constant has to be added.

## The 2024 modules' pins have no wheels for Python 3.13

Recorded 2026-08-04, when a rebuilt Pi first tried to install them.
**`numpy==2.0.0` and `scikit-image==0.24.0` publish no cp313 wheels** and fall
back to building from source on the Pi. They *resolve* cleanly, so
`uv pip install --dry-run` reports success and the cost appears only when a real
install starts compiling.

Nothing on the television path needs them: `tv_api_check.py` imports only
`requests`, `samsungtvws`, `websockets` and `python-dotenv`, and the live
hardware pass was run against exactly that subset.

**This is also the answer to whether the display plane could move to Python
3.14.** The obstacles are these 2024-plane pins, not the driver stack — the
e-paper stack itself builds on 3.13 and declares no upper bound. The curation
plane already rejected `numpy`, `opencv` and `scikit-image` outright, computing
LAB conversion and CIEDE2000 distance in first-party arithmetic instead, so these
pins retire with the 2024 modules rather than needing to be solved. What *would*
keep the display plane on the system interpreter regardless is its need for distro
C bindings, which is the standing reason the two planes have different
interpreters at all.

## GPIO is a non-issue on this hardware

The Pi 5's RP1 I/O controller breaks `RPi.GPIO`, which is why `rpi-lgpio` exists
as a drop-in replacement (and why the two cannot coexist in one environment).
**None of that applies here** — on a Pi 4, `RPi.GPIO` works normally and the
`IT8951[rpi]` extra can be installed as-is.

The recovered venv contained *both* `RPi.GPIO-0.7.1` and `lgpio-0.2.2.0`, and
`.lgd-nfy0` files (an lgpio artifact) were present in two project directories.
This looks like a Pi 5 GPIO conflict but is not one — `lgpio` was almost
certainly pulled in incidentally by PaperPi or gpiozero, both of which were also
checked out on the card.

## The driver stack is dormant

| Package | Last commit | Notes |
| --- | --- | --- |
| `robweber/omni-epd` | 2024-11-15 | Last release 0.4.2 |
| `GregDMeyer/IT8951` | 2023-11-08 | No releases published |

Neither has a commit or changelog entry mentioning Raspberry Pi 5, Python 3.12+,
Trixie, or lgpio. IT8951's history shows a recurring pattern of Python-version
fixes being opened and then closed unmerged (PRs #45, #55, #59).

Two consequences:

1. **The display driver is the most fragile dependency and also the most
   isolated** — the entire hardware surface is `display.py` (omni-epd) and
   `spi_test.py` (RPi.GPIO, spidev), about 119 lines. Putting it behind an
   interface means a driver failure is a swap rather than a rewrite, and stops a
   frozen 2023 repository from dictating the project's Python version.

2. **Builds were not reproducible, and now are.** omni-epd declares its
   dependency as `IT8951[rpi] @ git+https://github.com/GregDMeyer/IT8951.git`
   with no commit pin, so it resolved to whatever `master` currently was — which
   worked only because the repository has not moved since 2023. **Pinned to
   `9f13613` on both install paths 2026-08-07**, with vendoring rejected: it buys
   only survival if the repository disappears, and costs 1,500 lines of Cython
   nobody here can maintain plus the ability to take any upstream fix. It stays
   the escape hatch, and `deploy/pi-freeze-2024.txt` records what to vendor.

## The e-paper panel, verified against the panel itself

Measured 2026-08-04 on the wall's own Waveshare 6 inch HD, driven through
`omni-epd`'s `waveshare_epd.it8951` driver on the rebuilt Trixie card. Read off
the running panel, not from either project's source. **Re-measure after an
omni-epd or IT8951 bump** — both are dormant repositories, so a version move is
the only thing that changes these.

**The panel loads clean and reports 1448x1072**, matching § Target hardware.
Full-frame draw takes **1.5–1.9 s** against the 15 s label budget in
`nonfunctional-requirements.md` — roughly 10× headroom, so that
`[ASSUMPTION: 15 s | LOW impact]` is safe by a wide margin. `gray16` (1.49 s)
measured *faster* than `bw` (1.86 s), which is counterintuitive; that is one
sample and nothing should be designed around it.

### The greyscale default is a silent trap

**`modes_available` is `('bw', 'gray16')` and the driver's default is `bw`.**
Every legibility claim this product makes — the 16-level greyscale panel in
`nonfunctional-requirements.md`, the whole of `design_decisions.accessibility_approach`
— assumes 16 grey levels. A driver that does not explicitly set `mode = "gray16"`
gets 1 bit.

**`max_colors` reports 16 in both modes**, so the obvious sanity check cannot
tell them apart. Reading `mode` is the only honest test. Taken together these two
are worse than a plain defect: they would ship 1-bit type past every check a
reasonable person would think to run, and the failure is visible only to someone
standing in front of the panel comparing it to a memory of what it should look
like.

The consequence for the display plane is a requirement, not a note: **set the
mode explicitly and assert it was taken**, and assert on `mode` rather than on
`max_colors`.

The 2024 code shows what the trap catches. `display.py:41` passes
`greyscale_bits=1` to `ArtLabel`, which never stores or uses it
(`art.py:246-251`) — so 2024 rendered 1-bit type into a panel left in its 1-bit
default, and nothing anywhere reported it.

### Failure is unreadable from the return, and every change is a full frame

**`display()` returns `None`** in both modes. Success and failure are
indistinguishable from the return value; raised exceptions are the only signal
there is. This is the same shape as the television's `upload()` defect below, and
it wants the same treatment — the caller must not read a return value as
confirmation.

**No partial refresh exists** on omni-epd's surface for this driver. The whole
surface is `clear`, `close`, `display`, `prepare`, `sleep`. Every label change —
even one changed character — is a full-frame redraw at the cost measured above.

### The text stack installs under uv, and needs no distro *Python* packages

Measured on the Pi 2026-08-07, in a scratch venv, because the answer decides
whether the display plane's panel dependencies can be a uv dependency group at
all or have to reach into system site-packages.

**`uv pip install pygobject pycairo` resolves PyGObject 3.56.3 and pycairo 1.29.1
on Trixie/aarch64 and both import cleanly** — `gi.require_version("PangoCairo",
"1.0")` and the repository import succeed. PyGObject arrived as a wheel; only
pycairo built, in 12 s. **No `apt install python3-gi` is involved**, which is the
finding that matters: the 2024 requirements file documents a five-package apt
prerequisite list for exactly this, and it is now needed only by that install
path.

**Corrected 2026-08-10 — this section was titled "needs no distro packages" and
that is not what was measured.** What the Pi run shows is that no distro *Python*
package is needed; it says nothing about C headers, and the difference cost a red
CI job the first time the typesetting leg ever executed. `display/uv.lock` is the
authority and it is unambiguous: **pycairo 1.29.1 publishes Windows wheels only
(`win32`, `win_amd64` and `win_arm64`, across cp312–cp315), and PyGObject 3.56.3
publishes no wheel at all** — sdist only. The load-bearing half is that **no Linux
wheel exists for either**, on any architecture.
Every Linux install therefore compiles both from source and needs cairo's and
girepository's development headers present. The GitHub runner had neither and
failed at `Run-time dependency cairo found: NO (tried pkg-config and cmake)`.

Why the Pi got PyGObject prebuilt when PyPI carries no such wheel is **not settled
here** — a Pi-local wheel index is the obvious candidate and was not checked. What
is settled is that "it arrived as a wheel" was an observation about one machine
and was read as a property of the package. The generalisable form: *a measurement
of what installs on the machine in front of you bounds nothing about the machine
in CI*, and the sentence recording it has to carry the architecture it was taken
on or it will be read as universal.

The consequence is that the panel's dependencies split cleanly by *which machines
can install them*, which turns out to be the same seam the code splits on:
`raster` (the text stack, installable on any modern Linux including a CI runner)
and `epaper` (`omni_epd`, which compiles Cython against the Broadcom SPI and GPIO
libraries and installs on a Pi and nowhere else). **The typesetting is therefore
tested by CI rather than only by whoever last had a Pi in front of them.**

**PyGObject DOES work on this project's development Mac — corrected 2026-08-13.**
It resolves as a uv wheel (PyGObject 3.56.3 against Pango 1.57.1) and imports,
renders through PangoCairo and passes `display/tests/raster` there. What this
paragraph said before, and said for months, was that it "does not work at all"
and that no time should be spent on it: it built under Homebrew and then failed
at import inside `gi/overrides/__init__.py`, and reinstalling
`gobject-introspection`, clearing a duplicate glib keg and setting
`GI_TYPELIB_PATH` all failed. That was a Homebrew toolchain skew, and the wheel
route sidesteps it.

**The correction is the finding, and the cost of the stale version was real.** A
"do not spend time on it" note is one nobody re-tests, so the product's most
important accessibility surface was believed unrunnable locally and was first
seen in CI — which is where the byte-offset work for the styled runs would have
been proved, if 13B-2 had not happened to check. **The CI job stays regardless**:
it is what tests the typesetting on a machine nobody has to remember to use, and
a runner is the only place the claim holds for everyone.

None of this changes why the label's *judgement* (what it says, where it goes) is
a separate tier from its rasterization: an optional dependency group is still
optional, a device with a television and no panel installs neither half, and a
tier that needs no text stack is testable in a plain `uv sync`.

### Type sizing was settled 2026-08-11, and the probe's range was wrong

**Superseded, and kept because the correction is the finding.** The type ladder
put in front of the operator on 2026-08-04 was rendered with **PIL/DejaVu** while
the product renders with **Pango** — different rasterizer, different face,
different metrics — so this section correctly said its pixel numbers did not
transfer. It then recorded a surviving **range**, mid-20s through low-40s px, as
the thing the look *had* established.

**That range was not merely untransferable, it was below the threshold of
legibility**, and nothing here could tell because this document recorded no
viewing distance. Measured on 2026-08-11: the panel is 6 inches diagonal at
1448×1072 (~300 PPI) and is read from 7 feet, which makes 26 px a cap height of
**2.5 arcminutes** against the **5** that 20/20 vision needs to resolve a letter
at all. The low end of the live range was half the resolvable size, and the high
end barely reached it.

The numbers are no longer judged. They derive from the two physical facts above
against a calibrated cap height — `display/src/display/panel/legibility.py`, with
the reasoning in `accessibility-spec.md` § The type floor is derived from viewing
distance. On this panel that is a 130 px primary tier over a 92 px floor.

## The television, verified against the set itself

Everything below was measured on the wall's own television on 2026-08-04, running
**firmware 1310**, by executing `tv_api_check.py` and instrumented probes. It is
not read from the library's source. **Every figure here is firmware-scoped** —
after any firmware change, re-run that script rather than trusting this section.

**The set:** `QN50LS03DAFXZA`, reported as "The Frame", model `24_PONTUSM_FTV`
(2024 generation), Tizen, `TokenAuthSupport: true`, `resolution 3840x2160`,
`networkType: wired`. Art API version **4.3.4.0** — the new API, carrying the
`slideshow_*` verbs. It is a **50 inch** panel; the diagonal is deployment
configuration and feeds every physical-size judgement the product makes.

### `upload()` reports failure on uploads that succeeded

**This is the defect to design around, and it is worse than a plain failure
because it lies in the safe-looking direction: the image is on the television and
the caller is told it is not.** A caller that retries on a falsy return duplicates
images on the wall.

**What was measured, on the set, 2026-08-04:**

| Run | Result |
|---|---|
| Default `timeout=10`, bytes argument | returned `None` — **and the image landed**: the work the set listed carried the exact `image_date` this request sent |
| Default `timeout=10`, path argument | raised `AssertionError` out of `upload()` |
| Explicit `timeout=60`, path argument | returned its content id, **8.39 s** wall-clock |

> **Corrected 2026-08-04, and the correction matters to anyone fixing this.** An
> earlier version of this section made three claims it could not support, all
> since checked against the pinned source.
>
> **It attributed the two failures to the argument form.** `upload()` returns
> `None` on a timed-out acknowledgement regardless of form — `wait_for_response`
> then `return data["content_id"] if data else None`. The two runs above differ in
> more than their argument and the form is not established as the cause.
>
> **It cited the raise as an `assert data` "on the acknowledgement" at line 434.**
> That line is inside `get_thumbnail`. `upload()`'s only assertion guards the
> `send_image` handshake, *before* any bytes move, and its acknowledgement path
> does not assert at all. **The raise site is therefore not established** — the
> plausible mechanism is a late reply desynchronising response correlation, so a
> subsequent request asserts on a reply that is not its own, which is the failure
> mode the deletion wrapper was already written against. One instrumented run
> would settle it; until then this is a hypothesis, not a finding.
>
> **It reported the 8.39 s as "84% of the default" acknowledgement budget.** That
> figure is wall-clock for the whole call — transfer *and* acknowledgement — which
> `tv_api_check.check_upload` notes cannot be separated from outside the library.
> The timeout governs only the acknowledgement, so the ratio was never computable
> from what was measured.
>
> **None of this weakens the defect.** A default-window upload failed twice and a
> wide-window upload succeeded, and a reported failure was observed to have landed.
> What is retracted is the mechanism, not the behaviour.

**The rule this establishes, which generalises beyond upload:** *this library's
return values are not trustworthy in either direction — confirm against the
television's own content list.* Removal already works this way, and the same
treatment is owed to upload: pass an explicit timeout well above the default, and
on a falsy or raising result, read the category back before concluding anything.
Deletion's wrapper was written because collapsing *failed* into *unconfirmable*
was the original defect; upload has the mirror-image bug, collapsing *succeeded*
into *failed*.

Verified working on the same set: removal confirmed against the set's own list
returned `requested=1, deleted=1, surviving=()`, and the television was left
holding exactly the 41 works it started with.

### The upload data path is a second, separate TLS socket

Captured from the wire, because this is the expensive knowledge to re-derive and
nothing documents it. Uploading is **not** a websocket transfer:

1. Client emits `art_app_request` / `send_image` over the art channel, carrying
   `file_size`, `file_type`, `image_date`, `matte_id` and a `conn_info` naming
   `d2d_mode: "socket"`.
2. The set replies `ready_to_use` whose `conn_info` carries
   **`ip`, `port`, `key`, `stat`, `mode: "socket"` and `secured: true`** — a
   freshly allocated ephemeral port, different every upload.
3. The client opens a **separate TCP connection to that ip/port, TLS-wrapped
   because `secured` is true**, and streams the image in chunks.
4. Only then does the acknowledgement come back on the art channel — which is the
   step the 10 second default fails to wait out.

`secured: true` on this generation is handled by the library and is not a defect;
it is recorded because a hand-written client that ignored the flag would connect
in plaintext to a socket expecting TLS and fail with nothing pointing at why.

### Constructing the client performs blocking network I/O

Three measurements, because the spread is the finding:

| Condition | Blocking time |
|---|---|
| Valid cached token | **0.24 s** |
| No token — pairs during construction | **8.42 s** |
| Set asleep or in art mode | **~15.1 s** |

The blocking call is `get_token()`, which opens and closes the *remote-control*
websocket — a different channel from the art channel everything else uses. **A
daemon cannot construct this client on its event loop**, and the worst case is the
one that happens when the television is asleep, which is most of the time.

### Pairing needs the set genuinely awake, and says so misleadingly

With the set in art mode or standby, the remote-control channel **accepts the
websocket handshake and then sends nothing at all**, and the art channel answers
`ms.channel.timeOut`. That reads exactly like a protocol or library
incompatibility and is not one — `PowerState: 'on'` is the entire fix, after which
the set shows its allow dialogue and a token is issued. Anyone debugging a
first-connection failure should check power state before suspecting anything else.

> **Corrected 2026-08-07, and the correction is narrower than it looks.** The
> paragraph above describes *pairing*, with no token yet issued. It does **not**
> generalise to a client that already holds one: with a cached token in
> `TV_TOKEN_FILE`, both websocket channels open in **standby** (art channel in
> 2.4 s) and in **art mode**, and uploads, deletions, listings and brightness all
> succeed against a set whose panel is dark.
>
> So **`ms.channel.timeOut` is not a power-state signature.** It has since been
> seen with the set *in art mode and working*, after about twenty
> connect-and-close cycles in three minutes plus a daemon killed with SIGKILL that
> never closed its socket — which points at a cap on concurrent art-channel
> clients, with abandoned ones held until they time out. Read it as "too many
> connections lately", not "the set is asleep". `samsung-tv-state-findings.md`
> carries the state-by-state map.

The art channel itself is reachable **without** a token and answers
`ms.channel.connect` with a client list, so "the art channel responds" is not
evidence that pairing succeeded.

### Only one of the three image-changed events exists on this set

The 2024 loader registers three callbacks — `slideshow_image_changed` (new API),
`auto_rotation_image_changed` (old API) and `image_selected`. Provoked with a real
`select_image()` against an uploaded work, **only `image_selected` fires**, at
**+2.15 s**. The other two are dead wire here.

That is consistent rather than surprising: the two that stayed silent are
*slideshow advance* events, and host-driven rotation never advances the set's own
slideshow. It means the old/new API split costs this product nothing — the event
it depends on is the one that is not part of that split — and that a display
process needs to register exactly one callback, not three.

**That finding came from instrumented probes, and it could not have come from a
callback's own arguments** — which is a trap for anything that registers one.
`process_event` selects the callback by the *sub*-event carried inside the
message (`self.callbacks[sub_event]`) but invokes it with the *outer* websocket
message type, so **every art-channel callback is called with
`event="d2d_service_message"`**, whichever event actually fired. A recorder that
logs its first argument reports that constant forever and looks like a finding
about the television. Capture the trigger in a closure at registration instead;
selection by sub-event is what makes that exact. This cost a live run its answer
to the question the registration exists to ask, and the run's report gave no sign
it had.

### Detecting that the set is actually in art mode

**This is the signal a display process needs, and the obvious candidates do not
work.** Establishing it took the sequence below; it is written down because each
wrong answer looks right until it fails.

| Candidate | Verdict |
|---|---|
| `PowerState` from the REST endpoint | **Cannot distinguish art mode from normal TV** — reports `'on'` for both. Only tells you `'standby'` vs not |
| `get_artmode()` | **Answers in both directions** — `'on'` in art mode, `'off'` for a dark panel and for a television programme alike. See the correction below; the claim that it can only confirm the positive case was wrong |
| Presence of an `isHost: true` client in the art channel's `ms.channel.connect` frame | **Works, in both directions, without `start_listening()`** |

The set's own art application appears in the art channel's client list as a
`"deviceName": "Smart Device"` entry with `isHost: true`, and it is the peer that
`d2d_service_message` replies come *from*. When art mode is off that entry is
absent, the channel still accepts a raw websocket handshake and still returns
`ms.channel.connect` — so "the art channel responded" proves nothing — and
`start_listening()` then **hangs waiting for a ready event that never arrives**.

**It hangs rather than raising, and that is the operational point.** The same
condition was also observed raising `ms.channel.timeOut` after roughly 15 seconds
on a different attempt, so the behaviour is not even consistent between runs.
Anything that calls `start_listening()` unattended needs its own timeout around it
and must not assume the call returns.

> **Corrected 2026-08-07, and this one is load-bearing rather than tidying.** The
> premise above — that `start_listening()` fails whenever art mode is off, so
> `get_artmode()` can only ever confirm the positive case — does not hold with a
> **cached pairing token**. With one in `TV_TOKEN_FILE` the art channel opens in
> 2.4 s against a dark panel and against a set showing a programme, and
> `get_artmode()` answers `'off'` in both, `'on'` in art mode. All three readings
> are measured.
>
> **The display plane's safety gate depends on exactly that negative case.**
> Selecting an image on a set showing a television programme switches it into art
> mode and takes the screen off the person watching, so the daemon asks
> `get_artmode()` before every selection and declines unless it says `on`. Had
> this row still been believed, the gate would have looked impossible to build.
>
> The `isHost` technique below is still the only method that works *without* a
> token, which is what it was written for, and it remains the right answer for
> first-contact tooling.

**The set can be driven out of standby from software.** `KEY_POWER` over the
*remote-control* channel works. Two presses were needed from standby: the first
produced `PowerState: 'on'` with no art app running, the second brought the art
app up.

> **One clause here was retired on 2026-08-07**: this used to add "and that
> channel is reachable in standby while the art channel is not". The art channel
> *is* reachable in standby — it opens in 2.4 s with a cached pairing token, and
> serves uploads, deletions, listings and brightness against a dark panel. What
> is not available there is `select_image` taking effect, which is a different
> statement. See `samsung-tv-state-findings.md`.

> **What is NOT established, and should not be inferred from the above.** The
> power states almost certainly form a three-way arrangement — fully on, art mode,
> fully off — and only a two-press cycle from one starting state was observed. It
> was never determined whether the `'standby'` the set started in was fully off or
> a sleeping art mode, and press-and-hold was not tested at all. Treat the
> *detector* row above as established and the *transitions* as a sketch; a process
> that needs to put this set into art mode deliberately has mapping left to do.

### The library choice, re-verified 2026-08-04

The pinned fork `NickWaterton/samsung-tv-ws-api@fe95ef1` **is** that fork's
master, and master has not moved since 2026-04-06. The upload defect above is
therefore live upstream with no fix coming.

`xchwarze/samsung-tv-ws-api` — the actively developed project the PyPI
`samsungtvws` package is built from, with commits landing the same week — was
re-checked rather than assumed, because its art code has been reorganised into a
`samsungtvws/art/` package since it was last examined. **The reorganisation is
packaging only.** That package contains one module exposing
`class SamsungTVArt(SamsungTVWSConnection)` with a synchronous `def upload`. There
is no async art client and no art event callbacks; the project ships
`async_remote` and `async_rest` but has deliberately not done async art.

**What the fork is actually worth is the async art client**, not the callbacks.
Every television call in this repository is awaited inside an asyncio process, so
adopting the synchronous client means wrapping each call in a thread executor —
real work, worse fit, bought only with upstream liveness. The callbacks are the
weaker half of the case: the three registered in the 2024 loader are commented as
examples and dispatch to a handler that only logs at debug level, and because
rotation is host-driven the process already knows what it selected. Their genuine
use is noticing changes the host did **not** make — the remote, the phone app, the
set's own art UI — which polling the current image would also cover.

**The standing risk, stated plainly:** an unowned fork, four months static,
carrying a known defect, with no maintained alternative offering what this
product uses. The mitigation is not switching upstreams — it is keeping the
television boundary small and behind an interface, so replacing the client is a
swap rather than a rewrite. That is the same reasoning already applied to the
e-paper driver above, and the reason the protocol trace in this section is written
down: it is the expensive part of ever writing a replacement, and it was captured
once, from a live set.

## The abandoned IT8951 checkout — do not resurrect

`/home/tvpi/source/IT8951` on the card was a local checkout at upstream
`9f13613` with **uncommitted** modifications to `spi.pyx` (41 lines) and
`constants.py` (90 lines). It was never what ran in production: the project
venv's `direct_url.json` shows `IT8951-1.0.0` was pip-installed from
`https://github.com/GregDMeyer/IT8951.git` at `9f13613` — stock upstream.

The modifications are mid-debugging work-in-progress and are **broken**. Both
`read()` and `write()` index the low byte at `2*i` where it should be `2*i + 1`,
so `write()` discards the high byte of every word. Debug `print()` calls were
left enabled throughout. The `constants.py` diff is almost entirely a formatter
run that stripped `=` alignment padding.

Exactly one line is worth salvaging, if the 6 inch HD needs power control:

```python
class Pins:
    POWER = 18    # BCM 18 — HAT power control, absent from upstream
```

The rest should be discarded.

## Recovered repository state

For the record, so it is not re-investigated: the Pi's git repository was clean
and at `5a854a9`, identical to `origin/main`. There were **no unpushed commits**
and **no uncommitted working-tree changes** — every tracked file was
byte-identical to the GitHub copy. One orphaned commit (`27210b3`, an
experimental `get_top_n_colors` returning a colour/percentage dict) and one
stash labelled "useless" were found; both were superseded by later committed work
and were deliberately abandoned in 2024. Nothing was lost.

The systemd unit that actually ran the project existed **only** on the card and
was never in version control. It is now committed at
`deploy/samsung-frame-art-loader.service`.

## That card is gone — the Pi runs a rebuild

**Everything in the two sections above describes the 2024 SD card, which is no
longer what boots.** The Pi was rebuilt onto a fresh Trixie card, and three of
the findings recovered from the old one are now false *about the machine* while
remaining true about the card they were read from. Recorded 2026-08-04, measured
over SSH:

- **Access is `brooks@pi4-tv.local`** (uid 1000, sudo, already in `spi` and
  `gpio`). ~~There is no `tvpi` user on the rebuilt card at all~~ — **resolved
  2026-08-11 at the cutover**: `tvpi` was created (uid 102, `--system`, `nologin`,
  groups `spi` and `gpio`, home `/var/lib/tvpi` for tool state), and the
  `/home/tvpi/` paths both units named were retired to `/srv/art` and
  `/opt/samsung-frame-art-loader` rather than created. See `operational-spec.md`
  § The Service Account and `deploy/README.md` § The cutover.
- ~~**The art tree is effectively empty.**~~ **Restored, and then moved.** It was
  refilled after this was written, and the cutover moved it to `/srv/art` — 168
  files, 677,652,949 bytes, counted on both sides of the move. `raw/` holds 46
  files for 40 distinct works and `ready/` holds 41.
- ~~**The checkout is behind.**~~ The deployment checkout is now
  `/opt/samsung-frame-art-loader`, owned by `tvpi` and tracking the branch it was
  deployed from. The old `/home/brooks/source/…` checkout is **left in place on
  purpose**: nothing runs it, and it holds an uncommitted `all.json` whose
  `tv_content_id`s the 2026-08-07 run wrote.

**The masters survived; the renditions did not.** The masters are on the
operator's Mac at `~/art/raw` — 46 files, 40 distinct works, 574 MB, the six
extras being byte-identical re-downloads of two works under `_0001`-style names.
That directory is already the one `operator-verification.md` symlinks a scratch
art root at, so nothing new is needed to use it. `ready/` was **not** copied and
exists nowhere off the old card, so the finished 4K television renditions are
lost as files. The television still holds its uploaded copies, which is what the
adoption path in the build plan's Chunk 12 is for; everything else re-renders
from the masters.

**The lesson generalises past this card and is in `learnings.md`:** a claim about
a live machine's current state decays silently. `deploy/README.md`, the unit file
and the recovery findings above all still *read* correctly — the machine moved
out from under them without touching a line of the text that describes it.

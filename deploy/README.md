# Deployment

**`display.service` and `curation.service` run the wall**, as the `tvpi` service
account on the Raspberry Pi driving the Frame TV. They were installed and enabled
on 2026-08-11; § The cutover below is what was run.

`samsung-frame-art-loader.service` is the **2024** unit. It is retired, it is not
installed, and it is kept here as recovered evidence until the legacy retirement —
see the banner above its recipe further down before running anything from it.

## The two new units, and where everything they name now lives

`display.service` and `curation.service` are the planes this product is being
rebuilt onto. Three paths they depend on were unsettled until the cutover and are
settled now; `operational-spec.md` § Where the two trees live records why each one
won, and this is the short form:

| | |
|---|---|
| `ART_ROOT` | `/srv/art` |
| Checkout | `/opt/samsung-frame-art-loader` |
| `uv` | `/usr/local/bin/uv`, named absolutely in both units |

**All three are off any home directory, and that is the requirement rather than a
preference.** `tvpi` is a `--system` account with `/usr/sbin/nologin`; the machine's
existing checkout and its only `uv` both sat under a home directory at mode `0700`,
which such an account cannot traverse at all. A path the service account cannot
reach is not a detail to leave to whoever reads a unit file next.

Creating that account, giving it the `spi` and `gpio` groups, moving the art tree
to `/srv/art`, placing the checkout at `/opt`, and enabling these two units are
**one change, not five** — any of them landing alone leaves a machine that is
neither the old arrangement nor the new one. `operational-spec.md` § The Service
Account is the authority on the account; the build plan's Chunk 13B entry is the
authority on the order.

> **What this cutover is not.** It has been described in the plan as the moment
> `tvart.py` stops being the production entry point. On the machine as rebuilt
> that describes a swap that does not exist: **no unit of this product is
> installed on the Pi at all** — no `samsung-frame-art-loader.service`, no cron
> entry, no user service. The 2024 loader has not run unattended since the card
> was rebuilt on 2026-08-04, and the wall has been driven by hand since. So this
> is a first install rather than a replacement, which removes the rollback
> pressure a real cutover would carry and is worth knowing before anyone plans
> around a maintenance window. The sentence is corrected here rather than
> quietly, because it read as a statement about the machine and was one.

## The cutover

Performed 2026-08-11 on `pi4-tv` (Debian 13 trixie, aarch64). This is the record
of what was run, in order, and it is the procedure for doing it again.

    # uv where any account can reach it, and the account itself.
    # Copying the operator's own binary takes whatever version that account holds
    # — 0.12.1 on the day this was run, which is the fact worth recording, since
    # nothing else in the tree pins it. `uv --version` after the copy is the check.
    sudo install -m 0755 -o root -g root ~/.local/bin/uv /usr/local/bin/uv
    sudo adduser --system --group --no-create-home --shell /usr/sbin/nologin tvpi
    sudo adduser tvpi spi && sudo adduser tvpi gpio
    sudo install -d -m 0750 -o tvpi -g tvpi /var/lib/tvpi
    sudo usermod --home /var/lib/tvpi tvpi          # see the note below

    # the checkout, owned by the account that executes it
    sudo install -d -o "$USER" -g "$USER" /opt/samsung-frame-art-loader
    git clone <this repo> /opt/samsung-frame-art-loader
    sudo chown -R tvpi:tvpi /opt/samsung-frame-art-loader

    # the art tree, moved rather than copied — same filesystem, so it is a rename
    sudo mv <old ART_ROOT> /srv/art
    sudo chown -R tvpi:tvpi /srv/art

    # dependencies, as the account that will run them
    cd /opt/samsung-frame-art-loader/display && sudo -u tvpi /usr/local/bin/uv sync --group raster --group epaper
    cd /opt/samsung-frame-art-loader/curation && sudo -u tvpi /usr/local/bin/uv sync

    # the environment file: 0640, owned by tvpi, because it carries API keys
    sudo install -m 0640 -o tvpi -g tvpi <your .env> /opt/samsung-frame-art-loader/.env

    # the units and the journal bound
    sudo cp deploy/display.service deploy/curation.service /etc/systemd/system/
    sudo mkdir -p /etc/systemd/journald.conf.d
    sudo cp deploy/journald.conf.d/10-bound-the-journal.conf /etc/systemd/journald.conf.d/
    sudo systemctl restart systemd-journald && sudo systemctl daemon-reload
    sudo systemctl enable --now curation.service
    sudo systemctl enable --now display.service

**`--no-create-home` then `usermod --home` is not a detour, it is the finding.**
An account with `HOME=/nonexistent` cannot run `uv` at all — it fails on its own
cache directory before doing any work. `operational-spec.md` § The Service Account
records why the answer is a home for tool state rather than a list of `UV_*`
variables in both units. Create it directly with `--home /var/lib/tvpi` if you are
doing this fresh; the two-step above is only what this machine's history looked
like.

**Moving the art tree is a rename when `/srv` and the old location share a
filesystem**, which is worth checking (`stat -c %d`) before assuming the move is
instant: across filesystems it is a 647 MB copy and the ownership change after it
is not free either. Verify the count and the byte total on both sides rather than
trusting `mv`'s silence — this move was checked at 168 files and 677,652,949
bytes, identical before and after.

**A machine that has never run this product needs a catalogue before the wall can
do anything.** The units come up healthy against an art root with no catalogue and
correctly do nothing, which looks like a fault and is not one. Seeding is a
separate hand-run step and it neither spends nor renders — it carries the mat
colour from the 2024 index and adopts the renders already in the tree:

    sudo -u tvpi /usr/local/bin/uv run python -m curation.seed <path to all.json>

Then create a theme and activate it, over the JSON API or the browser interface —
**activation is what publishes the manifest**, and until one is published the
display plane has nothing to rotate and says so.

### What the first start actually did, and what to expect

Read as evidence that the arrangement works, not as a promise about your machine:

- The curation plane marked the art root on its own — it holds a catalogue but had
  no marker, and a directory holding a catalogue is an art root by the only
  evidence that matters.
- The display plane adopted the 40-entry manifest, **disabled the television's own
  slideshow**, and **removed 40 images the binding table could not account for**.
  That last one is startup reconciliation working as designed: this device had no
  prior state, so nothing on the set was accounted for, and it re-uploaded all 40.
  **Expect a fresh device to re-upload the whole theme**, which took about three
  and a half minutes for 40 works.
- The set was in standby, and the plane logged *"the television is not in art
  mode; leaving the wall alone until it is"* rather than acting. The heartbeat said
  `television_reachable: true`, `television_showing_art: false`,
  `label_surface_working: null` — which is the honest reading of a device that has
  a panel and has not yet had anything to draw.

### How to tell your own install worked

**The two failures this arrangement deliberately makes loud both happen before the
process runs**, which is why "read the journal" is not the answer to them: a
missing `EnvironmentFile=` and a missing `/usr/local/bin/uv` are both refused by
systemd, so there is no application log line to go looking for. `systemctl status`
names them and `journalctl -u <unit>` does not. Run these in order; each one fails
differently from the others, which is the point of having four rather than one.

    # 1. Both units loaded, active, and enabled — enabled is the one people skip,
    #    and its absence is invisible until a reboot leaves the wall dark.
    systemctl is-active curation.service display.service
    systemctl is-enabled curation.service display.service

    # 2. The installed copies still match the checkout. They drift the moment
    #    somebody edits /etc/systemd/system directly, and nothing else notices.
    for u in display curation; do
      diff -q /etc/systemd/system/$u.service /opt/samsung-frame-art-loader/deploy/$u.service
    done

    # 3. The account can actually reach what it needs. Run AS tvpi — running it as
    #    yourself proves nothing, because your account is the one that already works.
    sudo -u tvpi /usr/local/bin/uv --version
    sudo -u tvpi test -r /opt/samsung-frame-art-loader/.env && echo ".env readable"
    sudo -u tvpi test -w /srv/art && echo "/srv/art writable"

    # 4. The display plane's own account of itself. This is the honest one: it
    #    distinguishes a device with no panel from one whose panel will not open,
    #    and a set that is unreachable from one that is simply not showing art.
    sudo cat /srv/art/display-heartbeat.json

**Read the heartbeat rather than the wall.** `television_reachable: false` is a
network or pairing problem; `television_showing_art: false` with the set awake
means somebody is watching television and the plane is correctly leaving it alone;
`has_label_surface: true` with `label_surface_working: false` is a panel that was
configured and would not open — which costs the label and nothing else, and is a
different fault from `has_label_surface: false`, which is a device that never had
one. `label_surface_working: null` means nothing has been drawn yet, not that
something failed.

**A `last_error` of `null` and a `reported_at` that is not advancing is worse than
an error**, because it means the daemon is not looping. Read it twice, a minute
apart, before believing a quiet heartbeat.

Verify the journal bound while you are here — `systemd-analyze cat-config` proves
only that the file parses:

    sudo journalctl -b -u systemd-journald | grep -i 'Journal.*max'
    # expect: "Runtime Journal (...) is 8M, max 256M, 248M free."

**The display plane's panel needs two optional dependency groups, and a default
`uv sync` installs neither.** They are separate because they install on different
machines: `raster` is the label's text stack (PyGObject and pycairo, which build
or wheel on any modern Linux), and `epaper` is the panel driver (`omni_epd`, which
compiles Cython against the Broadcom SPI and GPIO libraries and installs on a
Raspberry Pi and nowhere else). On the Pi:

    cd display && uv sync --group raster --group epaper

**A device with a television and no panel installs neither, and that is a
supported deployment** — leave `EPD_DEVICE` empty in `.env` and the wall rotates
with no label. A device with a monitor rather than e-ink would install `raster`
alone. Verified on the Pi 2026-08-07: PyGObject 3.56 and pycairo 1.29 resolve
under uv on Trixie/aarch64 with no `apt install python3-gi` needed.

**Before the unit is enabled, the checkout needs its environment file.** Since
2026-07-27 `config.py` raises at import unless `ART_ROOT`, `TV_ADDRESS`,
`LATITUDE`, `LONGITUDE` and `LOCATION_NAME` all resolve — deliberately, so that a
missing deployment value stops the process instead of quietly running against a
plausible-looking default. The unit names that file in `EnvironmentFile=`, and
`load_dotenv` independently resolves it next to `config.py`; both point at the
repository root, which is also the unit's `WorkingDirectory`. The two agree
today because they read the same file, and if they are ever pointed at
different ones **the unit's `EnvironmentFile=` wins**: it is already in the
process environment by the time the code runs, and `load_dotenv` fills only
what the environment does not carry.

> **The recipe below installs the *2024* unit, and it is kept as a record rather
> than as an instruction — do not run it.** That unit is retired: it names
> `/home/tvpi/…` paths on a machine that has no such user, it runs `tvart.py`
> through a `.venv` that no longer exists, and its hand-written `PATH` carries
> pyenv shims and a stray editor directory. It is committed exactly as recovered
> because it had only ever existed on an SD card, and it is deleted with the rest
> of the 2024 plane at the legacy retirement. The live procedure is
> **§ The cutover, near the top of this file** — not below this banner, where the
> only thing you will find is the retired recipe itself. The Provenance section at
> the foot of this file records what else was assumed from the original card.

    cp .env.example .env      # then fill it in
    sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
    sudo mkdir -p /etc/systemd/journald.conf.d
    sudo cp deploy/journald.conf.d/10-bound-the-journal.conf /etc/systemd/journald.conf.d/
    sudo systemctl restart systemd-journald
    sudo systemctl daemon-reload
    sudo systemctl enable --now samsung-frame-art-loader

**The journald line is not optional decoration.** Committing that drop-in without
installing it is how the last unit file came to exist nowhere but a card. It bounds
the journal at 256M on *both* ceilings — `SystemMaxUse=` and `RuntimeMaxUse=` —
because Raspberry Pi OS ships `Storage=volatile`, so the journal lives in RAM and a
`SystemMaxUse=`-only file would bind nothing while reading as though it does. Two
things follow from volatile storage that are worth knowing before you debug
anything: **the journal does not survive a reboot**, and **logging does not wear the
card**. The file's own header carries the detail.

Verify it took — `systemd-analyze cat-config` proves only that the file parses:

    sudo journalctl -b -u systemd-journald | grep -i 'Journal.*max'
    # expect: "Runtime Journal (...) is 9.2M, max 256M, ..."

**Skipping the first line now fails loudly, and the two ways it can fail are
worth telling apart.** If `.env` is *absent*, systemd refuses to start the unit at
all and names the path it wanted — the fastest diagnosis available. If `.env` is
*present but incomplete*, the unit starts, `config.py` raises at import naming the
first variable it could not resolve, and the unit retries every ten seconds
indefinitely rather than giving up; `systemctl status` shows it actively failing
and `journalctl -u samsung-frame-art-loader` shows the variable. Neither case is
silent, which is the whole point of both settings.

## Provenance

This unit was recovered from the Pi's SD card, where it had only ever existed at
`/etc/systemd/system/`. It was never in version control, so it was invisible to
anyone reading this repo and would have been lost with the card.

It is committed here exactly as recovered. That means it still carries the
assumptions of the machine it was written on, all of which need revisiting before
it is deployed again:

- Absolute paths to `/home/tvpi/source/samsung-frame-art-loader` and its `.venv`.
- A hardcoded `PATH` containing pyenv shims and — spuriously — a VS Code Remote
  extension directory that happened to be in the shell environment when the unit
  was written.
- `User=tvpi`.
- ~~**No `EnvironmentFile=`, and the code now requires one.**~~ **Resolved
  2026-08-02** — the unit now declares
  `EnvironmentFile=/home/tvpi/source/samsung-frame-art-loader/.env`, un-prefixed,
  so a missing file stops the unit with a message naming the path instead of
  letting a process start that will raise at import. `operational-spec.md`
  § Configuration carries the reasoning and makes it a rule for every unit, not
  just this one. Note that the *path* is still one of the machine-specific
  absolutes listed above, and moves with them if the checkout ever does.
- `After=network.target`, which does not guarantee the network is actually up.
  `network-online.target` is the correct dependency for a service that talks to
  the TV on startup.
- ~~**`Restart=always` with no `RestartSec` or `StartLimit*` override**~~ —
  **Resolved 2026-08-02.** systemd's defaults restart after 100ms and give up
  after 5 attempts in 10 seconds, so a loader that crashed on startup burned its
  whole burst allowance in half a second and landed in `failed`, permanently, with
  nothing sent anywhere — the exact opposite of the success criterion requiring
  that *"a failure in the unattended loader is visible without inspecting the
  wall"*. The unit now sets `StartLimitIntervalSec=0` with `RestartSec=10`, so a
  persistent fault keeps retrying visibly rather than going quiet; the rule is
  recorded for every unit in `operational-spec.md` § Process Management. **The
  `OnFailure=` prescription that
  used to end this bullet is withdrawn (2026-07-20):** the recorded alerting
  decision (`observability-strategy.md` § The Health Surface) chose the curation
  UI health panel as the *only* alerting surface, and a crash-looped display
  already surfaces there as a stopped heartbeat with its age shown. Wiring
  `OnFailure=` to a notification path would implement an alerting surface the
  operator explicitly declined; if the deferred push path is ever revisited, that
  is the decision to reopen — not this unit file.
- No `SyslogIdentifier` or `StandardOutput` settings, so journal lines are
  attributed by executable path. Compounded by the code's use of `print()` for
  operational output, which produces journal entries with no level and no
  timestamp — recorded as a known departure in `project-preferences.md`.

## Before you install the current `requirements.txt` on the Pi

Two pin moves are described here. This one is the more recent; both have now
been exercised against the real television.

`aiohttp` (3.9.5 → 3.14.3), `lxml` (5.2.2 → 6.1.1), `pillow` (10.4.0 → 12.3.0),
`python-dotenv` (1.0.1 → 1.2.2) and `requests` (2.32.3 → 2.34.2) moved together on
2026-08-06 to clear published security advisories against the 2024 pins. What was
verified is that the set resolves in a clean 3.12 interpreter and that every
upstream call site these modules reach still behaves — the Pillow surface, the
`lxml`-backed BeautifulSoup parse, and the `samsungtvws` imports. `beautifulsoup4`
was left at 4.12.3: it was the companion bump lxml 6 looked likely to force, and
the parse was verified against 6.1.1 without it.

**It has been run against the television, and the check is discharged.**
`aiohttp` is not imported anywhere in this repo — it is the `samsungtvws` fork's
transport — so what was owed was a measurement on the set rather than an argument
from a resolver. `tv_api_check.py` passed 9 checks and 0 failures against the real
television on 2026-08-06 on `aiohttp` 3.14.3, `websockets` 16.1.1, `requests`
2.34.2 and the pinned fork. **The display plane then drove that transport hard on
2026-08-07** — 39 uploads, 41 deletions, brightness writes and confirmed
selections, unattended, across several hours. `pi-freeze-2024.txt` records the
pre-move version of all five and remains the rollback.

> **Attempted on 2026-08-06 and got no further than the handshake**, which is
> recorded so the next person does not read "owed" as "nobody has tried".
>
> **The diagnosis in this note was wrong, and is corrected here rather than
> quietly deleted** (2026-08-07). It said a set in standby refuses the art
> channel with `ms.channel.timeOut` and that `PowerState: 'on'` is the fix. With a
> cached pairing token both channels open in standby — the art channel in 2.4 s —
> and the whole surface works against a dark panel. `ms.channel.timeOut` has since
> been seen with the set **in art mode and healthy**, after heavy connection churn
> and a SIGKILLed client that never closed its socket, so it reads as a
> concurrent-client limit rather than a power state. If you meet it, wait a couple
> of minutes rather than reconnecting harder, and stop this plane with SIGTERM so
> it closes its own socket.
>
> `PowerState` is worth reading as the cheapest thing that separates a dark panel
> from a lit one, and this is how:
>
>     curl -s http://<TV_ADDRESS>:8001/api/v2/ | python3 -m json.tool | grep PowerState
>
> **It cannot tell art mode from somebody watching television** — it reads `on`
> for both. Only `get_artmode` does that, over the art websocket rather than this
> REST endpoint, which is why there is no one-liner for it here; the display
> plane asks it before every selection.
>
> The bumped set was exercised as far as the wire in the process: a clean 3.12
> interpreter carrying exactly these pins built the client, reached the set over
> the LAN, and failed only at pairing. **Everything past the handshake is proven
> now** — the display plane drove these pins through 39 uploads, 41 deletions and
> confirmed selections against the real television on 2026-08-07.

`samsungtvws` and `websockets` moved together on 2026-08-01 — a two-year-old fork
SHA to fork master, and websockets 12.0 to 16.1.1, which the new library requires.
~~That pair has been verified to resolve and import, and has not yet been run
against the television.~~ **It was run against the television on 2026-08-04 and the
checks pass** — construction, art-mode support, API version, a real 4K upload by
path, a confirmed delete, and callback registration, against a 2024
`QN50LS03DAFXZA` on firmware 1310. **One defect was found and is not fixed**
(issue #73): at the default `timeout=10`, `upload()` **reports failure on uploads
that succeeded** — observed twice, once returning `None` and once raising
`AssertionError`, with the `None` run's image demonstrably on the set. At an
explicit `timeout=60` the same upload returned its content id. Anything calling it
must pass an explicit timeout **and** confirm against the set's own content list
rather than trusting the return. *(The mechanism is deliberately not stated here:
an earlier revision named a raise site and an argument-form rule that the library's
source does not support, and both are retracted. Issue #73 separates what was
measured from what was inferred.)*
Findings in `.prawduct/artifacts/platform-and-dependency-findings.md` § The
television. Run it yourself after any change to the pins or the set's firmware:

    python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"

That exercises upload, callback registration, and a confirmed delete against the
live set, touching only the image it uploads itself, and exits non-zero if any
check fails. If it does fail, `pi-freeze-2024.txt` below is the rollback — it
records the exact versions the wall ran on before the move.

Behaviour changes to expect. Both were established by reading the library's source
and have since been confirmed on the set by the run above. (The upload defect is a
third change, but it belongs to neither category — it was *measured* on hardware,
and the source-derived mechanism first written around it has been retracted. Issue
#73 carries it.)

- **Building the art client now performs blocking network I/O** and raises when
  the set is unreachable, where it used to defer that to first use.
- **Deletion is confirmed against the television's own content list**, and the
  loader now says which of three things happened. *Removed* — an ordinary INFO
  line with the confirmed count. *Still listed* — the set kept them: a WARNING
  naming the images. ***Unconfirmable*** — nobody could establish which of those
  it is, whether because the set refused the request or because its list could
  not be read back: an ERROR, and the run *continues*, because stopping there
  would skip the catalogue save and every pending upload to prevent some leftover
  images. That third case is the one that used to be indistinguishable from
  success.

**The code and the pins can be deployed independently**, which is what makes this
safe to land ahead of the hardware pass. `tvart.py` calls only shapes that both
library versions carry: `available(category=...)` is unchanged between them, and
`upload()` has always accepted a path — the old one reads the file itself, the new
one streams it. So pulling the checkout without reinstalling degrades to the old
buffering behaviour and keeps working, rather than breaking.

### The e-paper driver is pinned rather than vendored, and here is why

`omni_epd` **declares `IT8951[rpi]` as a git dependency with no commit**, so
installing the parent alone resolves roughly 1,500 lines of Cython — which the
label panel depends on completely — to whatever that repository's master is on the
day. Builds are reproducible today only because it has not moved since 2023: a
fact about upstream inactivity, not a property of this project.

**Decision taken 2026-08-07: pin it.** A vendor buys exactly one thing a pin does
not — survival if the upstream repository disappears — and costs 1,500 lines of
Cython nobody here can maintain plus the ability to take any fix from upstream.
Vendoring stays available as the escape hatch if that repository ever goes away;
`pi-freeze-2024.txt` records what to vendor.

The pin is applied on both install paths, because they resolve independently:

- `requirements.txt` (the 2024 plane) carries an explicit `IT8951[rpi] @ …@9f13613`
  line beside `omni_epd`.
- `display/pyproject.toml` (the display plane) uses `[tool.uv] override-dependencies`,
  which is the only mechanism that reaches a requirement written inside another
  package's metadata. **Verified resolving on the Pi 2026-08-07** — `uv lock`
  lands `it8951` on `9f13613` from the override rather than from upstream's
  master happening to still be that commit.

**The compiler was the other unpinned axis**, and pinning the driver alone would
have left it open: `IT8951` builds its Cython extensions from 2023-era `.pyx`
sources and its own build-requires names `Cython` with no bound, so a PEP 517
isolated build takes whatever released most recently. `[tool.uv]
build-constraint-dependencies` holds it at `>=3.0,<4`. `requirements.txt` has no
equivalent mechanism, so that path remains exposed to a Cython 4 — one more reason
the 2024 install path is retired rather than maintained.

**If the label panel misbehaves after a rebuild, this is still the first thing to
check**: confirm the installed `it8951` is `9f13613` before looking anywhere else.

## What `pi-freeze-2024.txt` is

A `pip freeze` of the environment the 2024 loader was running on the Pi, captured
during the 2026-07-19 archaeology. **Nothing installs from it.** It is kept as
evidence of which versions the recovered code actually ran against — the frozen
`samsungtvws` in it is what dictated that plane's interpreter, and the record is
what makes that traceable rather than remembered. It is also the rollback target
for the dependency move described above.

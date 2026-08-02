# Deployment

`samsung-frame-art-loader.service` runs the loader as a persistent daemon on the
Raspberry Pi driving the Frame TV.

**Before the unit is enabled, the checkout needs its environment file.** Since
2026-07-27 `config.py` raises at import unless `ART_ROOT`, `TV_ADDRESS`,
`LATITUDE`, `LONGITUDE` and `LOCATION_NAME` all resolve — deliberately, so that a
missing deployment value stops the process instead of quietly running against a
plausible-looking default. The unit names that file in `EnvironmentFile=`, and
`load_dotenv` independently resolves it next to `config.py`; both point at the
repository root, which is also the unit's `WorkingDirectory`.

    cp .env.example .env      # then fill it in
    sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now samsung-frame-art-loader

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

`samsungtvws` and `websockets` moved together on 2026-08-01 — a two-year-old fork
SHA to fork master, and websockets 12.0 to 16.1.1, which the new library requires.
**That pair has been verified to resolve and import, and has not yet been run
against the television.** Until it has, treat installing it as the change it is:

    python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"

That exercises upload, callback registration, and a confirmed delete against the
live set, touching only the image it uploads itself, and exits non-zero if any
check fails. If it does fail, `pi-freeze-2024.txt` below is the rollback — it
records the exact versions the wall ran on before the move.

Behaviour changes to expect, established by reading the library's source rather
than by running it:

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

### Installing this file pulls one dependency that is not pinned

`omni_epd` is pinned to the commit the wall runs, but **it declares `IT8951[rpi]`
as a git dependency with no commit**, so a `pip install -r requirements.txt` on a
rebuilt Pi resolves the e-paper driver to whatever that repository's master is on
the day you run it. Before `omni_epd` was declared here, this file installed
neither package and the driver arrived out-of-band; declaring the parent is what
put the unpinned child on the install path.

The commit the wall actually ran is recorded in `pi-freeze-2024.txt`:

    IT8951 @ git+https://github.com/GregDMeyer/IT8951.git@9f136139378f74e17d9972d7165dc6ae53a2568e

**If the label panel misbehaves after a rebuild, suspect this first** and install
that line explicitly. It is documented rather than pinned here because pinning a
transitive git URL alongside the parent's own unpinned declaration is exactly the
kind of resolver behaviour that should be verified on the hardware before it is
committed, and the panel is not on the bench. Pinning or vendoring it is a
recorded decision still owed — see `project-state.yaml` →
`technical_decisions.operational`.

## What `pi-freeze-2024.txt` is

A `pip freeze` of the environment the 2024 loader was running on the Pi, captured
during the 2026-07-19 archaeology. **Nothing installs from it.** It is kept as
evidence of which versions the recovered code actually ran against — the frozen
`samsungtvws` in it is what dictated that plane's interpreter, and the record is
what makes that traceable rather than remembered. It is also the rollback target
for the dependency move described above.

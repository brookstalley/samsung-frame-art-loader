# Deployment

`samsung-frame-art-loader.service` runs the loader as a persistent daemon on the
Raspberry Pi driving the Frame TV.

**Before the unit is enabled, the checkout needs its environment file.** Since
2026-07-27 `config.py` raises at import unless `ART_ROOT`, `TV_ADDRESS`,
`LATITUDE`, `LONGITUDE` and `LOCATION_NAME` all resolve — deliberately, so that a
missing deployment value stops the process instead of quietly running against a
plausible-looking default. `load_dotenv` resolves `.env` next to `config.py`, so
it must sit in the directory the unit uses as its `WorkingDirectory`.

    cp .env.example .env      # then fill it in
    sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now samsung-frame-art-loader

Skipping the first line does not produce a warning. It produces an import-time
failure on every start, and — by this unit's own `Restart=always` defaults,
analysed below — a permanently `failed` unit within half a second, silently.

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
- **No `EnvironmentFile=`, and the code now requires one.** The unit predates the
  2026-07-27 config hoist and passes no environment through, so it depends
  entirely on a `.env` sitting in `WorkingDirectory`. Either declare
  `EnvironmentFile=` explicitly — which makes the dependency visible in the unit
  rather than implied by a library's search path — or record that the `.env`
  placement is the contract.
- `After=network.target`, which does not guarantee the network is actually up.
  `network-online.target` is the correct dependency for a service that talks to
  the TV on startup.
- **`Restart=always` with no `RestartSec` or `StartLimit*` override — and this one
  defeats a stated goal, not just a preference.** systemd's defaults restart after
  100ms and give up after 5 attempts in 10 seconds, so a loader that crashes on
  startup burns its whole burst allowance in half a second and lands in `failed`,
  permanently, with nothing sent anywhere. The product's success criteria require
  that *"a failure in the unattended loader is visible without inspecting the
  wall"*; this configuration produces the exact opposite — a blank or frozen TV and
  a service that stopped trying. Needs a real `RestartSec` and a widened
  `StartLimitIntervalSec`/`StartLimitBurst`. **The `OnFailure=` prescription that
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

## What `pi-freeze-2024.txt` is

A `pip freeze` of the environment the 2024 loader was running on the Pi, captured
during the 2026-07-19 archaeology. **Nothing installs from it.** It is kept as
evidence of which versions the recovered code actually ran against — the frozen
`samsungtvws` in it is what dictated that plane's interpreter, and the record is
what makes that traceable rather than remembered. It is also the rollback target
for the dependency move described above.

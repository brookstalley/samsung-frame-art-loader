# Deployment

`samsung-frame-art-loader.service` runs the loader as a persistent daemon on the
Raspberry Pi driving the Frame TV.

    sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now samsung-frame-art-loader

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

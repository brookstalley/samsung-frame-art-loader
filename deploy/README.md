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

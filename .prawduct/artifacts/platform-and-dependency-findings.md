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

## Python target: 3.13

**Decision: target Python 3.13. Fall back to 3.12 if the IT8951 build fails.**

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

**This is unverified and must be proven early.** The evidence that the stack
builds is from Python 3.12, not 3.13 — the recovered venv was
`.venv/lib/python3.12/` with a working `IT8951-1.0.0` built into
`build/lib.linux-aarch64-cpython-312`. Treat "IT8951 builds and runs on
3.13/aarch64" as an open assumption until a build proves it.

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

2. **Builds are not reproducible.** omni-epd declares its dependency as
   `IT8951[rpi] @ git+https://github.com/GregDMeyer/IT8951.git` with no commit
   pin, so it resolves to whatever `master` currently is. This works today only
   because the repository has not moved since 2023. Pin `9f13613` explicitly, or
   vendor the package outright — it is roughly 1,500 lines of frozen code that
   the project already depends on completely.

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

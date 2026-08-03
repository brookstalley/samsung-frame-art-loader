# Operator verification queue

Visual and live-integration work the operator has to look at with their own eyes.
An entry stays here until it is checked off; nothing here blocks a build, and
`operator_verification_required` is `false`, so this is a list rather than a gate.

**No screenshots are committed.** They are cheap to regenerate and would be stale
binaries in a public repo within a chunk. The command that produces them is in
each entry, which is the durable form.

## Pending

### A curator can see the candidate images in their own client — added 2026-08-03

**Visual, and it is the one thing this chunk's tests cannot prove.** Chunk 17A
returns candidate thumbnails as MCP image content blocks. The suite asserts the
blocks are present, correctly sized, and correctly correlated to their rows — but
what a *client* does with them is the client's business, and the whole safety
argument (`security-model.md` § Content Appropriateness) rests on the picture
actually being visible at the moment of judgement. A block that every test
accepts and Claude Code renders as a broken box would satisfy the suite and
defeat the gate.

Point a real MCP client at the running plane and look:

```
art_discovery(action='list_runs')                  # take a run_id
art_review(action='list_works', run_id='<that>')   # expect: pictures, inline
art_review(action='list_images', work_id='<one>')  # expect: the alternates
```

What to check with your eyes, beyond "images appeared":

- **The pictures render inline**, not as attachments or placeholders.
- **Each work's picture is its own.** Rows carry `image_block_index`; a client
  that reorders or drops a block would pair the wrong scan with the wrong
  painting, and nothing below the wire can detect that.
- **A work with no local copy still lists**, with `preview_note` saying why —
  rather than vanishing or rendering blank.
- **The size beside each picture is legible and useful.** `renders_at_inches` is
  the number a thumbnail cannot convey, and it is what stops a postage stamp
  reaching the wall; if it reads as noise in a real client, say so — the
  presentation is worth changing.

Verified so far *without* a real client: the plane was booted from its own entry
point against a scratch tree on 2026-08-03 and a real MCP client session returned
1 text + 2 image blocks, each index resolving to a decodable 400x400-box JPEG,
with the below-floor work pictured and marked `is_on_offer: false`.

### The loader unit starts clean with its declared `EnvironmentFile=` — added 2026-08-02

**Not visual — this needs the Pi, and it is quick.** The unit now declares
`EnvironmentFile=/home/tvpi/source/samsung-frame-art-loader/.env` un-prefixed and
sets `StartLimitIntervalSec=0` / `RestartSec=10`. Everything about that was
established by reading systemd's documentation; whether *this* unit on *this*
machine starts under it has not been observed, and the un-prefixed directive is
precisely the kind of change that turns a working unit into one that refuses to
start if the path is wrong by a character.

The wall is running now, so do this at a moment when a brief outage is fine:

```sh
sudo cp deploy/samsung-frame-art-loader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: active (running)
```

**Then prove the guard actually guards**, which is the half that cannot be
checked by reading:

```sh
sudo systemctl stop samsung-frame-art-loader
mv .env .env.parked && sudo systemctl start samsung-frame-art-loader
systemctl status samsung-frame-art-loader          # expect: refuses to start, names the .env path
mv .env.parked .env && sudo systemctl restart samsung-frame-art-loader
```

The second command is expected to fail — that is the pass condition. What to
record is **whether the error names the path**, since "failed to start" without it
would leave the operator no better off than before. Check acceptance box 3 on
issue #43 with the status output pasted in.

**If the path is wrong**, the fix is the `EnvironmentFile=` line, not a rollback:
the checkout's absolute paths are machine-specific and already flagged as such in
`deploy/README.md`.

### The samsungtvws move, against the live television — added 2026-08-01

**Not visual — this one needs the hardware, not your eyes.** The library pin and
`websockets` both moved, and every claim behind the move comes from reading
source. What a television does is a separate question, and this is the only thing
that answers it.

On the Pi, with the set awake:

```sh
pip install -r requirements.txt          # the new pins
python tv_api_check.py --image "$ART_ROOT/ready/<a 4K composite>.jpg"
```

It uploads one image, watches which callback the set emits, removes that image
and confirms the removal — touching nothing else on the wall — and exits non-zero
if any check fails. Paste its output onto issue #3; the last three acceptance
boxes there are exactly what it measures.

**Four numbers worth recording from the run**, because each is an input to the
display daemon rather than a pass/fail:

1. **How long construction blocks.** It makes a REST call and, on 2024-or-later
   panels, a token round trip, all inside `__init__`.
2. **Which callback events this set emits.** Three are registered:
   `slideshow_image_changed` and `auto_rotation_image_changed` are the same
   notion under two spellings, and the wrong one fails silently, so both go on;
   `image_selected` is the acknowledgement of the request the script itself
   made. The run prints whichever fired — record all of them.
3. **The reported model and API version**, which is what the old/new verb split
   turns on.
4. **Upload seconds against file size**, streamed by path. The comparison against
   the old whole-file-in-memory route is the reason the pin moved.

**If it fails, the rollback is `deploy/pi-freeze-2024.txt`** and nothing else has
changed on the Pi — the new pins only take effect on an install.

### The first browser surface — added 2026-08-01

**What to look at.** The four sections and a work detail view, over the real
corpus. What matters is the judgement a test cannot make: does the chrome recede
behind the artwork, or compete with it? That is the whole visual constraint, and
it is subjective by nature.

**How to bring it up over the real works, without touching the deployed tree:**

```sh
# A scratch art root with the real masters read-only behind a symlink.
SCRATCH=$(mktemp -d)/art && mkdir -p "$SCRATCH" && ln -s ~/art/raw "$SCRATCH/raw"
cd curation
ART_ROOT=$SCRATCH uv run python -m curation.seed ../all.json
ART_ROOT=$SCRATCH CURATION_PORT=8791 uv run python -m curation
# then open http://127.0.0.1:8791/
```

`~/art` on the dev Mac holds `raw/` and no `ready/`, so every work will show its
master image and the wall view will report every work as `no_rendition`. **That is
correct, not a fault** — the television renders live on the Pi. To see a mixed
manifest, give a few works a rendition first; the wall view is the section most
worth seeing with both states in it.

**Specific things worth an opinion, because each was a judgement call:**

1. **Card density and the fixed 4:3 image box.** Works are letterboxed inside it
   rather than cropped to fill, so a tall work leaves large empty margins. The
   alternative — cropping — is the one thing an art tool must not do, but the
   margins are a real cost and a different aspect box would trade differently.
2. **The serif for work titles** against a sans for chrome. Intended as a museum
   label; it may read as fussy at grid size.
3. **The badge row on each card** — fit verdict and image source, plus a third
   on an archived work. Two or three badges is a lot of furniture under a
   picture. They are there because a thumbnail cannot convey resolution, so
   "would show at 15.2 inches" is the number a curator actually judges by, and
   because an archived work that looked identical to a live one would be the kind
   of silence this product exists to refuse.
4. **`no_rendition` and the other reasons appear as the raw domain words**, with
   the sentence beside them. Deliberate: the tool surface returns the same words,
   so a curator and an agent share one vocabulary. It reads slightly machine-y.
5. **Dark and light.** Both are authored; the browser's own setting picks. There
   is no in-app toggle — say if you want one, since an image-review tool arguably
   deserves the ability to pin the surround while judging colour.

**One decision explicitly awaiting a veto** (`nonfunctional-requirements.md` §
The mat is geometric): the mat's bottom margin is now 1.15x the top. The
weighting had only ever been stated as a direction, and a box height cannot be
computed from a direction. 1.15 is the factor that reproduces that artifact's own
42-inch worked example, so it is inference rather than invention — but it is a
subtle weighting, and a more pronounced one is taste, not correctness. It is
`MAT_BOTTOM_WEIGHT` in `.env`, so overruling it is a one-line change.

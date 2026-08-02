# Operator verification queue

Visual and live-integration work the operator has to look at with their own eyes.
An entry stays here until it is checked off; nothing here blocks a build, and
`operator_verification_required` is `false`, so this is a list rather than a gate.

**No screenshots are committed.** They are cheap to regenerate and would be stale
binaries in a public repo within a chunk. The command that produces them is in
each entry, which is the durable form.

## Pending

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

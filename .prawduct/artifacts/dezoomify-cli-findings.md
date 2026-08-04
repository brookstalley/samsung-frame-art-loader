# dezoomify-rs: the CLI contract, probed

**Probed 2026-08-03 against `dezoomify-rs 2.18.1`** (Homebrew, `/opt/homebrew/bin/dezoomify-rs`),
live, against the Art Institute of Chicago's IIIF endpoint. Every statement below
is an observation from a real invocation, not a reading of the help text or of the
2024 call site.

This file exists because the binary's contract is unowned and unversioned: it is a
third-party tool with no stability promise to this product, and the acquisition
path's error handling is written entirely against the behaviours recorded here. It
is the durable form of a probe, in the same role `artic-api-findings.md` and
`openrouter-api-findings.md` play for their interfaces.

## The headline: exit codes classify nothing

| Exit | Observed cases |
|---|---|
| `0` | A real image was written. **Also**: no input URI supplied and stdin at EOF — nothing was fetched, nothing was written, and the process still exited `0`. |
| `1` | Every failure *and* every partial success: no tiles at all, some tiles, unresolvable host, unparseable input. |

**Neither exit code answers the question the caller has.** `0` does not mean an
image exists, and `1` does not mean one does not. The two outcomes the data model
cares about — `partial_tiles`, which is a normal recorded outcome, and `failed` —
are *both* exit `1`.

So the acquisition path must classify on **the produced file**, not the return
code: does the output path exist, and is it non-empty? That is the same check the
zero-byte guard already performs, which means one check answers both questions
rather than the exit code answering neither.

## Where the output filename is announced

**On stderr. `stdout` is empty on every non-interactive path.**

```
[INFO ] Image successfully saved to 'out2.jpg'
```

The 2024 call site (`image_utils.py`, `get_dezoomify_file`) parses this filename
out of **stdout**:

```python
out, err = p.communicate()
out_file = out.decode("utf-8").split("'")[1]
```

Against 2.18.1 `out` is empty, so that line raises `IndexError` on the *success*
path. Inferring the contract from the 2024 code — the thing the probe existed to
avoid — would have reproduced the bug.

The safe form is not to parse the announcement at all: pass an explicit output path
and stat it. The message is a log line, not an interface.

## Partial tiles

```
[WARN ] Only 120 tiles out of 238 could be downloaded. The resulting image was still created in 'out4.jpg'.
```

Exit `1`, and **the image is real and usable** — 3.5 MB across 120 of 238 tiles in
one observed run, 4.7 MB across 171 in another. Missing tiles render as gaps, so
the result is a legitimate image with holes, which is exactly why the data model
records `partial_tiles` as an outcome rather than an error.

**The 2024 code deletes this file.** On any non-zero return it removes the output
and returns failure, so a usable partial image is discarded and the outcome the
data model calls normal can never be recorded. That behaviour contradicts
`data-model.md`'s `Source.last_fetch_status` and is not carried forward.

## Total failure leaves a zero-byte file

```
[ERROR] Could not get any tile for the image. See https://dezoomify-rs.ophir.dev/no-tile-error
```

Exit `1`, and **a zero-byte output file is left on disk**. This is the concrete
producer of the zero-byte originals the catalogue guards against: the guard is not
defending against a hypothetical, it is defending against this exact path. A caller
that recorded the output path without stating it would persist a row naming an
empty file.

## The tile cache does not create its own directory

Given `--tile-cache ./tc` where `./tc` does not exist, the binary emits one warning
per tile —

```
[WARN ] Unable to write https://… to the tile cache ./tc: No such file or directory (os error 2)
```

— and **continues to completion, caching nothing**. Exit `0`, a correct image, and
a cache that silently did not happen. Since the cache's entire purpose is letting a
partial fetch be retried without re-downloading what already arrived, a caller that
does not create the directory loses that recovery and is told only in warnings it
probably is not reading. Create the directory before invoking.

With the directory pre-created, caching works: 20 tiles requested, 20 files
written, no warnings.

## Input is read interactively when absent

With no `INPUT_URI` argument the binary prompts on stdout and blocks on stdin:

```
Enter an URL or a path to a tiles.yaml file:
[WARN ] Reached end of input. Exiting...
```

`--image-index` carries the same hazard by its own documentation: *"If not
specified, the program will ask interactively when multiple images are
available."* A service invoking this with an inherited stdin can block
indefinitely; one invoking it with stdin at EOF gets the silent exit-`0`-with-no-
output described above.

Two mitigations, both required: give the child `stdin=DEVNULL`, and pass
`--image-index` explicitly so the multi-image case never reaches a prompt.

## Shell metacharacters are inert through argv

Invoked with a URL containing `;touch OWNED;#` as a single argv element, no file
was created and the metacharacters were URL-encoded into the request:

```
error sending request for url (https://example.invalid/a;touch%20OWNED;#/info.json)
```

This is the evidence behind the argv-list rule: the binary treats its URI argument
as data. The property belongs to the *caller's* invocation, not to the binary — it
holds only for as long as nothing interpolates a URL into a shell string.

## The input is not restricted to http(s), and that is a security surface

The `INPUT_URI` argument is documented as *"Input URL **or local file name**"*, and
it behaves that way:

- `dezoomify-rs /etc/hosts` **read the file** and ran every dezoomer against its
  contents, reporting parse errors that quote the file's own characters.
- `http://127.0.0.1:1/info.json` was attempted — loopback is reachable; the
  connection was merely refused.
- `--bulk` accepts "both local file paths and HTTP(S) URLs", so a file the binary
  reads can itself supply the list of URLs it then fetches.

A source URL reaching this argument comes from web discovery, which
`security-model.md` establishes as attacker-influenceable. Handing one through
unfiltered therefore offers a local-file read and an outbound request to any host
the loader can reach.

**A scheme allowlist applied before invocation is the mitigation for the first
half.** What policy governs the second — whether a fetch may be aimed at a
loopback or private-network address — is a security requirement this probe
surfaced and did not decide; it is raised against `security-model.md` rather than
settled here, because inventing it in the acquisition module is how an unwritten
rule gets one implementation and no owner.

## The output *extension* chooses the encoder, and an unknown one is fatal

Given an output path ending `.partial`, the binary refuses:

```
[WARN ] Error when finalizing image: The file extension `."partial"` was not recognized as an image format
[ERROR] Input/Output error: The file extension `."partial"` was not recognized as an image format
```

Exit `1`, and a zero-byte file left behind. Given `out.partial.jpg` the same fetch
exits `0` and writes a real JPEG.

**This is the property that was missing from the first version of this file, and
its absence cost a working build.** Everything above was probed; this was not, and
a later change staged fetches as `<name>.partial` — which passed every unit test,
because the stand-ins are shell scripts that write to their last argument whatever
it is called, and would have failed every tiled fetch in the deployment. So a
staged path must keep the real suffix last: `<stem>.partial<suffix>`.

`tests/live/test_dezoomify_contract_still_holds.py` is the durable form of this
page. Where a behaviour is the *binary's* rather than the wrapper's, only the
binary can witness it — a fake that writes wherever it is told cannot.

## Flags this product relies on, confirmed present in 2.18.1

`--max-width` · `--max-height` · `--compression` · `--parallelism` ·
`--min-interval` · `--tile-cache` · `--header` (repeatable) · `--image-index` ·
`--largest` · `--retries` · `--timeout`

`--max-width`/`--max-height` select the largest available zoom level **not
exceeding** the given value; they do not resize. Asking for 2000 against a
3333×4144 image yielded the 833×1036 level, not a downscale of the largest.

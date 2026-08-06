"""The display plane: make the physical world match the manifest.

This package reads two things — the theme manifest and the image tree, both under
`ART_ROOT` — and writes to two — the television, and its own device store. It
makes no network call to the curation process, imports no curation module, and
queries no curation database. That is a ratified norm rather than a convention,
and `tests/preferences/test_plane_isolation.py` enforces it mechanically, because
the violation it guards against ("just fetch the label text live") works
perfectly in development and in every test: curation is up in both, so a green
suite is exactly what the violation looks like.

The consequence worth knowing before reading further is that this plane keeps
working when the other one is gone. A manifest may be arbitrarily stale; if
curation stops, the wall goes on rotating the last theme forever, and that is
correct behaviour rather than degradation.
"""

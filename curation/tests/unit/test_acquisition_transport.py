"""Redirect following, which is where the fetch policy would otherwise have a hole.

The policy runs against the URL the catalogue recorded. A client left to follow
redirects itself would let a checked public URL answer with a `Location:` pointing
at the operator's own network — so the following happens in the transport, and
every hop is re-checked.
"""

import pytest

from curation.acquisition.transport import MAX_REDIRECTS, http_stream
from curation.acquisition.urls import UrlRefused
from curation.services.errors import ServiceError


class _Response:
    def __init__(self, status, *, url, location=None, body=b""):
        self.status_code = status
        self.url = _Url(url)
        self.headers = {} if location is None else {"location": location}
        self._body = body

    @property
    def is_redirect(self):
        return self.status_code in (301, 302, 303, 307, 308)

    def iter_bytes(self, _size):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Url(str):
    def join(self, other):
        from urllib.parse import urljoin

        return _Url(urljoin(str(self), other))


class _Client:
    """Answers a scripted sequence, recording every URL it was actually asked for."""

    def __init__(self, script):
        self._script = script
        self.requested = []

    def stream(self, _method, url, **_kwargs):
        self.requested.append(url)
        return self._script[url]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def patched(monkeypatch):
    def install(script):
        client = _Client(script)
        monkeypatch.setattr("curation.acquisition.transport.httpx.Client", lambda **_kw: client)
        return client

    return install


def _checks_everything(seen):
    def check(url):
        seen.append(url)
        if "127.0.0.1" in url or "192.168." in url:
            raise UrlRefused(f"{url} is not a public address.")
        return url

    return check


def test_a_direct_answer_streams_its_body(patched):
    patched({"https://m.example.com/a.jpg": _Response(200, url="https://m.example.com/a.jpg", body=b"bytes")})
    with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
        assert b"".join(chunks) == b"bytes"


def test_a_redirect_is_followed_and_its_target_streamed(patched):
    patched(
        {
            "https://m.example.com/a.jpg": _Response(
                302, url="https://m.example.com/a.jpg", location="https://cdn.example.com/a.jpg"
            ),
            "https://cdn.example.com/a.jpg": _Response(200, url="https://cdn.example.com/a.jpg", body=b"moved"),
        }
    )
    with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
        assert b"".join(chunks) == b"moved"


def test_every_hop_goes_through_the_policy(patched):
    seen = []
    patched(
        {
            "https://m.example.com/a.jpg": _Response(
                302, url="https://m.example.com/a.jpg", location="https://cdn.example.com/a.jpg"
            ),
            "https://cdn.example.com/a.jpg": _Response(200, url="https://cdn.example.com/a.jpg", body=b"ok"),
        }
    )
    with http_stream("ua", check=_checks_everything(seen))("https://m.example.com/a.jpg") as chunks:
        b"".join(chunks)
    assert seen == ["https://cdn.example.com/a.jpg"]


def test_a_redirect_to_a_private_host_is_refused_before_it_is_requested(patched):
    # The hole this exists to close: the first URL passes the policy, and the
    # source answers it with a pointer at the operator's own network.
    client = patched(
        {
            "https://m.example.com/a.jpg": _Response(
                302, url="https://m.example.com/a.jpg", location="http://127.0.0.1:8080/admin"
            ),
        }
    )
    with pytest.raises(UrlRefused):
        with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
            b"".join(chunks)
    assert client.requested == ["https://m.example.com/a.jpg"], "the private target must never be requested"


def test_a_relative_location_is_resolved_before_it_is_checked(patched):
    # An unresolved relative location would be checked as a different string than
    # the one actually requested.
    seen = []
    patched(
        {
            "https://m.example.com/art/a.jpg": _Response(301, url="https://m.example.com/art/a.jpg", location="../full/a.jpg"),
            "https://m.example.com/full/a.jpg": _Response(200, url="https://m.example.com/full/a.jpg", body=b"ok"),
        }
    )
    with http_stream("ua", check=_checks_everything(seen))("https://m.example.com/art/a.jpg") as chunks:
        assert b"".join(chunks) == b"ok"
    assert seen == ["https://m.example.com/full/a.jpg"]


def test_a_redirect_with_no_location_is_a_refusal(patched):
    patched({"https://m.example.com/a.jpg": _Response(302, url="https://m.example.com/a.jpg")})
    with pytest.raises(ServiceError, match="no location"):
        with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
            b"".join(chunks)


def test_an_endless_redirect_chain_is_bounded(patched):
    patched(
        {"https://m.example.com/a.jpg": _Response(302, url="https://m.example.com/a.jpg", location="https://m.example.com/a.jpg")}
    )
    with pytest.raises(ServiceError, match=f"more than {MAX_REDIRECTS}"):
        with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
            b"".join(chunks)


def test_an_error_status_is_reported_as_a_refusal(patched):
    patched({"https://m.example.com/a.jpg": _Response(404, url="https://m.example.com/a.jpg")})
    with pytest.raises(ServiceError, match="HTTP 404"):
        with http_stream("ua", check=_checks_everything([]))("https://m.example.com/a.jpg") as chunks:
            b"".join(chunks)

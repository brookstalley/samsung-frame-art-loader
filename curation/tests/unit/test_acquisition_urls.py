"""The gate every source URL passes before anything fetches it."""

import pytest

from curation.acquisition.urls import UrlRefused, check_fetchable


def _resolves_to(*addresses: str):
    """A resolver that answers with exactly these addresses, whatever it is asked."""

    def resolve(host: str):  # noqa: ARG001 - the answer is the point, not the question
        return list(addresses)

    return resolve


PUBLIC = _resolves_to("93.184.216.34")


class TestSchemes:
    def test_https_passes(self):
        url = "https://www.artic.edu/iiif/2/abc/info.json"
        assert check_fetchable(url, resolve=PUBLIC) == url

    def test_http_passes(self):
        url = "http://gallery.example.com/image.jpg"
        assert check_fetchable(url, resolve=PUBLIC) == url

    def test_file_scheme_is_refused(self):
        # The binary this guards reads local paths as readily as URLs, so this is
        # the refusal the module exists for.
        with pytest.raises(UrlRefused, match="not a fetchable scheme"):
            check_fetchable("file:///etc/passwd", resolve=PUBLIC)

    @pytest.mark.parametrize("url", ["ftp://example.com/x.jpg", "data:image/jpeg;base64,AAAA", "javascript:alert(1)"])
    def test_other_schemes_are_refused(self, url):
        with pytest.raises(UrlRefused, match="not a fetchable scheme"):
            check_fetchable(url, resolve=PUBLIC)

    def test_a_bare_path_is_refused(self):
        with pytest.raises(UrlRefused, match="not a fetchable scheme"):
            check_fetchable("/etc/hosts", resolve=PUBLIC)

    def test_the_refusal_names_the_scheme_it_saw(self):
        # A caller reading the recorded failure should not have to guess which
        # part of the URL was the problem.
        with pytest.raises(UrlRefused, match="'file'"):
            check_fetchable("file:///etc/passwd", resolve=PUBLIC)


class TestEmptyAndMalformed:
    @pytest.mark.parametrize("url", ["", "   ", "\n"])
    def test_empty_is_refused(self, url):
        with pytest.raises(UrlRefused, match="empty"):
            check_fetchable(url, resolve=PUBLIC)

    def test_a_scheme_with_no_host_is_refused(self):
        with pytest.raises(UrlRefused, match="no host"):
            check_fetchable("https:///just/a/path", resolve=PUBLIC)


class TestPrivateAddresses:
    @pytest.mark.parametrize(
        "literal",
        [
            "127.0.0.1",
            "127.1.2.3",
            "10.0.0.5",
            "192.168.1.1",
            "172.16.0.1",
            "169.254.169.254",
            "0.0.0.0",
        ],
    )
    def test_private_and_loopback_literals_are_refused(self, literal):
        # Literals are judged directly; the resolver would never be consulted, so
        # a resolver claiming everything is public must not rescue them.
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable(f"https://{literal}/info.json", resolve=PUBLIC)

    @pytest.mark.parametrize("literal", ["[::1]", "[fe80::1]", "[fc00::1]", "[::ffff:127.0.0.1]"])
    def test_private_ipv6_literals_are_refused(self, literal):
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable(f"https://{literal}/info.json", resolve=PUBLIC)

    @pytest.mark.parametrize("mapped", ["[::ffff:7f00:1]", "[::ffff:192.168.1.1]", "[::ffff:10.0.0.1]"])
    def test_an_ipv4_mapped_ipv6_address_is_judged_as_its_ipv4(self, mapped):
        # These read as `is_loopback=False`, so the worry is that they slip
        # through. How the stdlib classifies them moved between 3.12 and 3.14, so
        # this asserts the verdict rather than trusting either version's folding.
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable(f"https://{mapped}/info.json", resolve=PUBLIC)

    def test_a_mapped_public_ipv4_still_passes(self):
        # The other side of the same rule, and the half a version change breaks
        # in the opposite direction: on 3.12 this address reports
        # `is_reserved=True` and would be refused for carrying 8.8.8.8.
        url = "https://[::ffff:8.8.8.8]/info.json"
        assert check_fetchable(url, resolve=PUBLIC) == url

    def test_a_name_resolving_to_a_mapped_loopback_is_refused(self):
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable("https://museum.example.com/x.json", resolve=_resolves_to("::ffff:127.0.0.1"))

    def test_a_name_resolving_to_loopback_is_refused(self):
        # `localhost` and its aliases are names, so the refusal has to come from
        # the answer rather than from the spelling.
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable("https://localhost.localdomain/x.json", resolve=_resolves_to("127.0.0.1"))

    def test_a_public_name_resolving_privately_is_refused(self):
        # The realistic shape: the name looks like a museum, the answer is the
        # operator's own router.
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable("https://museum.example.com/x.json", resolve=_resolves_to("192.168.1.1"))

    def test_one_private_answer_among_public_ones_refuses(self):
        # A name answering with several addresses is only as safe as its worst
        # one, because nothing here chooses which the fetcher will use.
        resolve = _resolves_to("93.184.216.34", "127.0.0.1")
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable("https://museum.example.com/x.json", resolve=resolve)

    def test_a_private_ipv6_answer_beside_a_public_ipv4_refuses(self):
        resolve = _resolves_to("93.184.216.34", "fd00::1")
        with pytest.raises(UrlRefused, match="not a public address"):
            check_fetchable("https://museum.example.com/x.json", resolve=resolve)


class TestLocalNames:
    @pytest.mark.parametrize("host", ["printer.local", "PRINTER.LOCAL", "nas.local."])
    def test_mdns_names_are_refused_without_resolving(self, host):
        def explode(_host: str):
            raise AssertionError("a .local name must be refused before it reaches a resolver")

        with pytest.raises(UrlRefused, match="local-network name"):
            check_fetchable(f"https://{host}/image.jpg", resolve=explode)

    def test_a_name_merely_containing_local_is_not_refused(self):
        # `local` as a substring is not the mDNS suffix, and refusing it would
        # block real hosts for looking wrong.
        url = "https://localhistory.example.com/image.jpg"
        assert check_fetchable(url, resolve=PUBLIC) == url


class TestResolutionFailures:
    def test_a_name_that_does_not_resolve_is_refused(self):
        def fails(_host: str):
            raise UrlRefused("nope")

        with pytest.raises(UrlRefused):
            check_fetchable("https://nowhere.invalid/x.jpg", resolve=fails)

    def test_a_name_resolving_to_nothing_is_refused(self):
        # An empty answer must not fall through the address loop as though every
        # address had passed.
        with pytest.raises(UrlRefused, match="no addresses"):
            check_fetchable("https://empty.example.com/x.jpg", resolve=_resolves_to())

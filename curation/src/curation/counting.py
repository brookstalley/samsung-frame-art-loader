"""Saying a count out loud, with the words around it agreeing with it.

Four modules compose sentences about how many works a run touched, and each was
written with the plural hard-coded, so a run of exactly one work reported "1
works". The sentences are not one sentence — an MCP notice is written for a
model and a run view is written for a curator — but the agreement is one rule,
and copying it four ways is what let it be got right in one place and wrong in
six lines of the same function.

**Deliberately not in `services/`.** `architecture.md` § Components &
Responsibilities puts operation logic there and keeps bindings thin; this is
neither. It is how a number is spelled, it decides nothing, and a service that
imported it would not be doing anything more than its callers already do.

There is no attempt at general English here and there should not be. The nouns
this product counts — works, images, themes, entries — are regular, and the
irregular cases are handled by naming the plural at the call site. A
pluralisation library would bring a dictionary, a dependency and a set of
behaviours nobody here has a use for.
"""


def noun(count: int, singular: str, plural: str | None = None) -> str:
    """The form of a noun that agrees with `count` — `work`, `works`.

    `plural` defaults to suffixing an `s`, which is right for every noun this
    product counts, and is passed explicitly where it is not.
    """
    if count == 1:
        return singular
    return plural if plural is not None else f"{singular}s"


def counted(count: int, singular: str, plural: str | None = None) -> str:
    """A count and its noun — `1 work`, `12 works`.

    The overwhelmingly common case, and the one worth making shortest: every
    site this was written for says a number immediately followed by its noun.
    """
    return f"{count} {noun(count, singular, plural)}"


def agree(count: int, singular: str, plural: str) -> str:
    """The word elsewhere in the sentence that has to agree — `is`/`are`, `them`/`it`.

    **No default plural, unlike `noun`.** Verb agreement in English is not
    suffixation — `is`/`are`, `has`/`have` — so a default here could only be
    wrong, and wrong in the direction that looks right until somebody reads the
    output. A noun-only fix is how "1 work ... are reported" survives being
    fixed once already, which is the defect this argument's absence prevents.

    Pronouns and demonstratives take the same shape and are the same problem
    ("unreachable for them" over a count of one), so they are spelled through
    here rather than through a second function that would differ only in name.
    """
    return singular if count == 1 else plural

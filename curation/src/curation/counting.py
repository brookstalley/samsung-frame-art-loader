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

    **Exported although `counted` is its only caller here.** It is `counted`'s
    implementation and the natural subject of this module's own unit test, and a
    sentence that needs the noun without the number in front of it is the next
    call site rather than a hypothetical one.
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


def agree_partitive(part: int, whole: int, singular: str, plural: str) -> str:
    """Agreement for "N of M works …" — the shape where the nearest count is the wrong one.

    English agrees the verb with the head of the subject, and in "1 of the 5
    works" the head is *1*: "one of the five works **has** an image". The `5` sits
    inside a prepositional phrase and governs nothing. It is also the number
    printed immediately before the verb, which is why keying `agree` on it reads
    right and shipped "1 of 3 works in this theme **are** on the wall" — the same
    disagreement this module was written for, moved from the trailing count to
    the leading one.

    **Zero is the exception, and it is why this is a function rather than a note
    telling callers to pass the numerator.** "0 of 3 works" means *none of the
    three*, and none-of-many takes the plural; "0 of 1 work" means *none of the
    one*, and takes the singular. So at zero the whole governs, and at every
    other count the part does. Passing the numerator alone gets "0 of 1 work
    **are** on the wall", which is the fix over-applied.
    """
    return agree(whole if part == 0 else part, singular, plural)

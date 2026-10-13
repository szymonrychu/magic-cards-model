"""EP-02 R2 T7: counted permanents as an amount, round 2.

Extends the EP-02-R1 counted-group reader (`ep02_r1_counted_permanents`) and the
shared amount sentences (`amount_sentences`) additively; nothing here replaces a
reader they own.

- `have_clause_as_plain`: "you may have target player lose life equal to ..." is
  an optional (CR 608.2d) instruction aimed at a player; the clause readers know
  the bare verb phrase ("target player loses life ..."), so the "have" wrapper is
  peeled off and the verb put in the third person.
"""

import functools
import re

_HAVE_PLAYER_RE = re.compile(
    r"^have (?P<subject>(?:up to one )?target (?:player|opponent)|that player|each opponent|"
    r"each player|defending player) (?P<verb>lose|draw|discard|mill|gain|reveal|sacrifice)\b",
    re.IGNORECASE,
)


@functools.cache
def have_clause_as_plain(body: str) -> str | None:
    """`body` ("have target player lose life equal to the number of Allies you
    control") as the plain clause it asks for ("target player loses life equal to
    ..."), or `None` when it is not a "have <player> <verb>" body."""
    if not body.lower().startswith("have "):
        return None
    match = _HAVE_PLAYER_RE.match(body)
    if match is None:
        return None
    verb = match.group("verb").lower()
    third = verb + ("es" if verb.endswith(("ss", "sh", "ch", "x")) else "s")
    return f"{match.group('subject')} {third}{body[match.end():]}"


# --------------------------------------------------------------------------
# The group qualifiers the EP-02-R1 reader does not know.
# --------------------------------------------------------------------------

_NAMED_TAIL_RE = re.compile(r"\s+named\s+(?P<name>[A-Z][\w',-]*(?:\s+[A-Z][\w',-]*)*)\s*$")
_BOUND_RE = re.compile(
    r"\s+with\s+(?P<stat>power|toughness)\s+(?P<n>\d+)\s+or\s+(?P<dir>greater|less)\b",
    re.IGNORECASE,
)
_SUPERTYPE_WORDS = {
    "legendary": ("supertypes_all", "legendary"),
    "nonlegendary": ("supertypes_none", "legendary"),
    "basic": ("supertypes_all", "basic"),
    "nonbasic": ("supertypes_none", "basic"),
}
_LEAD_RE = re.compile(
    r"^(?P<head>(?:the )?(?:number of )?(?:other )?(?:(?:tapped|untapped|snow|nonsnow) )*)"
    r"(?P<mods>(?:(?:legendary|nonlegendary|basic|nonbasic|nontoken) )*)(?P<rest>.*)$",
    re.IGNORECASE,
)
_TOKEN_NOUN_RE = re.compile(r"^(?P<kind>.*?)\b(?:(?P<only>tokens?))(?P<tail>\s+you control.*)$")


def split_group_extras(phrase: str):
    """`(phrase without the qualifiers EP-02-R1's reader lacks, GroupExtras | None)`.

    The qualifiers peeled off: supertype words before the noun ("legendary
    creatures", "basic Islands", CR 205.4), "named <Name>" after the control
    clause ("lands you control named Wastes", CR 201.2), a power / toughness
    bound ("creatures you control with power 4 or greater", CR 208.1), and the
    token noun ("Blood tokens you control", CR 111.1 - a token with the
    subtype)."""
    from .layers.model import GroupExtras

    text = phrase.strip().rstrip(".")
    fields: dict = {}
    if (named := _NAMED_TAIL_RE.search(text)) is not None:
        fields["named"] = named.group("name")
        text = text[: named.start()]
    if (bound := _BOUND_RE.search(text)) is not None:
        stat, direction = bound.group("stat").lower(), bound.group("dir").lower()
        key = f"{stat}_{'at_least' if direction == 'greater' else 'at_most'}"
        fields[key] = int(bound.group("n"))
        text = text[: bound.start()] + text[bound.end() :]
    lead = _LEAD_RE.match(text)
    if lead is not None and lead.group("mods"):
        for word in lead.group("mods").lower().split():
            if word == "nontoken":
                fields["token"] = False
                continue
            key, value = _SUPERTYPE_WORDS[word]
            fields.setdefault(key, ())
            fields[key] = (*fields[key], value)
        text = lead.group("head") + lead.group("rest")
    token = _TOKEN_NOUN_RE.match(text)
    if token is not None:
        fields["token"] = True
        text = (token.group("kind").strip() + " permanents" if not token.group("kind").strip()
                else token.group("kind").strip()) + token.group("tail")
    if not fields:
        return phrase, None
    return " ".join(text.split()), GroupExtras(**fields)


_LAYER_GROUP_RE = re.compile(
    r"^(?P<other>other )?(?P<list>[a-z]+(?:(?:,? (?:and/or|and|or)|,) [a-z]+)*) you control$",
    re.IGNORECASE,
)
#: "This creature gets +1/+0 for each legendary creature you control." - the
#: `parse._SELF_PUMP_PER_CONTROLLED_PERMANENT_RE` shape, for a group with a
#: qualifier that regex's single bare word cannot carry.
LAYER_SELF_PUMP_GROUP_RE = re.compile(
    r"^this (?:creature|token|permanent) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each "
    r"(?P<group>[^.]+?)\.?$",
    re.IGNORECASE,
)


@functools.cache
def layer_group_count_factory(group: str):
    """`group` ("basic Island you control", "land you control named Wastes") as a
    factory `username -> CountGroup`, or `None` when it has no qualifier the
    plain card-type / subtype factory lacks, or any word of it is unread."""
    from .layers.model import CountGroup
    from .layers.parse import _card_type_word, _singular_subtype_word

    stripped, extras = split_group_extras(group)
    if extras is None:
        return None
    match = _LAYER_GROUP_RE.fullmatch(stripped)
    if match is None:
        return None
    types, subtypes = [], []
    for word in re.split(r",?\s*(?:and/or|and|or)\s+|,\s*", match.group("list"), flags=re.I):
        if not word:
            continue
        if word.lower().rstrip("s") == "permanent":
            continue  # every permanent: no type narrowing
        if (card_type := _card_type_word(word)) is not None:
            types.append(card_type)
        elif (subtype := _singular_subtype_word(word)) is not None:
            subtypes.append(subtype)
        else:
            return None
    other = match.group("other") is not None
    return lambda username: CountGroup(
        username=username,
        types_any=tuple(types),
        subtypes_any=tuple(subtypes),
        extras=extras,
        excludes_self=other,
    )

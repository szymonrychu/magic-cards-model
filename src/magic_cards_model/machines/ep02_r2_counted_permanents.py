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
    return f"{match.group('subject')} {third}{body[match.end() :]}"


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
        text = (
            token.group("kind").strip() + " permanents"
            if not token.group("kind").strip()
            else token.group("kind").strip()
        ) + token.group("tail")
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


# --------------------------------------------------------------------------
# ", where X is <counted group>" over a whole multi-sentence text.
# --------------------------------------------------------------------------

_WHERE_X_TAIL_RE = re.compile(
    r",\s*where X is (?P<mult>twice |three times )?(?P<expr>[^.]+?)"
    r"(?: as (?:this (?:ability|spell) resolves|it resolves))?(?=\.(?:\s|$)|$)",
    re.IGNORECASE,
)
_CONTINUATION_RE = re.compile(r",\s+(?:and|then)\s", re.IGNORECASE)
_MULTIPLIERS = {"twice ": 2, "three times ": 3}
#: "Search ... for up to X basic land cards. Put those cards onto the battlefield
#: tapped, then shuffle." (Kyoshi Island Plaza) is the older "..., put them onto
#: the battlefield tapped, then shuffle" with the sentence break moved.
_THOSE_CARDS_RE = re.compile(r"\.\s+Put those cards onto\b")
_WHOLE_TEXT_CONDITIONAL_RE = re.compile(r"^(?:if|unless|when|whenever|as long as)\b", re.IGNORECASE)


def _normalised(rendered: str) -> str:
    return _THOSE_CARDS_RE.sub(", put them onto", rendered)


def parse_where_x_whole_text(text: str, *, for_spell: bool):
    """A body whose X is defined by a trailing ", where X is <counted group>" in one
    sentence and used anywhere in the text ("Look at the top X cards of your
    library, where X is the number of lands you control. You may reveal a
    creature or land card from among them ..."; "Search ... for up to X basic land
    cards, where X is the number of Shrines you control. Put those cards ...").

    The count is fixed once as the object resolves (CR 608.2h) - "as this ability
    resolves" says the same - written into the text as a plain number (CR 107.3a
    gives X its value for the whole object), and the numeric text is read by the
    ordinary clause readers. `None` when the group is unread or the number left
    the text unreadable: there is no half-run instruction (CR 608.2c)."""
    if "where x is" not in text.lower():
        return None
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
    from .effects.text import _strip_non_effect_preamble
    from .effects.tokens import _is_notice_only
    from .ep02_r1_counted_permanents import _ABILITY_LINE_RE, _expression_reader

    body = _strip_non_effect_preamble(text).strip()
    if _WHOLE_TEXT_CONDITIONAL_RE.match(body) or (for_spell and _ABILITY_LINE_RE.match(body)):
        return None
    match = _WHERE_X_TAIL_RE.search(body)
    if match is None:
        return None
    expr = match.group("expr").strip()
    reader = _expression_reader(expr)
    spill = ""
    if reader is None and (cut := _CONTINUATION_RE.search(expr)) is not None:
        # "..., where X is the number of Swamps you control, and exile them": the
        # definition ends at the comma, the rest continues the instruction.
        expr, spill = expr[: cut.start()], expr[cut.start() :]
        reader = _expression_reader(expr)
    if reader is None:
        return None
    rest = body[: match.start()] + spill + body[match.end() :]
    if re.search(r"\bX\b", rest, re.IGNORECASE) is None:
        return None
    multiplier = _MULTIPLIERS.get((match.group("mult") or "").lower(), 1)
    parse = _spell_effect_or_notice if for_spell else _ability_effect_or_notice

    @functools.cache
    def parsed(rendered: str):
        effect = parse(_normalised(rendered))
        readable = (
            effect is not None
            and not _is_notice_only(effect)
            and getattr(effect, "unparsed_remainder", None) is None
        )
        return effect if readable else None

    from .amount_sentences import write_x

    if parsed(write_x(rest, 2)) is None:
        return None

    def effect(game, obj) -> None:
        count = max(reader(game, obj), 0) * multiplier
        resolved = parsed(write_x(rest, count))
        if resolved is not None:
            resolved(game, obj)

    return effect


# --------------------------------------------------------------------------
# "For each <group>, create <tokens>" - for-each-token-creation.
# --------------------------------------------------------------------------

_FOR_EACH_CREATE_RE = re.compile(
    r"^for each (?P<each>.+?), (?P<create>create .+?)(?P<tail>\.(?:\s.*)?|)$",
    re.IGNORECASE | re.DOTALL,
)


@functools.cache
def for_each_create_as_tail_form(text: str) -> str | None:
    """ "For each land you control, create a Treasure token." as the same instruction
    with the count after the verb ("Create a Treasure token for each land you
    control."), which the token readers already perform: the number of tokens is the
    count of the group as the instruction is performed, once (CR 608.2h), and the
    tokens are created together (CR 111.1). `None` for anything not led by a
    "for each <group>, create ..." sentence."""
    stripped = text.strip()
    if not stripped[:9].lower() == "for each ":
        return None
    match = _FOR_EACH_CREATE_RE.match(stripped)
    if match is None:
        return None
    create = match.group("create")
    return f"{create[:1].upper()}{create[1:]} for each {match.group('each')}{match.group('tail')}"


def parse_for_each_create_text(text: str, *, for_spell: bool):
    """The effect of a "For each <group>, create <tokens>" body, read in its
    tail form (see `for_each_create_as_tail_form`), or `None`."""
    rewritten = for_each_create_as_tail_form(text)
    if rewritten is None:
        return None
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
    from .effects.tokens import _is_notice_only

    effect = (_spell_effect_or_notice if for_spell else _ability_effect_or_notice)(rewritten)
    if (
        effect is None
        or _is_notice_only(effect)
        or getattr(effect, "unparsed_remainder", None) is not None
    ):
        return None
    return effect

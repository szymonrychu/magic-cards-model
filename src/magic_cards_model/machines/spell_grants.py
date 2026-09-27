"""Keywords a permanent's static ability grants to spells and to cards in hand.

Four printed shapes, all CR 604.2 static abilities of a permanent (or, CR
114.4, of an emblem) reaching out at objects its controller casts or holds:

- "`<Quality>` spells you cast[ from your hand] have `<keyword>`."
  (Prismari, the Inspiration's storm, Quandrix, the Proof's cascade,
  Witherbloom, the Balancer's affinity for creatures, Sami, Wildcat Captain's
  affinity for artifacts, The First Sliver's Sliver-only cascade);
- "Each `<quality>` spell you cast has `<keyword>`." (Silverquill, the
  Disputant's casualty 1);
- "The first spell you cast each turn has `<keyword>`." (Maelstrom Nexus);
- "Each `<quality>` card in your hand has `<keyword>`." (Lorehold, the
  Historian's miracle {2}).

The granted keyword is written back out as the line a card would print
("Storm", "Cascade", "Casualty 1", "Affinity for creatures", "Miracle {2}")
and handed to the machine that already executes the printed keyword - the
trigger expansions in `machines/keywords.py` (storm CR 702.40a, cascade CR
702.85a, miracle CR 702.94a), `Game.cost_reduction_for`'s affinity reading
(CR 702.41a) and `machines/casting.Casting.pay_casualty` (CR 702.153a). No
keyword gets a second, parallel implementation here.

**Only keywords some machine executes are read.** A line granting a keyword
this module does not list (convoke, delve, ripple, ...) is not a
grant it reads at all, so `reads_spell_keyword_grant_line` answers False and
the line keeps whatever verdict it had rather than being credited on a guess.

**Continuous, never locked in (CR 611.3a).** A grant "applies at any given
moment to whatever its text indicates", so every question below is asked of
the board as it stands when the keyword's own machine asks it: storm and
cascade as the spell becomes cast (CR 601.2i, CR 603.2), affinity and
casualty while the total cost is determined (CR 601.2b, CR 601.2f), miracle
as the card is drawn (CR 702.94a - the card must have the ability *as* it is
drawn, which is exactly when `Game._offer_miracle_reveal` asks).

**"Spells you cast" means cast.** CR 707.10: "a copy of a spell isn't cast",
so a copy on the stack is never granted anything by these lines - its
`CastRecord.is_copy` is what says so.
"""

import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from pydantic import ConfigDict

from ..models.card_state import CardState
from ..models.mana import ManaCost
from ..models.zone import Zone
from ..snapshot import EngineModel
from .abilities import AbilityKind, parse_abilities

#: The keywords a spell grant is read for, each with the rule of the machine
#: that executes it. Affinity's "[text]" and casualty's N travel with the
#: keyword; storm and cascade take nothing.
SPELL_GRANT_KEYWORDS: dict[str, str] = {
    "storm": "CR 702.40a",
    "cascade": "CR 702.85a",
    "casualty": "CR 702.153a",
    "affinity": "CR 702.41a",
    "conspire": "CR 702.78a",
}

#: The keywords a card-in-hand grant is read for.
HAND_GRANT_KEYWORDS: dict[str, str] = {
    "miracle": "CR 702.94a",
}

#: The keyword phrase itself, as printed after "have"/"has": a bare keyword,
#: "casualty N", "affinity for <text>", or "miracle <mana cost>".
_KEYWORD_PHRASE_RE = re.compile(
    r"^(?:(?P<bare>storm|cascade|improvise|conspire)"
    r"|(?P<casualty>casualty) (?P<n>\d+)"
    r"|(?P<affinity>affinity) for (?P<what>[a-z]+)"
    r"|(?P<miracle>miracle) (?P<cost>(?:\{[^{}]+\})+))$",
    re.IGNORECASE,
)

#: "`<Quality>` spells you cast[ from your hand] have `<keyword>`." - the
#: quality may be empty ("Spells you cast have affinity for artifacts.", Sami,
#: Wildcat Captain).
_SPELLS_YOU_CAST_HAVE_RE = re.compile(
    r"^(?P<what>(?:[\w'-]+ )*?)spells you cast(?: from your (?P<zone>hand|graveyard))? "
    r"have (?P<keyword>.+?)\.?$",
    re.IGNORECASE,
)

#: "Each `<quality>` spell you cast[ from your hand] has `<keyword>`."
_EACH_SPELL_YOU_CAST_HAS_RE = re.compile(
    r"^each (?P<what>(?:[\w'-]+ )*?)spell you cast(?: from your (?P<zone>hand|graveyard))? "
    r"has (?P<keyword>.+?)\.?$",
    re.IGNORECASE,
)

#: "The first `<quality>` spell you cast each turn has `<keyword>`."
#: (Maelstrom Nexus, with no quality at all.)
_FIRST_SPELL_EACH_TURN_HAS_RE = re.compile(
    r"^the first (?P<what>(?:[\w'-]+ )*?)spell you cast each turn has (?P<keyword>.+?)\.?$",
    re.IGNORECASE,
)

#: "Each `<quality>` card in your hand has `<keyword>`." / "`<Quality>` cards
#: in your hand have `<keyword>`."
_CARDS_IN_YOUR_HAND_HAVE_RE = re.compile(
    r"^(?:each (?P<each>(?:[\w'-]+ )*?)card in your hand has"
    r"|(?P<plural>(?:[\w'-]+ )*?)cards in your hand have) (?P<keyword>.+?)\.?$",
    re.IGNORECASE,
)

#: Reminder text (CR 207.2) trailing the grant: italics, no game function.
_TRAILING_REMINDER_RE = re.compile(r"\s*\([^()]*\)\s*$")

_ZONE_WORDS: dict[str, Zone] = {"hand": Zone.HAND, "graveyard": Zone.GRAVEYARD}


class SpellKeywordGrant(EngineModel):
    """One static line read as a keyword grant."""

    model_config = ConfigDict(frozen=True)

    subject: str
    """`"spell"` (spells you cast), `"first_spell"` (the first spell you cast
    each turn) or `"hand_card"` (cards in your hand)."""
    quality: str
    """The quality phrase the granted-to object must have, `""` for any."""
    from_zone: Zone | None = None
    """The zone the spell must be cast from ("from your hand"), or None."""
    keyword: str
    """The keyword, lower case."""
    line: str
    """The keyword written back out the way a card prints it."""
    rule: str


def _keyword_line(phrase: str, allowed: dict[str, str]) -> tuple[str, str] | None:
    """`(keyword, printed line)` for the phrase after "have"/"has", or None
    when it is not one of `allowed`'s keywords in a shape this reads."""
    match = _KEYWORD_PHRASE_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    if match.group("bare"):
        keyword = match.group("bare").lower()
        line = keyword.capitalize()
    elif match.group("casualty"):
        keyword = "casualty"
        line = f"Casualty {int(match.group('n'))}"
    elif match.group("affinity"):
        keyword = "affinity"
        what = match.group("what").lower()
        if not _affinity_is_counted(what):
            return None
        line = f"Affinity for {what}"
    else:
        keyword = "miracle"
        line = f"Miracle {match.group('cost')}"
    if keyword not in allowed:
        return None
    return keyword, line


def _affinity_is_counted(what: str) -> bool:
    """Whether `Game._affinity_count` counts CR 702.41a's "[text]" - an
    affinity it would reduce nothing for is not a grant this reads."""
    from ..models.game import _AFFINITY_CARD_TYPES, _AFFINITY_SUBTYPES

    return what in _AFFINITY_CARD_TYPES or what in _AFFINITY_SUBTYPES


def _normalized_quality(raw: str | None) -> str:
    """The quality phrase with CR 205.1's type list read as the disjunction
    it is: "instant and sorcery" names one spell that is either."""
    quality = (raw or "").strip().lower()
    return re.sub(r"\s+and\s+", " or ", quality)


def _quality_is_readable(quality: str) -> bool:
    from .next_spell import spell_quality_is_readable

    return not quality or spell_quality_is_readable(quality)


def _object_has_quality(state: CardState, quality: str) -> bool:
    from .next_spell import spell_has_quality

    return not quality or spell_has_quality(state, quality)


@lru_cache(maxsize=4096)
def spell_keyword_grant(text: str) -> SpellKeywordGrant | None:
    """Read one static line as a keyword grant, or None.

    Fails closed: an unreadable quality phrase or a keyword outside
    `SPELL_GRANT_KEYWORDS`/`HAND_GRANT_KEYWORDS` is no grant at all.
    """
    line = _TRAILING_REMINDER_RE.sub("", text.strip()).strip()
    for pattern, subject in (
        (_SPELLS_YOU_CAST_HAVE_RE, "spell"),
        (_EACH_SPELL_YOU_CAST_HAS_RE, "spell"),
        (_FIRST_SPELL_EACH_TURN_HAS_RE, "first_spell"),
    ):
        match = pattern.fullmatch(line)
        if match is None:
            continue
        read = _keyword_line(match.group("keyword"), SPELL_GRANT_KEYWORDS)
        quality = _normalized_quality(match.group("what"))
        if read is None or not _quality_is_readable(quality):
            return None
        zone_word = match.groupdict().get("zone")
        return SpellKeywordGrant(
            subject=subject,
            quality=quality,
            from_zone=_ZONE_WORDS[zone_word.lower()] if zone_word else None,
            keyword=read[0],
            line=read[1],
            rule=SPELL_GRANT_KEYWORDS[read[0]],
        )
    match = _CARDS_IN_YOUR_HAND_HAVE_RE.fullmatch(line)
    if match is None:
        return None
    read = _keyword_line(match.group("keyword"), HAND_GRANT_KEYWORDS)
    quality = _normalized_quality(match.group("each") or match.group("plural"))
    if read is None or not _quality_is_readable(quality):
        return None
    return SpellKeywordGrant(
        subject="hand_card",
        quality=quality,
        keyword=read[0],
        line=read[1],
        rule=HAND_GRANT_KEYWORDS[read[0]],
    )


def reads_spell_keyword_grant_line(text: str) -> bool:
    """Whether one static line is a grant this module reads - what
    `support.py` asks before crediting the line."""
    return spell_keyword_grant(text) is not None


#: A cheap test a line must pass before it is read at all: every shape above
#: says "you cast" or "in your hand".
_MIGHT_GRANT_RE = re.compile(r"you cast|in your hand", re.IGNORECASE)


def _grants_of(game: Any, controller: str) -> Iterator[tuple[str, SpellKeywordGrant]]:
    """`(source name, grant)` for every grant `controller`'s permanents and
    emblems have right now.

    A permanent's *computed* ability list (CR 613.1f), so a grant layer 6
    removed grants nothing and one layer 6 added does; an emblem's printed
    one (CR 114.4). Every shape above is anchored at the start of its line,
    so a sentence inside a triggered or activated ability ("Whenever ..., ")
    never reads as a static grant.
    """
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(controller):
        for line in board.of(permanent).abilities:
            if not _MIGHT_GRANT_RE.search(line):
                continue
            grant = spell_keyword_grant(line)
            if grant is not None:
                yield permanent.name, grant
    for emblem in game.emblems_of(controller):
        for ability in parse_abilities(emblem.card):
            if ability.kind is not AbilityKind.STATIC:
                continue
            grant = spell_keyword_grant(ability.raw or ability.text or "")
            if grant is not None:
                yield emblem.name, grant


def granted_spell_keyword_lines(
    game: Any,
    spell: CardState,
    caster: str,
    origin_zone: Zone,
    *,
    first_spell: bool,
) -> list[str]:
    """The keyword lines `caster`'s grants give `spell`, a spell `caster` is
    casting (or has cast) from `origin_zone`.

    `first_spell` says whether `spell` is the first spell `caster` has cast
    this turn - what "The first spell you cast each turn has ..." asks.
    One line per grant: two permanents granting storm are two instances
    (CR 702.40a, like CR 702.85c for cascade, triggers each separately).
    """
    if game is None:
        return []
    from .next_spell import next_spell_keyword_grants_for

    lines: list[str] = []
    if spell.zone is not Zone.STACK or game.cast_record_of(spell) is None:
        # "The next `<quality>` spell you cast this turn has `<keyword>`" -
        # live while this spell is being cast (CR 601.2f), gone the moment it
        # becomes cast (CR 601.2i), so a spell already cast reads none.
        lines.extend(grant.line for grant in next_spell_keyword_grants_for(game, spell, caster))
    for _name, grant in _grants_of(game, caster):
        if grant.subject == "hand_card":
            continue
        if grant.subject == "first_spell" and not first_spell:
            continue
        if grant.from_zone is not None and grant.from_zone is not origin_zone:
            continue
        if not _object_has_quality(spell, grant.quality):
            continue
        lines.append(grant.line)
    return lines


def granted_lines_of_stack_spell(game: Any, spell: CardState) -> list[str]:
    """`granted_spell_keyword_lines` for a spell already on the stack, read
    off its own `CastRecord`: nothing for a copy (CR 707.10) or for an object
    with no record of being cast."""
    if spell.zone is not Zone.STACK:
        return []
    record = game.cast_record_of(spell)
    if record is None or record.is_copy:
        return []
    caster = spell.controller
    if caster is None:
        return []
    cast = game.spells_cast_this_turn.get(caster, [])
    first_spell = bool(cast) and cast[0] is spell
    return granted_spell_keyword_lines(
        game, spell, caster, record.origin_zone, first_spell=first_spell
    )


def granted_hand_keyword_lines(game: Any, card: CardState) -> list[str]:
    """The keyword lines a card in its owner's hand has from that owner's
    "`<quality>` card in your hand has `<keyword>`" grants."""
    if game is None or card.zone is not Zone.HAND or card.owner is None:
        return []
    return [
        grant.line
        for _name, grant in _grants_of(game, card.owner)
        if grant.subject == "hand_card" and _object_has_quality(card, grant.quality)
    ]


def granted_triggered_abilities_for(game: Any, source: CardState) -> list[Any]:
    """The triggered abilities a spell on the stack or a card in hand has
    from `granted_spell_keyword_lines`/`granted_hand_keyword_lines` - storm,
    cascade and miracle written out by the same expansions a printed keyword
    goes through (`machines/keywords.granted_keyword_triggered_abilities`)."""
    from .keywords import (
        casualty_triggered_abilities,
        conspire_triggered_abilities,
        granted_keyword_triggered_abilities,
    )

    if source.zone is Zone.STACK:
        lines = granted_lines_of_stack_spell(game, source)
        record = game.cast_record_of(source)
        paid = 0 if record is None or record.is_copy else record.casualty_paid
        conspired = 0 if record is None or record.is_copy else record.conspire_paid
        casualty = casualty_triggered_abilities(paid) + conspire_triggered_abilities(conspired)
    elif source.zone is Zone.HAND:
        lines = granted_hand_keyword_lines(game, source)
        casualty = []
    else:
        return []
    return (granted_keyword_triggered_abilities(lines) if lines else []) + casualty


#: "Casualty N" as `granted_spell_keyword_lines` writes it.
_CASUALTY_LINE_RE = re.compile(r"^Casualty (?P<n>\d+)$")


def casualty_numbers(game: Any, spell: CardState, caster: str, origin_zone: Zone) -> list[int]:
    """The N of every casualty instance `spell` has as `caster` casts it
    from `origin_zone` (CR 702.153a): the printed ones, then one per grant
    ("Each instant and sorcery spell you cast has casualty 1."). CR 702.153b
    pays each of them separately."""
    from .keywords import printed_casualty_numbers

    numbers = printed_casualty_numbers(spell.card)
    if game is None:
        return numbers
    first_spell = not game.spells_cast_this_turn.get(caster)
    for line in granted_spell_keyword_lines(
        game, spell, caster, origin_zone, first_spell=first_spell
    ):
        match = _CASUALTY_LINE_RE.fullmatch(line)
        if match is not None:
            numbers.append(int(match.group("n")))
    return numbers


def conspire_count(game: Any, spell: CardState, caster: str, origin_zone: Zone) -> int:
    """How many conspire instances `spell` has as `caster` casts it from
    `origin_zone` (CR 702.78a): printed, then one per grant ("Each
    noncreature spell you cast has conspire.")."""
    from .keywords import printed_conspire_count

    count = printed_conspire_count(spell.card)
    if game is None:
        return count
    first_spell = not game.spells_cast_this_turn.get(caster)
    return count + sum(
        1
        for line in granted_spell_keyword_lines(
            game, spell, caster, origin_zone, first_spell=first_spell
        )
        if line == "Conspire"
    )


#: "Affinity for <text>" as `granted_spell_keyword_lines` writes it.
_AFFINITY_LINE_RE = re.compile(r"^Affinity for (?P<what>[a-z]+)$")


def granted_affinity_reductions(
    game: Any, spell: CardState, caster: str, origin_zone: Zone
) -> list[ManaCost]:
    """CR 702.41a for every affinity `caster`'s grants give `spell` while it
    is being cast: "This spell costs {1} less to cast for each [text] you
    control." One generic reduction per granted instance - the ruling on
    Witherbloom, the Balancer: "If a spell has multiple instances of
    affinity, each one applies."

    Asked during CR 601.2f, before the spell has become cast, so it is the
    first spell `caster` casts this turn exactly when nothing is on
    `Game.spells_cast_this_turn` for them yet.
    """
    if game is None:
        return []
    first_spell = not game.spells_cast_this_turn.get(caster)
    reductions: list[ManaCost] = []
    for line in granted_spell_keyword_lines(
        game, spell, caster, origin_zone, first_spell=first_spell
    ):
        match = _AFFINITY_LINE_RE.fullmatch(line)
        if match is None:
            continue
        amount = game._affinity_count(match.group("what"), caster)  # noqa: SLF001
        if amount:
            reductions.append(ManaCost(generic=amount))
    return reductions


# --------------------------------------------------------------------------
# R0a-T5: play permissions a resolving ability grants (CR 601.3, CR 118.9)
# --------------------------------------------------------------------------

#: "Choose an exiled card an opponent owns with a void counter on it. You may
#: play it this turn without paying its mana cost." (Dauthi Voidwalker). The
#: owner phrase and the counter name are read, not fixed; "play" reaches a
#: land (CR 601.1a's wider verb) where "cast" does not.
_CHOOSE_EXILED_WITH_COUNTER_RE = re.compile(
    r"^choose an exiled card(?: (?P<owner>an opponent owns|you own))? with an? "
    r"(?P<counter>[a-z0-9+/\-]+) counter on it\. you may (?P<verb>play|cast) "
    r"(?:it|that card) this turn(?P<free> without paying its mana cost)?\.?$",
    re.IGNORECASE,
)


def _permission_action(verb: str) -> Any:
    from .casting import PlayAction

    return PlayAction.PLAY if verb.lower() == "play" else PlayAction.CAST


def parse_choose_exiled_with_counter_play_clause(text: str) -> Any:
    """`_CHOOSE_EXILED_WITH_COUNTER_RE`'s effect: the controller chooses one
    card in exile carrying the counter (and owned as printed), and gets a
    this-turn play permission for it (CR 601.3), free where printed (CR
    118.9). Nothing to choose is nothing done."""
    match = _CHOOSE_EXILED_WITH_COUNTER_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    owner = (match.group("owner") or "").lower()
    kind = match.group("counter").lower()
    action = _permission_action(match.group("verb"))
    free = match.group("free") is not None

    def effect(game: Any, ability: Any) -> None:
        from .decisions import Decision, DecisionKind, source_id_of

        controller = ability.controller
        candidates = [
            state
            for state in game.exile
            if state.counter_count(kind) > 0
            and (
                not owner
                or (owner == "an opponent owns" and state.owner != controller)
                or (owner == "you own" and state.owner == controller)
            )
        ]
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller,
                prompt=f"choose an exiled card with a {kind} counter on it",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        by_id = {state.id: state for state in candidates}
        for chosen_id in chosen_ids or ():
            chosen = by_id.get(chosen_id)
            if chosen is None:
                continue
            game.grant_play_permission(
                chosen,
                controller,
                action=action,
                pays_mana_cost=not free,
                source_name=ability.source_name,
                rule="CR 118.9" if free else "CR 601.3",
            )

    return effect


#: "Creature cards in your graveyard gain "You may cast this card from your
#: graveyard" until end of turn." (Case of the Uneaten Feast) and the leading-
#: duration order "Until end of turn, each legendary card in your graveyard
#: gains "You may play this card from your graveyard."" (Kethis, the Hidden
#: Hand). CR 611.2c: a resolving ability's grant affects the cards there as
#: it resolves - a card arriving later is a new object (CR 400.7) and gains
#: nothing. The quoted ability is an opaque payload here (CR 113.10): only
#: the self-zone permission payload is performed; any other payload fails
#: closed with a notice.
_GRAVEYARD_CARDS_GAIN_QUOTED_RE = re.compile(
    r'^(?P<lead>until end of turn, )?(?:each )?(?P<quality>[a-z][a-z ]*?) cards? in your '
    r'graveyard gains? "(?P<payload>[^"]+)"(?P<trail> until end of turn)?\.?$',
    re.IGNORECASE,
)

#: The one payload performed: "You may cast/play this card from your graveyard".
_SELF_GRAVEYARD_PERMISSION_PAYLOAD_RE = re.compile(
    r"^you may (?P<verb>cast|play) this card from your graveyard\.?$", re.IGNORECASE
)


def parse_graveyard_cards_gain_cast_clause(text: str) -> Any:
    """`_GRAVEYARD_CARDS_GAIN_QUOTED_RE`'s effect: a this-turn permission
    (CR 601.3) for every card of that quality in the controller's graveyard,
    or a fail-closed notice for a payload this does not perform."""
    normalized = " ".join(text.split()).replace("\u201c", '"').replace("\u201d", '"')
    match = _GRAVEYARD_CARDS_GAIN_QUOTED_RE.fullmatch(normalized)
    if match is None or (match.group("lead") is None) == (match.group("trail") is None):
        return None
    quality = match.group("quality").strip().lower()
    payload = _SELF_GRAVEYARD_PERMISSION_PAYLOAD_RE.fullmatch(match.group("payload").strip())
    if payload is None:

        def payload_notice_only(game: Any, ability: Any) -> None:
            from ..models.game import UnmodeledTriggerEffectNotice

            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=match.group("payload"),
                )
            )

        return payload_notice_only
    action = _permission_action(payload.group("verb"))

    def effect(game: Any, ability: Any) -> None:
        from .casting import has_quality

        controller = ability.controller
        player = game.player(controller)
        for state in list(player.cards_in(Zone.GRAVEYARD)):
            if not has_quality(
                quality,
                colors=tuple(state.colors),
                types=tuple(state.types),
                subtypes=tuple(state.subtypes),
                supertypes=tuple(state.card.supertypes),
            ):
                continue
            game.grant_play_permission(
                state,
                controller,
                action=action,
                source_name=ability.source_name,
                zone=Zone.GRAVEYARD,
                until_end_of_turn=True,
            )

    return effect

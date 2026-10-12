"""EP-02 R1 T5: cards in a graveyard counted as an amount.

One reader for every "N of the cards in a graveyard" amount, so a card that
prints "for each artifact and/or creature card in your graveyard", "the number
of card types among cards in all graveyards", "each different mana value among
nonland cards in your graveyard", "the total number of instant and sorcery
cards you own in exile and in your graveyard" or "each card named X in each
graveyard" reads through the same grammar:

    [the] [total] [number of] <description> card(s) [named N] [you own]
        in <where>

- `<description>` is the search grammar's card description
  (`_quality_matcher`): card types joined by "and"/"and/or"/"or" (a union, one
  card is never counted twice - CR 205.2a), "permanent", a negated type
  ("nonland"), a subtype ("Lesson", "Elemental"), a colour.
- `<where>` is "your graveyard" (CR 404.1: every player has their own), "all
  graveyards" / "each graveyard" (every player's), "that player's graveyard" /
  "their graveyard" (the player the resolving ability targets or concerns), or
  "exile and in your graveyard" with "you own" (CR 108.3: cards by owner,
  whichever zone).
- "card types among cards in <where>" counts distinct CR 205.2a card types.
- "different mana value(s) among <description> cards in <where>" counts
  distinct mana values (CR 202.3), a card with no mana cost being 0.

The returned reader is `(game, controller) -> int`, the shape
`amounts.count_expression` returns; the caller counts once, as the effect
applies (CR 608.2h). A token is never counted: it is not a card, and ceases to
exist in a graveyard anyway.

Below the reader are the instruction shapes that use it and had no parser of
their own (life change, mill, counters, mana, tapped-and-attacking tokens, a
search limit, a damage pair sharing one X, a counted pump rider); each is gated
on the word "graveyard" and joins its ladder through the rungs at the end of
`machines/effects/amounts.py`.
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING

from ..models.player import Player
from ..numbers import COUNT, parse_count
from .decisions import source_id_of

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game

_WHERE = (
    r"(?P<where>your graveyard|all graveyards|each graveyard|each player's graveyard"
    r"|exile and in your graveyard|that player's graveyard|their graveyard)"
)
_PREFIX = r"^(?:the )?(?:total )?(?:number of )?"
_CARDS_RE = re.compile(
    rf"{_PREFIX}(?:(?P<quality>[^,]+?(?:, [^,]+?)*) )?cards?"
    rf"(?: named (?P<name>.+?))?(?P<owned> you own)? in {_WHERE}$",
    re.IGNORECASE,
)
_CARD_TYPES_AMONG_RE = re.compile(
    rf"{_PREFIX}card types among cards in {_WHERE}$",
    re.IGNORECASE,
)
_DIFFERENT_MANA_VALUES_RE = re.compile(
    rf"{_PREFIX}different mana values? among (?:(?P<quality>.+?) )?cards in {_WHERE}$",
    re.IGNORECASE,
)

_PUT_INTO_GRAVEYARD_RE = re.compile(
    rf"{_PREFIX}(?P<nontoken>nontoken )?(?P<quality>[a-z]+(?:(?:,| and/or| and| or) [a-z]+)*?)"
    r" (?:was |were )?put into your graveyard from the battlefield this turn$",
    re.IGNORECASE,
)

Reader = Callable[["Game", str], int]


def _cards_in(game: "Game", controller: str, where: str) -> "list[CardState]":
    """The cards `where` names, read off the live zones (CR 404.1, CR 108.3)."""
    where = where.lower()
    if where == "your graveyard":
        return list(game.player(controller).graveyard)
    if where in ("that player's graveyard", "their graveyard"):
        return list(game.player(_referent_player(game, controller)).graveyard)
    if where.startswith("exile and"):
        return [
            *(card for card in game.exile if card.owner == controller),
            *game.player(controller).graveyard,
        ]
    return [card for player in game.players for card in player.graveyard]


def _referent_player(game: "Game", controller: str) -> str:
    """The player "that player"/"their" names while an ability resolves: the
    first player it targets (Keening Stone, The Mouth of Sauron), else the
    player its event concerns (CR 603.2), else its controller (CR 109.5)."""
    resolving = game.resolving
    if resolving is not None and hasattr(resolving, "targets"):
        for target in game.resolve_targets(resolving):
            if isinstance(target, Player):
                return target.username
    event = getattr(resolving, "event", None)
    if event is not None and event.player is not None:
        return event.player
    return controller


def _quality(raw: str | None) -> Callable[["CardState"], bool] | None:
    """The description's predicate, or `None` when a word of it is unread.

    "and"/"and/or" between card types is the union `_quality_matcher` reads for
    "or" - "instant and sorcery cards" is every instant or sorcery card."""
    from .effects._common import _card_description_is_readable, _quality_matcher

    if raw is None:
        return lambda _card: True
    description = re.sub(r"\s+(?:and/or|and)\s+", " or ", raw.strip(), flags=re.IGNORECASE)
    if not _card_description_is_readable(description):
        return None
    return _quality_matcher(description)


@cache
def graveyard_count_expression(phrase: str) -> Reader | None:
    """`phrase` as a count of cards in a graveyard, or `None` when it is not
    one of the shapes in the module docstring."""
    text = " ".join(phrase.split()).rstrip(".")
    lowered = text.lower()
    if "graveyard" not in lowered:
        return None
    if " among cards in " in lowered:
        if "card types" in lowered:
            match = _CARD_TYPES_AMONG_RE.fullmatch(text)
            if match is None:
                return None
            where = match.group("where")
            return lambda game, controller: len(
                {kind for card in _cards_in(game, controller, where) for kind in card.types}
            )
        return None
    if "different mana value" in lowered:
        mana_values = _DIFFERENT_MANA_VALUES_RE.fullmatch(text)
        if mana_values is None:
            return None
        matches = _quality(mana_values.group("quality"))
        if matches is None:
            return None
        where = mana_values.group("where")
        return lambda game, controller: len(
            {card.mana_value for card in _cards_in(game, controller, where) if matches(card)}
        )
    if " from the battlefield this turn" in lowered:
        return _put_into_your_graveyard_this_turn(text)
    match = _CARDS_RE.fullmatch(text)
    if match is None:
        return None
    where = match.group("where")
    owned = match.group("owned") is not None
    if owned != where.lower().startswith("exile and"):
        return None
    matches = _quality(match.group("quality"))
    if matches is None:
        return None
    name = match.group("name")
    return lambda game, controller: sum(
        1
        for card in _cards_in(game, controller, where)
        if matches(card) and (name is None or card.name == name)
    )


def _put_into_your_graveyard_this_turn(text: str) -> Reader | None:
    """ "creature put into your graveyard from the battlefield this turn" (Fresh
    Meat): the turn's "to_graveyard" arrivals (CR 700.4 - "dies" is exactly
    this move) whose owner is the counting player (CR 108.3: the graveyard a
    card goes to is its owner's), judged by what each was as it last existed
    (CR 603.10a). A token counts too: it is put into a graveyard before it
    ceases to exist (CR 111.7)."""
    from ..models.card import Type
    from ..models.card_state import PERMANENT_TYPES
    from .effects.amounts import _singular_card_type

    match = _PUT_INTO_GRAVEYARD_RE.fullmatch(text)
    if match is None:
        return None
    words = re.split(r",? ?(?:and/or|and|or)? ", match.group("quality").lower())
    wanted: set[Type] = set()
    for word in (w for w in words if w):
        if word.rstrip("s") == "permanent":
            wanted |= set(PERMANENT_TYPES)
            continue
        card_type = _singular_card_type(word)
        if card_type is None:
            return None
        wanted.add(card_type)
    nontoken = match.group("nontoken") is not None

    def count(game: "Game", controller: str) -> int:
        return sum(
            1
            for entry in game.turn_history
            if entry.kind == "to_graveyard"
            and entry.owner == controller
            and entry.characteristics is not None
            and wanted & set(entry.characteristics.types)
            and not (nontoken and entry.characteristics.is_token)
        )

    return count


# --------------------------------------------------------------------------
# Instructions whose amount is a graveyard count
#
# The reader above answers "how many"; these are the instruction shapes that
# use it and had no reader of their own. Each is gated on the word "graveyard"
# so no existing parser's text is taken, and registers through one rung per
# ladder at the end of `machines/effects/amounts.py`.
#
# A graveyard that is the recipient's ("their graveyard", "that player's
# graveyard") is rewritten to "your graveyard" and counted for the recipient -
# the convention `_TARGET_PLAYER_REFERENCES` already uses for damage - while
# "your graveyard" stays the ability controller's (CR 109.5).
# --------------------------------------------------------------------------

_RECIPIENT_GRAVEYARD_RE = re.compile(
    r"\b(?:their|that (?:player|opponent)'s|its owner's) graveyard\b", re.IGNORECASE
)


def recipient_view(phrase: str) -> tuple[str, bool]:
    """`phrase` with the recipient's own graveyard written as "your graveyard",
    and whether any was rewritten (so the count is taken for the recipient)."""
    rewritten, count = _RECIPIENT_GRAVEYARD_RE.subn("your graveyard", phrase)
    return rewritten, count > 0


def _for_each_reader(phrase: str):
    """`(game, perspective, source_id) -> int` for a "for each <phrase>" tail."""
    from .effects import _for_each_multiplier

    return _for_each_multiplier(phrase)


def _equal_to_reader(phrase: str):
    """The same shape for an "equal to <phrase>" / "where X is <phrase>" amount
    (`amount_expression`'s four-argument form, the source read by id)."""
    from uuid import UUID

    from .effects.amounts import amount_expression

    reader = amount_expression(phrase)
    if reader is None:
        return None

    def read(game: "Game", perspective: str, source_id: str | None) -> int:
        source = None if source_id is None else game.find_by_id(UUID(source_id))
        return reader(game, perspective, source, 0)

    return read


_LIFE_CLAUSE_RE = re.compile(
    rf"^(?P<who>that player|they|target player|target opponent|each opponent) "
    rf"(?P<verb>gains?|loses?) (?:(?P<n>{COUNT}) life for each (?P<each>.+)"
    r"|life equal to (?P<expr>.+))$",
    re.IGNORECASE,
)


def _recipients(game: "Game", stack_object, who: str, controller: str) -> "list[Player]":
    """The players an instruction's subject names: the event's player for
    "that player"/"they" (CR 603.2), the chosen targets, or each opponent."""
    from .effects import _opponents
    from .ep01_r3_amounts import event_player_username

    if who == "each opponent":
        return list(_opponents(game, controller))
    if who.startswith("target"):
        return [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
    username = event_player_username(game, stack_object, who)
    return [] if username is None else [game.player(username)]


def parse_recipient_life_clause(clause: str, *, for_spell: bool):
    """ "that player loses life equal to the number of creature cards in your
    graveyard" (Graveblade Marauder), "target opponent loses 2 life for each
    creature card in their graveyard" (Liliana, Death Mage): a life change
    (CR 119.3) for the player the trigger's event concerns, a target, or each
    opponent, scaled by a graveyard count taken once as it applies (CR 608.2h).
    """
    from .effects import _targets_understood

    match = _LIFE_CLAUSE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or "graveyard" not in clause.lower():
        return None
    who = match.group("who").lower()
    if for_spell and who in ("that player", "they"):
        return None  # a spell has no event to name "that player"
    if who.startswith("target") and not _targets_understood(who, allow_player_targets=True):
        return None
    each, expr = match.group("each"), match.group("expr")
    phrase, relative = recipient_view(each if each is not None else expr)
    reader = _for_each_reader(phrase) if each is not None else _equal_to_reader(phrase)
    unit = 1 if each is None else parse_count(match.group("n"))
    if reader is None or unit is None:
        return None
    gains = match.group("verb").lower().startswith("gain")

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object).username
        for player in _recipients(game, stack_object, who, controller):
            amount = unit * reader(
                game, player.username if relative else controller, source_id_of(stack_object)
            )
            if amount <= 0:
                continue
            if gains:
                game.gain_life(player, amount)
            else:
                game.lose_life(player, amount)

    return effect


_MILL_WHERE_X_RE = re.compile(
    r"^(?P<who>target player|target opponent) mills x cards?, where x is (?P<expr>.+)$",
    re.IGNORECASE,
)


def parse_target_player_mills_where_x_clause(clause: str, *, for_spell: bool):
    """ "Target player mills X cards, where X is the number of cards in that
    player's graveyard" (Keening Stone), "... where X is the number of Lesson
    cards in your graveyard" (Master Pakku): CR 701.17a's mill for the chosen
    player, X counted once as the instruction applies (CR 608.2h) - after the
    graveyard it is counted in is whatever that moment holds."""
    from .effects import _targets_understood
    from .effects.library import _mill

    match = _MILL_WHERE_X_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or "graveyard" not in clause.lower():
        return None
    who = match.group("who").lower()
    if not _targets_understood(who, allow_player_targets=True):
        return None
    phrase, relative = recipient_view(match.group("expr"))
    reader = _equal_to_reader(phrase)
    if reader is None:
        return None

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object).username
        for player in _recipients(game, stack_object, who, controller):
            amount = reader(
                game, player.username if relative else controller, source_id_of(stack_object)
            )
            if amount > 0:
                _mill(game, player, amount)

    return effect


_SELF_COUNTERS_FOR_EACH_RE = re.compile(
    rf"^(?:then )?put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<subject>this [a-z]+) for each (?P<each>.+)$",
    re.IGNORECASE,
)


def parse_self_counters_for_each_clause(clause: str, *, for_spell: bool):
    """ "put a +1/+1 counter on this creature for each creature card in your
    graveyard" (Moldgraf Millipede, Ooze Patrol): CR 122.1 counters on the
    ability's own source, the count taken once as it applies (CR 608.2h) - so
    after the "mill" instruction before it (CR 608.2c). A source that has
    left the battlefield gets none (CR 400.7)."""
    from ..models.zone import Zone
    from .effects.counters import _counter_kind

    if for_spell:
        return None
    match = _SELF_COUNTERS_FOR_EACH_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or "graveyard" not in clause.lower():
        return None
    unit = parse_count(match.group("n"))
    reader = _for_each_reader(match.group("each"))
    if unit is None or reader is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object) -> None:
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        amount = unit * reader(game, stack_object.controller, source_id_of(stack_object))
        if amount > 0:
            game.add_counters(source, kind, amount)

    return effect


_FOR_EACH_COUNTER_ON_EACH_RE = re.compile(
    rf"^for each (?P<each>.+?), put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
    r"on each (?P<group>.+? you control)$",
    re.IGNORECASE,
)


def parse_for_each_counter_on_each_clause(clause: str, *, for_spell: bool):
    """ "For each creature card in your graveyard, put a +1/+1 counter on each
    creature you control" (Vraska, Regal Gorgon): the instruction repeats once
    per counted card (CR 608.2c - in order, so each pass puts one more on
    every creature then controlled), the count taken once before the first
    (CR 608.2h)."""
    from ..models.zone import Zone
    from .effects.counters import _counter_kind
    from .targeting import permanent_description

    match = _FOR_EACH_COUNTER_ON_EACH_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or "graveyard" not in clause.lower():
        return None
    unit = parse_count(match.group("n"))
    reader = _for_each_reader(match.group("each"))
    group = re.sub(r"\s+you control$", "", match.group("group"), flags=re.IGNORECASE)
    requirement = permanent_description(group)
    if unit is None or reader is None or requirement is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object).username
        passes = reader(game, controller, source_id_of(stack_object))
        for _ in range(passes):
            for permanent in list(game.permanents_controlled_by(controller)):
                if permanent.zone is Zone.BATTLEFIELD and (
                    requirement.rejects(permanent, controller, game) is None
                ):
                    game.add_counters(permanent, kind, unit)

    return effect


_ADD_MANA_FOR_EACH_RE = re.compile(
    r"^(?:then )?add (?P<mana>(?:\{[wubrgc]\})+) for each (?P<each>.+)$", re.IGNORECASE
)


def parse_add_mana_for_each_clause(clause: str, *, for_spell: bool):
    """ "then add {R} for each card named Rite of Flame in each graveyard"
    (Rite of Flame): CR 106.4's add-mana instruction, once per counted card
    (CR 608.2h - counted when the instruction is followed)."""
    from ..models.card import Color
    from .effects._common import _MANA_SYMBOL_RE

    match = _ADD_MANA_FOR_EACH_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or "graveyard" not in clause.lower():
        return None
    reader = _for_each_reader(match.group("each"))
    if reader is None:
        return None
    colors = [Color(symbol.upper()) for symbol in _MANA_SYMBOL_RE.findall(match.group("mana"))]

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object).username
        times = reader(game, controller, source_id_of(stack_object))
        pool = game.player(controller).mana_pool
        for _ in range(max(times, 0)):
            for color in colors:
                pool.add(color)

    return effect


_SEARCH_VALUE_AT_MOST_COUNT_RE = re.compile(
    r"^(?P<head>(?:[^.—]+ — )?search .*? with mana value )less than or equal to "
    r"(?P<expr>(?:the )?(?:total )?number of [^,]+?)(?P<tail>,.*)$",
    re.IGNORECASE | re.DOTALL,
)


def _search_value_at_most_count(text: str, *, for_spell: bool):
    """ "Search your library for a black card with mana value less than or
    equal to the number of creature cards in your graveyard, reveal it, put it
    into your hand, then shuffle." (Mausoleum Secrets): the limit is a count
    taken once as the search begins (CR 608.2h), so the search is read as the
    same sentence with that number written in ("mana value 3 or less") - the
    one search reader every such sentence already goes through."""
    from .effects.dispatch import parse_mixed_effect, parse_mixed_effect_for_spell

    if "less than or equal to the" not in text.lower():
        return None
    match = _SEARCH_VALUE_AT_MOST_COUNT_RE.fullmatch(" ".join(text.split()).rstrip("."))
    if match is None or "graveyard" not in match.group("expr").lower():
        return None
    counted = graveyard_count_expression(match.group("expr"))
    parse = parse_mixed_effect_for_spell if for_spell else parse_mixed_effect

    def written_with(limit: int) -> str:
        return f"{match.group('head')}{limit} or less{match.group('tail')}."

    if counted is None or parse(written_with(2)) is None:
        return None

    def effect(game: "Game", stack_object) -> None:
        limit = counted(game, game.controller_of(stack_object).username)
        resolved = parse(written_with(limit))
        if resolved is not None:
            resolved(game, stack_object)

    return effect


def parse_search_value_at_most_count_spell(text: str):
    """`_search_value_at_most_count` for a spell's resolution text."""
    return _search_value_at_most_count(text, for_spell=True)


def parse_search_value_at_most_count_ability(text: str):
    """`_search_value_at_most_count` for an ability's effect text."""
    return _search_value_at_most_count(text, for_spell=False)


_DAMAGE_PAIR_WHERE_X_RE = re.compile(
    r"^(?P<source>[^.,]+?) deals X damage to (?P<first>[^.,]+?) and X damage to "
    r"(?P<second>itself|you|[^.,]+?),\s*where X is (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


def _damage_pair_where_x(text: str, *, for_spell: bool):
    """ "This creature deals X damage to any target and X damage to itself,
    where X is the number of Elemental cards in your graveyard." (Sunflare
    Shaman): one X (CR 107.3f) given to both halves of an elliptical "and"
    pair, counted once as it resolves (CR 608.2h) and read as the two full
    sentences it stands for (CR 608.2c, in order)."""
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice

    if " and X damage to " not in text or "graveyard" not in text.lower():
        return None
    from .effects._common import _strip_non_effect_preamble

    match = _DAMAGE_PAIR_WHERE_X_RE.fullmatch(" ".join(_strip_non_effect_preamble(text).split()))
    if match is None:
        return None
    counted = _equal_to_reader(match.group("expr"))
    if counted is None:
        return None
    read = _spell_effect_or_notice if for_spell else _ability_effect_or_notice

    def written_with(value: int) -> str:
        source = match.group("source")
        return (
            f"{source} deals {value} damage to {match.group('first')}. "
            f"{source} deals {value} damage to {match.group('second')}."
        )

    if read(written_with(2)) is None:
        return None

    def effect(game: "Game", stack_object) -> None:
        value = max(
            counted(game, game.controller_of(stack_object).username, source_id_of(stack_object)), 0
        )
        resolved = read(written_with(value))
        if resolved is not None:
            resolved(game, stack_object)

    return effect


def parse_damage_pair_where_x_spell(text: str):
    """`_damage_pair_where_x` for a spell's resolution text."""
    return _damage_pair_where_x(text, for_spell=True)


def parse_damage_pair_where_x_ability(text: str):
    """`_damage_pair_where_x` for an ability's effect text."""
    return _damage_pair_where_x(text, for_spell=False)


_TAPPED_ATTACKING_TOKENS_FOR_EACH_RE = re.compile(
    rf"^create (?P<n>{COUNT}|an?) (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?"
    r"\s+that(?:'s|’s| is| are) tapped and attacking for each (?P<each>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_tapped_attacking_tokens_for_each_ability(text: str):
    """ "Create a 2/2 green Wolf creature token that's tapped and attacking for
    each creature card in your graveyard." (Kessig Cagebreakers): CR 508.4's
    tokens that enter tapped and attacking (never declared, so nothing
    "attacks"), `n` times the count taken once as it resolves (CR 608.2h)."""
    from ..models.token import create_tokens
    from .effects._common import _strip_non_effect_preamble
    from .effects.continuous import _defender_of_controllers_attack
    from .effects.tokens import _parse_generic_token_descriptor

    if "tapped and attacking for each" not in text.lower() or "graveyard" not in text.lower():
        return None
    match = _TAPPED_ATTACKING_TOKENS_FOR_EACH_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split()).rstrip(".")
    )
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    reader = _for_each_reader(match.group("each"))
    definition = _parse_generic_token_descriptor(
        match.group("desc").strip().split(), match.group("tail")
    )
    if unit is None or reader is None or definition is None:
        return None

    def effect(game: "Game", ability) -> None:
        controller = game.controller_of(ability).username
        count = unit * reader(game, controller, source_id_of(ability))
        if count > 0:
            create_tokens(
                game,
                definition,
                controller,
                count,
                tapped=True,
                attacking=_defender_of_controllers_attack(game, controller),
            )

    return effect


def parse_graveyard_count_clause(clause: str, *, for_spell: bool):
    """The first of this module's instruction shapes that reads `clause`."""
    lowered = clause.lower()
    if "graveyard" not in lowered:
        return None
    for parser in (
        parse_recipient_life_clause,
        parse_target_player_mills_where_x_clause,
        parse_self_counters_for_each_clause,
        parse_for_each_counter_on_each_clause,
        parse_add_mana_for_each_clause,
    ):
        found = parser(clause, for_spell=for_spell)
        if found is not None:
            return found
    return None


_PUMP_THEN_ADDITIONAL_PER_RE = re.compile(
    r"^(?P<subject>target creature) gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of "
    r"turn\.\s*it gets an additional (?P<extra_power>[+-]\d+)/(?P<extra_toughness>[+-]\d+) "
    r"until end of turn for each (?P<each>.+?)\.?$",
    re.IGNORECASE,
)


def _pump_then_additional_per_count(text: str, *, for_spell: bool):
    """ "Target creature gets +3/+3 until end of turn. It gets an additional
    +2/+2 until end of turn for each card named Growth Cycle in your
    graveyard." (Growth Cycle): both sentences modify the same creature in
    sublayer 7c (CR 613.4c) for the same duration, so the count (taken once, as
    the spell resolves - CR 608.2h) is folded into one pump, built by the same
    layer parser every "until end of turn" pump uses and put on the chosen
    target (CR 611.2c fixes who it affects)."""
    from .effects.continuous import continuous_effects, layer_context_for
    from .layers import parsed_layer_effects

    if "it gets an additional" not in text.lower():
        return None
    match = _PUMP_THEN_ADDITIONAL_PER_RE.fullmatch(" ".join(text.split()))
    if match is None or "graveyard" not in match.group("each").lower():
        return None
    reader = _for_each_reader(match.group("each"))
    if reader is None:
        return None

    def written_with(count: int) -> str:
        power = int(match.group("power")) + int(match.group("extra_power")) * count
        toughness = int(match.group("toughness")) + int(match.group("extra_toughness")) * count
        return f"Target creature gets {power:+d}/{toughness:+d} until end of turn."

    if parsed_layer_effects(written_with(1)) is None:
        return None

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object)
        count = max(reader(game, controller.username, source_id_of(stack_object)), 0)
        builder = parsed_layer_effects(written_with(count))
        targets = game.resolve_card_targets(stack_object)
        source = (
            stack_object
            if hasattr(stack_object, "oracle_text")
            else stack_object.source_or_last_known(game)
        )
        if builder is None or source is None or not targets:
            return
        store = continuous_effects(game)
        context = layer_context_for(game, controller)
        for built in builder(source, store.tick(), targets, context):
            if built.holds(game):
                store.add(built)

    return effect


def parse_pump_then_additional_per_count_spell(text: str):
    """`_pump_then_additional_per_count` for a spell's resolution text."""
    return _pump_then_additional_per_count(text, for_spell=True)


def parse_pump_then_additional_per_count_ability(text: str):
    """`_pump_then_additional_per_count` for an ability's effect text."""
    return _pump_then_additional_per_count(text, for_spell=False)

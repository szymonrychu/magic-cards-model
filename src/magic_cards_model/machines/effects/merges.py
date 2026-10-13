import re
from collections.abc import Callable
from random import Random
from typing import TYPE_CHECKING, Any
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import creature_type_vocabulary, subtype_vocabulary
from ...models.card import Color, Type
from ...models.card_state import (
    CardState,
    ExileAnnotation,
    ExileMarker,
)
from ...models.player import Player
from ...models.token import (
    create_tokens,
)
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    QuantitySource,
    count_pattern,
    parse_count,
    parse_quantity,
    quantity_pattern,
    where_x_pattern,
)
from ..casting import (
    PlayAction,
)
from ..converge import colors_of_mana_spent
from ..cost import (
    spend_restriction,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..layers import (
    BASIC_LAND_TYPES,
    ContinuousEffect,
    Duration,
    HasCounter,
    Layer,
    Sublayer,
    _split_and_validate_keywords,
    add_subtype,
    grant_ability,
    modify_power_toughness,
    only_this_incarnation,
)
from ..targeting import (
    ControllerRestriction,
    TargetingProfile,
    permanent_description,
    profile_for_text,
)
from ..triggers import (
    AbilityOnStack,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSES, SPELL_TEXT
from ._common import (
    _MANA_COST_LIST,
    _OWNER_PUTS_IT_INTO_LIBRARY_TAIL,
    _SACRIFICED_MANA_VALUE_TERM,
    AbilityEffect,
    ClauseEffect,
    Effect,
    TargetedClause,
    _PutDescription,
)

#: "exactly `<N>` colors" (Invasion of Ravnica // Guildpact Paragon's own
#: "a card that's exactly two colors") - CR 105.2's color count spelled out
#: with its own number rather than as one of `_COLOR_COUNT_WORDS`' two fixed
#: words. `_relative_quality_matcher` reads it for a card named as "card
#: that's `<clause>`" rather than "`<clause>` card".
_EXACTLY_N_COLORS_RE = re.compile(r"^exactly (?P<n>\w+) colors?$", re.IGNORECASE)


def _relative_quality_matcher(phrase: str) -> Callable[[CardState], bool] | None:
    """A card's quality named as a post-nominal relative clause - "a card
    that's exactly two colors" - rather than `_quality_matcher`'s pre-nominal
    adjective order ("a `<quality>` card"). CR 105.2's color count is the
    only shape read today: `_COLOR_COUNT_WORDS`' own "monocolored"/
    "multicolored" spelled this way too, or `_EXACTLY_N_COLORS_RE`'s spelled-
    out number, which `_quality_word_matcher` cannot parse at all - it reads
    a color count only as a single bare leading word, never as its own
    "exactly N" phrase. `None` for anything else, so an unreadable relative
    clause fails the whole clause closed rather than guessing.
    """
    lowered = phrase.strip().lower()
    if lowered in _COLOR_COUNT_WORDS:
        count_matches = _COLOR_COUNT_WORDS[lowered]
        return lambda state: count_matches(len(state.colors))
    exact = _EXACTLY_N_COLORS_RE.fullmatch(lowered)
    if exact is not None:
        n = parse_count(exact.group("n"))
        if n is None:
            return None
        return lambda state: len(state.colors) == n
    return None


#: "Search your library for `<quality>` card, put it into your hand,
#: shuffle" - Curse-Marred Demon's own ETB, minus its trailing "then discard
#: `<n>` card(s) at random" (`_DISCARD_AT_RANDOM_RE` already reads that half
#: on its own, from `_parse_each_player_step`). CR 608.2c's own ordered
#: series of instructions, where "then" marks only the *last* step rather
#: than sitting right before "shuffle" the way `_SEARCH_AND_PUT_RE`'s own
#: fixed tail (", then shuffle") always does - so the two clauses
#: `_prepare_effect_clauses` already cuts here (the search+shuffle half, and
#: the stranded "discard a card at random" with no antecedent of its own)
#: are read as a merged pair rather than two independent clauses, the same
#: way `_merge_reveal_hand_choose_discard_clauses` reads its own run.
_SEARCH_HAND_SHUFFLE_RE = re.compile(
    r"search (?:your|their) library for "
    rf"(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<that_many>that many)) "
    r"(?:(?P<quality>.+?) )?cards?"
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?: with mana cost (?P<mana_costs>" + _MANA_COST_LIST + r"))?"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put (?:it|them|that card|those cards) into your hand, shuffle$",
    re.IGNORECASE,
)


def _merge_search_hand_shuffle_then_discard_random_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_SEARCH_HAND_SHUFFLE_RE` immediately followed by `_DISCARD_AT_RANDOM_
    RE`'s own "discard `<n>` card(s) at random" - Curse-Marred Demon's own
    two clauses, and Reckless Handling's own leading pair ahead of its own
    "if an artifact card was discarded this way" third clause, which this
    merge leaves alone for whatever else reads it."""
    if index + 1 >= len(clauses):
        return None
    search_match = _SEARCH_HAND_SHUFFLE_RE.fullmatch(clauses[index].strip())
    if search_match is None:
        return None
    discard_match = _DISCARD_AT_RANDOM_RE.fullmatch(clauses[index + 1].strip())
    if discard_match is None:
        return None
    described = _search_descriptions(search_match)
    if described is None:
        return None
    count_reader = _read_search_count(search_match)
    if count_reader is None:
        return None
    matches, _description = described
    reveal = bool(search_match.groupdict().get("reveal"))
    discard_count = parse_count(discard_match.group("n")) if discard_match.group("n") else 1
    if discard_count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        game.search_and_put(
            player,
            matches,
            destination=Zone.HAND,
            count=count_reader(game, player.username),
            reveal=reveal,
            source=source,
            source_id=source_id,
        )
        _discard_at_random(game, player, discard_count, source)

    return 2, effect


#: "`<quality>` card(s)[ with mana value N or less| with mana value X or
#: less| with an even/odd mana value]" - the description a "put ... from
#: among them/the milled cards onto the battlefield" instruction names. The
#: mana-value ceiling is Aang, at the Crossroads' and Collected Company's;
#: X is Birthing Ritual's (defined by a trailing "where X is ..."); the
#: parity is Gyruda, Doom of Depths' (CR 202.3: a mana value is a number,
#: and 0 is even).
_PUT_DESCRIPTION_RE = re.compile(
    r"^(?P<quality>.+?) cards?"
    r"(?: with mana value (?P<max_mv>\d+|x) or less| with an? (?P<parity>even|odd) mana value)?$",
    re.IGNORECASE,
)


def _put_description(text: str) -> _PutDescription | None:
    """`_PUT_DESCRIPTION_RE`'s description, or `None` for a quality this
    engine cannot read whole (fail-closed: a put that silently offers fewer
    cards than the card names is a wrong answer, not a cautious one).

    An Oxford comma before the last alternative ("a creature, enchantment,
    or land card" - Fetch Quest) is the same "or" list without it.
    """
    match = _PUT_DESCRIPTION_RE.fullmatch(text.strip())
    if match is None:
        return None
    quality = re.sub(r",\s+or\s+", ", ", match.group("quality").strip(), flags=re.IGNORECASE)
    group = _parse_card_group_qualifier(quality)
    if group is None:
        if not _card_description_is_readable(quality):
            return None
        group = _quality_matcher(quality)
    max_mv = match.group("max_mv")
    x_bound = max_mv is not None and max_mv.lower() == "x"
    return _PutDescription(
        text=text.strip(),
        quality=group,
        max_mv=None if max_mv is None or x_bound else int(max_mv),
        x_bound=x_bound,
        parity=None if match.group("parity") is None else match.group("parity").lower(),
    )


#: "[then ]you may sacrifice `<restriction>`" - Birthing Ritual's own middle
#: sentence, printed between the look and the put it gates.
_THEN_MAY_SACRIFICE_RE = re.compile(r"^(?:then )?you may sacrifice (?P<restriction>.+)$", re.I)
#: "[you may ]put `<quantity>` `<description>` from among them/those cards
#: onto the battlefield[ tapped][, where X is N plus the sacrificed
#: `<type>`'s mana value]".
_PUT_FROM_AMONG_LOOKED_AT_RE = re.compile(
    rf"^(?P<may>you may )?put {quantity_pattern('n')} (?P<description>.+?) "
    r"from among (?:them|those cards) onto the battlefield(?P<tapped> tapped)?"
    rf"(?:, where x is {count_pattern('offset', article=False)} {_SACRIFICED_MANA_VALUE_TERM})?$",
    re.IGNORECASE,
)


def _merge_look_top_put_onto_battlefield_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Look at the top N cards of your library. [Then you may sacrifice
    `<restriction>`. If you do, ]`<put>` from among them onto the
    battlefield. Put the rest on the bottom of your library in any/a random
    order." - one anaphoric run of three or four clauses: "them"/"those
    cards" is the looked-at set, "the rest" whatever of it was not put.

    - Aang, at the Crossroads: "You may put a creature card with mana value
      4 or less from among them" - at most one, optional (CR 608.2d).
    - Collected Company: "Put up to two creature cards with mana value 3 or
      less from among them" - "up to two" is its own optionality (CR 107.1c
      reads "any number" the same way).
    - Birthing Ritual: the sacrifice sits *between* the look and the put
      (CR 608.2c: in the order written), gates it ("If you do"), and fixes
      its X (CR 107.3c: "where X is 1 plus the sacrificed creature's mana
      value", the creature's last known mana value, CR 608.2h). Declining
      puts nothing and bottoms all of them.

    `Game.look_at_top_and_split` does the look (CR 701.20e's knowledge
    included), runs the sacrifice between the look and the choice, and asks
    only about cards the description admits - a card outside it is never a
    legal choice (CR 608.2d). A put-onto-the-battlefield is not a cast
    (CR 110.2a), so no "when you cast" trigger fires.
    """
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    cursor = index + 1
    restriction: _SacrificeRestriction | None = None
    printed_restriction = ""
    if cursor < len(clauses):
        sacrifice = _THEN_MAY_SACRIFICE_RE.fullmatch(clauses[cursor].strip())
        if sacrifice is not None:
            printed_restriction = sacrifice.group("restriction").strip()
            restriction = _sacrifice_restriction(printed_restriction)
            if restriction is None:
                return None
            cursor += 1
    if cursor + 1 >= len(clauses):
        return None
    put_text = clauses[cursor].strip()
    if restriction is not None:
        gated = _IF_YOU_DO_RE.fullmatch(put_text)
        if gated is None:
            return None
        put_text = gated.group("consequence").strip()
    put = _PUT_FROM_AMONG_LOOKED_AT_RE.fullmatch(put_text)
    if put is None:
        return None
    quantity = parse_quantity(put.group("n"))
    if quantity is None or quantity.source not in (
        QuantitySource.FIXED,
        QuantitySource.ANY_NUMBER,
    ):
        return None
    if quantity.exact and quantity.source is QuantitySource.FIXED and put.group("may") is None:
        # A bare "put a creature card from among them" with no "may" is a
        # mandatory pick of exactly that many (CR 608.2d); "you may" or an
        # "up to" makes it a ceiling.
        exact = True
    else:
        exact = False
    description = _put_description(put.group("description"))
    if description is None:
        return None
    offset_word = put.group("offset")
    offset = None if offset_word is None else parse_count(offset_word, article=False)
    if description.x_bound != (offset is not None):
        # An X with no definition, or a definition with no X to define.
        return None
    bottom = _PUT_REST_ON_BOTTOM_ANY_ORDER_RE.fullmatch(clauses[cursor + 1].strip())
    if bottom is None:
        return None
    randomised = bottom.group("random") is not None
    tapped = put.group("tapped") is not None
    consumed = cursor + 2 - index

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        bound: dict[str, float | None] = {"x": None}
        allowed = {"put": restriction is None}

        def before_choosing(_looked: list[CardState]) -> None:
            if restriction is None:
                if offset is not None:
                    sacrificed = _cost_sacrificed_mana_value(game, stack_object)
                    bound["x"] = None if sacrificed is None else offset + sacrificed
                return
            sacrificed = _may_sacrifice_for_its_mana_value(
                game,
                stack_object,
                restriction,
                printed_restriction,
                for_spell=for_spell,
            )
            if sacrificed is None:
                return
            allowed["put"] = True
            if offset is not None:
                bound["x"] = offset + sacrificed

        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            source_id=source_id,
            prompt=f"put {put.group('n').lower()} {description.text} onto the battlefield",
            moved_label="the battlefield",
            kept_label="bottom of your library",
            rest_in_random_order=randomised,
            moved_amount=quantity.amount,
            moved_exact=exact,
            before_choosing=before_choosing,
            moved_candidates=lambda state: allowed["put"] and description.admits(state, bound["x"]),
        )
        with game.entering_together():  # CR 603.6a: one instruction, one event
            for state in moved:
                game.put_onto_battlefield(state, player.username, tapped=tapped)
        _put_rest_on_bottom(
            game,
            player,
            rest,
            randomised=randomised,
            source=source,
            source_id=source_id,
        )

    return consumed, effect


#: Silvan Reveler's own ETB rider: "discard a card. If you discard a land
#: card this way, put it from your graveyard onto the battlefield tapped." A
#: two-clause merge for the identical reason `_discard_cards`'s own
#: docstring gives its return value: "this way" (CR 400.7/CR 607.1) names the
#: specific card *this* discard moved, which only a caller holding that live
#: object - not a fresh graveyard scan, which could not tell this turn's
#: discard from a card that was already there - can answer.
_IF_DISCARD_QUALITY_THIS_WAY_PUT_BATTLEFIELD_RE = re.compile(
    r"^if you discard an? (?P<quality>[a-z]+(?:(?:,| or) [a-z]+)*) cards? this way, "
    r"put (?:it|them) from your graveyard onto the battlefield(?P<tapped> tapped)?$",
    re.IGNORECASE,
)


def _merge_discard_then_land_rebate_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_DISCARD_A_CARD_RE` (a bare, mandatory single discard) immediately
    followed by `_IF_DISCARD_QUALITY_THIS_WAY_PUT_BATTLEFIELD_RE` - see the
    banner above."""
    if index + 1 >= len(clauses):
        return None
    discard_match = _DISCARD_A_CARD_RE.fullmatch(clauses[index].strip().rstrip("."))
    if discard_match is None:
        return None
    if discard_match.group("any") or discard_match.group("upto") or discard_match.group("quality"):
        return None
    count = parse_count(discard_match.group("n"))
    if count is None:
        return None
    rebate_match = _IF_DISCARD_QUALITY_THIS_WAY_PUT_BATTLEFIELD_RE.fullmatch(
        clauses[index + 1].strip().rstrip(".")
    )
    if rebate_match is None:
        return None
    group_text = re.sub(
        r",\s*(?:or\s+)?", " or ", rebate_match.group("quality"), flags=re.IGNORECASE
    )
    predicate = _parse_card_group_qualifier(group_text) or _parse_card_group_alternatives(
        group_text
    )
    if predicate is None:
        return None
    tapped = bool(rebate_match.group("tapped"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        discarded = _discard_cards(game, controller, count, source, source_id=source_id)
        for state in discarded:
            if predicate(state) and state.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)

    return 2, effect


#: Through the Forest Gate's own shape: "Look at the top twenty cards of your
#: library, put any number of land cards from among them onto the
#: battlefield tapped, then shuffle." A two-clause merge: `_CLAUSE_SEPARATOR`
#: cuts the trailing ", then shuffle" off into its own bare "shuffle"
#: fragment (the identical artifact `_rejoin_search_clauses` reattaches for a
#: *search* clause above - this is the same cut on a *look*, which that
#: reattachment does not cover since it only reattaches onto a clause
#: `_MENTIONS_SEARCH_RE` recognises).
_LOOK_TOP_N_PUT_KIND_BATTLEFIELD_RE = re.compile(
    rf"^look at the top (?P<n>{COUNT}) cards? of your library, "
    rf"put {quantity_pattern('take_n')} (?P<kind>[a-z]+) cards? from among them "
    r"onto the battlefield(?P<tapped> tapped)?$",
    re.IGNORECASE,
)


def _merge_look_top_n_put_kind_battlefield_then_shuffle_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_LOOK_TOP_N_PUT_KIND_BATTLEFIELD_RE` immediately followed by a bare
    "shuffle" - see the banner above."""
    if index + 1 >= len(clauses):
        return None
    match = _LOOK_TOP_N_PUT_KIND_BATTLEFIELD_RE.fullmatch(clauses[index].strip().rstrip("."))
    if match is None:
        return None
    if clauses[index + 1].strip().rstrip(".").lower() != "shuffle":
        return None
    n = parse_count(match.group("n"))
    if n is None:
        return None
    quantity = parse_quantity(match.group("take_n"))
    if quantity is None or quantity.source not in (QuantitySource.FIXED, QuantitySource.ANY_NUMBER):
        return None
    kind_word = match.group("kind").lower()
    kind_predicate = _SELECT_FROM_TOP_KINDS.get(kind_word)
    if kind_predicate is None:
        return None
    tapped = bool(match.group("tapped"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        looked = list(controller.library[:n])
        candidates = [state for state in looked if kind_predicate(state)]
        if candidates:
            ceiling = (
                len(candidates)
                if quantity.source is QuantitySource.ANY_NUMBER or quantity.amount is None
                else min(quantity.amount, len(candidates))
            )
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"put any number of {kind_word} cards onto the battlefield",
                    source=source,
                    source_id=source_id,
                    amount=ceiling,
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                )
            )
            by_id = {state.id: state for state in candidates}
            for card_id in chosen_ids:
                state = by_id.get(card_id)
                if state is not None:
                    game.put_onto_battlefield(state, controller.username, tapped=tapped)
        game.shuffle_library(controller.username)

    return 2, effect


#: "If you put a `<quality>` card into your graveyard this way, put that
#: card into your hand." - Chandra, Chill of Compliance's own `+1` (a plain
#: quality, "noncreature, nonland") and Enlightened Confidant's own trigger
#: (a dynamic mana-value ceiling, "the amount of life you gained this
#: turn"), following a surveil. "This way" is CR 608.2c anaphora onto
#: exactly what the surveil itself just put into the graveyard - the
#: `Game.surveil`/`Game.scry` `CardSplit.moved` return value, not a second,
#: independent graveyard scan.
_SURVEIL_THEN_IF_PUT_QUALITY_TO_HAND_RE = re.compile(
    r"^if you put an? (?P<quality>.*?)card"
    r"(?: with mana value less than or equal to (?P<mv_expr>.+?))?"
    r" into your graveyard this way, put that card into your hand\.?$",
    re.IGNORECASE,
)


def _merge_surveil_then_if_quality_to_hand_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_SURVEIL_RE` immediately followed by `_SURVEIL_THEN_IF_PUT_QUALITY_
    TO_HAND_RE` - Chandra, Chill of Compliance's own `+1` and Enlightened
    Confidant's own end-step trigger. A merge, not two independent clauses:
    the second sentence's "this way" needs to know exactly which card (if
    any) the first sentence's surveil put into the graveyard, which only a
    caller holding the live `CardSplit` the surveil itself returned can
    answer - a fresh graveyard scan could not tell that card apart from one
    already sitting there.
    """
    if index + 1 >= len(clauses):
        return None
    surveil_match = _SURVEIL_RE.fullmatch(clauses[index].strip())
    if surveil_match is None:
        return None
    reader = _amount_reader(surveil_match.group("n"), surveil_match.group("where_x"))
    if reader is None:
        return None
    hand_match = _SURVEIL_THEN_IF_PUT_QUALITY_TO_HAND_RE.fullmatch(clauses[index + 1].strip())
    if hand_match is None:
        return None
    quality_text = (hand_match.group("quality") or "").strip()
    quality_matches = (
        (lambda state: True) if not quality_text else _nonland_or_typed_card_matcher(quality_text)
    )
    if quality_matches is None:
        return None
    mv_expr = hand_match.group("mv_expr")
    mv_counter = count_expression(mv_expr) if mv_expr else None
    if mv_expr and mv_counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        split = game.surveil(
            player, reader(game, player.username), source=source, source_id=source_id
        )
        if not split.moved:
            return
        ceiling = mv_counter(game, player.username) if mv_counter is not None else None
        by_id = {state.id: state for state in player.graveyard}
        for card_id in split.moved:
            state = by_id.get(card_id)
            if state is None or not quality_matches(state):
                continue
            if ceiling is not None and state.mana_value > ceiling:
                continue
            player.add(state, Zone.HAND)
            break

    return 2, effect


#: "for each card you put on top of your library, you draw a card" -
#: Starving Revenant's own ETB, the surveil's *kept* half rather than
#: `_SURVEIL_THEN_IF_PUT_QUALITY_TO_HAND_RE`'s graveyard-bound half. CR
#: 701.25a's own "the rest on top of your library" is exactly `CardSplit.
#: top_order`, which `Game.surveil` always fills (never `None`, unlike a
#: bare `look_at_top_and_split` caller that lets the order stay implicit),
#: so counting it needs no fallback to "N minus how many moved".
_SURVEIL_THEN_FOR_EACH_ON_TOP_DRAW_A_CARD_RE = re.compile(
    r"^for each card you put on top of your library, you draw a card$", re.IGNORECASE
)


def _merge_surveil_then_for_each_on_top_draw_and_lose_life_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_SURVEIL_RE` followed by `_SURVEIL_THEN_FOR_EACH_ON_TOP_DRAW_A_CARD_RE`
    and `_YOU_LOSE_LIFE_RE` (Starving Revenant's own three sentences once
    `_prepare_effect_clauses` has split "you draw a card and you lose 3
    life" at its own top-level "and") - a three-way merge for the identical
    CR 608.2c reason `_merge_surveil_then_if_quality_to_hand_clauses` merges
    two: "for each card you put on top" has no meaning apart from how many
    the surveil that ran a moment earlier actually kept there, which only
    the live `CardSplit` it returned can answer.

    Each kept card draws one card and loses the life separately (CR 608.2c's
    own "in the order written", one iteration of "you draw a card and you
    lose `<n>` life" per card), so a "whenever you draw a card" trigger this
    same permanent or another one carries - Starving Revenant's own descend
    8 - fires once per card kept, exactly as many times as the surveil kept
    cards on top, never once for the batch.
    """
    if index + 2 >= len(clauses):
        return None
    surveil_match = _SURVEIL_RE.fullmatch(clauses[index].strip())
    if surveil_match is None:
        return None
    reader = _amount_reader(surveil_match.group("n"), surveil_match.group("where_x"))
    if reader is None:
        return None
    if not _SURVEIL_THEN_FOR_EACH_ON_TOP_DRAW_A_CARD_RE.fullmatch(clauses[index + 1].strip()):
        return None
    lose_match = _YOU_LOSE_LIFE_RE.fullmatch(clauses[index + 2].strip().rstrip("."))
    if lose_match is None:
        return None
    life_per_card = int(lose_match.group("life"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        split = game.surveil(
            player, reader(game, player.username), source=source, source_id=source_id
        )
        for _ in split.top_order:
            game.draw_cards(player, 1)
            game.lose_life(player, life_per_card)

    return 3, effect


#: "Reveal the top card of your library and put that card into your hand.
#: You lose life equal to that card's mana value." - the Dark Confidant
#: template (CR 202.3's mana value), Pain Seer's own Inspired trigger.
#: Current Oracle text prints the pronoun instead ("... equal to its mana
#: value" - Dark Confidant's and Darkstar Augur's own upkeep triggers); "its"
#: and "that card's" name the same revealed card, so both spellings read.
#: `_prepare_effect_clauses` cuts the first sentence's own "and" the same
#: way it cuts every other one, so this reads as three clauses rather than
#: two.
_REVEAL_TOP_CARD_OF_LIBRARY_BARE_RE = re.compile(
    r"^reveal the top card of your library$", re.IGNORECASE
)
_PUT_THAT_CARD_INTO_YOUR_HAND_BARE_RE = re.compile(r"^put that card into your hand$", re.IGNORECASE)
_YOU_LOSE_LIFE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE = re.compile(
    r"^you lose life equal to (?:that card'?s|its) mana value$", re.IGNORECASE
)


def _merge_reveal_top_hand_lose_life_equal_to_mana_value_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_REVEAL_TOP_CARD_OF_LIBRARY_BARE_RE`, `_PUT_THAT_CARD_INTO_YOUR_HAND_
    BARE_RE`, then `_YOU_LOSE_LIFE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE` - a
    three-way merge for the identical CR 608.2c reason the surveil merges
    above are: "that card" (CR 608.2c anaphora) is whichever card the first
    sentence just revealed, which only this function, holding the live
    `CardState` the reveal touched, can answer; a fresh "top of library"
    lookup after the card has already moved to hand would answer nothing.

    The reveal (CR 701.20a) happens before the move, so every player sees
    the same card the life total is about to be measured against - moving
    it to hand first and revealing the hand card after would show a card
    that, by the rules text's own order, was never on top of the library
    when it was shown.
    """
    if index + 2 >= len(clauses):
        return None
    if not _REVEAL_TOP_CARD_OF_LIBRARY_BARE_RE.fullmatch(clauses[index].strip()):
        return None
    if not _PUT_THAT_CARD_INTO_YOUR_HAND_BARE_RE.fullmatch(clauses[index + 1].strip()):
        return None
    if not _YOU_LOSE_LIFE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE.fullmatch(clauses[index + 2].strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if not player.library:
            # CR 704.5b's failed-draw shape has no analogue that stops a
            # reveal from an empty library outright, but there is simply no
            # card to reveal, move, or measure a mana value from (CR 121.4).
            return
        card = player.library[0]
        game.reveal(card, source=source)
        mana_value = int(card.mana_value)
        player.add(card, Zone.HAND)
        game.lose_life(player, mana_value)

    return 3, effect


#: "It's an Island in addition to its other types for as long as it has a
#: flood counter on it." (Eluge, the Shoreless Sea) / "That land is an Island
#: ..." (Aquitect's Will) - the rider on a "put a `<kind>` counter on target
#: `<permanent>`" instruction just before it: the targeted permanent gains a
#: subtype (CR 205.1b) for exactly as long as it keeps that kind of counter
#: (CR 611.2b).
_SUBTYPE_WHILE_COUNTER_RIDER_RE = re.compile(
    r"^(?:it's|it is|that (?:land|permanent|creature|artifact)(?:'s| is)) an? "
    r"(?P<subtype>[A-Z][A-Za-z'-]*) in addition to its other types for as long as it has "
    r"an? (?P<kind>[a-z]+|\+1/\+1|-1/-1) counter on it\.?$",
    re.IGNORECASE,
)


def _merge_counter_then_subtype_while_counter_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Put a flood counter on target land. It's an Island in addition to its
    other types for as long as it has a flood counter on it." - the counter
    (CR 122.1) and then, on each target that got it, a layer 4 type-adding
    effect (CR 613.1d, CR 205.1b) whose "for as long as" duration (CR 611.2b)
    is the counter itself (`HasCounter`), not the source: it outlasts Eluge,
    and ends for good the moment the last such counter comes off. A basic
    land type brings its intrinsic mana ability along (CR 305.6,
    `add_subtype`). The rider must name the same counter kind the first
    clause puts, or this is not the shape.
    """
    if index + 1 >= len(clauses):
        return None
    put = _COUNTER_TARGET_RE.fullmatch(clauses[index].strip())
    rider = _SUBTYPE_WHILE_COUNTER_RIDER_RE.fullmatch(clauses[index + 1].strip())
    if put is None or rider is None or put.group("each") is not None:
        return None
    kind = _counter_kind(put.group("kind"))
    if _counter_kind(rider.group("kind")) != kind:
        return None
    amount = parse_count(put.group("n"))
    if amount is None or not _targets_understood(put.group("phrase"), count_agnostic=True):
        return None
    subtype = next(
        (word for word in subtype_vocabulary() if word == rider.group("subtype").lower()), None
    )
    if subtype is None:
        return None
    printed = rider.group("subtype").capitalize()
    mana_ability = BASIC_LAND_TYPES.get(printed)
    put_counters = put_counters_on_ability_targets(kind, amount)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        put_counters(game, stack_object)
        source = source_id_of(stack_object)
        store = continuous_effects(game)
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            store.add(
                ContinuousEffect(
                    description=(
                        f"{target.name} is {with_indefinite_article(printed)} in addition to "
                        f"its other types while it has a {kind} counter"
                    ),
                    layer=Layer.TYPE,
                    timestamp=store.tick(),
                    source_id=UUID(source) if source is not None else None,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=add_subtype(printed, mana_ability),
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=HasCounter(
                        card_id=target.id, stamp=target.zone_change_stamp, counter=str(kind)
                    ),
                ),
                game,
            )

    return 2, effect


def _merge_tap_target_then_no_untap_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Frost Breath, Chill of the Grave: the same "Tap ... target(s). It/
    those creatures don't untap ..." pair `_parse_tap_target_then_no_untap_
    clause` already reads whole for Tamiyo's loyalty ability, but printed on
    an instant instead - and, for Chill of the Grave, with a further "Draw a
    card." clause after it. `split_effect_clauses` cuts a spell's own text
    into one clause per sentence with no notion that this pair is one CR
    608.2c instruction, so `_parse_mixed_clauses` has to try the two adjacent
    clauses together before falling back to reading each alone; unused
    `for_spell` kept only for the same signature every other merge function
    in this chain has, since `effect()` below is generic over an ability or a
    spell already (`game.resolve_targets` and `game.controller_of` take
    either).
    """
    if index + 1 >= len(clauses):
        return None
    pair = f"{clauses[index].strip()}. {clauses[index + 1].strip()}."
    effect = _parse_tap_target_then_no_untap_clause(pair)
    if effect is None:
        return None
    return 2, effect


def _merge_tap_target_recipient_then_no_untap_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Glacial Grasp: "Tap target creature. Its controller mills two cards.
    That creature doesn't untap during its controller's next untap step." -
    `_merge_tap_target_then_no_untap_clauses`' pair with a sentence between
    its halves whose recipient is the target's controller (CR 109.5, a mill or
    life change read by `ep02_r1_controller_recipients`). Run in the printed
    order (CR 608.2c): tap, the recipient's instruction, the withheld untap."""
    if index + 2 >= len(clauses):
        return None
    from ..decisions import source_id_of
    from ..ep02_r1_controller_recipients import (
        CONTROLLER_ANAPHOR,
        controller_username,
        parse_predicate,
    )
    from ..ep02_r1_referenced_stat import snapshot_of

    recipient = re.fullmatch(
        rf"{CONTROLLER_ANAPHOR} (?P<predicate>.+?)\.?",
        clauses[index + 1].strip(),
        re.IGNORECASE,
    )
    if recipient is None:
        return None
    predicate = parse_predicate(recipient.group("predicate"))
    if predicate is None:
        return None
    pair = f"{clauses[index].strip()}. {clauses[index + 2].strip()}."
    tap_and_hold = _parse_tap_target_then_no_untap_clause(pair)
    if tap_and_hold is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        target = next(
            (t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)), None
        )
        if target is None:
            return  # CR 608.2b: nothing legal left to tap or refer to
        username = controller_username(game, target)
        referent = snapshot_of(game, target) if predicate.stat is not None else None
        tap_and_hold(game, stack_object)
        if username is not None:
            predicate.run(
                game,
                game.player(username),
                referent,
                getattr(stack_object, "source_name", None) or getattr(stack_object, "name", ""),
                source_id_of(stack_object),
            )

    return 3, effect


#: "Reveal cards from the top of your library until you reveal a `<kind>`[ or
#: `<kind2>`] card. Put that card `<dest>` and the rest on the bottom of your
#: library in a random order." - CR 701.20a's open-ended reveal, the same
#: family `_parse_reveal_until_land_damage_clause` reads for its own
#: damage-and-doubling shape, generalized to any of `_SELECT_FROM_TOP_KINDS`'
#: single types or an "or" pair of them, and to a plain "put that card
#: somewhere" outcome rather than a damage consequence - Identity Echo's own
#: activated ability. A common template (Evolutionary Leap, Clifftop Lookout,
#: Jace, Multiverse Architect's own `-3`), not unique to this card.
_REVEAL_UNTIL_KIND_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal "
    r"an? (?P<kind>[a-z]+(?: or [a-z]+)?) cards?$",
    re.IGNORECASE,
)
#: The rider naming what to do with the card that stopped the reveal -
#: `_CLAUSE_SEPARATOR`'s own bare-"and" split cuts this away from "the rest
#: ..." below it (`_PUT_REVEALED_CARD_REST_RANDOM_RE`) into two clause
#: fragments of its own, the same way it does everywhere else a printed
#: sentence joins two instructions with a bare "and".
_PUT_REVEALED_CARD_RE = re.compile(
    r"^put that card (?P<dest>into your hand|onto the battlefield tapped"
    r"|onto the battlefield|into your graveyard)$",
    re.IGNORECASE,
)
#: Where every other card revealed along the way goes - always the bottom of
#: the library, always randomized (CR 701.24a's shuffle is never the verb
#: printed here, so this is not a shuffle and nothing watching for one
#: fires), whichever of the two synonymous phrasings the pool prints for
#: "the cards that were not kept."
_PUT_REVEALED_CARD_REST_RANDOM_RE = re.compile(
    r"^(?:the rest|all other cards revealed this way) "
    r"on the bottom of your library in a random order$",
    re.IGNORECASE,
)


def _merge_reveal_until_kind_then_put_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_REVEAL_UNTIL_KIND_RE` immediately followed by `_PUT_REVEALED_CARD_RE`
    and `_PUT_REVEALED_CARD_REST_RANDOM_RE` - a three-clause merge, not
    independent instructions, for the identical reason `_merge_surveil_
    then_if_quality_to_hand_clauses` is: "that card" (CR 400.7/CR 607.1) is
    the specific card that stopped the reveal, which only a caller holding
    that live object (not a fresh library/graveyard scan) can name, and "the
    rest" is everything else this same reveal showed.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_match = _REVEAL_UNTIL_KIND_RE.fullmatch(clauses[index].strip().rstrip("."))
    if reveal_match is None:
        return None
    put_match = _PUT_REVEALED_CARD_RE.fullmatch(clauses[index + 1].strip().rstrip("."))
    if put_match is None:
        return None
    if _PUT_REVEALED_CARD_REST_RANDOM_RE.fullmatch(clauses[index + 2].strip().rstrip(".")) is None:
        return None
    kind_words = [word.strip() for word in reveal_match.group("kind").lower().split(" or ")]
    predicates = [_SELECT_FROM_TOP_KINDS.get(word) for word in kind_words]
    if any(predicate is None for predicate in predicates):
        return None

    def matches_kind(state: CardState) -> bool:
        return any(predicate(state) for predicate in predicates)  # type: ignore[misc]

    dest = put_match.group("dest").lower()

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        revealed: list[CardState] = []
        stopper: CardState | None = None
        for state in list(controller.library):
            game.reveal(state, source=source)
            revealed.append(state)
            if matches_kind(state):
                stopper = state
                break
        if stopper is not None:
            if dest == "into your hand":
                controller.move(stopper, Zone.HAND)
            elif dest == "into your graveyard":
                game.put_into_graveyard(stopper)
            else:
                game.put_onto_battlefield(
                    stopper, controller.username, tapped=dest.endswith("tapped")
                )
        # "The rest" is a randomization (CR 401.4's own owner's-choice
        # ordering is never asked here, unlike `_select_from_top_runner`'s
        # own "in any order" arm), reusing the same reproducible-seed
        # convention `_select_from_top_runner` and `_parse_reveal_top_n_
        # one_per_card_type_clause` already share.
        remainder = [
            state for state in revealed if state is not stopper and state.zone is Zone.LIBRARY
        ]
        if remainder:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-until-kind"
            )
            rng.shuffle(remainder)
            game.shuffles_performed += 1
            for state in remainder:
                controller.move(state, Zone.LIBRARY)

    return 3, effect


#: Skyserpent Seeker: "Exhaust - {4}: Reveal cards from the top of your
#: library until you reveal two land cards. Put those land cards onto the
#: battlefield tapped and the rest on the bottom of your library in a random
#: order." `_REVEAL_UNTIL_KIND_RE`'s own fixed "a `<kind>` card" (one)
#: widened to any literal `COUNT` two or greater via `_reveal_until_n_of_kind`
#: - the same resolution-time-count generalisation Aurora Awakener's and
#: Sanar's own variable X built - proven here on a real, off-pool,
#: Modern/Pioneer/Standard-legal printing that carries neither card's own
#: template, only the shared reveal-and-count core and `_shuffle_remainder_
#: to_bottom` (Aurora Awakener's own tail helper). A literal singular "a
#: `<kind>` card" stays `_REVEAL_UNTIL_KIND_RE`'s own case - English never
#: pluralises "cards" for a count of one, so the two patterns never compete
#: for the same sentence. See the dated MEMORY.md line for why Old
#: Stickfingers, this family's first-tried off-pool candidate, was replaced
#: with this one instead.
_REVEAL_UNTIL_N_KIND_RE = re.compile(
    rf"^reveal cards from the top of your library until you reveal "
    rf"(?P<count>{COUNT}) (?P<kind>[a-z]+) cards$",
    re.IGNORECASE,
)
#: "Put those `<kind>` cards onto the battlefield[ tapped]" - the plural,
#: mandatory-placement sibling of `_PUT_REVEALED_CARD_RE`'s own singular
#: "put that card `<dest>`", split off the clause after it by the same bare-
#: "and" `_CLAUSE_SEPARATOR` cut documented on `_PUT_REVEALED_CARD_RE`.
_PUT_REVEALED_CARDS_ONTO_BATTLEFIELD_RE = re.compile(
    r"^put those (?P<kind>[a-z]+) cards onto the battlefield(?P<tapped> tapped)?$",
    re.IGNORECASE,
)


def _merge_reveal_until_n_kind_put_onto_battlefield_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_REVEAL_UNTIL_N_KIND_RE` immediately followed by
    `_PUT_REVEALED_CARDS_ONTO_BATTLEFIELD_RE` and `_PUT_REVEALED_CARD_REST_
    RANDOM_RE` - a three-clause merge for the same reason `_merge_reveal_
    until_kind_then_put_clauses` is one: the cards that stopped the reveal
    are live objects only the caller resolving this ability holds, and "the
    rest" is everything else that same reveal showed.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_match = _REVEAL_UNTIL_N_KIND_RE.fullmatch(clauses[index].strip().rstrip("."))
    if reveal_match is None:
        return None
    put_match = _PUT_REVEALED_CARDS_ONTO_BATTLEFIELD_RE.fullmatch(
        clauses[index + 1].strip().rstrip(".")
    )
    if put_match is None:
        return None
    kind_word = reveal_match.group("kind").lower()
    if put_match.group("kind").lower() != kind_word:
        return None
    if _PUT_REVEALED_CARD_REST_RANDOM_RE.fullmatch(clauses[index + 2].strip().rstrip(".")) is None:
        return None
    predicate = _SELECT_FROM_TOP_KINDS.get(kind_word)
    if predicate is None:
        return None
    count = parse_count(reveal_match.group("count"))
    if count is None:
        return None
    tapped = put_match.group("tapped") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        matches, remainder = _reveal_until_n_of_kind(
            game, controller, predicate, count, source=source
        )
        for state in matches:
            game.put_onto_battlefield(state, controller.username, tapped=tapped)
        _shuffle_remainder_to_bottom(game, controller, remainder)

    return 3, effect


#: Part in Friendship's own trigger: "reveal cards from the top of your
#: library until you reveal a creature card. If its mana value is less than
#: or equal to the number of lands you control, put it onto the battlefield.
#: Otherwise, put it into your hand. Put the rest on the bottom of your
#: library in a random order." A four-clause merge - `_REVEAL_UNTIL_KIND_RE`
#: read whole across all four the same way `_merge_reveal_until_kind_then_
#: put_clauses` above reads it across three, only with the stopping card's
#: destination decided by a board-state comparison (CR 107.1a's "less than or
#: equal to", `count_expression`'s own general reader for "the number of
#: lands you control") instead of being the same fixed destination every
#: time.
_IF_MV_LTE_PUT_BATTLEFIELD_RE = re.compile(
    r"^if its mana value is less than or equal to (?P<expr>.+?), "
    r"put it onto the battlefield$",
    re.IGNORECASE,
)
_OTHERWISE_PUT_HAND_RE = re.compile(r"^otherwise, put it into your hand$", re.IGNORECASE)
#: The identical "the rest on the bottom of your library in a random order"
#: instruction `_PUT_REVEALED_CARD_REST_RANDOM_RE` already reads, printed here
#: as its own capitalized, "Put"-led sentence (Part in Friendship's fourth
#: clause) rather than as the second half of an "and"-joined sentence
#: (Identity Echo's own "... and the rest on the bottom ..."), which is why
#: that regex's own bare-lowercase anchor never matches this shape and a
#: sibling regex reads the "Put " prefix instead of assuming
#: `_CLAUSE_SEPARATOR` already stripped it.
_PUT_REST_BOTTOM_RANDOM_SENTENCE_RE = re.compile(
    r"^put the rest on the bottom of your library in a random order$", re.IGNORECASE
)


def _merge_reveal_until_kind_conditional_mv_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_REVEAL_UNTIL_KIND_RE` immediately followed by `_IF_MV_LTE_PUT_
    BATTLEFIELD_RE`, `_OTHERWISE_PUT_HAND_RE`, and `_PUT_REVEALED_CARD_REST_
    RANDOM_RE` - see the banner above. "Its"/"it" (CR 400.7/CR 607.1) is the
    one card that stopped the reveal, exactly as in `_merge_reveal_until_
    kind_then_put_clauses`.
    """
    if index + 3 >= len(clauses):
        return None
    reveal_match = _REVEAL_UNTIL_KIND_RE.fullmatch(clauses[index].strip().rstrip("."))
    if reveal_match is None:
        return None
    battlefield_match = _IF_MV_LTE_PUT_BATTLEFIELD_RE.fullmatch(
        clauses[index + 1].strip().rstrip(".")
    )
    if battlefield_match is None:
        return None
    if _OTHERWISE_PUT_HAND_RE.fullmatch(clauses[index + 2].strip().rstrip(".")) is None:
        return None
    if (
        _PUT_REST_BOTTOM_RANDOM_SENTENCE_RE.fullmatch(clauses[index + 3].strip().rstrip("."))
        is None
    ):
        return None
    kind_words = [word.strip() for word in reveal_match.group("kind").lower().split(" or ")]
    predicates = [_SELECT_FROM_TOP_KINDS.get(word) for word in kind_words]
    if any(predicate is None for predicate in predicates):
        return None

    def matches_kind(state: CardState) -> bool:
        return any(predicate(state) for predicate in predicates)  # type: ignore[misc]

    counter = count_expression(battlefield_match.group("expr").strip())
    if counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        revealed: list[CardState] = []
        stopper: CardState | None = None
        for state in list(controller.library):
            game.reveal(state, source=source)
            revealed.append(state)
            if matches_kind(state):
                stopper = state
                break
        if stopper is not None:
            ceiling = counter(game, controller.username)
            if stopper.mana_value <= ceiling:
                game.put_onto_battlefield(stopper, controller.username)
            else:
                controller.move(stopper, Zone.HAND)
        remainder = [
            state for state in revealed if state is not stopper and state.zone is Zone.LIBRARY
        ]
        if remainder:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-until-kind-conditional-mv"
            )
            rng.shuffle(remainder)
            game.shuffles_performed += 1
            for state in remainder:
                controller.move(state, Zone.LIBRARY)

    return 4, effect


#: "The next time target creature would deal damage this turn, prevent that
#: damage." (Awe Strike) - CR 615.8's next-instance shield naming a *source*,
#: not a shielded object; see `_prevent_next_damage_from_target` and
#: `_merge_prevent_damage_from_target_clauses` for the optional CR 615.5
#: life-gain rider on the sentence after it.
_PREVENT_NEXT_TIME_TARGET_WOULD_DEAL_DAMAGE_RE = re.compile(
    r"^the next time (?P<phrase>target creature) would deal damage this turn, "
    r"prevent that damage\.?$",
    re.IGNORECASE,
)
#: The optional CR 615.5 rider naming the amount by its own effect rather
#: than a fixed number - "You gain life equal to the damage prevented this
#: way."
_GAIN_LIFE_EQUAL_TO_DAMAGE_PREVENTED_RE = re.compile(
    r"^you gains? life equal to the damage prevented this way\.?$", re.IGNORECASE
)


#: The pump half of a combined "gets +N/+N and gains <keyword>" sentence
#: (Give In to Violence: "Target creature gets +2/+2 and gains lifelink until
#: end of turn."), once `split_effect_clauses`'s own "and" separator has cut
#: the duration and the keyword off the end of it. The plural alternative
#: ("(?:(?:up to )?{AMOUNT}|any number of) target creatures(?: you control)?
#: each get(s)? ...") is Aerial Formation's own shape - "Any number of target
#: creatures each get +1/+1 and gain flying until end of turn." - split the
#: identical way, with the plural verb "get" (not "gets") and the "each"
#: landing inside this first clause rather than after it.
_BARE_CONTINUOUS_PUMP_RE = re.compile(
    r"^(?:target creature gets|(?:(?:up to |one or )?"
    + AMOUNT
    + r"|any number of) target creatures(?: you control)? each gets?) [+-]\d+/[+-]\d+$",
    re.IGNORECASE,
)
#: The keyword half of the *reversed* order, "gains <keyword> and gets +N/+N"
#: - a shape this pool has no real card for, but CR 608.2c does not care which
#: half a card prints first, so it is read the same way as the forward order.
_BARE_CONTINUOUS_KEYWORD_START_RE = re.compile(
    r"^target creature gains [a-z]+(?: [a-z]+)?$", re.IGNORECASE
)
#: One more keyword in a run of them (Aerial Maneuver: "gains flying and first
#: strike" splits into a "gains flying" piece and a "first strike until end of
#: turn" piece, one bare word or two-word keyword name per clause, only the
#: last one carrying "until <duration>"). This does not check the word against
#: `Keyword` - that is `machines/layers.py`'s job once the whole spell reaches
#: `create_continuous_effect`; a keyword or a conjunction it does not know
#: (Aerial Maneuver's two keywords, Tainted Strike's infect) fails closed there
#: with a `LayerNotice` rather than never reaching a parser at all.
_CONTINUOUS_KEYWORD_CONTINUATION_RE = re.compile(
    r"^(?:gains?\s+)?(?P<word>[a-z]+(?:\s[a-z]+)?)"
    r"(?:\s+until\s+(?P<duration>end of turn|your next turn))?\.?$",
    re.IGNORECASE,
)
#: The pump half of the reversed order's tail, once "and" has cut it away from
#: the keyword that opened the sentence.
_BARE_CONTINUOUS_PUMP_TAIL_RE = re.compile(
    r"^gets [+-]\d+/[+-]\d+ until (?:end of turn|your next turn)\.?$", re.IGNORECASE
)


def _merge_continuous_pump_keyword_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Undo `split_effect_clauses`'s own "and" cut through "Target creature
    gets +N/+N and gains <keyword>[, and gains another, ...] until end of
    turn." (or its reverse) so the two or more clauses it left behind are
    handled as the one CR 608.2c instruction they actually are (CR 611.2), not
    several unreadable fragments.

    Spell-only: an ability's own continuous pump/keyword grant is never read
    off its printed text at all (`_CONTINUOUS_PUMP_OR_KEYWORD_RE`'s own
    docstring explains why) - it goes through `create_continuous_effect_of_ability`
    keyed by ability index instead, so this returns `None` outright when
    `for_spell` is false rather than guessing at a shape nothing here reads.

    Deliberately loose about what counts as "a keyword": this only recognises
    the *shape* the split left behind, not whether any word in it is one
    `machines/layers.py` or `machines/combat.py` actually models. Whatever gets
    merged back together is handed whole to `create_continuous_effect`, which
    reads the spell's own oracle text through `parsed_layer_effects` - the same
    parser a plain "gets +N/+N until end of turn." already goes through, and
    the one that turns a keyword it does not know, a reversed order it does not
    read, more than one keyword conjoined, or a duration other than "until end
    of turn" into a `LayerNotice` rather than a silent no-op.

    Returns how many clauses starting at `index` belong to this one
    instruction, and the effect to run for all of them, or `None` if `index`
    is not the start of this shape at all.
    """
    if not for_spell:
        return None
    first = clauses[index]
    if _BARE_CONTINUOUS_PUMP_RE.fullmatch(first):
        cursor = index + 1
        found_duration = False
        while cursor < len(clauses):
            match = _CONTINUOUS_KEYWORD_CONTINUATION_RE.fullmatch(clauses[cursor])
            if match is None:
                break
            cursor += 1
            if match.group("duration") is not None:
                found_duration = True
                break
        if found_duration:
            return cursor - index, create_continuous_effect  # type: ignore[return-value]
        return None
    if (
        _BARE_CONTINUOUS_KEYWORD_START_RE.fullmatch(first)
        and index + 1 < len(clauses)
        and _BARE_CONTINUOUS_PUMP_TAIL_RE.fullmatch(clauses[index + 1])
    ):
        return 2, create_continuous_effect  # type: ignore[return-value]
    return None


#: "`<n>` damage to `<phrase>`" with no subject or verb of its own - the
#: second half of "`<source>` deals `<n>` damage to `<phrase1>` and `<n>`
#: damage to `<phrase2>`" once `_CLAUSE_SEPARATOR`'s bare "and" split has
#: cut the shared "`<source>` deals" off the front of it. Way of the
#: Warlord's own granted "[-4]" ("This planeswalker deals 2 damage to up to
#: one target creature or planeswalker and 2 damage to target player.") and
#: Lunge's off-set "Lunge deals 2 damage to target creature and 2 damage to
#: target player or planeswalker." are the identical shape, one a loyalty
#: ability's own source, one a spell's.
_BARE_DAMAGE_CONTINUATION_RE = re.compile(
    rf"^(?P<n>{AMOUNT}) damage to (?P<phrase>any target|any other target|.*?target.+?)\.?$",
    re.IGNORECASE,
)


#: "Destroy target `<permanent>`." + "[If `<condition>`, ]`<this>` deals N
#: damage to that `<permanent>`'s controller." - Smash to Smithereens,
#: Destructive Revelry, Consign to the Pit, Unlicensed Disintegration, and
#: Cindervines' own sacrifice ability. CR 400.7's "that artifact" names the
#: first instruction's target; its controller is read before the destroy
#: moves it (CR 608.2h: last known information), and the damage is dealt
#: whether or not the destroy happened (an indestructible target still has a
#: controller). CR 608.2b: an illegal target determines nothing, so it
#: contributes no controller.
_DESTROY_TARGET_CLAUSE_RE = re.compile(r"^destroy (?:up to one )?target\b", re.IGNORECASE)
_DAMAGE_THAT_PERMANENTS_CONTROLLER_RE = re.compile(
    rf"^(?:if (?P<condition>[^,]+), )?(?P<subject>[^,]+?) deals (?P<n>{COUNT}) damage to "
    r"that (?P<noun>[a-z ]+?)'s controller\.?$",
    re.IGNORECASE,
)

#: The same follow-up with an amount that is a count of cards in a graveyard:
#: "`<this>` deals damage to that land's controller equal to the number of land
#: cards in that player's graveyard." (Roiling Terrain). The count is taken
#: after the destroy (CR 608.2c - the land just destroyed is in it) and in the
#: graveyard of the controller the target had before it (CR 608.2h).
_DAMAGE_THAT_PERMANENTS_CONTROLLER_EQUAL_RE = re.compile(
    r"^(?P<subject>[^,]+?) deals damage to that (?P<noun>[a-z ]+?)'s controller equal to "
    r"(?P<expr>[^,]*graveyard[^,]*?)\.?$",
    re.IGNORECASE,
)


def _merge_destroy_then_damage_controller_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_DESTROY_TARGET_CLAUSE_RE` + `_DAMAGE_THAT_PERMANENTS_CONTROLLER_RE`,
    read as one CR 608.2c instruction; see the banner above."""

    if index + 1 >= len(clauses):
        return None
    if _DESTROY_TARGET_CLAUSE_RE.match(clauses[index].strip()) is None:
        return None
    follow = clauses[index + 1].strip()
    match = _DAMAGE_THAT_PERMANENTS_CONTROLLER_RE.fullmatch(follow)
    equal = _DAMAGE_THAT_PERMANENTS_CONTROLLER_EQUAL_RE.fullmatch(follow)
    if (match or equal) is None or re.search(
        r"\btarget\b", (match or equal).group("subject"), re.IGNORECASE
    ):
        return None
    condition = match.group("condition") if match is not None else None
    if condition is not None and not _effect_condition_is_readable(condition):
        return None
    amount = parse_count(match.group("n")) if match is not None else None
    count_reader = None
    counts_for_controller = False
    if equal is not None:
        from ..ep02_r1_graveyard_counts import recipient_view

        phrase, counts_for_controller = recipient_view(equal.group("expr"))
        count_reader = amount_expression(phrase)
    if amount is None and count_reader is None:
        return None
    destroy = _parse_targeted_clause(clauses[index], for_spell=for_spell)
    if destroy is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controllers = [
            game.controller_of(target).username
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        destroy(game, stack_object)
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        )
        if condition is not None:
            controller = game.controller_of(stack_object).username
            if game.condition_holds(controller, condition, source) is not True:
                return
        for username in controllers:
            dealt = (
                amount
                if count_reader is None
                else count_reader(
                    game,
                    username
                    if counts_for_controller
                    else game.controller_of(stack_object).username,
                    source,
                    0,
                )
            )
            if dealt:
                game.deal_damage(game.player(username), dealt, source=source)

    return 2, effect


#: "`<source>` deals `<n>` damage to `<target phrase>`. If a `<creature
#: type>` is dealt damage this way, destroy it." - The Black Arrow's own ETB
#: ("to any target") and Silver Bolt's real, modern/pioneer-legal activated
#: ability ("to target creature"), split by the clause splitter's period
#: into two raw clauses that name each other: the second's "this way" (CR
#: 608.2h) points back at the first's own damage, so it is one CR 608.2c
#: instruction, not two independent ones. `creature_type_vocabulary` is the
#: same closed CR 205.3m word list `_GROUP_NON_SUBTYPE_RE`'s own subtype
#: filter already validates against, read here off the *result* `Game.
#: deal_damage` reports (CR 615.6: prevented damage was never "dealt this
#: way"), not merely off whether the creature carries the type before
#: damage is even assigned.
_DAMAGE_ANY_TARGET_RE = re.compile(
    r"^(?:it |this [a-z]+ )?deals (?P<n>\d+) damage to "
    r"(?P<phrase>any (?:other )?target|[^.]*?\btargets?\b[^.]*?)\.?$",
    re.IGNORECASE,
)


_DESTROY_IF_TYPE_DEALT_DAMAGE_THIS_WAY_RE = re.compile(
    r"^if an? (?P<quality>[a-z]+) is dealt damage this way, destroy it\.?$", re.IGNORECASE
)


def _merge_damage_any_target_then_destroy_if_type_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_DAMAGE_ANY_TARGET_RE` + `_DESTROY_IF_TYPE_DEALT_DAMAGE_THIS_WAY_RE`,
    read as one CR 608.2c instruction; see the banner above."""
    if index + 1 >= len(clauses):
        return None
    first_match = _DAMAGE_ANY_TARGET_RE.fullmatch(clauses[index].strip())
    if first_match is None:
        return None
    second_match = _DESTROY_IF_TYPE_DEALT_DAMAGE_THIS_WAY_RE.fullmatch(clauses[index + 1].strip())
    if second_match is None:
        return None
    quality = second_match.group("quality")
    if quality.title() not in creature_type_vocabulary():
        return None
    creature_type = quality.lower()
    amount = int(first_match.group("n"))
    if amount <= 0:
        return None
    phrase = first_match.group("phrase")
    if not _targets_understood(phrase, allow_player_targets=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object
            if isinstance(stack_object, CardState)
            else stack_object.source_or_last_known(game)  # type: ignore[union-attr]
        )
        for target in game.resolve_targets(stack_object):
            dealt = game.deal_damage(target, amount, source=source)
            if dealt <= 0 or not isinstance(target, CardState):
                continue
            if target.zone is not Zone.BATTLEFIELD:
                continue
            characteristics = game.characteristics_of(target)
            if characteristics is not None and creature_type in {
                subtype.lower() for subtype in characteristics.subtypes
            }:
                game.destroy(target)

    return 2, effect


#: "`<damage sentence>`. If `<a quality>` is dealt damage this way, `<effect>`."
#: (Provoke the Trolls, Redcap Melee, Play with Fire, Burn from Within.) The
#: leading text is read by the ordinary spell dispatcher and run first (CR
#: 608.2c); the branch then acts on exactly what that damage reached, read off
#: `Game.damage_dealt_this_turn` by source (CR 120.1) - damage that was
#: prevented was never dealt (CR 615.6) and an illegal target means no damage
#: at all (CR 608.2b). The quality is read generically: "player", "opponent",
#: or any counted permanent phrase `_permanent_quality` reads ("creature",
#: "nonred permanent", "planeswalker"), alternatives joined by "or"; a
#: permanent's colour and types are read as it is, off its computed
#: characteristics (CR 105.2, CR 613.5). Sentences after the branch that name
#: the same referent ("If that creature would die this turn, exile it
#: instead.") are read as more instructions on it.
_IF_QUALITY_DEALT_DAMAGE_THIS_WAY_RE = re.compile(
    r"^if (?:an? )?(?P<quality>[^,]+?) is dealt damage this way, (?P<effect>.+)$",
    re.IGNORECASE | re.DOTALL,
)

#: (game, stack object, permanents that matched) -> None
_ThisWayConsequence = Callable[["Game", "StackObject", list[CardState]], None]


def _dealt_quality_test(
    quality: str,
) -> tuple[Callable[["Game", str, str], bool], Callable[[object], bool] | None] | None:
    """`quality` as (does a player qualify, does a permanent's characteristics
    qualify), or `None` when any alternative is a word this does not read."""
    from ...models.game._conditions import _permanent_quality

    player_tests: list[Callable[[Game, str, str], bool]] = []
    permanent_tests: list[Callable[[object], bool]] = []
    for alternative in re.split(r"\s+and/or\s+|\s+or\s+", quality.strip().lower()):
        if alternative == "player":
            player_tests.append(lambda _game, _controller, _player: True)
        elif alternative == "opponent":
            player_tests.append(lambda _game, controller, player: player != controller)
        else:
            test = _permanent_quality(alternative)
            if test is None:
                return None
            permanent_tests.append(test)
    return (
        lambda game, controller, player: any(
            test(game, controller, player) for test in player_tests
        ),
        (lambda chars: any(test(chars) for test in permanent_tests)) if permanent_tests else None,
    )


def _read_this_way_consequence(text: str) -> tuple[bool, _ThisWayConsequence] | None:
    """One instruction of a "dealt damage this way" branch as (acts on the
    permanents that matched, the instruction), or `None` when it is not
    readable. An instruction naming "it"/"that creature" runs once per
    matching permanent through the referent readers; any other instruction
    (a player's own - "you sacrifice a land", "scry 1") runs once when
    anything matched. A branch that names a target is not this shape."""
    from .removal import _parse_bare_sacrifice_of_choice_clause
    from .text import _OBJECT_ANAPHOR_RE, _parse_referent_object_clause

    clean = text.strip().rstrip(".").strip()
    if not clean or re.search(r"\btarget\b", clean, re.IGNORECASE):
        return None
    if _OBJECT_ANAPHOR_RE.search(clean):
        referent = _parse_referent_object_clause(clean)
        if referent is None:
            return None
        return True, lambda game, stack_object, matched: referent(game, matched, stack_object)
    clauses = _parse_mixed_clauses(clean, for_spell=True)
    if clauses is not None:

        def run_clauses(
            game: "Game", stack_object: "StackObject", matched: list[CardState]
        ) -> None:
            for clause in clauses:
                clause(game, stack_object)

        return False, run_clauses
    sacrifice = _parse_bare_sacrifice_of_choice_clause(re.sub(r"^you ", "", clean, flags=re.I))
    if sacrifice is None or not re.match(r"you ", clean, re.IGNORECASE):
        return None

    def run_sacrifice(game: "Game", stack_object: "StackObject", matched: list[CardState]) -> None:
        source = stack_object if isinstance(stack_object, CardState) else None
        if source is None:
            return
        sacrifice(game, game.controller_of(source), source.name, source_id_of(source))

    return False, run_sacrifice


@SPELL_TEXT.rung("s18")
def _parse_if_quality_dealt_damage_this_way_spell(effect_text: str) -> Effect | None:
    """`_IF_QUALITY_DEALT_DAMAGE_THIS_WAY_RE`'s shape; see the banner above."""
    if "dealt damage this way" not in effect_text.lower():  # cheap literal gate
        return None
    sentences = _plain_resolution_sentences(
        " ".join(_strip_non_effect_preamble(effect_text).split())
    )
    index = next(
        (
            position
            for position, sentence in enumerate(sentences)
            if position > 0 and _IF_QUALITY_DEALT_DAMAGE_THIS_WAY_RE.fullmatch(sentence.strip())
        ),
        None,
    )
    if index is None:
        return None
    branch = _IF_QUALITY_DEALT_DAMAGE_THIS_WAY_RE.fullmatch(sentences[index].strip())
    assert branch is not None
    quality = _dealt_quality_test(branch.group("quality"))
    if quality is None:
        return None
    player_test, permanent_test = quality
    consequences = [_read_this_way_consequence(branch.group("effect"))]
    consequences += [_read_this_way_consequence(rest) for rest in sentences[index + 1 :]]
    if any(consequence is None for consequence in consequences):
        return None
    if any(not on_matched for on_matched, _ in consequences[1:]):  # type: ignore[misc]
        return None
    rest = _spell_effect_or_notice(" ".join(sentences[:index]))
    if rest is None or _is_notice_only(rest):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        start = len(game.damage_dealt_this_turn)
        rest(game, spell)
        matched: list[CardState] = []
        player_matched = False
        for record in game.damage_dealt_this_turn[start:]:
            if record.source_id != spell.id or record.amount <= 0:
                continue
            if record.recipient_id is not None:
                found = game.find_by_id(record.recipient_id)
                if (
                    isinstance(found, CardState)
                    and found not in matched
                    and permanent_test is not None
                    and permanent_test(game.characteristics_of(found))
                ):
                    matched.append(found)
            elif record.recipient_player is not None and player_test(
                game, controller, record.recipient_player
            ):
                player_matched = True
        if not matched and not player_matched:
            return
        for on_matched, consequence in consequences:  # type: ignore[misc]
            if on_matched and not matched:
                continue
            consequence(game, spell, matched)

    return effect


#: "Add `<mana>`. Spend this mana only to `<restriction>`." - CR 106.6's own
#: restriction sentence, printed as its own clause right after the
#: production it tags, on a spell or a resolving (non-mana) ability: one
#: CR 608.2c instruction, split by the clause splitter's period the same way
#: the damage-then-destroy pair above is. The production is any shape
#: `mana.read_add_mana_instruction` reads - Desolation of Smaug's "Add four
#: mana in any combination of colors.", Narset of the Ancient Way's loyalty
#: "Add {U}, {R}, or {W}." (CR 605.1a: a loyalty ability is never a mana
#: ability, so its mana arrives as it resolves), "Add one mana of any
#: color.", a literal "Add {U}." behind another instruction. The restriction
#: is `machines/cost.spend_restriction`, the exact CR 106.6 reader every
#: mana ability's own trailing sentence already goes through; one it cannot
#: read fails the whole instruction closed. It is read again against the
#: source as the instruction resolves, so "the chosen type" names the
#: source's own recorded choice (CR 614.12a), as a mana ability's does.
def _merge_add_any_combination_mana_with_restriction_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`read_add_mana_instruction` + `machines.cost.spend_restriction`, read
    as one CR 608.2c instruction; see the banner above."""
    if index + 1 >= len(clauses):
        return None
    add = read_add_mana_instruction(clauses[index])
    if add is None:
        return None
    sentence = clauses[index + 1].strip()
    if not sentence.endswith("."):
        sentence = sentence + "."
    restriction = spend_restriction(sentence)
    if restriction is None or not restriction.understood:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else stack_object
        )
        add(game, stack_object, spend_restriction(sentence, source))

    return 2, effect


def _merge_split_damage_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "`<source>` deals `<n>` damage to `<phrase1>` and `<m>` damage to
    `<phrase2>`." - one CR 608.2c instruction, cut into two clauses by
    `_CLAUSE_SEPARATOR`'s bare "and" split, which leaves the second half
    with no subject of its own (`_BARE_DAMAGE_CONTINUATION_RE`).

    CR 601.2c already keeps `phrase1`'s and `phrase2`'s own targets as two
    separate target requirements at announcement (`machines/targeting.py`'s
    own per-clause target reading handles that; this function is
    resolution-only and never re-derives an announcement). When `<n>` and
    `<m>` are the same amount, which requirement a resolved target came from
    does not matter - `game.resolve_targets(stack_object)` (CR 608.2b's own
    re-check) is enough, every one of them taking the one shared amount.

    When they differ (Hungry Flames: 3 to the creature, 2 to the player),
    *which* target came from which requirement matters, and `stack_object.
    targets` alone does not say - CR 601.2c lets the same word "target"
    appear more than once and each instance keep its own chosen object,  but
    nothing tags a stored `TargetRef` with which instance it answered.
    `first_match.group("phrase")`/`second_match.group("phrase")` are read
    back through `profile_for_text` into the same two `TargetRequirement`s
    `targeting.py` built at announcement, and each resolved target is
    classified against them with `TargetRequirement.rejects` (CR 601.2c/CR
    115's own eligibility rules restated, not reimplemented) rather than
    assumed by position - correct whichever order the targets were chosen or
    stored in. `AbilityOnStack.target_amounts`/`CardState.target_amounts`
    record the result, one entry per `targets` entry, mirroring `division`'s
    own resolution-time-read, announcement-shaped field.
    """
    if index + 1 >= len(clauses):
        return None
    first = clauses[index]
    second = clauses[index + 1]
    first_match = _DAMAGE_TARGET_RE.fullmatch(first)
    if first_match is None or first_match.group("each") or first_match.group("where_x"):
        return None
    if _DAMAGE_TARGET_RE.fullmatch(second) is not None:
        return None
    second_match = _BARE_DAMAGE_CONTINUATION_RE.fullmatch(second)
    if second_match is None:
        return None
    first_amount = parse_count(first_match.group("n"))
    second_amount = parse_count(second_match.group("n"))
    if first_amount is None or second_amount is None:
        return None
    first_phrase = first_match.group("phrase")
    second_phrase = second_match.group("phrase")
    if not _targets_understood(first_phrase, count_agnostic=True, allow_player_targets=True):
        return None
    if not _targets_understood(second_phrase, count_agnostic=True, allow_player_targets=True):
        return None
    first_requirement = profile_for_text(first_phrase).requirements[0]
    second_requirement = profile_for_text(second_phrase).requirements[0]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object if for_spell else stack_object.source(game)  # type: ignore[union-attr]
        )
        caster = game.controller_of(stack_object).username
        source_id = source.id
        resolved = [
            game.legal_target(stack_object, reference) for reference in stack_object.targets
        ]
        amounts: list[int] = [0] * len(resolved)
        ambiguous: list[int] = []
        for index, target in enumerate(resolved):
            if target is None:
                amounts[index] = 0
                continue
            # Classified by which requirement's own restrictions the
            # resolved target actually satisfies (CR 601.2c), not by
            # position - `first_requirement` tried first only because it is
            # the one printed first, exactly the left-to-right order
            # `TargetingProfile._fill_slots` already searches announced
            # requirements in.
            first_ok = first_requirement.rejects(target, caster, game, source_id) is None
            second_ok = second_requirement.rejects(target, caster, game, source_id) is None
            if first_ok and not second_ok:
                amounts[index] = first_amount
            elif second_ok and not first_ok:
                amounts[index] = second_amount
            elif first_ok and second_ok:
                # ecl-T8: both requirements are the identical bare CR 115.4
                # shape (Boulder Dash's own "any target and any other
                # target") - nothing about the object itself says which
                # instance of the word "target" it answers, so this is left
                # for the position pass below to settle by announcement
                # order instead (CR 601.2c: the instructions, and the
                # targets answering them, follow the order printed).
                ambiguous.append(index)
            else:
                # Neither requirement still accepts this target (a
                # continuous effect changed its qualities after it was
                # legally chosen) - CR 608.2b already treats that as an
                # illegal target for the parts of the effect it cannot
                # satisfy, so no amount is paid rather than guessed.
                amounts[index] = 0
        if ambiguous:
            first_used = sum(
                1
                for index, amount in enumerate(amounts)
                if index not in ambiguous and amount == first_amount
            )
            first_left = max(first_requirement.count - first_used, 0)
            for index in ambiguous:
                if first_left > 0:
                    amounts[index] = first_amount
                    first_left -= 1
                else:
                    amounts[index] = second_amount
        if second_requirement.controller is ControllerRestriction.PRIOR_TARGET_PLAYER:
            # CR 608.2b: "that player or that planeswalker's controller" is
            # rechecked against the first target as it is now - a creature
            # that changed control since is illegal and is dealt nothing.
            pair = TargetingProfile(requirements=(first_requirement, second_requirement))
            anchor = pair.prior_target_player(
                second_requirement,
                [game.resolve_target(reference) for reference in stack_object.targets],
                caster,
                game,
                source_id,
            )
            for position, reference in enumerate(stack_object.targets):
                target = game.legal_target(stack_object, reference)
                if (
                    anchor is not None
                    and isinstance(target, CardState)
                    and amounts[position] == second_amount
                    and first_requirement.rejects(target, caster, game, source_id) is not None
                    and game.controller_of(target).username != anchor
                ):
                    amounts[position] = 0
        stack_object.target_amounts = amounts
        for reference, amount in zip(stack_object.targets, amounts, strict=True):
            if amount <= 0:
                continue
            target = game.legal_target(stack_object, reference)
            if target is not None:
                game.deal_damage(target, amount, source=source)

    return 2, effect


def _merge_prevent_damage_from_target_clauses(
    clauses: list[str], index: int
) -> tuple[int, TargetedClause] | None:
    """ "The next time target creature would deal damage this turn, prevent
    that damage." (Awe Strike), plus its optional CR 615.5 rider on the
    sentence right after it - "You gain life equal to the damage prevented
    this way."

    Not `for_spell`-gated: `_prevent_next_damage_from_target`'s effect reads
    the resolving object generically through `Game.resolve_card_targets`/
    `Game.controller_of`, the same as `create_continuous_effect_of_ability`
    does, so there is no reason to refuse an ability printing this shape.

    Returns how many clauses starting at `index` belong to this one
    instruction, and the effect to run for both, or `None` if `index` is not
    the start of this shape at all.
    """
    match = _PREVENT_NEXT_TIME_TARGET_WOULD_DEAL_DAMAGE_RE.fullmatch(clauses[index])
    if match is None:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    gains_life = index + 1 < len(clauses) and bool(
        _GAIN_LIFE_EQUAL_TO_DAMAGE_PREVENTED_RE.fullmatch(clauses[index + 1])
    )
    consumed = 2 if gains_life else 1
    return consumed, _prevent_next_damage_from_target(gains_life=gains_life)


#: Ral, Monsoon Mage's own front-face trigger, as four clauses (CR 705.1's
#: own coin flip, CR 118.12's "you may ... If you do ..."):
#: "flip a coin. If you lose the flip, Ral deals 1 damage to you. If you win
#: the flip, you may exile Ral. If you do, return him to the battlefield
#: transformed under his owner's control." Read whole, ability-only, and not
#: pinned to this one printing's amount: any future card sharing this exact
#: four-sentence template - flip, a lose consequence naming a flat damage
#: amount, a win consequence offering a self-exile, and the transform-return -
#: reads the same way, whichever name and pronoun it prints.
_FLIP_A_COIN_RE = re.compile(r"^flip a coin\.?$", re.IGNORECASE)
_IF_YOU_LOSE_THE_FLIP_SELF_DAMAGE_RE = re.compile(
    r"^if you lose the flip, (?P<name>.+?) deals (?P<amount>\d+) damage to you\.?$",
    re.IGNORECASE,
)
_IF_YOU_WIN_THE_FLIP_MAY_EXILE_SELF_RE = re.compile(
    r"^if you win the flip, you may exile (?P<name>.+?)\.?$", re.IGNORECASE
)
_IF_YOU_DO_RETURN_TRANSFORMED_RE = re.compile(
    r"^if you do, return (?:it|him|her|them) to the battlefield"
    r"(?P<tapped> tapped)?(?P<transformed> transformed)?"
    r" under (?:its|his|her|their) owner'?s control\.?$",
    re.IGNORECASE,
)


def _merge_flip_coin_damage_or_exile_transform_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Ral, Monsoon Mage's whole front-face trigger as one CR 608.2c
    instruction - the second, third and fourth sentences are meaningless
    without knowing which side of the flip they answer for and, for the
    fourth, without the third's own accepted "you may", so all four have to
    resolve together or not at all (this project's paragraph-atomic rule).

    Ability-only: no spell in the pool prints this shape. `Game.flip_coin`
    is CR 705.1's own primitive - see its docstring for the reproducibility
    convention it shares with `Game.shuffle`.
    """
    if for_spell or index + 3 >= len(clauses):
        return None
    if _FLIP_A_COIN_RE.fullmatch(clauses[index].strip()) is None:
        return None
    lose_match = _IF_YOU_LOSE_THE_FLIP_SELF_DAMAGE_RE.fullmatch(clauses[index + 1].strip())
    if lose_match is None:
        return None
    win_match = _IF_YOU_WIN_THE_FLIP_MAY_EXILE_SELF_RE.fullmatch(clauses[index + 2].strip())
    if win_match is None:
        return None
    do_match = _IF_YOU_DO_RETURN_TRANSFORMED_RE.fullmatch(clauses[index + 3].strip())
    if do_match is None:
        return None
    lose_amount = int(lose_match.group("amount"))
    tapped = do_match.group("tapped") is not None
    transformed = do_match.group("transformed") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = ability.controller
        if game.flip_coin(controller):
            decision = Decision(
                kind=DecisionKind.MAY,
                player=controller,
                prompt=f"exile {source.name}, then return it to the battlefield"
                + (" transformed" if transformed else ""),
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=True,
            )
            if not game.ask(decision):
                return
            exiled = game.exile_permanent(source)
            if exiled.zone is not Zone.EXILE:
                return  # CR 111.8: a token refused the move.
            owner = exiled.owner or controller
            game.put_onto_battlefield(exiled, owner, tapped=tapped, transformed=transformed)
        else:
            game.deal_damage(game.player(controller), lose_amount, source=source)

    return 4, effect


#: "Flip a coin. If you lose the flip, `<consequence>`." - CR 705.1/705.2's
#: coin flip with only a losing branch printed (nothing at all happens on a
#: win, unlike Ral, Monsoon Mage's own four-clause shape above, which always
#: prints both). Goblin Kaboomist's own upkeep trigger: "... create a
#: colorless artifact token named Land Mine with '...'. Then flip a coin. If
#: you lose the flip, this creature deals 2 damage to itself." `<consequence>`
#: is read through the same per-clause dispatcher (`parse_mixed_effect`)
#: every other ability's own effect goes through, not a hand-written shape
#: fitted to Goblin Kaboomist's own self-damage - a future card pairing
#: "flip a coin. If you lose the flip, ..." with any other clause this file
#: already reads gets it for free.
_IF_YOU_LOSE_THE_FLIP_RE = re.compile(
    r"^if you lose the flip, (?P<consequence>.+)$", re.IGNORECASE | re.DOTALL
)


def _merge_flip_coin_lose_consequence_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_FLIP_A_COIN_RE` then `_IF_YOU_LOSE_THE_FLIP_RE`, as one CR 608.2c
    instruction pair - the second sentence means nothing without knowing
    which side of the flip it answers for, the same reason Ral, Monsoon
    Mage's own four-clause merge above reads all of its sentences together.

    Ability-only: no spell in the pool prints this shape, the same as Ral's.
    Tried after the four-clause merger above, so a card that prints both a
    losing *and* a winning branch (Ral's own shape) is still read by that
    more specific merger first; this one only ever sees the pair when there
    is no third "if you win the flip" sentence to go with it.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    if _FLIP_A_COIN_RE.fullmatch(clauses[index].strip()) is None:
        return None
    match = _IF_YOU_LOSE_THE_FLIP_RE.fullmatch(clauses[index + 1].strip())
    if match is None:
        return None
    consequence_text = match.group("consequence").strip().rstrip(".") + "."
    consequence = parse_mixed_effect(consequence_text)
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if not game.flip_coin(ability.controller):
            consequence(game, ability)  # type: ignore[arg-type]

    return 2, effect


_SELF_PUMP_DURATION_FIRST_NO_TAIL_RE = re.compile(
    r"^until end of turn, this creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)$",
    re.IGNORECASE,
)
_GROUP_KEYWORD_GRANT_NO_DURATION_RE = re.compile(
    r"^creatures you control gain (?P<keywords>[a-z][a-z, ]*?)$", re.IGNORECASE
)


def _merge_self_pump_and_group_keyword_grant_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, AbilityEffect] | None:
    """`_SELF_PUMP_DURATION_FIRST_NO_TAIL_RE` + `_GROUP_KEYWORD_GRANT_NO_
    DURATION_RE`, read as one CR 608.2c instruction; see the banner above."""
    if for_spell or index + 1 >= len(clauses):
        return None
    first_match = _SELF_PUMP_DURATION_FIRST_NO_TAIL_RE.fullmatch(clauses[index].strip())
    if first_match is None:
        return None
    second_match = _GROUP_KEYWORD_GRANT_NO_DURATION_RE.fullmatch(clauses[index + 1].strip())
    if second_match is None:
        return None
    power = int(first_match.group("power"))
    toughness = int(first_match.group("toughness"))
    keywords = _split_and_validate_keywords(second_match.group("keywords").strip())
    if keywords is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name}: gets {power:+d}/{toughness:+d} until end of turn",
                layer=Layer.POWER_TOUGHNESS,
                sublayer=Sublayer.MODIFY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=ability.source_id,
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=modify_power_toughness(power, toughness),
            )
        )
        controller = ability.controller
        board = game.computed_board()
        group = [
            permanent
            for permanent in game.battlefield
            if board.of(permanent).is_creature
            and game.controller_of(permanent).username == controller
        ]
        for creature in group:
            for keyword in keywords:
                store.add(
                    ContinuousEffect(
                        description=(
                            f"{ability.source_name}: creatures you control gain "
                            f"{keyword} until end of turn"
                        ),
                        layer=Layer.ABILITY,
                        timestamp=store.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        source_id=ability.source_id,
                        selector=only_this_incarnation(creature, creature.zone_change_stamp),
                        modification=grant_ability(keyword),
                    )
                )

    return 2, effect


def _merge_damage_each_filtered_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Undo the generic "and" clause split for
    `_parse_damage_each_filtered_clause`'s own sentence.

    End the Festivities prints one CR 608.2c instruction - "deals 1 damage to
    each opponent and each creature and planeswalker they control" - which
    `_prepare_effect_clauses` cuts into three on its own "and"s. Rejoining is
    the only way to see that "they control" belongs to the opponents named at
    the front, and getting it wrong is not a small error: the first fragment
    on its own reads as plain "damage to each opponent" and would silently
    drop the board half of the card.

    Longest match wins: the fragments are rejoined one at a time and the
    longest recombination that `_parse_damage_each_filtered_clause` reads is
    the one taken, so a genuinely separate following instruction is never
    swallowed (it will not parse as part of this sentence).
    """
    head = clauses[index].strip()
    if _DAMAGE_EACH_FILTERED_RE.fullmatch(head) is None:
        return None  # this clause is not a damage sentence; nothing to extend
    combined = head.rstrip(".")
    best: tuple[int, TargetedClause] | None = None
    head_effect = _parse_damage_each_filtered_clause(combined)
    if head_effect is not None:
        # The head alone already reads - as *some* effect, not necessarily
        # the right one. Fulminous Forte's own "deals 1 damage to each
        # creature" reads fine standing alone (an unfiltered type group),
        # but the fragment after it ("planeswalker your opponents control")
        # narrows what the sentence actually said - kept as a fallback, not
        # returned immediately, so the loop below still gets to look for a
        # longer, more specific reading before settling for this one.
        best = (1, head_effect)
    for consumed in range(1, len(clauses) - index):
        fragment = clauses[index + consumed].strip().rstrip(".")
        # Only a *fragment* of the same sentence may be reattached. A clause
        # that is a damage sentence in its own right is a separate CR 608.2c
        # instruction, and swallowing it would silently drop it.
        if _DAMAGE_EACH_FILTERED_RE.fullmatch(fragment) is not None:
            break
        combined = f"{combined} and {fragment}"
        effect = _parse_damage_each_filtered_clause(combined)
        if effect is not None:
            best = (consumed + 1, effect)
    return best


#: A bare "each `<type>`[, each `<type>`]*" continuation, split off from
#: `_DAMAGE_EACH_GROUP_RE`'s own sentence by the generic "and" clause
#: splitter - "deals 3 damage to each creature" / "each planeswalker" is
#: exactly this shape once cut in two. The optional `where_x_pattern` tail is
#: for Calamitous Cave-In's own split: its ", where X is ..." definition
#: rides on the *last* "each `<type>`" fragment ("each planeswalker, where X
#: is the number of Caves you control plus the number of Cave cards in your
#: graveyard"), since nothing in `_CLAUSE_SEPARATOR` breaks on a plain comma.
_BARE_EACH_GROUP_RE = re.compile(rf"^each ([a-z]+){where_x_pattern()}$", re.IGNORECASE)


def _merge_damage_each_group_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Reattach `_DAMAGE_EACH_GROUP_RE`'s own sentence to a bare "each
    `<type>`" fragment the generic "and" split cut off it - Brotherhood's End's
    "deals 3 damage to each creature and each planeswalker" is one CR 608.2c
    instruction, not "deals ... to each creature" followed by a second,
    unreadable "each planeswalker" clause. Consumes clause `index` plus every
    immediately following bare "each `<type>`" clause, then hands the
    reassembled sentence to `_parse_damage_each_group_clause`.

    Deliberately clause-list-scoped rather than tried on the whole, unsplit
    text: a card with an *earlier*, unrelated clause before this one
    (Extinguisher Battleship's "destroy target noncreature permanent. Then
    this Spacecraft deals 4 damage to each creature.") must not have that
    earlier clause swallowed by a greedy `.*` match against the whole text.
    """
    first = clauses[index].strip()
    if not _DAMAGE_EACH_GROUP_RE.fullmatch(first) or _BARE_EACH_GROUP_RE.fullmatch(first):
        return None
    consumed = 1
    combined = first.rstrip(".")
    while index + consumed < len(clauses) and _BARE_EACH_GROUP_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        combined = f"{combined} and {clauses[index + consumed].strip()}"
        consumed += 1
    if consumed == 1:
        return None  # nothing to reattach; the ordinary single-clause path handles it
    effect = _parse_damage_each_group_clause(combined)
    if effect is None:
        return None
    return consumed, effect


# --------------------------------------------------------------------------
# "Each player <does something>[, then <does something else>]" - the symmetric
# fan-out.
#
# CR 101.4 is the order: "If multiple players would make choices and/or take
# actions at the same time, the active player ... makes any choices required,
# then the next player in turn order ... and so on." CR 608.2e is why the
# *steps* are walked outermost and the players innermost rather than running
# one player's whole sentence before the next player starts: "Some spells and
# abilities have multiple steps or actions, denoted by separate sentences or
# clauses, that involve multiple players. In these cases, the choices for the
# first action are made in APNAP order" - so every player draws, and only then
# does every player discard. Burning Inquiry is the card where the difference
# is visible: a player who discarded first would be discarding from a hand the
# other player's draw had not yet been seen against.
# --------------------------------------------------------------------------

#: "Each player <rest>" - the head of the sentence, whatever `<rest>` is.
_EACH_OPPONENT_STEP_RE = re.compile(
    rf"^(?:loses (?:{COUNT}) life unless |discards their hand$)", re.IGNORECASE
)
_EACH_PLAYER_HEAD_RE = re.compile(r"^each (?P<who>player|opponent) (?P<rest>.+)$", re.IGNORECASE)

#: "discards N cards at random" - Burning Inquiry's own discard, which is not
#: `_DISCARD_A_CARD_RE`'s default choice at all: CR 701.9b, "By default,
#: effects that cause a player to discard a card allow the affected player to
#: choose which card to discard. Some effects, however, require a random
#: discard", so nobody is asked anything.
_DISCARD_AT_RANDOM_RE = re.compile(
    rf"^discards? (?:a card|(?P<n>{COUNT}) cards?) at random$", re.IGNORECASE
)

#: "Shuffle your hand and graveyard into your library, then draw seven cards." (Weftwalking's
#: enters trigger) - the controller-only twin of Day's Undoing's "each player shuffles ...".
#: CR 701.24a: the cards go to their owners' libraries, which are shuffled; CR 121.2 draws.
_SHUFFLE_OWN_HAND_GRAVEYARD_THEN_DRAW_RE = re.compile(
    rf"^shuffle your hand and graveyard into your library, then draw (?P<count>{COUNT}) cards?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s1")
def _parse_shuffle_own_hand_graveyard_then_draw_text(text: str) -> "AbilityEffect | None":
    """`_SHUFFLE_OWN_HAND_GRAVEYARD_THEN_DRAW_RE`'s shape, or `None`."""
    match = _SHUFFLE_OWN_HAND_GRAVEYARD_THEN_DRAW_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    count = parse_count(match.group("count"))
    if count is None:
        return None

    def effect(game: Any, ability: Any) -> None:
        player = game.player(game.controller_of(ability).username)
        for card_state in list(player.hand) + list(player.graveyard):
            player.move(card_state, Zone.LIBRARY)
        game.shuffle_library(player)
        game.draw_cards(player.username, count)

    return effect


#: "shuffles their hand and graveyard into their library" - Day's Undoing.
_SHUFFLE_HAND_AND_GRAVEYARD_RE = re.compile(
    r"^shuffles? (?:their|his or her) hand and graveyard into (?:their|his or her) library$",
    re.IGNORECASE,
)

#: "shuffles their graveyard into their library" - Mnemonic Nexus's "Each
#: player ..." step. CR 701.24a; each card goes into its owner's library.
_SHUFFLE_GRAVEYARD_RE = re.compile(
    r"^shuffles? (?:their|his or her) graveyard into (?:their|his or her) library$",
    re.IGNORECASE,
)

#: "shuffles their hand, graveyard, and all permanents they own into their
#: library" - Sway of the Stars. CR 701.24a's shuffle after CR 400.3's owner
#: rule: each card goes to its owner's library, so "permanents they own" is
#: every battlefield object whose owner is this player, token or not (a token
#: ceases to exist, CR 111.8).
_SHUFFLE_HAND_GRAVEYARD_PERMANENTS_RE = re.compile(
    r"^shuffles? (?:their|his or her) hand, graveyard, and all permanents they own "
    r"into (?:their|his or her) library$",
    re.IGNORECASE,
)

#: "discards all the cards in their hand" / "discards their hand" (Awaken
#: the Erstwhile, Dark Deal) - CR 701.9a, every card, no choice.
_DISCARD_WHOLE_HAND_RE = re.compile(
    r"^discards? (?:all the cards in |all cards in )?(?:their|his or her|your) hand$",
    re.IGNORECASE,
)

#: "creates that many 2/2 black Zombie creature tokens" / "creates N ...
#: tokens" - one player's own token creation within an "each player ..."
#: sentence (Awaken the Erstwhile).
_PLAYER_CREATES_TOKENS_RE = re.compile(
    rf"^creates? (?:(?P<that_many>that many)|(?P<n>{COUNT})) (?P<desc>.+?) \btokens?\b"
    r"(?:\s+with\s+(?P<tail>.+))?$",
    re.IGNORECASE,
)

#: A bare "shuffles" left over at the end of a fan-out sentence - Field of
#: Ruin's "..., then shuffles". Named distinctly from `_rejoin_search_
#: clauses`'s own `_BARE_SHUFFLE_RE` above (a different clause, read in a
#: different context - a search's own trailing "then shuffle" rather than an
#: each-player fan-out's own step) after the two collided under the same
#: name and the second silently shadowed the first at module load.
_BARE_SHUFFLES_RE = re.compile(r"^shuffles?$", re.IGNORECASE)

#: "exiles the top card of their library face down" - Pyxis of Pandemonium's
#: first activated ability, run for every player rather than for the
#: activating one, which is why it is a step of the "each player ..." sentence
#: rather than a controller-scoped clause.
#:
#: "Face down" is the load-bearing half: CR 406.3 keeps such a card from being
#: examined, and CR 406.3a gives it no characteristics at all, which
#: CR 202.3a then reads as a mana value of 0. The phrase is optional in the
#: pattern because the plain face-up exile is the same instruction otherwise.
_EACH_PLAYER_EXILES_TOP_RE = re.compile(
    rf"^exiles? the top (?:card|(?P<n>{COUNT}) cards) of (?:their|his or her) library"
    r"(?P<face_down> face down)?$",
    re.IGNORECASE,
)

#: "[may ]search(es) their library for `<quantity>` <quality> cards, [reveal
#: them,] put(s) it/them onto the battlefield/into their hand" - Field of
#: Ruin's own mandatory single basic-land fetch, run for every player rather
#: than for the resolving ability's controller (which is why it cannot go
#: through `_SEARCH_AND_PUT_RE`'s controller-scoped clause builder), and Weird
#: Harvest's "each player **may** search ... for **up to X** creature cards,
#: reveal those cards, put them **into their hand**" - one shape with a wider
#: printed count, a per-player "may", a reveal, and the other destination, not
#: a different instruction. Weird Harvest's own X is CR 107.3a's cast-
#: announced kind: `{COUNT}` never matches a bare "X" (see `_SEARCH_AND_PUT_
#: RE`'s own comment on why), so the unsubstituted first pass fails to match
#: here exactly as it does there, and `effect_for`'s substitution retry is
#: what actually makes it readable.
_EACH_PLAYER_SEARCH_RE = re.compile(
    rf"^(?P<subject>may )?search(?:es)? (?:your|their|his or her) library for "
    rf"(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<that_many>that many)) (?P<quality>.+?) cards?"
    r"(?P<reveal>, reveal (?:them|it|those cards|that card))?"
    r", puts? (?:it|them|that card|those cards) "
    r"(?P<dest>onto the battlefield(?P<tapped> tapped)?|into (?:your|their|his or her) hand)$",
    re.IGNORECASE,
)


#: A third-person life clause - "loses 1 life", "gains 3 life".
_THIRD_PERSON_LIFE_RE = re.compile(rf"^(?:loses|gains) (?:{COUNT}) life$", re.IGNORECASE)

#: "loses N life unless they <action>" - the punisher step of an "each player
#: ..." sentence (Tomb of Annihilation's Veils of Fear: "Each player loses 2
#: life unless they discard a card."; Sandfall Cell: "... unless they sacrifice
#: a creature, artifact, or land of their choice.").
_LOSES_LIFE_UNLESS_RE = re.compile(
    rf"^loses (?P<n>{COUNT}) life unless (?:they|he or she) "
    r"(?P<action>discards? a card|sacrifices? (?:an? )?(?P<description>.+?)"
    r"(?: of their choice)?)$",
    re.IGNORECASE,
)


def _parse_each_player_step(text: str) -> ClauseEffect | None:
    """One step of an "each player ..." sentence, as something to run for a
    single player - or `None` if this engine cannot read it, which fails the
    whole sentence closed rather than running the readable half of a
    symmetric effect (a half-run Burning Inquiry is strictly worse than an
    unread one: it would empty a hand and refill nobody's).
    """
    clause = text.strip().rstrip(".")
    if not clause:
        return None

    if match := _DISCARD_AT_RANDOM_RE.fullmatch(clause):
        amount = parse_count(match.group("n")) if match.group("n") else 1
        return lambda game, player, source, source_id: _discard_at_random(
            game, player, amount, source
        )

    if _SHUFFLE_HAND_AND_GRAVEYARD_RE.fullmatch(clause):

        def shuffle_hand_and_graveyard(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            for card_state in list(player.hand) + list(player.graveyard):
                player.move(card_state, Zone.LIBRARY)
            game.shuffle_library(player)

        return shuffle_hand_and_graveyard

    if _SHUFFLE_GRAVEYARD_RE.fullmatch(clause):

        def shuffle_graveyard(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            game.put_cards_into_library(list(player.graveyard))
            game.shuffle_library(player)

        return shuffle_graveyard

    if _SHUFFLE_HAND_GRAVEYARD_PERMANENTS_RE.fullmatch(clause):

        def shuffle_hand_graveyard_and_permanents(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            owned_permanents = [
                permanent for permanent in game.battlefield if permanent.owner == player.username
            ]
            game.put_cards_into_library(
                list(player.hand) + list(player.graveyard) + owned_permanents
            )
            game.shuffle_library(player)

        return shuffle_hand_graveyard_and_permanents

    if _BARE_SHUFFLES_RE.fullmatch(clause):
        return lambda game, player, source, source_id: game.shuffle_library(player)

    if _DISCARD_WHOLE_HAND_RE.fullmatch(clause):

        def discard_hand(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            # CR 701.9a: every card, so nobody chooses; the count is what a
            # later "that many" of this player reads (CR 608.2c).
            discarded = game.discard_cards(player.username, list(player.hand), source=source)
            game.record_count(len(discarded))

        return discard_hand

    if match := _PLAYER_CREATES_TOKENS_RE.fullmatch(clause):
        definition = _token_definition_from_words(match.group("desc"), match.group("tail"))
        if definition is None:
            return None
        fixed = None if match.group("that_many") else parse_count(match.group("n"))
        if fixed is None and not match.group("that_many"):
            return None

        def create_for_player(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            count = fixed
            if count is None:
                count = _that_many_or_notice(game, clause, source_id=source_id, source_name=source)
            if count:
                # CR 111.2: the player who creates the token owns and controls it.
                create_tokens(game, definition, player.username, count)

        return create_for_player

    if match := _EACH_PLAYER_EXILES_TOP_RE.fullmatch(clause):
        amount = parse_count(match.group("n")) if match.group("n") else 1
        face_down = match.group("face_down") is not None

        def exile_top_of_library(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            for card_state in list(player.library[:amount]):
                moved = game.exile_permanent(card_state)
                if moved is not None and face_down:
                    # CR 406.3: "Cards 'exiled face down' can't be examined by
                    # any player except when instructions allow it", and
                    # CR 406.3a: "A card exiled face down has no
                    # characteristics" - which `CardState.has_no_characteristics`
                    # is what actually enforces, once `face_up` is cleared.
                    moved.face_up = False

        return exile_top_of_library

    if match := _EACH_PLAYER_SEARCH_RE.fullmatch(clause):
        # "that many" is each player's own count (`Game.counting_for`).
        searches_that_many = match.group("that_many") is not None
        printed = None if searches_that_many else parse_count(match.group("n"))
        if printed is None and not searches_that_many:
            return None
        matcher = _quality_matcher(match.group("quality"))
        quality = match.group("quality")
        to_hand = match.group("dest").startswith("into")
        tapped = match.group("tapped") is not None
        reveal = match.group("reveal") is not None
        optional = bool((match.group("subject") or "").strip())

        def search_and_put(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            count = printed
            if count is None:
                count = _that_many_or_notice(game, clause, source_id=source_id, source_name=source)
                if count is None:
                    return
            if optional and not game.may(
                player,
                f"search your library for up to {count} {quality} cards",
                source=source,
                source_id=source_id,
            ):
                return
            found = game.search_library(
                player, matcher, count=count, optional=True, source=source, source_id=source_id
            )
            for state in found:
                if reveal:
                    game.reveal(state, source=source)
                if to_hand:
                    player.add(state, Zone.HAND)
                else:
                    game.put_onto_battlefield(state, player.username, tapped=tapped)

        return search_and_put

    if match := _LOSES_LIFE_UNLESS_RE.fullmatch(clause):
        return _loses_life_unless_step(match)

    plain = parse_clause_effect(clause)
    if plain is None and _THIRD_PERSON_LIFE_RE.fullmatch(clause):
        # "Each player loses 1 life." (Tomb of Annihilation's Trapped Entry):
        # the step's own subject is the player it runs for, so the life
        # clause is the one the controller would read with "you" - `_LOSE_
        # LIFE_RE`/`_GAIN_LIFE_RE` already accept the third-person verb.
        plain = parse_clause_effect(f"you {clause}")
    if plain is not None:
        return plain

    # A chain the sentence splitter left whole because its own joiner is a
    # comma rather than a period: Field of Ruin's "searches ..., puts it onto
    # the battlefield, then shuffles". CR 608.2c runs the parts in the order
    # written; every part must be readable or the whole step is refused.
    parts = [part.strip() for part in re.split(r",\s*then\s+", clause) if part.strip()]
    if len(parts) < 2:
        return None
    chain = [_parse_each_player_step(part) for part in parts]
    if any(part is None for part in chain):
        return None
    ordered = [part for part in chain if part is not None]

    def run_chain(game: "Game", player: Player, source: str, source_id: str | None) -> None:
        for part in ordered:
            part(game, player, source, source_id)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return run_chain


def _merge_each_player_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Each player <step>[, then <step>]*" as one CR 608.2c instruction,
    however many fragments `_prepare_effect_clauses` cut it into.

    The sentence's own subject is printed once and governs every following
    step, so a fragment that lost it ("discards three cards at random",
    "draws seven cards") is not an instruction for the *controller* - reading
    it as one is how a symmetric effect turns into a one-sided one. Fragments
    are therefore taken back one at a time and rejoined until they parse as a
    step; the run stops at the last fragment that completed a step, leaving
    anything after it for the caller (an unread leftover then fails the whole
    ability closed, which is the point).
    """
    head = _EACH_PLAYER_HEAD_RE.fullmatch(clauses[index].strip().rstrip("."))
    if head is None:
        return None
    if head.group("who").lower() == "opponent" and not _EACH_OPPONENT_STEP_RE.match(
        head.group("rest").strip()
    ):
        # "Each opponent" is read here only for the two punisher/hand shapes
        # below; every other "each opponent ..." sentence keeps the readers
        # it always had (Invasion of Amonkhet's "each opponent discards a card
        # and you draw a card" splits at the "and").
        return None

    steps: list[ClauseEffect] = []
    settled: tuple[int, int] | None = None  # (fragments consumed, steps kept)
    pending = head.group("rest").strip()
    position = index + 1
    consumed = 1
    while True:
        step = _parse_each_player_step(pending)
        if step is not None:
            steps.append(step)
            pending = ""
            settled = (consumed, len(steps))
        if position >= len(clauses):
            break
        fragment = clauses[position].strip().rstrip(".")
        if _EACH_PLAYER_HEAD_RE.fullmatch(fragment):
            break  # a second "each player" sentence of its own
        pending = f"{pending} and {fragment}" if pending else fragment
        position += 1
        consumed += 1

    if settled is None:
        return None
    kept_fragments, kept_steps = settled
    ordered = steps[:kept_steps]
    opponents_only = head.group("who").lower() == "opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        controller = game.controller_of(stack_object).username
        # `_permanent_id_and_name` (defined below) is called for its id half
        # only - see the exile-linking comment inside the loop for why.
        source_id, _ = _permanent_id_and_name(stack_object, for_spell=for_spell)
        for step in ordered:
            # CR 608.2e / CR 101.4: the whole table completes one step before
            # the next one starts, in APNAP order within each step.
            for player in _players_in_apnap_order(game):
                if opponents_only and player.username == controller:
                    continue
                before = len(game.exile)
                # CR 608.2e: a later "that many" of this player's is this
                # player's own count, not the table's.
                with game.counting_for(player.username):
                    step(game, player, source, source_id_of(stack_object))
                # CR 607.2a, CR 406.6: an ability that exiles cards and later
                # refers to "the exiled cards" or cards "exiled with [this
                # object]" links the two. Knowledge Pool's "Imprint — When
                # this artifact enters, each player exiles the top three
                # cards of their library" is exactly this instruction, routed
                # here through `_EACH_PLAYER_EXILES_TOP_RE`'s `exile_top_of_
                # library` step, and its second ability's "other cards
                # exiled with this artifact" is the reader - but until this
                # fix, `exile_top_of_library` called `Game.exile_permanent`
                # and left `exile_annotation` at `None`, so the reader always
                # found an empty pool no matter what ability 2 itself wrote.
                #
                # A `ClauseEffect` step is handed the source's name and the
                # string id its questions carry, never the object, so a step
                # does not annotate what it moves on its own - and most steps
                # exile nothing at all. Diffing `game.exile` before and after
                # each step instead is a property of *this* closure alone
                # (it already holds `stack_object`, and therefore the id):
                # whatever a step newly appended to the shared exile zone is
                # "exiled with" the object this whole ability is printed on,
                # by CR 607.2a's own structural test, no keyword or per-step
                # wiring needed.
                #
                # `if card.exile_annotation is None and card.face_up` leaves
                # alone anything a step already annotated for its own reason,
                # and leaves a face-down card (Pyxis of Pandemonium's own
                # "exiles the top card of their library face down") to
                # `link_cards_exiled_during`, which links it with a bare
                # `ExileMarker.LINKED` - a marker `CardState.has_no_
                # characteristics` still treats as no characteristics
                # (CR 406.3a, DDR#956's ruling in `test_judge_face_down_
                # exile.py`) until Pyxis's second ability turns it face up.
                for card in game.exile[before:]:
                    if card.exile_annotation is None and card.face_up:
                        card.exile_annotation = ExileAnnotation(
                            marker=ExileMarker.IMPRINTED,
                            owner=card.owner,
                            linked_permanent_id=source_id,
                        )

    return kept_fragments, effect


# --------------------------------------------------------------------------
# "Sacrifice a creature, an artifact, and a land." (CR 701.21a)
# --------------------------------------------------------------------------

#: One item of a sacrifice list, article included: "a creature", "an
#: artifact", "a land".
_SACRIFICE_LIST_ITEM_RE = re.compile(r"^(?:and )?an? (?P<description>[a-z][a-z -]*?),?$")


def _merge_sacrifice_one_of_each_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """ "sacrifice a creature, an artifact, and a land" (Tomb of Annihilation's
    Oubliette) - the controller sacrifices one permanent of each description,
    each their own choice (CR 701.21a, CR 608.2d), no permanent twice.
    `_prepare_effect_clauses` cuts the list at its serial comma, so its pieces
    are taken back here; each item is read by `targeting.permanent_description`
    or the whole instruction is refused."""
    first = clauses[index].strip().rstrip(".")
    head = re.match(r"^sacrifice (?P<rest>an? .+)$", first, re.IGNORECASE)
    if head is None:
        return None
    pieces = [part.strip() for part in head.group("rest").split(",") if part.strip()]
    consumed = 1
    while index + consumed < len(clauses) and _SACRIFICE_LIST_ITEM_RE.fullmatch(
        clauses[index + consumed].strip().rstrip(".").lower()
    ):
        pieces.append(clauses[index + consumed].strip().rstrip("."))
        consumed += 1
    descriptions: list[str] = []
    for piece in pieces:
        item = _SACRIFICE_LIST_ITEM_RE.fullmatch(piece.lower())
        if item is None:
            return None
        descriptions.append(item.group("description").strip())
    if len(descriptions) < 2:
        return None
    requirements = [permanent_description(description) for description in descriptions]
    if any(requirement is None for requirement in requirements):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        chosen: list[CardState] = []
        for description, requirement in zip(descriptions, requirements, strict=True):
            assert requirement is not None
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if permanent not in chosen
                and requirement.rejects(permanent, player.username, game) is None
            ]
            if not candidates:
                continue
            if len(candidates) == 1:
                chosen.append(candidates[0])
                continue
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"sacrifice {with_indefinite_article(description)}",
                    source=source,
                    amount=1,
                    cards=tuple(permanent.id for permanent in candidates),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in candidates}
            chosen.extend(by_id[card_id] for card_id in answer if card_id in by_id)
        for permanent in chosen:
            if permanent.zone is Zone.BATTLEFIELD:
                game.sacrifice(permanent)

    return consumed, effect


# --------------------------------------------------------------------------
# "Draw N cards and reveal them. You may cast one of them without paying its
# mana cost." (CR 608.2g)
# --------------------------------------------------------------------------

_DRAW_N_RE = re.compile(rf"^draw (?P<n>{COUNT}) cards?$", re.IGNORECASE)
_CAST_ONE_OF_THEM_FREE_RE = re.compile(
    r"^you may cast (?:one|up to one) of them without paying its mana cost$", re.IGNORECASE
)


def _merge_draw_reveal_cast_one_free_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """Dungeon of the Mad Mage's Mad Wizard's Lair: draw the cards, reveal
    them, and cast up to one of them during the resolution without paying
    its mana cost (CR 608.2g, CR 118.9)."""
    if index + 2 >= len(clauses):
        return None
    draw = _DRAW_N_RE.fullmatch(clauses[index].strip().rstrip("."))
    if draw is None or clauses[index + 1].strip().rstrip(".").lower() != "reveal them":
        return None
    if _CAST_ONE_OF_THEM_FREE_RE.fullmatch(clauses[index + 2].strip().rstrip(".")) is None:
        return None
    amount = parse_count(draw.group("n"))
    if amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        drawn = game.draw_cards(player.username, amount)
        for card in drawn:
            game.reveal(card, source=source)
        _offer_free_casts_from_among(
            game,
            list(drawn),
            player.username,
            source_name=source,
            source_id=source_id_of(stack_object),
            play=False,
            limit=1,
            zone=Zone.HAND,
        )

    return 3, effect


#: "you may cast the exiled `<quality>` card until end of turn" - the "if you
#: don't" branch of `_merge_exile_until_quality_then_counter_or_cast_clauses`
#: below. Black Widow's own trailing "and mana of any type can be spent to
#: cast that spell" is cut into its *own* clause by `split_effect_clauses`
#: (the same boundary `_ANY_TYPE_MANA_STANDALONE_RE` already reads elsewhere),
#: so it is not part of this sentence any more by the time this matches it -
#: the merge below looks for it as an optional following clause instead.
_CAST_EXILED_QUALITY_UNTIL_EOT_RE = re.compile(
    r"^cast the exiled (?P<quality>[\w' ,-]+?) card until end of turn\.?$",
    re.IGNORECASE,
)


def _merge_exile_until_quality_then_counter_or_cast_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Black Widow, Super Spy's whole trigger as one CR 608.2c/608.2d
    instruction chain: exile-until-quality (this file's own or the
    third-person twin above), then a plain "you may `<X>`." (CR 608.2d), then
    "If you don't, you may cast the exiled `<quality>` card ..." (CR 608.2d's
    other branch, itself carrying its own nested "you may" - CR 608.2d poses
    one question per "may", and nothing stops a second one inside the first's
    "if you don't" arm).

    `<X>` is read through `_parse_mixed_clause` generally (Black Widow's own
    "put a +1/+1 counter on this creature", after `trigger_effect_for`'s own
    CR 201.5 self-name normalization has already turned "Black Widow" into
    "this creature" on the pass that reaches this merge) rather than pinned
    to a counter, so a future printing with a different "you may" action
    still reads.

    Ability-only: `event.player` is an `AbilityOnStack`'s own attribute.
    """
    if for_spell or index + 2 >= len(clauses):
        return None
    antecedent = _parse_exile_until_antecedent(clauses[index])
    if antecedent is None:
        antecedent = _parse_exile_until_antecedent_third_person(clauses[index])
    if antecedent is None:
        return None
    exile, _ = antecedent
    quality_match = _EXILE_UNTIL_QUALITY_RE.fullmatch(
        clauses[index].strip().rstrip(".")
    ) or _EXILE_UNTIL_QUALITY_THIRD_PERSON_RE.fullmatch(clauses[index].strip().rstrip("."))
    if quality_match is None:
        return None
    quality = quality_match.group("quality").strip().lower()

    may_match = _YOU_MAY_ACTION_RE.fullmatch(clauses[index + 1].strip())
    if may_match is None:
        return None
    may_action_text = may_match.group("action").strip().rstrip(".")
    counter_effect = _parse_mixed_clause(may_action_text, for_spell=False)
    if counter_effect is None:
        return None

    if_match = _IF_YOU_DONT_RE.fullmatch(clauses[index + 2].strip())
    if if_match is None:
        return None
    dont_may_match = _YOU_MAY_ACTION_RE.fullmatch(if_match.group("consequence").strip())
    if dont_may_match is None:
        return None
    cast_match = _CAST_EXILED_QUALITY_UNTIL_EOT_RE.fullmatch(
        dont_may_match.group("action").strip().rstrip(".")
    )
    if cast_match is None:
        return None
    if cast_match.group("quality").strip().lower() != quality:
        return None
    consumed = 3
    any_type_mana = False
    if index + consumed < len(clauses) and _ANY_TYPE_MANA_STANDALONE_RE.fullmatch(
        clauses[index + consumed].strip()
    ):
        any_type_mana = True
        consumed += 1

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        exiled = exile(game, ability)
        if not exiled:
            return
        stopper = exiled[-1]
        controller = game.controller_of(ability)
        took_counter = game.may(
            controller,
            may_action_text,
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=(stopper,),
        )
        if took_counter:
            counter_effect(game, ability)
            return
        took_cast = game.may(
            controller,
            f"cast {stopper.name} until end of turn",
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=(stopper,),
        )
        if not took_cast:
            return
        game.grant_play_permission(
            stopper,
            controller.username,
            action=PlayAction.CAST,
            pays_mana_cost=True,
            source_name=ability.source_name,
            rule="CR 601.3",
            zone=stopper.zone,
            any_type_mana=any_type_mana,
            until_end_of_turn=True,
        )

    return consumed, effect


#: "You may cast any number of spells from among them without paying their
#: mana costs." - Improvisation Capstone's second sentence. CR 607.1: "them"
#: is whatever the sentence before it exiled. CR 608.2g: the casts happen
#: during the resolution (the card's own ruling: "You can't wait to cast them
#: later in the turn. Timing restrictions based on the cards' types are
#: ignored."), CR 107.1c's "any number" includes none, and CR 118.9's
#: "without paying" leaves X at 0 (CR 107.3b).
#: Doom Reigns Supreme's "You may cast up to two spells from among the exiled
#: cards without paying their mana costs." is the same instruction with an
#: "up to" maximum and the antecedent named rather than pronouned.
_CAST_ANY_NUMBER_FROM_AMONG_THEM_FREE_RE = re.compile(
    rf"^you may cast (?:any number of|up to {count_pattern('limit')}) spells from among"
    r" (?:them|the exiled cards|the (?P<this_way>[\w' -]+?) cards exiled this way)"
    r" without paying their mana costs\.?$",
    re.IGNORECASE,
)


def _merge_exile_then_cast_any_number_free_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> "tuple[int, TargetedClause] | None":
    """A plural exiling clause, then `_CAST_ANY_NUMBER_FROM_AMONG_THEM_FREE_RE`,
    as one CR 608.2c instruction. Cards not cast stay in exile - nothing
    printed moves them (CR 406.1)."""
    if index + 1 >= len(clauses):
        return None
    cast_match = _CAST_ANY_NUMBER_FROM_AMONG_THEM_FREE_RE.fullmatch(clauses[index + 1].strip())
    if cast_match is None:
        return None
    limit = parse_count(cast_match.group("limit")) if cast_match.group("limit") else None
    this_way = cast_match.group("this_way")
    each_player = _each_player_exile_until(clauses[index])
    if each_player is not None:
        # Etali, Primal Conqueror: "the nonland cards exiled this way" are the
        # cards that stopped each player's run - the antecedent's own quality.
        antecedent: tuple[ExileAntecedent, bool] | None = (each_player, True)
    elif this_way is not None:
        return None
    else:
        antecedent = None
    antecedent = (
        antecedent
        or _parse_exile_top_of_other_libraries_antecedent(clauses[index])
        or (
            _spell_safe_exile_antecedent(clauses[index])
            if for_spell
            else (
                _parse_exile_antecedent(clauses[index])
                or _parse_exile_until_antecedent(clauses[index])
            )
        )
    )
    if antecedent is None:
        return None
    exile, exiles_many = antecedent
    if not exiles_many:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        caster = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        found = exile(game, stack_object)
        _offer_free_casts_from_among(
            game,
            found,
            caster,
            source_name=source_name,
            source_id=source_id_of(stack_object),
            play=False,
            limit=limit,
        )

    return 2, effect


def _offer_free_casts_from_among(
    game: "Game",
    cards: list[CardState],
    caster: str,
    *,
    source_name: str,
    source_id: str | None,
    play: bool,
    limit: int | None = None,
    zone: Zone = Zone.EXILE,
) -> None:
    """CR 608.2g's "you may [play lands and] cast [any number of] spells from
    among <cards> without paying their mana costs", one card at a time until
    none is left that can legally be taken or the caster declines (CR 107.1c,
    CR 608.2d). `play=True` offers lands too (Gix's "play lands and cast
    spells"); otherwise a land is never offered, since a land is never cast
    (CR 305.9).

    A land's own resolution-time legality (CR 305.2b) has no public reader
    outside `Game.may_cast_during_resolution` itself, so every land among the
    remaining cards is offered and its real legality enforced there, per
    card, when chosen. A nonland card is pre-filtered by
    `can_cast_during_resolution` (CR 601.2c's targets, CR 700.2a's modes,
    CR 118.3's cost).
    """
    remaining = [card for card in cards if card.zone is zone]
    taken_count = 0
    while remaining and (limit is None or taken_count < limit):
        legal = [
            card
            for card in remaining
            if (play and card.card.is_land)
            or (not card.card.is_land and game.can_cast_during_resolution(card, caster))
        ]
        if not legal:
            break
        taken = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=caster,
                prompt=(
                    f"{'play a land or cast a spell' if play else 'cast a spell'} from among "
                    f"the cards {source_name} exiled, without paying its mana cost"
                ),
                source=source_name,
                source_id=source_id,
                affirmative_is_legal=True,
                cards=tuple(card.id for card in legal),
            )
        )
        if not taken:
            break
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=caster,
                prompt=(
                    f"choose a card to {'play or cast' if play else 'cast'} "
                    f"without paying its mana cost"
                ),
                source=source_name,
                source_id=source_id,
                amount=1,
                cards=tuple(card.id for card in legal),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {card.id: card for card in legal}
        chosen = by_id[chosen_ids[0]]
        remaining.remove(chosen)
        taken_count += 1  # "up to N" is a maximum, and N have been cast.
        if not play:
            # Already chosen above: cast it, with no second "you may".
            game.cast_during_resolution(chosen, caster, source_name=source_name, rule="CR 608.2g")
            continue
        game.may_cast_during_resolution(
            chosen,
            caster,
            prompt=f"play or cast {chosen.name} without paying its mana cost",
            source=source_name,
            source_id=source_id,
            source_name=source_name,
            rule="CR 608.2g",
            play=True,
        )


#: "you may exile the top card of your library" - Daredevil, Man Without
#: Fear's own attack trigger's first clause (CR 608.2d's "may" over a single
#: exile, rather than the unconditional `_EXILE_TOP_OF_YOUR_LIBRARY_RE`).
_MAY_EXILE_TOP_CARD_RE = re.compile(r"^you may exile the top card of your library$", re.IGNORECASE)

#: "if that card is a[n] `<quality>` card, `<effect>`" - CR 607.1's "that
#: card" pointing at whatever the previous clause just exiled, gating an
#: arbitrary trailing effect on the exiled card's own printed quality (a
#: property of one specific object, not `Game.condition_holds`'s live board
#: state) - Daredevil's own "Daredevil gets +2/+1 until end of turn."
_IF_THAT_CARD_IS_QUALITY_RE = re.compile(
    r"^if that card is an? (?P<quality>[\w' ,-]+?) card, (?P<effect>.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _merge_may_exile_top_conditional_pump_then_play_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Daredevil, Man Without Fear's whole attack trigger as one CR 608.2c
    instruction: an optional exile (CR 608.2d), a consequence conditioned on
    the exiled card's own quality (CR 607.1's "that card", not a board
    condition), and an unconditional play permission over the same card
    (`_PLAY_PERMISSION_RE`, already general).

    Ability-only: nothing in the pool prints this shape on a spell.
    """
    if for_spell or index + 2 >= len(clauses):
        return None
    if _MAY_EXILE_TOP_CARD_RE.fullmatch(clauses[index].strip().rstrip(".")) is None:
        return None
    cond_match = _IF_THAT_CARD_IS_QUALITY_RE.fullmatch(clauses[index + 1].strip().rstrip("."))
    if cond_match is None:
        return None
    quality = cond_match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)
    pump_text = cond_match.group("effect").strip().rstrip(".")

    def pump_effect(game: "Game", stack_object: "StackObject") -> None:
        # A no-target continuous-effect sentence on the ability's own
        # source (CR 611.2, Basking Rootwalla's shape) - the same primitive
        # `create_continuous_effect_of_ability` calls, given this merge's
        # own sub-clause text directly rather than the ability's whole
        # printed text (which has two other clauses this one is not).
        assert is_ability(stack_object)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        continuous_effects(game).create(
            source,
            targets=[source],
            context=layer_context_for(game, game.controller_of(stack_object)),
            ability_text=_as_sentence(pump_text),
            game=game,
        )

    permission = _PLAY_PERMISSION_RE.fullmatch(clauses[index + 2].strip().rstrip(","))
    if permission is None or permission.group("subject").lower() != "that card":
        return None
    duration = _permission_duration(permission)
    if duration is None:
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        controller = game.controller_of(ability)
        taken = game.may(
            controller,
            "exile the top card of your library",
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        if not taken or not controller.library:
            return
        card = game.exile_permanent(controller.library[0])
        if matches(card):
            pump_effect(game, ability)
        game.grant_play_permission(
            card,
            controller.username,
            action=action,
            pays_mana_cost=not free,
            source_name=ability.source_name,
            rule="CR 601.3",
            zone=card.zone,
            until_end_of_turn=duration is PermissionDuration.THIS_TURN,
            expires_end_of_next_turn=duration is PermissionDuration.NEXT_TURN,
            until_next_end_step_of=(
                controller.username if duration is PermissionDuration.NEXT_END_STEP else None
            ),
        )

    return 3, effect


#: "you may exile that card from your graveyard" - Moonstone, Harsh
#: Mistress's own discard trigger, "that card" being CR 607.1 anaphora back
#: to whatever was just discarded (`GameEvent.discarded_ids`).
_MAY_EXILE_THAT_CARD_FROM_GRAVEYARD_RE = re.compile(
    r"^you may exile that card from your graveyard$", re.IGNORECASE
)


def _merge_may_exile_discarded_card_then_play_permission_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Moonstone, Harsh Mistress's own two-sentence discard trigger: "you may
    exile that card from your graveyard" (CR 608.2d), then "if you do,
    `<play permission>`" (CR 118.12) over the very card just exiled.

    "That card" points at whichever card the *discard event* names
    (`GameEvent.discarded_ids`); CR 603.2c fires the trigger once even for a
    batched multi-card discard, so every card in the batch is offered in
    turn rather than only the first - each is its own independent CR 608.2d
    question, and only a card still sitting in the graveyard (nothing else
    already moved it) can be exiled from it.

    Ability-only: `event.discarded_ids` is an `AbilityOnStack`'s own
    attribute.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    if _MAY_EXILE_THAT_CARD_FROM_GRAVEYARD_RE.fullmatch(clauses[index].strip().rstrip(".")) is None:
        return None
    if_do_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_do_match is None:
        return None
    permission = _PLAY_PERMISSION_RE.fullmatch(if_do_match.group("consequence").strip().rstrip(","))
    if permission is None or permission.group("subject").lower() != "that card":
        return None
    duration = _permission_duration(permission)
    if duration is None:
        return None
    action = PlayAction.PLAY if permission.group("action").lower() == "play" else PlayAction.CAST
    free = permission.group("free") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object) or stack_object.event is None:
            return
        ability = stack_object
        controller = game.controller_of(ability)
        for card_id in ability.event.discarded_ids:
            card = game.find_by_id(card_id)
            if card is None or card.zone is not Zone.GRAVEYARD:
                continue
            taken = game.may(
                controller,
                f"exile {card.name} from your graveyard",
                source=ability.source_name,
                source_id=source_id_of(ability),
                cards=(card,),
            )
            if not taken:
                continue
            exiled = game.exile_permanent(card)
            game.grant_play_permission(
                exiled,
                controller.username,
                action=action,
                pays_mana_cost=not free,
                source_name=ability.source_name,
                rule="CR 601.3",
                zone=exiled.zone,
                until_end_of_turn=duration is PermissionDuration.THIS_TURN,
                expires_end_of_next_turn=duration is PermissionDuration.NEXT_TURN,
                until_next_end_step_of=(
                    controller.username if duration is PermissionDuration.NEXT_END_STEP else None
                ),
            )

    return 2, effect


#: "You may cast/play that card[ this turn]." with no *leading* duration -
#: Chandra, Torch of Defiance's own bare "You may cast that card." (no
#: duration at all - `Game.grant_play_permission`'s own `until_end_of_turn=
#: True` default is what this reads as, the engine's own sensible default
#: for an unqualified permission, not a CR citation for an implicit
#: duration CR 601.3 itself does not name) and Synth Eradicator's own
#: trailing "you may play that card this turn" (already `_PLAY_PERMISSION_
#: RE`'s own shape). Tried second, after that stricter reader, so a
#: printing carrying a real duration still reads through it unchanged.
_MAY_CAST_OR_PLAY_THAT_CARD_BARE_RE = re.compile(
    r"^you may (?P<action>cast|play) that card\.?$", re.IGNORECASE
)

#: "If you don't, `<consequence>`." - the CR 608.2d branch taken when the
#: "may" just above was declined, as opposed to `_IF_YOU_DO_RE`'s own "if
#: you do" branch for CR 118.12's optional-cost shape.
_IF_YOU_DONT_RE = re.compile(r"^if you don'?t,\s*(?P<consequence>.+)$", re.IGNORECASE | re.DOTALL)

#: "you may `<action>`" - the bare instruction a CR 608.2d "may" gates,
#: stripped of its own "you may" so the action can be read once, whichever
#: side of an "if you [do/don't]" pair it sits on - `_parse_mixed_clause`
#: already reads its own bare shape (Synth Eradicator's own "get {E}{E}"),
#: unlike the whole "you may ..." sentence, which would pose a *second*,
#: redundant CR 608.2d question on top of the one this merge already asked
#: to choose which branch to take.
_YOU_MAY_ACTION_RE = re.compile(r"^you may (?P<action>.+)$", re.IGNORECASE | re.DOTALL)


def _play_permission_action(text: str) -> PlayAction | None:
    """`PlayAction.CAST`/`.PLAY` if `text` is a play-permission grant for
    "that card" (either `_PLAY_PERMISSION_RE`'s own durationed shape or
    `_MAY_CAST_OR_PLAY_THAT_CARD_BARE_RE`'s bare one), or `None`."""
    match = _PLAY_PERMISSION_RE.fullmatch(text)
    if (
        match is not None
        and match.group("subject").lower() == "that card"
        and _permission_duration(match)
        not in (PermissionDuration.NEXT_TURN, PermissionDuration.NEXT_END_STEP)
    ):
        return PlayAction.PLAY if match.group("action").lower() == "play" else PlayAction.CAST
    match = _MAY_CAST_OR_PLAY_THAT_CARD_BARE_RE.fullmatch(text)
    if match is not None:
        return PlayAction.PLAY if match.group("action").lower() == "play" else PlayAction.CAST
    return None


def _merge_exile_top_may_x_if_you_dont_y_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Exile the top card of your library. You may `<X>`. If you don't,
    `<Y>`." where exactly one of `<X>`/`<Y>` is "cast/play that card[ this
    turn]" and the other is an ordinary effect - Chandra, Torch of
    Defiance's own `+1` (the permission on the "you may" side, a damage
    consequence on the "if you don't" side) and Synth Eradicator's own
    attack trigger (the identical shape reversed: an energy gain on the
    "you may" side, the permission on the "if you don't" side).

    A three-clause merge, not independent readings: "that card" is CR 607.1
    anaphora onto the first sentence's own exile, and whichever consequence
    is not the permission is conditioned on the CR 608.2d "may" the second
    sentence poses - a fact only this merge, resolving the whole paragraph
    as one instruction, can read back.

    Ability-only (`for_spell=False`): nothing in the pool prints this shape
    on a spell, and the source read below (`ability.source_name`) is an
    `AbilityOnStack`'s own attribute, not a resolving `CardState`'s.
    """
    if for_spell or index + 2 >= len(clauses):
        return None
    if _EXILE_TOP_OF_YOUR_LIBRARY_RE.fullmatch(clauses[index].strip()) is None:
        return None
    may_match = _YOU_MAY_ACTION_RE.fullmatch(clauses[index + 1].strip())
    if may_match is None:
        return None
    if_match = _IF_YOU_DONT_RE.fullmatch(clauses[index + 2].strip())
    if if_match is None:
        return None
    may_action_text = may_match.group("action").strip().rstrip(".")
    dont_text = if_match.group("consequence").strip().rstrip(".")

    yes_permission = _play_permission_action(clauses[index + 1].strip())
    no_permission = _play_permission_action(if_match.group("consequence").strip())
    if (yes_permission is None) == (no_permission is None):
        # Neither side, or both, grants the permission - not this shape.
        return None

    if yes_permission is not None:
        permission_on_yes = True
        action = yes_permission
        other_effect = _parse_mixed_clause(dont_text, for_spell=False)
    else:
        permission_on_yes = False
        action = no_permission
        other_effect = _parse_mixed_clause(may_action_text, for_spell=False)
    if other_effect is None or action is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        player = game.controller_of(ability)
        if not player.library:
            return
        card = game.exile_permanent(player.library[0])
        taken = game.may(
            player,
            f"{'cast' if action is PlayAction.CAST else 'play'} {card.name}"
            if permission_on_yes
            else may_action_text,
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        if taken == permission_on_yes:
            game.grant_play_permission(
                card,
                player.username,
                action=action,
                pays_mana_cost=True,
                source_name=ability.source_name,
                rule="CR 601.3",
                zone=card.zone,
            )
        else:
            other_effect(game, ability)

    return 3, effect


_REVEAL_HAND_RE = re.compile(
    r"^(?P<who>target (?:player|opponent)|that player) reveals their hand$", re.IGNORECASE
)
#: "you choose a/an <quality> card from it" - Thoughtseize's, Grief's, and
#: Thought-Knot Seer's shared second sentence, the CR 701.9b/CR 701.13a
#: override handing the choice to the resolving spell's/ability's controller
#: instead of the revealed player. Thought-Knot Seer prints its consequence
#: in the same sentence ("... from it and exile that card"), but
#: `split_effect_clauses` already cuts across that bare "and" the same way it
#: does everywhere else, so this clause and its consequence clause
#: (`_DISCARD_THAT_CARD_RE`/`_EXILE_THAT_CARD_RE`) always arrive separately.
#:
#: The trailing "with mana value N or less" is Inquisition of Kozilek's own,
#: and is a real narrowing of the choice rather than flavour - CR 202.3 makes
#: mana value a characteristic, so a card above the bound is CR 608.2d's
#: "option that's illegal" and must not be offered. Left optional so
#: Thoughtseize, Grief and Thought-Knot Seer read exactly as before.
#:
#: The count is `numbers.parse_quantity`'s: "a nonland card" (Thoughtseize),
#: "two cards" (Gruesome Discovery, no quality at all), "up to two". X is not
#: read here - nothing in this merge knows the spell's X.
_CHOOSE_CARD_FROM_REVEALED_RE = re.compile(
    rf"^you choose (?P<count>(?:up to )?{COUNT}) (?:(?P<quality>.+?) )?cards? from it"
    r"(?: with mana value (?P<max_mv>\d+) or less)?$",
    re.IGNORECASE,
)
#: "that player discards that card" (Thoughtseize, Grief) - the anaphoric
#: tail naming the same player `_REVEAL_HAND_RE` targeted and the same card
#: `_CHOOSE_CARD_FROM_REVEALED_RE` just chose.
_DISCARD_THAT_CARD_RE = re.compile(
    r"^(?:then )?(?:that player|they) discards? (?:that card|those cards)$", re.IGNORECASE
)
#: "exile that card" (Thought-Knot Seer, when not folded into the previous
#: sentence) - CR 701.13a's move, straight from the revealed hand.
_EXILE_THAT_CARD_RE = re.compile(r"^(?:then )?exile (?:that card|those cards|them)$", re.IGNORECASE)
#: "you lose N life" - Thoughtseize's own optional fourth sentence.
_YOU_LOSE_LIFE_RE = re.compile(r"^you lose (?P<life>\d+) life$", re.IGNORECASE)


#: "Its owner puts it ..." - the anaphoric second sentence of a two-clause
#: paragraph (Aether Gust's own "Choose target spell or permanent that's red
#: or green.", Subtlety's "Choose up to one target creature spell or
#: planeswalker spell."), paired below with whichever clause before it names
#: the target - "its owner" is CR 607.1 anaphora back to that target, so
#: there is nothing to resolve without both clauses read together.
_ITS_OWNER_PUTS_INTO_LIBRARY_RE = re.compile(
    rf"^its owner {_OWNER_PUTS_IT_INTO_LIBRARY_TAIL}", re.IGNORECASE
)

#: An optional leading "Choose " on the target-naming half of that two-clause
#: paragraph (Aether Gust's "Choose target ...", Subtlety's "Choose up to one
#: target ..."); a bare "target `<X>`." with no "Choose" is read the same way.
_CHOOSE_TARGET_PREFIX_RE = re.compile(r"^choose\s+", re.IGNORECASE)


def _merge_choose_target_then_owner_puts_it_into_library_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "(Choose )?`<target>`. Its owner puts it ..." - Aether Gust's own
    two-sentence paragraph ("Choose target spell or permanent that's red or
    green. Its owner puts it on their choice of the top or bottom of their
    library."); Subtlety's identical "Choose up to one target creature spell
    or planeswalker spell." is just this with "up to one" inside the target
    phrase, read by `_targets_understood`'s own `count_agnostic` the same way
    every other verb's "up to N target ..." already is.

    A merge, not two independent single-clause parsers: "its owner" in the
    second sentence is CR 607.1 anaphora back to whichever object the first
    sentence's target turned out to be, and there is nothing to resolve
    without both clauses read together. Works for spells and abilities alike
    - nothing about choosing a target this way is ability-only, and Aether
    Gust prints the identical shape on a spell.
    """
    if index + 1 >= len(clauses):
        return None
    destination_match = _ITS_OWNER_PUTS_INTO_LIBRARY_RE.fullmatch(clauses[index + 1].strip())
    if destination_match is None:
        return None
    phrase = _CHOOSE_TARGET_PREFIX_RE.sub("", clauses[index].strip())
    if not _targets_understood(phrase, count_agnostic=True, battlefield_only=False):
        return None
    depth = _owner_puts_it_into_library_destination_depth(destination_match)
    return 2, _owner_puts_it_into_library_effect(for_spell=for_spell, depth=depth)


def _merge_reveal_hand_choose_discard_clauses(
    clauses: list[str], index: int, *, for_spell: bool, anaphoric_revealer: bool = False
) -> tuple[int, TargetedClause] | None:
    """Thoughtseize's, Grief's, and Thought-Knot Seer's shared paragraph,
    read as one anaphoric run of clauses rather than several independent
    ones: "it" in the second sentence is the hand `_REVEAL_HAND_RE` just
    revealed, and "that card" in the third is whichever one
    `_CHOOSE_CARD_FROM_REVEALED_RE` just chose. Neither of those can be
    resolved by a clause parsed alone, which is why this is a multi-clause
    merge (see `_parse_mixed_clauses`'s own docstring) rather than several
    entries in `_parse_mixed_clause`'s single-clause chain.

    Grief prints "target opponent" where Thoughtseize prints "target player";
    `_REVEAL_HAND_RE` reads either, and the actual restriction is enforced
    through `_targets_understood` on the clause's own matched text (not a
    literal "target player") so the two are checked for what they actually
    say. The consequence clause is either `_DISCARD_THAT_CARD_RE`'s CR 701.9a
    discard (Thoughtseize, Grief) or `_EXILE_THAT_CARD_RE`'s CR 701.13a exile
    (Thought-Knot Seer) - the same anaphoric "that card", moved a different
    place.

    The trailing "you lose N life" is genuinely optional - Thoughtseize
    prints it, Grief and Thought-Knot Seer do not - and is read
    unconditionally regardless of whether a card was actually taken
    (CR 608.2c's printed order has no "if you do" gate on it the way
    `_parse_conditional_sacrifice_clause`'s consequence does).

    The reveal is CR 701.20a's, of the whole hand: every card in it is
    recorded through `Game.reveal` (all players, no viewers) before the
    choice is asked, not only the cards the choice may take.

    A hand with no nonland (or otherwise qualifying) card is CR 608.2d's
    "impossible option": nothing is asked, but the hand is still revealed,
    exactly as the paper cards do.

    The count is printed ("you choose two cards from it", Gruesome
    Discovery): the chooser picks that many, or every qualifying card when
    the hand holds fewer (CR 609.3), and the consequence moves all of them.

    `anaphoric_revealer` lets the first clause say "that player reveals their
    hand" - the player a preceding sentence already targeted, which only a
    caller that has read that sentence (`_parse_condition_instead_clause`)
    can vouch for.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_clause = clauses[index].strip()
    reveal_match = _REVEAL_HAND_RE.fullmatch(reveal_clause)
    if reveal_match is None:
        return None
    if reveal_match.group("who").lower() == "that player":
        if not anaphoric_revealer:
            return None
    elif not _targets_understood(reveal_clause.split(" reveals", 1)[0], allow_player_targets=True):
        return None
    choose_match = _CHOOSE_CARD_FROM_REVEALED_RE.fullmatch(clauses[index + 1].strip())
    if choose_match is None:
        return None
    quantity = parse_quantity(choose_match.group("count"))
    if quantity is None or quantity.source is not QuantitySource.FIXED or not quantity.amount:
        return None
    quality_text = choose_match.group("quality")
    if quality_text is None:

        def quality_matches(state: CardState) -> bool:
            return True

    else:
        read_quality = _nonland_or_typed_card_matcher(quality_text)
        if read_quality is None:
            return None
        quality_matches = read_quality
    max_mv = int(choose_match.group("max_mv")) if choose_match.group("max_mv") else None

    def matches(state: CardState) -> bool:
        # CR 202.3: mana value is a characteristic of the card, so the bound
        # narrows which cards may legally be chosen (CR 608.2d) rather than
        # only which one a well-behaved player would pick.
        if not quality_matches(state):
            return False
        return max_mv is None or state.mana_value <= max_mv

    consequence_clause = clauses[index + 2].strip()
    to_exile = _EXILE_THAT_CARD_RE.fullmatch(consequence_clause) is not None
    if not to_exile and _DISCARD_THAT_CARD_RE.fullmatch(consequence_clause) is None:
        return None
    consumed = 3
    life_loss = 0
    if index + 3 < len(clauses):
        life_match = _YOU_LOSE_LIFE_RE.fullmatch(clauses[index + 3].strip())
        if life_match is not None:
            life_loss = int(life_match.group("life"))
            consumed = 4

    quality_description = (quality_text or "").strip()
    if max_mv is not None:
        quality_description = f"{quality_description} (mana value {max_mv} or less)".strip()
    printed_count = quantity.amount
    exact = quantity.exact

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        revealer = next(
            (target for target in game.resolve_targets(stack_object) if isinstance(target, Player)),
            None,
        )
        if revealer is not None:
            for state in list(revealer.hand):
                game.reveal(state, source=source)
            candidates = [state for state in revealer.hand if matches(state)]
            if candidates:
                most = min(printed_count, len(candidates))
                noun = f"{quality_description} card".strip()
                if exact and most == 1:
                    wanted = with_indefinite_article(noun)
                else:
                    wanted = f"{'' if exact else 'up to '}{most} {noun}s"
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=controller.username,
                        prompt=f"choose {wanted} from {revealer.username}'s revealed hand",
                        source=source,
                        amount=most,
                        exact=exact,
                        cards=tuple(state.id for state in candidates),
                        source_id=source_id_of(stack_object),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {state.id: state for state in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids]
                if to_exile:
                    for card in chosen:
                        exiled = game.exile_permanent(card)
                        _grant_cast_exiled_card_permission_from_sibling_static(
                            game, stack_object, exiled
                        )
                elif chosen:
                    game.discard_cards(revealer.username, chosen, source=source)
        if life_loss:
            game.lose_life(controller, life_loss)

    return consumed, effect


def _merge_damage_target_then_reveal_choose_discard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Stinging Vitriol's own whole paragraph: "`<source>` deals N damage to
    target opponent. That player reveals their hand. You choose a `<quality>`
    card from it. They discard that card." - a targeted damage clause
    establishing the one player CR 400.7's "that player" then reads
    anaphorically, composed the same way `_parse_condition_instead_clause`
    already hands `anaphoric_revealer=True` to `_merge_reveal_hand_choose_
    discard_clauses` for its own "instead that player reveals..." shape.

    Both halves read `game.resolve_targets(stack_object)` independently and
    each finds the same single player target this ability ever names, so no
    referent has to be threaded between them by hand.
    """
    if not re.search(
        r"\bdeals? .+ damage to target (?:opponent|player)\b", clauses[index], re.IGNORECASE
    ):
        return None
    damage = _parse_targeted_clause(clauses[index], for_spell=for_spell)
    if damage is None:
        return None
    rest = _merge_reveal_hand_choose_discard_clauses(
        clauses, index + 1, for_spell=for_spell, anaphoric_revealer=True
    )
    if rest is None:
        return None
    rest_consumed, rest_effect = rest

    def effect(game: "Game", stack_object: "StackObject") -> None:
        damage(game, stack_object)
        rest_effect(game, stack_object)

    return 1 + rest_consumed, effect


@SPELL_TEXT.rung("s18")
def _parse_damage_then_followup_spell(effect_text: str) -> Effect | None:
    """A damage spell and the clauses that refer back to it - radiance groups,
    "you gain life equal to the damage dealt this way", "deals M damage
    instead", "that creature's controller", "that player discards" - read as
    one CR 608.2c sequence by `machines/damage_backrefs.py`."""
    from ..damage_backrefs import damage_then_followup_spell_effect

    return damage_then_followup_spell_effect(effect_text)


def _clauses_around_sentences(
    text: str,
    reader: Callable[[list[str], int], tuple[int, TargetedClause] | None],
    *,
    for_spell: bool,
) -> list[TargetedClause] | None:
    """`text`'s sentences with every run `reader` claims read as one clause and
    every other run read through the ordinary clause pipeline - or `None`
    when `reader` claims nothing, or any leftover run reads to nothing (CR
    608.2c: no partial run of the instruction).

    `reader(sentences, index)` returns how many sentences it consumed from
    `index` and the clause that performs them, or `None`. This is for a shape
    whose own sentences `split_effect_clauses` would cut apart (a bare "and"
    inside one sentence, or a pair that must share a gate), so the clause
    pipeline can never see it whole: the reader sees the sentences instead,
    and what sits beside it (a leading damage sentence, a trailing rider) is
    read exactly as it would be on a card without the shape.
    """
    sentences = _plain_resolution_sentences(text)
    clauses: list[TargetedClause] = []
    leftover: list[str] = []
    claimed = False

    def flush() -> bool:
        if not leftover:
            return True
        parsed = _parse_mixed_clauses(" ".join(leftover), for_spell=for_spell)
        leftover.clear()
        if parsed is None:
            return False
        clauses.extend(parsed)
        return True

    index = 0
    while index < len(sentences):
        hit = reader(sentences, index)
        if hit is None:
            leftover.append(sentences[index])
            index += 1
            continue
        if not flush():
            return None
        consumed, clause = hit
        clauses.append(clause)
        claimed = True
        index += consumed
    if not claimed or not flush():
        return None
    return clauses


# --------------------------------------------------------------------------
# Excess damage (CR 120.4a, CR 120.10): a damage spell whose next sentence
# does something with the part of the damage above what is lethal.
# --------------------------------------------------------------------------


def _excess_threshold(game: "Game", target: CardState, source: CardState | None) -> int | None:
    """What damage `target` can take before the rest is excess (CR 120.4a /
    CR 120.10), read *before* the damage is dealt: `_lethal_amount_before_
    damage`'s remaining toughness / loyalty, except that CR 120.4a makes a
    deathtouch source's lethal damage to a creature 1 (CR 702.2), so "any
    amount of damage greater than 1 is excess". `None` for a permanent that is
    neither a creature nor a planeswalker."""
    from ..combat import source_had_keyword

    threshold = _lethal_amount_before_damage(game, target)
    if threshold is None or source is None:
        return threshold
    chars = game.computed_board().of(target)
    if Type.CREATURE not in chars.types or not source_had_keyword(source, "deathtouch", game):
        return threshold
    creature_part = min(max(chars.numeric_toughness - target.damage, 0), 1)
    loyalty_part = (target.loyalty or 0) if Type.PLANESWALKER in chars.types else 0
    return max(creature_part, loyalty_part)


#: "`<source>` deals `<n>` damage to target creature[, where X is `<expr>`].
#: Excess damage is dealt to that creature's controller instead." (Flame
#: Spill, Pigment Storm, Gandalf's Sanction). The two sentences are one CR
#: 608.2c instruction: the second modifies the first's damage event (CR
#: 120.4a), so they are read whole, the same reason `_DAMAGE_THEN_EMPOWER_IF_
#: EXCESS_RE` is. `n` is a count, or CR 107.3a's announced X with or without
#: a printed definition.
_DAMAGE_THEN_EXCESS_TO_CONTROLLER_RE = re.compile(
    rf"^(?P<subject>[^.]*?) deals? {count_pattern('n', x=True)} damage to "
    r"(?P<phrase>(?:any )?target (?P<noun>creature|planeswalker|permanent)[^.,]*?)"
    r"(?:,\s*where\s+x\s+is\s+(?P<where_x>[^.]+))?\.\s*"
    r"excess damage is dealt to that (?P=noun)['’]s controller instead\.?$",
    re.IGNORECASE | re.DOTALL,
)

#: "`<source>` deals `<n>` damage to target creature. Create a number of
#: `<tokens>` equal to the amount of excess damage dealt to that creature this
#: way." (Goblin Negotiation, Hell to Pay, Lacerate Flesh); a trailing
#: reminder-text parenthetical is not part of the instruction.
_DAMAGE_THEN_TOKENS_PER_EXCESS_RE = re.compile(
    rf"^(?P<subject>[^.]*?) deals? {count_pattern('n', x=True)} damage to "
    r"(?P<phrase>(?:any )?target (?P<noun>creature|planeswalker|permanent)[^.,]*?)"
    r"(?:,\s*where\s+x\s+is\s+(?P<where_x>[^.]+))?\.\s*"
    r"create a number of (?P<desc>[^.]+?) tokens? equal to the amount of excess damage "
    r"dealt to that (?P=noun) this way\.?(?:\s*\([^)]*\))?$",
    re.IGNORECASE | re.DOTALL,
)


def _excess_damage_amount(
    n: str, where_x: str | None
) -> Callable[["Game", str, CardState, int], int] | None:
    """The damage a spell prints, as `(game, controller, spell, announced_x)`
    -> int: a count, a bare X (CR 107.3a, the announced value), or an X the
    card defines ("where X is ...", CR 107.3f)."""
    if n.strip().lower() == "x" and where_x is None:
        return lambda _game, _controller, _spell, x: x
    return _fixed_or_where_x_amount(n, where_x)


def _read_excess_damage_spell(
    match: re.Match[str],
) -> Callable[["Game", CardState], int] | None:
    """The printed damage of an excess-damage spell as a function of the
    resolving spell, or `None` when its subject, targets or amount are not
    readable (a "target ..." subject is a fight or bite, never this shape)."""
    if re.search(r"\btarget\b", match.group("subject"), re.IGNORECASE):
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    reader = _excess_damage_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None

    def amount_of(game: "Game", spell: CardState) -> int:
        controller = game.controller_of(spell).username
        return max(reader(game, controller, spell, _announced_x(game, spell)), 0)

    return amount_of


@SPELL_TEXT.rung("s18")
def _merge_damage_then_excess_to_controller_spell(effect_text: str) -> Effect | None:
    """`_DAMAGE_THEN_EXCESS_TO_CONTROLLER_RE`'s shape.

    CR 120.4a: the creature is dealt damage up to lethal (marked damage
    counted) and its controller is dealt the rest, by the same source. The
    controller is captured before the damage (CR 608.2h: last known
    information if the creature dies); CR 608.2b: with the creature an illegal
    target nothing happens at all, the controller's share included."""
    if "excess damage" not in effect_text.lower():  # cheap literal gate
        return None
    match = _DAMAGE_THEN_EXCESS_TO_CONTROLLER_RE.fullmatch(
        _strip_non_effect_preamble(effect_text).strip()
    )
    if match is None:
        return None
    amount_of = _read_excess_damage_spell(match)
    if amount_of is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = amount_of(game, spell)
        for target in game.resolve_targets(spell):
            if isinstance(target, CardState):
                _deal_with_excess_to_controller(game, target, amount, spell)

    return effect


def _deal_with_excess_to_controller(
    game: "Game", target: CardState, amount: int, source: CardState
) -> None:
    """CR 120.4a: `target` is dealt `amount` up to its threshold and its
    controller is dealt the excess. Each recipient's damage is its own event,
    so a prevention effect on one leaves the other alone."""
    controller = game.controller_of(target)
    threshold = _excess_threshold(game, target, source)
    to_target = amount if threshold is None else min(amount, threshold)
    if to_target > 0:
        game.deal_damage(target, to_target, source=source)
    if amount - to_target > 0:
        game.deal_damage(game.player(controller.username), amount - to_target, source=source)


#: "Target creature you control deals damage equal to its power to target
#: creature you don't control. If the creature you control has `<keyword>`,
#: excess damage is dealt to that creature's controller instead." (Ram
#: Through). A bite (`_parse_bite_damage_clause`'s first sentence) whose
#: second sentence is `_DAMAGE_THEN_EXCESS_TO_CONTROLLER_RE`'s modification,
#: gated on the biter's keyword as the damage is dealt (CR 614.1a: the
#: replacement applies when the damage event happens).
_BITE_THEN_EXCESS_TO_CONTROLLER_RE = re.compile(
    r"^target creature you control deals damage equal to its power to "
    r"(?P<victim>target creature you don['’]t control)\.\s*"
    r"if the creature you control has (?P<keyword>[a-z]+), "
    r"excess damage is dealt to that creature['’]s controller instead\.?$",
    re.IGNORECASE,
)


@SPELL_TEXT.rung("s18")
def _merge_bite_then_excess_to_controller_spell(effect_text: str) -> Effect | None:
    """`_BITE_THEN_EXCESS_TO_CONTROLLER_RE`'s shape.

    The biter is the target `spell`'s controller controls, the victim the one
    they do not (the same split `_resolve_bite_damage` makes); CR 608.2b: with
    either gone nothing is dealt. The keyword is read off the biter as the
    damage is dealt (CR 613.5), by last known information if it has left (CR
    608.2h); CR 120.4a deathtouch counts through the biter as the source."""
    if "excess damage" not in effect_text.lower():  # cheap literal gate
        return None
    match = _BITE_THEN_EXCESS_TO_CONTROLLER_RE.fullmatch(
        _strip_non_effect_preamble(effect_text).strip()
    )
    if match is None:
        return None
    if not _targets_understood("target creature you control", count_agnostic=False):
        return None
    if not _targets_understood(match.group("victim"), count_agnostic=True):
        return None
    keyword = match.group("keyword").lower()

    def effect(game: "Game", spell: CardState) -> None:
        from ..combat import source_had_keyword

        controller = game.controller_of(spell).username
        targets = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        mine = [t for t in targets if game.controller_of(t).username == controller]
        theirs = [t for t in targets if game.controller_of(t).username != controller]
        if not mine or not theirs:
            return
        biter, victim = mine[0], theirs[0]
        amount = game.power_of(biter) or 0
        if amount <= 0:
            return
        if source_had_keyword(biter, keyword, game):
            _deal_with_excess_to_controller(game, victim, amount, biter)
        else:
            game.deal_damage(victim, amount, source=biter)

    return effect


@SPELL_TEXT.rung("s18")
def _merge_damage_then_tokens_per_excess_spell(effect_text: str) -> Effect | None:
    """`_DAMAGE_THEN_TOKENS_PER_EXCESS_RE`'s shape.

    CR 120.10: the excess is what the damage dealt *actually* was (prevention
    already applied) above the threshold read before it landed, so prevented
    or absorbed damage makes no tokens; the caster creates them."""
    if "excess damage" not in effect_text.lower():  # cheap literal gate
        return None
    match = _DAMAGE_THEN_TOKENS_PER_EXCESS_RE.fullmatch(
        _strip_non_effect_preamble(effect_text).strip()
    )
    if match is None:
        return None
    amount_of = _read_excess_damage_spell(match)
    create = _token_creator_for_count(match.group("desc"))
    if amount_of is None or create is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = amount_of(game, spell)
        for target in game.resolve_targets(spell):
            if not isinstance(target, CardState):
                continue
            threshold = _excess_threshold(game, target, spell)
            dealt = game.deal_damage(target, amount, source=spell)
            if threshold is not None:
                create(game, spell, dealt - threshold)

    return effect


#: "`<source>` deals `<n>` damage to `<target>`. You gain life equal to the
#: excess damage dealt this way." (Razor Rings). The same two-sentence
#: instruction as `_DAMAGE_THEN_TOKENS_PER_EXCESS_RE` (CR 608.2c), with the
#: target phrase left open - "target attacking or blocking creature" is not a
#: bare "target creature" - and the payoff a life gain.
_DAMAGE_THEN_LIFE_PER_EXCESS_RE = re.compile(
    rf"^(?P<subject>[^.]*?) deals? {count_pattern('n', x=True)} damage to "
    r"(?P<phrase>(?:any )?target [^.]*?)"
    r"(?:,\s*where\s+x\s+is\s+(?P<where_x>[^.]+))?\.\s*"
    r"you gain life equal to the (?:amount of )?excess damage dealt "
    r"(?:to that [a-z]+ )?this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s18")
def _merge_damage_then_life_per_excess_spell(effect_text: str) -> Effect | None:
    """`_DAMAGE_THEN_LIFE_PER_EXCESS_RE`'s shape.

    CR 120.10: the excess is what the damage dealt *actually* was (prevention
    already applied, CR 615.6) above the threshold read before it landed, so
    prevented or absorbed damage gains nothing; with several targets the
    excesses add up, and a player has no lethal damage, so damage to one is
    never excess. Nothing is gained for 0 excess; the caster gains the life."""
    if "excess damage" not in effect_text.lower():  # cheap literal gate
        return None
    match = _DAMAGE_THEN_LIFE_PER_EXCESS_RE.fullmatch(
        _strip_non_effect_preamble(effect_text).strip()
    )
    if match is None:
        return None
    amount_of = _read_excess_damage_spell(match)
    if amount_of is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        amount = amount_of(game, spell)
        excess = 0
        for target in game.resolve_targets(spell):
            if not isinstance(target, CardState):
                game.deal_damage(target, amount, source=spell)
                continue
            threshold = _excess_threshold(game, target, spell)
            dealt = game.deal_damage(target, amount, source=spell)
            if threshold is not None:
                excess += max(dealt - threshold, 0)
        if excess > 0:
            game.gain_life(game.controller_of(spell), excess)

    return effect


#: "Target creature you control fights target creature an opponent controls. If
#: the creature the opponent controls is dealt excess damage this way, add that
#: much {R}." (The Last Agni Kai) - a fight (CR 701.14a) or a bite whose victim
#: is told apart by who controls it, then a payoff for the part of the damage the
#: victim could not use. The payoff sentence modifies the meaning of the first
#: (CR 608.2c), so they are one instruction read together.
_FIGHT_OR_BITE_RE = re.compile(
    r"^target creature you control (?:(?P<fight>fights)|deals damage equal to its power to) "
    r"target creature (?P<ctrl>an opponent controls|you don['’]t control)\.?$",
    re.IGNORECASE,
)
_EXCESS_ADD_MANA_RE = re.compile(
    r"^if the creature (?:the opponent controls|an opponent controls|you don['’]t control) "
    r"is dealt excess damage this way, add that much (?P<mana>\{[wubrgc]\})\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_fight_or_bite_then_excess_mana_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_FIGHT_OR_BITE_RE`'s sentence plus `_EXCESS_ADD_MANA_RE`'s, among
    `text`'s sentences.

    CR 120.4a: the excess is the damage above what is lethal for the victim,
    read before the damage lands (`_excess_threshold`, which also counts a
    deathtouch source's lethal damage as 1), and CR 120.10's "dealt" is what
    actually landed (`Game.deal_damage`'s return), so prevented damage makes no
    excess. The mana goes to the spell's controller (CR 106.4). A fight needs
    both creatures still on the battlefield and still creatures (CR 701.14b);
    a bite needs only its biter and its victim, as `_resolve_bite_damage`."""
    if "excess damage this way" not in text.lower() or not for_spell:
        return None

    def reader(sentences: list[str], index: int) -> tuple[int, TargetedClause] | None:
        if index + 1 >= len(sentences):
            return None
        action = _FIGHT_OR_BITE_RE.fullmatch(sentences[index].strip())
        payoff = _EXCESS_ADD_MANA_RE.fullmatch(sentences[index + 1].strip())
        if action is None or payoff is None:
            return None
        if not _targets_understood("target creature you control", count_agnostic=False):
            return None
        if not _targets_understood(f"target creature {action.group('ctrl')}", count_agnostic=True):
            return None
        fights = action.group("fight") is not None
        color = Color(payoff.group("mana").strip("{}").upper())

        def effect(game: "Game", spell: "StackObject") -> None:
            from ..conditions.history import record_fight

            controller = game.controller_of(spell)
            targets = [
                target
                for target in game.resolve_targets(spell)
                if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ]
            mine = [t for t in targets if game.controller_of(t).username == controller.username]
            theirs = [t for t in targets if game.controller_of(t).username != controller.username]
            if not mine or not theirs:
                return
            biter, victim = mine[0], theirs[0]
            if fights and not (
                game.characteristics_of(biter).is_creature
                and game.characteristics_of(victim).is_creature
            ):
                return  # CR 701.14b
            threshold = _excess_threshold(game, victim, biter)
            power = game.power_of(biter) or 0
            counter_power = game.power_of(victim) or 0
            dealt = game.deal_damage(victim, power, source=biter)
            if fights:
                game.deal_damage(biter, counter_power, source=victim)
                record_fight(game, biter, victim)
            excess = 0 if threshold is None else max(dealt - threshold, 0)
            if excess > 0:
                pool = game.mana_pool_receiving(controller.username)
                for _ in range(excess):
                    pool.add(color)

        return 2, effect

    return _clauses_around_sentences(text, reader, for_spell=for_spell)


def _merge_each_player_may_discard_hand_and_draw_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Rejoins `split_effect_clauses`'s bare-"and" cut of `_EACH_PLAYER_MAY_
    DISCARD_HAND_DRAW_RE`'s shape - "discard their hand" / "draw seven
    cards." are one CR 608.2c instruction, not two, the same reason `_merge_
    target_player_draws_and_loses_life_clauses` exists."""
    if index + 1 >= len(clauses):
        return None
    pair = f"{clauses[index].strip()} and {clauses[index + 1].strip()}."
    effect = _parse_each_player_may_discard_hand_and_draw_clause(pair, for_spell=for_spell)
    if effect is None:
        return None
    return 2, effect  # type: ignore[return-value]


def _merge_target_player_draws_and_loses_life_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Rejoins `split_effect_clauses`'s bare-"and" cut of `_TARGET_PLAYER_
    DRAWS_AND_LOSES_LIFE_RE`'s shape - see that regex's own docstring."""
    if index + 1 >= len(clauses):
        return None
    pair = f"{clauses[index].strip()} and {clauses[index + 1].strip()}."
    effect = _parse_target_player_draws_and_loses_life_clause(pair, for_spell=for_spell)
    if effect is None:
        return None
    return 2, effect  # type: ignore[return-value]


#: "you may discard a card"/"you may discard up to N cards"/"you may discard
#: any number of cards" - Formidable Speaker's own first clause ("a card"),
#: and Fable of the Mirror-Breaker II's own "you may discard up to two
#: cards" - CR 118.12's optional cost half of "[Do something]. If [a player]
#: does, ...", the same quantity grammar `_DISCARD_A_CARD_RE` reads for the
#: unconditional shape.
#:
#: "you may" is optional in the pattern: Territorial Kavu's own mode and
#: Shadow of the Goblin's "discard a card. If you do, draw a card." print the
#: mandatory form, whose "if you do" asks whether the player started to pay
#: (CR 118.12) - a player with an empty hand never does.
_MAY_DISCARD_N_CARDS_RE = re.compile(
    rf"^(?P<may>you may )?discards? "
    rf"(?:(?P<any>any number of)|(?:(?P<upto>up to )?(?P<n>{AMOUNT})))\s+cards?$",
    re.IGNORECASE,
)
#: "if you do, <consequence>" - CR 118.12's own consequence clause, split off
#: from `_MAY_DISCARD_N_CARDS_RE`'s clause by `_prepare_effect_clauses`'s
#: period splitting the same way `_MAY_SACRIFICE_IF_YOU_DO_RE`'s own two
#: halves would be if that shape were not read as one whole-text regex
#: instead - this one has to be a multi-clause merge, since "you may discard
#: a card. If you do, search ..." reaches `_parse_mixed_clause` as two
#: already-split clauses.
_IF_YOU_DO_RE = re.compile(r"^if you do,\s*(?P<consequence>.+)$", re.IGNORECASE | re.DOTALL)

#: "`<counted instruction>`. If you do, `<consequence>`." (CR 118.12) where
#: whether "you did" is how many the instruction moved - Necrodominance's
#: "You may pay any amount of life. If you do, draw that many cards." Paying
#: zero life is not paying (CR 119.4), so the consequence runs only on a
#: count above zero, and reads that count through `that_many`.
_COUNTED_ACTION_RE = re.compile(r"^(?:you may )?(?:pay any amount of life|mills? )", re.IGNORECASE)


def _merge_counted_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_COUNTED_ACTION_RE`'s instruction, then "If you do, `<player
    clause>`" - both read by the ordinary player-clause parsers."""
    if index + 1 >= len(clauses) or not _COUNTED_ACTION_RE.match(clauses[index].strip()):
        return None
    action = _parse_optional_player_clause(clauses[index].strip())
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if action is None or if_match is None:
        return None
    consequence = parse_clause_effect(if_match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        game.record_count(None)
        action(game, player, source, source_id_of(stack_object))
        if (game.recorded_count() or 0) > 0:
            consequence(game, player, source, source_id_of(stack_object))

    return 2, effect


#: "Return up to one other target permanent you control to its owner's
#: hand. If you do, put a +1/+1 counter on this creature." - Mirkwood
#: Nurturer's own enters trigger. CR 115.6's "up to one" target may choose
#: zero, and CR 118.12's "if you do" here asks whether a target was actually
#: returned - a targeted instruction, not a cost, so `Game.record_count` (the
#: same "how many did the instruction actually move" channel `_merge_counted_
#: if_you_do_clauses` just above already reads for its own counted player
#: clauses) is read off the return itself rather than off a payment decision.
#: The consequence is read through the ordinary ability-clause dispatcher
#: (`parse_mixed_effect`/`parse_mixed_effect_for_spell`), not `parse_clause_
#: effect`, because it needs the resolving ability's own source ("this
#: creature", CR 700.7) - `_parse_put_counters_on_self_clause`'s own shape,
#: reachable through the general dispatcher but not through `parse_clause_
#: effect`'s narrower no-object grammar.
def _merge_return_target_then_if_you_do_self_counter_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    if index + 1 >= len(clauses):
        return None
    match = _RETURN_TARGET_RE.fullmatch(clauses[index].strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True, battlefield_only=False):
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence_text = if_match.group("consequence").strip()
    consequence = (
        parse_mixed_effect_for_spell(consequence_text)  # type: ignore[assignment]
        if for_spell
        else parse_mixed_effect(consequence_text)
    )
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        moved = 0
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState):
                    game.return_to_hand(target)
                    moved += 1
        if moved > 0:
            consequence(game, stack_object)  # type: ignore[arg-type]

    return 2, effect


#: "Return it to its owner's hand. If you do, `<consequence>`." - Riders of
#: the Mark's end step trigger ("... if this creature attacked this turn,
#: return it to its owner's hand. If you do, create a number of 1/1 white
#: Human Soldier creature tokens equal to its toughness."). CR 118.12's "if
#: you do" asks whether the return happened; the self-return is whichever of
#: the two self-return clause parsers reads the first sentence.
_RETURN_SELF_TO_HAND_LEAD_RE = re.compile(
    r"^return (?:it|this (?:creature|permanent|artifact|enchantment|land|planeswalker))"
    r" to its owner'?s hand\.?$",
    re.IGNORECASE,
)

#: "Sacrifice this creature. If you do, `<consequence>`." - Flame-Kin War
#: Scout's enters trigger. CR 701.21a: only a permanent its controller still
#: controls on the battlefield can be sacrificed, so "if you do" is false
#: once it has left or changed hands; "this creature" in the consequence is
#: then the sacrificed object as it last existed (CR 113.7a).
_SACRIFICE_SELF_LEAD_RE = re.compile(
    r"^sacrifice this (?:creature|permanent|artifact|enchantment|land|planeswalker)\.?$",
    re.IGNORECASE,
)


def _sacrifice_own_source(game: "Game", ability: AbilityOnStack) -> None:
    """Sacrifice the ability's source if its controller still controls it on
    the battlefield (CR 701.21a); otherwise nothing happens."""
    source = ability.source(game)
    if (
        source is not None
        and source.zone is Zone.BATTLEFIELD
        and source.controller == ability.controller
    ):
        game.sacrifice(source)


def _merge_return_self_then_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_RETURN_SELF_TO_HAND_LEAD_RE` or `_SACRIFICE_SELF_LEAD_RE`, then "If
    you do, `<consequence>`" - the consequence runs only when the source
    really went to its owner's hand or graveyard (CR 118.12), and "its" in it
    is the moved object as it last existed on the battlefield (CR 608.2h)."""
    if for_spell or index + 1 >= len(clauses):
        return None
    first = clauses[index].strip()
    sacrificing = _SACRIFICE_SELF_LEAD_RE.fullmatch(first) is not None
    if sacrificing:
        returning: Any = _sacrifice_own_source
        destination = Zone.GRAVEYARD
    else:
        if _RETURN_SELF_TO_HAND_LEAD_RE.fullmatch(first) is None:
            return None
        returning = _parse_return_self_to_owners_hand_clause(
            first, for_spell=False
        ) or _parse_return_dead_self_to_hand_clause(first.rstrip("."), for_spell=False)
        if returning is None:
            return None
        destination = Zone.HAND
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence_text = if_match.group("consequence").strip()
    stat_match = _TOKENS_EQUAL_TO_ITS_STAT_RE.fullmatch(consequence_text)
    template = None
    consequence = None
    if stat_match is not None:
        template = _parse_token_clause(
            f"create a {stat_match.group('desc')} token", for_spell=False
        )
        if template is None:
            return None
    else:
        consequence = parse_mixed_effect(consequence_text)
        if consequence is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        characteristics = game.characteristics_of(source)
        returning(game, stack_object)
        moved = game.find_by_id(source.id)
        if not isinstance(moved, CardState) or moved.zone is not destination:
            return
        if template is not None:
            assert stat_match is not None
            stat = (
                characteristics.power
                if stat_match.group("stat").lower() == "power"
                else characteristics.toughness
            )
            for _ in range(max(stat or 0, 0)):
                template(game, stack_object)
            return
        assert consequence is not None
        consequence(game, stack_object)  # type: ignore[arg-type]

    return 2, effect


#: The processor cost (CR 118.12's "[do something]" half): "you may put a
#: card an opponent owns from exile into that player's graveyard" (Wasteland
#: Strangler, Murk Strider, Mind Raker, Ulamog's Reclaimer, Ruin Processor)
#: and the counted "put two cards your opponents own from exile into their
#: owners' graveyards" (Blight Herder). "you may" is optional in the pattern:
#: the mandatory spelling asks the same CR 118.12 "if you do" of whether the
#: player could start to pay.
_PROCESS_EXILED_CARD_RE = re.compile(
    r"^(?P<may>you may )?put "
    rf"(?:an? card an opponent owns|(?P<n>{COUNT}) cards (?:your opponents|an opponent) own) "
    r"from exile into (?:that player'?s|their owners'?|its owner'?s) graveyards?$",
    re.IGNORECASE,
)


def _merge_process_exile_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_PROCESS_EXILED_CARD_RE`, then "If you do, `<clause>`" - the processor
    template, read as one CR 118.12 instruction: the put is a cost paid as the
    ability resolves, and the payoff runs only if it was paid.

    The payoff is read by `_parse_mixed_clause`, so it may target ("target
    creature gets -3/-3 until end of turn", "return target creature to its
    owner's hand"). Its target was chosen as the ability went on the stack
    (CR 603.3d, 601.2c), and CR 608.2b's recheck of it happens before any of
    this runs - an ability whose only target is gone never reaches here, so
    no card is processed for nothing.
    """
    if index + 1 >= len(clauses):
        return None
    cost = _PROCESS_EXILED_CARD_RE.fullmatch(clauses[index].strip().rstrip("."))
    if cost is None:
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence_text = if_match.group("consequence").strip().rstrip(".")
    consequence = _parse_mixed_clause(consequence_text, for_spell=for_spell)
    if consequence is None:
        consequence = _targeted_layer_consequence(consequence_text)
    if consequence is None:
        return None
    count = parse_count(cost.group("n")) if cost.group("n") else 1
    if count is None or count < 1:
        return None
    optional = cost.group("may") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        piles = _processable_exile_piles(game, player.username)
        if sum(len(pile) for pile in piles) < count:
            return  # CR 118.12: the player can't, so they didn't.
        if optional and not game.may(
            player,
            "put a card an opponent owns from exile into that player's graveyard",
            source=source,
            source_id=source_id,
        ):
            return
        if _process_exiled_cards(game, player, count, source=source, source_id=source_id):
            consequence(game, stack_object)

    return 2, effect


#: Converge (CR 207.2c): Transcendent Archaic's own ETB trigger "you may draw
#: X cards, where X is the number of colors of mana spent to cast this
#: spell. If you draw one or more cards this way, discard two cards." Unlike
#: Uncover the Moon-Letters' own "may draw ... If you do, discard" pair just
#: below (whose X belongs to a *different*, still-on-stack spell the cast
#: trigger watched), this X belongs to the entering creature itself -
#: `AbilityOnStack.source`, already resolved onto the battlefield by the
#: time this ETB trigger runs - so it is read off `machines/converge.
#: colors_of_mana_spent(game, source)` rather than off `event.subject_id`.
#: The consequence is conditioned on cards actually having been drawn
#: ("this way", CR 608.2c anaphora), not merely on the "may" having been
#: accepted - a hand-size-zero-cards-drawn corner (an empty library) still
#: has to skip the discard, which is why `drawn` is checked rather than
#: `amount` alone. The discard count is read, not fixed at two, so a future
#: printing sharing this exact shape with a different discard count is
#: covered for free.
_CONVERGE_MAY_DRAW_CLAUSE_RE = re.compile(
    r"^you may draw x cards,?\s*where x is the number of colors of mana spent to cast "
    r"this (?:spell|creature)\.?$",
    re.IGNORECASE,
)
_IF_YOU_DREW_CARDS_THIS_WAY_DISCARD_RE = re.compile(
    rf"^if you draw (?:one or more|any) cards? this way,\s*discard (?P<n>{COUNT}) cards?\.?$",
    re.IGNORECASE,
)


def _merge_converge_may_draw_then_discard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_CONVERGE_MAY_DRAW_CLAUSE_RE` followed by `_IF_YOU_DREW_CARDS_THIS_
    WAY_DISCARD_RE`. Ability-only: this X is CR 601.2h's own count on the
    resolving *ability's own source*, which only an `AbilityOnStack` has -
    nothing casts itself, so no spell reaches this shape at all.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    if _CONVERGE_MAY_DRAW_CLAUSE_RE.fullmatch(clauses[index].strip()) is None:
        return None
    discard_match = _IF_YOU_DREW_CARDS_THIS_WAY_DISCARD_RE.fullmatch(clauses[index + 1].strip())
    if discard_match is None:
        return None
    discard_amount = parse_count(discard_match.group("n"))
    if discard_amount is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        player = game.controller_of(ability)
        source = ability.source(game)
        amount = colors_of_mana_spent(game, source) if source is not None else 0
        if amount <= 0:
            return
        if not game.may(
            player,
            f"draw {amount} cards",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        drawn = game.draw_cards(player.username, amount)
        if not drawn:
            return
        needed = min(discard_amount, len(player.hand))
        if needed <= 0:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"discard {needed} card(s)",
                source=ability.source_name,
                amount=needed,
                cards=tuple(state.id for state in player.hand),
                source_id=source_id_of(ability),
            )
        )
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in player.hand}
        game.discard_cards(
            player.username,
            [by_id[card_id] for card_id in chosen_ids],
            source=ability.source_name,
        )

    return 2, effect


#: Uncover the Moon-Letters' whole cast trigger: "Whenever you cast a
#: noncreature spell, you may draw X cards, where X is the amount of mana
#: spent to cast that spell. If you do, discard two cards." X is not CR
#: 107.3a's announced X (the trigger's own source carries no {X} at all) - it
#: is CR 601.2h's own mana-spent total on the *cast spell* the trigger
#: watched (`AbilityOnStack.event`'s own subject), read off that spell's
#: `CastRecord.mana_spent` the same way a self-referential "no mana was spent
#: to cast it" intervening *if* already does in `machines/triggers.py`, just
#: for a different object than the ability's own source.
_DRAW_MANA_SPENT_CLAUSE_RE = re.compile(
    r"^you may draw x cards,? where x is the amount of mana spent to cast that spell\.?$",
    re.IGNORECASE,
)


def _merge_draw_mana_spent_then_discard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_DRAW_MANA_SPENT_CLAUSE_RE` followed by `_IF_YOU_DO_RE` - see the
    banner comment above. Never a spell's own shape (nothing casts itself),
    so `for_spell` is not read; the parameter is kept only for the shared
    merger signature every caller in this dispatch loop already uses.
    """
    if index + 1 >= len(clauses):
        return None
    if _DRAW_MANA_SPENT_CLAUSE_RE.fullmatch(clauses[index].strip()) is None:
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence = parse_clause_effect(if_match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        event = getattr(stack_object, "event", None)
        spent = 0
        if event is not None and event.subject_id is not None:
            cast_spell = game.find_by_id(event.subject_id)
            if cast_spell is not None:
                record = game.cast_record_of(cast_spell)
                if record is not None:
                    spent = sum(record.mana_spent.values())
        if not game.may(player, f"draw {spent} cards", source=source, source_id=source_id):
            return
        if spent:
            game.draw_cards(player.username, spent)
        consequence(game, player, source, source_id)

    return 2, effect


def _merge_may_then_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """CR 118.12's general shape: "You may `<clause>`. If you do,
    `<clause>`." - Smuggler's Copter's own attack/block trigger ("you may
    draw a card. If you do, discard a card.") and Riddlesmith's identical
    cast trigger.

    A catch-all over `_parse_you_may_clause`'s own optional-clause reading
    (any action `parse_clause_effect` already understands) paired with a
    plain `parse_clause_effect` consequence, tried only after every other
    "you may `<verb>`. If you do, ..." merger in this loop - the discard-
    flavoured `_merge_may_discard_if_you_do_clauses`, the counted
    `_merge_counted_if_you_do_clauses`, and (earlier still in the dispatch
    that calls this one, `_ability_effect_or_notice`/`_spell_effect_or_
    notice`) the whole-text sacrifice, energy and mana readers - so none of
    those more specific shapes' own fingerprint winners change: each of
    them still catches its own cards before this ever sees the clause.

    CR 118.12: "The 'If [a player] does...' clause checks whether the
    player chose to pay an optional cost ..., regardless of what events
    actually occurred." That is read literally here - the `Game.may`
    question is asked exactly once, by this merger itself rather than
    through `_parse_optional_player_clause`'s own wrapped effect (which
    would ask it a second time with no way to read the first answer back),
    and the consequence runs whenever the answer is "yes", never re-checked
    against whatever the accepted action actually did (an empty library on
    Smuggler's Copter's own "you may draw a card" still discards, exactly
    as paper Magic does).
    """
    if index + 1 >= len(clauses):
        return None
    you_may = _parse_you_may_clause(clauses[index].strip())
    if you_may is None:
        return None
    inner_text, inner, default = you_may
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence = parse_clause_effect(if_match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if not game.may(
            player, inner_text, source=source, source_id=source_id_of(stack_object), default=default
        ):
            return
        inner(game, player, source, source_id_of(stack_object))
        consequence(game, player, source, source_id_of(stack_object))

    return 2, effect


#: "Choose a color." then "Target player adds three mana of the chosen color
#: for each artifact sacrificed this way." (Radiant Lotus) - CR 608.2d's
#: choice, then CR 106.4's add, the second sentence naming the first's
#: answer. Not a mana ability: it targets (CR 605.1a), so it resolves from
#: the stack like any other ability.
_CHOOSE_A_COLOR_RE = re.compile(r"^choose a colou?r$", re.IGNORECASE)
_ADD_MANA_OF_THE_CHOSEN_COLOR_RE = re.compile(
    rf"^(?P<who>target player adds|you add|add) (?P<n>{COUNT}) mana of the chosen colou?r"
    r"(?: for each (?P<each>.+?))?\.?$",
    re.IGNORECASE,
)


def _merge_choose_a_color_then_add_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_CHOOSE_A_COLOR_RE` followed by `_ADD_MANA_OF_THE_CHOSEN_COLOR_RE`,
    as one instruction. "For each `<phrase>`" is `_for_each_multiplier`'s,
    read once as it resolves (CR 608.2h)."""
    if index + 1 >= len(clauses) or not _CHOOSE_A_COLOR_RE.fullmatch(clauses[index].strip()):
        return None
    match = _ADD_MANA_OF_THE_CHOSEN_COLOR_RE.fullmatch(clauses[index + 1].strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    each = match.group("each")
    multiplier = _for_each_multiplier(each) if each is not None else None
    if each is not None and multiplier is None:
        return None
    targets_a_player = match.group("who").lower().startswith("target")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if targets_a_player:
            players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
            if not players:
                return
            receiver = players[0]
        else:
            receiver = controller
        color = _choose_a_color(
            game, controller, source, "choose a color", source_id=source_id_of(stack_object)
        )
        total = amount * (
            multiplier(game, controller.username, source_id_of(stack_object)) if multiplier else 1
        )
        if total > 0:
            receiver.mana_pool.add(color, total)

    return 2, effect


def _merge_may_discard_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Formidable Speaker's ETB trigger: "you may discard a card. If you do,
    search your library for a creature card, reveal it, put it into your
    hand, then shuffle." (CR 118.12's discard-flavoured cousin of
    `_parse_conditional_sacrifice_clause`'s sacrifice.) Fable of the
    Mirror-Breaker II's "you may discard up to two cards. If you do, draw
    that many cards." is the same shape with a non-exact quantity and a plain
    player clause for its consequence (`parse_clause_effect`), whose "that
    many" reads the count `_discard_cards` recorded (`that_many`).

    Reuses `_parse_sacrifice_consequence` outright for the "if you do" half:
    that function's own two shapes (a magnitude-threaded pair of clauses, or
    a plain mandatory search) are not sacrifice-specific in what they read,
    only in the docstring's own worked examples - Formidable Speaker's
    consequence is exactly `_SEARCH_AND_PUT_RE`'s shape, which
    `_parse_sacrifice_consequence` already tries. The `power` argument every
    consequence function takes is `None` here, since a discard produces no
    magnitude the way a sacrifice's power does, and `_search_and_place_for`'s
    own effect never reads it.
    """
    if index + 1 >= len(clauses):
        return None
    discard_match = _MAY_DISCARD_N_CARDS_RE.fullmatch(clauses[index].strip())
    if discard_match is None:
        return None
    if discard_match.group("any") is not None:
        amount: int | None = None
        exact = False
    else:
        amount = parse_count(discard_match.group("n"))
        if amount is None:
            return None
        exact = discard_match.group("upto") is None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence_text = if_match.group("consequence").strip()
    consequence = _parse_sacrifice_consequence(consequence_text)
    player_clause = None if consequence is not None else parse_clause_effect(consequence_text)
    if consequence is None and player_clause is None:
        return None

    optional = discard_match.group("may") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        needed = amount if amount is not None else len(player.hand)
        prompt = (
            "discard a card"
            if amount == 1 and exact
            else f"discard {'up to ' if not exact else ''}{needed} card(s)"
        )
        decision = Decision(
            kind=DecisionKind.MAY,
            player=player.username,
            prompt=prompt,
            source=source,
            affirmative_is_legal=bool(player.hand),
            source_id=source_id_of(stack_object),
        )
        if optional and not game.ask(decision):
            return
        discarded = _discard_cards(
            game, player, needed, source, source_id=source_id_of(stack_object), exact=exact
        )
        if not discarded:
            return
        if player_clause is not None:
            player_clause(game, player, source, source_id_of(stack_object))
            return
        assert consequence is not None
        consequence(game, player, None, source, source_id_of(stack_object))

    return 2, effect


#: "exile it" / "exile this artifact" - a mandatory action on the ability's
#: own source, CR 118.12's "[Do something]." half of "[Do something]. If [a
#: player] does, [effect]." (Mazemind Tome's state trigger: "exile it. If you
#: do, you gain 4 life.")
_EXILE_SELF_ACTION_RE = re.compile(r"^exile (?:it|this [a-z]+)$", re.IGNORECASE)


def _merge_exile_self_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Exile it. If you do, `<consequence>`." on a triggered or activated
    ability, CR 118.12: the exile is a mandatory cost paid as the ability
    resolves, and "if you do" asks whether it was paid.

    The source can only be exiled if it is still where the ability left it; a
    source that has already changed zones is a new object (CR 400.7) the
    ability cannot find, so nothing is exiled and the consequence does not
    happen. Ability-only, like `_parse_exile_dead_self_clause`: a resolving
    spell has no source permanent to exile.
    """
    if for_spell or index + 1 >= len(clauses):
        return None
    if _EXILE_SELF_ACTION_RE.fullmatch(clauses[index].strip()) is None:
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    consequence = _parse_mixed_clause(if_match.group("consequence").strip(), for_spell=False)
    if consequence is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.exile_permanent(source)
        if source.zone is not Zone.EXILE:
            return
        consequence(game, stack_object)

    return 2, effect


# --------------------------------------------------------------------------
# Wave W1's third primitive: look at the top N cards and split them between
# two destinations, general past `Game.scry`/`Game.surveil`'s own fixed
# pair - `Game.look_at_top_and_split`, next to `scry`/`surveil` themselves in
# `models/game.py`. Duskwatch Recruiter's `{2}{G}` ability is the vehicle:
# "Look at the top three cards of your library. You may reveal a creature
# card from among them and put it into your hand. Put the rest on the bottom
# of your library in any order." - a creature-only, at-most-one cousin of
# scry's "any number, any card" split, with "to hand"/"to the bottom" in
# place of scry's "to the bottom"/"back on top".
# --------------------------------------------------------------------------

#: "look at the top <count> cards of your library" - Duskwatch Recruiter's
#: own first clause.
_LOOK_AT_TOP_N_CARDS_RE = re.compile(
    rf"^look at the top (?P<count>{COUNT}) cards? of your library$", re.IGNORECASE
)
#: "you may reveal a/an/up to N/any number of <quality> card(s) from among
#: them" - the second clause, naming which of the looked-at cards may be
#: taken. Reality Heist and Domri, Chaos Bringer's own -3 print "up to two";
#: Lead the Stampede prints "any number of" (CR 107.1c). Duskwatch Recruiter's
#: bare "a" stays readable as `QUANTITY`'s own fixed-one case.
#: A mana value ceiling after the noun - Gavony Dawnguard's and Recruitment
#: Officer's "a creature card with mana value 3 or less" - is read too, the
#: same `max_mv` bound `_bounded_quality_matcher` applies to a search.
_MAY_REVEAL_FROM_AMONG_THEM_RE = re.compile(
    rf"^you may reveal {quantity_pattern('n')} "
    rf"(?:(?P<quality>.+?) cards?(?: with mana value (?P<max_mv>\d+) or less)?"
    # "a card that's exactly two colors" (Invasion of Ravnica // Guildpact
    # Paragon) - the same quality, spelled as a post-nominal relative clause
    # (CR 105.2's color count) rather than the pre-nominal adjective every
    # other printing above uses. `_relative_quality_matcher` reads the
    # clause; `quality`/`max_mv` are both `None` for this branch, so nothing
    # downstream needs to tell the two shapes apart except by which group
    # actually filled in.
    rf"|cards? that'?s (?P<rel_quality>.+?))"
    r" from among them$",
    re.IGNORECASE,
)
#: "put it into your hand" / "put them into your hand" / "put the revealed
#: cards into your hand" - `_CLAUSE_SEPARATOR`'s own "and" split of the second
#: sentence's tail; "them" is Reality Heist's own plural for a quantity that
#: can take more than one, "the revealed cards" is Lead the Stampede's.
_PUT_IT_OR_THEM_INTO_YOUR_HAND_RE = re.compile(
    r"^put (?:it|them|that card|the revealed cards) into your hand$", re.IGNORECASE
)
#: "put the rest on the bottom of your library in any order" - Duskwatch
#: Recruiter's own third sentence - **or** "... in a random order", which
#: Monumental Henge, Narset, Parter of Veils and Thundertrap Trainer print for
#: the identical run of four clauses. Only this one phrase differed, and the
#: whole family was refused for it, so all three cards did nothing.
#:
#: The two tails are told apart by the `random` group, because they are not
#: the same instruction. "In any order" is the controller's own free
#: arrangement (CR 401.4: "If an effect puts two or more cards in a specific
#: position in a library at the same time, the owner of those cards may
#: arrange them in any order"), so `Game.look_at_top_and_split`'s answered
#: order is used as given. "In a random order" is nobody's choice - and it is
#: still not CR 701.24a's shuffle ("To shuffle a library or a face-down pile
#: of cards, randomize the cards within it so that no player knows their
#: order"): that verb is not printed here, so nothing that keys off a shuffle
#: may fire. The randomisation is seeded off `Game.shuffle_seed` and the
#: running `shuffles_performed` counter, exactly as
#: `puts_graveyard_on_bottom_of_library` (Endurance) and
#: `_parse_look_top_n_may_battlefield_creature_bonus_clause` (Turntimber
#: Symbiosis) already do for their own "in a random order" tails.
_PUT_REST_ON_BOTTOM_ANY_ORDER_RE = re.compile(
    r"^put the rest on the bottom of your library in (?:(?P<random>a random)|any) order$",
    re.IGNORECASE,
)


def _merge_look_top_reveal_to_hand_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Duskwatch Recruiter's whole `{2}{G}` ability, read as one anaphoric run
    of four clauses (`_CLAUSE_SEPARATOR` cuts the second sentence's own
    "... among them and put it into your hand" in two at "and") rather than
    four independent ones - "them" is the top `count` cards the first clause
    looked at, "it" is whichever one the second clause chose, and "the rest"
    is whatever is left of that same set.

    `Game.look_at_top_and_split` asks the generic CR 608.2d split question
    with no notion of "only a creature card" or "at most one" built in - both
    are this card's own restriction, not the primitive's - so this function
    enforces them itself once the answer comes back: a `moved` half with more
    than one card, or one that fails the quality predicate, is CR 608.2d's
    "can't choose an option that's illegal", raised the same way `Game.ask`
    already raises for an illegal `CHOOSE_TARGETS`/`CHOOSE_CARDS` answer.
    """
    if index + 3 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    reveal_match = _MAY_REVEAL_FROM_AMONG_THEM_RE.fullmatch(clauses[index + 1].strip())
    if reveal_match is None:
        return None
    quantity = parse_quantity(reveal_match.group("n"))
    # CR 107.1c's "any number of" and a printed "up to N" are both read; an
    # unreadable quantifier (X, "that many" - no antecedent here) fails
    # closed rather than guessing.
    if quantity is None or quantity.source not in (QuantitySource.FIXED, QuantitySource.ANY_NUMBER):
        return None
    rel_quality = reveal_match.group("rel_quality")
    if rel_quality is not None:
        # "a card that's exactly two colors" (Invasion of Ravnica //
        # Guildpact Paragon) - the relative-clause spelling
        # `_bounded_quality_matcher`'s pre-nominal-adjective regex branch
        # never matches at all.
        matches = _relative_quality_matcher(rel_quality)
        if matches is None:
            return None
        noun_phrase_singular = f"card that's {rel_quality.strip()}"
        noun_phrase_plural = f"cards that are {rel_quality.strip()}"
    else:
        matches = _bounded_quality_matcher(
            reveal_match.group("quality"), reveal_match.group("max_mv")
        )
        quality_description = reveal_match.group("quality").strip()
        noun_phrase_singular = f"{quality_description} card"
        noun_phrase_plural = f"{quality_description} cards"
    if _PUT_IT_OR_THEM_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    bottom_match = _PUT_REST_ON_BOTTOM_ANY_ORDER_RE.fullmatch(clauses[index + 3].strip())
    if bottom_match is None:
        return None
    randomised = bottom_match.group("random") is not None

    if quantity.source is QuantitySource.ANY_NUMBER:
        reveal_prompt = f"reveal any number of {noun_phrase_plural} from the top"
    elif quantity.amount == 1 and quantity.exact:
        reveal_prompt = f"reveal {with_indefinite_article(noun_phrase_singular)} from the top"
    else:
        reveal_prompt = f"reveal up to {quantity.amount} {noun_phrase_plural} from the top"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        # "Look at" (CR 701.20e) shows the cards to the controller alone, and
        # `look_at_top_and_split` records that look once per card; "in a
        # random order" leaves the controller nothing to know about the rest.
        # The chosen card is then revealed (CR 701.20a) to everyone.
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=f"{reveal_prompt} {count}",
            moved_label="your hand",
            kept_label="bottom of your library",
            rest_in_random_order=randomised,
            source_id=source_id_of(stack_object),
            # "You may reveal a <quality> card": one at most; "up to N"/"any
            # number of" raise the ceiling (CR 107.1c). `None` here means no
            # printed ceiling other than the library itself.
            moved_amount=quantity.amount,
        )
        for state in moved:
            if not matches(state):
                # The count is `Game.ask`'s to refuse; what is left to be
                # wrong is the card itself, so the refusal names it.
                article = "an" if quality_description[:1].lower() in "aeiou" else "a"
                raise ValueError(
                    f"{source}: {state.name} is not {article} {quality_description} card "
                    "(CR 608.2d)"
                )
        for state in moved:
            game.reveal(state, source=source)
            player.add(state, Zone.HAND)
        if randomised and rest:
            # Not CR 701.24a's shuffle - see `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`.
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom")  # noqa: S311
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif rest:
            # CR 401.4: "in any order" is the player's own arrangement.
            rest = game.ask_library_bottom_order(
                player, rest, source=source, source_id=source_id_of(stack_object)
            )
        for state in rest:
            player.library.append(state)
        if rest:
            # CR 701.20d for the cards put back; CR 401.2 keeps the cards
            # above them in their order.
            player.note_library_changed(placed=rest)

    return 4, effect


#: "You may reveal `<A>` or `<B>` from among them" - Paradox Surveyor's own
#: "a land card or a card with {X} in its mana cost", where each half is a
#: whole noun phrase carrying its own "card" word rather than one shared
#: quality word list `_MAY_REVEAL_FROM_AMONG_THEM_RE`'s `(?P<quality>.+?)
#: cards?` can read (that group must be followed immediately by "card(s)",
#: which "... in its mana cost" never is). `_parse_card_group_alternatives`
#: already reads exactly this "or"-joined list of independent card
#: descriptions for the mass-return family below; this is the identical
#: grammar, reused for a look-and-reveal quality instead of a graveyard
#: group, so a future card naming any other two-description "or" list here
#: is covered for free rather than needing its own row.
_MAY_REVEAL_GROUP_FROM_AMONG_THEM_RE = re.compile(
    r"^you may reveal (?P<quality>.+\bor\b.+?) from among them$", re.IGNORECASE
)


def _merge_look_top_may_reveal_group_to_hand_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Paradox Surveyor's whole ETB: "Look at the top five cards of your
    library. You may reveal a land card or a card with {X} in its mana cost
    from among them and put it into your hand. Put the rest on the bottom
    of your library in a random order." - `_merge_look_top_reveal_to_hand_
    clauses`'s own shape, with the quality read by `_parse_card_group_
    alternatives` instead of `_bounded_quality_matcher` so an "or" between
    two whole noun phrases (each carrying its own "card") reads instead of
    just an "or" between bare type words.

    Always "a"/"an" - at most one - never a printed "up to N"/"any number
    of" on this shape (a card sharing the quantifier would still need its
    own reader; nothing in the pool prints one).
    """
    if index + 3 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    reveal_match = _MAY_REVEAL_GROUP_FROM_AMONG_THEM_RE.fullmatch(clauses[index + 1].strip())
    if reveal_match is None:
        return None
    quality_text = reveal_match.group("quality").strip()
    matches = _parse_card_group_alternatives(quality_text)
    if matches is None:
        return None
    if _PUT_IT_OR_THEM_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    bottom_match = _PUT_REST_ON_BOTTOM_ANY_ORDER_RE.fullmatch(clauses[index + 3].strip())
    if bottom_match is None:
        return None
    randomised = bottom_match.group("random") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=f"reveal {quality_text} from the top {count}",
            moved_label="your hand",
            kept_label="bottom of your library",
            rest_in_random_order=randomised,
            source_id=source_id_of(stack_object),
            moved_amount=1,
        )
        for state in moved:
            if not matches(state):
                raise ValueError(
                    f"{source}: {state.name} does not match {quality_text} (CR 608.2d)"
                )
        for state in moved:
            game.reveal(state, source=source)
            player.add(state, Zone.HAND)
        if randomised and rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom")  # noqa: S311
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif rest:
            rest = game.ask_library_bottom_order(
                player, rest, source=source, source_id=source_id_of(stack_object)
            )
        for state in rest:
            player.library.append(state)
        if rest:
            player.note_library_changed(placed=rest)

    return 4, effect


# --------------------------------------------------------------------------
# "Look at the top N cards of your library, then put them back in any
# order." - Ponder, Index, Pondering Mage's own ETB trigger - and its target
# variant, "... of target player's library, ..." (Architects of Will). Only
# CR 401.4's free arrangement, past that: no reveal, no hand, no bottom - the
# whole looked-at set goes straight back on top in whatever order the
# chooser answers. `Game.look_at_top_and_split`'s own generic split question
# still carries it: `moved_amount=0` pins the "moved" half to empty (nothing
# ever leaves), which leaves `rest` as the entire looked-at set and its
# `top_order` as the free arrangement CR 401.4 grants.
# --------------------------------------------------------------------------

#: "look at the top <count> cards of your library" or "... of target
#: player's library" (Architects of Will). `_CLAUSE_SEPARATOR`'s own ", then "
#: cut already split this away from "put them back in any order" below, so
#: this clause is read on its own.
_LOOK_AT_TOP_N_LIBRARY_RE = re.compile(
    rf"^look at the top (?P<count>{COUNT}) cards? of "
    r"(?P<subject>your|target player'?s) library$",
    re.IGNORECASE,
)
#: "put them back in any order" - Ponder's own second half of the same
#: sentence, and Architects of Will's identical tail over a different
#: library. "It" is `_LOOK_AT_TOP_N_LIBRARY_RE`'s own singular cousin, unused
#: by anything currently in the pool but read the same way `_PUT_IT_OR_
#: THEM_INTO_YOUR_HAND_RE` already reads "it"/"them" for the reveal-to-hand
#: family, rather than being fitted only to the two-or-more-card wording the
#: pool happens to print today.
_PUT_THEM_BACK_IN_ANY_ORDER_RE = re.compile(r"^put (?:it|them) back in any order$", re.IGNORECASE)


def _merge_look_top_put_back_any_order_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "Look at the top N cards of your library, then put them back in any
    order" - two clauses, read as one: the count named by the first is
    exactly the set the second re-orders, with nothing moved anywhere else.

    CR 608.2d's split question is `Game.look_at_top_and_split`'s own, asked
    with `moved_amount=0` so the "moved" half is never a legal choice beyond
    empty (CR 608.2d: "can't choose an option that's illegal") - the whole
    looked-at set is always `rest`, and its `top_order` is the free
    arrangement CR 401.4 grants ("the owner of those cards may arrange them
    in any order"). Declining (the unscripted default, `CardSplit()`) keeps
    the cards in the order they were looked at, which is what makes a rigged
    library stay rigged when a scenario asks for nothing else.

    "Target player's library" (Architects of Will) reads the library of a
    resolved player target, but the controller is still who looks, orders,
    and learns (the official ruling: "You look at the cards, not the
    targeted player.") - `Game.look_at_top_and_split`'s own `asked_of` is
    exactly that split, added for this reader.
    """
    if index + 1 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_LIBRARY_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    if _PUT_THEM_BACK_IN_ANY_ORDER_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    targeted = look_match.group("subject").lower().startswith("target")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        if targeted:
            players = [
                target
                for target in game.resolve_targets(stack_object)
                if isinstance(target, Player)
            ]
            # CR 608.2b: a target gone by resolution drops out; nothing left
            # to look at is nothing done, the same "no event" CR 609.3 gives
            # every other library-count effect a short library exhausts.
            if not players:
                return
            (subject,) = players
        else:
            subject = controller

        moved, rest = game.look_at_top_and_split(
            subject,
            count,
            source=source,
            prompt=f"look at the top {count} card(s), then put them back in any order",
            moved_label="not moved",
            kept_label="top of the library, in any order",
            moved_amount=0,
            asked_of=controller,
            source_id=source_id_of(stack_object),
        )
        assert not moved, "moved_amount=0: nothing is ever a legal 'moved' answer"
        library = subject.library
        for position, state in enumerate(rest):
            library.insert(position, state)
        if rest:
            # CR 701.20d: the looked-at cards are reordered; the cards below
            # them keep their own order (CR 401.2).
            subject.note_library_changed(placed=rest)

    return 2, effect


# --------------------------------------------------------------------------
# "Reveal the top N cards of your library. You may put a <quality> card from
# among them into your hand. Put the rest into your graveyard." - Malevolent
# Rumble, Grisly Salvage, Satyr Wayfinder: one anaphoric run of three clauses,
# read wherever it starts, so text printed after it (Malevolent Rumble's
# Eldrazi Spawn) keeps its own reader.
# --------------------------------------------------------------------------

#: "reveal the top <count> cards of your library"
_REVEAL_TOP_N_CARDS_RE = re.compile(
    rf"^reveal the top (?P<count>{COUNT}) cards? of your library$", re.IGNORECASE
)
#: "you may put a/an/up to N/any number of <quality> card(s) from among them
#: into your hand" - Glacial Revelation prints "any number of" (CR 107.1c),
#: Kruphix's Insight-shaped cards print "up to N"; a bare "a/an" reads as
#: `QUANTITY`'s own fixed-one case, unchanged from before this family read
#: any other quantifier.
_MAY_PUT_A_CARD_FROM_AMONG_THEM_INTO_HAND_RE = re.compile(
    rf"^you may put {quantity_pattern('n')} (?P<quality>.+?) cards? "
    r"from among them into your hand$",
    re.IGNORECASE,
)
#: "put the rest into your graveyard"
_PUT_THE_REST_INTO_YOUR_GRAVEYARD_RE = re.compile(
    r"^put the rest into your graveyard$", re.IGNORECASE
)


#: "for each card type, you may exile a card of that type from among them"
#: (Portent of Calamity) and "for each card type, you may put a card of that
#: type from among the revealed cards into your hand" (Atraxa, Grand Unifier):
#: one pick per CR 205.2a card type, taken to exile or to hand.
#: Hurkyl, Master Wizard narrows the loop to the card types among the spells
#: it names: "For each card type among noncreature spells you've cast this
#: turn, you may put a card of that type ..." (`card_types_among_spells_cast_
#: reader`).
_FOR_EACH_CARD_TYPE_MAY_TAKE_RE = re.compile(
    r"^for each (?P<among>card type among [^,]+|card type), you may (?:(?P<exile>exile)|put) "
    r"a card of that type from among "
    r"(?:them|the revealed cards)(?P<hand> into your hand)?$",
    re.IGNORECASE,
)
#: "you may cast a spell from among the exiled cards without paying its mana
#: cost if you exiled four or more cards this way" - a CR 608.2g cast gated on
#: how many cards the pick above actually exiled.
_MAY_CAST_FROM_AMONG_EXILED_IF_N_OR_MORE_RE = re.compile(
    r"^you may cast a spell from among the exiled cards without paying its mana cost "
    rf"if you exiled (?P<n>{COUNT}) or more cards this way$",
    re.IGNORECASE,
)
#: "(then) put the rest of the exiled cards into your hand"
_PUT_THE_REST_OF_THE_EXILED_CARDS_INTO_HAND_RE = re.compile(
    r"^put the rest of the exiled cards into your hand$", re.IGNORECASE
)


def _merge_reveal_top_one_card_per_type_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Reveal the top N, then one pick per card type from among them, then the
    rest somewhere - one anaphoric run.

    Atraxa, Grand Unifier: "reveal the top ten cards of your library. For each
    card type, you may put a card of that type from among the revealed cards
    into your hand. Put the rest on the bottom of your library in a random
    order." Portent of Calamity: "Reveal the top X cards of your library. For
    each card type, you may exile a card of that type from among them. Put the
    rest into your graveyard. You may cast a spell from among the exiled cards
    without paying its mana cost if you exiled four or more cards this way.
    Then put the rest of the exiled cards into your hand."

    CR 701.20a-b: each revealed card is recorded through `Game.reveal` while
    it is still in the library. CR 107.3a's X is not read here: `effect_for`
    substitutes the announced value and retries, so "X" arrives as a number.

    **The loop is over CR 205.2a's card types present among the revealed
    cards**, in `Type`'s order. A card with several types (an artifact
    creature) is a candidate for each, and once chosen it is no longer "from
    among them", so it fills one pick only; Atraxa's 2023-02-04 ruling lets
    it fill whichever pick the player chooses it for. Each pick is CR
    608.2d's "you may", asked only while that type still has a candidate,
    naming the candidates; a choice among two or more follows as a
    `CHOOSE_CARDS`, and a lone candidate needs none.

    The exile verb requires the free-cast tail and the hand verb forbids it,
    since an exiled pick with nothing saying where it goes next is not a
    shape any printing has. The cast is offered only when at least the
    printed number of cards actually reached exile and at least one of them
    `Game.can_cast_during_resolution` - a land never is (CR 305.9) - and goes
    through `Game.cast_during_resolution` (CR 608.2g). Every exiled card still
    in exile afterwards goes to hand.

    The rest is `_THE_OTHER_INTO_A_DESTINATION_RE`'s: the graveyard, the
    bottom "in any order" (CR 401.4, asked) or "in a random order" (seeded
    off `Game.shuffle_seed`, never CR 701.24a's shuffle).
    """
    if index + 2 >= len(clauses):
        return None
    reveal_match = _REVEAL_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if reveal_match is None:
        return None
    count_text = reveal_match.group("count")
    count = parse_count(count_text)
    if count is None:
        return None
    pick_match = _FOR_EACH_CARD_TYPE_MAY_TAKE_RE.fullmatch(clauses[index + 1].strip())
    if pick_match is None:
        return None
    exiling = pick_match.group("exile") is not None
    if exiling == (pick_match.group("hand") is not None):
        return None
    types_among = None
    if pick_match.group("among").lower() != "card type":
        types_among = card_types_among_spells_cast_reader(pick_match.group("among"))
        if types_among is None:
            return None
    rest_text = clauses[index + 2].strip()
    rest_match = _THE_OTHER_INTO_A_DESTINATION_RE.fullmatch(rest_text)
    if rest_match is None or not rest_text.lower().startswith("put the rest"):
        return None
    to_bottom = rest_match.group("destination").lower().startswith("on the bottom")
    randomised = rest_match.group("random") is not None
    consumed = 3
    threshold = 0
    if exiling:
        if index + 4 >= len(clauses):
            return None
        cast_match = _MAY_CAST_FROM_AMONG_EXILED_IF_N_OR_MORE_RE.fullmatch(
            clauses[index + 3].strip()
        )
        if cast_match is None:
            return None
        if (
            _PUT_THE_REST_OF_THE_EXILED_CARDS_INTO_HAND_RE.fullmatch(clauses[index + 4].strip())
            is None
        ):
            return None
        threshold = parse_count(cast_match.group("n")) or 0
        consumed = 5
    verb, destination = ("exile", "") if exiling else ("put", " into your hand")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        revealed = list(player.library[:count])
        for state in revealed:
            game.reveal(state, source=source)
        remaining = list(revealed)
        taken: list[CardState] = []
        allowed = set(Type) if types_among is None else types_among(game, player.username)
        for card_type in Type:
            if card_type not in allowed:
                continue
            candidates = [state for state in remaining if card_type in state.types]
            if not candidates:
                continue
            quality = with_indefinite_article(f"{card_type.value} card")
            if not game.may(
                player,
                f"{verb} {quality} from among the revealed cards{destination}",
                source=source,
                source_id=source_id,
                cards=candidates,
            ):
                continue
            chosen = _choose_one_card(
                game,
                player,
                candidates,
                prompt=f"choose {quality} to {verb}{destination}",
                source=source,
                source_id=source_id,
            )
            remaining.remove(chosen)
            taken.append(chosen)

        if not exiling:
            for state in taken:
                player.move(state, Zone.HAND)
        if to_bottom and randomised and remaining:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-{count}-bottom")  # noqa: S311
            rng.shuffle(remaining)
            for state in remaining:
                player.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1
        elif to_bottom:
            for state in game.ask_library_bottom_order(
                player, remaining, source=source, source_id=source_id
            ):
                player.move(state, Zone.LIBRARY)
        if not exiling:
            if not to_bottom:
                for state in remaining:
                    game.put_into_graveyard(state)
            return

        exiled = [state for state in game.exile_cards(taken) if state.zone is Zone.EXILE]
        if not to_bottom:
            for state in remaining:
                game.put_into_graveyard(state)
        if len(exiled) >= threshold:
            castable = [
                state for state in exiled if game.can_cast_during_resolution(state, player.username)
            ]
            if castable and game.may(
                player,
                "cast a spell from among the exiled cards without paying its mana cost",
                source=source,
                source_id=source_id,
                cards=castable,
            ):
                spell = _choose_one_card(
                    game,
                    player,
                    castable,
                    prompt="choose a spell to cast without paying its mana cost",
                    source=source,
                    source_id=source_id,
                )
                game.cast_during_resolution(
                    spell, player.username, source_name=source, rule="CR 608.2g"
                )
        for state in exiled:
            if state.zone is Zone.EXILE:
                game.return_to_hand(state)

    return consumed, effect


def _merge_reveal_top_to_hand_rest_to_graveyard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """The reveal-to-hand run above, as one effect.

    CR 701.20a: "To reveal a card, show that card to all players". Every card
    is recorded as a public reveal through `Game.reveal` the moment it is
    shown, while it still sits in the library (CR 701.20b) and before the
    next sentence moves anything (CR 608.2c). That is what makes the card put
    into hand known to the opponent: the live library record is carried into
    the hand by `Player.add`, the same known-draw carry Ancient Stirrings'
    revealed card already gets.

    Whether to take a card and which one are CR 608.2d choices: a `Game.may`
    that names the qualifying cards, then a `CHOOSE_CARDS` over them.
    Unscripted, the first qualifying card in library order is taken. The
    quality is `_quality_matcher`'s ("permanent" is CR 110.4a's permanent
    card, "creature or land" either type); a quality it cannot read is not
    matched at all rather than resolved as a reveal that offers nothing.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_match = _REVEAL_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if reveal_match is None:
        return None
    count = parse_count(reveal_match.group("count"))
    if count is None:
        return None
    if _PUT_THE_REST_INTO_YOUR_GRAVEYARD_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    # Tried first: "a creature card and/or a land card" would otherwise read
    # below as one pick of the unreadable quality "creature card and/or a land".
    one_of_each_kind = _reveal_take_one_of_each_kind(clauses[index + 1], count)
    if one_of_each_kind is not None:
        return one_of_each_kind
    take_match = _MAY_PUT_A_CARD_FROM_AMONG_THEM_INTO_HAND_RE.fullmatch(clauses[index + 1].strip())
    if take_match is None:
        return None
    quantity = parse_quantity(take_match.group("n"))
    if quantity is None or quantity.source not in (QuantitySource.FIXED, QuantitySource.ANY_NUMBER):
        return None
    quality = take_match.group("quality").strip()
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)
    article = "an" if quality[:1].lower() in "aeiou" else "a"
    if quantity.source is QuantitySource.ANY_NUMBER:
        take_noun = f"any number of {quality} cards"
    elif quantity.exact and quantity.amount == 1:
        take_noun = f"{article} {quality} card"
    else:
        take_noun = f"up to {quantity.amount} {quality} cards"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        revealed = list(player.library[:count])
        for state in revealed:
            game.reveal(state, source=source)
        candidates = [state for state in revealed if matches(state)]
        chosen: list[CardState] = []
        if candidates:
            if quantity.exact:
                # "you may put a/an <quality> card": a single optional pick,
                # gated behind the CR 608.2d "may" before naming candidates.
                if game.may(
                    player,
                    f"put {take_noun} from among them into your hand",
                    source=source,
                    source_id=source_id,
                    cards=candidates,
                ):
                    chosen_ids = game.ask(
                        Decision(
                            kind=DecisionKind.CHOOSE_CARDS,
                            player=player.username,
                            prompt=f"choose {take_noun} to put into your hand",
                            source=source,
                            source_id=source_id,
                            amount=1,
                            cards=tuple(state.id for state in candidates),
                            default_cards=(candidates[0].id,),
                        )
                    )
                    assert isinstance(chosen_ids, tuple)
                    chosen = [next(state for state in candidates if state.id == chosen_ids[0])]
            else:
                # "up to N"/"any number of": CR 107.1c - zero to the ceiling
                # is one question, with no separate "may" gate in front of it.
                ceiling = (
                    len(candidates)
                    if quantity.amount is None
                    else min(quantity.amount, len(candidates))
                )
                chosen_ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"put {take_noun} from among them into your hand",
                        source=source,
                        source_id=source_id,
                        amount=ceiling,
                        exact=False,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                assert isinstance(chosen_ids, tuple)
                by_id = {state.id: state for state in candidates}
                chosen = [by_id[card_id] for card_id in chosen_ids]
        for state in chosen:
            player.move(state, Zone.HAND)
        for state in revealed:
            if state not in chosen:
                game.put_into_graveyard(state)

    return 3, effect


#: "put one of them into your hand" - Waker of Waves' own second sentence,
#: read plain rather than through `_MAY_REVEAL_FROM_AMONG_THEM_RE`'s "you may
#: reveal a `<quality>` card": there is no quality restriction and no "you
#: may" - the split is mandatory, and which of the two cards goes where is the
#: controller's own unstated choice (CR 608.2d), the same free choice `scry`'s
#: "any order" already is.
#: "of them" is optional: Codecracker Hound prints the shorter "Put one into
#: your hand", Waker of Waves the fuller "Put one of them into your hand" -
#: the same CR 608.2d split either way.
#: The count is read, not fixed: Stock Up prints "Put two of them into your
#: hand", Dovin, Grand Arbiter's -7 "Put three of them into your hand".
#: "of those cards" is the identical anaphor to "of them" spelled out in
#: full - Stress Dream's own "Put one of those cards into your hand" - so it
#: is read as the same optional tail rather than a shape this reader misses.
_PUT_N_OF_THEM_INTO_YOUR_HAND_RE = re.compile(
    rf"^put (?P<count>{COUNT})(?: of (?:them|those cards))? into your hand$", re.IGNORECASE
)
#: "the other into your graveyard" - Waker of Waves' own third clause, split
#: off the second sentence's "and" by `_CLAUSE_SEPARATOR` the same way
#: Duskwatch Recruiter's own third/fourth clauses are. English ellipsis drops
#: the repeated verb ("put"), so it is optional here, unlike
#: `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`'s fully spelled-out sentence.
#: Sleight of Hand and Sea Gate Oracle print "the other on the bottom of your
#: library" in the same place, and Forbidden Alchemy, Anticipate and Shimmer of
#: Possibility "the rest into your graveyard" / "the rest on the bottom of your
#: library in any order" / "... in a random order": the same one-to-hand split,
#: a different second destination. "In any order" is CR 401.4's arrangement,
#: asked; "in a random order" is nobody's, seeded as
#: `_PUT_REST_ON_BOTTOM_ANY_ORDER_RE`'s own random tail is.
_THE_OTHER_INTO_A_DESTINATION_RE = re.compile(
    r"^(?:put )?the (?:other|rest) (?P<destination>into your graveyard|on the bottom of "
    r"your library(?: in (?:(?P<random>a random)|any) order)?)$",
    re.IGNORECASE,
)


def _merge_look_top_split_hand_graveyard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Waker of Waves' whole `{1}{U}` ability: "Look at the top two cards of
    your library. Put one of them into your hand and the other into your
    graveyard." - the same anaphoric-run shape `_merge_look_top_reveal_to_
    hand_clauses` reads for Duskwatch Recruiter, with a different pair of
    destinations and no quality restriction or "you may": both halves of the
    split are mandatory.

    `Game.look_at_top_and_split` asks the identical CR 608.2d question either
    way; what differs is only what this function does with the two answered
    groups, and the shape it enforces on them - CR 608.2d: "The player can't
    choose an option that's illegal or impossible", so an answer that does not
    put exactly the printed number into hand is refused rather than silently
    applied. The printed number is Waker of Waves' "one", Stock Up's "two" or
    Dovin, Grand Arbiter's "three"; a library holding fewer cards than that
    gives what it has (CR 609.3).
    """
    if index + 2 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    hand_match = _PUT_N_OF_THEM_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 1].strip())
    if hand_match is None:
        return None
    hand_word = hand_match.group("count").lower()
    if hand_word in ("a", "an"):
        return None
    hand_count = parse_count(hand_word)
    if hand_count is None or hand_count < 1:
        return None
    other = _THE_OTHER_INTO_A_DESTINATION_RE.fullmatch(clauses[index + 2].strip())
    if other is None:
        return None
    to_bottom = other.group("destination").lower().startswith("on the bottom")
    randomised = other.group("random") is not None
    rest_label = "bottom of your library" if to_bottom else "your graveyard"
    prompt = (
        f"put one into your hand, the other to {rest_label}"
        if hand_count == 1
        else f"put {hand_word} into your hand, the rest to {rest_label}"
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=prompt,
            moved_label="your hand",
            kept_label=rest_label,
            rest_in_random_order=randomised,
            source_id=source_id_of(stack_object),
            moved_amount=hand_count,
            moved_exact=True,
        )
        # CR 609.3: a library shorter than the printed number gives what it has.
        required = min(hand_count, len(moved) + len(rest))
        if len(moved) != required:
            raise ValueError(
                f"{source}: exactly {required} of the {len(moved) + len(rest)} looked at must "
                f"go to hand, the rest to {rest_label} (CR 608.2d)"
            )
        for state in moved:
            player.add(state, Zone.HAND)
        if to_bottom and randomised and rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom")  # noqa: S311
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif to_bottom:
            # CR 401.4: "in any order" is the player's own arrangement.
            rest = game.ask_library_bottom_order(
                player, rest, source=source, source_id=source_id_of(stack_object)
            )
        if to_bottom:
            # Under every card already there (CR 401.2), each looked-at card
            # once (CR 400.7); the look is pinned to this one put-back.
            player.library.extend(rest)
            if rest:
                player.note_library_changed(placed=rest)
        else:
            for state in rest:
                player.add(state, Zone.GRAVEYARD)
                # CR 700.11/CR 400.6: this puts a looked-at library card
                # straight into the graveyard without going through `Game.
                # put_into_graveyard`, so it has to feed the ledger itself.
                game._record_graveyard_arrival(  # noqa: SLF001
                    state, origin_zone=Zone.LIBRARY, permanent_types=None
                )

    return 3, effect


#: "look at the top X cards of your library, where X is `<expr>`" - Stirring
#: Honormancer's own ETB, a dynamic-count cousin of `_LOOK_AT_TOP_N_CARDS_RE`
#: (a fixed printed number) rather than a second copy of it: CR 107.3f's own
#: X, defined by the trailing "where X is" clause and read through
#: `count_expression`/`_fixed_or_where_x_amount` at resolution - never CR
#: 107.3a's cast-announced X, which this shape never carries (the card has
#: no {X} in its own mana cost).
_LOOK_AT_TOP_X_CARDS_WHERE_RE = re.compile(
    rf"^look at the top {count_pattern('count', x=True, article=False)} cards? of your library"
    rf"{where_x_pattern()}$",
    re.IGNORECASE,
)


def _merge_look_top_x_split_hand_graveyard_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Stirring Honormancer's whole ETB: "Look at the top X cards of your
    library, where X is the number of creatures you control. Put one of
    those cards into your hand and the rest into your graveyard." - the
    dynamic-count sibling of `_merge_look_top_split_hand_graveyard_clauses`:
    the second and third clauses are that function's own `_PUT_N_OF_THEM_
    INTO_YOUR_HAND_RE`/`_THE_OTHER_INTO_A_DESTINATION_RE` shapes verbatim
    (no new grammar needed there - "of those cards" and "the rest into your
    graveyard" are already read the general way), and only the first clause's
    count differs, read fresh at resolution the moment CR 611.2c fixes it
    rather than once at parse time.
    """
    if index + 2 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_X_CARDS_WHERE_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count_reader = _fixed_or_where_x_amount(look_match.group("count"), look_match.group("where_x"))
    if count_reader is None:
        return None
    hand_match = _PUT_N_OF_THEM_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 1].strip())
    if hand_match is None:
        return None
    hand_word = hand_match.group("count").lower()
    if hand_word in ("a", "an"):
        return None
    hand_count = parse_count(hand_word)
    if hand_count is None or hand_count < 1:
        return None
    other = _THE_OTHER_INTO_A_DESTINATION_RE.fullmatch(clauses[index + 2].strip())
    if other is None:
        return None
    to_bottom = other.group("destination").lower().startswith("on the bottom")
    randomised = other.group("random") is not None
    rest_label = "bottom of your library" if to_bottom else "your graveyard"
    prompt = (
        f"put one into your hand, the other to {rest_label}"
        if hand_count == 1
        else f"put {hand_word} into your hand, the rest to {rest_label}"
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_obj = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        count = max(count_reader(game, player.username, source_obj, 0), 0)
        if count <= 0:
            return
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=prompt,
            moved_label="your hand",
            kept_label=rest_label,
            rest_in_random_order=randomised,
            source_id=source_id_of(stack_object),
            moved_amount=hand_count,
            moved_exact=True,
        )
        required = min(hand_count, len(moved) + len(rest))
        if len(moved) != required:
            raise ValueError(
                f"{source}: exactly {required} of the {len(moved) + len(rest)} looked at must "
                f"go to hand, the rest to {rest_label} (CR 608.2d)"
            )
        for state in moved:
            player.add(state, Zone.HAND)
        if to_bottom and randomised and rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom")  # noqa: S311
            rng.shuffle(rest)
            game.shuffles_performed += 1
        elif to_bottom and rest:
            rest = game.ask_library_bottom_order(
                player, rest, source=source, source_id=source_id_of(stack_object)
            )
        if to_bottom:
            player.library.extend(rest)
            if rest:
                player.note_library_changed(placed=rest)
        else:
            for state in rest:
                player.add(state, Zone.GRAVEYARD)
                game._record_graveyard_arrival(  # noqa: SLF001
                    state, origin_zone=Zone.LIBRARY, permanent_types=None
                )

    return 3, effect


#: "put all <quality> cards revealed this way into your hand" - Wrenn and
#: Seven's own +1 ("land cards"), Mulch (the same "land cards" sentence,
#: word for word, off-pool), Merfolk Wayfinder ("Island cards"), Lair Delve
#: ("creature and land cards"). Every matching card, mandatorily - unlike
#: `_MAY_PUT_A_CARD_FROM_AMONG_THEM_INTO_HAND_RE`'s "you may put a
#: `<quality>` card", which is CR 608.2d's optional pick of *at most one*.
_PUT_ALL_QUALITY_REVEALED_INTO_HAND_RE = re.compile(
    r"^put all (?P<quality>.+?) cards? revealed this way into your hand$", re.IGNORECASE
)


def _merge_reveal_top_put_all_quality_to_hand_rest_elsewhere_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Wrenn and Seven's whole +1: "Reveal the top four cards of your
    library. Put all land cards revealed this way into your hand and the
    rest into your graveyard." - `_CLAUSE_SEPARATOR`'s own "and" cuts the
    second sentence into two clauses the same way `_merge_look_top_split_
    hand_graveyard_clauses` right above already reads its own pair back
    together, which is why this reuses that function's own `_THE_OTHER_
    INTO_A_DESTINATION_RE` for the tail rather than a second copy of it -
    Merfolk Wayfinder's "the rest on the bottom of your library in any
    order" is the identical shape with a different destination, not a
    different mechanic.

    CR 701.20a/b: every one of the `count` cards is revealed - shown to all
    players - while still in the library, before any of them move; which
    ones qualify for hand is CR 608.2c's own fixed instruction, not a
    choice, so nothing is asked about which cards go where, only (for the
    "on the bottom" destination) what order the rest keep.
    """
    if index + 2 >= len(clauses):
        return None
    reveal_match = _REVEAL_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if reveal_match is None:
        return None
    count = parse_count(reveal_match.group("count"))
    if count is None:
        return None
    put_match = _PUT_ALL_QUALITY_REVEALED_INTO_HAND_RE.fullmatch(clauses[index + 1].strip())
    if put_match is None:
        return None
    quality = put_match.group("quality").strip()
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)
    other = _THE_OTHER_INTO_A_DESTINATION_RE.fullmatch(clauses[index + 2].strip())
    if other is None:
        return None
    to_bottom = other.group("destination").lower().startswith("on the bottom")
    randomised = other.group("random") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        source_id = source_id_of(stack_object)
        revealed = list(player.library[:count])
        for state in revealed:
            game.reveal(state, source=source)
        to_hand = [state for state in revealed if matches(state)]
        rest = [state for state in revealed if state not in to_hand]
        for state in to_hand:
            player.add(state, Zone.HAND)
        if not rest:
            return
        if to_bottom:
            if randomised:
                rng = Random(  # noqa: S311
                    f"{game.shuffle_seed}:{game.shuffles_performed}:reveal-top-{count}-bottom"
                )
                rng.shuffle(rest)
                game.shuffles_performed += 1
            else:
                # CR 401.4: "in any order" is the player's own arrangement.
                rest = game.ask_library_bottom_order(
                    player, rest, source=source, source_id=source_id
                )
            # Under every card already there (CR 401.2), each revealed card
            # once (CR 400.7): lifted off the top first, or it would be listed
            # twice.
            for state in rest:
                player.library.remove(state)
            player.library.extend(rest)
            player.note_library_changed(placed=rest)
        else:
            for state in rest:
                game.put_into_graveyard(state)

    return 3, effect


#: "You may reveal up to `<n>` `<A>` and/or `<B>` cards from among them" -
#: Zimone's Experiment's own second clause. `_MAY_REVEAL_FROM_AMONG_THEM_RE`
#: reads a single quality word list (comma/"or"); this is the "and/or" join
#: `conditions/player.py`'s own `_CARD_QUALITY` already treats as one
#: existence check, but here each side is read as its *own* separate
#: predicate (not just their union) because what happens next depends on
#: which one a given revealed card actually is - a land goes to the
#: battlefield, a creature to hand, and a card that is both (extremely rare,
#: e.g. an animated land printed as a creature card is not a thing, but a
#: card with multiple relevant types is not ruled out here) would need to go
#: to more than one destination, which `_distribute_revealed_by_type` below
#: reads as "each destination whose quality it matches", not "the first
#: one" - CR 608.2c runs every instruction the text prints.
_MAY_REVEAL_TYPES_FROM_AMONG_THEM_RE = re.compile(
    rf"^you may reveal {quantity_pattern('n')} (?P<quality>.+?) cards? from among them$",
    re.IGNORECASE,
)
#: "put all `<quality>` cards revealed this way onto the battlefield[
#: tapped]" - Zimone's Experiment's own land half of the two-destination
#: split; `_PUT_ALL_QUALITY_REVEALED_INTO_HAND_RE` right above already reads
#: its hand half.
_PUT_ALL_QUALITY_REVEALED_ONTO_BATTLEFIELD_RE = re.compile(
    r"^put all (?P<quality>.+?) cards? revealed this way onto the battlefield(?P<tapped> tapped)?$",
    re.IGNORECASE,
)


def _merge_look_top_may_reveal_two_types_split_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Zimone's Experiment's whole spell: "Look at the top five cards of
    your library. You may reveal up to two creature and/or land cards from
    among them, then put the rest on the bottom of your library in a random
    order. Put all land cards revealed this way onto the battlefield tapped
    and put all creature cards revealed this way into your hand."

    Read as one CR 608.2c instruction: the "up to two" reveal is one CR
    608.2d choice among the looked-at cards (`Game.look_at_top_and_split`,
    the same primitive `_merge_look_top_reveal_to_hand_clauses` already asks
    for its own single-destination reveal), and the two trailing "put all
    `<quality>` cards revealed this way `<dest>`" sentences are that one
    choice's own fixed consequence, not a second choice - every land
    revealed goes to the battlefield, every creature to hand, with nothing
    left to decide once the reveal itself is answered.

    At least two trailing distribution clauses are required (a card printing
    only one would be `_merge_reveal_top_put_all_quality_to_hand_rest_
    elsewhere_clauses`'s own mandatory-reveal shape, not this optional one),
    read in whatever order they are printed - `type_words`' own order from
    the reveal sentence never has to match the distribution sentences' order,
    since each distribution clause carries its own quality word.
    """
    if index + 2 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    reveal_match = _MAY_REVEAL_TYPES_FROM_AMONG_THEM_RE.fullmatch(clauses[index + 1].strip())
    if reveal_match is None:
        return None
    quantity = parse_quantity(reveal_match.group("n"))
    if quantity is None or quantity.source not in (QuantitySource.FIXED, QuantitySource.ANY_NUMBER):
        return None
    quality_text = reveal_match.group("quality").strip()
    type_words = [
        word.strip()
        for word in re.split(r"\s+and/or\s+", quality_text, flags=re.IGNORECASE)
        if word.strip()
    ]
    if len(type_words) < 2 or any(not _card_description_is_readable(word) for word in type_words):
        return None
    type_matchers = [_quality_matcher(word) for word in type_words]

    def revealed_quality_ok(state: CardState) -> bool:
        return any(matcher(state) for matcher in type_matchers)

    bottom_match = _PUT_REST_ON_BOTTOM_ANY_ORDER_RE.fullmatch(clauses[index + 2].strip())
    if bottom_match is None:
        return None
    randomised = bottom_match.group("random") is not None

    destinations: list[tuple[Callable[[CardState], bool], bool, bool]] = []
    # Each entry is (matches, to_hand, tapped) - `to_hand=False` means the
    # battlefield, `tapped` only meaningful then.
    cursor = index + 3
    while cursor < len(clauses):
        hand_match = _PUT_ALL_QUALITY_REVEALED_INTO_HAND_RE.fullmatch(clauses[cursor].strip())
        if hand_match is not None:
            word = hand_match.group("quality").strip()
            if not _card_description_is_readable(word):
                return None
            destinations.append((_quality_matcher(word), True, False))
            cursor += 1
            continue
        battlefield_match = _PUT_ALL_QUALITY_REVEALED_ONTO_BATTLEFIELD_RE.fullmatch(
            clauses[cursor].strip()
        )
        if battlefield_match is not None:
            word = battlefield_match.group("quality").strip()
            if not _card_description_is_readable(word):
                return None
            destinations.append(
                (_quality_matcher(word), False, battlefield_match.group("tapped") is not None)
            )
            cursor += 1
            continue
        break
    if len(destinations) < 2:
        return None
    consumed = cursor - index

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt=f"reveal up to {quantity.amount} {quality_text} cards from the top {count}",
            moved_label="revealed",
            kept_label="bottom of your library",
            rest_in_random_order=randomised,
            source_id=source_id,
            moved_amount=quantity.amount,
        )
        for state in moved:
            if not revealed_quality_ok(state):
                raise ValueError(
                    f"{source}: {state.name} does not match {quality_text} (CR 608.2d)"
                )
        for state in moved:
            game.reveal(state, source=source)
        for state in moved:
            for matcher, to_hand, tapped in destinations:
                if matcher(state):
                    if to_hand:
                        player.add(state, Zone.HAND)
                    else:
                        game.put_onto_battlefield(state, player.username, tapped=tapped)
                    break
        if not rest:
            return
        if randomised:
            rng = Random(  # noqa: S311
                f"{game.shuffle_seed}:{game.shuffles_performed}:top-{count}-bottom"
            )
            rng.shuffle(rest)
            game.shuffles_performed += 1
        else:
            rest = game.ask_library_bottom_order(player, rest, source=source, source_id=source_id)
        player.library.extend(rest)
        player.note_library_changed(placed=rest)

    return consumed, effect


#: Expressive Iteration's own second sentence, split by `_CLAUSE_SEPARATOR`'s
#: single "and" into two raw clauses rather than three (no "then"/"and"
#: separates the first two destinations, only a comma) - "Put one of them
#: into your hand, put one of them on the bottom of your library," is one
#: fragment, "exile one of them" the other.
_PUT_HAND_AND_BOTTOM_RE = re.compile(
    r"^put one of them into your hand, put one of them on the bottom of your library,?$",
    re.IGNORECASE,
)
_EXILE_ONE_OF_THEM_RE = re.compile(r"^exile one of them$", re.IGNORECASE)
#: "You may play the exiled card this turn." - CR 601.3's time-boxed
#: permission, the same primitive `_parse_exile_then_play_permission_pair`
#: already uses for Ugin's -11 and Ragavan, but printed on a *spell* here
#: rather than an ability - that pairing is ability-only (see its own
#: docstring), so Expressive Iteration gets a dedicated merge instead.
_YOU_MAY_PLAY_THE_EXILED_CARD_THIS_TURN_RE = re.compile(
    r"^you may play the exiled cards? this turn$", re.IGNORECASE
)


#: "Look at the top five cards of your library, put one of them into your
#: hand, and exile the rest." (Browse) - the same one-to-hand split with the
#: look and the first put in one comma-joined clause, so it is split
#: differently and read by its own merge.
_LOOK_AT_TOP_PUT_ONE_INTO_HAND_RE = re.compile(
    r"^look at the top (?P<count>\w+) cards? of your library, put one of them into your hand,?$",
    re.IGNORECASE,
)
_EXILE_THE_REST_RE = re.compile(r"^(?:and )?exile the rest$", re.IGNORECASE)


def _merge_look_top_one_to_hand_exile_rest_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Browse's "Look at the top N cards of your library, put one of them
    into your hand, and exile the rest." - `Game.look_at_top_and_split`'s
    question, one card to hand and every other looked-at card exiled, each
    card moved once (CR 400.7)."""
    if index + 1 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_PUT_ONE_INTO_HAND_RE.fullmatch(clauses[index].strip())
    if look_match is None or _EXILE_THE_REST_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt="put one into your hand, exile the rest",
            moved_label="your hand",
            kept_label="exile",
            source_id=source_id_of(stack_object),
            moved_amount=1,
            moved_exact=True,
        )
        for state in moved:
            player.add(state, Zone.HAND)
        if rest:
            game.exile_cards(rest)

    return 2, effect


_PUT_THE_OTHER_INTO_YOUR_HAND_RE = re.compile(
    r"^(?:and )?put the other into your hand$", re.IGNORECASE
)


def _merge_look_top_exile_one_other_to_hand_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Ashiok, Wicked Manipulator's +1: "Look at the top two cards of your
    library. Exile one of them and put the other into your hand." - the same
    CR 608.2d one-to-hand question as Browse, the rest exiled."""
    if index + 2 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    if _EXILE_ONE_OF_THEM_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    if _PUT_THE_OTHER_INTO_YOUR_HAND_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    count = parse_count(look_match.group("count"))
    if count != 2:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        moved, rest = game.look_at_top_and_split(
            player,
            count,
            source=source,
            prompt="put one into your hand, exile the other",
            moved_label="your hand",
            kept_label="exile",
            source_id=source_id_of(stack_object),
            moved_amount=1,
            moved_exact=True,
        )
        for state in moved:
            player.add(state, Zone.HAND)
        if rest:
            game.exile_cards(rest)

    return 3, effect


def _merge_look_top_hand_bottom_exile_play_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Expressive Iteration's whole text: "Look at the top three cards of
    your library. Put one of them into your hand, put one of them on the
    bottom of your library, and exile one of them. You may play the exiled
    card this turn." - a three-way CR 608.2d split (`_merge_look_top_split_
    hand_graveyard_clauses`'s own two-way sibling), the third destination
    carrying a CR 601.3 play permission over whatever landed there.

    Spell-only: the pool has no ability printing this exact shape, and CR
    608.2b's "the resolving object's controller" is unambiguous for a spell
    (`game.controller_of(spell)`) in a way `_parse_exile_then_play_
    permission_pair`'s own docstring explains an `AbilityOnStack` is not.
    """
    if not for_spell or index + 3 >= len(clauses):
        return None
    look_match = _LOOK_AT_TOP_N_CARDS_RE.fullmatch(clauses[index].strip())
    if look_match is None:
        return None
    count = parse_count(look_match.group("count"))
    if count is None:
        return None
    if _PUT_HAND_AND_BOTTOM_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    if _EXILE_ONE_OF_THEM_RE.fullmatch(clauses[index + 2].strip()) is None:
        return None
    if _YOU_MAY_PLAY_THE_EXILED_CARD_THIS_TURN_RE.fullmatch(clauses[index + 3].strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        looked = game._look_at_top(player, count)
        if not looked:
            return
        # CR 701.20e: the looker knows the cards where they sit while each
        # destination is still being chosen; the put-back ends that record.
        pending_looks = game._look_before_choosing(player, looked, spell.name)

        def choose_one(prompt: str, pool: list[CardState]) -> CardState:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=prompt,
                    source=spell.name,
                    source_id=source_id_of(spell),
                    amount=1,
                    cards=tuple(state.id for state in pool),
                )
            )
            by_id = {state.id: state for state in pool}
            return by_id[chosen_ids[0]]

        to_hand = choose_one("put one of the looked-at cards into your hand", looked)
        remaining = [state for state in looked if state is not to_hand]
        to_bottom = (
            choose_one(
                "put one of the remaining looked-at cards on the bottom of your library",
                remaining,
            )
            if remaining
            else None
        )
        to_exile = [state for state in remaining if state is not to_bottom]

        # CR 400.7: every looked-at card leaves the top at once and lands in
        # exactly one destination - the card put into hand used to be left
        # in the library as well (battle 7, B7-01).
        game._end_looks(pending_looks)
        for state in looked:
            player.library.remove(state)
        player.add(to_hand, Zone.HAND)
        if to_bottom is not None:
            player.library.append(to_bottom)
            # CR 401.2: the cards it goes under keep their order and records;
            # the looker knows where the bottomed card went (CR 701.20e).
            player.note_library_changed(placed=[to_bottom])
            game.look(to_bottom, player.username, source=spell.name)
        for state in to_exile:
            exiled = game.exile_permanent(state)
            game.grant_play_permission(
                exiled,
                player.username,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=spell.name,
                rule="CR 601.3",
            )

    return 4, effect


#: "You lose/gain life equal to that card's/its mana value." read right after
#: a clause that targets a card - Reanimate's own second sentence, Divine
#: Offering's and Terashi's Grasp's "You gain life equal to its mana value."
#: The anaphor is CR 608.2c's read-back to the object the previous
#: instruction targeted; CR 608.2b's own "If part of the effect requires
#: information about an illegal target, it fails to determine any such
#: information" is why only a target still legal as the spell resolves is
#: counted. The value is read before the first clause moves the card, the
#: same mana value it has wherever it lands (CR 202.3).
_LIFE_EQUAL_TO_TARGET_MANA_VALUE_RE = re.compile(
    r"^you (?P<verb>lose|gain) life equal to "
    r"(?:its|that (?:card|creature|artifact|enchantment|permanent)['’]s) mana value\.?$",
    re.IGNORECASE,
)


def _merge_target_then_life_equal_to_its_mana_value_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """A targeted clause, then `_LIFE_EQUAL_TO_TARGET_MANA_VALUE_RE` - read
    as one CR 608.2c pair so the second sentence knows which card "that card"
    is. `None` unless the first clause names a target and reads on its own.
    """
    if index + 1 >= len(clauses):
        return None
    first = clauses[index].strip()
    if "target" not in first.lower():
        return None
    rider = _LIFE_EQUAL_TO_TARGET_MANA_VALUE_RE.fullmatch(clauses[index + 1].strip())
    if rider is None:
        return None
    head = _parse_mixed_clause(first, for_spell=for_spell)
    if head is None:
        return None
    loses = rider.group("verb").lower() == "lose"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        amount = sum(int(card.mana_value) for card in game.resolve_card_targets(stack_object))
        head(game, stack_object)
        game.announce_batched_events()
        controller = game.controller_of(stack_object)
        if loses:
            game.lose_life(controller, amount)
        else:
            game.gain_life(controller, amount)

    return 2, effect


#: "You may exile `<n>` [`<quality>`] cards from your graveyard. If you do,
#: `<consequence>`." (Emeritus of Ideation's attack trigger, Aegis
#: Sculptor's upkeep trigger). CR 118.12: the exile is a cost paid as the
#: ability resolves, and "if you do" checks whether it was paid; CR 118.3:
#: "A player can't pay a cost without having the necessary resources to pay
#: it fully" - so with fewer than `<n>` such cards the question is never
#: asked and nothing is exiled. The consequence may name the ability's own
#: source ("this creature becomes prepared", "put a +1/+1 counter on this
#: creature"), so it is read by `_parse_mixed_clause` when the player-clause
#: reader cannot read it.
_MAY_EXILE_FROM_GRAVEYARD_COST_RE = re.compile(
    rf"^you may exile (?P<n>{COUNT}) (?:(?P<quality>[a-z]+) )?cards? from your graveyard\.?$",
    re.IGNORECASE,
)


def _merge_may_exile_from_graveyard_if_you_do_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`_MAY_EXILE_FROM_GRAVEYARD_COST_RE`, then "If you do, `<clause>`"."""
    if index + 1 >= len(clauses):
        return None
    cost = _MAY_EXILE_FROM_GRAVEYARD_COST_RE.fullmatch(clauses[index].strip())
    if cost is None:
        return None
    if_match = _IF_YOU_DO_RE.fullmatch(clauses[index + 1].strip())
    if if_match is None:
        return None
    count = parse_count(cost.group("n"))
    if count is None or count < 1:
        return None
    quality = cost.group("quality")
    predicate: Callable[[CardState], bool] | None = None
    if quality is not None:
        predicate = _nonland_or_typed_card_matcher(quality) or _quality_matcher(quality)
        if predicate is None:
            return None
    consequence_text = if_match.group("consequence").strip().rstrip(".")
    player_consequence = parse_clause_effect(consequence_text)
    object_consequence = (
        _parse_mixed_clause(consequence_text, for_spell=for_spell)
        if player_consequence is None
        else None
    )
    if player_consequence is None and object_consequence is None:
        return None
    prompt = cost.group(0).strip().rstrip(".")[len("you may ") :]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        pool = [card for card in player.graveyard if predicate is None or predicate(card)]
        if len(pool) < count:
            return  # CR 118.3: the cost can't be paid, so it wasn't.
        if not game.may(player, prompt, source=source, source_id=source_id):
            return
        _exile_cards_from_graveyard(
            game, player, count, source, source_id=source_id, predicate=predicate
        )
        game.announce_batched_events()
        if player_consequence is not None:
            player_consequence(game, player, source, source_id)
        elif object_consequence is not None:
            object_consequence(game, stack_object)

    return 2, effect


#: The second half of "create `<token>` and suspect it" (Case of the Stashed
#: Skeleton's own enters trigger) once `split_effect_clauses` has cut it at
#: the bare "and".
_SUSPECT_THE_CREATED_TOKEN_RE = re.compile(r"^suspect (?:it|them)\.?$", re.IGNORECASE)


def _merge_create_token_then_suspect_it_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """ "create `<token>` and suspect it": "it" is the token just created (CR
    608.2c reads the sentence as one instruction), not the trigger event's
    subject `_parse_suspect_clause`'s own "suspect it" would read - so the
    two clauses are rejoined here. Every token the creation clause made is
    suspected (CR 701.60a), any token description `_parse_token_clause`
    reads."""
    if index + 1 >= len(clauses):
        return None
    if _SUSPECT_THE_CREATED_TOKEN_RE.fullmatch(clauses[index + 1].strip()) is None:
        return None
    token_clause = _parse_token_clause(clauses[index], for_spell=for_spell)
    if token_clause is None:
        return None

    def create_then_suspect(game: "Game", stack_object: "StackObject") -> None:
        before = {permanent.id for permanent in game.battlefield}
        token_clause(game, stack_object)
        for permanent in list(game.battlefield):
            if permanent.id not in before and permanent.token:
                suspect(game, permanent)

    return 2, create_then_suspect


def _merge_return_target_from_graveyard_tapped_then_attacking_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """`split_effect_clauses`'s own bare-"and" boundary cuts Grim Reaper,
    Lethal Legionnaire's own "... tapped and attacking with a finality
    counter on it" into "... tapped" / "attacking with a finality counter on
    it" - rejoined here the same way the sentence was always one CR 608.2c
    instruction, then read as a whole by `_parse_return_target_from_
    graveyard_tapped_and_attacking_clause`."""
    if for_spell or index + 1 >= len(clauses):
        return None
    combined = f"{clauses[index].strip()} and {clauses[index + 1].strip()}"
    effect = _parse_return_target_from_graveyard_tapped_and_attacking_clause(
        combined, for_spell=for_spell
    )
    if effect is None:
        return None
    return 2, effect


from ._common import (  # noqa: E402
    _ANY_TYPE_MANA_STANDALONE_RE,
    _COLOR_COUNT_WORDS,
    _COUNTER_TARGET_RE,
    _DAMAGE_EACH_FILTERED_RE,
    _DAMAGE_EACH_GROUP_RE,
    _DAMAGE_TARGET_RE,
    _DISCARD_A_CARD_RE,
    _EXILE_TOP_OF_YOUR_LIBRARY_RE,
    _EXILE_UNTIL_QUALITY_RE,
    _EXILE_UNTIL_QUALITY_THIRD_PERSON_RE,
    _PLAY_PERMISSION_RE,
    _RETURN_TARGET_RE,
    _SELECT_FROM_TOP_KINDS,
    _SURVEIL_RE,
    _TOKENS_EQUAL_TO_ITS_STAT_RE,
    ExileAntecedent,
    PermissionDuration,
    _card_description_is_readable,
    _effect_condition_is_readable,
    _nonland_or_typed_card_matcher,
    _parse_card_group_qualifier,
    _permanent_id_and_name,
    _permission_duration,
    _players_in_apnap_order,
    _quality_matcher,
    _SacrificeRestriction,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _amount_reader,
    _announced_x,
    _bounded_quality_matcher,
    _fixed_or_where_x_amount,
    _for_each_multiplier,
    _that_many_or_notice,
    amount_expression,
    count_expression,
)
from .continuous import (  # noqa: E402
    _grant_cast_exiled_card_permission_from_sibling_static,
    _parse_tap_target_then_no_untap_clause,
    _targeted_layer_consequence,
    continuous_effects,
    layer_context_for,
    suspect,
)
from .counters import _counter_kind, put_counters_on_ability_targets  # noqa: E402

#: "`<source>` deals N damage to that player and you gain N life." (Oath of
#: Kaya's attack trigger): CR 608.2c's two instructions in printed order - the
#: damage to the player the trigger event named (`_parse_damage_that_player_
#: clause`'s own referent: the attacking opponent), then the controller's
#: life gain. The gain does not depend on the damage being dealt: a
#: prevented damage event still leaves "you gain N life" to happen.
_DAMAGE_THAT_PLAYER_AND_YOU_GAIN_RE = re.compile(
    rf"^(?P<damage>[^.]*\bdeals? {COUNT} damage to (?:that player|them|that creature'?s "
    rf"controller)) and you gain (?P<n>{COUNT}) life\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s19", for_spell=False)
def _merge_damage_that_player_and_gain_life_text(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_DAMAGE_THAT_PLAYER_AND_YOU_GAIN_RE`'s pair. Ability-only: "that
    player" is the triggering event's (CR 603.2)."""
    if for_spell or "and you gain" not in text.lower():
        return None
    match = _DAMAGE_THAT_PLAYER_AND_YOU_GAIN_RE.fullmatch(text.strip())
    if match is None:
        return None
    damage = _parse_damage_that_player_clause(match.group("damage"), for_spell=False)
    gained = parse_count(match.group("n"))
    if damage is None or gained is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        damage(game, ability)
        game.gain_life(game.controller_of(ability), gained)

    return effect


#: "put a +1/+1 counter on this creature and prevent all damage that would be
#: dealt to it this turn." (Favored Hoplite's heroic trigger): "it" is the
#: object the first clause named about itself - the ability's own source
#: (CR 608.2c) - so the second clause is the self-shield of `_parse_prevent_
#: all_damage_to_self_this_turn_clause` (CR 615.1a).
_SELF_CLAUSE_AND_PREVENT_TO_IT_RE = re.compile(
    r"^(?P<first>[^.]*?\bthis (?P<noun>creature|permanent)\b[^.]*?) and "
    r"(?P<second>prevent all (?:combat )?damage that would be dealt to) it this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _merge_self_clause_and_prevent_to_it_clauses(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """`_SELF_CLAUSE_AND_PREVENT_TO_IT_RE`'s pair, on an ability. A first
    clause that also names a target is refused: "it" could be that target."""
    if for_spell or "would be dealt to it this turn" not in text.lower():
        return None
    match = _SELF_CLAUSE_AND_PREVENT_TO_IT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or "target" in match.group("first").lower():
        return None
    first = _parse_mixed_clause(match.group("first"), for_spell=False)
    second = _parse_prevent_all_damage_to_self_this_turn_clause(
        f"{match.group('second')} this {match.group('noun').lower()} this turn.", for_spell=False
    )
    if first is None or second is None:
        return None
    return [first, second]


from .damage import (  # noqa: E402
    _lethal_amount_before_damage,
    _parse_damage_each_filtered_clause,
    _parse_damage_each_group_clause,
    _parse_damage_that_player_clause,
    _parse_prevent_all_damage_to_self_this_turn_clause,
    _prevent_next_damage_from_target,
    card_types_among_spells_cast_reader,
)
from .dispatch import (  # noqa: E402
    _parse_mixed_clause,
    _parse_mixed_clauses,
    _parse_targeted_clause,
    _spell_effect_or_notice,
    parse_clause_effect,
    parse_mixed_effect,
    parse_mixed_effect_for_spell,
)
from .draw_discard import (  # noqa: E402
    _discard_at_random,
    _discard_cards,
    _parse_each_player_may_discard_hand_and_draw_clause,
    _parse_target_player_draws_and_loses_life_clause,
)
from .library import (  # noqa: E402
    _owner_puts_it_into_library_destination_depth,
    _owner_puts_it_into_library_effect,
    _parse_card_group_alternatives,
    _put_rest_on_bottom,
    _reveal_take_one_of_each_kind,
    _reveal_until_n_of_kind,
    _shuffle_remainder_to_bottom,
)
from .life import _loses_life_unless_step  # noqa: E402
from .mana import read_add_mana_instruction  # noqa: E402
from .modal import (  # noqa: E402
    _choose_a_color,
    _choose_one_card,
    _parse_optional_player_clause,
    _parse_you_may_clause,
)
from .removal import (  # noqa: E402
    _cost_sacrificed_mana_value,
    _each_player_exile_until,
    _exile_cards_from_graveyard,
    _may_sacrifice_for_its_mana_value,
    _parse_exile_antecedent,
    _parse_exile_top_of_other_libraries_antecedent,
    _parse_exile_until_antecedent,
    _parse_exile_until_antecedent_third_person,
    _parse_sacrifice_consequence,
    _process_exiled_cards,
    _processable_exile_piles,
    _sacrifice_restriction,
    _spell_safe_exile_antecedent,
)
from .returns import (  # noqa: E402
    _parse_return_dead_self_to_hand_clause,
    _parse_return_self_to_owners_hand_clause,
    _parse_return_target_from_graveyard_tapped_and_attacking_clause,
)
from .search import (  # noqa: E402
    _read_search_count,
    _search_descriptions,
    _search_quality_is_readable,
)
from .text import (  # noqa: E402
    _as_sentence,
    _plain_resolution_sentences,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _is_notice_only,
    _parse_token_clause,
    _token_creator_for_count,
    _token_definition_from_words,
    create_continuous_effect,
)

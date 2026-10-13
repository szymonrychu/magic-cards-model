import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from magic_cards_model.phrases import with_indefinite_article

from ...data.subtypes import subtype_vocabulary
from ...models.card import Type
from ...models.card_state import (
    CardState,
)
from ...models.player import Player
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    parse_count,
)
from ..abilities import (
    has_mana_ability,
)
from ..casting import (
    PlayAction,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..triggers import (
    AbilityOnStack,
    is_ability,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from ._common import _HAVING_PATTERN, _MANA_COST_LIST, AbilityEffect, Effect, TargetedClause


def _search_library(
    game: "Game",
    player: Player,
    matches: Callable[[CardState], bool],
    *,
    source: str | None = None,
    source_id: str | None,
) -> CardState | None:
    """Find and remove one matching card from a player's library, then shuffle.

    CR 701.23a: "To search for a card in a zone, look at all cards in that zone
    (even if it's a hidden zone) and find a card that matches the given
    description." The whole library is looked at, not just the top.

    `optional=True` is CR 701.23b and is right for every card that reaches here:
    "If a player is searching a hidden zone for cards with a **stated quality**,
    such as a card with a certain card type or color, that player isn't required
    to find some or all of those cards even if they're present in that zone."
    Every search in this registry names a quality - a basic land, a Mountain or
    Plains card, a creature card with mana value 1 or less - so failing to find
    is always a legal answer. It is *not* CR 701.23d's "simply a quantity of
    cards", which must find what is there.

    **The shuffle happens now.** CR 701.24a randomizes the library and CR 701.24b
    keeps the found card out of it: "the found cards aren't included in the
    shuffle ... all the cards in that library except those are shuffled." Taking
    the card out first and shuffling the rest is the same event. `Game` seeds the
    shuffle from `shuffle_seed`, so a scenario stays reproducible while the
    library really is randomized - which is what a scenario asserting on library
    order after a fetch has to reckon with.

    The card is taken from the library here; the caller decides where it goes.
    """
    found = game.search_library(
        player, matches, count=1, optional=True, source=source, source_id=source_id
    )
    return found[0] if found else None


def _having_matcher(having: str) -> Callable[[CardState], bool]:
    """What `_HAVING_PATTERN` names, as a predicate on a card.

    "a mana ability" is `has_mana_ability` on the face this object has now
    (CR 712.8a: the front face in a library). A keyword list is "has any one
    of them" (the same "or" a type list prints), compared as whole keyword
    names against `CardState.keywords` - CR 702.34a's flashback is a different
    keyword from flash, so Faithless Looting is not "a card with flash".
    """
    lowered = having.strip().lower()
    if lowered == "a mana ability":
        return lambda state: has_mana_ability(state.card, state.up_face_name)
    wanted = {word.strip() for word in re.split(r",\s*|\s+or\s+", lowered) if word.strip()}

    def matches(state: CardState) -> bool:
        return bool(wanted & {keyword.lower() for keyword in state.keywords})

    return matches


def _and_having(
    base: Callable[[CardState], bool], having: Callable[[CardState], bool]
) -> Callable[[CardState], bool]:
    def matches(state: CardState) -> bool:
        return base(state) and having(state)

    return matches


#: CR 305.6: "The basic land types are Plains, Island, Swamp, Mountain, and
#: Forest. If an object uses the words 'basic land type,' it's referring to
#: one of these subtypes." A *subtype* question, independent of the "basic"
#: supertype - CR 305.8: "Any land that doesn't have this supertype is a
#: nonbasic land, even if it has a basic land type" - so a shockland or a
#: Ravnica dual (Steam Vents, Breeding Pool: `Land — Island Mountain`,
#: `Land — Forest Island`) genuinely qualifies for "a land card with a basic
#: land type" even though it is not itself a basic land. Folding this
#: wording into `_quality_matcher`'s existing "basic land" branch (which
#: requires the *supertype*, for "a basic land card") would be the wrong,
#: narrower rule.
_BASIC_LAND_TYPE_NAMES = frozenset({"Plains", "Island", "Swamp", "Mountain", "Forest"})


def _has_a_basic_land_type(state: CardState) -> bool:
    return any(subtype in _BASIC_LAND_TYPE_NAMES for subtype in state.card.subtypes)


def _quality_description(
    quality: str | None,
    max_mv: str | None,
    *,
    basic_land_type: bool = False,
    mana_costs: str | None = None,
    having: str | None = None,
    mv_cmp: str = "less",
) -> str:
    """One card description for a `Game.may`/`Game.ask` prompt, article and
    all - "a basic land card", "a creature card with mana value 1 or less".

    The qualifiers follow the word "card", in the order the card prints them;
    appending "card" after the bound produced "a creature with mana value 1 or
    less card" (battle report B5-07). `None` is an unrestricted search ("a
    card", CR 701.23d), which names no quality word at all.

    `mv_cmp` names which side of the bound the card printed - "less" (Ranger-
    Captain of Eos's ceiling, the long-standing default) or "greater" (a
    floor, Conduit of Ruin's/Fierce Empath's own "with mana value N or
    greater" - CR 202.3's number compared the other direction).
    """
    noun = "card" if quality is None else f"{quality} card"
    if basic_land_type:
        noun += " with a basic land type"
    if max_mv is not None:
        noun += f" with mana value {max_mv} or {mv_cmp}"
    if mana_costs is not None:
        noun += f" with mana cost {mana_costs}"
    if having is not None:
        noun += f" with {having}"
    return with_indefinite_article(noun)


#: One whole card description inside a search sentence, after its article:
#: "basic Plains card", "creature card with mana value 1 or less", "land card
#: with a basic land type". `_SEARCH_AND_PUT_RE` reads the qualifiers of the
#: last description it sees; `_search_descriptions` reads every description
#: with this.
_SEARCH_DESCRIPTION_RE = re.compile(
    r"(?:(?P<quality>.+?) )?card(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or (?P<mv_cmp>less|greater))?"
    r"(?: with mana cost (?P<mana_costs>" + _MANA_COST_LIST + r"))?"
    r"(?: with (?P<having>" + _HAVING_PATTERN + r"))?",
    re.IGNORECASE,
)


def _search_descriptions(
    match: re.Match[str],
) -> tuple[Callable[[CardState], bool], str] | None:
    """What one `_SEARCH_AND_PUT_RE` match finds, and how to name it.

    CR 701.23a: "find a card that matches the given description." The given
    description may be two whole descriptions joined by "or a" - Starfield
    Shepherd's "a basic Plains card or a creature card with mana value 1 or
    less" - and then a card matching either one matches, with each
    description's own qualifiers applying to it alone (the mana value bound is
    the creature's, not the Plains'). Returns the predicate and the prompt
    wording ("a basic Plains card or a creature card with mana value 1 or
    less"), or `None` when any description has a word this engine cannot read
    - the caller fails closed rather than searching for a narrower set.
    """
    quality = match.group("quality")
    groups = match.groupdict()
    whole = "card" if quality is None else f"{quality} card"
    if groups.get("basic_land_type"):
        whole += " with a basic land type"
    if match.group("max_mv") is not None:
        # `mv_cmp` is only captured by the regexes widened for a mana-value
        # *floor* (Conduit of Ruin's/Fierce Empath's "or greater") - every
        # other search regex still names only `max_mv` with a bare "or less"
        # baked into its own pattern, so `groups.get` (never `match.group`,
        # which raises for a name absent from the pattern that matched)
        # defaults those to the ceiling reading they have always had.
        whole += f" with mana value {match.group('max_mv')} or {groups.get('mv_cmp') or 'less'}"
    if groups.get("mana_costs"):
        whole += f" with mana cost {groups['mana_costs']}"
    if groups.get("having"):
        whole += f" with {groups['having']}"
    joined = quality is not None and re.search(r"\bcard\b", quality, re.IGNORECASE)
    halves = _SEARCH_DESCRIPTION_JOIN_RE.split(whole) if joined else [whole]
    matchers: list[Callable[[CardState], bool]] = []
    descriptions: list[str] = []
    for half in halves:
        piece = _SEARCH_DESCRIPTION_RE.fullmatch(half.strip())
        if piece is None:
            return None
        half_quality = piece.group("quality")
        if half_quality is not None and not _card_description_is_readable(half_quality):
            return None
        max_mv = piece.group("max_mv")
        mv_cmp = piece.group("mv_cmp") or "less"
        matcher = _bounded_quality_matcher(half_quality, max_mv, mv_cmp)
        with_basic_land_type = bool(piece.group("basic_land_type"))
        if with_basic_land_type:
            # CR 305.6/305.8: a *subtype* question, not the "basic" supertype -
            # see `_has_a_basic_land_type`'s own docstring.
            matcher = _and_has_a_basic_land_type(matcher)
        mana_costs = piece.group("mana_costs")
        if mana_costs:
            # CR 202.1: a printed-cost bound, not a mana-value one - see
            # `_exact_mana_cost_matcher`.
            exact = _exact_mana_cost_matcher(mana_costs)
            if exact is None:
                return None
            matcher = _and_has_exact_mana_cost(matcher, exact)
        having = piece.group("having")
        if having:
            matcher = _and_having(matcher, _having_matcher(having))
        matchers.append(matcher)
        descriptions.append(
            _quality_description(
                half_quality,
                max_mv,
                basic_land_type=with_basic_land_type,
                mana_costs=mana_costs or None,
                having=having or None,
                mv_cmp=mv_cmp,
            )
        )
    if len(matchers) == 1:
        return matchers[0], descriptions[0]

    def matches_either(state: CardState) -> bool:
        return any(matcher(state) for matcher in matchers)

    return matches_either, " or ".join(descriptions)


def _and_has_a_basic_land_type(base: Callable[[CardState], bool]) -> Callable[[CardState], bool]:
    def matches(state: CardState) -> bool:
        return base(state) and _has_a_basic_land_type(state)

    return matches


def _read_search_count(match: re.Match[str]) -> Callable[["Game", str], int | None] | None:
    """The card count `_SEARCH_AND_PUT_RE`/`_REFERENT_SEARCH_RE` name - CR
    701.23b's "up to N" or CR 701.23d's plain N - fixed once the clause
    parses, never re-read from the board (nothing in this family's shape
    varies by resolution the way `count_expression`'s "the number of ... you
    control" does) - unless the card itself says otherwise below.

    "that many" (The Earth King's "search ... for up to that many basic land
    cards", Settle the Wreckage's "that many basic land cards") is a count
    carried from an earlier instruction or the trigger event: the reader
    returns `that_many`'s number, or `None` when there is none, which the
    caller turns into a notice and no search at all.

    A bare "X" (`n_x`) reads only with CR 107.3f's own "where X is <expr>"
    tail (Harvest Season), through `count_expression`, once at resolution;
    a bare "X" with no such tail is left to the caller's `{X}` substitution.
    """
    groups = match.groupdict()
    if groups.get("any_number"):
        # CR 107.1c: "any positive number or zero" - bounded only by what the
        # library holds when the search is made.
        return lambda game, controller: len(game.player(controller).library)
    if groups.get("that_many"):
        return lambda game, _controller: that_many(game)
    if groups.get("n_x"):
        where_x = groups.get("where_x")
        if not where_x:
            return None
        return count_expression(where_x.strip())
    n = groups.get("n")
    amount = 1 if n is None else parse_count(n)
    if amount is None:
        return None
    return lambda _game, _controller: amount


def _search_and_place_for(match: re.Match[str], *, optional: bool) -> Callable[..., None] | None:
    """The core of one search-and-put match - search, then place the find -
    as a function of **whichever player is doing it**, independent of who
    controls the resolving spell or ability.

    Read off the match's own quality/mana-value/tapped/destination groups
    once, the same way `_build_search_clause` always has; only *who* the
    player is, and whether the search is optional, have moved out to the
    caller. `_build_search_clause` supplies the resolving spell or ability's
    own controller and reads "you may" off its own match for `optional`;
    `_parse_referent_clause`'s search branch (`_REFERENT_SEARCH_RE`) matches
    against text with no subject of its own left in it at all (the "its
    controller"/"that player" was already consumed by
    `_ANAPHORIC_SUBJECT_RE`) and is always the printed "may" - the resolution
    of *which player* has moved out of the search parser entirely and into
    `_parse_anaphoric_clause_pair`, which reads it off the previous clause's
    target rather than off this one's own text.

    The count (`_read_search_count`) is read once here too - Behold the
    Beyond's plain "three cards" and Primeval Titan's "up to two land cards"
    are the same shape with a different printed number, not two different
    instructions.
    """
    described = _search_descriptions(match)
    if described is None:
        return None
    count_reader = _read_search_count(match)
    if count_reader is None:
        return None
    matches, description = described
    tapped = bool(match.group("tapped"))
    dest_text = match.group("dest")
    destination = (
        Zone.HAND
        if dest_text.startswith("into your hand")
        else Zone.GRAVEYARD
        if dest_text.startswith("into your graveyard")
        else Zone.BATTLEFIELD
    )
    reveal = bool(match.groupdict().get("reveal"))
    unique_word = match.groupdict().get("unique_word")
    if unique_word is not None:
        description = (
            f"{description} that doesn't have the same name as a {unique_word} you control"
        )

    def run(
        game: "Game",
        player: Player,
        source: str,
        source_id: str | None,
        *,
        caused_by: str | None = None,
    ) -> None:
        count = count_reader(game, player.username)
        if count is None:
            _that_many_or_notice(game, match.group(0), source_id=source_id, source_name=source)
            return
        if optional and not game.may(
            player,
            f"search your library for {description}",
            source=source,
            source_id=source_id,
        ):
            return
        effective_matches = matches
        if unique_word is not None:
            # CR 201.2a: "Two or more objects have the same name if they have
            # at least one name in common ... An object with no name doesn't
            # have the same name as any other object." A split card has two
            # names (CR 709.4a); a Room permanent has only its unlocked
            # doors' names, and none while fully locked (CR 709.5) - so the
            # controlled side is read off each permanent's own current
            # `name`, the searched card's off its printed one, both split
            # into single names, at the moment the search actually runs (not
            # baked in at parse time - the controlled set can only be known
            # then).
            type_matcher = _named_type_matcher(unique_word)
            excluded_names = {
                name
                for permanent in game.permanents_controlled_by(player.username)
                if type_matcher(permanent)
                for name in _single_names(permanent.name)
            }

            def effective_matches(
                state: CardState, _base=matches, _excluded=excluded_names
            ) -> bool:
                return _base(state) and _excluded.isdisjoint(_single_names(state.card.name))

        game.search_and_put(
            player,
            effective_matches,
            destination=destination,
            count=count,
            reveal=reveal,
            tapped=tapped,
            source=source,
            source_id=source_id,
            caused_by=caused_by,
        )

    return run


def _single_names(name: str) -> set[str]:
    """Each individual name in `name` - a split card's "Left // Right" is two
    (CR 709.4a) - and none for an object with no name (CR 201.2a)."""
    return {part for part in name.split(" // ") if part}


def _build_search_clause(match: re.Match[str], *, for_spell: bool) -> TargetedClause | None:
    """The effect for one `_SEARCH_AND_PUT_RE` match, as a `TargetedClause` -
    usable directly by `parse_search_and_put_effect`'s whole-text callers and
    by `_parse_mixed_clause`'s per-clause dispatch alike.

    Always the resolving spell or ability's own controller (CR 701.23g's "you
    may" is that player's choice). "Its controller may search ..." - Ghost
    Quarter's and White Orchid Phantom's own half of the deal - is a different
    sentence naming a different player and is read by
    `_parse_anaphoric_clause_pair` instead, paired with the destroy clause
    ahead of it; `_SEARCH_AND_PUT_RE`'s subject group no longer offers that
    alternative at all (see the regex's own comment).
    """
    optional = bool((match.group("subject") or "").strip())
    run = _search_and_place_for(match, optional=optional)
    if run is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        controller = game.controller_of(stack_object)
        # Ashiok, Dream Render's gate: this shape is always "you may search
        # your library" or a mandatory "search your library" (never "its
        # controller may", which `_parse_anaphoric_clause_pair` reads instead,
        # below) - the resolving spell or ability's own controller is both the
        # cause and the searcher, exactly the self-search
        # `machines.casting_restrictions.search_prohibition_source` reaches.
        run(
            game,
            controller,
            source,
            source_id_of(stack_object),
            caused_by=controller.username,
        )

    return effect


#: "Search your library for a `<quality>` card, reveal it, put it into your
#: hand or graveyard, then shuffle." - Dina's Guidance. `_SEARCH_AND_PUT_RE`'s
#: own `dest` group never reads this: it offers "into your hand", "into your
#: graveyard" and "onto the battlefield" as three independent, mutually
#: exclusive destinations a card picks one of at print time, never a choice
#: between two of them made by a player at resolution (CR 608.2d) - so this
#: is its own reader rather than a fourth `dest` alternative that would have
#: to smuggle a decision into a group `_search_and_place_for` currently reads
#: as a fixed `Zone`. A full-text Scryfall search this session found no
#: second printing sharing this exact "hand or graveyard" destination choice
#: (see `MEMORY.md`); the quality word is still read the general way every
#: other search reader in this file does, so any future card printing the
#: identical template is covered without a second row here.
_SEARCH_HAND_OR_GRAVEYARD_RE = re.compile(
    r"^search (?:your|their) library for an? (?P<quality>.+?) card, reveal it, "
    r"put it into your hand or graveyard, then shuffle\.?$",
    re.IGNORECASE,
)


#: "search your library for a basic Forest card and a basic Plains card,
#: reveal those cards, put them into your hand, then shuffle" (Yasharn,
#: Implacable Earth) - one CR 701.23a search for one card of each of two
#: qualities; CR 701.23b lets the searcher find either, both or neither (the
#: card's own ruling), and CR 701.20a reveals what was found.
_SEARCH_TWO_QUALITIES_TO_HAND_RE = re.compile(
    r"^search your library for an? (?P<first>[^,.]+?) card and an? (?P<second>[^,.]+?) card"
    r"(?:,|\.)\s*reveal (?:those cards|them), put them into your hand, then shuffle\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s34")
def _parse_search_two_qualities_to_hand_text(text: str) -> AbilityEffect | None:
    """`_SEARCH_TWO_QUALITIES_TO_HAND_RE`'s shape, or `None` - read whole, ahead
    of the clause splitter, which would cut the "and" between the qualities."""
    if "card and a" not in text:
        return None
    match = _SEARCH_TWO_QUALITIES_TO_HAND_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None
    qualities = [match.group("first").strip(), match.group("second").strip()]
    if not all(_card_description_is_readable(quality) for quality in qualities):
        return None
    matchers = [_quality_matcher(quality) for quality in qualities]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        if library_search_blocked(game, controller.username) is not None:
            return
        found: list[CardState] = []
        for matches in matchers:
            found += game.search_library(
                controller,
                matches,
                count=1,
                optional=True,
                shuffle=False,
                source=source,
                source_id=source_id,
                caused_by=controller.username,
            )
        for card in found:
            game.reveal(card, source=source)
            controller.add(card, Zone.HAND)
        game.shuffle_library(controller)

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_hand_or_graveyard_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_HAND_OR_GRAVEYARD_RE`'s shape, or `None`.

    The printed text carries no "you may" - the search itself is mandatory
    (unlike the "you may search" family `_SEARCH_AND_PUT_RE`'s own `subject`
    group reads) - so this never asks `Game.may` at all. CR 701.23b already
    makes the *find* optional regardless of wording: "If a player is
    searching a hidden zone for cards with a stated quality ... that player
    isn't required to find some or all of those cards even if they're
    present" - `_search_library`'s own `optional=True` is exactly that, and
    is enough on its own for a search to legally come up with nothing.
    CR 608.2d's own "put it into X or Y" is a real choice once a card is
    found, asked of the searcher (the resolving spell's own controller,
    CR 701.23g) through `DecisionKind.PUT_INTO_HAND_OR_GRAVEYARD` - the same
    plain boolean shape `DecisionKind.PUT_ON_TOP_OR_BOTTOM` already is for
    its own two-zone choice.
    """
    match = _SEARCH_HAND_OR_GRAVEYARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality = match.group("quality").strip()
    if not _card_description_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        # `_search_library` already performs CR 701.24a's shuffle itself
        # (see its own docstring: "the shuffle happens now"), whether or not
        # anything was found - so nothing further is shuffled here.
        found = _search_library(game, controller, matches, source=source, source_id=source_id)
        if found is None:
            return
        game.reveal(found, source=source)
        to_hand = game.ask(
            Decision(
                kind=DecisionKind.PUT_INTO_HAND_OR_GRAVEYARD,
                player=controller.username,
                prompt=f"put {found.name} into your hand or graveyard",
                source=source,
                source_id=source_id,
            )
        )
        assert isinstance(to_hand, bool)
        if to_hand:
            controller.add(found, Zone.HAND)
        else:
            game.put_into_graveyard(found)

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a search, fed either the whole ability text (a fetchland
    with nothing else on it) or one clause a multi-clause dispatcher split out
    and rejoined - see `_rejoin_search_clauses`.
    """
    match = _SEARCH_AND_PUT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    return _build_search_clause(match, for_spell=for_spell)


#: "Search your library for [up to] two `<quality>` cards[, reveal them,]
#: put one `<dest>` and the other `<dest>`[, then shuffle]." - Troop of
#: Ponies' own activated ability. `_SEARCH_AND_PUT_RE`'s own `dest` group
#: names exactly one destination for the whole find; this is CR 701.23a's
#: identical single search, only with the two cards it finds split across
#: two named destinations instead of both going to the same one. Built with
#: the *same* quality/basic-land-type/mana-value/mana-cost/having/reveal
#: group names `_SEARCH_AND_PUT_RE` uses so `_search_descriptions` (which
#: only ever reads those groups off whatever match it is given) reads this
#: match exactly the way it already reads that one - one description parser
#: shared by both search shapes, never a second copy of it.
_SEARCH_SPLIT_DESTINATION_RE = re.compile(
    r"search (?:your|their) library for "
    rf"(?:(?P<upto>up to )?(?P<n>{COUNT}) )"
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?: with mana cost (?P<mana_costs>" + _MANA_COST_LIST + r"))?"
    r"(?: with (?P<having>" + _HAVING_PATTERN + r"))?"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put one "
    r"(?P<dest1>into your hand|into your graveyard|onto the battlefield(?P<tapped1> tapped)?)"
    r" and the other "
    r"(?P<dest2>into your hand|into your graveyard|onto the battlefield(?P<tapped2> tapped)?)"
    r"(?:, then shuffle)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_split_destination_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_SPLIT_DESTINATION_RE`'s shape, or `None`.

    CR 701.23a is one search that finds `count` cards at once (`Game.
    search_library`'s own docstring: "one choice, over every candidate at
    once"), not two independent finds - a second `search_library` call for
    "the other" card would let a second, different card slip in that the
    first search's own count ceiling already excluded. Every card this
    search actually finds is asked once, as one `CHOOSE_CARDS` decision, which
    of them goes to `dest1`; whatever is left goes to `dest2`. With only one
    card found (the library came up short, CR 701.23d's "or as many as
    possible"), `Game.ask` already answers a one-option question without
    asking (see `search_library`'s own docstring), so that lone card is
    simply assigned to `dest1` and "the other" clause has nothing left to
    place - CR 608.2b's ordinary "some of this instruction can't happen"
    tolerance, not a special case coded here.
    """
    match = _SEARCH_SPLIT_DESTINATION_RE.fullmatch(clause.strip())
    if match is None:
        return None
    described = _search_descriptions(match)
    if described is None:
        return None
    matches, description = described
    count = parse_count(match.group("n"))
    if count != 2:
        # The "one ... and the other ..." shape only ever prints on a
        # two-card search - a different count here is a template this
        # parser was not built to read, not a card this wave proves.
        return None
    optional = bool(match.group("upto"))
    reveal = bool(match.group("reveal"))
    dest1_text = match.group("dest1")
    dest2_text = match.group("dest2")
    dest1 = _split_destination_zone(dest1_text)
    dest2 = _split_destination_zone(dest2_text)
    tapped1 = bool(match.group("tapped1"))
    tapped2 = bool(match.group("tapped2"))

    def place(
        game: "Game", controller: Player, states: list[CardState], zone: Zone, tapped: bool
    ) -> None:
        # `Game.search_library` already pulled every one of `states` out of
        # the library's own list (its own docstring: "the found cards
        # aren't included in the shuffle"), so - exactly like `Game.search_
        # and_put`'s identical loop right after its own `search_library`
        # call - nothing here re-checks `state.zone`: it is stale (still
        # reading whatever zone the card was in before the search), not a
        # zone list membership `controller.move` could still act on.
        for state in states:
            if zone is Zone.HAND:
                controller.add(state, Zone.HAND)
            elif zone is Zone.GRAVEYARD:
                game.put_into_graveyard(state)
            else:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        found = game.search_library(
            controller,
            matches,
            count=count,
            optional=optional,
            shuffle=True,
            source=source,
            source_id=source_id,
        )
        if reveal:
            for state in found:
                game.reveal(state, source=source)
        if not found:
            return
        pick_count = min(1, len(found))
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"put one {description} {dest1_text}",
                source=source,
                source_id=source_id,
                amount=pick_count,
                cards=tuple(state.id for state in found),
            )
        )
        by_id = {state.id: state for state in found}
        first = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        rest = [state for state in found if state not in first]
        place(game, controller, first, dest1, tapped1)
        place(game, controller, rest, dest2, tapped2)

    return effect


#: Elven Passage's own activated ability: "Search your library for a basic
#: land card, put it onto the battlefield tapped, then shuffle. You may
#: behold a `<quality>`. If you do, untap that land." CR 701.4a: "'Behold a
#: [quality]' means 'Reveal a [quality] card from your hand or choose a
#: [quality] permanent you control on the battlefield.'" - a resolution-time
#: action here, not a cost the way `machines/cost.py`'s own `behold_cost`
#: reads it inside an activation cost; `Game.search_library`'s own docstring
#: is the reason this stays one whole-text reader instead of a per-clause
#: split: "that land" (CR 400.7/CR 607.1) names the specific card the search
#: just found, which only a caller holding it live can point at.
_SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_BEHOLD_UNTAP_RE = re.compile(
    r"^search (?:your|their) library for "
    rf"(?:(?P<n>{COUNT}) )?"
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r", put it onto the battlefield tapped, then shuffle\.\s*"
    r"you may behold an? (?P<behold_quality>[a-z' -]+?)\.\s*"
    r"if you do, untap that land\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s34")
def _parse_search_put_battlefield_tapped_then_behold_untap_clause(
    text: str,
) -> AbilityEffect | None:
    """`_SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_BEHOLD_UNTAP_RE`'s shape, or
    `None`.

    The single `CHOOSE_CARDS` question folds CR 701.4a's own "or" and CR
    608.2d's "you may" into one ask the same way `Game.search_library`'s own
    docstring already does for an ordinary optional search: every card in
    either pool - a matching hand card or a matching battlefield permanent -
    is one candidate list, `amount=1, exact=False` so declining (zero chosen)
    is a legal answer, and the pool is offered at all only when it is
    non-empty (asking a question with no legal affirmative answer is refused
    everywhere else in this module too). CR 701.4a's "reveal" only applies to
    the hand half - a battlefield permanent is already public information
    (CR 400.2) - so only a hand card chosen this way is actually revealed.
    """
    match = _SEARCH_PUT_BATTLEFIELD_TAPPED_THEN_BEHOLD_UNTAP_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    quality_text = (match.group("quality") or "").strip()
    base_matcher = _quality_matcher(quality_text) if quality_text else (lambda state: True)
    with_basic_land_type = bool(match.group("basic_land_type"))
    if with_basic_land_type:

        def search_matches(
            state: CardState, base: Callable[[CardState], bool] = base_matcher
        ) -> bool:
            return base(state) and _has_a_basic_land_type(state)
    else:
        search_matches = base_matcher
    n = parse_count(match.group("n")) if match.group("n") else 1
    if n is None:
        return None
    behold_quality = match.group("behold_quality").strip()
    behold_matches = _quality_matcher(behold_quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.player(ability.controller)
        source = ability.source_name
        source_id = source_id_of(ability)
        found = game.search_library(
            controller,
            search_matches,
            count=n,
            optional=False,
            shuffle=True,
            source=source,
            source_id=source_id,
        )
        land: CardState | None = None
        if found:
            land = found[0]
            game.put_onto_battlefield(land, controller.username, tapped=True)
        hand_candidates = [state for state in controller.hand if behold_matches(state)]
        battlefield_candidates = [
            state
            for state in game.permanents_controlled_by(controller.username)
            if behold_matches(state)
        ]
        candidates = hand_candidates + battlefield_candidates
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"behold {with_indefinite_article(behold_quality)}",
                source=source,
                source_id=source_id,
                amount=1,
                exact=False,
                cards=tuple(state.id for state in candidates),
            )
        )
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id.get(chosen_ids[0])
        if chosen is None:
            return
        if chosen.zone is Zone.HAND:
            game.reveal(chosen, source=source)
        if land is not None and land.zone is Zone.BATTLEFIELD:
            land.untap()

    return effect


#: Roads Go Ever, Ever On's own chapter I: "Search your library for up to two
#: basic Plains cards, exile them, then shuffle. You gain 2 life." A fifth
#: search destination beside `_SEARCH_AND_PUT_RE`'s hand/battlefield/
#: graveyard trio and `_SEARCH_REVEAL_SHUFFLE_TOP_RE`'s own top-of-library
#: one: CR 701.23a's identical search, "exile" the destination instead of a
#: "put ... into/onto" phrase. Built with the same quality/basic-land-type/
#: mana-value/mana-cost/having group names `_SEARCH_AND_PUT_RE` uses, so
#: `_search_descriptions` reads this match exactly the way it reads that
#: one. No card in the pool names it, but `_source_reads_its_exiled_cards`/
#: `link_cards_exiled_during` (CR 607.2a, `models/game.py`'s own generic
#: post-resolution hook) already tag whatever this exiles as "exiled with"
#: the Saga automatically, from nothing more than this ability's own "exile"
#: verb and the card's *other* printed ability reading "cards exiled with
#: this Saga" - no linking code belongs in this reader at all.
_SEARCH_AND_EXILE_THEN_SHUFFLE_RE = re.compile(
    r"search (?:your|their) library for "
    rf"(?:(?P<upto>up to )?(?P<n>{COUNT}) )"
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?: with mana cost (?P<mana_costs>" + _MANA_COST_LIST + r"))?"
    r"(?: with (?P<having>" + _HAVING_PATTERN + r"))?"
    r", exile (?:it|them)(?P<face_down> face down)?(?:, then shuffle)?"
    rf"(?:\.\s*you gain (?P<life>{COUNT}) life)?"
    # Hoarding Broodlord: CR 400.7's own bound on the permission - "for as long
    # as that card remains exiled" ends the moment the card leaves exile.
    r"(?P<play>\.\s*for as long as that card remains exiled, you may play it)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_and_exile_then_shuffle_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_AND_EXILE_THEN_SHUFFLE_RE`'s shape, or `None`."""
    match = _SEARCH_AND_EXILE_THEN_SHUFFLE_RE.fullmatch(text.strip())
    if match is None:
        return None
    described = _search_descriptions(match)
    if described is None:
        return None
    matches, _description = described
    n = parse_count(match.group("n"))
    if n is None:
        return None
    life = parse_count(match.group("life")) if match.group("life") else 0
    face_down = match.group("face_down") is not None
    play = match.group("play") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        # CR 701.23b: a stated-quality search is always declinable per find -
        # `Game.search_and_put`'s own `optional=True` (see its docstring)
        # is the identical reading this reuses, whether the card prints "up
        # to N" or a bare count. Nothing here gates the search itself behind
        # a `game.may`: that gate belongs only to a printed "you may search"
        # subject, which no card using this template prints.
        found = game.search_library(
            controller,
            matches,
            count=n,
            optional=True,
            shuffle=True,
            source=source,
            source_id=source_id,
        )
        for exiled in game.exile_cards(found):
            if face_down:
                exiled.face_up = False
            if play:
                game.grant_play_permission(
                    exiled,
                    controller.username,
                    action=PlayAction.PLAY,
                    source_name=source,
                    rule="CR 601.3, CR 611.2a",
                    zone=Zone.EXILE,
                    until_end_of_turn=False,
                )
        if life:
            game.gain_life(controller, life)

    return effect


def parse_search_exile_then_play_whole_text(text: str) -> TargetedClause | None:
    """Hoarding Broodlord's two sentences read whole: the search-and-exile and
    the permission that is bound to what it exiled ("that card")."""
    flat = " ".join(text.split())
    if "remains exiled, you may play it" not in flat.lower():
        return None
    return _parse_search_and_exile_then_shuffle_clause(flat, for_spell=False)


#: "Search your library for `<quality>` card[s][, reveal it,] then shuffle
#: and put that card on top [of your library]." - Loyal Tutor's own shape,
#: the classic Mystical Tutor family, widened for Insatiable Avarice's own
#: first Spree mode ("Search your library for a card, then shuffle and put
#: that card on top."), which prints no reveal at all - CR 701.23e's reveal
#: is its own instruction, not implied by the search, so a card that omits
#: it simply never turns the found card face up (Ainok Guide's own second
#: mode still prints "reveal it" and is unaffected: `reveal` only fires when
#: the clause actually names it). A fourth search destination beside
#: `_SEARCH_AND_PUT_RE`'s hand/battlefield pair: CR 701.24a's shuffle happens
#: to the *remaining* library before the find goes back, not after (the
#: found card is already removed from the library by `Game.search_library`
#: before its own shuffle runs, so the shuffle never touches it), and the
#: find is put back on top of the very library it came out of rather than
#: into a different zone at all - `Game.put_cards_into_library`'s own
#: `to_bottom=False` arm is exactly CR 701.20d's "a card put on top sits
#: above every card already there".
#:
#: `max_mv`'s bound reads "or greater" as well as "or less" (`_search_
#: descriptions`/`_bounded_quality_matcher`) - Conduit of Ruin's own cast
#: trigger, "search your library for a colorless creature card with mana
#: value 7 or greater", is this same family with a floor instead of Ranger-
#: Captain of Eos's ceiling; a trigger reaches this parser exactly as a
#: spell does, both being a `TargetedClause` of `for_spell`'s two callers.
_SEARCH_REVEAL_SHUFFLE_TOP_RE = re.compile(
    r"(?P<subject>you may )?"
    r"search (?:your|their) library for "
    rf"(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<that_many>that many)) "
    r"(?:(?P<quality>.+?) )?card(?:s)?"
    r"(?P<basic_land_type> with a basic land type)?"
    # Conduit of Ruin's own floor, "with mana value 7 or greater" - the same
    # bidirectional bound `_SEARCH_AND_PUT_RE` reads, widened here too.
    r"(?: with mana value (?P<max_mv>\d+) or (?P<mv_cmp>less|greater))?"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?, then shuffle"
    r"(?: (?:your|their) library)? "
    r"and put (?:it|them|that card|those cards) on top(?: of (?:your|their) library)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_reveal_shuffle_top_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_REVEAL_SHUFFLE_TOP_RE`'s shape, or `None`."""
    match = _SEARCH_REVEAL_SHUFFLE_TOP_RE.fullmatch(clause.strip())
    if match is None:
        return None
    described = _search_descriptions(match)
    if described is None:
        return None
    count_reader = _read_search_count(match)
    if count_reader is None:
        return None
    matches, description = described
    optional = bool((match.group("subject") or "").strip())
    reveal = bool(match.group("reveal"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        if optional and not game.may(
            player,
            f"search your library for {description}",
            source=source,
            source_id=source_id,
        ):
            return
        found = game.search_library(
            player,
            matches,
            count=count_reader(game, player.username),
            optional=True,
            shuffle=True,
            source=source,
            source_id=source_id,
        )
        if reveal:
            for state in found:
                game.reveal(state, source=source)
        game.put_cards_into_library(found, to_bottom=False)

    return effect


#: "Search your library for up to `<n>` `<quality>` cards with different
#: names, reveal them, put them into your hand, then shuffle." - Fblthp,
#: Knows the Way's own ETB. CR 701.23a's "find a card that matches the given
#: description" still names one card at a time, but "with different names"
#: narrows the *candidate pool itself*, one pick at a time, to exclude any
#: name already chosen this search - offering two Forests as simultaneous
#: choices in one CR 701.23a decision would let both be "found" at once and
#: break the printed restriction the instant they are both legal answers to
#: the same question.
_SEARCH_DISTINCT_NAMES_RE = re.compile(
    r"(?P<subject>you may )?"
    r"search (?:your|their) library for "
    rf"(?P<upto>up to )?(?:(?P<n>{COUNT})|(?P<that_many>that many)) "
    r"(?:(?P<quality>.+?) )?cards?"
    r"(?P<basic_land_type> with a basic land type)?"
    r"(?: with mana value (?P<max_mv>\d+) or less)?"
    r"(?: with mana cost (?P<mana_costs>" + _MANA_COST_LIST + r"))?"
    r" with different names"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put (?:it|them|that card|those cards) "
    r"(?P<dest>into your hand|onto the battlefield(?P<tapped> tapped)?)"
    r"(?:, then shuffle)?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_distinct_names_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SEARCH_DISTINCT_NAMES_RE`'s shape, or `None`."""
    match = _SEARCH_DISTINCT_NAMES_RE.fullmatch(clause.strip())
    if match is None:
        return None
    described = _search_descriptions(match)
    if described is None:
        return None
    count_reader = _read_search_count(match)
    if count_reader is None:
        return None
    base_matches, description = described
    dest_text = match.group("dest")
    to_hand = dest_text.startswith("into your hand")
    tapped = bool(match.group("tapped"))
    reveal = bool(match.groupdict().get("reveal"))
    optional = bool((match.group("subject") or "").strip())

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        count = count_reader(game, player.username)
        if optional and not game.may(
            player,
            f"search your library for up to {count} {description} with different names",
            source=source,
            source_id=source_id,
        ):
            return
        found: list[CardState] = []
        seen_names: set[str] = set()
        for _ in range(max(count, 0)):

            def not_yet_found(state: CardState) -> bool:
                return base_matches(state) and (state.name or "") not in seen_names

            picked = game.search_library(
                player,
                not_yet_found,
                count=1,
                optional=True,
                shuffle=False,
                source=source,
                source_id=source_id,
            )
            if not picked:
                break
            found.extend(picked)
            seen_names.add(picked[0].name or "")
        if reveal:
            for state in found:
                game.reveal(state, source=source)
        for state in found:
            if to_hand:
                player.add(state, Zone.HAND)
            else:
                game.put_onto_battlefield(state, player.username, tapped=tapped)
        game.shuffle_library(player)

    return effect


#: Beseech the Queen's own shape: "Search your library for a card with mana
#: value less than or equal to <the number of lands you control>, reveal it,
#: put it into your hand, then shuffle." `_SEARCH_AND_PUT_RE`'s own `max_mv`
#: group is `\d+` only - a literal printed digit, Ranger-Captain of Eos's
#: "mana value 1 or less" - so a search bounded by a live board count instead
#: never matches it and the whole clause was falling through to nothing. CR
#: 701.23a/701.23b: still a plain search with a stated quality (failing to
#: find remains legal); CR 701.24a/701.24b: `_search_library` already folds
#: the shuffle in. No quality beyond the mana-value ceiling is printed ("a
#: card", not "a creature card"), so `_quality_matcher` plays no part here.
_SEARCH_MV_LTE_COUNT_RE = re.compile(
    r"^search (?:your|their) library for a card with mana value less than or "
    r"equal to (?P<expr>.+?), reveal it, put it into your hand, then shuffle\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_mv_lte_count_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_SEARCH_MV_LTE_COUNT_RE`'s shape, or `None` if this is not it."""
    match = _SEARCH_MV_LTE_COUNT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    counter = count_expression(match.group("expr"))
    if counter is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        ceiling = counter(game, controller.username)

        def matches(state: CardState) -> bool:
            return state.mana_value <= ceiling

        game.search_and_put(
            controller,
            matches,
            destination=Zone.HAND,
            reveal=True,
            source=source,
            source_id=source_id_of(stack_object),
        )

    return effect


#: Celestial Reunion's own shape: "Search your library for a creature card
#: with mana value X or less, reveal it, put it into your hand, then
#: shuffle. If this spell's additional cost was paid and the revealed card
#: is the chosen type, put that card onto the battlefield instead of putting
#: it into your hand." Two sentences read as one clause (CR 608.2c), the
#: same way `_X_DAMAGE_DIVIDED_DOUBLED_RE` reads Shatterskull Smashing's
#: pair whole rather than through the generic per-clause splitter, because
#: the second sentence's "the revealed card" is CR 608.2c's own anaphoric
#: reference to what the first one just found - there is nothing for a
#: clause-by-clause dispatch to hand it. "This spell's additional cost was
#: paid" is CR 607.2i's own linked read, off `CastRecord.behold_chosen_type_
#: paid` (folded into `optional_additional_cost_paid`, the same generic
#: door Cinder Strike's and Burning Curiosity's own identical phrase already
#: use); "the chosen type" is CR 607.2d's, off `CastRecord.chosen_creature_
#: type` - both set by `Casting.behold_chosen_type_for_cost` as the
#: optional cost is paid, since this is a sorcery with no permanent
#: incarnation to carry a CR 614.12a `CardState.choice` on.
_BEHOLD_CHOSEN_TYPE_SEARCH_RE = re.compile(
    r"^search (?:your|their) library for a creature card with mana value "
    r"(?P<mv_expr>[a-z0-9]+) or less, reveal it, put it into your hand, then shuffle\.\s*"
    r"if this spell'?s additional cost was paid and the revealed card is the chosen type, "
    r"put that card onto the battlefield instead of putting it into your hand\.?$",
    re.IGNORECASE | re.DOTALL,
)


@SPELL_TEXT.rung("s17", for_spell=True)
def _parse_behold_chosen_type_search_clause(text: str, *, for_spell: bool) -> Effect | None:
    """`_BEHOLD_CHOSEN_TYPE_SEARCH_RE`'s shape, or `None`.

    Spell-only (CR 608.2c's card is a sorcery): `for_spell` mirrors the
    `for_spell` guard every other search-and-put reader in this module
    already carries, refusing an activated- or triggered-ability reading of
    a shape no printing gives one."""
    if not for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    match = _BEHOLD_CHOSEN_TYPE_SEARCH_RE.fullmatch(whole)
    if match is None:
        return None
    if match.group("mv_expr").lower() != "x":
        # CR 107.3a: the printed cap is always X on this shape; a literal
        # digit is a different card this reader has never seen, and is left
        # for whatever prints it to add its own read rather than guessed at.
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        record = game.cast_record(spell)
        ceiling = record.x_value

        def matches(state: CardState) -> bool:
            return Type.CREATURE in state.types and state.mana_value <= ceiling

        found = game.search_library(
            controller,
            matches,
            count=1,
            optional=True,
            shuffle=False,
            source=spell.name,
            source_id=source_id_of(spell),
        )
        if found:
            (card,) = found
            game.reveal(card, source=spell.name)
            chosen_type = record.chosen_creature_type
            to_battlefield = (
                record.optional_additional_cost_paid
                and chosen_type is not None
                and chosen_type in {subtype.lower() for subtype in card.subtypes}
            )
            if to_battlefield:
                game.put_onto_battlefield(card, controller.username)
            else:
                controller.add(card, Zone.HAND)
        game.shuffle_library(controller)

    return effect


#: Sisay, Weatherlight Captain's own shape: "Search your library for a
#: `<quality>` card with mana value less than this permanent's power, put
#: that card onto the battlefield, then shuffle." `_SEARCH_MV_LTE_COUNT_RE`'s
#: own `<expr>` is a board count (`count_expression`, `(game, controller) ->
#: int`); this bound is a *source's own* characteristic (CR 613's computed
#: power) instead, which needs the source object itself, not just its
#: controller - `_self_normalized_effect_text` has already turned Sisay's own
#: printed name into "this permanent" by the time this ever runs, the same
#: normalisation `_COUNTER_ON_SELF_RE` relies on. No printed reveal
#: instruction (CR 701.23e), so the find goes straight to the battlefield
#: unrevealed - genuinely different from `_SEARCH_MV_LTE_COUNT_RE`'s reveal-
#: to-hand destination, which is why this is its own regex rather than a
#: widened `expr` on that one.
_SEARCH_MV_LESS_THAN_SELF_POWER_RE = re.compile(
    r"^search (?:your|their) library for a (?P<quality>.+?) card with mana value less than "
    r"this (?:permanent|creature)'s power, put that card onto the battlefield, "
    r"then shuffle\.?$",
    re.IGNORECASE,
)


def _parse_search_mv_less_than_self_power_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_MV_LESS_THAN_SELF_POWER_RE`'s shape - ability-only, the same
    reason `_parse_put_counters_on_self_clause` is: a spell has no permanent
    self to read a power off (CR 613 layers apply to objects on the
    battlefield)."""
    if for_spell:
        return None
    match = _SEARCH_MV_LESS_THAN_SELF_POWER_RE.fullmatch(clause.strip())
    if match is None:
        return None
    quality_matches = _quality_matcher(match.group("quality"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        source = ability.source(game)
        if source is None:
            return
        power = game.power_of(source)
        if power is None:
            return

        def matches(state: CardState) -> bool:
            return state.mana_value < power and quality_matches(state)

        game.search_and_put(
            game.controller_of(ability),
            matches,
            destination=Zone.BATTLEFIELD,
            source=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_search_mv_equal_to_sacrificed_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_MV_EQUAL_TO_SACRIFICED_RE`'s shape on a spell or ability that
    sacrificed a permanent to pay a cost - Neoform's and Eldritch Evolution's
    additional cost, Prime Speaker Vannifar's activation cost. The number is
    never printed: it is `_cost_sacrificed_mana_value`'s. A spell or ability
    that sacrificed nothing has no number to compare against, so nothing is
    searched for rather than a search bounded by the bare offset.

    Read by `_parse_mixed_clause` for the one-sentence form and by
    `_parse_unsplittable_whole_text` for Eldritch Evolution's
    two-sentence one, whose ". Put that card onto the battlefield" the
    clause splitter would otherwise cut away from its own search.
    """
    run = _sacrificed_mana_value_search(clause)
    if run is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        sacrificed = _cost_sacrificed_mana_value(game, stack_object)
        if sacrificed is None:
            return
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        run(
            game,
            game.controller_of(stack_object),
            sacrificed,
            source,
            source_id_of(stack_object),
        )

    return effect


#: Evolving Door's whole ability text: "Count the colors of the sacrificed
#: creature, then search your library for a creature card that's exactly that
#: many colors plus one. Exile that card, then shuffle. You may cast the
#: exiled card." Read whole (`text._parse_unsplittable_whole_text`) because the
#: clause split would cut "that many colors plus one" away from the count it
#: names. CR 105.1 counts the colours; the sacrificed permanent's count was
#: taken as the cost was paid (`AbilityOnStack.cost_sacrificed_color_counts`,
#: CR 608.2h), so a sacrificed token that has ceased to exist still counts.
_COUNT_COLORS_SEARCH_EXILE_CAST_RE = re.compile(
    r"^count the colors of the sacrificed (?P<noun>[a-z]+), then search your library for "
    r"an? (?P<quality>[a-z]+) card that's exactly that many colors plus one\. "
    r"exile that card, then shuffle\. you may cast the exiled card\.?$",
    re.IGNORECASE,
)


def _parse_count_colors_search_exile_cast_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_COUNT_COLORS_SEARCH_EXILE_CAST_RE`'s shape - ability-only (a spell's
    sacrifice is not recorded at resolution). A sacrifice that paid nothing
    leaves nothing to count, so nothing is searched for. The find is exiled
    (CR 701.23a, the library shuffled by `search_library`) and may then be cast
    paying its mana cost (CR 608.2g), at the sorcery speed the card prints for
    its activation."""
    if for_spell:
        return None
    match = _COUNT_COLORS_SEARCH_EXILE_CAST_RE.fullmatch(clause.strip())
    if match is None or not _search_quality_is_readable(match.group("quality")):
        return None
    quality_matches = _quality_matcher(match.group("quality"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        counts = stack_object.cost_sacrificed_color_counts
        if not counts:
            return
        wanted = counts[0] + 1
        controller = game.controller_of(stack_object)
        found = game.search_library(
            controller,
            lambda state: quality_matches(state) and len(state.card.colors or ()) == wanted,
            count=1,
            optional=True,
            source=stack_object.source_name,
            source_id=source_id_of(stack_object),
        )
        game.exile_cards(found)
        for card in found:
            game.may_cast_during_resolution(
                card,
                controller.username,
                prompt=f"cast {card.name}",
                source=stack_object.source_name,
                source_id=source_id_of(stack_object),
                source_name=stack_object.source_name,
                rule="CR 608.2g",
                pays_mana_cost=True,
            )

    return effect


#: Primeval Titan's own shape: "search your library for up to two land cards,
#: put them onto the battlefield tapped, then shuffle." Used to need its own
#: regex and parser (`_SEARCH_UP_TO_N_AND_PUT_RE`/`_parse_search_up_to_n_
#: and_put_clause`, both retired) because `_SEARCH_AND_PUT_RE`'s count slot
#: was a literal "a"/"an" and its "put it"/"reveal it" pronouns were singular
#: throughout - a counted, plural "up to N `<quality>` cards"/"put them"
#: search did not match it at all, so the whole clause fell through to
#: nothing. `_SEARCH_AND_PUT_RE` now reads any `{COUNT}` in that slot (see its
#: own comment) and both pronoun numbers, so this shape - and Behold the
#: Beyond's un-"up to" "three cards", and Tooth and Nail's hand-bound "up to
#: two creature cards, reveal them, put them into your hand" - are one
#: `_parse_search_clause` path rather than two.
def parse_search_and_put_effect(text: str) -> AbilityEffect | None:
    """Recognise a plain library search off the ability's own printed text,
    instead of a per-card table entry - see `_SEARCH_AND_PUT_RE`.

    A fetchland's cost (CR 602.1a: everything before the colon - {T}, pay 1
    life, sacrifice the land) is `machines/cost.py`'s business; this is only
    the effect after it, and the same function reads Flagstones of Trokair's
    trigger and Expedition Map's activated ability, because all three are one
    sentence of this shape with nothing else in it.

    The found card arrives **untapped** unless the sentence says "tapped"
    (CR 110.5b's default for anything entering the battlefield) - a shockland
    found this way then asks its own "as this land enters, you may pay 2 life"
    question, a replacement effect (CR 614.12) `Game.enter_the_battlefield`
    already consults. `put_onto_battlefield` is used and not a land drop:
    CR 305.1's one-land-per-turn restriction applies to *playing* a land, and
    this is an effect putting one there.

    "Reveal it" / "reveal that card" is a real reveal (CR 701.23e: an effect
    that does not print "reveal" does not reveal, and one that does shows the
    find to all players, CR 701.20a), recorded by `Game.search_and_put` and
    carried into the hand. The printed "you may" is asked as CR 701.23g;
    either way, CR 701.23b makes "find nothing" a legal answer for a search
    naming a stated quality, so an empty or exhausted library just does
    nothing. The first match in library order is taken unless a scenario rigs
    it - and the library is genuinely shuffled afterwards (CR 701.24a), so the
    rig only survives until the search happens.
    """
    return _parse_search_clause(text, for_spell=False)


def _search_up_to_and_exile_effect(match: re.Match[str]) -> AbilityEffect | None:
    """`_SEARCH_UP_TO_AND_EXILE_RE`'s search, then exile (CR 701.23a, CR
    701.24a's shuffle by `Game.search_library` itself)."""
    quality = match.group("quality")
    count = parse_count(match.group("n"))
    if count is None or not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        found = game.search_library(
            player,
            matches,
            count=count,
            optional=True,
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
        for card in found:
            game.exile_permanent(card)

    return effect


#: "You may search your library for up to that many land cards, put them
#: onto the battlefield tapped, then shuffle." - Hexhaven Invigorator's own
#: "Whenever this creature is dealt damage" trigger. "That many" here is
#: CR 607.1's anaphora onto the very event that triggered this ability - the
#: damage just dealt to it - read by `that_many`, the same per-trigger-event
#: count family Marauding Mako's and The Millennium Calendar's own "that
#: many" clauses already use. Never a spell's own shape
#: (this "that many" is an *event's* own count, not a count carried from an
#: earlier sentence in the same text - `_read_search_count`'s own "up to
#: that many" refusal is that different, still-unbuilt channel), so
#: `for_spell` refuses outright.
_SEARCH_THAT_MANY_BATTLEFIELD_RE = re.compile(
    r"^you may search (?:your|their) library for up to that many land cards?, "
    r"put them onto the battlefield(?P<tapped> tapped)?, then shuffle\.?$",
    re.IGNORECASE,
)


def _parse_search_that_many_battlefield_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_THAT_MANY_BATTLEFIELD_RE`'s shape, or `None`."""
    if for_spell:
        return None
    match = _SEARCH_THAT_MANY_BATTLEFIELD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    tapped = bool(match.group("tapped"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not is_ability(stack_object):
            return
        ability = stack_object
        count = _that_many_or_notice(
            game,
            clause,
            source_id=ability.source_id,
            source_name=ability.source_name,
            stack_object=ability,
        )
        if count is None:
            return
        if count <= 0:
            return
        player = game.controller_of(ability)
        if not game.may(
            player,
            f"search your library for up to {count} land card(s)",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.search_and_put(
            player,
            lambda state: Type.LAND in state.types,
            destination=Zone.BATTLEFIELD,
            count=count,
            tapped=tapped,
            source=ability.source_name,
            source_id=source_id_of(ability),
        )

    return effect


def _search_quality_is_readable(quality: str) -> bool:
    """Whether every word of a stated quality reaches a real matcher.

    Mirrors `_quality_matcher`'s own splitting - "basic "/"snow " prefixes
    (CR 205.4c, CR 205.4g), then words separated by commas or "or", each
    optionally carrying one of `_HAND_EXILE_COLOR_WORDS`' color adjectives
    (CR 105.2c) - so the two cannot drift apart on what counts as readable.
    """
    lowered = quality.strip().lower()
    if lowered.startswith("basic "):
        return _search_quality_is_readable(lowered.removeprefix("basic "))
    if lowered.startswith("snow "):
        return _search_quality_is_readable(lowered.removeprefix("snow "))
    if lowered == "historic":
        # CR 700.6 - `_quality_matcher` reads it (`_historic`); this check
        # had drifted from it and refused the word.
        return True
    words = [word.strip() for word in re.split(r",\s*|\s+or\s+", lowered) if word.strip()]
    if not words:
        return False
    for word in words:
        parts = word.split()
        if parts and parts[0] in _COLOR_COUNT_WORDS:
            if len(parts) == 2 and not _type_word_is_readable(parts[1]):
                return False
            if len(parts) > 2:
                return False
        elif len(parts) == 2 and parts[0] in _HAND_EXILE_COLOR_WORDS:
            if not _type_word_is_readable(parts[1]):
                return False
        elif (
            len(parts) == 2
            and parts[0] in subtype_vocabulary()
            and _type_word_is_readable(parts[1])
        ):
            # "`<subtype>` `<type>`" - Sphinx's Approach's own "Sphinx
            # creature card" - mirrors `_quality_word_matcher`'s identical
            # branch (CR 205.3, `subtype_vocabulary`).
            pass
        elif (
            (negated := _NON_SUBTYPE_PREFIX_RE.fullmatch(word)) is not None
            and negated.group("subtype").lower() in subtype_vocabulary()
            and _singular_card_type(negated.group("rest").strip()) is not None
        ):
            # "non-Human creature" (Invasion of Ikoria) - mirrors
            # `_named_type_matcher`'s identical negated-subtype-then-type
            # branch, itself `_parse_card_group_qualifier`'s own
            # `_NON_SUBTYPE_PREFIX_RE` reused rather than duplicated.
            pass
        elif len(parts) != 1 or not _type_word_is_readable(word):
            return False
    return True


#: CR 702.124j's second half, written out by `machines/keywords.
#: _partner_with_ability`: "target player may search their library for a
#: card named [name], reveal it, put it into their hand, then shuffle." The
#: printed reminder text on current printings elides "search"/"reveal" for
#: space ("target player may put [name] into their hand from their
#: library, then shuffle"), but the WotC ruling on Evie Frye (2024-07-05,
#: `mise run rules:pull` fetched the current CR the same session) spells
#: out that both still happen, which is why the *generated* text - not the
#: printed shorthand - carries them, and why this reads the fuller wording.
#: `[name]` is greedy-but-bounded by the fixed tail, so a name that itself
#: contains a comma (none in the pool do) would still stop at the first
#: ", reveal it" rather than swallowing it.
_TARGET_PLAYER_MAY_SEARCH_NAMED_CARD_RE = re.compile(
    r"^target player may search (?:their|your|his or her) library for a card named "
    r"(?P<name>.+?), reveal it, put it into (?:their|your|his or her) hand, then shuffle$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_target_player_may_search_named_card_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_TARGET_PLAYER_MAY_SEARCH_NAMED_CARD_RE`'s shape, or `None`.

    Two layers of "may", matching `_parse_search_reveal_shuffle_top_clause`'s
    own "you may search ..." convention: the outer `game.may` is CR 608.2d's
    plain optional instruction - declining it skips the search (and its
    shuffle) entirely, exactly as declining any other "you may" does. Once
    taken, the search itself is still declinable per-card (CR 701.23b treats
    a name the same as a stated type or color: "a player ... isn't required
    to find ... even if [it is] present") - `Game.search_and_put` already
    sets `optional=True` on its own inner `Game.search_library` call, so the
    target player can search, see the named card sitting right there, and
    still choose not to take it. Either way `Game.search_and_put` shuffles
    unconditionally once it runs, which is what makes the named card's
    genuine absence from the library ("search fails") indistinguishable from
    a present-but-declined find - both still shuffle, only the inner "may" a
    scenario scripts differs.
    """
    match = _TARGET_PLAYER_MAY_SEARCH_NAMED_CARD_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    name = match.group("name").strip()
    if not name:
        return None

    def matches(state: CardState) -> bool:
        return state.name == name

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, Player):
                continue
            if not game.may(
                target,
                f"search your library for a card named {name}",
                source=source,
                source_id=source_id,
            ):
                continue
            game.search_and_put(
                target,
                matches,
                destination=Zone.HAND,
                reveal=True,
                source=source,
                source_id=source_id,
            )

    return effect


#: "[You may ]search your library for a card named [name], reveal it, put it
#: into your hand, then shuffle." - Asmoranomardicadaistinaculdacar's enters
#: trigger and Tempest Hawk's combat-damage trigger,
#: whose name is its own (CR 201.5: after self-name normalisation it reads
#: "a card named this creature", the object's own name). The controller's
#: twin of `_TARGET_PLAYER_MAY_SEARCH_NAMED_CARD_RE`; CR 701.23b lets the
#: searcher fail to find even a present card, which `Game.search_and_put`'s
#: own optional search already honours. "named A or B" (Bogbrew Witch) accepts
#: either name, and the find may go onto the battlefield, tapped or not,
#: instead of into the hand (CR 701.23e: revealed only when the text says so).
_YOU_SEARCH_NAMED_CARD_RE = re.compile(
    r"^(?P<may>you may )?search your library for a card named (?P<name>.+?), "
    r"(?:(?P<reveal>reveal it, put it into your hand)|"
    r"put it onto the battlefield(?P<tapped> tapped)?), then shuffle$",
    re.IGNORECASE,
)
_SELF_NAME_RE = re.compile(
    r"^this (?:creature|permanent|artifact|enchantment|land|planeswalker|spell|card)$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_you_search_named_card_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_YOU_SEARCH_NAMED_CARD_RE`'s shape, or `None`."""
    match = _YOU_SEARCH_NAMED_CARD_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    printed = match.group("name").strip()
    if not printed:
        return None
    optional = match.group("may") is not None
    reveal = match.group("reveal") is not None
    tapped = match.group("tapped") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        names = (
            [source.split(" // ")[0]]
            if _SELF_NAME_RE.fullmatch(printed)
            else [alternative.strip() for alternative in printed.split(" or ")]
        )
        controller = game.controller_of(stack_object)
        prompt = f"search your library for a card named {' or '.join(names)}"
        if optional and not game.may(controller, prompt, source=source, source_id=source_id):
            return
        game.search_and_put(
            controller,
            lambda state: state.name in names,
            destination=Zone.HAND if reveal else Zone.BATTLEFIELD,
            reveal=reveal,
            tapped=tapped,
            source=source,
            source_id=source_id,
        )

    return effect


def _search_and_exile_matching_name(
    game: "Game",
    zones_owner: Player,
    name: str,
    *,
    chooser: Player,
    cap: int | None,
    source: str,
    source_id: str | None,
) -> tuple[list[CardState], int]:
    """Search `zones_owner`'s graveyard, hand, and library, in that printed
    order, for cards named `name`, exile every one found (capped at `cap`
    total, or every match when `cap` is `None` - Surgical Extraction's own
    "any number"), and shuffle only the library (CR 701.24b), once,
    regardless of whether the library search itself found anything
    (CR 701.24e).

    `chooser` is who decides *which* matches to take when there are more
    than `cap` of them - CR 701.23g's "you" search, not `zones_owner`, who is
    only the zones' owner and not necessarily the one doing the searching
    (The Stone Brain searches an *opponent's* zones; Surgical Extraction may
    search the caster's own, if the targeted card sat in their own
    graveyard). The choice is a real `DecisionKind.CHOOSE_CARDS` question
    over every zone's matches at once, offered before anything is removed
    from any zone - taking the cap's worth greedily out of whichever zone
    happened to search first would silently prefer that zone's matches over
    an otherwise identical one two zones later, which is not what "up to
    four" printed with no zone preference means.

    When the total is at or under `cap` (or `cap` is `None`), nothing is
    asked at all: CR 701.23d's "must find that many (or as many as
    possible)" leaves no real choice once every match is going to be taken
    anyway, the same no-question-when-there-is-no-real-choice shape
    `Player.discard_to_maximum_hand_size` already holds for a hand already
    within its maximum.

    Returns `(exiled, exiled_from_hand)` - the second is The Stone Brain's own
    "for each card exiled from their hand this way" count; Surgical
    Extraction's caller has no use for it and ignores it.
    """
    zones_in_order = (Zone.GRAVEYARD, Zone.HAND, Zone.LIBRARY)
    candidates = {
        zone: [state for state in zones_owner.cards_in(zone) if state.name == name]
        for zone in zones_in_order
    }
    total = sum(len(states) for states in candidates.values())
    if cap is not None and total > cap:
        offered = [state for zone in zones_in_order for state in candidates[zone]]
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=chooser.username,
                prompt=f"choose {cap} card(s) named {name!r} to exile",
                source=source,
                amount=cap,
                cards=tuple(state.id for state in offered),
                source_id=source_id,
            )
        )
        assert isinstance(chosen_ids, tuple)
        chosen = set(chosen_ids)
        candidates = {
            zone: [state for state in states if state.id in chosen]
            for zone, states in candidates.items()
        }

    exiled: list[CardState] = []
    exiled_from_hand = 0
    for zone in zones_in_order:
        wanted_ids = {state.id for state in candidates[zone]}
        found = game.search_library(
            zones_owner,
            lambda state, wanted_ids=wanted_ids: state.id in wanted_ids,
            count=max(len(wanted_ids), 0) or 1,
            optional=False,
            zone=zone,
            source=source,
            source_id=source_id,
        )
        for state in found:
            game.exile_permanent(state)
            exiled.append(state)
            if zone is Zone.HAND:
                exiled_from_hand += 1
    return exiled, exiled_from_hand


# --------------------------------------------------------------------------
# Bringing a card in from outside the game (CR 400.11b, CR 108.3b)
# --------------------------------------------------------------------------

#: Karn, the Great Creator's `−2`, read whole: "You may reveal an artifact card
#: you own from outside the game or choose a face-up artifact card you own in
#: exile. Put that card into your hand."
#:
#: One paragraph is one ability, so the two sentences are matched together and
#: never half-run: the "put that card into your hand" is the whole point of the
#: choice above it, and an engine that could read one sentence and not the other
#: would have nothing sensible to do with either.
#:
#: The card type is a group, not a hard-coded "artifact", because the shape is
#: general - the rules that make it work are CR 400.11c's narrow exception for
#: "spells and abilities that allow those cards to be brought into the game",
#: CR 108.3b's ownership gate, and CR 406.3's face-up requirement - and none of
#: those is about artifacts.
_OUTSIDE_THE_GAME_FETCH_RE = re.compile(
    r"^you may reveal an? (?P<quality>[a-z]+) card you own from outside the game "
    r"or choose a face-up (?P<exile_quality>[a-z]+) card you own in exile\.?\s*"
    r"put that card into your hand\.?$",
    re.IGNORECASE,
)

#: A sentence that reaches outside the game in some other shape. Matched only to
#: fail closed with a notice, per the paragraph-atomic rule: an ability that
#: mentions outside the game and cannot be read whole records that it went
#: unread rather than resolving as silence.
_LOOKS_LIKE_OUTSIDE_THE_GAME_RE = re.compile(r"\bfrom outside the game\b", re.IGNORECASE)


#: North Wind Avatar's "you may put a card you own from outside the game into
#: your hand" and Mastermind's Acquisition's mode "Put a card you own from
#: outside the game into your hand." - the unrevealed, any-card wish
#: (CR 108.3b, CR 400.11b): no quality and no reveal, so the card arrives
#: hidden.
_PUT_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE = re.compile(
    r"^(?P<may>you may )?put a card you own from outside the game into your hand\.?$",
    re.IGNORECASE,
)


def _put_from_outside_the_game_into_hand(
    game: "Game", controller: Player, optional: bool, source: str, source_id: object
) -> None:
    """Perform `_PUT_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE`: the controller
    chooses one card they own outside the game (CR 108.3b), if they have any
    and - for "you may" - want to, and it goes to their hand (CR 400.11b)."""
    candidates = controller.owned_outside_the_game()
    if not candidates:
        return
    if optional and not game.may(
        controller,
        "put a card you own from outside the game into your hand",
        source=source,
        source_id=source_id,
    ):
        return
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller.username,
            prompt="choose a card you own from outside the game",
            source=source,
            source_id=source_id,
            amount=1,
            cards=tuple(state.id for state in candidates),
            card_labels=tuple(state.name for state in candidates),
        )
    )
    assert isinstance(chosen_ids, tuple)
    by_id = {state.id: state for state in candidates}
    for card_id in chosen_ids:
        controller.bring_into_the_game(by_id[card_id], Zone.HAND)


@SPELL_TEXT.rung("s21")
def _parse_put_from_outside_the_game_into_hand_spell(effect_text: str) -> Effect | None:
    """The spell (or spell mode) form of `_PUT_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE`."""
    match = _PUT_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE.fullmatch(" ".join(effect_text.split()))
    if match is None:
        return None
    optional = match.group("may") is not None

    def effect(game: "Game", spell: CardState) -> None:
        _put_from_outside_the_game_into_hand(
            game, game.controller_of(spell), optional, spell.name, source_id_of(spell)
        )

    return effect


@ABILITY_TEXT.rung("s16")
def _parse_outside_the_game_fetch(effect_text: str) -> AbilityEffect | None:
    """Karn's `−2` shape, or a notice for a near miss, or None.

    Every rule this performs was looked up in the session that wrote it:

    - **CR 400.11a** - "Cards in a player's sideboard are outside the game."
    - **CR 400.11c** - cards outside the game "can't be affected by spells or
      abilities, except ... spells and abilities that allow those cards to be
      brought into the game", which is what this ability is.
    - **CR 108.3b** - "Some spells and abilities allow a player to take cards
      **they own** from outside the game and bring them into the game."
    - **CR 400.11b** - a card brought in "remain[s] in the game until the game
      ends".
    - **CR 701.20a** - "To reveal a card, show that card to all players for a
      brief time", and CR 701.20b: it does not move the card. The reveal is the
      price of taking a card out of a group nobody may look at; the exile half
      needs none, because CR 406.3 already makes a face-up exiled card one that
      "may be examined by any player at any time".
    - **CR 406.3** - "Cards 'exiled face down' can't be examined by any player
      except when instructions allow it", so a face-down exiled card is not a
      "face-up artifact card" and cannot be chosen. CR 406.3a: it "has no
      characteristics" to be an artifact with in the first place.
    - **CR 608.2d** - the "you may" and the choice are made as the ability
      resolves, by its controller, and an option that is illegal or impossible
      cannot be chosen.
    """
    put = _PUT_FROM_OUTSIDE_THE_GAME_INTO_HAND_RE.fullmatch(" ".join(effect_text.split()))
    if put is not None:
        optional = put.group("may") is not None

        def put_into_hand(game: "Game", ability: AbilityOnStack) -> None:
            _put_from_outside_the_game_into_hand(
                game,
                game.player(ability.controller),
                optional,
                ability.source_name,
                source_id_of(ability),
            )

        return put_into_hand
    reveal = _read_reveal_from_outside_the_game(effect_text)
    if reveal is not None and reveal[2] is None:
        # Vivien, Arkbow Ranger's −5: the Wish sentence on an ability, with no
        # spell to exile.
        quality, matches, _ = reveal

        def reveal_into_hand(game: "Game", ability: AbilityOnStack) -> None:
            _reveal_a_quality_card_from_outside_the_game(
                game,
                game.player(ability.controller),
                quality,
                matches,
                ability.source_name,
                source_id_of(ability),
            )

        return reveal_into_hand
    match = _OUTSIDE_THE_GAME_FETCH_RE.match(" ".join(effect_text.split()))
    if match is None:
        if _LOOKS_LIKE_OUTSIDE_THE_GAME_RE.search(effect_text):

            def outside_the_game_notice_only(game: "Game", ability: AbilityOnStack) -> None:
                game.unmodeled_trigger_effect_notices.append(
                    UnmodeledTriggerEffectNotice(
                        source_id=ability.source_id,
                        source_name=ability.source_name,
                        text=effect_text,
                    )
                )

            return outside_the_game_notice_only
        return None

    quality = _card_type_from_quality(match.group("quality"))
    exile_quality = _card_type_from_quality(match.group("exile_quality"))
    if quality is None or exile_quality is None:
        return None

    def fetch(game: "Game", ability: AbilityOnStack) -> None:
        _bring_in_from_outside_the_game_or_exile(game, ability, quality, exile_quality)

    return fetch


def _card_type_from_quality(word: str) -> Type | None:
    """ "artifact" -> `Type.ARTIFACT`; anything that is not a card type -> None."""
    try:
        return Type(word.strip().lower())
    except ValueError:
        return None


#: "Search your library, graveyard, and/or outside the game for an `<quality>`
#: card you own, reveal it, and put it into your hand. If you search your
#: library this way, shuffle." - Invasion of Arcavios's own Siege ETB. A
#: Scryfall search for this exact wording turns up no other printing, so the
#: quality is still read generally (`_quality_matcher`, parameterised, never
#: this card's name) rather than hardcoded to "instant or sorcery".
#:
#: One CR 701.23a search naming three zones at once, not three independent
#: ones (`Game.search_library`'s own "graveyard, hand, and library"
#: precedent runs one search *per* zone only because that shape moves every
#: matching card out of every zone named - see its own docstring): a single
#: choice over every legal candidate wherever it sits, the same reading
#: `_parse_quest_counter_threshold_sacrifice_search_clause` already gives
#: "search your hand and/or library for a `<quality>` card". This printing's
#: own rulings (2023-04-14) confirm it: "You don't have to declare up front
#: where you're going to search. You may search your library, ... then
#: finally grab a ... card from your sideboard" - so the library is always
#: looked through and always shuffled (CR 701.24a), found there or not.
#: Nothing here reads "you may": CR 701.23d's plain "search ... for a card"
#: is mandatory (find one if you can), the same as Mystical Tutor's own
#: unqualified "Search your library for an instant card".
_SEARCH_LIBRARY_GRAVEYARD_OUTSIDE_THE_GAME_RE = re.compile(
    r"^search your library, graveyard, and/or outside the game for an? "
    r"(?P<quality>.+?) card you own, reveal it, and put it into your hand\.\s*"
    r"if you search your library this way, shuffle\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s1")
def _parse_search_library_graveyard_outside_the_game_clause(text: str) -> AbilityEffect | None:
    """`_SEARCH_LIBRARY_GRAVEYARD_OUTSIDE_THE_GAME_RE`'s shape, or `None`."""
    match = _SEARCH_LIBRARY_GRAVEYARD_OUTSIDE_THE_GAME_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    quality = match.group("quality")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability)

        def owned(state: CardState) -> bool:
            return state.owner == controller.username and matches(state)

        candidates = (
            [state for state in controller.library if owned(state)]
            + [state for state in controller.graveyard if owned(state)]
            + controller.owned_outside_the_game(matches)
        )
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"search your library, graveyard, and/or outside the game for "
                        f"{with_indefinite_article(f'{quality} card')} you own"
                    ),
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    exact=False,
                    cards=tuple(state.id for state in candidates),
                    card_labels=tuple(state.name for state in candidates),
                    default_cards=tuple(state.id for state in candidates[:1]),
                )
            )
            assert isinstance(chosen_ids, tuple)
            if chosen_ids:
                by_id = {state.id: state for state in candidates}
                found = by_id[chosen_ids[0]]
                zone = found.zone
                game.reveal(found, source=ability.source_name)
                if zone in (Zone.LIBRARY, Zone.GRAVEYARD):
                    controller.move(found, Zone.HAND)
                else:
                    controller.bring_into_the_game(found, Zone.HAND)
        game.shuffle_library(controller)

    return effect


def _outside_the_game_card_phrase(quality: str) -> str:
    """ "a creature card", or "a card named Legion Angel" for a name quality."""
    if quality.startswith("named "):
        return f"a card {quality}"
    return with_indefinite_article(f"{quality} card")


#: Wish: "You may play a card you own from outside the game this turn." A
#: spell-side twin of `_parse_outside_the_game_fetch`, printed as a plain
#: CR 601.3 grant rather than Karn's "reveal ... put into your hand": Wish
#: never says the card goes to hand, and its printed "this turn" is a real
#: expiring window - CR 601.3's "a rule or effect allows that player to
#: [play] it" is exactly `machines.casting.PlayPermission`'s own shape
#: (`until_end_of_turn=True`, the default), the same "exile it, then permit
#: it until end of turn" idiom Ugin, Eye of the Storms' `−11` and Ragavan,
#: Nimble Pilferer's trigger already use for a card that was not previously
#: in the game at all. Bringing it straight into the hand instead (Karn's
#: own shape) would be wrong here specifically: CR 400.11b leaves a
#: brought-in card "in the game" indefinitely once it is an ordinary object
#: of its new zone, and a card sitting in hand needs no permission at all
#: (`why_cannot_cast_from`'s own `zone is Zone.HAND` fast path) - so the
#: printed "this turn" would silently become "forever" the moment the turn
#: ended. Exile is the zone this grant is anchored to instead: CR 406.3 makes
#: a face-up exiled card visible to everyone the way a revealed card is, and
#: once `until_end_of_turn` lapses (CR 514.2, `Game.cleanup_step`) the card is
#: simply an unclaimed face-up exiled card forever after (CR 400.11b's own
#: "remain[s] in the game" default) - a legitimate resting state Wish's own
#: text names no other fate for, unlike cascade's own "put ... on the
#: bottom" instruction (CR 702.85a).
_OUTSIDE_THE_GAME_PLAY_RE = re.compile(
    r"^you may play a card you own from outside the game this turn\.?$", re.IGNORECASE
)


@SPELL_TEXT.rung("s21")
def _parse_outside_the_game_play_clause(effect_text: str) -> Effect | None:
    """`_OUTSIDE_THE_GAME_PLAY_RE`'s shape, or `None` if this is not it."""
    if _OUTSIDE_THE_GAME_PLAY_RE.fullmatch(effect_text.strip()) is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        candidates = controller.owned_outside_the_game()
        if not candidates:
            return
        # CR 608.2d's plain "you may": the whole instruction is optional.
        if not game.may(
            controller,
            "play a card you own from outside the game this turn",
            source=spell.name,
            source_id=source_id_of(spell),
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a card you own from outside the game to play this turn",
                source=spell.name,
                source_id=source_id_of(spell),
                amount=1,
                cards=tuple(state.id for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if not chosen_ids:
            return
        by_id = {state.id: state for state in candidates}
        chosen = by_id[chosen_ids[0]]
        # CR 701.20a/b: reveal makes the pick public without moving it, the
        # same order `_bring_in_from_outside_the_game_or_exile` already uses.
        game.reveal(chosen, source=spell.name)
        # `bring_into_the_game` keeps CR 108.3b's ownership gate and routes the
        # move itself through `Game.exile_cards`: CR 400.1's exile zone is the
        # game's one shared pile, and the old `Player.move` half of this put
        # the card into a second, per-player one as well.
        controller.bring_into_the_game(chosen, Zone.EXILE)
        game.grant_play_permission(
            chosen,
            controller.username,
            action=PlayAction.PLAY,
            pays_mana_cost=True,
            source_name=spell.name,
            zone=Zone.EXILE,
            rule="CR 601.3",
        )

    return effect


#: "Search your library and/or outside the game for exactly `<n>` `<quality>`
#: cards you own with different names, then reveal those cards. An opponent
#: chooses `<m>` of them. Put the chosen cards into your hand and shuffle the
#: rest into your library." - Turtles Forever's whole effect, read as one
#: paragraph the same way `_REVEAL_TWO_DIFFERENT_NAMES_OUTSIDE_THEN_OPPONENT_
#: CHOOSES_RE` already is: "those cards"/"them"/"the rest" are all CR 400.7
#: anaphora back to the one search this sentence performs, which no per-clause
#: parser could ever read back together.
_SEARCH_LIBRARY_AND_OUTSIDE_DISTINCT_NAMES_OPPONENT_CHOOSES_RE = re.compile(
    r"^search your library and/or outside the game for exactly (?P<n>" + COUNT + r") "
    r"(?P<quality>.+?) cards you own with different names, then reveal "
    r"(?:those|these) cards\.\s*an opponent chooses (?P<m>" + COUNT + r") of them\.\s*"
    r"put the chosen cards into your hand and shuffle the rest into your library\.?$",
    re.IGNORECASE,
)


def _parse_search_library_and_outside_distinct_names_opponent_chooses_clause(
    text: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_SEARCH_LIBRARY_AND_OUTSIDE_DISTINCT_NAMES_OPPONENT_CHOOSES_RE`'s
    shape - Turtles Forever.

    CR 400.11a makes the sideboard "outside the game", CR 400.11c's own
    exception ("spells and abilities that allow those cards to be brought
    into the game") is what lets this ability reach it at all, and CR 108.3b
    limits that reach to cards this player **owns**. "And/or" (CR 608.2c's
    plain English) pools both groups into one search, exactly the way
    `_bring_in_from_outside_the_game_or_exile` already pools "outside the
    game" and "in exile" into one candidate list for Karn, the Great
    Creator's own `-2` - the same convention, applied to a library instead of
    exile as the second pool.

    "With different names" is read the identical way `_parse_search_
    distinct_names_clause` already reads it for a library-only search: one
    representative CardState per name, so the controller's own choice of
    `n` can never repeat a name (CR 701.23a still finds one card at a time in
    spirit, even though this reader offers the whole deduplicated pool at
    once rather than looping one pick per name the way that library-only
    reader does - both land on the same "at most one of each name" answer).

    A pool smaller than `n` distinct names never asks the question at all
    (CR 608.2d: nothing here is a partial "as many as possible" instruction
    the way a bare `_SEARCH_AND_PUT_RE` count is; "exactly `<n>`" is read the
    same strict way `_REVEAL_TWO_DIFFERENT_NAMES_OUTSIDE_THEN_OPPONENT_
    CHOOSES_RE`'s own "exactly two" already is).

    The reveal (CR 701.20a) happens once, over every card this search found,
    before the opponent's own CR 608.2d choice of `m` of them; the unchosen
    ones are "the rest" - CR 701.24a's shuffle folds a library-origin one
    back in for free and a sideboard-origin one is brought in first
    (`Player.bring_into_the_game`, CR 400.11b) so it has a library to be
    shuffled into at all.
    """
    if not for_spell:
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _SEARCH_LIBRARY_AND_OUTSIDE_DISTINCT_NAMES_OPPONENT_CHOOSES_RE.fullmatch(whole)
    if match is None:
        return None
    n = parse_count(match.group("n"))
    m = parse_count(match.group("m"))
    if n is None or m is None or n < 1 or m < 1:
        return None
    quality = match.group("quality").strip()
    if not _card_description_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source_name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        source_id = source_id_of(stack_object)
        pool = [state for state in controller.library if matches_quality(state)]
        pool += controller.owned_outside_the_game(matches_quality)
        by_name: dict[str, CardState] = {}
        for state in pool:
            by_name.setdefault(state.name or "", state)
        candidates = list(by_name.values())
        if len(candidates) < n:
            return
        if not game.may(
            controller,
            f"search your library and/or outside the game for exactly {n} "
            f"{quality} cards with different names",
            source=source_name,
            source_id=source_id,
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose exactly {n} {quality} cards with different names",
                source=source_name,
                source_id=source_id,
                amount=n,
                exact=True,
                cards=tuple(state.id for state in candidates),
                card_labels=tuple(state.name for state in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if len(chosen_ids) < n:
            return
        by_id = {state.id: state for state in candidates}
        found = [by_id[card_id] for card_id in chosen_ids]
        for state in found:
            game.reveal(state, source=source_name)
        opponents = _opponents(game, controller.username)
        if not opponents:
            return
        # CR 102.2: a two-player game has exactly one opponent to ask.
        chooser = opponents[0]
        picked_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=chooser.username,
                prompt=f"choose {m} of the revealed cards",
                source=source_name,
                source_id=source_id,
                amount=min(m, len(found)),
                exact=True,
                cards=tuple(state.id for state in found),
                card_labels=tuple(state.name for state in found),
            )
        )
        assert isinstance(picked_ids, tuple)
        picked_id_set = set(picked_ids)
        picked = [state for state in found if state.id in picked_id_set]
        rest = [state for state in found if state.id not in picked_id_set]
        for state in picked:
            if state.zone.is_outside_the_game:
                controller.bring_into_the_game(state, Zone.HAND)
            else:
                controller.move(state, Zone.HAND)
        for state in rest:
            if state.zone.is_outside_the_game:
                controller.bring_into_the_game(state, Zone.LIBRARY)
        game.shuffle_library(controller)

    return effect


from ..player_action_prohibitions import library_search_blocked  # noqa: E402
from ._common import (  # noqa: E402
    _COLOR_COUNT_WORDS,
    _HAND_EXILE_COLOR_WORDS,
    _NON_SUBTYPE_PREFIX_RE,
    _SEARCH_AND_PUT_RE,
    _SEARCH_DESCRIPTION_JOIN_RE,
    UnmodeledTriggerEffectNotice,
    _card_description_is_readable,
    _opponents,
    _quality_matcher,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _bounded_quality_matcher,
    _that_many_or_notice,
    count_expression,
    that_many,
)
from .library import (  # noqa: E402
    _read_reveal_from_outside_the_game,
    _reveal_a_quality_card_from_outside_the_game,
)
from .mana import _and_has_exact_mana_cost, _exact_mana_cost_matcher  # noqa: E402
from .removal import _cost_sacrificed_mana_value, _sacrificed_mana_value_search  # noqa: E402
from .returns import _bring_in_from_outside_the_game_or_exile  # noqa: E402
from .text import (  # noqa: E402
    _named_type_matcher,
    _singular_card_type,
    _split_destination_zone,
    _strip_non_effect_preamble,
    _type_word_is_readable,
)

import re
from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article

from ...models.card import Type
from ...models.card_state import (
    CardState,
    Counter,
)
from ...models.player import Player
from ...models.zone import Zone
from ...numbers import (
    AMOUNT,
    COUNT,
    count_pattern,
    halve,
    parse_count,
    parse_half,
    where_x_pattern,
)
from .. import (
    block_reassignment,
    map_tokens,
    mass_pump_conditions,
    token_riders,
)
from .. import combat as combat_rules
from ..abilities import (
    TriggerEvent,
)
from ..casting import (
    PlayAction,
)
from ..casting_restrictions import parse_casting_rule_clause
from ..chosen_type import (
    parse_choose_creature_type_then_emblem_clause,
    parse_choose_type_hexproof_indestructible_clause,
    parse_gathering_stone_look_clause,
)
from ..connive import parse_connive_clause
from ..counter_effects import parse_resolution_text as _parse_counter_resolution_text
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    DelayedTrigger,
    NextSpellCannotBeCountered,
)
from ..layers import (
    ContinuousEffect,
    Duration,
    Layer,
    SetTypesAndSubtypes,
    grant_ability,
    only_this_incarnation,
    split_and_validate_keywords,
)
from ..targeting import (
    permanent_description,
)
from ..triggers import (
    AbilityOnStack,
)
from ..turn_scoped_riders import (
    parse_event_subject_controller_poison_clause,
)
from ..zone_resets import (
    merge_each_player_may_shuffle_hand_graveyard_then_draw_clauses,
    parse_each_player_may_shuffle_hand_graveyard_then_draw_clause,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._common import (
    _SPELL_QUALIFIER_WORD,
    _UNQUOTED_PREFIX,
    AbilityEffect,
    ClauseEffect,
    Effect,
    TargetedClause,
)

# --------------------------------------------------------------------------
# Prevention effects (CR 615)
# --------------------------------------------------------------------------


def end_the_turn_effect(game: "Game", spell: CardState) -> None:
    """Time Stop: "End the turn." - CR 724.1's procedure, in `Game`.

    Deliberately the last thing this clause does and nothing more: CR 724.1b
    exiles every object on the stack "including the object that's resolving",
    so the spell exiles itself here rather than reaching a graveyard.

    A spliced clause (CR 702.47c adds the spliced card's text to this spell)
    still runs, because `effect_for`'s fallback executes each clause in the
    order written (CR 608.2c) and this one is Time Stop's only sentence -
    anything spliced on sits beside it and is reached on its own.

    Reached from an activated ability's own printed text the identical way,
    with no row or extension of its own needed: `_PLAIN_END_THE_TURN_RE`
    lives in `_parse_targeted_clause`, which `parse_mixed_effect`/
    `activated_effect_for` already try for every activated ability with no
    `ACTIVATED_EFFECTS` row, and this function never reads its second
    argument at all - it works identically for an `AbilityOnStack` as for a
    `CardState`. Sundial of the Infinite's "{1}, {T}: End the turn." is the
    printing that exercises it (its own "Activate only during your turn."
    is a separate CR 602.5 timing restriction, already stripped off the
    effect text before this is ever reached - see `ActivatedAbility.
    instructions`/`activated_effect_for`).
    """
    game.end_the_turn()


def _subtypes_in(phrase: str) -> frozenset[str]:
    """The creature types named in "Werewolves and Wolves", singularised.

    Printed text names them in the plural; `Characteristics.subtypes` holds
    them the way the type line does, so "Werewolves" has to come back as
    "Werewolf". Only the two endings the pool actually uses are handled, and
    an unrecognised word is kept as-is rather than mangled - a subtype that
    matches nothing simply never excludes anything, which fails closed.
    """
    words = re.split(r",|\band\b", phrase)
    found: set[str] = set()
    for word in words:
        cleaned = word.strip().rstrip(".")
        if not cleaned:
            continue
        if cleaned.endswith("ves"):
            cleaned = cleaned[:-3] + "f"
        elif cleaned.endswith("s"):
            cleaned = cleaned[:-1]
        found.add(cleaned)
    return frozenset(found)


def _unreadable_search_description(text: str) -> str | None:
    """The first search clause in `text` whose description does not read
    (`_search_descriptions`), or `None`."""
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        match = _SEARCH_AND_PUT_RE.fullmatch(clause.strip())
        if match is not None and _search_descriptions(match) is None:
            return clause.strip()
    return None


def _unreadable_search_count(text: str) -> str | None:
    """The first search clause in `text` whose stated *quality* reads fine
    but whose *count* does not (`_read_search_count`) - a count word this
    reader does not take. Distinct from `_unreadable_search_description`'s
    own check right above, which is the quality half of the same clause.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        match = _SEARCH_AND_PUT_RE.fullmatch(clause.strip())
        if match is None:
            continue
        if _search_descriptions(match) is None:
            continue  # `_unreadable_search_description`'s own case
        if _read_search_count(match) is None:
            return clause.strip()
    return None


#: Wanderwine Farewell's own convoke spell body: "Return one or two target
#: nonland permanents to their owners' hands. Then if you control a
#: Merfolk, create a 1/1 white and blue Merfolk creature token for each
#: permanent returned to its owner's hand this way." The second sentence's
#: "returned ... this way" is CR 608.2c's own anaphora for however many the
#: first sentence's `game.resolve_targets` actually found still legal
#: (CR 608.2b) - not necessarily the number targeted - so this reads both
#: sentences as one instruction rather than through the generic per-clause
#: `_RETURN_TARGET_RE` dispatch, which has nowhere to hand that count on to
#: a second, independently dispatched clause.
_WANDERWINE_FAREWELL_RE = re.compile(
    r"^return (?P<phrase>one or two target nonland permanents) to their owners'? hands\.\s*"
    r"then if you control a merfolk, create a 1/1 white and blue merfolk creature token "
    r"for each permanent returned to its owner'?s hand this way\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_wanderwine_farewell_clause(text: str, *, for_spell: bool) -> Effect | None:
    """`_WANDERWINE_FAREWELL_RE`'s shape, or `None`."""
    if not for_spell:
        return None
    whole = _strip_non_effect_preamble(text).strip()
    match = _WANDERWINE_FAREWELL_RE.fullmatch(whole)
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        returned: list[CardState] = []
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in game.resolve_targets(spell):
                if isinstance(target, CardState):
                    game.return_to_hand(target)
                    returned.append(target)
        if not returned:
            return
        controls_a_merfolk = any(
            Type.CREATURE in game.characteristics_of(state).types
            and "merfolk" in {s.lower() for s in game.characteristics_of(state).subtypes}
            for state in game.permanents_controlled_by(controller.username)
        )
        if not controls_a_merfolk:
            return
        token_effect = _parse_token_clause(
            f"create {len(returned)} 1/1 white and blue Merfolk creature tokens",
            for_spell=for_spell,
        )
        if token_effect is not None:
            token_effect(game, spell)

    return effect


#: "Take `<N>` extra turn(s) after this one." (CR 500.7) - Teferi, Master of
#: Time's "Take two extra turns after this one.", Teferi, Timebender's and
#: Savor the Moment's "Take an extra turn after this one." CR 500.7: "If a
#: player is given multiple extra turns, the extra turns are added one at a
#: time" - N grants, each pushed onto `TurnMachine.extra_turns`.
_TAKE_EXTRA_TURNS_RE = re.compile(
    rf"take {count_pattern('n', article=True)} extra turns? after this one",
    re.IGNORECASE,
)

#: "Skip the untap step of that turn." (CR 614.10) - the rider that follows
#: "Take an extra turn after this one." (Savor the Moment). "That turn" is
#: the extra turn the previous clause just added directly after this one
#: (CR 500.7), which is the next turn this player takes, so its untap step
#: is their next untap step - `Game.players_skipping_next_untap`'s count.
_SKIP_UNTAP_STEP_OF_THAT_TURN_RE = re.compile(r"skip the untap step of that turn", re.IGNORECASE)

#: "Harness this permanent." (CR 701.64a) - The Mind Stone's own "{5}{W},
#: {T}: Harness The Mind Stone." (self-normalized before this ever runs, the
#: same "this permanent" `_COUNTER_ON_SELF_RE` already reads a card's own
#: printed name as). `<noun>` is any word, matching every other self-
#: reference shape in this module.
_HARNESS_SELF_RE = re.compile(r"^harness this \w+\.?$", re.IGNORECASE)

#: "During that turn, power-up abilities can't be activated." (CR 702.193a) -
#: Kang the Conqueror's own rider on "Take an extra turn after this one.":
#: "that turn" is the extra turn the previous clause just inserted directly
#: after this one (CR 500.7), the identical anaphora `_SKIP_UNTAP_STEP_OF_
#: THAT_TURN_RE` already reads for Savor the Moment's own rider on the same
#: clause.
_DURING_THAT_TURN_POWER_UP_RESTRICTED_RE = re.compile(
    r"^during that turn, power-up abilities can'?t be activated\.?$", re.IGNORECASE
)

#: The optional "for each `<expr>`" tail - Mastery of the Unseen's "gain 1
#: life for each creature you control" - is read by `_for_each_multiplier`
#: below, once, at the moment CR 608.2h fixes the count.
_GAIN_LIFE_RE = re.compile(
    rf"you gains? (?:(?P<times>{COUNT}) times )?(?P<n>{COUNT}) life"
    rf"(?: for each (?P<each>.+))?",
    re.IGNORECASE,
)
_LOSE_LIFE_RE = re.compile(
    rf"you loses? (?P<n>{COUNT}) life(?: for each (?P<each>.+))?", re.IGNORECASE
)
#: "<player> loses that much life" - an amount carried by the triggering
#: event or an earlier instruction (`that_many`, CR 608.2c / 603.2c): Professor
#: Dellian Fel's emblem "Whenever you gain life, target opponent loses that
#: much life." The player is whoever the dispatcher runs the clause for.
_THAT_MUCH_LIFE_LOSS_RE = re.compile(r"^you loses? that much life\.?$", re.IGNORECASE)


#: "You gain hexproof until your next turn." (Blossoming Calm), and the
#: player half of "You and permanents you control gain hexproof from blue and
#: from black until end of turn." (Veil of Summer, once its compound subject is
#: split): a player-subject grant of CR 702.11c's hexproof, CR 702.11d's
#: "hexproof from [quality]" (CR 702.11f's "from A and from B" list read as
#: one ability per quality), or CR 702.18a's shroud "or player", for CR
#: 611.2a's stated duration. "gain", never "gains": `_parse_optional_player_
#: clause` retries a subject-less clause with "you" restored, and a bare
#: "gains hexproof until end of turn" is always a permanent's grant cut off
#: from its subject (Blossoming Defense's "... and gains hexproof"), not the
#: player's.
_PLAYER_GAINS_HEXPROOF_RE = re.compile(
    r"you gain (?P<keyword>hexproof|shroud)(?: from (?P<qualities>.+?))?"
    r" until (?P<duration>end of turn|your next turn)",
    re.IGNORECASE,
)
#: "Each opponent loses N life." - Cauldron Familiar's own enters trigger,
#: the flat-number twin of `_EACH_OPPONENT_LOSES_LIFE_EQUAL_TO_RE`'s counted
#: amount. CR 119.3 adjusts a life total directly, and unlike CR 119.2's
#: damage nothing here is dealt by a source, so no prevention or protection
#: applies; CR 102.2's "each opponent" is every player in the game other than
#: the clause's own controller.
_EACH_OPPONENT_LOSES_LIFE_RE = re.compile(
    rf"each opponent loses (?P<n>{COUNT}) life", re.IGNORECASE
)


# CR 107.14: "The energy symbol is {E}. It represents one energy counter."
_ENERGY_RE = re.compile(r"(?:you )?gets? (?P<e>(?:\{e\})+)", re.IGNORECASE)
# CR 122.1f: poison counters are a kind a player gets - "you get a poison
# counter" (Phyrexian Vatmother), "target opponent gets a poison counter"
# (Venerated Rotpriest, through `_TARGET_PLAYER_OR_OPPONENT_VERB_RE`), "gets
# two poison counters". Ten of them lose the game (CR 704.5c).
_POISON_COUNTERS_RE = re.compile(rf"(?:you )?gets? (?P<n>{COUNT}) poison counters?", re.IGNORECASE)
# CR 121.1/121.2: drawing, one card at a time. The "you" is often left
# implicit - a triggered or activated ability's effect just says "Draw a
# card." The optional "for each `<expr>`" tail folds in Kaito, Bane of
# Nightmares' own "draw a card for each opponent who lost life this turn" -
# `_for_each_multiplier` reads "opponent who lost life this turn" as one of
# its own qualifiers, rather than this regex pinning that one sentence - and
# Keruga, the Macrosage's "draw a card for each other permanent you control
# with mana value 3 or greater".
#: "draw that many cards" (Jaya Ballard, Cavalier of Flame, Fable of the
#: Mirror-Breaker II) reads the count channel (`that_many`).
#: "that many cards minus one" (Dark Deal) / "plus one" adjusts it (CR 107.1b:
#: a negative result is zero).
#: "draw an additional card" / "draw two additional cards" (The Immortal Sun's
#: draw-step trigger) is the same draw: "additional" only says it comes on top
#: of CR 504.1's own draw that turn, which has already happened by the time
#: the trigger resolves (CR 504.2).
_DRAW_RE = re.compile(
    rf"(?:you )?draws? (?:an? (?:additional )?card|"
    rf"(?:(?P<that_many>that many)|(?P<n>{COUNT})) (?:additional )?cards?"
    rf"(?: (?P<op>plus|minus) (?P<adjust>{COUNT}))?)"
    rf"(?: for each (?P<each>.+))?",
    re.IGNORECASE,
)


# G3: "exile(s) N [quality] card(s) from your/their graveyard" - Relic of
# Progenitus's "Target player exiles a card from their graveyard.", Merrow
# Bonegnawer's identically-worded tap ability, and Curse of Oblivion's own
# upkeep trigger ("that player exiles two cards from their graveyard.").
# Modelled on `_DISCARD_A_CARD_RE`/`_discard_cards` directly above: the same
# COUNT-plus-optional-quality grammar, over the acting player's own
# graveyard instead of their hand. By the time a `ClauseEffect` this reader
# returns actually runs, `player` is already whichever player the sentence's
# own subject named - "target player" (`_TARGET_PLAYER_CLAUSE_RE`), "each
# player"/"each opponent" (`_EACH_PLAYER_HEAD_RE`), or "that player" (CR
# 607.1's own triggered-ability anaphora, see `_parse_that_player_clause`
# below) - every one of those subjects already delegates its own rest-of-
# sentence to `parse_clause_effect`, so this one reader closes all of them
# at once rather than needing a fresh regex per subject the way the sacrifice
# and life-total families under `_ANAPHORIC_SUBJECT_RE` had to.
#
# No quality word is exercised by any of this wave's own proof cards, but
# the slot is read the same optional way `_DISCARD_A_CARD_RE`'s is (Chandra,
# Chill of Compliance's own "exile a nonland card" shape, for instance,
# would already be readable through it if that clause ever reaches here).
_EXILE_CARDS_FROM_OWN_GRAVEYARD_RE = re.compile(
    rf"^exiles? (?P<n>{COUNT})\s+(?:(?P<quality>[a-z]+) )?cards? from (?:your|their) graveyard$",
    re.IGNORECASE,
)
# "Discard your hand." (Behold the Beyond, second person, addressed to the
# caster) and "discards their hand"/"discards his or her hand" (the same
# verb, third person - Reforge the Soul's "Each player discards their hand,
# then draws seven cards", reached through `_parse_each_player_step`'s own
# fallback to `parse_clause_effect` for a step it has no dedicated pattern
# for). CR 701 has no separate "Discard your hand" keyword action: this is
# CR 701.9a's ordinary per-card discard, applied to every card the hand
# holds at resolution - `_discard_cards`'s own `count=len(player.hand)`,
# read fresh inside the returned callable rather than at parse time, is
# exactly that.
_DISCARD_HAND_RE = re.compile(r"^discards? (?:your|their|his or her) hand\.?$", re.IGNORECASE)


# CR 701.17a: "puts that many cards from the top of their library into their
# graveyard." The optional "for each `<expr>`" tail is the same reader as
# `_DRAW_RE`'s own.
_MILL_RE = re.compile(
    rf"(?:you )?mills? (?:a card|(?:(?P<that_many>that many)|(?P<n>{COUNT})) cards?)"
    rf"(?: for each (?P<each>.+))?",
    re.IGNORECASE,
)
#: "mills half their library, rounded down" (Traumatize), "exiles the top
#: half of their library, rounded up" (Ulamog, the Defiler's cast trigger) -
#: CR 701.17a's mill and CR 701.13a's exile, each taking a count that is half
#: the acting player's own library (`numbers.parse_half`, CR 107.1a's printed
#: rounding). "Their"/"your" is the player the clause is run against - the
#: target of "Target player ...", or the controller of a bare instruction.
_HALF_OF_OWN_LIBRARY_RE = re.compile(
    r"^(?:you )?(?P<verb>mills?|exiles?) (?P<half>(?:the top )?half (?:of )?(?:their|your) "
    r"library, rounded (?:up|down))$",
    re.IGNORECASE,
)
#: "You have no maximum hand size for the rest of the game." (Sea Gate
#: Restoration) - CR 613.11's rule-modifying effect with CR 611.2a's stated
#: duration: it outlives the spell and every permanent, so it is recorded on
#: the player (`Player.no_maximum_hand_size_for_rest_of_game`), which
#: `Player.has_no_maximum_hand_size` reads.
_NO_MAXIMUM_HAND_SIZE_REST_OF_GAME_RE = re.compile(
    r"^you have no maximum hand size for the rest of the game$", re.IGNORECASE
)
#: CR 725.1 - "you become the monarch." Nothing to read but the plain
#: sentence: CR 725 puts no cost or condition inside it, so it is only ever
#: this exact shape (Grave Venerations, Palace Sentinels).
_BECOME_THE_MONARCH_RE = re.compile(r"^you become the monarch$", re.IGNORECASE)


#: "Scry N" (Preordain, most spells) and "Target player scries N" (Kozilek's
#: Command's third-person mode) - `scr(?:y|ies)` reads both conjugations.
#: "Scry X, where X is `<expr>`" (Oath of Jace) reads the same way.
#: The explicit-subject spelling "you scry N" (Torch the Tower's bargained
#: "... and you scry 1") reads as the bare one.
_SCRY_RE = re.compile(rf"(?:you )?scr(?:y|ies) (?P<n>{AMOUNT}){where_x_pattern()}", re.IGNORECASE)


#: "you may pay any amount of life" (Necrodominance) - CR 119.4's variable
#: payment, zero upward. The "may" is the amount itself (paying 0 is not
#: paying), so it is one question (`Game.pay_any_amount_of_life`), never a
#: "you may" wrapper plus a second one. The amount paid is recorded for a
#: later "that many" (`that_many`).
#: "Remove a loyalty counter from each of any number of permanents you
#: control." (Chandra, Legacy of Fire's 0) - CR 107.1c's any number, zero
#: upward, of the controller's own permanents that have such a counter; how
#: many were chosen is recorded for a later "that many" (`that_many`).
_REMOVE_A_COUNTER_FROM_EACH_OF_ANY_NUMBER_RE = re.compile(
    r"^remove an? (?P<kind>\S+) counter from each of any number of "
    r"(?P<description>.+?) you control$",
    re.IGNORECASE,
)


#: "Untap all tokens you control." (Jiang Yanggu, Never Alone's end step
#: trigger); "Untap all nonland permanents you control." (Dramatic
#: Reversal) - CR 701.26b's untap over a filtered group rather than one
#: named object, and player-owned rather than source-owned, which is why
#: this lives in the shared per-clause reader (both a spell's own
#: resolution and a triggered ability's reach it) rather than only the
#: ability-only fallback `_UNTAP_TRIGGER_SUBJECT_RE` is read from. Only the
#: qualifiers the pool prints are read; a filter this cannot name leaves the
#: clause unread rather than guessing.
_UNTAP_ALL_QUALIFIER_RE = re.compile(
    r"^untap all (?P<nonland>nonland )?(?P<noun>permanents|creatures|artifacts|tokens|lands) "
    r"you control$",
    re.IGNORECASE,
)


#: Avatar Aang: "Whenever you waterbend, earthbend, firebend, or airbend,
#: draw a card. Then if you've done all four this turn, transform Avatar
#: Aang." `split_effect_clauses` cuts the sentence in two on the period;
#: "draw a card" is `_DRAW_RE`'s own ordinary shape (nothing new needed for
#: it), and this reads the second clause. The name is captured rather than
#: assumed, so this is CR 201.5's self-reference by printed name generalised
#: past Aang's own - any future double-faced card that prints this exact
#: "done all four this turn, transform `<name>`" shape reads the same way,
#: it is only that no other one exists yet. The four "this turn" facts
#: (`_ALL_FOUR_BEND_FACTS`) are `Game.turn_facts` entries recorded by
#: whichever mechanic actually bent that way - CR 701.67c for waterbend
#: (`Game.record_turn_fact("waterbent", ...)`, see `models/game.py`); this
#: clause only reads the ledger, not how any entry got there.
_TRANSFORM_IF_DONE_ALL_FOUR_BENDS_RE = re.compile(
    r"^(?:then\s+)?if you'?ve done all four this turn,\s*transform (?P<name>[^.]+)$",
    re.IGNORECASE,
)

_ALL_FOUR_BEND_FACTS = ("waterbent", "earthbent", "firebent", "airbent")


#: "You gain life equal to the life you've lost this turn." - Children of
#: Korlis. The amount is read off `Player.life_lost_this_turn`, the gross
#: per-turn ledger, not the net change in the life total: every route down
#: counts, because CR 119.2 ("Damage dealt to a player normally causes that
#: player to lose that much life") and CR 120.3a make damage a life loss, and
#: CR 118.3b ("Paying life is done by subtracting the indicated amount of life
#: from a player's life total") makes a cost paid in life one too. The
#: reminder text the card prints - "(Damage causes loss of life.)" - names only
#: the damage half and is not rules text (CR 207.2a); `parse_clause_effect`
#: strips it before this ever runs.
_GAIN_LIFE_EQUAL_TO_LIFE_LOST_THIS_TURN_RE = re.compile(
    r"you gains? life equal to the life you'?(?:ve|’ve)? lost this turn",
    re.IGNORECASE,
)


#: "the number of `<kind>` counters on it" - Kjeldoran Javelineer's own "deals
#: damage equal to the number of age counters on it": `_COUNTER_ON_IT_RE`'s
#: source-relative count, spelled as a number rather than a "for each".
_NUMBER_OF_COUNTERS_ON_IT_RE = re.compile(
    r"^the number of (?P<counters>(?:\+1/\+1|-1/-1|[a-z]+) counters on (?:it|this \w+))$",
    re.IGNORECASE,
)


def parse_clause_effect(clause: str) -> ClauseEffect | None:
    """One clause of an effect with nobody to ask a question of: a plain life
    total change, an energy grant, a draw, a mill, a surveil or a scry.

    `fullmatch` throughout, on purpose - the same discipline
    `parse_search_and_put_effect` uses. A clause with anything else in it
    (a target, a "you may", a number this parser cannot read) matches nothing
    and comes back `None`, which `parse_player_effect` below treats as reason
    to run *none* of the effect rather than part of it.
    """
    clause = clause.strip()
    # CR 207.2a: reminder text in parentheses is not rules text - "get {E}
    # (an energy counter)" and "surveil 1 (Look at ...)" both carry one.
    clause = re.sub(r"\s*\([^()]*\)\s*$", "", clause).strip().rstrip(".").strip()

    life_total_becomes = life_total_becomes_effect_for(clause)
    if life_total_becomes is not None:
        return life_total_becomes

    double_life_total = _parse_double_your_life_total_clause(clause)
    if double_life_total is not None:
        return double_life_total

    count_the_number_of = _parse_count_the_number_of_clause(clause)
    if count_the_number_of is not None:
        return count_the_number_of

    lands_dont_untap_next_step = _parse_lands_dont_untap_next_step_clause(clause)
    if lands_dont_untap_next_step is not None:
        return lands_dont_untap_next_step

    discard_unless = _parse_discard_unless_condition_clause(clause)
    if discard_unless is not None:
        return discard_unless

    if _PUT_CARD_FROM_HAND_ON_BOTTOM_OF_LIBRARY_RE.fullmatch(clause):
        return _put_card_from_hand_on_bottom_of_library

    each_opponent_draws = _each_opponent_draws_clause(clause)
    if each_opponent_draws is not None:
        return each_opponent_draws

    if match := _GAIN_LIFE_RE.fullmatch(clause):
        amount = parse_count(match.group("n"))
        if match.group("times") is not None:
            amount *= parse_count(match.group("times"))
        each = match.group("each")
        multiplier = _for_each_multiplier(each) if each is not None else None
        if each is not None and multiplier is None:
            return None

        # Through `Game.gain_life`, not `Player.gain_life`. CR 119.9: "Some
        # triggered abilities are written, 'Whenever [a player] gains life,
        # . . . .' Such abilities are treated as though they are written,
        # 'Whenever a source causes [a player] to gain life, . . . .'" - the
        # rule puts no condition on *which* source, so a spell's own "you
        # gain 3 life" is as much a life-gain event as lifelink is. Calling
        # `Player.gain_life` directly adjusted the total (CR 119.3) but
        # emitted nothing, so Amalia Benavides Aguirre and every other
        # "whenever you gain life" card was blind to every spell in the pool.
        def gain_life(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            # CR 608.2h: a "for each" count is taken once, when the effect
            # applies.
            total = amount * multiplier(game, player.username, source_id) if multiplier else amount
            game.gain_life(player, total)

        return gain_life

    if match := _PLAYER_GAINS_HEXPROOF_RE.fullmatch(clause):
        return _player_gains_hexproof_clause(match)

    if match := _TAKE_EXTRA_TURNS_RE.fullmatch(clause):
        turns = parse_count(match.group("n"))
        if turns is None or turns < 1:
            return None

        def take_extra_turns(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            for _ in range(turns):
                game.grant_extra_turn(player.username)

        return take_extra_turns

    if _SKIP_UNTAP_STEP_OF_THAT_TURN_RE.fullmatch(clause):

        def skip_that_turns_untap_step(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            skipping = game.players_skipping_next_untap
            skipping[player.username] = skipping.get(player.username, 0) + 1

        return skip_that_turns_untap_step

    if _DURING_THAT_TURN_POWER_UP_RESTRICTED_RE.fullmatch(clause):

        def restrict_power_up_next_turn(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            game.power_up_restricted_turns.add(game.turn.turns_taken + 1)

        return restrict_power_up_next_turn

    if _HARNESS_SELF_RE.fullmatch(clause):

        def harness_self(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            permanent = game.find_by_id(UUID(source_id)) if source_id is not None else None
            if permanent is not None:
                game.harness(permanent)

        return harness_self

    if match := _ADDITIONAL_LAND_PLAY_RE.fullmatch(clause):
        amount = parse_count(match.group("n"))
        if amount is None or amount < 1:
            return None

        def extra_land_play(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            game.grant_extra_land_play(player.username, amount)

        return extra_land_play

    if match := _REMOVE_A_COUNTER_FROM_EACH_OF_ANY_NUMBER_RE.fullmatch(clause):
        kind = _counter_kind(match.group("kind"))
        description = match.group("description")
        requirement = (
            None
            if description.lower() in ("permanent", "permanents")
            else permanent_description(description)
        )
        if requirement is None and description.lower() not in ("permanent", "permanents"):
            return None

        def remove_from_any_number(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if permanent.counters[kind] > 0
                and (
                    requirement is None
                    or requirement.rejects(permanent, player.username, game) is None
                )
            ]
            chosen_ids: tuple[UUID, ...] = ()
            if candidates:
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"remove a {kind} counter from each of any number of permanents",
                        source=source,
                        source_id=source_id,
                        amount=len(candidates),
                        exact=False,
                        cards=tuple(state.id for state in candidates),
                    )
                )
                assert isinstance(answer, tuple)
                chosen_ids = answer
            by_id = {state.id: state for state in candidates}
            for card_id in chosen_ids:
                by_id[card_id].remove_counters(kind, 1)
            # CR 608.2c: "Exile that many cards" reads how many came off.
            game.record_count(len(chosen_ids))

        return remove_from_any_number

    if _PAY_ANY_AMOUNT_OF_LIFE_RE.fullmatch(clause):

        def pay_any_amount_of_life(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            game.record_count(
                game.pay_any_amount_of_life(player, source=source, source_id=source_id)
            )

        return pay_any_amount_of_life

    if _GAIN_LIFE_EQUAL_TO_LIFE_LOST_THIS_TURN_RE.fullmatch(clause):
        # Through `Game.gain_life` for the same CR 119.9 reason the flat
        # "you gain N life" above uses it.
        return lambda game, player, source, source_id: game.gain_life(
            player, player.life_lost_this_turn
        )

    if match := _LOSE_LIFE_RE.fullmatch(clause):
        amount = parse_count(match.group("n"))
        each = match.group("each")
        multiplier = _for_each_multiplier(each) if each is not None else None
        if each is not None and multiplier is None:
            return None

        def lose_life(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            total = amount * multiplier(game, player.username, source_id) if multiplier else amount
            game.lose_life(player, total)

        return lose_life

    if _THAT_MUCH_LIFE_LOSS_RE.fullmatch(clause):

        def lose_that_much_life(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            amount = _that_many_or_notice(game, clause, source_id=source_id, source_name=source)
            if amount:
                game.lose_life(player, amount)

        return lose_that_much_life

    counted_life = _parse_counted_life_change_clause(clause)
    if counted_life is not None:
        return counted_life

    half_life_loss = _parse_half_life_loss_clause(clause)
    if half_life_loss is not None:
        return half_life_loss

    each_opponent_punisher = _parse_each_opponent_loses_life_unless_sacrifice_or_discard_clause(
        clause
    )
    if each_opponent_punisher is not None:
        return each_opponent_punisher

    if match := _EACH_OPPONENT_LOSES_LIFE_RE.fullmatch(clause):
        amount = parse_count(match.group("n"))

        def each_opponent_loses(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            for opponent in _opponents(game, player.username):
                game.lose_life(opponent, amount)

        return each_opponent_loses

    if match := _ENERGY_RE.fullmatch(clause):
        amount = len(re.findall(r"\{e\}", match.group("e"), re.IGNORECASE))
        return lambda game, player, source, source_id: game.add_player_counters(
            player, Counter.ENERGY, amount
        )

    if match := _POISON_COUNTERS_RE.fullmatch(clause):
        poison = parse_count(match.group("n"))
        return lambda game, player, source, source_id: game.add_player_counters(
            player, Counter.POISON, poison
        )

    if match := _DRAW_CARDS_EQUAL_TO_RE.fullmatch(clause):
        # "Draw cards equal to `<expr>`" (Sea Gate Restoration's "the number
        # of cards in your hand plus one", Tamiyo, Seasoned Scholar's "half
        # the number of cards in your library, rounded up"). A bare X has no
        # announced value to read here, so it is refused rather than read as
        # zero.
        expression = match.group("expr")
        if re.search(r"\bx\b", expression, re.IGNORECASE):
            return None
        reader = amount_expression(expression)
        if reader is None:
            return None

        def draw_equal_to(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            # CR 608.2h: counted once, as the effect applies.
            total = reader(game, player.username, None, 0)
            if total:
                game.draw_cards(player.username, total)

        return draw_equal_to

    if match := _HALF_OF_OWN_LIBRARY_RE.fullmatch(clause):
        half = parse_half(match.group("half"))
        if half is None:
            return None
        mills = match.group("verb").lower().startswith("mill")
        round_up = half.round_up

        def half_of_own_library(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            # CR 608.2h: the library's size as the effect applies.
            count = halve(len(player.library), round_up=round_up)
            if count <= 0:
                return
            if mills:
                _mill(game, player, count)
            else:
                game.exile_cards(list(player.library[:count]))

        return half_of_own_library

    if _NO_MAXIMUM_HAND_SIZE_REST_OF_GAME_RE.fullmatch(clause):
        return lambda game, player, source, source_id: (
            player.remove_maximum_hand_size_for_rest_of_game()
        )

    if _BECOME_THE_MONARCH_RE.fullmatch(clause):
        # CR 725.1 - Grave Venerations' "you become the monarch.", Palace
        # Sentinels' identical clause off a creature ETB rather than an
        # enchantment's.
        return lambda game, player, source, source_id: game.become_monarch(player.username)

    if match := _DRAW_RE.fullmatch(clause):
        amount = parse_count(match.group("n")) if match.group("n") else 1
        each = match.group("each")
        multiplier = _for_each_multiplier(each) if each is not None else None
        if each is not None and multiplier is None:
            return None
        draws_that_many = match.group("that_many") is not None
        adjust = parse_count(match.group("adjust")) if match.group("adjust") else 0
        if adjust is None or (adjust and not draws_that_many):
            return None
        if match.group("op") and match.group("op").lower() == "minus":
            adjust = -adjust

        def draw(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            base = amount
            if draws_that_many:
                counted = _that_many_or_notice(
                    game, clause, source_id=source_id, source_name=source
                )
                if counted is None:
                    return
                base = max(counted + adjust, 0)  # CR 107.1b
            total = base * multiplier(game, player.username, source_id) if multiplier else base
            if total:
                game.draw_cards(player.username, total)

        return draw

    if match := _DISCARD_A_CARD_RE.fullmatch(clause):
        quality_word = match.group("quality")
        predicate: Callable[[CardState], bool] | None = None
        if quality_word is not None:
            predicate = _nonland_or_typed_card_matcher(quality_word) or _quality_matcher(
                quality_word
            )
            if predicate is None:
                return None
        if match.group("any") is not None:
            return lambda game, player, source, source_id: _discard_cards(
                game,
                player,
                len(player.hand),
                source,
                source_id=source_id,
                exact=False,
                predicate=predicate,
            )
        amount = parse_count(match.group("n"))
        if amount is None:
            return None
        exact = match.group("upto") is None
        return lambda game, player, source, source_id: _discard_cards(
            game,
            player,
            amount,
            source,
            source_id=source_id,
            exact=exact,
            predicate=predicate,
        )

    if match := _EXILE_CARDS_FROM_OWN_GRAVEYARD_RE.fullmatch(clause):
        quality_word = match.group("quality")
        exile_predicate: Callable[[CardState], bool] | None = None
        if quality_word is not None:
            exile_predicate = _nonland_or_typed_card_matcher(quality_word) or _quality_matcher(
                quality_word
            )
            if exile_predicate is None:
                return None
        amount = parse_count(match.group("n"))
        if amount is None:
            return None
        return lambda game, player, source, source_id: _exile_cards_from_graveyard(
            game,
            player,
            amount,
            source,
            source_id=source_id,
            predicate=exile_predicate,
        )

    if _DISCARD_HAND_RE.fullmatch(clause):

        def discard_hand(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            _discard_cards(game, player, len(player.hand), source, source_id=source_id, exact=True)

        return discard_hand

    if match := _GET_AN_EMBLEM_RE.fullmatch(clause):
        emblem_text = match.group("text")

        def get_an_emblem(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            game.create_emblem(player.username, emblem_text, source)

        return get_an_emblem

    if match := _MILL_RE.fullmatch(clause):
        amount = parse_count(match.group("n")) if match.group("n") else 1
        each = match.group("each")
        multiplier = _for_each_multiplier(each) if each is not None else None
        if each is not None and multiplier is None:
            return None
        mills_that_many = match.group("that_many") is not None

        def mill(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            base = amount
            if mills_that_many:
                counted = _that_many_or_notice(
                    game, clause, source_id=source_id, source_name=source
                )
                if counted is None:
                    return
                base = counted
            total = base * multiplier(game, player.username, source_id) if multiplier else base
            _mill(game, player, total)

        return mill

    if match := _SURVEIL_RE.fullmatch(clause):
        reader = _amount_reader(match.group("n"), match.group("where_x"))
        if reader is None:
            return None
        return lambda game, player, source, source_id: game.surveil(
            player, reader(game, player.username), source=source, source_id=source_id
        )

    if match := _SCRY_RE.fullmatch(clause):
        reader = _amount_reader(match.group("n"), match.group("where_x"))
        if reader is None:
            return None
        return lambda game, player, source, source_id: game.scry(
            player, reader(game, player.username), source=source, source_id=source_id
        )

    if _SHUFFLE_RE.fullmatch(clause):
        # CR 701.24a. Always wrapped by `_parse_optional_player_clause`'s
        # "you may" (no printed card in the pool shuffles unconditionally
        # here - that shape goes through `_BARE_SHUFFLES_RE`'s own "each
        # player ..." family instead). Unlike every other optional clause
        # this parser reads, an unscripted "you may shuffle" declines - see
        # `_parse_optional_player_clause`'s own `default=False` for this one
        # clause, and `Decision.default_may`'s docstring for the CR 701.20d
        # reasoning.
        return lambda game, player, source, source_id: game.shuffle_library(player)

    if match := _UNTAP_ALL_QUALIFIER_RE.fullmatch(clause):
        nonland = match.group("nonland") is not None
        noun = match.group("noun").lower()

        def untap_all(game: "Game", player: Player, source: str, source_id: str | None) -> None:
            for state in list(game.battlefield):
                if state.controller == player.username and _untap_all_qualifier_matches(
                    game, state, noun, nonland
                ):
                    state.untap(exert_applies=False)

        return untap_all

    if match := _TRANSFORM_IF_DONE_ALL_FOUR_BENDS_RE.fullmatch(clause):
        name = match.group("name").strip()

        def transform_if_done_all_four_bends(
            game: "Game", player: Player, source: str, source_id: str | None
        ) -> None:
            # CR 201.5: "if an object's text uses its own name, it is
            # referring to that particular object" - the printed name is
            # read here rather than assumed, so a differently-named card
            # printing this same shape self-references correctly too.
            if name.lower() != source.lower() or source_id is None:
                return
            if not all(
                game.turn_fact_holds(fact, player.username) for fact in _ALL_FOUR_BEND_FACTS
            ):
                return
            permanent = game.find_by_id(UUID(source_id))
            if permanent is None or permanent.zone is not Zone.BATTLEFIELD:
                return
            transform_permanent(game, permanent)

        return transform_if_done_all_four_bends

    return None


def _parse_player_clauses(text: str) -> list[ClauseEffect] | None:
    """Every clause of `text`, or `None` the moment one of them fails to parse.

    Fail-closed on purpose: CR 608.2c has no notion of running half an effect,
    and a half-executed spell - the mana paid, one clause resolved, the next
    silently skipped - is a wrong game state that looks like a right one. A
    single unparseable clause (a target, a choice, anything this wave does not
    cover) throws away every clause around it too, even the ones that would
    have parsed fine alone.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed = [_parse_optional_player_clause(clause) for clause in clauses]
    if any(effect is None for effect in parsed):
        return None
    return parsed  # type: ignore[return-value]


def parse_player_effect(text: str) -> AbilityEffect | None:
    """A triggered or activated ability's effect, read off its own printed
    text instead of a per-card table entry - see `parse_clause_effect` and
    `split_effect_clauses`.

    This is what fixes Guide of Souls: "Whenever another creature you control
    enters, you gain 1 life and get {E}" used to go on the stack, resolve, and
    change nothing, because no table row taught the model either half of it.
    """
    clauses = _parse_player_clauses(text)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.player(ability.controller)
        for clause in clauses:
            clause(game, player, ability.source_name, source_id_of(ability))
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def parse_player_effect_for_spell(text: str) -> Effect | None:
    """The spell-resolution twin of `parse_player_effect`, for an instant or
    sorcery with no table row - Mishra's Bauble aside, a plain "gain life /
    draw / mill / surveil / scry" spell has no cost or target to complicate
    it, so the same clause parser reads it off `Card.oracle_text` directly.
    """
    clauses = _parse_player_clauses(text)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        player = game.controller_of(spell)
        for clause in clauses:
            clause(game, player, spell.card.name, source_id_of(spell))
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: CR 722.3a - "Target creature becomes prepared" (Hexhaven Dueling Arena).
#: `phrase` captures the whole "target ..." noun phrase, "that attacked this
#: turn" qualifier included, the same way `_DESTROY_TARGET_RE.phrase` does -
#: `_targets_understood` reads the qualifier off it via `machines/targeting.
#: py`'s own `must_have_attacked_this_turn`, not this regex.
_BECOMES_PREPARED_TARGET_RE = re.compile(
    r"^(?P<phrase>target .+?) becomes prepared\.?$", re.IGNORECASE
)


#: "Exile target player's graveyard." (Bojuka Bog, Tormod's Crypt) - checked
#: ahead of `_EXILE_TARGET_RE` below, which would otherwise match the same
#: text (its `.*target.+` phrase is a superset), read `_targets_understood`
#: with `allow_player_targets` left at its default `False`, refuse the whole
#: clause on the player-target it cannot see, and `return None` before this
#: pattern ever got a turn - `_parse_targeted_clause` commits to the first
#: regex that fullmatches, not the first that also parses successfully.
#:
#: The plural, count-bearing form reads the same way: "Exile any number of
#: target players' graveyards." (Thraben Charm's third mode, The Death of
#: Gwen Stacy's chapter III) - one graveyard per player target, and CR
#: 107.1c's "any number" (zero included) is simply how many player targets
#: the stack object carries.
_EXILE_TARGET_PLAYERS_GRAVEYARD_RE = re.compile(
    r"^exile (?P<phrase>.*target (?:player's graveyard|players' graveyards))\.?$",
    re.IGNORECASE,
)
#: "Exile all graveyards." (Rest in Peace) and "Exile all cards that are
#: `<quality>` from all graveyards." (Sanctifier en-Vec) - no "target" at all
#: (CR 115.1 has nothing to target here), so neither collides with
#: `_EXILE_TARGET_RE`'s "target" requirement.
_EXILE_ALL_GRAVEYARDS_RE = re.compile(r"^exile all graveyards\.?$", re.IGNORECASE)
#: "Exile each opponent's graveyard." (Soul-Guide Lantern, Ashiok, Dream
#: Render) - `_EXILE_ALL_GRAVEYARDS_RE`'s own "no target" shape (CR 115.1)
#: with a player-set qualifier narrowing which graveyards, the way
#: `_DAMAGE_EACH_OPPONENT_RE` reads "each opponent" for damage.
#:
#: The leading "then " this pattern used to carry is gone, and so is the
#: sibling comment that justified it: Ashiok's whole ability is two clauses
#: ("Target player mills four cards. Then exile each opponent's graveyard.")
#: and `split_effect_clauses` now strips a sentence-initial "then" for every
#: card (`_LEADING_THEN_RE`), so the word never reaches a clause parser and
#: keeping it here would leave a branch nothing can match.
_EXILE_EACH_OPPONENTS_GRAVEYARD_RE = re.compile(
    r"^exile each opponent'?s graveyards?\.?$", re.IGNORECASE
)


_EXILE_QUALITY_FROM_ALL_GRAVEYARDS_RE = re.compile(
    r"^exile all cards that are (?P<quality>.+?) from all graveyards\.?$", re.IGNORECASE
)


#: "Counter target creature or legendary spell unless its controller pays
#: {3}." (Icy Reception) - a compound target whose printed noun is not
#: literally "spell" (`_COUNTER_UNLESS_PAYS_RE`'s own shape), read through
#: `_targets_understood` - `machines/targeting.py` already reads "or
#: legendary spell"/"or `<type>` spell" as CR 601.2c's own compound
#: restriction (`TargetRequirement.or_any_spell`) - rather than a second,
#: narrower qualifier grammar hand-fitted to this one card's wording.
_COUNTER_UNLESS_PAYS_PHRASE_RE = re.compile(
    r"^counter (?P<phrase>target .+?) unless its controller pays \{(?P<n>\d+)\}\.?$",
    re.IGNORECASE,
)
#: "Counter target spell an opponent controls unless they pay {1}." -
#: Hope-Ender Coatl's own cast trigger (CR 603.2, 601.2i): the ability-
#: context twin of `_COUNTER_UNLESS_PAYS_PHRASE_RE`'s spell-context "unless
#: its controller pays". CR 607.1's antecedent for "they" is the identical
#: player either way - the *targeted* spell's controller, the same one
#: `_counter_unless_pays_effect` already asks (its own docstring: "the
#: targeted spell's controller ... not this counterspell's caster") - only
#: the printed pronoun differs, answering back to "an opponent controls"
#: rather than repeating "its controller". Nothing before this needed a
#: *triggered* ability to ask an "unless" question of a targeted spell's
#: controller (`_COUNTER_UNLESS_PAYS_PHRASE_RE` is `for_spell`-gated, a
#: resolving spell's own row), so this is read for both `for_spell` values
#: rather than narrowing either existing shape.
_COUNTER_UNLESS_THEY_PAY_PHRASE_RE = re.compile(
    r"^counter (?P<phrase>target .+?) unless they pay \{(?P<n>\d+)\}\.?$",
    re.IGNORECASE,
)
#: "Counter target triggered ability or colorless spell." (Consign to
#: Memory) and the like - a compound target rather than a single qualified
#: noun, so `_COUNTER_TARGET_SPELL_RE` does not reach it. `counter_targets`
#: does not care which half of the "or" was actually targeted - see its own
#: docstring - so this only has to recognise the shape, not re-derive it.
_COUNTER_TARGET_ABILITY_OR_SPELL_RE = re.compile(
    r"^counter target (?:(?:activated|triggered)\s+)*abilit(?:y|ies) or "
    rf"(?:{_SPELL_QUALIFIER_WORD} )?spell\.?$",
    re.IGNORECASE,
)
#: "Counter target activated or triggered ability." (Repudiate) - CR 113.9's
#: plain ability-only shape, with no "or spell" tail at all (unlike
#: `_COUNTER_TARGET_ABILITY_OR_SPELL_RE`'s Consign to Memory/Cryptic Command
#: compound). `resolve_target`/`legal_target` already resolve a `TargetRef`
#: against an `AbilityOnStack` via `Game.find_ability_by_id` when
#: `find_by_id` finds no card (Tishana's Tidebinder is what built that path),
#: and `Game.counter` already accepts either kind of `StackObject`
#: (CR 113.9) - so `counter_targets` needs nothing new, only this regex to
#: reach it, the same way `_COUNTER_TARGET_ABILITY_OR_SPELL_RE` already does
#: for the compound shape.
#: "Counter target spell that targets `<description>`." (Fugitive Droid) and
#: "Counter target spell or ability that targets `<description>`." (Siren
#: Stormtamer) - a general catch-all for any "Counter target `<phrase>`."
#: sentence none of this file's own hand-fitted templates above already
#: claims, tried only once they have all declined: `_targets_understood`
#: (via `machines/targeting.py`'s own reader, widened this task with
#: `must_target_you`/`must_target_types` for exactly this "that targets ..."
#: shape) is what actually vets it, so a phrase neither this file nor
#: targeting.py can read still fails closed rather than silently countering
#: an unrestricted "any spell".
_COUNTER_TARGET_PHRASE_RE = re.compile(r"^counter (?P<phrase>target .+?)\.?$", re.IGNORECASE)

_COUNTER_TARGET_ABILITY_RE = re.compile(
    r"^counter target (?:activated or triggered |activated |triggered )?"
    r"abilit(?:y|ies)\.?$",
    re.IGNORECASE,
)


#: "Put target card from your graveyard on the bottom of your library."
#: (Paradox Shaper's own printed `{2}` ability) and "Put target card from a
#: graveyard on the bottom of its owner's library." (Cogwork Archivist's own
#: shape, targeting any graveyard rather than only the controller's own) -
#: the same verb and destination, printed both ways. CR 401.2: a library
#: stays face down and in whatever order it arrives in, so this is a plain
#: move, never CR 701.24's shuffle. `Game.put_cards_into_library` already
#: moves each card into *its own* owner's library regardless of which
#: printing's wording is read, so "your library" and "its owner's library"
#: need no different code - only the target phrase's own "your graveyard"
#: vs "a graveyard" actually changes what may be targeted (CR 404.1: a
#: graveyard is per player).
_PUT_TARGET_FROM_GRAVEYARD_BOTTOM_OF_LIBRARY_RE = re.compile(
    r"put (?P<phrase>.*target.+(?:in|from) (?:a|your|their|any) graveyard) "
    r"on the bottom of (?:its owner'?s|your|their) library\.?$",
    re.IGNORECASE,
)


#: "Put target creature card from your graveyard on top of your library." -
#: Paramecia Coloniex's own reflexive consequence (TMT), the "top" twin of
#: `_PUT_TARGET_FROM_GRAVEYARD_BOTTOM_OF_LIBRARY_RE` immediately above. Same
#: verb, same origin-zone phrase kept inside `phrase` for `_targets_
#: understood` to read the zone off, only the printed end of the library
#: differs.
_PUT_TARGET_FROM_GRAVEYARD_TOP_OF_LIBRARY_RE = re.compile(
    r"put (?P<phrase>.*target.+(?:in|from) (?:a|your|their|any) graveyard) "
    r"on top of (?:its owner'?s|your|their) library\.?$",
    re.IGNORECASE,
)


#: "Put target nonland permanent on top of its owner's library." - Lashweed
#: Lurker's own cast trigger (wrapped in "you may", CR 118.12/608.2d, read by
#: `_YOU_MAY_RE`'s generic optional-targeted-clause wrap before this is ever
#: tried). The battlefield twin of `_PUT_TARGET_FROM_GRAVEYARD_TOP_OF_
#: LIBRARY_RE`: no "from ... graveyard" origin phrase at all, since the
#: target here is still on the battlefield (CR 401.1's library placement
#: applies the identical way regardless of which zone the card is leaving,
#: `put_ability_targets_on_top_of_owners_library`'s own docstring).
_PUT_TARGET_PERMANENT_TOP_OF_OWNERS_LIBRARY_RE = re.compile(
    r"put (?P<phrase>target [^.]*?) on top of (?:its owner'?s|your|their) library\.?$",
    re.IGNORECASE,
)


#: "Return target card from your graveyard to your hand." (Eternal Witness,
#: wrapped in "you may") and "Return target creature card from your graveyard
#: to your hand." (Raise Dead) - the same verb as `_RETURN_TARGET_RE` but "to
#: your hand" rather than "to its owner's hand", so the two patterns never
#: collide. `phrase` keeps "from your graveyard" inside it so
#: `_targets_understood` can see the zone the way it already reads "target
#: creature card in your graveyard" for `return_ability_targets_to_hand`
#: elsewhere in this file.
_RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE = re.compile(
    r"return (?P<phrase>.*target.+from your graveyard) to your hand\.?$", re.IGNORECASE
)
#: "Return target creature card with mana value 3 or less from your
#: graveyard to the battlefield." (Unearth), "... target permanent card ...
#: to the battlefield." (Renegade Rallier's Revolt trigger), and Tameshi,
#: Reality Architect's own activated ability once `substitute_x` has already
#: turned its "mana value X or less" into a real number - the same verb as
#: `_RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE` immediately above, with the only
#: difference being the printed destination. Not Greasefang's shape
#: (`_RETURN_TARGET_FROM_GRAVEYARD_GAINS_THEN_BOUNCE_RE`): that one is tried
#: first, against the *whole* unsplit ability text, so a card whose sentence
#: continues past "to the battlefield." with "It gains ..." never reaches
#: this fullmatch at all.
#: Celestine, the Living Saint's own "... with mana value X or less from
#: your graveyard to the battlefield, where X is the amount of life you
#: gained this turn." widens this further: CR 107.3c's own "where X is
#: <expression>" definition sits *after* "to the battlefield" in the printed
#: sentence, past where the un-widened regex's own `\.?$` anchor used to end
#: the match outright. `machines/targeting.profile_for_text` already reads
#: "with mana value X or less, where X is ..." into `comparison_x_definition`
#: regardless of what comes between the two ("from your graveyard to the
#: battlefield" here) - proven directly against `profile_for_text` before
#: this regex was touched - so the fix is only to let the *outer* fullmatch
#: reach that far, and to fold the "where X is ..." tail into `phrase` before
#: `_targets_understood` reads it, the same window `profile_for_text` itself
#: already scans.
_RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_RE = re.compile(
    r"return (?P<phrase>.*target.+from your graveyard) to the battlefield(?P<tapped> tapped)?"
    r"(?P<where_x>, where [xX] is [^.]+)?\.?$",
    re.IGNORECASE,
)
#: "Return target `<X>` from your graveyard to the battlefield[ tapped] with
#: [an additional] `<n>` `<kind>` counter(s) on it." - Generous Revival's own
#: "an additional" (Neoform's own already-general rider phrase) and Persist's
#: bare "with a `<kind>` counter on it" (no "additional" at all) are the same
#: CR 122.1 counter-placed-as-the-permanent-arrives shape, one word shorter -
#: "additional" is optional rather than required, mirroring `_RETURN_CARDS_
#: FROM_YOUR_GRAVEYARD_RE`'s own untargeted "with N `<kind>` counters on it"
#: tail for the targeted family. Makeshift Mannequin's own "mannequin"
#: counter (real, off-set, non-fra) proves this reads the shape rather than
#: either card's own counter word.
_RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_WITH_COUNTER_RE = re.compile(
    r"return (?P<phrase>.*target.+from your graveyard) to the battlefield"
    r"(?P<tapped> tapped)?"
    rf" with an? (?:additional )?(?:(?P<counter_n>{COUNT}) )?(?P<counter>[a-z0-9+/-]+) counters? "
    r"on it\.?$",
    re.IGNORECASE,
)


#: "Up to one target player puts all the cards from their graveyard on the
#: bottom of their library in a random order." (Endurance) - CR 115.6's "up
#: to one" prefix sits before "target player", which is why `phrase` starts
#: with a greedy `.+` rather than anchoring on the word "target" itself.
_GRAVEYARD_TO_BOTTOM_OF_LIBRARY_RE = re.compile(
    r"^(?P<phrase>.*target player) puts all the cards from (?:their|his or her) graveyard "
    r"on the bottom of (?:their|his or her) library in a random order\.?$",
    re.IGNORECASE,
)


#: "Regenerate target X." - Asceticism's `{1}{G}` and Welding Jar's sacrifice
#: ability. CR 701.19a: "If the effect of a resolving spell or ability
#: regenerates a permanent, it creates a replacement effect that protects the
#: permanent the next time it would be destroyed this turn." Creating the
#: shield is the whole of what happens now - CR 701.19c says in as many words
#: that activating an ability which creates a shield "is not the same as
#: regenerating a permanent", so nothing is tapped and no damage removed until
#: the shield is actually spent.
_REGENERATE_TARGET_RE = re.compile(r"regenerate (?P<phrase>.*target.+)", re.IGNORECASE)

#: "Remove target attacking or blocking creature from combat." (Hollowhenge
#: Spirit, Labyrinth of Skophos), "Remove target blocking creature from
#: combat" (Balduvian Warlord's first sentence), and the riders that share the
#: clause: "... from combat and untap it." (Reconnaissance, "attacking creature
#: you control") and the reversed "Untap target attacking creature an opponent
#: controls and remove it from combat." (Thaumatic Compass). CR 506.4: "if an
#: effect specifically removes it from combat" the permanent is removed from
#: combat; the phrase itself (attacking and/or blocking) is `targeting.py`'s.
_REMOVE_FROM_COMBAT_RE = re.compile(
    r"remove (?P<phrase>(?:up to )?(?:\S+ )?target [^.]+?) from combat"
    r"(?P<untap> and untap (?:it|them))?",
    re.IGNORECASE,
)
_UNTAP_AND_REMOVE_FROM_COMBAT_RE = re.compile(
    r"untap (?P<phrase>(?:up to )?(?:\S+ )?target [^.]+?) and remove (?:it|them) from combat",
    re.IGNORECASE,
)


def remove_ability_targets_from_combat(game: "Game", stack_object: "StackObject") -> None:
    """Remove each target this still legally targets from combat (CR 506.4).

    `CombatMachine.remove` is the whole of it: a removed attacker takes its
    attack with it, a removed blocker leaves its attacker blocked (CR 509.1h).
    """
    for target in game.resolve_targets(stack_object):
        if isinstance(target, CardState):
            game.combat.remove(target.id)


#: Fling: "<Source> deals damage equal to the sacrificed creature's power to
#: any target." An additional-cost-bound amount, not `_DAMAGE_TARGET_RE`'s
#: literal number - `COUNT` never matches the word "equal", so this needs
#: its own regex and its own resolution-time read of `Game.cast_record`'s
#: `additional_cost_cards` (CR 118.8a's "sacrifice a creature" additional
#: cost, CR 601.2h's payment already ran by the time this clause resolves).
_DAMAGE_EQUAL_TO_SACRIFICED_CREATURE_POWER_RE = re.compile(
    r"^.*\bdeals? damage equal to the sacrificed creature'?s power to "
    r"(?P<phrase>any target|.*target.+)\.?$",
    re.IGNORECASE,
)
#: "This creature deals damage equal to its power to `<target>`." - the
#: ability's own source deals damage equal to its own power (CR 208.1):
#: Cyclops Superconductor's reflexive consequence, Spikeshot Elder's
#: activation. CR 608.2h reads the power as the effect is applied - the
#: current power while the source is on the battlefield, its last known
#: information once it is not - and CR 113.7a lets the source "still perform
#: the action even though it no longer exists", which is what a dies trigger
#: (CR 603.10a) always asks of it.
_SELF_DEALS_DAMAGE_EQUAL_TO_ITS_STAT_RE = re.compile(
    r"^this [a-z]+ deals damage equal to its (?P<stat>power|toughness) to "
    r"(?P<phrase>any target|.*\btarget\b.+?)\.?$",
    re.IGNORECASE,
)
#: Combustion Technique: "<Source> deals damage equal to 2 plus the number of
#: Lesson cards in your graveyard to target creature." A dynamic amount read
#: through `amount_expression` (arithmetic over one or more `count_expression`
#: terms, CR 107.1b's floor at zero already built in there) rather than a
#: fixed `{COUNT}` - the general twin of `_DAMAGE_EQUAL_TO_SACRIFICED_
#: CREATURE_POWER_RE`'s one specific expression, for any future card whose
#: own damage amount is one `amount_expression` can read, not only this one.
_DAMAGE_EQUAL_TO_EXPR_TARGET_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage equal to (?P<expr>.+?) to "
    r"(?P<phrase>any target|.*target.+)\.?$",
    re.IGNORECASE,
)
#: The same amount printed after the target instead of before it: "deals
#: damage to any target equal to the number of Shrines you control" (Honden
#: of Infinite Rage), "deals damage to target attacking creature equal to the
#: number of untapped Mountains you control" (Ben-Ben, Akki Hermit), "deals
#: damage to target creature equal to the number of Mountains you control"
#: (Koth, Fire of Resistance). `expr` is read by `amount_expression`, so every
#: count it knows - subtype, card type, tapped/untapped status - reads here.
_DAMAGE_TARGET_EQUAL_TO_EXPR_RE = re.compile(
    rf"^{_UNQUOTED_PREFIX}\bdeals? damage to "
    r"(?P<phrase>any target|[^.]*?\btargets?\b[^.]*?) equal to (?P<expr>[^.]+?)\.?$",
    re.IGNORECASE,
)


#: "divided evenly, rounded down" (Fireball: "Fireball deals X damage
#: divided evenly, rounded down, among any number of targets.") is a second,
#: mutually exclusive splitting method beside "as you choose" - the card
#: dictates the whole division itself, so there is nothing for CR 601.2d to
#: have the caster announce (`Casting.announce_division` is never reachable
#: for this shape: `machines/targeting.py`'s own `Division`/`_read_division`
#: only ever reads the "as you choose" template, so `TargetingProfile.
#: division` stays `None` here and `announce_division` correctly refuses
#: "does not divide anything to announce"). `evenly` records which template
#: matched, so the resolution-time payout (`_deal_divided_damage_shares`)
#: knows to floor-divide with the remainder simply dropped rather than
#: dumped on the first target(s) the way an un-announced "as you choose"
#: falls back.
_DIVIDED_DAMAGE_RE = re.compile(
    rf".*\bdeals? (?P<n>{AMOUNT}) damage divided "
    rf"(?:as you choose|(?P<evenly>evenly, rounded down)),? among "
    rf"(?P<phrase>[^.]+?){where_x_pattern()}\.?$",
    re.IGNORECASE,
)


#: "<Source> deals N damage to each opponent." (Guttersnipe) - CR 119.3, with
#: no target at all: "each opponent" is CR 102.2's "the other player" (in a
#: two-player game), not something chosen.
#: `damage_each_opponent` reads `ability.controller` directly rather than
#: through `Game.controller_of`, for a triggered or activated ability;
#: Dragon's Approach's own "Dragon's Approach deals 3 damage to each
#: opponent." is the spell-side twin, `damage_each_opponent_spell`,
#: which does go through `Game.controller_of(spell)`.
#: `n` reads `AMOUNT`/`where_x_pattern` the same as `_DAMAGE_TARGET_RE` -
#: Scourge of Valkas' variant, "it deals X damage to each opponent, where X
#: is the number of Dragons you control", would otherwise be silent purely
#: for lacking a fixed digit.
_DAMAGE_EACH_OPPONENT_RE = re.compile(
    rf".*\bdeals? (?P<n>{AMOUNT}) damage to each opponent{where_x_pattern()}\.?$", re.IGNORECASE
)
#: "<Source> deals N damage to itself." (CR 119.3, 120.2b) - Goblin
#: Kaboomist's own coin-flip loser. Same `.*\bdeals?` source-agnostic prefix
#: as `_DAMAGE_EACH_OPPONENT_RE` just above, so "this creature", "this
#: token", or a self-named reference (CR 201.5) all read identically.
_DAMAGE_TO_ITSELF_RE = re.compile(
    rf".*\bdeals? (?P<n>{AMOUNT}) damage to itself{where_x_pattern()}\.?$", re.IGNORECASE
)
#: "<Source> deals N damage to you." (CR 119.3, 120.2b) - Mana Crypt's own
#: coin-flip loser. Same source-agnostic prefix as the two patterns above.
_DAMAGE_TO_CONTROLLER_RE = re.compile(
    rf".*\bdeals? (?P<n>{AMOUNT}) damage to you{where_x_pattern()}\.?$", re.IGNORECASE
)
#: "<Source> deals N damage to each player." (Cast Away Doubt) - CR 102.1's
#: whole player set, the caster included - `_DAMAGE_EACH_OPPONENT_RE`'s own
#: CR 102.2 subset with "player" standing in for "opponent".
_DAMAGE_EACH_PLAYER_RE = re.compile(
    rf".*\bdeals? (?P<n>{COUNT}) damage to each player\.?$", re.IGNORECASE
)
#: "<Source> deals N damage to each creature." (Extinguisher Battleship) -
#: CR 119.3, also with no target: "each creature" is every creature on the
#: battlefield, not something chosen or a player group. Same X/where-X
#: widening as `_DAMAGE_EACH_OPPONENT_RE` just above.
_DAMAGE_EACH_CREATURE_RE = re.compile(
    rf".*\bdeals? (?P<n>{AMOUNT}) damage to each creature{where_x_pattern()}\.?$", re.IGNORECASE
)
#: "Prevent all combat damage that would be dealt this turn." (Fog, Angelsong)
#: - CR 615.1a's prevention effect naming neither a permanent nor a player, so
#: the shield protects the whole board; see `prevent_all_combat_damage`.
#: Time Stop's whole text. CR 724.1's procedure lives on `Game.end_the_turn`;
#: this is only the sentence that calls it. Distinct from `_END_THE_TURN_RE`
#: far below, which is Day's Undoing's own *gated* "if it's your turn, end
#: the turn" and reads `end_the_turn_if_your_turn_effect` instead.
_PLAIN_END_THE_TURN_RE = re.compile(r"^end the turn\.?$", re.IGNORECASE)
_PREVENT_ALL_COMBAT_DAMAGE_RE = re.compile(
    r"^prevent all combat damage that would be dealt this turn\.?$", re.IGNORECASE
)
#: Moonmist's shape: the same shield, minus the creature types it names.
#: CR 609.7b makes this a property rechecked when the damage would be dealt,
#: so the excluded types travel to the shield as words - see
#: `PreventionShield.excluded_source_subtypes`.
_PREVENT_ALL_COMBAT_DAMAGE_EXCEPT_RE = re.compile(
    r"^prevent all combat damage that would be dealt this turn by creatures "
    r"other than (?P<except>.+?)\.?$",
    re.IGNORECASE,
)
#: "Prevent the next N damage that would be dealt to any target this turn."
#: (Bandage) - CR 615.7's counting shield around whichever kind of target CR
#: 115.1 hands back; see `prevent_next_damage_to_target`.
_PREVENT_NEXT_DAMAGE_TO_TARGET_RE = re.compile(
    rf"prevent the next (?P<n>{COUNT}) damage that would be dealt to "
    r"(?P<phrase>any target|.*target.+) this turn\.?$",
    re.IGNORECASE,
)
#: "target opponent draws a card" (Thought-Knot Seer's leaves-the-battlefield
#: trigger), "target player <does something>" more generally - the plain
#: player-clause vocabulary `parse_clause_effect` already reads (a life
#: total, a draw, a mill, a scry, ...), run against whichever player this
#: clause names rather than the resolving spell's/ability's own controller.
#: Distinct from `_parse_target_player_mode`, which only ever runs for a
#: modal spell's own mode text and never reaches a triggered ability's plain
#: effect clause the way this one, wired into `_parse_targeted_clause`, does.
_TARGET_PLAYER_OR_OPPONENT_VERB_RE = re.compile(
    r"^target (?P<who>player|opponent) (?P<rest>.+)$", re.IGNORECASE
)
#: CR 119.5's own targeted subjects: "target player's life total becomes
#: `<amount>`" (Magister Sphinx, Vraska, Relic Seeker's -10), "target
#: opponent's life total becomes `<amount>`" (Sorin Markov's -3), and "up to
#: one target player's life total becomes `<amount>`" (Torgaar, Famine
#: Incarnate's own ETB, CR 115.6's optional target). The possessive "'s"
#: is why this cannot reuse `_TARGET_PLAYER_OR_OPPONENT_VERB_RE` just above -
#: that pattern requires a literal space after "player"/"opponent", which
#: "player's"/"opponent's" never has, the identical gap "Exile target
#: player's graveyard" (`_EXILE_TARGET_PLAYERS_GRAVEYARD_RE`) already works
#: around by matching the possessive shape whole instead.
_LIFE_TOTAL_BECOMES_TARGET_RE = re.compile(
    r"^(?P<phrase>target player|target opponent|up to one target player)'s "
    r"life total becomes (?P<amount>.+)$",
    re.IGNORECASE,
)
#: "Each player's life total becomes `<amount>`" (Arbiter of Knollridge's
#: ETB, Biorhythm, Shaman of Forgotten Ways's Formidable activation, Repay
#: in Kind, Worldfire, Sway of the Stars) - CR 102.1's whole player set, no
#: target at all, the identical "no target" shape `_DAMAGE_EACH_PLAYER_RE`
#: above already reads for damage.
_EACH_PLAYERS_LIFE_TOTAL_BECOMES_RE = re.compile(
    r"^each player'?s life total becomes (?P<amount>.+)$", re.IGNORECASE
)
#: "Each player exiles all creature cards from their graveyard, then
#: sacrifices all creatures they control, then puts all cards they exiled
#: this way onto the battlefield." (Living End) - three CR 608.2c instructions
#: joined by "then" inside one sentence, so `_spell_effect_or_notice` matches
#: this against the whole (preamble-stripped) text before `_CLAUSE_SEPARATOR`
#: ever gets to cut it into three fragments on its own "then"s; see
#: `each_player_exiles_sacrifices_and_returns_creatures`.
_EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE = re.compile(
    r"^each player exiles all creature cards from (?:their|his or her) graveyard, "
    r"then sacrifices all creatures they control, then puts all cards they "
    r"exiled this way onto the battlefield\.?$",
    re.IGNORECASE,
)


#: "Target creature gets +N/+N until end of turn." (Giant Growth, Dismember,
#: Mutagenic Growth) and "Target creature gains <keyword> until end of turn."
#: (Assault Strobe) - a continuous effect from a resolving spell (CR 611.2),
#: sublayer 7c or layer 6 (CR 613.4c, CR 613.1f). The combined shape, "gets
#: +N/+N *and gains* <keyword>" (Give In to Violence, Violent Urge), is not
#: this regex's job any more - `split_effect_clauses` cuts it in half on its
#: own "and" separator before this ever runs, so
#: `_merge_continuous_pump_keyword_clauses` below undoes that cut first. Routes
#: to `create_continuous_effect`, which reads the card's real text through
#: `machines/layers.py`'s `parsed_layer_effects` rather than anything
#: hard-coded to these two shapes.
#: Psychotic Fury's own qualifier, "Target **multicolored** creature gains
#: double strike until end of turn." - an adjective sitting between "target"
#: and "creature" the way `_SPELL_QUALIFIER_WORD` already lets a counterspell
#: qualify "spell". `machines/targeting.py`'s `profile_for_text` already
#: reads "target multicolored creature" as a legal, colour-restricted
#: requirement at announcement (CR 601.2c) - this regex only recognises which
#: *shape* of resolution clause the text is, so widening it to admit one
#: qualifying word costs nothing: `create_continuous_effect` still gets its
#: targets from `Game.resolve_card_targets`, the already-validated
#: announcement, never from this match.
#: Echoing Courage's own subject widens this again: "Target creature **and all
#: other creatures with the same name as that creature** get +2/+2 until end of
#: turn." One target (CR 115.1), and then a second, untargeted group defined
#: off it by CR 201.2a's "Two or more objects have the same name if they have
#: at least one name in common". The plural verb "get" comes with the plural
#: subject, so both spellings are admitted.
#:
#: This subject carries a bare " and ", which `split_effect_clauses` cuts in
#: two - so `_parse_mixed_clauses` tries this regex against the whole unsplit
#: text before it splits anything, the same treatment
#: `_parse_choose_name_search_and_exile_whole_text` already gets there.
#:
#: Recognising the shape is all this does. *Which* permanents the buff reaches
#: is `machines/layers.py`'s selector, read off the card's own text by
#: `parsed_layer_effects` - and there is no `same name as that creature`
#: selector there yet, so this text still comes back unreadable from that side.
#:
#: The second alternative is Dauntless Onslaught's own plural CR 115.6 shape:
#: "Up to two target creatures each get +2/+2 until end of turn." - this
#: dispatcher only has to recognise the shape (`create_continuous_effect`
#: reads every legally-resolved target the same way regardless of count, and
#: `machines/layers.py`'s own `_PUMP_RE` is what actually builds one
#: `ContinuousEffect` per target), so admitting the plural subject here costs
#: nothing beyond matching it.
_CONTINUOUS_PUMP_OR_KEYWORD_RE = re.compile(
    r"^(?:target (?:[a-z]+ )?creature"
    r"(?: and all other creatures with the same name as that creature)?"
    rf"|(?:(?:up to |one or )?{AMOUNT}|any number of) target (?:[a-z]+ )?creatures(?: each)?)"
    r" (?:gets? [+-]\d+/[+-]\d+|gains? [a-z ]+) until end of turn\.?$",
    re.IGNORECASE,
)


#: "`<target phrase>` can't be blocked this turn." (CR 509.1b) - Eardrum
#: Rattler's own "Another target creature you control with power 2 or less
#: can't be blocked this turn.": a direct grant with no antecedent, unlike
#: `_RIDER_CANT_BE_BLOCKED_RE`'s anaphoric "It can't be blocked this turn."
#: after a different sentence. `phrase` is read the same way every other
#: targeted clause's own phrase is, through `_targets_understood` -
#: `machines/targeting.py` already reads "with power N or less" as CR
#: 115.1's own comparison restriction, so this never has to.
#: `exception_keyword` ("... except by creatures with `<keyword>`", Speed,
#: Young Avenger's own rider) grants the exception verbatim onto the target -
#: `machines/combat.py`'s `evasion_restriction_refusal` reads a "can't be
#: blocked except by creatures with `<keyword>`" sentence for exactly this
#: shape (CR 509.1b's restriction with its own "unless" shape folded on),
#: refusing a blocker without the named keyword and letting one with it
#: through.
_TARGET_CANT_BE_BLOCKED_RE = re.compile(
    r"^(?P<phrase>(?:another )?target .+) can'?t be blocked this turn"
    r"(?: except by creatures with (?P<exception_keyword>[a-z][a-z ]*?))?\.?$",
    re.IGNORECASE,
)

#: "`<target phrase>` can't block this turn." (CR 509.1b) - Hawkeye, Master
#: Marksman's own "Net" mode: "Target creature can't block this turn.", and
#: Maulfist Doorbuster's and Frenzied Goblin's own paid consequence. The
#: mirror restriction of `_TARGET_CANT_BE_BLOCKED_RE` just above - denying a
#: block rather than granting evasion from one - granted the same way: as the
#: self line "This creature can't block." that `machines/combat.py`'s own
#: blocker restriction already reads, for the rest of the turn.
_TARGET_CANT_BLOCK_RE = re.compile(
    r"^(?P<phrase>(?:another )?target .+?) can'?t (?P<what>attack or block|attack|block) "
    r"(?P<duration>this turn|until your next turn)\.?$",
    re.IGNORECASE,
)

#: "`<target phrase>` phases out." (CR 702.26b) - Teferi, Master of Time's
#: "Target creature you don't control phases out.", Haystack's "Target
#: creature you control phases out.". The restriction is whatever
#: `machines/targeting.py` reads off the phrase; the reminder text
#: ("(Treat it and anything attached to it ...)") is stripped before this
#: sees the clause. A leading "up to X"/"up to N" count (March of Swirling
#: Mist's "Up to X target creatures phase out.") rides on the phrase, which
#: `machines/targeting.py` reads in full.
_TARGET_PHASES_OUT_RE = re.compile(
    r"^(?P<phrase>(?:up to \w+ )?(?:another )?target .+?) phases? out\.?$", re.IGNORECASE
)

#: "`<target phrase>` gains `<keyword>`[, `<keyword>`, and `<keyword>`] until
#: end of turn." (CR 613.1f) - a direct grant over an arbitrary target
#: phrase `machines/targeting.py` already reads in full (a comparison, a
#: counter qualifier, a compound type list), rather than the much narrower
#: `_SUBJECT` pattern `machines/layers.py`'s own generalised shapes are
#: built on. Tomik, Orzhov Lawmage's own "Target creature with a +1/+1
#: counter on it gains flying until end of turn." is the reported shape;
#: `_SUBJECT` was never meant to grow a full comparison/counter grammar
#: just to match it.
_TARGET_GAINS_KEYWORDS_RE = re.compile(
    r"^(?P<phrase>(?:another )?target .+?) gains? "
    r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*| and )[a-z]+(?: [a-z]+)?)*) until end of turn\.?$",
    re.IGNORECASE,
)


def _parse_targeted_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a targeted effect, or `None` if this wave does not cover
    its shape or cannot confidently read its restriction.

    `for_spell` only changes which damage builder is used: `deal_damage`
    names the resolving spell as the source, `damage_ability_targets` names
    the permanent an ability came from - the same distinction those two
    existing functions already draw (CR 120.2b), not a new one made here.
    """
    clause = clause.strip()

    if match := _YOU_MAY_RE.match(clause):
        inner_text = match.group("clause").strip()
        inner = _parse_targeted_clause(inner_text, for_spell=for_spell)
        if inner is None:
            return None
        return _optional_targeted_clause(inner, inner_text, for_spell=for_spell)

    if for_spell and _CONTINUOUS_PUMP_OR_KEYWORD_RE.fullmatch(clause):
        # A continuous effect from a resolving spell (CR 611.2) - handing the
        # whole spell to `create_continuous_effect` rather than building
        # anything here, so the actual pump/keyword comes from
        # `machines/layers.py`'s `parsed_layer_effects` reading the card's own
        # text, not from this regex match. Ability-side text ("this creature
        # gets ...") is not read here: it reaches the same parser through
        # `create_continuous_effect_of_ability` instead, keyed by ability
        # index rather than a clause shape.
        return create_continuous_effect  # type: ignore[return-value]

    if not for_spell:
        move_counter = _parse_move_counter_clause(clause)
        if move_counter is not None:
            # SOS's Tester of the Tangential: reached here (not only through
            # `_ability_effect_or_notice`'s own whole-text dispatch) so that
            # `reflexive_consequence_effect`'s `parse_mixed_effect` call - the
            # only reader a CR 603.12 reflexive ability's own text goes
            # through at resolution - can read a "move ... counters"
            # consequence too, not only a directly-printed one (Diamond
            # City's non-reflexive "Move a shield counter ...").
            return move_counter

    if match := _TARGET_CANT_BE_BLOCKED_RE.fullmatch(clause):
        # CR 509.1b's evasion restriction, granted directly rather than as
        # the anaphoric rider `_RIDER_CANT_BE_BLOCKED_RE` reads after a
        # different antecedent - Eardrum Rattler's whole activated ability
        # is this one sentence, with no antecedent in front of it at all.
        exception_keyword = match.group("exception_keyword")
        if exception_keyword is not None:
            exception_keyword = exception_keyword.strip().lower()
            if combat_rules.block_exception_keyword(exception_keyword) is None:
                # Not one of `combat.Keyword`'s closed vocabulary - unread,
                # so this clause stays unmatched rather than granting an
                # exception `evasion_restriction_refusal` cannot enforce.
                return None
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        granted_text = (
            f"This creature can't be blocked except by creatures with {exception_keyword}."
            if exception_keyword is not None
            else "This creature can't be blocked."
        )

        def cant_be_blocked_targets(game: "Game", stack_object: "StackObject") -> None:
            effects = game.continuous_effects
            for target in game.resolve_targets(stack_object):
                if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                    continue
                effects.add(
                    ContinuousEffect(
                        description=f"{target.name} can't be blocked this turn",
                        layer=Layer.ABILITY,
                        timestamp=effects.tick(),
                        duration=Duration.UNTIL_END_OF_TURN,
                        selector=only_this_incarnation(target, target.zone_change_stamp),
                        modification=grant_ability(granted_text),
                    )
                )

        return cant_be_blocked_targets

    if match := _TARGET_CANT_BLOCK_RE.fullmatch(clause):
        # CR 509.1b's mirror restriction - see `_TARGET_CANT_BLOCK_RE`'s own
        # banner.
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None

        # "can't attack" (CR 508.1c) as well as "can't block" (CR 509.1b),
        # each granted as the self line `machines/combat.py` reads, "this
        # turn" or "until your next turn" (CR 611.2a, Tomb of the Mad Mage's
        # Twisted Caverns: "Target creature can't attack until your next
        # turn.").
        what = match.group("what").lower()
        granted = [f"This creature can't {verb}." for verb in ("attack", "block") if verb in what]
        until_next_turn = match.group("duration").lower() == "until your next turn"

        def cant_block_targets(game: "Game", stack_object: "StackObject") -> None:
            effects = game.continuous_effects
            controller = game.controller_of(stack_object).username
            for target in game.resolve_targets(stack_object):
                if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                    continue
                for text in granted:
                    effects.add(
                        ContinuousEffect(
                            description=f"{target.name}: {text[len('This creature ') :]}",
                            layer=Layer.ABILITY,
                            timestamp=effects.tick(),
                            duration=(
                                Duration.UNTIL_YOUR_NEXT_TURN
                                if until_next_turn
                                else Duration.UNTIL_END_OF_TURN
                            ),
                            until_next_turn_of=controller if until_next_turn else None,
                            selector=only_this_incarnation(target, target.zone_change_stamp),
                            modification=grant_ability(text),
                        )
                    )

        return cant_block_targets

    if match := _TARGET_PHASES_OUT_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None

        def phase_out_targets(game: "Game", stack_object: "StackObject") -> None:
            # CR 608.2b: an illegal target is simply not affected; a legal
            # one phases out with whatever is attached to it (CR 702.26g).
            for target in game.resolve_targets(stack_object):
                if isinstance(target, CardState):
                    game.phase_out(target)

        return phase_out_targets

    if match := _TARGET_GAINS_KEYWORDS_RE.fullmatch(clause):
        phrase = match.group("phrase")
        if re.search(r"\bgets?\b", phrase, re.IGNORECASE):
            # `_targets_understood` tolerates a trailing tail it does not
            # read (it is meant to, for an ordinary target scan) - which
            # would otherwise let this shape's own non-greedy `phrase` steal
            # "Target creature gets +2/+2 and gains reach until end of
            # turn." away from the compound pump-and-keyword sentence it
            # actually is, reading only the keyword half and silently
            # dropping the pump. A genuine target phrase for this shape
            # never itself contains a pump verb.
            return None
        if not _targets_understood(phrase, count_agnostic=True):
            return None
        keywords = split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None

        def gains_keywords_targets(game: "Game", stack_object: "StackObject") -> None:
            effects = game.continuous_effects
            for target in game.resolve_targets(stack_object):
                if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                    continue
                for keyword in keywords:
                    effects.add(
                        ContinuousEffect(
                            description=f"{target.name} gains {keyword}",
                            layer=Layer.ABILITY,
                            timestamp=effects.tick(),
                            duration=Duration.UNTIL_END_OF_TURN,
                            selector=only_this_incarnation(target, target.zone_change_stamp),
                            modification=grant_ability(keyword),
                        )
                    )

        return gains_keywords_targets

    if spell_counter := _COUNTER_TARGET_SPELL_RE.fullmatch(clause):
        # CR 701.6a on a targeted spell, from a spell or from an ability
        # (Spellstutter Sprite's enters trigger): `counter_targets` reads only
        # `targets` and the stack, both of which an `AbilityOnStack` carries.
        # A "where X is" bound nobody can count would refuse every target at
        # announcement, so it is refused here instead of reading as handled.
        definition = spell_counter.group("where_x")
        if definition is not None and count_expression(definition) is None:
            return None
        return counter_targets

    if _COUNTER_TARGET_ABILITY_OR_SPELL_RE.fullmatch(
        clause
    ) or _COUNTER_TARGET_ABILITY_RE.fullmatch(clause):
        # CR 113.9: abilities "can be countered by spells and abilities that
        # specifically counter abilities". `counter_targets` reads only
        # `targets` and the stack, which an `AbilityOnStack` carries too, so
        # Rimewind Cryomancer's and Azorius Guildmage's activated "Counter
        # target activated ability." reach it the way Repudiate does.
        return counter_targets

    if match := _COUNTER_UNLESS_PAYS_RE.fullmatch(clause):
        return _counter_unless_pays_effect(int(match.group("n"))) if for_spell else None

    if (
        for_spell
        and (phrase_match := _COUNTER_UNLESS_PAYS_PHRASE_RE.fullmatch(clause))
        and _targets_understood(phrase_match.group("phrase"))
    ):
        return _counter_unless_pays_effect(int(phrase_match.group("n")))

    if (
        they_pay_match := _COUNTER_UNLESS_THEY_PAY_PHRASE_RE.fullmatch(clause)
    ) and _targets_understood(they_pay_match.group("phrase"), battlefield_only=False):
        return _counter_unless_pays_effect(int(they_pay_match.group("n")))

    counter_if_mana_value = _parse_counter_if_mana_value_clause(clause, for_spell=for_spell)
    if counter_if_mana_value is not None:
        return counter_if_mana_value

    if (
        (phrase_match := _COUNTER_TARGET_PHRASE_RE.fullmatch(clause))
        # CR 118.12a: an "unless ..." cost none of the readers above took
        # (Syncopate's "{X}" before X is announced) is never an unconditional
        # counter - `_targets_understood` would tolerate it as a tail.
        and not re.search(r"\bunless\b", clause, re.IGNORECASE)
        and _targets_understood(phrase_match.group("phrase"), battlefield_only=False)
    ):
        # Fugitive Droid: "Counter target spell that targets an artifact or
        # creature you control." Siren Stormtamer: "Counter target spell or
        # ability that targets you or a creature you control." Neither
        # matches `_COUNTER_TARGET_SPELL_RE`'s own qualifier/predicate slots
        # (`_SPELL_PREDICATE` only ever reads a trailing "with `<comparison>`
        # ..."), because the restriction is not on the spell's own printed
        # characteristics at all - it is on what *that spell itself targets*
        # (CR 601.2c), which `machines/targeting.py`'s own `must_target_you`/
        # `must_target_types` fields (widened this task) already enforce at
        # announcement and at the CR 608.2b recheck. `counter_targets` needs
        # nothing new beyond a legal target to have been chosen at all.
        # Tried dead last among every "Counter target ..." shape, after every
        # more specific one (including the "unless"/mana-value variants just
        # above) has already declined - `_targets_understood` tolerates a
        # trailing tail it does not itself read (see its own docstring), so
        # tried any earlier it would misread an "unless ..." cost clause as
        # an unconditional counter and silently drop the cost, exactly the
        # regression a real playtest would call a bug. `battlefield_only=
        # False`: a spell target lives on the stack, never the battlefield
        # (CR 112.1, CR 110.1).
        return counter_targets

    if match := _DESTROY_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return destroy_ability_targets

    if match := _BECOMES_PREPARED_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return become_prepared_ability_targets  # type: ignore[return-value]

    becomes_unprepared = _parse_becomes_unprepared_target_clause(clause)
    if becomes_unprepared is not None:
        return becomes_unprepared

    # Ahead of `_EXILE_TARGET_PLAYERS_GRAVEYARD_RE`/`_EXILE_TARGET_RE` for the
    # same reason that one is ahead of `_EXILE_TARGET_RE`: "target player's
    # hand and graveyard" would otherwise be committed to a player-blind read.
    exile_hands_and_graveyards = _parse_exile_all_cards_from_hands_and_graveyards_clause(clause)
    if exile_hands_and_graveyards is not None:
        return exile_hands_and_graveyards

    if match := _EXILE_TARGET_PLAYERS_GRAVEYARD_RE.fullmatch(clause):
        # Ahead of `_EXILE_TARGET_RE`: that pattern's phrase is a superset of
        # this one's and would otherwise commit first, read the player target
        # with `allow_player_targets` left `False`, and refuse the clause.
        if not _targets_understood(
            match.group("phrase"), allow_player_targets=True, count_agnostic=True
        ):
            return None
        return exile_target_players_graveyard

    if _EXILE_ALL_GRAVEYARDS_RE.fullmatch(clause):
        return exile_all_graveyards  # type: ignore[return-value]

    if _EXILE_EACH_OPPONENTS_GRAVEYARD_RE.fullmatch(clause):
        return exile_each_opponents_graveyard  # type: ignore[return-value]

    exile_all_but_bottom = _parse_exile_all_but_bottom_of_library_clause(
        clause, for_spell=for_spell
    )
    if exile_all_but_bottom is not None:
        return exile_all_but_bottom

    exile_library_end = _parse_exile_from_own_library_end_clause(clause)
    if exile_library_end is not None:
        return exile_library_end

    if match := _EXILE_QUALITY_FROM_ALL_GRAVEYARDS_RE.fullmatch(clause):
        matches = _graveyard_exile_quality_matcher(match.group("quality"))
        if matches is None:
            return None
        return _exile_matching_from_all_graveyards(matches)

    exile_until_leaves = _parse_exile_until_leaves_battlefield_clause(clause, for_spell=for_spell)
    if exile_until_leaves is not None:
        return exile_until_leaves

    if match := _EXILE_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return exile_ability_targets

    if match := _PUT_TARGET_FROM_GRAVEYARD_BOTTOM_OF_LIBRARY_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return put_ability_targets_on_bottom_of_owners_library

    if match := _PUT_TARGET_FROM_GRAVEYARD_TOP_OF_LIBRARY_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return put_ability_targets_on_top_of_owners_library

    if match := _PUT_TARGET_PERMANENT_TOP_OF_OWNERS_LIBRARY_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return put_ability_targets_on_top_of_owners_library

    if match := _RETURN_FROM_YOUR_GRAVEYARD_TO_HAND_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return return_ability_targets_to_hand

    put_onto_battlefield = _parse_put_from_graveyard_onto_battlefield_clause(clause)
    if put_onto_battlefield is not None:
        return put_onto_battlefield

    if match := _RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_WITH_COUNTER_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        counter_amount = parse_count(match.group("counter_n")) if match.group("counter_n") else 1
        if counter_amount is None:
            return None
        return _return_ability_targets_to_battlefield_with_counter(
            bool(match.group("tapped")), match.group("counter"), counter_amount
        )

    if match := _RETURN_FROM_YOUR_GRAVEYARD_TO_BATTLEFIELD_RE.fullmatch(clause):
        phrase = match.group("phrase") + (match.group("where_x") or "")
        if not _targets_understood(phrase, count_agnostic=True, battlefield_only=False):
            return None
        if match.group("tapped"):
            return _return_ability_targets_to_battlefield_with_counter(True)
        return return_ability_targets_to_battlefield

    if match := _RETURN_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, battlefield_only=False
        ):
            return None
        return return_ability_targets_to_hand

    if match := _GRAVEYARD_TO_BOTTOM_OF_LIBRARY_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, allow_player_targets=True
        ):
            return None
        return puts_graveyard_on_bottom_of_library

    owner_puts_it_into_library = _parse_owner_puts_it_into_library_clause(
        clause, for_spell=for_spell
    )
    if owner_puts_it_into_library is not None:
        return owner_puts_it_into_library

    if match := _REMOVE_FROM_COMBAT_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return (
            remove_ability_targets_from_combat_and_untap
            if match.group("untap")
            else remove_ability_targets_from_combat
        )

    if match := _UNTAP_AND_REMOVE_FROM_COMBAT_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return remove_ability_targets_from_combat_and_untap

    if match := _TAP_UNTAP_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return (
            tap_ability_targets if match.group("verb").lower() == "tap" else untap_ability_targets
        )

    if match := _REGENERATE_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        return regenerate_ability_targets  # type: ignore[return-value]

    by_spells_mana_value = _parse_put_counters_on_target_by_that_spells_mana_value_clause(
        clause, for_spell=for_spell
    )
    if by_spells_mana_value is not None:
        return by_spells_mana_value

    if match := _COUNTER_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), count_agnostic=True):
            return None
        amount = parse_count(match.group("n"))
        kind = _counter_kind(match.group("kind"))
        each_text = match.group("each")
        if each_text is None:
            return put_counters_on_ability_targets(kind, amount)
        multiplier = count_expression(each_text)
        if multiplier is None:
            # Fails closed rather than placing the bare per-instance amount:
            # an unread "for each" is a wrong count, not a missing one.
            return None
        return put_counters_on_ability_targets(kind, amount, multiplier)

    if not for_spell and (match := _SELF_DEALS_DAMAGE_EQUAL_TO_ITS_STAT_RE.fullmatch(clause)):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        return _self_deals_damage_equal_to_its_stat(match.group("stat").lower())

    if not for_spell and (
        lose_life_equal_to_sacrificed
        := _parse_target_player_loses_life_equal_to_sacrificed_creature_clause(clause)
    ):
        return lose_life_equal_to_sacrificed

    if for_spell and (match := _DAMAGE_EQUAL_TO_SACRIFICED_CREATURE_POWER_RE.fullmatch(clause)):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        return _deal_damage_equal_to_sacrificed_creature_power

    if (
        for_spell
        and (match := _DAMAGE_EQUAL_TO_EXPR_TARGET_RE.fullmatch(clause))
        # "its power"/"its loyalty" is Compel Brutality's/Aggressive
        # Instinct's own bite-family shape (`_parse_bite_damage_clause`),
        # which threads the *referent's own* power through as the subject
        # of the whole sentence, not the resolving spell's own X or a
        # game-wide count - `amount_expression`'s object-characteristic term
        # would silently read 0 for it here (no live object to ask), so this
        # reader steps aside for that shape entirely rather than shadowing
        # the one built for it.
        and _OBJECT_CHARACTERISTIC_RE.fullmatch(match.group("expr").strip()) is None
    ):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        reader = amount_expression(match.group("expr"))
        if reader is None:
            return None
        return deal_damage_equal_to_expression(reader)

    if (
        not for_spell
        and (match := _DAMAGE_EQUAL_TO_EXPR_TARGET_RE.fullmatch(clause))
        and (counted := _NUMBER_OF_COUNTERS_ON_IT_RE.fullmatch(match.group("expr").strip()))
    ):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        counter_reader = _for_each_multiplier(counted.group("counters"))
        if counter_reader is None:
            return None
        return _damage_ability_targets_equal_to(counter_reader)

    if (
        not for_spell
        and (match := _DAMAGE_EQUAL_TO_EXPR_TARGET_RE.fullmatch(clause))
        # Stepping aside for the counters-on-it shape just above and the
        # bite-family "its power"/"its loyalty" one (`_OBJECT_CHARACTERISTIC_
        # RE`, no live object bound to "obj" the way that reader's own
        # subject is) - matched, not merely excluded, so falling through to
        # try `_parse_self_damage_equal_to_count_clause` and every other
        # reader below is exactly what an unmatched `expr` should do, the
        # same "and reader is not None" chaining `_DAMAGE_TARGET_EQUAL_TO_
        # EXPR_RE`'s own sibling block just below already uses rather than
        # this file's other "matched the regex, now commit or refuse" shape.
        and _NUMBER_OF_COUNTERS_ON_IT_RE.fullmatch(match.group("expr").strip()) is None
        and _OBJECT_CHARACTERISTIC_RE.fullmatch(match.group("expr").strip()) is None
        and (reader := amount_expression(match.group("expr"))) is not None
        and _targets_understood(match.group("phrase"), allow_player_targets=True)
    ):
        # Stadium Headliner's own "It deals damage equal to the number of
        # creatures you control to target creature." - the ability-side twin
        # of the spell branch's general `amount_expression` read, widened
        # past the counters-on-it special case: any game-wide count
        # (`count_expression`'s own "creatures you control", "Mountains you
        # control", ...) that `amount_expression` already reads for a spell
        # now reads for an activated or triggered ability too.
        return damage_ability_targets_equal_to_expression(reader)

    if (
        (match := _DAMAGE_TARGET_EQUAL_TO_EXPR_RE.fullmatch(clause))
        and (reader := amount_expression(match.group("expr"))) is not None
        and _targets_understood(match.group("phrase"), allow_player_targets=True)
    ):
        if for_spell:
            return deal_damage_equal_to_expression(reader)
        return damage_ability_targets_equal_to_expression(reader)

    if match := _DAMAGE_TARGET_RE.fullmatch(clause):
        # CR 601.2d's division is triggered only by the card's own printed
        # word "divided" - `_DIVIDED_DAMAGE_RE` reads that shape, and this
        # regex never matches text carrying it (there is no literal "to"
        # right after "damage" in "damage divided as you choose among").
        # Absent that word, "up to one target creature" (Mjolnir) and "each
        # of up to two target creatures" (Dual Shot) are CR 115.6's ordinary
        # optional targets: every target actually chosen takes the *whole*
        # printed amount, which is exactly what `deal_damage`/
        # `damage_ability_targets`'s per-target loop already does - so this
        # is `count_agnostic` after all, unlike the docstring above used to
        # claim, once "divided" is what actually decides the mechanism.
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, allow_player_targets=True
        ):
            return None
        each = match.group("each")
        where_x = match.group("where_x")
        if each is None and where_x is None:
            amount = parse_count(match.group("n"))
            return deal_damage(amount) if for_spell else damage_ability_targets(amount)
        amount_fn = _resolve_multiplied_amount(match.group("n"), each, where_x)
        if amount_fn is None:
            return None
        return _deal_damage_for_each(amount_fn, for_spell=for_spell)

    if for_spell and _DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE.fullmatch(clause):
        # `game.cast_record` (the plain-X reading below) is a spell-only
        # concept, and no ability in the pool prints this shape - narrowed
        # to `for_spell` rather than promising support this has no card to
        # prove. Tried before the generic `_DIVIDED_DAMAGE_RE` below - see
        # `_DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE`'s own
        # docstring for why the order matters.
        return _parse_divided_damage_among_target_players_creatures_clause(clause)

    if match := _DIVIDED_DAMAGE_RE.fullmatch(clause):
        # Unlike `_DAMAGE_TARGET_RE`, this phrase genuinely can carry a
        # printed restriction (Ureni's "target creatures and/or
        # planeswalkers your opponents control"), so it is vetted the same
        # way every other targeted clause's phrase is - a bare CR 115.4
        # "targets" with no noun after it reads as the ordinary any-target
        # requirement `_read_phrase` already gives one.
        if not _targets_understood(
            match.group("phrase"), count_agnostic=True, allow_player_targets=True
        ):
            return None
        where_x = match.group("where_x")
        n = match.group("n")
        even_split = match.group("evenly") is not None
        if n.lower() == "x":
            if where_x is not None:
                multiplier = count_expression(where_x)
                if multiplier is None:
                    return None
                return _deal_divided_damage_for_expression(  # type: ignore[return-value]
                    multiplier, even_split=even_split
                )
            # No "where X is ..." definition at all: CR 107.3's plain,
            # caster-announced X (Fireball) - the same shape Shatterskull
            # Smashing's own separate parser already reads off `x_value`,
            # generalised into this dispatch rather than left a one-card
            # special case now that a second real printing needs it too.
            return _deal_x_divided_damage(even_split=even_split)  # type: ignore[return-value]
        amount = parse_count(n)
        return deal_divided_damage(amount, even_split=even_split)  # type: ignore[return-value]

    if match := _DAMAGE_EACH_OPPONENT_RE.fullmatch(clause):
        # No target at all (CR 102.2's "each opponent"), so nothing to check
        # through `_targets_understood`. The plain-amount reading serves a
        # spell too (`damage_each_opponent_spell`, Dragon's Approach's own
        # "Dragon's Approach deals 3 damage to each opponent."); the
        # dynamic "where X is ..." reading (Scourge of Valkas) stays
        # ability-only - `_damage_each_opponent_for_expression` reads
        # `AbilityOnStack.controller` directly, and no spell in the pool
        # prints this shape with a variable count to give it a spell-side
        # twin for yet.
        where_x = match.group("where_x")
        if where_x is None:
            amount = parse_count(match.group("n"))
            if for_spell:
                return damage_each_opponent_spell(amount)  # type: ignore[return-value]
            return damage_each_opponent(amount)  # type: ignore[return-value]
        if for_spell:
            return None
        amount_fn = _resolve_multiplied_amount(match.group("n"), None, where_x)
        if amount_fn is None:
            return None
        return _damage_each_opponent_for_expression(amount_fn)  # type: ignore[return-value]

    if match := _DAMAGE_TO_ITSELF_RE.fullmatch(clause):
        # No target either (CR 120.2b's own source, not something chosen),
        # and ability-only for the same reason `_DAMAGE_EACH_OPPONENT_RE` is:
        # `damage_to_itself` reads `AbilityOnStack.source`.
        if for_spell:
            return None
        where_x = match.group("where_x")
        if where_x is not None:
            return None  # no printing in the pool needs a variable self-damage count yet
        amount = parse_count(match.group("n"))
        return damage_to_itself(amount)  # type: ignore[return-value]

    if match := _DAMAGE_TO_CONTROLLER_RE.fullmatch(clause):
        # Ability-only, same reason: `damage_to_controller` reads
        # `AbilityOnStack.controller`.
        if for_spell:
            return None
        where_x = match.group("where_x")
        if where_x is not None:
            return None  # no printing in the pool needs a variable count here yet
        amount = parse_count(match.group("n"))
        return damage_to_controller(amount)  # type: ignore[return-value]

    if match := _DAMAGE_EACH_PLAYER_RE.fullmatch(clause):
        # No target either (CR 102.1's whole player set).
        amount = parse_count(match.group("n"))
        if for_spell:
            return damage_each_player_spell(amount)
        return damage_each_player(amount)  # type: ignore[return-value]

    if match := _DAMAGE_EACH_CREATURE_RE.fullmatch(clause):
        # No target either (every creature on the battlefield, CR 119.3).
        where_x = match.group("where_x")
        if where_x is None:
            amount = parse_count(match.group("n"))
            if for_spell:
                return damage_each_creature_spell(amount)
            return damage_each_creature(amount)  # type: ignore[return-value]
        amount_fn = _resolve_multiplied_amount(match.group("n"), None, where_x)
        if amount_fn is None:
            return None
        return _damage_each_creature_for_expression(amount_fn, for_spell=for_spell)

    if _PLAIN_END_THE_TURN_RE.fullmatch(clause):
        return end_the_turn_effect  # type: ignore[return-value]

    if _END_THE_TURN_RE.fullmatch(clause.strip().rstrip(".")):
        return end_the_turn_if_your_turn_effect

    if _PREVENT_ALL_COMBAT_DAMAGE_RE.fullmatch(clause):
        return prevent_all_combat_damage  # type: ignore[return-value]

    if match := _PREVENT_ALL_COMBAT_DAMAGE_EXCEPT_RE.fullmatch(clause):
        excluded = _subtypes_in(match.group("except"))
        if not excluded:
            return None
        return prevent_all_combat_damage_except(excluded)  # type: ignore[return-value]

    if match := _PREVENT_NEXT_DAMAGE_TO_TARGET_RE.fullmatch(clause):
        if not _targets_understood(match.group("phrase"), allow_player_targets=True):
            return None
        amount = parse_count(match.group("n"))
        return prevent_next_damage_to_target(amount)  # type: ignore[return-value]

    if match := _TARGET_PLAYER_OR_OPPONENT_VERB_RE.fullmatch(clause):
        if not _targets_understood(f"target {match.group('who')}", allow_player_targets=True):
            return None
        rest = match.group("rest").strip()
        clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
        if clause_effect is None:
            return None

        def player_verb_effect(game: "Game", stack_object: "StackObject") -> None:
            source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
            for target in game.resolve_targets(stack_object):
                if isinstance(target, Player):
                    clause_effect(game, target, source, source_id_of(stack_object))

        return player_verb_effect

    if match := _LIFE_TOTAL_BECOMES_TARGET_RE.fullmatch(clause):
        if not _targets_understood(
            match.group("phrase"), allow_player_targets=True, count_agnostic=True
        ):
            return None
        amount_reader = _life_total_becomes_amount_reader(match.group("amount"))
        if amount_reader is None:
            return None

        def target_life_total_becomes(game: "Game", stack_object: "StackObject") -> None:
            for target in game.resolve_targets(stack_object):
                if isinstance(target, Player):
                    new_total = amount_reader(game, target.username, None, 0)
                    game.set_life_total(target, new_total)

        return target_life_total_becomes

    if match := _EACH_PLAYERS_LIFE_TOTAL_BECOMES_RE.fullmatch(clause):
        amount_reader = _life_total_becomes_amount_reader(match.group("amount"))
        if amount_reader is None:
            return None

        def each_player_life_total_becomes(game: "Game", stack_object: "StackObject") -> None:
            # CR 119.5's own set applies to every player "at once" in
            # effect: each player's new total is read off the board as it
            # stood before this instruction touched anyone, then every
            # total is set - never one player's already-adjusted total
            # feeding the next player's own count (irrelevant for "the
            # number of creatures they control", but load-bearing for "the
            # highest/lowest life total among all players").
            new_totals = {
                player.username: amount_reader(game, player.username, None, 0)
                for player in game.players_in_game
            }
            for username, new_total in new_totals.items():
                game.set_life_total(username, new_total)

        return each_player_life_total_becomes

    return None


def _parse_targeted_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every clause of a targeted effect, or `None` the moment one fails.

    Fail-closed for the same reason `_parse_player_clauses` is (CR 608.2c has
    no notion of running half an effect): a multi-clause card with one clause
    this wave does not cover - Assassin's Trophy's compensation, Fatal Push's
    Revolt line - throws away every clause around it too, rather than destroy
    or exile something and silently skip the rest of the sentence.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed = [_parse_targeted_clause(clause, for_spell=for_spell) for clause in clauses]
    if any(effect is None for effect in parsed):
        return None
    return parsed  # type: ignore[return-value]


def parse_targeted_effect_for_spell(text: str) -> Effect | None:
    """A spell whose whole effect is one or more of this wave's targeted
    shapes, read off the card's own printed text instead of a per-card row -
    Bone Splinters, Utter End, Lightning Bolt.
    """
    clauses = _parse_targeted_clauses(text, for_spell=True)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for clause in clauses:
            clause(game, spell)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def parse_targeted_effect(text: str) -> AbilityEffect | None:
    """The same, for a triggered or activated ability's own printed text -
    Ravenous Chupacabra, Aether Adept, Icy Manipulator, Kiora's Follower,
    Anafenza, the Foremost.
    """
    clauses = _parse_targeted_clauses(text, for_spell=False)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for clause in clauses:
            clause(game, ability)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: Craterous Stomp's own shape: "<Name> deals N damage to target creature an
#: opponent controls. Each other creature that player controls becomes a
#: `<type>` in addition to its other types and gains \"`<ability text>`.\""
#: `_ANAPHORIC_SUBJECT_RE`/`_unreadable_anaphoric_clause` only recognise "that
#: player"/"its controller" as the *whole* subject of the second sentence
#: (Solitude's "That creature's controller gains life...") - here the
#: back-reference sits mid-clause ("each other creature *that player*
#: controls"), CR 400.7's same anaphora in a shape neither regex reads, so
#: the pair never even reached the notice path and the whole two-sentence
#: instruction (damage included) was silently doing nothing. Read whole,
#: ahead of `parse_mixed_effect_for_spell`: recognising the templated shape
#: is enough to record a proper `AnaphoricClauseNotice` instead. Building the
#: effect for real needs two things this engine does not have anywhere else -
#: a *group* continuous type-and-ability grant fixed off an anaphoric
#: referent's controller (CR 611.2c), and blocking-restriction enforcement
#: for a granted "can't block `<creature type>`" ability
#: (`machines/combat.py` only reads a printed attacker-side "can't be
#: blocked by ..." restriction today, see `test_evasion_restrictions.py`) -
#: so this fails the whole paragraph closed (CR 608.2c: no notion of running
#: half an instruction; the damage does not fire either) rather than
#: half-execute the damage alone. See `docs/engine-coverage.md`.
_DAMAGE_THEN_GROUP_TYPE_ABILITY_GRANT_RE = re.compile(
    r"^.*\bdeals? \d+ damage to target creature an opponent controls\.\s*"
    r"each other creature that player controls becomes an? [a-z]+ in addition to its "
    r'other types and gains "[^"]+\."\.?$',
    re.IGNORECASE | re.DOTALL,
)


#: "You may cast target <quality> card from your graveyard this turn. [If
#: that spell would be put into your graveyard, exile it instead.]" - Jace,
#: Telepath Unbound's -3 and Vohar, Vodalian Desecrator's sacrifice ability.
#: CR 601.3's permission handed to one targeted card for the rest of the turn
#: (CR 611.2a), with CR 614.1a's replacement riding on "that spell" - the
#: object the card becomes as it is cast this way (CR 400.7h), which is why
#: the rider is carried on the permission (`PlayPermission.exile_instead_of_
#: graveyard`) rather than on the card.
_CAST_TARGET_CARD_FROM_GRAVEYARD_RE = re.compile(
    r"^you may cast (?P<phrase>target .+? card) from your graveyard this turn\.\s*"
    r"(?P<rider>if that spell would be put into (?:your|a) graveyard, exile it instead\.?)?$",
    re.IGNORECASE,
)


def _parse_cast_target_card_from_graveyard_clause(text: str) -> TargetedClause | None:
    """`_CAST_TARGET_CARD_FROM_GRAVEYARD_RE`'s shape.

    The target is rechecked as the ability resolves (CR 608.2b); a card that
    has left the graveyard since is a new object and is handed nothing.
    """
    match = _CAST_TARGET_CARD_FROM_GRAVEYARD_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    phrase = f"{match.group('phrase')} from your graveyard"
    if not _targets_understood(phrase, battlefield_only=False):
        return None
    exile_instead = match.group("rider") is not None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                game.grant_play_permission(
                    target,
                    controller,
                    action=PlayAction.CAST,
                    pays_mana_cost=True,
                    source_name=source_name,
                    zone=Zone.GRAVEYARD,
                    rule="CR 601.3",
                    exile_instead_of_graveyard=exile_instead,
                )

    return effect


#: "the sacrificed creature's mana value" - Neoform's and Eldritch
#: Evolution's own right-hand side. See `AnaphoricClauseNotice` for why this
#: is recorded rather than performed: the spell has no record of what its own
#: CR 118.8a additional cost sacrificed.
_SACRIFICED_COST_REFERENCE_RE = re.compile(
    r"\bthe sacrificed (?:creature|permanent|artifact)'?s (?:mana value|power|toughness)\b",
    re.IGNORECASE,
)


def _unreadable_cost_reference_clause(text: str) -> str | None:
    """The clause of `text` that reads back a value off an object the spell's
    own additional cost consumed, if there is one - see
    `_SACRIFICED_COST_REFERENCE_RE`."""
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _SACRIFICED_COST_REFERENCE_RE.search(clause):
            return clause.strip()
    return None


def _unreadable_anaphoric_clause(text: str, *, for_spell: bool) -> str | None:
    """The second sentence of `text`'s "<verb> target X. Its/that X's
    controller ..." shape, if it has one **and this wave still cannot build
    it** - used only to decide whether a parse failure deserves an
    `AnaphoricClauseNotice`, not to parse the clause itself
    (`_parse_mixed_clauses` already tried and failed by the time this runs).

    Checking `_parse_anaphoric_clause_pair` itself, not just the two regexes'
    shape, matters: Boseiju's Channel ability fails to parse as a whole for
    two independent reasons, not one - `This ability costs {1} less to
    activate ...` is a third sentence neither this nor any other clause
    parser reads, *and* its own destroy-then-search pair does not read
    either, because `_REFERENT_SEARCH_RE` cannot match "a land card with a
    basic land type" (the "with a basic land type" tail falls into none of
    the regex's optional groups). A shape-only check would blame whichever
    sentence happens to fail the shape test first, which is the wrong
    clause exactly as often as it is the right one; checking the actual
    parse keeps the notice pointed at a sentence this wave really cannot
    read, whichever one that turns out to be.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for first, second in zip(clauses, clauses[1:], strict=False):
        verb_match = _DESTROY_TARGET_RE.fullmatch(first) or _EXILE_TARGET_RE.fullmatch(first)
        if verb_match is None:
            continue
        second_stripped = second.strip()
        if _ANAPHORIC_SUBJECT_RE.fullmatch(second_stripped):
            if _parse_anaphoric_clause_pair(first, second, for_spell=for_spell) is None:
                return second
            continue
        if (
            _LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE.match(second_stripped)
            and _parse_exile_then_return_clause_pair(first, second, for_spell=for_spell) is None
        ):
            return second
    # The object-anaphor half (CR 400.7's "it"/"they"/"that creature", not CR
    # 400.7's player anaphors above). Reported for *any* antecedent whose
    # referent this wave can name, not only a destroy or an exile, because
    # that is what an object anaphor is printed on: Eluge's "It's an Island
    # ... for as long as it has a flood counter on it", Firebending Lesson's
    # "it deals 5 damage to that creature instead", Combustion Technique's "If
    # that creature would die this turn, exile it instead".
    #
    # Gated on `_referent_reader` answering, for the same reason the pairs
    # above are gated on their own parser rather than on a shape test: without
    # it, a sentence that merely contains the word "it" ("put it into your
    # hand") would be blamed for a failure belonging to some other clause
    # entirely, which is the wrong sentence exactly as often as the right one.
    for first, second in zip(clauses, clauses[1:], strict=False):
        second_stripped = second.strip()
        if not _OBJECT_ANAPHOR_RE.search(second_stripped):
            continue
        if _ANAPHORIC_SUBJECT_RE.fullmatch(second_stripped):
            # A *player* anaphor that happens to contain the word "it" further
            # in - Boseiju's "That player may search their library ..., put
            # **it** onto the battlefield, then shuffle." The pair above owns
            # this shape, and blaming this sentence for a failure somewhere
            # else in the card is the wrong sentence exactly as often as the
            # right one.
            continue
        if _referent_reader(first) is None:
            continue
        if _parse_mixed_clause(first, for_spell=for_spell) is None:
            continue
        if _parse_object_anaphor_clause_pair(first, second, for_spell=for_spell) is None:
            return second
    return None


#: "Put onto the battlefield under your control all creature cards in your
#: opponents' graveyards that were put there from the battlefield this turn.
#: They are Food artifacts with "{2}, {T}, Sacrifice this artifact: You gain
#: 3 life." (They lose all other types and subtypes.)" (Supper for Spiders)
#: and "Return to the battlefield all permanent cards in your graveyard that
#: were put there from the battlefield this turn." (Faith's Reward). The
#: history is `Game.cards_put_into_graveyard_from_battlefield_this_turn`; CR
#: 110.2a puts each under the resolving spell's controller. One instruction
#: is one event (CR 603.6a, `Game.entering_together`), and the "They are
#: `<subtype>` `<type>`s with "`<ability>`"" rider is in place before that
#: event is announced: layer 4 sets the types (CR 205.1a, CR 613.1d), layer
#: 6 grants the quoted ability (CR 613.1f), no duration (CR 611.2a).
_PUT_CARDS_THAT_DIED_THIS_TURN_RE = re.compile(
    r"^(?:put onto the battlefield under your control|return to the battlefield) all "
    r"(?P<quality>[a-z]+) cards in (?P<whose>your|your opponents['’]|all) graveyards? "
    r"that were put there from the battlefield this turn\."
    r"(?:\s*they are (?P<subtype>[A-Z][a-z]+) (?P<type>artifact|enchantment|land)s with "
    r"[\"“](?P<ability>[^\"”]+)[\"”]\.?)?"
    r"(?:\s*\(they lose all other types and subtypes\.\))?$",
    re.IGNORECASE,
)


def _parse_put_cards_that_died_this_turn_clause(text: str) -> Effect | None:
    """`_PUT_CARDS_THAT_DIED_THIS_TURN_RE`'s shape - see the banner above."""
    match = _PUT_CARDS_THAT_DIED_THIS_TURN_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    quality = match.group("quality").lower()
    if quality == "permanent":
        wanted: frozenset[Type] = frozenset(_PERMANENT_CARD_TYPES)
    else:
        card_type = _singular_card_type(quality)
        if card_type is None:
            return None
        wanted = frozenset({card_type})
    whose = match.group("whose").lower()
    rider_type = _singular_card_type(match.group("type")) if match.group("type") else None
    rider_subtype = match.group("subtype")
    rider_ability = match.group("ability")
    if rider_ability is not None:
        rider_ability = rider_ability.strip()
        if not rider_ability.endswith("."):
            rider_ability += "."

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        if whose == "your":
            owners = [controller]
        elif whose == "all":
            owners = [player.username for player in game.players_in_game]
        else:
            owners = [p.username for p in game.players_in_game if p.username != controller]
        cards = [
            card
            for owner in owners
            for card in game.cards_put_into_graveyard_from_battlefield_this_turn(owner)
            if wanted & set(card.types)
        ]
        if not cards:
            return
        with game.entering_together():
            for card in cards:
                game.put_onto_battlefield(card, controller)
                if card.zone is not Zone.BATTLEFIELD or rider_type is None:
                    continue
                store = continuous_effects(game)
                timestamp = store.tick()
                selector = only_this_incarnation(card, card.zone_change_stamp)
                store.add(
                    ContinuousEffect(
                        description=f"{spell.name}: {card.name} is a {rider_subtype} "
                        f"{rider_type.value}",
                        layer=Layer.TYPE,
                        timestamp=timestamp,
                        selector=selector,
                        modification=SetTypesAndSubtypes(
                            types=(rider_type,), subtypes=(str(rider_subtype),)
                        ),
                    ),
                    game,
                )
                if rider_ability is not None:
                    store.add(
                        ContinuousEffect(
                            description=f"{spell.name}: {card.name} has {rider_ability!r}",
                            layer=Layer.ABILITY,
                            timestamp=timestamp,
                            selector=selector,
                            modification=grant_ability(rider_ability),
                        ),
                        game,
                    )
                    # `Game.activated_abilities` reads a granted activated
                    # ability off `granted_ability_texts` (the resolved-grant
                    # channel Urza's Saga's chapter II uses); CR 400.7 clears
                    # it again when the card leaves the battlefield.
                    if rider_ability not in card.granted_ability_texts:
                        card.granted_ability_texts = (*card.granted_ability_texts, rider_ability)

    return effect


def _ability_effect_or_notice(effect_text: str) -> AbilityEffect | None:
    """`parse_mixed_effect` on `effect_text`, or - if that failed specifically
    on an unreadable anaphoric second clause - a stand-in effect that records
    an `AnaphoricClauseNotice` and otherwise does nothing (CR 608.2c: still no
    partial run of the instruction). Returns `None`, exactly as before, for
    any other kind of unreadable text - Fatal Push's Revolt line keeps its
    old, unrecorded silence; only this one specific shape has a notice built
    for it so far.

    Tried only once the ordinary clause parser has already failed on the
    whole text: `_is_layer_effect_text` is a fallback net for a continuous
    effect `parse_mixed_effect`'s per-clause splitting cannot read as printed
    (Karn, the Great Creator's +1; Oliphaunt's "another target creature you
    control gets +2/+0 and gains trample until end of turn." attack trigger),
    not a replacement for it - a card mixing a continuous-effect clause with
    some other clause (a draw, a search) still needs the ordinary path to run
    both, so this never overrides a parse that already succeeded.
    `create_continuous_effect_of_ability` is what Basking Rootwalla's own
    "{1}{G}: This creature gets +2/+2 until end of turn." (no target at all)
    and Karn's targeted "+1" both route to - no `ACTIVATED_EFFECTS` row is
    needed for either any more, and none is needed for a triggered ability
    of the same shape either, which is what lights up Oliphaunt.

    Tried ahead of everything else: `_parse_conditional_sacrifice_clause`'s
    "you may sacrifice ... If you do, ..." shape (CR 118.12) has to be read
    off the *whole*, unsplit text the same way `_EACH_PLAYER_EXILE_SACRIFICE_
    RETURN_RE` is in `_spell_effect_or_notice` below - Disciple of Freyalise's
    own "you gain X life and draw X cards, where X is that creature's power"
    is one CR 608.2c instruction that `split_effect_clauses`'s bare "and" cut
    would otherwise slice into fragments none of `parse_mixed_effect`'s
    per-clause parsers read.

    Also tried ahead of everything else: `_parse_mana_adding_trigger`'s
    "[its controller ]adds an additional <mana>" shape (CR 605.1b, CR
    106.12a) - Utopia Sprawl, Leyline of Abundance, Badgermole Cub. None of
    `parse_clause_effect`'s player-clause shapes read "add mana" at all, so
    without this the whole ability would fall through every check below and
    come back `None`, exactly the reported defect.

    Tried ahead of everything else too: `parse_casting_rule_clause` against
    the *whole*, unsplit `effect_text` - Ral, Monsoon Mage's own +1, "Until
    your next turn, instant and sorcery spells you cast cost {1} less to
    cast.", has to be read as one CR 608.2c instruction, but `_CLAUSE_SEPARATOR`
    splits on any bare " and " (CR 608.2c has no notion of "and" inside a type
    list), which cuts "instant and sorcery" into "instant" / "sorcery spells
    you cast cost {1} less to cast." before `parse_casting_rule_clause` ever
    sees the sentence whole - neither fragment matches anything, so
    `parse_mixed_effect` used to fail closed on the entire ability and
    activating the +1 did nothing at all: no `CastingRuleEffect`, no cost
    reduction, ever - the real defect a wrongly-matching static line in
    `Game.static_cost_modifiers_for` was masking (see that function's own
    fix). Matching the whole text here first is exactly the same
    "tried against the whole unsplit text before it can be cut apart"
    treatment this docstring already gives `_parse_choose_name_search_and_
    exile_whole_text` above it, and is safe for `parse_casting_rule_clause`'s
    other two shapes (Ranger-Captain of Eos's sacrifice ability, Teferi, Time
    Raveler's own +1) too: neither contains a bare " and ", so both already
    matched by the per-clause path below and now simply match one step
    earlier, for the identical effect.

    Tried ahead of everything else too, now: `_parse_cast_from_hand_then_
    exile_clause` against the whole, unsplit text - Knowledge Pool's "Whenever
    a player casts a spell from their hand, that player exiles it. If the
    player does, ..." is the reported defect this fifth precedent exists for:
    `_prepare_effect_clauses` cuts the ability at the period, and the second
    fragment's "If the player does" is CR 118.12 anaphora straight back to
    the first - read apart, neither `parse_mixed_effect` clause parser below
    had any idea the two sentences were one instruction, so ability 2
    resolved and did nothing: no exile, no `Notice`, the gap invisible.
    Possibility Storm shares the identical opening and is read the same way.
    """
    from ..meld import parse_meld_activation_clause, parse_meld_resolution_clause
    from ..plans import (
        parse_put_counters_on_two_objects,
        parse_sacrifice_self_then_series,
        parse_sacrifice_self_when_you_do,
    )

    blight_counter_punisher = _parse_put_counter_then_for_each_counter_punisher_clause(effect_text)
    if blight_counter_punisher is not None:
        return blight_counter_punisher
    optional_behold_then_if_you_do = _parse_optional_behold_then_if_you_do_clause(effect_text)
    if optional_behold_then_if_you_do is not None:
        return optional_behold_then_if_you_do
    exile_until_n_quality_cast_one_free = _parse_exile_until_n_quality_cast_one_free_clause(
        effect_text
    )
    if exile_until_n_quality_cast_one_free is not None:
        return exile_until_n_quality_cast_one_free
    exile_hand_draw_then_play_ability = (
        _parse_exile_hand_draw_then_play_until_next_turn_ability_clause(effect_text)
    )
    if exile_hand_draw_then_play_ability is not None:
        return exile_hand_draw_then_play_ability
    exile_top_card_then_play_permission = _parse_exile_top_card_then_play_permission_clause(
        effect_text
    )
    if exile_top_card_then_play_permission is not None:
        return exile_top_card_then_play_permission
    search_library_graveyard_outside_the_game = (
        _parse_search_library_graveyard_outside_the_game_clause(effect_text)
    )
    if search_library_graveyard_outside_the_game is not None:
        return search_library_graveyard_outside_the_game
    counter_resolution = _parse_counter_resolution_text(effect_text)
    if counter_resolution is not None:
        return counter_resolution
    from ..becomes import becomes_ability_effect

    becomes = becomes_ability_effect(effect_text)
    if becomes is not None:
        return becomes
    from ..lose_abilities_destroy import lose_abilities_then_destroy_ability_effect

    lose_then_destroy = lose_abilities_then_destroy_ability_effect(effect_text)
    if lose_then_destroy is not None:
        return lose_then_destroy
    leading_then_if_otherwise = _parse_leading_then_if_otherwise_clause(
        effect_text, for_spell=False
    )
    if leading_then_if_otherwise is not None:
        return leading_then_if_otherwise
    counters_then_draw_half = _parse_put_n_counters_on_self_then_draw_half_n_clause(effect_text)
    if counters_then_draw_half is not None:
        return counters_then_draw_half
    choose_card_name = _parse_choose_card_name_for_source_clause(effect_text)
    if choose_card_name is not None:
        return choose_card_name
    source_relative = _source_relative_whole_text_ability_effect(effect_text)
    if source_relative is not None:
        return source_relative
    meld_activation = parse_meld_activation_clause(effect_text)
    if meld_activation is not None:
        return meld_activation
    # The Plans' payoff joins and Claim the Kingdom's two-object "put" -
    # `machines/plans.py`. Read whole: "When you do" and the shared "put"
    # both straddle the clause splitter's cuts.
    for plan_shape in (
        parse_sacrifice_self_when_you_do,
        parse_sacrifice_self_then_series,
        parse_put_counters_on_two_objects,
    ):
        plan_effect = plan_shape(effect_text)
        if plan_effect is not None:
            return plan_effect
    doubled = _parse_double_power_and_toughness_clause(effect_text)
    if doubled is not None:
        return doubled
    self_base_pt_with_keywords = _parse_self_base_pt_set_with_keywords_clause(effect_text)
    if self_base_pt_with_keywords is not None:
        return self_base_pt_with_keywords
    if re.search(r"\bif you don'?t,", effect_text, re.IGNORECASE):
        # Origin of the Avengers' "... from your hand onto the battlefield.
        # If you don't, draw a card." - the tail belongs to the put, so the
        # whole text is read before the clause splitter cuts it off.
        put_or_else = _parse_may_put_card_from_hand_clause(effect_text, for_spell=False)
        if put_or_else is not None:
            return put_or_else
    r0a_t5 = _r0a_t5_ability_effect(effect_text)
    if r0a_t5 is not None:
        return r0a_t5
    c02_t6 = _c02_t6_ability_effect(effect_text)
    if c02_t6 is not None:
        return c02_t6
    # EC7: Kozilek, the Broken Reality's own "Up to two target players each
    # manifest two cards from their hands. For each card manifested this
    # way, you draw a card." - read whole, ahead of the clause splitter: the
    # second sentence's "manifested this way" is CR 608.2c anaphora back to
    # the first sentence's own count, which no per-clause parser below has
    # any room to carry across the period.
    manifest_from_hand_then_draw = _parse_manifest_from_hand_then_draw_clause(effect_text)
    if manifest_from_hand_then_draw is not None:
        return manifest_from_hand_then_draw
    # EC7: Distended Mindbender's own "Target opponent reveals their hand.
    # You choose from it a `<qualityA>` card with mana value N or less and a
    # `<qualityB>` card with mana value M or greater. That player discards
    # those cards." - read whole, ahead of the clause splitter's bare-"and"
    # cut through "... or less and a card ...".
    reveal_two_bounds = _parse_reveal_hand_choose_two_bounded_cards_then_discard_clause(effect_text)
    if reveal_two_bounds is not None:
        return reveal_two_bounds
    # EC7: Hydroid Krasis's own "You gain half X life and draw half X cards.
    # Round down each time." - read whole: the trailing "Round down each
    # time." sentence governs both halves in the sentence before it, which
    # no per-clause parser below has any room to see together.
    half_x_life_and_draw = _parse_half_x_life_and_draw_half_x_cards_clause(effect_text)
    if half_x_life_and_draw is not None:
        return half_x_life_and_draw
    # ecl-T8: Meek Attack's own "... a creature card with total power and
    # toughness 5 or less from your hand onto the battlefield." - read whole,
    # ahead of the clause splitter, the same reason `_DOUBLE_TARGET_POWER_
    # AND_TOUGHNESS_RE` is: the bare "and" inside "power and toughness" is
    # not a conjunction between two instructions, and `split_effect_clauses`
    # cuts clean through it regardless.
    put_permanent_from_hand = _parse_put_permanent_card_from_hand_clause(
        effect_text, for_spell=False
    )
    if put_permanent_from_hand is not None:
        return put_permanent_from_hand
    # ecl-T8: Mutable Explorer's own "create a tapped Mutavault token. (It's a
    # land with "..." and "...")." - read whole, ahead of the splitter, since
    # the reminder text's own inner quoted ability can carry a period of its
    # own that a sentence split would cut in half.
    create_named_token = _parse_create_named_permanent_token_clause(effect_text)
    if create_named_token is not None:
        return create_named_token
    any_player_may_punisher = _parse_any_player_may_punisher_clause(effect_text)
    if any_player_may_punisher is not None:
        return any_player_may_punisher
    from ..infusion import infusion_ability_effect

    infused = infusion_ability_effect(effect_text)
    if infused is not None:
        return infused
    base_pt_become = _parse_base_pt_become_clause(effect_text)
    if base_pt_become is not None:
        return base_pt_become
    prevent_dealt_by_target = _parse_prevent_damage_dealt_by_target_clause(effect_text)
    if prevent_dealt_by_target is not None:
        return prevent_dealt_by_target
    exchange_control_clause = _parse_exchange_control_clause(effect_text)
    if exchange_control_clause is not None:
        return exchange_control_clause
    meld_resolution = parse_meld_resolution_clause(effect_text)
    if meld_resolution is not None:
        return meld_resolution
    draw_equal_to_sacrificed_then_discard = (
        _parse_draw_equal_to_sacrificed_creature_power_then_discard_clause(effect_text)
    )
    if draw_equal_to_sacrificed_then_discard is not None:
        # Read whole, ahead of the comma split: "then discard a card" is not
        # a readable clause on its own (nothing to discard *to*), and the
        # draw half needs the activation's own cost-sacrificed card, which no
        # per-clause parser below has access to.
        return draw_equal_to_sacrificed_then_discard
    opponents_lose_equal_to_sacrificed = (
        _parse_each_opponent_loses_life_equal_to_sacrificed_creature_clause(effect_text)
    )
    if opponents_lose_equal_to_sacrificed is not None:
        return opponents_lose_equal_to_sacrificed

    gain_life_equal_to_sacrificed = _parse_gain_life_equal_to_sacrificed_creature_clause(
        effect_text
    )
    if gain_life_equal_to_sacrificed is not None:
        return gain_life_equal_to_sacrificed
    may_transform_self_if_you_do = _parse_may_transform_self_if_you_do_clause(effect_text)
    if may_transform_self_if_you_do is not None:
        return may_transform_self_if_you_do
    self_layer_and_verb = _parse_self_layer_and_verb_clause(effect_text)
    if self_layer_and_verb is not None:
        return self_layer_and_verb
    cast_from_graveyard_now = _parse_cast_from_graveyard_now_clause(effect_text)
    if cast_from_graveyard_now is not None:
        return cast_from_graveyard_now
    counter_exile_may_cast = _parse_counter_exile_may_cast_free_clause(effect_text)
    if counter_exile_may_cast is not None:
        return counter_exile_may_cast
    face_down_exile_play = _parse_face_down_exile_play_clause(effect_text)
    if face_down_exile_play is not None:
        return face_down_exile_play
    cast_from_hand_then_exile = _parse_cast_from_hand_then_exile_clause(effect_text)
    if cast_from_hand_then_exile is not None:
        return cast_from_hand_then_exile
    linked_exile = _parse_linked_exile_clause(effect_text)
    if linked_exile is not None:
        return linked_exile
    exile_cards_from_your_hand = _parse_exile_cards_from_your_hand_clause(effect_text)
    if exile_cards_from_your_hand is not None:
        return exile_cards_from_your_hand
    look_top_keep_one_on_top = _parse_look_top_keep_one_on_top_clause(effect_text)
    if look_top_keep_one_on_top is not None:
        return look_top_keep_one_on_top
    cast_trigger_look_top_x = _parse_cast_trigger_look_top_x_take_one_clause(effect_text)
    if cast_trigger_look_top_x is not None:
        return cast_trigger_look_top_x
    cast_trigger_reveal_top_x_put_one_permanent = (
        _parse_cast_trigger_reveal_top_x_put_one_permanent_clause(effect_text)
    )
    if cast_trigger_reveal_top_x_put_one_permanent is not None:
        return cast_trigger_reveal_top_x_put_one_permanent
    cast_trigger_reveal_until_x_kind_to_graveyard = (
        _parse_cast_trigger_reveal_until_x_kind_to_graveyard_clause(effect_text)
    )
    if cast_trigger_reveal_until_x_kind_to_graveyard is not None:
        return cast_trigger_reveal_until_x_kind_to_graveyard
    target_opponent_exile_top_then_put_lands = (
        _parse_target_opponent_exile_top_then_put_lands_clause(effect_text)
    )
    if target_opponent_exile_top_then_put_lands is not None:
        return target_opponent_exile_top_then_put_lands
    damage_target_player_and_theirs = _parse_damage_target_player_and_their_creatures_clause(
        effect_text
    )
    if damage_target_player_and_theirs is not None:
        return damage_target_player_and_theirs
    cast_target_from_graveyard = _parse_cast_target_card_from_graveyard_clause(effect_text)
    if cast_target_from_graveyard is not None:
        return cast_target_from_graveyard
    it_gains_quoted_ability = _parse_it_gains_quoted_ability_clause(effect_text)
    if it_gains_quoted_ability is not None:
        return it_gains_quoted_ability
    target_attacking_alone_pump_gain_life = _parse_target_attacking_alone_pump_gain_life_clause(
        effect_text
    )
    if target_attacking_alone_pump_gain_life is not None:
        return target_attacking_alone_pump_gain_life
    it_dynamic_x_pump = _parse_it_dynamic_x_pump_clause(effect_text)
    if it_dynamic_x_pump is not None:
        return it_dynamic_x_pump
    self_gains_quoted_ability_until_eot = _parse_self_gains_quoted_ability_until_eot_clause(
        effect_text
    )
    if self_gains_quoted_ability_until_eot is not None:
        return self_gains_quoted_ability_until_eot
    choose_target_then_return_to_your_hand = _parse_choose_target_then_return_to_your_hand_pair(
        effect_text
    )
    if choose_target_then_return_to_your_hand is not None:
        return choose_target_then_return_to_your_hand
    reveal_n_then_choose_discard = _parse_reveal_n_cards_then_choose_discard_whole_text(
        effect_text, for_spell=False
    )
    if reveal_n_then_choose_discard is not None:
        return reveal_n_then_choose_discard
    choose_opponent_reveal_exile_choice = (
        _parse_choose_opponent_and_creature_reveal_exile_choice_whole_text(
            effect_text, for_spell=False
        )
    )
    if choose_opponent_reveal_exile_choice is not None:
        return choose_opponent_reveal_exile_choice
    # S22's whole-text readers: each names its own object ("exiled with this
    # creature", "that card" after an exile, "them" after a count), so none
    # of them may be cut apart by the clause splitter below.
    target_attacks_if_able = _parse_target_attacks_if_able_clause(effect_text)
    if target_attacks_if_able is not None:
        return target_attacks_if_able
    target_blocks_self_if_able = _parse_target_blocks_self_if_able_clause(effect_text)
    if target_blocks_self_if_able is not None:
        return target_blocks_self_if_able
    exile_card_then_token_copy = _parse_exile_card_then_token_copy_clause(
        effect_text, for_spell=False
    )
    if exile_card_then_token_copy is not None:
        return exile_card_then_token_copy
    put_card_exiled_with_self = _parse_put_card_exiled_with_self_clause(effect_text)
    if put_card_exiled_with_self is not None:
        return put_card_exiled_with_self
    remove_all_counters_then_that_many = _parse_remove_all_counters_then_that_many_clause(
        effect_text
    )
    if remove_all_counters_then_that_many is not None:
        return remove_all_counters_then_that_many
    flashback_grant = _parse_grant_flashback_clause(effect_text)
    if flashback_grant is not None:
        return flashback_grant
    casting_rule_whole = parse_casting_rule_clause(effect_text, for_spell=False)
    if casting_rule_whole is not None:
        return casting_rule_whole
    until_your_next_turn_attack_pump = _parse_until_your_next_turn_attack_pump_clause(effect_text)
    if until_your_next_turn_attack_pump is not None:
        return until_your_next_turn_attack_pump
    divided_damage_then_retaliate = _parse_divided_damage_then_retaliate_clause(effect_text)
    if divided_damage_then_retaliate is not None:
        return divided_damage_then_retaliate
    attacks_alone_this_turn_counters_and_keywords = (
        _parse_attacks_alone_this_turn_counters_and_keywords_clause(effect_text)
    )
    if attacks_alone_this_turn_counters_and_keywords is not None:
        return attacks_alone_this_turn_counters_and_keywords
    until_your_next_turn_group_attack_pump = _parse_until_your_next_turn_group_attack_pump_clause(
        effect_text
    )
    if until_your_next_turn_group_attack_pump is not None:
        return until_your_next_turn_group_attack_pump
    batched_attack_group_pump = _parse_batched_attack_group_pump_clause(effect_text)
    if batched_attack_group_pump is not None:
        return batched_attack_group_pump
    ante_self = _parse_ante_self_if_you_do_clause(effect_text)
    if ante_self is not None:
        return ante_self
    exile_until_leaves_then_counters = _parse_exile_targets_until_leaves_then_counters(effect_text)
    if exile_until_leaves_then_counters is not None:
        return exile_until_leaves_then_counters
    mass_gain_control = _parse_mass_gain_control_untap_ability(effect_text)
    if mass_gain_control is not None:
        return mass_gain_control
    copy_of_linked_exile = _parse_copy_of_card_exiled_with_self_clause(effect_text)
    if copy_of_linked_exile is not None:
        return copy_of_linked_exile
    may_exile_return_others = _parse_may_exile_that_card_return_others_clause(effect_text)
    if may_exile_return_others is not None:
        return may_exile_return_others
    ability_return_as_creature = _parse_return_as_creature_clause(effect_text)
    if ability_return_as_creature is not None:
        return ability_return_as_creature
    untap_and_gain_control = _parse_untap_and_gain_control_ability(effect_text)
    if untap_and_gain_control is not None:
        return untap_and_gain_control
    token_copies_except = _parse_create_token_copies_except_clause(effect_text, for_spell=False)
    if token_copies_except is not None:
        return token_copies_except
    for_each_creature_target_player_copy = _parse_for_each_creature_target_player_copy_clause(
        effect_text, for_spell=False
    )
    if for_each_creature_target_player_copy is not None:
        return for_each_creature_target_player_copy
    for_each_creature_you_control_copy = _parse_for_each_creature_you_control_copy_clause(
        effect_text, for_spell=False
    )
    if for_each_creature_you_control_copy is not None:
        return for_each_creature_you_control_copy
    modal_triggered = _resolve_modal_triggered_ability_clause(effect_text)
    if modal_triggered is not None:
        return modal_triggered
    put_land_repeat = _parse_put_land_from_hand_repeat_clause(effect_text)
    if put_land_repeat is not None:
        return put_land_repeat
    draw_then_put_land_cave = _parse_draw_then_put_land_cave_bonus_clause(effect_text)
    if draw_then_put_land_cave is not None:
        return draw_then_put_land_cave
    discard_then_draw_token_per_nonland = _parse_discard_then_draw_token_per_nonland_clause(
        effect_text
    )
    if discard_then_draw_token_per_nonland is not None:
        return discard_then_draw_token_per_nonland
    return_self_then_create_tokens = _parse_return_self_then_create_tokens_clause(effect_text)
    if return_self_then_create_tokens is not None:
        return return_self_then_create_tokens
    reveal_until_land = _parse_reveal_until_land_damage_clause(effect_text)
    if reveal_until_land is not None:
        return reveal_until_land
    outside_the_game = _parse_outside_the_game_fetch(effect_text)
    if outside_the_game is not None:
        return outside_the_game
    undergrowth_pump_and_fight = _parse_undergrowth_pump_and_fight_clause(effect_text)
    if undergrowth_pump_and_fight is not None:
        return undergrowth_pump_and_fight
    each_opponent_choose_then_sacrifice = (
        _parse_each_opponent_choose_one_of_each_type_then_sacrifice(effect_text)
    )
    if each_opponent_choose_then_sacrifice is not None:
        return each_opponent_choose_then_sacrifice
    each_sacrifices_then_if_you_did = _parse_each_sacrifices_then_if_you_did_clause(
        effect_text, for_spell=False
    )
    if each_sacrifices_then_if_you_did is not None:
        return each_sacrifices_then_if_you_did
    choose_target_owner_shuffles_it = _parse_choose_target_owner_shuffles_it_clause(
        effect_text, for_spell=False
    )
    if choose_target_owner_shuffles_it is not None:
        return choose_target_owner_shuffles_it
    target_player_name_reveal_branch = _parse_target_player_name_reveal_branch_clause(effect_text)
    if target_player_name_reveal_branch is not None:
        return target_player_name_reveal_branch
    each_player_name_reveal_branch = _parse_each_player_name_reveal_branch_clause(effect_text)
    if each_player_name_reveal_branch is not None:
        return each_player_name_reveal_branch
    damage_that_player = _parse_damage_that_player_clause(effect_text, for_spell=False)
    if damage_that_player is not None:
        return damage_that_player
    damage_that_much = _parse_damage_that_much_clause(effect_text, for_spell=False)
    if damage_that_much is not None:
        return damage_that_much
    may_discard_or_sacrifice = _parse_may_discard_or_sacrifice_if_you_do_clause(
        effect_text, for_spell=False
    )
    if may_discard_or_sacrifice is not None:
        return may_discard_or_sacrifice
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=False)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    conditional_remove_counter_from_self = _parse_conditional_remove_counter_from_self_clause(
        effect_text, for_spell=False
    )
    if conditional_remove_counter_from_self is not None:
        return conditional_remove_counter_from_self
    may_tap_untapped_if_you_do = _parse_may_tap_untapped_if_you_do_clause(effect_text)
    if may_tap_untapped_if_you_do is not None:
        return may_tap_untapped_if_you_do
    tap_another_untapped_when_you_do = _parse_tap_another_untapped_subtype_when_you_do_clause(
        effect_text
    )
    if tap_another_untapped_when_you_do is not None:
        return tap_another_untapped_when_you_do
    reflexive_sacrifice_or_discard = _parse_reflexive_sacrifice_or_discard_clause(effect_text)
    if reflexive_sacrifice_or_discard is not None:
        return reflexive_sacrifice_or_discard
    reflexive_sacrifice = _parse_reflexive_sacrifice_clause(effect_text)
    if reflexive_sacrifice is not None:
        return reflexive_sacrifice
    reflexive_may_discard = _parse_reflexive_may_discard_clause(effect_text)
    if reflexive_may_discard is not None:
        return reflexive_may_discard
    reflexive_pay_energy = _parse_reflexive_pay_energy_clause(effect_text)
    if reflexive_pay_energy is not None:
        return reflexive_pay_energy
    may_pay_energy_if_you_do = _parse_may_pay_energy_if_you_do_clause(effect_text)
    if may_pay_energy_if_you_do is not None:
        return may_pay_energy_if_you_do
    get_energy_then_pay_create_x_token = _parse_get_energy_then_pay_create_x_token_clause(
        effect_text
    )
    if get_energy_then_pay_create_x_token is not None:
        return get_energy_then_pay_create_x_token
    reflexive_pay_mana = _parse_reflexive_pay_mana_clause(effect_text)
    if reflexive_pay_mana is not None:
        return reflexive_pay_mana
    reflexive_pay_mana_and_life = _parse_reflexive_pay_mana_and_life_clause(effect_text)
    if reflexive_pay_mana_and_life is not None:
        return reflexive_pay_mana_and_life
    reflexive_pay_life = _parse_reflexive_pay_life_clause(effect_text)
    if reflexive_pay_life is not None:
        return reflexive_pay_life
    reflexive_may_tap_self = _parse_reflexive_may_tap_self_clause(effect_text)
    if reflexive_may_tap_self is not None:
        return reflexive_may_tap_self
    reflexive_pay_up_to_n_times_choose_modes = (
        _parse_reflexive_pay_up_to_n_times_choose_modes_clause(effect_text)
    )
    if reflexive_pay_up_to_n_times_choose_modes is not None:
        return reflexive_pay_up_to_n_times_choose_modes
    may_pay_mana_if_you_do = _parse_may_pay_mana_if_you_do_clause(effect_text)
    if may_pay_mana_if_you_do is not None:
        return may_pay_mana_if_you_do
    may_pay_life_if_you_do = _parse_may_pay_life_if_you_do_clause(effect_text)
    if may_pay_life_if_you_do is not None:
        return may_pay_life_if_you_do
    may_exile_hand_if_you_do = _parse_may_exile_hand_if_you_do_clause(effect_text)
    if may_exile_hand_if_you_do is not None:
        return may_exile_hand_if_you_do
    reflexive_mandatory_token = _parse_reflexive_mandatory_token_clause(effect_text)
    if reflexive_mandatory_token is not None:
        return reflexive_mandatory_token
    reflexive_mandatory_mill = _parse_reflexive_mandatory_mill_clause(effect_text)
    if reflexive_mandatory_mill is not None:
        return reflexive_mandatory_mill
    reflexive_self_counter_if = _parse_reflexive_self_counter_if_clause(effect_text)
    if reflexive_self_counter_if is not None:
        return reflexive_self_counter_if
    create_token_then_may_attach = _parse_create_token_then_may_attach_clause(effect_text)
    if create_token_then_may_attach is not None:
        return create_token_then_may_attach
    create_token_then_attach = _parse_create_token_then_attach_clause(effect_text)
    if create_token_then_attach is not None:
        return create_token_then_attach
    may_attach_to_entering_creature = _parse_may_attach_to_entering_creature_clause(effect_text)
    if may_attach_to_entering_creature is not None:
        return may_attach_to_entering_creature
    return_then_instead_battlefield = (
        _parse_return_target_card_then_instead_battlefield_if_cost_paid_clause(effect_text)
    )
    if return_then_instead_battlefield is not None:
        return return_then_instead_battlefield
    choose_exile_until_leaves_then_permanent = (
        _parse_choose_target_exile_until_leaves_then_instead_permanent_clause(effect_text)
    )
    if choose_exile_until_leaves_then_permanent is not None:
        return choose_exile_until_leaves_then_permanent
    named_equipment_token = _parse_named_equipment_token_clause(effect_text)
    if named_equipment_token is not None:
        return named_equipment_token
    attach_then_when_you_do = _parse_attach_self_then_when_you_do_clause(effect_text)
    if attach_then_when_you_do is not None:
        return attach_then_when_you_do
    attach_self_to_target = _attach_self_to_target_effect(effect_text)
    if attach_self_to_target is not None:
        return attach_self_to_target
    amass_then_attach = _parse_amass_then_attach_clause(effect_text)
    if amass_then_attach is not None:
        return amass_then_attach
    attach_target_equipment_up_to_one_creature = (
        _parse_attach_target_equipment_up_to_one_creature_clause(effect_text)
    )
    if attach_target_equipment_up_to_one_creature is not None:
        return attach_target_equipment_up_to_one_creature
    attach_any_number_equipment = _parse_attach_any_number_equipment_clause(effect_text)
    if attach_any_number_equipment is not None:
        return attach_any_number_equipment
    put_self_counter_then_attach = (
        _parse_put_self_counter_for_each_opponent_creature_then_attach_clause(effect_text)
    )
    if put_self_counter_then_attach is not None:
        return put_self_counter_then_attach
    choose_type_treasure = _parse_choose_creature_type_treasure_per_match_clause(effect_text)
    if choose_type_treasure is not None:
        return choose_type_treasure
    equipped_attackers_gain_keywords = _parse_equipped_attacking_creatures_gain_keywords_clause(
        effect_text
    )
    if equipped_attackers_gain_keywords is not None:
        return equipped_attackers_gain_keywords
    dalkovan_attack_tokens = _parse_attack_this_turn_create_tapped_attacking_tokens(effect_text)
    if dalkovan_attack_tokens is not None:
        return dalkovan_attack_tokens
    self_combat_damage_draw = _parse_until_end_of_turn_self_combat_damage_draw_clause(effect_text)
    if self_combat_damage_draw is not None:
        return self_combat_damage_draw
    cast_noncreature_this_turn_copy_token = (
        _parse_cast_noncreature_spell_this_turn_copy_token_clause(effect_text)
    )
    if cast_noncreature_this_turn_copy_token is not None:
        return cast_noncreature_this_turn_copy_token
    created_trigger = _parse_created_trigger_ability_text(effect_text)
    if created_trigger is not None:
        return created_trigger
    created_replacement = _parse_created_replacement_ability_text(effect_text)
    if created_replacement is not None:
        return created_replacement
    event_subject_counters_and_keywords = _parse_event_subject_counters_and_keywords_clause(
        effect_text
    )
    if event_subject_counters_and_keywords is not None:
        return event_subject_counters_and_keywords
    attacking_tokens_then_sacrifice = _parse_create_tapped_attacking_tokens_then_sacrifice(
        effect_text
    )
    if attacking_tokens_then_sacrifice is not None:
        return attacking_tokens_then_sacrifice
    tapped_attacking_tokens = _parse_tapped_attacking_tokens_whole_text(
        effect_text, for_spell=False
    )
    if tapped_attacking_tokens is not None:
        return tapped_attacking_tokens
    may_cost_then_attacking_token = _parse_may_cost_then_attacking_token_clause(effect_text)
    if may_cost_then_attacking_token is not None:
        return may_cost_then_attacking_token
    put_from_hand_attacking = _parse_put_creature_from_hand_attacking_then_return(effect_text)
    if put_from_hand_attacking is not None:
        return put_from_hand_attacking
    put_mv_x_from_hand_attacking = _parse_put_creature_mv_x_from_hand_attacking(effect_text)
    if put_mv_x_from_hand_attacking is not None:
        return put_mv_x_from_hand_attacking
    exchange_life = _parse_exchange_life_totals_then_draw(effect_text)
    if exchange_life is not None:
        return exchange_life
    copy_exiled_and_cast = _parse_copy_exiled_card_and_cast(effect_text)
    if copy_exiled_and_cast is not None:
        return copy_exiled_and_cast
    copy_cost_exiled = _parse_copy_cost_exiled_cards_and_cast(effect_text)
    if copy_cost_exiled is not None:
        return copy_cost_exiled
    exile_one_of_each_type_copy_cast = _parse_exile_one_of_each_type_copy_cast_clause(effect_text)
    if exile_one_of_each_type_copy_cast is not None:
        return exile_one_of_each_type_copy_cast
    exile_target_copy_cast = _parse_exile_target_card_copy_it_cast_clause(effect_text)
    if exile_target_copy_cast is not None:
        return exile_target_copy_cast
    mana_adding = _parse_mana_adding_trigger(effect_text)
    if mana_adding is not None:
        return mana_adding
    firebending = _parse_firebending_add_mana(effect_text)
    if firebending is not None:
        return firebending
    add_one_mana_of_any_color = _parse_add_one_mana_of_any_color_trigger(effect_text)
    if add_one_mana_of_any_color is not None:
        return add_one_mana_of_any_color
    add_mana_in_any_combination = _parse_add_mana_in_any_combination_trigger(effect_text)
    if add_mana_in_any_combination is not None:
        return add_mana_in_any_combination
    add_that_much_colored_mana = _parse_add_that_much_colored_mana_trigger(effect_text)
    if add_that_much_colored_mana is not None:
        return add_that_much_colored_mana
    sacrifice_unless_discard = _parse_sacrifice_unless_discard_trigger(effect_text)
    if sacrifice_unless_discard is not None:
        return sacrifice_unless_discard
    draw_then_discard_unless_ability = _parse_draw_then_discard_unless_ability(effect_text)
    if draw_then_discard_unless_ability is not None:
        return draw_then_discard_unless_ability
    tap_any_number_when_you_do = _parse_tap_any_number_of_untapped_creatures_when_you_do_clause(
        effect_text
    )
    if tap_any_number_when_you_do is not None:
        return tap_any_number_when_you_do
    counter_on_subject_and_shared_type = _parse_counter_on_subject_and_shared_type_clause(
        effect_text
    )
    if counter_on_subject_and_shared_type is not None:
        return counter_on_subject_and_shared_type
    self_keyword_choice_until_eot = _parse_self_keyword_choice_until_eot_trigger(effect_text)
    if self_keyword_choice_until_eot is not None:
        return self_keyword_choice_until_eot
    each_other_attacking_pump = _parse_each_other_attacking_creature_pump_trigger(effect_text)
    if each_other_attacking_pump is not None:
        return each_other_attacking_pump
    other_attacking_grant = _parse_other_attacking_creatures_grant_trigger(effect_text)
    if other_attacking_grant is not None:
        return other_attacking_grant
    counters_on_target_where_x_is = _parse_put_counters_on_target_where_x_is_clause(effect_text)
    if counters_on_target_where_x_is is not None:
        return counters_on_target_where_x_is
    may_then_if_you_do_layer = _parse_may_then_if_you_do_layer_clause(effect_text)
    if may_then_if_you_do_layer is not None:
        return may_then_if_you_do_layer
    emblem_then = _parse_get_an_emblem_then_clause(effect_text)
    if emblem_then is not None:
        return emblem_then
    tap_untap_two_targets = _parse_tap_untap_two_targets_clause(effect_text)
    if tap_untap_two_targets is not None:
        return tap_untap_two_targets
    emblem = _parse_get_an_emblem_clause(effect_text)
    if emblem is not None:
        return emblem
    choose_type_then_emblem = parse_choose_creature_type_then_emblem_clause(effect_text)
    if choose_type_then_emblem is not None:
        return choose_type_then_emblem
    choose_type_hexproof_indestructible = parse_choose_type_hexproof_indestructible_clause(
        effect_text
    )
    if choose_type_hexproof_indestructible is not None:
        return choose_type_hexproof_indestructible
    gathering_stone_look = parse_gathering_stone_look_clause(effect_text)
    if gathering_stone_look is not None:
        return gathering_stone_look
    counters_by_subtype = _parse_counters_more_if_subtype_clause(effect_text)
    if counters_by_subtype is not None:
        return counters_by_subtype
    nth_resolution = _parse_nth_resolution_clause(effect_text)
    if nth_resolution is not None:
        return nth_resolution
    mill_then_take = _parse_mill_that_many_then_take_from_among_them(effect_text)
    if mill_then_take is not None:
        return mill_then_take
    # Tried against the whole, unsplit text, the same precedent
    # `parse_casting_rule_clause` above documents: "tapped and transformed"
    # has a bare " and " in it, which `split_effect_clauses`'s
    # `_CLAUSE_SEPARATOR` cuts into "return it to the battlefield tapped" /
    # "transformed under its owner's control" before either fragment reaches
    # a clause parser - Ojer Taq, Deepest Foundation's own death trigger.
    return_self_as_type = _parse_return_self_as_type_clause(effect_text)
    if return_self_as_type is not None:
        return return_self_as_type
    counter_targeting_unless = _parse_counter_targeting_object_unless_clause(effect_text)
    if counter_targeting_unless is not None:
        return counter_targeting_unless
    if_you_do_self_gains = _parse_targeted_then_self_gains_clause(effect_text)
    if if_you_do_self_gains is not None:
        return if_you_do_self_gains
    return_self_transformed_whole = _parse_return_self_to_battlefield_transformed_clause(
        effect_text, for_spell=False
    )
    if return_self_transformed_whole is not None:
        return return_self_transformed_whole
    transform_self = _parse_transform_clause(effect_text)
    if transform_self is not None:
        return transform_self
    exile_self_then_return = _parse_may_exile_self_then_return_clause(effect_text)
    if exile_self_then_return is not None:
        return exile_self_then_return
    mandatory_exile_self_then_return = _parse_exile_self_then_return_clause(effect_text)
    if mandatory_exile_self_then_return is not None:
        return mandatory_exile_self_then_return
    sacrifice_unless_energy = _parse_sacrifice_unless_pay_energy(effect_text)
    if sacrifice_unless_energy is not None:
        return sacrifice_unless_energy
    destroy_each_then_remove_counters = _parse_destroy_each_then_remove_all_counters(effect_text)
    if destroy_each_then_remove_counters is not None:
        return destroy_each_then_remove_counters
    destroy_each = _parse_destroy_each_clause(_strip_non_effect_preamble(effect_text).strip())
    if destroy_each is not None:
        return destroy_each
    put_counters_on_group = _parse_put_counters_on_group_clause(effect_text)
    if put_counters_on_group is not None:
        return put_counters_on_group
    counters_on_named_group = _parse_counters_on_named_group_clause(effect_text)
    if counters_on_named_group is not None:
        return counters_on_named_group
    counter_then_if_count = _parse_put_counter_on_self_then_if_count_clause(effect_text)
    if counter_then_if_count is not None:
        return counter_then_if_count
    put_counters_on_self = _parse_put_counters_on_self_clause(effect_text)
    if put_counters_on_self is not None:
        return put_counters_on_self
    put_up_to_n_counters_on_self_capped = _parse_put_up_to_n_counters_on_self_capped_clause(
        effect_text
    )
    if put_up_to_n_counters_on_self_capped is not None:
        return put_up_to_n_counters_on_self_capped
    put_counters_equal_to = _parse_put_counters_equal_to_clause(effect_text)
    if put_counters_equal_to is not None:
        return put_counters_equal_to
    adapt = _parse_adapt_clause(effect_text)
    if adapt is not None:
        return adapt
    endure = _parse_endure_clause(effect_text)
    if endure is not None:
        return endure
    monstrosity = _parse_monstrosity_clause(effect_text)
    if monstrosity is not None:
        return monstrosity
    # Tried against the whole, unsplit text - "copy that spell. You may
    # choose new targets for the copy." has a bare period joining its two
    # sentences, which `_prepare_effect_clauses` cuts into two separate
    # clauses before either ever reaches `_parse_mixed_clause`'s per-clause
    # dispatch, the same precedent already documented above for `parse_
    # casting_rule_clause` and `_parse_return_self_to_battlefield_
    # transformed_clause`.
    copy_that_spell_whole = _parse_copy_that_spell_clause(effect_text, for_spell=False)
    if copy_that_spell_whole is not None:
        return copy_that_spell_whole
    create_x_tokens_where_x_is = _parse_create_x_tokens_where_x_is_clause(effect_text)
    if create_x_tokens_where_x_is is not None:
        return create_x_tokens_where_x_is
    double_counters_on_group = _parse_double_counters_on_group_clause(effect_text)
    if double_counters_on_group is not None:
        return double_counters_on_group
    defending_player_reveals_top_land = _parse_defending_player_reveals_top_conditional_land_clause(
        effect_text
    )
    if defending_player_reveals_top_land is not None:
        return defending_player_reveals_top_land
    untap_self = _parse_untap_self_clause(effect_text)
    if untap_self is not None:
        return untap_self
    deals_damage_lose_life_then_transform = (
        _parse_deals_damage_lose_life_then_transform_if_low_clause(effect_text)
    )
    if deals_damage_lose_life_then_transform is not None:
        return deals_damage_lose_life_then_transform
    untap_trigger_subject = _parse_untap_trigger_subject_clause(effect_text)
    if untap_trigger_subject is not None:
        return untap_trigger_subject
    untap_trigger_subject_and_scry = _parse_untap_trigger_subject_and_scry_clause(effect_text)
    if untap_trigger_subject_and_scry is not None:
        return untap_trigger_subject_and_scry
    attached_subject_gains_keywords_until = _parse_attached_subject_gains_keywords_until_clause(
        effect_text
    )
    if attached_subject_gains_keywords_until is not None:
        return attached_subject_gains_keywords_until
    return_a_land_you_control = _parse_return_a_land_you_control_clause(effect_text)
    if return_a_land_you_control is not None:
        return return_a_land_you_control
    gains_ability = _parse_gains_ability_clause(effect_text)
    if gains_ability is not None:
        return gains_ability
    remove_time_counter_self = _parse_remove_time_counter_from_self_clause(effect_text)
    if remove_time_counter_self is not None:
        return remove_time_counter_self
    remove_all_counters_from_target = _parse_remove_all_counters_from_target_clause(effect_text)
    if remove_all_counters_from_target is not None:
        return remove_all_counters_from_target
    remove_up_to_n_counters_from_target = _parse_remove_up_to_n_counters_from_target_clause(
        effect_text
    )
    if remove_up_to_n_counters_from_target is not None:
        return remove_up_to_n_counters_from_target
    remove_n_counters_from_self = _parse_remove_n_counters_from_self_clause(effect_text)
    if remove_n_counters_from_self is not None:
        return remove_n_counters_from_self
    self_cant_block = _parse_self_cant_block_clause(effect_text)
    if self_cant_block is not None:
        return self_cant_block
    put_its_counters_on_target = _parse_put_its_counters_on_target_clause(
        effect_text, for_spell=False
    )
    if put_its_counters_on_target is not None:
        return put_its_counters_on_target
    for_each_opponent_tap_then_stun = _parse_for_each_opponent_tap_then_stun_clause(
        effect_text, for_spell=False
    )
    if for_each_opponent_tap_then_stun is not None:
        return for_each_opponent_tap_then_stun
    for_each_opponent_tap = _parse_for_each_opponent_tap_clause(effect_text, for_spell=False)
    if for_each_opponent_tap is not None:
        return for_each_opponent_tap
    goad_then_counters = _parse_goad_for_each_opponent_then_counters_clause(
        effect_text, for_spell=False
    )
    if goad_then_counters is not None:
        return goad_then_counters
    for_each_opponent_counters = _parse_for_each_opponent_counters_clause(
        effect_text, for_spell=False
    )
    if for_each_opponent_counters is not None:
        return for_each_opponent_counters
    for_each_opponent_destroy = _parse_for_each_opponent_destroy_clause(
        effect_text, for_spell=False
    )
    if for_each_opponent_destroy is not None:
        return for_each_opponent_destroy
    for_each_opponent_exile = _parse_for_each_opponent_exile_clause(effect_text, for_spell=False)
    if for_each_opponent_exile is not None:
        return for_each_opponent_exile
    for_each_opponent_return_to_hand = _parse_for_each_opponent_return_to_hand_clause(
        effect_text, for_spell=False
    )
    if for_each_opponent_return_to_hand is not None:
        return for_each_opponent_return_to_hand
    whole_text_token = _parse_whole_text_token_clause(effect_text)
    if whole_text_token is not None:
        return whole_text_token
    # Read whole, ahead of the clause splitter, for the same reason
    # `_parse_whole_text_token_clause` above is: Parhelion II's own "with
    # flying and vigilance" carries a bare " and " inside one noun phrase,
    # which `_CLAUSE_SEPARATOR` would cut into two fragments neither half of
    # which is a token clause at all.
    attacking_token_whole = _parse_attacking_token_clause(effect_text, for_spell=False)
    if attacking_token_whole is not None:
        return attacking_token_whole
    exile_reflexive_creature_counter = _parse_exile_target_card_reflexive_creature_counter(
        effect_text
    )
    if exile_reflexive_creature_counter is not None:
        return exile_reflexive_creature_counter
    create_token_mill_repeat = _parse_create_token_mill_repeat_clause(effect_text)
    if create_token_mill_repeat is not None:
        return create_token_mill_repeat
    mill_then_may_return_creature = _parse_mill_then_may_return_creature_clause(effect_text)
    if mill_then_may_return_creature is not None:
        return mill_then_may_return_creature
    # -- whole-text shapes whose sentences point back at one another -------
    reflexive_discard_count = _parse_reflexive_discard_count_clause(effect_text)
    if reflexive_discard_count is not None:
        return reflexive_discard_count
    explores_then_destroy = _parse_explores_then_conditional_mass_destroy(effect_text)
    if explores_then_destroy is not None:
        return explores_then_destroy
    sacrifice_then_reanimate = _parse_each_player_sacrifices_then_mass_reanimate(effect_text)
    if sacrifice_then_reanimate is not None:
        return sacrifice_then_reanimate
    reanimate_gains_then_bounce = _parse_return_target_from_graveyard_gains_then_bounce(effect_text)
    if reanimate_gains_then_bounce is not None:
        return reanimate_gains_then_bounce
    mill_then_play = _parse_mill_then_play_that_card(effect_text)
    if mill_then_play is not None:
        return mill_then_play
    mill_then_return_to_hand = _parse_mill_then_return_to_hand_clause(effect_text)
    if mill_then_return_to_hand is not None:
        return mill_then_return_to_hand
    conditional_token_count = _parse_conditional_token_count_on_sacrificed(effect_text)
    if conditional_token_count is not None:
        return conditional_token_count
    double_power = _parse_double_power_target_clause(effect_text)
    if double_power is not None:
        return double_power
    # -- end whole-text shapes ---------------------------------------------
    # The general "mill or look at the top N, then optionally move one"
    # family. It replaced a card-specific `_parse_mill_then_may_put_land_in_hand_clause`
    # (Six only), which is why the dispatch entry for that parser is not
    # carried over here - the function no longer exists.
    look_top_may_reveal = _parse_look_top_may_reveal_clause(effect_text)
    if look_top_may_reveal is not None:
        return look_top_may_reveal
    select_from_top = _parse_select_from_top_clause(effect_text)
    if select_from_top is not None:
        return select_from_top
    look_top_x_put_permanents = _parse_look_top_x_put_permanents_clause(effect_text)
    if look_top_x_put_permanents is not None:
        return look_top_x_put_permanents
    exile_top_n_put_from_among = _parse_exile_top_n_put_from_among_clause(effect_text)
    if exile_top_n_put_from_among is not None:
        return exile_top_n_put_from_among
    that_player_loses_life_searches = _parse_that_player_loses_life_searches_puts_in_hand_clause(
        effect_text, for_spell=False
    )
    if that_player_loses_life_searches is not None:
        return that_player_loses_life_searches
    mill_then_may_put_on_top = _parse_mill_then_may_put_on_top_clause(effect_text)
    if mill_then_may_put_on_top is not None:
        return mill_then_may_put_on_top
    mill_then_take_from_milled_ability = _parse_mill_then_may_take_from_milled_ability(effect_text)
    if mill_then_take_from_milled_ability is not None:
        return mill_then_take_from_milled_ability
    mill_then_put_all_from_milled_ability = _parse_mill_then_put_all_from_milled_ability(
        effect_text
    )
    if mill_then_put_all_from_milled_ability is not None:
        return mill_then_put_all_from_milled_ability
    reveal_top_n_put_random_kind = _parse_reveal_top_n_put_random_kind_clause(effect_text)
    if reveal_top_n_put_random_kind is not None:
        return reveal_top_n_put_random_kind
    search_put_battlefield_tapped_then_behold_untap = (
        _parse_search_put_battlefield_tapped_then_behold_untap_clause(effect_text)
    )
    if search_put_battlefield_tapped_then_behold_untap is not None:
        return search_put_battlefield_tapped_then_behold_untap
    # R0a-T2: Fabled Passage's own "... then shuffle. Then if you control
    # <n> or more lands, untap that land." - additive, see machines/
    # map_tokens.py.
    search_put_battlefield_tapped_then_count_lands_untap = (
        map_tokens.parse_search_put_battlefield_tapped_then_count_lands_untap_clause(effect_text)
    )
    if search_put_battlefield_tapped_then_count_lands_untap is not None:
        return search_put_battlefield_tapped_then_count_lands_untap
    look_top_card_conditional = _parse_look_top_card_conditional_clause(effect_text)
    if look_top_card_conditional is not None:
        return look_top_card_conditional
    damage_to_that_spells_controller = _parse_damage_to_that_spells_controller_clause(effect_text)
    if damage_to_that_spells_controller is not None:
        return damage_to_that_spells_controller
    discard_hand_draw_x = _parse_discard_hand_draw_x_clause(effect_text)
    if discard_hand_draw_x is not None:
        return discard_hand_draw_x
    pump_per_discard_then_delayed_draw = _parse_pump_per_discard_then_delayed_draw_clause(
        effect_text
    )
    if pump_per_discard_then_delayed_draw is not None:
        return pump_per_discard_then_delayed_draw
    each_opponent_skips_next_untap = _parse_each_opponent_skips_next_untap_clause(effect_text)
    if each_opponent_skips_next_untap is not None:
        return each_opponent_skips_next_untap
    hideaway = _parse_hideaway_clause(effect_text)
    if hideaway is not None:
        return hideaway
    hideaway_counter_then_free_cast = _parse_hideaway_counter_then_conditional_free_cast_clause(
        effect_text
    )
    if hideaway_counter_then_free_cast is not None:
        return hideaway_counter_then_free_cast
    target_opponent_draw_then_copy = _parse_target_opponent_draw_then_copy_that_spell_clause(
        effect_text
    )
    if target_opponent_draw_then_copy is not None:
        return target_opponent_draw_then_copy
    create_token_then_copy_spell_retargeted = _parse_create_token_then_copy_spell_retargeted_clause(
        effect_text
    )
    if create_token_then_copy_spell_retargeted is not None:
        return create_token_then_copy_spell_retargeted
    copy_that_spell_retargeted = _parse_copy_that_spell_retargeted_clause(effect_text)
    if copy_that_spell_retargeted is not None:
        return copy_that_spell_retargeted
    copy_next_spell_you_cast = _parse_copy_next_spell_you_cast_clause(effect_text)
    if copy_next_spell_you_cast is not None:
        return copy_next_spell_you_cast
    copy_next_instant_or_sorcery_you_cast = _parse_copy_next_instant_or_sorcery_you_cast_clause(
        effect_text
    )
    if copy_next_instant_or_sorcery_you_cast is not None:
        return copy_next_instant_or_sorcery_you_cast
    its_controller_may_pay_life_then_draw = _parse_its_controller_may_pay_life_then_draw_clause(
        effect_text
    )
    if its_controller_may_pay_life_then_draw is not None:
        return its_controller_may_pay_life_then_draw
    next_spell_cannot_be_countered = _parse_next_spell_cannot_be_countered_clause(effect_text)
    if next_spell_cannot_be_countered is not None:
        return next_spell_cannot_be_countered
    pay_any_life_then_draw = _parse_pay_any_life_then_draw_that_many_clause(effect_text)
    if pay_any_life_then_draw is not None:
        return pay_any_life_then_draw
    each_opponent_loses_life = _parse_each_opponent_loses_life_equal_to(effect_text)
    if each_opponent_loses_life is not None:
        return each_opponent_loses_life
    pump_for_each_color_spent = _parse_pump_for_each_color_spent_on_that_spell_clause(effect_text)
    if pump_for_each_color_spent is not None:
        return pump_for_each_color_spent
    same_is_true = mass_pump_conditions.same_is_true_effect(effect_text)
    if same_is_true is not None:
        return same_is_true
    mass_pump = _mass_pump_ability_effect(effect_text)
    if mass_pump is not None:
        return mass_pump
    where_x_is_continuous = _parse_where_x_is_continuous_effect(effect_text)
    if where_x_is_continuous is not None:
        return where_x_is_continuous
    tap_then_no_untap = _parse_tap_target_then_no_untap_clause(effect_text)
    if tap_then_no_untap is not None:
        return tap_then_no_untap
    tap_enchanted_then_unprepared = _parse_tap_enchanted_then_unprepared_clause(effect_text)
    if tap_enchanted_then_unprepared is not None:
        return tap_enchanted_then_unprepared
    copy_cast_spell = _parse_copy_cast_spell_clause(effect_text)
    if copy_cast_spell is not None:
        return copy_cast_spell
    move_counter = _parse_move_counter_clause(effect_text)
    if move_counter is not None:
        return move_counter
    pump_and_becomes_chosen_color = _parse_pump_and_becomes_chosen_color_clause(effect_text)
    if pump_and_becomes_chosen_color is not None:
        return pump_and_becomes_chosen_color
    self_keyword_grant_until_eot = _parse_self_keyword_grant_until_eot_clause(effect_text)
    if self_keyword_grant_until_eot is not None:
        return self_keyword_grant_until_eot
    protection_from_chosen_color = _parse_protection_from_chosen_color_clause(effect_text)
    if protection_from_chosen_color is not None:
        return protection_from_chosen_color
    becomes_chosen_color = _parse_becomes_chosen_color_clause(effect_text)
    if becomes_chosen_color is not None:
        return becomes_chosen_color
    put_exiled_target_onto_battlefield = _parse_put_exiled_target_onto_battlefield_clause(
        effect_text
    )
    if put_exiled_target_onto_battlefield is not None:
        return put_exiled_target_onto_battlefield
    hideaway_play = _parse_hideaway_play_clause(effect_text)
    if hideaway_play is not None:
        return hideaway_play
    token_copy_of_cost_exiled_card = _parse_create_token_copy_of_cost_exiled_card_clause(
        effect_text
    )
    if token_copy_of_cost_exiled_card is not None:
        return token_copy_of_cost_exiled_card
    exiled_card_owner_token = _parse_exiled_card_owner_creates_x_token_clause(effect_text)
    if exiled_card_owner_token is not None:
        return exiled_card_owner_token
    event_subject_pump = _parse_event_subject_pump_clause(effect_text)
    if event_subject_pump is not None:
        return event_subject_pump
    event_subject_variable_pump = _parse_event_subject_variable_pump_clause(effect_text)
    if event_subject_variable_pump is not None:
        return event_subject_variable_pump
    target_plus_x_minus_x = _parse_target_plus_x_minus_x_clause(effect_text)
    if target_plus_x_minus_x is not None:
        return target_plus_x_minus_x
    reveal_until_x_kind_put_any = _parse_reveal_until_x_kind_put_any_onto_battlefield_clause(
        effect_text
    )
    if reveal_until_x_kind_put_any is not None:
        return reveal_until_x_kind_put_any
    reveal_until_x_nonland_exile_per_color = _parse_reveal_until_x_nonland_exile_per_color_clause(
        effect_text
    )
    if reveal_until_x_nonland_exile_per_color is not None:
        return reveal_until_x_nonland_exile_per_color
    # TMT T7 (see that section, near the bottom of this file, for why each of
    # these is read whole rather than through the ordinary clause split).
    exile_several_then_return = _parse_exile_several_up_to_one_targets_then_return_clause(
        effect_text
    )
    if exile_several_then_return is not None:
        return exile_several_then_return
    exile_then_return_tapped_attacking = (
        _parse_exile_target_then_return_tapped_and_attacking_clause(effect_text)
    )
    if exile_then_return_tapped_attacking is not None:
        return exile_then_return_tapped_attacking
    exile_then_pay_or_else_return = _parse_exile_then_pay_or_else_return_clause(effect_text)
    if exile_then_pay_or_else_return is not None:
        return exile_then_pay_or_else_return
    draw_then_delayed_discard = _parse_draw_then_delayed_discard_at_random_clause(effect_text)
    if draw_then_delayed_discard is not None:
        return draw_then_delayed_discard
    mass_return_entered_this_turn = _parse_mass_return_entered_this_turn_clause(
        effect_text, for_spell=False
    )
    if mass_return_entered_this_turn is not None:
        return mass_return_entered_this_turn
    reflexive_may_exile_dead_self = _parse_reflexive_may_exile_dead_self_clause(
        effect_text, for_spell=False
    )
    if reflexive_may_exile_dead_self is not None:
        return reflexive_may_exile_dead_self
    return_target_and_same_name_from_graveyard = (
        _parse_return_target_and_same_name_from_graveyard_clause(effect_text, for_spell=False)
    )
    if return_target_and_same_name_from_graveyard is not None:
        return return_target_and_same_name_from_graveyard
    linked_exile_return_pair = _parse_linked_exile_return_pair_clause(effect_text)
    if linked_exile_return_pair is not None:
        return linked_exile_return_pair
    if_condition_exile_self_and_each = _parse_if_condition_exile_self_and_each_clause(
        effect_text, for_spell=False
    )
    if if_condition_exile_self_and_each is not None:
        # Read whole, ahead of `parse_mixed_effect`'s per-clause split:
        # `split_effect_clauses` cuts on a bare " and " regardless of the
        # comma already separating the leading "if" from the effect, and
        # slices "each artifact and creature your opponents control" into
        # three fragments none of which reads as a known clause on its own
        # (the same reason `_parse_draw_equal_to_sacrificed_creature_power_
        # then_discard_clause` above is read whole too).
        return if_condition_exile_self_and_each
    you_and_event_player_gain = _parse_you_and_event_player_gain_that_much_life_clause(
        effect_text, for_spell=False
    )
    if you_and_event_player_gain is not None:
        # Read whole, ahead of the splitter: "you and that player each gain
        # that much life" has a bare " and " of its own that `split_effect_
        # clauses` cuts clean through, leaving "you" on one side and "that
        # player each gain that much life" on the other, neither of which is
        # a clause any per-clause parser reads.
        return you_and_event_player_gain
    parsed = parse_mixed_effect(effect_text)
    if parsed is not None:
        return parsed
    put_then_grant_then_delayed = _parse_put_then_grant_then_delayed_whole_text(
        effect_text, for_spell=False
    )
    if put_then_grant_then_delayed is not None:
        return put_then_grant_then_delayed
    condition_instead = _parse_condition_instead_clause_for_ability(effect_text)
    if condition_instead is not None:
        return condition_instead
    damage_target_and_controller = _parse_damage_target_also_damages_controller_clause(effect_text)
    if damage_target_and_controller is not None:
        return damage_target_and_controller
    # "... deals N damage to target creature and each other creature that
    # shares a color with it / with the same name as that creature" -
    # `machines/damage_backrefs.py`.
    from ..damage_backrefs import damage_backref_ability_effect

    damage_backref = damage_backref_ability_effect(effect_text)
    if damage_backref is not None:
        return damage_backref
    composed = _compose_layer_effect_with_remainder_for_ability(effect_text)
    if composed is not None:
        return composed
    then_exile_self_and_return = _parse_then_exile_self_and_return_clause(effect_text)
    if then_exile_self_and_return is not None:
        return then_exile_self_and_return
    then_if_moved_this_way = _parse_then_if_moved_this_way_clause(effect_text)
    if then_if_moved_this_way is not None:
        return then_if_moved_this_way

    # CR 701.68's Blight as an ordinary resolving effect (not the cost
    # `machines/cost.py` already reads) - `machines/blight_effects.py`,
    # this round's own owner of every position it prints in. Imported here,
    # not at module load, to avoid the import cycle that module's own
    # `from .effects import ...` calls would otherwise close.
    from .. import blight_effects

    bare_blight = blight_effects.parse_bare_blight_ability_clause(effect_text)
    if bare_blight is not None:
        return bare_blight
    each_opponent_blights = blight_effects.parse_each_opponent_blights_clause(effect_text)
    if each_opponent_blights is not None:
        return each_opponent_blights
    target_opponent_blights = blight_effects.parse_target_opponent_blights_clause(effect_text)
    if target_opponent_blights is not None:
        return target_opponent_blights
    may_blight_then_copy_blighted = (
        blight_effects.parse_may_blight_then_copy_blighted_creature_clause(effect_text)
    )
    if may_blight_then_copy_blighted is not None:
        return may_blight_then_copy_blighted
    may_blight_then_reflexive = blight_effects.parse_may_blight_then_reflexive_clause(effect_text)
    if may_blight_then_reflexive is not None:
        return may_blight_then_reflexive
    target_gains_quoted_trigger = blight_effects.parse_target_gains_quoted_ability_until_eot_clause(
        effect_text
    )
    if target_gains_quoted_trigger is not None:
        return target_gains_quoted_trigger
    protection_from_each_color = (
        blight_effects.parse_protection_from_each_color_until_your_next_turn_clause(effect_text)
    )
    if protection_from_each_color is not None:
        return protection_from_each_color
    then_if_not_main_phase = blight_effects.parse_then_if_not_main_phase_clause(
        effect_text, for_spell=False
    )
    if then_if_not_main_phase is not None:
        return then_if_not_main_phase
    # The general CR 118.12 "you may `<action>`. If you [do|don't],
    # `<consequence>`." reader last, so every narrower "may ... if you
    # do/don't" reader above (sacrifice, discard, pay energy, pay mana, tap,
    # remove a counter) still gets first refusal at its own shape - this one
    # only ever runs when every one of those already failed.
    may_action_then_branch = blight_effects.parse_may_action_then_branch_clause(effect_text)
    if may_action_then_branch is not None:
        return may_action_then_branch

    unread_conditional = _unreadable_conditional_clause(effect_text, for_spell=False)
    if unread_conditional is not None:

        def conditional_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.conditional_clause_notices.append(
                ConditionalClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_conditional,
                )
            )

        return conditional_notice_only

    unread_search = _unreadable_search_description(effect_text)
    if unread_search is not None:

        def search_description_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.search_description_notices.append(
                SearchDescriptionNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_search,
                )
            )

        return search_description_notice_only

    unread_search_count = _unreadable_search_count(effect_text)
    if unread_search_count is not None:
        # Same notice class as `unread_search` above and, deliberately, the
        # same closure name: `scripts/sweep_pool.py` recognises a dispatcher
        # answer as "notice" (not "silent") by this exact name, and this is
        # the same kind of answer - a search this wave recognised the shape
        # of but could not run - for a different reason (the count, not the
        # description).
        def search_description_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.search_description_notices.append(
                SearchDescriptionNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_search_count,
                )
            )

        return search_description_notice_only

    # `_unreadable_cost_reference_clause` is on this side too, not only the
    # spell side: Birthing Ritual reads back "the sacrificed creature's mana
    # value" out of a *triggered* ability, and without this half of the pair
    # the ability was refused (correctly) in complete silence, which is the
    # exact failure mode `AnaphoricClauseNotice` exists to end. The asymmetry
    # was an oversight, not a decision - the notice's own docstring already
    # describes the shape without restricting it to spells.
    unread_anaphoric = _unreadable_anaphoric_clause(
        effect_text, for_spell=False
    ) or _unreadable_cost_reference_clause(effect_text)
    if unread_anaphoric is not None:

        def anaphoric_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_anaphoric,
                )
            )

        return anaphoric_notice_only

    unread_delayed = _unreadable_delayed_clause(effect_text, for_spell=False)
    if unread_delayed is not None:

        def delayed_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.delayed_clause_notices.append(
                DelayedClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_delayed,
                )
            )

        return delayed_notice_only

    unread_imprint = _unreadable_imprint_quality(effect_text)
    if unread_imprint is not None:

        def imprint_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.imprint_notices.append(
                ImprintNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_imprint,
                )
            )

        return imprint_notice_only

    unread_cast_permission = _unreadable_cast_permission_clause(effect_text, for_spell=False)
    if unread_cast_permission is not None:

        def cast_permission_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_cast_permission,
                )
            )

        return cast_permission_notice_only

    unread_hand_choice = _unreadable_unbounded_hand_choice_clause(effect_text, for_spell=False)
    if unread_hand_choice is not None:

        def unbounded_hand_choice_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_hand_choice,
                )
            )

        return unbounded_hand_choice_notice_only

    unread_event_player_target = _unreadable_event_player_target_clause(
        effect_text, for_spell=False
    )
    if unread_event_player_target is not None:

        def event_player_target_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_event_player_target,
                )
            )

        return event_player_target_notice_only

    unread_reflexive = _unreadable_reflexive_clause(effect_text)
    if unread_reflexive is not None:

        def reflexive_notice_only(game: "Game", ability: AbilityOnStack) -> None:
            game.reflexive_clause_notices.append(
                ReflexiveClauseNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=unread_reflexive,
                )
            )

        return reflexive_notice_only

    return None


#: All Is Dust: "Each player sacrifices all permanents they control that are
#: one or more colors." CR 701.21a's sacrifice, not CR 701.8a's destroy, so
#: CR 702.12b's indestructible never enters into it - the single easiest
#: thing to get wrong about this card.
_EACH_PLAYER_SACRIFICES_COLORED_RE = re.compile(
    r"^each player sacrifices all permanents they control that are one or more colors\.?$",
    re.IGNORECASE,
)


def _spell_effect_or_notice(effect_text: str) -> Effect | None:
    """The spell-side twin of `_ability_effect_or_notice`, for `effect_for`.

    The same `_is_layer_effect_text` fallback applies here: Tower Above's
    "Until end of turn, target creature gets +4/+4 and gains trample, wither,
    and ..." leads with its duration, which `split_effect_clauses`'s bare
    "and" cuts (twice) into fragments none of this wave's clause shapes read.
    Routing the whole text to `create_continuous_effect` instead reaches
    `parsed_layer_effects`, which reads its sentence whole (normalising the
    duration-first opening) and - since the granted keywords still are not
    all ones `_KNOWN_KEYWORDS` and a single-keyword grant can read - records a
    `LayerNotice` rather than the card doing nothing with no trace.
    """
    whole = _strip_non_effect_preamble(effect_text).strip()
    counter_resolution = _parse_counter_resolution_text(whole, for_spell=True)
    if counter_resolution is not None:
        return counter_resolution
    from ..becomes import becomes_spell_effect

    becomes = becomes_spell_effect(whole)
    if becomes is not None:
        return becomes
    from ..lose_abilities_destroy import lose_abilities_then_destroy_spell_effect

    lose_then_destroy = lose_abilities_then_destroy_spell_effect(whole)
    if lose_then_destroy is not None:
        return lose_then_destroy
    from ..spell_remainders_e5 import spell_sentence_sequence_effect

    multi_slot = spell_sentence_sequence_effect(whole)
    if multi_slot is not None:
        return multi_slot
    r0a_t5 = _r0a_t5_spell_effect(whole)
    if r0a_t5 is not None:
        return r0a_t5
    # Pre-split: a trailing win condition can carry its own "and" (Coalition
    # Victory's "a land of each basic land type and a creature of each
    # color"), which `split_effect_clauses` would cut in half.
    win_if = _parse_if_condition_you_win_the_game_clause(whole, for_spell=True)
    if win_if is not None:
        return win_if
    c02_t6 = _c02_t6_spell_effect(whole)
    if c02_t6 is not None:
        return c02_t6
    # ecl-T8: the spell-side twin of the same early, pre-split try above -
    # see its own comment for why "power and toughness" cannot survive
    # `split_effect_clauses`.
    put_permanent_from_hand = _parse_put_permanent_card_from_hand_clause(whole, for_spell=True)
    if put_permanent_from_hand is not None:
        return put_permanent_from_hand
    from ..infusion import infusion_spell_effect

    infused = infusion_spell_effect(whole)
    if infused is not None:
        return infused
    # TMT T7 proof printing: Echoing Return shares Rat King, Verminister's own
    # "and all other cards with the same name as that card" grouping, as a
    # spell rather than an activated ability.
    return_target_and_same_name_from_graveyard = (
        _parse_return_target_and_same_name_from_graveyard_clause(whole, for_spell=True)
    )
    if return_target_and_same_name_from_graveyard is not None:
        return return_target_and_same_name_from_graveyard  # type: ignore[return-value]
    exile_all_creatures_then_hand_refill = _parse_exile_all_creatures_then_hand_refill_clause(whole)
    if exile_all_creatures_then_hand_refill is not None:
        return exile_all_creatures_then_hand_refill
    source_relative = _source_relative_whole_text_spell_effect(whole)
    if source_relative is not None:
        return source_relative
    dealt_damage_this_way = _parse_dealt_damage_this_way_die_to_exile(whole)
    if dealt_damage_this_way is not None:
        return dealt_damage_this_way
    destroy_then_rider_if_type_destroyed = (
        _parse_destroy_target_then_rider_if_type_destroyed_clause(whole, for_spell=True)
    )
    if destroy_then_rider_if_type_destroyed is not None:
        return destroy_then_rider_if_type_destroyed  # type: ignore[return-value]
    create_tokens_then_instead_tapped_attacking = (
        _parse_create_tokens_then_instead_tapped_attacking_if_cost_paid_clause(whole)
    )
    if create_tokens_then_instead_tapped_attacking is not None:
        return create_tokens_then_instead_tapped_attacking
    prevent_dealt_by_target = _parse_prevent_damage_dealt_by_target_clause(whole)
    if prevent_dealt_by_target is not None:
        return prevent_dealt_by_target  # type: ignore[return-value]
    put_cards_that_died = _parse_put_cards_that_died_this_turn_clause(whole)
    if put_cards_that_died is not None:
        return put_cards_that_died
    exchange_control_clause = _parse_exchange_control_clause(whole)
    if exchange_control_clause is not None:
        return exchange_control_clause  # type: ignore[return-value]
    exile_card_then_token_copy = _parse_exile_card_then_token_copy_clause(whole, for_spell=True)
    if exile_card_then_token_copy is not None:
        return exile_card_then_token_copy
    damage_target_player_and_theirs = _parse_damage_target_player_and_their_creatures_clause(whole)
    if damage_target_player_and_theirs is not None:
        return damage_target_player_and_theirs
    cast_target_from_graveyard = _parse_cast_target_card_from_graveyard_clause(whole)
    if cast_target_from_graveyard is not None:
        return cast_target_from_graveyard
    target_attacks_if_able = _parse_target_attacks_if_able_clause(whole)
    if target_attacks_if_able is not None:
        return target_attacks_if_able
    target_blocks_self_if_able = _parse_target_blocks_self_if_able_clause(whole)
    if target_blocks_self_if_able is not None:
        return target_blocks_self_if_able
    created_trigger = _parse_created_trigger_spell_text(whole)
    if created_trigger is not None:
        return created_trigger
    created_replacement = _parse_created_replacement_spell_text(whole)
    if created_replacement is not None:
        return created_replacement
    created_replacement_then_rest = _parse_created_replacement_then_rest_spell_text(whole)
    if created_replacement_then_rest is not None:
        return created_replacement_then_rest
    draw_x_from_target_graveyard_from_library = (
        _parse_draw_x_from_target_graveyard_from_library_clause(whole)
    )
    if draw_x_from_target_graveyard_from_library is not None:
        return draw_x_from_target_graveyard_from_library
    copy_next_instant_or_sorcery_you_cast = (
        _parse_copy_next_instant_or_sorcery_you_cast_spell_clause(whole)
    )
    if copy_next_instant_or_sorcery_you_cast is not None:
        return copy_next_instant_or_sorcery_you_cast
    choose_target_owner_may_top_else_bottom = _parse_choose_target_owner_may_top_else_bottom_clause(
        whole, for_spell=True
    )
    if choose_target_owner_may_top_else_bottom is not None:
        return choose_target_owner_may_top_else_bottom
    choose_target_owner_shuffles_it = _parse_choose_target_owner_shuffles_it_clause(
        whole, for_spell=True
    )
    if choose_target_owner_shuffles_it is not None:
        return choose_target_owner_shuffles_it
    choose_creature_type_destroy_except = _parse_choose_creature_type_destroy_except_clause(
        whole, for_spell=True
    )
    if choose_creature_type_destroy_except is not None:
        return choose_creature_type_destroy_except
    each_sacrifices_then_if_you_did = _parse_each_sacrifices_then_if_you_did_clause(
        whole, for_spell=True
    )
    if each_sacrifices_then_if_you_did is not None:
        return each_sacrifices_then_if_you_did
    exile_if_mv_return_then_re_exile = _parse_exile_if_mv_return_then_re_exile_clause(
        whole, for_spell=True
    )
    if exile_if_mv_return_then_re_exile is not None:
        return exile_if_mv_return_then_re_exile
    switch_power_toughness_then_draw = _parse_switch_power_toughness_then_draw_clause(whole)
    if switch_power_toughness_then_draw is not None:
        return switch_power_toughness_then_draw
    delirium_damage_instead = _parse_delirium_damage_instead_clause(whole)
    if delirium_damage_instead is not None:
        return delirium_damage_instead
    choose_then_return = _parse_choose_targets_then_return_to_hand_pair(whole)
    if choose_then_return is not None:
        return choose_then_return
    choose_then_token_copies = _parse_choose_target_then_create_token_copies_pair(whole)
    if choose_then_token_copies is not None:
        return choose_then_token_copies
    token_copies_except = _parse_create_token_copies_except_clause(whole, for_spell=True)
    if token_copies_except is not None:
        return token_copies_except
    for_each_creature_target_player_copy = _parse_for_each_creature_target_player_copy_clause(
        whole, for_spell=True
    )
    if for_each_creature_target_player_copy is not None:
        return for_each_creature_target_player_copy
    for_each_creature_you_control_copy = _parse_for_each_creature_you_control_copy_clause(
        whole, for_spell=True
    )
    if for_each_creature_you_control_copy is not None:
        return for_each_creature_you_control_copy
    tokens_graveyard_cast_counters = _parse_create_tokens_graveyard_cast_counters_clause(whole)
    if tokens_graveyard_cast_counters is not None:
        return tokens_graveyard_cast_counters
    tokens_then_counter_other_subtype = _parse_create_tokens_then_counter_other_subtype_clause(
        whole
    )
    if tokens_then_counter_other_subtype is not None:
        return tokens_then_counter_other_subtype
    mass_gain_control = _parse_mass_gain_control_untap_clause(whole)
    if mass_gain_control is not None:
        return mass_gain_control
    return_as_creature = _parse_return_as_creature_clause(whole)
    if return_as_creature is not None:
        return return_as_creature
    untap_and_gain_control = _parse_untap_and_gain_control_clause(whole)
    if untap_and_gain_control is not None:
        return untap_and_gain_control
    # -- Wave W6's own whole-text additions, contiguous block -------------
    revolt_destroy = _parse_revolt_destroy_or_exile_clause(whole)
    if revolt_destroy is not None:
        return revolt_destroy
    converge_exile = _parse_converge_exile_by_colors_spent(whole)
    if converge_exile is not None:
        return converge_exile
    gain_life_if_color_spent = _parse_gain_life_if_color_spent_clause(whole)
    if gain_life_if_color_spent is not None:
        return gain_life_if_color_spent
    x_life_mass_debuff = _parse_x_life_mass_debuff(whole)
    if x_life_mass_debuff is not None:
        return x_life_mass_debuff
    x_life_return_types_mv_x = _parse_x_life_return_types_mv_x_clause(whole)
    if x_life_return_types_mv_x is not None:
        return x_life_return_types_mv_x
    exile_target_and_top_owner_may_play = _parse_exile_target_and_top_owner_may_play_clause(whole)
    if exile_target_and_top_owner_may_play is not None:
        return exile_target_and_top_owner_may_play
    # -- end Wave W6 whole-text additions -----------------------------------
    # -- sos-t2's own converge/Fractal/X-count whole-text additions --------
    converge_discard = _parse_converge_discard_by_colors_spent(whole)
    if converge_discard is not None:
        return converge_discard
    converge_damage_then_exile_excess = _parse_converge_damage_then_exile_excess_clause(whole)
    if converge_damage_then_exile_excess is not None:
        return converge_damage_then_exile_excess
    converge_fractal_tokens_and_life = _parse_converge_fractal_tokens_and_life_clause(whole)
    if converge_fractal_tokens_and_life is not None:
        return converge_fractal_tokens_and_life
    converge_draw_damage_life = _parse_converge_draw_damage_life_clause(whole)
    if converge_draw_damage_life is not None:
        return converge_draw_damage_life
    converge_draw_and_lose_life = _parse_converge_draw_and_lose_life_clause(whole)
    if converge_draw_and_lose_life is not None:
        return converge_draw_and_lose_life
    fractal_token_by_cards_drawn = _parse_fractal_token_by_cards_drawn_this_turn_clause(whole)
    if fractal_token_by_cards_drawn is not None:
        return fractal_token_by_cards_drawn
    power_of_two_draw = _parse_power_of_two_draw_clause(whole)
    if power_of_two_draw is not None:
        return power_of_two_draw
    tokens_then_counter_if_not_from_hand = _parse_tokens_then_counter_if_not_cast_from_hand_clause(
        whole
    )
    if tokens_then_counter_if_not_from_hand is not None:
        return tokens_then_counter_if_not_from_hand
    # -- end sos-t2 whole-text additions -------------------------------------
    citys_blessing_instead = _parse_citys_blessing_instead_clause(whole)
    if citys_blessing_instead is not None:
        return citys_blessing_instead
    kicked_choose_return = _parse_kicked_choose_return_delayed_clause(whole)
    if kicked_choose_return is not None:
        return kicked_choose_return
    counter_exile_may_cast = _parse_counter_exile_may_cast_free_clause(whole)
    if counter_exile_may_cast is not None:
        return counter_exile_may_cast
    face_down_exile_play = _parse_face_down_exile_play_clause(whole)
    if face_down_exile_play is not None:
        return face_down_exile_play
    look_top_split_conditional_instead = _parse_look_top_split_conditional_instead_clause(whole)
    if look_top_split_conditional_instead is not None:
        return look_top_split_conditional_instead
    condition_instead = _parse_condition_instead_clause(whole)
    if condition_instead is not None:
        return condition_instead
    gift_promised_return = _parse_gift_promised_return_instead_clause(whole)
    if gift_promised_return is not None:
        return gift_promised_return
    if _EACH_PLAYER_EXILE_SACRIFICE_RETURN_RE.fullmatch(whole):
        # Read whole, ahead of `parse_mixed_effect_for_spell`: the sentence's
        # own ", then " joins are CR 608.2c instructions in one breath, not
        # three clauses `_CLAUSE_SEPARATOR` may cut apart and fail separately.
        return each_player_exiles_sacrifices_and_returns_creatures
    may_discard_or_sacrifice = _parse_may_discard_or_sacrifice_if_you_do_clause(
        effect_text, for_spell=True
    )
    if may_discard_or_sacrifice is not None:
        return may_discard_or_sacrifice
    conditional_sacrifice = _parse_conditional_sacrifice_clause(effect_text, for_spell=True)
    if conditional_sacrifice is not None:
        return conditional_sacrifice
    mandatory_sacrifice_then_return = _parse_mandatory_sacrifice_then_return_to_hand_clause(
        effect_text, for_spell=True
    )
    if mandatory_sacrifice_then_return is not None:
        return mandatory_sacrifice_then_return
    may_exile_self_and_named_copies = _parse_may_exile_self_and_named_copies_if_you_do_clause(
        effect_text
    )
    if may_exile_self_and_named_copies is not None:
        return may_exile_self_and_named_copies
    target_energy_damage = _parse_target_get_energy_pay_damage(effect_text)
    if target_energy_damage is not None:
        return target_energy_damage
    x_energy_destroy = _parse_x_energy_pay_destroy_by_mana_value(effect_text)
    if x_energy_destroy is not None:
        return x_energy_destroy
    x_divided_damage_doubled = _parse_x_damage_divided_and_doubled_clause(effect_text)
    if x_divided_damage_doubled is not None:
        return x_divided_damage_doubled
    behold_chosen_type_search = _parse_behold_chosen_type_search_clause(effect_text, for_spell=True)
    if behold_chosen_type_search is not None:
        return behold_chosen_type_search
    shared_type_sacrifice = _parse_shared_type_sacrifice_clause(effect_text, for_spell=True)
    if shared_type_sacrifice is not None:
        return shared_type_sacrifice
    choose_type_return_from_graveyard = _parse_choose_type_return_from_graveyard_clause(
        effect_text, for_spell=True
    )
    if choose_type_return_from_graveyard is not None:
        return choose_type_return_from_graveyard
    choose_type_draw_per_permanent = _parse_choose_type_draw_per_permanent_clause(
        effect_text, for_spell=True
    )
    if choose_type_draw_per_permanent is not None:
        return choose_type_draw_per_permanent
    wanderwine_farewell = _parse_wanderwine_farewell_clause(effect_text, for_spell=True)
    if wanderwine_farewell is not None:
        return wanderwine_farewell
    damage_target_kicked_instead = _parse_damage_target_kicked_instead_clause(effect_text)
    if damage_target_kicked_instead is not None:
        return damage_target_kicked_instead
    damage_target_also_damages_controller = _parse_damage_target_also_damages_controller_clause(
        effect_text
    )
    if damage_target_also_damages_controller is not None:
        return damage_target_also_damages_controller
    choose_target_return_chosen_card = _parse_choose_target_return_chosen_card_clause(effect_text)
    if choose_target_return_chosen_card is not None:
        return choose_target_return_chosen_card
    reveal_top_n_may_battlefield_creature_teamwork = (
        _parse_reveal_top_n_may_battlefield_creature_teamwork_clause(effect_text)
    )
    if reveal_top_n_may_battlefield_creature_teamwork is not None:
        return reveal_top_n_may_battlefield_creature_teamwork
    damage_then_empower_if_excess = _parse_damage_then_empower_if_excess_clause(effect_text)
    if damage_then_empower_if_excess is not None:
        return damage_then_empower_if_excess
    cant_cast_kicked_attack = _parse_target_player_cant_cast_kicked_attack_clause(effect_text)
    if cant_cast_kicked_attack is not None:
        return cant_cast_kicked_attack
    destroy_two_targets = _parse_destroy_two_targets_clause(effect_text)
    if destroy_two_targets is not None:
        return destroy_two_targets
    tap_untap_two_targets = _parse_tap_untap_two_targets_clause(effect_text)
    if tap_untap_two_targets is not None:
        return tap_untap_two_targets
    if _CONTROL_REPLACEMENT_RE.fullmatch(whole):

        def control_replacement_notice_only(game: "Game", spell: CardState) -> None:
            game.control_replacement_notices.append(
                ControlReplacementNotice(
                    source_id=spell.id, source_name=spell.card.name, text=whole
                )
            )

        return control_replacement_notice_only
    bottom_hand_then_draw = _parse_bottom_hand_then_draw_plus_one_clause(effect_text)
    if bottom_hand_then_draw is not None:
        return bottom_hand_then_draw
    look_top_n_battlefield = _parse_look_top_n_may_battlefield_creature_bonus_clause(effect_text)
    if look_top_n_battlefield is not None:
        return look_top_n_battlefield
    select_from_top_spell = _parse_select_from_top_spell_clause(effect_text)
    if select_from_top_spell is not None:
        return select_from_top_spell
    if _EACH_PLAYER_SACRIFICES_COLORED_RE.fullmatch(whole):
        return each_player_sacrifices_colored_permanents
    destroy_each_then_add_mana = _parse_destroy_each_then_add_mana_per_destroyed(effect_text)
    if destroy_each_then_add_mana is not None:
        return destroy_each_then_add_mana
    destroy_each_for_spell = _parse_destroy_each_clause(whole)
    if destroy_each_for_spell is not None:
        return destroy_each_for_spell
    mass_pump_for_spell = _mass_pump_spell_effect(whole)
    if mass_pump_for_spell is not None:
        return mass_pump_for_spell
    flashback_grant = _parse_grant_flashback_clause(whole)
    if flashback_grant is not None:
        return flashback_grant
    tap_land_additional_mana = _parse_until_end_of_turn_tap_land_additional_mana_clause(whole)
    if tap_land_additional_mana is not None:
        return tap_land_additional_mana
    each_graveyard_flashback_grant = _parse_each_graveyard_instant_sorcery_gains_flashback_clause(
        whole
    )
    if each_graveyard_flashback_grant is not None:
        return each_graveyard_flashback_grant
    outside_the_game_play = _parse_outside_the_game_play_clause(whole)
    if outside_the_game_play is not None:
        return outside_the_game_play
    reveal_from_outside_into_hand = _parse_reveal_from_outside_the_game_into_hand_clause(whole)
    if reveal_from_outside_into_hand is not None:
        return reveal_from_outside_into_hand
    put_from_outside_into_hand = _parse_put_from_outside_the_game_into_hand_spell(whole)
    if put_from_outside_into_hand is not None:
        return put_from_outside_into_hand
    exile_hand_draw_then_play = _parse_exile_hand_draw_then_play_until_next_turn_clause(whole)
    if exile_hand_draw_then_play is not None:
        return exile_hand_draw_then_play
    # -- whole-text shapes whose sentences point back at one another -------
    return_then_conditional_draw = _parse_return_target_then_conditional_draw(whole)
    if return_then_conditional_draw is not None:
        return return_then_conditional_draw
    mill_then_take_from_milled = _parse_mill_then_may_take_from_milled(effect_text)
    if mill_then_take_from_milled is not None:
        return mill_then_take_from_milled
    mill_then_put_all_from_milled = _parse_mill_then_put_all_from_milled(effect_text)
    if mill_then_put_all_from_milled is not None:
        return mill_then_put_all_from_milled
    mill_then_return_to_hand = _parse_mill_then_return_to_hand_clause(effect_text)
    if mill_then_return_to_hand is not None:
        return mill_then_return_to_hand
    draw_then_discard_unless = _parse_draw_then_discard_unless(effect_text)
    if draw_then_discard_unless is not None:
        return draw_then_discard_unless
    look_top_lands_to_hand = _parse_look_top_lands_take_to_hand(effect_text)
    if look_top_lands_to_hand is not None:
        return look_top_lands_to_hand
    look_top_n_total_mv = _parse_look_top_n_put_total_mv_onto_battlefield(effect_text)
    if look_top_n_total_mv is not None:
        return look_top_n_total_mv
    return_up_to_n_total_mv_from_graveyard = (
        _parse_return_up_to_n_total_mv_from_graveyard_to_battlefield(effect_text)
    )
    if return_up_to_n_total_mv_from_graveyard is not None:
        return return_up_to_n_total_mv_from_graveyard
    # -- end whole-text shapes ---------------------------------------------
    if _DAMAGE_THEN_GROUP_TYPE_ABILITY_GRANT_RE.fullmatch(whole):

        def damage_then_group_grant_notice_only(game: "Game", spell: CardState) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(source_id=spell.id, source_name=spell.card.name, text=whole)
            )

        return damage_then_group_grant_notice_only
    # A narrow, local strip - not the full `whole` (`_strip_non_effect_
    # preamble` also drops reminder text and keyword-ability lines this
    # fallback needs untouched). Only the self cost-reduction preambles: an
    # unstripped one ahead of a real effect (Closing Statement's own "This
    # spell costs {2} less to cast during your end step.") is not a clause
    # any per-clause parser reads, so `_parse_mixed_clauses`' own fail-
    # closed-per-clause rule took the whole card down with it even though
    # every clause that actually resolves the spell read fine on its own.
    # (`_spell_effect_or_notice` is only ever reached for a non-permanent
    # spell now - CR 608.3's own resolving-permanent steps never call
    # `effect_for` at all - so the keyword-line caution the *fuller* strip
    # would need does not apply here regardless.)
    cost_reduction_stripped = _SELF_COST_REDUCTION_LINE_RE.sub("", effect_text)
    cost_reduction_stripped = _PER_COUNT_COST_REDUCTION_LINE_RE.sub("", cost_reduction_stripped)
    cost_reduction_stripped = _TIMING_COST_REDUCTION_LINE_RE.sub("", cost_reduction_stripped)
    parsed = parse_mixed_effect_for_spell(cost_reduction_stripped)
    if parsed is not None:
        return parsed
    composed = _compose_layer_effect_with_remainder(effect_text)
    if composed is not None:
        return composed
    put_then_grant_then_delayed = _parse_put_then_grant_then_delayed_whole_text(
        effect_text, for_spell=True
    )
    if put_then_grant_then_delayed is not None:
        return put_then_grant_then_delayed

    # CR 701.68's Blight as a spell effect (Dose of Dawnglow's own "Then if
    # it isn't your main phase, blight 2." tail) - see the ability-side hook
    # in `_ability_effect_or_notice` for why this is imported here.
    from .. import blight_effects

    bare_blight = blight_effects.parse_bare_blight_spell_clause(effect_text)
    if bare_blight is not None:
        return bare_blight
    then_if_not_main_phase = blight_effects.parse_then_if_not_main_phase_clause(
        effect_text, for_spell=True
    )
    if then_if_not_main_phase is not None:
        return then_if_not_main_phase

    unread_conditional = _unreadable_conditional_clause(effect_text, for_spell=True)
    if unread_conditional is not None:

        def conditional_notice_only(game: "Game", spell: CardState) -> None:
            game.conditional_clause_notices.append(
                ConditionalClauseNotice(
                    source_id=spell.id, source_name=spell.card.name, text=unread_conditional
                )
            )

        return conditional_notice_only

    unread_search = _unreadable_search_description(effect_text)
    if unread_search is not None:

        def search_description_notice_only(game: "Game", spell: CardState) -> None:
            game.search_description_notices.append(
                SearchDescriptionNotice(
                    source_id=spell.id, source_name=spell.card.name, text=unread_search
                )
            )

        return search_description_notice_only

    unread_search_count = _unreadable_search_count(effect_text)
    if unread_search_count is not None:
        # Same notice class and, deliberately, the same closure name as
        # `unread_search` right above - see that block's own comment on the
        # ability-dispatcher twin of this one.
        def search_description_notice_only(game: "Game", spell: CardState) -> None:
            game.search_description_notices.append(
                SearchDescriptionNotice(
                    source_id=spell.id, source_name=spell.card.name, text=unread_search_count
                )
            )

        return search_description_notice_only

    unread = _unreadable_anaphoric_clause(
        effect_text, for_spell=True
    ) or _unreadable_cost_reference_clause(effect_text)
    if unread is not None:

        def anaphoric_notice_only(game: "Game", spell: CardState) -> None:
            game.anaphoric_clause_notices.append(
                AnaphoricClauseNotice(source_id=spell.id, source_name=spell.card.name, text=unread)
            )

        return anaphoric_notice_only
    unread_delayed = _unreadable_delayed_clause(effect_text, for_spell=True)
    if unread_delayed is None:
        return None

    def delayed_notice_only(game: "Game", spell: CardState) -> None:
        game.delayed_clause_notices.append(
            DelayedClauseNotice(
                source_id=spell.id, source_name=spell.card.name, text=unread_delayed
            )
        )

    return delayed_notice_only


#: A looser prefix match for the same shape, used only by
#: `_unreadable_anaphoric_clause` to tell "this is recognisably a return-to-
#: battlefield sentence this wave cannot fully read" apart from "this is some
#: other second sentence entirely" - CR 608.2c has no notion of running half
#: of "exile ..., then return ...", so a card whose own wording falls outside
#: `_RETURN_TO_BATTLEFIELD_RE`'s three optional groups must still take the
#: whole effect down with it rather than silently keep only the exile half
#: (trap: an exile with nothing to return it is strictly worse than doing
#: nothing at all).
_LOOKS_LIKE_RETURN_TO_BATTLEFIELD_RE = re.compile(
    r"^return (?:it|that \w+) to the battlefield", re.IGNORECASE
)


def _unreadable_imprint_quality(text: str) -> str | None:
    """The `_HAND_EXILE_RE` clause inside `text`, if it matches CR 608.2d's
    "you may exile a `<quality>` card ... from your hand" shape but this
    wave's `_hand_exile_quality_matcher` cannot read the stated quality -
    used only to decide whether a parse failure deserves an `ImprintNotice`,
    the same way `_unreadable_anaphoric_clause` decides for its own shape.
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        match = _HAND_EXILE_RE.fullmatch(clause.strip().rstrip("."))
        if match is None:
            continue
        if _hand_exile_quality_matcher(match.group("quality")) is None:
            return clause
    return None


def _unreadable_conditional_clause(text: str, *, for_spell: bool) -> str | None:
    """The "you may sacrifice ... If you do, ..." clause inside `text`, if it
    matches CR 118.12's shape but `_parse_conditional_sacrifice_clause` still
    cannot read its restriction or consequence - used only to decide whether
    a parse failure deserves a `ConditionalClauseNotice`, the same way
    `_unreadable_imprint_quality` decides for its own shape.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _MAY_SACRIFICE_IF_YOU_DO_RE.fullmatch(whole)
    if match is not None:
        if _parse_conditional_sacrifice_clause(text, for_spell=for_spell) is not None:
            return None
        return whole
    return _unreadable_end_the_turn_clause(whole)


#: "If it's your turn, end the turn." - Day's Undoing's second sentence, read
#: for real by `end_the_turn_if_your_turn_effect` (`_parse_targeted_clause`,
#: reached through the ordinary per-clause dispatch ahead of everything
#: below). What is left here is `_unreadable_end_the_turn_clause`'s own use of
#: this same regex as a `ConditionalClauseNotice` detector for a card that
#: pairs this exact sentence with some *other* clause this wave still cannot
#: read - the per-clause parse of "if it's your turn, end the turn" alone
#: would succeed, but CR 608.2c's fail-closed-per-instruction rule still takes
#: the whole effect down with its unreadable sibling, and this is what names
#: the shape in the notice rather than leaving the whole card silent.
_END_THE_TURN_RE = re.compile(r"^if it'?s your turn, end the turn$", re.IGNORECASE)


def _unreadable_end_the_turn_clause(whole: str) -> str | None:
    """The "end the turn" clause inside `whole`, if there is one - see
    `_END_THE_TURN_RE`'s own docstring for why this still exists even though
    the clause itself now parses."""
    clauses = _prepare_effect_clauses(whole)
    if clauses is None:
        return None
    for clause in clauses:
        if _END_THE_TURN_RE.fullmatch(clause.strip().rstrip(".")):
            return clause.strip()
    return None


#: Any "`<action>`. When you do, `<consequence>`." shape at all, read only to
#: tell "not this shape" apart from "this shape, but unreadable" for
#: `_unreadable_reflexive_clause` - the same role `_MAY_SACRIFICE_IF_YOU_DO_RE`
#: plays for `_unreadable_conditional_clause`.
_REFLEXIVE_CLAUSE_RE = re.compile(
    r"^(?P<action>.+?)\.\s*when you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _unreadable_reflexive_clause(text: str) -> str | None:
    """The "`<action>`. When you do, `<consequence>`." clause inside `text`,
    if it matches CR 603.12's shape but `_parse_reflexive_sacrifice_clause`
    still cannot read it - used only to decide whether a parse failure
    deserves a `ReflexiveClauseNotice`, the same way `_unreadable_conditional_
    clause` decides for its own shape.
    """
    whole = _strip_non_effect_preamble(text).strip()
    match = _REFLEXIVE_CLAUSE_RE.fullmatch(whole)
    if match is None:
        return None
    if _parse_reflexive_sacrifice_clause(text) is not None:
        return None
    if _parse_reflexive_may_discard_clause(text) is not None:
        return None
    if _parse_reflexive_pay_energy_clause(text) is not None:
        return None
    if _parse_reflexive_mandatory_token_clause(text) is not None:
        return None
    return whole


#: "Look at target player's hand." (Gitaxian Probe, Peek) - the same CR 701.20e
#: look as `_LOOK_AT_TOP_CARD_RE`, except the thing looked at is a player's
#: hand rather than a library's top card, so `machines/targeting.py` reads
#: "target player's hand" as targeting the *player* (its own module-level
#: docstring lists this exact phrase as one it reads that way).
_LOOK_AT_TARGET_HAND_RE = re.compile(r"^look at target player'?s hand$", re.IGNORECASE)


# --------------------------------------------------------------------------
# The Ring tempts you (CR 701.54) - the same shape as amass just above: a CR
# 701 keyword action embedded in another ability's or spell's effect text
# (Gollum, Patient Plotter's "When Gollum leaves the battlefield, the Ring
# tempts you."; Claim the Precious' "Destroy target creature. The Ring tempts
# you."). `Game.ring_tempts` performs it.
# --------------------------------------------------------------------------

#: "the Ring tempts you" - optionally led by "then", the way Samwise the
#: Stouthearted and Rangers of Ithilien print it after another instruction.
_RING_TEMPTS_YOU_RE = re.compile(r"^(?:then,?\s+)?the ring tempts you$", re.IGNORECASE)


def _parse_ring_tempts_you_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "The Ring tempts you." as one clause among however many the card
    prints around it. It targets nothing (CR 701.54a's "choose a creature you
    control" is CR 608.2d's choice, asked by `Game.ring_tempts`), and "you"
    is the spell's or ability's controller, so the same clause works for a
    spell and an ability alike."""
    if _RING_TEMPTS_YOU_RE.fullmatch(clause.strip().rstrip(".")) is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        game.ring_tempts(
            game.controller_of(stack_object).username,
            source_name=source,
            source_id=source_id_of(stack_object),
        )

    return effect


# --------------------------------------------------------------------------
# Empower Jace (CR 701.71) - Reality Fracture's own keyword action, the same
# shape as earthbend and amass just above: embedded in another ability's or
# spell's effect text rather than a keyword ability of its own, so it lives
# here and not in `machines/keywords.py` (which is still told the word, see
# that module, so the pool sweeper does not report it as executed nowhere).
#
# CR 701.71a: "To empower Jace N means 'If you don't control a Jace
# planeswalker token, create a blue Jace planeswalker token with 0 loyalty,
# "[-1]: Surveil 1," and "[-3]: Draw a card." Choose a Jace planeswalker
# token you control. Put N loyalty counters on it.'"
#
# Three steps, all CR 608.2c instructions of one keyword action:
#
# - **the token, conditionally** - `models/token.py`'s `JACE` predefined
#   definition, created only when the controller controls none. The token is
#   never legendary (CR 306.4 retired the planeswalker uniqueness rule, and
#   the real `tfra` printing carries no Legendary supertype), so nothing
#   about creating it needs the legend rule; the "if you don't control one"
#   gate is the whole of what keeps a second one from appearing in ordinary
#   play.
# - **the choice** - "a Jace planeswalker token you control", never a Jace
#   planeswalker *card* (Jace, Reality Sculptor is a Jace but not a token,
#   and does not qualify either as the zero-token check or as a choice).
#   Not a target (CR 601.2c's word never appears), so it is a resolution-time
#   choice (CR 608.2d): the ordinary case is exactly one candidate (the token
#   this same instruction just made, or the sole one already there) and needs
#   no question at all; more than one - reachable only through some other
#   effect copying the token - asks `DecisionKind.CHOOSE_CARDS`, the same
#   question `_knowledge_pool_free_cast_effect` already asks for "choose one
#   of several cards".
# - **the counters** - `Game.add_counters`, which is also what lets Inspired
#   Tethermage's own "whenever you put one or more loyalty counters on a
#   planeswalker" trigger see them arrive.
# --------------------------------------------------------------------------

#: "Empower Jace N." or "Empower Jace X, where X is `<expr>`." - never
#: printed with the word "target" (CR 701.71a names no target at all), so
#: unlike earthbend this clause reads no targeting phrase, only the count.
_EMPOWER_JACE_RE = re.compile(
    rf"^empower jace {count_pattern('n', x=True)}{where_x_pattern()}$", re.IGNORECASE
)


def _parse_empower_jace_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Empower Jace N." or "Empower Jace X, where X is `<expr>`." - the
    whole of a spell's or an ability's effect text once any trigger
    condition has been split off, and one mode's own text once
    `parse_mode_effect` has substituted X and stripped its bullet.

    No target to resolve (unlike `_parse_earthbend_clause` just above), so
    this only has to read the stack object's controller, source and X for
    the "where X is ..." tail - through `_fixed_or_where_x_amount`, the same
    reader earthbend and amass use, so "the number of Islands you control"
    (Jace, Reality Sculptor's own `+1`), "the number of creatures you
    control" (Repurposed Enforcer) and "the number of creatures exiled this
    way" (Overwrite the Multiverse, through `count_expression`'s own
    "`<verb>` this way" reader) all already work with no code of their own.
    An "X" this cannot evaluate leaves the whole instruction unread
    (CR 608.2c) rather than empowering for zero.
    """
    match = _EMPOWER_JACE_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    reader = _fixed_or_where_x_amount(match.group("n"), match.group("where_x"))
    if reader is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if isinstance(stack_object, AbilityOnStack):
            controller = stack_object.controller
            source_id = stack_object.source_id
            source_name = stack_object.source_name
            x_value = stack_object.x_value
        else:
            controller = game.controller_of(stack_object).username
            source_id = stack_object.id
            source_name = stack_object.name
            x_value = 0
        source_state = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        )
        amount = reader(game, controller, source_state, x_value)
        empower_jace(game, amount, controller, source_id, source_name)

    return effect


#: The shape `ControlReplacementNotice` fails closed on.
_CONTROL_REPLACEMENT_RE = re.compile(
    r"^if a? ?[a-z]+ would enter the battlefield under an? [a-z' ]+'?s control"
    r"(?: this turn)?, it enters under [a-z' ]+ control instead\.?$",
    re.IGNORECASE,
)


def _unreadable_delayed_clause(text: str, *, for_spell: bool) -> str | None:
    """The first clause of `text` that names one of `ANAPHORIC_TIMING_STEPS`'s
    phrases, if `_prepare_effect_clauses` can split it out at all - used only
    to decide whether an effect this wave already failed to parse deserves a
    `DelayedClauseNotice`, not to parse it (the caller already tried and
    failed by the time this runs, exactly as `_unreadable_anaphoric_clause`'s
    caller does).
    """
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _parse_delayed_timing_clause(clause) is not None:
            return clause
    return None


#: "until end of turn, you may cast that card"/"you may cast it"/"you may cast
#: those cards" - the *orphaned* form of the sentence `_PLAY_PERMISSION_RE`
#: reads as half of `_parse_exile_then_play_permission_pair`. Reached only when
#: that pair parser refused, which for this sentence means one thing: the
#: clause in front of it is not an exiling clause this file can read, so there
#: is no antecedent for "that card" (CR 607.1) and no object to grant a
#: permission over. Granting nothing, or guessing at an object, is the silent
#: half-run the notice exists to prevent.
_CAST_PERMISSION_CLAUSE_RE = re.compile(
    r"^(?:(?:until end of turn|until the end of your next turn|until your next end step), )?"
    r"you may (?:cast|play) (?:it|that card|those cards|them)"
    r"(?: without paying (?:its|their) mana costs?)?"
    r"(?: this turn| until the end of your next turn| until your next end step)?$",
    re.IGNORECASE,
)

#: "you may put any number of ... into your hand" - a bare CR 608.2d choice
#: with nothing around it to say *which* cards are on offer.
#:
#: `Decision.exact=False` is the decision shape for CR 107.1c's "any number"
#: and always has been; what a lone clause of this wording lacks is the set to
#: choose from. Nashi, Searcher in the Dark's own second sentence says "from
#: among them", pointing back at the cards its first sentence milled, and is
#: read as one paragraph with them by
#: `_parse_mill_that_many_then_take_from_among_them` - so Nashi never reaches
#: this notice any more. A future card writing the clause with an antecedent
#: this file cannot read still fails closed here.
_UNBOUNDED_HAND_CHOICE_RE = re.compile(
    r"^you may put any number of .+ into your hand$", re.IGNORECASE
)

#: "target <type> that player controls" - Questing Beast's own tail, where
#: "that player" is whoever the trigger's own combat damage was dealt to
#: (CR 120.2a), not the ability's controller. `machines/targeting.
#: profile_for_text` only ever reads a targeting restriction off the
#: ability's own static printed text - "you control"/"an opponent controls"
#: against the *controller* - and has no way to restrict a target by what an
#: upstream game event says instead.
_EVENT_PLAYER_TARGET_RE = re.compile(r"target \w+(?:\s\w+)? that player controls", re.IGNORECASE)


def _unreadable_cast_permission_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` matching `_CAST_PERMISSION_CLAUSE_RE`, if any -
    used only to decide whether an effect this wave already failed to parse
    (via `parse_mixed_effect`) deserves an `UnmodeledTriggerEffectNotice`, the
    same "caller already tried and failed" contract every other `_unreadable_
    *_clause` function here keeps.

    Ability-only: a spell's dispatch is handed a permanent's whole printed text
    too (`effect_for`), where this sentence belongs to a triggered or activated
    ability that is judged on its own - reading it there would put a notice on
    Ragavan's or Ugin's resolution as a creature or planeswalker spell. Battle
    report B6-03 was a tap ability resolving with no permission and no notice.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _CAST_PERMISSION_CLAUSE_RE.fullmatch(clause.strip()):
            return clause
    return None


def _unreadable_unbounded_hand_choice_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` matching `_UNBOUNDED_HAND_CHOICE_RE`, if any - see
    `_unreadable_cast_permission_clause`'s docstring for the "already tried
    and failed" contract this shares.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _UNBOUNDED_HAND_CHOICE_RE.fullmatch(clause.strip()):
            return clause
    return None


def _unreadable_event_player_target_clause(text: str, *, for_spell: bool) -> str | None:
    """The clause of `text` containing `_EVENT_PLAYER_TARGET_RE`'s shape, if
    any - see `_unreadable_cast_permission_clause`'s docstring for the
    "already tried and failed" contract this shares. A `search`, not a
    `fullmatch`: the restriction is a tail of a larger sentence ("it deals
    that much damage to target planeswalker that player controls"), not a
    clause of its own.
    """
    if for_spell:
        return None
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    for clause in clauses:
        if _EVENT_PLAYER_TARGET_RE.search(clause):
            return clause
    return None


#: "Then exile that player's graveyard" - Go Blank's own second clause,
#: anaphoric to the same target its first clause (`_TARGET_PLAYER_DISCARDS_RE`)
#: already discarded into that graveyard. Reuses `exile_target_players_
#: graveyard` outright rather than a copy of it: that function already reads
#: the player off `game.resolve_targets(stack_object)`, which is exactly the
#: same target this clause means by "that player" - Go Blank prints only one
#: target for its whole text, so both clauses resolve it to the same `Player`.
#:
#: The printed "Then " is **not** in this pattern any more:
#: `split_effect_clauses` now strips a sentence-initial "then" for every card
#: (`_LEADING_THEN_RE`), so anchoring on it here would match nothing. Losing
#: the word is what generalises the shape - any card printing "Exile that
#: player's graveyard." as a plain second sentence reads the same way now,
#: where before only Go Blank's exact "Then exile ..." wording did.
_EXILE_THAT_PLAYERS_GRAVEYARD_RE = re.compile(r"^exile that player'?s graveyard$", re.IGNORECASE)


#: "Players can't gain life this turn." (Skullcrack), "Your opponents can't
#: gain life this turn." (Roiling Vortex, Atarka's Command) and "Damage can't
#: be prevented this turn." (Skullcrack, Stomp, Impractical Joke) - CR 611.1's
#: rules-of-the-game effects from a resolving spell or ability, recorded on
#: `Game.casting_rule_effects` (CR 611.2c: they apply to anything later in
#: the turn too) and dropped in the cleanup step (CR 514.2). CR 119.7 reads
#: the life-gain ban, CR 615.12 the prevention one.
_TURN_RULES_BAN_RE = re.compile(
    r"^(?:(?P<players>players)|(?P<opponents>your opponents)) can'?t gain life this turn\.?$"
    r"|^(?P<damage>damage) can'?t be prevented this turn\.?$",
    re.IGNORECASE,
)


def _parse_turn_rules_ban_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_TURN_RULES_BAN_RE`'s three shapes, as a recorded `CastingRuleEffect`."""
    match = _TURN_RULES_BAN_RE.fullmatch(clause.strip())
    if match is None:
        return None
    from ..casting_restrictions import CastingRuleEffect, CastingRuleKind

    if match.group("players"):
        kind = CastingRuleKind.PLAYERS_CANT_GAIN_LIFE
    elif match.group("opponents"):
        kind = CastingRuleKind.OPPONENTS_CANT_GAIN_LIFE
    else:
        kind = CastingRuleKind.DAMAGE_CANT_BE_PREVENTED

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source_name = (
            stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        )
        game.casting_rule_effects.append(
            CastingRuleEffect(
                kind=kind,
                controller=game.controller_of(stack_object).username,
                source_name=source_name,
            )
        )

    return effect


#: "You and target opponent each draw three cards." (Secret Rendezvous) and
#: "you and target opponent each draw a card." (Farsight Adept, Sky Crier,
#: Loran of the Third Path) - a compound subject (CR 608.2c), one instruction
#: carried out by each named player. The predicate is read by the ordinary
#: player-clause reader, once per player; CR 101.4 orders only *choices*, and
#: a draw has none, so the controller simply goes first.
_YOU_AND_TARGET_PLAYER_EACH_RE = re.compile(
    r"^you and (?P<phrase>target (?:player|opponent)) each (?P<predicate>.+?)\.?$",
    re.IGNORECASE,
)


def _parse_you_and_target_player_each_clause(clause: str) -> TargetedClause | None:
    """`_YOU_AND_TARGET_PLAYER_EACH_RE`'s shape, or `None`."""
    match = _YOU_AND_TARGET_PLAYER_EACH_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), allow_player_targets=True):
        return None
    predicate = parse_clause_effect(match.group("predicate").strip())
    if predicate is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        players = [game.controller_of(stack_object)]
        players.extend(
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        )
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        for player in players:
            predicate(game, player, source, source_id_of(stack_object))

    return effect


def _parse_mixed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """One clause of a mixed effect: the targeted shape first, then a token
    creation, then a search, then the imprint shape, then a delayed-trigger
    creation, then the plain player shape (CR 608.2c does not care which kind
    of instruction a card lists first, so no parser gets priority for any
    reason beyond "try this one, then the next").
    """
    # CR 701.68's Blight as an ordinary resolving effect - tried per clause
    # here (not only as a whole-text shape in `_ability_effect_or_notice`)
    # so a "blight N"/"you may blight N. If you do, ..." clause is also read
    # when it is one clause of a larger printed sentence, or when it is the
    # consequence half of another reader's own recursive `parse_mixed_
    # effect`/`parse_mixed_effect_for_spell` call (Dose of Dawnglow's own
    # "Then if it isn't your main phase, blight 2." tail).
    # `machines/blight_effects.py` is this round's own owner; imported here
    # rather than at module load to avoid its own `from .effects import ...`
    # closing an import cycle.
    from .. import blight_effects

    bare_blight = (
        blight_effects.parse_bare_blight_spell_clause(clause)
        if for_spell
        else blight_effects.parse_bare_blight_ability_clause(clause)
    )
    if bare_blight is not None:
        return bare_blight  # type: ignore[return-value]
    if not for_spell:
        each_opponent_blights = blight_effects.parse_each_opponent_blights_clause(clause)
        if each_opponent_blights is not None:
            return each_opponent_blights
        target_opponent_blights = blight_effects.parse_target_opponent_blights_clause(clause)
        if target_opponent_blights is not None:
            return target_opponent_blights
        may_blight_then_copy_blighted = (
            blight_effects.parse_may_blight_then_copy_blighted_creature_clause(clause)
        )
        if may_blight_then_copy_blighted is not None:
            return may_blight_then_copy_blighted
        may_blight_then_reflexive = blight_effects.parse_may_blight_then_reflexive_clause(clause)
        if may_blight_then_reflexive is not None:
            return may_blight_then_reflexive
        target_gains_quoted_trigger = (
            blight_effects.parse_target_gains_quoted_ability_until_eot_clause(clause)
        )
        if target_gains_quoted_trigger is not None:
            return target_gains_quoted_trigger
        protection_from_each_color = (
            blight_effects.parse_protection_from_each_color_until_your_next_turn_clause(clause)
        )
        if protection_from_each_color is not None:
            return protection_from_each_color
    then_if_not_main_phase = blight_effects.parse_then_if_not_main_phase_clause(
        clause, for_spell=for_spell
    )
    if then_if_not_main_phase is not None:
        return then_if_not_main_phase  # type: ignore[return-value]

    targeted = _parse_targeted_clause(clause, for_spell=for_spell)
    if targeted is not None:
        return targeted
    this_turn_spell_grant = _parse_this_turn_spell_grant_clause(clause, for_spell=for_spell)
    if this_turn_spell_grant is not None:
        return this_turn_spell_grant
    exile_other_tops = _parse_exile_top_of_other_libraries_clause(clause)
    if exile_other_tops is not None:
        return exile_other_tops
    each_player_exiles = _parse_each_player_exiles_until_clause(clause, for_spell=for_spell)
    if each_player_exiles is not None:
        return each_player_exiles
    play_exiled_with = _parse_play_a_card_exiled_with_clause(clause, for_spell=for_spell)
    if play_exiled_with is not None:
        return play_exiled_with
    poison_that_many = _parse_event_player_gets_that_many_poison_clause(clause, for_spell=for_spell)
    if poison_that_many is not None:
        return poison_that_many
    subject_controller_poison = parse_event_subject_controller_poison_clause(
        clause, for_spell=for_spell
    )
    if subject_controller_poison is not None:
        return subject_controller_poison
    each_player_attacked_loses = _parse_each_player_this_creature_attacked_loses_clause(
        clause, for_spell=for_spell
    )
    if each_player_attacked_loses is not None:
        return each_player_attacked_loses
    draw_the_difference = _parse_draw_the_difference_clause(clause, for_spell=for_spell)
    if draw_the_difference is not None:
        return draw_the_difference
    from ..player_control import parse_control_target_player_next_turn

    control_player = parse_control_target_player_next_turn(clause, for_spell=for_spell)
    if control_player is not None:
        return control_player
    shuffle_targets = _parse_shuffle_target_cards_into_library_clause(clause, for_spell=for_spell)
    if shuffle_targets is not None:
        return shuffle_targets
    shuffle_permanent_target = _parse_shuffle_target_permanent_into_library_clause(
        clause, for_spell=for_spell
    )
    if shuffle_permanent_target is not None:
        return shuffle_permanent_target
    prevent_all_to_you_next_turn = _parse_prevent_all_damage_to_you_until_next_turn_clause(clause)
    if prevent_all_to_you_next_turn is not None:
        return prevent_all_to_you_next_turn
    prevent_all_to_self = _parse_prevent_all_damage_to_self_this_turn_clause(
        clause, for_spell=for_spell
    )
    if prevent_all_to_self is not None:
        return prevent_all_to_self
    exile_self = _parse_exile_self_clause(clause, for_spell=for_spell)
    if exile_self is not None:
        return exile_self
    explores = _parse_explores_clause(clause, for_spell=for_spell)
    if explores is not None:
        return explores
    connives = parse_connive_clause(clause, for_spell=for_spell)
    if connives is not None:
        return connives
    loyalty_instant_speed = _parse_loyalty_instant_speed_clause(clause, for_spell=for_spell)
    if loyalty_instant_speed is not None:
        return loyalty_instant_speed
    proliferate = _parse_proliferate_clause(clause)
    if proliferate is not None:
        return proliferate
    token = _parse_token_clause(clause, for_spell=for_spell)
    if token is not None:
        return token
    that_many_color_pip_tokens = _parse_create_that_many_color_pip_tokens_clause(
        clause, for_spell=for_spell
    )
    if that_many_color_pip_tokens is not None:
        return that_many_color_pip_tokens
    damage_equal_to_that_spells_mv = _parse_damage_equal_to_that_spells_mv_clause(
        clause, for_spell=for_spell
    )
    if damage_equal_to_that_spells_mv is not None:
        return damage_equal_to_that_spells_mv
    if not for_spell:
        self_gains_quoted_ability = _parse_self_gains_quoted_ability_until_eot_clause(clause)
        if self_gains_quoted_ability is not None:
            return self_gains_quoted_ability
        self_pump_bare = _parse_bare_self_pump_until_eot_clause(clause)
        if self_pump_bare is not None:
            return self_pump_bare
        choose_new_targets_for_that_spell = _parse_choose_new_targets_for_that_spell_clause(clause)
        if choose_new_targets_for_that_spell is not None:
            return choose_new_targets_for_that_spell
        self_keyword_grant_until_eot = _parse_self_keyword_grant_until_eot_clause(clause)
        if self_keyword_grant_until_eot is not None:
            return self_keyword_grant_until_eot
        return_target_tapped_and_attacking = (
            _parse_return_target_from_graveyard_tapped_and_attacking_clause(
                clause, for_spell=for_spell
            )
        )
        if return_target_tapped_and_attacking is not None:
            return return_target_tapped_and_attacking
        return_that_card_to_owners_hand = _parse_return_that_card_to_owners_hand_clause(
            clause, for_spell=for_spell
        )
        if return_that_card_to_owners_hand is not None:
            return return_that_card_to_owners_hand
    mass_pump = _parse_mass_pump_group_clause(clause, for_spell=for_spell)
    if mass_pump is not None:
        return mass_pump
    target_player_creatures_pump = _parse_target_player_creatures_pump_clause(
        clause, for_spell=for_spell
    )
    if target_player_creatures_pump is not None:
        return target_player_creatures_pump
    mass_lose_all = _parse_mass_lose_all_abilities_clause(clause, for_spell=for_spell)
    if mass_lose_all is not None:
        return mass_lose_all
    spells_cant_be_countered = _parse_spells_cant_be_countered_clause(clause, for_spell=for_spell)
    if spells_cant_be_countered is not None:
        return spells_cant_be_countered
    turn_rules_ban = _parse_turn_rules_ban_clause(clause, for_spell=for_spell)
    if turn_rules_ban is not None:
        return turn_rules_ban
    you_and_group_gain = _parse_you_and_group_gain_clause(clause, for_spell=for_spell)
    if you_and_group_gain is not None:
        return you_and_group_gain
    you_and_target_player_each = _parse_you_and_target_player_each_clause(clause)
    if you_and_target_player_each is not None:
        return you_and_target_player_each
    target_player_creates = _parse_target_player_creates_clause(clause)
    if target_player_creates is not None:
        return target_player_creates
    named_token = _parse_named_token_clause(clause, for_spell=for_spell)
    if named_token is not None:
        return named_token
    variable_count_token = _parse_variable_count_token_clause(clause, for_spell=for_spell)
    if variable_count_token is not None:
        return variable_count_token
    self_fights_target = _parse_self_fights_target_clause(clause, for_spell=for_spell)
    if self_fights_target is not None:
        return self_fights_target
    enchanted_fights_target = _parse_enchanted_creature_fights_target_clause(
        clause, for_spell=for_spell
    )
    if enchanted_fights_target is not None:
        return enchanted_fights_target
    target_fights_target = _parse_target_fights_target_clause(clause, for_spell=for_spell)
    if target_fights_target is not None:
        return target_fights_target
    bite_damage = _parse_bite_damage_clause(clause, for_spell=for_spell)
    if bite_damage is not None:
        return bite_damage
    counter_each_other_creature = _parse_counter_each_other_creature_clause(
        clause, for_spell=for_spell
    )
    if counter_each_other_creature is not None:
        return counter_each_other_creature
    counter_each_attacked_this_turn = _parse_counter_each_attacked_this_turn_clause(clause)
    if counter_each_attacked_this_turn is not None:
        return counter_each_attacked_this_turn
    counter_each_creature_with_counter = _parse_counter_each_creature_with_counter_clause(
        clause, for_spell=for_spell
    )
    if counter_each_creature_with_counter is not None:
        return counter_each_creature_with_counter
    remove_all_counters_from_target = _parse_remove_all_counters_from_target_clause(clause)
    if remove_all_counters_from_target is not None:
        return remove_all_counters_from_target  # type: ignore[return-value]
    remove_up_to_n_counters_from_target = _parse_remove_up_to_n_counters_from_target_clause(clause)
    if remove_up_to_n_counters_from_target is not None:
        return remove_up_to_n_counters_from_target  # type: ignore[return-value]
    untap_all_group = _parse_untap_all_group_clause(clause, for_spell=for_spell)
    if untap_all_group is not None:
        return untap_all_group
    untap_each_subtype = _parse_untap_each_subtype_clause(clause, for_spell=for_spell)
    if untap_each_subtype is not None:
        return untap_each_subtype
    goad = _parse_goad_clause(clause, for_spell=for_spell)
    if goad is not None:
        return goad
    suspect_clause = _parse_suspect_clause(clause, for_spell=for_spell)
    if suspect_clause is not None:
        return suspect_clause
    venture_clause = _parse_venture_clause(clause, for_spell=for_spell)
    if venture_clause is not None:
        return venture_clause
    renown = _parse_renown_clause(clause, for_spell=for_spell)
    if renown is not None:
        return renown
    additional_combat_and_main_phase = _parse_additional_combat_and_main_phase_clause(clause)
    if additional_combat_and_main_phase is not None:
        return additional_combat_and_main_phase  # type: ignore[return-value]
    untap_all_attacking = _parse_untap_all_attacking_clause(clause)
    if untap_all_attacking is not None:
        return untap_all_attacking  # type: ignore[return-value]
    self_pump_for_each = _parse_self_pump_for_each_clause(clause)
    if self_pump_for_each is not None:
        return self_pump_for_each  # type: ignore[return-value]
    self_damage_equal_to_count = _parse_self_damage_equal_to_count_clause(
        clause, for_spell=for_spell
    )
    if self_damage_equal_to_count is not None:
        return self_damage_equal_to_count  # type: ignore[return-value]
    additional_combat_phase_only = _parse_additional_combat_phase_only_clause(clause)
    if additional_combat_phase_only is not None:
        return additional_combat_phase_only  # type: ignore[return-value]
    for_each_opponent_tap_then_stun = _parse_for_each_opponent_tap_then_stun_clause(
        clause, for_spell=for_spell
    )
    if for_each_opponent_tap_then_stun is not None:
        return for_each_opponent_tap_then_stun  # type: ignore[return-value]
    for_each_opponent_tap = _parse_for_each_opponent_tap_clause(clause, for_spell=for_spell)
    if for_each_opponent_tap is not None:
        return for_each_opponent_tap  # type: ignore[return-value]
    for_each_opponent_counters = _parse_for_each_opponent_counters_clause(
        clause, for_spell=for_spell
    )
    if for_each_opponent_counters is not None:
        return for_each_opponent_counters  # type: ignore[return-value]
    for_each_opponent_destroy = _parse_for_each_opponent_destroy_clause(clause, for_spell=for_spell)
    if for_each_opponent_destroy is not None:
        return for_each_opponent_destroy  # type: ignore[return-value]
    for_each_opponent_exile = _parse_for_each_opponent_exile_clause(clause, for_spell=for_spell)
    if for_each_opponent_exile is not None:
        return for_each_opponent_exile  # type: ignore[return-value]
    for_each_opponent_return_to_hand = _parse_for_each_opponent_return_to_hand_clause(
        clause, for_spell=for_spell
    )
    if for_each_opponent_return_to_hand is not None:
        return for_each_opponent_return_to_hand  # type: ignore[return-value]
    counter_each_creature_target_player = _parse_counter_each_creature_target_player_clause(
        clause, for_spell=for_spell
    )
    if counter_each_creature_target_player is not None:
        return counter_each_creature_target_player
    role_token = _parse_create_role_token_clause(clause, for_spell=for_spell)
    if role_token is not None:
        return role_token
    city_blessing_copy = _parse_city_blessing_token_copy_clause(clause, for_spell=for_spell)
    if city_blessing_copy is not None:
        return city_blessing_copy
    self_copy_token = _parse_self_copy_token_clause(clause, for_spell=for_spell)
    if self_copy_token is not None:
        return self_copy_token
    create_token_copy_of_target = _parse_create_token_copy_of_target_clause(
        clause, for_spell=for_spell
    )
    if create_token_copy_of_target is not None:
        return create_token_copy_of_target
    create_token_copy_of_quality_you_control = (
        _parse_create_token_copy_of_quality_you_control_clause(clause)
    )
    if create_token_copy_of_quality_you_control is not None:
        return create_token_copy_of_quality_you_control
    create_token_copies_except = _parse_create_token_copies_except_clause(
        clause, for_spell=for_spell
    )
    if create_token_copies_except is not None:
        return create_token_copies_except
    counter_on_additional_cost_card = _parse_counter_on_additional_cost_card_clause(clause)
    if counter_on_additional_cost_card is not None:
        return counter_on_additional_cost_card
    gain_life_equal_to_cost_card = _parse_gain_life_equal_to_additional_cost_card_clause(
        clause, for_spell=for_spell
    )
    if gain_life_equal_to_cost_card is not None:
        return gain_life_equal_to_cost_card
    each_player_may_discard_hand_draw = _parse_each_player_may_discard_hand_and_draw_clause(
        clause, for_spell=for_spell
    )
    if each_player_may_discard_hand_draw is not None:
        return each_player_may_discard_hand_draw
    if for_spell:
        # "Put two +1/+1 counters on each creature you control." as a spell
        # (Germination Practicum, Basri's Solidarity) - the ability-side read
        # below, with "you" the spell's own controller.
        spell_counters_on_group = _parse_put_counters_on_group_clause(clause, for_spell=True)
        if spell_counters_on_group is not None:
            return spell_counters_on_group  # type: ignore[return-value]
    if not for_spell:
        # "Put a +1/+1 counter on this creature." was reachable only as a
        # *whole* ability's effect (`_ability_effect_or_notice`), never as one
        # clause among several - so Kappa Cannoneer's "put a +1/+1 counter on
        # this creature. It can't be blocked this turn." had no readable
        # antecedent for its rider to attach to, and the pair failed on the
        # half that was already built. Spells are excluded because the effect
        # reads `AbilityOnStack.source`, and a sorcery is not a permanent that
        # can carry a counter anyway (CR 122.1).
        counters_on_self = _parse_put_counters_on_self_clause(clause)
        if counters_on_self is not None:
            return counters_on_self  # type: ignore[return-value]
        search_that_many_battlefield = _parse_search_that_many_battlefield_clause(
            clause, for_spell=for_spell
        )
        if search_that_many_battlefield is not None:
            return search_that_many_battlefield
        search_mv_less_than_self_power = _parse_search_mv_less_than_self_power_clause(
            clause, for_spell=for_spell
        )
        if search_mv_less_than_self_power is not None:
            return search_mv_less_than_self_power
        # "Put N counters on each `<group>` you control." was reachable only
        # as a *whole* ability's effect, the same gap `counters_on_self` just
        # above was closed for: Voja, Jaws of the Conclave's "put X +1/+1
        # counters on each creature you control, where X is the number of
        # Elves you control. Draw a card for each Wolf you control." is two
        # clauses, so the whole-text dispatcher's own direct call to this
        # parser (`fullmatch` against the *entire* two-sentence text) never
        # matches, and the ability silently did nothing.
        counters_on_group = _parse_put_counters_on_group_clause(clause)
        if counters_on_group is not None:
            return counters_on_group  # type: ignore[return-value]
        counters_on_named_group = _parse_counters_on_named_group_clause(clause)
        if counters_on_named_group is not None:
            return counters_on_named_group  # type: ignore[return-value]
        counters_equal_to = _parse_put_counters_equal_to_clause(clause)
        if counters_equal_to is not None:
            return counters_equal_to  # type: ignore[return-value]
        regenerate_self = _parse_regenerate_self_clause(clause)
        if regenerate_self is not None:
            return regenerate_self  # type: ignore[return-value]
        offspring_copy = _parse_offspring_token_copy_clause(clause)
        if offspring_copy is not None:
            return offspring_copy  # type: ignore[return-value]
        transform_self = _parse_transform_clause(clause)
        if transform_self is not None:
            return transform_self
        untap_self = _parse_untap_self_clause(clause)
        if untap_self is not None:
            return untap_self  # type: ignore[return-value]
        becomes_prepared_self = _parse_becomes_prepared_self_clause(clause)
        if becomes_prepared_self is not None:
            return becomes_prepared_self  # type: ignore[return-value]
        becomes_unprepared_self = _parse_becomes_unprepared_self_clause(clause)
        if becomes_unprepared_self is not None:
            return becomes_unprepared_self  # type: ignore[return-value]
        becomes_prepared_group = _parse_becomes_prepared_group_clause(clause)
        if becomes_prepared_group is not None:
            return becomes_prepared_group  # type: ignore[return-value]
        untap_named_self = _parse_untap_named_self_clause(clause)
        if untap_named_self is not None:
            return untap_named_self  # type: ignore[return-value]
    return_from_your_graveyard = _parse_return_cards_from_your_graveyard_clause(
        clause, for_spell=for_spell
    )
    if return_from_your_graveyard is not None:
        return return_from_your_graveyard
    return_a_card_at_random_from_graveyard = _parse_return_a_card_at_random_from_graveyard_clause(
        clause, for_spell=for_spell
    )
    if return_a_card_at_random_from_graveyard is not None:
        return return_a_card_at_random_from_graveyard
    transform_all = _parse_transform_all_subtype_clause(clause, for_spell=for_spell)
    if transform_all is not None:
        return transform_all
    search_hand_or_graveyard = _parse_search_hand_or_graveyard_clause(clause, for_spell=for_spell)
    if search_hand_or_graveyard is not None:
        return search_hand_or_graveyard
    draw_equal_to_target_hand = _parse_draw_cards_equal_to_target_hand_clause(
        clause, for_spell=for_spell
    )
    if draw_equal_to_target_hand is not None:
        return draw_equal_to_target_hand
    search = _parse_search_clause(clause, for_spell=for_spell)
    if search is not None:
        return search
    search_and_exile_then_shuffle = _parse_search_and_exile_then_shuffle_clause(
        clause, for_spell=for_spell
    )
    if search_and_exile_then_shuffle is not None:
        return search_and_exile_then_shuffle
    search_split_destination = _parse_search_split_destination_clause(clause, for_spell=for_spell)
    if search_split_destination is not None:
        return search_split_destination
    search_reveal_shuffle_top = _parse_search_reveal_shuffle_top_clause(clause, for_spell=for_spell)
    if search_reveal_shuffle_top is not None:
        return search_reveal_shuffle_top
    search_distinct_names = _parse_search_distinct_names_clause(clause, for_spell=for_spell)
    if search_distinct_names is not None:
        return search_distinct_names
    put_land_from_hand = _parse_put_land_from_hand_clause(clause, for_spell=for_spell)
    if put_land_from_hand is not None:
        return put_land_from_hand
    search_mv_lte_count = _parse_search_mv_lte_count_clause(clause, for_spell=for_spell)
    if search_mv_lte_count is not None:
        return search_mv_lte_count
    search_mv_equal_to_sacrificed = _parse_search_mv_equal_to_sacrificed_clause(
        clause, for_spell=for_spell
    )
    if search_mv_equal_to_sacrificed is not None:
        return search_mv_equal_to_sacrificed
    imprint = _parse_imprint_clause(clause, for_spell=for_spell)
    if imprint is not None:
        return imprint
    return_imprinted = _parse_return_imprinted_clause(clause, for_spell=for_spell)
    if return_imprinted is not None:
        return return_imprinted
    self_return = _parse_self_return_clause(clause, for_spell=for_spell)
    if self_return is not None:
        return self_return
    exile_dead_self = _parse_exile_dead_self_clause(clause, for_spell=for_spell)
    if exile_dead_self is not None:
        return exile_dead_self
    return_dead_self = _parse_return_dead_self_to_hand_clause(clause, for_spell=for_spell)
    if return_dead_self is not None:
        return return_dead_self
    dead_object_to_library = _parse_dead_object_to_library_clause(clause, for_spell=for_spell)
    if dead_object_to_library is not None:
        return dead_object_to_library
    owner_shuffles_graveyard = _parse_owner_shuffles_graveyard_into_library_clause(
        clause, for_spell=for_spell
    )
    if owner_shuffles_graveyard is not None:
        return owner_shuffles_graveyard
    tokens_equal_to_event_subject_stat = _parse_create_tokens_equal_to_event_subject_stat_clause(
        clause, for_spell=for_spell
    )
    if tokens_equal_to_event_subject_stat is not None:
        return tokens_equal_to_event_subject_stat
    sacrifice_self = _parse_sacrifice_self_clause(clause, for_spell=for_spell)
    if sacrifice_self is not None:
        return sacrifice_self
    delayed = _parse_delayed_single_clause(clause, for_spell=for_spell)
    if delayed is not None:
        return delayed
    airbend_clause = _parse_airbend_clause(clause, for_spell=for_spell)
    if airbend_clause is not None:
        return airbend_clause
    earthbend_clause = _parse_earthbend_clause(clause, for_spell=for_spell)
    if earthbend_clause is not None:
        return earthbend_clause
    amass_clause = _parse_amass_clause(clause, for_spell=for_spell)
    if amass_clause is not None:
        return amass_clause
    ring_tempts_clause = _parse_ring_tempts_you_clause(clause, for_spell=for_spell)
    if ring_tempts_clause is not None:
        return ring_tempts_clause
    blocker_sacrificed = _parse_blocking_creature_sacrificed_clause(clause, for_spell=for_spell)
    if blocker_sacrificed is not None:
        return blocker_sacrificed
    empower_jace_clause = _parse_empower_jace_clause(clause, for_spell=for_spell)
    if empower_jace_clause is not None:
        return empower_jace_clause
    investigate_clause = _parse_investigate_clause(clause, for_spell=for_spell)
    if investigate_clause is not None:
        return investigate_clause
    discover_clause = _parse_discover_clause(clause, for_spell=for_spell)
    if discover_clause is not None:
        return discover_clause
    learn_clause = _parse_learn_clause(clause, for_spell=for_spell)
    if learn_clause is not None:
        return learn_clause
    manifest_top_clause = _parse_manifest_top_card_clause(clause, for_spell=for_spell)
    if manifest_top_clause is not None:
        return manifest_top_clause
    manifest_dread_clause = _parse_manifest_dread_clause(clause, for_spell=for_spell)
    if manifest_dread_clause is not None:
        return manifest_dread_clause
    if_graveyard_count = _parse_if_graveyard_count_clause(clause, for_spell=for_spell)
    if if_graveyard_count is not None:
        return if_graveyard_count
    if_additional_cost_paid = _parse_if_additional_cost_paid_clause(clause, for_spell=for_spell)
    if if_additional_cost_paid is not None:
        return if_additional_cost_paid
    if_keyword_cost_paid = _parse_if_keyword_cost_paid_clause(clause, for_spell=for_spell)
    if if_keyword_cost_paid is not None:
        return if_keyword_cost_paid
    exile_that_players_library = _parse_exile_that_players_library_clause(
        clause, for_spell=for_spell
    )
    if exile_that_players_library is not None:
        return exile_that_players_library
    it_gains_rebound = _parse_it_gains_rebound_clause(clause, for_spell=for_spell)
    if it_gains_rebound is not None:
        return it_gains_rebound
    grant_enters_with_colors_spent = _parse_grant_enters_with_colors_spent_counters_clause(
        clause, for_spell=for_spell
    )
    if grant_enters_with_colors_spent is not None:
        return grant_enters_with_colors_spent
    they_gain_or_lose_life = _parse_they_gain_or_lose_life_clause(clause, for_spell=for_spell)
    if they_gain_or_lose_life is not None:
        return they_gain_or_lose_life
    that_permanent_no_untap = _parse_that_permanent_no_untap_clause(clause, for_spell=for_spell)
    if that_permanent_no_untap is not None:
        return that_permanent_no_untap
    distribute_counters = _parse_distribute_counters_among_targets_clause(
        clause, for_spell=for_spell
    )
    if distribute_counters is not None:
        return distribute_counters
    distribute_counters_you_control = _parse_distribute_counters_among_you_control_clause(clause)
    if distribute_counters_you_control is not None:
        return distribute_counters_you_control
    copy_that_spell = _parse_copy_that_spell_clause(clause, for_spell=for_spell)
    if copy_that_spell is not None:
        return copy_that_spell
    counter_that_spell = _parse_counter_that_spell_clause(clause, for_spell=for_spell)
    if counter_that_spell is not None:
        return counter_that_spell
    defending_player_exiles = _parse_defending_player_exiles_top_n_clause(
        clause, for_spell=for_spell
    )
    if defending_player_exiles is not None:
        return defending_player_exiles
    look_at_top_card = _parse_look_at_top_card_clause(clause)
    if look_at_top_card is not None:
        return look_at_top_card
    if _LOOK_AT_TARGET_HAND_RE.fullmatch(clause.strip()):
        return _look_at_target_hand
    # -- Wave W1's own single-clause additions, contiguous block ----------
    target_player_discards = _parse_target_player_discards_clause(clause, for_spell=for_spell)
    if target_player_discards is not None:
        return target_player_discards
    each_opponent_discards = _parse_each_opponent_discards_clause(clause, for_spell=for_spell)
    if each_opponent_discards is not None:
        return each_opponent_discards
    target_player_may_put_from_hand = _parse_target_player_may_put_card_from_hand_clause(
        clause, for_spell=for_spell
    )
    if target_player_may_put_from_hand is not None:
        return target_player_may_put_from_hand
    # `_parse_owner_puts_it_into_library_clause`'s single-clause shape is
    # already tried above through `_parse_targeted_clause`, this function's
    # very first check - a second call here could never be reached.
    target_player_draws = _parse_target_player_draws_clause(clause, for_spell=for_spell)
    if target_player_draws is not None:
        return target_player_draws
    target_player_becomes_monarch = _parse_target_player_becomes_monarch_clause(
        clause, for_spell=for_spell
    )
    if target_player_becomes_monarch is not None:
        return target_player_becomes_monarch
    n_target_players_each_draw = _parse_n_target_players_each_draw_clause(
        clause, for_spell=for_spell
    )
    if n_target_players_each_draw is not None:
        return n_target_players_each_draw
    target_player_shuffles = _parse_target_player_shuffles_clause(clause, for_spell=for_spell)
    if target_player_shuffles is not None:
        return target_player_shuffles
    target_player_sacrifices = _parse_target_player_sacrifices_clause(clause, for_spell=for_spell)
    if target_player_sacrifices is not None:
        return target_player_sacrifices
    if _EXILE_THAT_PLAYERS_GRAVEYARD_RE.fullmatch(clause.strip()):
        return exile_target_players_graveyard
    # -- end Wave W1 single-clause additions -------------------------------
    # -- CR 702.124j: "Partner with [name]" -------------------------------
    target_player_may_search_named_card = _parse_target_player_may_search_named_card_clause(
        clause, for_spell=for_spell
    )
    if target_player_may_search_named_card is not None:
        return target_player_may_search_named_card
    # -- end Partner with ---------------------------------------------------
    # -- Wave W11's own single-clause addition (CR 106.4, CR 605.1a) ------
    add_mana = _parse_add_mana_clause(clause, for_spell=for_spell)
    if add_mana is not None:
        return add_mana
    add_combination_mana = _parse_add_any_combination_mana_clause(clause, for_spell=for_spell)
    if add_combination_mana is not None:
        return add_combination_mana
    # -- end Wave W11 single-clause addition -------------------------------
    conditional_add_mana_equal_to = _parse_if_condition_add_mana_equal_to_clause(
        clause, for_spell=for_spell
    )
    if conditional_add_mana_equal_to is not None:
        return conditional_add_mana_equal_to
    # -- returning cards from a graveyard, and mass returns to hand --------
    return_self_from_graveyard = _parse_return_self_from_graveyard_to_battlefield_clause(
        clause, for_spell=for_spell
    )
    if return_self_from_graveyard is not None:
        return return_self_from_graveyard
    return_self_from_graveyard_attached = (
        _parse_return_self_from_graveyard_to_battlefield_attached_clause(
            clause, for_spell=for_spell
        )
    )
    if return_self_from_graveyard_attached is not None:
        return return_self_from_graveyard_attached
    return_self_transformed = _parse_return_self_to_battlefield_transformed_clause(
        clause, for_spell=for_spell
    )
    if return_self_transformed is not None:
        return return_self_transformed
    return_event_subject = _parse_return_event_subject_to_battlefield_clause(
        clause, for_spell=for_spell
    )
    if return_event_subject is not None:
        return return_event_subject
    self_owner_shuffles_self = _parse_self_owner_shuffles_self_into_library_clause(
        clause, for_spell=for_spell
    )
    if self_owner_shuffles_self is not None:
        return self_owner_shuffles_self
    if_condition_you_win_the_game = _parse_if_condition_you_win_the_game_clause(
        clause, for_spell=for_spell
    )
    if if_condition_you_win_the_game is not None:
        return if_condition_you_win_the_game
    if_condition_players_cant_cast = _parse_if_condition_players_cant_cast_clause(
        clause, for_spell=for_spell
    )
    if if_condition_players_cant_cast is not None:
        return if_condition_players_cant_cast
    mass_return_from_graveyard = _parse_mass_return_from_graveyard_to_battlefield_clause(
        clause, for_spell=for_spell
    )
    if mass_return_from_graveyard is not None:
        return mass_return_from_graveyard
    mass_return_from_graveyard_to_hand = _parse_mass_return_from_graveyard_to_hand_clause(
        clause, for_spell=for_spell
    )
    if mass_return_from_graveyard_to_hand is not None:
        return mass_return_from_graveyard_to_hand
    mass_return_to_hand = _parse_mass_return_to_hand_clause(clause, for_spell=for_spell)
    if mass_return_to_hand is not None:
        return mass_return_to_hand
    each_player_may_shuffle_hand_graveyard_then_draw = (
        parse_each_player_may_shuffle_hand_graveyard_then_draw_clause(clause, for_spell=for_spell)
    )
    if each_player_may_shuffle_hand_graveyard_then_draw is not None:
        # The whole sentence, unsplit - see `merge_each_player_may_shuffle_
        # hand_graveyard_then_draw_clauses`'s own docstring for why the
        # ordinary case never reaches this single-clause form at all.
        return each_player_may_shuffle_hand_graveyard_then_draw
    sacrifice_group = _parse_sacrifice_n_of_a_group_clause(clause, for_spell=for_spell)
    if sacrifice_group is not None:
        return sacrifice_group
    that_player_sacrifices = _parse_that_player_sacrifices_of_their_choice_clause(
        clause, for_spell=for_spell
    )
    if that_player_sacrifices is not None:
        return that_player_sacrifices
    sacrifice_of_their_choice = _parse_each_sacrifices_of_their_choice_clause(clause)
    if sacrifice_of_their_choice is not None:
        return sacrifice_of_their_choice
    target_opponent_sacrifice_greatest_mv = _parse_target_opponent_sacrifice_greatest_mv_clause(
        clause, for_spell=for_spell
    )
    if target_opponent_sacrifice_greatest_mv is not None:
        return target_opponent_sacrifice_greatest_mv
    attacking_tokens = _parse_attacking_token_clause(clause, for_spell=for_spell)
    if attacking_tokens is not None:
        return attacking_tokens
    recruit = _parse_recruit_clause(clause, for_spell=for_spell)
    if recruit is not None:
        return recruit
    that_player_mills_that_many = _parse_that_player_mills_that_many_clause(
        clause, for_spell=for_spell
    )
    if that_player_mills_that_many is not None:
        return that_player_mills_that_many
    copy_this_spell = _parse_copy_this_spell_clause(clause, for_spell=for_spell)
    if copy_this_spell is not None:
        return copy_this_spell
    choose_new_targets = _parse_choose_new_targets_clause(clause, for_spell=for_spell)
    if choose_new_targets is not None:
        return choose_new_targets
    change_target = _parse_change_target_clause(clause, for_spell=for_spell)
    if change_target is not None:
        return change_target
    put_from_hand_into_library = _parse_put_cards_from_hand_into_library_clause(
        clause, for_spell=for_spell
    )
    if put_from_hand_into_library is not None:
        return put_from_hand_into_library
    put_permanent_from_hand = _parse_put_permanent_card_from_hand_clause(
        clause, for_spell=for_spell
    )
    if put_permanent_from_hand is not None:
        return put_permanent_from_hand
    draw_equal_to_count = _parse_draw_cards_equal_to_count_clause(clause, for_spell=for_spell)
    if draw_equal_to_count is not None:
        return draw_equal_to_count
    return_self_to_hand = _parse_return_self_to_owners_hand_clause(clause, for_spell=for_spell)
    if return_self_to_hand is not None:
        return return_self_to_hand
    transform_self_later = _parse_transform_self_at_next_step_clause(clause, for_spell=for_spell)
    if transform_self_later is not None:
        return transform_self_later
    # -- end graveyard/return/token/keyword-action additions ----------------
    # -- Wave W6's own single-clause additions (Brotherhood's End's modes) -
    destroy_each = _parse_destroy_each_clause(clause)
    if destroy_each is not None:
        return destroy_each
    remove_all_counters_from_each = _parse_remove_all_counters_from_each_clause(clause)
    if remove_all_counters_from_each is not None:
        return remove_all_counters_from_each
    exile_each = _parse_exile_each_clause(clause)
    if exile_each is not None:
        return exile_each
    put_each_on_bottom = _parse_put_each_on_bottom_clause(clause)
    if put_each_on_bottom is not None:
        return put_each_on_bottom
    untap_all_you_control = _parse_untap_all_you_control_clause(clause)
    if untap_all_you_control is not None:
        return untap_all_you_control
    sacrifice_all_you_control = _parse_sacrifice_all_you_control_clause(clause)
    if sacrifice_all_you_control is not None:
        return sacrifice_all_you_control
    tap_all_group = _parse_tap_all_group_clause(clause)
    if tap_all_group is not None:
        return tap_all_group
    tap_attached = _parse_tap_attached_clause(clause)
    if tap_attached is not None:
        return tap_attached
    destroy_or_exile_attached = _parse_destroy_or_exile_attached_clause(clause)
    if destroy_or_exile_attached is not None:
        return destroy_or_exile_attached
    target_gains_ability_until_cast = _parse_target_gains_ability_until_cast_from_exile_clause(
        clause
    )
    if target_gains_ability_until_cast is not None:
        return target_gains_ability_until_cast
    self_cast_while_exiled = _parse_self_cast_while_exiled_clause(clause)
    if self_cast_while_exiled is not None:
        return self_cast_while_exiled
    damage_each_group = _parse_damage_each_group_clause(clause)
    if damage_each_group is not None:
        return damage_each_group
    damage_each_filtered = _parse_damage_each_filtered_clause(clause)
    if damage_each_filtered is not None:
        return damage_each_filtered
    # -- end Wave W6 single-clause additions --------------------------------
    # -- draw-if-you-control clause (Ral, Monsoon Mage's -2) ---------------
    draw_if_control = _parse_draw_if_you_control_color_permanent_clause(clause)
    if draw_if_control is not None:
        return draw_if_control
    # -- end draw-if-you-control clause --------------------------------------
    # -- plain "if <condition>, <consequence>" / "<consequence> if
    # <condition>" clause (G2a), tried only once every more specific reader
    # above - `draw_if_control` included, so Ral, Monsoon Mage's own colour
    # shape keeps its winner - and every whole-text "instead" reader has
    # already failed (see `_parse_condition_clause`'s own docstring) ------
    plain_condition = _parse_condition_clause(clause, for_spell=for_spell)
    if plain_condition is not None:
        return plain_condition
    # -- end plain if-condition clause ---------------------------------------
    # -- Wave W5's own single-clause addition (CR 611.1) -------------------
    casting_rule = parse_casting_rule_clause(clause, for_spell=for_spell)
    if casting_rule is not None:
        return casting_rule
    # -- end Wave W5 single-clause addition ---------------------------------
    if not for_spell:
        counter_on_trigger_subject = _parse_counter_on_trigger_subject_clause(clause)
        if counter_on_trigger_subject is not None:
            return counter_on_trigger_subject
        counter_on_it_trigger_subject = _parse_counter_on_it_trigger_subject_clause(clause)
        if counter_on_it_trigger_subject is not None:
            return counter_on_it_trigger_subject
        that_player = _parse_that_player_clause(clause, for_spell=for_spell)
        if that_player is not None:
            return that_player
        that_players_life_total_becomes = _parse_that_players_life_total_becomes_clause(
            clause, for_spell=for_spell
        )
        if that_players_life_total_becomes is not None:
            return that_players_life_total_becomes
        self_assigns_no_combat_damage = _parse_self_assigns_no_combat_damage_clause(
            clause, for_spell=for_spell
        )
        if self_assigns_no_combat_damage is not None:
            return self_assigns_no_combat_damage
    minus_counters_clause = _parse_minus_counters_mixed_clause(clause, for_spell=for_spell)
    if minus_counters_clause is not None:
        return minus_counters_clause
    player_clause = _parse_optional_player_clause(clause)
    if player_clause is None:
        # Last resort: a "you may" over a board instruction rather than over
        # the plain-player vocabulary `_parse_optional_player_clause` covers.
        mixed_or_hand = _parse_optional_mixed_clause(
            clause, for_spell=for_spell
        ) or _parse_may_put_card_from_hand_clause(clause, for_spell=for_spell)
        if mixed_or_hand is not None:
            return mixed_or_hand
        if for_spell:
            return None
        # The true last resort: the general CR 118.12 "you may `<action>`.
        # If you [do|don't], `<consequence>`." reader
        # (`machines/blight_effects.py`), tried only once every narrower "may
        # ... if you do/don't" reader in this whole dispatch chain - and
        # every other clause shape this function knows - has already
        # refused the text, so it never shadows a more specific reader's own
        # handling of the identical shape.
        from .. import blight_effects

        return blight_effects.parse_may_action_then_branch_clause(clause)  # type: ignore[return-value]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        player = game.controller_of(stack_object)
        source = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        player_clause(game, player, source, source_id_of(stack_object))

    return effect


def _parse_shared_subject_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every sentence of `text` read through `_parse_shared_subject_sentence`
    where that sentence opens one of the five subject shapes, and through
    the ordinary `_parse_mixed_clauses` pipeline (recursively, one sentence
    at a time) for any sentence that does not - `None` the moment either
    reading fails, or the text carries no shared-subject sentence at all.

    **The review fix this is** (T10/G7 round 2): the first cut of this
    reader required *every* sentence of the text to open with one of
    `_SHARED_SUBJECT_RE`'s five subject words before it would carry a
    subject across even one of them. That is stricter than the fail-open it
    was built to close actually needs: a shared-subject list sitting beside
    an *ordinary* bystander sentence that states no subject of its own at
    all - "Draw a card.", "Scry 1." (CR 701's own keyword-action
    imperatives, always the resolving spell's or ability's own controller by
    default, needing no stated subject to read correctly on their own) -
    fell through this reader entirely, and the list's own later items were
    right back where they started: reaching `_parse_optional_player_clause`
    at `_parse_mixed_clause`'s own last resort, whose "you " retry has no
    memory of the list's real subject and silently ran them against the
    resolving ability's own *controller* instead. `_parse_mixed_clauses(
    "Each opponent discards a card and loses 2 life. Draw a card.")` is the
    probe that found it: three clauses, with "loses 2 life" orphaned onto
    the controller exactly as it was before this reader existed at all.

    Splitting sentence-by-sentence instead of all-or-nothing closes that:
    every sentence that *does* open a shared-subject list is read by
    `_parse_shared_subject_sentence` (unchanged), so its own later items
    never reach the split-based per-clause dispatch that could orphan them
    in the first place, whatever sits beside it. A sentence that does not
    open one is read by recursing into `_parse_mixed_clauses` for that one
    sentence alone - exactly the reading it would already get as the whole
    text of a card with no shared-subject list at all, since a lone sentence
    never re-enters this function (the length check below returns `None`
    immediately for it, the same way the original all-or-nothing form did
    for a text with no matching sentence). Fail-closed still holds per
    sentence: any sentence, matched or not, that fails to parse fails the
    whole text (CR 608.2c's usual "no partial run of the instruction"), so
    this is strictly a widening of *which* texts this reader reaches, never
    a loosening of what counts as a read.

    Real cards never actually exercise the gap this widening closes -
    Archon of Cruelty, Arbiter of Woe, and Dusk Mangler all state "You ..."
    explicitly for their own controller's half, which is itself one of the
    five subject words and so already matched under the old all-or-nothing
    form. `tests/test_mixed_effects.py` pins the gap itself with a synthetic
    string (no real card in the fixture pool, or in a live Scryfall search
    for this shape, carries it); the fixture-pool, real-board proof that the
    underlying mechanism is correct remains those three cards' own scenario
    tests, unaffected since their own text was never routed through the new
    branch below.

    Tried only after every more specific whole-text merger already in
    `_parse_mixed_clauses` has had first refusal (see this function's own
    call site) - `_parse_target_player_draws_and_loses_life_clause`'s own
    two-item list among them keeps its own wording/decision-prompt exactly
    as before, since this more general reader never reaches a sentence that
    one already claimed.
    """
    sentences = _plain_resolution_sentences(text)
    if len(sentences) < 2:
        # A lone sentence gets no benefit from carrying a subject across
        # itself, and reading it here would recurse into `_parse_mixed_
        # clauses` for the identical text that called this function in the
        # first place - unchanged from the original all-or-nothing form,
        # which also read a single sentence through `_parse_shared_subject_
        # sentence` alone (never through this widened branch).
        if not sentences:
            return None
        effect = _parse_shared_subject_sentence(sentences[0], for_spell=for_spell)
        return [effect] if effect is not None else None
    has_shared_subject_sentence = any(
        _parse_shared_subject_sentence(sentence, for_spell=for_spell) is not None
        for sentence in sentences
    )
    if not has_shared_subject_sentence:
        # Nothing here opens a shared-subject list at all - leave the text
        # untouched for the rest of `_parse_mixed_clauses`' own pipeline,
        # exactly as the original all-or-nothing form already did.
        return None
    effects: list[TargetedClause] = []
    for sentence in sentences:
        effect = _parse_shared_subject_sentence(sentence, for_spell=for_spell)
        if effect is not None:
            effects.append(effect)
            continue
        bystander_effects = _parse_mixed_clauses(sentence, for_spell=for_spell)
        if bystander_effects is None:
            return None
        effects.extend(bystander_effects)
    return effects


#: Stone-Giant of High Pass's own token clause prints its keyword tail before
#: the name ("create a 3/1 colorless Wall artifact creature token with
#: defender named Stone Boulder"), the reverse of `_TOKEN_CLAUSE_RE`'s own
#: "token named `<Name>` with `<tail>`" order (Drowner of Truth and every
#: other pool printing so far). CR 111.9's naming and a keyword-tail clause
#: are two independent modifiers on the same "token" noun phrase, and Oracle
#: text is not consistent about which one it prints first, so this rewrites
#: the less common order into the one `_TOKEN_CLAUSE_RE` already reads rather
#: than teaching every one of that regex's many call sites a second name
#: group each. Applied once, ahead of every clause parser below, the same way
#: `_fold_following_token_grant` folds its own token-only rewrite in first.
_TOKEN_WITH_TAIL_THEN_NAMED_RE = re.compile(
    r"\btoken with (?P<tail>.+?) named (?P<name>[A-Z][\w' -]*?)(?=[.,]|$)", re.IGNORECASE
)


def _reorder_token_named_after_tail(text: str) -> str:
    """`_TOKEN_WITH_TAIL_THEN_NAMED_RE`'s rewrite; see the banner above."""

    def swap(match: re.Match[str]) -> str:
        return f"token named {match.group('name')} with {match.group('tail')}"

    return _TOKEN_WITH_TAIL_THEN_NAMED_RE.sub(swap, text)


def _parse_mixed_clauses(text: str, *, for_spell: bool) -> list[TargetedClause] | None:
    """Every clause of `text`, or `None` the moment one clause (or one
    anaphoric pair of clauses) matches nothing this wave reads.

    A run of two or more consecutive clauses is tried first, against several
    different shapes that are each one CR 608.2c instruction `split_effect_
    clauses` has cut apart on its own separators, not several independent
    ones: `_merge_continuous_pump_keyword_clauses` for "gets +N/+N and gains
    <keyword>" (Give In to Violence, CR 611.2), `_parse_anaphoric_clause_
    pair` for "destroy/exile target X. Its/that X's controller ..." (CR
    400.7), and `_parse_exile_then_return_clause_pair` for "exile target X,
    then return it to the battlefield ..." (Ephemerate). Only when a clause
    run opens none of these does it fall back to
    `_parse_mixed_clause`'s ordinary one-clause-at-a-time dispatch - Fatal
    Push's Revolt line is still read by neither and still takes the whole
    effect down with it.

    Fail-closed **per clause (or run), not per parser**: CR 608.2c has no
    notion of running half an effect, so a card with one clause nothing here
    reads still comes back `None` for the whole thing, exactly as
    `_parse_targeted_clauses` and `_parse_player_clauses` already refuse it
    alone.

    Tried first, against the whole unsplit `text`: `_parse_choose_name_
    search_and_exile_whole_text` (The Stone Brain, Surgical Extraction) -
    both cards' own "graveyard, hand, and library"/"with that name and exile
    them" wording carries a bare "and" `_CLAUSE_SEPARATOR` would otherwise
    cut into fragments no per-clause parser below could ever read back
    together, so this has to see the paragraph whole before anything splits
    it.
    """
    # CR 608.2c: a token's "It has "<ability>"" sentence is part of the token
    # the sentence before it created, folded into one token clause first.
    text = _fold_following_token_grant(text)
    text = _reorder_token_named_after_tail(text)
    shuffle_self_and_targets = _parse_shuffle_self_and_targets_into_owners_libraries_clause(
        text, for_spell=for_spell
    )
    if shuffle_self_and_targets is not None:
        # Read whole, ahead of the "and" clause split: "Shuffle this creature
        # **and** target `<X>` into their owners' libraries." (Floodpits
        # Drowner) has one CR 608.2c instruction whose own object list uses
        # the same bare "and" `_CLAUSE_SEPARATOR` would otherwise cut into
        # two fragments neither reads alone.
        return [shuffle_self_and_targets]
    exile_graveyard_then_creature_rider = _parse_exile_graveyard_then_creature_rider_clause(
        text, for_spell=for_spell
    )
    if exile_graveyard_then_creature_rider is not None:
        # Read whole, ahead of the sentence split: "Exile up to `<n>` target
        # card(s) from graveyards. If a/for each creature card was/exiled
        # this way, `<rider>`." (Graveyard Trespasser) is one CR 608.2c
        # instruction chain - the second sentence's own "this way" is
        # anaphora back to the first, exactly like every other reflexive
        # pair `split_effect_clauses` would otherwise cut apart.
        return [exile_graveyard_then_creature_rider]
    # Read whole: the second sentence's "It"/"That player" is the first
    # sentence's target, with a CR 611.2b duration tied to the source.
    for whole_text_reader in (
        _parse_remove_all_counters_then_cant_have_clause,
        _parse_player_loses_all_counters_clause,
        block_reassignment.parse_remove_blocker_then_it_blocks_another_clause,
    ):
        whole = whole_text_reader(text)
        if whole is not None:
            return [whole]
    destroy_amass_draw = _parse_destroy_then_amass_by_referent_then_draw_if_controlled_clause(
        text, for_spell=for_spell
    )
    if destroy_amass_draw is not None:
        # Read whole, ahead of the comma/clause split: a third sentence
        # chains off the same referent the second sentence's anaphora
        # already reads, which `_parse_mixed_clause`'s ordinary two-clause
        # pairing (`_parse_anaphoric_clause_pair`) has no room for.
        return [destroy_amass_draw]
    # R0a-T2: Magmatic Hellkite's own "Destroy target nonbasic land an
    # opponent controls. Its controller searches their library for a basic
    # land card, puts it onto the battlefield tapped with a stun counter on
    # it, then shuffles." - additive, see machines/map_tokens.py. Read whole
    # for the identical reason `destroy_amass_draw` above is: the second
    # sentence's own internal comma ("... tapped with a stun counter on it,
    # then shuffles") would otherwise be cut apart by the ordinary split,
    # which `_parse_anaphoric_clause_pair`'s two-clause pairing has no room
    # to rejoin.
    destroy_referent_search = map_tokens.parse_destroy_then_referent_mandatory_search_tapped_clause(
        text, for_spell=for_spell
    )
    if destroy_referent_search is not None:
        return [destroy_referent_search]
    may_sacrifice_damage_amass = _parse_may_sacrifice_then_damage_then_amass_if_excess_clause(
        text, for_spell=for_spell
    )
    if may_sacrifice_damage_amass is not None:
        # Read whole for the identical reason: the excess-damage sentence's
        # own anaphora ("this way") points back across two sentences, one of
        # them itself a CR 118.12 optional-cost check.
        return [may_sacrifice_damage_amass]
    if not for_spell:
        quest_counter_search = _parse_quest_counter_threshold_sacrifice_search_clause(text)
        if quest_counter_search is not None:
            # Read whole: four sentences chained by "if it has ...", "if you
            # do" and "if you search your library this way", none of them a
            # shape any per-clause parser below reads alone.
            return [quest_counter_search]  # type: ignore[list-item]
        create_then_threshold_sacrifice = (
            _parse_create_token_then_if_control_n_sacrifice_self_then_clause(text)
        )
        if create_then_threshold_sacrifice is not None:
            # Read whole: "Then if ..." and "If you do, ..." both chain off
            # sentences ahead of them that no per-clause parser below reads
            # as part of the same instruction.
            return [create_then_threshold_sacrifice]  # type: ignore[list-item]
        create_then_threshold_half_life = (
            _parse_create_token_then_if_control_n_that_player_half_life_clause(text)
        )
        if create_then_threshold_half_life is not None:
            # Read whole for the identical reason: "Then if ..." chains off
            # the token-creation sentence ahead of it, and "that player"
            # names the trigger's own event, not a subject any per-clause
            # parser below could resolve on its own.
            return [create_then_threshold_half_life]  # type: ignore[list-item]
    choose_two_draw_pump_trample = _parse_choose_exactly_two_draw_pump_trample_clause(
        text, for_spell=for_spell
    )
    if choose_two_draw_pump_trample is not None:
        # Read whole, ahead of the comma/clause split: "the chosen creatures"
        # in the second sentence is CR 608.2d anaphora back to the first
        # sentence's own choice, which no per-clause parser below has any
        # room to carry across a period.
        return [choose_two_draw_pump_trample]  # type: ignore[list-item]
    token_list = _parse_token_list_clause(text, for_spell=for_spell)
    if token_list is not None:
        return [token_list]
    target_gains_then_dies_token = _parse_target_gains_then_dies_this_turn_token_whole_text(
        text, for_spell=for_spell
    )
    if target_gains_then_dies_token is not None:
        # Read whole, ahead of the bare-"and" split - see that function's
        # own docstring for why "gains deathtouch and lifelink" cannot
        # survive `_prepare_effect_clauses` otherwise.
        return [target_gains_then_dies_token]
    target_player_creatures_pump_whole = _parse_target_player_creatures_pump_clause(
        text, for_spell=for_spell
    )
    if target_player_creatures_pump_whole is not None:
        # Read whole, ahead of the bare-"and" split, for the identical
        # reason: "get +1/+1 and gain haste" (Grub's Command's own mode)
        # carries the same bare "and" `_prepare_effect_clauses` cuts clean
        # through.
        return [target_player_creatures_pump_whole]
    search_or_else_token = token_riders.parse_search_or_else_create_token_clause(
        text, for_spell=for_spell
    )
    if search_or_else_token is not None:
        # Read whole, ahead of the comma/clause split: the second sentence's
        # "this way" is CR 118.12 anaphora straight back to the first
        # sentence's own search outcome, which no per-clause parser below
        # reads once the period has already cut the two apart.
        return [search_or_else_token]
    explores_whole_text = _parse_explores_clause(text, for_spell=for_spell)
    if explores_whole_text is not None:
        # Read whole, ahead of the comma/clause split, for the same reason
        # every other "X, then Y" shape below is: "it explores, then it
        # explores again" carries a bare ", then " `_CLAUSE_SEPARATOR` cuts
        # clean through (Jadelight Ranger, Over the Edge's second mode), and
        # the trailing fragment - "it explores again" - is not itself a
        # clause `_parse_mixed_clause` can read alone. A plain "it explores."
        # with nothing else on the card also matches here, before ever
        # reaching the splitter; one with a second, unrelated clause (Enter
        # the Unknown's own extra land drop) does not match the *whole*
        # text and falls through to the per-clause registration below.
        return [explores_whole_text]
    copy_target_spell_whole = _parse_copy_target_spell_clause(text, for_spell=for_spell)
    if copy_target_spell_whole is not None:
        return [copy_target_spell_whole]
    token_copy_of_target_whole = _parse_create_token_copy_of_target_clause(
        text, for_spell=for_spell
    )
    if token_copy_of_target_whole is not None:
        # Read whole: "It gains haste" and "Sacrifice it at the beginning of
        # the next end step" point back across the period at the token the
        # first sentence made (CR 608.2c), not at anything they name.
        return [token_copy_of_target_whole]
    from ..dies_this_turn import parse_then_when_that_creature_dies_this_turn
    from ..exile_until_casts import exile_until_casts_whole_text
    from ..stack_sweeps import parse_mass_stack_whole_text

    dies_this_turn = parse_then_when_that_creature_dies_this_turn(text, for_spell=for_spell)
    if dies_this_turn is not None:
        # Read whole: "that creature" and "its power" point back across the
        # period at the first sentence's target (`machines/dies_this_turn.py`).
        return [dies_this_turn]
    exile_until_casts = exile_until_casts_whole_text(text, for_spell=for_spell)
    if exile_until_casts is not None:
        # Read whole: "exiled this way"/"that card" point back across the
        # period at the exile-until sentence (`machines/exile_until_casts.py`).
        return [exile_until_casts]

    if not for_spell:
        from ..cast_copies import parse_that_spell_gains_clause

        # Read whole: "gains deathtouch and lifelink" carries the "and" the
        # clause splitter would cut (`machines/cast_copies.py`).
        that_spell_gains = parse_that_spell_gains_clause(text)
        if that_spell_gains is not None:
            return [that_spell_gains]
    mass_stack = parse_mass_stack_whole_text(text, for_spell=for_spell)
    if mass_stack is not None:
        # Read whole: "counter all spells ... and all abilities ..." and
        # "exile all other spells and counter all abilities" carry an "and"
        # the clause splitter would cut, and "countered this way" points back
        # across the period (`machines/stack_sweeps.py`).
        return [mass_stack]

    # R0a-T7 (`machines/spell_texts_r0a.py`): every one of these carries a
    # bare "and"/an anaphor across a sentence boundary the ordinary split
    # would cut - see that module's own docstring for why each is tried
    # whole rather than per clause.
    from .. import spell_texts_r0a

    same_name_destroy = spell_texts_r0a.parse_destroy_target_and_same_name_permanents_clause(
        text, for_spell=for_spell
    )
    if same_name_destroy is not None:
        return [same_name_destroy]
    same_name_return = spell_texts_r0a.parse_return_target_and_same_name_permanents_to_hands_clause(
        text, for_spell=for_spell
    )
    if same_name_return is not None:
        return [same_name_return]
    blocks_if_able = spell_texts_r0a.parse_target_blocks_if_able_then_may_gain_keyword_clause(
        text, for_spell=for_spell
    )
    if blocks_if_able is not None:
        return [blocks_if_able]
    token_with_quoted_ability = spell_texts_r0a.parse_token_with_quoted_ability_then_rest_clause(
        text, for_spell=for_spell
    )
    if token_with_quoted_ability is not None:
        return [token_with_quoted_ability]
    look_top_reveal_conditional = (
        spell_texts_r0a.parse_look_top_reveal_conditional_battlefield_clause(
            text, for_spell=for_spell
        )
    )
    if look_top_reveal_conditional is not None:
        return [look_top_reveal_conditional]
    return_distinct_mv = spell_texts_r0a.parse_return_from_graveyard_to_battlefield_distinct_clause(
        text, for_spell=for_spell
    )
    if return_distinct_mv is not None:
        return [return_distinct_mv]
    exiles_creature_and_graveyard = (
        spell_texts_r0a.parse_target_player_exiles_creature_and_graveyard_clause(
            text, for_spell=for_spell
        )
    )
    if exiles_creature_and_graveyard is not None:
        return [exiles_creature_and_graveyard]

    whole_text_effect = _parse_choose_name_search_and_exile_whole_text(text, for_spell=for_spell)
    if whole_text_effect is not None:
        return [whole_text_effect]
    mass_destroy_then_graveyard_hate = _parse_mass_destroy_then_conditional_graveyard_hate_clause(
        text, for_spell=for_spell
    )
    if mass_destroy_then_graveyard_hate is not None:
        return [mass_destroy_then_graveyard_hate]
    if for_spell:
        return_up_to_n_total_mv_from_graveyard = (
            _parse_return_up_to_n_total_mv_from_graveyard_to_battlefield(text)
        )
        if return_up_to_n_total_mv_from_graveyard is not None:
            return [return_up_to_n_total_mv_from_graveyard]
    exile_then_cast_types_effect = _parse_exile_top_then_cast_types_free_this_turn_whole_text(
        text, for_spell=for_spell
    )
    if exile_then_cast_types_effect is not None:
        return [exile_then_cast_types_effect]
    exile_then_play_during_resolution = _parse_exile_top_then_play_during_resolution_whole_text(
        text, for_spell=for_spell
    )
    if exile_then_play_during_resolution is not None:
        return [exile_then_play_during_resolution]
    look_top_cast_le_greatest_attacking_power = (
        _parse_look_top_cast_le_greatest_attacking_power_whole_text(text, for_spell=for_spell)
    )
    if look_top_cast_le_greatest_attacking_power is not None:
        return [look_top_cast_le_greatest_attacking_power]
    reveal_top_if_quality = _parse_reveal_top_card_if_quality_clause(text, for_spell=for_spell)
    if reveal_top_if_quality is not None:
        return [reveal_top_if_quality]
    draw_and_gain_off_sacrificed = _parse_draw_and_gain_off_sacrificed_clause(
        text, for_spell=for_spell
    )
    if draw_and_gain_off_sacrificed is not None:
        return [draw_and_gain_off_sacrificed]
    unsplittable_whole = _parse_unsplittable_whole_text(text, for_spell=for_spell)
    if unsplittable_whole is not None:
        return [unsplittable_whole]
    grant_then_return_front_face = _parse_grant_quoted_ability_then_return_front_face_whole_text(
        text, for_spell=for_spell
    )
    if grant_then_return_front_face is not None:
        return [grant_then_return_front_face]
    plural_target_gain_quoted_ability = _parse_plural_target_gain_quoted_ability_whole_text(
        text, for_spell=for_spell
    )
    if plural_target_gain_quoted_ability is not None:
        return [plural_target_gain_quoted_ability]
    each_sacrifices_then_if_you_did = _parse_each_sacrifices_then_if_you_did_clause(
        text, for_spell=for_spell
    )
    if each_sacrifices_then_if_you_did is not None:
        return [each_sacrifices_then_if_you_did]
    separate_into_two_piles = _parse_separate_into_two_piles_then_consequence_whole_text(
        text, for_spell=for_spell
    )
    if separate_into_two_piles is not None:
        return [separate_into_two_piles]
    look_top_face_down_face_up_piles = _parse_look_top_separate_face_down_face_up_piles_clause(
        text, for_spell=for_spell
    )
    if look_top_face_down_face_up_piles is not None:
        return [look_top_face_down_face_up_piles]
    each_discards_then_draw_per_shortfall = (
        _parse_each_opponent_discards_then_draw_per_shortfall_whole_text(text, for_spell=for_spell)
    )
    if each_discards_then_draw_per_shortfall is not None:
        return [each_discards_then_draw_per_shortfall]
    each_discards_then_shortfall_loses_life = (
        _parse_each_opponent_discards_then_shortfall_loses_life_whole_text(
            text, for_spell=for_spell
        )
    )
    if each_discards_then_shortfall_loses_life is not None:
        return [each_discards_then_shortfall_loses_life]
    each_chooses_creature_then_sacrifices_rest = (
        _parse_each_player_chooses_creature_then_sacrifices_rest_whole_text(
            text, for_spell=for_spell
        )
    )
    if each_chooses_creature_then_sacrifices_rest is not None:
        return [each_chooses_creature_then_sacrifices_rest]
    search_reveal_shuffle_top = _parse_search_reveal_shuffle_top_clause(text, for_spell=for_spell)
    if search_reveal_shuffle_top is not None:
        # Read whole, ahead of the comma/clause split, for the identical
        # reason the two whole-text parsers just above are: "reveal it, then
        # shuffle and put that card on top" carries a bare " and " that
        # `_CLAUSE_SEPARATOR` cuts clean through, leaving "shuffle" and "put
        # that card on top" as two fragments neither of which is a clause
        # `_parse_mixed_clause` can read alone.
        return [search_reveal_shuffle_top]
    search_split_destination_whole = _parse_search_split_destination_clause(
        text, for_spell=for_spell
    )
    if search_split_destination_whole is not None:
        # Read whole for the identical bare-"and" reason: "put one onto the
        # battlefield tapped and the other into your hand" (Troop of Ponies)
        # carries a bare " and " `_CLAUSE_SEPARATOR` cuts clean through,
        # leaving "the other into your hand" as a subjectless, verbless
        # fragment no per-clause parser can read alone.
        return [search_split_destination_whole]
    mill_then_take_from_milled_run = _mill_then_may_take_from_milled_runner(text)
    if mill_then_take_from_milled_run is not None:
        # Read whole, ahead of the comma/clause split, for the identical
        # bare-"and" reason `search_reveal_shuffle_top` just above is:
        # Smuggler's Surprise's own first Spree mode, "Mill four cards. You
        # may put up to two creature and/or land cards from among the
        # milled cards into your hand.", carries a bare " and " inside its
        # own quality list (`_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`'s "and/or"
        # widening) that `_CLAUSE_SEPARATOR` cuts clean through. This also
        # gives the runner its first path from a *mode's* own text at all -
        # `_parse_mill_then_may_take_from_milled`/`_ability` were reachable
        # only from the whole-card dispatchers (`_spell_effect_or_notice`/
        # `_ability_effect_or_notice`) before this, never from
        # `parse_mixed_effect_for_spell`/`parse_mixed_effect`, which is all
        # `parse_mode_effect` ever calls.
        def mill_then_take_from_milled_whole(game: "Game", stack_object: "StackObject") -> None:
            player = game.controller_of(stack_object)
            source = (
                stack_object.name  # type: ignore[union-attr]
                if for_spell
                else stack_object.source_name  # type: ignore[union-attr]
            )
            mill_then_take_from_milled_run(game, player, source, source_id_of(stack_object))

        return [mill_then_take_from_milled_whole]
    counter_threshold = _parse_counter_threshold_whole_text(text, for_spell=for_spell)
    if counter_threshold is not None:
        # Read whole: "on it" and "those counters" point back at the counter
        # sentence, and the consequence list's commas would split it apart.
        return [counter_threshold]
    two_counters_on_self = _parse_two_counters_on_self_clause(text, for_spell=for_spell)
    if two_counters_on_self is not None:
        # Read whole, ahead of the bare-"and" split, for the identical
        # reason every other whole-text case above it is - see
        # `_TWO_COUNTERS_ON_SELF_RE`'s own docstring.
        return [two_counters_on_self]
    counters_then_look_top_transform = (
        _parse_counters_then_look_top_may_battlefield_transform_clause(text, for_spell=for_spell)
    )
    if counters_then_look_top_transform is not None:
        # Read whole, ahead of the ", then "/period split, for the identical
        # reason - see `_COUNTERS_THEN_LOOK_TOP_MAY_BATTLEFIELD_TRANSFORM_
        # RE`'s own docstring.
        return [counters_then_look_top_transform]
    choose_odd_or_even_then_destroy = _parse_choose_odd_or_even_then_destroy_clause(
        text, for_spell=for_spell
    )
    if choose_odd_or_even_then_destroy is not None:
        # Read whole: "the chosen quality" in the second sentence is CR
        # 608.2c anaphora back to the first, which a per-clause parser
        # cannot resolve alone.
        return [choose_odd_or_even_then_destroy]
    choose_creature_copy_keywords = _parse_choose_creature_copy_keywords_clause(
        text, for_spell=for_spell
    )
    if choose_creature_copy_keywords is not None:
        # Read whole: "that creature" across every "do the same for ..."
        # repetition is CR 608.2c anaphora back to the first sentence's own
        # target, which no per-clause parser can resolve alone.
        return [choose_creature_copy_keywords]
    tap_all_pay_energy_counter_chosen = _parse_tap_all_pay_energy_counter_chosen_whole_text(
        text, for_spell=for_spell
    )
    if tap_all_pay_energy_counter_chosen is not None:
        # Read whole: four sentences carrying anaphora across all of them
        # ("that many", "tapped this way", "each of them").
        return [tap_all_pay_energy_counter_chosen]
    reveal_two_outside_opponent_chooses = _parse_reveal_two_outside_opponent_chooses_clause(
        text, for_spell=for_spell
    )
    if reveal_two_outside_opponent_chooses is not None:
        # Read whole: three sentences carrying anaphora across all of them
        # ("one of them" back to the two revealed cards, "that card" back to
        # the opponent's own choice), with no reading of any one sentence
        # alone.
        return [reveal_two_outside_opponent_chooses]
    search_library_and_outside_opponent_chooses = (
        _parse_search_library_and_outside_distinct_names_opponent_chooses_clause(
            text, for_spell=for_spell
        )
    )
    if search_library_and_outside_opponent_chooses is not None:
        # Read whole for the identical reason: "those cards"/"them"/"the
        # rest" all carry anaphora back to the one search this paragraph
        # performs.
        return [search_library_and_outside_opponent_chooses]
    target_player_draws_and_loses_life = _parse_target_player_draws_and_loses_life_clause(
        text, for_spell=for_spell
    )
    if target_player_draws_and_loses_life is not None:
        # Read whole for the same bare-"and" reason: "draws N cards and
        # loses N life" splits into a targeted clause and a subject-less
        # "loses N life" fragment that would otherwise land on the wrong
        # player.
        return [target_player_draws_and_loses_life]
    each_player_may_discard_hand_and_draw = _parse_each_player_may_discard_hand_and_draw_clause(
        " ".join(text.strip().split()), for_spell=for_spell
    )
    if each_player_may_discard_hand_and_draw is not None:
        # Read whole for the identical bare-"and" reason: "discard their
        # hand and draw seven cards" splits into two clause fragments,
        # neither of which `_parse_mixed_clause` can read alone.
        return [each_player_may_discard_hand_and_draw]
    if for_spell and _CONTINUOUS_PUMP_OR_KEYWORD_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).strip().split())
    ):
        # Read whole for the same reason the two above are: Echoing Courage's
        # subject, "Target creature and all other creatures with the same name
        # as that creature", carries a bare " and " that `_CLAUSE_SEPARATOR`
        # cuts through, leaving two fragments neither of which is a readable
        # clause. A single-sentence pump with no such "and" (Giant Growth)
        # reaches exactly the same `create_continuous_effect` one step earlier
        # than it used to, for the identical effect. `_strip_non_effect_
        # preamble` first, the same way every whole-text check above already
        # reads `whole = _strip_non_effect_preamble(text).strip()` before its
        # own regex - Aerial Formation's own leading "Strive — This spell
        # costs {2}{U} more to cast for each target beyond the first." is a
        # sibling *cost* sentence (CR 601.2f), never part of this one's own
        # shape, and this raw `text` (unlike the whole-text parsers' own
        # `whole`) was never stripped before reaching here.
        return [create_continuous_effect]  # type: ignore[list-item]
    mass_pump_group_whole = _parse_mass_pump_group_clause(
        " ".join(text.strip().split()), for_spell=for_spell
    )
    if mass_pump_group_whole is not None:
        # Read whole for the identical bare-"and" reason as the two blocks
        # above: Smuggler's Surprise's own third Spree mode, "Creatures you
        # control with power 4 or greater gain hexproof and indestructible
        # until end of turn.", carries a bare " and " between its two
        # granted keywords that `_CLAUSE_SEPARATOR` cuts clean through,
        # leaving "... gain hexproof" and "indestructible until end of
        # turn." as two fragments neither of which `_parse_mixed_clause`
        # can read alone - a single-keyword grant with no such "and"
        # (Gustrider Exuberant's "gain flying") already survived the split
        # intact and reaches this same reader one step later, in the
        # ordinary per-clause dispatch `_parse_mass_pump_group_clause`
        # itself already documents.
        return [mass_pump_group_whole]
    # Riveteers Charm's own mode one ("... with the greatest mana value
    # among creatures and planeswalkers they control.") is a single sentence
    # whose own internal "and" the ordinary clause split would still cut
    # through - tried whole here for the identical reason, ahead of any
    # sentence-count branch.
    greatest_mv_sacrifice_whole = _parse_target_opponent_sacrifice_greatest_mv_clause(
        text, for_spell=for_spell
    )
    if greatest_mv_sacrifice_whole is not None:
        return [greatest_mv_sacrifice_whole]
    shared_subject_clauses = _parse_shared_subject_clauses(text, for_spell=for_spell)
    if shared_subject_clauses is not None:
        # G7: read whole, ahead of the comma/"and" clause split, for the
        # same reason every whole-text try above it is - see `_parse_shared_
        # subject_clauses`'s own docstring for the fail-open this closes.
        return shared_subject_clauses
    effect_sentences = _plain_resolution_sentences(_strip_non_effect_preamble(text))
    if len(effect_sentences) == 3:
        # Cling to Dust's "... If it was a creature card, ... Otherwise, ..."
        # - three sentences, one instruction, read whole; its escape line is
        # a keyword, not part of the resolution, so it is stripped first.
        if_it_was = _parse_if_it_was_quality_card_otherwise_triple(
            *effect_sentences, for_spell=for_spell
        )
        if if_it_was is not None:
            return [if_it_was]
    sentences = _plain_resolution_sentences(text)
    if len(sentences) == 2:
        # Tried whole, ahead of the comma/and clause split, for the same
        # reason the `_CONTINUOUS_PUMP_OR_KEYWORD_RE` case just above is:
        # Tethermage's Advantage's own antecedent, "Target creature gets
        # +2/+2 and gains reach until end of turn.", is cut by
        # `_CLAUSE_SEPARATOR`'s bare "and" into two clause fragments before
        # `_parse_object_anaphor_clause_pair` ever gets a two-clause window
        # where the first element is the *whole* antecedent sentence - by
        # the time the loop below reaches the rider ("Untap it."), the
        # pump-keyword merge has already consumed the antecedent's own
        # fragments into a callable, leaving no text behind to pair it with.
        # Every other object-anaphor pair already in the pool (Kaito's own
        # "Tap target creature. Put two stun counters on it.") is exactly
        # two sentences with no internal "and" to begin with, so reading the
        # sentences whole here changes nothing for them - it only reaches
        # the compound-antecedent shape the finer split could never recover.
        anaphor_pair = (
            _parse_object_anaphor_clause_pair(sentences[0], sentences[1], for_spell=for_spell)
            or _parse_token_then_object_anaphor_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_choose_then_object_anaphor_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_draw_equal_to_then_lose_life_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_target_player_discards_then_play_land_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_each_group_discards_then_consequence_per_failure_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_if_target_card_quality_rider_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_if_it_was_target_card_quality_rider_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
            or _parse_distribute_counters_then_targets_gain_clause_pair(
                sentences[0], sentences[1], for_spell=for_spell
            )
        )
        if anaphor_pair is not None:
            return [anaphor_pair]
        # Break Under Pressure's own first sentence, read whole for the
        # identical reason: "creatures and planeswalkers they control"
        # carries a bare "and" the ordinary clause split would cut through,
        # leaving no readable fragment for `_TARGET_OPPONENT_SACRIFICE_
        # GREATEST_MV_RE` to match. The second sentence ("You gain 2 life.")
        # has no such "and" and reads through the ordinary per-clause path.
        greatest_mv_sacrifice = _parse_target_opponent_sacrifice_greatest_mv_clause(
            sentences[0], for_spell=for_spell
        )
        if greatest_mv_sacrifice is not None:
            rest = _parse_mixed_clause(sentences[1], for_spell=for_spell)
            if rest is not None:
                return [greatest_mv_sacrifice, rest]
        # Eye of Jace's own second sentence, read whole for the identical
        # reason: "sacrifice this artifact, it deals 2 damage to each
        # opponent, and you gain 2 life" carries a bare ", and" the ordinary
        # top-level clause split would cut through, severing the last
        # instruction from `_IF_GRAVEYARD_COUNT_RE`'s own "rest" before
        # `_parse_if_graveyard_count_clause` ever sees it whole.
        first_clause = _parse_mixed_clause(sentences[0], for_spell=for_spell)
        if first_clause is not None:
            second_sentence = re.sub(r"^then\s+", "", sentences[1].strip(), flags=re.IGNORECASE)
            conditional = _parse_if_graveyard_count_clause(second_sentence, for_spell=for_spell)
            if conditional is not None:
                return [first_clause, conditional]
    elif len(sentences) >= 3:
        # Teyo, Lightshield Expert's own three-sentence ETB: an antecedent
        # ("target permanent you control gains hexproof until end of turn.")
        # followed by *two* independent riders naming the same referent
        # ("Put a +1/+1 counter on it if it's a creature." / "Put a loyalty
        # counter on it if it's a planeswalker."), read whole for the
        # identical reason the two-sentence case just above is - reached
        # only once the exactly-two-sentence shapes above have already
        # failed to match, so it never steals a genuine two-clause pair.
        series = _parse_object_anaphor_clause_series(
            sentences[0], sentences[1:], for_spell=for_spell
        )
        if series is not None:
            return [series]
    clauses = _prepare_effect_clauses(text)
    if clauses is None:
        return None
    parsed: list[TargetedClause] = []
    index = 0
    while index < len(clauses):
        merged = _merge_continuous_pump_keyword_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_prevent_damage_from_target_clauses(clauses, index)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_split_damage_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_destroy_then_damage_controller_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_self_pump_and_group_keyword_grant_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_damage_any_target_then_destroy_if_type_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_add_any_combination_mana_with_restriction_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_delayed_blink_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_exile_any_number_of_your_permanents_then_delayed_return_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_delayed_token_copy_of_it_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- Wave W1's own multi-clause merges, contiguous block -----------
        merged = _merge_reveal_hand_choose_discard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_search_hand_shuffle_then_discard_random_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_damage_target_then_reveal_choose_discard_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_surveil_then_if_quality_to_hand_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_surveil_then_for_each_on_top_draw_and_lose_life_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_top_hand_lose_life_equal_to_mana_value_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_until_kind_then_put_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_until_n_kind_put_onto_battlefield_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_until_kind_conditional_mv_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_discard_then_land_rebate_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_n_put_kind_battlefield_then_shuffle_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_exile_top_may_x_if_you_dont_y_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_may_discard_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_counted_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_return_target_then_if_you_do_self_counter_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_return_self_then_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_may_exile_from_graveyard_if_you_do_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_target_then_life_equal_to_its_mana_value_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_process_exile_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_draw_mana_spent_then_discard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_converge_may_draw_then_discard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # G5's general merger, tried only once every more specific "you may
        # <verb>. If you do, ..." shape above (and, earlier in the dispatch
        # that calls this loop, the whole-text sacrifice/energy/mana
        # readers) has already had first refusal - see its own docstring.
        merged = _merge_may_then_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_choose_a_color_then_add_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_exile_self_if_you_do_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_put_onto_battlefield_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_reveal_to_hand_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_may_reveal_group_to_hand_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_x_split_hand_graveyard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_may_reveal_two_types_split_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_put_back_any_order_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_top_one_card_per_type_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_top_to_hand_rest_to_graveyard_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_split_hand_graveyard_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_reveal_top_put_all_quality_to_hand_rest_elsewhere_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_one_to_hand_exile_rest_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_look_top_hand_bottom_exile_play_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_exile_then_cast_any_number_free_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_flip_coin_damage_or_exile_transform_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_flip_coin_lose_consequence_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end Wave W1 multi-clause merges --------------------------------
        merged = _parse_exile_into_suspend_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_counter_exile_then_cast_free_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_devotion_drain_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _parse_scry_or_untap_if_not_starting_player_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_counter_then_subtype_while_counter_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_tap_target_then_no_untap_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_target_player_draws_and_loses_life_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_each_player_may_discard_hand_and_draw_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = merge_each_player_may_shuffle_hand_graveyard_then_draw_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- Wave W6's own multi-clause merges, contiguous block ------------
        merged = _parse_delayed_reanimate_haste_exile_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_damage_each_group_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_damage_each_filtered_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_each_player_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end Wave W6 multi-clause merges ----------------------------------
        merged = _merge_sacrifice_one_of_each_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        merged = _merge_draw_reveal_cast_one_free_clauses(clauses, index, for_spell=for_spell)
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- G1c's own multi-clause merge (CR 108.3, CR 115.6, CR 401.2/609.3) -
        merged = _merge_choose_target_then_owner_puts_it_into_library_clauses(
            clauses, index, for_spell=for_spell
        )
        if merged is not None:
            consumed, effect = merged
            parsed.append(effect)
            index += consumed
            continue
        # -- end G1c multi-clause merge ---------------------------------------
        if index + 1 < len(clauses):
            merged = _parse_delayed_pay_or_lose_clauses(clauses, index, for_spell=for_spell)
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            paired = _parse_anaphoric_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            from ..infusion import _parse_conditional_anaphoric_clause_pair

            paired = _parse_conditional_anaphoric_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_all_of_target_player_then_referent_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_untap_then_if_type_counter_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_destroy_then_if_not_attacking_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_destroy_then_if_that_permanent_was_draw_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = token_riders.parse_destroy_if_mv_then_consequence_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_landfall_type_then_add_mana_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # CR 608.2c's own worked example, tried before the general object
            # anaphor below because it is not the same shape: this rider
            # modifies the destruction rather than running after it, so the
            # pair cannot be split into "antecedent, then rider".
            paired = _parse_cant_be_regenerated_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # Ahead of the general object anaphor: this is the one shape
            # here whose rider names a target of its own, which the general
            # referent reader cannot tell apart from the antecedent's.
            paired = _parse_pump_then_fight_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # Same reason: the bite rider names its own victim target, and
            # the antecedent's own pump is conditional (Burrog Barrage).
            paired = _parse_conditional_pump_then_bite_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_conditional_self_pump_instead_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_self_pump_then_conditional_also_gains_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # Same reason: the bite rider names its own biter target.
            paired = _parse_bite_damage_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # Two clauses that each name their own target, told apart by
            # controller rather than by an antecedent/rider relationship at
            # all - Awaken the Inferno's own "deals damage to target ... an
            # opponent controls. Put a +1/+1 counter on ... target ... you
            # control." Tried ahead of the general object anaphor for the
            # identical reason the two pairs just above are: the second
            # clause names a target of its own, which the anaphor reader has
            # no way to tell apart from the first clause's.
            paired = _parse_controller_split_target_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            # CR 608.2c: a run of riders that all name the antecedent's object
            # ("Put a +1/+1 counter on that creature. Put a lifelink counter on
            # that creature.") is one antecedent with several riders, not a
            # pair followed by a rider with no antecedent of its own.
            run_end = index + 1
            while run_end < len(clauses) and _OBJECT_ANAPHOR_RE.search(clauses[run_end]):
                run_end += 1
            if run_end - index > 2:
                series = _parse_object_anaphor_clause_series(
                    clauses[index], clauses[index + 1 : run_end], for_spell=for_spell
                )
                if series is not None:
                    parsed.append(series)
                    index = run_end
                    continue
            paired = _parse_object_anaphor_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_token_then_object_anaphor_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_choose_then_object_anaphor_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_draw_equal_to_then_lose_life_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_target_player_discards_then_play_land_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_exile_then_return_clause_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_referent_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_create_tokens_by_mana_value_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_wizard_mana_from_countered_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_delayed_any_combination_mana_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_recruit_by_mana_value_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_then_exile_instead_of_graveyard_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            paired = _parse_counter_unless_pays_then_condition_upgrade_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
            merged = _parse_conditional_exile_then_play_permission_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _parse_exile_then_play_permission_clauses(clauses, index, for_spell=for_spell)
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _parse_exile_targets_then_owner_play_permission_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _merge_exile_until_quality_then_counter_or_cast_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _merge_may_exile_top_conditional_pump_then_play_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _merge_may_exile_discarded_card_then_play_permission_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _merge_create_token_then_suspect_it_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            merged = _merge_return_target_from_graveyard_tapped_then_attacking_clauses(
                clauses, index, for_spell=for_spell
            )
            if merged is not None:
                consumed, effect = merged
                parsed.append(effect)
                index += consumed
                continue
            paired = _parse_next_time_draw_replacement_pair(
                clauses[index], clauses[index + 1], for_spell=for_spell
            )
            if paired is not None:
                parsed.append(paired)
                index += 2
                continue
        effect = _parse_mixed_clause(clauses[index], for_spell=for_spell)
        if effect is None:
            return None
        parsed.append(effect)
        index += 1
    return parsed


def parse_mixed_effect_for_spell(text: str) -> Effect | None:
    """A spell whose clauses may be targeted, player-only, or a mix of both,
    read off the card's own printed text - Lightning Helix, with no `EFFECTS`
    row any more. Subsumes `parse_targeted_effect_for_spell` and
    `parse_player_effect_for_spell`: a wholly-targeted or wholly-player-clause
    card still parses here, since each clause simply succeeds on the first of
    the two parsers it is tried against.
    """
    clauses = _parse_mixed_clauses(text, for_spell=True)
    if clauses is None and (carried := _carry_where_x_forward(text)) != text.strip():
        clauses = _parse_mixed_clauses(carried, for_spell=True)
    if clauses is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for clause in clauses:
            clause(game, spell)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


def parse_mixed_effect(text: str) -> AbilityEffect | None:
    """The ability-resolution twin of `parse_mixed_effect_for_spell`: a
    triggered or activated ability whose clauses may be targeted, a search, a
    plain player clause, or a mix, read off the ability's own printed text
    with no table row.

    This is what lets Ghost Quarter and White Orchid Phantom drop their
    `ACTIVATED_EFFECTS`/`TRIGGER_EFFECTS` rows: "Destroy target land." is one
    clause `_parse_targeted_clause` reads, "Its controller may search their
    library for a basic land card, put it onto the battlefield, then shuffle."
    is the next, read by `_parse_search_clause` once `_rejoin_search_clauses`
    has put its "then shuffle" back where it belongs. `trigger_effect_for` and
    `activated_effect_for` call this instead of trying
    `parse_search_and_put_effect`, `parse_targeted_effect`, and
    `parse_player_effect` in turn, since a search-only or plain-player-only or
    wholly-targeted ability still parses here - each of its clauses simply
    succeeds on the first of the three parsers it is tried against.
    """
    clauses = _parse_mixed_clauses(text, for_spell=False)
    if clauses is None and (carried := _carry_where_x_forward(text)) != text.strip():
        clauses = _parse_mixed_clauses(carried, for_spell=False)
    if clauses is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for clause in clauses:
            clause(game, ability)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: "The next spell you cast this turn can't be countered." - Theorist's
#: Proxy, and Mistrise Village (Tarkir: Dragonstorm) off-set. Not "count",
#: "type", or any other filter - just the bare next one, CR 603.7b's default.
_NEXT_SPELL_CANNOT_BE_COUNTERED_RE = re.compile(
    r"^the next spell you cast this turn can'?t be countered\.?$", re.IGNORECASE
)


def _parse_next_spell_cannot_be_countered_clause(text: str) -> AbilityEffect | None:
    """`_NEXT_SPELL_CANNOT_BE_COUNTERED_RE`'s shape, the same CR 603.7
    delayed-trigger machinery `_parse_copy_next_spell_you_cast_clause` above
    already builds for the identical "the next spell you cast this turn ..."
    template - `remaining=1`, `expires_end_of_turn=True`, `only_when_active`
    scoped to the controller who resolved this ability, watching
    `TriggerEvent.CAST_SPELL`. Only the delayed effect itself differs:
    `NextSpellCannotBeCountered` grants the found spell "This spell can't be
    countered." onto `CardState.granted_ability_texts` instead of copying it.
    """
    match = _NEXT_SPELL_CANNOT_BE_COUNTERED_RE.fullmatch(
        " ".join(_strip_non_effect_preamble(text).split())
    )
    if match is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        game.create_delayed_trigger(
            DelayedTrigger(
                text="The next spell you cast this turn can't be countered.",
                event=TriggerEvent.CAST_SPELL,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                only_when_active=ability.controller,
                remaining=1,
                expires_end_of_turn=True,
                effect=NextSpellCannotBeCountered(),
            )
        )

    return effect


#: "That player `<rest>`." - CR 607.1's own within-one-ability anaphora back
#: to whichever specific player a triggered ability's own condition just
#: fired for (`GameEvent.player`), the identical subject
#: `_THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE` and `_THEY_GAIN_OR_LOSE_
#: LIFE_RE` already read for their own one hand-written verb apiece. Curse
#: of Oblivion's own "At the beginning of enchanted player's upkeep, that
#: player exiles two cards from their graveyard" is the shape that exposed
#: the gap a fresh one-off regex per verb would leave standing: neither of
#: those two readers know "exiles", and a third bespoke copy of the same
#: `ability.event.player` plumbing for one more verb is exactly the
#: per-card-shaped pattern this project's own "target the mechanic" rule
#: bans. This reader is the general form instead - whatever `<rest>` is,
#: `parse_clause_effect` already reads it (this wave's own graveyard-exile
#: clause among them), so every present and future verb printed after
#: "that player" is closed by the one reader that already understands it,
#: not by a fresh table row.
#:
#: Tried only as the dispatcher's own last resort (see its call site,
#: mirroring where `_parse_optional_player_clause` is tried last for a
#: plain "you"-subject clause): every more specific "that player ..." shape
#: above - the sacrifice and life-total ones among them - keeps first claim
#: on the clauses it already reads correctly, so this never changes their
#: behaviour.
_THAT_PLAYER_CLAUSE_RE = re.compile(r"^that player (?P<rest>.+)$", re.IGNORECASE | re.DOTALL)


def _parse_that_player_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_THAT_PLAYER_CLAUSE_RE`'s shape. Ability-only: a resolving spell has
    no `ability.event` to resolve "that player" against, the same
    restriction every other event-anaphora reader in this family already
    states."""
    if for_spell:
        return None
    match = _THAT_PLAYER_CLAUSE_RE.match(clause.strip())
    if match is None:
        return None
    rest = match.group("rest").strip()
    clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
    if clause_effect is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.player is None:
            return
        player = game.player(event.player)
        clause_effect(game, player, ability.source_name, source_id_of(ability))

    return effect


#: "you may cast {an? `<quality>` spell|target `<quality>` card} from your
#: graveyard[ without paying its mana cost]. [If {an? `<quality>` spell cast
#: this way|that spell} would be put into your graveyard, exile it instead.]"
#: - Bilbo, Thief in the Night's and The Dawning Archaic's attack triggers:
#: a cast made while the ability resolves (CR 608.2g), out of the
#: controller's own graveyard, with CR 614.1a's exile rider carried on the
#: cast (`CastRecord.exile_instead_of_graveyard`, the record S26's graveyard
#: permissions write - `machines/replacement._stack_replacements` reads it).
_CAST_FROM_GRAVEYARD_NOW_RE = re.compile(
    r"^you may cast (?:an? (?P<quality>.+?) spell|(?P<target>target .+? card)) from your graveyard"
    r"(?P<free> without paying its mana cost)?\.?"
    r"(?:\s*if (?:an? (?P<rider_quality>.+?) spell cast this way|that spell) would be put "
    r"into (?:your|a) graveyard, exile it instead\.?)?$",
    re.IGNORECASE,
)


def _parse_cast_from_graveyard_now_clause(effect_text: str) -> AbilityEffect | None:
    """`_CAST_FROM_GRAVEYARD_NOW_RE`'s shape.

    CR 608.2d: the "may" is offered only when a legal choice exists - a
    graveyard card of the quality (or the targeted card, rechecked by CR
    608.2b) that `Game.can_cast_during_resolution` finds castable - then
    `DecisionKind.CHOOSE_CARDS` for which one, and `Game.cast_during_
    resolution` casts it, paying its mana cost unless the text waives it
    (CR 118.9). The rider applies to the spell only when it has the rider's
    own quality ("an instant or sorcery spell cast this way"), or always for
    "that spell".
    """
    whole = " ".join(_strip_non_effect_preamble(effect_text).split())
    match = _CAST_FROM_GRAVEYARD_NOW_RE.fullmatch(whole)
    if match is None:
        return None
    quality = match.group("quality")
    target_phrase = match.group("target")
    if quality is not None and not _card_description_is_readable(quality):
        return None
    if target_phrase is not None and not _targets_understood(
        f"{target_phrase} from your graveyard", battlefield_only=False
    ):
        return None
    matches_quality = _quality_matcher(quality) if quality is not None else None
    has_rider = "exile it instead" in whole.lower()
    rider_quality = match.group("rider_quality")
    if rider_quality is not None and not _card_description_is_readable(rider_quality):
        return None
    rider_matches = _quality_matcher(rider_quality) if rider_quality is not None else None
    free = match.group("free") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        caster = game.controller_of(ability).username
        if target_phrase is not None:
            pool = [
                card
                for card in game.resolve_targets(ability)
                if isinstance(card, CardState) and card.zone is Zone.GRAVEYARD
            ]
        else:
            pool = [
                card
                for card in game.player(caster).graveyard
                if matches_quality is not None and matches_quality(card)
            ]
        candidates = [
            card
            for card in pool
            if not card.card.is_land and game.can_cast_during_resolution(card, caster)
        ]
        described = (
            with_indefinite_article(f"{quality} spell") if quality is not None else "that card"
        )
        cost_words = " without paying its mana cost" if free else ""
        taken = game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=caster,
                prompt=f"cast {described} from your graveyard{cost_words}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=bool(candidates),
                cards=tuple(card.id for card in candidates),
            )
        )
        if not taken or not candidates:
            return
        chosen = candidates[0]
        if len(candidates) > 1 or target_phrase is None:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=caster,
                    prompt=f"choose a card to cast{cost_words}",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(card.id for card in candidates),
                )
            )
            assert isinstance(chosen_ids, tuple)
            chosen = {card.id: card for card in candidates}[chosen_ids[0]]
        exile_instead = has_rider and (rider_matches is None or rider_matches(chosen))
        game.cast_during_resolution(
            chosen,
            caster,
            source_name=ability.source_name,
            rule="CR 608.2g",
            pays_mana_cost=not free,
            exile_instead_of_graveyard=exile_instead,
        )

    return effect


def _r0a_t5_ability_effect(effect_text: str) -> AbilityEffect | None:
    """R0a-T5's whole-text ability readers, tried ahead of the clause split
    (each reads a multi-sentence instruction chain), one per owning module."""
    from ..control_change import parse_gain_control_untimed_clause
    from ..delayed import parse_self_flicker_at_next_end_step_clause
    from ..designations import parse_becomes_solved_clause
    from ..hand_reveal_exile import parse_hand_exile_until_leaves_clause
    from ..linked_exile import (
        parse_exile_all_until_leaves_clause,
        parse_exiled_card_owner_manifests_dread_clause,
        parse_put_linked_into_graveyard_then_tokens_clause,
    )
    from ..spell_grants import (
        parse_choose_exiled_with_counter_play_clause,
        parse_exile_at_random_from_graveyard_play_clause,
        parse_graveyard_cards_gain_cast_clause,
    )

    for reader in (
        parse_choose_exiled_with_counter_play_clause,
        parse_becomes_solved_clause,
        parse_graveyard_cards_gain_cast_clause,
        parse_self_flicker_at_next_end_step_clause,
        parse_exile_all_until_leaves_clause,
        parse_put_linked_into_graveyard_then_tokens_clause,
        parse_hand_exile_until_leaves_clause,
        parse_gain_control_untimed_clause,
        parse_exile_at_random_from_graveyard_play_clause,
        parse_exiled_card_owner_manifests_dread_clause,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def _r0a_t5_spell_effect(effect_text: str) -> Effect | None:
    """The spell-side twin of `_r0a_t5_ability_effect`."""
    from ..graveyard_cast_transform import parse_cast_from_graveyard_transform_clause

    return parse_cast_from_graveyard_transform_clause(effect_text)


def _c02_t6_ability_effect(effect_text: str) -> AbilityEffect | None:
    """C02-T6's whole-text ability readers, tried ahead of the clause split
    (each reads an instruction chain `_prepare_effect_clauses` would cut
    apart): the animation gate above, then `machines/copy_effects.py`'s and
    `machines/control_change.py`'s own readers."""
    from ..cast_copies import cast_copy_ability_effect
    from ..control_change import control_change_ability_effect
    from ..copy_effects import copy_ability_effect
    from ..hand_reveal_exile import parse_reveal_some_then_choose_one
    from ..resolving_exile import resolving_exile_ability_effect
    from ..sieges import exile_then_cast_transformed_effect

    for reader in (
        _parse_if_self_isnt_a_creature_clause,
        _parse_double_target_power_and_toughness_clause,
        _parse_target_fights_other_target_clause,
        _parse_return_with_rider_clause,
        copy_ability_effect,
        cast_copy_ability_effect,
        resolving_exile_ability_effect,
        parse_reveal_some_then_choose_one,
        control_change_ability_effect,
        exile_then_cast_transformed_effect,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def _c02_t6_spell_effect(effect_text: str) -> Effect | None:
    """The spell-side twin of `_c02_t6_ability_effect`."""
    from ..control_change import control_change_spell_effect
    from ..copy_effects import copy_spell_effect

    for reader in (
        _parse_double_target_power_and_toughness_clause,
        _parse_target_fights_other_target_clause,
        copy_spell_effect,
        control_change_spell_effect,
    ):
        effect = reader(effect_text)
        if effect is not None:
            return effect
    return None


def _source_relative_whole_text_ability_effect(effect_text: str) -> AbilityEffect | None:
    """The readers above, tried in turn on a resolving ability's whole text -
    `_ability_effect_or_notice` asks this first."""
    evasion = _gains_and_cant_be_blocked_this_turn(effect_text, parse_mixed_effect)
    if evasion is not None:
        return evasion
    for reader in (
        _parse_each_opponent_loses_x_you_gain_x,
        _parse_draw_if_power_at_least,
        _parse_target_player_creates_token,
        _parse_transform_it,
        _parse_attach_target_equipment_to_self,
        _parse_attach_self_then_that_creature,
        _parse_attach_self_then_conditional_rider_clause,
        _parse_put_type_from_hand_attach_if_subtype,
        _parse_return_self_then_may_attach_equipment,
        _parse_self_counter_then_rider,
        _parse_may_pay_then_drain_total,
        _parse_until_eot_assigns_toughness,
        _parse_may_pay_life_then_rider,
        _parse_cast_spell_targets_gain,
        _parse_multi_part_sacrifice_gain_draw_discard_damage_counters_clause,
        _parse_reveal_until_creature_then_attacking_rest_random_clause,
        _parse_combat_damage_reanimate_from_that_players_graveyard_attacking_clause,
        _parse_put_two_card_groups_and_or_from_hand_clause,
        _parse_gain_life_equal_to_event_subject_toughness_clause,
        _parse_etb_damage_any_target_and_self_clause,
        _parse_reveal_any_number_then_x_plus_damage_clause,
        _parse_look_hand_may_exile_owner_may_play_clause,
    ):
        found = reader(effect_text)
        if found is not None:
            return found
    return None


def _source_relative_whole_text_spell_effect(effect_text: str) -> Effect | None:
    """The spell-side twin, for `_spell_effect_or_notice`: Pym Particles'
    shared-subject evasion rider, and Char's own "deals `<n>` damage to any
    target and `<n2>` damage to you" (CR 201.5's literal self-name subject,
    no "when ~ enters" condition in front of it the way Spicy Oatmeal Pizza's
    own ability-side printing has)."""
    evasion = _gains_and_cant_be_blocked_this_turn(effect_text, parse_mixed_effect_for_spell)
    if evasion is not None:
        return evasion
    return _parse_etb_damage_any_target_and_self_clause(effect_text, for_spell=True)


# --------------------------------------------------------------------------
# 271-tmt T8: outside-the-game search, multi-part sacrifice, tuck-then-draw,
# combat-damage reanimation, put-onto-battlefield-attacking off a library
# reveal, and-or hand permanents, LKI-toughness lifegain, split ETB damage.
# --------------------------------------------------------------------------

#: "Put a card from your hand on the bottom of your library." - CR 118.12's
#: tuck half of Manhole Missile's own "You may put a card from your hand on
#: the bottom of your library. If you do, draw a card." - the identical
#: shape `_merge_may_then_if_you_do_clauses` already reads generically for
#: "you may `<clause>`. If you do, `<clause>`.", once `parse_clause_effect`
#: (this function) can read the tuck half at all.
_PUT_CARD_FROM_HAND_ON_BOTTOM_OF_LIBRARY_RE = re.compile(
    r"^put a card from your hand on the bottom of your library$", re.IGNORECASE
)


from ._common import (  # noqa: E402
    _ADDITIONAL_LAND_PLAY_RE,
    _ANAPHORIC_SUBJECT_RE,
    _COUNTER_TARGET_RE,
    _COUNTER_TARGET_SPELL_RE,
    _COUNTER_UNLESS_PAYS_RE,
    _DAMAGE_TARGET_RE,
    _DESTROY_TARGET_RE,
    _DISCARD_A_CARD_RE,
    _DIVIDED_DAMAGE_AMONG_TARGET_PLAYERS_CREATURES_RE,
    _DRAW_CARDS_EQUAL_TO_RE,
    _EXILE_TARGET_RE,
    _GET_AN_EMBLEM_RE,
    _HAND_EXILE_RE,
    _MAY_SACRIFICE_IF_YOU_DO_RE,
    _OBJECT_ANAPHOR_RE,
    _OBJECT_CHARACTERISTIC_RE,
    _PAY_ANY_AMOUNT_OF_LIFE_RE,
    _PER_COUNT_COST_REDUCTION_LINE_RE,
    _PERMANENT_CARD_TYPES,
    _RETURN_TARGET_RE,
    _SEARCH_AND_PUT_RE,
    _SELF_COST_REDUCTION_LINE_RE,
    _SHUFFLE_RE,
    _SURVEIL_RE,
    _TAP_UNTAP_TARGET_RE,
    _TIMING_COST_REDUCTION_LINE_RE,
    _YOU_MAY_RE,
    AnaphoricClauseNotice,
    ConditionalClauseNotice,
    ControlReplacementNotice,
    DelayedClauseNotice,
    ImprintNotice,
    ReflexiveClauseNotice,
    SearchDescriptionNotice,
    UnmodeledTriggerEffectNotice,
    _card_description_is_readable,
    _nonland_or_typed_card_matcher,
    _opponents,
    _parse_delayed_timing_clause,
    _prepare_effect_clauses,
    _quality_matcher,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _amount_reader,
    _carry_where_x_forward,
    _fixed_or_where_x_amount,
    _for_each_multiplier,
    _parse_converge_damage_then_exile_excess_clause,
    _parse_converge_discard_by_colors_spent,
    _parse_converge_draw_and_lose_life_clause,
    _parse_converge_draw_damage_life_clause,
    _parse_converge_exile_by_colors_spent,
    _parse_converge_fractal_tokens_and_life_clause,
    _parse_count_the_number_of_clause,
    _parse_counted_life_change_clause,
    _parse_devotion_drain_clauses,
    _parse_event_subject_variable_pump_clause,
    _parse_half_life_loss_clause,
    _parse_half_x_life_and_draw_half_x_cards_clause,
    _parse_if_graveyard_count_clause,
    _parse_it_dynamic_x_pump_clause,
    _parse_nth_resolution_clause,
    _parse_put_creature_mv_x_from_hand_attacking,
    _parse_variable_count_token_clause,
    _parse_where_x_is_continuous_effect,
    _parse_x_damage_divided_and_doubled_clause,
    _parse_x_energy_pay_destroy_by_mana_value,
    _parse_x_life_mass_debuff,
    _parse_x_life_return_types_mv_x_clause,
    _resolve_multiplied_amount,
    _that_many_or_notice,
    amount_expression,
    count_expression,
)
from .continuous import (  # noqa: E402
    _attach_self_to_target_effect,
    _compose_layer_effect_with_remainder,
    _compose_layer_effect_with_remainder_for_ability,
    _gains_and_cant_be_blocked_this_turn,
    _mass_pump_ability_effect,
    _mass_pump_spell_effect,
    _parse_additional_combat_and_main_phase_clause,
    _parse_additional_combat_phase_only_clause,
    _parse_attach_any_number_equipment_clause,
    _parse_attach_self_then_conditional_rider_clause,
    _parse_attach_self_then_that_creature,
    _parse_attach_self_then_when_you_do_clause,
    _parse_attach_target_equipment_to_self,
    _parse_attach_target_equipment_up_to_one_creature_clause,
    _parse_attached_subject_gains_keywords_until_clause,
    _parse_attack_this_turn_create_tapped_attacking_tokens,
    _parse_attacks_alone_this_turn_counters_and_keywords_clause,
    _parse_bare_self_pump_until_eot_clause,
    _parse_base_pt_become_clause,
    _parse_batched_attack_group_pump_clause,
    _parse_becomes_chosen_color_clause,
    _parse_becomes_prepared_group_clause,
    _parse_becomes_prepared_self_clause,
    _parse_becomes_unprepared_self_clause,
    _parse_becomes_unprepared_target_clause,
    _parse_cant_be_regenerated_clause_pair,
    _parse_cast_spell_targets_gain,
    _parse_conditional_pump_then_bite_clause_pair,
    _parse_conditional_self_pump_instead_pair,
    _parse_delayed_pay_or_lose_clauses,
    _parse_double_power_and_toughness_clause,
    _parse_double_power_target_clause,
    _parse_double_target_power_and_toughness_clause,
    _parse_each_graveyard_instant_sorcery_gains_flashback_clause,
    _parse_each_opponent_loses_x_you_gain_x,
    _parse_each_opponent_skips_next_untap_clause,
    _parse_each_other_attacking_creature_pump_trigger,
    _parse_each_player_this_creature_attacked_loses_clause,
    _parse_equipped_attacking_creatures_gain_keywords_clause,
    _parse_event_player_gets_that_many_poison_clause,
    _parse_event_subject_pump_clause,
    _parse_for_each_opponent_tap_clause,
    _parse_for_each_opponent_tap_then_stun_clause,
    _parse_gains_ability_clause,
    _parse_get_an_emblem_clause,
    _parse_get_an_emblem_then_clause,
    _parse_get_energy_then_pay_create_x_token_clause,
    _parse_goad_clause,
    _parse_goad_for_each_opponent_then_counters_clause,
    _parse_grant_enters_with_colors_spent_counters_clause,
    _parse_grant_flashback_clause,
    _parse_grant_quoted_ability_then_return_front_face_whole_text,
    _parse_if_condition_players_cant_cast_clause,
    _parse_if_keyword_cost_paid_clause,
    _parse_it_gains_quoted_ability_clause,
    _parse_it_gains_rebound_clause,
    _parse_lands_dont_untap_next_step_clause,
    _parse_mass_gain_control_untap_ability,
    _parse_mass_gain_control_untap_clause,
    _parse_mass_lose_all_abilities_clause,
    _parse_mass_pump_group_clause,
    _parse_may_attach_to_entering_creature_clause,
    _parse_may_tap_untapped_if_you_do_clause,
    _parse_may_then_if_you_do_layer_clause,
    _parse_may_transform_self_if_you_do_clause,
    _parse_other_attacking_creatures_grant_trigger,
    _parse_player_loses_all_counters_clause,
    _parse_protection_from_chosen_color_clause,
    _parse_pump_and_becomes_chosen_color_clause,
    _parse_pump_for_each_color_spent_on_that_spell_clause,
    _parse_pump_per_discard_then_delayed_draw_clause,
    _parse_pump_then_fight_clause_pair,
    _parse_put_then_grant_then_delayed_whole_text,
    _parse_put_type_from_hand_attach_if_subtype,
    _parse_self_base_pt_set_with_keywords_clause,
    _parse_self_cant_block_clause,
    _parse_self_gains_quoted_ability_until_eot_clause,
    _parse_self_keyword_choice_until_eot_trigger,
    _parse_self_keyword_grant_until_eot_clause,
    _parse_self_layer_and_verb_clause,
    _parse_self_pump_for_each_clause,
    _parse_self_pump_then_conditional_also_gains_pair,
    _parse_spells_cant_be_countered_clause,
    _parse_suspect_clause,
    _parse_switch_power_toughness_then_draw_clause,
    _parse_tap_all_group_clause,
    _parse_tap_all_pay_energy_counter_chosen_whole_text,
    _parse_tap_another_untapped_subtype_when_you_do_clause,
    _parse_tap_any_number_of_untapped_creatures_when_you_do_clause,
    _parse_tap_attached_clause,
    _parse_tap_enchanted_then_unprepared_clause,
    _parse_tap_target_then_no_untap_clause,
    _parse_tap_untap_two_targets_clause,
    _parse_tapped_attacking_tokens_whole_text,
    _parse_target_attacking_alone_pump_gain_life_clause,
    _parse_target_attacks_if_able_clause,
    _parse_target_blocks_self_if_able_clause,
    _parse_target_gains_ability_until_cast_from_exile_clause,
    _parse_target_gains_then_dies_this_turn_token_whole_text,
    _parse_target_get_energy_pay_damage,
    _parse_target_player_becomes_monarch_clause,
    _parse_target_player_cant_cast_kicked_attack_clause,
    _parse_target_player_creatures_pump_clause,
    _parse_target_plus_x_minus_x_clause,
    _parse_targeted_then_self_gains_clause,
    _parse_that_permanent_no_untap_clause,
    _parse_this_turn_spell_grant_clause,
    _parse_transform_all_subtype_clause,
    _parse_transform_clause,
    _parse_transform_it,
    _parse_transform_self_at_next_step_clause,
    _parse_undergrowth_pump_and_fight_clause,
    _parse_untap_all_attacking_clause,
    _parse_untap_all_group_clause,
    _parse_untap_all_you_control_clause,
    _parse_untap_and_gain_control_ability,
    _parse_untap_and_gain_control_clause,
    _parse_untap_each_subtype_clause,
    _parse_untap_named_self_clause,
    _parse_untap_self_clause,
    _parse_untap_then_if_type_counter_clause_pair,
    _parse_untap_trigger_subject_and_scry_clause,
    _parse_untap_trigger_subject_clause,
    _parse_until_end_of_turn_tap_land_additional_mana_clause,
    _parse_until_your_next_turn_attack_pump_clause,
    _parse_until_your_next_turn_group_attack_pump_clause,
    _parse_you_and_group_gain_clause,
    _player_gains_hexproof_clause,
    _untap_all_qualifier_matches,
    become_prepared_ability_targets,
    continuous_effects,
    remove_ability_targets_from_combat_and_untap,
    tap_ability_targets,
    transform_permanent,
    untap_ability_targets,
)
from .control_copy import (  # noqa: E402
    _parse_cast_noncreature_spell_this_turn_copy_token_clause,
    _parse_change_target_clause,
    _parse_copy_cast_spell_clause,
    _parse_copy_cost_exiled_cards_and_cast,
    _parse_copy_exiled_card_and_cast,
    _parse_copy_next_instant_or_sorcery_you_cast_clause,
    _parse_copy_next_instant_or_sorcery_you_cast_spell_clause,
    _parse_copy_next_spell_you_cast_clause,
    _parse_copy_of_card_exiled_with_self_clause,
    _parse_copy_target_spell_clause,
    _parse_copy_that_spell_clause,
    _parse_copy_that_spell_retargeted_clause,
    _parse_copy_this_spell_clause,
    _parse_exchange_control_clause,
    _parse_exchange_life_totals_then_draw,
    _parse_for_each_creature_target_player_copy_clause,
    _parse_for_each_creature_you_control_copy_clause,
    _parse_self_copy_token_clause,
)
from .counters import (  # noqa: E402
    _counter_kind,
    _parse_adapt_clause,
    _parse_conditional_remove_counter_from_self_clause,
    _parse_counter_each_attacked_this_turn_clause,
    _parse_counter_each_creature_target_player_clause,
    _parse_counter_each_creature_with_counter_clause,
    _parse_counter_each_other_creature_clause,
    _parse_counter_exile_may_cast_free_clause,
    _parse_counter_exile_then_cast_free_clauses,
    _parse_counter_if_mana_value_clause,
    _parse_counter_on_additional_cost_card_clause,
    _parse_counter_on_it_trigger_subject_clause,
    _parse_counter_on_subject_and_shared_type_clause,
    _parse_counter_on_trigger_subject_clause,
    _parse_counter_then_create_tokens_by_mana_value_pair,
    _parse_counter_then_delayed_any_combination_mana_pair,
    _parse_counter_then_exile_instead_of_graveyard_pair,
    _parse_counter_then_recruit_by_mana_value_pair,
    _parse_counter_then_referent_pair,
    _parse_counter_then_wizard_mana_from_countered_pair,
    _parse_counter_threshold_whole_text,
    _parse_counters_more_if_subtype_clause,
    _parse_counters_on_named_group_clause,
    _parse_counters_then_look_top_may_battlefield_transform_clause,
    _parse_distribute_counters_among_targets_clause,
    _parse_distribute_counters_among_you_control_clause,
    _parse_distribute_counters_then_targets_gain_clause_pair,
    _parse_double_counters_on_group_clause,
    _parse_endure_clause,
    _parse_event_subject_counters_and_keywords_clause,
    _parse_for_each_opponent_counters_clause,
    _parse_loyalty_instant_speed_clause,
    _parse_minus_counters_mixed_clause,
    _parse_monstrosity_clause,
    _parse_move_counter_clause,
    _parse_proliferate_clause,
    _parse_put_counter_on_self_then_if_count_clause,
    _parse_put_counter_then_for_each_counter_punisher_clause,
    _parse_put_counters_equal_to_clause,
    _parse_put_counters_on_group_clause,
    _parse_put_counters_on_self_clause,
    _parse_put_counters_on_target_by_that_spells_mana_value_clause,
    _parse_put_counters_on_target_where_x_is_clause,
    _parse_put_its_counters_on_target_clause,
    _parse_put_n_counters_on_self_then_draw_half_n_clause,
    _parse_put_self_counter_for_each_opponent_creature_then_attach_clause,
    _parse_put_up_to_n_counters_on_self_capped_clause,
    _parse_quest_counter_threshold_sacrifice_search_clause,
    _parse_remove_all_counters_from_each_clause,
    _parse_remove_all_counters_from_target_clause,
    _parse_remove_all_counters_then_cant_have_clause,
    _parse_remove_all_counters_then_that_many_clause,
    _parse_remove_n_counters_from_self_clause,
    _parse_remove_time_counter_from_self_clause,
    _parse_remove_up_to_n_counters_from_target_clause,
    _parse_renown_clause,
    _parse_self_counter_then_rider,
    _parse_two_counters_on_self_clause,
    put_counters_on_ability_targets,
)
from .damage import (  # noqa: E402
    _damage_ability_targets_equal_to,
    _damage_each_creature_for_expression,
    _damage_each_opponent_for_expression,
    _deal_damage_equal_to_sacrificed_creature_power,
    _deal_damage_for_each,
    _deal_divided_damage_for_expression,
    _deal_x_divided_damage,
    _parse_airbend_clause,
    _parse_bite_damage_clause,
    _parse_bite_damage_clause_pair,
    _parse_combat_damage_reanimate_from_that_players_graveyard_attacking_clause,
    _parse_damage_each_filtered_clause,
    _parse_damage_each_group_clause,
    _parse_damage_equal_to_that_spells_mv_clause,
    _parse_damage_target_also_damages_controller_clause,
    _parse_damage_target_kicked_instead_clause,
    _parse_damage_target_player_and_their_creatures_clause,
    _parse_damage_that_much_clause,
    _parse_damage_that_player_clause,
    _parse_damage_then_empower_if_excess_clause,
    _parse_damage_to_that_spells_controller_clause,
    _parse_deals_damage_lose_life_then_transform_if_low_clause,
    _parse_dealt_damage_this_way_die_to_exile,
    _parse_delirium_damage_instead_clause,
    _parse_divided_damage_among_target_players_creatures_clause,
    _parse_divided_damage_then_retaliate_clause,
    _parse_earthbend_clause,
    _parse_enchanted_creature_fights_target_clause,
    _parse_etb_damage_any_target_and_self_clause,
    _parse_firebending_add_mana,
    _parse_prevent_all_damage_to_self_this_turn_clause,
    _parse_prevent_all_damage_to_you_until_next_turn_clause,
    _parse_prevent_damage_dealt_by_target_clause,
    _parse_self_assigns_no_combat_damage_clause,
    _parse_self_damage_equal_to_count_clause,
    _parse_self_fights_target_clause,
    _parse_target_fights_other_target_clause,
    _parse_target_fights_target_clause,
    _parse_until_end_of_turn_self_combat_damage_draw_clause,
    _parse_until_eot_assigns_toughness,
    _self_deals_damage_equal_to_its_stat,
    damage_ability_targets,
    damage_ability_targets_equal_to_expression,
    damage_each_creature,
    damage_each_creature_spell,
    damage_each_opponent,
    damage_each_opponent_spell,
    damage_each_player,
    damage_each_player_spell,
    damage_to_controller,
    damage_to_itself,
    deal_damage,
    deal_damage_equal_to_expression,
    deal_divided_damage,
    empower_jace,
    prevent_all_combat_damage,
    prevent_all_combat_damage_except,
    prevent_next_damage_to_target,
)
from .draw_discard import (  # noqa: E402
    _discard_cards,
    _each_opponent_draws_clause,
    _parse_discard_hand_draw_x_clause,
    _parse_discard_then_draw_token_per_nonland_clause,
    _parse_discard_unless_condition_clause,
    _parse_draw_and_gain_off_sacrificed_clause,
    _parse_draw_cards_equal_to_count_clause,
    _parse_draw_cards_equal_to_target_hand_clause,
    _parse_draw_equal_to_sacrificed_creature_power_then_discard_clause,
    _parse_draw_equal_to_then_lose_life_clause_pair,
    _parse_draw_if_power_at_least,
    _parse_draw_if_you_control_color_permanent_clause,
    _parse_draw_the_difference_clause,
    _parse_draw_then_delayed_discard_at_random_clause,
    _parse_draw_then_discard_unless,
    _parse_draw_then_discard_unless_ability,
    _parse_draw_then_put_land_cave_bonus_clause,
    _parse_draw_x_from_target_graveyard_from_library_clause,
    _parse_each_group_discards_then_consequence_per_failure_clause_pair,
    _parse_each_opponent_discards_clause,
    _parse_each_opponent_discards_then_draw_per_shortfall_whole_text,
    _parse_each_opponent_discards_then_shortfall_loses_life_whole_text,
    _parse_each_player_may_discard_hand_and_draw_clause,
    _parse_may_discard_or_sacrifice_if_you_do_clause,
    _parse_may_put_card_from_hand_clause,
    _parse_n_target_players_each_draw_clause,
    _parse_next_time_draw_replacement_pair,
    _parse_power_of_two_draw_clause,
    _parse_put_land_from_hand_clause,
    _parse_put_land_from_hand_repeat_clause,
    _parse_put_permanent_card_from_hand_clause,
    _parse_put_two_card_groups_and_or_from_hand_clause,
    _parse_target_opponent_draw_then_copy_that_spell_clause,
    _parse_target_player_discards_clause,
    _parse_target_player_discards_then_play_land_clause_pair,
    _parse_target_player_draws_and_loses_life_clause,
    _parse_target_player_draws_clause,
    _parse_target_player_may_put_card_from_hand_clause,
)
from .library import (  # noqa: E402
    _look_at_target_hand,
    _mill,
    _mill_then_may_take_from_milled_runner,
    _parse_bottom_hand_then_draw_plus_one_clause,
    _parse_cast_trigger_look_top_x_take_one_clause,
    _parse_cast_trigger_reveal_top_x_put_one_permanent_clause,
    _parse_cast_trigger_reveal_until_x_kind_to_graveyard_clause,
    _parse_dead_object_to_library_clause,
    _parse_defending_player_reveals_top_conditional_land_clause,
    _parse_discover_clause,
    _parse_each_player_name_reveal_branch_clause,
    _parse_explores_clause,
    _parse_explores_then_conditional_mass_destroy,
    _parse_hideaway_clause,
    _parse_hideaway_counter_then_conditional_free_cast_clause,
    _parse_hideaway_play_clause,
    _parse_learn_clause,
    _parse_look_at_top_card_clause,
    _parse_look_hand_may_exile_owner_may_play_clause,
    _parse_look_top_card_conditional_clause,
    _parse_look_top_cast_le_greatest_attacking_power_whole_text,
    _parse_look_top_keep_one_on_top_clause,
    _parse_look_top_lands_take_to_hand,
    _parse_look_top_may_reveal_clause,
    _parse_look_top_n_may_battlefield_creature_bonus_clause,
    _parse_look_top_n_put_total_mv_onto_battlefield,
    _parse_look_top_separate_face_down_face_up_piles_clause,
    _parse_look_top_split_conditional_instead_clause,
    _parse_look_top_x_put_permanents_clause,
    _parse_manifest_dread_clause,
    _parse_manifest_from_hand_then_draw_clause,
    _parse_manifest_top_card_clause,
    _parse_mill_that_many_then_take_from_among_them,
    _parse_mill_then_may_put_on_top_clause,
    _parse_mill_then_may_return_creature_clause,
    _parse_mill_then_may_take_from_milled,
    _parse_mill_then_may_take_from_milled_ability,
    _parse_mill_then_play_that_card,
    _parse_mill_then_put_all_from_milled,
    _parse_mill_then_put_all_from_milled_ability,
    _parse_mill_then_return_to_hand_clause,
    _parse_owner_puts_it_into_library_clause,
    _parse_owner_shuffles_graveyard_into_library_clause,
    _parse_put_cards_from_hand_into_library_clause,
    _parse_put_each_on_bottom_clause,
    _parse_recruit_clause,
    _parse_reveal_any_number_then_x_plus_damage_clause,
    _parse_reveal_from_outside_the_game_into_hand_clause,
    _parse_reveal_hand_choose_two_bounded_cards_then_discard_clause,
    _parse_reveal_n_cards_then_choose_discard_whole_text,
    _parse_reveal_top_card_if_quality_clause,
    _parse_reveal_top_n_may_battlefield_creature_teamwork_clause,
    _parse_reveal_top_n_put_random_kind_clause,
    _parse_reveal_two_outside_opponent_chooses_clause,
    _parse_reveal_until_creature_then_attacking_rest_random_clause,
    _parse_reveal_until_land_damage_clause,
    _parse_reveal_until_x_kind_put_any_onto_battlefield_clause,
    _parse_reveal_until_x_nonland_exile_per_color_clause,
    _parse_scry_or_untap_if_not_starting_player_clauses,
    _parse_select_from_top_clause,
    _parse_select_from_top_spell_clause,
    _parse_self_owner_shuffles_self_into_library_clause,
    _parse_shuffle_self_and_targets_into_owners_libraries_clause,
    _parse_shuffle_target_cards_into_library_clause,
    _parse_shuffle_target_permanent_into_library_clause,
    _parse_target_player_name_reveal_branch_clause,
    _parse_target_player_shuffles_clause,
    _parse_that_player_mills_that_many_clause,
    _parse_venture_clause,
    _put_card_from_hand_on_bottom_of_library,
    put_ability_targets_on_bottom_of_owners_library,
    put_ability_targets_on_top_of_owners_library,
    puts_graveyard_on_bottom_of_library,
)
from .life import (  # noqa: E402
    _life_total_becomes_amount_reader,
    _parse_double_your_life_total_clause,
    _parse_each_opponent_loses_life_equal_to,
    _parse_each_opponent_loses_life_equal_to_sacrificed_creature_clause,
    _parse_each_opponent_loses_life_unless_sacrifice_or_discard_clause,
    _parse_gain_life_equal_to_additional_cost_card_clause,
    _parse_gain_life_equal_to_event_subject_toughness_clause,
    _parse_gain_life_equal_to_sacrificed_creature_clause,
    _parse_gain_life_if_color_spent_clause,
    _parse_its_controller_may_pay_life_then_draw_clause,
    _parse_may_pay_life_if_you_do_clause,
    _parse_may_pay_life_then_rider,
    _parse_may_pay_then_drain_total,
    _parse_pay_any_life_then_draw_that_many_clause,
    _parse_target_player_loses_life_equal_to_sacrificed_creature_clause,
    _parse_that_player_loses_life_searches_puts_in_hand_clause,
    _parse_that_players_life_total_becomes_clause,
    _parse_they_gain_or_lose_life_clause,
    _parse_you_and_event_player_gain_that_much_life_clause,
    life_total_becomes_effect_for,
)
from .mana import (  # noqa: E402
    _parse_add_any_combination_mana_clause,
    _parse_add_mana_clause,
    _parse_add_mana_in_any_combination_trigger,
    _parse_add_one_mana_of_any_color_trigger,
    _parse_add_that_much_colored_mana_trigger,
    _parse_if_condition_add_mana_equal_to_clause,
    _parse_landfall_type_then_add_mana_clause_pair,
    _parse_mana_adding_trigger,
    _parse_may_pay_mana_if_you_do_clause,
)
from .merges import (  # noqa: E402
    _merge_add_any_combination_mana_with_restriction_clauses,
    _merge_choose_a_color_then_add_clauses,
    _merge_choose_target_then_owner_puts_it_into_library_clauses,
    _merge_continuous_pump_keyword_clauses,
    _merge_converge_may_draw_then_discard_clauses,
    _merge_counted_if_you_do_clauses,
    _merge_counter_then_subtype_while_counter_clauses,
    _merge_create_token_then_suspect_it_clauses,
    _merge_damage_any_target_then_destroy_if_type_clauses,
    _merge_damage_each_filtered_clauses,
    _merge_damage_each_group_clauses,
    _merge_damage_target_then_reveal_choose_discard_clauses,
    _merge_destroy_then_damage_controller_clauses,
    _merge_discard_then_land_rebate_clauses,
    _merge_draw_mana_spent_then_discard_clauses,
    _merge_draw_reveal_cast_one_free_clauses,
    _merge_each_player_clauses,
    _merge_each_player_may_discard_hand_and_draw_clauses,
    _merge_exile_self_if_you_do_clauses,
    _merge_exile_then_cast_any_number_free_clauses,
    _merge_exile_top_may_x_if_you_dont_y_clauses,
    _merge_exile_until_quality_then_counter_or_cast_clauses,
    _merge_flip_coin_damage_or_exile_transform_clauses,
    _merge_flip_coin_lose_consequence_clauses,
    _merge_look_top_hand_bottom_exile_play_clauses,
    _merge_look_top_may_reveal_group_to_hand_clauses,
    _merge_look_top_may_reveal_two_types_split_clauses,
    _merge_look_top_n_put_kind_battlefield_then_shuffle_clauses,
    _merge_look_top_one_to_hand_exile_rest_clauses,
    _merge_look_top_put_back_any_order_clauses,
    _merge_look_top_put_onto_battlefield_clauses,
    _merge_look_top_reveal_to_hand_clauses,
    _merge_look_top_split_hand_graveyard_clauses,
    _merge_look_top_x_split_hand_graveyard_clauses,
    _merge_may_discard_if_you_do_clauses,
    _merge_may_exile_discarded_card_then_play_permission_clauses,
    _merge_may_exile_from_graveyard_if_you_do_clauses,
    _merge_may_exile_top_conditional_pump_then_play_clauses,
    _merge_may_then_if_you_do_clauses,
    _merge_prevent_damage_from_target_clauses,
    _merge_process_exile_if_you_do_clauses,
    _merge_return_self_then_if_you_do_clauses,
    _merge_return_target_from_graveyard_tapped_then_attacking_clauses,
    _merge_return_target_then_if_you_do_self_counter_clauses,
    _merge_reveal_hand_choose_discard_clauses,
    _merge_reveal_top_hand_lose_life_equal_to_mana_value_clauses,
    _merge_reveal_top_one_card_per_type_clauses,
    _merge_reveal_top_put_all_quality_to_hand_rest_elsewhere_clauses,
    _merge_reveal_top_to_hand_rest_to_graveyard_clauses,
    _merge_reveal_until_kind_conditional_mv_clauses,
    _merge_reveal_until_kind_then_put_clauses,
    _merge_reveal_until_n_kind_put_onto_battlefield_clauses,
    _merge_sacrifice_one_of_each_clauses,
    _merge_search_hand_shuffle_then_discard_random_clauses,
    _merge_self_pump_and_group_keyword_grant_clauses,
    _merge_split_damage_clauses,
    _merge_surveil_then_for_each_on_top_draw_and_lose_life_clauses,
    _merge_surveil_then_if_quality_to_hand_clauses,
    _merge_tap_target_then_no_untap_clauses,
    _merge_target_player_draws_and_loses_life_clauses,
    _merge_target_then_life_equal_to_its_mana_value_clauses,
)
from .modal import (  # noqa: E402
    _optional_targeted_clause,
    _parse_ante_self_if_you_do_clause,
    _parse_any_player_may_punisher_clause,
    _parse_choose_card_name_for_source_clause,
    _parse_choose_creature_copy_keywords_clause,
    _parse_choose_creature_type_destroy_except_clause,
    _parse_choose_creature_type_treasure_per_match_clause,
    _parse_choose_exactly_two_draw_pump_trample_clause,
    _parse_choose_name_search_and_exile_whole_text,
    _parse_choose_new_targets_clause,
    _parse_choose_new_targets_for_that_spell_clause,
    _parse_choose_odd_or_even_then_destroy_clause,
    _parse_choose_opponent_and_creature_reveal_exile_choice_whole_text,
    _parse_choose_target_exile_until_leaves_then_instead_permanent_clause,
    _parse_choose_target_owner_may_top_else_bottom_clause,
    _parse_choose_target_owner_shuffles_it_clause,
    _parse_choose_target_return_chosen_card_clause,
    _parse_choose_target_then_create_token_copies_pair,
    _parse_choose_target_then_return_to_your_hand_pair,
    _parse_choose_targets_then_return_to_hand_pair,
    _parse_choose_then_object_anaphor_clause_pair,
    _parse_choose_type_draw_per_permanent_clause,
    _parse_choose_type_return_from_graveyard_clause,
    _parse_citys_blessing_instead_clause,
    _parse_condition_clause,
    _parse_condition_instead_clause,
    _parse_condition_instead_clause_for_ability,
    _parse_delayed_single_clause,
    _parse_each_opponent_choose_one_of_each_type_then_sacrifice,
    _parse_each_player_chooses_creature_then_sacrifices_rest_whole_text,
    _parse_gift_promised_return_instead_clause,
    _parse_if_additional_cost_paid_clause,
    _parse_if_condition_you_win_the_game_clause,
    _parse_if_it_was_quality_card_otherwise_triple,
    _parse_if_it_was_target_card_quality_rider_clause_pair,
    _parse_if_self_isnt_a_creature_clause,
    _parse_if_target_card_quality_rider_clause_pair,
    _parse_kicked_choose_return_delayed_clause,
    _parse_may_pay_energy_if_you_do_clause,
    _parse_optional_behold_then_if_you_do_clause,
    _parse_optional_mixed_clause,
    _parse_optional_player_clause,
    _parse_reflexive_discard_count_clause,
    _parse_reflexive_mandatory_mill_clause,
    _parse_reflexive_mandatory_token_clause,
    _parse_reflexive_may_discard_clause,
    _parse_reflexive_may_exile_dead_self_clause,
    _parse_reflexive_may_tap_self_clause,
    _parse_reflexive_pay_energy_clause,
    _parse_reflexive_pay_life_clause,
    _parse_reflexive_pay_mana_and_life_clause,
    _parse_reflexive_pay_mana_clause,
    _parse_reflexive_pay_up_to_n_times_choose_modes_clause,
    _parse_reflexive_sacrifice_clause,
    _parse_reflexive_sacrifice_or_discard_clause,
    _parse_reflexive_self_counter_if_clause,
    _parse_separate_into_two_piles_then_consequence_whole_text,
    _parse_then_if_moved_this_way_clause,
    _resolve_modal_triggered_ability_clause,
    end_the_turn_if_your_turn_effect,
)
from .removal import (  # noqa: E402
    _counter_unless_pays_effect,
    _exile_cards_from_graveyard,
    _exile_matching_from_all_graveyards,
    _graveyard_exile_quality_matcher,
    _hand_exile_quality_matcher,
    _parse_blocking_creature_sacrificed_clause,
    _parse_cast_from_hand_then_exile_clause,
    _parse_conditional_exile_then_play_permission_clauses,
    _parse_conditional_sacrifice_clause,
    _parse_counter_targeting_object_unless_clause,
    _parse_counter_that_spell_clause,
    _parse_counter_unless_pays_then_condition_upgrade_pair,
    _parse_defending_player_exiles_top_n_clause,
    _parse_destroy_each_clause,
    _parse_destroy_each_then_add_mana_per_destroyed,
    _parse_destroy_each_then_remove_all_counters,
    _parse_destroy_or_exile_attached_clause,
    _parse_destroy_target_then_rider_if_type_destroyed_clause,
    _parse_destroy_then_amass_by_referent_then_draw_if_controlled_clause,
    _parse_destroy_then_if_not_attacking_clause_pair,
    _parse_destroy_then_if_that_permanent_was_draw_clause_pair,
    _parse_destroy_two_targets_clause,
    _parse_each_player_exiles_until_clause,
    _parse_each_player_sacrifices_then_mass_reanimate,
    _parse_each_sacrifices_of_their_choice_clause,
    _parse_each_sacrifices_then_if_you_did_clause,
    _parse_exile_all_but_bottom_of_library_clause,
    _parse_exile_all_cards_from_hands_and_graveyards_clause,
    _parse_exile_all_creatures_then_hand_refill_clause,
    _parse_exile_any_number_of_your_permanents_then_delayed_return_clauses,
    _parse_exile_card_then_token_copy_clause,
    _parse_exile_cards_from_your_hand_clause,
    _parse_exile_dead_self_clause,
    _parse_exile_each_clause,
    _parse_exile_from_own_library_end_clause,
    _parse_exile_graveyard_then_creature_rider_clause,
    _parse_exile_hand_draw_then_play_until_next_turn_ability_clause,
    _parse_exile_hand_draw_then_play_until_next_turn_clause,
    _parse_exile_if_mv_return_then_re_exile_clause,
    _parse_exile_into_suspend_clauses,
    _parse_exile_one_of_each_type_copy_cast_clause,
    _parse_exile_self_clause,
    _parse_exile_self_then_return_clause,
    _parse_exile_several_up_to_one_targets_then_return_clause,
    _parse_exile_target_and_top_owner_may_play_clause,
    _parse_exile_target_card_copy_it_cast_clause,
    _parse_exile_target_card_reflexive_creature_counter,
    _parse_exile_target_then_return_tapped_and_attacking_clause,
    _parse_exile_targets_then_owner_play_permission_clauses,
    _parse_exile_targets_until_leaves_then_counters,
    _parse_exile_that_players_library_clause,
    _parse_exile_then_pay_or_else_return_clause,
    _parse_exile_then_play_permission_clauses,
    _parse_exile_then_return_clause_pair,
    _parse_exile_top_card_then_play_permission_clause,
    _parse_exile_top_n_put_from_among_clause,
    _parse_exile_top_of_other_libraries_clause,
    _parse_exile_top_then_cast_types_free_this_turn_whole_text,
    _parse_exile_top_then_play_during_resolution_whole_text,
    _parse_exile_until_leaves_battlefield_clause,
    _parse_exile_until_n_quality_cast_one_free_clause,
    _parse_exiled_card_owner_creates_x_token_clause,
    _parse_face_down_exile_play_clause,
    _parse_for_each_opponent_destroy_clause,
    _parse_for_each_opponent_exile_clause,
    _parse_if_condition_exile_self_and_each_clause,
    _parse_imprint_clause,
    _parse_linked_exile_clause,
    _parse_linked_exile_return_pair_clause,
    _parse_mandatory_sacrifice_then_return_to_hand_clause,
    _parse_mass_destroy_then_conditional_graveyard_hate_clause,
    _parse_may_exile_hand_if_you_do_clause,
    _parse_may_exile_self_and_named_copies_if_you_do_clause,
    _parse_may_exile_self_then_return_clause,
    _parse_may_exile_that_card_return_others_clause,
    _parse_may_sacrifice_then_damage_then_amass_if_excess_clause,
    _parse_multi_part_sacrifice_gain_draw_discard_damage_counters_clause,
    _parse_play_a_card_exiled_with_clause,
    _parse_put_card_exiled_with_self_clause,
    _parse_put_exiled_target_onto_battlefield_clause,
    _parse_regenerate_self_clause,
    _parse_revolt_destroy_or_exile_clause,
    _parse_sacrifice_all_you_control_clause,
    _parse_sacrifice_n_of_a_group_clause,
    _parse_sacrifice_self_clause,
    _parse_sacrifice_unless_discard_trigger,
    _parse_sacrifice_unless_pay_energy,
    _parse_self_cast_while_exiled_clause,
    _parse_shared_type_sacrifice_clause,
    _parse_target_opponent_exile_top_then_put_lands_clause,
    _parse_target_opponent_sacrifice_greatest_mv_clause,
    _parse_target_player_sacrifices_clause,
    _parse_that_player_sacrifices_of_their_choice_clause,
    _parse_then_exile_self_and_return_clause,
    counter_targets,
    destroy_ability_targets,
    each_player_exiles_sacrifices_and_returns_creatures,
    each_player_sacrifices_colored_permanents,
    exile_ability_targets,
    exile_all_graveyards,
    exile_each_opponents_graveyard,
    exile_target_players_graveyard,
    regenerate_ability_targets,
)
from .returns import (  # noqa: E402
    _parse_delayed_blink_clauses,
    _parse_delayed_reanimate_haste_exile_clauses,
    _parse_for_each_opponent_return_to_hand_clause,
    _parse_mass_return_entered_this_turn_clause,
    _parse_mass_return_from_graveyard_to_battlefield_clause,
    _parse_mass_return_from_graveyard_to_hand_clause,
    _parse_mass_return_to_hand_clause,
    _parse_put_creature_from_hand_attacking_then_return,
    _parse_put_from_graveyard_onto_battlefield_clause,
    _parse_return_a_card_at_random_from_graveyard_clause,
    _parse_return_a_land_you_control_clause,
    _parse_return_as_creature_clause,
    _parse_return_cards_from_your_graveyard_clause,
    _parse_return_dead_self_to_hand_clause,
    _parse_return_event_subject_to_battlefield_clause,
    _parse_return_imprinted_clause,
    _parse_return_self_as_type_clause,
    _parse_return_self_from_graveyard_to_battlefield_attached_clause,
    _parse_return_self_from_graveyard_to_battlefield_clause,
    _parse_return_self_then_create_tokens_clause,
    _parse_return_self_then_may_attach_equipment,
    _parse_return_self_to_battlefield_transformed_clause,
    _parse_return_self_to_owners_hand_clause,
    _parse_return_target_and_same_name_from_graveyard_clause,
    _parse_return_target_card_then_instead_battlefield_if_cost_paid_clause,
    _parse_return_target_from_graveyard_gains_then_bounce,
    _parse_return_target_from_graveyard_tapped_and_attacking_clause,
    _parse_return_target_then_conditional_draw,
    _parse_return_that_card_to_owners_hand_clause,
    _parse_return_up_to_n_total_mv_from_graveyard_to_battlefield,
    _parse_return_with_rider_clause,
    _parse_self_return_clause,
    _return_ability_targets_to_battlefield_with_counter,
    return_ability_targets_to_battlefield,
    return_ability_targets_to_hand,
)
from .search import (  # noqa: E402
    _parse_behold_chosen_type_search_clause,
    _parse_outside_the_game_fetch,
    _parse_outside_the_game_play_clause,
    _parse_put_from_outside_the_game_into_hand_spell,
    _parse_search_and_exile_then_shuffle_clause,
    _parse_search_clause,
    _parse_search_distinct_names_clause,
    _parse_search_hand_or_graveyard_clause,
    _parse_search_library_and_outside_distinct_names_opponent_chooses_clause,
    _parse_search_library_graveyard_outside_the_game_clause,
    _parse_search_mv_equal_to_sacrificed_clause,
    _parse_search_mv_less_than_self_power_clause,
    _parse_search_mv_lte_count_clause,
    _parse_search_put_battlefield_tapped_then_behold_untap_clause,
    _parse_search_reveal_shuffle_top_clause,
    _parse_search_split_destination_clause,
    _parse_search_that_many_battlefield_clause,
    _parse_target_player_may_search_named_card_clause,
    _read_search_count,
    _search_descriptions,
)
from .text import (  # noqa: E402
    _parse_all_of_target_player_then_referent_pair,
    _parse_anaphoric_clause_pair,
    _parse_controller_split_target_clause_pair,
    _parse_leading_then_if_otherwise_clause,
    _parse_object_anaphor_clause_pair,
    _parse_object_anaphor_clause_series,
    _parse_plural_target_gain_quoted_ability_whole_text,
    _parse_shared_subject_sentence,
    _parse_unsplittable_whole_text,
    _plain_resolution_sentences,
    _referent_reader,
    _singular_card_type,
    _strip_non_effect_preamble,
)
from .tokens import (  # noqa: E402
    _fold_following_token_grant,
    _parse_amass_clause,
    _parse_amass_then_attach_clause,
    _parse_attacking_token_clause,
    _parse_city_blessing_token_copy_clause,
    _parse_conditional_token_count_on_sacrificed,
    _parse_create_named_permanent_token_clause,
    _parse_create_role_token_clause,
    _parse_create_tapped_attacking_tokens_then_sacrifice,
    _parse_create_that_many_color_pip_tokens_clause,
    _parse_create_token_copies_except_clause,
    _parse_create_token_copy_of_cost_exiled_card_clause,
    _parse_create_token_copy_of_quality_you_control_clause,
    _parse_create_token_copy_of_target_clause,
    _parse_create_token_mill_repeat_clause,
    _parse_create_token_then_attach_clause,
    _parse_create_token_then_copy_spell_retargeted_clause,
    _parse_create_token_then_if_control_n_sacrifice_self_then_clause,
    _parse_create_token_then_if_control_n_that_player_half_life_clause,
    _parse_create_token_then_may_attach_clause,
    _parse_create_tokens_equal_to_event_subject_stat_clause,
    _parse_create_tokens_graveyard_cast_counters_clause,
    _parse_create_tokens_then_counter_other_subtype_clause,
    _parse_create_tokens_then_instead_tapped_attacking_if_cost_paid_clause,
    _parse_create_x_tokens_where_x_is_clause,
    _parse_created_replacement_ability_text,
    _parse_created_replacement_spell_text,
    _parse_created_replacement_then_rest_spell_text,
    _parse_created_trigger_ability_text,
    _parse_created_trigger_spell_text,
    _parse_delayed_token_copy_of_it_clauses,
    _parse_fractal_token_by_cards_drawn_this_turn_clause,
    _parse_investigate_clause,
    _parse_may_cost_then_attacking_token_clause,
    _parse_named_equipment_token_clause,
    _parse_named_token_clause,
    _parse_offspring_token_copy_clause,
    _parse_target_player_creates_clause,
    _parse_target_player_creates_token,
    _parse_token_clause,
    _parse_token_list_clause,
    _parse_token_then_object_anaphor_clause_pair,
    _parse_tokens_then_counter_if_not_cast_from_hand_clause,
    _parse_whole_text_token_clause,
    create_continuous_effect,
)

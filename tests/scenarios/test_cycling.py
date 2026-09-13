"""Cycling: an activated ability that functions in the hand (CR 702.29).

CR 702.29a: "Cycling is an activated ability that functions only while the card
with cycling is in a player's hand. 'Cycling [cost]' means "[Cost], Discard this
card: Draw a card.""

That zone is the whole point of this file. `Game.begin_activating` only ever
activates an ability of a battlefield permanent, so cycling had no execution
path at all; `machines/keywords.KeywordActivation` is the general form that
names the zone an ability functions in.

CR 702.29b keeps the ability from vanishing elsewhere: "Although the cycling
ability can be activated only if the card is in a player's hand, it continues to
exist while the object is on the battlefield and in all other zones."

CR 702.29e is typecycling, and CR 702.29f says a typecycling ability *is* a
cycling ability. The discard is part of the cost (CR 601.2h shape), which is why
the card is already in the graveyard by the time the draw happens.

CR 702.29e in full: "[Type]cycling [cost]" means "[Cost], Discard this card:
Search your library for a [type] card, reveal it, and put it into your hand.
Then shuffle your library." ... "This type is usually a subtype (as in
"mountaincycling") but can be any card type, subtype, supertype, or combination
thereof (as in "basic landcycling")." So the search is a real CR 701.23a search:
the whole library is looked at and the player *chooses* which matching card to
find, and CR 701.23b ("isn't required to find some or all of those cards even
if they're present") makes finding nothing a legal answer for a stated type.
CR 701.20a makes the reveal a showing to all players, and CR 701.24a's shuffle
closes it. The typecycling half used to take the first match in library order,
never asking, never revealing, never shuffling - Lorien Revealed's
Islandcycling picked the Island for the player in a live game.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind, DecisionPending
from magic_cards_model.machines.keywords import (
    KEYWORD_EFFECTS,
    KeywordActivation,
    cycle,
    cycling_abilities,
    cycling_activation,
)
from magic_cards_model.models import CardState, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from


def board(**kwargs) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", **kwargs)
        .player("bob", battlefield=["Mountain"])
    )


def pay_with(*sources):
    def hook(payment):
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))

    return hook


def test_the_cycling_ability_is_read_off_the_printed_line():
    """CR 702.1a: the cost is printed after the keyword, mana or sentence."""
    (censor,) = cycling_abilities(card("Censor"))
    assert censor.cost == "{U}"
    assert censor.cost_is_mana

    (wraith,) = cycling_abilities(card("Street Wraith"))
    assert wraith.cost == "Pay 2 life"
    assert not wraith.cost_is_mana


def test_cycling_discards_the_card_and_draws_one():
    """CR 702.29a, the whole ability."""
    scenario = board(hand=["Censor"], library=["Lightning Bolt"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    drawn = cycle(scenario.game, censor, "alice", pay_with(island))

    assert censor.zone is Zone.GRAVEYARD
    assert [state.name for state in drawn] == ["Lightning Bolt"]
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice").zone is Zone.HAND


def test_a_life_payment_cycling_cost_is_paid_in_life():
    """Street Wraith prints its cost after an em dash: `Cycling—Pay 2 life.`"""
    scenario = board(hand=["Street Wraith"], library=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    cycle(scenario.game, wraith, "alice")

    assert scenario.player("alice").life == 18
    assert wraith.zone is Zone.GRAVEYARD


def test_cycling_cannot_be_activated_from_the_battlefield():
    """CR 702.29a: "functions only while the card ... is in a player's hand"."""
    scenario = board(battlefield=["Striped Riverwinder", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    riverwinder = scenario.creature("Striped Riverwinder")
    activation = cycling_activation(scenario.game, riverwinder, "alice")

    assert "functions in the hand" in (activation.why_not() or "")
    with pytest.raises(ValueError, match="functions in the hand"):
        activation.begin_paying()


def test_the_ability_still_exists_on_the_battlefield():
    """CR 702.29b: it continues to exist, it just cannot be activated."""
    scenario = board(battlefield=["Striped Riverwinder"]).build()
    riverwinder = scenario.creature("Striped Riverwinder")
    assert cycling_abilities(riverwinder.card)


def test_cycling_uses_the_stack_and_can_be_responded_to():
    """It is an ordinary activated ability, so it is not a mana ability.

    CR 605.1a would take it off the stack if it added mana; it draws a card, so
    the ability sits there and the opponent gets a window - which is also why
    the card is in the graveyard before the draw happens.
    """
    scenario = board(hand=["Censor"], library=["Lightning Bolt"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island")
    activation = cycling_activation(scenario.game, censor, "alice")
    payment = activation.begin_paying()
    payment.tap_for_mana(island, mana_from(island))
    payment.pay()

    on_stack = activation.activate()
    assert on_stack in scenario.game.stack
    assert censor.zone is Zone.GRAVEYARD  # the discard was a cost
    assert scenario.player("alice").hand == []

    activation.resolve()
    assert scenario.game.stack_is_empty
    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_a_cost_that_cannot_be_paid_leaves_the_card_in_hand():
    """CR 118.3: no resources, no payment - and no discard either."""
    scenario = board(hand=["Censor"], library=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    censor = scenario.find("Censor", Zone.HAND, "alice")
    activation = cycling_activation(scenario.game, censor, "alice")
    payment = activation.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()

    assert censor.zone is Zone.HAND


def test_typecycling_searches_the_library_for_that_type():
    """CR 702.29e: "[Type]cycling [cost]" searches instead of drawing.

    CR 702.29f makes it a cycling ability all the same, so it shares every other
    rule - the hand-only zone and the discard as a cost.
    """
    scenario = board(
        hand=["Generous Ent"],
        library=["Lightning Bolt", "Forest", "Island"],
        battlefield=["Forest", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ent = scenario.find("Generous Ent", Zone.HAND, "alice")
    (ability,) = cycling_abilities(ent.card)
    assert ability.canonical == "Forestcycling"

    found = cycle(
        scenario.game, ent, "alice", pay_with(*scenario.untapped_sources("Forest", "Forest"))
    )

    assert ent.zone is Zone.GRAVEYARD
    assert [state.name for state in found] == ["Forest"]
    assert scenario.find("Forest", Zone.HAND, "alice").zone is Zone.HAND
    # CR 701.24a: what the search left behind is shuffled, so only the set of
    # cards left is asserted, never their order.
    remaining = sorted(state.name for state in scenario.player("alice").library)
    assert remaining == ["Island", "Lightning Bolt"]


def test_the_activation_is_the_general_form_for_any_zone():
    """The gap this closes: an activated ability that is not on the battlefield."""
    scenario = board(hand=["Censor"], battlefield=["Island"]).build()
    censor = scenario.find("Censor", Zone.HAND, "alice")
    activation = cycling_activation(scenario.game, censor, "alice")

    assert isinstance(activation, KeywordActivation)
    assert activation.zone is Zone.HAND
    assert activation.why_not() is None


# -- typecycling is a search the player answers (CR 702.29e, CR 701.23) -------

LORIEN = "L\u00f3rien Revealed"


def _library_named(scenario: Scenario, name: str) -> list[CardState]:
    return [state for state in scenario.player("alice").library if state.name == name]


def _search_questions(scenario: Scenario, source: str) -> list[Decision]:
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.source == source
    ]


def _islandcycling_board() -> Scenario:
    """Lorien Revealed in hand; a library holding a non-Island, two Islands and
    a fetchland that is a land but not an Island."""
    return board(
        hand=[LORIEN],
        library=["Lightning Bolt", "Island", "Island", "Flooded Strand"],
        battlefield=["Island"],
    )


def _cycle_lorien(scenario: Scenario):
    lorien = scenario.find(LORIEN, Zone.HAND, "alice")
    found = cycle(scenario.game, lorien, "alice", pay_with(*scenario.untapped_sources("Island")))
    return lorien, found


def test_islandcycling_offers_exactly_the_islands_in_the_library():
    """CR 701.23a: the whole library is looked at, and only cards matching the
    stated type are findable - not the Bolt, not the fetchland that is merely a
    land. CR 701.23b makes the question inexact: up to one card."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = _library_named(scenario, "Island")

    _cycle_lorien(scenario)

    (question,) = _search_questions(scenario, LORIEN)
    assert question.player == "alice"
    assert set(question.cards) == {state.id for state in islands}
    assert list(question.card_labels) == ["Island", "Island"]
    assert question.amount == 1
    assert question.exact is False


def test_islandcycling_finds_the_island_the_player_chose():
    """The choice is the player's: the second Island, not the first in order."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = _library_named(scenario, "Island")
    scenario.will_choose_cards(second, username="alice", source=LORIEN)

    lorien, found = _cycle_lorien(scenario)

    assert found == [second]
    assert second.zone is Zone.HAND
    assert second in scenario.player("alice").hand
    assert first in scenario.player("alice").library
    assert lorien.zone is Zone.GRAVEYARD


def test_typecycling_may_find_nothing_and_the_card_is_still_cycled():
    """CR 701.23b: searching a hidden zone for a stated quality, the player
    "isn't required to find" the card even though it is there. The discard was
    the cost (CR 702.29a), so the card is cycled regardless."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(username="alice", source=LORIEN)

    lorien, found = _cycle_lorien(scenario)

    assert found == []
    assert lorien.zone is Zone.GRAVEYARD
    assert scenario.player("alice").hand == []
    assert len(_library_named(scenario, "Island")) == 2
    assert scenario.game.reveals == []


def test_typecycling_pauses_on_the_search_rather_than_resolving():
    """With nobody scripted and pausing on, the resolving ability stops at the
    CHOOSE_CARDS question (CR 608.2d) instead of picking for the player."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        _cycle_lorien(scenario)

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.CHOOSE_CARDS
    assert pending.decision.player == "alice"
    assert pending.decision.source == LORIEN
    assert scenario.player("alice").hand == []
    assert len(_library_named(scenario, "Island")) == 2


def test_the_found_card_is_revealed_to_every_player():
    """CR 702.29e's "reveal it", CR 701.20a: shown to all players, recorded
    once, while it is still in the library (CR 701.20b: revealing moves
    nothing)."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _, second = _library_named(scenario, "Island")
    scenario.will_choose_cards(second, username="alice", source=LORIEN)

    _cycle_lorien(scenario)

    (reveal,) = scenario.game.reveals
    assert reveal.card_id == second.id
    assert reveal.card_name == "Island"
    assert reveal.revealed_by == "alice"
    assert reveal.zone is Zone.LIBRARY
    assert reveal.source == LORIEN


def test_the_library_is_shuffled_after_the_search():
    """CR 702.29e's "Then shuffle your library", CR 701.24a - counted, because a
    seeded shuffle may leave a short library in its old order."""
    scenario = _islandcycling_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.game.shuffles_performed

    _cycle_lorien(scenario)

    assert scenario.game.shuffles_performed == before + 1


def test_the_library_is_shuffled_even_when_nothing_is_found():
    """The shuffle is its own instruction, not a consequence of finding."""
    scenario = board(
        hand=[LORIEN], library=["Lightning Bolt", "Flooded Strand"], battlefield=["Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.game.shuffles_performed

    _, found = _cycle_lorien(scenario)

    assert found == []
    assert _search_questions(scenario, LORIEN) == []
    assert scenario.game.shuffles_performed == before + 1


# -- generality: typecycling cards outside every deck pool ---------------------


def test_basic_landcycling_offers_only_basic_lands():
    """Ash Barrens' "Basic landcycling {1}" names a supertype plus a card type -
    CR 702.29e's "combination thereof". Breeding Pool is a land with basic land
    types but is not basic, so it is not offered; the Bolt is not a land."""
    scenario = board(
        hand=["Ash Barrens"],
        library=["Breeding Pool", "Forest", "Lightning Bolt", "Island"],
        battlefield=["Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = _library_named(scenario, "Forest")
    (island,) = _library_named(scenario, "Island")
    scenario.will_choose_cards(island, username="alice", source="Ash Barrens")

    barrens = scenario.find("Ash Barrens", Zone.HAND, "alice")
    found = cycle(scenario.game, barrens, "alice", pay_with(*scenario.untapped_sources("Island")))

    (question,) = _search_questions(scenario, "Ash Barrens")
    assert set(question.cards) == {forest.id, island.id}
    assert found == [island]
    assert island.zone is Zone.HAND
    assert barrens.zone is Zone.GRAVEYARD


def test_wizardcycling_searches_for_a_creature_subtype():
    """Vedalken Aethermage's Wizardcycling names a creature type, not a land
    type - it used to have no effect at all and cycled into nothing."""
    scenario = board(
        hand=["Vedalken Aethermage"],
        library=["Grizzly Bears", "Aether Adept", "Island", "Harbinger of the Seas"],
        battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (adept,) = _library_named(scenario, "Aether Adept")
    (harbinger,) = _library_named(scenario, "Harbinger of the Seas")
    scenario.will_choose_cards(harbinger, username="alice", source="Vedalken Aethermage")

    aethermage = scenario.find("Vedalken Aethermage", Zone.HAND, "alice")
    found = cycle(
        scenario.game,
        aethermage,
        "alice",
        pay_with(*scenario.untapped_sources("Island", "Island", "Island")),
    )

    (question,) = _search_questions(scenario, "Vedalken Aethermage")
    assert set(question.cards) == {adept.id, harbinger.id}
    assert found == [harbinger]
    assert harbinger.zone is Zone.HAND
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == harbinger.id


def test_swampcycling_finds_a_nonbasic_land_with_the_swamp_type():
    """Twisted Abomination's Swampcycling looks for the Swamp *type* (CR 305.6),
    so Watery Grave (Land - Island Swamp) is findable beside a basic Swamp."""
    scenario = board(
        hand=["Twisted Abomination"],
        library=["Island", "Swamp", "Watery Grave"],
        battlefield=["Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = _library_named(scenario, "Swamp")
    (grave,) = _library_named(scenario, "Watery Grave")
    scenario.will_choose_cards(grave, username="alice", source="Twisted Abomination")

    abomination = scenario.find("Twisted Abomination", Zone.HAND, "alice")
    found = cycle(
        scenario.game,
        abomination,
        "alice",
        pay_with(*scenario.untapped_sources("Swamp", "Swamp")),
    )

    (question,) = _search_questions(scenario, "Twisted Abomination")
    assert set(question.cards) == {swamp.id, grave.id}
    assert found == [grave]
    assert grave.zone is Zone.HAND


def test_no_cycling_keyword_has_a_row_of_its_own():
    """Typecycling is dispatched by the keyword's shape - any "<type>cycling" -
    so no per-type row exists to forget a type in."""
    assert not [name for name in KEYWORD_EFFECTS if name.endswith("cycling")]

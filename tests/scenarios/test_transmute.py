"""Transmute: discard this, tutor by mana value (CR 702.53).

CR 702.53a: "Transmute is an activated ability that functions only while the
card with transmute is in a player's hand. 'Transmute [cost]' means '[Cost],
Discard this card: Search your library for a card with the same mana value
as the discarded card, reveal that card, and put it into your hand. Then
shuffle your library. Activate only as a sorcery.'"

The same shape as cycling's own typecycling variant (CR 702.29e) - the
discard is folded into the cost, and the search predicate is read off the
just-discarded card rather than off the printed line, the way typecycling's
predicate is read off the keyword's own suffix rather than off a sentence.
Built with `off_zone_abilities`/`KeywordActivation`, the general machine
cycling and unearth already use for an ability that functions off the
battlefield (CR 113.6j).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.

The search is CR 701.23a's: the whole library is looked at and the player
chooses which card of that mana value to find. "A card with the same mana value"
is a stated quality, so CR 701.23b lets the player find nothing even when one is
there. CR 701.20a's reveal shows the found card to all players, and CR 701.24a
shuffles afterwards. The effect used to take the first match in library order
without asking, revealing or shuffling.

Tolaria West (Transmute {1}{U}{U}, mana value 0 - a land) is the assigned
card. Muddle the Mixture (Transmute {1}{U}{U} too, but mana value 2 - an
instant that counters a spell) is not in the deck pool and not named in the
brief, and proves the search predicate comes from the *discarded card's own*
mana value rather than from a number baked into either printing's reminder
text - Tolaria West's reminder literally spells out "mana value 0" (its own,
fixed value) while Muddle's spells out "the same mana value as this card"; a
reader keyed to either exact wording would have missed the other.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind, DecisionPending
from magic_cards_model.machines.keywords import (
    KeywordActivation,
    off_zone_abilities,
    off_zone_activation,
    transmute_abilities,
    transmute_activation,
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


def test_the_transmute_ability_is_read_off_the_printed_line():
    (ability,) = transmute_abilities(card("Tolaria West"))
    assert ability.cost == "{1}{U}{U}"
    assert ability.cost_is_mana


def test_transmute_discards_and_searches_by_mana_value():
    """Tolaria West is mana value 0 - Mishra's Bauble (also mana value 0) is
    what the search should find in a library stacked with something else on
    top."""
    scenario = board(
        hand=["Tolaria West"],
        library=["Lightning Bolt", "Mishra's Bauble"],
        battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    west = scenario.find("Tolaria West", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")
    activation = transmute_activation(scenario.game, west, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    found = activation.resolve()

    assert west.zone is Zone.GRAVEYARD, "discarded as part of the cost (CR 601.2h)"
    assert found is not None
    assert found.name == "Mishra's Bauble"
    assert found.zone is Zone.HAND
    # CR 701.24a: only what is left is asserted, never its order.
    assert [state.name for state in scenario.player("alice").library] == ["Lightning Bolt"]


def test_transmute_finds_nothing_when_no_card_matches():
    scenario = board(
        hand=["Tolaria West"], library=["Lightning Bolt"], battlefield=["Island"] * 3
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    west = scenario.find("Tolaria West", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")
    activation = transmute_activation(scenario.game, west, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    found = activation.resolve()

    assert found is None
    assert scenario.find("Lightning Bolt", Zone.LIBRARY, "alice").zone is Zone.LIBRARY


def test_transmute_only_functions_in_the_hand():
    scenario = board(battlefield=["Tolaria West"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    west = scenario.game.battlefield[0]
    activation = transmute_activation(scenario.game, west, "alice")

    assert "functions in the hand" in (activation.why_not() or "")


def test_transmute_is_a_sorcery_speed_activation():
    scenario = board(hand=["Tolaria West"], battlefield=["Island"] * 3).build()
    scenario.start_at(Step.END_STEP)

    west = scenario.find("Tolaria West", Zone.HAND, "alice")
    activation = transmute_activation(scenario.game, west, "alice")

    assert "sorcery" in (activation.why_not() or "")


def test_off_zone_abilities_lists_transmute():
    entries = off_zone_abilities(card("Tolaria West"))
    assert [entry.family for entry in entries] == ["transmute"]

    scenario = board(
        hand=["Tolaria West"], library=["Mishra's Bauble"], battlefield=["Island"] * 3
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    west = scenario.find("Tolaria West", Zone.HAND, "alice")
    activation = off_zone_activation(scenario.game, west, "alice", 0)
    assert isinstance(activation, KeywordActivation)
    assert activation.keyword.lower() == "transmute"


# -- generality: a second, un-named transmute printing -----------------------


def test_muddle_the_mixture_searches_by_its_own_mana_value():
    """Muddle the Mixture is mana value 2 - Lightning Bolt (mana value 1)
    would not match; Counterspell (mana value 2) does."""
    scenario = board(
        hand=["Muddle the Mixture"],
        library=["Lightning Bolt", "Counterspell"],
        battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    muddle = scenario.find("Muddle the Mixture", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")
    activation = transmute_activation(scenario.game, muddle, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    found = activation.resolve()

    assert muddle.zone is Zone.GRAVEYARD
    assert found is not None
    assert found.name == "Counterspell"


# -- the search is the player's choice (CR 701.23a-b) ------------------------


def _library_named(scenario: Scenario, name: str) -> list[CardState]:
    return [state for state in scenario.player("alice").library if state.name == name]


def _search_questions(scenario: Scenario, source: str) -> list[Decision]:
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.CHOOSE_CARDS and decision.source == source
    ]


def _west_board() -> Scenario:
    """Tolaria West (mana value 0) in hand; a library with two mana value 0 cards
    among others of other mana values."""
    return board(
        hand=["Tolaria West"],
        library=["Lightning Bolt", "Mishra's Bauble", "Counterspell", "Ornithopter"],
        battlefield=["Island", "Island", "Island"],
    )


def _transmute(scenario: Scenario, name: str):
    transmuted = scenario.find(name, Zone.HAND, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")
    activation = transmute_activation(scenario.game, transmuted, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return transmuted, activation.resolve()


def test_transmute_offers_exactly_the_cards_of_that_mana_value():
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bauble,) = _library_named(scenario, "Mishra's Bauble")
    (thopter,) = _library_named(scenario, "Ornithopter")

    _transmute(scenario, "Tolaria West")

    (question,) = _search_questions(scenario, "Tolaria West")
    assert question.player == "alice"
    assert set(question.cards) == {bauble.id, thopter.id}
    assert question.amount == 1
    assert question.exact is False


def test_transmute_finds_the_card_the_player_chose():
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bauble,) = _library_named(scenario, "Mishra's Bauble")
    (thopter,) = _library_named(scenario, "Ornithopter")
    scenario.will_choose_cards(thopter, username="alice", source="Tolaria West")

    west, found = _transmute(scenario, "Tolaria West")

    assert found is thopter
    assert thopter.zone is Zone.HAND
    assert bauble in scenario.player("alice").library
    assert west.zone is Zone.GRAVEYARD


def test_transmute_may_find_nothing_even_when_a_card_matches():
    """CR 701.23b: a stated quality need not be found."""
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(username="alice", source="Tolaria West")

    west, found = _transmute(scenario, "Tolaria West")

    assert found is None
    assert west.zone is Zone.GRAVEYARD
    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == 4
    assert scenario.game.reveals == []


def test_transmute_pauses_on_the_search_rather_than_resolving():
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.decisions.pause_when_unanswered = True

    with pytest.raises(DecisionPending) as excinfo:
        _transmute(scenario, "Tolaria West")

    pending = excinfo.value.pending
    assert pending.decision.kind is DecisionKind.CHOOSE_CARDS
    assert pending.decision.player == "alice"
    assert pending.decision.source == "Tolaria West"
    assert scenario.player("alice").hand == []


def test_the_transmuted_for_card_is_revealed():
    """CR 702.53a's "reveal that card", CR 701.20a."""
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (thopter,) = _library_named(scenario, "Ornithopter")
    scenario.will_choose_cards(thopter, username="alice", source="Tolaria West")

    _transmute(scenario, "Tolaria West")

    (reveal,) = scenario.game.reveals
    assert reveal.card_id == thopter.id
    assert reveal.revealed_by == "alice"
    assert reveal.zone is Zone.LIBRARY
    assert reveal.source == "Tolaria West"


def test_transmute_shuffles_the_library():
    """CR 702.53a's "Then shuffle your library", found or not."""
    scenario = _west_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = scenario.game.shuffles_performed

    _transmute(scenario, "Tolaria West")

    assert scenario.game.shuffles_performed == before + 1


def test_muddle_the_mixture_offers_and_finds_by_its_own_mana_value():
    """Muddle the Mixture (mana value 2, outside every deck pool): Counterspell
    and Abrupt Decay are offered, the Bolt and the Island are not, and the
    player's pick of the second is the card found."""
    scenario = board(
        hand=["Muddle the Mixture"],
        library=["Lightning Bolt", "Counterspell", "Island", "Abrupt Decay"],
        battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (counterspell,) = _library_named(scenario, "Counterspell")
    (decay,) = _library_named(scenario, "Abrupt Decay")
    scenario.will_choose_cards(decay, username="alice", source="Muddle the Mixture")
    before = scenario.game.shuffles_performed

    muddle, found = _transmute(scenario, "Muddle the Mixture")

    (question,) = _search_questions(scenario, "Muddle the Mixture")
    assert set(question.cards) == {counterspell.id, decay.id}
    assert found is decay
    assert decay.zone is Zone.HAND
    assert muddle.zone is Zone.GRAVEYARD
    (reveal,) = scenario.game.reveals
    assert reveal.card_id == decay.id
    assert scenario.game.shuffles_performed == before + 1

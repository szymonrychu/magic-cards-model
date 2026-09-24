""" "Reveal the top card of your library. If it's a <kind>[ or <kind>] card,
put it into your hand. Otherwise, you may put it <somewhere>."
(`_LOOK_TOP_CARD_CONDITIONAL_RE` / `_parse_look_top_card_conditional_clause`
in `machines/effects.py`).

The reader already knew Fecund Greenshell's and Coiling Oracle's shapes, where
the *kept* branch may carry a "you may" and the *otherwise* branch is
mandatory. Two things were missing:

- a disjunction of card types - **Ajani, Sleeper Agent**'s `+1`: "If it's a
  creature or planeswalker card, put it into your hand";
- an optional else-arm - "Otherwise, you may put it on the bottom of your
  library" (Ajani) / "Otherwise, you may put it into your graveyard"
  (**Nylea, Keen-Eyed**'s `{2}{G}`, the second printing: not a listed card,
  not in any api deck, a different destination and an activated ability
  paid with mana instead of loyalty).

Declining the optional else-arm leaves the card where it is - on top of the
library, still revealed information but not moved (CR 701.20a: revealing a
card doesn't cause it to leave its zone).

The type check reads the card as it is in the library:

- CR 712.8a - a double-faced card outside the battlefield and stack has only
  its front face's characteristics, so Fable of the Mirror-Breaker (a Saga
  whose back face is a creature) is *not* a creature card here, and
  Blackbloom Rogue (a modal DFC with a creature front face) is.
- CR 709.4 / 709.4c - a split card in the library has both halves' card
  types combined; neither half of Bound // Determined is a creature or
  planeswalker, so it takes the otherwise branch.

An empty library means nothing to reveal: the loyalty cost is still paid
(CR 606.3 lets the ability be activated; CR 609.3 does only as much as
possible on resolution).

CR numbers read with `mise run rules:find` in the session that wrote this
file: 606.3, 609.3, 701.20a, 709.4, 709.4c, 712.8a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

AJANI = "Ajani, Sleeper Agent"
NYLEA = "Nylea, Keen-Eyed"


def _ajani_board(library: list[str]) -> tuple[PlayedScenario, object]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[AJANI], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.put_onto_battlefield(AJANI, "alice")
    return scenario, ajani


def _plus_one(scenario: PlayedScenario, ajani) -> None:
    scenario.activate(ajani, index=0, username="alice")
    scenario.pass_until_resolved()


def _names(cards) -> list[str]:
    return [card.name for card in cards]


def test_a_creature_card_goes_to_hand_without_a_question():
    scenario, ajani = _ajani_board(["Tarmogoyf", "Forest"])
    loyalty = ajani.counter_count(Counter.LOYALTY)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Tarmogoyf"]
    assert _names(alice.library) == ["Forest"]
    assert ajani.counter_count(Counter.LOYALTY) == loyalty + 1
    assert [q for q in scenario.questions_asked() if q.source == AJANI] == []


def test_a_planeswalker_card_goes_to_hand():
    scenario, ajani = _ajani_board(["Vivien, Arkbow Ranger", "Forest"])

    _plus_one(scenario, ajani)

    assert _names(scenario.player("alice").hand) == ["Vivien, Arkbow Ranger"]


def test_any_other_card_may_go_to_the_bottom():
    scenario, ajani = _ajani_board(["Lightning Bolt", "Forest", "Island"])
    scenario.will_take_the_may(True, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _names(alice.library) == ["Forest", "Island", "Lightning Bolt"]


def test_declining_leaves_the_card_on_top():
    scenario, ajani = _ajani_board(["Lightning Bolt", "Forest"])
    scenario.will_take_the_may(False, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _names(alice.library) == ["Lightning Bolt", "Forest"]


def test_the_card_is_revealed_to_every_player():
    scenario, ajani = _ajani_board(["Lightning Bolt"])
    scenario.will_take_the_may(False, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    reveals = [r for r in scenario.game.reveals if r.source == AJANI]
    assert [(r.card_name, r.viewers) for r in reveals] == [("Lightning Bolt", None)]


def test_a_modal_double_faced_card_with_a_creature_front_face_is_a_creature_card():
    """CR 712.8a: front face only - Blackbloom Rogue's front is a creature."""
    scenario, ajani = _ajani_board(["Blackbloom Rogue", "Forest"])

    _plus_one(scenario, ajani)

    assert _names(scenario.player("alice").hand) == ["Blackbloom Rogue"]


def test_a_modal_double_faced_card_with_a_land_back_face_uses_its_front_face():
    """CR 712.8a: Shatterskull Smashing is a sorcery card in the library."""
    scenario, ajani = _ajani_board(["Shatterskull Smashing", "Forest"])
    scenario.will_take_the_may(True, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.library[-1].name.startswith("Shatterskull Smashing")


def test_a_double_faced_card_whose_back_face_is_a_creature_is_not_a_creature_card():
    """CR 712.8a: Fable of the Mirror-Breaker is a Saga in the library; its
    back face, Reflection of Kiki-Jiki, is a creature but does not count."""
    scenario, ajani = _ajani_board(["Fable of the Mirror-Breaker", "Forest"])
    scenario.will_take_the_may(True, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.library[-1].name.startswith("Fable of the Mirror-Breaker")


def test_a_split_card_with_no_creature_half_takes_the_otherwise_branch():
    """CR 709.4c: a split card has the card types of both halves - here two
    instants, so it is neither a creature nor a planeswalker card."""
    scenario, ajani = _ajani_board(["Bound // Determined", "Forest"])
    scenario.will_take_the_may(True, username="alice", source=AJANI)

    _plus_one(scenario, ajani)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert alice.library[-1].name.startswith("Bound")


def test_an_empty_library_still_pays_the_loyalty_and_does_nothing_else():
    scenario, ajani = _ajani_board([])
    loyalty = ajani.counter_count(Counter.LOYALTY)

    _plus_one(scenario, ajani)

    assert scenario.player("alice").hand == []
    assert ajani.counter_count(Counter.LOYALTY) == loyalty + 1
    assert scenario.game.unmodeled_trigger_effect_notices == []


# -- Nylea, Keen-Eyed: "Otherwise, you may put it into your graveyard" -------


def _nylea_board(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[NYLEA, "Forest", "Forest", "Forest"], library=library)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _activate_nylea(scenario: PlayedScenario) -> None:
    nylea = scenario.find(NYLEA, Zone.BATTLEFIELD, "alice")
    scenario.activate(
        nylea, *scenario.untapped_sources("Forest", "Forest", "Forest"), username="alice"
    )
    scenario.pass_until_resolved()


def test_nylea_puts_a_creature_card_into_hand():
    scenario = _nylea_board(["Tarmogoyf", "Island"])

    _activate_nylea(scenario)

    alice = scenario.player("alice")
    assert _names(alice.hand) == ["Tarmogoyf"]
    assert _names(alice.library) == ["Island"]


def test_nylea_may_put_a_noncreature_card_into_the_graveyard():
    scenario = _nylea_board(["Lightning Bolt", "Island"])
    scenario.will_take_the_may(True, username="alice", source=NYLEA)

    _activate_nylea(scenario)

    alice = scenario.player("alice")
    assert alice.hand == []
    assert _names(alice.graveyard) == ["Lightning Bolt"]
    assert _names(alice.library) == ["Island"]


def test_nylea_declined_leaves_the_card_on_top():
    scenario = _nylea_board(["Lightning Bolt", "Island"])
    scenario.will_take_the_may(False, username="alice", source=NYLEA)

    _activate_nylea(scenario)

    alice = scenario.player("alice")
    assert alice.graveyard == []
    assert _names(alice.library) == ["Lightning Bolt", "Island"]


def test_nylea_does_not_take_a_planeswalker():
    """The kind list is read, not assumed: Nylea names only creature cards."""
    scenario = _nylea_board(["Vivien, Arkbow Ranger"])
    scenario.will_take_the_may(False, username="alice", source=NYLEA)

    _activate_nylea(scenario)

    assert scenario.player("alice").hand == []

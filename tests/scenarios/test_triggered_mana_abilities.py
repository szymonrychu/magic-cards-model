"""Triggered mana abilities resolve at once, off the stack, and count toward
paying a cost (CR 605.1b, CR 605.4a, CR 106.12a, CR 601.2g-h).

- **CR 605.1b** - "A triggered ability is a mana ability if it meets all of
  the following criteria: it doesn't require a target (see rule 115.6), it
  triggers from the activation or resolution of an activated mana ability
  (see rule 605.1a) or from mana being added to a player's mana pool, and it
  could add mana to a player's mana pool when it resolves."
- **CR 605.4a** - "A triggered mana ability doesn't go on the stack, so it
  can't be targeted, countered, or otherwise responded to. Rather, it resolves
  immediately after the mana ability that triggered it, without waiting for
  priority."
- **CR 106.12a** - "An ability that triggers whenever a permanent 'is tapped
  for mana' or is tapped for mana of a specified type triggers whenever such a
  mana ability resolves and produces mana or the specified type of mana."
- **CR 605.3a** - a mana ability may be activated "whenever they are casting a
  spell or activating an ability that requires a mana payment", which is where
  CR 601.2g puts it; the extra mana a trigger adds is in the pool when CR
  601.2h's payment is made.

Battle 7 found Leyline of Abundance and Badgermole Cub (deck pool) putting
"Whenever you tap a creature for mana, add an additional {G}." on the stack
(B7-02), and the payment search refusing casts only that mana could pay
(B7-03). Wild Growth, Fertile Ground, Nirkana Revenant, Vernal Bloom and Zendikar
Resurgent are in neither deck pool; each prints a different subject or a
different amount of mana.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import could_pay_mana_cost
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.action import ActionKind, Affordability
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def _board(alice_battlefield: list[str], alice_hand: list[str] | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=alice_battlefield, hand=alice_hand or [])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- resolving at once (CR 605.4a) ------------------------------------------


def test_leyline_of_abundance_adds_its_mana_at_once_without_the_stack():
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves")

    scenario.activate(elves)

    assert scenario.stack_names() == []
    assert scenario.game.pending_triggers == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_two_triggered_mana_abilities_off_one_tap_both_resolve_at_once():
    scenario = _board(["Leyline of Abundance", "Badgermole Cub", "Llanowar Elves"])

    scenario.activate(scenario.creature("Llanowar Elves"))

    assert scenario.stack_names() == []
    assert [q.kind for q in scenario.questions_asked()] == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 3}


def test_wild_growth_adds_to_the_enchanted_lands_controller_at_once():
    scenario = _board(["Forest", "Forest"], alice_hand=["Wild Growth"])
    payer, enchanted = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Wild Growth", payer, targets=[enchanted])
    scenario.player("alice").mana_pool.empty()

    scenario.activate(enchanted)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}


def test_fertile_ground_asks_the_color_as_its_mana_is_added():
    scenario = _board(["Forest", "Forest", "Forest"], alice_hand=["Fertile Ground"])
    first, second, enchanted = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Fertile Ground", first, second, targets=[enchanted])
    scenario.player("alice").mana_pool.empty()
    scenario.will_choose(Color.BLUE.value, source="Fertile Ground")

    scenario.activate(enchanted)

    assert scenario.stack_names() == []
    asked = [q for q in scenario.questions_asked() if q.source == "Fertile Ground"]
    assert asked[-1].kind is DecisionKind.CHOOSE_A_QUALITY
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1, Color.BLUE: 1}


def test_nirkana_revenant_reads_a_land_subtype_in_its_condition():
    scenario = _board(["Nirkana Revenant", "Swamp", "Forest"])
    (swamp,) = scenario.untapped_sources("Swamp")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(swamp)
    scenario.activate(forest)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 2, Color.GREEN: 1}


def test_vernal_bloom_gives_the_extra_mana_to_whoever_tapped_the_forest():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vernal Bloom"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.CLEANUP)
    scenario.advance()
    (forest,) = scenario.untapped_sources("Forest", username="bob")

    scenario.activate(forest, username="bob")

    assert scenario.stack_names() == []
    assert scenario.player("bob").mana_pool.floating == {Color.GREEN: 2}
    assert scenario.player("alice").mana_pool.total == 0


def test_zendikar_resurgent_adds_one_mana_of_the_type_the_land_produced():
    scenario = _board(["Zendikar Resurgent", "Island"])

    scenario.activate(scenario.untapped_sources("Island")[0])

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 2}


# -- paying with that mana (CR 601.2g-h) -------------------------------------


def test_a_creature_tapped_while_paying_brings_leylines_mana_into_the_payment():
    """B7-03: Llanowar Elves alone plus Leyline of Abundance pays {1}{G}."""
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"], alice_hand=["Grizzly Bears"])
    elves = scenario.creature("Llanowar Elves")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.cast(bears, "alice", mana_sources=[elves])

    assert bears.zone is Zone.STACK
    assert scenario.stack_names() == ["Grizzly Bears"]
    assert scenario.player("alice").mana_pool.total == 0


def test_a_pinned_source_colour_list_can_name_the_triggered_mana_too():
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"], alice_hand=["Grizzly Bears"])
    elves = scenario.creature("Llanowar Elves")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.cast(bears, "alice", mana_sources=[(elves, [Color.GREEN, Color.GREEN])])

    assert scenario.stack_names() == ["Grizzly Bears"]
    assert scenario.player("alice").mana_pool.total == 0


def test_a_pinned_source_naming_only_its_own_mana_still_gets_the_trigger():
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"], alice_hand=["Grizzly Bears"])
    elves = scenario.creature("Llanowar Elves")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.cast(bears, "alice", mana_sources=[(elves, [Color.GREEN])])

    assert scenario.stack_names() == ["Grizzly Bears"]


def test_affordability_counts_the_triggered_mana():
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"], alice_hand=["Grizzly Bears"])
    game = scenario.game
    elves = scenario.creature("Llanowar Elves")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    assert could_pay_mana_cost(ManaCost.parse("{1}{G}"), game.battlefield, game=game, payer="alice")
    assert not could_pay_mana_cost(
        ManaCost.parse("{2}{G}"), game.battlefield, game=game, payer="alice"
    )
    (cast,) = [
        action
        for action in legal_actions(game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == bears.id
    ]
    assert cast.affordable is Affordability.YES
    assert [entry.card_id for entry in cast.pays_with] == [elves.id]


def test_fertile_ground_any_color_is_chosen_by_the_auto_tap_to_fit_the_cost():
    scenario = _board(
        ["Forest", "Forest", "Forest"], alice_hand=["Fertile Ground", "Sleight of Hand"]
    )
    first, second, enchanted = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Fertile Ground", first, second, targets=[enchanted])
    scenario.player("alice").mana_pool.empty()
    sleight = scenario.find("Sleight of Hand", Zone.HAND, "alice")

    scenario.game.cast(sleight, "alice", mana_sources=[enchanted])

    assert scenario.stack_names() == ["Sleight of Hand"]
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}, (
        "the Forest's own {G} was not needed and floats (CR 106.4a)"
    )


def test_a_refused_payment_takes_back_the_triggered_mana_with_the_tap():
    """CR 733.1: a payment that cannot finish rewinds, and the mana the
    trigger added is part of what the rewind throws away."""
    scenario = _board(["Leyline of Abundance", "Llanowar Elves"], alice_hand=["Hill Giant"])
    elves = scenario.creature("Llanowar Elves")
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")

    try:
        scenario.game.cast(giant, "alice", mana_sources=[(elves, [Color.GREEN])])
    except ValueError:
        pass
    else:
        raise AssertionError("{3}{R} cannot be paid with two green")

    assert giant.zone is Zone.HAND
    assert elves.untapped
    assert scenario.player("alice").mana_pool.total == 0
    assert scenario.stack_names() == []

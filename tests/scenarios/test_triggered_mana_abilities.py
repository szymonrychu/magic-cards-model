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


# -- a count, computed as the mana is added (CR 608.2h) ----------------------


def _guided_forest(elves: list[str]):
    """Elvish Guidance ("Whenever enchanted land is tapped for mana, its
    controller adds an additional {G} for each Elf on the battlefield.") on a
    Forest, with `elves` on alice's side and one Elf on bob's."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Elvish Guidance"],
            battlefield=["Forest", "Forest", "Forest", "Forest", *elves],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    *payers, enchanted = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Elvish Guidance", *payers[:3], targets=[enchanted])
    scenario.player("alice").mana_pool.empty()
    return scenario, enchanted


def test_elvish_guidance_adds_one_green_for_each_elf_on_the_battlefield_at_once():
    """Every Elf on the battlefield counts, bob's included."""
    scenario, enchanted = _guided_forest(["Wood Elves", "Bloodbraid Elf"])

    scenario.activate(enchanted)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 4}


def test_elvish_guidance_counts_at_resolution_so_no_elf_adds_nothing_extra():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Elvish Guidance"], battlefield=["Forest", "Forest", "Forest", "Forest"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    *payers, enchanted = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Elvish Guidance", *payers[:3], targets=[enchanted])
    scenario.player("alice").mana_pool.empty()

    scenario.activate(enchanted)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}


def test_the_payment_search_counts_elvish_guidances_mana():
    """Deterministic when the tap is planned: the Elves are on the board -
    alice's Wood Elves and bob's Llanowar Elves, so one Forest makes three."""
    scenario, enchanted = _guided_forest(["Wood Elves"])
    game = scenario.game
    game.player("alice").hand.clear()

    sources = [enchanted]
    assert could_pay_mana_cost(ManaCost.parse("{2}{G}"), sources, game=game, payer="alice")
    assert not could_pay_mana_cost(ManaCost.parse("{3}{G}"), sources, game=game, payer="alice")


def test_a_cast_paid_by_the_enchanted_land_alone_uses_the_counted_mana():
    """Grizzly Bears' {1}{G} from one Forest: its {G} and one Elf's {G}."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Elvish Guidance", "Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Wood Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    *payers, enchanted = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Elvish Guidance", *payers[:3], targets=[enchanted])
    scenario.player("alice").mana_pool.empty()
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.game.cast(bears, "alice", mana_sources=[enchanted])

    assert scenario.stack_names() == ["Grizzly Bears"]
    assert scenario.player("alice").mana_pool.total == 0
    assert enchanted.tapped, "the enchanted Forest alone paid"
    assert scenario.creature("Wood Elves").untapped


# -- "may add", asked in place (CR 608.2d) -----------------------------------


def _snowfall(land: str):
    scenario = _board(["Snowfall", land])
    (island,) = scenario.untapped_sources(land)
    return scenario, island


def test_snowfall_asks_its_may_at_once_and_an_unscripted_seat_takes_the_mana():
    scenario, island = _snowfall("Island")

    scenario.activate(island)

    assert scenario.stack_names() == []
    asked = [q for q in scenario.questions_asked() if q.source == "Snowfall"]
    assert [q.kind for q in asked] == [DecisionKind.MAY]
    pool = scenario.player("alice").mana_pool
    assert pool.floating == {Color.BLUE: 2}
    assert len(pool.restricted) == 1, "CR 106.6: Snowfall's own {U} carries its restriction"


def test_declining_snowfalls_may_adds_nothing_extra():
    scenario, island = _snowfall("Island")
    scenario.will_take_the_may(False, source="Snowfall")

    scenario.activate(island)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}
    assert scenario.player("alice").mana_pool.restricted == []


def test_a_snow_island_gets_snowfalls_two_blue_instead():
    scenario, island = _snowfall("Snow-Covered Island")

    scenario.activate(island)

    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 3}


def test_snowfalls_restricted_mana_is_not_counted_toward_a_spell():
    """CR 106.6: "Spend this mana only to pay cumulative upkeep costs" - no
    spell can spend it, so the payment search does not count it."""
    scenario, island = _snowfall("Island")
    game = scenario.game

    assert could_pay_mana_cost(ManaCost.parse("{U}"), game.battlefield, game=game, payer="alice")
    assert not could_pay_mana_cost(
        ManaCost.parse("{1}{U}"), game.battlefield, game=game, payer="alice"
    )

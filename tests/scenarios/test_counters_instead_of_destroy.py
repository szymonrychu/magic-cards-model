"""Scenario: "If another creature you control with a +1/+1 counter on it would
be destroyed, instead remove all +1/+1 counters from it and all damage already
dealt to it is healed." (Dr. McCoy, Surly Surgeon).

CR 614.1a: "instead" makes it a replacement effect, so the destruction (CR
701.8a, a destroy spell or CR 704.5g's lethal damage) never happens; the
creature stays with no +1/+1 counters and no marked damage (CR 120.6). No
other legal printing carries this replacement (Scryfall, in the writing
session), so the corner cases below vary the creature instead.

CR rules cited here were looked up with `mise run rules:find` in the writing
session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Dr. McCoy, Surly Surgeon", "Grizzly Bears", "Savannah Lions"],
        )
        .player(
            "bob", hand=["Go for the Throat", "Lightning Bolt"], battlefield=["Swamp", "Mountain"]
        )
    )


def bob_turn(scenario):
    while scenario.turn.active_player != "bob":
        scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


def test_a_destroy_spell_takes_the_counters_instead():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2, putter="alice")
    bob_turn(scenario)
    scenario.cast_and_resolve(
        "Go for the Throat",
        *scenario.untapped_sources("Swamp", "Swamp", username="bob"),
        targets=[bears],
    )
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_lethal_damage_is_healed_instead_of_destroying():
    """Lightning Bolt marks 3 on a 3/3 (a 2/2 with a counter); the state-based
    destruction is replaced: the counter goes, the damage is healed."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    bob_turn(scenario)
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain", username="bob"), targets=[bears]
    )
    scenario.state_based_actions()
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_a_creature_without_a_counter_is_destroyed():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creature("Savannah Lions", "alice")
    bob_turn(scenario)
    scenario.cast_and_resolve(
        "Go for the Throat",
        *scenario.untapped_sources("Swamp", "Swamp", username="bob"),
        targets=[lions],
    )
    assert lions.zone is Zone.GRAVEYARD


def test_dr_mccoy_does_not_protect_himself():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mccoy = scenario.creature("Dr. McCoy, Surly Surgeon", "alice")
    scenario.game.add_counters(mccoy, Counter.PLUS_ONE, 1, putter="alice")
    bob_turn(scenario)
    scenario.cast_and_resolve(
        "Go for the Throat",
        *scenario.untapped_sources("Swamp", "Swamp", username="bob"),
        targets=[mccoy],
    )
    assert mccoy.zone is Zone.GRAVEYARD


def test_an_opponents_creature_is_not_protected():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Go for the Throat"],
            battlefield=["Dr. McCoy, Surly Surgeon", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="bob")
    scenario.cast_and_resolve(
        "Go for the Throat", *scenario.untapped_sources("Swamp"), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD


def test_dr_mccoy_surly_surgeon_counters_a_creature_then_saves_it():
    """His enters trigger puts a +1/+1 counter on another target creature you
    control; that counter is then what lets the replacement save it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dr. McCoy, Surly Surgeon"],
            battlefield=["Plains"] * 4 + ["Grizzly Bears"],
            library=["Plains"] * 6,
        )
        .player(
            "bob",
            hand=["Go for the Throat"],
            battlefield=["Swamp", "Swamp"],
            library=["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Dr. McCoy, Surly Surgeon", [bears])
    scenario.cast_and_resolve(
        "Dr. McCoy, Surly Surgeon", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    bob_turn(scenario)
    scenario.cast_and_resolve(
        "Go for the Throat",
        *scenario.untapped_sources("Swamp", "Swamp", username="bob"),
        targets=[bears],
    )
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counter_count(Counter.PLUS_ONE) == 0

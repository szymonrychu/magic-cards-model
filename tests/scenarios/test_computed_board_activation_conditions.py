"""Scenario: `Game._activation_condition_holds`'s three shapes - Mox Opal's
metalcraft ("you control three or more artifacts"), Fanatic of Rhonas's
ferocious ("you control a creature with power 4 or greater"), and Diamond
City's "two or more creatures entered the battlefield under your control
this turn" - all read a permanent's *computed* characteristics (CR 613.5),
not its printed ones.

Every CR number below was looked up with `mise run rules:find` this session.

- **Metalcraft** counts card types (`Type.ARTIFACT in state.types`, printed).
  Liquimetal Coating's own `{T}: Target permanent becomes an artifact in
  addition to its other types until end of turn.` makes a plain creature an
  artifact computed-only, so a fix that keeps reading the printed line never
  sees the third artifact and metalcraft never turns on.
- **Ferocious** compares `state.power`, which counts CR 122.1a's counters but
  not a sublayer 7c pump (CR 613.4c) - Giant Growth's "+3/+3 until end of
  turn" is invisible to it. `board.of(state).power` sees the pump.
- **Diamond City**'s "entered this turn" clause counts `state.is_creature`
  (printed). A land earthbent (CR 701.66a) the same turn it was played is a
  creature only on the computed board, so it should count as a second
  creature that entered this turn alongside Badgermole Cub itself, and a
  printed read undercounts by one.

The inverse of each - metalcraft with only two real artifacts, ferocious
with no pump, Diamond City with only one creature entering - is covered
too, so a fix that over-reads (treats everything as the counted type) fails
those the same way an under-reading fix fails the positive cases.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_metalcraft_turns_on_once_liquimetal_coating_makes_a_third_artifact():
    """Mox Opal itself and Liquimetal Coating (a real Artifact) are two
    printed artifacts; Liquimetal Coating's own ability makes Grizzly Bears
    an artifact too, computed only, reaching CR 602.5b's "three or more".
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mox Opal", "Liquimetal Coating", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD)
    coating = scenario.find("Liquimetal Coating", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(mox, 0) is not None, "only two real artifacts so far"

    scenario.activate(coating, index=0, targets=[bears])
    scenario.pass_until_resolved()

    from magic_cards_model.models.card import Type

    assert Type.ARTIFACT in scenario.game.characteristics_of(bears).types
    assert scenario.why_cannot_activate(mox, 0) is None, "three artifacts now: metalcraft is on"


def test_metalcraft_stays_off_with_only_two_real_artifacts():
    """The inverse: with no Liquimetal Coating activation, Grizzly Bears
    never becomes an artifact, and Mox Opal's metalcraft never turns on.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mox Opal", "Liquimetal Coating", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mox = scenario.find("Mox Opal", Zone.BATTLEFIELD)

    reason = scenario.why_cannot_activate(mox, 0)
    assert reason is not None
    assert "602.5b" in reason


def test_ferocious_turns_on_for_an_earthbent_land_pumped_to_power_4():
    """`CardState.power`/`.toughness` are already board-aware once
    `bind_to_game` has run (see their own docstring) - a plain creature
    pumped by Giant Growth already reads the right power under the old
    code. `is_creature`, built off the *printed* `.types`, is not: an
    earthbent land (CR 701.66a) reads False there right up until CR 613.5's
    computed board is consulted. The land is 0/0 plus earthbend's own one
    +1/+1 counter (CR 613.4c sublayer 7c comes after the counter's own
    sublayer 7c) and Giant Growth's "+3/+3 until end of turn" - 1 + 3 = 4,
    exactly Fanatic of Rhonas's ferocious threshold (CR 602.5b).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Giant Growth"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Fanatic of Rhonas"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.find("Fanatic of Rhonas", Zone.BATTLEFIELD)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    pay_sources, target_forest, pump_source = sources[:2], sources[2], sources[3]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(target_forest).is_creature
    assert scenario.game.characteristics_of(target_forest).power == 1

    assert scenario.why_cannot_activate(fanatic, 1) is not None, "power 1 does not meet ferocious"

    scenario.cast_and_resolve("Giant Growth", pump_source, targets=[target_forest])

    assert scenario.game.characteristics_of(target_forest).power == 4
    assert scenario.why_cannot_activate(fanatic, 1) is None, "power 4 now: ferocious is on"


def test_ferocious_stays_off_without_a_pump():
    """The inverse: Grizzly Bears alone, unpumped, never satisfies ferocious."""
    scenario = (
        Scenario().player("alice", battlefield=["Fanatic of Rhonas", "Grizzly Bears"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.find("Fanatic of Rhonas", Zone.BATTLEFIELD)

    reason = scenario.why_cannot_activate(fanatic, 1)
    assert reason is not None
    assert "power 4 or greater" in reason.lower() or "602.5b" in reason


def test_diamond_city_counts_an_earthbent_land_among_creatures_that_entered():
    """Badgermole Cub itself entered this turn (one creature, printed and
    computed alike); the Forest it earthbends was also played this turn and
    is a creature only on the computed board. Diamond City's own ability
    needs "two or more creatures entered the battlefield under your control
    this turn" (CR 602.5b) to activate - only true if the animated land
    counts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Forest"],
            battlefield=["Forest", "Forest", "Diamond City"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = scenario.find("Diamond City", Zone.BATTLEFIELD)
    pay_sources = scenario.untapped_sources("Forest", "Forest")
    new_forest = scenario.play_land("Forest")
    scenario.choose_trigger_targets("Badgermole Cub", [new_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(new_forest).is_creature
    assert new_forest.turn_entered == scenario.game.turn.turn_number

    move_shield = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(diamond_city))
        if "shield counter" in (ability.text or "").lower() and "target creature" in ability.text
    )

    reason = scenario.why_cannot_activate(diamond_city, move_shield)
    assert reason is None, "two creatures entered this turn: Badgermole Cub and the animated Forest"


def test_diamond_city_refuses_with_only_one_creature_entering():
    """The inverse: with no earthbend, only Badgermole Cub itself entered
    this turn as a creature, so Diamond City's ability stays refused.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub"],
            battlefield=["Forest", "Forest", "Diamond City"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    diamond_city = scenario.find("Diamond City", Zone.BATTLEFIELD)
    old_forest = scenario.find("Forest", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Badgermole Cub", [old_forest])
    scenario.put_onto_battlefield("Badgermole Cub")
    scenario.pass_until_resolved()

    assert old_forest.turn_entered != scenario.game.turn.turn_number, (
        "the earthbent land is a creature, but it did not enter this turn"
    )

    move_shield = next(
        index
        for index, ability in enumerate(scenario.game.activated_abilities(diamond_city))
        if "shield counter" in (ability.text or "").lower() and "target creature" in ability.text
    )

    reason = scenario.why_cannot_activate(diamond_city, move_shield)
    assert reason is not None
    assert "602.5b" in reason

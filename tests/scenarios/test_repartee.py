"""Scenario: Repartee (CR 207.2c ability word - "Repartee — Whenever you
cast an instant or sorcery spell that targets a creature, [effect]", no
rules meaning of its own beyond tying together cards that share the
trigger). Stirring Hopesinger's own Repartee clause is already covered by
`test_cast_spell_targets_condition.py`.

This file is the off-pool proof the requirement names: **Rehearsed Debater**
- "Repartee — Whenever you cast an instant or sorcery spell that targets a
creature, this creature gets +1/+1 until end of turn." Lightning Bolt is the
control on both sides of the same card, cast at two different things: "any
target" (CR 601.2c) genuinely includes both a creature and a player, so
whether Repartee fires turns on what *this* cast actually targeted, not on
what the spell's text could target in general.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Rehearsed Debater", "Mountain"],
            hand=["Lightning Bolt"],
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
    )


def test_off_pool_rehearsed_debater_pumps_when_the_spell_targets_a_creature():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    debater = scenario.creature("Rehearsed Debater", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    scenario.pass_until_resolved()  # the Repartee trigger

    chars = scenario.game.characteristics_of(debater)
    assert chars.power == 4  # printed 3, +1/+1
    assert chars.toughness == 4


def test_off_pool_rehearsed_debater_does_not_pump_when_the_spell_targets_a_player():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    debater = scenario.creature("Rehearsed Debater", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    chars = scenario.game.characteristics_of(debater)
    assert chars.power == 3
    assert chars.toughness == 3

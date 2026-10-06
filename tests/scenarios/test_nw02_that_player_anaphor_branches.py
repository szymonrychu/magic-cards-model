"""A spell's "that player" is the player its own "target player" named
(CR 608.2c: later text on the card may modify the meaning of earlier text;
CR 115.1a / CR 601.2c: the target was chosen as the spell was cast).

Hidetsugu's Second Rite ({3}{R}): "If target player has exactly 10 life,
Hidetsugu's Second Rite deals 10 damage to that player." - the condition is
checked as the spell resolves (CR 608.2c), against the chosen player.

Aggressive Sabotage ({2}{B}, Kicker {R}): "Target player discards two cards.
If this spell was kicked, it deals 3 damage to that player." - CR 702.33d's
kicked flag gates the second instruction, which acts on the same player the
first one did.

Proof printing on the same binding: Haunting Hymn ("Target player discards two
cards. If you cast this spell during your main phase, that player discards
four cards instead.") - the "instead" branch acts on the player the first
sentence named.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario, mana_from

_HAND = ["Grizzly Bears"] * 5


def _rite(bob_life: int) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Hidetsugu's Second Rite"], battlefield=["Mountain"] * 4)
        .player("bob", life=bob_life)
    )


def _cast_rite(bob_life: int):
    scenario = _rite(bob_life).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Hidetsugu's Second Rite",
        *scenario.untapped_sources(*["Mountain"] * 4),
        targets=["bob"],
    )
    return scenario


def test_exactly_ten_life_takes_ten_damage():
    scenario = _cast_rite(10)
    assert scenario.player("bob").life == 0


def test_nine_life_is_not_exactly_ten():
    scenario = _cast_rite(9)
    assert scenario.player("bob").life == 9


def test_eleven_life_is_not_exactly_ten():
    scenario = _cast_rite(11)
    assert scenario.player("bob").life == 11


def test_the_condition_is_the_targets_not_the_casters():
    """Alice sits on exactly 10 life; Bob on 20 - nothing happens to either."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", life=10, hand=["Hidetsugu's Second Rite"], battlefield=["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Hidetsugu's Second Rite",
        *scenario.untapped_sources(*["Mountain"] * 4),
        targets=["bob"],
    )
    assert scenario.player("alice").life == 10
    assert scenario.player("bob").life == 20


def test_the_caster_can_target_themselves_at_exactly_ten():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", life=10, hand=["Hidetsugu's Second Rite"], battlefield=["Mountain"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Hidetsugu's Second Rite",
        *scenario.untapped_sources(*["Mountain"] * 4),
        targets=["alice"],
    )
    assert scenario.player("alice").life == 0
    assert scenario.player("bob").life == 20


def _sabotage(*, kicked: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Aggressive Sabotage"], battlefield=["Swamp"] * 3 + ["Mountain"])
        .player("bob", hand=_HAND)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Aggressive Sabotage")
    if kicked:
        casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    lands = ["Swamp"] * 3 + (["Mountain"] if kicked else [])
    for source in scenario.untapped_sources(*lands):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def test_unkicked_sabotage_only_discards():
    scenario = _sabotage(kicked=False)
    assert len(scenario.player("bob").hand) == 3
    assert scenario.player("bob").life == 20


def test_kicked_sabotage_discards_and_deals_three_to_that_player():
    scenario = _sabotage(kicked=True)
    assert len(scenario.player("bob").hand) == 3
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def _haunting_hymn(*, main_phase: bool):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Haunting Hymn"], battlefield=["Swamp"] * 6)
        .player("bob", hand=_HAND + ["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN if main_phase else Step.BEGINNING_OF_COMBAT)
    return scenario


def test_haunting_hymn_in_the_main_phase_discards_four_to_that_player():
    scenario = _haunting_hymn(main_phase=True)
    scenario.cast_and_resolve(
        "Haunting Hymn", *scenario.untapped_sources(*["Swamp"] * 6), targets=["bob"]
    )
    assert len(scenario.player("bob").hand) == 4

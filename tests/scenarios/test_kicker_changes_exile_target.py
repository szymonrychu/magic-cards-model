"""CR 702.33a, 702.33d, 601.2c: kicker that changes what the spell targets.

Tear Asunder - "Kicker {1}{B}. Exile target artifact or enchantment. If this
spell was kicked, exile target nonland permanent instead."

The kicker is announced before targets (CR 601.2b precedes CR 601.2c), and a
spell "may require alternative targets only if an alternative or additional
cost was chosen for it" (CR 601.2c). So an unkicked cast may only aim at an
artifact or enchantment, a kicked cast at any nonland permanent, and the
choice of which restriction applies is fixed at announcement.

CR numbers used, read with `mise run rules:find` in this session: CR 702.33a
(kicker is an additional cost), CR 702.33d ("kicked" once the intention to pay
is declared), CR 601.2c (alternative targets only through an additional cost),
CR 608.2b (a target that became illegal is not affected).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

TEAR = "Tear Asunder"
LANDS = ["Forest", "Swamp", "Swamp", "Swamp"]


def _board(
    *, bob_battlefield: list[str], alice_extra: list[str] | None = None, lands: int = 4
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[TEAR], battlefield=[*LANDS[:lands], *(alice_extra or [])])
        .player("bob", battlefield=bob_battlefield)
    )


def _cast(scenario, target, *, kicked: bool):
    casting = scenario.cast(TEAR)
    if kicked:
        casting.pay_kicker()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    needed = 4 if kicked else 2
    for source in scenario.untapped_sources(*LANDS[:needed]):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return casting


def _resolve(scenario, casting):
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_unkicked_exiles_a_target_artifact():
    scenario = _board(bob_battlefield=["Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _resolve(scenario, _cast(scenario, ring, kicked=False))

    assert ring.zone is Zone.EXILE


def test_unkicked_exiles_a_target_enchantment():
    scenario = _board(bob_battlefield=["Glorious Anthem"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    enchantment = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "bob")

    _resolve(scenario, _cast(scenario, enchantment, kicked=False))

    assert enchantment.zone is Zone.EXILE


def test_unkicked_cannot_target_a_nonartifact_nonenchantment_creature():
    """CR 601.2c: without the additional cost the alternative target is not
    available, so a plain creature is refused."""
    scenario = _board(bob_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast(TEAR)

    with pytest.raises(ValueError):
        casting.choose_targets([bears])

    assert bears.zone is Zone.BATTLEFIELD


def test_unkicked_cannot_target_a_land():
    scenario = _board(bob_battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError):
        scenario.cast(TEAR).choose_targets([mountain])


def test_kicked_exiles_a_nonland_permanent_that_is_neither_artifact_nor_enchantment():
    """CR 702.33d + CR 601.2c: kicked, the alternative target applies."""
    scenario = _board(bob_battlefield=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    casting = _cast(scenario, bears, kicked=True)
    assert casting.kicked == 1
    _resolve(scenario, casting)

    assert bears.zone is Zone.EXILE


def test_kicked_still_exiles_an_artifact_or_enchantment():
    """Every artifact and enchantment is a nonland permanent too."""
    scenario = _board(bob_battlefield=["Sol Ring", "Glorious Anthem"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _resolve(scenario, _cast(scenario, ring, kicked=True))

    assert ring.zone is Zone.EXILE
    assert scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


def test_kicked_cannot_target_a_land():
    scenario = _board(bob_battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast(TEAR)
    casting.pay_kicker()

    with pytest.raises(ValueError):
        casting.choose_targets([mountain])


def test_kicked_target_may_be_my_own_permanent():
    """Nothing restricts the controller: "nonland permanent" is any."""
    scenario = _board(bob_battlefield=[], alice_extra=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    _resolve(scenario, _cast(scenario, mine, kicked=True))

    assert mine.zone is Zone.EXILE


def test_unkicked_cast_costs_only_the_mana_cost_and_is_recorded_unkicked():
    scenario = _board(bob_battlefield=["Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    casting = _cast(scenario, ring, kicked=False)

    assert casting.kicked == 0
    assert len(scenario.untapped_sources("Swamp", "Swamp")) == 2


def test_kicked_cast_needs_the_kicker_mana():
    """CR 702.33a: the {1}{B} is paid on top of {1}{G}; two lands do not do."""
    scenario = _board(bob_battlefield=["Grizzly Bears"], lands=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast(TEAR)
    casting.pay_kicker()
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Forest", "Swamp"):
        payment.tap_for_mana(source, mana_from(source))

    with pytest.raises(ValueError):
        payment.pay()


def test_target_gone_before_resolution_fizzles_and_exiles_nothing():
    """CR 608.2b: the sole target left the battlefield, so the spell does not
    resolve; the spell card goes to the graveyard."""
    scenario = _board(bob_battlefield=["Grizzly Bears", "Sol Ring"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = _cast(scenario, bears, kicked=True)
    scenario.put_on_stack(casting)
    scenario.game.return_to_hand(bears)
    scenario.resolve_top()

    assert scenario.find("Grizzly Bears", Zone.HAND, "bob")
    assert scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob").zone is Zone.BATTLEFIELD


# -- the same template on a second printing, worded differently ---------------
#
# Bloodchief's Thirst - "Kicker {2}{B}. Destroy target creature or planeswalker
# with mana value 2 or less. If this spell was kicked, instead destroy target
# creature or planeswalker." The "instead" leads the kicked sentence and the
# verb is "destroy", so this exercises the reader, not Tear Asunder's sentence.

THIRST = "Bloodchief's Thirst"


def _thirst_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[THIRST], battlefield=["Swamp"] * 4)
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel"])
    )


def _thirst_cast(scenario, target, *, kicked: bool):
    casting = scenario.cast(THIRST)
    if kicked:
        casting.pay_kicker()
    casting.choose_targets([target])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Swamp"] * (4 if kicked else 1)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return casting


def test_second_printing_unkicked_is_limited_to_mana_value_2_or_less():
    scenario = _thirst_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError):
        scenario.cast(THIRST).choose_targets([angel])

    _resolve(scenario, _thirst_cast(scenario, bears, kicked=False))
    assert bears.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.BATTLEFIELD


def test_second_printing_kicked_lifts_the_mana_value_limit():
    scenario = _thirst_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.find("Serra Angel", Zone.BATTLEFIELD, "bob")

    casting = _thirst_cast(scenario, angel, kicked=True)
    assert casting.kicked == 1
    _resolve(scenario, casting)

    assert angel.zone is Zone.GRAVEYARD

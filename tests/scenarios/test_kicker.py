"""Kicker: an optional additional cost announced while casting (CR 702.33).

CR 702.33a: "Kicker is a static ability that functions while the spell with
kicker is on the stack. 'Kicker [cost]' means "You may pay an additional [cost]
as you cast this spell.""

CR 118.8a makes it an *additional* cost, which is the difference from evoke: the
printed mana cost is still paid on top of it, not replaced by it.

CR 702.33d: "If a spell's controller declares the intention to pay any of that
spell's kicker costs, that spell has been 'kicked.'" That flag is the whole
reason kicker needs recording at all - CR 702.33e and CR 607.2i link it to the
card's other ability, "If this spell was kicked, it deals 4 damage instead."

CR 702.33c's multikicker may be paid any number of times; plain kicker may not,
and refusing a second payment is the corner case here.

What a kicked spell *does* differently is read at resolution off
`Game.cast_record(spell).kicked` (`_parse_damage_target_kicked_instead_clause`
in `machines/effects.py`), covered below by
`test_an_unkicked_burst_lightning_deals_its_base_damage` and
`test_a_kicked_burst_lightning_deals_the_kicked_amount_instead` - Burst
Lightning used to have no `EFFECTS` row at all and resolved doing nothing,
kicked or not, until its own two-sentence shape ("<Name> deals 2 damage to any
target. If this spell was kicked, it deals 4 damage instead.") got a reader.
Burst Lightning's own printed "Kicker {4} (...)" *line* used to poison the
clause split of the sentence after it too (the same bug flashback's own line
caused; `_strip_keyword_ability_lines` fixes both) - both are exercised end to end here.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def board(lands: int = 5) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Burst Lightning"], battlefield=["Mountain"] * lands)
        .player("bob")
    )


def cast_it(scenario, *, kicked: bool):
    casting = scenario.cast("Burst Lightning")
    if kicked:
        casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    needed = 5 if kicked else 1
    for source in scenario.untapped_sources(*["Mountain"] * needed):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    return casting


def test_an_unkicked_spell_costs_only_its_mana_cost():
    """The cost is optional: not paying it is the default."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    assert str(casting.total_cost.mana) == "{R}"
    assert casting.kicked == 0


def test_paying_the_kicker_adds_it_to_the_total_cost():
    """CR 118.8a: additional, so {R} becomes {4}{R} rather than {4}."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    assert str(casting.total_cost.mana) == "{4}{R}"


def test_a_kicked_spell_records_that_it_was_kicked():
    """CR 702.33d: the flag CR 702.33e's linked ability reads."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = cast_it(scenario, kicked=True)
    spell = scenario.put_on_stack(casting)

    assert casting.kicked == 1
    assert spell.zone is Zone.STACK
    assert all(source.tapped for source in scenario.game.battlefield)


def test_an_unkicked_spell_leaves_the_extra_lands_untapped():
    """The other side of the same board: one Mountain pays for it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_it(scenario, kicked=False)
    tapped = [source for source in scenario.game.battlefield if source.tapped]
    assert len(tapped) == 1


def test_the_kicker_cannot_be_paid_without_the_mana():
    """CR 118.3: the total cost is one cost, and it is paid in full or not at all."""
    scenario = board(lands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    for source in scenario.untapped_sources("Mountain", "Mountain", "Mountain"):
        payment.tap_for_mana(source, mana_from(source))

    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_plain_kicker_cannot_be_paid_twice():
    """CR 702.33c: paying more than once is multikicker's rule, not kicker's."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    with pytest.raises(ValueError, match="plain kicker"):
        casting.pay_kicker()


def test_a_card_without_kicker_refuses_the_announcement():
    """Kicker is printed or it is not: there is no default kicker cost."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt")
    with pytest.raises(ValueError, match="no kicker ability"):
        casting.pay_kicker()


def test_rewinding_a_kicked_casting_returns_the_mana_sources():
    """CR 733.1: the whole announcement is reversed, kicker included."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = cast_it(scenario, kicked=True)
    casting.cancel()

    assert all(source.untapped for source in scenario.game.battlefield)
    assert scenario.find("Burst Lightning", Zone.HAND, "alice").zone is Zone.HAND


def test_an_unkicked_burst_lightning_deals_its_base_damage():
    """ "Burst Lightning deals 2 damage to any target." (CR 119.3), unkicked."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    casting = cast_it(scenario, kicked=False)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob.life == 18


def test_a_kicked_burst_lightning_deals_the_kicked_amount_instead():
    """ "If this spell was kicked, it deals 4 damage instead." - not 2 plus 4."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    casting = cast_it(scenario, kicked=True)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob.life == 16

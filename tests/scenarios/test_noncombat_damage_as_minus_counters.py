"""Noncombat damage replaced by -1/-1 counters (CR 614.1a, CR 122.1a).

Soul-Scar Mage: "If a source you control would deal noncombat damage to a
creature an opponent controls, put that many -1/-1 counters on that creature
instead." CR 614.1a: "Effects that use the word 'instead' are replacement
effects." CR 122.1a: "-X/-Y counters subtract from power and toughness."

The damage is never dealt - it is replaced, not prevented (the printing's own
ruling: "Soul-Scar Mage's effect isn't a prevention effect"), so no damage is
marked. The event side is the same `_SOURCE_YOU_CONTROL_DAMAGE_EVENT_RE`
Torbran and Fiery Emancipation already share; the replacement side reads any
"put that many <kind> counters on that creature instead".

No second legal printing carries this replacement (Scryfall search
`o:"-1/-1 counters" o:"instead" o:"would deal"` returns Soul-Scar Mage alone),
recorded in MEMORY.md; the reader is keyed on the template, never the name.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*, alice_hand=("Lightning Bolt",), bob_hand=()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Soul-Scar Mage", "Mountain", "Mountain", "Colossal Dreadmaw"],
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Colossal Dreadmaw", "Mountain", "Grizzly Bears"],
            library=["Mountain"] * 5,
        )
    )


def test_burn_on_an_opponents_creature_becomes_minus_counters():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain")[:1], targets=[dreadmaw]
    )
    scenario.pass_until_resolved()  # prowess, then the Bolt

    assert dreadmaw.counter_count(Counter.MINUS_ONE) == 3
    assert dreadmaw.damage == 0


def test_the_counters_kill_a_small_creature_through_state_based_actions():
    """A 2/2 with three -1/-1 counters is a -1/-1: CR 704.5f puts it in the
    graveyard for zero toughness."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain")[:1], targets=[bears]
    )
    scenario.pass_until_resolved()  # prowess, then the Bolt
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD


def test_damage_to_a_player_is_untouched():
    """"to a creature" - the player takes the 3 damage."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain")[:1],
        targets=[scenario.player("bob")],
    )
    scenario.pass_until_resolved()  # prowess, then the Bolt

    assert scenario.player("bob").life == 17


def test_damage_to_your_own_creature_is_untouched():
    """"a creature an opponent controls" - alice's own Dreadmaw takes damage."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Colossal Dreadmaw", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain")[:1], targets=[mine]
    )
    scenario.pass_until_resolved()  # prowess, then the Bolt

    assert mine.damage == 3
    assert mine.counter_count(Counter.MINUS_ONE) == 0


def test_an_opponents_source_is_untouched():
    """"a source you control" - noncombat damage from bob's source to alice's
    creature is marked as damage."""
    scenario = _board(alice_hand=()).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Colossal Dreadmaw", "alice")
    bobs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.deal_damage(mine, 3, source=bobs)

    assert mine.damage == 3
    assert mine.counter_count(Counter.MINUS_ONE) == 0


def test_combat_damage_is_untouched():
    """"noncombat damage" - Soul-Scar Mage's own combat damage is marked."""
    scenario = _board(alice_hand=()).build()
    mage = scenario.creature("Soul-Scar Mage", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mage)
    scenario.pass_until_resolved()
    scenario.turn.advance_to(Step.DECLARE_BLOCKERS)
    scenario.game.sync_priority_with_step()
    scenario.block(mage, bears)
    scenario.combat_damage()

    assert bears.damage == 1
    assert bears.counter_count(Counter.MINUS_ONE) == 0


def test_the_line_is_credited_as_handled():
    from magic_cards_model.support import card_support
    from tests.cards import card

    support = card_support(card("Soul-Scar Mage"))
    assert "static_unaudited" not in str(support)


@pytest.mark.parametrize("amount", [1, 3])
def test_the_counter_count_is_that_many(amount: int):
    """"that many" - the amount of damage that would have been dealt."""
    scenario = _board(alice_hand=()).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    mage = scenario.creature("Soul-Scar Mage", "alice")

    scenario.game.deal_damage(dreadmaw, amount, source=mage)

    assert dreadmaw.counter_count(Counter.MINUS_ONE) == amount
    assert dreadmaw.damage == 0

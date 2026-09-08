"""Damage dealt to a planeswalker removes loyalty counters (CR 120.3c, CR 306.8).

Every rule cited here was read in full from `.rules/MagicCompRules.txt` (the
Comprehensive Rules effective August 7, 2026) with `mise run rules:find` in the
session that wrote this file.

- **CR 120.3c** - "Damage dealt to a planeswalker causes that many loyalty
  counters to be removed from that planeswalker."
- **CR 306.8** - "Damage dealt to a planeswalker results in that many loyalty
  counters being removed from it." The same rule from the planeswalker's side.
- **CR 120.3e** - "Damage dealt to a creature by a source with neither wither
  nor infect causes that much damage to be marked on that creature." Marking
  is the *creature* result. A planeswalker is not a creature, so nothing is
  marked on one, and there is no marked-damage bookkeeping for CR 514.2's
  cleanup to remove.
- **CR 306.9** - "If a planeswalker's loyalty is 0, it's put into its owner's
  graveyard. (This is a state-based action. See rule 704.)"
- **CR 704.5i** - "If a planeswalker has loyalty 0, it's put into its owner's
  graveyard."
- **CR 306.5b / 306.5c** - a planeswalker enters with its printed loyalty in
  counters, and its loyalty on the battlefield is the number of loyalty
  counters on it.
- **CR 702.19b** - trample: "Once all those blocking creatures are assigned
  lethal damage, any excess damage is assigned as its controller chooses among
  those blocking creatures and the player, planeswalker, or battle the
  creature is attacking."
- **CR 510.2** - all combat damage is dealt simultaneously, so two attackers
  hitting one planeswalker are one nine-point event, not two.

**The division of labour is the point of this file.** Removing the loyalty is
part of the *damage event* (CR 120.3c), immediate and no state-based action.
Only the graveyard move is a state-based action (CR 306.9, CR 704.5i), and
that half already worked - `tests/scenarios/test_loyalty_abilities.py` and
`test_counters.py` cover it from the counters' side. What was missing was the
first half: `Game.deal_damage` marked damage on any permanent that was not a
player, so a planeswalker collected `damage` it had no rule to read and kept
every loyalty counter it started with.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# The production game this file was written from: an Eldrazi board attacking
# an Ugin, Eye of the Storms that had already used its `+2` once.
UGIN = "Ugin, Eye of the Storms"


def _eldrazi_vs_ugin(*, attackers: list[str]) -> Scenario:
    """Alice's attackers against bob's freshly landed Ugin (7 printed loyalty)."""
    return (
        Scenario()
        .player("alice", library=["Mountain"] * 10, battlefield=attackers)
        .player("bob", library=["Forest"] * 10, battlefield=[UGIN])
        .build()
    )


def _bobs_turn_then_alices(scenario) -> None:
    """Hand the turn to bob, then back to alice's declare attackers step."""
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- the reported game (CR 120.3c, CR 510.2, CR 704.5i) --------------------


def test_nine_combat_damage_from_two_attackers_kills_a_nine_loyalty_ugin():
    """The production report, reproduced card for card.

    Ugin, Eye of the Storms at 9 loyalty (7 printed, CR 306.5b, plus the `+2`
    its controller activated, CR 606.4), attacked by Devourer of Destiny (6/6)
    and Sowing Mycospawn (3/3) with no blockers: exactly 9 combat damage.

    CR 120.3c removes 9 loyalty counters as the damage is dealt, which takes
    Ugin to 0 loyalty, and CR 704.5i then puts it into its owner's graveyard
    at the state-based check the combat damage step already runs.
    """
    scenario = _eldrazi_vs_ugin(attackers=["Devourer of Destiny", "Sowing Mycospawn"])
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")

    _bobs_turn_then_alices(scenario)
    scenario.activate(ugin, username="bob")  # `+2`, CR 606.4
    scenario.pass_until_resolved()
    assert ugin.loyalty == 9, "the board the report describes: Ugin at 9 loyalty"

    while scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    devourer = scenario.creature("Devourer of Destiny", "alice")
    mycospawn = scenario.creature("Sowing Mycospawn", "alice")
    scenario.attack_with(devourer, mycospawn, defending=ugin)
    scenario.no_blocks()
    assignment = scenario.combat_damage()

    assert sorted(amount for _, amount in assignment) == [3, 6], "CR 510.1a: power each"
    assert ugin.counter_count(Counter.LOYALTY) == 0, "CR 120.3c: 9 loyalty counters removed"
    assert ugin.zone is Zone.GRAVEYARD, "CR 704.5i / CR 306.9"
    assert scenario.player("bob").life == 23, (
        "CR 702.19f: none of the 9 reached the player; 23 is 20 plus the 3 Ugin's +2 gained"
    )


def test_damage_to_a_planeswalker_is_never_marked_on_it():
    """CR 120.3e marks damage on a *creature*. A planeswalker is not one.

    Six damage onto a 7-loyalty Ugin leaves it at 1 loyalty and alive, with
    nothing marked - the reported symptom was the exact inverse, `damage=9`
    with `loyalty=9` untouched.
    """
    scenario = _eldrazi_vs_ugin(attackers=["Devourer of Destiny"])
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(scenario.creature("Devourer of Destiny", "alice"), defending=ugin)
    scenario.no_blocks()
    scenario.combat_damage()

    assert ugin.loyalty == 1, "CR 120.3c: 7 - 6"
    assert ugin.damage == 0, "CR 120.3e is the creature result; nothing is marked here"
    assert ugin.zone is Zone.BATTLEFIELD, "CR 704.5i takes only a walker at 0"


def test_more_damage_than_loyalty_removes_only_the_counters_that_are_there():
    """Nine damage onto a 7-loyalty Ugin is not an error, and not -2 loyalty.

    CR 120.3c removes "that many" counters; there are only seven, so seven come
    off and the walker is at 0 for CR 704.5i. `Counters.remove` refuses to take
    more than are present (CR 118.3), so the amount has to be clamped where the
    damage is applied rather than handed straight through.
    """
    scenario = _eldrazi_vs_ugin(attackers=["Devourer of Destiny", "Sowing Mycospawn"])
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    devourer = scenario.creature("Devourer of Destiny", "alice")
    mycospawn = scenario.creature("Sowing Mycospawn", "alice")
    scenario.attack_with(devourer, mycospawn, defending=ugin)
    scenario.no_blocks()
    scenario.combat_damage()

    assert ugin.counter_count(Counter.LOYALTY) == 0
    assert ugin.zone is Zone.GRAVEYARD


# -- noncombat damage (CR 120.3c is not a combat rule) ---------------------


def test_a_damage_spell_removes_loyalty_too():
    """CR 120.3c says "damage dealt to a planeswalker", not "combat damage".

    Lightning Bolt at Ugin takes 3 loyalty counters off (CR 306.7: the old
    redirection rule is gone, so a burn spell names the planeswalker itself).
    """
    scenario = (
        Scenario()
        .player(
            "alice", library=["Mountain"] * 5, hand=["Lightning Bolt"], battlefield=["Mountain"]
        )
        .player("bob", library=["Forest"] * 5, battlefield=[UGIN])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[ugin])

    assert ugin.loyalty == 4, "CR 120.3c: 7 - 3"
    assert ugin.damage == 0
    assert ugin.zone is Zone.BATTLEFIELD


def test_two_damage_spells_kill_a_planeswalker_between_them():
    """Loyalty removal accumulates across separate damage events."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"] * 5,
            hand=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"] * 5, battlefield=[UGIN])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")
    for expected in (4, 1):
        mountain = scenario.untapped_sources("Mountain")[0]
        scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[ugin])
        assert ugin.loyalty == expected
        assert ugin.zone is Zone.BATTLEFIELD

    last = scenario.untapped_sources("Mountain")[0]
    scenario.cast_and_resolve("Lightning Bolt", last, targets=[ugin])

    assert ugin.counter_count(Counter.LOYALTY) == 0
    assert ugin.zone is Zone.GRAVEYARD, "CR 704.5i, at the check after the spell resolved"


# -- trample (CR 702.19b) --------------------------------------------------


def test_trample_over_a_blocker_removes_the_planeswalkers_loyalty():
    """CR 702.19b: the excess goes to "the player, planeswalker, or battle the
    creature is attacking".

    Colossal Dreadmaw (6/6 trample) attacking Ugin, blocked by a Grizzly Bears:
    2 is lethal for the Bears (CR 510.1c), the other 4 tramples onto Ugin and
    takes four loyalty counters off it.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Mountain"] * 5, battlefield=["Colossal Dreadmaw"])
        .player("bob", library=["Forest"] * 5, battlefield=[UGIN, "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(dreadmaw, defending=ugin)
    scenario.block(dreadmaw, bears)
    scenario.combat_damage()

    assert bears.zone is Zone.GRAVEYARD, "CR 704.5g: 2 damage on a 2/2"
    assert ugin.loyalty == 3, "CR 702.19b: the 4 that trampled over, CR 120.3c: 7 - 4"
    assert ugin.damage == 0
    assert ugin.zone is Zone.BATTLEFIELD


# -- the creature rule is untouched (CR 120.3e, CR 704.5g) -----------------


def test_a_creature_still_has_its_damage_marked():
    """The other half of CR 120.3: a creature's damage is still marked on it,
    still not lethal below its toughness, and still cleared at CR 514.2."""
    scenario = (
        Scenario()
        .player(
            "alice", library=["Mountain"] * 5, hand=["Lightning Bolt"], battlefield=["Mountain"]
        )
        .player("bob", library=["Forest"] * 5, battlefield=["Devourer of Destiny"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    devourer = scenario.creature("Devourer of Destiny", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[devourer])

    assert devourer.damage == 3, "CR 120.3e"
    assert devourer.zone is Zone.BATTLEFIELD, "CR 704.5g: 3 is not lethal on a 6/6"


# -- a printed ability that names the planeswalker (CR 120.3c) -------------


def test_hellriders_attack_trigger_burns_the_planeswalker_it_is_attacking():
    """Hellrider: "deals 1 damage to the player **or planeswalker** it's attacking".

    `machines/effects.damage_the_attacked_player` used to return without
    dealing anything when the defender was a planeswalker, on the stated
    grounds that loyalty counters were not modelled. They are now what
    CR 120.3c removes, so the card does what it prints: one loyalty counter
    off as the trigger resolves, then three more from Hellrider's own combat
    damage (CR 510.1a).
    """
    scenario = (
        Scenario()
        .player("alice", library=["Mountain"] * 5, battlefield=["Hellrider"])
        .player("bob", library=["Forest"] * 5, battlefield=[UGIN])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    ugin = scenario.find(UGIN, Zone.BATTLEFIELD, "bob")

    scenario.attack_with(scenario.creature("Hellrider", "alice"), defending=ugin)
    scenario.pass_until_resolved()

    assert ugin.loyalty == 6, "CR 120.3c: the attack trigger's 1 damage"
    assert scenario.player("bob").life == 20, "the trigger names what it is attacking, not bob"

    scenario.no_blocks()
    scenario.combat_damage()

    assert ugin.loyalty == 3, "CR 510.1a plus CR 120.3c: Hellrider's own 3"
    assert ugin.damage == 0

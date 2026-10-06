"""Group and plural damage sources: several objects each deal their own damage.

Listed cards (NW-01, task T3):

- **Allies at Last** - "Up to two target creatures you control each deal
  damage equal to their power to target creature an opponent controls." with
  its Affinity for Allies line as the cost reducer (CR 702.41a).
- **Graceful Takedown** - "Any number of target enchanted creatures you
  control and up to one other target creature you control each deal damage
  equal to their power to target creature you don't control."
- **Aura Barbs** - "Each enchantment deals 2 damage to its controller, then
  each Aura attached to a creature deals 2 damage to the creature it's
  attached to."
- **Solar Blaze** - "Each creature deals damage to itself equal to its power."

Second printings that prove the readers are templates, not cards (each legal
in Modern, none in a deck list):

- **Band Together** - "Up to two target creatures you control each deal
  damage equal to their power to another target creature."
- **Friendly Rivalry** - "Target creature you control and up to one other
  target legendary creature you control each deal damage equal to their power
  to target creature you don't control."
- **Justice Strike** - "Target creature deals damage to itself equal to its
  power."
- **The Akroan War**, chapter III - "Each tapped creature deals damage to
  itself equal to its power."

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 120.1 / 120.2b** - an object that deals damage is its source, and a
  spell names which object deals it: here each creature, not the spell.
- **CR 120.3e / 120.3f** - damage marked on a creature; a lifelink source's
  controller gains that much life. Each source is its own damage event.
- **CR 608.2b** - an illegal target is not affected; the rest of the spell
  still happens unless every target is illegal.
- **CR 608.2h** - a source's power is read as the spell resolves.
- **CR 303.4b** - an Aura attached to a permanent makes it "enchanted".
- **CR 702.41a** - "Affinity for [text]" is "This spell costs {1} less to cast
  for each [text] you control."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(
    *,
    alice_battlefield: list[str],
    bob_battlefield: list[str],
    hand: list[str],
) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=alice_battlefield)
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Allies at Last -----------------------------------------------------------


def _allies_at_last(**kwargs):
    return _board(
        hand=["Allies at Last"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Forest", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw"],
        **kwargs,
    )


def test_allies_at_last_both_creatures_each_deal_their_power():
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[bears, giant, dreadmaw])

    assert dreadmaw.damage == 5, "2 from Grizzly Bears plus 3 from Hill Giant"
    assert bears.damage == 0 and giant.damage == 0, "damage goes one way only"


def test_allies_at_last_with_one_source_up_to_two_means_one():
    scenario = _allies_at_last()
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 3


def test_allies_at_last_with_no_source_chosen_does_nothing():
    """CR 115.6's "up to two" lets the caster choose none; the spell still
    resolves (its victim is legal) and no creature deals damage."""
    scenario = _allies_at_last()
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[dreadmaw])

    assert dreadmaw.damage == 0
    assert scenario.game.stack == []


def test_allies_at_last_victim_must_be_an_opponents_creature():
    """CR 115.1: the target's own restriction ("an opponent controls") is
    enforced at the announcement."""
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    with pytest.raises(ValueError):
        scenario.cast("Allies at Last", targets=[bears, giant])


def test_allies_at_last_sources_must_be_creatures_the_caster_controls():
    """Two of the opponent's creatures cannot both be sources: only one fits
    the victim's own requirement, and the other fits nothing."""
    scenario = _board(
        hand=["Allies at Last"],
        alice_battlefield=["Forest", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw", "Hill Giant"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Allies at Last", targets=[dreadmaw, giant])


def test_allies_at_last_the_victim_named_first_is_still_the_victim():
    """CR 601.2c fills each requirement from the targets chosen; which target
    plays the victim is the requirement it filled, not its place in the list."""
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[dreadmaw, bears, giant])

    assert dreadmaw.damage == 5


def test_allies_at_last_victim_gone_on_resolution_means_no_damage():
    """CR 608.2b: the victim left, the sources are still legal, so the spell
    resolves - and has nothing to hit."""
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Allies at Last", auto=True, targets=[bears, giant, dreadmaw])
    scenario.game.destroy(dreadmaw)

    scenario.resolve_top()

    assert bears.damage == 0 and giant.damage == 0
    assert scenario.find("Allies at Last", Zone.GRAVEYARD, "alice") is not None


def test_allies_at_last_a_source_that_left_deals_nothing_but_the_other_still_does():
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Allies at Last", auto=True, targets=[bears, giant, dreadmaw])
    scenario.game.destroy(giant)

    scenario.resolve_top()

    assert dreadmaw.damage == 2, "only Grizzly Bears is still a legal source"


def test_allies_at_last_reads_power_as_it_resolves():
    """CR 608.2h: a +1/+1 counter put on a source before resolution counts."""
    scenario = _allies_at_last()
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Allies at Last", auto=True, targets=[bears, dreadmaw])
    bears.add_counters(Counter.PLUS_ONE, 2)

    scenario.resolve_top()

    assert dreadmaw.damage == 4


def test_allies_at_last_each_source_is_its_own_damage_event():
    """CR 120.3f: a lifelink source's controller gains life, and CR 702.2's
    deathtouch applies to that source's own event - not the other's."""
    scenario = _board(
        hand=["Allies at Last"],
        alice_battlefield=["Typhoid Rats", "Child of Night", "Forest", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    rats = scenario.creature("Typhoid Rats", "alice")
    child = scenario.creature("Child of Night", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[rats, child, dreadmaw])

    assert scenario.player("alice").life == 22, "Child of Night's 2 lifelink damage"
    assert dreadmaw.zone is Zone.GRAVEYARD, "Typhoid Rats' deathtouch"


def test_allies_at_last_affinity_for_allies_reduces_the_cost():
    """CR 702.41a: the affinity line is a cost reducer, not part of the
    resolution text. With an Ally in play {2}{G} costs {1}{G}."""
    scenario = _board(
        hand=["Allies at Last"],
        alice_battlefield=["Hada Freeblade", "Grizzly Bears", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Allies at Last", auto=True, targets=[bears, dreadmaw])

    assert dreadmaw.damage == 2


def test_allies_at_last_without_an_ally_two_lands_are_not_enough():
    scenario = _board(
        hand=["Allies at Last"],
        alice_battlefield=["Grizzly Bears", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Allies at Last", auto=True, targets=[bears, dreadmaw])


# -- Band Together (the same reader on a second printing) -----------------------


def test_band_together_hits_another_target_creature_of_either_side():
    """ "another target creature" is any creature, so a creature the caster
    controls is a legal victim too - and, being distinct from the sources, it
    is the last target announced."""
    scenario = _board(
        hand=["Band Together"],
        alice_battlefield=[
            "Grizzly Bears",
            "Hill Giant",
            "Runeclaw Bear",
            "Forest",
            "Forest",
            "Forest",
        ],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")

    scenario.cast_and_resolve("Band Together", auto=True, targets=[bears, giant, runeclaw])

    assert runeclaw.zone is Zone.GRAVEYARD, "5 damage kills a 2/2"
    assert bears.damage == 0 and giant.damage == 0


def test_band_together_one_source_one_victim():
    scenario = _board(
        hand=["Band Together"],
        alice_battlefield=["Hill Giant", "Forest", "Forest", "Forest"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Band Together", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 3


# -- Graceful Takedown -----------------------------------------------------------


def _takedown_board():
    scenario = _board(
        hand=["Graceful Takedown"],
        alice_battlefield=[
            "Grizzly Bears",
            "Hill Giant",
            "Runeclaw Bear",
            "Pacifism",
            "Forest",
            "Forest",
        ],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    pacifism.attach_to(scenario.creature("Grizzly Bears", "alice"))
    return scenario


def test_graceful_takedown_enchanted_creature_and_one_other_each_deal_their_power():
    scenario = _takedown_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Graceful Takedown", auto=True, targets=[bears, giant, dreadmaw])

    assert dreadmaw.damage == 5


def test_graceful_takedown_the_unenchanted_creature_alone_is_the_up_to_one_other():
    scenario = _takedown_board()
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Graceful Takedown", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 3


def test_graceful_takedown_two_unenchanted_creatures_cannot_both_be_sources():
    """CR 303.4b: only an Aura on it makes a creature "enchanted"; the second
    unenchanted creature has no slot (the "other" slot takes just one)."""
    scenario = _takedown_board()
    giant = scenario.creature("Hill Giant", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Graceful Takedown", targets=[giant, runeclaw, dreadmaw])


def test_graceful_takedown_victim_must_be_a_creature_the_caster_does_not_control():
    scenario = _takedown_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")

    with pytest.raises(ValueError):
        scenario.cast("Graceful Takedown", targets=[bears, runeclaw])


def test_graceful_takedown_a_source_whose_aura_left_is_illegal_on_resolution():
    """CR 608.2b: "enchanted" is part of the target's own restriction, so a
    creature whose only Aura was removed before resolution deals nothing."""
    scenario = _takedown_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Graceful Takedown", auto=True, targets=[bears, giant, dreadmaw])
    scenario.game.destroy(scenario.find("Pacifism", Zone.BATTLEFIELD, "alice"))

    scenario.resolve_top()

    assert dreadmaw.damage == 3, "only Hill Giant is still a legal source"


def test_graceful_takedown_any_number_of_enchanted_creatures():
    scenario = _board(
        hand=["Graceful Takedown"],
        alice_battlefield=[
            "Grizzly Bears",
            "Hill Giant",
            "Runeclaw Bear",
            "Pacifism",
            "Pacifism",
            "Forest",
            "Forest",
        ],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    first, second = [
        card
        for card in scenario.game.battlefield
        if card.name == "Pacifism" and card.controller == "alice"
    ]
    first.attach_to(bears)
    second.attach_to(giant)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve(
        "Graceful Takedown", auto=True, targets=[bears, giant, runeclaw, dreadmaw]
    )

    assert dreadmaw.zone is Zone.GRAVEYARD, "2 + 3 from the enchanted pair and 2 from the one other"


# -- Friendly Rivalry (the same reader, a legendary "other" slot) ---------------


def test_friendly_rivalry_creature_and_a_legendary_one_each_deal_their_power():
    scenario = _board(
        hand=["Friendly Rivalry"],
        alice_battlefield=["Grizzly Bears", "Appa, Steadfast Guardian", "Forest", "Mountain"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    appa = scenario.creature("Appa, Steadfast Guardian", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Friendly Rivalry", auto=True, targets=[bears, appa, dreadmaw])

    assert dreadmaw.damage == 5, "2 from Grizzly Bears, 3 from Appa"


def test_friendly_rivalry_the_other_source_must_be_legendary():
    scenario = _board(
        hand=["Friendly Rivalry"],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Forest", "Mountain"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Friendly Rivalry", targets=[bears, giant, dreadmaw])


# -- Aura Barbs ------------------------------------------------------------------


def _barbs_board(*, alice_extra=(), bob_extra=()):
    scenario = _board(
        hand=["Aura Barbs"],
        alice_battlefield=[
            "Hill Giant",
            "Pacifism",
            "Glorious Anthem",
            "Mountain",
            "Mountain",
            "Mountain",
            *alice_extra,
        ],
        bob_battlefield=["Grizzly Bears", "Pacifism", *bob_extra],
    )
    alice_pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "alice")
    bob_pacifism = scenario.find("Pacifism", Zone.BATTLEFIELD, "bob")
    # Alice's Aura enchants Bob's creature, Bob's Aura enchants Alice's.
    alice_pacifism.attach_to(scenario.creature("Grizzly Bears", "bob"))
    bob_pacifism.attach_to(scenario.creature("Hill Giant", "alice"))
    return scenario


def test_aura_barbs_every_enchantment_hurts_its_controller_then_auras_hurt_their_creature():
    scenario = _barbs_board()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Aura Barbs", auto=True)

    # Alice controls Pacifism and Glorious Anthem, Bob controls Pacifism.
    assert scenario.player("alice").life == 16
    assert scenario.player("bob").life == 18
    assert giant.damage == 2, "Bob's Pacifism is attached to Hill Giant"
    assert bears.zone is Zone.GRAVEYARD, (
        "Alice's Pacifism is attached to Grizzly Bears: 2 is lethal"
    )


def test_aura_barbs_an_aura_on_a_land_hurts_only_its_controller():
    """ "each Aura attached to a creature": an Aura on a land is an enchantment
    (it deals 2 to its controller) but not one the second half reaches."""
    scenario = _board(
        hand=["Aura Barbs"],
        alice_battlefield=[
            "Hill Giant",
            "Wild Growth",
            "Forest",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.find("Wild Growth", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Aura Barbs", auto=True)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20
    assert giant.damage == 0 and bears.damage == 0


def test_aura_barbs_with_no_enchantments_does_nothing():
    scenario = _board(
        hand=["Aura Barbs"],
        alice_battlefield=["Hill Giant", "Mountain", "Mountain", "Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )

    scenario.cast_and_resolve("Aura Barbs", auto=True)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20
    assert scenario.creature("Hill Giant", "alice").damage == 0


def test_aura_barbs_second_half_reads_the_board_after_the_first():
    """CR 608.2c: the instructions run in order. An Aura on a creature Pacifism
    has not killed yet is still attached when the second half runs - here the
    only creature dies of the second half, so the Aura it carried goes after."""
    scenario = _barbs_board()
    scenario.cast_and_resolve("Aura Barbs", auto=True)

    assert scenario.find("Pacifism", Zone.GRAVEYARD, "alice") is not None, (
        "its creature died, so the Aura it enchanted went to the graveyard (CR 303.4c)"
    )


# -- Solar Blaze and the self-damage template ------------------------------------


def test_solar_blaze_each_creature_deals_damage_to_itself_equal_to_its_power():
    scenario = _board(
        hand=["Solar Blaze"],
        alice_battlefield=[
            "Grizzly Bears",
            "Hada Freeblade",
            "Mountain",
            "Mountain",
            "Plains",
            "Plains",
        ],
        bob_battlefield=["Colossal Dreadmaw", "Darksteel Colossus"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    hada = scenario.creature("Hada Freeblade", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    colossus = scenario.creature("Darksteel Colossus", "bob")

    scenario.cast_and_resolve("Solar Blaze", auto=True)

    assert bears.zone is Zone.GRAVEYARD
    assert dreadmaw.zone is Zone.GRAVEYARD
    assert hada.zone is Zone.BATTLEFIELD and hada.damage == 0, "a 0-power creature takes 0"
    assert colossus.zone is Zone.BATTLEFIELD and colossus.damage == 11, "indestructible"


def test_solar_blaze_reads_power_as_it_resolves():
    """CR 608.2h: +1/+1 counters raise the power, so the 2/2 that would
    survive nothing is a 3/3 taking 3."""
    scenario = _board(
        hand=["Solar Blaze"],
        alice_battlefield=["Grizzly Bears", "Mountain", "Mountain", "Plains", "Plains"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 2)  # a 4/4 taking 4 dies too, so check the amount
    scenario.cast_and_resolve("Solar Blaze", auto=True)

    assert bears.zone is Zone.GRAVEYARD


def test_solar_blaze_creatures_are_their_own_sources():
    """CR 120.3f: a lifelink creature gains its controller life from the
    damage it deals itself."""
    scenario = _board(
        hand=["Solar Blaze"],
        alice_battlefield=["Child of Night", "Mountain", "Mountain", "Plains", "Plains"],
        bob_battlefield=[],
    )
    scenario.cast_and_resolve("Solar Blaze", auto=True)

    assert scenario.player("alice").life == 22


def test_solar_blaze_leaves_non_creatures_alone():
    scenario = _board(
        hand=["Solar Blaze"],
        alice_battlefield=["Glorious Anthem", "Mountain", "Mountain", "Plains", "Plains"],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.cast_and_resolve("Solar Blaze", auto=True)

    assert scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice") is not None
    assert scenario.player("alice").life == 20


def test_justice_strike_target_creature_deals_damage_to_itself():
    scenario = _board(
        hand=["Justice Strike"],
        alice_battlefield=["Mountain", "Plains"],
        bob_battlefield=["Colossal Dreadmaw", "Grizzly Bears"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Justice Strike", auto=True, targets=[dreadmaw])

    assert dreadmaw.zone is Zone.GRAVEYARD
    assert bears.damage == 0, "only the target hurts itself"


def test_justice_strike_target_power_zero_deals_nothing():
    scenario = _board(
        hand=["Justice Strike"],
        alice_battlefield=["Mountain", "Plains", "Hada Freeblade"],
        bob_battlefield=[],
    )
    hada = scenario.creature("Hada Freeblade", "alice")

    scenario.cast_and_resolve("Justice Strike", auto=True, targets=[hada])

    assert hada.damage == 0 and hada.zone is Zone.BATTLEFIELD


def _akroan_war_chapter_three():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["The Akroan War"], battlefield=["Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Colossal Dreadmaw", "Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_akroan_war_chapter_three_each_tapped_creature_hurts_itself():
    scenario = _akroan_war_chapter_three()
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    bears.tapped = True
    runeclaw.tapped = True
    saga = scenario.find("The Akroan War", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(saga, "alice")
    scenario.choose_trigger_targets(
        "The Akroan War", [scenario.creature("Colossal Dreadmaw", "bob")]
    )
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    for _ in range(2):
        scenario.game.add_counters(saga, Counter.LORE, 1)
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()
            scenario.game.put_triggers_on_stack()

    assert bears.zone is Zone.GRAVEYARD, "tapped: took its own 2 power"
    assert runeclaw.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 0, "untapped creatures are not hit"


# -- "Tap/pump <sources>. They each deal damage equal to their power to ..." --
#
# Coordinated Clobbering, Tandem Takedown, Terrific Team-Up: the first
# sentence acts on the same targets "They" names (CR 608.2c, in order), so the
# power each deals is read after the pump (CR 608.2h).


def _two_sentence_board(name, *, extra=()):
    return _board(
        hand=[name],
        alice_battlefield=["Grizzly Bears", "Hill Giant", "Forest", "Forest", "Forest", *extra],
        bob_battlefield=["Colossal Dreadmaw"],
    )


def test_tandem_takedown_pumps_each_source_then_each_deals_its_new_power():
    scenario = _two_sentence_board("Tandem Takedown")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Tandem Takedown", auto=True, targets=[bears, giant, dreadmaw])

    assert dreadmaw.zone is Zone.GRAVEYARD, "(2+1) plus (3+1) is 7 damage to a 6/6"
    assert scenario.game.power_of(bears) == 3 and scenario.game.power_of(giant) == 4


def test_tandem_takedown_one_source_is_enough():
    scenario = _two_sentence_board("Tandem Takedown")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Tandem Takedown", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 4


def test_tandem_takedown_victim_gone_still_pumps_the_sources():
    scenario = _two_sentence_board("Tandem Takedown")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_onto_stack("Tandem Takedown", auto=True, targets=[giant, dreadmaw])
    scenario.game.deal_damage(dreadmaw, 6, source=giant)
    scenario.game.check_state_based_actions()
    scenario.resolve_top()

    assert dreadmaw.zone is Zone.GRAVEYARD
    assert scenario.game.power_of(giant) == 4, "CR 608.2b: one legal target left, still resolves"


def test_coordinated_clobbering_taps_the_sources_which_then_deal_damage():
    scenario = _two_sentence_board("Coordinated Clobbering")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Coordinated Clobbering", auto=True, targets=[bears, giant, dreadmaw])

    assert bears.tapped and giant.tapped
    assert dreadmaw.damage == 5


def test_coordinated_clobbering_an_already_tapped_creature_is_not_a_legal_source():
    scenario = _two_sentence_board("Coordinated Clobbering")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Coordinated Clobbering", targets=[bears, dreadmaw])
    scenario.cast_and_resolve("Coordinated Clobbering", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 3


def test_coordinated_clobbering_victim_must_be_an_opponents_creature():
    scenario = _two_sentence_board("Coordinated Clobbering")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    with pytest.raises(ValueError):
        scenario.cast("Coordinated Clobbering", targets=[bears, giant])


def test_terrific_team_up_one_source_pumped_then_deals_damage():
    scenario = _two_sentence_board("Terrific Team-Up")
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Terrific Team-Up", auto=True, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 4


def test_terrific_team_up_is_two_cheaper_with_a_big_permanent():
    scenario = _two_sentence_board("Terrific Team-Up", extra=("Colossal Dreadmaw",))
    giant = scenario.creature("Hill Giant", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Terrific Team-Up", *forests, targets=[giant, dreadmaw])

    assert dreadmaw.damage == 4, "{3}{G} less {2} is payable with two Forests"

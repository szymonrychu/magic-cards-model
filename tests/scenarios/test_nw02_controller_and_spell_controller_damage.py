"""Scenario: damage to a target's controller, to a spell's controller, and to "you".

Listed: Judgment Bolt (X damage to that creature's controller, where X is the
number of Equipment you control), Kami's Flare (a trailing "if you control a
modified creature"), Flames of the Raze-Boar ("Then ... deals 2 damage to each
other creature that player controls if you control a creature with power 4 or
greater"), Parallectric Feedback (damage to target spell's controller equal to
that spell's mana value) and Orcish Cannonade ("2 damage to any target and 3
damage to you. Draw a card.").

Second printings: Synchronized Spellcraft (where-X over the party), Refuse //
Cooperate (Refuse is Parallectric Feedback's template), Psionic Blast (the
any-target-and-you damage). Kami's Flare and Flames of the Raze-Boar are the
only printings of their templates legal in Modern, Pioneer or Standard
(Scryfall `o:/also deals \\d+ damage to .* controller if/` and `o:/deals \\d+
damage to each other creature that player controls/` return one card each).

Verified this session with `mise run rules:find`:

- **CR 608.2b** - a spell whose only target is illegal doesn't resolve: no
  part of it happens, the controller damage included.
- **CR 608.2c** - instructions are followed in the order written; "Then"
  and a trailing "if" are checked as that instruction is reached.
- **CR 608.2h** - "that player" / "that creature's controller" is read from
  last known information when the creature has already left.
- **CR 700.9** - modified: Equipment and Auras you control and counters on it.
- **CR 202.3** - mana value; a spell on the stack counts the announced X
  (CR 107.3a).
- **CR 120.3a** - damage to a player makes them lose that much life.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone

from .harness import Scenario, mana_from


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            life=20,
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _life(scenario):
    return scenario.player("alice").life, scenario.player("bob").life


# -- Judgment Bolt and Synchronized Spellcraft: where-X controller damage -----------


def test_judgment_bolt_deals_x_equal_to_equipment_you_control_to_the_controller():
    scenario = _board(
        alice_hand=["Judgment Bolt"],
        alice_battlefield=["Mountain"] * 4 + ["Bonesplitter", "Bonesplitter"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Judgment Bolt", *scenario.untapped_sources(*["Mountain"] * 4), targets=[giant]
    )
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 18), "two Equipment: X is 2"


def test_judgment_bolt_with_no_equipment_deals_zero_to_the_controller():
    scenario = _board(
        alice_hand=["Judgment Bolt"],
        alice_battlefield=["Mountain"] * 4,
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Judgment Bolt", *scenario.untapped_sources(*["Mountain"] * 4), targets=[giant]
    )
    assert _life(scenario) == (20, 20)
    assert giant.zone is Zone.GRAVEYARD


def test_judgment_bolt_counts_only_equipment_the_caster_controls():
    scenario = _board(
        alice_hand=["Judgment Bolt"],
        alice_battlefield=["Mountain"] * 4 + ["Bonesplitter"],
        bob_battlefield=["Hill Giant", "Bonesplitter"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Judgment Bolt", *scenario.untapped_sources(*["Mountain"] * 4), targets=[giant]
    )
    assert _life(scenario) == (20, 19), "bob's own Bonesplitter does not count"


def test_judgment_bolt_pays_the_controller_even_when_the_creature_dies_to_the_damage():
    """CR 608.2h: the controller is read from last known information."""
    scenario = _board(
        alice_hand=["Judgment Bolt"],
        alice_battlefield=["Mountain"] * 4 + ["Bonesplitter"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Judgment Bolt", *scenario.untapped_sources(*["Mountain"] * 4), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19


def test_judgment_bolt_does_nothing_when_its_target_has_left():
    """CR 608.2b: no target left, nothing happens, no controller damage."""
    scenario = _board(
        alice_hand=["Judgment Bolt"],
        alice_battlefield=["Mountain"] * 4 + ["Bonesplitter"],
        bob_battlefield=["Grizzly Bears", "Island"],
        bob_hand=["Unsummon"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    spell = scenario.cast_onto_stack(
        "Judgment Bolt", *scenario.untapped_sources(*["Mountain"] * 4), targets=[bears]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 20)


def test_synchronized_spellcraft_counts_the_party_the_same_way():
    scenario = _board(
        alice_hand=["Synchronized Spellcraft"],
        alice_battlefield=["Mountain"] * 5 + ["Pondering Mage"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Synchronized Spellcraft", *scenario.untapped_sources(*["Mountain"] * 5), targets=[giant]
    )
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19, "a Wizard alone is a party of one"


# -- Kami's Flare: a trailing condition -------------------------------------------


def _equip_bonesplitter(scenario, creature):
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    activation = equip_activation(scenario.game, bonesplitter, creature, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Mountain"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_kamis_flare_also_hits_the_controller_when_you_control_a_modified_creature():
    scenario = _board(
        alice_hand=["Kami's Flare"],
        alice_battlefield=["Mountain"] * 3 + ["Bonesplitter", "Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    _equip_bonesplitter(scenario, bears)
    scenario.cast_and_resolve(
        "Kami's Flare", *scenario.untapped_sources("Mountain", "Mountain"), targets=[giant]
    )
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18


def test_kamis_flare_without_a_modified_creature_deals_only_the_first_damage():
    scenario = _board(
        alice_hand=["Kami's Flare"],
        alice_battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Kami's Flare", *scenario.untapped_sources("Mountain", "Mountain"), targets=[giant]
    )
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20, "an unmodified creature is not enough"


def test_kamis_flare_counts_a_creature_with_a_counter_as_modified():
    scenario = _board(
        alice_hand=["Kami's Flare"],
        alice_battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    bears.add_counters("+1/+1", 1)
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Kami's Flare", *scenario.untapped_sources("Mountain", "Mountain"), targets=[giant]
    )
    assert scenario.player("bob").life == 18


def test_kamis_flare_only_counts_creatures_you_control_as_modified():
    scenario = _board(
        alice_hand=["Kami's Flare"],
        alice_battlefield=["Mountain", "Mountain"],
        bob_battlefield=["Hill Giant", "Grizzly Bears"],
    )
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").add_counters("+1/+1", 1)
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Kami's Flare", *scenario.untapped_sources("Mountain", "Mountain"), targets=[giant]
    )
    assert scenario.player("bob").life == 20


def test_kamis_flare_can_target_a_planeswalker_and_pay_its_controller():
    scenario = _board(
        alice_hand=["Kami's Flare"],
        alice_battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        bob_battlefield=["Jace Beleren"],
    )
    scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").add_counters("+1/+1", 1)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    loyalty = jace.counter_count("loyalty")
    scenario.cast_and_resolve(
        "Kami's Flare", *scenario.untapped_sources("Mountain", "Mountain"), targets=[jace]
    )
    scenario.state_based_actions()
    assert scenario.player("bob").life == 18
    assert jace.zone is Zone.GRAVEYARD or jace.counter_count("loyalty") == loyalty - 3


# -- Flames of the Raze-Boar -------------------------------------------------------


def test_raze_boar_hits_the_target_then_every_other_creature_that_player_controls():
    scenario = _board(
        alice_hand=["Flames of the Raze-Boar"],
        alice_battlefield=["Mountain"] * 6 + ["Colossal Dreadmaw", "Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Elvish Mystic", "Llanowar Elves"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Flames of the Raze-Boar", *scenario.untapped_sources(*["Mountain"] * 6), targets=[giant]
    )
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").damage == 0
    assert scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD, "alice").damage == 0


def test_raze_boar_without_a_power_four_creature_stops_after_the_first_damage():
    scenario = _board(
        alice_hand=["Flames of the Raze-Boar"],
        alice_battlefield=["Mountain"] * 6 + ["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Elvish Mystic"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Flames of the Raze-Boar", *scenario.untapped_sources(*["Mountain"] * 6), targets=[giant]
    )
    scenario.state_based_actions()
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "bob").damage == 0


def test_raze_boar_power_four_is_a_threshold_not_an_exact_value():
    """Power exactly 4 counts (a 4/4 Serra Angel-sized creature is 4/4)."""
    scenario = _board(
        alice_hand=["Flames of the Raze-Boar"],
        alice_battlefield=["Mountain"] * 6 + ["Serra Angel"],
        bob_battlefield=["Hill Giant", "Elvish Mystic"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Flames of the Raze-Boar", *scenario.untapped_sources(*["Mountain"] * 6), targets=[giant]
    )
    scenario.state_based_actions()
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "bob") is not None


def test_raze_boar_with_a_lone_target_creature_has_nobody_else_to_hit():
    scenario = _board(
        alice_hand=["Flames of the Raze-Boar"],
        alice_battlefield=["Mountain"] * 6 + ["Colossal Dreadmaw"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    target = scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Flames of the Raze-Boar", *scenario.untapped_sources(*["Mountain"] * 6), targets=[target]
    )
    assert target.damage == 4
    assert scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD, "alice").damage == 0


def test_raze_boar_only_targets_a_creature_an_opponent_controls():
    scenario = _board(
        alice_hand=["Flames of the Raze-Boar"],
        alice_battlefield=["Mountain"] * 6 + ["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError):
        scenario.cast("Flames of the Raze-Boar", username="alice", targets=[mine])


# -- Parallectric Feedback / Refuse ------------------------------------------------


def _alice_casts_then_bob_responds(scenario, alice_spell, alice_args, bob_card, bob_land_names):
    spell = scenario.cast_onto_stack(
        alice_spell, *alice_args["sources"], targets=alice_args["targets"]
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        bob_card,
        *scenario.untapped_sources(*bob_land_names, username="bob"),
        username="bob",
        targets=[spell],
    )
    return spell


def test_parallectric_feedback_deals_the_spells_mana_value_to_its_controller():
    scenario = _board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        bob_hand=["Parallectric Feedback"],
        bob_battlefield=["Mountain"] * 4,
    )
    _alice_casts_then_bob_responds(
        scenario,
        "Lightning Bolt",
        {"sources": scenario.untapped_sources("Mountain"), "targets": ["bob"]},
        "Parallectric Feedback",
        ["Mountain"] * 4,
    )
    scenario.resolve_top()
    scenario.resolve_top()
    assert _life(scenario) == (19, 17), "Feedback: 1 to alice; her Bolt then hit bob for 3"


def test_parallectric_feedback_counts_x_on_a_spell_on_the_stack():
    scenario = _board(
        alice_hand=["Banefire"],
        alice_battlefield=["Mountain"] * 5,
        bob_hand=["Parallectric Feedback"],
        bob_battlefield=["Mountain"] * 4,
    )
    banefire = scenario.find("Banefire", Zone.HAND, "alice")
    scenario.game.cast(
        banefire,
        "alice",
        x_value=4,
        targets=["bob"],
        mana_sources=scenario.untapped_sources(*["Mountain"] * 5),
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Parallectric Feedback",
        *scenario.untapped_sources(*["Mountain"] * 4, username="bob"),
        username="bob",
        targets=[banefire],
    )
    scenario.resolve_top()
    assert scenario.player("alice").life == 15, "CR 202.3 + CR 107.3a: {X}{R} with X=4 is 5"


def test_parallectric_feedback_does_nothing_if_the_targeted_spell_is_gone():
    """CR 608.2b: countered first, so the only target is illegal."""
    scenario = _board(
        alice_hand=["Lightning Bolt", "Counterspell"],
        alice_battlefield=["Mountain", "Island", "Island"],
        bob_hand=["Parallectric Feedback"],
        bob_battlefield=["Mountain"] * 4,
    )
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_priority("alice")
    feedback = scenario.cast_onto_stack(
        "Parallectric Feedback",
        *scenario.untapped_sources(*["Mountain"] * 4, username="bob"),
        username="bob",
        targets=[bolt],
    )
    scenario.pass_priority("bob")
    scenario.cast_and_resolve(
        "Counterspell", *scenario.untapped_sources("Island", "Island"), targets=[bolt]
    )
    assert bolt.zone is Zone.GRAVEYARD
    scenario.resolve_top()
    assert feedback.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 20)


def test_refuse_is_the_second_printing_of_the_spell_controller_template():
    scenario = _board(
        alice_hand=["Lightning Bolt"],
        alice_battlefield=["Mountain"],
        bob_hand=["Refuse // Cooperate"],
        bob_battlefield=["Mountain"] * 4,
    )
    _alice_casts_then_bob_responds(
        scenario,
        "Lightning Bolt",
        {"sources": scenario.untapped_sources("Mountain"), "targets": ["bob"]},
        "Refuse // Cooperate",
        ["Mountain"] * 4,
    )
    scenario.resolve_top()
    assert scenario.player("alice").life == 19


# -- Orcish Cannonade --------------------------------------------------------------


def test_orcish_cannonade_deals_two_to_the_target_three_to_you_and_draws():
    scenario = _board(
        alice_hand=["Orcish Cannonade"],
        alice_battlefield=["Mountain"] * 3,
    )
    hand_before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve(
        "Orcish Cannonade", *scenario.untapped_sources(*["Mountain"] * 3), targets=["bob"]
    )
    assert _life(scenario) == (17, 18)
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1, "cast one, drew one"


def test_orcish_cannonade_can_hit_a_creature_and_still_costs_you_three_and_a_card():
    scenario = _board(
        alice_hand=["Orcish Cannonade"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Orcish Cannonade", *scenario.untapped_sources(*["Mountain"] * 3), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]


def test_orcish_cannonade_kills_you_at_three_life_but_you_still_drew_first():
    """CR 608.2c: all of it happens, then CR 704.5a checks the 0 life."""
    scenario = _board(alice_hand=["Orcish Cannonade"], alice_battlefield=["Mountain"] * 3)
    scenario.player("alice").life = 3
    scenario.cast_and_resolve(
        "Orcish Cannonade", *scenario.untapped_sources(*["Mountain"] * 3), targets=["bob"]
    )
    scenario.state_based_actions()
    assert scenario.player("alice").life == 0
    assert scenario.player("bob").life == 18
    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]


def test_orcish_cannonade_with_an_illegal_target_does_nothing_at_all():
    """CR 608.2b: its only target is gone; nothing, including the draw."""
    scenario = _board(
        alice_hand=["Orcish Cannonade"],
        alice_battlefield=["Mountain"] * 3,
        bob_battlefield=["Grizzly Bears", "Island"],
        bob_hand=["Unsummon"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    spell = scenario.cast_onto_stack(
        "Orcish Cannonade", *scenario.untapped_sources(*["Mountain"] * 3), targets=[bears]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    assert _life(scenario) == (20, 20)
    assert scenario.player("alice").hand == []


def test_psionic_blast_is_the_same_clause_without_a_following_instruction():
    scenario = _board(alice_hand=["Psionic Blast"], alice_battlefield=["Island"] * 2 + ["Mountain"])
    scenario.cast_and_resolve(
        "Psionic Blast", *scenario.untapped_sources("Island", "Island", "Mountain"), targets=["bob"]
    )
    assert _life(scenario) == (18, 16)

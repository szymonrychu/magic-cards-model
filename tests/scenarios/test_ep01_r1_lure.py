"""Scenario: lure - "All creatures able to block `<this>` do so." (CR 509.1c),
its enchanted/equipped forms, and the neighbouring attacker-side
requirements "must be blocked if able" under a condition (Frodo Baggins) and
"must be blocked by exactly one creature if able" (Nacatl War-Pride).

CR 509.1c: "The defending player checks each creature they control to see
whether it's affected by any requirements ... If the number of requirements
that are being obeyed is fewer than the maximum possible number of
requirements that could be obeyed without disobeying any restrictions, the
declaration of blockers is illegal." A lure is one requirement per creature
that can block the lure creature: a creature that cannot block it (tapped,
"can't block", no flying or reach for a flyer) has no requirement to obey, so
the restriction side (CR 509.1b) always wins.

Proof printings: Breaker of Armies, Elvish Bard and Prized Unicorn (self),
Lure (enchanted creature), Nemesis Mask (equipped creature), Noble Quarry
(self or enchanted creature), Frodo Baggins, Nacatl War-Pride.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines import combat as combat_rules
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.effects import trigger_effect_for
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card

from .harness import Scenario, mana_from

_LISTED = [
    "Breaker of Armies",
    "Elvish Bard",
    "Nessian Boar",
    "Ochran Assassin",
    "Prized Unicorn",
    "Shinen of Life's Roar",
    "Treeshaker Chimera",
    "Lure",
    "Nemesis Mask",
    "Noble Quarry",
]

_MARKERS = (
    "able to block",
    "must be blocked",
)


@pytest.mark.parametrize("name", _LISTED + ["Frodo Baggins", "Nacatl War-Pride"])
def test_every_listed_card_reads_its_requirement_line_as_handled(name):
    clauses = [
        clause
        for clause in classify_clauses(card(name))
        if clause.text.lower().startswith(("all creatures able to block", "as long as"))
        or "must be blocked" in clause.text.lower()
    ]
    assert clauses, f"{name}: no clause carries the lure/must-be-blocked line"
    assert all(clause.category == HANDLED for clause in clauses), clauses


def setup(attackers, blockers):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=attackers)
        .player("bob", battlefield=blockers)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def attack(scenario, *names):
    found = [
        creature
        for creature in scenario.game.permanents_controlled_by("alice")
        if creature.name in names
    ]
    scenario.attack_with(*found)
    return found


# -- self form -------------------------------------------------------------------


@pytest.mark.parametrize("lure", ["Breaker of Armies", "Elvish Bard", "Prized Unicorn"])
def test_a_declaration_that_leaves_an_able_creature_home_is_illegal(lure):
    scenario = setup([lure], ["Grizzly Bears", "Hill Giant"])
    (attacker,) = attack(scenario, lure)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="all creatures able to block|able to block"):
        scenario.no_blocks()
    with pytest.raises(ValueError, match="Hill Giant"):
        scenario.block(attacker, bears)
    assert scenario.blockers() == []


def test_every_able_creature_blocking_is_legal():
    scenario = setup(["Breaker of Armies"], ["Grizzly Bears", "Hill Giant"])
    (attacker,) = attack(scenario, "Breaker of Armies")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.block(attacker, bears, giant)

    assert set(scenario.game.combat.attack_by(attacker.id).blockers) == {bears.id, giant.id}


def test_the_refusal_is_in_the_engines_own_words():
    scenario = setup(["Breaker of Armies"], ["Grizzly Bears"])
    attack(scenario, "Breaker of Armies")

    with pytest.raises(ValueError) as refused:
        scenario.no_blocks()
    text = str(refused.value)
    assert "Breaker of Armies" in text and "Grizzly Bears" in text and "CR 509.1c" in text


def test_a_tapped_creature_is_excused():
    scenario = setup(["Breaker of Armies"], ["Grizzly Bears", "Hill Giant"])
    (attacker,) = attack(scenario, "Breaker of Armies")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    giant.tapped = True

    scenario.block(attacker, bears)

    assert scenario.game.combat.attack_by(attacker.id).blockers == [bears.id]


def test_a_creature_that_cant_block_is_excused_and_the_rest_still_must():
    """A lure plus a "can't block" restriction on one creature stays legal:
    Bloodghast is excused, Grizzly Bears is not."""
    scenario = setup(["Breaker of Armies"], ["Bloodghast", "Grizzly Bears"])
    (attacker,) = attack(scenario, "Breaker of Armies")
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.no_blocks()
    scenario.block(attacker, bears)
    assert scenario.game.is_blocked(attacker)


def test_with_every_creature_unable_to_block_no_block_is_legal():
    scenario = setup(["Breaker of Armies"], ["Bloodghast"])
    attack(scenario, "Breaker of Armies")

    scenario.no_blocks()

    assert scenario.blockers() == []


def test_a_creature_without_flying_or_reach_is_excused_against_a_flying_lure():
    scenario = setup(["Serra Angel", "Lure"], ["Grizzly Bears", "Wind Drake"])
    angel = scenario.creature("Serra Angel")
    lure = scenario.find("Lure", Zone.BATTLEFIELD, "alice")
    lure.attach_to(angel)
    scenario.attack_with(angel)
    drake = scenario.creature("Wind Drake", "bob")

    with pytest.raises(ValueError, match="Wind Drake"):
        scenario.no_blocks()
    scenario.block(angel, drake)
    assert scenario.blockers() == [drake]


def test_a_creature_that_can_block_only_flyers_is_excused_for_a_ground_lure():
    scenario = setup(["Breaker of Armies"], ["Cloud Elemental", "Grizzly Bears"])
    (attacker,) = attack(scenario, "Breaker of Armies")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.block(attacker, bears)

    assert scenario.blockers() == [bears]


def test_a_non_lure_attacker_beside_it_may_be_left_unblocked():
    scenario = setup(["Breaker of Armies", "Hill Giant"], ["Grizzly Bears"])
    breaker, giant = attack(scenario, "Breaker of Armies", "Hill Giant")
    bears = scenario.creature("Grizzly Bears", "bob")
    if breaker.name != "Breaker of Armies":
        breaker, giant = giant, breaker

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.block(giant, bears)  # blocking the wrong attacker obeys nothing
    scenario.block(breaker, bears)
    assert not scenario.game.is_blocked(giant)


def test_two_lures_each_blocker_serves_one_of_them():
    scenario = setup(["Breaker of Armies", "Elvish Bard"], ["Grizzly Bears", "Runeclaw Bear"])
    breaker, bard = attack(scenario, "Breaker of Armies", "Elvish Bard")
    if breaker.name != "Breaker of Armies":
        breaker, bard = bard, breaker
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError, match="able to block"):
        scenario.game.declare_blockers([(bears, breaker)])  # Runeclaw Bear could block too
    scenario.game.declare_blockers([(bears, breaker), (other, bard)])
    assert scenario.game.is_blocked(breaker) and scenario.game.is_blocked(bard)


def test_two_lures_both_blockers_on_one_is_as_good():
    scenario = setup(["Breaker of Armies", "Elvish Bard"], ["Grizzly Bears", "Runeclaw Bear"])
    breaker, bard = attack(scenario, "Breaker of Armies", "Elvish Bard")
    if breaker.name != "Breaker of Armies":
        breaker, bard = bard, breaker
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")

    scenario.block(breaker, bears, other)

    assert not scenario.game.is_blocked(bard)


def test_a_blocker_with_extra_blocks_must_serve_both_lures():
    scenario = setup(["Breaker of Armies", "Elvish Bard"], ["Palace Guard"])
    breaker, bard = attack(scenario, "Breaker of Armies", "Elvish Bard")
    guard = scenario.creature("Palace Guard", "bob")

    with pytest.raises(ValueError, match="able to block"):
        scenario.game.declare_blockers([(guard, breaker)])
    scenario.game.declare_blockers([(guard, breaker), (guard, bard)])
    assert scenario.game.is_blocked(breaker) and scenario.game.is_blocked(bard)


def test_a_menace_lure_with_one_able_blocker_may_go_unblocked():
    """CR 509.1b beats CR 509.1c: one creature cannot block a menace attacker
    alone, so there is no legal declaration obeying the lure."""
    scenario = setup(["Boggart Brute", "Nemesis Mask"], ["Grizzly Bears"])
    brute = scenario.creature("Boggart Brute")
    scenario.find("Nemesis Mask", Zone.BATTLEFIELD, "alice").attach_to(brute)
    scenario.attack_with(brute)

    scenario.no_blocks()

    assert scenario.blockers() == []


def test_a_menace_lure_with_two_able_blockers_needs_both():
    """No single blocker is legal on its own, but the two together are: the
    maximum obeyable is both."""
    scenario = setup(["Boggart Brute", "Nemesis Mask"], ["Grizzly Bears", "Hill Giant"])
    brute = scenario.creature("Boggart Brute")
    scenario.find("Nemesis Mask", Zone.BATTLEFIELD, "alice").attach_to(brute)
    scenario.attack_with(brute)

    with pytest.raises(ValueError, match="together"):
        scenario.no_blocks()
    scenario.block(
        brute,
        scenario.creature("Grizzly Bears", "bob"),
        scenario.creature("Hill Giant", "bob"),
    )


def test_the_lure_must_be_obeyed_by_defaults_when_nobody_scripts_the_blocks():
    scenario = setup(["Breaker of Armies"], ["Grizzly Bears", "Hill Giant"])
    (attacker,) = attack(scenario, "Breaker of Armies")

    pairs = combat_rules.required_block_declaration(scenario.game, "bob")

    assert {blocker_id for blocker_id, _ in pairs} == {
        creature.id for creature in scenario.game.permanents_controlled_by("bob")
    }
    assert {attacker_id for _, attacker_id in pairs} == {attacker.id}


# -- equipped / enchanted ------------------------------------------------------------


def test_lure_aura_forces_the_blocks_on_the_enchanted_creature():
    scenario = setup(["Hill Giant", "Lure"], ["Grizzly Bears"])
    giant = scenario.creature("Hill Giant")
    lure = scenario.find("Lure", Zone.BATTLEFIELD, "alice")
    lure.attach_to(giant)
    scenario.attack_with(giant)

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.no_blocks()
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))


def test_an_unattached_lure_forces_nothing():
    scenario = setup(["Hill Giant", "Lure"], ["Grizzly Bears"])
    giant = scenario.creature("Hill Giant")
    scenario.attack_with(giant)

    scenario.no_blocks()


def test_nemesis_mask_forces_the_blocks_on_the_equipped_creature_only():
    scenario = setup(["Hill Giant", "Runeclaw Bear", "Nemesis Mask"], ["Grizzly Bears"])
    giant = scenario.creature("Hill Giant")
    other = scenario.creature("Runeclaw Bear")
    mask = scenario.find("Nemesis Mask", Zone.BATTLEFIELD, "alice")
    mask.attach_to(giant)
    scenario.attack_with(giant, other)
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.block(other, bears)
    scenario.block(giant, bears)


def test_noble_quarry_is_a_lure_as_a_creature():
    scenario = setup(["Noble Quarry"], ["Grizzly Bears"])
    attack(scenario, "Noble Quarry")

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.no_blocks()


def test_noble_quarry_attached_makes_the_enchanted_creature_a_lure_too():
    scenario = setup(["Hill Giant", "Noble Quarry"], ["Grizzly Bears"])
    giant = scenario.creature("Hill Giant")
    quarry = scenario.find("Noble Quarry", Zone.BATTLEFIELD, "alice")
    quarry.attach_to(giant)
    scenario.attack_with(giant)

    with pytest.raises(ValueError, match="Grizzly Bears"):
        scenario.no_blocks()


# -- Frodo Baggins: "As long as ~ is your Ring-bearer, it must be blocked if able" ----


def test_frodo_must_be_blocked_only_while_he_is_the_ring_bearer():
    scenario = setup(["Frodo Baggins"], ["Grizzly Bears"])
    (frodo,) = attack(scenario, "Frodo Baggins")

    scenario.no_blocks()  # not the Ring-bearer: no requirement
    assert scenario.blockers() == []


def test_frodo_the_ring_bearer_must_be_blocked_if_able():
    scenario = setup(["Frodo Baggins"], ["Grizzly Bears"])
    frodo = scenario.creature("Frodo Baggins")
    player = scenario.player("alice")
    player.ring_bearer_id = frodo.id
    player.ring_bearer_stamp = frodo.zone_change_stamp
    scenario.attack_with(frodo)

    assert scenario.game.ring_bearer_of("alice") is frodo
    with pytest.raises(ValueError, match="must be blocked"):
        scenario.no_blocks()
    scenario.block(frodo, scenario.creature("Grizzly Bears", "bob"))


# -- Nacatl War-Pride: "must be blocked by exactly one creature if able" ---------------


def test_nacatl_war_pride_unblocked_is_illegal_when_a_creature_could_block_it():
    scenario = setup(["Nacatl War-Pride"], ["Grizzly Bears"])
    attack(scenario, "Nacatl War-Pride")

    with pytest.raises(ValueError, match="exactly 1 creature"):
        scenario.no_blocks()


def test_nacatl_war_pride_blocked_by_exactly_one_is_legal():
    scenario = setup(["Nacatl War-Pride"], ["Grizzly Bears", "Hill Giant"])
    (war_pride,) = attack(scenario, "Nacatl War-Pride")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.block(war_pride, bears)

    assert scenario.game.combat.attack_by(war_pride.id).blockers == [bears.id]


def test_nacatl_war_pride_blocked_by_two_is_illegal_when_one_would_do():
    scenario = setup(["Nacatl War-Pride"], ["Grizzly Bears", "Hill Giant"])
    (war_pride,) = attack(scenario, "Nacatl War-Pride")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError, match="exactly 1 creature"):
        scenario.block(war_pride, bears, giant)


def test_nacatl_war_pride_with_no_able_blocker_is_unblocked():
    scenario = setup(["Nacatl War-Pride"], ["Bloodghast"])
    attack(scenario, "Nacatl War-Pride")

    scenario.no_blocks()

    assert scenario.blockers() == []


def test_nacatl_war_pride_exactly_one_beats_the_other_blocker_staying_home_is_fine():
    scenario = setup(["Nacatl War-Pride"], ["Grizzly Bears", "Hill Giant"])
    (war_pride,) = attack(scenario, "Nacatl War-Pride")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.block(war_pride, giant)

    assert scenario.blockers() == [giant]


# -- the one-shot forms: Shinen's Channel and Glorfindel's mode ---------------------


def test_shinens_channel_makes_the_target_a_lure_for_the_turn():
    """ "All creatures able to block target creature this turn do so." - paid
    from hand ({2}{G}{G}, discard it), then the attack must be blocked by
    every creature able."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shinen of Life's Roar"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Hill Giant"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shinen = scenario.find("Shinen of Life's Roar", Zone.HAND, "alice")
    giant = scenario.creature("Hill Giant")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    activation = off_battlefield_activation(scenario.game, shinen, "alice", targets=[giant])
    payment = activation.begin_paying()
    for forest in forests:
        payment.tap_for_mana(forest, mana_from(forest))
    payment.pay()
    activation.activate()
    activation.resolve()
    assert shinen.zone is Zone.GRAVEYARD

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    bears = scenario.creature("Grizzly Bears", "bob")
    other = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError, match="able to block"):
        scenario.block(giant, bears)
    scenario.block(giant, bears, other)


def test_glorfindels_mode_grants_must_be_blocked_for_the_turn():
    """ "Glorfindel must be blocked this turn if able." - the mode's effect,
    dispatched the way a resolving trigger is, puts the requirement on its
    source; an ordinary attacker beside it carries none."""
    scenario = setup(["Glorfindel, Dauntless Rescuer"], ["Grizzly Bears"])
    glorfindel = scenario.creature("Glorfindel, Dauntless Rescuer")
    trigger = next(
        ability
        for ability in parse_abilities(card("Glorfindel, Dauntless Rescuer"))
        if isinstance(ability, TriggeredAbility)
    )
    effect = trigger_effect_for(
        glorfindel.name, trigger.event, "Glorfindel must be blocked this turn if able."
    )
    assert effect is not None
    with scenario.game._id_allocator_scope():
        effect(
            scenario.game,
            AbilityOnStack(
                kind=AbilityKind.TRIGGERED,
                ability=trigger,
                source_id=glorfindel.id,
                source_name=glorfindel.name,
                controller="alice",
                source_stamp=glorfindel.zone_change_stamp,
            ),
        )
    scenario.attack_with(glorfindel)

    with pytest.raises(ValueError, match="must be blocked"):
        scenario.no_blocks()
    scenario.block(glorfindel, scenario.creature("Grizzly Bears", "bob"))

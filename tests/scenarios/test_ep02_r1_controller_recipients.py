"""Scenario: the controller of the object a text or its trigger names, as the
recipient of a life loss or a mill.

Listed cards:

- **Revenge of Ravens** - "Whenever a creature attacks you or a planeswalker
  you control, that creature's controller loses 1 life and you gain 1 life."
- **Blood Reckoning** - the same trigger, "that creature's controller loses 1
  life."
- **Banewasp Affliction** - "When enchanted creature dies, that creature's
  controller loses life equal to its toughness."
- **Grisly Spectacle** - "Destroy target nonartifact creature. Its controller
  mills cards equal to that creature's power."
- **Phthisis** - "Destroy target creature. Its controller loses life equal to
  its power plus its toughness."

Second printings (none is a listed card or in any deck list), each with its
own wording of the same recipient:

- **Hissing Miasma** - "Whenever a creature attacks you, its controller loses
  1 life." (the "its" form)
- **Sinister Possession**, **Contaminated Bond** - "Whenever enchanted
  creature attacks or blocks, its controller loses N life." (an Aura, two
  events)
- **Carnage Gladiator** - "Whenever a creature blocks, that creature's
  controller loses 1 life." (a block event whose referent is the blocker)
- **Gloom Sower** - "Whenever this creature becomes blocked by a creature,
  that creature's controller loses 2 life and you gain 2 life."
- **Countermand** - "Counter target spell. Its controller mills four cards."
  (the target is a spell)

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 109.5** - "you"/"your" and the words that follow them refer to the
  controller of the object; "its controller" is the controller of the object
  the text just named.
- **CR 608.2c** - instructions are followed in the order written, so the
  second sentence acts on the target as the first left it.
- **CR 608.2h** - information about an object that has left is taken from
  last known information (power, toughness, controller).
- **CR 603.10a** - a dies trigger looks back in time.
- **CR 509.3a** - the block triggers.
- **CR 119.3** - life loss; **CR 701.17a** - mill; **CR 107.1b** - a negative
  amount is zero.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def settle(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def test_every_card_here_is_fully_handled():
    for name in (
        "Revenge of Ravens",
        "Blood Reckoning",
        "Banewasp Affliction",
        "Grisly Spectacle",
        "Phthisis",
        "Hissing Miasma",
        "Sinister Possession",
        "Contaminated Bond",
        "Carnage Gladiator",
        "Gloom Sower",
        "Countermand",
    ):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- attack triggers: Revenge of Ravens, Blood Reckoning, Hissing Miasma --------


def _attack_board(enchantment: str, *, third_player=False, walker=False, hand=None):
    """alice (active) attacks; bob controls `enchantment`."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"], library=["Island"] * 5)
        .player(
            "bob",
            battlefield=[enchantment, *(["Jace Beleren"] if walker else [])],
            hand=hand or [],
            library=["Island"] * 5,
        )
    )
    if third_player:
        scenario.player("carol", battlefield=["Grizzly Bears"], library=["Island"] * 5)
    built = scenario.build()
    built.start_at(Step.DECLARE_ATTACKERS)
    return built


def test_revenge_of_ravens_drains_the_attackers_controller_for_each_attacker():
    scenario = _attack_board("Revenge of Ravens")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(bears, giant)
    settle(scenario)

    assert scenario.player("alice").life == 18  # one life lost per attacking creature
    assert scenario.player("bob").life == 22


def test_revenge_of_ravens_triggers_for_an_attack_on_a_planeswalker_you_control():
    scenario = _attack_board("Revenge of Ravens", walker=True)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending=jace)
    settle(scenario)

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 21


def test_revenge_of_ravens_ignores_an_attack_on_another_player():
    scenario = _attack_board("Revenge of Ravens", third_player=True)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending="carol")
    settle(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_blood_reckoning_only_makes_the_attackers_controller_lose_life():
    scenario = _attack_board("Blood Reckoning")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears)
    settle(scenario)

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20  # no gain on this card


def test_blood_reckoning_on_a_planeswalker_attack():
    scenario = _attack_board("Blood Reckoning", walker=True)
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(giant, defending=jace)
    settle(scenario)

    assert scenario.player("alice").life == 19


def test_hissing_miasma_its_controller_loses_one_life_per_attacker():
    scenario = _attack_board("Hissing Miasma")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    scenario.attack_with(bears, giant)
    settle(scenario)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20


def test_hissing_miasma_does_not_punish_an_attack_on_someone_else():
    scenario = _attack_board("Hissing Miasma", third_player=True)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears, defending="carol")
    settle(scenario)

    assert scenario.player("alice").life == 20


# -- enchanted creature attacks or blocks: Sinister Possession, Contaminated Bond -


@pytest.mark.parametrize(("aura", "loss"), [("Sinister Possession", 2), ("Contaminated Bond", 3)])
def test_an_enchanted_creature_attacking_costs_its_controller_life(aura, loss):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", aura], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find(aura, Zone.BATTLEFIELD, "alice").attach_to(bears)

    scenario.attack_with(bears)
    settle(scenario)

    assert scenario.player("alice").life == 20 - loss
    assert scenario.player("bob").life == 20


def test_an_enchanted_creature_blocking_costs_its_controller_life():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant", "Sinister Possession"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.find("Sinister Possession", Zone.BATTLEFIELD, "bob").attach_to(giant)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))

    scenario.block(scenario.attackers()[0], giant)
    settle(scenario)

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_the_aura_controller_does_not_pay_for_an_opponents_enchanted_attacker():
    """CR 303.4e: bob's Aura on alice's creature - alice, the creature's
    controller, loses the life, not bob."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .player("bob", battlefield=["Sinister Possession"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Sinister Possession", Zone.BATTLEFIELD, "bob").attach_to(bears)

    scenario.attack_with(bears)
    settle(scenario)

    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 20


def test_an_unenchanted_creature_attacking_costs_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Hill Giant"], library=["Island"] * 5)
        .player("bob", battlefield=["Sinister Possession"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Sinister Possession", Zone.BATTLEFIELD, "bob").attach_to(bears)

    scenario.attack_with(scenario.creature("Hill Giant", "alice"))
    settle(scenario)

    assert scenario.player("alice").life == 20


# -- block triggers: Carnage Gladiator, Gloom Sower -----------------------------


def test_carnage_gladiator_the_blockers_controller_loses_life():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .player("carol", battlefield=["Carnage Gladiator"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears, defending="bob")

    scenario.block(bears, scenario.creature("Hill Giant", "bob"))
    settle(scenario)

    assert scenario.player("bob").life == 19  # the blocker's controller, not the attacker's
    assert scenario.player("alice").life == 20
    assert scenario.player("carol").life == 20


def test_gloom_sower_drains_the_controller_of_the_creature_that_blocked_it():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Gloom Sower"], library=["Island"] * 5)
        .player("bob", battlefield=["Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sower = scenario.creature("Gloom Sower", "alice")
    scenario.attack_with(sower)

    scenario.block(sower, scenario.creature("Hill Giant", "bob"))
    settle(scenario)

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


# -- Banewasp Affliction ---------------------------------------------------------


def _banewasp_board(*, creature="Craw Wurm", creature_owner="bob", aura_owner="alice"):
    boards = {"alice": [], "bob": []}
    boards[creature_owner].append(creature)
    boards[aura_owner].append("Banewasp Affliction")
    scenario = (
        Scenario()
        .player("alice", battlefield=boards["alice"], library=["Island"] * 5)
        .player("bob", battlefield=boards["bob"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    host = scenario.creature(creature, creature_owner)
    scenario.find("Banewasp Affliction", Zone.BATTLEFIELD, aura_owner).attach_to(host)
    return scenario, host


def test_banewasp_affliction_the_creatures_controller_loses_life_equal_to_its_toughness():
    scenario, wurm = _banewasp_board()

    scenario.game.destroy(wurm)
    settle(scenario)

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16  # Craw Wurm is 6/4
    assert scenario.player("alice").life == 20


def test_banewasp_affliction_reads_the_toughness_it_had_with_a_counter_on_it():
    """CR 608.2h, CR 603.10a: the +1/+1 counters are gone with the creature but
    the loss uses the toughness it had on the battlefield."""
    scenario, wurm = _banewasp_board()
    scenario.game.add_counters(wurm, "+1/+1", 2)

    scenario.game.destroy(wurm)
    settle(scenario)

    assert scenario.player("bob").life == 14  # 4 + 2


def test_banewasp_affliction_the_aura_controller_loses_when_it_is_their_own_creature():
    scenario, bears = _banewasp_board(
        creature="Grizzly Bears", creature_owner="alice", aura_owner="alice"
    )

    scenario.game.destroy(bears)
    settle(scenario)

    assert scenario.player("alice").life == 18  # Grizzly Bears has toughness 2


def test_banewasp_affliction_does_nothing_while_the_creature_lives():
    scenario, wurm = _banewasp_board()
    settle(scenario)

    assert scenario.player("bob").life == 20
    assert wurm.zone is Zone.BATTLEFIELD


# -- Grisly Spectacle ------------------------------------------------------------


def _spectacle_board(*, bob_creature="Craw Wurm", bob_library=5, hand_for="alice"):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grisly Spectacle"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Grizzly Bears"],
            library=["Island"] * 8,
        )
        .player("bob", battlefield=[bob_creature], library=["Island"] * bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_spectacle(scenario, target):
    return scenario.cast_and_resolve(
        "Grisly Spectacle",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[target],
    )


def test_grisly_spectacle_destroys_and_mills_cards_equal_to_the_power():
    scenario = _spectacle_board(bob_library=10)
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_spectacle(scenario, wurm)

    assert wurm.zone is Zone.GRAVEYARD
    assert len(scenario.player("bob").library) == 4  # Craw Wurm has power 6
    assert len(scenario.player("alice").library) == 8


def test_grisly_spectacle_reads_the_power_the_creature_had_pumped():
    scenario = _spectacle_board(bob_library=10)
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.game.add_counters(wurm, "+1/+1", 1)

    _cast_spectacle(scenario, wurm)

    assert len(scenario.player("bob").library) == 3  # 7 power


def test_grisly_spectacle_mills_what_is_there_from_a_short_library():
    scenario = _spectacle_board(bob_library=2)
    wurm = scenario.creature("Craw Wurm", "bob")

    _cast_spectacle(scenario, wurm)

    assert len(scenario.player("bob").library) == 0
    assert len(scenario.player("bob").graveyard) == 3  # the Wurm and two milled cards


def test_grisly_spectacle_on_your_own_creature_mills_you():
    scenario = _spectacle_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_spectacle(scenario, bears)

    assert len(scenario.player("alice").library) == 6  # Grizzly Bears has power 2
    assert len(scenario.player("bob").library) == 5


def test_grisly_spectacle_cannot_target_an_artifact_creature():
    scenario = _spectacle_board(bob_creature="Ornithopter")
    ornithopter = scenario.creature("Ornithopter", "bob")

    with pytest.raises(ValueError, match="artifact"):
        _cast_spectacle(scenario, ornithopter)


# -- Phthisis --------------------------------------------------------------------


def _phthisis_board(target="Craw Wurm", **bob):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Phthisis"],
            battlefield=["Swamp"] * 7 + ["Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=[target], library=["Island"] * 5, **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_phthisis_destroys_and_drains_power_plus_toughness():
    scenario = _phthisis_board()
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.cast_and_resolve(
        "Phthisis", *scenario.untapped_sources(*["Swamp"] * 7), targets=[wurm]
    )

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 10  # 6 + 4
    assert scenario.player("alice").life == 20


def test_phthisis_counts_a_pump_in_both_numbers():
    scenario = _phthisis_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.game.add_counters(wurm, "+1/+1", 3)

    scenario.cast_and_resolve(
        "Phthisis", *scenario.untapped_sources(*["Swamp"] * 7), targets=[wurm]
    )

    assert scenario.player("bob").life == 4  # 9 + 7 = 16


def test_phthisis_on_your_own_creature_costs_you_the_life():
    scenario = _phthisis_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Phthisis", *scenario.untapped_sources(*["Swamp"] * 7), targets=[bears]
    )

    assert scenario.player("alice").life == 16  # 2 + 2
    assert scenario.player("bob").life == 20


def test_phthisis_still_drains_when_the_target_is_not_destroyed():
    """Darksteel Myr is indestructible: a legal target the destroy could not
    move still has a controller and last-known characteristics, and the spell
    resolves normally (CR 608.2b)."""
    scenario = _phthisis_board("Darksteel Myr")
    myr = scenario.creature("Darksteel Myr", "bob")

    scenario.cast_and_resolve("Phthisis", *scenario.untapped_sources(*["Swamp"] * 7), targets=[myr])

    assert myr.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 19  # 0 + 1


# -- Countermand: the target is a spell -------------------------------------------


def test_countermand_counters_the_spell_and_mills_its_controller():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Forest", "Forest"],
            library=["Island"] * 5,
        )
        .player(
            "bob",
            hand=["Countermand"],
            battlefield=["Island", "Island", "Island", "Island"],
            library=["Island"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack("Grizzly Bears", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Countermand", username="bob", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 1  # four milled from five
    assert len(scenario.player("bob").library) == 8

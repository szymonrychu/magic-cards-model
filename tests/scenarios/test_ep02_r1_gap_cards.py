"""Scenario: four EP-02-R1 cards whose last clause the round's readers left open.

- **Zulaport Duelist** - "When this creature enters, up to one target creature
  gets -2/-0 until end of turn. Its controller mills two cards." The pump
  opening is followed by a sentence whose recipient is the target's controller.
- **Glacial Grasp** - "Tap target creature. Its controller mills two cards.
  That creature doesn't untap during its controller's next untap step. Draw a
  card." The tap, the mill on the target's controller, the withheld untap and
  the draw all happen, in that order.
- **Nettling Curse** - "{1}{R}: Enchanted creature attacks this turn if able."
  A requirement on the creature the Aura is attached to rather than on a
  target.
- **Shriveling Rot** - "Choose one - Until end of turn, whenever a creature is
  dealt damage, destroy it. / Until end of turn, whenever a creature dies, that
  creature's controller loses life equal to its toughness." Entwine {2}{B}.

Second printings: Crippling Chill (the tap / "doesn't untap" / draw spell
without the mill), Heckling Fiends (an attack requirement on a target),
Death Pits of Rath ("Whenever a creature is dealt damage, destroy it.") and
Mage Hunters' Onslaught ("Whenever a creature blocks this turn, its
controller loses 1 life.").

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 302.6** - a creature's activated ability with the tap or untap symbol
  can't be activated unless it has been under its controller's control
  continuously since their most recent turn began (summoning sickness); the
  untap step rules are CR 502.3.
- **CR 508.1d** - attack requirements are obeyed as far as possible.
- **CR 603.7** - a delayed triggered ability is created during a resolution
  and waits for its event; CR 603.7c a delayed trigger that refers to events
  of a specific kind triggers only once per event.
- **CR 702.42** - entwine.
- **CR 608.2c** - the instructions are followed in the order written.
- **CR 109.5** - "its controller" is the controller of the object just named.
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
        "Zulaport Duelist",
        "Glacial Grasp",
        "Nettling Curse",
        "Shriveling Rot",
        "Crippling Chill",
        "Heckling Fiends",
        "Death Pits of Rath",
        "Mage Hunters' Onslaught",
    ):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- Zulaport Duelist ---------------------------------------------------------


def _duelist_board():
    scenario = (
        Scenario()
        .player("alice", hand=["Zulaport Duelist"], battlefield=["Island"], library=["Island"] * 5)
        .player("bob", battlefield=["Craw Wurm"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_zulaport_duelist_shrinks_the_target_and_mills_its_controller():
    scenario = _duelist_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.choose_trigger_targets("Zulaport Duelist", [wurm])

    scenario.cast_and_resolve("Zulaport Duelist", *scenario.untapped_sources("Island"))
    settle(scenario)

    assert scenario.game.characteristics_of(wurm).power == 4  # 6 - 2
    assert scenario.game.characteristics_of(wurm).toughness == 4
    assert len(scenario.player("bob").library) == 3
    assert len(scenario.player("alice").library) == 5


def test_zulaport_duelist_milling_follows_the_creature_not_the_caster():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zulaport Duelist"],
            battlefield=["Island", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Zulaport Duelist", [bears])

    scenario.cast_and_resolve("Zulaport Duelist", *scenario.untapped_sources("Island"))
    settle(scenario)

    assert len(scenario.player("alice").library) == 3
    assert len(scenario.player("bob").library) == 5


def test_zulaport_duelist_with_no_target_mills_nobody():
    scenario = _duelist_board()
    scenario.choose_trigger_targets("Zulaport Duelist", [])

    scenario.cast_and_resolve("Zulaport Duelist", *scenario.untapped_sources("Island"))
    settle(scenario)

    assert len(scenario.player("bob").library) == 5
    assert len(scenario.player("alice").library) == 5


# -- Glacial Grasp / Crippling Chill ---------------------------------------------


def _grasp_board(spell="Glacial Grasp", *, bob_creature=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=[bob_creature] if bob_creature else [], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_glacial_grasp_taps_mills_withholds_the_untap_and_draws():
    scenario = _grasp_board()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Glacial Grasp", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bears]
    )

    assert bears.tapped
    assert bears.exerted
    assert len(scenario.player("alice").library) == 2  # milled two (its controller), drew one
    assert len(scenario.player("alice").graveyard) == 3  # two milled plus Glacial Grasp
    assert len(scenario.player("alice").hand) == 1
    scenario.game.untap_step()
    assert bears.tapped
    scenario.game.untap_step()
    assert not bears.tapped


def test_glacial_grasp_on_an_opposing_creature_mills_its_controller_only():
    scenario = _grasp_board(bob_creature="Hill Giant")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve(
        "Glacial Grasp", *scenario.untapped_sources("Island", "Island", "Island"), targets=[giant]
    )

    assert giant.tapped
    assert giant.exerted
    assert len(scenario.player("bob").library) == 3
    assert len(scenario.player("alice").library) == 4  # only the draw
    assert len(scenario.player("alice").hand) == 1


def test_crippling_chill_taps_withholds_the_untap_and_draws():
    scenario = _grasp_board("Crippling Chill")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Crippling Chill", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bears]
    )

    assert bears.tapped
    assert bears.exerted
    assert len(scenario.player("alice").library) == 4
    assert len(scenario.player("alice").hand) == 1


# -- Nettling Curse (Heckling Fiends' target form: test_attacks_each_combat_until_next_turn) --


def _curse_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Nettling Curse", "Mountain", "Mountain"],
            library=["Island"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Nettling Curse", Zone.BATTLEFIELD, "alice").attach_to(bears)
    return scenario, bears


def test_nettling_curse_forces_the_enchanted_creature_to_attack():
    scenario, bears = _curse_board()
    curse = scenario.find("Nettling Curse", Zone.BATTLEFIELD, "alice")

    bears.summoning_sick = False
    scenario.activate(curse, *scenario.untapped_sources("Mountain", "Mountain"))
    settle(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with()
    scenario.attack_with(bears)
    assert scenario.attackers() == [bears]


def test_nettling_curse_without_the_activation_leaves_the_attack_optional():
    scenario, bears = _curse_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()

    assert scenario.attackers() == []


# -- Shriveling Rot / Death Pits of Rath / Mage Hunters' Onslaught -------------------


def _rot_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shriveling Rot"],
            battlefield=["Swamp"] * 7 + ["Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Craw Wurm", "Hill Giant"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_rot(scenario, modes, *, entwined=False):
    from .harness import mana_from

    casting = scenario.cast("Shriveling Rot")
    casting.choose_modes(modes, entwined=entwined)
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Swamp"] * (7 if entwined else 4)):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def test_shriveling_rot_first_mode_destroys_any_creature_dealt_damage_this_turn():
    scenario = _rot_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    guide = scenario.creature("Grizzly Bears", "alice")
    _cast_rot(scenario, [1])

    scenario.game.deal_damage(wurm, 1, source=guide)
    settle(scenario)

    assert wurm.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD  # undamaged
    assert scenario.player("bob").life == 20  # the second mode was not chosen


def test_shriveling_rot_second_mode_drains_the_dead_creatures_controller_by_toughness():
    scenario = _rot_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    _cast_rot(scenario, [2])

    scenario.game.destroy(wurm)
    settle(scenario)

    assert scenario.player("bob").life == 16  # Craw Wurm's toughness is 4
    assert scenario.player("alice").life == 20


def test_shriveling_rot_second_mode_reads_your_own_creatures_too():
    scenario = _rot_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_rot(scenario, [2])

    scenario.game.destroy(bears)
    settle(scenario)

    assert scenario.player("alice").life == 18  # Grizzly Bears has toughness 2


def test_shriveling_rot_entwined_destroys_the_damaged_and_drains_for_it():
    scenario = _rot_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    guide = scenario.creature("Grizzly Bears", "alice")
    _cast_rot(scenario, [1, 2], entwined=True)

    scenario.game.deal_damage(wurm, 1, source=guide)
    settle(scenario)

    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 16


def test_shriveling_rot_ends_with_the_turn():
    scenario = _rot_board()
    wurm = scenario.creature("Craw Wurm", "bob")
    guide = scenario.creature("Grizzly Bears", "alice")
    _cast_rot(scenario, [1])
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        settle(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.deal_damage(wurm, 1, source=guide)
    settle(scenario)

    assert wurm.zone is Zone.BATTLEFIELD


def test_death_pits_of_rath_destroys_every_creature_dealt_damage():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Death Pits of Rath", "Grizzly Bears"], library=["Island"] * 5
        )
        .player("bob", battlefield=["Craw Wurm"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.deal_damage(wurm, 1, source=bears)
    settle(scenario)

    assert wurm.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_mage_hunters_onslaught_makes_each_blocker_s_controller_lose_a_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mage Hunters' Onslaught"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Hill Giant", "Craw Wurm"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_and_resolve(
        "Mage Hunters' Onslaught",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[wurm],
    )
    assert wurm.zone is Zone.GRAVEYARD
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.advance()
    scenario.block(bears, giant)
    settle(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20

"""The "would die, exile it instead" replacement (CR 614.1a), widened to the
shapes this round's cards print, plus the group -1/-1 by target player that
shares a card with it.

- Gnashing of Teeth's first mode, "Target creature gets -5/-5 until end of
  turn. If that creature would die this turn, exile it instead." - the
  targeted rider C00-T3 built for Bleed Dry (`Game.die_to_exile_this_turn`),
  now reached from a *mode* too: the mode-scoped layer composer used to read
  the pump alone and drop the rider with a notice.
- Gnashing of Teeth's second mode, "Creatures target player controls get
  -1/-1 until end of turn." - a player-targeted group pump; the set of
  creatures is fixed as it resolves (CR 611.2c). Wail of War (modal, "target
  opponent") and Neutralize the Guards (followed by Surveil 2) are the
  off-set proofs.
- Head of the Hunt's static "If a creature an opponent controls would die,
  exile it instead. When you do, create a 2/2 green Wolf creature token." -
  the static replacement Gisa already reads, with CR 603.12's reflexive
  trigger after it: it triggers only when the replacement was actually
  applied. Nemata, Primeval Warden (off-set proof, a 1/1 Saproling) prints
  the same template.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

GNASH = "Gnashing of Teeth"


def _cast_gnashing(scenario, mode, target):
    casting = scenario.cast(GNASH, username="alice")
    casting.choose_modes([mode])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def _board(scenario):
    return scenario.game.computed_board()


# -- Gnashing of Teeth, mode one: -5/-5 and the targeted die-exile rider ----


def test_mode_one_exiles_the_creature_it_kills():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_gnashing(scenario, 1, angel)

    assert angel.zone is Zone.EXILE
    assert scenario.game.layer_remainder_notices == []


def test_mode_one_rider_lasts_the_turn_for_a_creature_that_survived_the_shrink():
    """Colossal Dreadmaw (6/6) survives -5/-5 as a 1/1; the "this turn"
    replacement still waits, so when it dies later this turn it is exiled."""
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _cast_gnashing(scenario, 1, dreadmaw)
    assert dreadmaw.zone is Zone.BATTLEFIELD
    assert _board(scenario).of(dreadmaw).power_toughness == (1, 1)

    scenario.game.destroy(dreadmaw)

    assert dreadmaw.zone is Zone.EXILE


def test_mode_one_rider_ends_with_the_turn():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _cast_gnashing(scenario, 1, dreadmaw)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)
    scenario.game.destroy(dreadmaw)

    assert dreadmaw.zone is Zone.GRAVEYARD


def test_mode_one_rider_reaches_only_its_own_target():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Colossal Dreadmaw", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_gnashing(scenario, 1, dreadmaw)

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD


# -- Gnashing of Teeth, mode two: creatures target player controls ----------


def test_mode_two_shrinks_only_the_target_players_creatures():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")

    _cast_gnashing(scenario, 2, scenario.player("bob"))

    assert _board(scenario).of(theirs).power_toughness == (1, 1)
    assert _board(scenario).of(mine).power_toughness == (2, 2)
    # A 1/1 at 0 toughness is put into the graveyard (CR 704.5f) - mode two
    # carries no exile rider, so it is not exiled.
    assert elves.zone is Zone.GRAVEYARD


def test_mode_two_affected_set_is_locked_in_as_it_resolves():
    """CR 611.2c: a creature bob gets afterwards is not shrunk."""
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", hand=["Grizzly Bears"], battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_gnashing(scenario, 2, scenario.player("bob"))

    late = scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert _board(scenario).of(giant).power_toughness == (2, 2)
    assert _board(scenario).of(late).power_toughness == (2, 2)


def test_mode_two_can_target_its_own_controller():
    """ "target player", not "target opponent"."""
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")

    _cast_gnashing(scenario, 2, scenario.player("alice"))

    assert _board(scenario).of(giant).power_toughness == (2, 2)


def test_mode_two_ends_at_cleanup():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_gnashing(scenario, 2, scenario.player("bob"))

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert _board(scenario).of(giant).power_toughness == (3, 3)


def test_wail_of_war_first_mode_reads_the_target_opponent_form():
    scenario = (
        Scenario()
        .player("alice", hand=["Wail of War"], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Hill Giant", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    elves = scenario.creature("Llanowar Elves", "bob")

    casting = scenario.cast("Wail of War", username="alice")
    casting.choose_modes([1])
    casting.choose_targets([scenario.player("bob")])
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert _board(scenario).of(giant).power_toughness == (2, 2)
    assert elves.zone is Zone.GRAVEYARD


def test_neutralize_the_guards_shrinks_then_surveils():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Neutralize the Guards"],
            battlefield=["Swamp", "Swamp", "Swamp"],
            library=["Island", "Forest", "Plains"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.surveil_to_graveyard(*scenario.top_of_library(2, "alice"))

    scenario.cast_and_resolve(
        "Neutralize the Guards",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice"),
        targets=[scenario.player("bob")],
    )

    assert _board(scenario).of(giant).power_toughness == (2, 2)
    assert len(scenario.player("alice").graveyard) == 1 + 2  # the spell and two surveilled


# -- Head of the Hunt: static die-exile with a reflexive token --------------


def _wolves(scenario, username):
    return [
        card
        for card in scenario.game.battlefield
        if card.name == "Wolf Token" and card.controller == username
    ]


def test_head_of_the_hunt_exiles_a_dying_opposing_creature_and_makes_a_wolf():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Head of the Hunt"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    assert bears.zone is Zone.EXILE
    scenario.pass_until_resolved()  # the reflexive "When you do" trigger (CR 603.12)

    wolves = _wolves(scenario, "alice")
    assert len(wolves) == 1
    assert _board(scenario).of(wolves[0]).power_toughness == (2, 2)


def test_head_of_the_hunt_leaves_its_own_controllers_creatures_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Head of the Hunt", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.pending_triggers == []
    assert _wolves(scenario, "alice") == []


def test_a_creature_leaving_some_other_way_makes_no_wolf():
    """Only a death is replaced - a bounced creature is not "exiled this
    way", so the reflexive trigger never exists."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Head of the Hunt"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.return_to_hand(bears)

    assert bears.zone is Zone.HAND
    assert scenario.pending_triggers == []


def test_two_heads_exile_the_creature_once_and_make_one_wolf():
    """CR 614.5: a replacement gets one opportunity at an event; once one
    Head has exiled the creature, it no longer would die for the other."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Head of the Hunt", "Head of the Hunt"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert len(_wolves(scenario, "alice")) == 1


def test_a_creature_dying_to_state_based_actions_is_exiled_too():
    scenario = (
        Scenario()
        .player("alice", hand=[GNASH], battlefield=["Swamp", "Swamp", "Swamp", "Head of the Hunt"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "bob")

    _cast_gnashing(scenario, 2, scenario.player("bob"))
    scenario.pass_until_resolved()

    assert elves.zone is Zone.EXILE
    assert len(_wolves(scenario, "alice")) == 1


def test_nemata_reads_the_same_template_with_a_saproling():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Nemata, Primeval Warden"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    saprolings = [card for card in scenario.game.battlefield if card.name == "Saproling Token"]
    assert len(saprolings) == 1
    assert saprolings[0].controller == "alice"
    assert _board(scenario).of(saprolings[0]).power_toughness == (1, 1)

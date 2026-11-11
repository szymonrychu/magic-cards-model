"""Scenario: assimilate, CR 701.72 (trk).

CR 701.72a: assimilating a permanent gains control of it and puts a +1/+1
counter on it; it becomes a Borg artifact creature. CR 701.72b: assimilating
a card in another zone puts it onto the battlefield under your control with
a +1/+1 counter; it's a Borg artifact creature. The reminder text adds "and
loses all other creature types" (CR 205.1a: setting a subtype replaces the
set). No duration is printed (CR 611.2a), so it lasts until the object
leaves (CR 400.7). Layer 4 effects apply in timestamp order (CR 613.7), so a
later creature-type grant adds types back; a changeling's CDA applies first
(CR 613.3) and is replaced.

Proof of generality: the two trk printings word it differently - Death Is
Irrelevant targets a card in any graveyard, Borg Cube takes an untargeted
card from its own linked exile pile (CR 607.2a) with an "if you can't"
fallback. No other Modern-legal printing assimilates (Scryfall
`o:assimilate`, 2026-11-11: the only other one, Borg Queen, is not Modern
legal).

CR rules cited here were looked up with `mise run rules:find` in the writing session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.assimilate import assimilate_permanent
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.effects.amounts import creature_types_among
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _types(scenario, permanent) -> tuple[set[Type], tuple[str, ...]]:
    chars = scenario.game.characteristics_of(permanent)
    return set(chars.types), tuple(chars.subtypes)


def _end_step_assimilation(graveyard_owner: str, card: str):
    """Death Is Irrelevant on alice's battlefield, `card` in `graveyard_owner`'s
    graveyard; the end step trigger resolves targeting it."""
    players = {"alice": [], "bob": []}
    players[graveyard_owner] = [card]
    scenario = (
        Scenario()
        .player("alice", battlefield=["Death Is Irrelevant"], graveyard=players["alice"])
        .player("bob", graveyard=players["bob"])
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    target = scenario.find(card, Zone.GRAVEYARD, graveyard_owner)
    scenario.advance()  # end step
    scenario.choose_trigger_targets("Death Is Irrelevant", [target])
    scenario.pass_until_resolved()
    return scenario, target


# -- corner cases ------------------------------------------------------------


def test_assimilated_card_from_own_graveyard_is_a_borg_artifact_creature_with_a_counter() -> None:
    """CR 701.72b from your own graveyard: on the battlefield under your
    control, +1/+1 counter (a 3/3 Bears), artifact and creature, and Borg is
    its only creature type."""
    scenario, bears = _end_step_assimilation("alice", "Grizzly Bears")
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"
    assert bears.counter_count(Counter.PLUS_ONE) == 1
    types, subtypes = _types(scenario, bears)
    assert {Type.ARTIFACT, Type.CREATURE} <= types
    assert subtypes == ("Borg",)
    assert (scenario.game.power_of(bears), scenario.game.toughness_of(bears)) == (3, 3)


def test_assimilated_card_from_an_opponents_graveyard_is_yours_to_control() -> None:
    """ "From a graveyard" includes bob's: alice controls it, bob still owns it."""
    scenario, giant = _end_step_assimilation("bob", "Hill Giant")
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(giant).username == "alice"
    assert giant.owner == "bob"
    assert _types(scenario, giant)[1] == ("Borg",)


def test_an_assimilated_changeling_loses_every_other_creature_type() -> None:
    """CR 613.3: the changeling CDA applies first in layer 4, then the
    assimilation replaces the creature-type set - only Borg is left."""
    scenario, outcast = _end_step_assimilation("alice", "Changeling Outcast")
    assert _types(scenario, outcast)[1] == ("Borg",)


def test_an_assimilated_creature_is_left_out_of_the_federation_count() -> None:
    """It is a Borg now, so "non-Borg creatures" no longer sees its Bear type."""
    scenario, _bears = _end_step_assimilation("alice", "Grizzly Bears")
    assert creature_types_among(scenario.game, "alice", "Borg") == 0


def test_a_later_creature_type_grant_applies_on_top_of_the_assimilation() -> None:
    """CR 613.7: Amoeboid Changeling's "target creature gains all creature
    types" has a later timestamp, so it applies after the Borg set."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Death Is Irrelevant", "Amoeboid Changeling"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.advance()
    scenario.choose_trigger_targets("Death Is Irrelevant", [bears])
    scenario.pass_until_resolved()
    assert _types(scenario, bears)[1] == ("Borg",)
    amoeboid = scenario.creature("Amoeboid Changeling", "alice")
    amoeboid.summoning_sick = False
    scenario.activate(amoeboid, index=0, targets=[bears])
    scenario.pass_until_resolved()
    subtypes = _types(scenario, bears)[1]
    assert "Borg" in subtypes and "Bear" in subtypes and "Elf" in subtypes


def test_artifact_creatures_you_control_have_indestructible_covers_the_assimilated() -> None:
    """Death Is Irrelevant's static sees the new artifact creature."""
    scenario, bears = _end_step_assimilation("alice", "Grizzly Bears")
    assert has_keyword(bears, "indestructible", scenario.game)


def test_an_assimilated_permanent_that_leaves_and_returns_is_a_new_object() -> None:
    """CR 400.7: back in hand and played again, it is a plain Bear with no
    counter and no Borg typing."""
    scenario, bears = _end_step_assimilation("alice", "Grizzly Bears")
    scenario.game.return_to_hand(bears)
    scenario.game.put_onto_battlefield(bears, "alice")
    assert bears.counter_count(Counter.PLUS_ONE) == 0
    types, subtypes = _types(scenario, bears)
    assert Type.ARTIFACT not in types
    assert subtypes == ("Bear",)


def test_a_target_gone_before_resolution_is_not_assimilated() -> None:
    """CR 608.2b: the card left the graveyard, so the target is illegal."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Death Is Irrelevant"], graveyard=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.advance()
    scenario.choose_trigger_targets("Death Is Irrelevant", [bears])
    scenario.pass_priority()  # the trigger goes on the stack
    scenario.game.exile_cards([bears])
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE


def test_assimilating_a_permanent_takes_control_for_good() -> None:
    """CR 701.72a's battlefield form: control, a +1/+1 counter and the Borg
    typing, all with no duration - still alice's on bob's next turn."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 3)
        .player("bob", library=["Island"] * 3, battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    assert assimilate_permanent(scenario.game, "alice", giant, source_name="test")
    assert scenario.game.controller_of(giant).username == "alice"
    assert giant.counter_count(Counter.PLUS_ONE) == 1
    assert _types(scenario, giant)[1] == ("Borg",)
    scenario.start_at(Step.CLEANUP)
    scenario.advance()  # bob's turn
    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of(giant).username == "alice"
    assert _types(scenario, giant)[1] == ("Borg",)


# -- Borg Cube ------------------------------------------------------------------


def _cast_borg_cube(scenario, exile_target):
    lands = scenario.untapped_sources("Plains", "Swamp", *["Plains"] * 5)
    scenario.will_choose_targets(*([exile_target] if exile_target else []), source="Borg Cube")
    scenario.cast_onto_stack("Borg Cube", *lands)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    return scenario.find("Borg Cube", Zone.BATTLEFIELD, "alice")


def test_borg_cube_with_nothing_exiled_falls_back_to_exiling_a_creature() -> None:
    """ "If you can't": the pile is empty on entering, so up to one target
    creature is exiled - and linked to the Cube (CR 607.2a)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Borg Cube"], battlefield=["Plains"] * 6 + ["Swamp"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    cube = _cast_borg_cube(scenario, giant)
    assert giant.zone is Zone.EXILE
    assert giant in scenario.game.cards_exiled_with(cube.id, cube.zone_change_stamp)


def test_borg_cube_attacking_assimilates_the_card_it_exiled() -> None:
    """With twelve charge counters the Cube is a 6/6 artifact creature
    (CR 722.2b); its attack trigger assimilates the exiled Hill Giant under
    alice's control instead of exiling anything."""
    scenario = (
        Scenario()
        .player("alice", hand=["Borg Cube"], battlefield=["Plains"] * 6 + ["Swamp"])
        .player("bob", battlefield=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    cube = _cast_borg_cube(scenario, giant)
    scenario.game.add_counters(cube, Counter.CHARGE, 12, putter="alice")
    cube.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(bears, source="Borg Cube")
    scenario.attack_with(cube)
    scenario.pass_until_resolved()
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(giant).username == "alice"
    assert giant.counter_count(Counter.PLUS_ONE) == 1
    assert _types(scenario, giant)[1] == ("Borg",)
    assert bears.zone is Zone.BATTLEFIELD, "the fallback did not run"
    assert has_keyword(giant, "flying", scenario.game), "12+: artifact creatures have flying"


# -- one test per card ---------------------------------------------------------


def test_death_is_irrelevant_assimilates_at_end_step_and_grants_indestructible() -> None:
    """Both abilities: artifact creatures you control have indestructible, and
    at the beginning of your end step a creature card from a graveyard is
    assimilated."""
    scenario, giant = _end_step_assimilation("bob", "Hill Giant")
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(giant).username == "alice"
    assert giant.counter_count(Counter.PLUS_ONE) == 1
    assert has_keyword(giant, "indestructible", scenario.game)
    scenario.game.destroy(giant)
    assert giant.zone is Zone.BATTLEFIELD


def test_borg_cube_exiles_on_entering_then_assimilates_on_attack() -> None:
    """Borg Cube end to end: the ETB exiles bob's creature (nothing to
    assimilate yet), the attack trigger assimilates it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Borg Cube"], battlefield=["Plains"] * 6 + ["Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    cube = _cast_borg_cube(scenario, bears)
    assert bears.zone is Zone.EXILE
    scenario.game.add_counters(cube, Counter.CHARGE, 12, putter="alice")
    cube.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(source="Borg Cube")
    scenario.attack_with(cube)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"
    assert _types(scenario, bears)[1] == ("Borg",)

"""Goad (CR 701.15) and the attack requirements it creates (CR 508.1d).

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file (rules effective September 25, 2026):

- **CR 701.15a** - "Certain spells and abilities can goad a creature. Until
  the next turn of the controller of that spell or ability, that creature is
  goaded."
- **CR 701.15b** - "Goaded is a designation a permanent can have. A goaded
  creature attacks each combat if able and attacks a player other than the
  controller of the permanent, spell, or ability that caused it to be goaded
  if able. Goaded is neither an ability nor part of the permanent's copiable
  values."
- **CR 701.15c** - "A creature can be goaded by multiple players. Doing so
  creates additional combat requirements."
- **CR 701.15d** - "Once a player has goaded a creature, the same player
  goading it again has no effect. Doing so doesn't create additional combat
  requirements."
- **CR 508.1d** - "If the number of requirements that are being obeyed is
  fewer than the maximum possible number of requirements that could be
  obeyed without disobeying any restrictions, the declaration of attackers is
  illegal."

The proof card is Glóin, Dwarf Emissary (Modern-legal; in neither deck pool):
"Whenever you cast a historic spell, create a Treasure token. This ability
triggers only once each turn." and "{T}, Sacrifice a Treasure: Goad target
creature." The other printed goad subjects are proven on real off-format
printings, each a different wording and a different ability kind:

- Disrupt Decorum (a spell): "Goad all creatures you don't control."
- Geode Rager (a trigger): "goad each creature target player controls."
- Oceanus Dragon (a trigger): "tap target creature an opponent controls. Goad it."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines import combat as combat_rules
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario

GLOIN = "Glóin, Dwarf Emissary"
LIBRARY = ["Mountain"] * 8


def _resolve_everything(scenario) -> None:
    game = scenario.game
    game.put_triggers_on_stack()
    while game.stack:
        scenario.pass_until_resolved()
        game.put_triggers_on_stack()


def _treasures(scenario, username: str = "alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name == "Treasure Token"
    ]


def _advance_until(scenario, predicate) -> None:
    for _ in range(200):
        if predicate(scenario):
            return
        scenario.advance()
    raise AssertionError("never reached the wanted step")


def _at(active: str, step: Step):
    return lambda s: s.turn.active_player == active and s.step is step


def _board(*extra_players: str, alice: list[str] | None = None, bob: list[str] | None = None):
    scenario = Scenario().player(
        "alice",
        battlefield=[GLOIN, *(alice or [])],
        hand=["Ornithopter", "Ornithopter"],
        library=list(LIBRARY),
    )
    scenario = scenario.player("bob", battlefield=bob or ["Grizzly Bears"], library=list(LIBRARY))
    for name in extra_players:
        scenario = scenario.player(name, battlefield=["Hill Giant"], library=list(LIBRARY))
    return scenario.build()


def _make_treasure(scenario) -> None:
    scenario.cast_onto_stack("Ornithopter")
    _resolve_everything(scenario)


def _goad_with_gloin(scenario, target) -> None:
    gloin = scenario.creature(GLOIN, "alice")
    (treasure,) = _treasures(scenario)[:1]
    scenario.activate(gloin, index=0, username="alice", sacrificing=[treasure], targets=[target])
    _resolve_everything(scenario)


def _goaded_bears():
    """Alice goads bob's Grizzly Bears in her first main phase."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_treasure(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    _goad_with_gloin(scenario, bears)
    return scenario, bears


def _to_bobs_declare_attackers(scenario) -> None:
    _advance_until(scenario, _at("bob", Step.BEGINNING_OF_COMBAT))
    scenario.start_at(Step.DECLARE_ATTACKERS)


# --------------------------------------------------------------------------
# Glóin's own Treasure trigger
# --------------------------------------------------------------------------


def test_gloin_makes_a_treasure_for_a_historic_spell_only_once_each_turn():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _make_treasure(scenario)
    assert len(_treasures(scenario)) == 1

    _make_treasure(scenario)
    assert len(_treasures(scenario)) == 1, "the trigger triggers only once each turn"


# --------------------------------------------------------------------------
# The designation (CR 701.15a, 701.15d)
# --------------------------------------------------------------------------


def test_gloin_goads_the_target_for_its_controller():
    scenario, bears = _goaded_bears()

    assert bears.goaded_by == ["alice"]
    assert _treasures(scenario) == [], "the Treasure was sacrificed to pay the cost"
    assert scenario.creature(GLOIN, "alice").tapped


def test_the_same_player_goading_again_adds_nothing():
    """CR 701.15d: Oceanus Dragon's "Goad it." after Glóin's goad, both
    alice's, is still one goader and one set of requirements."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[GLOIN],
            hand=["Ornithopter", "Oceanus Dragon"],
            library=list(LIBRARY),
        )
        .player("bob", battlefield=["Grizzly Bears"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_treasure(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    _goad_with_gloin(scenario, bears)
    alice = TargetRef.coerce("alice")
    before = combat_rules.attack_requirements_obeyed(scenario.game, bears, alice)
    assert before == 1

    scenario.will_choose_targets(bears, source="Oceanus Dragon")
    scenario.put_onto_battlefield("Oceanus Dragon", "alice")
    _resolve_everything(scenario)

    assert bears.goaded_by == ["alice"]
    assert combat_rules.attack_requirements_obeyed(scenario.game, bears, alice) == before


def test_leaving_the_battlefield_ends_the_goad():
    scenario, bears = _goaded_bears()

    scenario.game.return_to_hand(bears)

    assert bears.goaded_by == []


# --------------------------------------------------------------------------
# The requirement on the goaded creature's controller's turn (CR 508.1d)
# --------------------------------------------------------------------------


def test_on_the_opponents_turn_a_declaration_without_the_goaded_creature_is_refused():
    scenario, bears = _goaded_bears()
    _to_bobs_declare_attackers(scenario)

    with pytest.raises(ValueError, match=r"CR 508\.1d") as refused:
        scenario.attack_with()

    message = str(refused.value)
    assert "Grizzly Bears" in message
    assert "goad" in message.lower()
    assert "CR 701.15b" in message
    assert scenario.attackers() == []


def test_in_two_player_attacking_the_goader_is_legal_and_required():
    """No player other than alice exists, so the "other than the goader"
    requirement cannot be obeyed; attacking alice obeys the "attacks each
    combat" one, which is the most that can be obeyed."""
    scenario, bears = _goaded_bears()
    _to_bobs_declare_attackers(scenario)

    scenario.attack_with(bears, defending="alice")

    assert scenario.attackers() == [bears]


def test_the_unscripted_seat_attacks_with_the_goaded_creature():
    scenario, bears = _goaded_bears()
    _to_bobs_declare_attackers(scenario)

    scenario.game.declare_attackers_step()

    assert scenario.attackers() == [bears]


def test_a_scripted_empty_declaration_is_refused_at_the_step():
    scenario, _bears = _goaded_bears()
    _to_bobs_declare_attackers(scenario)
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.DECLARE_ATTACKERS, value=(), player="bob")
    )

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.game.declare_attackers_step()


def test_a_tapped_goaded_creature_is_not_required_to_attack():
    scenario, bears = _goaded_bears()
    _to_bobs_declare_attackers(scenario)
    bears.tap()

    scenario.attack_with()

    assert scenario.attackers() == []


def test_a_summoning_sick_goaded_creature_is_not_required_to_attack():
    scenario = Scenario()
    scenario = scenario.player(
        "alice", battlefield=[GLOIN], hand=["Ornithopter"], library=list(LIBRARY)
    )
    scenario = scenario.player("bob", hand=["Grizzly Bears"], library=list(LIBRARY)).build()
    _advance_until(scenario, _at("bob", Step.PRECOMBAT_MAIN))
    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    scenario.game.goad(bears, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with()

    assert scenario.attackers() == []


def test_a_restriction_still_wins_over_goad():
    """CR 508.1d counts only requirements obeyable "without disobeying any
    restrictions": a goaded creature with defender cannot attack at all."""
    scenario = _board(bob=["Wall of Omens"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_treasure(scenario)
    wall = scenario.creature("Wall of Omens", "bob")
    _goad_with_gloin(scenario, wall)
    assert wall.goaded_by == ["alice"]
    _to_bobs_declare_attackers(scenario)

    scenario.attack_with()

    assert scenario.attackers() == []


# --------------------------------------------------------------------------
# Duration (CR 701.15a): until the goader's next turn
# --------------------------------------------------------------------------


def test_the_goad_survives_the_goaders_own_cleanup_and_the_opponents_turn():
    scenario, bears = _goaded_bears()

    _advance_until(scenario, _at("alice", Step.CLEANUP))
    assert bears.goaded_by == ["alice"]
    _advance_until(scenario, _at("bob", Step.CLEANUP))
    assert bears.goaded_by == ["alice"]


def test_the_goad_ends_as_the_goaders_next_turn_begins():
    scenario, bears = _goaded_bears()

    _advance_until(scenario, _at("bob", Step.CLEANUP))
    _advance_until(scenario, _at("alice", Step.UPKEEP))

    assert bears.goaded_by == []
    assert combat_rules.attack_requirement_holders(scenario.game, "bob") == []


# --------------------------------------------------------------------------
# More than two players: "a player other than [the goader]" and CR 701.15c
# --------------------------------------------------------------------------


def _three_player_goad():
    scenario = _board("carol")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_treasure(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    _goad_with_gloin(scenario, bears)
    return scenario, bears


def test_with_another_player_attacking_the_goader_is_refused():
    scenario, bears = _three_player_goad()
    _to_bobs_declare_attackers(scenario)

    with pytest.raises(ValueError, match=r"CR 508\.1d") as refused:
        scenario.attack_with(bears, defending="alice")

    assert "other than alice" in str(refused.value)
    assert scenario.attackers() == []


def test_with_another_player_attacking_them_obeys_both_requirements():
    scenario, bears = _three_player_goad()
    _to_bobs_declare_attackers(scenario)

    scenario.attack_with(bears, defending="carol")

    assert scenario.attackers() == [bears]


def test_the_unscripted_seat_attacks_a_player_other_than_the_goader():
    scenario, bears = _three_player_goad()
    _to_bobs_declare_attackers(scenario)

    scenario.game.declare_attackers_step()

    (attack,) = scenario.game.combat.attacks
    assert attack.defender.username == "carol"


def test_two_goaders_each_add_their_own_requirements():
    """CR 701.15c: goaded by alice and by carol, the Bears obey three
    requirements attacking either (twice "attacks each combat", once "a
    player other than" the goader it is not attacking), so either is legal."""
    scenario, bears = _three_player_goad()
    scenario.game.goad(bears, "carol")
    assert bears.goaded_by == ["alice", "carol"]
    _to_bobs_declare_attackers(scenario)
    game = scenario.game

    assert combat_rules.attack_requirements_obeyed(game, bears, TargetRef.coerce("alice")) == 3
    assert combat_rules.attack_requirements_obeyed(game, bears, TargetRef.coerce("carol")) == 3
    assert combat_rules.attack_requirements_obeyed(game, bears, None) == 0

    scenario.attack_with(bears, defending="alice")
    assert scenario.attackers() == [bears]


def test_each_goaders_goad_ends_on_its_own_goaders_turn():
    scenario, bears = _three_player_goad()
    scenario.game.goad(bears, "carol")

    _advance_until(scenario, _at("carol", Step.UPKEEP))

    assert bears.goaded_by == ["alice"]


# --------------------------------------------------------------------------
# The other printed goad subjects (spell, trigger, anaphor, per opponent)
# --------------------------------------------------------------------------


def test_disrupt_decorum_goads_every_creature_its_caster_does_not_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Disrupt Decorum"],
            battlefield=["Mountain"] * 4 + ["Juggernaut"],
            library=list(LIBRARY),
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Disrupt Decorum", *scenario.untapped_sources(*["Mountain"] * 4))

    assert scenario.creature("Grizzly Bears", "bob").goaded_by == ["alice"]
    assert scenario.creature("Hill Giant", "bob").goaded_by == ["alice"]
    assert scenario.creature("Juggernaut", "alice").goaded_by == []


def test_geode_rager_goads_each_creature_the_target_player_controls():
    scenario = (
        Scenario()
        .player("alice", hand=["Mountain"], battlefield=["Geode Rager"], library=list(LIBRARY))
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", source="Geode Rager")

    scenario.play_land("Mountain")
    _resolve_everything(scenario)

    assert scenario.creature("Grizzly Bears", "bob").goaded_by == ["alice"]
    assert scenario.creature("Hill Giant", "bob").goaded_by == ["alice"]
    assert scenario.creature("Geode Rager", "alice").goaded_by == []


def test_oceanus_dragon_taps_its_target_and_goads_it():
    scenario = (
        Scenario()
        .player("alice", hand=["Oceanus Dragon"], library=list(LIBRARY))
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, source="Oceanus Dragon")

    scenario.put_onto_battlefield("Oceanus Dragon", "alice")
    _resolve_everything(scenario)

    assert bears.tapped
    assert bears.goaded_by == ["alice"]
    assert scenario.creature("Hill Giant", "bob").goaded_by == []

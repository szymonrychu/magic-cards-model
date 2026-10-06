"""Damage spells whose second instruction restricts or requires something of a
group, or of exactly the objects and players the damage reached.

Listed cards (NW-01, task T5):

- **Aggravate** - "Each creature dealt damage this way attacks this turn if
  able." (CR 508.1d requirement on exactly the creatures actually dealt
  damage, CR 120.3).
- **Aurelia's Fury** - X damage divided (CR 601.2d), then "Tap each creature
  dealt damage this way. Players dealt damage this way can't cast noncreature
  spells this turn."
- **Barrage of Boulders**, **Cosmotronic Wave**, **Ember Gale**, **Concussive
  Bolt** - "creatures [of some group] can't block this turn" (CR 509.1b), the
  first and last behind an ability word (CR 207.2c) and an "if" condition.
- **Chandra's Revolution** - "Tap target land. That land doesn't untap during
  its controller's next untap step." (CR 502.3).

Second printings proving the same readers: **Ballista Wielder**'s ability
("A creature dealt damage this way can't block this turn."), **Hazardous
Blast** (the opponents' group), **Stensia Innkeeper** ("That land doesn't
untap ...").

The "can't block" group is a restriction on the rules of combat, not a change
to any object's characteristics or controller, so CR 611.2c does not fix the
set: a creature that arrives later in the turn is restricted too.

Rules read with `mise run rules:find` in the session that wrote this file:
CR 120.3, CR 207.2c, CR 502.3, CR 508.1d, CR 509.1b, CR 601.2d, CR 608.2b,
CR 611.2c, CR 701.26a.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _cant_block(scenario, state) -> bool:
    board = scenario.game.continuous_effects.board(scenario.game.battlefield)
    return "This creature can't block." in board.of(state).abilities


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _advance_until(scenario, predicate) -> None:
    while not predicate(scenario):
        scenario.advance()
        _resolve_stack(scenario)


def _to_bobs_attack(scenario) -> None:
    _advance_until(
        scenario,
        lambda s: s.turn.active_player == "bob" and s.step is Step.BEGINNING_OF_COMBAT,
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)


def _board(alice_hand, alice_battlefield, bob_battlefield, *, bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Mountain"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Aggravate: each creature dealt damage this way attacks this turn ---------


def _aggravate_on_bobs_turn(bob_battlefield, bob_hand=()):
    scenario = _board(["Aggravate"], ["Mountain"] * 5, bob_battlefield, bob_hand=bob_hand)
    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN
    )
    scenario.pass_priority("bob")
    scenario.cast_and_resolve("Aggravate", username="alice", auto=True, targets=["bob"])
    return scenario


def test_aggravate_damages_each_creature_and_makes_it_attack():
    scenario = _aggravate_on_bobs_turn(["Hill Giant", "Runeclaw Bear"])
    giant = scenario.creature("Hill Giant", "bob")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    assert (giant.damage, runeclaw.damage) == (1, 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(giant)

    scenario.attack_with(giant, runeclaw, defending="alice")
    assert scenario.attackers() == [giant, runeclaw]


def test_aggravate_binds_no_creature_its_damage_never_reached():
    """Protection from red prevents the damage (CR 120.3: none was dealt), so
    Paladin en-Vec was not "dealt damage this way" and may stay home."""
    scenario = _aggravate_on_bobs_turn(["Hill Giant", "Paladin en-Vec"])
    giant = scenario.creature("Hill Giant", "bob")
    paladin = scenario.creature("Paladin en-Vec", "bob")
    assert paladin.damage == 0
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(giant, defending="alice")

    assert scenario.attackers() == [giant]


def test_aggravate_binds_no_creature_that_arrives_later():
    scenario = _aggravate_on_bobs_turn(["Hill Giant"], bob_hand=["Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "bob")
    late = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    late.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(giant, defending="alice")

    assert scenario.attackers() == [giant]


def test_aggravate_requirement_ends_with_the_turn():
    scenario = _board(["Aggravate"], ["Mountain"] * 5, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Aggravate", auto=True, targets=["bob"])
    assert giant.damage == 1
    _to_bobs_attack(scenario)

    scenario.attack_with()

    assert scenario.attackers() == []


# -- Aurelia's Fury: tap the creatures, silence the players --------------------


def _fury(x, targets, division, bob_hand=("Shock", "Ambush Viper")):
    scenario = _board(
        ["Aurelia's Fury", "Shock"],
        ["Mountain"] * (x + 2) + ["Plains"],
        ["Grizzly Bears", "Hill Giant", "Mountain", "Forest", "Forest"],
        bob_hand=bob_hand,
    )
    resolved = [scenario.creature(t, "bob") if t != "bob" else "bob" for t in targets]
    scenario.game.cast(
        scenario.find("Aurelia's Fury", Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=resolved,
        division=division,
        mana_sources=scenario.untapped_sources(*["Mountain"] * (x + 1), "Plains"),
    )
    scenario.pass_until_resolved()
    return scenario


def test_aurelias_fury_taps_each_creature_dealt_damage():
    scenario = _fury(3, ["Grizzly Bears", "bob"], [1, 2])
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    assert bears.damage == 1 and bears.tapped
    assert not giant.tapped
    assert scenario.player("bob").life == 18


def test_aurelias_fury_player_dealt_damage_cannot_cast_noncreature_spells():
    scenario = _fury(3, ["Grizzly Bears", "bob"], [1, 2])
    scenario.pass_priority("alice")

    with pytest.raises(ValueError):
        scenario.game.cast(
            scenario.find("Shock", Zone.HAND, "bob"),
            "bob",
            targets=["alice"],
            mana_sources=scenario.untapped_sources("Mountain", username="bob"),
        )
    scenario.game.cast(
        scenario.find("Ambush Viper", Zone.HAND, "bob"),
        "bob",
        mana_sources=scenario.untapped_sources("Forest", "Forest", username="bob"),
    )
    assert scenario.stack_names() == ["Ambush Viper"]


def test_aurelias_fury_leaves_a_player_it_did_not_damage_free_to_cast():
    scenario = _fury(2, ["Grizzly Bears", "Hill Giant"], [1, 1])
    assert scenario.player("bob").life == 20
    scenario.pass_priority("alice")

    scenario.game.cast(
        scenario.find("Shock", Zone.HAND, "bob"),
        "bob",
        targets=["alice"],
        mana_sources=scenario.untapped_sources("Mountain", username="bob"),
    )

    assert scenario.stack_names() == ["Shock"]


def test_aurelias_fury_does_not_silence_its_own_caster():
    scenario = _fury(3, ["Grizzly Bears", "bob"], [1, 2])

    scenario.game.cast(
        scenario.find("Shock", Zone.HAND, "alice"),
        "alice",
        targets=["bob"],
        mana_sources=scenario.untapped_sources("Mountain", username="alice"),
    )

    assert scenario.stack_names() == ["Shock"]


def test_aurelias_fury_restriction_ends_with_the_turn():
    scenario = _fury(3, ["Grizzly Bears", "bob"], [1, 2])
    _advance_until(
        scenario, lambda s: s.turn.active_player == "bob" and s.step is Step.PRECOMBAT_MAIN
    )

    scenario.game.cast(
        scenario.find("Shock", Zone.HAND, "bob"),
        "bob",
        targets=["alice"],
        mana_sources=scenario.untapped_sources("Mountain", username="bob"),
    )

    assert scenario.stack_names() == ["Shock"]


# -- Ballista Wielder: the same "dealt damage this way" reader ----------------


def _wielder(bob_battlefield):
    scenario = _board(
        [], ["Ballista Watcher", "Colossal Dreadmaw"] + ["Mountain"] * 3, bob_battlefield
    )
    wielder = scenario.find("Ballista Watcher", Zone.BATTLEFIELD, "alice")
    wielder.transform(day_night=True)
    assert wielder.name == "Ballista Wielder"
    return scenario, wielder


def test_ballista_wielder_creature_dealt_damage_this_way_cannot_block():
    scenario, wielder = _wielder(["Hill Giant", "Watchwolf"])
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.activate(
        wielder, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=[giant]
    )
    scenario.pass_until_resolved()

    assert giant.damage == 1
    assert _cant_block(scenario, giant)
    assert not _cant_block(scenario, wolf)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    dreadmaw.summoning_sick = False
    scenario.attack_with(dreadmaw)
    with pytest.raises(ValueError, match=r"can't block"):
        scenario.block(dreadmaw, giant)
    scenario.block(dreadmaw, wolf)
    assert scenario.blockers() == [wolf]


def test_ballista_wielder_at_a_player_restricts_no_creature():
    scenario, wielder = _wielder(["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(
        wielder, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert not _cant_block(scenario, giant)


def _huatli(bob_battlefield):
    scenario = _board([], ["Huatli, Warrior Poet", "Colossal Dreadmaw"], bob_battlefield)
    huatli = scenario.find("Huatli, Warrior Poet", Zone.BATTLEFIELD, "alice")
    return scenario, huatli


def test_huatli_minus_x_divided_damage_stops_exactly_the_damaged_creatures_blocking():
    """CR 107.3a/606.4: "-X" is announced on activation; CR 601.2d divides
    it. Only the creatures actually dealt damage this way can't block."""
    scenario, huatli = _huatli(["Hill Giant", "Watchwolf", "Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(huatli, index=2, x_value=2, targets=[giant, wolf], division=[1, 1])
    scenario.pass_until_resolved()

    assert huatli.counters[Counter.LOYALTY] == 1
    assert giant.damage == 1 and wolf.damage == 1
    assert _cant_block(scenario, giant)
    assert _cant_block(scenario, wolf)
    assert not _cant_block(scenario, bears)


def test_huatli_creature_killed_by_the_damage_leaves_nothing_restricted():
    scenario, huatli = _huatli(["Grizzly Bears", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(huatli, index=2, x_value=2, targets=[bears], division=[2])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert not _cant_block(scenario, giant)


# -- Group "can't block this turn" ---------------------------------------------


def _attack_and_try_to_block(scenario, attacker_name, blocker):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature(attacker_name, "alice")
    attacker.summoning_sick = False
    scenario.attack_with(attacker)
    scenario.block(attacker, blocker)


def test_cosmotronic_wave_damages_and_stops_opponents_creatures_blocking():
    scenario = _board(
        ["Cosmotronic Wave"], ["Mountain"] * 4 + ["Grizzly Bears"], ["Hill Giant", "Memnite"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    memnite = scenario.creature("Memnite", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Cosmotronic Wave", auto=True)

    assert giant.damage == 1 and memnite.zone is Zone.GRAVEYARD
    assert bears.damage == 0
    assert _cant_block(scenario, giant)
    assert not _cant_block(scenario, bears)
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", giant)


def test_cosmotronic_wave_reaches_a_creature_that_arrives_later_this_turn():
    """CR 611.2c: the restriction changes no characteristics, so the set of
    creatures it covers is not fixed when it begins."""
    scenario = _board(
        ["Cosmotronic Wave"], ["Mountain"] * 4 + ["Grizzly Bears"], [], bob_hand=["Hill Giant"]
    )
    scenario.cast_and_resolve("Cosmotronic Wave", auto=True)
    late = scenario.put_onto_battlefield("Hill Giant", "bob")

    assert _cant_block(scenario, late)
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", late)


def test_cosmotronic_wave_restriction_ends_with_the_turn():
    scenario = _board(["Cosmotronic Wave"], ["Mountain"] * 4, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Cosmotronic Wave", auto=True)
    _advance_until(scenario, lambda s: s.turn.active_player == "bob")

    assert not _cant_block(scenario, giant)


def test_hazardous_blast_is_the_same_group_restriction():
    scenario = _board(
        ["Hazardous Blast"], ["Mountain"] * 4 + ["Grizzly Bears"], ["Hill Giant", "Watchwolf"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.cast_and_resolve("Hazardous Blast", auto=True)

    assert (giant.damage, wolf.damage) == (1, 1)
    assert _cant_block(scenario, giant) and _cant_block(scenario, wolf)
    assert not _cant_block(scenario, scenario.creature("Grizzly Bears", "alice"))
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", wolf)


def test_barrage_of_boulders_with_ferocious_stops_every_creature_blocking():
    scenario = _board(
        ["Barrage of Boulders"],
        ["Mountain"] * 3 + ["Colossal Dreadmaw", "Grizzly Bears"],
        ["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")

    scenario.cast_and_resolve("Barrage of Boulders", auto=True)

    assert giant.damage == 1
    assert dreadmaw.damage == 0
    assert _cant_block(scenario, giant) and _cant_block(scenario, dreadmaw)
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", giant)


def test_barrage_of_boulders_without_ferocious_only_deals_damage():
    scenario = _board(
        ["Barrage of Boulders"], ["Mountain"] * 3 + ["Grizzly Bears"], ["Colossal Dreadmaw"]
    )
    their_dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Barrage of Boulders", auto=True)

    assert their_dreadmaw.damage == 1
    assert not _cant_block(scenario, their_dreadmaw)
    _attack_and_try_to_block(scenario, "Grizzly Bears", their_dreadmaw)
    assert scenario.blockers() == [their_dreadmaw]


def test_ember_gale_stops_target_players_creatures_and_burns_white_and_blue():
    scenario = _board(
        ["Ember Gale"],
        ["Mountain"] * 4 + ["Serra Angel", "Grizzly Bears"],
        ["Serra Angel", "Watchwolf", "Hill Giant"],
    )
    their_angel = scenario.creature("Serra Angel", "bob")
    wolf = scenario.creature("Watchwolf", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    my_angel = scenario.creature("Serra Angel", "alice")

    scenario.cast_and_resolve("Ember Gale", auto=True, targets=["bob"])

    assert (their_angel.damage, wolf.damage, giant.damage) == (1, 1, 0)
    assert my_angel.damage == 0
    assert all(_cant_block(scenario, c) for c in (their_angel, wolf, giant))
    assert not _cant_block(scenario, my_angel)
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", giant)


def test_ember_gale_aimed_at_its_caster_restricts_the_caster():
    scenario = _board(
        ["Ember Gale"], ["Mountain"] * 4 + ["Serra Angel"], ["Hill Giant", "Serra Angel"]
    )
    my_angel = scenario.creature("Serra Angel", "alice")
    their_angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve("Ember Gale", auto=True, targets=["alice"])

    assert my_angel.damage == 1 and their_angel.damage == 0
    assert _cant_block(scenario, my_angel)
    assert not _cant_block(scenario, their_angel)


def _bolt_board(artifacts, bob_battlefield):
    return _board(
        ["Concussive Bolt"],
        ["Mountain"] * 5 + ["Grizzly Bears"] + ["Ornithopter"] * artifacts,
        bob_battlefield,
    )


def test_concussive_bolt_with_metalcraft_stops_that_players_creatures():
    scenario = _bolt_board(3, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Concussive Bolt", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 16
    assert _cant_block(scenario, giant)
    assert not any(
        _cant_block(scenario, c)
        for c in scenario.game.permanents_controlled_by("alice")
        if scenario.game.characteristics_of(c).is_creature
    )
    with pytest.raises(ValueError, match=r"can't block"):
        _attack_and_try_to_block(scenario, "Grizzly Bears", giant)


def test_concussive_bolt_at_a_planeswalker_stops_its_controllers_creatures():
    scenario = _bolt_board(3, ["Hill Giant", "Jace Beleren"])
    giant = scenario.creature("Hill Giant", "bob")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(jace, Counter.LOYALTY, 6)
    loyalty = jace.counters[Counter.LOYALTY]

    scenario.cast_and_resolve("Concussive Bolt", auto=True, targets=[jace])

    assert jace.counters[Counter.LOYALTY] == loyalty - 4
    assert scenario.player("bob").life == 20
    assert _cant_block(scenario, giant)


def test_concussive_bolt_without_metalcraft_only_deals_damage():
    scenario = _bolt_board(2, ["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Concussive Bolt", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 16
    assert not _cant_block(scenario, giant)


# -- Chandra's Revolution / Stensia Innkeeper: that land doesn't untap ---------


def _to_untap_of(scenario, player, *, turns=1):
    for _ in range(turns):
        _advance_until(scenario, lambda s: s.turn.active_player != player)
        _advance_until(
            scenario, lambda s: s.turn.active_player == player and s.step is Step.PRECOMBAT_MAIN
        )


def test_chandras_revolution_damages_taps_and_holds_the_land():
    scenario = _board(["Chandra's Revolution"], ["Mountain"] * 4, ["Hill Giant", "Forest"])
    giant = scenario.creature("Hill Giant", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Chandra's Revolution", auto=True, targets=[giant, forest])

    assert giant.zone is Zone.GRAVEYARD
    assert forest.tapped
    _to_untap_of(scenario, "bob")
    assert forest.tapped
    _to_untap_of(scenario, "bob")
    assert not forest.tapped


def test_chandras_revolution_still_taps_the_land_if_the_creature_is_gone():
    """CR 608.2b: one illegal target does not stop the instructions that
    name a target still legal."""
    scenario = _board(["Chandra's Revolution"], ["Mountain"] * 4, ["Hill Giant", "Forest"])
    giant = scenario.creature("Hill Giant", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    scenario.cast_onto_stack("Chandra's Revolution", auto=True, targets=[giant, forest])
    scenario.game.sacrifice(giant)

    scenario.pass_until_resolved()

    assert forest.tapped
    _to_untap_of(scenario, "bob")
    assert forest.tapped


def test_stensia_innkeeper_holds_the_land_it_tapped():
    scenario = _board(["Stensia Innkeeper"], ["Mountain"] * 5, ["Forest"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    innkeeper = scenario.find("Stensia Innkeeper", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(innkeeper, "alice")
    scenario.choose_trigger_targets("Stensia Innkeeper", [forest])
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)

    assert forest.tapped
    _to_untap_of(scenario, "bob")
    assert forest.tapped
    _to_untap_of(scenario, "bob")
    assert not forest.tapped


def test_chandras_revolution_taps_only_the_land_it_targeted():
    """CR 601.2c: each target was chosen for its own phrase - the creature
    that survives the damage is neither tapped nor held."""
    scenario = _board(["Chandra's Revolution"], ["Mountain"] * 4, ["Colossal Dreadmaw", "Forest"])
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Chandra's Revolution", auto=True, targets=[dreadmaw, forest])

    assert dreadmaw.damage == 4
    assert not dreadmaw.tapped and not dreadmaw.exerted
    assert forest.tapped and forest.exerted


def test_aggravate_names_the_player_but_does_not_damage_them():
    scenario = _board(["Aggravate"], ["Mountain"] * 5, ["Hill Giant"])

    scenario.cast_and_resolve("Aggravate", auto=True, targets=["bob"])

    assert scenario.player("bob").life == 20
    assert scenario.creature("Hill Giant", "bob").damage == 1

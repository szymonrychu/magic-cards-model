"""Removal that first takes indestructible away, and creature pumps whose size
is read as the spell resolves - doubled, or counted.

Listed cards (NW-01, task T5):

- **Rebel Salvo** - "deals 5 damage to target creature or planeswalker. That
  permanent loses indestructible until end of turn." (CR 613.1f layer 6
  removal, CR 702.12b).
- **Hour of Devastation** - "All creatures lose indestructible until end of
  turn. Hour of Devastation deals 5 damage to each creature and each
  non-Bolas planeswalker." (the removal first, CR 608.2c; "non-Bolas" a
  planeswalker-type exclusion, CR 205.3j).
- **Dragonclaw Strike** - "Double the power and toughness of target creature
  you control until end of turn. Then it fights up to one target creature an
  opponent controls." (CR 701.10a/b, CR 701.14a, CR 115.6's "up to one").
- **Fists of Flame** - "Draw a card. Until end of turn, target creature gains
  trample and gets +1/+0 for each card you've drawn this turn." (the count
  taken as it resolves, after the draw, CR 608.2h).

Second printings proving the same readers: **Soul Sear** and **Smite the
Deathless** (the lost-indestructible rider), **Battle of Frost and Fire**
("each non-Giant creature and each planeswalker"), **Chelonian Tackle**
(the "then it fights" pair read whole), **Get a Leg Up** ("gets +1/+1 for
each creature you control and gains reach").

Rules read with `mise run rules:find` in the session that wrote this file:
CR 115.6, CR 205.3j, CR 608.2b, CR 608.2c, CR 608.2h, CR 611.2c, CR 613.1f,
CR 701.10a, CR 701.10b, CR 701.14a, CR 701.14b, CR 702.12b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(alice_hand, alice_battlefield, bob_battlefield, *, alice_library=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=list(alice_library or ["Mountain"] * 10),
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _to_next_turn(scenario) -> None:
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()


# -- Rebel Salvo / Soul Sear / Smite the Deathless ------------------------------


def test_rebel_salvo_kills_an_indestructible_creature():
    scenario = _board(["Rebel Salvo"], ["Mountain"] * 3, ["Darksteel Gargoyle"])
    gargoyle = scenario.creature("Darksteel Gargoyle", "bob")
    assert is_indestructible(gargoyle, scenario.game)

    scenario.cast_and_resolve("Rebel Salvo", auto=True, targets=[gargoyle])

    assert gargoyle.zone is Zone.GRAVEYARD


def test_rebel_salvo_at_a_planeswalker_removes_loyalty():
    scenario = _board(["Rebel Salvo"], ["Mountain"] * 3, ["Jace Beleren"])
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(jace, Counter.LOYALTY, 6)
    before = jace.counters[Counter.LOYALTY]

    scenario.cast_and_resolve("Rebel Salvo", auto=True, targets=[jace])

    assert jace.counters[Counter.LOYALTY] == before - 5


def test_soul_sear_removal_lasts_until_end_of_turn_only():
    scenario = _board(
        ["Soul Sear", "Giant Growth"], ["Mountain"] * 3 + ["Forest"], ["Darksteel Gargoyle"]
    )
    gargoyle = scenario.creature("Darksteel Gargoyle", "bob")
    scenario.cast_and_resolve("Giant Growth", auto=True, targets=[gargoyle])

    scenario.cast_and_resolve("Soul Sear", auto=True, targets=[gargoyle])

    assert gargoyle.zone is Zone.BATTLEFIELD and gargoyle.damage == 5
    assert not is_indestructible(gargoyle, scenario.game)
    _to_next_turn(scenario)
    assert is_indestructible(gargoyle, scenario.game)


def test_soul_sear_keeps_the_creatures_other_keywords():
    scenario = _board(
        ["Soul Sear", "Giant Growth"], ["Mountain"] * 3 + ["Forest"], ["Darksteel Gargoyle"]
    )
    gargoyle = scenario.creature("Darksteel Gargoyle", "bob")
    scenario.cast_and_resolve("Giant Growth", auto=True, targets=[gargoyle])

    scenario.cast_and_resolve("Soul Sear", auto=True, targets=[gargoyle])

    abilities = scenario.game.characteristics_of(gargoyle).abilities
    assert "Flying" in abilities


def test_soul_sear_does_not_touch_another_indestructible_creature():
    scenario = _board(["Soul Sear"], ["Mountain"] * 3, ["Darksteel Gargoyle", "Hill Giant"])
    gargoyle = scenario.creature("Darksteel Gargoyle", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Soul Sear", auto=True, targets=[giant])

    assert giant.zone is Zone.GRAVEYARD
    assert is_indestructible(gargoyle, scenario.game)


def test_smite_the_deathless_exiles_the_creature_it_unmade():
    scenario = _board(["Smite the Deathless"], ["Mountain"] * 2, ["Darksteel Gargoyle"])
    gargoyle = scenario.creature("Darksteel Gargoyle", "bob")

    scenario.cast_and_resolve("Smite the Deathless", auto=True, targets=[gargoyle])

    assert gargoyle.zone is Zone.EXILE


# -- Hour of Devastation / Battle of Frost and Fire ----------------------------


def _bolas(scenario):
    bolas = scenario.find("Nicol Bolas, the Ravager", Zone.BATTLEFIELD, "bob")
    bolas.transform()
    scenario.game.add_counters(bolas, Counter.LOYALTY, 7)
    return bolas


def test_hour_of_devastation_strips_indestructible_then_deals_damage():
    scenario = _board(
        ["Hour of Devastation"],
        ["Mountain"] * 5 + ["Darksteel Gargoyle"],
        ["Darksteel Gargoyle", "Colossal Dreadmaw", "Jace Beleren"],
    )
    mine = scenario.creature("Darksteel Gargoyle", "alice")
    theirs = scenario.creature("Darksteel Gargoyle", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(jace, Counter.LOYALTY, 6)
    before = jace.counters[Counter.LOYALTY]

    scenario.cast_and_resolve("Hour of Devastation", auto=True)

    assert mine.zone is Zone.GRAVEYARD and theirs.zone is Zone.GRAVEYARD
    assert dreadmaw.zone is Zone.BATTLEFIELD and dreadmaw.damage == 5
    assert jace.counters[Counter.LOYALTY] == before - 5


def test_hour_of_devastation_spares_a_bolas_planeswalker():
    scenario = _board(
        ["Hour of Devastation"], ["Mountain"] * 5, ["Nicol Bolas, the Ravager", "Jace Beleren"]
    )
    bolas = _bolas(scenario)
    before = bolas.counters[Counter.LOYALTY]

    scenario.cast_and_resolve("Hour of Devastation", auto=True)

    assert bolas.zone is Zone.BATTLEFIELD
    assert bolas.counters[Counter.LOYALTY] == before


def test_hour_of_devastation_creature_arriving_later_keeps_indestructible():
    """CR 611.2c: the removal changes characteristics, so its set is fixed
    as it begins."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hour of Devastation", "Darksteel Gargoyle"],
            battlefield=["Mountain"] * 5,
            library=["Mountain"] * 10,
        )
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Hour of Devastation", auto=True)

    late = scenario.put_onto_battlefield("Darksteel Gargoyle", "alice")

    assert is_indestructible(late, scenario.game)


def test_battle_of_frost_and_fire_spares_giants_but_not_planeswalkers():
    scenario = _board(
        ["Battle of Frost and Fire"], [], ["Hill Giant", "Colossal Dreadmaw", "Jace Beleren"]
    )
    giant = scenario.creature("Hill Giant", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(jace, Counter.LOYALTY, 6)
    before = jace.counters[Counter.LOYALTY]
    saga = scenario.find("Battle of Frost and Fire", Zone.HAND, "alice")

    scenario.game.put_onto_battlefield(saga, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert giant.damage == 0
    assert dreadmaw.damage == 4
    assert jace.counters[Counter.LOYALTY] == before - 4


# -- Dragonclaw Strike / Chelonian Tackle -------------------------------------


def _dragonclaw(alice_battlefield, bob_battlefield):
    return _board(
        ["Dragonclaw Strike", "Giant Growth"],
        ["Forest", "Forest", "Island", "Island", "Mountain", "Mountain", "Forest"]
        + list(alice_battlefield),
        bob_battlefield,
    )


def test_dragonclaw_strike_doubles_then_fights():
    scenario = _dragonclaw(["Grizzly Bears"], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Dragonclaw Strike", auto=True, targets=[bears, giant])

    assert scenario.game.characteristics_of(bears).power_toughness == (4, 4)
    assert giant.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 3


def test_dragonclaw_strike_doubles_what_is_already_pumped():
    """CR 701.10b: X is the power as the spell resolves, earlier pumps included."""
    scenario = _dragonclaw(["Grizzly Bears"], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Giant Growth", auto=True, targets=[bears])

    scenario.cast_and_resolve("Dragonclaw Strike", auto=True, targets=[bears])

    assert scenario.game.characteristics_of(bears).power_toughness == (10, 10)


def test_dragonclaw_strike_with_no_second_target_only_doubles():
    """CR 115.6: "up to one" may choose none; nothing fights."""
    scenario = _dragonclaw(["Grizzly Bears"], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.cast_and_resolve("Dragonclaw Strike", auto=True, targets=[bears])

    assert scenario.game.characteristics_of(bears).power_toughness == (4, 4)
    assert giant.damage == 0 and bears.damage == 0


def test_dragonclaw_strike_fight_target_gone_still_doubles():
    """CR 608.2b: the illegal target is skipped, the doubling still happens,
    and with no opponent creature nothing fights (CR 701.14b)."""
    scenario = _dragonclaw(["Grizzly Bears"], ["Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Dragonclaw Strike", auto=True, targets=[bears, giant])
    scenario.game.sacrifice(giant)

    scenario.pass_until_resolved()

    assert scenario.game.characteristics_of(bears).power_toughness == (4, 4)
    assert bears.damage == 0


def test_dragonclaw_strike_doubling_ends_at_end_of_turn():
    scenario = _dragonclaw(["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Dragonclaw Strike", auto=True, targets=[bears])

    _to_next_turn(scenario)

    assert scenario.game.characteristics_of(bears).power_toughness == (2, 2)


def test_chelonian_tackle_pumps_then_fights():
    scenario = _board(
        ["Chelonian Tackle"], ["Forest"] * 3 + ["Grizzly Bears"], ["Colossal Dreadmaw"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Chelonian Tackle", auto=True, targets=[bears, dreadmaw])

    assert scenario.game.characteristics_of(bears).power_toughness == (2, 12)
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 6
    assert dreadmaw.damage == 2


# -- Fists of Flame / Get a Leg Up ----------------------------------------------


def test_fists_of_flame_counts_its_own_draw():
    scenario = _board(["Fists of Flame"], ["Mountain"] * 2 + ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Fists of Flame", auto=True, targets=[bears])

    chars = scenario.game.characteristics_of(bears)
    assert chars.power_toughness == (3, 2)
    assert "Trample" in chars.abilities


def test_fists_of_flame_counts_every_card_drawn_this_turn():
    scenario = _board(["Fists of Flame"], ["Mountain"] * 2 + ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.draw(2, "alice")

    scenario.cast_and_resolve("Fists of Flame", auto=True, targets=[bears])

    assert scenario.game.characteristics_of(bears).power_toughness == (5, 2)


def test_fists_of_flame_count_is_locked_in_on_resolution():
    """CR 608.2h: a later draw does not grow the bonus."""
    scenario = _board(["Fists of Flame"], ["Mountain"] * 2 + ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Fists of Flame", auto=True, targets=[bears])

    scenario.draw(3, "alice")

    assert scenario.game.characteristics_of(bears).power_toughness == (3, 2)


def test_fists_of_flame_with_its_only_target_gone_does_not_resolve():
    """CR 608.2b: every target illegal, so the spell does not resolve - not
    even its untargeted draw."""
    scenario = _board(["Fists of Flame"], ["Mountain"] * 2 + ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    spell = scenario.cast_onto_stack("Fists of Flame", auto=True, targets=[bears])
    scenario.game.sacrifice(bears)

    scenario.pass_until_resolved()

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.game.cards_drawn_this_turn.get("alice", 0) == 0


def test_fists_of_flame_pump_ends_at_end_of_turn():
    scenario = _board(["Fists of Flame"], ["Mountain"] * 2 + ["Grizzly Bears"], [])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Fists of Flame", auto=True, targets=[bears])

    _to_next_turn(scenario)

    chars = scenario.game.characteristics_of(bears)
    assert chars.power_toughness == (2, 2)
    assert "Trample" not in chars.abilities


def test_get_a_leg_up_counts_creatures_and_grants_reach():
    scenario = _board(
        ["Get a Leg Up"], ["Forest", "Grizzly Bears", "Runeclaw Bear", "Llanowar Elves"], []
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Get a Leg Up", auto=True, targets=[bears])

    chars = scenario.game.characteristics_of(bears)
    assert chars.power_toughness == (5, 5)
    assert "Reach" in chars.abilities

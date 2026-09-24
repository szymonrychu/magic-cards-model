"""Scenario: "whenever you put a +1/+1 counter on <a description>" and its riders.

The active-voice counter-placement trigger (CR 122.6) as Marvel Super
Heroes prints it three ways, plus the older printings of the identical
shape:

- Ant-Man, Colony Commander: "Whenever you put a +1/+1 counter on a
  creature, create a 1/1 green Insect creature token. This ability triggers
  only once each turn."
- Knight of Wundagore: "Whenever you put a +1/+1 counter on another
  creature, put a +1/+1 counter on this creature. This ability triggers only
  once each turn."
- Invisible Woman, Sue Storm: "Whenever you put one or more +1/+1 counters on
  one or more other Heroes you control, you may create a 0/4 colorless Wall
  creature token with defender."
- Stocking the Pantry (BLB) and Terrasymbiosis (EOE), neither a listed card
  nor in a deck: "Whenever you put one or more +1/+1 counters on a creature
  you control, ..." - the proof the reader is the template, not the MSH
  wording.

"You put" is who puts the counters (CR 122.6a names the object's controller
as the default putter; a resolving spell or ability's instructions are
followed by its controller), carried on the event as `GameEvent.player`.

Card text verified against Scryfall's oracle text. Every CR number here was
looked up with `mise run rules:find` in the session that wrote this file:

- **CR 122.6** - "Some spells and abilities refer to counters being put on an
  object. This refers to putting counters on that object while it's on the
  battlefield and also to an object that's given counters as it enters the
  battlefield."
- **CR 122.6a** - "If the effect doesn't specify a player, the object's
  controller puts those counters on it."
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs. However, it can trigger repeatedly if one event contains multiple
  occurrences."
- **CR 603.2h** - "Do this only once each turn" / "This ability triggers only
  once each turn": the ability triggers only if its source's controller has
  not yet taken that action this turn.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _board(*alice: str, bob: tuple[str, ...] = ("Grizzly Bears",)) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=list(alice), library=["Forest"] * 5)
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
    )


def _names(scenario, username: str) -> list[str]:
    return sorted(
        permanent.name
        for permanent in scenario.game.battlefield
        if permanent.controller == username
    )


def _next_turn(scenario) -> None:
    """Advance through the turn structure until the other player's turn."""
    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        _resolve_pending(scenario)
        scenario.advance()


def _resolve_pending(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


# -- Ant-Man, Colony Commander ----------------------------------------------


def test_ant_man_triggers_when_you_put_a_counter_on_your_creature():
    scenario = _board("Ant-Man, Colony Commander", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert [t.source_name for t in scenario.pending_triggers] == ["Ant-Man, Colony Commander"]
    _resolve_pending(scenario)
    assert _names(scenario, "alice").count("Insect Token") == 1


def test_ant_man_triggers_on_a_counter_you_put_on_an_opponents_creature():
    """ "a creature" has no controller clause: any creature, so long as *you*
    put the counter."""
    scenario = _board("Ant-Man, Colony Commander").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, Counter.PLUS_ONE, 1, putter="alice")

    assert [t.source_name for t in scenario.pending_triggers] == ["Ant-Man, Colony Commander"]


def test_ant_man_ignores_counters_an_opponent_puts():
    """CR 122.6a: the putter is whoever follows the instruction - bob putting
    a counter on alice's creature is not "you put"."""
    scenario = _board("Ant-Man, Colony Commander", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="bob")

    assert scenario.pending_triggers == []


def test_ant_man_ignores_another_kind_of_counter():
    scenario = _board("Ant-Man, Colony Commander", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []


def test_ant_man_triggers_only_once_each_turn():
    """CR 603.2h: a second counter the same turn does not trigger it again."""
    scenario = _board("Ant-Man, Colony Commander", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []
    assert _names(scenario, "alice").count("Insect Token") == 1


def test_ant_man_does_not_trigger_on_a_counter_that_is_not_on_a_creature():
    """Stocking the Pantry's supply counter goes on an enchantment - not "a
    creature" - so it is not Ant-Man's event even though alice put it."""
    scenario = _board("Ant-Man, Colony Commander", "Stocking the Pantry").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pantry = next(p for p in scenario.game.battlefield if p.name == "Stocking the Pantry")

    scenario.game.add_counters(pantry, "supply", 1, putter="alice")

    assert scenario.pending_triggers == []


# -- Knight of Wundagore ----------------------------------------------------


def test_knight_grows_when_you_put_a_counter_on_another_creature():
    scenario = _board("Knight of Wundagore", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Wundagore", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)

    assert knight.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.pending_triggers == [], "its own counter is not 'another creature'"


def test_knight_ignores_a_counter_on_itself():
    scenario = _board("Knight of Wundagore", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Wundagore", "alice")

    scenario.game.add_counters(knight, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []


def test_knight_triggers_only_once_each_turn():
    scenario = _board("Knight of Wundagore", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Wundagore", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []
    assert knight.counter_count(Counter.PLUS_ONE) == 1


def test_knight_triggers_again_on_a_new_turn():
    scenario = _board("Knight of Wundagore", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)

    _next_turn(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert [t.source_name for t in scenario.pending_triggers] == ["Knight of Wundagore"]


# -- Invisible Woman, Sue Storm ---------------------------------------------


def test_invisible_woman_makes_a_wall_when_another_hero_gets_counters():
    scenario = _board("Invisible Woman, Sue Storm", "Kid Loki").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = scenario.creature("Kid Loki", "alice")
    scenario.will_take_the_may(True)

    scenario.game.add_counters(loki, Counter.PLUS_ONE, 2, putter="alice")
    _resolve_pending(scenario)

    walls = [p for p in scenario.game.battlefield if p.name == "Wall Token"]
    assert len(walls) == 1
    wall = walls[0]
    assert (wall.power, wall.toughness) == (0, 4)
    assert scenario.game.characteristics_of(wall).colors == ()
    assert has_keyword(wall, Keyword.DEFENDER, scenario.game)


def test_invisible_woman_may_decline_the_wall():
    scenario = _board("Invisible Woman, Sue Storm", "Kid Loki").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = scenario.creature("Kid Loki", "alice")
    scenario.will_take_the_may(False)

    scenario.game.add_counters(loki, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)

    assert "Wall Token" not in _names(scenario, "alice")


def test_invisible_woman_ignores_herself_and_non_heroes():
    """ "other Heroes": neither her own counters nor a non-Hero's count."""
    scenario = _board("Invisible Woman, Sue Storm", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sue = scenario.creature("Invisible Woman, Sue Storm", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.add_counters(sue, Counter.PLUS_ONE, 1, putter="alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []


def test_invisible_woman_ignores_an_opponents_hero():
    """ "Heroes you control" - bob's Kid Loki is not one."""
    scenario = _board("Invisible Woman, Sue Storm", bob=("Kid Loki",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Kid Loki", "bob")

    scenario.game.add_counters(theirs, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []


def test_counters_on_two_heroes_at_once_are_one_trigger():
    """CR 603.2c: "one or more counters on one or more other Heroes" is one
    event however many Heroes the one instruction reached."""
    scenario = _board("Invisible Woman, Sue Storm", "Kid Loki", "Beast, Erudite Aerialist").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = scenario.creature("Kid Loki", "alice")
    beast = scenario.creature("Beast, Erudite Aerialist", "alice")

    scenario.game.add_counters(loki, Counter.PLUS_ONE, 1, putter="alice")
    scenario.game.add_counters(beast, Counter.PLUS_ONE, 1, putter="alice")

    assert [t.source_name for t in scenario.pending_triggers] == ["Invisible Woman, Sue Storm"]


# -- the template on printings outside the listed cards ----------------------


def test_stocking_the_pantry_reads_the_same_template():
    """Stocking the Pantry: "Whenever you put one or more +1/+1 counters on a
    creature you control, put a supply counter on this enchantment." - the
    supply counter goes on an enchantment, so it does not re-trigger it."""
    scenario = _board("Stocking the Pantry", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    pantry = next(p for p in scenario.game.battlefield if p.name == "Stocking the Pantry")

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2, putter="alice")
    _resolve_pending(scenario)

    assert pantry.counter_count("supply") == 1
    assert scenario.pending_triggers == []


def test_stocking_the_pantry_ignores_a_creature_you_do_not_control():
    scenario = _board("Stocking the Pantry").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    scenario.game.add_counters(theirs, Counter.PLUS_ONE, 1, putter="alice")

    assert scenario.pending_triggers == []


def test_terrasymbiosis_draws_that_many_once_each_turn():
    """Terrasymbiosis: "... you may draw that many cards. Do this only once
    each turn." - "that many" is the event's own count (CR 603.2c: one event,
    two counters)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Terrasymbiosis", "Grizzly Bears"],
            library=["Forest"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True)

    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2, putter="alice")
    _resolve_pending(scenario)
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1, putter="alice")
    _resolve_pending(scenario)

    assert len(scenario.player("alice").hand) == hand_before + 2


# -- The Thing, Ben Grimm: "Whenever one or more Heroes you control deal damage
# to a player, put two +1/+1 counters on The Thing." ---------------------------
#
# CR 510.2's combat damage is dealt simultaneously - one event per player per
# step (CR 603.2c) - and noncombat damage is its own event. A Hero is a
# creature type (CR 205.3m).

THING = "The Thing, Ben Grimm"


def _thing_board(*alice: str, bob: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=[THING, *alice], library=["Forest"] * 5)
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
    )


def _attack(scenario, *attackers) -> None:
    for attacker in attackers:
        attacker.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.advance()
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_pending(scenario)


def test_the_thing_grows_when_a_hero_deals_combat_damage_to_a_player():
    scenario = _thing_board("Kid Loki").build()
    thing = scenario.creature(THING, "alice")
    loki = scenario.creature("Kid Loki", "alice")

    _attack(scenario, loki)

    assert thing.counter_count(Counter.PLUS_ONE) == 2


def test_two_heroes_in_one_combat_damage_step_are_one_trigger():
    """The Thing is a Hero too: it and Kid Loki connecting together is one
    event (CR 603.2c), two counters, not four."""
    scenario = _thing_board("Kid Loki").build()
    thing = scenario.creature(THING, "alice")
    loki = scenario.creature("Kid Loki", "alice")

    _attack(scenario, thing, loki)

    assert thing.counter_count(Counter.PLUS_ONE) == 2


def test_a_non_hero_dealing_damage_does_nothing():
    scenario = _thing_board("Grizzly Bears").build()
    thing = scenario.creature(THING, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    _attack(scenario, bears)

    assert thing.counter_count(Counter.PLUS_ONE) == 0


def test_noncombat_damage_from_a_hero_counts():
    """ "deal damage", not "combat damage": a Hero's noncombat damage to a
    player is the event too (CR 120.1)."""
    scenario = _thing_board("Kid Loki").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thing = scenario.creature(THING, "alice")
    loki = scenario.creature("Kid Loki", "alice")

    scenario.game.deal_damage(scenario.player("bob"), 1, source=loki)
    _resolve_pending(scenario)

    assert thing.counter_count(Counter.PLUS_ONE) == 2


def test_damage_to_a_creature_does_not_count():
    scenario = _thing_board("Kid Loki", bob=("Grizzly Bears",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thing = scenario.creature(THING, "alice")
    loki = scenario.creature("Kid Loki", "alice")

    scenario.game.deal_damage(scenario.creature("Grizzly Bears", "bob"), 1, source=loki)
    _resolve_pending(scenario)

    assert thing.counter_count(Counter.PLUS_ONE) == 0


def test_an_opponents_hero_does_not_count():
    """ "Heroes you control" - bob's Kid Loki hitting alice is not it."""
    scenario = _thing_board(bob=("Kid Loki",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thing = scenario.creature(THING, "alice")
    theirs = scenario.creature("Kid Loki", "bob")

    scenario.game.deal_damage(scenario.player("alice"), 1, source=theirs)
    _resolve_pending(scenario)

    assert thing.counter_count(Counter.PLUS_ONE) == 0


# -- Wakandan Royal Guard: "put a +1/+1 counter on target creature. If that
# creature is another Hero, put two +1/+1 counters on it instead." -----------
#
# CR 614.1a: "instead" - a Hero gets two, never one plus two. Elder Cathar's
# "If that creature is a Human, put two +1/+1 counters on it instead." is the
# older printing of the same reader (tests/scenarios/test_counter_or_more_if_
# subtype.py); "another" is what this one adds - the Guard is a Hero itself.

GUARD = "Wakandan Royal Guard"


def _guard_enters(scenario, target) -> None:
    scenario.choose_trigger_targets(GUARD, [target])
    scenario.put_onto_battlefield(GUARD, "alice")
    _resolve_pending(scenario)


def _guard_board(*alice: str) -> Scenario:
    return Scenario().player("alice", hand=[GUARD], battlefield=list(alice)).player("bob")


def test_the_guard_puts_two_counters_on_another_hero():
    scenario = _guard_board("Kid Loki").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = scenario.creature("Kid Loki", "alice")

    _guard_enters(scenario, loki)

    assert loki.counter_count(Counter.PLUS_ONE) == 2


def test_the_guard_puts_one_counter_on_a_non_hero():
    scenario = _guard_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _guard_enters(scenario, bears)

    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_the_guard_on_itself_is_not_another_hero():
    scenario = _guard_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guard = scenario.put_onto_battlefield(GUARD, "alice")
    scenario.choose_trigger_targets(GUARD, [guard])
    _resolve_pending(scenario)

    assert guard.counter_count(Counter.PLUS_ONE) == 1


# -- Heroic Feast: "Whenever you gain life, choose up to that many target
# creatures you control. Put a +1/+1 counter on each of them." ---------------
#
# CR 601.2c (via CR 603.3d): the number of targets is fixed as the ability goes
# on the stack - "that many" is the life the event gained (CR 119.9).

FEAST = "Heroic Feast"


def test_heroic_feast_grows_up_to_that_many_creatures():
    scenario = (
        Scenario()
        .player("alice", battlefield=[FEAST, "Grizzly Bears", "Kid Loki", "Knight of Wundagore"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    loki = scenario.creature("Kid Loki", "alice")
    scenario.will_choose_targets(bears, loki, username="alice")

    scenario.game.gain_life("alice", 2)
    _resolve_pending(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 1
    assert loki.counter_count(Counter.PLUS_ONE) == 1
    assert scenario.creature("Knight of Wundagore", "alice").counter_count(Counter.PLUS_ONE) == 1, (
        "Knight of Wundagore's own trigger: a counter on another creature"
    )


def test_heroic_feast_caps_the_targets_at_the_life_gained():
    scenario = (
        Scenario()
        .player("alice", battlefield=[FEAST, "Grizzly Bears", "Kid Loki"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(bears, username="alice")

    scenario.game.gain_life("alice", 1)
    scenario.game.put_triggers_on_stack()

    (question,) = [q for q in scenario.questions_asked() if q.kind.name == "CHOOSE_TARGETS"]
    assert question.target_maximum == 1


def test_heroic_feast_may_choose_no_creature():
    scenario = Scenario().player("alice", battlefield=[FEAST, "Grizzly Bears"]).player("bob")
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets(username="alice")

    scenario.game.gain_life("alice", 3)
    _resolve_pending(scenario)

    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_heroic_feast_ignores_an_opponents_life_gain():
    scenario = Scenario().player("alice", battlefield=[FEAST, "Grizzly Bears"]).player("bob")
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("bob", 3)

    assert scenario.pending_triggers == []


def test_heroic_feast_enters_with_a_food():
    scenario = Scenario().player("alice", hand=[FEAST]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(FEAST, "alice")
    _resolve_pending(scenario)

    assert "Food Token" in _names(scenario, "alice")


# -- Alien Invasion: "At the beginning of combat on your turn, create a 1/1 red
# Alien creature token with haste and "This token attacks each combat if
# able." Put a +1/+1 counter on it for each invasion counter on this
# enchantment, then put an invasion counter on this enchantment." ------------

INVASION = "Alien Invasion"


def _to_combat(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()
    _resolve_pending(scenario)


def _aliens(scenario) -> list:
    return [p for p in scenario.game.battlefield if p.name == "Alien Token"]


def test_the_first_alien_has_no_counters_and_the_enchantment_gets_one():
    scenario = Scenario().player("alice", battlefield=[INVASION]).player("bob").build()
    invasion = next(p for p in scenario.game.battlefield if p.name == INVASION)

    _to_combat(scenario)

    (alien,) = _aliens(scenario)
    assert alien.counter_count(Counter.PLUS_ONE) == 0
    assert invasion.counter_count("invasion") == 1
    assert (alien.power, alien.toughness) == (1, 1)
    assert has_keyword(alien, Keyword.HASTE, scenario.game)


def test_each_alien_counts_the_invasion_counters_already_there():
    """CR 608.2c: counted before the new invasion counter is put on."""
    scenario = Scenario().player("alice", battlefield=[INVASION]).player("bob").build()
    invasion = next(p for p in scenario.game.battlefield if p.name == INVASION)
    invasion.add_counters("invasion", 2)

    _to_combat(scenario)

    (alien,) = _aliens(scenario)
    assert alien.counter_count(Counter.PLUS_ONE) == 2
    assert invasion.counter_count("invasion") == 3


def test_the_alien_attacks_each_combat_if_able():
    """CR 508.1d: its granted "This token attacks each combat if able." - the
    declaration the turn structure makes for alice has it attacking."""
    scenario = Scenario().player("alice", battlefield=[INVASION]).player("bob").build()
    _to_combat(scenario)
    (alien,) = _aliens(scenario)

    scenario.advance()

    assert scenario.step is Step.DECLARE_ATTACKERS
    assert scenario.attackers() == [alien]

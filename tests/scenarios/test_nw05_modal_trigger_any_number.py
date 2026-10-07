"""A "choose any number -" modal triggered ability, and the turn-long "a
source would deal damage to a player or battle" plus-N replacement one of its
modes creates (NW-05, task T5).

Rankle and Torbran: "Whenever Rankle and Torbran deals combat damage to a
player or battle, choose any number - / Each player creates a Treasure token.
/ Each player sacrifices a creature of their choice. / If a source would deal
damage to a player or battle this turn, it deals that much damage plus 2
instead."

- **CR 700.2b** - "The controller of a modal triggered ability chooses the
  mode(s) as part of putting that ability on the stack. ... If no mode is
  chosen, the ability is removed from the stack." "Any number" is zero to
  every mode, so choosing none is legal and removes the ability.
- **CR 700.2d** - a mode can't be chosen more than once unless the card says
  so.
- **CR 111.10a** - a Treasure token is a colorless Treasure artifact token
  with "{T}, Sacrifice this token: Add one mana of any color."
- **CR 701.21a** - each player sacrifices a permanent they control.
- **CR 614.1a** - "instead" makes the third mode a replacement effect; it
  applies to any source (no "you control"), and only to damage dealt to a
  player or a battle (CR 310.6: damage to a battle removes defense counters).
- **CR 608.2c** - the chosen modes run in printed order.

Rankle, Master of Pranks is the second printing of "choose any number -" on a
combat-damage trigger; The Flame of Keld's chapter III is the regression for
the "a permanent or player" recipient list the battle reading generalises.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.machines.effects.modal import modal_trigger_profile
from magic_cards_model.machines.replacement.parse import read_turn_damage_spec
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

RT = "Rankle and Torbran"
TREASURE = "Each player creates a Treasure token."
SACRIFICE = "Each player sacrifices a creature of their choice."
PLUS_TWO = (
    "If a source would deal damage to a player or battle this turn, it deals that much "
    "damage plus 2 instead."
)
ERGAMON = "Invasion of Ergamon"  # Battle - Siege, defense 5

LISTED = [RT]
SECOND_PRINTINGS = ["Rankle, Master of Pranks", "The Flame of Keld"]


@pytest.mark.parametrize("name", LISTED + SECOND_PRINTINGS)
def test_every_printing_is_fully_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, (name, bad)


def test_any_number_reads_as_zero_to_every_mode():
    effect = card(RT).oracle_text.split("\n", 1)[1].split(", ", 1)[1]
    profile = modal_trigger_profile(effect)
    assert profile is not None
    assert (profile.minimum, profile.maximum) == (0, 3)
    assert [mode.text for mode in profile.modes] == [TREASURE, SACRIFICE, PLUS_TWO]


def test_the_plus_two_mode_reads_any_source_and_a_player_or_battle():
    spec = read_turn_damage_spec(PLUS_TWO)
    assert spec is not None
    assert spec.addend == 2
    assert spec.recipient == "a player or battle"
    assert spec.any_controller is True


def _board(*, alice=(), bob=(), bob_hand=(), alice_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[RT, *alice],
            hand=list(alice_hand),
            library=["Mountain"] * 3,
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Mountain"] * 3)
        .build()
    )
    return scenario


def _first_strike_hits(scenario, *attackers):
    """Declare `attackers` against bob, no blocks, and deal the first-strike
    combat damage step only; Rankle and Torbran's trigger is then on the
    stack."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.game.combat_damage_step()
    scenario.game.put_triggers_on_stack()


def _mode_questions(scenario):
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_A_MODE]


def _choose(scenario, *modes):
    for mode in modes:
        scenario.will_choose_mode(mode, username="alice")
    if len(modes) < 3:
        scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")


def _resolve_all(scenario):
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _bob_bolts(scenario, target):
    """Alice passes with an empty stack; bob casts Lightning Bolt at
    `target` and it resolves."""
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[target],
    )
    scenario.resolve_top()


def _enter_siege(scenario):
    """Invasion of Ergamon enters under alice's control, protected by bob
    (CR 310.9b); its own enters trigger's optional discard is declined."""
    scenario.will_take_the_may(False, username="alice", source=ERGAMON)
    siege = scenario.put_onto_battlefield(ERGAMON, "alice")
    scenario.pass_until_resolved()
    return siege


def _treasures(scenario, username):
    return [p for p in scenario.game.permanents_controlled_by(username) if p.name == "Treasure Token"]


def test_choosing_no_mode_removes_the_ability():
    """CR 700.2b: zero modes is a legal choice for "any number", and it
    removes the ability from the stack."""
    scenario = _board()
    rt = scenario.creature(RT, "alice")
    _choose(scenario)
    _first_strike_hits(scenario, rt)

    (question,) = _mode_questions(scenario)
    assert NO_FURTHER_MODES in question.options
    assert scenario.game.stack_is_empty
    assert scenario.player("bob").life == 17
    assert _treasures(scenario, "alice") == []


def test_the_treasure_mode_alone_gives_each_player_a_treasure():
    scenario = _board()
    rt = scenario.creature(RT, "alice")
    _choose(scenario, TREASURE)
    _first_strike_hits(scenario, rt)
    _resolve_all(scenario)

    assert len(_treasures(scenario, "alice")) == 1
    assert len(_treasures(scenario, "bob")) == 1
    assert scenario.game.mode_notices == []


def test_the_sacrifice_mode_has_each_player_choose_their_own_creature():
    scenario = _board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    rt = scenario.creature(RT, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _choose(scenario, SACRIFICE)
    _first_strike_hits(scenario, rt)
    scenario.will_choose_cards(bears, username="alice")
    _resolve_all(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert rt.zone is Zone.BATTLEFIELD


def test_the_plus_two_mode_adds_two_to_later_combat_damage_to_a_player():
    """Rankle and Torbran's first-strike damage triggers it; the Bears'
    regular combat damage that follows is 2 plus 2."""
    scenario = _board(alice=["Grizzly Bears"])
    rt = scenario.creature(RT, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _choose(scenario, PLUS_TWO)
    _first_strike_hits(scenario, rt, bears)
    assert scenario.player("bob").life == 17
    _resolve_all(scenario)
    scenario.game.combat_damage_step()

    assert scenario.player("bob").life == 13


def test_the_plus_two_applies_to_an_opponents_source_too():
    """No "you control": bob's Lightning Bolt at alice deals 5."""
    scenario = _board(bob=["Mountain"], bob_hand=["Lightning Bolt"])
    rt = scenario.creature(RT, "alice")
    _choose(scenario, PLUS_TWO)
    _first_strike_hits(scenario, rt)
    _resolve_all(scenario)

    _bob_bolts(scenario, "alice")
    assert scenario.player("alice").life == 15


def test_the_plus_two_does_not_touch_damage_to_a_creature():
    scenario = _board(alice=["Craw Wurm"], bob=["Mountain"], bob_hand=["Lightning Bolt"])
    rt = scenario.creature(RT, "alice")
    wurm = scenario.creature("Craw Wurm", "alice")
    _choose(scenario, PLUS_TWO)
    _first_strike_hits(scenario, rt)
    _resolve_all(scenario)

    _bob_bolts(scenario, wurm)
    assert wurm.damage == 3


def test_the_plus_two_adds_to_damage_dealt_to_a_battle():
    """Rankle and Torbran hits bob in the first-strike step; the Bears'
    regular damage to the battle is then 2 plus 2 (CR 310.6: four defense
    counters come off)."""
    scenario = _board(alice=["Grizzly Bears"], alice_hand=[ERGAMON])
    rt = scenario.creature(RT, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario)
    _choose(scenario, PLUS_TWO)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.declare_attackers([(rt, "bob"), (bears, siege)])
    scenario.no_blocks()
    scenario.game.combat_damage_step()
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)
    scenario.game.combat_damage_step()

    assert siege.counter_count("defense") == 1


def test_combat_damage_to_a_battle_triggers_it_too():
    """"deals combat damage to a player or battle": the battle alone is
    enough."""
    scenario = _board(alice_hand=[ERGAMON])
    rt = scenario.creature(RT, "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario)
    _choose(scenario, TREASURE)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(rt, defending=siege)
    scenario.no_blocks()
    scenario.game.combat_damage_step()
    scenario.game.put_triggers_on_stack()
    _resolve_all(scenario)

    assert siege.counter_count("defense") == 2
    assert len(_treasures(scenario, "alice")) == 1


def test_every_mode_runs_in_printed_order():
    """CR 608.2c: treasures first, then each player sacrifices a creature
    (the new Treasures are not creatures), then the turn-long plus 2."""
    scenario = _board(alice=["Grizzly Bears"], bob=["Hill Giant", "Mountain"])
    rt = scenario.creature(RT, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _choose(scenario, PLUS_TWO, SACRIFICE, TREASURE)
    _first_strike_hits(scenario, rt)
    scenario.will_choose_cards(bears, username="alice")
    (ability,) = list(scenario.game.stack)
    assert sorted(ability.modes) == [1, 2, 3]
    _resolve_all(scenario)

    assert len(_treasures(scenario, "alice")) == 1
    assert len(_treasures(scenario, "bob")) == 1
    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


# -- Rankle, Master of Pranks: the same "choose any number" -------------------


def test_rankle_master_of_pranks_runs_the_chosen_two_of_three():
    """The draw mode is announced first, the discard second; they still run
    in printed order (CR 608.2c), so alice, with an empty hand, discards
    nothing and then keeps the card she draws."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rankle, Master of Pranks"], library=["Mountain"] * 3)
        .player("bob", hand=["Island"], library=["Swamp"] * 3)
        .build()
    )
    rankle = scenario.creature("Rankle, Master of Pranks", "alice")
    scenario.will_choose_mode("Each player loses 1 life and draws a card.", username="alice")
    scenario.will_choose_mode("Each player discards a card.", username="alice")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(rankle)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve_all(scenario)

    assert scenario.player("bob").life == 20 - 3 - 1
    assert scenario.player("alice").life == 19
    assert [c.name for c in scenario.player("alice").hand] == ["Mountain"]
    assert scenario.player("alice").graveyard == []
    assert [c.name for c in scenario.player("bob").graveyard] == ["Island"]
    assert [c.name for c in scenario.player("bob").hand] == ["Swamp"]


def test_rankle_master_of_pranks_may_choose_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rankle, Master of Pranks"], library=["Mountain"] * 3)
        .player("bob", hand=["Island"], library=["Island"] * 3)
        .build()
    )
    rankle = scenario.creature("Rankle, Master of Pranks", "alice")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(rankle)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.game.stack_is_empty
    assert len(scenario.player("bob").hand) == 1


# -- The Flame of Keld III: the recipient list it shares, unchanged -----------


def test_flame_of_keld_three_still_adds_two_to_a_red_source_you_control():
    """Chapter III's "a permanent or player" list and "you control" still read
    the way they did: alice's red Bolt deals 5 to bob and to his creature."""
    spec = read_turn_damage_spec(card("The Flame of Keld").oracle_text.split("III \u2014 ", 1)[1])
    assert spec is not None and spec.addend == 2
    assert spec.recipient == "a permanent or player"
    assert spec.any_controller is False

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Flame of Keld", "Mountain", "Mountain"],
            library=["Lightning Bolt", "Lightning Bolt"],
        )
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for chapter in range(3):
        scenario.game.put_triggers_on_stack()
        _resolve_all(scenario)
        if chapter < 2:
            scenario.game.saga_lore_step()
    wurm = scenario.creature("Craw Wurm", "bob")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    scenario.cast_and_resolve("Lightning Bolt", second, targets=[wurm])

    assert scenario.player("bob").life == 15
    assert wurm.zone is Zone.GRAVEYARD  # 5 damage to a 6/4; 3 would not kill it

"""A permanent's own ability preventing all damage that would be dealt to
that permanent this turn - "Prevent all damage that would be dealt to him
this turn." - as the rider on a planeswalker that has just turned itself into
a creature.

- Oko, the Trickster: "0: Until end of turn, Oko becomes a copy of target
  creature you control. Prevent all damage that would be dealt to him this
  turn." The copy is CR 707.4's "a permanent ... copy[ing] a different
  object while remaining on the battlefield", a layer 1a effect (CR 613.2a)
  with CR 611.2a's stated duration.
- Gideon of the Trials (off-set proof, legal, in no deck list): "0: Until end
  of turn, Gideon becomes a 4/4 Human Soldier creature with indestructible
  that's still a planeswalker. Prevent all damage that would be dealt to him
  this turn." - the same rider after a type-changing animation rather than a
  copy, on a permanent that stays a planeswalker.

Rules, each looked up this session with `mise run rules:find`:

- **CR 615.1a** - "Effects that use the word 'prevent' are prevention
  effects."
- **CR 615.3** - a prevention effect lasts "until [it's] used up or [its]
  duration has expired"; this one is never used up.
- **CR 514.2** - "all 'until end of turn' and 'this turn' effects end" in the
  cleanup step: both the copy and the shield.
- **CR 707.2** - copiable values; "Other effects ..., status, counters, and
  stickers are not copied." Oko's own loyalty counters stay on him, the
  target's +1/+1 counters are not copied onto him.
- **CR 306.5** - "Loyalty is a characteristic only planeswalkers have." While
  a copy of a creature, Oko is no planeswalker, so CR 704.5i (a planeswalker
  with loyalty 0) does not look at him and CR 120.3c (damage to a
  planeswalker removes loyalty) does not apply: CR 120.3e marks damage.
- **CR 608.2b** - an ability whose only target is illegal doesn't resolve:
  no copy, and no shield either.
- **CR 400.7** - an Oko that leaves and returns is a new object: neither the
  copy nor the shield follows him.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone

from .harness import Scenario

OKO = "Oko, the Trickster"
GIDEON = "Gideon of the Trials"
COPY = 1  # "0: Until end of turn, Oko becomes a copy of ..."
ANIMATE = 1  # "0: Until end of turn, Gideon becomes a 4/4 ..."


def _oko_board(*, alice_hand=("Lightning Bolt",), bob_battlefield=(), bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[OKO, "Grizzly Bears", "Mountain", "Mountain", "Plains"],
            hand=list(alice_hand),
            library=["Island"] * 8,
        )
        .player(
            "bob",
            battlefield=["Mountain", *bob_battlefield],
            hand=list(bob_hand),
            library=["Forest"] * 8,
        )
        .build()
    )


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _oko_copies_the_bears(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    oko = scenario.find(OKO, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(oko, index=COPY, targets=[bears])
    scenario.resolve_top()
    return oko, bears


def _bolt(scenario, target, username="alice"):
    mountain = next(
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if permanent.name == "Mountain" and not permanent.tapped
    )
    scenario.cast_and_resolve("Lightning Bolt", mountain, username=username, targets=[target])


def _to_bobs_turn(scenario):
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- Oko: the copy ------------------------------------------------------------------------


def test_oko_becomes_a_copy_of_the_target_creature():
    scenario = _oko_board()
    oko, _ = _oko_copies_the_bears(scenario)

    chars = _chars(scenario, oko)
    assert chars.name == "Grizzly Bears"
    assert chars.types == (Type.CREATURE,)
    assert Type.PLANESWALKER not in chars.types
    assert chars.power_toughness == (2, 2)


def test_oko_keeps_his_loyalty_counters_and_is_not_a_planeswalker_at_zero_check():
    """CR 707.2: counters are not copiable values, so the copy changes none of
    them; and CR 306.5 / 704.5i: no planeswalker, so nothing about loyalty
    puts him in the graveyard."""
    scenario = _oko_board()
    oko, _ = _oko_copies_the_bears(scenario)

    assert oko.counters["loyalty"] == 4
    scenario.state_based_actions()
    assert oko.zone is Zone.BATTLEFIELD


def test_the_targets_counters_are_not_copied():
    scenario = _oko_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, "+1/+1", 2)
    oko = scenario.find(OKO, Zone.BATTLEFIELD, "alice")

    scenario.activate(oko, index=COPY, targets=[bears])
    scenario.resolve_top()

    assert _chars(scenario, oko).power_toughness == (2, 2)
    assert _chars(scenario, bears).power_toughness == (4, 4)


# -- Oko: the prevention ------------------------------------------------------------------


def test_damage_that_would_be_dealt_to_oko_this_turn_is_prevented():
    scenario = _oko_board()
    oko, _ = _oko_copies_the_bears(scenario)

    _bolt(scenario, oko)

    assert oko.zone is Zone.BATTLEFIELD
    assert oko.damage == 0
    assert oko.counters["loyalty"] == 4


def test_the_shield_does_not_cover_the_creature_he_copied():
    scenario = _oko_board()
    _, bears = _oko_copies_the_bears(scenario)

    _bolt(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD


def test_combat_damage_to_oko_as_a_blocked_attacker_is_prevented():
    scenario = _oko_board(bob_battlefield=["Grizzly Bears"])
    oko, _ = _oko_copies_the_bears(scenario)
    blocker = scenario.creature("Grizzly Bears", "bob")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(oko)
    scenario.advance()
    scenario.block(oko, blocker)
    scenario.combat_damage()

    assert oko.zone is Zone.BATTLEFIELD
    assert oko.damage == 0
    assert blocker.zone is Zone.GRAVEYARD


# -- Oko: the end of the turn -------------------------------------------------------------


def test_oko_is_a_planeswalker_again_after_cleanup_with_his_loyalty():
    scenario = _oko_board()
    oko, _ = _oko_copies_the_bears(scenario)

    _to_bobs_turn(scenario)

    chars = _chars(scenario, oko)
    assert chars.name == OKO
    assert Type.PLANESWALKER in chars.types
    assert Type.CREATURE not in chars.types
    assert oko.counters["loyalty"] == 4


def test_the_shield_ends_with_the_turn():
    """CR 514.2: "this turn" ends in the cleanup step - next turn a Bolt at
    the planeswalker removes three loyalty counters (CR 120.3c)."""
    scenario = _oko_board(alice_hand=(), bob_hand=["Lightning Bolt"])
    oko, _ = _oko_copies_the_bears(scenario)

    _to_bobs_turn(scenario)
    _bolt(scenario, oko, username="bob")

    assert oko.counters["loyalty"] == 1


# -- Oko: corner cases --------------------------------------------------------------------


def test_an_illegal_target_means_no_copy_and_no_shield():
    """CR 608.2b: the only target is gone, so the ability doesn't resolve -
    the prevention sentence never happens either."""
    scenario = _oko_board(alice_hand=["Lightning Bolt", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    oko = scenario.find(OKO, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(oko, index=COPY, targets=[bears])
    _bolt(scenario, bears)  # in response
    assert bears.zone is Zone.GRAVEYARD
    scenario.resolve_top()  # Oko's 0, fizzled

    assert Type.PLANESWALKER in _chars(scenario, oko).types
    _bolt(scenario, oko)
    assert oko.counters["loyalty"] == 1


def test_an_oko_that_left_and_returned_is_neither_the_copy_nor_shielded():
    """CR 400.7: Ephemerate's returned Oko is a new object. He enters with his
    printed loyalty (CR 306.5b) as a planeswalker, and the Bolt removes
    loyalty from him."""
    scenario = _oko_board(alice_hand=["Ephemerate", "Lightning Bolt"])
    oko, _ = _oko_copies_the_bears(scenario)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Ephemerate", plains, targets=[oko])
    returned = scenario.find(OKO, Zone.BATTLEFIELD, "alice")

    chars = _chars(scenario, returned)
    assert chars.name == OKO
    assert Type.PLANESWALKER in chars.types
    _bolt(scenario, returned)
    assert returned.counters["loyalty"] == 1


# -- Gideon of the Trials: the same rider on an animation ----------------------------------


def _gideon_animates():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[GIDEON, "Mountain"],
            hand=["Lightning Bolt"],
            library=["Island"] * 8,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gideon = scenario.find(GIDEON, Zone.BATTLEFIELD, "alice")
    scenario.activate(gideon, index=ANIMATE)
    scenario.resolve_top()
    return scenario, gideon


def test_gideon_is_a_creature_planeswalker_whose_damage_is_prevented():
    """Still a planeswalker, so unprevented damage would remove loyalty (CR
    120.3c) as well as be marked (CR 120.3e); prevented, it does neither."""
    scenario, gideon = _gideon_animates()
    chars = _chars(scenario, gideon)
    assert {Type.CREATURE, Type.PLANESWALKER} <= set(chars.types)
    assert chars.power_toughness == (4, 4)

    _bolt(scenario, gideon)

    assert gideon.counters["loyalty"] == 3
    assert gideon.damage == 0


def test_gideons_shield_ends_with_the_turn():
    scenario, gideon = _gideon_animates()
    _to_bobs_turn(scenario)
    assert Type.CREATURE not in _chars(scenario, gideon).types

    scenario.game.deal_damage(gideon, 2, source=scenario.find("Mountain", Zone.BATTLEFIELD))

    assert gideon.counters["loyalty"] == 1

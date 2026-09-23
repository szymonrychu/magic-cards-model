"""Scenario: Strive (CR 207.2c ability word - "Strive — This spell costs
[cost] more to cast for each target beyond the first.", no rules meaning of
its own beyond tying together cards that add that one cost-increase clause).

The cost half is CR 601.2f, priced generically by `machines/casting.py`'s
`_COST_INCREASE_PER_TARGET_RE` and already proven elsewhere. This file is
about the *resolution* half - CR 611.2's "until end of turn" duration on
whatever the spell grants each target, read generally by two different
readers:

- **`machines/layers.py`'s `_PUMP_RE`/`_PLURAL_TARGET_SUBJECT`**, widened
  here to accept "any number of" alongside "up to N"/"N": Aerial Formation's
  "Any number of target creatures each get +1/+1 and gain flying until end
  of turn." - a plain pump plus a bare keyword.
- **`machines/effects.py`'s `_parse_plural_target_gain_quoted_ability_
  whole_text`**: Launch the Fleet's "Until end of turn, any number of
  target creatures each gain "`<quoted triggered ability>`"." and Warriors'
  Lesson's differently-worded "Until end of turn, up to two target creatures
  you control each gain "`<quoted triggered ability>`"." - a quoted
  triggered ability, not a keyword, granted through `CardState.granted_
  ability_texts` (CR 113.10a) with its own `DelayedTrigger`-based "until end
  of turn" expiry (CR 514.2's cleanup-step turn-based action, watched as
  `TriggerEvent.BEGINNING_OF_STEP`/`Step.CLEANUP`).

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`. Launch the Fleet itself (the pool
card) is covered by the sweep's own `--card` check; this file's proofs are
the two off-pool printings the requirement names.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_off_pool_aerial_formation_pumps_and_grants_flying_to_any_number_of_targets():
    """ "Any number of target creatures each get +1/+1 and gain flying until
    end of turn." - a plain pump plus a bare keyword, on two targets at once,
    proving the reader is not fitted to a single-target "target creature ..."
    sentence."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aerial Formation"],
            battlefield=["Sol Ring"] + ["Island"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve("Aerial Formation", auto=True, targets=[bears, giant])

    bears_chars = scenario.game.characteristics_of(bears)
    assert bears_chars.power == 3  # printed 2, +1/+1
    assert bears_chars.toughness == 3
    assert "Flying" in bears_chars.abilities

    giant_chars = scenario.game.characteristics_of(giant)
    assert giant_chars.power == 4  # printed 3, +1/+1
    assert giant_chars.toughness == 4
    assert "Flying" in giant_chars.abilities


def test_off_pool_aerial_formation_can_choose_a_single_target():
    """CR 107.1c: "any number" includes one - a single target is just as
    legal as two, and the pump/grant still lands on it alone."""
    scenario = (
        Scenario()
        .player("alice", hand=["Aerial Formation"], battlefield=["Sol Ring"] + ["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Aerial Formation", auto=True, targets=[bears])

    chars = scenario.game.characteristics_of(bears)
    assert chars.power == 3
    assert chars.toughness == 3
    assert "Flying" in chars.abilities


def test_off_pool_warriors_lesson_grants_a_quoted_triggered_ability_to_two_targets():
    """ "Until end of turn, up to two target creatures you control each gain
    "Whenever this creature deals combat damage to a player, draw a card."" -
    a different quantifier ("up to two" rather than "any number of"), a
    controller qualifier ("you control", absent from Launch the Fleet's own
    wording), and a differently-worded granted ability, proving the reader
    generalises past Launch the Fleet's own exact sentence."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warriors' Lesson"],
            battlefield=["Grizzly Bears", "Hill Giant", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_and_resolve("Warriors' Lesson", auto=True, targets=[bears, giant])

    granted = "Whenever this creature deals combat damage to a player, draw a card."
    assert granted in bears.granted_ability_texts
    assert granted in giant.granted_ability_texts


def test_off_pool_warriors_lessons_granted_ability_actually_triggers():
    """The grant is not merely cosmetic text - it is a real triggered
    ability CR 603 fires: bears connects unblocked and alice draws a card
    off the granted line, the same way she would off a printed one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warriors' Lesson"],
            battlefield=["Grizzly Bears", "Forest"],
            library=["Mountain"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Warriors' Lesson", auto=True, targets=[bears])
    hand_before = len(scenario.player("alice").hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()  # the granted trigger's own draw

    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_off_pool_warriors_lessons_grant_expires_at_cleanup():
    """CR 514.2: "all 'until end of turn' ... effects end" in the cleanup
    step - the granted line is gone by the next time anyone could ask, and a
    later attack no longer draws a card from it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Warriors' Lesson"],
            battlefield=["Grizzly Bears", "Forest"],
            library=["Mountain"] * 5,
        )
        .player("bob", life=20, library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Warriors' Lesson", auto=True, targets=[bears])
    granted = "Whenever this creature deals combat damage to a player, draw a card."
    assert granted in bears.granted_ability_texts

    scenario.start_at(Step.END_STEP)
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    # Entering the cleanup step already ran its own turn-based actions
    # (CR 514.1/514.2) and put the revoke trigger on the stack (CR 514.3a).
    scenario.pass_until_resolved()

    assert granted not in bears.granted_ability_texts


def test_launch_the_fleet_grants_the_attack_trigger_and_it_fires():
    """The reported card itself, end to end: "any number of target creatures
    each gain "Whenever this creature attacks, create a 1/1 white Soldier
    creature token that's tapped and attacking."" - Elvish Mystic attacks
    and a Soldier token appears already attacking beside it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Launch the Fleet"],
            battlefield=["Elvish Mystic", "Plains"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "alice")
    scenario.cast_and_resolve("Launch the Fleet", auto=True, targets=[mystic])
    granted = (
        "Whenever this creature attacks, create a 1/1 white Soldier creature "
        "token that's tapped and attacking."
    )
    assert granted in mystic.granted_ability_texts

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(mystic)
    scenario.pass_until_resolved()  # the granted attack trigger

    soldiers = [state for state in scenario.game.battlefield if state.name == "Soldier Token"]
    assert len(soldiers) == 1
    assert soldiers[0].tapped
    assert soldiers[0] in scenario.attackers()

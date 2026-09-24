"""Copying spells (CR 707.10: a copy is put onto the stack and is not cast;
CR 707.10c: "you may choose new targets for the copy").

- Loki Laufeyson: "{1}, {T}: When you next cast an instant or sorcery spell
  with mana value less than or equal to Loki's power this turn, copy that
  spell. You may choose new targets for the copy." - a delayed triggered
  ability (CR 603.7) that waits for the next *matching* spell, compared
  against Loki's power when that spell is cast.
- Fin Fang Foom: "Whenever you cast an instant or sorcery spell that targets
  an artifact or land, copy that spell. You may choose new targets for the
  copy. Put two +1/+1 counters on Fin Fang Foom."
- Photon Blast Barrage: "When you cast this spell, copy it X times. You may
  choose new targets for the copies. / Photon Blast Barrage deals 1 damage to
  target creature." - a triggered ability of the spell on the stack
  (CR 113.6k), not part of its resolution.

Off-set proofs (legal, in no deck list):

- Dual Strike: "When you next cast an instant or sorcery spell with mana
  value 4 or less this turn, copy that spell." - the same delayed copy with a
  fixed bound, on a spell rather than an ability.
- Show of Confidence: "When you cast this spell, copy it for each other
  instant and sorcery spell you've cast this turn." - the same cast trigger
  with a counted number of copies.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

LOKI = "Loki Laufeyson"
FOOM = "Fin Fang Foom"
BARRAGE = "Photon Blast Barrage"


def _life(scenario, username):
    return scenario.player(username).life


# -- Loki Laufeyson -------------------------------------------------------------------


def _loki_board(hand, *, lands=6):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[LOKI] + ["Mountain"] * lands,
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )


def _activate_loki(scenario):
    loki = scenario.creature(LOKI, "alice")
    loki.summoning_sick = False
    scenario.activate(loki, *scenario.untapped_sources("Mountain"), index=0)
    scenario.pass_until_resolved()
    return loki


def test_loki_copies_the_next_cheap_instant():
    scenario = _loki_board(["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_loki(scenario)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()  # the copy trigger
    scenario.pass_until_resolved()  # the copy
    scenario.pass_until_resolved()  # the Bolt

    assert _life(scenario, "bob") == 14


def _resolve_everything(scenario):
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


def test_loki_waits_past_a_spell_above_his_power_then_copies_the_cheap_one():
    """A -1/-1 counter leaves Loki at power 1: Smash to Smithereens (mana
    value 2) is above it and is not copied - and the delayed ability, which
    waits for the next *matching* spell, is still there to copy the Bolt
    (mana value 1)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smash to Smithereens", "Lightning Bolt"],
            battlefield=[LOKI] + ["Mountain"] * 4,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Mind Stone"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = _activate_loki(scenario)
    scenario.game.add_counters(loki, Counter.MINUS_ONE, 1)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")

    scenario.cast_onto_stack(
        "Smash to Smithereens", *scenario.untapped_sources("Mountain", "Mountain"), targets=[stone]
    )
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 17  # no copy
    assert len(scenario.game.delayed_triggers.triggers) == 1

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _resolve_everything(scenario)

    assert _life(scenario, "bob") == 11


def test_lokis_power_is_read_when_the_spell_is_cast():
    """Counters put on Loki after the activation count: with a -1/-1 and his
    power-up's two +1/+1 counters he is at power 3, and Smash to Smithereens
    (mana value 2) is copied."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Smash to Smithereens"],
            battlefield=[LOKI] + ["Mountain"] * 3,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Mind Stone"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    loki = _activate_loki(scenario)
    scenario.game.add_counters(loki, Counter.MINUS_ONE, 1)
    scenario.game.add_counters(loki, Counter.PLUS_ONE, 2)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    scenario.will_take_the_may(False)  # the copy keeps its target

    scenario.cast_onto_stack(
        "Smash to Smithereens", *scenario.untapped_sources("Mountain", "Mountain"), targets=[stone]
    )
    _resolve_everything(scenario)

    # The copy resolved first (destroying the Stone and dealing 3); the
    # original then found its only target gone (CR 608.2b).
    assert stone.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 17
    assert not scenario.game.delayed_triggers.triggers


def test_lokis_copy_expires_at_end_of_turn():
    scenario = _loki_board(["Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_loki(scenario)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    assert not scenario.game.delayed_triggers.triggers


def test_loki_does_not_copy_a_creature_spell():
    scenario = _loki_board(["Goblin Guide", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _activate_loki(scenario)
    scenario.cast_and_resolve("Goblin Guide", *scenario.untapped_sources("Mountain"))

    assert len(scenario.game.delayed_triggers.triggers) == 1


# -- Dual Strike (off-set proof) -------------------------------------------------------


def test_dual_strike_copies_the_next_instant_with_mana_value_four_or_less():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dual Strike", "Lightning Bolt"],
            battlefield=["Mountain"] * 3,
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Dual Strike", *scenario.untapped_sources("Mountain", "Mountain"))

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert _life(scenario, "bob") == 14


# -- Fin Fang Foom ------------------------------------------------------------------------


def _foom_board(hand, bob=(), *, lands=2):
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[FOOM] + ["Mountain"] * lands,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )


def test_fin_fang_foom_copies_an_artifact_removal_spell_and_grows():
    scenario = _foom_board(["Smash to Smithereens"], ["Mind Stone", "Ornithopter"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    thopter = scenario.creature("Ornithopter", "bob")
    foom = scenario.creature(FOOM, "alice")
    scenario.will_take_the_may(True)  # choose new targets for the copy
    scenario.will_choose_targets(thopter)

    scenario.cast_onto_stack(
        "Smash to Smithereens", *scenario.untapped_sources("Mountain", "Mountain"), targets=[stone]
    )
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()

    assert foom.counters[Counter.PLUS_ONE] == 2
    assert stone.zone is Zone.GRAVEYARD
    assert thopter.zone is Zone.GRAVEYARD
    assert _life(scenario, "bob") == 14  # 3 from each


def test_fin_fang_foom_ignores_a_spell_that_targets_only_a_creature():
    scenario = _foom_board(["Lightning Bolt"], ["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    foom = scenario.creature(FOOM, "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )

    assert foom.counters[Counter.PLUS_ONE] == 0
    assert not scenario.game.stack


def test_fin_fang_foom_triggers_on_a_spell_that_targets_a_land():
    """Fumarole targets a creature and a land - it targets a land, so it is
    copied (the copy keeps both targets)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fumarole"],
            battlefield=[FOOM, "Swamp"] + ["Mountain"] * 4,
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears", "Forest"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")
    foom = scenario.creature(FOOM, "alice")
    scenario.will_take_the_may(False)  # keep the copy's targets

    scenario.cast_onto_stack(
        "Fumarole",
        *scenario.untapped_sources("Swamp", "Mountain", "Mountain", "Mountain", "Mountain"),
        targets=[bears, forest],
    )
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()

    assert foom.counters[Counter.PLUS_ONE] == 2
    assert forest.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD


def test_fin_fang_foom_does_not_see_an_opponents_spell():
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Smash to Smithereens"],
            battlefield=["Mountain", "Mountain"],
            library=["Forest"] * 5,
        )
        .player("alice", battlefield=[FOOM, "Mind Stone"], library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    foom = scenario.creature(FOOM, "alice")

    scenario.cast_and_resolve(
        "Smash to Smithereens",
        *scenario.untapped_sources("Mountain", "Mountain", username="bob"),
        username="bob",
        targets=[stone],
    )

    assert foom.counters[Counter.PLUS_ONE] == 0
    assert stone.zone is Zone.GRAVEYARD


# -- Photon Blast Barrage ------------------------------------------------------------------


def _cast_barrage(scenario, x_value, target):
    casting = scenario.cast(BARRAGE, username="alice", targets=[target])
    payment = casting.determine_cost(x_value=x_value)
    scenario.pay_with(payment, *scenario.untapped_sources(*["Mountain"] * (2 + x_value)))
    scenario.put_on_stack(casting)
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()


def _barrage_board(bob):
    return (
        Scenario()
        .player(
            "alice",
            hand=[BARRAGE],
            battlefield=["Mountain"] * 5 + ["Lecturing Scornmage"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )


def test_photon_blast_barrage_copies_itself_x_times():
    scenario = _barrage_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, times=None)  # the copies keep the Giant

    _cast_barrage(scenario, 2, giant)
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD  # three damage from three objects


def test_photon_blast_barrage_with_x_zero_makes_no_copy():
    scenario = _barrage_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _cast_barrage(scenario, 0, giant)

    assert giant.damage == 1


def test_photon_blast_barrage_copies_are_not_cast():
    """CR 707.10: a copy isn't cast - Lecturing Scornmage's cast trigger sees
    only the original."""
    scenario = _barrage_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scornmage = scenario.creature("Lecturing Scornmage", "alice")
    scenario.will_take_the_may(False, times=None)

    _cast_barrage(scenario, 2, giant)

    assert scornmage.counters[Counter.PLUS_ONE] == 1


# -- Show of Confidence (off-set proof) -----------------------------------------------------


def test_show_of_confidence_copies_itself_for_each_earlier_instant_or_sorcery():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Show of Confidence"],
            battlefield=["Mountain", "Plains", "Plains", "Grizzly Bears"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.will_take_the_may(False, times=None)

    scenario.cast_onto_stack(
        "Show of Confidence", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.pass_until_resolved()

    assert bears.counters[Counter.PLUS_ONE] == 2

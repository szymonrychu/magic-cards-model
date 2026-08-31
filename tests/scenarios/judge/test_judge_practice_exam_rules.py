"""Judge scenarios: rulings mined from the L2 practice exam.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1000** - L2 Practice Exam (Rules)

Twenty-five questions, of which two are buildable against this engine today and
are built here:

- Both players lose at the same state-based-action check, so the game is a draw
  (CR 104.4a) - the exam's Giant's Ire question, where the damage kills the
  opponent and the mandatory draw kills the caster.
- A spell with two targets, one of which has become illegal, still resolves
  (CR 608.2b) - the exam's Prey Upon plus Cloud Shift question.

The rest are recorded in `COVERED-waveA.md` rather than half-built: several are
already covered elsewhere in this directory (Leyline of the Void suppressing a
dies trigger, the intervening *if* rechecked on resolution), and several need
mechanics the engine does not have (X reaching an effect, the two-headed giant
variant, commander, copy effects, linked abilities).

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Everybody loses at once: CR 104.4a
# --------------------------------------------------------------------------


def test_a_lethal_hit_and_an_empty_library_at_the_same_check_draw_the_game():
    """The exam's Giant's Ire question: bob is dealt lethal damage by a spell
    that also makes alice draw from an empty library.

    CR 704.5a puts a player at 0 or less life out of the game; CR 704.5b does
    the same to "a player [who] attempted to draw a card from a library with no
    cards in it since the last time state-based actions were checked". Both
    conditions are met at the same check, both players leave, and CR 104.4a
    says: "If all the players remaining in a game lose simultaneously, the game
    is a draw."

    The damage is dealt by a real Lightning Bolt rather than by the exam's own
    Giant's Ire, whose "deal 4 damage ... If you control a Giant, draw a card"
    has no entry in `machines/effects.py` - the draw is therefore performed
    through `Game.draw_cards`, the same call the draw step makes, so the failed
    draw is recorded exactly as CR 121.4 describes.
    """
    scenario = (
        Scenario()
        .player("alice", life=20, library=[], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", life=3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.game.draw_cards("alice", 1)
    scenario.resolve_top()

    assert scenario.game.drawn
    assert scenario.game.winner is None
    assert sorted(scenario.game.losers) == ["alice", "bob"]


def test_one_player_losing_alone_is_a_win_for_the_other():
    """The control case, so the draw above is not just "both flags set".

    CR 704.5a alone removes bob, and with a player still in the game there is a
    winner rather than a draw.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            library=["Grizzly Bears"],
            hand=["Lightning Bolt"],
            battlefield=["Mountain"],
        )
        .player("bob", life=3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert not scenario.game.drawn
    assert scenario.game.winner == "alice"


def test_the_failed_draw_alone_loses_the_game_for_the_drawer():
    """The other half of the pair, isolated: CR 121.4's "A player who attempts
    to draw a card from a library with no cards in it loses the game the next
    time a player would receive priority."

    Nothing happens at the moment of the draw - the loss is CR 704.5b's
    state-based action, so it waits for the check.
    """
    scenario = Scenario().player("alice", library=[]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 1)

    assert scenario.game.losers == []

    scenario.state_based_actions()

    assert scenario.game.losers == ["alice"]
    assert scenario.game.winner == "bob"


# --------------------------------------------------------------------------
# One illegal target of two: CR 608.2b
# --------------------------------------------------------------------------


def test_a_fight_spell_with_one_illegal_target_still_resolves():
    """The exam's Prey Upon question. Prey Upon's real text, confirmed with
    `resolve_cards`: "Target creature you control fights target creature you
    don't control."

    CR 608.2b: "If all its targets, for every instance of the word *target*, are
    now illegal, the spell or ability doesn't resolve." One of two is not all of
    two, so the spell resolves - and then does as much as it can, which with one
    of the two fighters gone is nothing at all.

    bob's creature is killed with a Bolt in response rather than blinked, which
    makes the target illegal for the same CR 608.2b reason (it is no longer in
    the zone it was in when it was targeted).

    Only the *resolves rather than fizzles* half is evidence here: Prey Upon has
    no entry in `machines/effects.py`, so no fight would have happened even with
    both targets legal. The last assertion is kept because it is the exam's own
    stated outcome, not because the engine earned it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prey Upon", "Lightning Bolt"],
            battlefield=["Forest", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Hill Giant", "bob")

    (forest,) = scenario.untapped_sources("Forest", username="alice")
    prey = scenario.cast_onto_stack("Prey Upon", forest, username="alice", targets=[mine, theirs])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[theirs])
    scenario.resolve_top()  # the Bolt kills the Hill Giant

    assert theirs.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # Prey Upon

    assert prey.id not in scenario.game.fizzled
    assert prey.zone is Zone.GRAVEYARD
    assert mine.zone is Zone.BATTLEFIELD
    assert mine.damage == 0

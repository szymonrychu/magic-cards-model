"""Generic replacement shapes read straight off oracle text: doubling/tripling
damage a source deals (CR 701.10g), and "prevent that damage and mill instead"
(CR 615.1a, CR 701.17a).

Both are compiled by `machines/replacement.py`'s `_compile_damage_multiplier`
and `_compile_prevent_damage_and_mill` on a `REPLACEMENTS` registry miss, with
no per-card row - the DDR#830 gap `tests/scenarios/judge/test_judge_replacement_effects.py`
first found: Furnace of Rath and The Mindskinner both parsed into a real
`ReplacementKind` and still did nothing at the table. This file is the
non-judge coverage for the same two shapes, plus Angel of Suffering as a second
card sharing the mill shape with a different subject and multiplier - proof the
compiler reads the wording rather than being bent to fit one card.

Every CR number here was looked up with `knowledge_search(type="rules")`:
- **CR 701.10g** - "To double an amount of damage a source would deal, that
  source instead deals twice that much damage. This is a replacement effect."
- **CR 615.1a** - "Effects that use the word 'prevent' are prevention effects."
- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Furnace of Rath: doubling damage from *any* source
# --------------------------------------------------------------------------


def test_furnace_of_rath_doubles_a_bolt():
    """CR 701.10g. A plain 3-damage Bolt becomes 6."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Furnace of Rath"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == starting_life - 6


def test_furnace_of_rath_doubles_damage_from_either_players_sources():
    """ "A source would deal damage" - not "a source *you* control". Furnace of
    Rath doubles everyone's damage, including its own controller's opponent's.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Furnace of Rath"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("alice").life

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.player("alice").life == starting_life - 6


def test_furnace_of_rath_doubles_combat_damage_too():
    """ "A source would deal damage to a permanent or player" names no event
    kind, so combat damage doubles the same as a spell's.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hill Giant", "Furnace of Rath"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "alice")
    starting_life = scenario.player("bob").life

    scenario.attack_with(giant)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == starting_life - 6


def test_two_furnaces_of_rath_do_not_apply_twice_to_one_event():
    """CR 614.5: each Furnace gets one opportunity, but CR 616.2 re-runs the
    choice against the now-doubled event, so two Furnaces quadruple rather than
    doubling once or stacking additively.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Furnace of Rath", "Furnace of Rath"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == starting_life - 12


# --------------------------------------------------------------------------
# The Mindskinner: prevent damage you deal to an opponent, that opponent mills
# --------------------------------------------------------------------------


def test_the_mindskinner_prevents_its_controllers_damage_and_mills_the_opponent():
    """DDR#830's Mindskinner half, outside the judge file: alice's own Bolt to
    bob deals 0 and bob mills 3 - the amount the Bolt would have dealt.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "The Mindskinner"],
        )
        .player("bob", library=["Forest", "Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == starting_life, "the damage was prevented, not dealt"
    assert len(scenario.player("bob").graveyard) == 3
    assert len(scenario.player("bob").library) == 1


def test_the_mindskinner_leaves_an_opponents_own_damage_alone():
    """ "A source *you control*" - The Mindskinner only watches its own
    controller's damage, not damage an opponent deals.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Mindskinner"], library=["Forest"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("alice").life

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.player("alice").life == starting_life - 3
    assert len(scenario.player("alice").library) == 1, "no mill from an opponent's own Bolt"


# --------------------------------------------------------------------------
# Angel of Suffering: prevent damage dealt *to you*, doubling the mill
# --------------------------------------------------------------------------


def test_angel_of_suffering_prevents_damage_to_its_controller_and_doubles_the_mill():
    """The same "prevent and mill" shape as The Mindskinner, on a different
    subject ("damage would be dealt to you", not "a source you control ...")
    and a different multiplier ("twice that many", not the same amount) - proof
    the compiler reads the two wordings rather than assuming one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Angel of Suffering"],
            library=["Forest"] * 6,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("alice").life

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.player("alice").life == starting_life, "prevented, not dealt"
    assert len(scenario.player("alice").graveyard) == 6, "twice the 3 damage prevented"


def test_angel_of_suffering_does_not_catch_damage_to_its_controllers_opponent():
    """ "Damage would be dealt to *you*" - Angel of Suffering only watches
    damage aimed at its own controller.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Angel of Suffering"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == starting_life - 3
    assert len(scenario.player("bob").library) == 1, "no mill from damage aimed at the opponent"


# --------------------------------------------------------------------------
# CR 616.1: doubling and prevent-and-mill competing for the same event
# --------------------------------------------------------------------------


def test_furnace_of_rath_and_the_mindskinner_together_pick_one_or_the_other():
    """DDR#830's full scenario, restated here without the judge file's xfail
    scaffolding: CR 616.1 gives bob's damage's affected player - here alice, the
    Mindskinner's own controller - the choice between doubling and
    prevent-and-mill. Either is a legal outcome; "3 damage and nothing else" is
    not, because that would mean neither replacement effect applied at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Furnace of Rath", "The Mindskinner"],
        )
        .player("bob", library=["Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    life_lost = starting_life - scenario.player("bob").life
    assert life_lost in (0, 6), "3 alone means neither replacement fired"
    if life_lost == 0:
        assert len(scenario.player("bob").graveyard) == 3

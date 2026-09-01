"""Judge scenarios: targets that stop being legal while the spell waits.

Sourced from the DDR judge transcripts. Episodes covered:

- **DDR#814** - Chaos Warp vs. Commander (the target left the zone; the spell is
  countered on resolution)
- **DDR#694** - Tom Bombadil + Elspeth Conquers Death (some targets illegal, at
  least one still legal)
- **DDR#71** - Electrolyze + Mother of Runes (protection makes a chosen target
  illegal after the fact)
- **DDR#995** - Run Away Together + Eldrazi Spawn (a target sacrificed for mana
  *while paying for the very spell targeting it*, and the spell resolving for
  the target that is left)

CR 608.2b is the whole file: as a spell resolves it rechecks its targets, "a
target that's no longer in the zone it was in when it was targeted is illegal",
and a spell with no legal targets left does not resolve. Every CR number here
was looked up with `knowledge_search(type="rules")`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_bolt_whose_only_target_was_exiled_in_response_does_nothing():
    """DDR#814: the target changed zones, so the spell is countered by the rules.

    CR 608.2b: the target is no longer in the zone it was in when it was
    targeted, so it is illegal; with no legal targets left the spell "doesn't
    resolve" and is put into its owner's graveyard from the stack. None of its
    effects happen - not even the ones that do not mention the target.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Swords to Plowshares"], battlefield=["Plains", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bears])

    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", plains, username="bob", targets=[bears])

    scenario.resolve_top()  # Swords resolves first: last in, first out (CR 608)
    assert bears.zone is Zone.EXILE

    scenario.resolve_top()  # and now the Bolt has nothing legal left

    assert spell.zone is Zone.GRAVEYARD
    assert spell.id in scenario.game.fizzled
    # Swords already resolved (the earlier assertion) and gained bob life
    # equal to the Bears' power (2) before the Bolt ever got a turn to fizzle
    # - that life gain is Swords' own effect, not one of the Bolt's, so the
    # Bolt fizzling clean is still "no effects at all" for the Bolt itself.
    assert scenario.player("bob").life == 22, "no effects at all, not even redirected ones"


def test_a_bolt_still_resolves_if_its_target_merely_gained_damage():
    """The control: only *illegality* stops resolution, not any change (CR 608.2b).

    "Other changes to the game state may cause a target to no longer be legal" -
    but a creature that simply took damage is still a creature on the
    battlefield, so the Bolt resolves normally.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Lightning Bolt", "Lightning Bolt"], battlefield=["Mountain", "Mountain"]
        )
        .player("bob", battlefield=["Questing Beast"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    beast = scenario.creature("Questing Beast", "bob")

    first, second = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", first, username="alice", targets=[beast])
    scenario.cast_and_resolve("Lightning Bolt", second, username="alice", targets=[beast])
    assert beast.damage == 3 and beast.zone is Zone.BATTLEFIELD

    scenario.resolve_top()

    assert spell.id not in scenario.game.fizzled
    assert beast.zone is Zone.GRAVEYARD


def test_a_two_target_spell_resolves_for_whichever_target_is_still_legal():
    """DDR#694: one illegal target does not counter the spell.

    CR 608.2b: the spell is only countered if *all* its targets are illegal. It
    otherwise resolves, doing as much as it can for the targets that remain -
    and its untargeted half (Electrolyze's card draw) happens either way.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Electrolyze"],
            battlefield=["Island", "Mountain", "Mountain"],
            library=["Preordain"],
        )
        .player(
            "bob",
            hand=["Swords to Plowshares"],
            battlefield=["Plains", "Grizzly Bears", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    doomed, survivor = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="bob")

    sources = scenario.untapped_sources("Island", "Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Electrolyze", *sources, username="alice", targets=[doomed, survivor])

    scenario.pass_priority("alice")
    (plains,) = scenario.untapped_sources("Plains", username="bob")
    scenario.cast_onto_stack("Swords to Plowshares", plains, username="bob", targets=[doomed])
    scenario.resolve_top()

    scenario.resolve_top()

    assert survivor.damage == 1
    assert len(scenario.player("alice").hand) == 1, "the draw happens regardless"


def test_protection_gained_in_response_makes_the_creature_an_illegal_target():
    """DDR#71: the target stays in its zone but stops being legal anyway.

    CR 702.16b: "A permanent or player with protection can't be targeted by
    spells with the stated quality." Mother of Runes grants protection from red
    after the Bolt is already on the stack; CR 608.2b rechecks legality on
    resolution and finds none, so the Bolt is countered.

    The announcement itself was legal - the protection did not exist yet - so
    this is the recheck doing the work, not CR 601.2c. That is the whole point
    of the ruling: protection gained *in response* is what kills the spell.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Plains", "Mother of Runes"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.creature("Mother of Runes", "bob")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    spell = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[mother])

    # bob activates Mother of Runes targeting herself, choosing red. The colour
    # is CR 608.2d's choice and has to be answered: left to the default table
    # the ability would choose white, and a red Bolt would resolve untouched.
    scenario.will_choose("R", username="bob", source="Mother of Runes")
    scenario.game.activate_ability(mother, 0, "bob", targets=[mother])
    scenario.resolve_top()

    scenario.resolve_top()

    assert spell.id in scenario.game.fizzled
    assert mother.zone is Zone.BATTLEFIELD
    assert mother.damage == 0


# --------------------------------------------------------------------------
# DDR#995 - a target sacrificed for mana in the middle of its own spell's cast
# --------------------------------------------------------------------------


def _run_away_together_board() -> "Scenario":
    """Alice holds Run Away Together and controls a Goblin she can sacrifice
    for mana; bob has the creature she actually wants bounced.

    Skirk Prospector ("Sacrifice a Goblin: Add {R}", confirmed with
    `resolve_cards`) stands in for the episode's Eldrazi Spawn token, which is
    not in the pool: both are a mana ability whose cost sacrifices a creature,
    which is the only property the ruling turns on.
    """
    return (
        Scenario()
        .player(
            "alice",
            hand=["Run Away Together"],
            battlefield=["Island", "Island", "Skirk Prospector", "Raging Goblin"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_a_target_sacrificed_for_mana_mid_cast_does_not_counter_the_spell():
    """DDR#995: targets are chosen before costs are paid, and one dead target
    out of two does not remove the spell from the stack.

    CR 601.2c is where "the player announces their choice of an appropriate
    object or player for each target"; CR 601.2g's chance to activate mana
    abilities and CR 601.2h's payment both come after it. So a creature that
    was legally targeted at 601.2c can be sacrificed for mana at 601.2g and the
    targeting is not undone.

    CR 608.2b then decides what resolution does: a target no longer in the zone
    it was in is illegal, but the spell is only removed from the stack if
    *every* target is. `Game.fizzled` is the engine's record of that removal
    (CR 608.2b's "doesn't resolve"), and Run Away Together is not in it - the
    same distinction `test_a_bolt_whose_only_target_was_exiled_in_response_does_nothing`
    above shows from the other side.
    """
    scenario = _run_away_together_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    prospector = scenario.creature("Skirk Prospector", "alice")
    islands = scenario.untapped_sources("Island", "Island")

    casting = scenario.cast("Run Away Together", targets=[goblin, bears])  # CR 601.2c
    payment = casting.begin_paying()

    scenario.activate(prospector, sacrificing=[goblin])  # CR 601.2g, CR 605.3a
    assert goblin.zone is Zone.GRAVEYARD

    scenario.pay_with(payment, *islands)  # CR 601.2h
    spell = scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert spell.id not in scenario.game.fizzled
    assert spell.zone is Zone.GRAVEYARD


def test_run_away_together_still_bounces_the_target_that_is_left():
    """DDR#995's actual payoff: bob's creature is returned to his hand.

    Run Away Together (confirmed with `resolve_cards`): "Choose two target
    creatures controlled by different players. Return those creatures to their
    owners' hands." With alice's own target already in the graveyard, CR 608.2b
    leaves the spell resolving for the target that remains legal - "If all its
    targets, for every instance of the word 'target,' are now illegal, the
    spell or ability doesn't resolve", and one of two is not all of them.

    CR 400.3 puts the survivor in its *owner's* hand: "If an object would go to
    any library, graveyard, or hand other than its owner's, it goes to its
    owner's corresponding zone."
    """
    scenario = _run_away_together_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    prospector = scenario.creature("Skirk Prospector", "alice")
    islands = scenario.untapped_sources("Island", "Island")

    casting = scenario.cast("Run Away Together", targets=[goblin, bears])
    payment = casting.begin_paying()
    scenario.activate(prospector, sacrificing=[goblin])
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND


def test_run_away_together_refuses_two_creatures_the_same_player_controls():
    """DDR#995's card, read strictly: "creatures controlled by different players".

    CR 601.2c: "The player announces their choice of an appropriate object or
    player for each target the spell requires" - appropriate meaning it matches
    every restriction the spell states, so two creatures alice controls are not
    a legal announcement and the cast should be refused before any cost is
    determined.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Run Away Together"],
            battlefield=["Island", "Island", "Grizzly Bears", "Raging Goblin"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Raging Goblin", "alice")

    with pytest.raises(ValueError):
        scenario.cast("Run Away Together", targets=[bears, goblin])

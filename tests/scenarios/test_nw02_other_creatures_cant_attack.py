"""A spell's rider "Other creatures can't attack this turn." (and its blocking
twin), read as a restriction on every creature except the one the spell named.

Rules verified with `mise run rules:find`:

- **CR 508.1c** - the active player checks each creature they control against
  any restriction "(effects that say a creature can't attack ...)"; a
  declaration that disobeys one is illegal.
- **CR 509.1b** - the same for blockers and "can't block" effects.
- **CR 611.2a** - the effect lasts as long as stated ("this turn").
- **CR 611.2c** - the set an effect fixes when it begins is only for effects
  that change characteristics or control; a restriction is not one, so a
  creature that enters later this turn is restricted too.
- **CR 608.2b** - a spell whose only target is illegal on resolution does
  nothing, the rider included.
- **CR 509.1c** - "blocks this turn if able" is a requirement to block.

Reported card: Intimidation Bolt ("... deals 3 damage to target creature.
Other creatures can't attack this turn."). Second printing: Mark for Death
("Target creature an opponent controls blocks this turn if able. Untap that
creature. Other creatures that player controls can't block this turn."),
which proves the "other" exclusion on the blocking side, scoped to one player.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _bolt_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Intimidation Bolt", "Hill Giant"],
            battlefield=[
                "Mountain",
                "Plains",
                "Plains",
                "Serra Angel",
                "Grizzly Bears",
                "Goblin Guide",
            ],
        )
        .player("bob", battlefield=["Gray Ogre", "Runeclaw Bear"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_bolt(scenario, target) -> None:
    sources = scenario.untapped_sources("Mountain", "Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Intimidation Bolt", *sources, username="alice", targets=[target])


def test_intimidation_bolt_deals_damage_and_stops_every_other_creature_attacking():
    scenario = _bolt_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Goblin Guide", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    _cast_bolt(scenario, ogre)
    scenario.state_based_actions()

    assert ogre.zone is Zone.GRAVEYARD
    assert _notices(scenario) == []

    scenario.start_at(Step.DECLARE_ATTACKERS)
    for creature in (bears, goblin, angel):
        assert not scenario.can_attack(creature)
    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.attack_with(bears)


def test_the_creature_the_bolt_targeted_is_the_one_exception():
    scenario = _bolt_board()
    angel = scenario.creature("Serra Angel", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_bolt(scenario, angel)  # 3 damage does not kill a 4/4
    scenario.state_based_actions()
    assert angel.zone is Zone.BATTLEFIELD

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(angel)
    assert not scenario.can_attack(bears)
    scenario.attack_with(angel)
    assert [c.id for c in scenario.attackers()] == [angel.id]


def test_a_creature_that_enters_later_this_turn_cannot_attack_either():
    """CR 611.2c: a restriction is not a locked-in set."""
    scenario = _bolt_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    _cast_bolt(scenario, ogre)
    late = scenario.put_onto_battlefield("Hill Giant", username="alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    late.summoning_sick = False
    assert not scenario.can_attack(late)


def test_the_restriction_is_about_attacking_only():
    scenario = _bolt_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_bolt(scenario, ogre)

    lines = scenario.game.characteristics_of(bears).abilities
    assert "This creature can't attack." in lines
    assert "This creature can't block." not in lines


def test_the_restriction_ends_with_the_turn():
    scenario = _bolt_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_bolt(scenario, ogre)
    assert "This creature can't attack." in scenario.game.characteristics_of(bears).abilities

    scenario.game.continuous_effects.end_the_turn(scenario.game)
    assert "This creature can't attack." not in scenario.game.characteristics_of(bears).abilities


def test_a_bolt_whose_only_target_became_illegal_restricts_nobody():
    """CR 608.2b."""
    scenario = _bolt_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Plains", "Plains", username="alice")
    scenario.cast_onto_stack("Intimidation Bolt", *sources, username="alice", targets=[ogre])
    scenario.game.return_to_hand(ogre)
    scenario.pass_until_resolved()

    assert "This creature can't attack." not in scenario.game.characteristics_of(bears).abilities
    assert _notices(scenario) == []


# -- second printing: Mark for Death -------------------------------------------


def _mark_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mark for Death"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Gray Ogre"],
        )
        .player("bob", battlefield=["Hill Giant", "Runeclaw Bear", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_mark(scenario, target) -> None:
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Mark for Death", *sources, username="alice", targets=[target])


def test_mark_for_death_untaps_the_target_and_other_creatures_of_that_player_cannot_block():
    scenario = _mark_board()
    giant = scenario.creature("Hill Giant", "bob")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    ogre = scenario.creature("Gray Ogre", "alice")
    giant.tap()
    _cast_mark(scenario, giant)

    assert giant.untapped
    assert _notices(scenario) == []
    lines = scenario.game.characteristics_of(runeclaw).abilities
    assert "This creature can't block." in lines
    assert "This creature can't block." not in scenario.game.characteristics_of(giant).abilities
    assert "This creature can't block." not in scenario.game.characteristics_of(ogre).abilities

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ogre)
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")
    assert scenario.step is Step.DECLARE_BLOCKERS
    # CR 509.1c: the requirement made the targeted creature block, so the
    # engine declared it as a blocker at the start of the declare blockers step.
    assert [c.id for c in scenario.blockers()] == [giant.id]
    # CR 509.1b: the other creatures of that player cannot be added.
    with pytest.raises(ValueError, match="can't block"):
        scenario.block(ogre, runeclaw)
    assert [c.id for c in scenario.blockers()] == [giant.id]

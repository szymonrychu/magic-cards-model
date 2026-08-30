"""Scenario: which targets a spell may legally be announced with (CR 115).

CR 601.2c has the caster announce "an appropriate object or player for each
target the spell requires", and appropriate is decided by the spell's own
words. An announcement that breaks that is not a spell that resolves badly - it
is a spell that was never cast, so the card stays in hand and nothing is tapped
(CR 601.6).

CR 115.2 is the zone half of the same question: only permanents are legal
targets unless the spell says it reaches somewhere else.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def test_a_creature_spell_cannot_be_aimed_at_a_player():
    """Swords to Plowshares says "target creature"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="cannot target the player"):
        scenario.cast("Swords to Plowshares", username="alice", targets=["bob"])

    assert scenario.find("Swords to Plowshares", Zone.HAND, "alice").zone is Zone.HAND
    assert all(state.untapped for state in scenario.game.battlefield)


def test_a_player_spell_cannot_be_aimed_at_a_creature():
    """Lava Spike says "target player or planeswalker" - a creature is neither."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lava Spike"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    with pytest.raises(ValueError, match="needs a planeswalker"):
        scenario.cast("Lava Spike", username="alice", targets=[bears])


def test_a_player_spell_takes_a_player():
    scenario = (
        Scenario()
        .player("alice", hand=["Lava Spike"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    spike = scenario.cast_and_resolve(
        "Lava Spike", *scenario.untapped_sources("Mountain"), username="alice", targets=["bob"]
    )

    assert spike.zone is Zone.GRAVEYARD


def test_a_counterspell_cannot_target_a_permanent_on_the_battlefield():
    """ "Target spell" reaches the stack and nowhere else (CR 115.2)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Counterspell"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    with pytest.raises(ValueError, match="needs a target in the stack"):
        scenario.cast("Counterspell", username="alice", targets=[bears])


def test_a_spell_that_reaches_a_graveyard_cannot_be_aimed_at_the_battlefield():
    """Raise Dead reads "target creature card from your graveyard"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Raise Dead"],
            battlefield=["Swamp", "Grizzly Bears"],
            graveyard=["Questing Beast"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    living = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    with pytest.raises(ValueError, match="needs a target in the graveyard"):
        scenario.cast("Raise Dead", username="alice", targets=[living])


def test_the_same_spell_takes_the_card_in_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Raise Dead"],
            battlefield=["Swamp"],
            graveyard=["Questing Beast"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dead = scenario.find("Questing Beast", Zone.GRAVEYARD, "alice")

    casting = scenario.cast("Raise Dead", username="alice", targets=[dead])

    assert casting.targets[0].card_id == dead.id


def test_a_spell_that_wants_an_opponents_creature_refuses_your_own():
    """Craterous Stomp reads "target creature an opponent controls"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Craterous Stomp"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.untapped_sources("Grizzly Bears", username="alice")[0]

    with pytest.raises(ValueError, match="which alice controls"):
        scenario.cast("Craterous Stomp", username="alice", targets=[mine])

    theirs = scenario.untapped_sources("Grizzly Bears", username="bob")[0]
    casting = scenario.cast("Craterous Stomp", username="alice", targets=[theirs])
    assert casting.targets[0].card_id == theirs.id


def test_a_tapped_only_target_refuses_an_untapped_creature():
    """Swallow Whole exiles "target tapped creature"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swallow Whole"], battlefield=["Plains", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.untapped_sources("Grizzly Bears", username="bob")[0]

    with pytest.raises(ValueError, match="needs a tapped permanent"):
        scenario.cast("Swallow Whole", username="alice", targets=[theirs])


def test_more_targets_than_the_spell_takes_is_illegal():
    """CR 601.2c: one appropriate choice per target the spell requires."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    both = scenario.untapped_sources("Grizzly Bears", "Grizzly Bears", username="bob")

    with pytest.raises(ValueError, match="too many targets"):
        scenario.cast("Swords to Plowshares", username="alice", targets=both)


def test_a_spell_with_no_targets_at_all_refuses_one():
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError, match="too many targets"):
        scenario.cast("Grizzly Bears", username="alice", targets=["bob"])


def test_a_two_target_spell_needs_one_of_each_kind():
    """Fumarole destroys "target creature and target land"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Fumarole"], battlefield=["Swamp", "Mountain"] * 3)
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    creatures = scenario.untapped_sources("Grizzly Bears", "Grizzly Bears", username="bob")
    forest = scenario.untapped_sources("Forest", username="bob")[0]

    with pytest.raises(ValueError, match="illegal target"):
        scenario.cast("Fumarole", username="alice", targets=creatures)

    casting = scenario.cast("Fumarole", username="alice", targets=[creatures[0], forest])
    assert len(casting.targets) == 2


def test_an_illegal_target_leaves_the_board_untouched():
    """CR 601.6: an illegal announcement rewinds to before it started."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", username="alice")[0]

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Swords to Plowshares", plains, username="alice", targets=["bob"])

    assert plains.untapped
    assert scenario.game.stack_is_empty
    assert scenario.find("Swords to Plowshares", Zone.HAND, "alice").zone is Zone.HAND

"""Scenario: state-based actions (CR 704).

The mechanic is the checks the game performs on its own whenever a player would
receive priority (CR 704.3), controlled by no player (CR 704.2) and using no
stack. Lethal damage (CR 704.5g) and a player at zero life (CR 704.5a) have
their own files - `test_removal.py` and `test_damage_to_players.py` - so this
file covers the rest of the list the model can express, and the ordering rules
around them.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

# -- CR 704.5f: toughness 0 or less -----------------------------------------


def test_a_creature_with_toughness_zero_is_put_into_the_graveyard():
    """CR 704.5f: "If a creature has toughness 0 or less, it's put into its
    owner's graveyard."

    Hangarback Walker is printed 0/0 and is only ever a creature at all because
    of the +1/+1 counters it enters with (CR 122). Counters are not modelled, so
    a Hangarback Walker put straight onto the battlefield is a real 0/0 - which
    makes it the honest test of this rule rather than a contrived one.
    """
    scenario = Scenario().player("alice", battlefield=["Hangarback Walker"]).player("bob").build()
    walker = scenario.creature("Hangarback Walker", username="alice")

    scenario.game.check_state_based_actions()

    assert walker.zone is Zone.GRAVEYARD
    assert "Hangarback Walker" not in scenario.battlefield_names()


def test_toughness_zero_needs_no_damage_at_all():
    """CR 704.5f is separate from CR 704.5g: nothing has to have dealt damage."""
    scenario = Scenario().player("alice", battlefield=["Hangarback Walker"]).build()
    walker = scenario.creature("Hangarback Walker", username="alice")
    assert walker.damage == 0

    scenario.game.check_state_based_actions()

    assert walker.zone is Zone.GRAVEYARD


def test_a_positive_toughness_creature_survives_the_same_check():
    """The control case: CR 704.5f only fires at 0 or less."""
    scenario = Scenario().player("alice", battlefield=["Memnite", "Grizzly Bears"]).build()

    scenario.game.check_state_based_actions()

    assert sorted(scenario.battlefield_names()) == ["Grizzly Bears", "Memnite"]


# -- CR 704.5b: a draw from an empty library --------------------------------


def test_a_player_who_tried_to_draw_from_an_empty_library_loses():
    """CR 704.5b: "If a player attempted to draw a card from a library with no
    cards in it since the last time state-based actions were checked, that
    player loses the game." (CR 104.3c, CR 121.4.)
    """
    scenario = Scenario().player("alice", library=["Mountain"]).player("bob").build()
    bob = scenario.player("bob")
    assert bob.draw_up_to(1) == [], "an empty library gives nothing"

    scenario.game.check_state_based_actions()

    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


def test_the_loss_is_for_the_attempt_not_for_the_empty_library():
    """Corner case: an empty library on its own loses nobody anything.

    A player only loses once they have actually been asked to draw, which is
    why `Player.tried_to_draw_from_empty_library` exists as a separate flag.
    """
    scenario = Scenario().player("alice", library=[]).player("bob", library=[]).build()

    scenario.game.check_state_based_actions()

    assert scenario.game.players_in_game == [scenario.player("alice"), scenario.player("bob")]
    assert scenario.game.winner is None


def test_drawing_the_last_card_is_not_a_failed_draw():
    """The off-by-one: emptying the library is fine, drawing from empty is not."""
    scenario = Scenario().player("alice", library=["Mountain"]).player("bob").build()
    alice = scenario.player("alice")

    assert [state.name for state in alice.draw_up_to(1)] == ["Mountain"]
    assert not alice.tried_to_draw_from_empty_library

    scenario.game.check_state_based_actions()

    assert scenario.game.is_in_game("alice")


def test_a_short_draw_takes_what_is_there_and_still_loses():
    """CR 104.3c: "they draw the remaining cards and then lose the game"."""
    scenario = Scenario().player("alice", library=["Mountain"]).player("bob").build()
    alice = scenario.player("alice")

    drawn = alice.draw_up_to(3)

    assert [state.name for state in drawn] == ["Mountain"], "the one card is still drawn"
    scenario.game.check_state_based_actions()
    assert not scenario.game.is_in_game("alice")


# -- CR 704.5j: the legend rule ---------------------------------------------


def test_the_legend_rule_puts_the_extra_copy_into_the_graveyard():
    """CR 704.5j: "If two or more legendary permanents with the same name are
    controlled by the same player, that player chooses one of them, and the
    rest are put into their owners' graveyards."
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Questing Beast", "Questing Beast"])
        .player("bob")
        .build()
    )

    scenario.game.check_state_based_actions()

    assert scenario.battlefield_names() == ["Questing Beast"]
    assert [state.name for state in scenario.player("alice").graveyard] == ["Questing Beast"]


def test_the_legend_rule_leaves_exactly_one_of_three():
    """The rule keeps one, not one per pair."""
    scenario = Scenario().player("alice", battlefield=["Questing Beast"] * 3).build()

    scenario.game.check_state_based_actions()

    assert scenario.battlefield_names() == ["Questing Beast"]
    assert len(scenario.player("alice").graveyard) == 2


def test_the_legend_rule_is_per_player():
    """Corner case: "controlled by the same player" is the whole condition.

    Two players may each keep their own copy; only one controller having two is
    the trigger.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Questing Beast"])
        .player("bob", battlefield=["Questing Beast"])
        .build()
    )

    scenario.game.check_state_based_actions()

    assert scenario.battlefield_names() == ["Questing Beast", "Questing Beast"]


def test_the_legend_rule_applies_to_a_land_too():
    """CR 205.4d: any permanent with the legendary supertype is subject to it."""
    scenario = Scenario().player("alice", battlefield=["Urborg, Tomb of Yawgmoth"] * 2).build()

    scenario.game.check_state_based_actions()

    assert scenario.battlefield_names() == ["Urborg, Tomb of Yawgmoth"]


def test_two_different_legends_both_stay():
    """The rule is name-based, not supertype-based."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Questing Beast", "Urborg, Tomb of Yawgmoth"])
        .build()
    )

    scenario.game.check_state_based_actions()

    assert sorted(scenario.battlefield_names()) == [
        "Questing Beast",
        "Urborg, Tomb of Yawgmoth",
    ]


def test_a_nonlegendary_duplicate_is_untouched():
    """Grizzly Bears is not legendary, so four of them coexist happily."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"] * 4).build()

    scenario.game.check_state_based_actions()

    assert len(scenario.battlefield_names()) == 4


# -- CR 704.3: when and how often the check runs ----------------------------


def test_state_based_actions_run_before_anyone_gets_priority():
    """CR 704.3: the check happens whenever a player *would* get priority.

    Nobody calls it here; resolving the Bolt is what runs it, and the 0/0 that
    was already on the battlefield goes at the same time as the burned creature.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Hangarback Walker"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    walker = scenario.creature("Hangarback Walker", username="bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD, "CR 704.5g"
    assert walker.zone is Zone.GRAVEYARD, "CR 704.5f, in the same check"


def test_a_check_that_changes_the_game_is_repeated():
    """CR 704.3: perform all applicable actions, then check again.

    Alice is at 1 life and has a 0/0 out. The first round removes the 0/0 and
    takes alice out for being at 0 life; the repeat finds nothing left to do
    and the last player standing has won (CR 104.2a).
    """
    scenario = (
        Scenario().player("alice", life=0, battlefield=["Hangarback Walker"]).player("bob").build()
    )
    walker = scenario.creature("Hangarback Walker", username="alice")

    gone = scenario.game.check_state_based_actions()

    assert walker in gone
    assert scenario.game.winner == "bob"

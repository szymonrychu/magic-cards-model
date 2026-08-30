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

    `Game.retain_priority` now runs that check too (CR 117.3c is such a moment),
    so a 0-toughness creature already on the battlefield would not survive to
    see the Bolt resolve - it dies the instant the Bolt is put on the stack and
    the caster is handed priority back. To keep this test's point (several
    state-based actions performed together, CR 704.3's "single event"), the
    Walker is put onto the battlefield *after* the Bolt is already on the
    stack, with no priority-check moment in between, so both it and the bolted
    Bears are only found invalid at the same check: the one the Bolt's
    resolution triggers.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"],
        )
        .player("bob", hand=["Hangarback Walker"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", username="bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bears])
    walker = scenario.put_onto_battlefield("Hangarback Walker", username="bob")
    scenario.resolve_top()

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


# -- the reported defect: SBAs after a mutating path other than resolving ---
#
# Bob played a second Flagstones of Trokair while already controlling one and
# both stayed on the battlefield through a priority pass. The cause:
# `Game.play_land` (CR 116.2a's special action, no stack, no priority change)
# left nothing to catch the duplicate, and `Game.pass_priority` only ever
# checked state-based actions indirectly, through `resolve_top`, when the
# stack had something to resolve - never on a plain pass with an empty stack.
# `Game.retain_priority`, the other place CR 117.3c hands priority back
# without a pass (after casting or activating), had the same gap. All three
# now run `Game._check_state_based_actions_and_stack_triggers` first.


def test_a_second_legendary_land_dies_on_the_next_priority_pass():
    """The reported defect, reproduced exactly: play a second Flagstones of
    Trokair while already controlling one, then pass priority. CR 116.2a means
    playing the land changes nothing about who holds priority, so both copies
    are legally on the battlefield until the moment CR 704.3 next applies -
    which `pass_priority` must check before acting on the pass.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Flagstones of Trokair"], battlefield=["Flagstones of Trokair"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first = scenario.find("Flagstones of Trokair", Zone.BATTLEFIELD, "alice")

    scenario.play_land("Flagstones of Trokair", "alice")
    assert len(scenario.battlefield_names()) == 2, "both are legal until the next check"

    scenario.pass_priority("alice")

    assert scenario.battlefield_names() == ["Flagstones of Trokair"]
    assert scenario.find("Flagstones of Trokair", Zone.BATTLEFIELD, "alice") is first, (
        "the docstring on `_legend_rule_losers` keeps the first copy on the "
        "battlefield rather than asking the controller - deterministic, so "
        "this holds on every run"
    )
    assert [state.name for state in scenario.player("alice").graveyard] == ["Flagstones of Trokair"]


def test_a_second_legendary_creature_from_a_non_cast_effect_dies_too():
    """Different card, different mutating path: a permanent that reaches the
    battlefield without being cast (the Tooth and Nail shape, CR 601 does not
    apply) is exactly as invisible to the legend rule until the next priority
    check as a played land is. `put_onto_battlefield` puts no ability on the
    stack and does not call `retain_priority`, so only the general fix in
    `pass_priority` catches this.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ragavan, Nimble Pilferer"],
            battlefield=["Ragavan, Nimble Pilferer"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Ragavan, Nimble Pilferer", username="alice")
    assert len(scenario.battlefield_names()) == 2

    scenario.pass_priority("alice")

    assert scenario.battlefield_names() == ["Ragavan, Nimble Pilferer"]
    assert len(scenario.player("alice").graveyard) == 1


def test_the_legend_rule_still_leaves_each_players_own_copy_after_a_land_drop():
    """Fail-open risk: the legend rule is per controller (CR 704.5j says
    "controlled by the same player"). Two different players each playing their
    own Flagstones of Trokair must not collide just because the general SBA
    check now runs after every land drop.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Flagstones of Trokair"], battlefield=["Flagstones of Trokair"])
        .player("bob", battlefield=["Flagstones of Trokair"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Flagstones of Trokair", "alice")
    scenario.pass_priority("alice")

    assert len(scenario.game.permanents_controlled_by("alice")) == 1, (
        "the legend rule caught alice's own duplicate"
    )
    assert len(scenario.game.permanents_controlled_by("bob")) == 1, (
        "CR 704.5j is per controller - bob's copy is untouched by alice's check"
    )
    assert scenario.player("alice").graveyard != []
    assert scenario.player("bob").graveyard == []


def test_a_legendary_entering_and_another_dying_share_one_check():
    """Fail-open risk: a legendary permanent entering while a different
    permanent is already dying must be handled in the same CR 704.3 pass
    without either condition interfering with the other. The Bolt is put on
    the stack, then a second Flagstones is put straight onto the battlefield
    (no stack, no priority moment of its own) before the Bolt resolves, so
    both the lethal damage and the legend rule are only found by the one
    check the Bolt's resolution triggers.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Flagstones of Trokair"],
            battlefield=["Mountain", "Flagstones of Trokair", "Ragavan, Nimble Pilferer"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", username="alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[ragavan])
    scenario.put_onto_battlefield("Flagstones of Trokair", username="alice")
    scenario.resolve_top()

    assert ragavan.zone is Zone.GRAVEYARD, "CR 704.5g: lethal damage from the Bolt"
    remaining = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Flagstones of Trokair"
    ]
    assert len(remaining) == 1, "CR 704.5j: the legend rule, caught in the same check"

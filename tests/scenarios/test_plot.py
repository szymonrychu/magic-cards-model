"""Plot: exile it now, cast it later (CR 702.170, CR 116.2k).

Two halves, and they are two different rules.

**The special action.** CR 116.2k: "A player who has a card with plot in their
hand may exile that card. This is a special action." CR 702.170b says it does
not use the stack, and CR 702.170a puts it in a main phase with the stack empty.
The plot cost is paid to *put the card away*.

**The permission.** CR 702.170d: "A plotted card's owner may cast it from exile
without paying its mana cost during their main phase while the stack is empty
during any turn after the turn in which it became plotted."

That last clause is why exile needs an annotation at all (CR 406.4): exile is a
public zone full of otherwise identical cards, and "which of these may I cast"
is answered by which pile a card is in and when it got there.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile, keyword_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Slickshot Show-Off"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Island"])
    )


def plot_it(scenario) -> None:
    """Alice takes the plot special action on the Slickshot Show-Off in her hand."""
    card = scenario.find("Slickshot Show-Off", Zone.HAND, "alice")
    action = MarkedExile.plot(scenario.game, card, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.pay_with(action.begin_paying(), *sources)
    action.take()


def alices_next_turn(scenario) -> None:
    """Walk the turn machine round until it is alice's turn again."""
    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            return
    raise AssertionError("never got back to alice's main phase")


# -- the special action -----------------------------------------------------


def test_plotting_exiles_the_card_and_marks_the_pile():
    """CR 702.170c: the card becomes plotted, which is a fact about the exile pile."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    plot_it(scenario)

    plotted = scenario.find("Slickshot Show-Off", Zone.EXILE)
    assert plotted.zone is Zone.EXILE
    assert plotted.exile_annotation is not None
    assert plotted.exile_annotation.marker is ExileMarker.PLOTTED
    assert plotted.exile_annotation.owner == "alice"
    assert plotted.exile_annotation.turn_exiled == scenario.turn.turn_number


def test_plotting_costs_the_plot_cost_and_does_not_use_the_stack():
    """CR 116.1: a special action does not use the stack, so nothing lands on it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    plot_it(scenario)

    assert scenario.game.stack_is_empty
    assert all(source.tapped for source in scenario.game.permanents_controlled_by("alice"))


def test_plot_is_refused_outside_a_main_phase():
    """CR 702.170a: "Any time you have priority during your main phase"."""
    scenario = board().build()
    scenario.start_at(Step.UPKEEP)

    card = scenario.find("Slickshot Show-Off", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="main phase"):
        MarkedExile.plot(scenario.game, card, "alice")


def test_plot_is_refused_on_someone_elses_turn():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alices_next_turn(scenario)  # bob's turn comes first
    while scenario.turn.active_player == "alice":
        scenario.advance()
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()

    card = scenario.find("Slickshot Show-Off", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="main phase"):
        MarkedExile.plot(scenario.game, card, "alice")


def test_a_card_without_plot_cannot_be_plotted():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND)

    with pytest.raises(ValueError, match="no plot ability"):
        MarkedExile.plot(scenario.game, bears, "alice")


# -- casting it later -------------------------------------------------------


def test_casting_the_plotted_card_without_announcing_plot_is_refused():
    """The `test_flashback.py` live-game defect, generalized to plot:
    CR 702.170d's exile permission does not exist apart from Plot's own "cast
    it ... without paying its mana cost" - a caster who never calls
    `use_keyword("Plot")` gets no permission at all to cast from exile, not a
    fallback to the printed mana cost. The mere existence of the option (the
    card is plotted, it is a later turn, alice is the owner) is not CR
    601.2b's announced choice.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)
    alices_next_turn(scenario)
    # `manual_turn_based_actions()` means nothing untaps automatically - the
    # Mountains spent on the plot special action stay tapped across the
    # manual `advance()` loop in `alices_next_turn`, so this test (unlike its
    # neighbours, which cast Plot for free) untaps them itself to pay a real
    # mana cost.
    for mountain in scenario.game.permanents_controlled_by("alice"):
        mountain.untap()

    sources = scenario.untapped_sources("Mountain", "Mountain")
    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)
    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")
    scenario.pay_with(casting.begin_paying(), *sources)

    with pytest.raises(ValueError, match="Plot"):
        casting.cast()
    casting.cancel()

    assert scenario.find("Slickshot Show-Off", Zone.EXILE, "alice").zone is Zone.EXILE
    assert all(source.untapped for source in sources)


def test_a_plotted_card_cannot_be_cast_on_the_turn_it_was_plotted():
    """CR 702.170d: "during any turn after the turn in which it became plotted"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="later turn"):
        casting.use_keyword("Plot")


def test_a_plotted_card_is_cast_from_exile_on_a_later_turn_for_nothing():
    """CR 702.170d: cast "without paying its mana cost" - so the total cost is {0}."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)
    alices_next_turn(scenario)

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")

    assert casting.total_cost.mana == ManaCost()
    assert casting.base_cost == ManaCost.parse("{1}{R}")

    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    bird = scenario.resolve_top()

    assert bird.zone is Zone.BATTLEFIELD
    assert bird not in scenario.game.exile


def test_the_annotation_is_gone_once_the_card_leaves_exile():
    """CR 400.7: it is a new object, so its old pile means nothing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)
    alices_next_turn(scenario)

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")
    casting.begin_paying().pay()
    bird = scenario.put_on_stack(casting)

    assert bird.exile_annotation is None


def test_an_unmarked_card_in_exile_cannot_be_cast_with_plot():
    """A Slickshot Show-Off exiled by something else is not a plotted card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", exile=["Slickshot Show-Off"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)

    with pytest.raises(ValueError, match="not plotted"):
        casting.use_keyword("Plot")


def test_only_the_owner_may_cast_a_plotted_card():
    """CR 702.170d says "A plotted card's owner", not whoever finds it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)
    alices_next_turn(scenario)

    plotted = scenario.find("Slickshot Show-Off", Zone.EXILE)
    (option,) = keyword_cast_options(plotted.card)

    assert option.why_not(plotted, "bob", scenario.game) is not None
    assert option.why_not(plotted, "alice", scenario.game) is None


def test_plot_only_as_a_sorcery_blocks_casting_it_in_the_opponents_turn():
    """CR 702.170d: main phase, stack empty - which is sorcery timing."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plot_it(scenario)
    alices_next_turn(scenario)
    while scenario.turn.active_player == "alice":
        scenario.advance()

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE, username="alice")

    with pytest.raises(ValueError, match="only be used as a sorcery"):
        casting.use_keyword("Plot")

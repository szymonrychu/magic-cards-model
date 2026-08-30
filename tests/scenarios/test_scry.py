"""Scenario: scry, and the decision inside it (CR 701.22).

Scry is the smallest complete example of the thing the engine could not do
before: a resolving effect that stops and asks its controller a question. The
Modern metagame sweep in `docs/engine-coverage.md` deliberately left Preordain
unregistered rather than paper over the scry with a bare draw, and this file is
what makes registering it honest.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, and the full text of each
was then read out of the `2026-08-19` Comprehensive Rules release that
`knowledge_search(type="cr_versions")` names as current, downloaded from the
`source_url` it gives and verified against its published sha256
(`4381ad1b39ab2c05f7d03633a20f711ed37277074d3266dcba5f38cbb527423f`).

- **CR 701.22a** - "To 'scry N' means to look at the top N cards of your
  library, then put any number of them on the bottom of your library in any
  order and the rest on top of your library in any order." Three freedoms in one
  sentence: how many go to the bottom, in what order, and in what order the rest
  come back.
- **CR 701.22b** - "If a player is instructed to scry 0, no scry event occurs.
  Abilities that trigger whenever a player scries won't trigger." A scry 0 is
  not a scry that does nothing; it is not a scry.
- **CR 701.22c** - a simultaneous multi-player scry decides in APNAP order
  (CR 101.4). No card in the pool does this, so it is not covered here.
- **CR 701.22d** - a "whenever a player scries" trigger fires after the whole
  process, "even if some or all of those actions were impossible". Nothing emits
  a scry event yet - see `docs/engine-coverage.md`.
- **CR 608.2d** - the rule that makes any of this possible: "If an effect of a
  spell or ability offers any choices ... the player announces these while
  applying the effect."

The scry itself is `Game.scry`; the scenario answers it with
`scry_bottoming` / `scry_keeping_everything_on_top`. Most of this file drives
`Game.scry` directly, so that one rule is being tested at a time; the section at
the bottom runs the same rule through Preordain, which has a
`machines/effects.py` entry now.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _library(*names: str) -> Scenario:
    """One player with a known library, top-first, and nothing else going on."""
    return Scenario().manual_turn_based_actions().player("alice", library=list(names))


def _names(scenario, count: int = 5) -> list[str]:
    return [state.card.name for state in scenario.player("alice").library[:count]]


def test_scry_two_leaves_the_library_alone_when_both_stay_on_top():
    """CR 701.22a: "put any number of them on the bottom" - and none is a number.

    The happy path, and the one that shows a scry is not obliged to move
    anything. A rigged library that nobody chose to disturb is still rigged.
    """
    scenario = _library("Island", "Mountain", "Forest", "Swamp").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.scry_keeping_everything_on_top()

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Island", "Mountain", "Forest", "Swamp"]


def test_a_card_put_on_the_bottom_goes_under_everything_else():
    """CR 701.22a: "on the bottom of your library".

    The bottom, not "one from the bottom" and not "after the cards it was looked
    at with" - the whole rest of the library goes above it.
    """
    scenario = _library("Island", "Mountain", "Forest", "Swamp").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.top_of_library(2)
    scenario.scry_bottoming(island)

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Mountain", "Forest", "Swamp", "Island"]
    assert mountain.zone is Zone.LIBRARY, "a card kept on top never left the library"


def test_both_cards_can_go_to_the_bottom_and_keep_the_order_they_were_named_in():
    """CR 701.22a: "any number of them on the bottom of your library in any order".

    Two freedoms at once. The order they are named in is the order they land in,
    so a scenario can say which of the two bottomed cards ends up deepest.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.top_of_library(2)
    scenario.scry_bottoming(mountain, island)

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Forest", "Mountain", "Island"]


def test_the_cards_kept_on_top_can_be_reordered():
    """CR 701.22a: "and the rest on top of your library in any order".

    The half of the rule that is easy to miss. Keeping both cards is not the
    same as leaving them alone: their relative order is the player's to choose,
    and swapping the top two is a legal scry that moves nothing to the bottom.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island, mountain) = scenario.top_of_library(2)
    scenario.scry_bottoming(top_order=[mountain, island])

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Mountain", "Island", "Forest"]


def test_scry_zero_is_not_a_scry_at_all():
    """CR 701.22b: "If a player is instructed to scry 0, no scry event occurs."

    The distinction is invisible in the library - nothing moves either way - so
    it is asserted where it is visible: no question was ever put to the player.
    That is also what CR 701.22b's second sentence turns on, since a trigger
    that watches for scrying needs an event to watch.
    """
    scenario = _library("Island", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.scry("alice", 0, source="Preordain")

    assert scenario.questions_asked() == []
    assert _names(scenario) == ["Island", "Mountain"]


def test_scrying_more_cards_than_the_library_holds_looks_at_what_is_there():
    """CR 701.22a says to look at the top N; a library with fewer has fewer.

    Not the same as CR 701.22b's scry 0: this *is* a scry event, and the player
    is asked about the cards that exist. Drawing from an empty library has a
    rule of its own (CR 121.3) and scrying does not, so the shortfall is simply
    fewer cards to decide about.
    """
    scenario = _library("Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.top_of_library(1)
    scenario.scry_bottoming(island)

    scenario.game.scry("alice", 3, source="Preordain")

    asked = scenario.questions_asked()
    assert [question.kind for question in asked] == [DecisionKind.SCRY]
    assert asked[0].amount == 3, "the instruction was still scry 3"
    assert len(asked[0].cards) == 1, "only one card was there to look at"
    assert _names(scenario) == ["Island"], "one card cannot change places with itself"


def test_scrying_an_empty_library_asks_about_nothing_and_moves_nothing():
    """A scry with no cards to look at. CR 701.22b exempts only scry *0*.

    So the event happens, the player is asked, and every answer is the same one.
    Nothing here loses the game: CR 704.5b is about a player who *tried to draw*
    from an empty library, and scrying is not drawing.
    """
    scenario = _library().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.scry("alice", 2, source="Preordain")

    assert len(scenario.questions_asked()) == 1
    assert scenario.player("alice").library == []
    assert scenario.game.winner is None


def test_the_question_says_which_card_asked_it():
    """CR 608.2d asks "the player"; a scenario needs to know which effect asked.

    The source is carried on the question so an answer can be aimed at one card
    - a board with two things that scry should not have the first answer
    swallowed by whichever resolves first.
    """
    scenario = _library("Island", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.scry_keeping_everything_on_top()

    scenario.game.scry("alice", 1, source="Preordain")

    (question,) = scenario.questions_asked()
    assert question.source == "Preordain"
    assert question.player == "alice"
    assert question.prompt == "scry 1"


def test_an_unanswered_scry_keeps_everything_on_top():
    """The documented default, asserted so a change to it breaks a test.

    `machines/decisions.default_answer` keeps every card on top, because
    CR 701.22a permits it and because it is the only default that leaves a
    rigged library rigged - a scenario that stacked its top card to reach a turn
    would otherwise have it silently bottomed.
    """
    scenario = _library("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.scry("alice", 2, source="Preordain")

    assert _names(scenario) == ["Island", "Mountain", "Forest"]


def test_one_scripted_answer_is_spent_by_one_scry():
    """An answer is for a question, not for a game.

    Two scries and one queued answer: the first takes it, the second falls back
    to the default. Otherwise a scenario that meant to bottom one card would
    quietly bottom every card it ever looked at.
    """
    scenario = _library("Island", "Mountain", "Forest", "Swamp").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.top_of_library(1)
    scenario.scry_bottoming(island)

    scenario.game.scry("alice", 1, source="Preordain")
    scenario.game.scry("alice", 1, source="Preordain")

    assert _names(scenario) == ["Mountain", "Forest", "Swamp", "Island"]


# -- through a real card ---------------------------------------------------
#
# Preordain: "Scry 2, then draw a card." One card that puts CR 701.22a and
# CR 608.2c in the same sentence.


def _preordain(*library: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=list(library), hand=["Preordain"], battlefield=["Island"])
        .player("bob")
    )


def test_preordain_scries_and_then_draws_what_the_scry_left_on_top():
    """CR 608.2c: "The controller of the spell or ability follows its
    instructions in the order written."

    That order is the whole card. Bottoming the top card with the scry means the
    draw takes the *second* card, and asserting on which card was drawn is the
    only way to prove the two halves happened in the printed order rather than
    at the same time.
    """
    scenario = _preordain("Island", "Mountain", "Forest", "Swamp").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island, _mountain = scenario.top_of_library(2)
    scenario.scry_bottoming(island)

    (source,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Preordain", source, username="alice")

    assert [state.card.name for state in scenario.player("alice").hand] == ["Mountain"]
    assert _names(scenario) == ["Forest", "Swamp", "Island"]


def test_preordain_asks_its_question_naming_itself():
    """CR 608.2d puts the choice to "the player" - the spell's controller - and
    the question carries the card that asked it.

    Which matters for a scenario with two scries in flight: an answer scripted
    against a source only answers that card's question.
    """
    scenario = _preordain("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (source,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Preordain", source, username="alice")

    (asked,) = scenario.questions_asked()
    assert asked.kind is DecisionKind.SCRY
    assert asked.player == "alice"
    assert asked.source == "Preordain"
    assert asked.amount == 2


def test_preordain_keeps_the_top_card_when_nobody_bottoms_anything():
    """The default answer, through the card: "put any number of them on the
    bottom" (CR 701.22a) and none is a number, so a rigged top card survives
    Preordain and is what gets drawn.
    """
    scenario = _preordain("Island", "Mountain", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (source,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Preordain", source, username="alice")

    assert [state.card.name for state in scenario.player("alice").hand] == ["Island"]
    assert _names(scenario) == ["Mountain", "Forest"]


def test_preordain_on_a_one_card_library_scries_what_is_there_and_draws_it():
    """CR 701.22a says "the top N cards", and a library with fewer than N has
    fewer to look at; nothing about the scry fails.

    The draw that follows then empties the library, which is not a loss on its
    own - CR 104.3c only takes effect when a player *would* draw from an empty
    library, at the next state-based action check.
    """
    scenario = _preordain("Island").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (source,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_and_resolve("Preordain", source, username="alice")

    (asked,) = scenario.questions_asked()
    assert len(asked.cards) == 1, "only one card to look at"
    assert [state.card.name for state in scenario.player("alice").hand] == ["Island"]
    assert scenario.player("alice").library == []

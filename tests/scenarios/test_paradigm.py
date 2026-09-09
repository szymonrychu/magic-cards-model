"""Paradigm (CR 702.192): exile-instead-of-graveyard, plus a delayed trigger
that keeps handing out free copies for the rest of the game.

Every CR number here was looked up with `mise run rules:find` against the
2026-08-19 Comprehensive Rules in the session that wrote this file.

- **CR 702.192a** - "Paradigm represents two spell abilities, one of which
  creates a delayed triggered ability. Paradigm means 'If this is the first
  time a spell you control with this spell's name has resolved this game, at
  the beginning of each of your precombat main phases for the rest of the
  game, create a copy of this object in exile. You may cast the copy without
  paying its mana cost' and 'Exile this spell.'"
- **CR 603.7b** - "unless it has a stated duration" - "for the rest of the
  game" is exactly that, so the trigger's own `remaining` is unbounded.
- **CR 603.7c** - a delayed trigger that finds its object gone does not
  affect it.
- **CR 704.5e/707.10a** - "If a copy of a card is in any zone other than the
  stack or the battlefield, it ceases to exist" - the fate of a declined
  copy; see `machines/delayed.ParadigmCopyAndCast`'s own docstring for how
  this is settled without the general state-based action.

Improvisation Capstone is the deck-pool card: `{5}{R}{R}` Sorcery — Lesson,
"Exile cards from the top of your library until you exile cards with total
mana value 4 or greater. You may cast any number of spells from among them
without paying their mana costs." Its own resolution body has no registry
entry (out of scope for this wave - Paradigm is the mechanic under test, not
this specific card's mill-and-cast effect), so most of these tests assert on
the Paradigm scaffolding alone: exile, the delayed trigger, and the free
recast existing and resolving. Restoration Seminar - a second, differently
bodied Paradigm card ("Return target nonland permanent card from your
graveyard to the battlefield."), added with `scripts/add_card.py` - proves
the whole pipeline end to end, body effect and targeting included, on a card
that is not the deck-pool one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind, ScriptedAnswer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def run_to_next_precombat_main(scenario, username: str) -> None:
    """Walk the turn forward, resolving whatever is on the stack, until
    `username`'s own next precombat main phase begins - the same idiom
    `test_rebound.py`'s `run_to_erins_next_upkeep` uses for CR 603.3's own
    "the next time a player would receive priority"."""
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.PRECOMBAT_MAIN
        and scenario.game.active_player.username == username
    ):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def test_a_resolved_paradigm_spell_is_exiled_not_binned():
    """CR 702.192a's unconditional half: "Exile this spell.\""""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Improvisation Capstone"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 7))

    capstone = scenario.cast_and_resolve("Improvisation Capstone", *sources)

    assert capstone.zone is Zone.EXILE
    assert capstone not in scenario.player("alice").graveyard


def test_a_second_resolution_of_a_different_physical_copy_does_not_double_the_trigger():
    """CR 702.192a: "If this is the *first* time a spell you control with
    this spell's name has resolved this game" - a second, independently cast
    copy of the same-named card does not create a second delayed trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Improvisation Capstone", "Improvisation Capstone"],
            battlefield=["Mountain"] * 14,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first_sources = scenario.untapped_sources(*(["Mountain"] * 7))
    scenario.cast_and_resolve("Improvisation Capstone", *first_sources)
    second_sources = scenario.untapped_sources(*(["Mountain"] * 7))

    scenario.cast_and_resolve("Improvisation Capstone", *second_sources)

    from magic_cards_model.machines.delayed import ParadigmCopyAndCast

    matching = [
        trigger
        for trigger in scenario.game.delayed_triggers.triggers
        if isinstance(trigger.effect, ParadigmCopyAndCast)
        and trigger.controller == "alice"
        and trigger.source_name == "Improvisation Capstone"
    ]
    assert len(matching) == 1


def test_the_delayed_trigger_offers_a_free_copy_at_the_next_precombat_main():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Improvisation Capstone"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 7))
    scenario.cast_and_resolve("Improvisation Capstone", *sources)
    scenario.will_take_the_may(True, username="alice", times=None)

    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()  # the delayed trigger: create + cast the copy

    on_stack = [state for state in scenario.game.stack if state.name == "Improvisation Capstone"]
    assert len(on_stack) == 1
    assert scenario.game.controller_of(on_stack[0]).username == "alice"
    assert on_stack[0].is_copy is True


def test_declining_the_free_copy_leaves_it_ceasing_to_exist():
    """CR 704.5e/707.10a: a card copy left anywhere but the stack or the
    battlefield ceases to exist - a declined copy does not linger in exile."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Improvisation Capstone"],
            battlefield=["Mountain"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Mountain"] * 7))
    scenario.cast_and_resolve("Improvisation Capstone", *sources)
    scenario.will_take_the_may(False, username="alice", times=None)

    run_to_next_precombat_main(scenario, "alice")
    exile_before = len(scenario.game.exile)
    scenario.resolve_top()  # the delayed trigger: create the copy, decline the cast

    assert len(scenario.game.exile) == exile_before
    assert scenario.game.stack_is_empty


# -- generality: a second, differently bodied Paradigm printing -------------


def test_restoration_seminar_a_differently_bodied_paradigm_card_recasts_and_replays():
    """Restoration Seminar - "Return target nonland permanent card from your
    graveyard to the battlefield." - is not the deck-pool card and has
    nothing in common with Improvisation Capstone's own effect. Both the
    original cast and the delayed trigger's free recast actually reanimate a
    creature, proving `machines/delayed.ParadigmCopyAndCast`/`Game.
    cast_free_from_exile` generalise past the deck-pool printing, targeting
    included.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Restoration Seminar"],
            battlefield=["Plains"] * 14,
            graveyard=["Grizzly Bears", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (first_bear, second_bear) = alice.graveyard
    first_sources = scenario.untapped_sources(*(["Plains"] * 7))

    scenario.cast_and_resolve("Restoration Seminar", *first_sources, targets=[first_bear])

    assert first_bear.zone is Zone.BATTLEFIELD
    assert first_bear not in alice.graveyard

    scenario.will_take_the_may(True, username="alice", times=None)
    scenario.game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_TARGETS,
            value=(second_bear.id,),
            player="alice",
            source=None,
            uses=None,
        )
    )

    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()  # the delayed trigger: create + cast the free copy
    scenario.resolve_top()  # the copy itself resolving

    assert second_bear.zone is Zone.BATTLEFIELD
    assert second_bear not in alice.graveyard
    recast_copies = [
        state
        for state in scenario.game.exile
        if state.name == "Restoration Seminar" and state.is_copy
    ]
    assert len(recast_copies) == 1
    assert recast_copies[0].zone is Zone.EXILE

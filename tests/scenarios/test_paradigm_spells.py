"""Paradigm spells (CR 702.192a) whose own first sentence has to resolve too.

`test_paradigm.py` proves the keyword's scaffolding - "Exile this spell." and
the delayed trigger that offers a free copy "at the beginning of each of your
precombat main phases for the rest of the game". This file is about the other
half of every Paradigm card: the spell's own printed effect, which the
keyword line must not hide, resolving both on the original cast and on every
free copy.

- **Germination Practicum** - "Put two +1/+1 counters on each creature you
  control." A spell-side group counter placement (CR 122.1), counted off the
  computed board (CR 613.5) and only for the caster's own creatures.
- **Improvisation Capstone** - its exile-until/free-cast body (see
  `test_exile_until_cast.py` for the body itself); here, that body runs and
  *then* Paradigm exiles the spell and hands out the copy.
- **Decorum Dissertation** - the second Paradigm printing, off the deck pool:
  "Target player draws two cards and loses 2 life."
- **Basri's Solidarity** - the second printing of the spell-side counter
  sentence, off the deck pool and not a Paradigm card: "Put a +1/+1 counter
  on each creature you control."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

PRACTICUM = "Germination Practicum"
CAPSTONE = "Improvisation Capstone"


def run_to_next_precombat_main(scenario: Scenario, username: str) -> None:
    turns = scenario.turn.turns_taken
    while not (
        scenario.turn.turns_taken > turns
        and scenario.step is Step.PRECOMBAT_MAIN
        and scenario.game.active_player.username == username
    ):
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
        scenario.advance()


def _practicum_board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[PRACTICUM],
            battlefield=["Forest"] * 5 + ["Grizzly Bears", "Memnite", "Sol Ring"],
        )
        .player("bob", battlefield=["Tarmogoyf"])
    )


def test_germination_practicum_puts_two_counters_on_each_creature_you_control():
    scenario = _practicum_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    goyf = scenario.creature("Tarmogoyf", "bob")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    practicum = scenario.cast_and_resolve(PRACTICUM, *scenario.untapped_sources(*["Forest"] * 5))

    assert bears.counters[Counter.PLUS_ONE] == 2
    assert memnite.counters[Counter.PLUS_ONE] == 2
    assert goyf.counters[Counter.PLUS_ONE] == 0
    assert ring.counters[Counter.PLUS_ONE] == 0
    assert scenario.game.characteristics_of(bears).power == 4
    assert practicum.zone is Zone.EXILE


def test_germination_practicum_with_no_creatures_still_resolves_and_is_exiled():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[PRACTICUM], battlefield=["Forest"] * 5)
        .player("bob", battlefield=["Tarmogoyf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = scenario.creature("Tarmogoyf", "bob")

    practicum = scenario.cast_and_resolve(PRACTICUM, *scenario.untapped_sources(*["Forest"] * 5))

    assert practicum.zone is Zone.EXILE
    assert goyf.counters[Counter.PLUS_ONE] == 0


def test_germination_practicums_free_copy_puts_two_more_counters_each_main_phase():
    scenario = _practicum_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(PRACTICUM, *scenario.untapped_sources(*["Forest"] * 5))
    scenario.will_take_the_may(True, username="alice", times=None)

    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()  # the delayed trigger: create and cast the copy
    scenario.resolve_top()  # the copy
    assert bears.counters[Counter.PLUS_ONE] == 4

    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()
    scenario.resolve_top()
    assert bears.counters[Counter.PLUS_ONE] == 6
    copies = [s for s in scenario.game.exile if s.name == PRACTICUM and s.is_copy]
    assert copies == []


def test_the_copy_counts_creatures_as_it_resolves_not_as_the_original_did():
    """CR 608.2c: a creature that arrived after the original resolved gets
    the copy's counters too, and one that has left gets nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[PRACTICUM, "Memnite"],
            battlefield=["Forest"] * 5 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(PRACTICUM, *scenario.untapped_sources(*["Forest"] * 5))
    memnite = scenario.cast_and_resolve("Memnite")
    assert memnite.counters[Counter.PLUS_ONE] == 0
    scenario.game.destroy(bears)

    scenario.will_take_the_may(True, username="alice", times=None)
    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()
    scenario.resolve_top()

    assert memnite.counters[Counter.PLUS_ONE] == 2
    assert bears.zone is Zone.GRAVEYARD
    assert bears.counters[Counter.PLUS_ONE] == 0


def test_basris_solidarity_reads_the_same_spell_side_sentence():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Basri's Solidarity"],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Memnite"],
        )
        .player("bob", battlefield=["Tarmogoyf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    goyf = scenario.creature("Tarmogoyf", "bob")

    solidarity = scenario.cast_and_resolve(
        "Basri's Solidarity", *scenario.untapped_sources("Plains", "Plains")
    )

    assert bears.counters[Counter.PLUS_ONE] == 1
    assert memnite.counters[Counter.PLUS_ONE] == 1
    assert goyf.counters[Counter.PLUS_ONE] == 0
    assert solidarity.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Improvisation Capstone: the body, then Paradigm
# --------------------------------------------------------------------------


def test_capstone_body_resolves_then_paradigm_exiles_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CAPSTONE],
            battlefield=["Mountain"] * 7,
            library=["Grizzly Bears", "Tarmogoyf", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, source=CAPSTONE)
    scenario.will_take_the_may(False, source=CAPSTONE)
    scenario.will_choose_cards(bears, source=CAPSTONE)
    capstone = scenario.cast_onto_stack(CAPSTONE, *scenario.untapped_sources(*["Mountain"] * 7))

    scenario.resolve_top()

    assert capstone.zone is Zone.EXILE
    assert scenario.stack_names() == ["Grizzly Bears"]
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD


def test_capstones_free_copy_runs_the_body_again_at_the_next_main_phase():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CAPSTONE],
            battlefield=["Mountain"] * 7,
            library=[
                "Island",
                "Tarmogoyf",
                "Grizzly Bears",
                "Tarmogoyf",
                "Grizzly Bears",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source=CAPSTONE)
    scenario.cast_and_resolve(CAPSTONE, *scenario.untapped_sources(*["Mountain"] * 7))
    assert [s.name for s in scenario.player("alice").library] == [
        "Tarmogoyf",
        "Grizzly Bears",
        "Forest",
    ]

    scenario.will_take_the_may(True, username="alice")  # the paradigm trigger's copy
    scenario.will_take_the_may(False, source=CAPSTONE)  # the copy's own "any number"
    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()  # the delayed trigger: create and cast the copy
    scenario.resolve_top()  # the copy: exiles until total mana value 4

    assert [s.name for s in scenario.player("alice").library] == ["Forest"]


def test_decorum_dissertation_second_paradigm_printing_resolves_body_and_copy():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Decorum Dissertation"],
            battlefield=["Swamp"] * 5,
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    dissertation = scenario.cast_and_resolve(
        "Decorum Dissertation", *scenario.untapped_sources(*["Swamp"] * 5), targets=["alice"]
    )

    assert dissertation.zone is Zone.EXILE
    assert len(alice.hand) == 2
    assert alice.life == 18

    scenario.will_take_the_may(True, username="alice", times=None)
    scenario.will_choose_targets("bob", source="Decorum Dissertation")
    run_to_next_precombat_main(scenario, "alice")
    scenario.resolve_top()
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert len(scenario.player("bob").hand) == 2

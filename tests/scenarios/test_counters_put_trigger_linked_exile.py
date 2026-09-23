"""Put a creature card exiled with this permanent onto the battlefield under
your control - Emperor of Bones' counters-put trigger, and the same linked-
exile reader on Sisters of Stone Death's activated ability.

    Whenever one or more +1/+1 counters are put on this creature, put a
    creature card exiled with this creature onto the battlefield under your
    control with a finality counter on it. It gains haste. Sacrifice it at
    the beginning of the next end step.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 607.2a** - "exiled with this creature" is the pile this object's own
  exiling ability made; a card exiled any other way is not in it.
- **CR 122.6** - "counters put on" an object includes counters put on it on
  the battlefield, which is what the trigger watches.
- **CR 701.46a** - Adapt N puts N +1/+1 counters only if the permanent has
  none, so a second adapt puts none and triggers nothing.
- **CR 122.1h** - a finality counter exiles the permanent instead of letting
  it go to a graveyard from the battlefield.
- **CR 603.7c** - the delayed sacrifice affects only the object put there.

Sisters of Stone Death is the proof printing: legal in Modern (Scryfall
legalities, 2026-09-23), in no deck under `magic-cards-model-api/decks/`, an
activated ability rather than a trigger, naming itself by name rather than
"this creature", with no counter and no end-step tail.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _resolve_stack(scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _emperor_board(bob_graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Emperor of Bones", "Swamp", "Swamp", "Swamp", "Swamp"],
            library=["Swamp"] * 5,
        )
        .player("bob", graveyard=bob_graveyard, library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.creature("Emperor of Bones")


def _exile_with_emperor(scenario, card) -> None:
    scenario.will_choose_targets(card)
    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)
    assert card.zone is Zone.EXILE


def _adapt(scenario, emperor) -> None:
    scenario.activate(emperor, *scenario.untapped_sources("Swamp", "Swamp"), index=0)
    _resolve_stack(scenario)


def test_emperor_puts_the_exiled_creature_under_your_control_with_finality_and_haste():
    scenario, emperor = _emperor_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    _exile_with_emperor(scenario, giant)

    _adapt(scenario, emperor)

    assert emperor.counter_count(Counter.PLUS_ONE) == 2
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(giant).username == "alice"
    assert giant.owner == "bob"
    assert giant.counter_count(Counter.FINALITY) == 1
    assert has_keyword(giant, "Haste", scenario.game)


def test_emperor_sacrifice_at_end_step_is_replaced_by_finality_exile():
    scenario, emperor = _emperor_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    _exile_with_emperor(scenario, giant)
    _adapt(scenario, emperor)

    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.EXILE, "CR 122.1h: exiled instead of the graveyard"


def test_emperor_with_nothing_exiled_puts_nothing():
    scenario, emperor = _emperor_board([])
    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)

    _adapt(scenario, emperor)

    assert emperor.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.battlefield_names().count("Emperor of Bones") == 1
    assert scenario.game.delayed_triggers.triggers == []


def test_emperor_ignores_a_noncreature_card_it_exiled():
    scenario, emperor = _emperor_board(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    _exile_with_emperor(scenario, bolt)

    _adapt(scenario, emperor)

    assert bolt.zone is Zone.EXILE


def test_emperor_ignores_a_creature_card_exiled_by_something_else():
    """CR 607.2a: a card exiled some other way is not exiled with Emperor."""
    scenario, emperor = _emperor_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    scenario.game.exile_permanent(giant)
    _walk_to(scenario, Step.BEGINNING_OF_COMBAT)

    _adapt(scenario, emperor)

    assert giant.zone is Zone.EXILE


def test_a_second_adapt_puts_no_counters_and_so_nothing_triggers():
    scenario, emperor = _emperor_board(["Hill Giant", "Grizzly Bears"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    _exile_with_emperor(scenario, giant)
    _adapt(scenario, emperor)
    giant_on_battlefield = giant.zone is Zone.BATTLEFIELD

    _adapt(scenario, emperor)

    assert emperor.counter_count(Counter.PLUS_ONE) == 2, "CR 701.46a: no new counters"
    assert giant_on_battlefield
    assert bears.zone is Zone.GRAVEYARD
    assert len(scenario.game.delayed_triggers.triggers) == 1, "only the first put made one"


def test_emperor_delayed_sacrifice_skips_a_creature_that_already_left():
    scenario, emperor = _emperor_board(["Hill Giant"])
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "bob")
    _exile_with_emperor(scenario, giant)
    _adapt(scenario, emperor)
    scenario.game.return_to_hand(giant)

    _walk_to(scenario, Step.END_STEP)

    assert giant.zone is Zone.HAND


# --------------------------------------------------------------------------
# Sisters of Stone Death - the proof printing
# --------------------------------------------------------------------------


def test_sisters_put_a_creature_they_exiled_onto_the_battlefield_under_your_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Sisters of Stone Death",
                "Swamp",
                "Swamp",
                "Swamp",
                "Forest",
                "Forest",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sisters = scenario.creature("Sisters of Stone Death")
    sisters.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(sisters)
    scenario.block(sisters, bears)

    swamp, *_ = scenario.untapped_sources("Swamp")
    forest, *_ = scenario.untapped_sources("Forest")
    scenario.activate(sisters, swamp, forest, index=1, targets=[bears])
    _resolve_stack(scenario)
    assert bears.zone is Zone.EXILE

    scenario.activate(sisters, *scenario.untapped_sources("Swamp", "Swamp", "Forest"), index=2)
    _resolve_stack(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(bears).username == "alice"
    assert bears.counter_count(Counter.FINALITY) == 0, "no counter printed on this one"


def test_sisters_with_nothing_exiled_put_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sisters of Stone Death", "Swamp", "Swamp", "Swamp"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisters = scenario.creature("Sisters of Stone Death")

    scenario.activate(sisters, *scenario.untapped_sources("Swamp", "Swamp", "Swamp"), index=2)
    _resolve_stack(scenario)

    assert scenario.battlefield_names().count("Grizzly Bears") == 0


def test_every_listed_clause_is_handled_by_the_sweep():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    for clause in card_support(card("Emperor of Bones")).clauses:
        if clause.kind == "keyword":
            continue
        assert clause.outcome == HANDLED, (clause.text, clause.outcome)
    for clause in card_support(card("Sisters of Stone Death")).clauses:
        if clause.kind == "keyword":
            continue
        assert clause.outcome == HANDLED, (clause.text, clause.outcome)

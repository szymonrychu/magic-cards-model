"""Scenario: a cost reduction that applies "as long as `<graveyard condition>`"
(CR 601.2f: "Some effects may increase or reduce the cost to pay").

Gran-Gran: "Noncreature spells you cast cost {1} less to cast as long as there
are three or more Lesson cards in your graveyard." - a static ability of a
permanent (CR 604.2) whose discount is on exactly while the condition holds
(CR 611.3a), read as the cost is determined. "Your graveyard" and "spells you
cast" are both Gran-Gran's controller's; a creature spell is not a
noncreature spell (CR 205.2b); the count is a gate, not a multiplier. A
generic reduction never touches coloured pips (CR 118.7a).

Drag to the Roots is the second printing: "Delirium - This spell costs {2}
less to cast as long as there are four or more card types among cards in
your graveyard." - the same "as long as" tail on a spell's own
self-reduction, with a different count (card types, CR 205.2a) - and the
spell still resolves ("Destroy target nonland permanent.") once the
reduction line is read.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _gran_gran_board(
    *,
    lessons: int = 3,
    graveyard: list[str] | None = None,
    hand: str = "Environmental Sciences",
    bob_graveyard: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[hand],
            battlefield=["Gran-Gran", "Forest", "Forest"],
            graveyard=[*["Combustion Technique"] * lessons, *(graveyard or [])],
            library=["Forest"] * 6,
        )
        .player(
            "bob",
            hand=["Environmental Sciences"],
            battlefield=["Forest", "Forest"],
            graveyard=list(bob_graveyard or []),
            library=["Island"] * 6,
        )
        .build()
    )


def _total_cost(scenario: Scenario, name: str, username: str = "alice", **kwargs) -> str:
    casting = scenario.cast(name, username, **kwargs)
    payment = scenario.game.determine_total_cost(casting)
    return str(payment.cost)


def test_gran_grans_static_reads_as_supported():
    support = card_support(card("Gran-Gran"))

    assert support.status == "handled"
    assert all(clause.outcome == "handled" for clause in support.clauses)


def test_three_lessons_discount_a_noncreature_spell():
    """Environmental Sciences ({2}, a Lesson sorcery) costs {1}."""
    scenario = _gran_gran_board(lessons=3)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Environmental Sciences") == "{1}"


def test_two_lessons_do_not():
    scenario = _gran_gran_board(lessons=2)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Environmental Sciences") == "{2}"


def test_four_lessons_still_discount_only_one():
    scenario = _gran_gran_board(lessons=4)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Environmental Sciences") == "{1}"


def test_instants_that_are_not_lessons_do_not_count():
    scenario = _gran_gran_board(lessons=2, graveyard=["Lightning Bolt", "Opt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Environmental Sciences") == "{2}"


def test_lessons_in_the_opponents_graveyard_do_not_count():
    scenario = _gran_gran_board(lessons=0, bob_graveyard=["Combustion Technique"] * 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Environmental Sciences") == "{2}"


def test_a_creature_spell_is_not_discounted():
    scenario = _gran_gran_board(lessons=3, hand="Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert _total_cost(scenario, "Grizzly Bears") == "{1}{G}"


def test_the_opponents_spells_are_not_discounted():
    """ "Spells *you* cast": Bob, with his own three Lessons, casting under
    Alice's Gran-Gran pays full price."""
    scenario = _gran_gran_board(lessons=3, bob_graveyard=["Combustion Technique"] * 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_spell = scenario.find("Environmental Sciences", Zone.HAND, "bob")

    _, decreases, _ = scenario.game.static_cost_modifiers_for(bobs_spell, "bob")

    assert decreases == []


def test_no_discount_once_gran_gran_is_gone():
    scenario = _gran_gran_board(lessons=3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.exile_cards([scenario.creature("Gran-Gran", "alice")])

    assert _total_cost(scenario, "Environmental Sciences") == "{2}"


def test_the_discounted_spell_is_cast_and_resolves():
    scenario = _gran_gran_board(lessons=3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest", username="alice")[:1]

    sciences = scenario.cast_onto_stack("Environmental Sciences", forest, username="alice")

    assert sciences.zone is Zone.STACK
    assert len(scenario.untapped_sources("Forest", username="alice")) == 1


# -- Drag to the Roots: the same tail on a spell's own reduction -------------


def _drag_board(graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Drag to the Roots"],
            battlefield=["Swamp", "Forest", "Swamp", "Forest"],
            graveyard=graveyard,
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 3)
        .build()
    )


#: Four card types among them: land, creature, instant, artifact.
_FOUR_TYPES = ["Forest", "Grizzly Bears", "Lightning Bolt", "Mishra's Bauble"]


def test_drag_to_the_roots_costs_full_price_with_three_card_types():
    scenario = _drag_board(_FOUR_TYPES[:3])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _total_cost(scenario, "Drag to the Roots", targets=[bears]) == "{2}{B}{G}"


def test_drag_to_the_roots_costs_two_less_with_four_card_types():
    scenario = _drag_board(_FOUR_TYPES)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _total_cost(scenario, "Drag to the Roots", targets=[bears]) == "{B}{G}"


def test_one_card_with_two_types_counts_both():
    """CR 205.2b: an artifact creature is two card types."""
    scenario = _drag_board(["Forest", "Ornithopter", "Lightning Bolt"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    assert _total_cost(scenario, "Drag to the Roots", targets=[bears]) == "{B}{G}"


def test_drag_to_the_roots_resolves_after_the_discount():
    scenario = _drag_board(_FOUR_TYPES)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    swamp, forest = (
        scenario.untapped_sources("Swamp", username="alice")[0],
        scenario.untapped_sources("Forest", username="alice")[0],
    )

    scenario.cast_and_resolve("Drag to the Roots", swamp, forest, username="alice", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD

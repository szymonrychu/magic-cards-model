"""A search bounded by an exact printed mana cost, not by mana value.

Urza's Saga chapter III: "Search your library for an artifact card with mana
cost {0} or {1}, put it onto the battlefield, then shuffle." (battle report
B6-02: the search offered, and put onto the battlefield, Engineered Explosives,
whose mana cost is {X}.)

Every CR number below was read in this session with `mise run rules:find`:

- **CR 202.1** - "A card's mana cost is indicated by mana symbols near the top
  of the card." The mana cost is the symbols.
- **CR 202.1b** - "Some objects have no mana cost. This normally includes all
  land cards, any other cards that have no mana symbols where their mana cost
  would appear ..." No mana cost is not a mana cost of {0}.
- **CR 202.3e** - "When calculating the mana value of an object with an {X} in
  its mana cost, X is treated as 0 while the object is not on the stack". That
  is a rule about the *mana value*; the printed cost is still {X}.
- **CR 107.3g** - "If a card in any zone other than the stack has an {X} in its
  mana cost, the value of {X} is treated as 0" - a value for X, not a change to
  the symbols the card has.

Only one printing in Magic uses "with mana cost {N}" (Scryfall
`o:"with mana cost {"` returns Urza's Saga alone), so there is no second
searcher to prove the reading on. Generality is proven on the cards being
searched for instead: Swooping Lookout ({W}, mana value 1), Seat of the Synod (no
mana cost, mana value 0) and Endless One ({X}) are all outside the deck pool,
and each would pass a mana-value bound while failing the printed-cost one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario
from tests.scenarios.test_urzas_saga import _advance_a_chapter, _saga_at_chapter_one


def _chapter_three(library: list[str]):
    scenario, saga = _saga_at_chapter_one(library=library)
    _advance_a_chapter(scenario)
    _advance_a_chapter(scenario)
    return scenario, saga


def _offered_names(scenario) -> list[str]:
    offered: list[str] = []
    for question in scenario.questions_asked():
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == "Urza's Saga":
            for card_id in question.cards:
                found = scenario.game.find_by_id(card_id)
                assert found is not None
                offered.append(found.name)
    return sorted(offered)


def test_an_x_cost_artifact_is_not_an_artifact_with_mana_cost_zero_or_one():
    """CR 202.1: Engineered Explosives' mana cost is {X}. Its mana value in the
    library is 0 (CR 202.3e), which is why a mana-value bound let it through."""
    scenario, saga = _chapter_three(["Engineered Explosives"])

    explosives = scenario.find("Engineered Explosives", Zone.LIBRARY)
    assert explosives.zone is Zone.LIBRARY
    assert _offered_names(scenario) == []
    assert saga.zone is Zone.GRAVEYARD


def test_the_search_offers_exactly_the_printed_zero_and_one_costs():
    """{0} and {1} are offered; {X}, {X}{X}, {W} (mana value 1), {2} and no mana
    cost at all (CR 202.1b) are not."""
    scenario, _saga = _chapter_three(
        [
            "Engineered Explosives",
            "Chalice of the Void",
            "Swooping Lookout",
            "Seat of the Synod",
            "Mind Stone",
            "Welding Jar",
            "Pithing Needle",
        ]
    )

    assert _offered_names(scenario) == ["Pithing Needle", "Welding Jar"]


def test_a_colored_one_drop_artifact_is_not_found():
    """Swooping Lookout costs {W}: mana value 1, but its mana cost is not {1}."""
    scenario, _saga = _chapter_three(["Swooping Lookout"])

    assert scenario.find("Swooping Lookout", Zone.LIBRARY).zone is Zone.LIBRARY
    assert _offered_names(scenario) == []


def test_an_artifact_with_no_mana_cost_is_not_found():
    """CR 202.1b: Seat of the Synod has no mana cost, which is not {0}, although
    CR 202.3a gives it mana value 0."""
    scenario, _saga = _chapter_three(["Seat of the Synod"])

    assert scenario.find("Seat of the Synod", Zone.LIBRARY).zone is Zone.LIBRARY
    assert _offered_names(scenario) == []


def test_a_one_cost_artifact_is_found_and_put_onto_the_battlefield():
    scenario, _saga = _chapter_three(["Pithing Needle"])

    assert scenario.find("Pithing Needle", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_a_mana_value_bound_still_counts_x_as_zero():
    """ "with mana value N or less" is unchanged: Ranger-Captain of Eos's search
    still finds Endless One ({X}, mana value 0 in the library per CR 202.3e)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ranger-Captain of Eos"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Endless One", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Ranger-Captain of Eos", auto=True)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.find("Endless One", Zone.HAND).zone is Zone.HAND

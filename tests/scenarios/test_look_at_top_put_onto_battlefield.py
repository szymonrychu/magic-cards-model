"""Scenario: "Look at the top N cards of your library. [You may] put
`<quantity>` `<description>` from among them onto the battlefield. Put the
rest on the bottom of your library in a random/any order." -
`_merge_look_top_put_onto_battlefield_clauses`.

Aang, at the Crossroads' enters trigger is the reported shape ("You may put a
creature card with mana value 4 or less ... in a random order"). Collected
Company (Modern- and Pioneer-legal, in no `magic-cards-model-api` deck) is
the off-pool proof: a different count (six), an "up to two" with no "you
may", a different ceiling (3), an instant rather than a trigger, and "in any
order" rather than "in a random order". Birthing Ritual's sacrifice-gated
form of the same reader is in `test_sacrificed_mana_value_bound.py`.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.20e** - "Looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player."
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible": a card outside the description is never offered, and "you
  may" / "up to two" both allow choosing none.
- **CR 202.3** - mana value; a card with exactly the ceiling qualifies.
- **CR 110.2a** - put onto the battlefield under that player's control, not
  cast.
- **CR 401.4** - "in any order" is the owner's arrangement; "in a random
  order" is nobody's.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

AANG = "Aang, at the Crossroads"
COCO = "Collected Company"


def _offered(scenario: PlayedScenario, source: str) -> list[str] | None:
    """The cards the put question offered - the first `CHOOSE_CARDS` from
    `source`; an "in any order" bottoming asks a second one after it."""
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == source
    ]
    if not questions:
        return None
    offered = set(questions[0].cards)
    return sorted(state.name for state in scenario.all_card_states() if state.id in offered)


def _library(scenario: PlayedScenario) -> list[str]:
    return [state.name for state in scenario.player("alice").library]


def _card(scenario: PlayedScenario, name: str):
    return next(state for state in scenario.player("alice").library if state.name == name)


# --------------------------------------------------------------------------
# Aang, at the Crossroads
# --------------------------------------------------------------------------

_FIVE = ["Serra Angel", "Hill Giant", "Opt", "Grizzly Bears", "Forest"]


def _aang(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[AANG], library=library)
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _aang_enters(scenario: PlayedScenario) -> None:
    scenario.put_onto_battlefield(AANG, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def test_aang_puts_a_creature_card_with_mana_value_four_or_less():
    scenario = _aang([*_FIVE, "Island", "Island"])
    giant = _card(scenario, "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=AANG)

    _aang_enters(scenario)

    assert giant.zone is Zone.BATTLEFIELD and giant.controller == "alice"
    assert _offered(scenario, AANG) == ["Grizzly Bears", "Hill Giant"], (
        "a 4 is 'four or less'; Serra Angel (5), Opt and Forest are never offered"
    )
    library = _library(scenario)
    assert library[:2] == ["Island", "Island"], "the unlooked-at cards are now on top"
    assert sorted(library[2:]) == sorted(name for name in _FIVE if name != "Hill Giant")


def test_aang_may_put_nothing_and_bottoms_all_five():
    scenario = _aang([*_FIVE, "Island"])
    scenario.will_choose_cards(username="alice", source=AANG)

    _aang_enters(scenario)

    assert all(state.zone is not Zone.BATTLEFIELD for state in scenario.player().library)
    library = _library(scenario)
    assert library[0] == "Island"
    assert sorted(library[1:]) == sorted(_FIVE)


def test_aang_with_no_qualifying_card_asks_nothing():
    scenario = _aang(["Serra Angel", "Opt", "Forest", "Forest", "Craw Wurm", "Island"])

    _aang_enters(scenario)

    assert _offered(scenario, AANG) is None
    assert _library(scenario)[0] == "Island"
    assert len(scenario.player("alice").library) == 6


def test_aang_with_a_short_library_looks_at_what_there_is():
    scenario = _aang(["Grizzly Bears", "Opt"])
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=AANG)

    _aang_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert _library(scenario) == ["Opt"]


def test_aang_the_put_card_is_not_cast():
    """CR 110.2a: put, not cast - no spell was cast this turn."""
    scenario = _aang(["Grizzly Bears", "Island"])
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=AANG)

    _aang_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.game.spells_cast_this_turn.get("alice", []) == []


# --------------------------------------------------------------------------
# Collected Company - the off-pool proof
# --------------------------------------------------------------------------

_SIX = ["Gray Ogre", "Hill Giant", "Grizzly Bears", "Opt", "Llanowar Elves", "Forest"]


def _coco(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[COCO], battlefield=["Forest"] * 4, library=[*library, "Island"])
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_coco(scenario: PlayedScenario) -> None:
    forests = scenario.untapped_sources(*(["Forest"] * 4))
    scenario.cast_and_resolve(COCO, *forests)


def test_collected_company_puts_up_to_two_with_mana_value_three_or_less():
    scenario = _coco(_SIX)
    ogre = _card(scenario, "Gray Ogre")
    elves = _card(scenario, "Llanowar Elves")
    scenario.will_choose_cards(ogre, elves, username="alice", source=COCO)

    _cast_coco(scenario)

    assert ogre.zone is Zone.BATTLEFIELD and elves.zone is Zone.BATTLEFIELD
    assert _offered(scenario, COCO) == ["Gray Ogre", "Grizzly Bears", "Llanowar Elves"], (
        "Hill Giant's 4 is over the ceiling; Opt and Forest are not creature cards"
    )
    library = _library(scenario)
    assert library[0] == "Island"
    assert sorted(library[1:]) == sorted(["Hill Giant", "Grizzly Bears", "Opt", "Forest"])


def test_collected_company_may_put_just_one():
    scenario = _coco(_SIX)
    bears = _card(scenario, "Grizzly Bears")
    scenario.will_choose_cards(bears, username="alice", source=COCO)

    _cast_coco(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.player("alice").library) == 6


def test_collected_company_may_put_none():
    """ "Up to two" (CR 107.1c's range from zero) needs no "you may"."""
    scenario = _coco(_SIX)
    scenario.will_choose_cards(username="alice", source=COCO)

    _cast_coco(scenario)

    assert len(scenario.player("alice").library) == 7
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == COCO
    ]
    assert questions[0].exact is False and questions[0].amount == 2


def test_collected_company_bottoms_the_rest_in_the_owner_s_chosen_order():
    """CR 401.4: "in any order" is the owner's to arrange."""
    scenario = _coco(["Gray Ogre", "Opt", "Forest", "Hill Giant", "Serra Angel", "Craw Wurm"])
    ogre = _card(scenario, "Gray Ogre")
    order = [_card(scenario, name) for name in ("Craw Wurm", "Forest", "Serra Angel")]
    order += [_card(scenario, name) for name in ("Opt", "Hill Giant")]
    scenario.will_choose_cards(ogre, username="alice", source=COCO)
    scenario.will_choose_cards(*order, username="alice", source=COCO)

    _cast_coco(scenario)

    assert ogre.zone is Zone.BATTLEFIELD
    assert _library(scenario) == [
        "Island",
        "Craw Wurm",
        "Forest",
        "Serra Angel",
        "Opt",
        "Hill Giant",
    ]

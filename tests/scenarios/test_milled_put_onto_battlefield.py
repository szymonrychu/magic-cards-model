"""Scenario: "[each player mills|mill] N cards. [Then ]put a `<description>`
card from among the milled cards onto the battlefield[ under your control]."
- `_mill_then_may_take_from_milled_runner`, widened past Rapid Rescue's and
Vorinclex's own "mill ... you may put ..." to a mandatory single put, every
player's mill at once, an Oxford-comma type list, and a mana-value parity.

Gyruda, Doom of Depths is the reported card. Fetch Quest (Bramble Familiar's
Adventure, legal in Standard, Pioneer and Modern, in no
`magic-cards-model-api` deck) is the off-pool proof: the controller's own
mill, a "Then" in front of the put, and "a creature, enchantment, or land
card" instead of a creature with a parity. Gyruda's companion condition
("only cards with even mana values") is proven in `test_companion.py`; its
in-game special action is proven at the end of this file.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 202.3** - mana value; **CR 202.3a** - an object with no mana cost has
  mana value 0, and 0 is even.
- **CR 110.2a** - "under your control": the put card is controlled by the
  resolving ability's controller, whoever owns it.
- **CR 608.2d** - a card outside the description is never offered; the put
  is not optional, so one must be chosen when any qualifies.
- **CR 702.139a** - companion: pay {3} and put it into your hand.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

GYRUDA = "Gyruda, Doom of Depths"


def _offered(scenario: PlayedScenario, source: str) -> list[str] | None:
    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == source
    ]
    if not questions:
        return None
    offered = set(questions[-1].cards)
    return sorted(state.name for state in scenario.all_card_states() if state.id in offered)


def _gyruda(alice: list[str], bob: list[str], *, graveyard: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", hand=[GYRUDA], library=alice, graveyard=graveyard or [])
        .player("bob", library=bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _gyruda_enters(scenario: PlayedScenario) -> None:
    scenario.put_onto_battlefield(GYRUDA, "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _milled(scenario: PlayedScenario, username: str, name: str):
    return next(state for state in scenario.player(username).graveyard if state.name == name)


def test_gyruda_takes_an_even_creature_from_an_opponent_s_mill():
    scenario = _gyruda(
        ["Llanowar Elves", "Gray Ogre", "Forest", "Opt", "Island"],
        ["Grizzly Bears", "Hill Giant", "Island", "Island", "Island"],
    )
    scenario.put_onto_battlefield(GYRUDA, "alice")
    scenario.game.put_triggers_on_stack()
    bob = scenario.player("bob")
    giant = next(state for state in bob.library if state.name == "Hill Giant")
    scenario.will_choose_cards(giant, username="alice", source=GYRUDA)
    scenario.pass_until_resolved()

    assert giant.zone is Zone.BATTLEFIELD
    assert giant.controller == "alice" and giant.owner == "bob", "CR 110.2a: under your control"
    assert _offered(scenario, GYRUDA) == ["Grizzly Bears", "Hill Giant"], (
        "only the even mana values (2, 4) - Llanowar Elves (1) and Gray Ogre (3) are odd"
    )
    assert [state.name for state in scenario.player("alice").library] == ["Island"]
    assert [state.name for state in bob.library] == ["Island"]


def test_gyruda_mana_value_zero_is_even():
    scenario = _gyruda(["Memnite", "Llanowar Elves", "Opt", "Forest"], ["Island"] * 4)
    memnite = scenario.player("alice").library[0]

    _gyruda_enters(scenario)

    assert memnite.zone is Zone.BATTLEFIELD, "CR 202.3a: 0 is even, and the only candidate"
    assert _offered(scenario, GYRUDA) is None, "one qualifying card and one to put: no choice"


def test_gyruda_with_no_even_creature_puts_nothing():
    scenario = _gyruda(["Llanowar Elves", "Gray Ogre", "Forest", "Opt"], ["Island"] * 4)

    _gyruda_enters(scenario)

    assert _offered(scenario, GYRUDA) is None
    assert len(scenario.player("alice").graveyard) == 4
    assert not any(state.name != GYRUDA for state in scenario.game.battlefield), (
        "nothing but Gyruda itself"
    )


def test_gyruda_must_put_one_when_several_qualify():
    """The put is not optional (CR 608.2d): the question asks for exactly one."""
    scenario = _gyruda(
        ["Grizzly Bears", "Hill Giant", "Opt", "Forest"], ["Wall of Omens"] + ["Island"] * 3
    )
    bears = scenario.player("alice").library[0]
    scenario.will_choose_cards(bears, username="alice", source=GYRUDA)

    _gyruda_enters(scenario)

    questions = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.CHOOSE_CARDS and question.source == GYRUDA
    ]
    assert questions[-1].exact is True and questions[-1].amount == 1
    assert bears.zone is Zone.BATTLEFIELD
    assert _offered(scenario, GYRUDA) == ["Grizzly Bears", "Hill Giant", "Wall of Omens"]


def test_gyruda_ignores_creatures_already_in_a_graveyard():
    """ "From among the milled cards" - the Craw Wurm already in alice's
    graveyard was not milled, even though its 6 is even."""
    scenario = _gyruda(
        ["Opt", "Forest", "Island", "Island"], ["Island"] * 4, graveyard=["Craw Wurm"]
    )

    _gyruda_enters(scenario)

    wurm = _milled(scenario, "alice", "Craw Wurm")
    assert wurm.zone is Zone.GRAVEYARD
    assert _offered(scenario, GYRUDA) is None


def test_gyruda_with_short_libraries_mills_what_there_is():
    scenario = _gyruda(["Grizzly Bears"], ["Island", "Island"])
    bears = scenario.player("alice").library[0]

    _gyruda_enters(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").library == [] and scenario.player("bob").library == []


def test_gyruda_as_a_companion_comes_to_hand_for_three():
    """CR 702.139a: once per game, pay {3} and put the companion into your
    hand - Gyruda's own keyword line, driven by the same reader as every
    other companion."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Island", "Island", "Island"],
            library=["Island"] * 5,
            companion=GYRUDA,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island", "Island")

    scenario.bring_companion_to_hand(*islands)

    assert [state.name for state in scenario.player("alice").hand] == [GYRUDA]


# --------------------------------------------------------------------------
# Fetch Quest - the off-pool proof
# --------------------------------------------------------------------------


def _fetch_quest(library: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bramble Familiar"],
            battlefield=["Forest"] * 7,
            library=[*library, "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_fetch_quest(scenario: PlayedScenario) -> None:
    forests = scenario.untapped_sources(*(["Forest"] * 7))
    casting = scenario.cast("Bramble Familiar")
    casting.cast_as_adventure()
    scenario.pay_with(casting.begin_paying(), *forests)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


_SEVEN = ["Opt", "Glorious Anthem", "Forest", "Lightning Bolt", "Serra Angel", "Opt", "Opt"]


def test_fetch_quest_puts_an_enchantment_from_its_own_mill():
    scenario = _fetch_quest(_SEVEN)
    anthem = next(
        state for state in scenario.player("alice").library if state.name == "Glorious Anthem"
    )
    scenario.will_choose_cards(anthem, username="alice", source="Fetch Quest")

    _cast_fetch_quest(scenario)

    assert anthem.zone is Zone.BATTLEFIELD
    assert _offered(scenario, "Fetch Quest") == ["Forest", "Glorious Anthem", "Serra Angel"], (
        "a creature, enchantment, or land card - never Opt or Lightning Bolt"
    )
    assert [state.name for state in scenario.player("alice").library] == ["Island"]


def test_fetch_quest_may_put_a_land():
    scenario = _fetch_quest(_SEVEN)
    forest = next(state for state in scenario.player("alice").library if state.name == "Forest")
    scenario.will_choose_cards(forest, username="alice", source="Fetch Quest")

    _cast_fetch_quest(scenario)

    assert forest.zone is Zone.BATTLEFIELD


def test_fetch_quest_with_nothing_that_qualifies_puts_nothing():
    scenario = _fetch_quest(["Opt"] * 4 + ["Lightning Bolt"] * 3)

    _cast_fetch_quest(scenario)

    assert _offered(scenario, "Fetch Quest") is None
    assert [state.name for state in scenario.player("alice").library] == ["Island"]

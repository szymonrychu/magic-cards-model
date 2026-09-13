"""A library search for "a <description> card or a <description> card".

"Search your library for a basic Plains card or a creature card with mana value
1 or less, reveal it, put it into your hand, then shuffle." (Starfield
Shepherd) names two whole card descriptions joined by "or", and the mana value
bound belongs to the second one only.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description." A card matching either description matches.
- **CR 701.23b** - a stated quality makes the find optional, so the searcher
  is asked which qualifying card to take and may take none.
- **CR 701.23e** - "reveal it" is a real reveal, so the find is known to the
  opponent once it is in hand.

A description this engine cannot read fails closed with a notice instead of
searching for nothing: an empty search is a legal answer a player may give, so
silently offering no cards is indistinguishable from a real miss.

Outcaster Greenblade ("a basic land card or a Desert card") and Gatecreeper
Vine ("you may search ... for a basic land card or a Gate card") are not in any
deck pool; they prove the template rather than the reported card. The wording
of the may-prompt is grammatical for every generated description: the bound
follows the word "card" ("a creature card with mana value 1 or less"), never
the other way round.

Every CR number above was read in full from `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import trigger_effect_for
from magic_cards_model.models import Game, Zone

from .harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone]]:
    return sorted((entry.card_name, entry.zone) for entry in game.known_to(viewer))


def _cast_with_etb(creature: str, lands: list[str], library: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[creature], battlefield=lands, library=library)
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _resolve_shepherd(scenario: Scenario) -> None:
    sources = scenario.untapped_sources(*["Plains"] * 5)
    scenario.cast_and_resolve("Starfield Shepherd", *sources)
    scenario.pass_until_resolved()


def _search_question(scenario: Scenario):
    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]
    return asked


SHEPHERD_LIBRARY = [
    "Hallowed Fountain",
    "Grizzly Bears",
    "Llanowar Elves",
    "Plains",
    "Memnite",
    "Island",
]


def test_either_description_qualifies_and_nothing_else_does():
    scenario = _cast_with_etb("Starfield Shepherd", ["Plains"] * 5, SHEPHERD_LIBRARY)
    elves = scenario.find("Llanowar Elves", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(elves, username="alice", source="Starfield Shepherd")

    _resolve_shepherd(scenario)

    offered = {
        scenario.game.find_by_id(card_id).name for card_id in _search_question(scenario).cards
    }
    assert offered == {"Llanowar Elves", "Plains", "Memnite"}
    assert elves.zone is Zone.HAND


def test_the_basic_plains_half_can_be_taken():
    scenario = _cast_with_etb("Starfield Shepherd", ["Plains"] * 5, SHEPHERD_LIBRARY)
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(plains, username="alice", source="Starfield Shepherd")

    _resolve_shepherd(scenario)

    assert plains.zone is Zone.HAND


def test_the_find_is_revealed_to_the_opponent():
    scenario = _cast_with_etb("Starfield Shepherd", ["Plains"] * 5, SHEPHERD_LIBRARY)
    memnite = scenario.find("Memnite", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(memnite, username="alice", source="Starfield Shepherd")

    _resolve_shepherd(scenario)

    assert ("Memnite", Zone.HAND) in known(scenario.game, "bob")


def test_the_mana_value_bound_does_not_apply_to_the_plains_half():
    """A basic Plains has mana value 0 either way, so the bound is proven on
    the creature half instead: a two-drop creature is not offered."""
    scenario = _cast_with_etb("Starfield Shepherd", ["Plains"] * 5, ["Grizzly Bears", "Island"])

    _resolve_shepherd(scenario)

    assert [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS] == []
    assert scenario.player("alice").hand == []


def test_the_searcher_may_decline_to_find_anything():
    scenario = _cast_with_etb("Starfield Shepherd", ["Plains"] * 5, SHEPHERD_LIBRARY)
    scenario.will_choose_cards(username="alice", source="Starfield Shepherd")

    _resolve_shepherd(scenario)

    assert _search_question(scenario).exact is False
    assert scenario.player("alice").hand == []


def test_outcaster_greenblade_finds_a_basic_land_or_a_desert():
    scenario = _cast_with_etb(
        "Outcaster Greenblade",
        ["Forest"] * 3,
        ["Hallowed Fountain", "Sunscorched Desert", "Grizzly Bears", "Forest"],
    )
    desert = scenario.find("Sunscorched Desert", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(desert, username="alice", source="Outcaster Greenblade")

    scenario.cast_and_resolve("Outcaster Greenblade", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()

    offered = {
        scenario.game.find_by_id(card_id).name for card_id in _search_question(scenario).cards
    }
    assert offered == {"Sunscorched Desert", "Forest"}
    assert desert.zone is Zone.HAND


# -- the prompt names the description grammatically (B5-07) -------------------


def _may_prompt(scenario: Scenario) -> str:
    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    return asked.prompt


def test_a_bounded_description_puts_the_bound_after_card():
    scenario = _cast_with_etb("Ranger-Captain of Eos", ["Plains"] * 3, ["Llanowar Elves"])
    scenario.will_take_the_may(True, username="alice")

    scenario.cast_and_resolve("Ranger-Captain of Eos", *scenario.untapped_sources(*["Plains"] * 3))
    scenario.pass_until_resolved()

    assert (
        _may_prompt(scenario) == "search your library for a creature card with mana value 1 or less"
    )


def test_a_disjunction_names_both_whole_descriptions():
    scenario = _cast_with_etb("Gatecreeper Vine", ["Forest"] * 2, ["Forest", "Grizzly Bears"])
    scenario.will_take_the_may(True, username="alice")

    scenario.cast_and_resolve("Gatecreeper Vine", *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()

    assert _may_prompt(scenario) == "search your library for a basic land card or a Gate card"
    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]


# -- an unreadable description fails closed -------------------------------------


def test_an_unreadable_half_of_the_disjunction_fails_closed_with_a_notice():
    """Moonsilver Key's "an artifact card with a mana ability or a basic land
    card": "with a mana ability" is not a description this engine reads, so the
    search is not run at all rather than run for the wrong set of cards."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Moonsilver Key", "Plains"],
            library=["Plains", "Mind Stone"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    key = scenario.find("Moonsilver Key", Zone.BATTLEFIELD, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(key, plains)
    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    assert [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS] == []
    (notice,) = scenario.game.search_description_notices
    assert notice.source_name == "Moonsilver Key"
    assert "with a mana ability" in notice.text


def test_the_unreadable_search_is_a_notice_not_a_silent_parse():
    effect = trigger_effect_for(
        "Moonsilver Key",
        TriggerEvent.ENTERS_THE_BATTLEFIELD,
        "search your library for an artifact card with a mana ability or a basic land card, "
        "reveal it, put it into your hand, then shuffle.",
    )
    assert effect is not None
    assert effect.__name__ == "search_description_notice_only"

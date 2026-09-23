"""A library search for "an instant card or a card with flash".

"Search your library for an instant card or a card with flash, reveal it, put
it into your hand, then shuffle." (Waterlogged Teachings // Inundated Archive,
Mystical Teachings) names two whole card descriptions joined by "or a": a card
type, and a card that has one keyword ability.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description." A card matching either description matches.
- **CR 702.8a** - "Flash is a static ability that functions in any zone from
  which you could play the card it's on." It is a keyword the card *has* in
  the library, so a flash creature, artifact, enchantment or planeswalker all
  qualify; a sorcery does not.
- **CR 702.34a** - flashback is its own keyword, not flash: a sorcery with
  flashback is not "a card with flash", while an instant with flashback is
  still an instant.
- **CR 712.8a** - "While a double-faced card is outside the game or in a zone
  other than the battlefield or stack, it has only the characteristics of its
  front face." A double-faced card is judged by its front face in the library.
- **CR 701.23e** - "reveal it" is a real reveal, so the find is known to the
  opponent once it is in hand.

Mystical Teachings is the second printing of the template: legal in Modern,
Pioneer and Standard, and in no deck pool. Every CR number above was read in
full from `mise run rules:find` in the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Game, Type, Zone

from .harness import Scenario

LIBRARY = [
    "Lightning Bolt",
    "Spellstutter Sprite",
    "Disruptor Flute",
    "Leyline Binding",
    "The Wandering Emperor",
    "Hydroelectric Specimen",
    "Faithless Looting",
    "Grizzly Bears",
    "Island",
]

#: Every card in `LIBRARY` that is an instant or has flash.
QUALIFYING = {
    "Lightning Bolt",
    "Spellstutter Sprite",
    "Disruptor Flute",
    "Leyline Binding",
    "The Wandering Emperor",
    "Hydroelectric Specimen",
}


def _scenario(spell: str, library: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=["Island"] * 4, library=library)
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario: Scenario, spell: str) -> None:
    scenario.cast_and_resolve(spell, *scenario.untapped_sources(*["Island"] * 4))
    scenario.pass_until_resolved()


def _search_questions(scenario: Scenario):
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_CARDS]


def _offered(scenario: Scenario) -> set[str]:
    (asked,) = _search_questions(scenario)
    return {scenario.game.find_by_id(card_id).name for card_id in asked.cards}


def _known(game: Game, viewer: str) -> list[tuple[str, Zone]]:
    return sorted((entry.card_name, entry.zone) for entry in game.known_to(viewer))


# -- what qualifies -------------------------------------------------------------


def test_instants_and_flash_cards_of_every_type_qualify():
    scenario = _scenario("Waterlogged Teachings", LIBRARY)
    sprite = scenario.find("Spellstutter Sprite", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(sprite, username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    assert _offered(scenario) == QUALIFYING
    assert sprite.zone is Zone.HAND


def test_a_sorcery_with_flashback_is_not_a_card_with_flash():
    """CR 702.34a: flashback is a different keyword. Faithless Looting is a
    sorcery, and its "Flashback" must not be read as containing "flash"."""
    scenario = _scenario(
        "Waterlogged Teachings", ["Faithless Looting", "Grizzly Bears", "Lightning Bolt"]
    )
    scenario.will_choose_cards(username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    assert _offered(scenario) == {"Lightning Bolt"}


def test_an_instant_with_flashback_still_qualifies_as_an_instant():
    scenario = _scenario("Waterlogged Teachings", ["Mystical Teachings", "Faithless Looting"])
    teachings = scenario.find("Mystical Teachings", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(teachings, username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    assert _offered(scenario) == {"Mystical Teachings"}
    assert teachings.zone is Zone.HAND


def test_a_double_faced_card_is_judged_by_its_front_face():
    """CR 712.8a: Waterlogged Teachings in the library is an instant (its land
    back face is not what it is there), so a second copy is a legal find."""
    scenario = _scenario("Waterlogged Teachings", ["Waterlogged Teachings", "Grizzly Bears"])
    second = scenario.find("Waterlogged Teachings", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(second, username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    assert _offered(scenario) == {"Waterlogged Teachings"}
    assert second.zone is Zone.HAND


def test_the_find_is_revealed_and_the_library_shuffled_around_it():
    scenario = _scenario("Waterlogged Teachings", LIBRARY)
    flute = scenario.find("Disruptor Flute", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(flute, username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    assert ("Disruptor Flute", Zone.HAND) in _known(scenario.game, "bob")
    assert len(scenario.player("alice").library) == len(LIBRARY) - 1


def test_the_searcher_may_find_nothing():
    """CR 701.23b: a search for a stated quality never has to find anything."""
    scenario = _scenario("Waterlogged Teachings", LIBRARY)
    scenario.will_choose_cards(username="alice", source="Waterlogged Teachings")

    _cast(scenario, "Waterlogged Teachings")

    (asked,) = _search_questions(scenario)
    assert asked.exact is False
    assert scenario.player("alice").hand == []
    assert len(scenario.player("alice").library) == len(LIBRARY)


def test_the_spell_is_parsed_not_silent():
    """The resolving spell really searches: before this reader existed the
    clause matched nothing and the spell resolved doing nothing at all."""
    scenario = _scenario("Waterlogged Teachings", ["Spellstutter Sprite"])
    scenario.will_choose_cards(
        scenario.find("Spellstutter Sprite", Zone.LIBRARY, "alice"),
        username="alice",
        source="Waterlogged Teachings",
    )

    _cast(scenario, "Waterlogged Teachings")

    assert [state.name for state in scenario.player("alice").hand] == ["Spellstutter Sprite"]
    assert scenario.game.search_description_notices == []


# -- the second printing ------------------------------------------------------


def test_mystical_teachings_reads_the_same_template():
    scenario = _scenario("Mystical Teachings", LIBRARY)
    emperor = scenario.find("The Wandering Emperor", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(emperor, username="alice", source="Mystical Teachings")

    _cast(scenario, "Mystical Teachings")

    assert _offered(scenario) == QUALIFYING
    assert emperor.zone is Zone.HAND
    assert ("The Wandering Emperor", Zone.HAND) in _known(scenario.game, "bob")


# -- the land back face stays playable ------------------------------------------


def test_inundated_archive_is_played_as_a_tapped_land_that_taps_for_blue_or_black():
    """CR 712.12: played as a land, the card enters with its land face up;
    "This land enters tapped." applies, and it taps for {U} or {B}."""
    scenario = (
        Scenario()
        .player("alice", hand=["Waterlogged Teachings"], library=["Island"])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    archive = scenario.play_land("Waterlogged Teachings")

    assert archive.zone is Zone.BATTLEFIELD
    assert archive.name == "Inundated Archive"
    assert archive.types == (Type.LAND,)
    assert archive.tapped

    archive.untap()
    scenario.activate(archive, color=Color.BLACK)
    assert scenario.player("alice").mana_pool.floating == {Color.BLACK: 1}

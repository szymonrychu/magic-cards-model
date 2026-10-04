"""Scenario: the 293-fra fixtures refreshed after release carry current oracle
wording, and the engine reads that wording.

Gallia, the Merrymaker was fetched before release as "with +1/+1 counter on
it" (no article) and Stingcaster Mage without its flashback reminder text.
Both printings are re-fetched from Scryfall; each test pins the current text
and then proves the card does what that text says, on the real printing.

CR 702.10a (haste), CR 702.34a (flashback), CR 603.1 (triggered abilities).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario


def test_gallia_prints_the_current_article_wording():
    text = card("Gallia, the Merrymaker").oracle_text
    assert "with a +1/+1 counter on it has haste" in text


def test_gallia_grants_haste_only_to_another_creature_carrying_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Gallia, the Merrymaker", "Grizzly Bears", "Llanowar Elves"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    countered = scenario.creature("Grizzly Bears")
    plain = scenario.creature("Llanowar Elves")
    countered.add_counters(Counter.PLUS_ONE)

    assert has_keyword(countered, Keyword.HASTE, scenario.game)
    assert not has_keyword(plain, Keyword.HASTE, scenario.game)


def test_stingcaster_mage_prints_its_flashback_reminder_and_still_grants_flashback():
    printing = card("Stingcaster Mage")
    assert "(You may cast that card from your graveyard for its flashback cost." in (
        printing.oracle_text
    )

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stingcaster Mage"],
            graveyard=["Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.choose_trigger_targets("Stingcaster Mage", [bolt])
    scenario.cast_and_resolve("Stingcaster Mage", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.action is PlayAction.CAST
    assert permission.zone is Zone.GRAVEYARD

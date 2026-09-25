"""Web-slinging: an alternative cost that returns a tapped creature you
control to its owner's hand (CR 702.188).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 702.188a** - "Web-slinging is a static ability that functions while
  the spell with web-slinging is on the stack. 'Web-slinging [cost]' means
  'You may cast this spell by paying [cost] and returning a tapped creature
  you control to its owner's hand rather than paying its mana cost.' Casting
  a spell using its web-slinging ability follows the rules for paying
  alternative costs in rules 601.2b and 601.2f-h."
- **CR 118.9a** - only one alternative cost per spell.
- **CR 601.2h** - the creature is returned as the total cost is paid; a cost
  that cannot be paid in full is not paid at all.

Spider-UK (Web-slinging {2}{W}) brought the keyword into the pool for its end
step trigger (EC4 cluster H3); Spider-Man, Web-Slinger (Web-slinging {W}) is a
second printing in no deck, the proof the cost is read off the keyword line.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(hand: str, battlefield: list[str], *, bob: list[str] | None = None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[hand], battlefield=battlefield, library=["Plains"] * 3)
        .player("bob", battlefield=list(bob or []), library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _web_sling(scenario, name, returned, lands):
    spell = scenario.find(name, Zone.HAND, "alice")
    return scenario.game.cast(
        spell,
        "alice",
        keyword="web-slinging",
        choosing=list(returned),
        mana_sources=list(lands),
    )


def test_web_slinging_is_a_hand_cast_option_under_cr_702_188a():
    for name in ("Spider-Man, Web-Slinger", "Spider-UK"):
        (option,) = [o for o in keyword_cast_options(card(name)) if o.keyword == "Web-slinging"]
        assert option.zone is Zone.HAND
        assert option.rule == "CR 702.188a"
        assert option.understood
        assert not option.pays_mana_cost


def test_a_tapped_creature_goes_back_and_the_web_slinging_cost_is_paid():
    """Spider-Man, Web-Slinger for {W}, returning a tapped Grizzly Bears."""
    scenario = _board("Spider-Man, Web-Slinger", ["Grizzly Bears", "Plains"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    spider = _web_sling(
        scenario, "Spider-Man, Web-Slinger", [bears], scenario.untapped_sources("Plains")
    )
    assert spider.zone is Zone.STACK
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None
    scenario.pass_until_resolved()
    assert "Spider-Man, Web-Slinger" in scenario.battlefield_names()


def test_the_second_printing_reads_its_own_cost():
    """Spider-UK: Web-slinging {2}{W} - three lands, not one."""
    scenario = _board("Spider-UK", ["Grizzly Bears", "Plains", "Plains", "Plains"])
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tapped = True
    with pytest.raises(ValueError):
        _web_sling(scenario, "Spider-UK", [bears], scenario.untapped_sources("Plains"))
    assert bears.zone is Zone.BATTLEFIELD
    spider = _web_sling(
        scenario, "Spider-UK", [bears], scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    assert spider.zone is Zone.STACK


def test_an_untapped_creature_does_not_pay_it():
    scenario = _board("Spider-Man, Web-Slinger", ["Grizzly Bears", "Plains"])
    bears = scenario.creature("Grizzly Bears", "alice")
    with pytest.raises(ValueError, match="tapped"):
        _web_sling(
            scenario, "Spider-Man, Web-Slinger", [bears], scenario.untapped_sources("Plains")
        )
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.find("Spider-Man, Web-Slinger", Zone.HAND, "alice") is not None


def test_no_creature_returned_is_refused():
    scenario = _board("Spider-Man, Web-Slinger", ["Plains"])
    with pytest.raises(ValueError):
        _web_sling(scenario, "Spider-Man, Web-Slinger", [], scenario.untapped_sources("Plains"))
    assert scenario.find("Spider-Man, Web-Slinger", Zone.HAND, "alice") is not None


def test_an_opponents_tapped_creature_is_not_yours_to_return():
    scenario = _board("Spider-Man, Web-Slinger", ["Plains"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tapped = True
    with pytest.raises(ValueError, match="control"):
        _web_sling(
            scenario, "Spider-Man, Web-Slinger", [bears], scenario.untapped_sources("Plains")
        )
    assert bears.zone is Zone.BATTLEFIELD


def test_a_tapped_land_is_not_a_creature():
    scenario = _board("Spider-Man, Web-Slinger", ["Plains", "Plains"])
    land, other = scenario.untapped_sources("Plains", "Plains")
    land.tapped = True
    with pytest.raises(ValueError, match="creature"):
        _web_sling(scenario, "Spider-Man, Web-Slinger", [land], [other])
    assert land.zone is Zone.BATTLEFIELD

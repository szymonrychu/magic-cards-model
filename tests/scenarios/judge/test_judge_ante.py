"""Judge scenarios: the ante zone, and the cards that move things into it.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#666** - How does Ante Work?

Ante is still in the Comprehensive Rules (CR 407), and the episode is a tour of
it: the ante zone is a public zone (CR 400.2), only a card's owner may ante a
card (CR 407.4), and an ante card's own ability fails closed when the ante it
depends on cannot happen.

This engine has no ante zone at all - `models/zone.Zone` is CR 400.1's seven
zones plus a sideboard - so the two tests here are `xfail`, and they are what a
future wave that adds one would be measured against. Jeweled Bird's real oracle
text, confirmed with `resolve_cards`: "Remove this card from your deck before
playing if you're not playing for ante. / {T}: Ante this artifact. If you do,
put all other cards you own from the ante into your graveyard, then draw a
card."

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_seven_rules_zones_are_modelled_and_ante_is_not():
    """CR 400.1: "There are normally seven zones: library, hand, battlefield,
    graveyard, stack, exile, and command. Some older cards also use the ante
    zone."

    The passing half of this file, and the honest statement of the gap: the
    engine models the seven, plus the sideboard, and stops there. CR 400.2 makes
    the ante zone a public zone alongside the graveyard, battlefield, stack and
    exile, which is the episode's "all cards in it are face up".
    """
    assert {zone.value for zone in Zone} == {
        "library",
        "hand",
        "battlefield",
        "graveyard",
        "stack",
        "exile",
        "command",
        "sideboard",
    }
    assert "ante" not in {zone.value for zone in Zone}


@pytest.mark.xfail(
    strict=True,
    reason="There is no ante zone in `models/zone.Zone` (CR 400.1's optional "
    "eighth), so nothing can be anted and Jeweled Bird's ability has no entry in "
    "`machines/effects.py` either.",
)
def test_anteing_the_bird_moves_it_out_of_the_battlefield():
    """CR 407.4: "To ante an object is to put that object into the ante zone
    from whichever zone it's currently in."

    Jeweled Bird's own first instruction is to ante itself, so a resolution that
    worked would leave the battlefield without it.
    """
    scenario = Scenario().player("alice", battlefield=["Jeweled Bird"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD


@pytest.mark.xfail(
    strict=True,
    reason="Same gap: nothing can be anted, so the 'If you do' the rest of the "
    "ability hangs off never becomes true and no card is drawn either.",
)
def test_the_owner_antes_the_bird_and_draws_a_card():
    """The half of the episode's Jeweled Bird question that is supposed to work.

    CR 407.4: "The owner of an object is the only player who can ante that
    object" - and here the owner is doing it, so the ante happens, and the "If
    you do" clause that follows it does too. The stolen-Bird case the episode
    actually asks about is the mirror image: with the ante refused, that same
    "if you do" is false and *nothing* in the ability happens. This engine
    reaches the stolen-Bird answer by accident (it can never ante anything), so
    only the case it should get right is asserted here.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Grizzly Bears"], battlefield=["Jeweled Bird"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bird = scenario.find("Jeweled Bird", Zone.BATTLEFIELD, "alice")

    scenario.activate(bird)
    scenario.resolve_top()

    assert bird.zone is not Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]

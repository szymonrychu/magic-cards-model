"""Judge scenarios: evoke granted by another permanent, and outliving it.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1003** - Ashling, the Limitless vs Removal Spell

Ashling's real oracle text, confirmed with `resolve_cards`: "Elemental permanent
spells you cast from your hand gain evoke {4} as you cast them." - so a card
that never printed evoke gains it while being cast, and CR 702.74a's second
ability (the enters-the-battlefield sacrifice) comes with it.

The episode's ruling is that killing Ashling in response does *not* save the
creature: CR 400.7b keeps the effect of a static ability that granted an ability
to a permanent spell applying to the permanent that spell becomes, and CR 611.3d
says that where the granted ability also functions on the battlefield, "the
ability lasts indefinitely unless some other duration is stated". The Elemental
still has evoke as it enters, so evoke's trigger still fires and it is still
sacrificed.

This engine models evoke as an alternative cost read off a card's *own* printed
keyword (`Casting.use_keyword`, `scenarios/test_evoke.py`); a keyword *granted*
by another permanent's static ability is not read anywhere, so both halves of
the episode are `xfail` here. Every CR number was looked up with
`knowledge_search(type="rules")` in the session that wrote the file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*extra_battlefield: str):
    """alice holds an Elemental with no printed evoke, and enough Mountains to
    pay Ashling's granted evoke {4}."""
    return (
        Scenario()
        .player(
            "alice",
            hand=["Ashmouth Hound"],
            battlefield=[
                "Ashling, the Limitless",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                *extra_battlefield,
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_the_hound_has_no_evoke_of_its_own():
    """The premise, and the reason Ashling is needed at all.

    Ashmouth Hound is an Elemental Dog with no evoke printed on it, so
    `Casting.use_keyword("evoke")` has nothing of its own to find. Everything
    below is about an evoke that came from somewhere else.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="alice")

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")


@pytest.mark.xfail(
    strict=True,
    reason="A keyword *granted* to a spell by another permanent's static ability "
    "is not read anywhere: `Casting.use_keyword` looks only at the card's own "
    "printed keywords, so Ashling's 'gain evoke {4} as you cast them' never "
    "reaches the Hound.",
)
def test_ashling_grants_evoke_to_an_elemental_being_cast():
    """CR 702.74a: "Evoke represents two abilities: a static ability that
    functions in any zone from which the card with evoke can be cast and a
    triggered ability that functions on the battlefield."

    Ashling hands both to the Hound as it is cast, so alice may pay {4} instead
    of {1}{R} - and accepts the sacrifice trigger that comes with it.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="alice")
    casting.use_keyword("evoke")

    assert casting.total_cost.mana == "{4}"


@pytest.mark.xfail(
    strict=True,
    reason="Same gap, one step further on: with no granted evoke there is no "
    "evoke sacrifice trigger either, so nothing about killing Ashling in response "
    "can be observed.",
)
def test_killing_ashling_in_response_does_not_save_the_evoked_elemental():
    """The episode's actual question, and its answer.

    CR 400.7b: "Effects from static abilities that grant an ability to a
    permanent spell that functions on the battlefield continue to apply to the
    permanent that spell becomes", and CR 611.3d adds that such an ability
    "lasts indefinitely unless some other duration is stated". So bob's removal
    spell takes Ashling and changes nothing: the Hound enters with evoke, evoke's
    trigger fires, and the Hound is sacrificed anyway.
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="alice")
    casting.use_keyword("evoke")
    payment = casting.begin_paying()
    scenario.pay_with(
        payment,
        *scenario.untapped_sources(
            "Mountain", "Mountain", "Mountain", "Mountain", username="alice"
        ),
    )
    hound = scenario.put_on_stack(casting)

    scenario.pass_priority("alice")
    (bobs_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    ashling = scenario.creature("Ashling, the Limitless", "alice")
    scenario.cast_and_resolve("Lightning Bolt", bobs_mountain, username="bob", targets=[ashling])
    scenario.resolve_top()  # the Hound
    scenario.resolve_top()  # evoke's sacrifice trigger

    assert ashling.zone is Zone.GRAVEYARD
    assert hound.zone is Zone.GRAVEYARD

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

Both halves of the granted keyword are modelled: `Casting.granted_cast_options`
reads CR 610.5's grant into the same `KeywordCastOption` a printed evoke
produces, and `Casting._use_keyword` stamps the granted keyword line onto
`CardState.granted_ability_texts`, where `machines/triggers.
granted_triggered_abilities_of` reads it back as CR 702.74a's second ability.
Every CR number was looked up with
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
    `Casting.use_keyword("evoke")` has nothing of its own to find with nobody
    granting it - everything below is about an evoke that came from somewhere
    else, and this is the board without that somewhere else.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ashmouth Hound"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="alice")

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")


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

    assert str(casting.total_cost.mana) == "{4}"


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

"""Harmonize: CR 702.180a's three static abilities.

"Harmonize [cost]" means "You may cast this card from your graveyard by
paying [cost] and tapping up to one untapped creature you control rather
than paying this spell's mana cost," "If you cast this spell using its
harmonize ability, its total cost is reduced by an amount of generic mana
equal to the tapped creature's power," and "If the harmonize cost was paid,
exile this card instead of putting it anywhere else any time it would leave
the stack." Built the same way flashback already is - a `KeywordCastOption`
from `machines/casting.py`'s `_option_from_keyword` (CR 702.34a's own
graveyard-cast shape) plus a new `Casting.pay_harmonize` for the tap-and-
reduce half, and the exile-instead check widened alongside flashback's own
in `machines/replacement.py`.

Proved on Roamer's Routine, a card outside the deck pool and outside this
wave's brief, alongside Winternight Stories.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_winternight_stories_casts_from_the_graveyard_with_the_discount():
    """Winternight Stories: "Draw three cards. Then discard two cards unless
    you discard a creature card." "Harmonize {4}{U}" - a Grizzly Bears
    (power 2) reduces the cost to {2}{U}.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Winternight Stories"],
            library=["Forest", "Forest", "Forest"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stories = scenario.find("Winternight Stories", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    hand_before = len(scenario.player("alice").hand)

    casting = scenario.cast("Winternight Stories", from_zone=Zone.GRAVEYARD, username="alice")
    casting.use_keyword("Harmonize")
    casting.pay_harmonize(bears)
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.tapped, "the creature was tapped to reduce the cost"
    assert stories.zone is Zone.EXILE, "CR 702.180a's own exile-instead"
    assert len(scenario.player("alice").hand) >= hand_before + 1


def test_roamers_routine_casts_from_the_graveyard_and_reduces_by_power():
    """Roamer's Routine: "Search your library for a basic land card, put it
    onto the battlefield tapped, then shuffle." "Harmonize {4}{G}" - not in
    the deck pool, not named in this wave's brief. A Hill Giant (power 3)
    reduces the cost to {1}{G}.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Roamer's Routine"],
            library=["Forest", "Forest"],
            battlefield=["Forest", "Forest", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    routine = scenario.find("Roamer's Routine", Zone.GRAVEYARD, "alice")
    giant = scenario.creature("Hill Giant", "alice")

    casting = scenario.cast("Roamer's Routine", from_zone=Zone.GRAVEYARD, username="alice")
    casting.use_keyword("Harmonize")
    casting.pay_harmonize(giant)
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert giant.tapped
    assert routine.zone is Zone.EXILE
    lands = [state for state in scenario.game.battlefield if state.name == "Forest"]
    assert len(lands) == 3, "the fetched Forest entered tapped alongside the two paid ones"

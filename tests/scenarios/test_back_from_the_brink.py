"""Scenario: Back from the Brink's "Exile a creature card from your
graveyard and pay its mana cost: Create a token that's a copy of that card.
Activate only as a sorcery."

The activation cost names no fixed mana amount at all - the amount owed is
whichever creature card the activating player chooses to exile, known only
once that choice is made. `machines/cost.py`'s `exile_and_pay_mana_cost_cost`
and `CostComponent.pay_mana_cost_of_chosen` are the new pieces:
`Game.activation_cost` folds `ManaCost.parse(card.mana_cost)` into the
activation's own mana cost once the chosen card is known, the same way
Emerge/Delve's "pay [a card]'s mana cost" templates would if the pool had one
(it does not - this is the first).

"That card" in the effect is not a target (CR 115.1 - the sentence never
says "target") - it is CR 607.1's anaphora back to whatever was exiled to
pay the cost, carried onto the stack as the new `AbilityOnStack.cost_exiled_
card_id` field (there was previously no channel from a cost choice to a
resolving effect at all).

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 707.2** - "the copy acquires the copiable values of the original
  object's characteristics."
- **CR 701.7a** - creating a token.
- **CR 602.1a** - "the activation cost is everything before the colon."
- **CR 118.3** - a cost cannot be paid without the resources to pay it.
- **CR 602.5d, 307.5** - "Activate only as a sorcery."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Back from the Brink"],
            graveyard=["Goblin Guide"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
                "Island",
            ],
        )
        .player("bob")
    )


def test_exiling_a_creature_and_paying_its_mana_cost_creates_a_copy_token():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island", "Island")
    brink = scenario.cast_and_resolve("Back from the Brink", *sources)

    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "alice")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.activate(brink, mountain, exiling=[goblin])
    scenario.resolve_top()

    assert goblin.zone is Zone.EXILE

    battlefield_names = scenario.battlefield_names()
    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Goblin Guide" and state.id != goblin.id
    ]
    assert len(tokens) == 1
    token = tokens[0]
    assert token.zone is Zone.BATTLEFIELD
    assert token.power == 2
    assert token.toughness == 2
    assert "Goblin Guide" in battlefield_names


def test_a_cost_without_enough_mana_for_the_chosen_card_is_refused():
    """CR 118.3: the chosen card's own mana cost has to actually be paid -
    Goblin Guide's {R} cannot be paid with only islands untapped."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island", "Island")
    brink = scenario.cast_and_resolve("Back from the Brink", *sources)

    goblin = scenario.find("Goblin Guide", Zone.GRAVEYARD, "alice")
    (island,) = scenario.untapped_sources("Island")

    payment = scenario.game.begin_activating(brink, 0, "alice", exiling=[goblin])
    payment.tap_for_mana(island, [Color.BLUE])
    with pytest.raises(ValueError):
        payment.pay()

    assert goblin.zone is Zone.GRAVEYARD


def test_the_ability_cannot_be_activated_with_something_on_the_stack():
    """CR 602.5d, CR 307.5: "Activate only as a sorcery" needs the stack
    empty, not only the main phase."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island", "Island")
    brink = scenario.cast_and_resolve("Back from the Brink", *sources)

    assert scenario.why_cannot_activate(brink) is None

    scenario.game.stack.append(brink)  # anything non-empty on the stack
    try:
        reason = scenario.why_cannot_activate(brink)
        assert reason is not None
        assert "sorcery" in reason
    finally:
        scenario.game.stack.remove(brink)

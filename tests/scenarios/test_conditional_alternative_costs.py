"""Scenario: an alternative cost printed as a plain, *conditional* sentence.

`test_alternative_costs.py` covers the unconditional shape (Force of Will) and
Force of Negation's "If it's not your turn" gate. This file is about the third
shape: a condition on the game's own history, printed ahead of the offer -
Mindbreak Trap's "If an opponent cast three or more spells this turn, you may
pay {0} rather than pay this spell's mana cost." (confirmed with
`resolve_cards`). No keyword names it, so nothing in `keyword_cast_options`
sees it, and its condition is neither a timing question nor a board scan.

CR numbers, each looked up with `knowledge_search(type="rules")` in the session
that wrote this file and quoted from what it returned:

- **CR 118.9** - "Some spells have alternative costs. An alternative cost is a
  cost listed in a spell's text, or applied to it from another effect, that its
  controller may pay rather than paying the spell's mana cost."
- **CR 118.9a** - "Only one alternative cost can be applied to any one spell as
  it's being cast. The controller of the spell announces their intentions to
  pay that cost as described in rule 601.2b."
- **CR 118.9b** - "Alternative costs are generally optional." The Trap may
  always be hard-cast instead.
- **CR 118.9c** - "An alternative cost doesn't change a spell's mana cost, only
  what its controller has to pay to cast it."
- **CR 118.5** - "Some costs are represented by {0}, or are reduced to {0}. The
  action necessary for a player to pay such a cost is the player's
  acknowledgment that they are paying it." So the Trap's {0} is a cost that is
  paid, not an absence of one.
- **CR 604.6** - "Some static abilities apply while a card is in any zone that
  you could cast or play it from (usually your hand)."
- **CR 601.2f** - the total cost, alternative cost included, is determined and
  locked in.

Every printing is a real Scryfall fixture from `tests/fixtures/cards/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.models import Zone

from .harness import Scenario


def _board() -> Scenario:
    """bob is the active player with three one-mana spells and the lands for
    them; alice holds the Trap and four Islands to hard-cast it with."""
    return (
        Scenario()
        .player(
            "bob",
            hand=["Lightning Bolt", "Lava Spike", "Ponder"],
            battlefield=["Mountain", "Mountain", "Island"],
            library=["Island"] * 5,
        )
        .player(
            "alice",
            hand=["Mindbreak Trap"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
    )


def _bob_casts(scenario, name: str, land: str, targets=None):
    """One of bob's spells, resolved - CR 117.1a wants the stack empty before
    he may cast the next sorcery, and the Trap's condition is a count of
    spells *cast*, which resolution does not undo."""
    (source,) = scenario.untapped_sources(land, username="bob")
    return scenario.cast_and_resolve(name, source, username="bob", targets=targets)


def _bob_casts_leaving_it_on_the_stack(scenario, name: str, land: str, targets=None):
    (source,) = scenario.untapped_sources(land, username="bob")
    return scenario.cast_onto_stack(name, source, username="bob", targets=targets)


def test_the_offer_is_listed_but_unavailable_before_the_third_spell():
    """CR 118.9's offer exists on the card whatever the board says; its
    condition is what decides whether it can be announced right now.

    Two opposing spells is not three, so the option is reported carrying its
    own reason rather than silently missing - a seat that is shown only the
    legal options cannot tell "no alternative cost" from "not yet".
    """
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bob_casts(scenario, "Lightning Bolt", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Lava Spike", "Mountain", targets=["alice"])
    scenario.pass_priority("bob")

    casting = scenario.cast("Mindbreak Trap", username="alice", targets=[])
    (offer,) = [
        option
        for option in casting.alternative_costs
        if option.source is AlternativeCostSource.PRINTED
    ]

    assert not offer.available
    assert "three" in (offer.unavailable or "")


def test_the_trap_can_be_cast_for_zero_after_three_opposing_spells():
    """The condition met: three spells from one opponent this turn, so the
    {0} may be paid rather than the printed {2}{U}{U} (CR 118.9, CR 118.5)."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bob_casts(scenario, "Lightning Bolt", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Lava Spike", "Mountain", targets=["alice"])
    bobs_ponder = _bob_casts_leaving_it_on_the_stack(scenario, "Ponder", "Island")
    scenario.pass_priority("bob")

    casting = scenario.cast("Mindbreak Trap", username="alice")
    casting.use_pitch_cost()  # CR 601.2b, before CR 601.2c's targets
    casting.choose_targets([bobs_ponder])
    payment = casting.begin_paying()
    payment.pay()
    trap = scenario.put_on_stack(casting)

    assert str(payment.cost) == "{0}"
    assert trap.zone is Zone.STACK
    assert all(
        not land.tapped for land in scenario.untapped_sources(*["Island"] * 4, username="alice")
    ), "nothing was spent: the {0} is the whole cost (CR 118.5)"


def test_the_alternative_cost_leaves_the_printed_mana_cost_alone():
    """CR 118.9c: the Trap's mana cost and mana value are what they always
    were, however it was paid for - the Minor Misstep ruling."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bob_casts(scenario, "Lightning Bolt", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Lava Spike", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Ponder", "Island")
    scenario.pass_priority("bob")

    casting = scenario.cast("Mindbreak Trap", username="alice")
    casting.use_pitch_cost()

    assert casting.spell.card.mana_cost == "{2}{U}{U}"
    assert casting.spell.card.cmc == 4
    assert str(casting.base_cost) == "{2}{U}{U}"


def test_the_condition_counts_one_opponent_not_the_table():
    """ "An opponent cast three or more spells" is about a single opponent, and
    in a two-player game that is the only opponent there is - alice's own
    spells never count towards it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mindbreak Trap", "Ponder", "Ponder", "Ponder"],
            battlefield=["Island", "Island", "Island", "Island"],
            library=["Island"] * 9,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for _ in range(3):
        (island,) = scenario.untapped_sources("Island")
        scenario.cast_and_resolve("Ponder", island)

    casting = scenario.cast("Mindbreak Trap")

    with pytest.raises(ValueError, match="three"):
        casting.use_pitch_cost()


def test_the_hard_cast_is_still_available_when_the_condition_holds():
    """CR 118.9b: alternative costs are optional. Three opposing spells offer
    the {0}; declining it and paying {2}{U}{U} is a legal cast."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bob_casts(scenario, "Lightning Bolt", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Lava Spike", "Mountain", targets=["alice"])
    _bob_casts(scenario, "Ponder", "Island")
    scenario.pass_priority("bob")

    islands = scenario.untapped_sources(*["Island"] * 4, username="alice")
    trap = scenario.cast_onto_stack("Mindbreak Trap", *islands, username="alice", targets=[])

    assert trap.zone is Zone.STACK
    assert all(island.tapped for island in islands)

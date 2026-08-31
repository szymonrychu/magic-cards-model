"""Scenario: a keyword another permanent grants a spell as it is cast.

Every keyword this engine casts with until now was printed on the card being
cast (`Casting.use_keyword` reads `keyword_cast_options(self.spell.card)`).
Ashling, the Limitless hands one out from the battlefield instead: "Elemental
permanent spells you cast from your hand gain evoke {4} as you cast them."
(confirmed with `resolve_cards`), so a Dog with no evoke of its own may be cast
for {4}.

CR numbers, each looked up with `knowledge_search(type="rules")` in the session
that wrote this file and quoted from what it returned:

- **CR 610.5** - "Some static abilities create one-shot effects that cause
  spells a player casts to gain an ability as that player casts them. These
  effects begin to apply to appropriate spells at the time the player proposes
  the casting of that spell." That is the rule the grant is read under, and the
  reason it is read at announcement rather than off the printed card.
- **CR 604.2** - "Static abilities create continuous effects ... These effects
  are active as long as the permanent with the ability remains on the
  battlefield and has the ability." No Ashling, no grant.
- **CR 110.4b** - "The term 'permanent spell' is used to refer to a spell that
  will enter the battlefield as a permanent as part of its resolution.
  Specifically, it means an artifact, battle, creature, enchantment, land, or
  planeswalker spell." Which is what makes an instant ineligible for Ashling's
  grant however Elemental it is.
- **CR 118.9** - the granted evoke is an alternative cost, and
- **CR 118.9a** - only one of them may be paid.
- **CR 702.74a** - "Evoke represents two abilities: a static ability that
  functions in any zone from which the card with evoke can be cast and a
  triggered ability that functions on the battlefield." The static half is the
  alternative cost; the triggered half is the sacrifice.
- **CR 400.7b** - "Effects from static abilities that grant an ability to a
  permanent spell that functions on the battlefield continue to apply to the
  permanent that spell becomes."

Every printing is a real Scryfall fixture from `tests/fixtures/cards/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*extra: str, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand or ["Ashmouth Hound"],
            battlefield=[
                "Ashling, the Limitless",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                *extra,
            ],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
    )


def test_the_granted_evoke_is_listed_as_an_alternative_cost():
    """CR 610.5's grant reaches `alternative_costs`, so a seat driving the
    engine can find it - the option carries the keyword and its {4}."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound")
    (option,) = [
        candidate
        for candidate in casting.alternative_costs
        if candidate.source is AlternativeCostSource.KEYWORD
    ]

    assert option.available
    assert (option.keyword or "").lower() == "evoke"
    assert option.source_name == "Ashling, the Limitless"
    assert str(option.cost.mana) == "{4}"


def test_the_hound_is_cast_for_the_granted_evoke_cost():
    """{4} rather than the printed {1}{R} (CR 118.9), and the four Mountains
    that paid it are what proves the price was real."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound")
    casting.use_keyword("evoke")
    payment = casting.begin_paying()
    mountains = scenario.untapped_sources(*["Mountain"] * 4)
    scenario.pay_with(payment, *mountains)
    hound = scenario.put_on_stack(casting)

    assert str(payment.cost) == "{4}"
    assert hound.zone is Zone.STACK
    assert casting.keyword_used.lower() == "evoke"


def test_the_grant_needs_ashling_on_the_battlefield():
    """CR 604.2: the static ability is active while its permanent is on the
    battlefield. Without her, the Hound has no evoke of its own (CR 702.74a
    is read off the card, and the card says nothing)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Ashmouth Hound"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound")

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")


def test_the_grant_only_covers_the_spells_it_names():
    """ "Elemental permanent spells" is a filter, not a flourish: Grizzly Bears
    is a Creature - Bear, so Ashling hands it nothing."""
    scenario = _board(hand=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Grizzly Bears")

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")


def test_an_instant_is_not_a_permanent_spell():
    """CR 110.4b: an instant never enters the battlefield, so it is not a
    permanent spell whatever its subtypes - Lightning Bolt is not covered even
    though it is red and cast from hand."""
    scenario = _board(hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Lightning Bolt", targets=["bob"])

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")


def test_the_grant_only_covers_the_zone_it_names():
    """ "spells you cast from your hand" - a Hound in the graveyard is not one,
    and nothing else lets it be cast from there either (CR 601.3)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Ashmouth Hound"],
            battlefield=["Ashling, the Limitless", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", from_zone=Zone.GRAVEYARD)

    with pytest.raises(ValueError, match="evoke"):
        casting.use_keyword("evoke")


def test_the_grant_is_read_from_the_casters_own_board():
    """ "spells **you** cast": Ashling grants nothing to her controller's
    opponent."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ashling, the Limitless", "Mountain"])
        .player("bob", hand=["Ashmouth Hound"], battlefield=["Mountain"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # to bob's turn, where his creature spell is castable
    while scenario.game.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Ashmouth Hound", username="bob")

    with pytest.raises(ValueError, match="no evoke ability"):
        casting.use_keyword("evoke")

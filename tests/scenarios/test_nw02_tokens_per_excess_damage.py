"""Scenario: "Create a number of <tokens> equal to the amount of excess damage
dealt to that creature this way."

Goblin Negotiation (1/1 red Goblin creature tokens), Hell to Pay (tapped
Treasure tokens) and Lacerate Flesh (Blood tokens). These three are the only
in-pool printings of the template (Scryfall `o:"amount of excess damage"` in
Modern/Pioneer/Standard also returns Unleash the Inferno, whose "when it deals
excess damage this way, destroy ..." is a different, trigger-shaped template),
so the reader is proven across the three listed token kinds instead of a
fourth printing.

Verified this session with `mise run rules:find`:

- **CR 120.10** - excess damage dealt to a creature is the amount dealt
  greater than lethal damage; lethal accounts for damage already marked.
- **CR 111.10a / 111.10g** - Treasure and Blood are predefined artifact
  tokens, each with its quoted ability.
- **CR 608.2b** - an illegal sole target means the spell does nothing.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type

from .harness import Scenario


def _board(*, hand, lands, bob_battlefield, library_size=3):
    scenario = (
        Scenario()
        .player(
            "alice", hand=list(hand), battlefield=list(lands), library=["Mountain"] * library_size
        )
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_x(scenario, name, x, target, extra_colored):
    spell = scenario.find(name, Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=x,
        targets=[target],
        mana_sources=scenario.untapped_sources(*["Mountain"] * (x + extra_colored)),
    )
    scenario.resolve_top()


def _tokens(scenario, name):
    return [state for state in scenario.game.battlefield if state.name == name]


# -- Goblin Negotiation --------------------------------------------------------


def test_goblin_negotiation_makes_a_goblin_per_excess_damage():
    scenario = _board(
        hand=["Goblin Negotiation"],
        lands=["Mountain"] * 7,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_x(scenario, "Goblin Negotiation", 5, bears, 2)
    assert bears.zone is Zone.GRAVEYARD
    goblins = _tokens(scenario, "Goblin Token")
    assert len(goblins) == 3  # 5 damage, 2 lethal
    for goblin in goblins:
        chars = scenario.game.characteristics_of(goblin)
        assert (chars.numeric_power, chars.numeric_toughness) == (1, 1)
        assert "Goblin" in chars.subtypes
        assert scenario.game.controller_of(goblin).username == "alice"


def test_goblin_negotiation_with_no_excess_makes_no_goblins():
    scenario = _board(
        hand=["Goblin Negotiation"],
        lands=["Mountain"] * 4,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_x(scenario, "Goblin Negotiation", 2, bears, 2)
    assert bears.zone is Zone.GRAVEYARD
    assert _tokens(scenario, "Goblin Token") == []


def test_goblin_negotiation_x_zero_makes_nothing():
    scenario = _board(
        hand=["Goblin Negotiation"],
        lands=["Mountain"] * 2,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_x(scenario, "Goblin Negotiation", 0, bears, 2)
    assert bears.zone is Zone.BATTLEFIELD
    assert _tokens(scenario, "Goblin Token") == []


def test_goblin_negotiation_counts_damage_already_marked():
    scenario = _board(
        hand=["Goblin Negotiation"],
        lands=["Mountain"] * 5,
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    giant.damage = 2  # 1 toughness left
    _cast_x(scenario, "Goblin Negotiation", 3, giant, 2)
    assert giant.zone is Zone.GRAVEYARD
    assert len(_tokens(scenario, "Goblin Token")) == 2


def test_goblin_negotiation_with_an_illegal_target_makes_no_goblins():
    scenario = _board(
        hand=["Goblin Negotiation"],
        lands=["Mountain"] * 7,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = scenario.find("Goblin Negotiation", Zone.HAND, "alice")
    scenario.game.cast(
        spell,
        "alice",
        x_value=5,
        targets=[bears],
        mana_sources=scenario.untapped_sources(*["Mountain"] * 7),
    )
    scenario.game.destroy(bears)
    scenario.resolve_top()
    assert _tokens(scenario, "Goblin Token") == []


# -- Hell to Pay ---------------------------------------------------------------


def test_hell_to_pay_makes_tapped_treasures_equal_to_the_excess():
    scenario = _board(hand=["Hell to Pay"], lands=["Mountain"] * 5, bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_x(scenario, "Hell to Pay", 4, giant, 1)
    assert giant.zone is Zone.GRAVEYARD
    treasures = _tokens(scenario, "Treasure Token")
    assert len(treasures) == 1  # 4 damage, 3 lethal
    assert all(treasure.tapped for treasure in treasures)


def test_hell_to_pay_large_excess_makes_that_many_tapped_treasures():
    scenario = _board(
        hand=["Hell to Pay"], lands=["Mountain"] * 8, bob_battlefield=["Elvish Mystic"]
    )
    mystic = scenario.creature("Elvish Mystic", "bob")
    _cast_x(scenario, "Hell to Pay", 7, mystic, 1)
    treasures = _tokens(scenario, "Treasure Token")
    assert len(treasures) == 6
    assert all(treasure.tapped for treasure in treasures)
    assert all(
        "Treasure" in scenario.game.characteristics_of(treasure).subtypes for treasure in treasures
    )


def test_hell_to_pay_no_excess_no_treasure():
    scenario = _board(hand=["Hell to Pay"], lands=["Mountain"] * 4, bob_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "bob")
    _cast_x(scenario, "Hell to Pay", 3, giant, 1)
    assert giant.zone is Zone.GRAVEYARD
    assert _tokens(scenario, "Treasure Token") == []


# -- Lacerate Flesh ------------------------------------------------------------


def test_lacerate_flesh_makes_blood_tokens_equal_to_the_excess():
    scenario = _board(
        hand=["Lacerate Flesh"],
        lands=["Mountain"] * 5,
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Lacerate Flesh", *scenario.untapped_sources(*["Mountain"] * 5), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    blood = _tokens(scenario, "Blood Token")
    assert len(blood) == 2  # 4 damage, 2 lethal
    for token in blood:
        chars = scenario.game.characteristics_of(token)
        assert "Blood" in chars.subtypes
        assert Type.ARTIFACT in chars.types
        assert not token.tapped


def test_lacerate_flesh_no_excess_no_blood():
    scenario = _board(
        hand=["Lacerate Flesh"],
        lands=["Mountain"] * 5,
        bob_battlefield=["Colossal Dreadmaw"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve(
        "Lacerate Flesh", *scenario.untapped_sources(*["Mountain"] * 5), targets=[dreadmaw]
    )
    assert dreadmaw.damage == 4
    assert _tokens(scenario, "Blood Token") == []


def test_a_blood_token_rummages_for_a_card():
    """CR 111.10g: {1}, {T}, Discard a card, Sacrifice this token: Draw a card."""
    scenario = _board(
        hand=["Lacerate Flesh", "Hill Giant"],
        lands=["Mountain"] * 6,
        bob_battlefield=["Elvish Mystic"],
        library_size=3,
    )
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.cast_and_resolve(
        "Lacerate Flesh", *scenario.untapped_sources(*["Mountain"] * 5), targets=[mystic]
    )
    blood = _tokens(scenario, "Blood Token")
    assert len(blood) == 3
    giant = scenario.find("Hill Giant", Zone.HAND, "alice")
    library_before = len(scenario.player("alice").library)
    scenario.activate(blood[0], *scenario.untapped_sources("Mountain"), discarding=[giant])
    scenario.resolve_top()
    assert giant.zone is Zone.GRAVEYARD
    assert blood[0].zone is not Zone.BATTLEFIELD
    assert len(scenario.player("alice").library) == library_before - 1

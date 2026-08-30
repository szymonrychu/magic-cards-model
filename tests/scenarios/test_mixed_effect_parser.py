"""Scenario: an effect that mixes a targeted clause and a plain player clause
in one card, read off its own printed text with no `machines/effects.py`
table row.

`parse_targeted_effect_for_spell` (`tests/scenarios/test_targeted_effect_parser.py`)
and `parse_player_effect_for_spell` (`tests/scenarios/test_player_effect_parser.py`)
are each whole-effect parsers: every clause has to be their one shape or the
whole card is refused. Lightning Helix - "deals 3 damage to any target and you
gain 3 life" - is a targeted clause followed by a player clause, and used to
need a registry row for exactly that reason: neither whole-effect parser could
read it alone. `parse_mixed_effect_for_spell` tries both parsers on each
clause independently, which is what this file proves reaches the board.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - why a multi-clause effect runs clause
  by clause in printed order, and why one bad clause among them takes the
  whole effect down rather than the half that would have worked being run
  alone.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly."
- **CR 118.3** - a resolving effect that gains life for its controller.
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.cost import TotalCost, discard_cost
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _announce(scenario: PlayedScenario, name: str, username: str = "alice") -> Casting:
    """Begin casting, with the game attached so a non-mana additional cost can
    be paid - the same helper `test_costs.py` uses for Cathartic Reunion's own
    discard cost.
    """
    casting = scenario.cast(name, username=username)
    casting.game = scenario.game
    return casting


# --------------------------------------------------------------------------
# The worked case: a targeted clause and a player clause, back to back
# --------------------------------------------------------------------------


def test_lightning_helix_deals_damage_and_gains_life_off_its_own_text():
    """Lightning Helix: "Lightning Helix deals 3 damage to any target and you
    gain 3 life." No `EFFECTS` row any more (`test_registry_is_minimal.py`
    fails loudly if one is re-added) - both halves run off the parsed text.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Helix"], battlefield=["Mountain", "Plains"])
        .player("bob", battlefield=["Doran, the Siege Tower"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # 0/5, so 3 damage marks without being lethal - the point is checking the
    # damage stuck, not that the creature died.
    doran = scenario.creature("Doran, the Siege Tower", "bob")
    alice = scenario.player("alice")
    assert alice.life == 20

    scenario.cast_and_resolve(
        "Lightning Helix",
        *scenario.untapped_sources("Mountain", "Plains"),
        targets=[doran],
    )

    assert doran.damage == 3
    assert alice.life == 23


def test_vraskas_contempt_exiles_and_gains_life_off_its_own_text():
    """A different real card, the same mixed shape but with "exile" in place
    of "damage": "Exile target creature or planeswalker. You gain 2 life."
    Two sentences this time, not one joined by "and", so this also proves
    `split_effect_clauses`' period-based split feeds the mixed dispatcher the
    same way its "and"-based split does.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Vraska's Contempt"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"]
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice = scenario.player("alice")
    assert alice.life == 20

    scenario.cast_and_resolve(
        "Vraska's Contempt",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bears],
    )

    assert bears.zone is Zone.EXILE
    assert alice.life == 22


# --------------------------------------------------------------------------
# Fail-closed per clause: one bad clause takes a mixed effect down whole
# --------------------------------------------------------------------------


def test_fatal_push_destroys_a_cheap_creature():
    """Fatal Push: "Destroy target creature if it has mana value 2 or less.
    Revolt — Destroy that creature if it has mana value 4 or less instead if a
    permanent left the battlefield under your control this turn." Wave W6's
    own `_parse_revolt_destroy_or_exile_clause` reads the two-paragraph shape
    as one instruction, with the mana-value threshold (2, or 4 under Revolt)
    enforced by `machines/targeting.py`'s `TargetRequirement.comparison_value_
    if_revolt` rather than dropped - see `scenarios/test_fatal_push_revolt.py`
    for the full Revolt-aware board-level proof this file used to lack.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "bob")

    scenario.cast_and_resolve("Fatal Push", *scenario.untapped_sources("Swamp"), targets=[mystic])

    assert mystic.zone is Zone.GRAVEYARD, "mana value 1 is within the base clause's own ceiling"


# --------------------------------------------------------------------------
# Cathartic Reunion's preamble: the additional-cost line is not an effect clause
# --------------------------------------------------------------------------


def test_cathartic_reunion_draws_three_cards_with_its_cost_line_stripped():
    """Cathartic Reunion: "As an additional cost to cast this spell, discard
    two cards. Draw three cards." The additional cost (CR 118.8a) is paid on
    the way to the stack and is not part of resolving the spell; before the
    preamble strip was shared with the player-clause parser
    (`_prepare_effect_clauses`), that cost line was read as an unparseable
    effect clause and took the whole card down, so "Draw three cards" never
    ran even though it is exactly the shape `parse_clause_effect` reads.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cathartic Reunion", "Grizzly Bears", "Elvish Mystic"],
            library=["Plains", "Island", "Swamp"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)
    fodder = [
        scenario.find("Grizzly Bears", Zone.HAND, "alice"),
        scenario.find("Elvish Mystic", Zone.HAND, "alice"),
    ]

    casting = _announce(scenario, "Cathartic Reunion")
    casting.add_additional_cost(TotalCost.of(None, discard_cost(*fodder)))
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # Two discarded, three drawn, one spell cast from hand: net +0, but only
    # if the draw actually ran - a total failure (the old behaviour, before
    # the preamble strip was shared with the player-clause parser) would
    # leave the hand two cards short instead.
    assert len(alice.hand) == hand_before - 1 - 2 + 3
    assert all(card.zone is Zone.GRAVEYARD for card in fodder)
    assert len(alice.graveyard) == 1 + 2  # Cathartic Reunion itself, plus the discard

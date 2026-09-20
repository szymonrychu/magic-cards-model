"""Scenario: "<destroy/exile> target X. Its controller gains N life." - the
fixed-number half of `_parse_referent_clause`'s life-gain branch
(`_REFERENT_GAIN_LIFE_RE`, `machines/effects.py`).

`test_anaphoric_referent_clauses.py` already covers the "gains life equal to
its power" shape (Solitude, Swords to Plowshares). Nature's Claim and Last
Breath print a plain number instead - "Its controller gains 4 life." - and
the old regex only matched "gains life equal to <expr>", so this second
sentence never read at all. `_parse_anaphoric_clause_pair` correctly refuses
to run half of a two-sentence instruction (CR 608.2c has no notion of that),
so the whole spell - the destroy/exile half included - silently did nothing:
Nature's Claim was reported as a spell whose whole effect fails closed.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 608.2c** - the controller of the resolving spell follows its
  instructions in the order written; the life gain is not optional once the
  first sentence's target was actually destroyed or exiled.
- **CR 119.3** - "If an effect causes a player to gain life or lose life,
  that player's life total is adjusted accordingly."
- **CR 400.7** - an object that changes zones becomes a new object with no
  memory of its previous existence - the destroyed/exiled permanent's
  *controller*, read here, is read off the object as it was, before it moved.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_natures_claim_destroys_and_gains_the_targets_controller_life():
    """ "Destroy target artifact or enchantment. Its controller gains 4
    life." - alice casts it on bob's artifact, bob (not alice) gains 4 life.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Nature's Claim"], battlefield=["Forest"])
        .player("bob", battlefield=["Mind Stone"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mind_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Nature's Claim", forest, targets=[mind_stone])

    assert mind_stone.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 24
    assert scenario.player("alice").life == 20


def test_last_breath_exiles_and_gains_the_targets_controller_life():
    """Last Breath: "Exile target creature with power 2 or less. Its
    controller gains 4 life." A different verb (exile, not destroy) and a
    different mana value, proving the fix is the shared referent-clause
    parser, not a Nature's Claim-specific patch.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Last Breath"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Last Breath", *sources, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert scenario.player("bob").life == 24
    assert scenario.player("alice").life == 20

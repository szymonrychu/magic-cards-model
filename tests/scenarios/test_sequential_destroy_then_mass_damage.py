"""Extinguisher Battleship: "When this Spacecraft enters, destroy target
noncreature permanent. Then this Spacecraft deals 4 damage to each creature."

CR 608.2c: a resolving ability's instructions happen in the order printed, and
"then" is not a second, independent triggered ability the way CR 603.12's
"When you do" is - it is one instruction with two parts. `_parse_targeted_
clause` already reads "destroy target X" (`_DESTROY_TARGET_RE`) and "deals N
damage to each creature" (`_DAMAGE_EACH_CREATURE_RE`, new for this card) as two
ordinary clauses of the same ability; `_CLAUSE_SEPARATOR` already splits on a
bare "then" (Living End's own three-clause sentence proves that), so no new
combined-clause parser is needed here - only the second clause's own reader,
`damage_each_creature`.

CR numbers verified this session with `knowledge_search(q="...", type="rules")`:

- **CR 608.2c** - a resolving ability does what it says, "in the order... in
  which the instructions appear in its text".
- **CR 701.8a** - to destroy is to move a permanent to its owner's graveyard.
- **CR 119.3, 120.3a** - damage marked on a permanent, and creatures die to it
  as a state-based action (CR 704.5g) once `resolve_top` checks afterward, not
  before.
- **CR 102.2** is deliberately *not* what "each creature" means here: unlike
  Guttersnipe's "each opponent", this names every creature on the battlefield
  regardless of controller - both alice's own and bob's die below.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

BATTLESHIP = "Extinguisher Battleship"


def _battleship_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[BATTLESHIP],
            battlefield=["Sol Ring", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
    )


def test_destroys_the_target_then_deals_four_to_every_creature():
    """The happy path: a noncreature permanent dies to the first clause, and
    every creature on the battlefield - both players' - dies to the second,
    in that order (CR 608.2c)."""
    scenario = _battleship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.put_onto_battlefield(BATTLESHIP, "alice")
    scenario.choose_trigger_targets(BATTLESHIP, [sol_ring])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert sol_ring.zone is Zone.GRAVEYARD, "CR 701.8a: destroyed by the first clause"
    assert bears.zone is Zone.GRAVEYARD, "2 toughness, 4 damage (CR 704.5g)"
    assert giant.zone is Zone.GRAVEYARD, "3 toughness, 4 damage - not CR 102.2's 'each opponent'"


def test_the_battleship_itself_survives_since_it_is_not_yet_a_creature():
    """Station's own text: "It's an artifact creature at 5+" charge counters
    (CR 205.2a). A freshly entered Spacecraft with none is not a creature at
    all, so "deals 4 damage to each creature" never names it - it deals the
    damage, but does not take any."""
    scenario = _battleship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)

    battleship = scenario.put_onto_battlefield(BATTLESHIP, "alice")
    scenario.choose_trigger_targets(BATTLESHIP, [sol_ring])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert battleship.zone is Zone.BATTLEFIELD
    assert battleship.damage == 0


def test_a_creature_target_is_illegal_so_the_first_clause_alone_does_nothing():
    """The target restriction is "noncreature permanent" - a creature is not a
    legal choice at all (CR 601.2c fails to announce it), so this proves the
    restriction is actually enforced rather than merely printed."""
    scenario = _battleship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    scenario.put_onto_battlefield(BATTLESHIP, "alice")
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(BATTLESHIP, [giant])


def test_the_targets_death_in_response_fizzles_the_whole_ability():
    """CR 608.2b: "If all its targets, for every instance of the word
    'target,' are illegal, the spell or ability doesn't resolve." This
    ability names exactly one target in the whole of its text - the destroy
    clause's own - so once that one target is gone, none of it happens: not
    the destroy (nothing left to destroy anyway), and not the untargeted mass
    damage either, unlike a card whose clauses could fizzle independently.
    """
    scenario = _battleship_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    battleship = scenario.put_onto_battlefield(BATTLESHIP, "alice")
    scenario.choose_trigger_targets(BATTLESHIP, [sol_ring])
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(sol_ring)  # gone before the trigger resolves
    assert sol_ring.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD, (
        "CR 608.2b: the whole ability fizzled, not just the destroy"
    )
    assert battleship.zone is Zone.BATTLEFIELD

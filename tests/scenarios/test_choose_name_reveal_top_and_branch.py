"""Scenario: "chooses a card name, then reveals the top card [of a
library] ... If that card has the chosen name, [it goes to hand]. [If it
does not, some other consequence.]" - CR 608.2c's resolving ability doing
exactly what it is printed to do, CR 701.20a's reveal, and CR 201.4a's plain
name comparison.

Vexing Arcanix: "{3}, {T}: Target player chooses a card name, then reveals
the top card of their library. If that card has the chosen name, that
player puts it into their hand. Otherwise, they put it into their graveyard
and this artifact deals 2 damage to them." Before this file, `machines/
effects.py`'s own `_DAMAGE_THAT_PLAYER_RE` (a bare `.*` in front of "deals N
damage to that player") matched the *tail* of this whole paragraph and
reported the card `handled` while silently discarding the naming choice,
the reveal, and the hand branch outright - `scripts/sweep_pool.py --card
"Vexing Arcanix"` said `handled` for a card that could not actually put
anything into anyone's hand.

Conundrum Sphinx (a second, real, Modern-legal printing of the same core
mechanic - not the reported card): "Whenever this creature attacks, each
player chooses a card name. Then each player reveals the top card of their
library. If the card a player revealed has the name they chose, that player
puts it into their hand. If it doesn't, that player puts it on the bottom of
their library." Same choose/reveal/compare core
(`machines.effects._ask_name_reveal_top_and_branch`), a group subject and a
different miss action instead of Vexing Arcanix's single target and damage
rider.

Every CR number here was looked up with `mise run rules:find <n>` in the
session that wrote this file:

- **CR 608.2c** - the controller of a resolving ability follows its
  instructions in the order written.
- **CR 701.20a** - revealing a card.
- **CR 201.4a** - a card "has" a name if that name is printed on it (or, for
  a nameless token, an ability grants it one).
- **CR 609.3** / **CR 101.3** - an effect that attempts something
  impossible (nothing to reveal) does only as much as possible.
- **CR 101.4** - APNAP order for simultaneous choices among several
  players.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

ARCANIX = "Vexing Arcanix"
SPHINX = "Conundrum Sphinx"


def _activate_arcanix(scenario: Scenario, *, targets):
    arcanix = scenario.find(ARCANIX, Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    return scenario.activate(arcanix, *sources, targets=targets)


# --------------------------------------------------------------------------
# Vexing Arcanix
# --------------------------------------------------------------------------


def test_a_matching_name_goes_to_the_targets_hand_with_no_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[ARCANIX, "Forest", "Forest", "Forest"],
            library=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top = alice.library[0]
    life_before = alice.life

    scenario.will_choose("Lightning Bolt", source=ARCANIX)
    _activate_arcanix(scenario, targets=["alice"])
    scenario.resolve_top()

    assert top.zone is Zone.HAND
    assert alice.life == life_before


def test_an_unmatched_name_goes_to_the_graveyard_and_deals_2_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=[ARCANIX, "Forest", "Forest", "Forest"])
        .player("bob", library=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    top = bob.library[0]
    life_before = bob.life

    scenario.will_choose("Counterspell", source=ARCANIX)
    _activate_arcanix(scenario, targets=["bob"])
    scenario.resolve_top()

    assert top.zone is Zone.GRAVEYARD
    assert bob.life == life_before - 2


def test_an_empty_library_leaves_the_ability_with_nothing_to_do():
    """CR 609.3/CR 101.3: no top card to reveal means the whole instruction
    does as much as possible, which here is nothing at all - not even the
    naming question, since nothing could ever be compared against it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[ARCANIX, "Forest", "Forest", "Forest"], library=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    life_before = alice.life

    _activate_arcanix(scenario, targets=["alice"])
    scenario.resolve_top()

    assert alice.life == life_before
    assert scenario.game.decisions.asked == []


# --------------------------------------------------------------------------
# Conundrum Sphinx: the second, differently-shaped real printing
# --------------------------------------------------------------------------


def test_each_attacking_players_own_library_is_named_and_revealed_independently():
    """Alice's own chosen name matches her own top card (Lightning Bolt goes
    to her hand); bob's chosen name does not match his own top card (Forest
    goes to the bottom of his library) - each player names and reveals only
    their own library, never the other's."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[SPHINX],
            library=["Lightning Bolt"],
        )
        .player("bob", library=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sphinx = scenario.creature(SPHINX)
    alice_top = scenario.player("alice").library[0]
    bob_top = scenario.player("bob").library[0]

    scenario.will_choose("Lightning Bolt", username="alice", source=SPHINX)
    scenario.will_choose("Counterspell", username="bob", source=SPHINX)
    scenario.attack_with(sphinx)
    scenario.resolve_top()

    assert alice_top.zone is Zone.HAND
    assert bob_top.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1] is bob_top

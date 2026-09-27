"""Scenario: "If [noncombat |combat ]damage would be dealt to you, prevent that
damage[. You gain life equal to the damage prevented this way.]"

A permanent's static prevention effect aimed at its controller, read off
oracle text by `machines/replacement.py`'s `_compile_prevent_damage_to_you`.
Purity is the only printing carrying the CR 615.5 life-gain rider on this
static (a Scryfall search for the rider across every format returns it alone),
so the generality of the template is the parser's: the qualifier word and the
rider are each read, never pinned to one card.

- CR 615.1a: "Effects that use the word 'prevent' are prevention effects."
- CR 615.5: the additional effect "may refer to the amount of damage that was
  prevented ... the rest of the effect takes place immediately afterward."
- CR 120.2a / 120.2b: combat damage versus damage dealt as an effect of a
  spell or ability - "noncombat" leaves the first alone.
- CR 604.2: a static ability's effect is active only while the permanent
  remains on the battlefield.
- CR 615.12: against damage that can't be prevented the effect applies but
  prevents nothing, so "the damage prevented this way" is zero.

Every CR number here was looked up with `scripts/cr.sh` in the session that
wrote this file: 615.1a, 615.5, 120.2a, 120.2b, 604.2, 615.12.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*, bob_battlefield=(), alice_hand=None, alice_battlefield=()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Plains"],
            hand=alice_hand or [],
            battlefield=["Purity", "Grizzly Bears", *alice_battlefield],
        )
        .player(
            "bob",
            library=["Mountain"],
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Goblin Guide", *bob_battlefield],
        )
    )


def _bob_bolts(scenario, target) -> None:
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[target])


def test_a_burn_spell_aimed_at_puritys_controller_is_prevented_and_gains_that_much():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    _bob_bolts(scenario, alice)

    assert alice.life == 23


def test_a_damage_trigger_is_prevented_and_gains_that_much_too():
    """Guttersnipe's "deals 2 damage to each opponent" is an ability's
    damage (CR 120.2b), and the Bolt it triggered on is prevented as well."""
    scenario = _board(bob_battlefield=["Guttersnipe"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[alice])
    scenario.resolve_top()  # Guttersnipe's trigger
    assert alice.life == 22
    scenario.resolve_top()  # Lightning Bolt

    assert alice.life == 25


def test_direct_noncombat_damage_is_prevented_and_the_prevented_amount_is_gained():
    scenario = _board().build()
    alice = scenario.player("alice")
    guide = scenario.creature("Goblin Guide", "bob")

    assert scenario.game.deal_damage(alice, 4, source=guide) == 0
    assert alice.life == 24


def test_combat_damage_to_puritys_controller_is_not_prevented():
    """CR 120.2a: an unblocked attacker's damage is combat damage, which
    "noncombat" leaves alone - here Bob controls Purity and Alice attacks."""
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Grizzly Bears"])
        .player("bob", library=["Mountain"], battlefield=["Purity"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")
    scenario.no_blocks()

    scenario.combat_damage()

    assert scenario.player("bob").life == 18


def test_damage_to_puritys_controllers_creatures_is_not_affected():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _bob_bolts(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_damage_to_the_opponent_is_not_affected():
    scenario = _board().build()
    bob = scenario.player("bob")

    assert scenario.game.deal_damage(bob, 3, source=scenario.creature("Purity", "alice")) == 3
    assert bob.life == 17
    assert scenario.player("alice").life == 20


def test_the_effect_stops_once_purity_leaves_the_battlefield():
    scenario = _board().build()
    alice = scenario.player("alice")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.game.destroy(scenario.creature("Purity", "alice"))

    assert scenario.game.deal_damage(alice, 3, source=guide) == 3
    assert alice.life == 17


def test_unpreventable_damage_is_dealt_and_nothing_is_gained():
    """CR 615.12 - Skullcrack's "Damage can't be prevented this turn.": the
    effect applies, prevents nothing, so "the damage prevented this way" is
    zero and no life is gained."""
    scenario = _board(alice_hand=["Skullcrack"], alice_battlefield=["Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Skullcrack", *mountains, username="alice", targets=["bob"])

    assert scenario.game.deal_damage(alice, 2, source=scenario.creature("Goblin Guide", "bob")) == 2
    assert alice.life == 18


def test_two_purities_prevent_once_and_gain_once():
    """CR 615.5's rider is the applied effect's own: once the first Purity has
    prevented the damage there is none left for the second to prevent."""
    scenario = _board(alice_battlefield=["Purity"]).build()
    alice = scenario.player("alice")

    scenario.game.deal_damage(alice, 3, source=scenario.creature("Goblin Guide", "bob"))

    assert alice.life == 23


def test_puritys_static_line_is_credited_as_handled():
    from magic_cards_model.support import card_support
    from tests.cards import card

    support = card_support(card("Purity"))
    static = [clause for clause in support.clauses if clause.text.startswith("If noncombat damage")]
    assert static and all(clause.outcome == "handled" for clause in static)

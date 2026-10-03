"""Hope-Ender Coatl: "When you cast this spell, counter target spell an
opponent controls unless they pay {1}." - the *cast-trigger* twin of
Censor's/Mystical Dispute's plain "unless its controller pays {N}" spell
shape (`_counter_unless_pays_effect`), read the same way but through a
triggered ability rather than the resolving spell's own text, and with the
antecedent spelled "they" (answering back to "an opponent controls") rather
than repeating "its controller".

Every CR number below was looked up with `mise run rules:find <number>` in
the session that wrote this file.

- **CR 603.2 / CR 601.2i** - the cast trigger fires the moment the spell
  becomes cast, before it resolves; **CR 603.3** puts it on the stack above
  Hope-Ender Coatl itself.
- **CR 118.12a** - "[Do something] unless [a player does something else]"
  means "[a player] may [do something else]. If [that player] doesn't, [do
  something]." - so paying here is what *avoids* the counter, the opposite
  polarity from the punisher template's own "any player may ... . If a
  player does, counter ..." (`test_cast_trigger_punisher.py`).
- **CR 118.3** - a player can't pay a cost without the resources to pay it
  fully.
- **CR 701.6a** - to counter a spell removes it from the stack; a countered
  spell goes to its owner's graveyard.

Hope-Ender Coatl's own 2024-06-07 ruling (verified against Scryfall's
rulings text this session): "Hope-Ender Coatl's triggered ability will
resolve before Hope-Ender Coatl does. If Hope-Ender Coatl is countered or
otherwise leaves the stack in response to that triggered ability, the
triggered ability will still resolve as normal."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", life=20, hand=["Hope-Ender Coatl"], battlefield=["Island"] * 3)
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=bob_battlefield)
    )


def _cast_bolt_then_coatl(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")
    (red,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", red, username="bob", targets=[alice])
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Hope-Ender Coatl", [bolt])
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Hope-Ender Coatl", *islands, username="alice")
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Hope-Ender Coatl",
        "Hope-Ender Coatl's triggered ability",
    ]
    return alice, bolt


def test_paying_the_one_mana_lets_the_targeted_spell_through():
    scenario = _board(bob_battlefield=["Mountain", "Wastes"]).build()
    alice, bolt = _cast_bolt_then_coatl(scenario)

    scenario.will_pay_the_mana_cost(
        True, username="bob", source="Hope-Ender Coatl's triggered ability"
    )

    scenario.resolve_top()  # the cast trigger

    assert bolt.zone is Zone.STACK
    assert scenario.stack_names() == ["Lightning Bolt", "Hope-Ender Coatl"]

    scenario.resolve_top()  # Hope-Ender Coatl itself, entering the battlefield
    scenario.resolve_top()  # the Bolt, never countered

    assert alice.life == 17


def test_declining_to_pay_counters_the_targeted_spell():
    scenario = _board(bob_battlefield=["Mountain", "Wastes"]).build()
    alice, bolt = _cast_bolt_then_coatl(scenario)

    scenario.will_pay_the_mana_cost(
        False, username="bob", source="Hope-Ender Coatl's triggered ability"
    )

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Hope-Ender Coatl"]
    assert alice.life == 20


def test_a_player_with_no_mana_available_cannot_choose_to_pay():
    """CR 118.3: bob has tapped out casting Lightning Bolt and controls no
    other mana source, so paying {1} is not a real option (CR 608.2d), and
    the unscripted default takes the only legal answer."""
    scenario = _board(bob_battlefield=["Mountain"]).build()
    alice, bolt = _cast_bolt_then_coatl(scenario)

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert alice.life == 20

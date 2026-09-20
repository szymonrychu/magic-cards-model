"""Scenario: "You may pay `<N>`. If you do, `<consequence>`." (CR 118.12) -
Proft, Consulting Detective's own "Whenever you scry or surveil, you may pay
{2}. If you do, put a +1/+1 counter on Proft and draw a card."

`_parse_reflexive_pay_mana_clause` already read the same grammar for "When
you do" - Lich's Relic's own CR 603.12 reflexive trigger, a second object on
the stack with its own target announced later (`test_per_opponent_targets.py`).
"If you do" is not that shape: CR 118.12's own consequence runs immediately,
on the very same resolving ability, with no second stack object and nothing
announced later - the same distinction `_parse_may_pay_energy_if_you_do_
clause` already draws for energy. Proft's own consequence needed no target of
its own ("Proft" and "a card" are both fixed), so nothing here ever surfaced
the missing "if you do" mana twin until this card's own probe: the whole
trigger simply resolved doing nothing, silently.

`_parse_may_pay_mana_if_you_do_clause` reads it. Aphelia, Viper Whisperer is
the off-pool generality proof: a different trigger ("whenever `<self>`
attacks", not "whenever you scry or surveil"), a hybrid mana cost
({1}{B/G}, not a plain {2}), and a token-creation consequence rather than a
self-counter-and-draw.

Verified this session with `mise run rules:find` (on-disk CR effective
2026-09-25):

- **CR 118.12** - "[A player] may [do something]. If [that player] [does,
  doesn't, or can't], [effect]." - the consequence answered by whether the
  cost was paid, on the same resolving object.
- **CR 601.2h/118.3** - paying an optional cost as an ability resolves.
- **CR 701.22a/701.25a** - scry and surveil, Proft's own trigger condition
  (`test_scry_or_surveil_trigger.py`).
- **CR 508.1** - declaring attackers, Aphelia's own trigger condition.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_proft_pays_two_and_gets_a_counter_and_a_card_when_scrying():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Proft, Consulting Detective", "Island", "Island"],
            library=["Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proft = scenario.creature("Proft, Consulting Detective", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.will_pay_the_mana_cost(True, source="Proft, Consulting Detective")

    scenario.game.scry("alice", 1, source="Proft, Consulting Detective")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Proft, Consulting Detective's triggered ability"]
    scenario.pass_until_resolved()

    assert proft.counter_count(Counter.PLUS_ONE) == 1
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.stack_names() == [], "CR 118.12: no second stack object at all"


def test_proft_declining_the_payment_gets_neither():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Proft, Consulting Detective", "Island"],
            library=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proft = scenario.creature("Proft, Consulting Detective", "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.scry_keeping_everything_on_top(username="alice")
    scenario.will_pay_the_mana_cost(False, source="Proft, Consulting Detective")

    scenario.game.scry("alice", 1, source="Proft, Consulting Detective")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert proft.counter_count(Counter.PLUS_ONE) == 0
    assert len(scenario.player("alice").hand) == hand_before


def test_aphelia_pays_hybrid_mana_and_creates_a_snake_token_off_pool():
    """Off-pool generality proof: Aphelia, Viper Whisperer's own attack
    trigger - a hybrid mana cost, a different trigger event, and a token
    consequence rather than a self-counter-and-draw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Aphelia, Viper Whisperer", "Swamp", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    aphelia = scenario.creature("Aphelia, Viper Whisperer", "alice")
    scenario.will_pay_the_mana_cost(True, source="Aphelia, Viper Whisperer")

    scenario.attack_with(aphelia)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Aphelia, Viper Whisperer's triggered ability"]
    scenario.pass_until_resolved()

    snakes = [
        state
        for state in scenario.game.battlefield
        if state.name == "Snake Token" and state.zone is Zone.BATTLEFIELD
    ]
    assert len(snakes) == 1
    assert scenario.stack_names() == []

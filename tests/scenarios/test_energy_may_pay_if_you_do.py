"""Scenario: "you may pay `<energy>`. If you do, `<consequence>`." (CR
118.12, CR 107.14) - a cost paid within the same resolution, not CR 603.12's
reflexive-ability creation (`_REFLEXIVE_MAY_PAY_ENERGY_RE`'s own "When you
do," shape, already read elsewhere for Guide of Souls).

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Aether Chaser**: "Whenever this creature attacks, you may pay {E}{E}. If
  you do, create a 1/1 colorless Servo artifact creature token." A fixed
  amount.
- **Aether Refinery** (a second, richer shape on the same theme): "{T}: You
  get {E}, then you may pay one or more {E}. If you do, create an X/X black
  Aetherborn creature token, where X is the amount of {E} paid this way." A
  variable amount (CR 608.2d), sizing the created token by what was actually
  paid.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_aether_chaser_creates_a_servo_when_the_energy_is_paid():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aether Chaser"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.add_player_counters(scenario.player("alice"), Counter.ENERGY, 2)
    scenario.will_pay_the_energy(True)

    chaser = scenario.creature("Aether Chaser", "alice")
    scenario.attack_with(chaser)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 0
    servos = [
        state
        for state in scenario.game.battlefield
        if state.token and "Servo" in (state.card.type_line or "")
    ]
    assert len(servos) == 1


def test_aether_chaser_creates_nothing_when_the_energy_is_declined():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aether Chaser"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.add_player_counters(scenario.player("alice"), Counter.ENERGY, 2)
    scenario.will_pay_the_energy(False)

    chaser = scenario.creature("Aether Chaser", "alice")
    scenario.attack_with(chaser)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("alice").energy == 2
    servos = [state for state in scenario.game.battlefield if state.token]
    assert servos == []


def test_aether_refinery_sizes_the_token_by_the_amount_of_energy_paid():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Aether Refinery"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.add_player_counters(scenario.player("alice"), Counter.ENERGY, 3)
    scenario.will_pay_energy_amount(3)

    refinery = scenario.find("Aether Refinery", Zone.BATTLEFIELD, "alice")
    scenario.activate(refinery)
    scenario.pass_until_resolved()

    # Aether Refinery's own other static line doubles every {E} a player
    # *gets*: the starting 3 became 6, and the ability's own "you get {E}"
    # became 2, for 8 available before paying - but paying is a different
    # event from getting, so the 3 actually paid is untouched by that
    # doubling, and so is the token it sizes.
    assert scenario.player("alice").energy == 5
    aetherborns = [
        state
        for state in scenario.game.battlefield
        if state.token and "Aetherborn" in (state.card.type_line or "")
    ]
    assert len(aetherborns) == 1
    assert aetherborns[0].power == 3
    assert aetherborns[0].toughness == 3

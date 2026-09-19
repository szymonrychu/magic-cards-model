"""Emrakul, the Exigent Doom's own exile-from-hand activated ability:

"{3}, Exile this card from your hand: Target land gains "{T}: Add {C}{C}"
until this card is cast from exile. You may cast this card for as long as
it remains exiled."

Three things happen when this resolves, none of them printed as a keyword:

1. CR 113.10a's grant of an activated ability - `_parse_gains_ability_clause`
   already reads this shape self-referentially (Urza's Saga's own chapter I,
   "This Saga gains..."), widened here to a *targeted* permanent
   (`_parse_target_gains_ability_until_cast_from_exile_clause`).
2. An expiry tied to a game event rather than a turn boundary: a
   `DelayedTrigger` watching `TriggerEvent.CAST_SPELL` for the *exiled card
   itself*, not the land - two different objects, the split
   `machines/delayed.StaticPrisonReturn`'s own docstring already argues for
   its own delayed trigger.
3. CR 601.3's grant to cast the exiled card itself, "for as long as it
   remains exiled" - `_parse_self_cast_while_exiled_clause`, the self-
   referential ("this card") sibling of `_PLAY_PERMISSION_RE`'s "it"/"that
   card" shape, which always paired with an antecedent exile *clause* in the
   effect text; here the exile already happened as the activation's own
   *cost*, so there is nothing to pair with.

The cost itself - "Exile this card from your hand" - is CR 113.6j's own
shape (`machines/abilities._activated_ability_zone`), the same rule Channel
already reads for "discard this card"; the only new thing is exiling in
place of discarding, verified because discarding is unconditionally a hand-
to-graveyard move (CR 701.9a) and so never has to spell "from your hand" out,
while exiling does.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 113.6j** - an activated ability whose cost cannot be paid on the
  battlefield functions from any zone where it can be.
- **CR 113.10a** - a granted activated ability carries whatever activation
  instructions the granting effect prints.
- **CR 113.7a** - an ability exists on the stack independently of its source,
  which can still be found by CR 400.7 identity if it has not left the zone
  the ability expects.
- **CR 601.3** - a rule or effect must allow a cast; CR 400.7's "as long as
  it remains exiled" is that allowance staying live for exactly this exiled
  incarnation of the card.
- **CR 603.7 / CR 603.7c** - a delayed triggered ability, and its own
  "still there, same incarnation" recheck at resolution.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario, mana_from


def _board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Exigent Doom"],
            battlefield=["Wastes", "Wastes", "Wastes", "Forest"],
        )
    )


def _activate(scenario) -> tuple:
    emrakul = scenario.find("Emrakul, the Exigent Doom", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes")
    activation = off_battlefield_activation(scenario.game, emrakul, "alice", targets=[forest])
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    return emrakul, forest


def test_activating_exiles_the_card_and_grants_the_land_a_mana_ability():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    emrakul, forest = _activate(scenario)

    assert emrakul.zone is Zone.EXILE
    assert forest.granted_ability_texts == ("{T}: Add {C}{C}",)


def test_the_granted_mana_ability_actually_taps_for_two_colorless():
    """The grant is not just recorded text - the land really produces two
    colorless mana when tapped, through the same `CostPayment.tap_for_mana`
    `test_urzas_saga.py`'s identical check already uses for its own granted
    mana ability. Forest's own printed `{T}: Add {G}` is index 0, so the
    granted `{T}: Add {C}{C}` - appended after it - is index 1."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _emrakul, forest = _activate(scenario)

    payment = scenario.game.begin_activating(forest, 1, "alice")
    payment.tap_for_mana(forest, mana_from(forest, color=Color.COLORLESS))

    assert payment.pool.floating == {Color.COLORLESS: 2}
    assert forest.tapped


def test_the_permission_lets_emrakul_be_cast_from_exile():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul, _forest = _activate(scenario)

    permission = scenario.game.play_permission_for(emrakul, "alice")
    assert permission is not None
    assert permission.zone is Zone.EXILE
    assert permission.pays_mana_cost is True
    assert permission.until_end_of_turn is False


def test_the_permission_survives_a_turn_change_since_it_is_not_turn_boxed():
    """Unlike a plain CR 601.3 "you may cast it this turn" grant, "for as
    long as it remains exiled" carries no turn boundary at all."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul, _forest = _activate(scenario)

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert scenario.game.play_permission_for(emrakul, "alice") is not None


def test_casting_emrakul_from_exile_revokes_the_lands_granted_ability():
    """The delayed trigger fires the moment the *specific exiled card* is
    cast, not on any other spell - and strips exactly the text it granted,
    leaving the land's own printed ability untouched. `pays_mana_cost=True`
    (`test_the_permission_lets_emrakul_be_cast_from_exile`) means the {10}
    is still owed in full - eleven more Wastes on top of the three the
    activation already spent."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Exigent Doom"],
            battlefield=["Wastes"] * 14 + ["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    emrakul, forest = _activate(scenario)
    assert forest.granted_ability_texts == ("{T}: Add {C}{C}",)

    casting = scenario.cast("Emrakul, the Exigent Doom", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    payment = casting.begin_paying()
    for source in scenario.untapped_sources(*["Wastes"] * 10, username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert forest.granted_ability_texts == ()
    assert mana_from(forest) == [Color.GREEN]


def test_a_different_spell_being_cast_does_not_revoke_the_grant():
    """`DelayedTrigger.subject_id` scopes the watch to the one exiled card by
    its own CR 400.7 identity - any other cast, even by the same
    controller, must leave the land's granted ability alone."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Exigent Doom", "Lightning Bolt"],
            battlefield=["Wastes", "Wastes", "Wastes", "Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _emrakul, forest = _activate(scenario)
    assert forest.granted_ability_texts == ("{T}: Add {C}{C}",)

    (mountain,) = scenario.untapped_sources("Mountain")
    bob = scenario.player("bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bob])

    assert forest.granted_ability_texts == ("{T}: Add {C}{C}",)

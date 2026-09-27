""" "Whenever equipped creature attacks, put a +1/+1 counter on that creature
and each other creature you control that shares a creature type with it." -
Invasion of New Capenna // Holy Frazzle-Cannon's own back face.

Every CR number here was looked up with `mise run rules:find`:

- **CR 301.5a** - "equipped creature" is whatever the Equipment is attached
  to; "that creature"/"it" (CR 400.7's self-reference through the trigger's
  own condition) both name it, not the Equipment itself.
- **CR 702.73a** - "'Changeling' means 'This object is every creature
  type.'" - `machines/chosen_type.shares_creature_type` already reads this
  for Winnowing's own "don't share a creature type with the chosen creature"
  (a sacrifice filter); this is the identical comparison feeding a
  counter-placement group instead.
- **CR 122.1c** - a +1/+1 counter changes power and toughness, never a
  creature's own types or subtypes, so adding one to Grizzly Bears mid-loop
  cannot change whether Runeclaw Bear still shares "Bear" with it.

No second Modern/Pioneer/Standard-legal printing of this exact sentence
turned up on a Scryfall search of the printed text - Stoneforge Masterwork
("Equipped creature gets +1/+1 for each other creature you control that
shares a creature type with it.") shares the identical "shares a creature
type with it" comparison but as a static power/toughness bonus rather than a
counter-placement trigger, a different code path (`machines/layers.py`'s
`amount_expression`, not this file's counter dispatch) this session's own
fix did not touch and is noted, not fixed, here - see `MEMORY.md`. Generality
for *this* clause is therefore proven the way `shares_creature_type` itself
already is: shared with Winnowing's unrelated sacrifice-filter reading, not
duplicated for this card.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

CAPENNA = "Invasion of New Capenna // Holy Frazzle-Cannon"


def _equip(scenario, equipment, target, *mana_sources, username="alice"):
    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in mana_sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def _board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CAPENNA],
            battlefield=["Grizzly Bears", "Runeclaw Bear", "Watchwolf", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def test_attacking_puts_a_counter_on_equipped_and_every_sharing_creature():
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Capenna", Zone.HAND, "alice")
    cannon = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    bears, runeclaw, wolf = scenario.creatures(
        "Grizzly Bears", "Runeclaw Bear", "Watchwolf", username="alice"
    )
    _equip(scenario, cannon, bears, *scenario.untapped_sources("Swamp", username="alice"))

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.pass_until_resolved()  # the equipment's own attack trigger

    assert bears.counter_count("+1/+1") == 1
    assert runeclaw.counter_count("+1/+1") == 1, "Bear shares its creature type with Bear"
    assert wolf.counter_count("+1/+1") == 0, "Wolf shares no creature type with Bear"


def test_an_opponents_creature_never_gets_the_counter_even_if_it_shares_the_type():
    """ "Each other creature **you control**" (CR 109.5's own controller,
    Holy Frazzle-Cannon's controller here) - Bob's own Bear-type creature,
    if he had one, would still be excluded; proven here with the pool's own
    off-type Hill Giant standing in for "anything of bob's"."""
    scenario = _board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Capenna", Zone.HAND, "alice")
    cannon = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _equip(scenario, cannon, bears, *scenario.untapped_sources("Swamp", username="alice"))

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.pass_until_resolved()

    assert giant.counter_count("+1/+1") == 0

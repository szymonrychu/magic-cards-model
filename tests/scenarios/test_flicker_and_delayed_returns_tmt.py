"""Scenario: TMT T7's three flicker/delayed-return shapes.

- **Don & Leo, Problem Solvers**: "At the beginning of your end step, exile
  up to one target artifact you control and up to one target creature you
  control. Then return them to the battlefield under their owners'
  control." Two *independent* CR 115.6 "up to one" targets of different
  descriptions, exiled and returned together as new objects (CR 400.7).
- **The Neutrinos**: "Whenever The Neutrinos attack, exile up to one target
  creature you own, then return it to the battlefield under your control
  tapped and attacking." CR 508.4: a creature put onto the battlefield
  attacking was never *declared* an attacker, so it is unaffected by
  declaration-time restrictions (CR 508.4c) - including summoning sickness -
  and reads as joining the attack The Neutrinos itself is already making.
- **Koya, Death from Above**: "When Koya enters, exile up to one other
  target creature. At the beginning of the next end step, you may pay
  {3}{B}. If you don't, return that card to the battlefield under its
  owner's control." CR 118.12's optional-payment "unless" shape, read the
  same direction Summoner's Pact's own "pay or lose" already is
  (`test_pact_delayed_upkeep_cost.py`), except not paying triggers CR 610.3's
  return instead of a loss.

Proof printing (Modern/Pioneer-legal, already in the fixture pool, not one
of the cards above and not in any deck list): **Displace** - "Exile up to
two target creatures you control, then return those cards to the
battlefield under their owner's control." A single "up to two" requirement
(not two independent "up to one" ones) naming its own subjects "those
cards" rather than "them", proving the shared exile-then-return-together
machinery (`entering_together`, CR 603.6a) Don & Leo's own multi-target
reader is built directly on top of already generalises across wording. No
second real printing shares Don & Leo's own "two distinct simultaneous 'up
to one' target descriptions" grammar at all - verified by a Scryfall
full-text oracle search that returns Don & Leo alone - recorded as a dated
line in `MEMORY.md`.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 115.6 (up to one/any number may choose zero), 400.7 (a moved
object is new, no memory of counters or summoning sickness), 610.3/610.3c
(the return, under the owner's control by default), 603.6a (several objects
entering together see each other), 508.4/508.4c (put onto the battlefield
attacking; never declared, so declaration-time restrictions do not apply),
118.12/118.12a (the "unless" payment shape), 104.3e/104.5 (not directly
tested here - see `test_pact_delayed_upkeep_cost.py` for the parallel "pay
or lose" case this file's own "pay or else return" shares its delayed-
trigger/`may_pay_mana_cost` machinery with).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

DON_LEO = "Don & Leo, Problem Solvers"
NEUTRINOS = "The Neutrinos"
KOYA = "Koya, Death from Above"
DISPLACE = "Displace"


def test_listed_and_proof_printings_are_handled():
    for name in (DON_LEO, NEUTRINOS, KOYA, DISPLACE):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _settle(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _to_end_step(scenario):
    while scenario.step is not Step.END_STEP:
        _settle(scenario)
        scenario.advance()
    _settle(scenario)


# -- Don & Leo: two independent "up to one" targets, then return together ---


def _don_leo_board():
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[DON_LEO, "Grizzly Bears", "Mind Stone"] + ["Plains"] * 5,
        )
        .player("bob")
        .build()
    )


def test_don_and_leo_flickers_the_chosen_artifact_and_creature_as_new_objects():
    scenario = _don_leo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)
    bears_stamp_before = bears.zone_change_stamp
    scenario.choose_trigger_targets(DON_LEO, [stone, bears])

    _to_end_step(scenario)

    new_bears = scenario.creature("Grizzly Bears")
    new_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assert new_bears.zone_change_stamp != bears_stamp_before, "CR 400.7: a new object"
    assert new_bears.counter_count(Counter.PLUS_ONE) == 0, "CR 400.7/122.2: counters are gone"
    assert new_bears.summoning_sick, "CR 400.7/302.6: summoning sick again"
    assert new_bears.controller == "alice" and new_stone.controller == "alice"


def test_don_and_leo_may_choose_only_the_artifact():
    """CR 115.6: each "up to one" is independent - choosing the artifact
    alone leaves the creature untouched."""
    scenario = _don_leo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    bears.summoning_sick = False
    stone_stamp_before = stone.zone_change_stamp
    bears_stamp_before = bears.zone_change_stamp
    scenario.choose_trigger_targets(DON_LEO, [stone])

    _to_end_step(scenario)

    new_stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assert new_stone.zone_change_stamp != stone_stamp_before
    assert bears.zone_change_stamp == bears_stamp_before, "the creature was never touched"
    assert not bears.summoning_sick


def test_don_and_leo_choosing_neither_target_does_nothing():
    scenario = _don_leo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    bears_stamp = bears.zone_change_stamp
    stone_stamp = stone.zone_change_stamp
    scenario.choose_trigger_targets(DON_LEO, [])

    _to_end_step(scenario)

    assert bears.zone_change_stamp == bears_stamp
    assert stone.zone_change_stamp == stone_stamp


# -- The Neutrinos: return tapped and attacking, never declared -------------


def _neutrinos_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=[NEUTRINOS, "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_neutrinos_flickers_its_own_creature_tapped_and_attacking():
    scenario = _neutrinos_board()
    neutrinos = scenario.creature(NEUTRINOS, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears_stamp_before = bears.zone_change_stamp
    scenario.choose_trigger_targets(NEUTRINOS, [bears])

    scenario.attack_with(neutrinos, defending="bob")
    scenario.pass_until_resolved()  # the Alliance/attack triggers settle

    flickered = scenario.creature("Grizzly Bears", "alice")
    assert flickered.zone_change_stamp != bears_stamp_before, "CR 400.7: a new object"
    assert flickered.tapped
    assert flickered in scenario.attackers()
    assert scenario.game.combat.attack_by(flickered.id).defender.username == "bob"


def test_neutrinos_flickered_creature_is_summoning_sick_but_attacks_anyway():
    """CR 508.4c: a creature put onto the battlefield attacking "isn't
    affected by requirements or restrictions that apply to the declaration
    of attackers" - summoning sickness (CR 508.1a) among them."""
    scenario = _neutrinos_board()
    neutrinos = scenario.creature(NEUTRINOS, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets(NEUTRINOS, [bears])

    scenario.attack_with(neutrinos, defending="bob")
    scenario.pass_until_resolved()

    flickered = scenario.creature("Grizzly Bears", "alice")
    assert flickered.summoning_sick, "CR 400.7/302.6: a new object, sick again"
    assert flickered in scenario.attackers(), "CR 508.4c: sickness never gated this arrival"


def test_neutrinos_choosing_no_target_still_attacks_alone():
    scenario = _neutrinos_board()
    neutrinos = scenario.creature(NEUTRINOS, "alice")
    scenario.choose_trigger_targets(NEUTRINOS, [])

    scenario.attack_with(neutrinos, defending="bob")
    scenario.pass_until_resolved()

    assert scenario.attackers() == [neutrinos]


# -- Koya: optional payment gates the delayed return -------------------------


def _koya_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=[KOYA],
            battlefield=["Plains"] * 6 + ["Swamp"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
    )


def _cast_koya(scenario, target):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.choose_trigger_targets(KOYA, [target])
    scenario.cast_and_resolve(KOYA, *sources)
    scenario.pass_until_resolved()  # the ETB trigger: exile Grizzly Bears


def test_koya_exiles_the_target_immediately():
    scenario = _koya_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_koya(scenario, bears)
    assert bears.zone is Zone.EXILE


def test_koya_paying_at_the_next_end_step_keeps_the_card_in_exile():
    scenario = _koya_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_koya(scenario, bears)

    scenario.will_pay_the_mana_cost(True, username="alice", source=KOYA)
    _to_end_step(scenario)

    assert bears.zone is Zone.EXILE


def test_koya_declining_the_payment_returns_the_card_under_its_owners_control():
    scenario = _koya_board().build()
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_koya(scenario, bears)

    scenario.will_pay_the_mana_cost(False, username="alice", source=KOYA)
    _to_end_step(scenario)

    returned = scenario.creature("Grizzly Bears", "bob")
    assert returned.zone is Zone.BATTLEFIELD
    assert returned.controller == "bob", "CR 610.3c: under its owner's control"


def test_koya_unable_to_pay_returns_the_card_too():
    """No mana left to pay {3}{B} with: `may_pay_mana_cost` refuses the
    payment as illegal (CR 118.3), the same as declining outright."""
    scenario = (
        Scenario()
        .player("alice", hand=[KOYA], battlefield=["Plains"] * 3, library=["Plains"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_koya(scenario, bears)

    _to_end_step(scenario)

    returned = scenario.creature("Grizzly Bears", "bob")
    assert returned.zone is Zone.BATTLEFIELD


def test_koya_choosing_no_target_creates_no_delayed_trigger():
    scenario = _koya_board().build()
    scenario.choose_trigger_targets(KOYA, [])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.cast_and_resolve(KOYA, *sources)
    scenario.pass_until_resolved()
    assert scenario.game.delayed_triggers.triggers == []


# -- proof printing: Displace's own "up to two", single-requirement flicker -


def test_displace_blinks_two_creatures_together_as_new_objects():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[DISPLACE],
            battlefield=["Island"] * 3 + ["Grizzly Bears", "Hill Giant"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    giant = scenario.creature("Hill Giant")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 1)
    bears.tapped = True
    giant.tapped = True
    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve(DISPLACE, *sources, targets=[bears, giant])

    new_bears = scenario.creature("Grizzly Bears")
    new_giant = scenario.creature("Hill Giant")
    assert new_bears.counter_count(Counter.PLUS_ONE) == 0, "CR 400.7: a new object"
    assert not new_bears.tapped and not new_giant.tapped, "a new object enters untapped"
    assert new_bears.controller == "alice" and new_giant.controller == "alice"

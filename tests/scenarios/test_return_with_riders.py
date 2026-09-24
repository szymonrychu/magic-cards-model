"""A dies trigger that returns the creature to the battlefield with a counter
and a rider on the new object.

- Hellcat, Undying Vigilante: "When Hellcat dies, return her to the
  battlefield under her owner's control with a +1/+1 counter on her. She
  loses all abilities and gains haste." The returned Hellcat is a new object
  (CR 400.7) with no abilities (layer 6, CR 613.1f) but haste - so it does
  not come back a second time.
- Thunderbolts Conspiracy: "Whenever a Villain you control dies, return it to
  the battlefield under its owner's control with a finality counter on it.
  That creature is a Hero in addition to its other types." "It" is the
  creature that died, not the enchantment. CR 205.1b keeps every prior type;
  the finality counter exiles it the next time it would die (CR 122.1h).

The return-with-rider shape prints only on Marvel Super Heroes cards; the
two listed cards are its two wordings (the source itself, and the dying
creature named by the event).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

HELLCAT = "Hellcat, Undying Vigilante"
CONSPIRACY = "Thunderbolts Conspiracy"
VILLAIN = "Scientist Supreme of A.I.M."


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _on_battlefield(scenario, name):
    return [card for card in scenario.game.battlefield if card.name == name]


# -- Hellcat, Undying Vigilante ---------------------------------------------------


def _hellcat_dies(scenario):
    hellcat = scenario.creature(HELLCAT, "alice")
    scenario.game.destroy(hellcat)
    scenario.pass_until_resolved()
    return _on_battlefield(scenario, HELLCAT)


def test_hellcat_returns_with_a_counter_no_abilities_but_haste():
    scenario = Scenario().player("alice", battlefield=[HELLCAT]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (returned,) = _hellcat_dies(scenario)

    assert returned.counters[Counter.PLUS_ONE] == 1
    chars = _chars(scenario, returned)
    assert chars.power_toughness == (3, 3)
    assert chars.abilities == ("Haste",)


def test_the_returned_hellcat_does_not_return_again():
    """Her dies trigger was one of the abilities she lost."""
    scenario = Scenario().player("alice", battlefield=[HELLCAT]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (returned,) = _hellcat_dies(scenario)

    scenario.game.destroy(returned)
    scenario.pass_until_resolved()

    assert not _on_battlefield(scenario, HELLCAT)
    assert returned.zone is Zone.GRAVEYARD


def test_the_returned_hellcat_can_attack_at_once():
    scenario = Scenario().player("alice", battlefield=[HELLCAT]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (returned,) = _hellcat_dies(scenario)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(returned)

    assert returned in scenario.attackers()


def test_hellcat_exiled_from_the_graveyard_in_response_stays_gone():
    scenario = Scenario().player("alice", battlefield=[HELLCAT]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hellcat = scenario.creature(HELLCAT, "alice")
    scenario.game.destroy(hellcat)
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_cards([hellcat])
    scenario.pass_until_resolved()

    assert not _on_battlefield(scenario, HELLCAT)


def test_hellcat_returns_under_her_owners_control():
    """Stolen and then killed, she comes back to her owner."""
    scenario = (
        Scenario()
        .player("alice", hand=["Act of Treason"], battlefield=["Mountain"] * 3)
        .player("bob", battlefield=[HELLCAT])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hellcat = scenario.creature(HELLCAT, "bob")
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[hellcat],
    )
    scenario.game.destroy(hellcat)
    scenario.pass_until_resolved()

    (returned,) = _on_battlefield(scenario, HELLCAT)
    assert scenario.game.controller_of(returned).username == "bob"


# -- Thunderbolts Conspiracy -------------------------------------------------------


def test_a_villain_that_dies_returns_as_a_hero_with_a_finality_counter():
    scenario = Scenario().player("alice", battlefield=[CONSPIRACY, VILLAIN]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villain = scenario.creature(VILLAIN, "alice")

    scenario.game.destroy(villain)
    scenario.pass_until_resolved()

    (returned,) = _on_battlefield(scenario, VILLAIN)
    assert returned.counters[Counter.FINALITY] == 1
    subtypes = _chars(scenario, returned).subtypes
    assert "Hero" in subtypes and "Villain" in subtypes and "Scientist" in subtypes
    assert _on_battlefield(scenario, CONSPIRACY)  # "it" was never the enchantment


def test_the_returned_villain_is_exiled_the_next_time_it_would_die():
    scenario = Scenario().player("alice", battlefield=[CONSPIRACY, VILLAIN]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villain = scenario.creature(VILLAIN, "alice")
    scenario.game.destroy(villain)
    scenario.pass_until_resolved()
    (returned,) = _on_battlefield(scenario, VILLAIN)

    scenario.game.destroy(returned)
    scenario.pass_until_resolved()

    assert returned.zone is Zone.EXILE
    assert not _on_battlefield(scenario, VILLAIN)


def test_a_non_villain_dying_does_not_trigger_it():
    scenario = (
        Scenario().player("alice", battlefield=[CONSPIRACY, "Grizzly Bears"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_an_opponents_villain_dying_does_not_trigger_it():
    scenario = (
        Scenario().player("alice", battlefield=[CONSPIRACY]).player("bob", battlefield=[VILLAIN])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villain = scenario.creature(VILLAIN, "bob")

    scenario.game.destroy(villain)
    scenario.pass_until_resolved()

    assert villain.zone is Zone.GRAVEYARD


def test_a_borrowed_villain_returns_to_its_owner():
    """ "Under its owner's control": alice's Conspiracy sees her stolen Villain
    die, and it comes back on bob's side."""
    scenario = (
        Scenario()
        .player("alice", hand=["Act of Treason"], battlefield=[CONSPIRACY] + ["Mountain"] * 3)
        .player("bob", battlefield=[VILLAIN])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villain = scenario.creature(VILLAIN, "bob")
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[villain],
    )
    scenario.game.destroy(villain)
    scenario.pass_until_resolved()

    (returned,) = _on_battlefield(scenario, VILLAIN)
    assert scenario.game.controller_of(returned).username == "bob"
    assert "Hero" in _chars(scenario, returned).subtypes


def test_the_hero_type_stays_with_the_returned_object_only():
    """CR 400.7: bounced and recast, it is a new object - a Villain again,
    not a Hero."""
    scenario = Scenario().player("alice", battlefield=[CONSPIRACY, VILLAIN]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    villain = scenario.creature(VILLAIN, "alice")
    scenario.game.destroy(villain)
    scenario.pass_until_resolved()
    (returned,) = _on_battlefield(scenario, VILLAIN)

    scenario.game.return_to_hand(returned)
    again = scenario.put_onto_battlefield(VILLAIN, "alice")

    assert "Hero" not in _chars(scenario, again).subtypes

"""Scenario: Hoarding Broodlord - "When this creature enters, search your
library for a card, exile it face down, then shuffle. For as long as that card
remains exiled, you may play it. Spells you cast from exile have convoke."
and Party Thrasher's "Noncreature spells you cast from exile have convoke."

CR 701.23 (search), CR 406.3 (face-down exile), CR 601.3 and CR 400.7 (the
permission lasts only while that object stays in exile), CR 702.51a (convoke),
CR 604.2 (a static ability granting convoke to spells, here only those cast
from exile).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import play_permissions_on
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(*alice_battlefield, library=("Divination", "Island", "Island"), hand=("Divination",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice_battlefield),
            hand=list(hand),
            library=list(library),
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_enters_trigger_exiles_a_found_card_face_down_and_lets_me_play_it():
    scenario = _board("Grizzly Bears", hand=("Hoarding Broodlord",))
    found = scenario.find("Divination", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(found)
    scenario.put_onto_battlefield("Hoarding Broodlord", "alice")

    scenario.pass_until_resolved()

    assert found.zone is Zone.EXILE
    assert not found.face_up
    assert play_permissions_on(scenario.game, found)


def test_the_permission_has_no_turn_limit():
    """ "For as long as that card remains exiled" - not "this turn"."""
    scenario = _board("Grizzly Bears", hand=("Hoarding Broodlord",))
    found = scenario.find("Divination", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(found)
    scenario.put_onto_battlefield("Hoarding Broodlord", "alice")
    scenario.pass_until_resolved()
    for _ in range(14):
        scenario.advance()

    assert found.zone is Zone.EXILE
    assert play_permissions_on(scenario.game, found)


def test_a_spell_cast_from_exile_has_convoke():
    scenario = _board("Hoarding Broodlord", "Grizzly Bears", "Grizzly Bears", "Island")
    card = scenario.game.exile_permanent(scenario.find("Divination", Zone.HAND, "alice"))
    scenario.game.grant_play_permission(
        card, "alice", action=_cast(), source_name="test", rule="CR 601.3", zone=Zone.EXILE
    )
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Divination", "alice", Zone.EXILE)
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])

    assert str(payment.mana_owed) == "{U}"
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.pay_with(payment, island)
    scenario.put_on_stack(casting)
    assert bears[0].tapped and bears[1].tapped


def test_a_spell_cast_from_hand_does_not_have_convoke():
    scenario = _board("Hoarding Broodlord", "Grizzly Bears")
    bear = scenario.creature("Grizzly Bears")

    casting = scenario.cast("Divination", "alice")
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        convoke(payment, casting.spell, bear)


def test_party_thrasher_gives_convoke_only_to_noncreature_spells_from_exile():
    scenario = _board(
        "Party Thrasher", "Grizzly Bears", hand=("Divination", "Grizzly Bears")
    )
    for name in ("Divination", "Grizzly Bears"):
        card = scenario.game.exile_permanent(scenario.find(name, Zone.HAND, "alice"))
        scenario.game.grant_play_permission(
            card, "alice", action=_cast(), source_name="test", rule="CR 601.3", zone=Zone.EXILE
        )
    ours = scenario.creature("Grizzly Bears", "alice")

    spell = scenario.cast("Divination", "alice", Zone.EXILE)
    payment = spell.begin_paying()
    convoke(payment, spell.spell, ours)
    assert str(payment.mana_owed) == "{1}{U}"
    spell.cancel()

    creature_spell = scenario.cast("Grizzly Bears", "alice", Zone.EXILE)
    with pytest.raises(ValueError):
        convoke(creature_spell.begin_paying(), creature_spell.spell, ours)


def _cast():
    from magic_cards_model.machines.casting import PlayAction

    return PlayAction.CAST

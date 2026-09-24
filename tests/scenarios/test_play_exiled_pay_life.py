"""Scenario: "Exile the top <N> cards of <a library>. <Duration>, you may play
<those cards | one of those cards>. If you cast a spell this way, pay life
equal to its mana value rather than pay[ing] its mana cost."

The permission is CR 601.3's, for the effect's controller, and the rider is
an alternative cost (CR 118.9: "a cost ... that its controller may pay rather
than paying the spell's mana cost") that the permission *requires* (CR
118.9b: "An effect that allows you to cast a spell may require a certain
alternative cost to be paid"), so no mana can be paid instead. The life is
determined with the rest of the total cost (CR 601.2f), from the spell's
mana value on the stack (CR 202.3e), and can be paid only with enough life
(CR 119.4). A land is played, not cast (CR 305.2a counts it as the turn's
land play), so the rider never touches it. "This turn" ends in cleanup
(CR 514.2).

Printings: Inside Information (a spell, "the top X cards of target
opponent's library", "those cards", "rather than pay"), off-set Nashi, Moon
Sage's Scion (a combat damage trigger, "the top card of each player's
library", "one of those cards", "rather than paying") - a different ability
kind, antecedent, choice and wording, so the rider is read as the template.

CR numbers verified with `mise run rules:find`: 601.3, 118.9, 118.9b, 601.2f,
202.3e, 119.4, 305.2a, 514.2.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

NASHI = "Nashi, Moon Sage's Scion"


def test_both_printings_are_handled():
    assert card_support(card("Inside Information")).status == "handled"
    triggered = [c for c in card_support(card(NASHI)).clauses if c.kind == "triggered"]
    assert [c.outcome for c in triggered] == ["handled"]


def _inside_information(*, alice_life: int = 20, x: int = 3):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=alice_life,
            hand=["Inside Information"],
            battlefield=["Swamp"] * 5,
            library=["Island"] * 5,
        )
        .player(
            "bob",
            library=["Grizzly Bears", "Lightning Bolt", "Forest", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Inside Information", targets=["bob"])
    payment = casting.determine_cost(x_value=x)
    casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * (2 + x)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def _cast_from_exile(scenario, name: str, targets=None):
    casting = scenario.cast(name, username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    if targets is not None:
        casting.choose_targets(targets)
    return casting


def test_the_top_x_cards_of_the_opponents_library_are_exiled():
    scenario = _inside_information()
    assert sorted(c.name for c in scenario.game.exile) == [
        "Forest",
        "Grizzly Bears",
        "Lightning Bolt",
    ]
    assert [c.name for c in scenario.player("bob").library] == ["Island", "Island"]


def test_a_creature_is_cast_for_life_equal_to_its_mana_value_and_no_mana():
    scenario = _inside_information()
    alice = scenario.player("alice")
    casting = _cast_from_exile(scenario, "Grizzly Bears")
    payment = casting.begin_paying()
    assert not casting.total_cost.mana.symbols
    scenario.pay_with(payment)
    scenario.put_on_stack(casting)
    assert alice.life == 18
    scenario.resolve_top()
    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.owner == "bob"


def test_an_instant_costs_one_life_and_still_needs_its_target():
    scenario = _inside_information()
    alice = scenario.player("alice")
    casting = _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert alice.life == 19
    assert scenario.player("bob").life == 17


def test_a_land_is_played_for_no_life_as_the_turns_land_play():
    scenario = _inside_information()
    alice = scenario.player("alice")
    scenario.game.play_land(scenario.find("Forest", Zone.EXILE), "alice")
    assert alice.life == 20
    assert scenario.game.lands_played["alice"] == 1


def test_not_enough_life_means_the_spell_cannot_be_cast():
    """CR 119.4: two life cannot be paid from a life total of one."""
    scenario = _inside_information(alice_life=1)
    casting = _cast_from_exile(scenario, "Grizzly Bears")
    with pytest.raises(ValueError):
        scenario.pay_with(casting.begin_paying())
        scenario.put_on_stack(casting)
    assert scenario.player("alice").life == 1


def test_the_permission_ends_with_the_turn():
    scenario = _inside_information()
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    assert (
        scenario.game.play_permission_for(scenario.find("Grizzly Bears", Zone.EXILE), "alice")
        is None
    )


def test_x_of_zero_exiles_nothing():
    scenario = _inside_information(x=0)
    assert scenario.game.exile == []
    assert len(scenario.player("bob").library) == 5


# -- Nashi, Moon Sage's Scion: one of those cards, from each library ---------


def _nashi_hits():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[NASHI],
            library=["Grizzly Bears", "Island", "Island"],
        )
        .player("bob", library=["Lightning Bolt", "Mountain", "Island"])
        .build()
    )
    nashi = scenario.creature(NASHI, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(nashi, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    return scenario


def test_nashi_exiles_the_top_card_of_each_players_library():
    scenario = _nashi_hits()
    assert sorted(c.name for c in scenario.game.exile) == ["Grizzly Bears", "Lightning Bolt"]
    assert scenario.player("bob").life == 17


def test_nashi_one_of_those_cards_casting_one_ends_the_other():
    scenario = _nashi_hits()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    alice = scenario.player("alice")
    casting = _cast_from_exile(scenario, "Lightning Bolt", targets=["bob"])
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert alice.life == 19
    assert scenario.player("bob").life == 14
    bears = scenario.find("Grizzly Bears", Zone.EXILE)
    assert scenario.game.play_permission_for(bears, "alice") is None


def test_nashi_either_card_may_be_the_one():
    scenario = _nashi_hits()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    alice = scenario.player("alice")
    casting = _cast_from_exile(scenario, "Grizzly Bears")
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert alice.life == 18
    assert scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_nashi_playing_a_land_as_the_one_ends_the_other():
    scenario = (
        Scenario()
        .player("alice", battlefield=[NASHI], library=["Forest", "Island"])
        .player("bob", library=["Lightning Bolt", "Island"])
        .build()
    )
    nashi = scenario.creature(NASHI, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(nashi, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.game.play_land(scenario.find("Forest", Zone.EXILE), "alice")
    assert scenario.player("alice").life == 20
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    assert scenario.game.play_permission_for(bolt, "alice") is None

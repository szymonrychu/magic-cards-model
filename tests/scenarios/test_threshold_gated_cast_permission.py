"""Null Summoner: a Threshold-gated grant of CR 601.3's "mana of any type
can be spent" permission.

"When this creature enters, if you cast it, target opponent reveals their
hand. You choose a nonland card from it. Exile that card." is the same
reveal-choose-exile shape Thoughtseize's, Grief's and Thought-Knot Seer's own
triggers already read (`test_reveal_hand_and_choose.py`); nothing about it
needed to change. What is new is the card's *second*, entirely separate
ability: "Threshold — As long as there are seven or more cards in your
graveyard, you may cast the exiled card, and mana of any type can be spent
to cast that spell." - CR 604.1's own "written as a statement" shape, read
generically off whatever sibling static line the exiling permanent prints
(`_grant_cast_exiled_card_permission_from_sibling_static`), not folded into
the triggered ability that does the exiling.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import once_per_turn_key, play_permissions_on
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _permission_for(scenario: Scenario, card):
    """The raw permission Null Summoner's static ability recorded against
    `card`, refused or not - `Game.play_permission_for` only ever returns a
    permission that is *currently usable*, so a below-threshold refusal
    needs the unfiltered list instead."""
    permissions = play_permissions_on(scenario.game, card)
    return permissions[0] if permissions else None


def _board(alice_graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Null Summoner"],
            battlefield=["Island", "Island", "Swamp", "Forest", "Forest"],
            graveyard=alice_graveyard or [],
        )
        .player("bob", hand=["Lightning Bolt"])
    )


def _cast_and_exile(scenario) -> "CardState":  # noqa: F821
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    sources = scenario.untapped_sources("Island", "Island", "Swamp", "Forest", username="alice")
    scenario.choose_trigger_targets("Null Summoner", ["bob"])
    scenario.will_discard(bolt, username="alice")
    scenario.cast_and_resolve("Null Summoner", *sources, username="alice")
    scenario.pass_until_resolved()
    return bolt


def test_the_etb_trigger_still_exiles_the_chosen_card():
    """The reveal/choose/exile shape is untouched by the Threshold rider."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _cast_and_exile(scenario)

    assert bolt.zone is Zone.EXILE


def test_the_permission_refuses_below_threshold():
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 6).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _cast_and_exile(scenario)

    permission = _permission_for(scenario, bolt)
    assert permission is not None
    refusal = permission.why_not(bolt, "alice", scenario.game)
    assert refusal is not None
    assert "as long as" in refusal
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_the_permission_allows_casting_with_any_color_mana_at_threshold():
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _cast_and_exile(scenario)
    permission = scenario.game.play_permission_for(bolt, "alice")
    assert permission is not None
    assert permission.why_not(bolt, "alice", scenario.game) is None

    casting = scenario.cast("Lightning Bolt", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    assert str(casting.total_cost.mana) == "{R}"

    (forest,) = scenario.untapped_sources("Forest", username="alice")
    payment = casting.begin_paying()
    payment.tap_for_mana(forest, [Color.GREEN])
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_the_permission_never_expires_on_its_own_only_on_the_condition():
    """No `until_end_of_turn` here - CR 604.1's "as long as" is a live
    condition, not a turn-boxed grant, so the permission itself survives
    across turns and is only ever refused by the condition failing."""
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = _cast_and_exile(scenario)
    permission = _permission_for(scenario, bolt)
    assert permission is not None
    assert permission.until_end_of_turn is False

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert scenario.game.play_permission_for(bolt, "alice") is not None


def _usable(scenario: Scenario, card) -> bool:
    return scenario.game.play_permission_for(card, "alice") is not None


def test_dropping_below_threshold_mid_turn_removes_the_permission_and_regaining_restores_it():
    """CR 604.1 / CR 113.6: "as long as" is re-read each time it is asked."""
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = _cast_and_exile(scenario)
    assert _usable(scenario, bolt)

    alice = scenario.game.player("alice")
    removed = alice.graveyard.pop()
    assert not _usable(scenario, bolt)
    refusal = _permission_for(scenario, bolt).why_not(bolt, "alice", scenario.game)
    assert refusal is not None and "seven or more cards in your graveyard" in refusal

    alice.graveyard.append(removed)
    assert _usable(scenario, bolt)


def test_the_permission_ends_when_null_summoner_leaves_the_battlefield():
    """CR 113.6 / CR 611.3b: a static ability's effect lasts only while the
    permanent that has it is on the battlefield."""
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = _cast_and_exile(scenario)
    assert _usable(scenario, bolt)

    scenario.game.destroy(scenario.find("Null Summoner", Zone.BATTLEFIELD, "alice"))

    assert bolt.zone is Zone.EXILE
    assert not _usable(scenario, bolt)
    refusal = _permission_for(scenario, bolt).why_not(bolt, "alice", scenario.game)
    assert refusal is not None and "Null Summoner" in refusal


def test_entering_without_being_cast_exiles_nothing_and_grants_nothing():
    """CR 603.4: "if you cast it" is an intervening 'if'; a Summoner put onto
    the battlefield any other way never triggers."""
    scenario = _board(alice_graveyard=["Grizzly Bears"] * 7).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    scenario.put_onto_battlefield("Null Summoner", "alice")

    assert not scenario.pending_triggers
    assert bolt.zone is Zone.HAND
    assert play_permissions_on(scenario.game, bolt) == []


def test_each_summoner_permission_is_linked_to_its_own_exiled_card_only():
    """CR 607.2a: the exiled card is linked to the ability that exiled it,
    so a second Summoner's card keeps its permission when the first leaves."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Null Summoner", "Null Summoner"],
            battlefield=["Island", "Island", "Swamp", "Forest"] * 2,
            graveyard=["Grizzly Bears"] * 7,
        )
        .player("bob", hand=["Lightning Bolt", "Counterspell"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    counterspell = scenario.find("Counterspell", Zone.HAND, "bob")

    for victim in (bolt, counterspell):
        sources = scenario.untapped_sources("Island", "Island", "Swamp", "Forest", username="alice")
        scenario.choose_trigger_targets("Null Summoner", ["bob"])
        scenario.will_discard(victim, username="alice")
        scenario.cast_and_resolve("Null Summoner", *sources, username="alice")
        scenario.pass_until_resolved()
    assert bolt.zone is Zone.EXILE and counterspell.zone is Zone.EXILE
    assert _usable(scenario, bolt) and _usable(scenario, counterspell)

    first_permission = _permission_for(scenario, bolt)
    assert first_permission.while_controlling != (
        _permission_for(scenario, counterspell).while_controlling
    )
    owners = {card.id: card for card in scenario.game.permanents_controlled_by("alice")}
    summoner_of_bolt = next(
        card
        for card in owners.values()
        if once_per_turn_key(card) == first_permission.while_controlling
    )
    scenario.game.destroy(summoner_of_bolt)

    assert not _usable(scenario, bolt)
    assert _usable(scenario, counterspell)


def test_the_exiled_card_keeps_its_own_timing():
    """CR 117.1a / CR 307.1: the permission does not make a creature castable
    at instant speed."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Null Summoner"],
            battlefield=["Island", "Island", "Swamp", "Forest", "Forest"],
            graveyard=["Grizzly Bears"] * 7,
        )
        .player("bob", hand=["Grizzly Bears"])
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Swamp", "Forest", username="alice")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.choose_trigger_targets("Null Summoner", ["bob"])
    scenario.will_discard(bears, username="alice")
    scenario.cast_and_resolve("Null Summoner", *sources, username="alice")
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE

    scenario.advance("alice")  # out of the main phase
    assert scenario.step is not Step.PRECOMBAT_MAIN
    with pytest.raises(ValueError, match="117.1a|sorcery|main phase|timing"):
        casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
        casting.use_permission()
        casting.begin_paying()

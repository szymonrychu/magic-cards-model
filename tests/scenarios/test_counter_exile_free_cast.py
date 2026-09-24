"""Scenario: "Counter target spell. If <a permanent spell | that spell> is
countered this way, exile it instead of putting it into its owner's
graveyard. You may cast that card without paying its mana cost for as long
as it remains exiled."

CR 701.6a puts a countered spell into its owner's graveyard; the second
sentence replaces that destination (CR 614.1a), for Thranduil's Decree only
when the countered spell is a permanent spell (CR 110.4b: "an artifact,
battle, creature, enchantment, or planeswalker spell"). The third sentence is
a CR 601.3 permission for the countering spell's controller - "you" - with no
"this turn" on it, so it lasts for as long as the card stays in exile, and
it waives the mana cost (CR 118.9's alternative cost of nothing). CR 400.7
ends it the moment the card leaves exile.

Printings: Thranduil's Decree (a spell, "a permanent spell" rider), off-set
Kheru Spellsnatcher (a turned-face-up trigger, "that spell" rider) - a
different ability kind and a different rider, so the reader is the template.

CR numbers verified with `mise run rules:find`: 701.6a, 614.1a, 110.4b,
601.3, 118.9, 400.7, 702.37e.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def test_both_printings_are_handled():
    assert card_support(card("Thranduil's Decree")).status == "handled"
    triggered = [
        c for c in card_support(card("Kheru Spellsnatcher")).clauses if c.kind == "triggered"
    ]
    assert [c.outcome for c in triggered] == ["handled"]


def _decree_board(bob_hand: list[str], bob_lands: list[str]) -> Scenario:
    """Bob's turn first, so his sorcery-speed spell can be answered."""
    return (
        Scenario()
        .player("bob", hand=bob_hand, battlefield=bob_lands, library=["Island"] * 5)
        .player(
            "alice", hand=["Thranduil's Decree"], battlefield=["Island"] * 6, library=["Island"] * 5
        )
    )


def _bob_casts_then_alice_decrees(scenario, spell: str, *, targets=None):
    bob_spell = scenario.cast_onto_stack(spell, username="bob", auto=True, targets=targets)
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Thranduil's Decree", username="alice", auto=True, targets=[bob_spell])
    scenario.resolve_top()
    return bob_spell


def _turn_to_bobs_main(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _next_main(scenario):
    """Advance to the next turn's precombat main phase."""
    active = scenario.turn.active_player
    while scenario.turn.active_player == active or scenario.step is not Step.PRECOMBAT_MAIN:
        while scenario.game.stack:
            scenario.resolve_top()
        scenario.advance()


def test_a_countered_creature_spell_is_exiled_and_the_decree_caster_may_cast_it_free():
    scenario = _decree_board(["Grizzly Bears"], ["Forest", "Forest"]).build()
    _turn_to_bobs_main(scenario)
    bears = _bob_casts_then_alice_decrees(scenario, "Grizzly Bears")
    assert scenario.stack_names() == []
    exiled = scenario.find("Grizzly Bears", Zone.EXILE)
    assert exiled.owner == "bob"
    assert bears.zone is Zone.EXILE

    # Alice's own main phase: no mana left, and she may still cast it free.
    _next_main(scenario)
    for land in scenario.game.permanents_controlled_by("alice"):
        land.tapped = True
    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    bears_now = scenario.creature("Grizzly Bears", "alice")
    assert bears_now.owner == "bob"


def test_its_owner_may_not_cast_it_from_exile():
    scenario = _decree_board(["Grizzly Bears"], ["Forest", "Forest"]).build()
    _turn_to_bobs_main(scenario)
    _bob_casts_then_alice_decrees(scenario, "Grizzly Bears")
    casting = scenario.cast("Grizzly Bears", username="bob", from_zone=Zone.EXILE)
    try:
        casting.use_permission()
    except ValueError:
        pass
    else:
        raise AssertionError("bob was allowed to use alice's permission")


def test_the_permission_outlasts_the_turn():
    """No "this turn": the card stays castable for as long as it remains
    exiled, turns later."""
    scenario = _decree_board(["Grizzly Bears"], ["Forest", "Forest"]).build()
    _turn_to_bobs_main(scenario)
    _bob_casts_then_alice_decrees(scenario, "Grizzly Bears")
    for _ in range(3):
        _next_main(scenario)
    assert scenario.turn.active_player == "alice"
    casting = scenario.cast("Grizzly Bears", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.creature("Grizzly Bears", "alice")


def test_a_countered_instant_goes_to_the_graveyard_and_grants_nothing():
    """Thranduil's Decree only exiles a *permanent* spell (CR 110.4b)."""
    scenario = _decree_board(["Lightning Bolt"], ["Mountain"]).build()
    _turn_to_bobs_main(scenario)
    _bob_casts_then_alice_decrees(scenario, "Lightning Bolt", targets=["alice"])
    assert [c.name for c in scenario.player("bob").graveyard] == ["Lightning Bolt"]
    assert scenario.player("alice").life == 20


def test_a_countered_artifact_spell_is_a_permanent_spell_too():
    scenario = _decree_board(["Ornithopter"], []).build()
    _turn_to_bobs_main(scenario)
    _bob_casts_then_alice_decrees(scenario, "Ornithopter")
    assert scenario.find("Ornithopter", Zone.EXILE)


# -- Kheru Spellsnatcher: the same template on a turned-face-up trigger ------


def _face_down_kheru(scenario):
    casting = scenario.cast("Kheru Spellsnatcher", username="alice")
    casting.use_keyword("Morph")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 3))
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_kheru_exiles_even_an_instant_and_its_controller_may_cast_it_free():
    scenario = (
        Scenario()
        .player("alice", hand=["Kheru Spellsnatcher"], battlefield=["Island"] * 9)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kheru = _face_down_kheru(scenario)
    scenario.pass_priority("alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=["alice"])
    scenario.pass_priority("bob")
    scenario.choose_trigger_targets("Kheru Spellsnatcher", [bolt])
    scenario.turn_face_up(kheru, *scenario.untapped_sources(*["Island"] * 6), username="alice")
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Kheru Spellsnatcher's triggered ability",
    ]
    scenario.resolve_top()
    assert scenario.player("alice").life == 20
    exiled = scenario.find("Lightning Bolt", Zone.EXILE)
    assert exiled.owner == "bob"
    casting = scenario.cast("Lightning Bolt", username="alice", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying())
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == 17
    # Cast from exile, it resolved to its owner's graveyard; the permission died with the move.
    assert [c.name for c in scenario.player("bob").graveyard] == ["Lightning Bolt"]

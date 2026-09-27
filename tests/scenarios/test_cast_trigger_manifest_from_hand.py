"""Scenario: "When you cast this spell, up to two target players each
manifest two cards from their hands. For each card manifested this way, you
draw a card." - Kozilek, the Broken Reality.

The same CR 117.2a/603.3 cast-trigger shape `test_cast_triggers.py` proves for
Ulamog, the Ceaseless Hunger, generalising `manifest`/CR 701.40a - printed
elsewhere in this pool only off the top of a library - to a card taken from a
player's own hand instead. CR 701.40a's own wording never restricts manifest
to any one origin zone ("To manifest a card, turn it face down. ... Put that
card onto the battlefield face down."), so the keyword action itself carries
straight over.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 117.2a / 603.3** - the trigger resolves above its own spell.
- **CR 701.40a** - manifest: turn the card face down (no text, no name, no
  subtypes, no mana cost, a 2/2), then put it onto the battlefield.
- **CR 608.2c** - "for each card manifested this way" is the running count of
  what the first sentence actually did, read once the whole instruction is
  over.
- **CR 609.3** - an instruction "does as much as it can" - a hand short of
  two cards manifests every card it has rather than nothing.
- **CR 601.2d / 701.9b** - by default, a choice among a player's own cards is
  that player's, not the caster's - each target player picks *which* two
  cards of their own hand to manifest.
- **CR 608.2b** - a target player no longer legal at resolution contributes
  nothing.

The effect is `_parse_manifest_from_hand_then_draw_clause` in
`machines/effects.py`, tried by `_ability_effect_or_notice`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario

MOUNTAINS_FOR_KOZILEK = ["Wastes"] * 9


def _kozilek_board(alice_hand: list[str], bob_hand: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Kozilek, the Broken Reality", *alice_hand],
            battlefield=list(MOUNTAINS_FOR_KOZILEK),
            library=["Swamp"] * 10,
        )
        .player("bob", hand=list(bob_hand), library=["Mountain"] * 10)
    )


def test_the_cast_trigger_sits_above_its_own_spell_on_the_stack():
    scenario = _kozilek_board(["Forest", "Island"], ["Mountain", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(
        "Kozilek, the Broken Reality", [scenario.player("alice"), scenario.player("bob")]
    )
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)

    assert scenario.stack_names() == [
        "Kozilek, the Broken Reality",
        "Kozilek, the Broken Reality's triggered ability",
    ]


def test_both_target_players_manifest_two_and_the_caster_draws_four():
    scenario = _kozilek_board(["Forest", "Island"], ["Mountain", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(
        "Kozilek, the Broken Reality", [scenario.player("alice"), scenario.player("bob")]
    )
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()  # the trigger only

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 4
    assert {state.controller for state in manifested} == {"alice", "bob"}
    assert scenario.player("bob").hand == []
    # Kozilek itself has left alice's hand for the stack (-1), her own two
    # cards were manifested away (-2), and she draws once per manifested
    # card across both target players (+4).
    assert len(scenario.player("alice").hand) == hand_before - 1 - 2 + 4


def test_manifested_permanents_are_two_two_vanillas_with_no_name():
    """CR 701.40a, in full: no text, no name, no subtypes, no mana cost, and
    a 2/2 regardless of the card hidden underneath."""
    scenario = _kozilek_board(["Forest", "Island"], []).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Kozilek, the Broken Reality", [scenario.player("alice")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 2
    for permanent in manifested:
        assert permanent.name == ""
        assert permanent.card.name in {"Forest", "Island"}
        assert scenario.game.power_of(permanent) == 2
        assert scenario.game.toughness_of(permanent) == 2
        assert list(scenario.game.characteristics_of(permanent).types) == [Type.CREATURE]


def test_a_short_hand_manifests_only_what_it_has_and_still_counts():
    """CR 609.3: one card in hand manifests one card, no question asked -
    there is no choice to make when the whole hand is taken."""
    scenario = _kozilek_board(["Forest"], []).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Kozilek, the Broken Reality", [scenario.player("alice")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 1
    assert manifested[0].card.name == "Forest"
    # -1 for Kozilek moving to the stack, -1 manifested away, +1 drawn for it.
    assert len(scenario.player("alice").hand) == hand_before - 1 - 1 + 1


def test_an_empty_hand_manifests_nothing_and_draws_nothing():
    scenario = _kozilek_board([], []).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Kozilek, the Broken Reality", [scenario.player("alice")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()  # the trigger
    scenario.pass_until_resolved()  # Kozilek itself

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert manifested == []
    assert scenario.player("alice").hand == []
    assert "Kozilek, the Broken Reality" in scenario.battlefield_names()


def test_up_to_two_may_target_just_one_player():
    scenario = _kozilek_board(["Forest", "Island"], ["Mountain", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Kozilek, the Broken Reality", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()

    manifested = [state for state in scenario.game.battlefield if state.face_down]
    assert len(manifested) == 2
    assert all(state.controller == "bob" for state in manifested)
    assert scenario.player("alice").hand != []  # alice's own cards untouched


def test_a_larger_hand_lets_the_owner_choose_which_two_to_manifest():
    """CR 601.2d/701.9b: manifesting from a hand of more than two cards is
    the *target player's own* choice, not the caster's - `will_choose_cards`
    stages bob's answer the way `will_discard` stages a cleanup discard."""
    scenario = _kozilek_board([], ["Mountain", "Swamp", "Plains"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Kozilek, the Broken Reality", [scenario.player("bob")])
    sources = scenario.untapped_sources(*MOUNTAINS_FOR_KOZILEK)

    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    plains = scenario.find("Plains", Zone.HAND, "bob")
    scenario.will_choose_cards(mountain, plains, username="bob")

    scenario.cast_onto_stack("Kozilek, the Broken Reality", *sources)
    scenario.pass_until_resolved()

    manifested_names = {state.card.name for state in scenario.game.battlefield if state.face_down}
    assert manifested_names == {"Mountain", "Plains"}
    remaining = [state.name for state in scenario.player("bob").hand]
    assert remaining == ["Swamp"]

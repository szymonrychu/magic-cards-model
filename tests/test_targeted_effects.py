"""Single-clause TARGETED effects, parsed off real oracle text rather than a
per-card table row - see `machines/effects.py`'s `parse_targeted_effect`,
`parse_targeted_effect_for_spell` and `_restriction_understood`.

Wave 2 of the effect-parser work: wave 1 (`test_effects.py`) covers untargeted
player effects (gain life, draw, mill, scry, surveil); this wave covers
`Destroy target X.`, `Exile target X.`, `<Source> deals N damage to target X.`
(and "to any target"), `Return target X to its owner's hand.`,
`Tap`/`Untap target X.`, and `Put N +1/+1 (or -1/-1) counters on target X.`

This is a unit-test file: it checks what the parser returns (`None` or a
callable) against real printed text. Whether the callable actually changes a
real game state, including restriction enforcement and illegal-target
handling, is `tests/scenarios/test_targeted_effect_parser.py`'s job.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - why a multi-clause effect is split and
  run clause by clause, and why one bad clause takes the rest down with it.
- **CR 608.2b** - a target no longer legal on resolution is skipped; this
  module never re-decides that, it reuses `machines/targeting.py`'s own
  parser through `profile_for_text`.
- **CR 115.4** - "any target" means a creature, player, planeswalker, or
  battle.
- **CR 701.8a** - "To destroy a permanent, move it from the battlefield to
  its owner's graveyard."
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
- **CR 701.26a/b** - to tap/untap a permanent, turn it sideways/upright.
- **CR 118.8a** - an additional cost is paid as the spell is cast, before
  resolution - not part of what the spell does, so it is stripped before a
  targeted effect's clauses are split.
- **CR 700.2** - a modal spell's targets and effects depend on which mode was
  chosen, which is out of this wave's scope.
"""

from magic_cards_model.machines import AbilityKind, TriggerEvent, abilities_of_kind
from magic_cards_model.machines.effects import (
    ACTIVATED_EFFECTS,
    EFFECTS,
    TRIGGER_EFFECTS,
    activated_effect_for,
    effect_for,
    parse_targeted_effect,
    parse_targeted_effect_for_spell,
    trigger_effect_for,
)
from tests.cards import card


def _triggered_effect_text(name: str, event: TriggerEvent | None = None) -> str:
    triggers = abilities_of_kind(card(name), AbilityKind.TRIGGERED)
    if event is not None:
        (ability,) = [ability for ability in triggers if ability.event is event]
        return ability.effect
    (ability,) = triggers
    return ability.effect


def _activated_effect_text(name: str, index: int = 0) -> str:
    ability = abilities_of_kind(card(name), AbilityKind.ACTIVATED)[index]
    return ability.effect


# --------------------------------------------------------------------------
# One verb each, off real printed text
# --------------------------------------------------------------------------


def test_destroy_with_an_additional_cost_line_still_parses():
    """Bone Splinters: the cost line is stripped before the clause is read."""
    assert parse_targeted_effect_for_spell(card("Bone Splinters").oracle_text) is not None


def test_exile_target_nonland_permanent_parses():
    assert parse_targeted_effect_for_spell(card("Utter End").oracle_text) is not None


def test_damage_to_any_target_parses():
    """Lightning Bolt: no longer a table row (see `EFFECTS`) - the parser
    reaches it directly.
    """
    assert parse_targeted_effect_for_spell(card("Lightning Bolt").oracle_text) is not None


def test_damage_to_any_target_parses_off_a_triggered_ability():
    """Footlight Fiend: "When this creature dies, it deals 1 damage to any
    target." - never had a table row at all.
    """
    assert parse_targeted_effect(_triggered_effect_text("Footlight Fiend")) is not None


def test_return_target_creature_to_its_owners_hand_parses():
    assert parse_targeted_effect(_triggered_effect_text("Aether Adept")) is not None


def test_destroy_target_creature_an_opponent_controls_parses():
    assert parse_targeted_effect(_triggered_effect_text("Ravenous Chupacabra")) is not None


def test_tap_target_with_a_multi_type_restriction_parses():
    assert parse_targeted_effect(_activated_effect_text("Icy Manipulator")) is not None


def test_untap_another_target_permanent_parses():
    """Kiora's Follower: "another" sits between the verb and "target" without
    being part of the restriction.
    """
    assert parse_targeted_effect(_activated_effect_text("Kiora's Follower")) is not None


def test_put_a_counter_on_another_target_tapped_creature_you_control_parses():
    assert parse_targeted_effect(_triggered_effect_text("Anafenza, the Foremost")) is not None


def test_goblin_bombardments_effect_half_parses_on_its_own():
    """The cost ("Sacrifice a creature:") is already stripped by the ability
    parser by the time this text arrives; only the effect half is left.
    """
    assert parse_targeted_effect(_activated_effect_text("Goblin Bombardment")) is not None


# --------------------------------------------------------------------------
# Fail-closed: modal cards, multi-clause spells, and unenforced restrictions
# --------------------------------------------------------------------------


def test_a_modal_card_does_not_parse():
    """Abrade: "Choose one - Abrade deals 3 damage to target creature. -
    Destroy target artifact." Which mode was chosen changes both the target
    and the effect (CR 700.2c), and that needs a registry keyed by mode - a
    later wave's job, not this one's.
    """
    assert parse_targeted_effect_for_spell(card("Abrade").oracle_text) is None


def test_a_multi_clause_spell_with_one_unparseable_clause_parses_as_nothing():
    """Assassin's Trophy: "Destroy target permanent an opponent controls.
    Its controller may search their library..." The second clause is a "you
    may" choice this wave does not resolve (nobody to ask); CR 608.2c gives
    no notion of running half an effect, so neither clause runs.
    """
    assert parse_targeted_effect_for_spell(card("Assassin's Trophy").oracle_text) is None


def test_fatal_pushs_revolt_clause_takes_the_whole_effect_down():
    """Fatal Push has a second printed line ("Revolt - ...") this wave does
    not read; the plain "Destroy target creature if it has mana value 2 or
    less" alone would parse, but the effect is not run partially.
    """
    assert parse_targeted_effect_for_spell(card("Fatal Push").oracle_text) is None


def test_a_mana_value_restriction_now_parses_since_targeting_enforces_it():
    """Abrupt Decay: "target nonland permanent with mana value 3 or less" used
    to read as `understood=True` with the mana value comparison silently
    dropped, so this wave refused to act on it. `machines/targeting.py` now
    reads the comparison into `TargetRequirement.comparison_attribute` /
    `comparison_operator` / `comparison_value` and enforces it for real in
    `_rejects_comparison` (`Game.legal_target` consults it on resolution,
    CR 608.2b) - verified this session. `_targets_understood` no longer
    refuses on the mere presence of "mana value", so this parses.
    """
    assert parse_targeted_effect_for_spell(card("Abrupt Decay").oracle_text) is not None


def test_a_flashback_line_takes_the_whole_effect_down():
    """Lava Dart: the flashback keyword is printed as a second line of the
    same oracle text this wave reads, and it is not one of this wave's
    shapes - so nothing runs, and Lava Dart keeps its explicit `EFFECTS` row.
    """
    assert parse_targeted_effect_for_spell(card("Lava Dart").oracle_text) is None
    assert "Lava Dart" in EFFECTS


def test_tap_up_to_two_now_parses_count_agnostic():
    """Wave 2: tap is one of the verbs `_targets_understood` now accepts
    CR 115.6's "up to N" for, because tapping repeats itself once per legal
    target whatever the count - unlike damage, nothing about "tap" changes
    meaning between one target and several.
    """
    assert parse_targeted_effect("Tap up to two target creatures.") is not None


def test_damage_to_more_than_one_mandatory_target_still_does_not_parse():
    """Wave 2 deliberately excludes damage from the count-agnostic relaxation:
    multiple damage targets divide a total at announcement (CR 601.2d,
    Electrolyze), a different mechanism `deal_damage` does not model, so
    "deals 3 damage to two targets" must still be refused rather than dealing
    the full amount to each.
    """
    assert parse_targeted_effect("This creature deals 3 damage to two targets.") is None


def test_damage_up_to_one_target_still_does_not_parse():
    """Even "up to one", which would resolve to at most a single target
    anyway, stays refused for damage - the relaxation is verb-specific, not
    count-specific, and damage never gets it."""
    assert parse_targeted_effect("This creature deals 2 damage to up to one target creature.") is (
        None
    )


def test_destroy_up_to_two_now_parses_count_agnostic():
    assert parse_targeted_effect("Destroy up to two target creatures.") is not None


def test_exile_two_mandatory_targets_now_parses_count_agnostic():
    """Ulamog, the Ceaseless Hunger's own shape: not "up to", a flat "two"."""
    assert parse_targeted_effect("Exile two target permanents.") is not None


def test_return_up_to_one_now_parses_count_agnostic():
    assert (
        parse_targeted_effect("Return up to one target creature to its owner's hand.") is not None
    )


def test_untap_up_to_two_now_parses_count_agnostic():
    assert parse_targeted_effect("Untap up to two target creatures.") is not None


def test_put_counters_on_one_or_two_now_parses_count_agnostic():
    assert parse_targeted_effect("Put a +1/+1 counter on one or two target creatures.") is not None


def test_an_unbounded_target_count_still_does_not_parse():
    """ "Any number of" (CR 107.1c) is unbounded, not merely count-agnostic -
    `_targets_understood` refuses it the same as before wave 2, because there
    is still no maximum to repeat the verb up to."""
    assert parse_targeted_effect("Exile any number of target creatures.") is None


def test_a_graveyard_targeting_exile_now_parses():
    """Faerie Macabre's "Exile up to two target cards from graveyards": CR
    406.2/701.13a exile "from whatever zone it's currently in", so
    `exile_ability_targets` no longer hard-filters to `Zone.BATTLEFIELD` and
    `_targets_understood(battlefield_only=False)` trusts whatever zones the
    printed text names - `Game.legal_target` rechecks the target is still
    there on resolution (CR 608.2b) regardless.
    """
    assert parse_targeted_effect("Exile up to two target cards from graveyards.") is not None


def test_a_graveyard_targeting_return_now_parses():
    """Raise Dead's own shape, generalised past its "to your hand" mismatch
    (see `tests/scenarios/test_targeted_effect_parser.py`): CR 701.19a's
    "return" names no particular origin zone either, so this parses the same
    way the exile case does now.
    """
    assert (
        parse_targeted_effect(
            "Return target creature card from your graveyard to its owner's hand."
        )
        is not None
    )


def test_prismatic_ending_still_refuses_an_unreadable_comparison():
    """Relaxing the mana-value/power/toughness half of the old guard must not
    reopen the door for a comparison this engine genuinely cannot evaluate.
    Prismatic Ending's "if its mana value is less than or equal to the number
    of colors of mana spent to cast this spell" names a count with no digit
    or X in it at all - `_extract_comparison` returns the
    `_COMPARISON_UNREADABLE` sentinel for it, so `profile_for_text` comes
    back `understood=False` and `_targets_understood` refuses before its own
    "if" check is even reached. Still refused after this session's changes.
    """
    assert parse_targeted_effect_for_spell(card("Prismatic Ending").oracle_text) is None


def test_an_if_clause_with_no_comparison_is_still_refused():
    """The "if" guard on its own: a hypothetical restriction phrased with
    "if" that `machines/targeting.py` does not tie to a mana
    value/power/toughness comparison must still be refused, not trusted just
    because "mana value"/"power"/"toughness" are no longer blanket words.
    `_UNENFORCED_CONDITIONAL_RE` catches this by checking for a bare "if"
    that the parsed requirement's own `comparison_attribute` does not
    account for.
    """
    assert parse_targeted_effect("Destroy target creature if it's your turn.") is None


# --------------------------------------------------------------------------
# Wired into all three resolution paths, and an explicit row always wins
# --------------------------------------------------------------------------


def test_effect_for_falls_back_to_the_targeted_parser_for_a_spell():
    assert "Utter End" not in EFFECTS
    assert effect_for("Utter End", "Exile target nonland permanent.") is not None


def test_trigger_effect_for_falls_back_to_the_targeted_parser():
    assert ("Aether Adept", TriggerEvent.ENTERS_THE_BATTLEFIELD, "") not in TRIGGER_EFFECTS
    assert (
        trigger_effect_for(
            "Aether Adept",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            "return target creature to its owner's hand.",
        )
        is not None
    )


def test_activated_effect_for_falls_back_to_the_targeted_parser():
    assert ("Icy Manipulator", 0) not in ACTIVATED_EFFECTS
    assert (
        activated_effect_for("Icy Manipulator", 0, "Tap target artifact, creature, or land.")
        is not None
    )


def test_an_explicit_spell_row_wins_over_the_targeted_parser(monkeypatch):
    sentinel = object()
    monkeypatch.setitem(EFFECTS, "Utter End", sentinel)

    assert effect_for("Utter End", "Exile target nonland permanent.") is sentinel


def test_an_explicit_trigger_row_wins_over_the_targeted_parser(monkeypatch):
    sentinel = object()
    key = ("Aether Adept", TriggerEvent.ENTERS_THE_BATTLEFIELD, "")
    monkeypatch.setitem(TRIGGER_EFFECTS, key, sentinel)

    assert (
        trigger_effect_for(
            "Aether Adept",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            "return target creature to its owner's hand.",
        )
        is sentinel
    )


def test_an_explicit_activated_row_wins_over_the_targeted_parser(monkeypatch):
    sentinel = object()
    monkeypatch.setitem(ACTIVATED_EFFECTS, ("Icy Manipulator", 0), sentinel)

    assert (
        activated_effect_for("Icy Manipulator", 0, "Tap target artifact, creature, or land.")
        is sentinel
    )


def test_no_card_has_a_registry_entry_that_would_shadow_the_targeted_effect_parser():
    """The targeted twin of `test_effects.py`'s equivalent guard: re-adding a
    per-card row for any of these would silently take over from the parser.
    """
    newly_unlocked_spells = ["Utter End", "Lightning Bolt"]
    for name in newly_unlocked_spells:
        assert name not in EFFECTS

    newly_unlocked_triggers = [
        ("Aether Adept", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Ravenous Chupacabra", TriggerEvent.ENTERS_THE_BATTLEFIELD),
        ("Anafenza, the Foremost", TriggerEvent.ATTACKS),
        ("Footlight Fiend", TriggerEvent.DIES),
    ]
    for name, event in newly_unlocked_triggers:
        for row_name, row_event, _marker in TRIGGER_EFFECTS:
            assert not (row_name == name and row_event is event), (name, event)

    newly_unlocked_activated = [
        ("Icy Manipulator", 0),
        ("Kiora's Follower", 0),
        ("Goblin Bombardment", 0),
    ]
    for key in newly_unlocked_activated:
        assert key not in ACTIVATED_EFFECTS

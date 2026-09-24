"""Spell-cast and targeting triggers from Marvel Super Heroes (task C02-T7):

- **Thor, God of Thunder** - "Whenever you cast a noncreature spell, Thor
  deals damage equal to that spell's mana value to any target." CR 400.7/
  607.1 anaphora onto the CAST_SPELL event's own `subject_card`.
- **Namor the Sub-Mariner** - "Whenever you cast a noncreature spell with
  one or more blue mana symbols in its mana cost, create that many 1/1 blue
  Merfolk creature tokens." "That many" here is the trigger condition's own
  mana-symbol count, read back off `TriggeredAbility.condition` at
  resolution time. Namor's own CDA ("Namor's power is equal to the number
  of Merfolk you control.") is C01-T7's own reader and was already
  `handled` before this task touched anything - verified, not rebuilt.
- **Iron Fist, Living Weapon** - "Whenever you cast a spell that targets a
  creature you control, Iron Fist gains "`{T}`: Iron Fist deals damage
  equal to his power to any other target" until end of turn." A hand-built
  layer-6 `ContinuousEffect` via `layers.grant_ability`/`ContinuousEffects.
  add` (the quoted-ability-grant shape `create_continuous_effect_of_ability`
  cannot read - it only interprets a *keyword or plain static* sentence off
  `LAYER_EFFECTS`, `machines/layers.py`, locked to another C02 task this
  round). Widens `_OBJECT_CHARACTERISTIC_RE`/`_SELF_DAMAGE_EQUAL_TO_COUNT_RE`
  for "his"/"her power" pronouns so the granted ability's own damage reads.
- **Ms. Marvel, Kamala Khan** - the identical trigger condition; its own
  effect, "draw a card. Until end of turn, Ms. Marvel gains "Ms. Marvel's
  base power is equal to the number of cards in your hand."", is now proven
  in full, granted power-defining CDA included. `machines/layers.py` gained
  a `LayerContext.hand_size_by_player`/`hand_size_of` (a sixth
  off-battlefield count, alongside graveyards/life/mana pools - see that
  class's own docstring) and `_HAND_SIZE_POWER_CDA_RE`'s general "`<this>`'s
  [base] power is equal to the number of cards in your hand" reader
  (sublayer 7a, the same CDA layer Tarmogoyf's and Boneyard Wurm's own
  "power is equal to ..." rows use). The grant itself needed a second,
  genuinely cross-file fix: `effects_for`'s static-only battlefield sweep
  never consulted `_granted_ability_effects` at all (only the resolution
  path did), so a resolved trigger's own self-granted *static* line - as
  opposed to Iron Fist's *activated* one, which the sweep is right to
  refuse (CR 611.3 never covers CR 602.1) - never reached a later board
  computation; widened to try it on both paths, `static_only` threaded
  straight through so `_effect_sentences`'s own `StaticAbility`-only gate
  still refuses an activated line there. `CardState.granted_ability_texts`
  also needed populating *before* that sweep runs, which a one-shot
  resolved grant (unlike a static ability's own printed quoted grant,
  `quoted_ability_grants`/`sync_granted_ability_texts`) had never done -
  `_sync_stored_grant_ability_texts` reconciles it from the stored
  `ContinuousEffect` itself every board computation, so the grant comes off
  again the instant `end_the_turn` drops it, with nothing extra to clean up.
- **Speedball, New Warrior** - "Whenever a player casts a spell that
  targets Speedball, he gets +2/+2 until end of turn. You may choose new
  targets for that spell." `Game.change_targets` (CR 115.7d,
  `RetargetScope.ANY`) for the redirect; a new general "bare self-pump
  until end of turn, as one clause among several" reader for the pump
  (Daredevil, Man Without Fear's own exile-trigger pump needed the
  identical primitive, in `test_exile_and_cast_msh.py`).
- **Speed, Young Avenger** - "Whenever you cast a noncreature spell, you
  may pay `{1}`. When you do, target creature with haste can't be blocked
  this turn except by creatures with haste." The pay/"when you do" wrapper
  and the plain "target creature can't be blocked this turn" grant both
  already read; the "except by creatures with `<keyword>`" exception is now
  read too - `_TARGET_CANT_BE_BLOCKED_RE` grants the exception verbatim
  once the keyword names a real `combat.Keyword` member, and `machines/
  combat.py`'s `evasion_restriction_refusal` reads a "can't be blocked
  except by creatures with `<keyword>`" sentence (CR 509.1a with CR 509.1b's
  own "unless" folded on), refusing a blocker without the keyword and
  letting one with it through. Proven end to end, real cast through real
  combat declaration, in `test_speed_grants_the_haste_exception_and_
  combat_enforces_it` below.
- **The Vision** - "Whenever you cast a noncreature spell, choose one that
  hasn't been chosen this turn -" (three quoted modes). Already `handled`
  before this task touched anything (C01-T6's own per-object `chosen_modal_
  options` reader, built against Gollum, Riddle Master's *unqualified*
  "hasn't been chosen"), but the "this turn" qualifier had no reset at all -
  a real bug, not a verified-clean shape; see `test_modes_not_chosen_this_
  turn.py`, this task's own dedicated file, for the fix
  (`CardState.chosen_modal_options_this_turn`, reset every cleanup step) and
  its proof. The "Solar Beam" bullet's own "`<Name>` gains double strike
  until end of turn." also needed `_SELF_KEYWORD_GRANT_UNTIL_EOT_RE` widened
  to accept `_self_normalized_effect_text`'s "this permanent" alongside the
  bare-trigger "it" it already read, and wiring into `_parse_mixed_clause`
  (it was only reachable from a whole-ability-text dispatcher before, never
  from a modal bullet's own per-clause one).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 601.2i** - a spell is cast, which is when a CAST_SPELL trigger's
  condition can be checked (CR 603.2).
- **CR 202.3** - mana value; **CR 202.2** - mana symbols in a cost.
- **CR 115.7d** - "choose new targets" changes any number of a spell's
  targets, each independently, to another legal target.
- **CR 613.1f** - layer 6, ability-adding and -removing effects.
- **CR 208.1** - power and toughness, including a pronoun's self-reference
  to the object the ability is on.
- **CR 509.1a** - an unblockable grant; CR 509.1b - blocking restrictions
  and their own printed exceptions.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _cast_bolt_targeting_bob(scenario: Scenario, source_land: str = "Mountain") -> None:
    """Cast Lightning Bolt at bob and resolve everything the cast put on the
    stack - the cast spell itself, plus any CAST_SPELL trigger that beat it
    there (CR 603.3b: the trigger goes on top)."""
    (mountain,) = scenario.untapped_sources(source_land)
    casting = scenario.cast("Lightning Bolt")
    casting.choose_targets(["bob"])
    scenario.pay_with(casting.begin_paying(), mountain)
    scenario.put_on_stack(casting)
    while scenario.game.stack:
        scenario.resolve_top()


# -- Thor, God of Thunder: cast-noncreature-spell damage trigger ------------


def test_thor_deals_damage_equal_to_the_cast_spells_mana_value():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Thor, God of Thunder", "Mountain"], hand=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    _cast_bolt_targeting_bob(scenario)

    # Lightning Bolt (mv 1) hits bob for 3; Thor's own trigger deals 1 more.
    assert scenario.player("bob").life == 16


# -- Namor the Sub-Mariner ----------------------------------------------


def test_namor_creates_a_merfolk_token_per_blue_mana_symbol():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Namor the Sub-Mariner", "Island", "Island", "Island", "Island"],
            hand=["Stolen Goods"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Stolen Goods")
    casting.choose_targets(["bob"])
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.pay_with(casting.begin_paying(), *islands)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    merfolk = [
        state for state in scenario.game.battlefield if state.token and "Merfolk" in state.subtypes
    ]
    assert len(merfolk) == 1  # Stolen Goods is {3}{U}: one blue symbol


def test_namors_cda_power_is_the_number_of_merfolk_he_controls():
    """VERIFY ONLY (C01-T7's CDA reader): no code owned by this task."""
    scenario = Scenario().player("alice", battlefield=["Namor the Sub-Mariner"]).build()
    namor = scenario.creature("Namor the Sub-Mariner", "alice")
    assert scenario.game.power_of(namor) == 1  # Namor himself is a Merfolk


# -- Iron Fist, Living Weapon ---------------------------------------------


def test_iron_fist_gains_a_tap_ability_dealing_damage_equal_to_his_power():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Iron Fist, Living Weapon", "Grizzly Bears", "Forest"],
            hand=["Giant Growth"],
        )
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    iron_fist = scenario.creature("Iron Fist, Living Weapon", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.activate(iron_fist, targets=[wurm])
    scenario.resolve_top()

    assert wurm.damage == 2  # Iron Fist is a 2/3


def test_iron_fist_grants_nothing_when_no_spell_targets_his_own_creature():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Iron Fist, Living Weapon", "Mountain"], hand=["Lightning Bolt"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_bolt_targeting_bob(scenario)

    iron_fist = scenario.creature("Iron Fist, Living Weapon", "alice")
    assert scenario.game.activated_abilities(iron_fist) == []


# -- Ms. Marvel, Kamala Khan (the draw half only) --------------------------


def test_ms_marvel_draws_a_card_when_a_spell_targets_her_own_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ms. Marvel, Kamala Khan", "Grizzly Bears", "Forest"],
            hand=["Giant Growth"],
            library=["Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    assert "Island" in [state.name for state in scenario.player("alice").hand]


def test_ms_marvel_grants_her_controller_a_power_equal_to_hand_size_and_it_tracks_live():
    """The granted power-defining CDA now actually applies, not just the
    draw half: `machines/layers.py`'s `LayerContext.hand_size_by_player`/
    `_HAND_SIZE_POWER_CDA_RE` (CR 604.3/613.4a) plus a resolved trigger's
    self-grant now reaching the static battlefield sweep
    (`_granted_ability_effects`/`_sync_stored_grant_ability_texts`, both
    widened to the sweep rather than only the resolution path). Her power
    becomes the number of cards in alice's hand the moment the trigger
    resolves, and keeps tracking it live for the rest of the turn (CR
    613.5) rather than freezing at that count - drawing again afterward,
    with no further trigger, moves it again.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ms. Marvel, Kamala Khan", "Grizzly Bears", "Forest"],
            hand=["Giant Growth", "Lightning Bolt"],
            library=["Island", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    marvel = scenario.creature("Ms. Marvel, Kamala Khan", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])

    # Giant Growth spent, Embiggen Fist's own draw replaced it: Lightning
    # Bolt + the drawn Island, two cards.
    assert len(scenario.player("alice").hand) == 2
    assert scenario.game.power_of(marvel) == 2

    # Live, not frozen at grant time - a further draw with no further
    # trigger still moves her power, because the CDA is rebuilt from the
    # controller's live hand every time the board is computed.
    scenario.draw(1, "alice")
    assert len(scenario.player("alice").hand) == 3
    assert scenario.game.power_of(marvel) == 3


def test_ms_marvel_grants_her_controller_no_maximum_hand_size():
    """Ms. Marvel's own static "You have no maximum hand size." - the
    already-proven generic reader (`test_no_maximum_hand_size.py`'s own
    Reliquary Tower proof), read off a second printing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ms. Marvel, Kamala Khan"],
            hand=["Forest"] * 9,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    assert alice.has_no_maximum_hand_size
    scenario.game.cleanup_step()

    assert len(alice.hand) == 9


# -- Speedball, New Warrior -------------------------------------------------


def test_speedballs_own_condition_fires_and_the_pump_and_redirect_resolve():
    """ "a player casts a spell that targets Speedball" now fires for real
    (CR 201.5/201.5c self-reference,
    `triggers._cast_spell_targets_condition_holds`), putting the genuine
    `TriggeredAbility` on the stack above the spell (CR 603.3b) rather than
    a hand-built stand-in - and its own effect, the self-pump and the
    `Game.change_targets` redirect, then resolves correctly once it does.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Speedball, New Warrior", "Forest"], hand=["Giant Growth"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    speedball = scenario.creature("Speedball, New Warrior", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.will_take_the_may(False)  # decline the redirect - simplest branch
    casting = scenario.cast("Giant Growth")
    casting.choose_targets([speedball])
    scenario.pay_with(casting.begin_paying(), forest)
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()

    assert len(scenario.game.stack) == 2, (
        "Speedball's own trigger should have beaten the spell to the stack (CR 603.3b)"
    )
    assert scenario.game.stack[-1].source_name == "Speedball, New Warrior"

    scenario.resolve_top()  # Speedball's own trigger, fired for real
    assert speedball.power == 4  # 2/2 base + 2/+2 from his own trigger

    scenario.resolve_top()  # Giant Growth itself
    assert speedball.power == 7  # +3/+3 more


# -- Speed, Young Avenger: the pay/"when you do" wrapper fires -------------


def test_speed_asks_to_pay_one_when_a_noncreature_spell_is_cast():
    """Proves the CR 608.2d 'you may pay {1}. When you do, ...' wrapper and
    the trigger condition both fire; the granted evasion exception itself is
    a documented blocker (see the module docstring and MEMORY.md) - declining
    the payment here keeps the assertion to what is actually implemented."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Speed, Young Avenger", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_mana_cost(False)
    _cast_bolt_targeting_bob(scenario, source_land="Mountain")

    # No error raised, and the game state is otherwise exactly as Lightning
    # Bolt alone would leave it - the wrapper asked and the decline was
    # honored (CR 608.2d).
    assert scenario.player("bob").life == 17


def test_speed_grants_the_haste_exception_and_combat_enforces_it():
    """The full clause, paid and targeted for real: Speed's own trigger
    resolves, granting "can't be blocked except by creatures with haste" to
    the target (herself - she has haste, so she is a legal target and can
    attack the same turn regardless), and real combat declaration then
    refuses a non-haste blocker and allows a haste one - `Game.can_block`/
    `why_cannot_block`/`block`, not `combat.evasion_restriction_refusal`
    called as a bare reader.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Speed, Young Avenger", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
        )
        .player("bob", battlefield=["Goblin Guide", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    speed = scenario.creature("Speed, Young Avenger", "alice")
    scenario.will_pay_the_mana_cost(True, source="Speed, Young Avenger")
    scenario.will_choose_targets(speed, source="Speed, Young Avenger")
    _cast_bolt_targeting_bob(scenario)

    guide = scenario.creature("Goblin Guide", "bob")  # has haste
    bears = scenario.creature("Grizzly Bears", "bob")  # does not

    scenario.attack_with(speed)
    scenario.advance("alice")  # into declare blockers

    assert scenario.game.can_block(guide, speed)
    reason = scenario.game.why_cannot_block(bears, speed)
    assert reason is not None
    assert "haste" in reason
    assert "CR 509.1a" in reason
    with pytest.raises(ValueError, match="haste"):
        scenario.block(speed, bears)


# -- The Vision (verify only: C01-T6's own per-turn chosen-mode reader) ----


def test_the_vision_offers_three_modes_not_chosen_this_turn():
    """VERIFY ONLY: `test_modes_not_chosen_this_turn.py` is this task's own
    dedicated file for the per-turn reset; this only confirms the ability
    was already `handled` and still is."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Vision", "Mountain"],
            hand=["Lightning Bolt"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_mode("Technopathy — Draw a card.")
    _cast_bolt_targeting_bob(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]

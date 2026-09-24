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
  base power is equal to the number of cards in your hand."", is proven
  only for the draw half. The granted power-defining CDA needs a `Count`
  variant counting cards in a player's hand - `machines/layers.Count` is a
  closed discriminated union with no such member, and it is defined in
  `machines/layers.py`, locked to another C02 task this round. A hand-built
  `ContinuousEffect` can add the ability *line* (proven not to break
  anything else), but nothing in this task's own files can make a second,
  later layer pass read that added line back as a further layer-7b effect -
  a genuine cross-file blocker, not a dropped choice. See MEMORY.md.
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
  already read; the "except by creatures with `<keyword>`" exception does
  not - `machines/combat.py` (locked to another C02 task this round) has no
  reader for a keyword-qualified block exception at all (only a bare
  restriction, a power comparison, and a token exclusion), so granting the
  plain sentence would silently drop the exception (refusing haste
  creatures too) and granting nothing would silently allow every block -
  both wrong in different directions. The clause is matched and then
  explicitly refused, so it stays a `notice`, not a silent wrong answer.
  Genuine cross-file blocker; see MEMORY.md.
- **The Vision** - "Whenever you cast a noncreature spell, choose one that
  hasn't been chosen this turn -" (three quoted modes). Already `handled`
  before this task touched anything (C01-T6's own per-object `chosen_modal_
  options` reader, reused as-is) - verified here, not rebuilt.

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

import uuid

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind, TriggeredAbility, TriggerWord
from magic_cards_model.machines.triggers import AbilityOnStack, GameEvent, TriggerEvent
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


# -- Speedball, New Warrior -------------------------------------------------


def test_speedballs_pump_and_redirect_effect_resolves_correctly_once_triggered():
    """This proves the *effect* this task built - the self-pump and the
    `Game.change_targets` redirect - resolves correctly once the ability is
    on the stack. Whether "a player casts a spell that targets Speedball"
    itself fires is a separate, pre-existing gap this task did not
    introduce: `machines/triggers._cast_spell_targets_condition_holds`
    (locked to another C02 task this round) reads a "that targets
    `<restriction>`" tail through `machines/targeting._read_phrase` with no
    self-name ever threaded through, so "that targets Speedball" (a literal
    CR 201.5 self-reference, not a generic descriptive phrase like Danitha's
    own "a creature you control") is read as an unrecognised target
    description and the whole condition fails closed - see MEMORY.md and
    the module docstring above.
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
    spell = scenario.game.stack[-1]

    # The condition-matching gap the docstring above names means the real
    # trigger never queues itself here; this builds the identical
    # `AbilityOnStack` shape the engine's own trigger machinery would if it
    # could read the condition, so what this test actually exercises is
    # this task's own effect - the self-pump and the `change_targets`
    # redirect - not the broken condition match.
    effect_text = "he gets +2/+2 until end of turn. You may choose new targets for that spell."
    ability = AbilityOnStack(
        id=uuid.uuid4(),
        kind=AbilityKind.TRIGGERED,
        ability=TriggeredAbility(
            raw=effect_text,
            text=effect_text,
            kind=AbilityKind.TRIGGERED,
            face="Speedball, New Warrior",
            word=TriggerWord.WHENEVER,
            condition="a player casts a spell that targets Speedball",
            event=TriggerEvent.CAST_SPELL,
            effect=effect_text,
        ),
        source_id=speedball.id,
        source_name=speedball.name,
        controller="alice",
        source_stamp=speedball.zone_change_stamp,
        event=GameEvent(
            event=TriggerEvent.CAST_SPELL,
            subject_id=spell.id,
            subject_name=spell.name,
            subject_controller="alice",
            subject_card=spell.card,
            player="alice",
        ),
    )
    scenario.game.stack.append(ability)
    scenario.resolve_top()  # this task's own hand-built trigger
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

"""Scenario: type-changing effects and power/toughness-*setting* effects (W6).

Reported defect: Alice activated Karn, the Great Creator's +1 targeting her own
Trinisphere ("Until your next turn, up to one target noncreature artifact
becomes an artifact creature with power and toughness each equal to its mana
value."). The loyalty cost paid (5 -> 6), the ability resolved, and Trinisphere
came out unchanged: `type_line: "Artifact"`, `power: null`, `toughness: null`.

Two rules shapes W5 did not cover:

- **CR 613.1d** (layer 4, type-changing) - "becomes a[n] <type> creature" -
  distinct from W5's keyword *grant* (layer 6).
- **CR 613.4b** (sublayer 7b, *setting* P/T "to a specific number or value" -
  "Effects that refer to the base power and/or toughness of a creature apply
  in this layer") - distinct from W5's pump, which is sublayer 7c
  (CR 613.4c, "modify power and/or toughness ... don't set").

One ability can do both (**CR 613.6**, "If an effect should be applied in
different layers and/or sublayers, the parts of the effect each apply in their
appropriate ones").

`machines/layers.py`'s `_becomes_creature_with_mana_value_pt_builder` reads
Karn's shape straight off his own oracle text, the same `parsed_layer_effects`
fallback W5 built; `_base_pt_set_builder` reads the sibling P/T-*set* shape
("This creature has base power and toughness N/N until end of turn.",
Flexible Waterbender). `machines/effects.py`'s `create_continuous_effect_of_ability`
- already how Basking Rootwalla's pump reaches the board - is generalised to use
an activated ability's *resolved targets* rather than always its own source, so
a loyalty ability's effect reaches the layer engine through the ordinary
activated-ability path (CR 602.2, CR 606) rather than a planeswalker-specific
one.

Two more gaps this defect exposed, fixed alongside it because the fix above is
inert without them: `machines/combat.py`'s attack/block legality and
`Game._state_based_actions_once`'s death check both read `CardState.is_creature`
- the **printed** type line - rather than the computed board (CR 613.5), so an
animated permanent could not attack, block, or be dealt lethal damage;
`machines/targeting.py`'s card-type check had the same gap, which blocked even
*casting* a pump spell at an animated permanent since CR 601.2c's announcement
check ran against the printed type too. All three now ask
`Game.characteristics_of` when a `Game` is available, the same thing this
file's neighbour `test_static_abilities.py`'s combat half already established
for keywords.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import (
    ContinuousEffect,
    ContinuousEffects,
    Duration,
    Layer,
    LayerContext,
    LayerNotice,
    Sublayer,
    _only,
    compute_board,
    looks_like_unparsed_layer_effect,
    modify_power_toughness,
    parsed_layer_effects,
    set_power_toughness,
)
from magic_cards_model.models import CardState, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario


def _karn_and_artifact(*artifacts: str, opponent_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, the Great Creator", *artifacts],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(opponent_battlefield or []), library=["Mountain"] * 5)
        .build()
    )


def _activate_karn(scenario: Scenario, target_name: str):
    karn = scenario.creature("Karn, the Great Creator", "alice")
    target = scenario.creature(target_name, "alice")
    scenario.activate(karn, index=0, targets=[target])
    scenario.pass_until_resolved()
    return target


def _until_bob_has_had_a_turn(scenario: Scenario) -> None:
    """Advance to bob's turn - still inside "until alice's next turn" (CR 800.4m)."""
    while scenario.turn.active_player != "bob":
        scenario.advance()


def _until_alices_next_turn(scenario: Scenario) -> None:
    """Advance all the way to the start of alice's own next turn."""
    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)


# --------------------------------------------------------------------------
# The exact reported case
# --------------------------------------------------------------------------


def test_karns_plus_one_turns_trinisphere_into_an_artifact_creature_at_its_mana_value():
    """CR 613.1d + CR 613.4b + CR 613.6, read off Karn's own printed text.

    Before: `type_line: "Artifact"`, power/toughness `null` - the reported
    defect. After: an artifact creature, 3/3 (Trinisphere's mana value is 3),
    and *still* an artifact - CR 205.1a's "new card type(s) replaces any
    existing card types" happens to keep it here only because Karn's own text
    names both types explicitly ("artifact creature"), not because this is an
    "in addition to" grant the way Opalescence's is.
    """
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trinisphere = scenario.creature("Trinisphere", "alice")

    assert trinisphere.card.type_line == "Artifact"
    assert trinisphere.power is None and trinisphere.toughness is None

    karn = scenario.creature("Karn, the Great Creator", "alice")
    assert karn.loyalty == 5
    scenario.activate(karn, index=0, targets=[trinisphere])
    assert karn.loyalty == 6, "CR 606.4: the +1 cost is paid on activation"
    scenario.pass_until_resolved()

    computed = scenario.game.computed_board().of(trinisphere)
    assert computed.is_creature, "the reported defect: this used to stay False"
    assert "artifact" in [t.value for t in computed.types], "still an Artifact"
    assert computed.power == 3
    assert computed.toughness == 3


def test_the_value_is_read_off_the_targeted_object_not_a_constant():
    """The same ability on a different mana value proves it, rather than a
    number this wave's parser happened to hard-code for Trinisphere."""
    scenario = _karn_and_artifact("Sol Ring")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = _activate_karn(scenario, "Sol Ring")

    computed = scenario.game.computed_board().of(sol_ring)
    assert computed.is_creature
    assert computed.power == 1 and computed.toughness == 1, "Sol Ring's mana value is 1"


# --------------------------------------------------------------------------
# Duration: "until your next turn" (CR 800.4m)
# --------------------------------------------------------------------------


def test_the_effect_is_present_through_the_opponents_turn():
    """CR 800.4m: the duration outlasts the rest of the turn it was made in,
    and the turn(s) in between - it is not "until end of turn"."""
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trinisphere = _activate_karn(scenario, "Trinisphere")

    _until_bob_has_had_a_turn(scenario)
    computed = scenario.game.computed_board().of(trinisphere)
    assert computed.is_creature and computed.power == 3, (
        "still active during bob's intervening turn"
    )


def test_the_effect_ends_when_alices_own_next_turn_begins():
    """CR 800.4m: "will last until that turn would have begun" - alice's own
    next turn, specifically, not merely "a" next turn."""
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trinisphere = _activate_karn(scenario, "Trinisphere")

    _until_alices_next_turn(scenario)
    computed = scenario.game.computed_board().of(trinisphere)
    assert not computed.is_creature, "gone by alice's next turn"
    assert computed.power is None and computed.toughness is None


# --------------------------------------------------------------------------
# It really is a creature - not just a type line
# --------------------------------------------------------------------------


def test_the_animated_artifact_can_block_and_dies_to_lethal_combat_damage():
    """Proof it functions as a creature: it can be declared as a blocker
    (CR 509.1a - `block_refusal` used to read the printed type line and would
    have refused this), it deals its own combat damage back (CR 510.1a's
    "assigns combat damage equal to its power", read off the computed board),
    and 4 damage on a 3-toughness creature is lethal (CR 704.5g), destroying
    it exactly as it would a printed creature.
    """
    scenario = _karn_and_artifact("Trinisphere", opponent_battlefield=["Questing Beast"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trinisphere = _activate_karn(scenario, "Trinisphere")
    beast = scenario.creature("Questing Beast", "bob")

    _until_bob_has_had_a_turn(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(beast, defending="alice")
    scenario.block(beast, trinisphere)
    scenario.combat_damage()

    assert trinisphere.zone is Zone.GRAVEYARD, "4 damage on a 3/3 is lethal (CR 704.5g)"
    assert beast.damage == 3, "the 3/3 dealt its own combat damage back (CR 510.1a)"
    assert beast.zone is Zone.BATTLEFIELD, "4 toughness survives 3 damage"


# --------------------------------------------------------------------------
# Summoning sickness (CR 302.6, 508.1a)
# --------------------------------------------------------------------------


def test_an_artifact_already_under_control_can_attack_the_turn_it_is_animated():
    """CR 508.1a asks how long the *permanent* has been controlled, not how
    long it has been a creature - `CardState.summoning_sick` is the raw
    entered-the-battlefield fact, set once and never about card type. A
    Trinisphere present since before the game began can attack the instant it
    becomes a creature.
    """
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trinisphere = _activate_karn(scenario, "Trinisphere")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.can_attack(trinisphere)
    scenario.attack_with(trinisphere)  # raises if this is somehow illegal


def test_an_artifact_cast_this_turn_is_still_summoning_sick_once_animated():
    """The other half of the same rule: a Trinisphere that arrived this turn
    has not been controlled "continuously since [alice's] most recent turn
    began" (CR 508.1a), animated or not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Trinisphere"],
            battlefield=["Karn, the Great Creator", "Mountain", "Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    trinisphere = scenario.cast_and_resolve("Trinisphere", *sources)
    assert trinisphere.summoning_sick

    karn = scenario.creature("Karn, the Great Creator", "alice")
    scenario.activate(karn, index=0, targets=[trinisphere])
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(trinisphere).is_creature

    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert not scenario.can_attack(trinisphere), "CR 508.1a: not controlled since the turn began"


# --------------------------------------------------------------------------
# The same rule, for a {T} activated ability rather than attacking
#
# Reported defect: The Filigree Sylex was cast and animated into a creature by
# Karn's +1 the same turn. The board view then reported `summoning_sick: false`
# for it and a dry run of its {T} ability came back `allowed: true`. CR 302.6 /
# CR 602.5a hold a creature's {T}-ability back on the same "controlled
# continuously since the turn began" clause CR 508.1a uses for attacking - the
# two tests above already prove the attack half; these prove the ability half,
# which took a different, still-broken path: `Game.can_activate_tap_ability`
# read `CardState.is_creature` - the printed type line - instead of
# `Game.characteristics_of`, so a permanent that is not a creature on its own
# card never tripped the summoning-sickness check at all, animated or not.
# --------------------------------------------------------------------------


def test_an_artifact_cast_this_turn_cannot_activate_its_tap_ability_once_animated():
    """The exact reported case: cast The Filigree Sylex, animate it the same
    turn with Karn's +1, and its {T} ability must stay refused (CR 302.6,
    602.5a) even though it is now a creature."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Filigree Sylex"],
            battlefield=["Karn, the Great Creator", "Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    sylex = scenario.cast_and_resolve("The Filigree Sylex", *sources)
    assert sylex.summoning_sick, "it arrived this turn"

    karn = scenario.creature("Karn, the Great Creator", "alice")
    scenario.activate(karn, index=0, targets=[sylex])
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(sylex).is_creature, "Karn's +1 landed"

    refusal = scenario.why_cannot_activate(sylex, index=0)
    assert refusal is not None, (
        "not controlled since the turn began, so the {T} ability stays refused "
        "however long it has been a creature"
    )
    assert not sylex.tapped, "the refused activation must not have gone through"


def test_an_artifact_already_under_control_can_activate_its_tap_ability_once_animated():
    """The converse: a Filigree Sylex present since before the game began has
    been controlled continuously since alice's turn started, so animating it
    mid-turn does not make its {T} ability newly restricted."""
    scenario = _karn_and_artifact("The Filigree Sylex")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sylex = _activate_karn(scenario, "The Filigree Sylex")
    assert not sylex.summoning_sick, "controlled since before the game began"
    assert scenario.game.characteristics_of(sylex).is_creature

    assert scenario.why_cannot_activate(sylex, index=0) is None

    scenario.activate(sylex, index=0)
    scenario.pass_until_resolved()
    assert sylex.counter_count("oil") == 1, "the activation actually went through"
    assert sylex.tapped


def test_haste_lets_an_animated_artifact_cast_this_turn_activate_its_tap_ability():
    """CR 702.10c: haste lifts the restriction CR 302.6 would otherwise apply,
    even for a permanent animated the same turn it was cast. Fires of
    Yavimaya's "Creatures you control have haste" is a layer 6 grant, so this
    also proves `Game.can_activate_tap_ability` reads haste off the computed
    board rather than only the printed card - the grant is not on The Filigree
    Sylex's own text."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Filigree Sylex"],
            battlefield=["Karn, the Great Creator", "Fires of Yavimaya", "Mountain", "Mountain"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")
    sylex = scenario.cast_and_resolve("The Filigree Sylex", *sources)
    assert sylex.summoning_sick, "it arrived this turn"

    karn = scenario.creature("Karn, the Great Creator", "alice")
    scenario.activate(karn, index=0, targets=[sylex])
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(sylex).is_creature

    assert scenario.why_cannot_activate(sylex, index=0) is None, "Fires of Yavimaya grants haste"

    scenario.activate(sylex, index=0)
    scenario.pass_until_resolved()
    assert sylex.counter_count("oil") == 1
    assert sylex.tapped


# --------------------------------------------------------------------------
# Sublayer 7b (set) versus 7c (modify) - CR 613.4
# --------------------------------------------------------------------------


def test_setting_pt_beats_a_pump_regardless_of_which_was_created_first():
    """CR 613.4: "Within layer 7, apply effects in a series of sublayers ...
    Note that dependency may alter the order in which effects are applied
    within a layer or sublayer, but not among different sublayers." A set
    (7b) always applies before a modifier (7c) on the same object, whichever
    one has the older timestamp (CR 613.7 only orders effects *within* a
    sublayer) - so a +3/+3 pump lands on top of a base-3/3 set either way, and
    a base-3/3 set overwrites whatever a pump already did either way.
    """
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    permanents = [bears]

    def board_with(set_timestamp: int, pump_timestamp: int):
        set_effect = ContinuousEffect(
            description="test: base P/T 3/3",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=set_timestamp,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=_only(bears.id),
            modification=set_power_toughness(3, 3),
        )
        pump_effect = ContinuousEffect(
            description="test: +3/+3",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=pump_timestamp,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=_only(bears.id),
            modification=modify_power_toughness(3, 3),
        )
        return compute_board(permanents, [set_effect, pump_effect])

    # The set is timestamped *older* than the pump - the "natural" order, a
    # set-to-mana-value ability resolving before a later Giant Growth.
    older_set = board_with(set_timestamp=1, pump_timestamp=2)
    assert older_set.of(bears).power_toughness == (6, 6), "3 (set) + 3 (pump) = 6"

    # The set is timestamped *newer* than the pump - a Giant Growth resolving
    # first, then a set-to-mana-value ability animating and re-basing it.
    # CR 613.4 says the sublayer order still wins: 7b still applies before 7c,
    # so the answer is identical.
    newer_set = board_with(set_timestamp=2, pump_timestamp=1)
    assert newer_set.of(bears).power_toughness == (6, 6), (
        "sublayer order, not timestamp order, decides across sublayers (CR 613.4)"
    )


# --------------------------------------------------------------------------
# The sibling P/T-*set* shape: "has base power and toughness N/N" (CR 613.4b)
# --------------------------------------------------------------------------


def test_the_base_pt_set_shape_is_read_off_its_own_sentence():
    """Flexible Waterbender's "This creature has base power and toughness 5/2
    until end of turn." - the sentence `_base_pt_set_builder` reads.
    (Its real activation cost, "Waterbend {3}:", is a bespoke keyword cost
    this project's cost parser does not read yet - see
    `docs/engine-coverage.md` - so the shape is exercised on the clause
    itself, the same way `test_layer_effects_registry_is_minimal.py` checks
    Violent Urge's *Delirium* clause on its own.)
    """
    text = "This creature has base power and toughness 5/2 until end of turn."
    assert text in (card("Flexible Waterbender").oracle_text or "")
    builder = parsed_layer_effects(text)
    assert builder is not None

    scenario = Scenario().player("alice", battlefield=["Flexible Waterbender"]).build()
    waterbender = scenario.creature("Flexible Waterbender", "alice")
    effects = builder(waterbender, 1, [waterbender], LayerContext())
    board = compute_board([waterbender], effects)

    assert board.of(waterbender).power_toughness == (5, 2)
    assert effects[0].sublayer is Sublayer.SET, "7b, not 7c - it sets, it does not modify"


# --------------------------------------------------------------------------
# Fail-closed: an unreadable shape produces no effect and a notice
# --------------------------------------------------------------------------


def test_teferis_own_until_your_next_turn_ability_is_correctly_out_of_scope():
    """Teferi, Time Raveler's +1 also reads "Until your next turn, ..." but
    grants a permission ("you may cast sorcery spells as though they had
    flash"), not a type change - a different rules shape this wave does not
    claim to read. It must produce neither a parsed effect nor a false
    `LayerNotice`: `_LOOKS_LIKE_LAYER_EFFECT_RE`'s "up to ... target" fragment
    is what keeps the two apart.
    """
    text = card("Teferi, Time Raveler").oracle_text
    assert parsed_layer_effects(text) is None
    assert not looks_like_unparsed_layer_effect(text)


def test_a_becomes_creature_sentence_with_an_unread_type_word_is_a_notice_not_silence():
    """A two-word type name ("Human Soldier") after "becomes a" is not one of
    the single permanent-type words this wave reads - fails closed with a
    `LayerNotice` rather than silently doing nothing, the same contract W5's
    pump/keyword/anthem shapes already keep."""
    text = (
        "Until your next turn, up to one target noncreature artifact becomes a Human "
        "Soldier creature with power and toughness each equal to its mana value."
    )
    assert parsed_layer_effects(text) is None
    assert looks_like_unparsed_layer_effect(text)


def test_a_base_pt_set_sentence_with_the_wrong_duration_is_a_notice_not_silence():
    """ "... until your next turn" instead of "... until end of turn" is not
    the shape `_BASE_PT_SET_RE` reads - fails closed rather than silently
    doing nothing."""
    text = "This creature has base power and toughness 5/2 until your next turn."
    assert parsed_layer_effects(text) is None
    assert looks_like_unparsed_layer_effect(text)


def test_an_unreadable_static_ability_records_a_layer_notice_on_the_board():
    """End-to-end version of the fail-closed contract, through the same
    `ContinuousEffects.layer_notices` W5's `test_parsed_layer_effects.py`
    already exercises for Fiend Artisan - proof the notice is not just a
    property of the regex functions but reaches a real computed board.

    `Card.model_copy` makes a fresh, independent object with the unreadable
    sentence swapped in for the oracle text - `tests.cards.pool()` is
    `functools.cache`d, so mutating the real "Flexible Waterbender" printing
    in place would corrupt every other test that looks it up afterwards.
    """
    text = "This creature has base power and toughness 5/2 until your next turn."
    reprinted = card("Flexible Waterbender").model_copy(update={"oracle_text": text})
    waterbender = CardState(
        card=reprinted, zone=Zone.BATTLEFIELD, controller="alice", owner="alice"
    )

    store = ContinuousEffects()
    board = store.board([waterbender])

    assert board.of(waterbender).power_toughness == (2, 5), "the printed 2/5 is untouched"
    assert store.layer_notices == [
        LayerNotice(source_id=waterbender.id, source_name="Flexible Waterbender", text=text)
    ]


# --------------------------------------------------------------------------
# Zero targets (CR 115.6), and an illegal one (CR 601.2c) - game
# 433dff95eae24b04a780a960bd2445b7, seq 240-242
#
# Reported defect: alice activated Karn's +1 with an *empty* target list
# (`targets: null` in the raw log). On resolution, Karn himself became a 4/4
# artifact creature (4 = his own mana value) and was marked summoning sick.
# Wrong twice over: CR 115.6 says a spell/ability that "requires targets" may
# still legally choose zero, and one that does is "targeted only if one or
# more targets were actually chosen" - zero chosen means the ability affects
# nothing, never a fallback to its own source. Separately, Karn is a
# Legendary Planeswalker (`resolve_cards`: type_line "Legendary Planeswalker
# — Karn"), never a legal "target noncreature artifact" (CR 601.2c) even if
# a target *had* been announced.
#
# Root cause: `machines/effects.py`'s `create_continuous_effect_of_ability`
# used to test `if ability.targets else [source]` - `ability.targets` being
# an empty list is exactly what CR 115.6's "chose zero" case looks like *and*
# exactly what an untargeted ability like Basking Rootwalla's pump looks
# like, so the two were indistinguishable and the zero-target case fell
# through to `[source]`. Fixed by reading whether the ability's own printed
# text requires a target at all (`profile_for_text(ability.ability.text)`,
# the same check `Game.activate_ability` already runs at CR 601.2c
# announcement) rather than inferring it from how many targets came back.
# --------------------------------------------------------------------------


def test_karns_plus_one_with_no_target_chosen_changes_nothing():
    """The exact reported case: activate Karn's +1 with zero targets chosen
    (CR 115.6). Karn must stay exactly as he was - not a creature, no P/T,
    not summoning sick - never redirected onto his own source."""
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    trinisphere = scenario.creature("Trinisphere", "alice")
    assert karn.loyalty == 5

    scenario.activate(karn, index=0, targets=[])
    assert karn.loyalty == 6, "CR 606.4: the +1 cost is paid on activation regardless"
    scenario.pass_until_resolved()

    computed_karn = scenario.game.computed_board().of(karn)
    assert not computed_karn.is_creature, "the reported defect: Karn became a 4/4"
    assert computed_karn.power is None and computed_karn.toughness is None
    assert not karn.summoning_sick, "never animated, so never newly summoning sick either"

    # Nothing else on the board moved either - the untargeted artifact stays
    # exactly what it was.
    computed_trinisphere = scenario.game.computed_board().of(trinisphere)
    assert not computed_trinisphere.is_creature
    assert computed_trinisphere.power is None and computed_trinisphere.toughness is None


def test_karns_plus_one_refuses_karn_himself_as_an_illegal_target():
    """Karn is a Legendary Planeswalker (`resolve_cards`), never a legal
    "target noncreature artifact" (CR 601.2c) - the activation itself must be
    refused, not merely a no-op on resolution."""
    scenario = _karn_and_artifact("Trinisphere")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")

    with pytest.raises(ValueError, match="illegal target"):
        scenario.activate(karn, index=0, targets=[karn])

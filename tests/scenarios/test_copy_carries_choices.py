"""A copy of a spell carries its own choices (CR 707.10, CR 707.2).

CR 707.10: "To copy a spell ... means to put a copy of it onto the stack; a
copy of a spell isn't cast... the copy acquires the copiable values of the
original object's characteristics and, for an object on the stack, choices
made when casting or activating it (mode, targets, the value of X, whether it
was kicked, and so on). ... A copy of a spell is owned by the player under
whose control it was put on the stack. A copy of a spell or ability is
controlled by the player under whose control it was put on the stack."

CR 707.2 lists exactly what travels: "mode, targets, the value of X, whether it
was kicked, how it will affect multiple targets, and so on" - and gives its own
worked counter-example for what does not: "a copy of Dawnglow Infusion won't
cause you to gain any life" because the mana spent to cast the original is not
among the copied values.

Before this file, `Game.copy_spell` built the copy's `CardState` alone and left
`Game.cast_record` reading the copy's own (empty) default: an X spell copied
for X=0, a modal spell's copy with no modes, a kicked spell's copy unkicked.
`Game.note_cast` now writes the copy its own `CastRecord`, keyed by the copy's
own `zone_change_stamp` and marked `is_copy=True`, carrying every CR 707.2
choice across and none of CR 707.2's own exclusions (mana spent, the additional
"spend effect" tags, and CR 604.5's exile-instead-of-graveyard grant, which
belongs to how the *original* left the stack, not to the copy).

`CastRecord.is_copy` also settles every "cast from <zone>" and "was cast" read
for a copy: CR 707.10 is explicit a copy "isn't cast", so `origin_zone=Zone.
STACK` (never `Zone.HAND`, the field's own default) already answers every
positive "cast from hand"/"cast from a graveyard" check correctly (STACK is
neither), and a negation-shaped read ("wasn't cast from your hand") is written
to check `is_copy` explicitly rather than lean on that default alone.

Doublecast ("When you next cast an instant or sorcery spell this turn, copy
that spell. You may choose new targets for the copy.") is the one printing in
the pool with a real dispatcher for making a copy from a resolving *ability*,
so it drives every case below that needs a copy made that way rather than by
calling `Game.copy_spell` directly. Reverberate ("Copy target instant or
sorcery spell.") and Increasing Vengeance ("Copy target instant or sorcery
spell you control. If this spell was cast from a graveyard, copy that spell
twice instead. You may choose new targets for the copies.") are read by
`machines/effects.py`'s `_parse_copy_target_spell_clause` (a *spell's own*
"copy target ... spell" clause, CR 707.10, distinct from Doublecast's "that
spell" trigger-anaphora shape) - case (f) resolves Increasing Vengeance for
real through it. Case (g)'s Reverberate and case (h)'s modal retarget still
drive `Game.copy_spell`/`Game.offer_new_targets_for_copy` directly, the exact
two public methods the parsed dispatcher itself calls, the same precedent
`tests/test_copy_spell_stack_decode.py` already sets for calling `copy_spell`
directly on a real cast spell rather than routing every case through a
resolution incidental to what is being tested.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file (CR 707.10, 707.10a, 707.2, 700.2f, 700.2g, 702.33d).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.models.card_state import CardState
from tests.scenarios.harness import Scenario


def _doublecast_board(
    hand: list[str],
    battlefield: list[str] | None = None,
    bob_hand: list[str] | None = None,
    **extra,
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=hand,
            battlefield=battlefield or ["Mountain"] * 12,
            library=["Mountain"] * 10,
            **extra,
        )
        .player("bob", life=20, hand=bob_hand or [])
    )


def _copy_of(scenario: Scenario, name: str, original: CardState) -> CardState:
    """The copy of `name` the engine just made - the stack object still
    named `name` that is not `original` itself, since a copy prints the same
    name as the spell it copies."""
    (copy,) = [item for item in scenario.game.stack if item.name == name and item.id != original.id]
    return copy


def _resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


# --------------------------------------------------------------------------
# (a) X is copied - Doublecast then Fireball X=3 at bob
# --------------------------------------------------------------------------


def test_doublecast_then_fireball_copies_the_x_value():
    """CR 707.10's own listed example, "the value of X": an uncopied Fireball
    with X=3 would deal 3. Doublecast's copy carries the same X, so bob
    (20 life) takes 3 from the copy and 3 from the original - 6 total, not 3."""
    scenario = _doublecast_board(hand=["Doublecast", "Fireball"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    casting = scenario.cast("Fireball", targets=["bob"])
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    scenario.put_on_stack(casting)

    assert scenario.stack_names() == ["Fireball", "Doublecast's triggered ability"]

    fireball = scenario.find("Fireball", Zone.STACK)
    scenario.will_take_the_may(False, source="Doublecast")  # keep the copy's own target
    scenario.resolve_top()  # Doublecast's triggered ability makes the copy

    copy = _copy_of(scenario, "Fireball", fireball)
    assert copy.is_copy is True
    assert scenario.game.cast_record(copy).x_value == 3, (
        "the copy's own CastRecord must carry the original's announced X"
    )

    _resolve_all(scenario)
    assert scenario.player("bob").life == 14, "3 from the copy, 3 from the original"


# --------------------------------------------------------------------------
# (b) modes are copied and cannot be re-chosen - Kolaghan's Command
# --------------------------------------------------------------------------


def test_doublecast_then_kolaghans_command_copies_both_chosen_modes():
    """CR 700.2g: "If an effect allows a player to copy a modal spell or
    ability, the player may not choose new modes for the copy." The copy is
    never offered a `CHOOSE_A_MODE` decision at all - `copy_spell` writes its
    modes straight from the original's own `CastRecord` - so this proves the
    only way it could still perform "other" modes is checked directly: the
    copy's own recorded modes equal the original's."""
    scenario = _doublecast_board(
        hand=["Doublecast", "Kolaghan's Command"],
        battlefield=["Mountain"] * 10 + ["Swamp", "Swamp"],
        bob_hand=["Mountain", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    casting = scenario.cast("Kolaghan's Command")
    casting.choose_modes([2, 4])  # discard a card; deal 2 damage to any target
    casting.choose_targets(["bob", "bob"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    command = scenario.put_on_stack(casting)

    assert scenario.stack_names() == [
        "Kolaghan's Command",
        "Doublecast's triggered ability",
    ]
    scenario.will_take_the_may(False, source="Doublecast")
    scenario.resolve_top()

    copy = _copy_of(scenario, "Kolaghan's Command", command)
    record = scenario.game.cast_record(copy)
    assert record.is_copy is True
    assert record.modes == [2, 4], "the copy performs the same two modes, CR 700.2g"

    starting_hand = len(scenario.player("bob").hand)
    _resolve_all(scenario)
    assert scenario.player("bob").life == 16, "2 damage from the copy, 2 from the original"
    assert len(scenario.player("bob").hand) == starting_hand - 2, "discarded once per copy"


# --------------------------------------------------------------------------
# (c) a modal-plus-X copy keeps both - Kozilek's Command
# --------------------------------------------------------------------------


def test_doublecast_then_kozileks_command_copies_modes_and_x():
    """Kozilek's Command is both modal and X-keyed - its copy has to carry
    both at once, sliced back into `mode_targets` per CR 700.2f."""
    scenario = _doublecast_board(
        hand=["Doublecast", "Kozilek's Command"],
        battlefield=["Mountain", "Mountain", "Wastes", "Wastes", "Wastes", "Wastes"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    # Mode 1: "Target player creates X 0/1 ... Eldrazi Spawn ... tokens."
    # Mode 2: "Target player scries X, then draws a card."
    casting = scenario.cast("Kozilek's Command")
    casting.choose_modes([1, 2], x_value=2)
    casting.choose_targets(["alice", "alice"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    command = scenario.put_on_stack(casting)

    assert scenario.stack_names() == [
        "Kozilek's Command",
        "Doublecast's triggered ability",
    ]
    scenario.will_take_the_may(False, source="Doublecast")
    scenario.resolve_top()

    copy = _copy_of(scenario, "Kozilek's Command", command)
    record = scenario.game.cast_record(copy)
    assert record.modes == [1, 2]
    assert record.x_value == 2
    assert len(record.mode_targets) == 2 and all(record.mode_targets)

    def spawn_count() -> int:
        return len(
            [
                state
                for state in scenario.game.permanents_controlled_by("alice")
                if state.name == "Eldrazi Spawn Token"
            ]
        )

    scenario.resolve_top()  # the copy
    assert spawn_count() == 2, "the copy's own mode 1 made X=2 tokens"
    scenario.resolve_top()  # the original
    assert spawn_count() == 4, "the original's mode 1 made 2 more"


# --------------------------------------------------------------------------
# (d) kicked is copied - Burst Lightning
# --------------------------------------------------------------------------


def test_doublecast_then_kicked_burst_lightning_copies_kicked():
    """CR 707.2's own list: "whether it was kicked". An unkicked Burst
    Lightning deals 2; kicked, 4. The copy must deal 4 too, not 2."""
    scenario = _doublecast_board(hand=["Doublecast", "Burst Lightning"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    casting = scenario.cast("Burst Lightning")
    casting.pay_kicker()
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    burst = scenario.put_on_stack(casting)

    assert scenario.stack_names() == ["Burst Lightning", "Doublecast's triggered ability"]
    scenario.will_take_the_may(False, source="Doublecast")
    scenario.resolve_top()

    copy = _copy_of(scenario, "Burst Lightning", burst)
    assert scenario.game.cast_record(copy).kicked > 0

    scenario.resolve_top()  # the copy
    assert scenario.player("bob").life == 16, "the copy dealt the kicked 4, not the base 2"
    scenario.resolve_top()  # the original
    assert scenario.player("bob").life == 12


# --------------------------------------------------------------------------
# (e) mana spent is not copied - Dawnglow Infusion (CR 707.2's own example)
# --------------------------------------------------------------------------


def test_a_copy_of_dawnglow_infusion_carries_no_mana_spent():
    """CR 707.2's own worked example, verbatim: "Dawnglow Infusion is a
    sorcery that reads, 'You gain X life if {G} was spent to cast this spell
    and X life if {W} was spent to cast it.' Because mana isn't an object, a
    copy of Dawnglow Infusion won't cause you to gain any life, no matter
    what mana was spent to cast the original spell." Dawnglow Infusion's
    actual printed oracle text (`resolve_cards`/the fixture in
    `tests/fixtures`... - `src/magic_cards_model/data/printings/
    dawnglow_infusion.json`) says "cast this spell" both times; the engine
    now has a real parser for it
    (`machines/effects._parse_gain_life_if_color_spent_clause`), so this
    resolves both spells for real rather than only reading `CastRecord`: the
    real cast paid {G}{G} (X=1), so it gains 1 life on resolution; the copy's
    own record carries `x_value=1` but no `mana_spent` at all (CR 707.2's own
    exclusion), so it must resolve for 0."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dawnglow Infusion"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    starting_life = scenario.player("alice").life

    casting = scenario.cast("Dawnglow Infusion")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    infusion = scenario.put_on_stack(casting)

    original_record = scenario.game.cast_record(infusion)
    assert original_record.mana_of_color_spent(Color.GREEN) == 2, "the real cast paid {G}{G}"
    assert original_record.any_mana_spent, "the real cast actually paid mana"

    copy = scenario.game.copy_spell(infusion, controller="alice")
    copy_record = scenario.game.cast_record(copy)
    assert copy_record.is_copy is True
    assert copy_record.x_value == 1, "X itself IS copied (CR 707.2)"
    assert not copy_record.any_mana_spent, "CR 707.2: mana spent is never copied"
    assert copy_record.mana_spent == {}

    # The copy sits on top of the stack (CR 707.10d) - resolve it first. A
    # real cast of Dawnglow Infusion with no dispatcher for its own text
    # resolves silently (no gain, no notice); this proves the resolution
    # itself, not just the record it reads from.
    assert scenario.game.stack[-1].id == copy.id
    scenario.resolve_top()  # the copy
    assert scenario.player("alice").life == starting_life, (
        "CR 707.2's own worked example: the copy gains no life at all"
    )

    scenario.resolve_top()  # the original
    assert scenario.player("alice").life == starting_life + 1, (
        "the original paid {G}, so it gains X=1 life"
    )


# --------------------------------------------------------------------------
# (f) a copy is not cast - Increasing Vengeance cast with flashback, resolved
#     for real through the engine's own "copy target instant or sorcery
#     spell" dispatcher (`machines/effects.py`'s
#     `_parse_copy_target_spell_clause`), then a copy of Increasing Vengeance
#     itself, also resolved for real; the copy of Increasing Vengeance is not
#     "cast from a graveyard"
# --------------------------------------------------------------------------


def _increasing_vengeance_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            graveyard=["Increasing Vengeance"],
            hand=["Lightning Bolt"],
            battlefield=["Mountain"] * 8,
        )
        .player("bob", life=20)
    )


def test_increasing_vengeance_cast_from_a_graveyard_copies_the_target_twice():
    """Increasing Vengeance: "Copy target instant or sorcery spell you
    control. If this spell was cast from a graveyard, copy that spell twice
    instead. You may choose new targets for the copies." Cast for real with
    flashback (from the graveyard), its own `CastRecord.origin_zone` is
    `Zone.GRAVEYARD` - a real fact, recorded by the real `Casting`/
    `note_cast` machinery.

    This is the engine's own dispatcher actually resolving the card - not a
    reader this test defines and calls instead - so `bob` really does take 3
    from the original Bolt and 3 more from each of the two copies CR 707.10's
    own rider makes: 9 total, not 3.
    """
    scenario = _increasing_vengeance_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (bolt_source,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", bolt_source, targets=["bob"])

    casting = scenario.cast("Increasing Vengeance", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    vengeance = scenario.put_on_stack(casting)

    vengeance_record = scenario.game.cast_record(vengeance)
    assert vengeance_record.origin_zone is Zone.GRAVEYARD
    assert vengeance_record.is_copy is False

    # Keep each copy's own target (bob) rather than retargeting it - one
    # "may" question per copy CR 707.10's rider makes.
    scenario.will_take_the_may(False, source="Increasing Vengeance", times=2)
    scenario.resolve_top()  # Increasing Vengeance's own resolution

    copies = [
        item for item in scenario.game.stack if item.name == "Lightning Bolt" and item.id != bolt.id
    ]
    assert len(copies) == 2, (
        "Increasing Vengeance was cast from a graveyard, so CR 707.10's own "
        "rider copies the targeted spell twice, not once"
    )
    for copy in copies:
        record = scenario.game.cast_record(copy)
        assert record.is_copy is True
        assert record.origin_zone is not Zone.HAND
        assert record.origin_zone is Zone.STACK

    _resolve_all(scenario)
    scenario.state_based_actions()
    assert scenario.player("bob").life == 20 - 3 - 3 - 3, (
        "the original Bolt and both of its copies each deal 3"
    )


def test_a_copy_of_increasing_vengeance_was_not_cast_from_a_graveyard():
    """A copy of Increasing Vengeance (what Doublecast's or Reverberate's own
    resolution would build) is a different object with its own record: CR
    707.10 - a copy "isn't cast" - so `is_copy=True`, `origin_zone=Zone.
    STACK`, never `Zone.HAND` either, which the field's own bare default
    would otherwise silently read as if nobody had recorded anything.

    Resolved for real through the same dispatcher the sibling test above
    exercises, the copy's own "if this spell was cast from a graveyard" read
    must come back false even though the *original* really was cast from a
    graveyard: `CastRecord.is_copy`, not `origin_zone` alone, is what the
    dispatcher checks - only one copy of the Bolt reaches the stack, not two.
    """
    scenario = _increasing_vengeance_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (bolt_source,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", bolt_source, targets=["bob"])

    casting = scenario.cast("Increasing Vengeance", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    vengeance = scenario.put_on_stack(casting)

    vengeance_record = scenario.game.cast_record(vengeance)
    assert vengeance_record.origin_zone is Zone.GRAVEYARD
    assert vengeance_record.is_copy is False

    # What Doublecast's/Reverberate's own resolution would do to Increasing
    # Vengeance itself, before the original ever resolves - `Game.
    # copy_spell`, the same public method either clause calls.
    copy_of_vengeance = scenario.game.copy_spell(vengeance, controller="alice")
    copy_record = scenario.game.cast_record(copy_of_vengeance)
    assert copy_record.is_copy is True
    assert copy_record.origin_zone is not Zone.HAND
    assert copy_record.origin_zone is Zone.STACK

    # The copy is on top of the stack (just pushed) - resolve *it*, through
    # the real dispatcher, not the still-unresolved original underneath it.
    assert scenario.stack_names()[-1] == "Increasing Vengeance"
    scenario.will_take_the_may(False, source="Increasing Vengeance", times=1)
    scenario.resolve_top()

    copies = [
        item for item in scenario.game.stack if item.name == "Lightning Bolt" and item.id != bolt.id
    ]
    assert len(copies) == 1, (
        "the copy of Increasing Vengeance was never cast at all, so it was not "
        "'cast from a graveyard' - it copies once, not twice"
    )
    (copy_of_bolt,) = copies
    copy_of_bolt_record = scenario.game.cast_record(copy_of_bolt)
    assert copy_of_bolt_record.is_copy is True


# --------------------------------------------------------------------------
# (g) a copy of an opponent's spell is owned and controlled by the copier,
#     and ceases to exist on leaving the stack - Reverberate
# --------------------------------------------------------------------------


def test_reverberate_copying_the_opponents_bolt_is_owned_by_the_copier():
    """CR 707.10: "A copy of a spell is owned by the player under whose
    control it was put on the stack. A copy of a spell or ability is
    controlled by the player under whose control it was put on the stack."
    bob owns and cast the Bolt; alice's Reverberate copies it, so the copy is
    alice's, start to finish - not bob's, the way `copy_spell`'s old fallback
    (`owner=spell.owner`) would have made it.

    CR 707.10a: once the copy leaves the stack it ceases to exist (the CR
    704.5e/707.10a state-based sweep, already built and unchanged here) - it
    never sits in anyone's graveyard.
    """
    scenario = (
        Scenario()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", hand=["Reverberate"], battlefield=["Mountain", "Mountain"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (bob_mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", bob_mountain, username="bob", targets=["alice"]
    )
    scenario.pass_priority("bob")  # hand priority to alice so she may respond

    alice_mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    casting = scenario.cast("Reverberate", username="alice", targets=[bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *alice_mountains)
    reverberate = scenario.put_on_stack(casting)
    assert reverberate.controller == "alice"

    # Reverberate's own text has no dispatcher yet (see this file's module
    # docstring) - `Game.copy_spell` is the exact public method its
    # resolution would call.
    copy = scenario.game.copy_spell(bolt, controller="alice")
    assert copy.owner == "alice", "CR 707.10: owned by whoever put the copy on the stack"
    assert scenario.game.controller_of(copy).username == "alice"
    assert bolt.owner == "bob", "the original is untouched"

    scenario.resolve_top()  # the copy, on top of the stack
    assert scenario.player("alice").life == 17, "the copy still deals its 3 damage"

    scenario.state_based_actions()
    everywhere = [
        state for zone_cards in list(scenario.game.shared_zones.values()) for state in zone_cards
    ] + [
        state
        for player in scenario.game.players
        for zone_cards in player.zones.values()
        for state in zone_cards
    ]
    assert copy.id not in {state.id for state in everywhere if isinstance(state, type(bolt))}, (
        "CR 707.10a: the copy ceases to exist, it never reaches a graveyard"
    )


# --------------------------------------------------------------------------
# (h) retargeting a modal copy keeps its modes and keeps mode_targets in
#     step with targets - Reverberate on Kolaghan's Command
# --------------------------------------------------------------------------


def test_retargeting_a_modal_copy_keeps_its_modes_and_syncs_mode_targets():
    """CR 700.2f: "Modal spells and abilities may have different targeting
    requirements for each mode." CR 707.10c: "you may choose new targets for
    the copy." Together: retargeting Reverberate's copy of Kolaghan's Command
    must not touch which two modes it performs, and the changed target has to
    land back in the right mode's own slice of `mode_targets`, not just in
    the flat `targets` list."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kolaghan's Command"],
            battlefield=["Mountain", "Mountain", "Swamp"],
        )
        .player("bob", life=20, hand=["Mountain"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Kolaghan's Command")
    casting.choose_modes([2, 4])  # discard a card; deal 2 damage to any target
    casting.choose_targets(["bob", "bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", "Swamp"))
    command = scenario.put_on_stack(casting)

    # Reverberate's own resolution, simulated the same way (h)'s sibling (g)
    # does - `copy_spell` then `offer_new_targets_for_copy`, the two public
    # methods its "copy target ... spell. You may choose new targets for the
    # copy." would call.
    copy = scenario.game.copy_spell(command, controller="alice")
    before = scenario.game.cast_record(copy)
    assert before.modes == [2, 4]
    assert [ref.card_id if ref.is_card else ref.username for ref in copy.targets] == [
        scenario.player("bob").username,
        scenario.player("bob").username,
    ]

    scenario.will_take_the_may(True, source="Reverberate")
    scenario.will_choose_targets("bob", bear, source="Reverberate")
    scenario.game.offer_new_targets_for_copy(
        copy, "alice", source_name="Reverberate", source_id=str(copy.id)
    )

    after = scenario.game.cast_record(copy)
    assert after.modes == [2, 4], "retargeting never changes which modes were chosen"
    assert len(after.mode_targets) == 2
    discard_mode_targets, damage_mode_targets = after.mode_targets
    assert discard_mode_targets and discard_mode_targets[0].username == "bob", (
        "mode 2 (discard) was left alone"
    )
    assert damage_mode_targets and damage_mode_targets[0].card_id == bear.id, (
        "mode 4 (damage) was retargeted onto the bear, and mode_targets moved with it"
    )
    assert [ref.card_id if ref.is_card else ref.username for ref in copy.targets] == [
        "bob",
        bear.id,
    ], "the flat targets list agrees with the per-mode slices"


# --------------------------------------------------------------------------
# (i) Game.copy_spell_targeting keeps a modal copy's mode_targets in step
#     with the specified new target - Abrade, the same shape Frontline
#     Heroism's own dispatcher calls
# --------------------------------------------------------------------------


def test_copy_spell_targeting_keeps_a_modal_copys_mode_targets_in_step():
    """CR 707.10e ("Some effects copy a spell ... and specify a new target
    for the copy") plus CR 700.2f ("Modal spells and abilities may have
    different targeting requirements for each mode"): `Game.
    copy_spell_targeting` overwrites the copy's flat `targets`, but a modal
    spell's own resolution (`machines/effects.py`'s `resolve_modal_spell`)
    reads `CastRecord.mode_targets`, never `copy.targets` - so a modal copy
    built this way has to carry the forced retarget into its own chosen
    mode's slice, the same sync `offer_new_targets_for_copy` already does
    for CR 707.10c's optional permission.

    Abrade's first mode, "Abrade deals 3 damage to target creature.", is
    chosen alone - one mode, one target, so `mode_targets` is a one-element
    list of one-element slices, and a copy_spell_targeting that only ever
    touched `copy.targets` would leave that slice on Abrade's own original
    target (`bear`) instead of the specified new one (`mystic`).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Abrade"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears", "Elvish Mystic"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    mystic = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Abrade")
    casting.choose_modes([1])  # "Abrade deals 3 damage to target creature."
    casting.choose_targets([bear])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    abrade = scenario.put_on_stack(casting)

    # Frontline Heroism's own shape ("... then copy that spell. The copy
    # targets that token.") specifies the new target unconditionally - the
    # exact public method its dispatcher calls.
    copy = scenario.game.copy_spell_targeting(abrade, "alice", mystic)
    assert copy is not None, "the mystic is a legal target for Abrade's damage mode"
    assert [ref.card_id for ref in copy.targets] == [mystic.id]

    record = scenario.game.cast_record(copy)
    assert record.modes == [1]
    assert len(record.mode_targets) == 1
    (mode_one_targets,) = record.mode_targets
    assert [ref.card_id for ref in mode_one_targets] == [mystic.id], (
        "mode_targets must move with the forced retarget, not stay on the "
        "original's bear - resolve_modal_spell reads mode_targets, not "
        "copy.targets"
    )

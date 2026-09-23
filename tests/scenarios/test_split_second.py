"""Split second: CR 702.61a.

"Split second is a static ability that functions only while the spell with
split second is on the stack. 'Split second' means 'As long as this spell is
on the stack, players can't cast other spells or activate abilities that
aren't mana abilities.'"

Not new to Reality Fracture and not printed on any card in this set - Samut,
Tyrant of Naktamun grants it to "Instant and sorcery spells you control", a
`_permanent_quality`-scoped keyword grant that belongs with S9's own
"group grants" machinery (`Thopters you control have haste`, explicitly on
S9's own missing list in the survey) rather than being duplicated here. This
file covers the base keyword itself - CR 702.61a's stack-wide lock - proved
on Sudden Shock (Time Spiral Remastered), a real printing with split second
on its own front rather than granted.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sudden Shock"],
            battlefield=["Mountain", "Mountain"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Vampire Bats", "Swamp"],
            life=20,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_no_other_spell_may_be_cast_while_split_second_is_on_the_stack():
    scenario = _board()
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_a_non_mana_ability_may_not_be_activated_either():
    scenario = _board()
    bats = scenario.creature("Vampire Bats", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    refusal = scenario.why_cannot_activate(bats, username="bob")
    assert refusal is not None
    assert "CR 702.61a" in refusal
    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.activate(bats, username="bob")


def test_a_mana_ability_is_unaffected():
    """CR 605.1a: activating a mana ability is never "casting a spell" or
    the other kind of "activating an ability" split second stops."""
    scenario = _board()
    swamp = scenario.find("Swamp", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    assert scenario.why_cannot_activate(swamp, username="bob") is None
    scenario.activate(swamp, username="bob")
    assert swamp.tapped


def test_casting_resumes_once_split_second_leaves_the_stack():
    scenario = _board()
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_onto_stack("Sudden Shock", *mountains, username="alice", targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    scenario.pass_priority("alice")

    (bolt_source,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", bolt_source, username="bob", targets=["alice"])

    assert scenario.player("alice").life == 17


# -- Krosan Grip (Time Spiral) - a second real printing, and CR 702.61b's ---
# -- own two corners: a special action, and a triggered ability's own stack -


def _krosan_grip_board() -> Scenario:
    """Alice holds Krosan Grip and a face-down Brine Elemental (cast before
    split second is ever on the stack, at ordinary sorcery speed, for its own
    {3} morph cost, so she is the one who may turn it face up later - CR
    702.37e names the *controller*) for the printed {5}{U}{U} - ten Islands
    covers both casts, with none reused untapped between them. Bob controls
    the artifact Krosan Grip will destroy, and holds a spell of his own to
    have refused."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Krosan Grip", "Brine Elemental"],
            battlefield=["Forest", "Forest", "Forest", *(["Island"] * 10)],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            battlefield=["Welding Jar", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Brine Elemental", username="alice")
    casting.use_keyword("Morph")
    payment = casting.begin_paying()
    scenario.pay_with(
        payment, *scenario.untapped_sources("Island", "Island", "Island", username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario


def _cast_krosan_grip(scenario: Scenario, *, pass_after: bool = True):
    """Alice casts Krosan Grip at bob's Welding Jar. CR 117.3c: casting a
    spell does not by itself give up priority, so she still holds it - a
    caller that wants the special-action corner keeps `pass_after=False` and
    takes it in that same window; every other test passes as usual."""
    jar = scenario.find("Welding Jar", Zone.BATTLEFIELD, "bob")
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_onto_stack("Krosan Grip", *forests, username="alice", targets=[jar])
    if pass_after:
        scenario.pass_priority("alice")
    return jar


def _face_down_brine_elemental(scenario: Scenario):
    """`find` matches by printed name, and a face-down permanent has none
    (CR 708.2) - the one face-down creature on alice's battlefield is it."""
    (permanent,) = [
        state for state in scenario.game.permanents_controlled_by("alice") if state.face_down
    ]
    return permanent


def _turn_brine_elemental_face_up(scenario: Scenario):
    permanent = _face_down_brine_elemental(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 7), username="alice")
    return scenario.turn_face_up(permanent, *sources)


def test_krosan_grip_is_split_second_too_off_pool_proof():
    """A second real printing (CR 702.61a's own text is identical, but this is
    not Sudden Shock's own card, wording or effect - a destroy rather than
    damage), proving the reader is not fitted to Sudden Shock's sentence."""
    scenario = _krosan_grip_board()
    _cast_krosan_grip(scenario)

    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.cast("Lightning Bolt", username="bob")


def test_krosan_grip_refuses_a_non_mana_ability_too():
    """Not Vampire Bats this time (that printing is not on this board) -
    Welding Jar's own "Sacrifice this artifact: Regenerate target artifact."
    is a real, different non-mana ability refused the identical way."""
    scenario = _krosan_grip_board()
    _cast_krosan_grip(scenario)
    jar = scenario.find("Welding Jar", Zone.BATTLEFIELD, "bob")

    refusal = scenario.why_cannot_activate(jar, username="bob")
    assert refusal is not None
    assert "CR 702.61a" in refusal
    with pytest.raises(ValueError, match="CR 702.61a"):
        scenario.activate(jar, username="bob")


def test_a_special_action_is_allowed_while_krosan_grip_is_on_the_stack():
    """CR 702.61b: "Players may activate mana abilities and take special
    actions while a spell with split second is on the stack." Turning a
    face-down permanent face up (CR 116.2b, CR 702.37e) is a special action -
    it is not "casting a spell" or "activating an ability" at all, so it is
    not what split second's own words refuse in the first place, and this is
    the proof `Game.turn_face_up` was never routed through `begin_activating`
    or `Casting` to begin with."""
    scenario = _krosan_grip_board()
    _cast_krosan_grip(scenario, pass_after=False)
    permanent = _face_down_brine_elemental(scenario)
    assert permanent.face_down

    turned = _turn_brine_elemental_face_up(scenario)

    assert turned.face_up
    # Krosan Grip is still sitting on the stack underneath, unresolved and
    # untouched by the special action that just happened around it - the
    # only new stack object is what turning face up triggered (CR 603.3: it
    # goes on the next time a player would receive priority, which
    # `Game.retain_priority` inside `turn_face_up` already is).
    assert scenario.stack_names() == ["Krosan Grip", "Brine Elemental's triggered ability"]


def test_a_triggered_ability_still_goes_on_the_stack_above_split_second():
    """CR 702.61b's second sentence: "Triggered abilities trigger and are put
    on the stack as normal while a spell with split second is on the stack."
    Turning Brine Elemental face up is itself a special action CR 702.61b
    allows (the test above), and nothing about split second stops what that
    special action triggers - "When this creature is turned face up, each
    opponent skips their next untap step." Krosan Grip stays exactly where it
    was, and the new trigger goes on top of it (CR 603.3), not underneath and
    not refused."""
    scenario = _krosan_grip_board()
    _cast_krosan_grip(scenario, pass_after=False)

    # `turn_face_up` retains priority for the controller (CR 116.4: a special
    # action never costs priority), and CR 603.3 puts a triggered ability on
    # the stack "the next time a player would receive priority" - which
    # retaining priority already is, so it lands here with no separate call.
    _turn_brine_elemental_face_up(scenario)

    assert scenario.pending_triggers == []
    assert scenario.stack_names() == ["Krosan Grip", "Brine Elemental's triggered ability"]


def test_krosan_grip_resolves_and_destroys_the_target_artifact():
    scenario = _krosan_grip_board()
    jar = _cast_krosan_grip(scenario)

    scenario.resolve_top()

    assert jar.zone is Zone.GRAVEYARD

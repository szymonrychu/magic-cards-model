"""A delayed triggered ability at the beginning of the next combat this
turn, about the one creature an earlier instruction targeted, whose body is
the borrow template (gain control until end of turn, untap, haste).

- **The Wrath of Khan**, chapter I - "This Saga deals 4 damage to target
  creature an opponent controls. At the beginning of the next combat this
  turn, gain control of that creature until end of turn. Untap it. It gains
  haste until end of turn."

The body is Act of Treason's three instructions (`continuous.
_gain_control_untap_grant`), here about "that creature" instead of a target.
No other printing pairs a next-combat delayed trigger with a borrow
(Scryfall, 2026-11-12: Feral Encounter and Legion's Initiative are the
other next-combat triggers, with other bodies), so generality is shown by
varying the board: the creature dies to the damage, leaves and comes back,
starts tapped, and the chapter resolves after combat so no combat is left
this turn.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 500.6** - "at the beginning of" a step triggers as it begins; the
  combat phase opens with its beginning of combat step (CR 506.1).
- **CR 702.11b** - hexproof only stops targeting by an opponent's spells and
  abilities; the delayed ability does not target (CR 603.7c: it refers to the
  creature), so a creature that gained hexproof is still borrowed.
- **CR 715.3a / 715.2b** - the Saga enters with a lore counter, and chapter
  I triggers on it.
- **CR 603.7a** - resolving the chapter ability creates the delayed ability.
- **CR 603.7b** - it triggers only once; "this turn" bounds it to this turn.
- **CR 603.7c** - it refers to that creature; one that left the battlefield
  and came back is a new object (CR 400.7) and is not affected.
- **CR 400.7** - a control change keeps the same object, so the delayed ability
  still affects a creature whose controller changed before it resolved.
- **CR 603.7e** - its controller is the chapter ability's, so the Saga's
  controller gains control.
- **CR 613.1b** - the control change is a layer 2 effect.
- **CR 611.2a** - "until end of turn" ends it in the cleanup step.
- **CR 701.26b** - untap rotates a tapped permanent upright.
- **CR 702.10b** - haste lets the borrowed creature attack this turn.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_KHAN = "The Wrath of Khan"


def _board(
    bob_battlefield: list[str],
    *,
    alice_hand: tuple[str, ...] = (),
    alice_battlefield: tuple[str, ...] = (),
    bob_hand: tuple[str, ...] = (),
) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=[_KHAN, *alice_hand],
            battlefield=list(alice_battlefield),
            library=["Island"] * 6,
        )
        .player(
            "bob", hand=list(bob_hand), battlefield=bob_battlefield, library=["Island"] * 6, life=20
        )
    )


def _chapter_one(scenario, target) -> None:
    """The Saga enters with its first lore counter (CR 715.3a), so chapter I
    triggers (CR 715.2b) with `target` chosen; resolve it in the current
    step."""
    scenario.choose_trigger_targets(_KHAN, [target])
    scenario.put_onto_battlefield(_KHAN, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _to_beginning_of_combat(scenario) -> None:
    assert scenario.advance() is Step.BEGINNING_OF_COMBAT
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _controller(scenario, state) -> str:
    return scenario.game.controller_of(state).username


def test_the_damaged_creature_is_borrowed_untapped_with_haste_at_the_next_combat():
    scenario = _board(["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)

    assert dreadmaw.damage == 4
    assert _controller(scenario, dreadmaw) == "bob", "nothing is borrowed before combat"
    assert len(scenario.game.delayed_triggers.triggers) == 1

    _to_beginning_of_combat(scenario)

    assert _controller(scenario, dreadmaw) == "alice"
    assert not dreadmaw.tapped
    assert scenario.can_attack(dreadmaw), "haste (CR 702.10b)"
    assert scenario.game.delayed_triggers.triggers == [], "it triggers once (CR 603.7b)"


def test_a_tapped_creature_is_untapped_and_attacks_for_alice():
    scenario = _board(["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    dreadmaw.tap()
    _chapter_one(scenario, dreadmaw)
    _to_beginning_of_combat(scenario)

    assert not dreadmaw.tapped
    scenario.advance()
    scenario.attack_with(dreadmaw)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 14


def test_control_returns_to_bob_after_the_turn():
    """CR 611.2a: "until end of turn" ends in the cleanup step."""
    scenario = _board(["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)
    _to_beginning_of_combat(scenario)
    assert _controller(scenario, dreadmaw) == "alice"

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()

    assert _controller(scenario, dreadmaw) == "bob"


def test_a_creature_the_damage_killed_is_not_borrowed():
    """CR 603.7c: Grizzly Bears died to the 4 damage, so nothing is left for
    the delayed ability to affect."""
    scenario = _board(["Grizzly Bears", "Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, bears)
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD

    _to_beginning_of_combat(scenario)

    assert _controller(scenario, dreadmaw) == "bob"
    assert scenario.game.permanents_controlled_by("alice") == [
        scenario.find(_KHAN, Zone.BATTLEFIELD, "alice")
    ]


def test_a_creature_that_left_and_came_back_is_a_new_object():
    """CR 603.7c / CR 400.7: Colossal Dreadmaw returned to Bob's hand and put
    back is not the creature the ability refers to."""
    scenario = _board(["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)
    scenario.game.return_to_hand(dreadmaw)
    back = scenario.put_onto_battlefield("Colossal Dreadmaw", "bob")

    _to_beginning_of_combat(scenario)

    assert _controller(scenario, back) == "bob"


def test_only_the_targeted_creature_is_borrowed():
    scenario = _board(["Colossal Dreadmaw", "Craw Wurm"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    _chapter_one(scenario, dreadmaw)
    _to_beginning_of_combat(scenario)

    assert _controller(scenario, dreadmaw) == "alice"
    assert _controller(scenario, wurm) == "bob"


def test_with_no_combat_left_this_turn_nothing_is_borrowed_next_turn():
    """CR 603.7b: "the next combat this turn" - the chapter resolved in the
    postcombat main phase, so no combat is left this turn and the ability
    ends with it rather than waiting for a later turn's combat."""
    scenario = _board(["Colossal Dreadmaw"]).build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)
    assert len(scenario.game.delayed_triggers.triggers) == 1

    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()

    assert scenario.game.delayed_triggers.triggers == []
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert _controller(scenario, dreadmaw) == "bob"


def test_a_creature_that_gained_hexproof_is_still_borrowed():
    """CR 702.11b: hexproof stops targeting, and the delayed ability refers to
    the creature rather than targeting it (CR 603.7c). Bob makes Colossal
    Dreadmaw hexproof (Snakeskin Veil) after chapter I resolved; Alice still
    gains control of it at the beginning of combat."""
    scenario = _board(["Colossal Dreadmaw", "Forest"], bob_hand=("Snakeskin Veil",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)
    scenario.pass_priority("alice")
    (forest,) = scenario.untapped_sources("Forest", username="bob")
    scenario.cast_onto_stack("Snakeskin Veil", forest, username="bob", targets=[dreadmaw])
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(dreadmaw).has_ability("Hexproof")

    _to_beginning_of_combat(scenario)

    assert _controller(scenario, dreadmaw) == "alice"
    assert not dreadmaw.tapped
    assert scenario.can_attack(dreadmaw)


def test_a_creature_whose_controller_changed_earlier_is_still_affected():
    """CR 400.7 does not apply to a control change (the object stays), so the
    delayed ability still untaps and hastes a creature Alice already took with
    Act of Treason and then tapped; both effects end together at cleanup
    (CR 611.2a) and the creature goes home to Bob."""
    scenario = _board(
        ["Colossal Dreadmaw"], alice_hand=("Act of Treason",), alice_battlefield=("Mountain",) * 3
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    _chapter_one(scenario, dreadmaw)
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[dreadmaw],
    )
    assert _controller(scenario, dreadmaw) == "alice"
    dreadmaw.tap()

    _to_beginning_of_combat(scenario)

    assert _controller(scenario, dreadmaw) == "alice"
    assert not dreadmaw.tapped, "the delayed ability's untap still applied"
    assert scenario.game.delayed_triggers.triggers == []
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.advance()
    assert _controller(scenario, dreadmaw) == "bob"

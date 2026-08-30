"""CR 606: loyalty abilities - activating a planeswalker, paying in counters.

Every rule cited here was looked up with `knowledge_search(type="rules")` and
read in full from the checksum-verified 2026-08-19 Comprehensive Rules release
in the session that wrote the file.

- **CR 606.2** - "An activated ability with a loyalty symbol in its cost is a
  loyalty ability. Normally, only planeswalkers have loyalty abilities."
- **CR 606.3** - "A player may activate a loyalty ability of a permanent they
  control any time they have priority and the stack is empty during a main
  phase of their turn, but only if no player has previously activated a
  loyalty ability of that permanent that turn." The once-per-turn rule is per
  *permanent*: activating one of Ugin's loyalty abilities refuses the others
  until the next turn.
- **CR 606.4** - "The cost to activate a loyalty ability of a permanent is to
  put on or remove from that permanent a certain number of loyalty counters,
  as shown by the loyalty symbol in the ability's cost." The counter change is
  the cost, so it is paid on activation, before anything resolves - CR 602.2b.
- **CR 606.6** - "A loyalty ability with a negative loyalty cost, taking into
  account any additional costs, can't be activated unless the permanent has at
  least that many loyalty counters on it."
- **CR 605.1a** - the third of its mana-ability criteria is "it's not a
  loyalty ability", so a loyalty ability goes on the stack like any other
  activated ability (CR 602.2, CR 113.3b). Ugin's `0: Add {C}{C}{C}.` is the
  trap: it reads like a mana ability and is not one.
- **CR 107.7** - `[+N]` means "Put N loyalty counters on this permanent,"
  `[−N]` means "Remove N loyalty counters from this permanent," and `[0]`
  means "Put zero loyalty counters on this permanent."
- **CR 306.5b / 306.5c** - a planeswalker enters with its printed loyalty in
  counters, and its loyalty is the number of counters on it.
- **CR 704.5i** - "If a planeswalker has loyalty 0, it's put into its owner's
  graveyard."
- **CR 608.2n** - an ability is removed from the stack as it finishes
  resolving.

Entering with printed loyalty and the zero-loyalty state-based action are also
covered from the counters' side in `test_counters.py`; here they are reached
through the abilities themselves, which is what was missing.

**The effect half resolves as nothing, on purpose.** None of the planeswalkers
used here has an entry in `machines/effects.py`'s activated-ability registry,
so every ability below resolves and does nothing beyond CR 608.2n's removal.
These tests assert the rules about *activating* - legality, the cost landing,
the stack - and say so rather than pretending Ugin gained life. Adding the
effects would be the effect half's own task.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter, TargetRef
from tests.scenarios.harness import Scenario


def _ugin_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Mountain"] * 5,
            hand=["Lightning Bolt"],
            battlefield=["Ugin, Eye of the Storms", "Mountain"],
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )


def _tamiyo_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 5,
            battlefield=["Tamiyo, Compleated Sage", "Grizzly Bears"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )


def _alice_next_turn(scenario: Scenario) -> None:
    """Advance past bob's intervening turn, then back to alice's main phase."""
    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- entering and the positive cost (CR 306.5b, 606.4, 107.7) --------------


def test_a_planeswalker_enters_with_its_printed_loyalty():
    """CR 306.5b: "This permanent enters with a number of loyalty counters on
    it equal to its printed loyalty number." Ugin prints 7."""
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    assert ugin.loyalty == 7
    assert ugin.counter_count(Counter.LOYALTY) == 7
    assert scenario.why_cannot_activate(ugin) is None, "a fresh walker may activate"


def test_a_positive_loyalty_cost_puts_counters_on_when_paid():
    """Ugin's `+2: You gain 3 life and draw a card.`

    CR 606.4 makes the counter change the cost, so the two loyalty counters
    are already on the walker while the ability waits on the stack - the same
    place in time a sacrifice is already gone in `test_activated_abilities.py`.
    The effect half resolves as nothing (no registry entry): this test is
    about the cost, and it says so.
    """
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    ability = scenario.activate(ugin)

    assert isinstance(ability, AbilityOnStack)
    assert ugin.loyalty == 9, "CR 606.4: the +2 cost is paid on activation"
    assert ugin.counter_count(Counter.LOYALTY) == 9

    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty, "CR 608.2n: the ability is removed as it resolves"
    assert ugin.loyalty == 9, "the counters stay; the effect half did nothing (no registry entry)"


# -- the zero cost and the stack (CR 605.1a, 606.2, 107.7) -----------------


def test_a_zero_loyalty_cost_is_not_a_mana_ability():
    """Ugin's `0: Add {C}{C}{C}.` looks like Llanowar Elves and is not one.

    CR 605.1a's third criterion is "it's not a loyalty ability", so CR 605.3b's
    "doesn't go on the stack" is false of it: CR 606.2 makes it a loyalty
    ability, and CR 602.2 puts it on the stack. `[0]` (CR 107.7) puts zero
    loyalty counters on, so the cost itself is no event at all - but it is
    still a cost, and it is still paid.
    """
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    ability = scenario.activate(ugin, index=1)

    assert isinstance(ability, AbilityOnStack), "a loyalty ability uses the stack (CR 605.1a)"
    assert ugin.loyalty == 7, "CR 107.7: [0] puts zero loyalty counters on"
    assert not scenario.player("alice").mana_pool.floating, (
        "the mana arrives when it resolves, not on activation"
    )

    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert not scenario.player("alice").mana_pool.floating, (
        "no activated-ability registry entry, so the effect half resolves as "
        "nothing - the honest boundary of this file"
    )


# -- once per permanent per turn (CR 606.3) --------------------------------


def test_a_second_loyalty_ability_of_the_same_walker_is_refused():
    """Ugin's +2, then his `0` - a different ability, the same walker.

    CR 606.3: "but only if no player has previously activated a loyalty
    ability of that permanent that turn." The rule is per permanent, so the
    second activation is refused however the first was paid. CR 602.5's "a
    player can't begin to activate" means the refusal comes before any cost:
    the counters the first activation paid stay exactly as they were.
    """
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    scenario.activate(ugin)
    assert ugin.loyalty == 9
    scenario.pass_until_resolved()

    reason = scenario.why_cannot_activate(ugin, index=1)
    assert reason == (
        "Ugin, Eye of the Storms's loyalty abilities have already been "
        "activated this turn (CR 606.3)"
    )
    with pytest.raises(ValueError, match="CR 606.3"):
        scenario.activate(ugin, index=1)
    assert ugin.loyalty == 9, "nothing was spent on the refused activation"


def test_the_once_per_turn_rule_lifts_on_the_next_turn():
    """CR 606.3's restriction is "that turn", so a new turn allows it again."""
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    scenario.activate(ugin)
    scenario.pass_until_resolved()
    _alice_next_turn(scenario)

    assert scenario.why_cannot_activate(ugin) is None


# -- the timing half of CR 606.3 -------------------------------------------


def test_a_loyalty_ability_needs_a_main_phase():
    """CR 606.3: "any time they have priority and the stack is empty during a
    main phase of their turn". The beginning of combat is not one."""
    scenario = _ugin_board()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(ugin) == (
        "Ugin, Eye of the Storms's loyalty ability can only be activated "
        "during alice's main phase, with the stack empty (CR 606.3)"
    )


def test_a_loyalty_ability_needs_the_activators_own_turn():
    """CR 606.3: "during a main phase of their turn". Bob's turn is not."""
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    while scenario.turn.active_player != "bob":
        scenario.advance()

    reason = scenario.why_cannot_activate(ugin)
    assert reason == (
        "Ugin, Eye of the Storms's loyalty ability can only be activated "
        "during alice's main phase, with the stack empty (CR 606.3)"
    )


def test_a_loyalty_ability_needs_an_empty_stack():
    """CR 606.3: "the stack is empty". A spell waiting above the walker's
    would-be ability keeps it where it is."""
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    assert not scenario.game.stack_is_empty

    assert "CR 606.3" in scenario.why_cannot_activate(ugin)


# -- the negative cost (CR 606.6, 606.4) -----------------------------------


def test_a_negative_cost_beyond_the_loyalty_is_refused():
    """Ugin at 7 loyalty cannot pay `−11` (CR 606.6).

    The gate reads the counters that are there right now (CR 306.5c), so a
    walker at 9 - after one +2 - refuses for a different number.
    """
    scenario = _ugin_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ugin = scenario.find("Ugin, Eye of the Storms", Zone.BATTLEFIELD)

    assert scenario.why_cannot_activate(ugin, index=2) == (
        "Ugin, Eye of the Storms has 7 loyalty, not the 11 its −11 cost removes (CR 606.6)"
    )

    scenario.activate(ugin)  # +2, to 9
    scenario.pass_until_resolved()
    _alice_next_turn(scenario)

    assert scenario.why_cannot_activate(ugin, index=2) == (
        "Ugin, Eye of the Storms has 9 loyalty, not the 11 its −11 cost removes (CR 606.6)"
    )


def test_paying_a_negative_cost_to_zero_triggers_the_state_based_action():
    """Nahiri, the Harbinger: loyalty 4, `−2: Exile target enchantment, tapped
    artifact, or tapped creature.` - twice, on consecutive turns.

    CR 606.4 makes the counter change the cost, so each activation removes two
    loyalty counters; CR 306.5c makes what remains her loyalty; CR 704.5i puts
    her into her owner's graveyard when it reaches 0. The state-based action
    is checked on `Game.check_state_based_actions` directly, so the dispatch
    inside `Game` is what is under test - the scenario harness's own SBA
    helper is not involved. Two Blood Moons (not legendary, so both are legal
    permanents at once) are the enchantments her -2 points at, one per
    activation: `machines/effects.py`'s targeted-effect parser now reads this
    ability's own printed text and actually exiles its target (see
    `tests/scenarios/test_targeted_effect_parser.py`), so the first Blood
    Moon is gone by the second activation and cannot be re-targeted.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"] * 5,
            battlefield=["Nahiri, the Harbinger", "Blood Moon", "Blood Moon"],
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nahiri = scenario.find("Nahiri, the Harbinger", Zone.BATTLEFIELD)
    moons = [state for state in scenario.game.battlefield if state.name == "Blood Moon"]
    assert len(moons) == 2
    first_moon, second_moon = moons

    scenario.activate(nahiri, index=1, targets=[first_moon])
    assert nahiri.loyalty == 2, "CR 606.4: the −2 cost removed two loyalty counters"
    scenario.pass_until_resolved()
    assert first_moon.zone is Zone.EXILE, "the exile half of the ability now actually runs"

    _alice_next_turn(scenario)

    scenario.activate(nahiri, index=1, targets=[second_moon])
    assert nahiri.loyalty == 0

    leaving = scenario.game.check_state_based_actions()
    assert nahiri in leaving
    assert nahiri.zone is Zone.GRAVEYARD, "CR 704.5i: a planeswalker at 0 loyalty"
    assert nahiri in scenario.player("alice").cards_in(Zone.GRAVEYARD)


# -- targets on a loyalty ability (CR 602.2b) ------------------------------


def test_a_targeted_loyalty_ability_announces_its_target():
    """Tamiyo, Compleated Sage's `+1: Tap up to one target artifact or
    creature. It doesn't untap during its controller's next untap step.`

    CR 602.2: "the remainder of the process for activating an ability is
    identical to the process for casting a spell", so the target is announced
    and checked like any activated ability's. The tap her text describes is
    the effect, and the effect half resolves as nothing here - no registry
    entry - so the bears stay untapped: this test is about the announcement
    and the cost.
    """
    scenario = _tamiyo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")

    ability = scenario.activate(tamiyo, targets=[bears])

    assert isinstance(ability, AbilityOnStack)
    assert ability.targets == [TargetRef.to_card(bears)]
    assert tamiyo.loyalty == 6, "CR 606.4: the +1 cost put a loyalty counter on"

    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert not bears.tapped, "the effect half resolved as nothing (no registry entry)"


def test_a_variable_loyalty_cost_is_refused_until_something_can_choose_x():
    """Tamiyo's `−X: Exile target nonland permanent card with mana value X
    from your graveyard. Create a token that's a copy of that card.`

    CR 107.7: "a minus sign followed by a number or an X" - the X is a
    player's choice, and there is no decision point to choose it in. The
    engine refuses rather than guessing an amount: `activation_cost` raises
    "cannot build a cost for '−X'", and the walker is untouched. The xfail
    below records the missing capability.
    """
    scenario = _tamiyo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD)

    with pytest.raises(ValueError, match="cannot build a cost for '−X'"):
        scenario.activate(tamiyo, index=1)

    assert tamiyo.loyalty == 5, "the refusal left the walker alone"


@pytest.mark.xfail(
    strict=True,
    reason="Tamiyo's −X cost parses (CostKind.LOYALTY, amount None, per CR "
    "107.7's 'a minus sign followed by a number or an X'), but no player can "
    "choose the X: machines/cost.py has no component for a variable loyalty "
    "cost, so game.py's activation_cost raises 'cannot build a cost for −X'. "
    "Choosing X needs a decision point this engine does not have yet.",
)
def test_activating_tamiyos_minus_x_pays_the_chosen_amount():
    """The whole path once X can be chosen: activate with X = 2, and two of
    Tamiyo's five loyalty counters come off as the cost (CR 606.4, 606.6)."""
    scenario = _tamiyo_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD)

    scenario.activate(tamiyo, index=1)  # with a chosen X of 2
    assert tamiyo.loyalty == 3

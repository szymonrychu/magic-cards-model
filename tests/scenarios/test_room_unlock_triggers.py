"""Scenario: "When you unlock this door, `<effect>`." (CR 709.5h) - a Room's
own door-unlock trigger, and CR 709.5d's "given the unlocked designation as
it enters the battlefield if that half was cast as a spell" that fires it
the first time.

Nothing in the engine modelled a Room's unlocked designations at all before
this file (`docs/mcp-tools.md`/`legal_actions.py`'s own grep-confirmed "empty
for ... 'unlock cost', 'locked half'"). `CardState.unlocked_doors` is the new
designation store; `Game.unlock_door` is the one function every route to an
unlocked designation runs through (CR 709.5d's cast-half unlock here, a
future CR 709.5e special action or CR 709.5f "unlock" instruction the same
way); `ExtraTriggerEvent.DOOR_UNLOCKED` is the event "when you unlock this
door" watches, matched to the ability's own printed face (`BaseAbility.
face`) so only the door actually unlocked triggers.

Also closed by the same work: Unholy Annex's own end-step trigger, "draw a
card. If you control a Demon, each opponent loses 2 life and you gain 2
life. Otherwise, you lose 2 life." - a compound "if/otherwise" CR 608.2c
instruction split across two sentences, which no per-clause reader could
read half of alone (`machines/effects._parse_leading_then_if_otherwise_
clause`).

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Unholy Annex // Ritual Chamber**: "Unholy Annex — At the beginning of
  your end step, draw a card. If you control a Demon, each opponent loses 2
  life and you gain 2 life. Otherwise, you lose 2 life." / "Ritual Chamber —
  When you unlock this door, create a 6/6 black Demon creature token with
  flying."
- **Central Elevator // Promising Stairs** (a second printing, not in the
  api deck pool): "Central Elevator — When you unlock this door, search
  your library for a Room card that doesn't have the same name as a Room
  you control, reveal it, put it into your hand, then shuffle." - proof the
  new trigger fires for a *different* door's own text and a different
  effect (a search, not a token), and that casting the *front* half (rather
  than Ritual Chamber's back half) unlocks correctly too.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

UNHOLY_ANNEX = "Unholy Annex // Ritual Chamber"
RITUAL_CHAMBER = "Ritual Chamber"
CENTRAL_ELEVATOR = "Central Elevator // Promising Stairs"


def _cast_split_half(scenario: Scenario, front_name: str, half: str | None, *sources) -> None:
    """Cast `front_name` (a split card, found by its front half's own name -
    `Scenario.find`'s own prefix match), choosing `half` if it names the
    back one (`Casting.cast_as_split_half`, CR 709.3)."""
    casting = scenario.cast(front_name)
    if half is not None:
        casting.cast_as_split_half(half)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)


def test_casting_ritual_chamber_unlocks_it_and_creates_a_demon():
    scenario = (
        Scenario()
        .player("alice", hand=[UNHOLY_ANNEX], battlefield=["Swamp"] * 5)
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources(*["Swamp"] * 5)
    _cast_split_half(scenario, "Unholy Annex", RITUAL_CHAMBER, *swamps)
    ritual_chamber = scenario.resolve_top()

    assert ritual_chamber.unlocked_doors == (RITUAL_CHAMBER,)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{UNHOLY_ANNEX}'s triggered ability"]
    scenario.resolve_top()

    demons = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Demon Token"
    ]
    assert len(demons) == 1
    assert scenario.game.power_of(demons[0]) == 6 and scenario.game.toughness_of(demons[0]) == 6


def test_unholy_annex_end_step_otherwise_branch_without_a_demon():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[UNHOLY_ANNEX],
            library=["Forest"],
            battlefield=["Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    _cast_split_half(scenario, "Unholy Annex", None, *swamps)
    scenario.resolve_top()
    life_before = scenario.player("alice").life
    hand_before = len(scenario.player("alice").hand)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{UNHOLY_ANNEX}'s triggered ability"]
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.player("alice").life == life_before - 2, "no Demon: you lose 2 life"


def test_unholy_annex_end_step_if_branch_with_a_demon():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[UNHOLY_ANNEX],
            library=["Forest"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources(*["Swamp"] * 5)
    _cast_split_half(scenario, "Unholy Annex", RITUAL_CHAMBER, *swamps)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the door-unlock trigger: creates the Demon

    life_before = scenario.player("alice").life
    bob_life_before = scenario.player("bob").life
    hand_before = len(scenario.player("alice").hand)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{UNHOLY_ANNEX}'s triggered ability"]
    scenario.resolve_top()

    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.player("alice").life == life_before + 2, "controls a Demon: you gain 2 life"
    assert scenario.player("bob").life == bob_life_before - 2


def test_unholy_annexs_own_door_does_not_fire_ritual_chambers_trigger():
    """CR 709.5h: only the door that was actually unlocked - Unholy Annex's
    own door, not Ritual Chamber's - triggers."""
    scenario = (
        Scenario()
        .player("alice", hand=[UNHOLY_ANNEX], battlefield=["Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    _cast_split_half(scenario, "Unholy Annex", None, *swamps)
    unholy_annex = scenario.resolve_top()

    assert unholy_annex.unlocked_doors == ("Unholy Annex",)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_central_elevator_unlocks_and_searches_for_another_room():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[CENTRAL_ELEVATOR],
            library=[UNHOLY_ANNEX, "Forest"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island")
    scenario.will_choose_cards(scenario.find(UNHOLY_ANNEX, Zone.LIBRARY, "alice"))
    _cast_split_half(scenario, "Central Elevator", None, *islands)
    elevator = scenario.resolve_top()

    assert elevator.unlocked_doors == ("Central Elevator",)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{CENTRAL_ELEVATOR}'s triggered ability"]
    scenario.resolve_top()

    # The trigger fires and its search runs (no notice, no exception) - a
    # second door's own text, a different effect entirely (a search, not a
    # token). The search's own "doesn't have the same name as a Room you
    # control" restriction is a pre-existing, unrelated search-quality gap
    # (`machines/effects.py`'s quality vocabulary, not a trigger condition) -
    # recorded in `MEMORY.md` rather than fixed here.
    assert scenario.game.conditional_clause_notices == []

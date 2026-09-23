"""Scenario: exile with time counters, and "If it doesn't have suspend, it
gains suspend." - Delay's counter-into-suspend and Suspend's exile-into-
suspend.

Delay: "Counter target spell. If the spell is countered this way, exile it
with three time counters on it instead of putting it into its owner's
graveyard. If it doesn't have suspend, it gains suspend." Suspend (the card):
"Exile target creature and put two time counters on it. If it doesn't have
suspend, it gains suspend." Both leave a card in exile that CR 702.62b calls
suspended, and from there the keyword's own two exile-zone triggers (CR
702.62a) take over exactly as they do for a card suspended from hand: one
time counter off per owner's upkeep, then a free cast, with haste for a
creature.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file.

- **CR 702.62a** - suspend's second and third abilities "function in the
  exile zone": "At the beginning of your upkeep, if this card is suspended,
  remove a time counter from it" and "When the last time counter is removed
  from this card, if it's exiled, you may play it without paying its mana
  cost if able. ... If you cast a creature spell this way, it gains haste
  ..."
- **CR 702.62b** - "A card is 'suspended' if it's in the exile zone, has
  suspend, and has a time counter on it."
- **CR 611.2a** - a resolution effect with no stated duration lasts until the
  end of the game; **CR 400.7** - but the object that leaves exile is a new
  object, so the granted suspend does not follow the card out.
- **CR 701.6a / CR 113.6g** - a spell that can't be countered is not
  countered, so "if the spell is countered this way" is false: nothing is
  exiled and no counters are placed.
- **CR 608.2b** - a target gone from the stack: nothing happens.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState, Counter
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Island"] * 12


def delay_board(alice_hand: list[str], *, bob_hand: list[str] | None = None) -> PlayedScenario:
    """Alice casts; Bob holds Delay and two Islands. Alice's main phase."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=["Forest", "Forest", "Island", "Mountain", "Mountain", "Mountain"]
            + ["Plains", "Swamp", "Swamp"],
            library=LIBRARY,
        )
        .player(
            "bob",
            hand=bob_hand if bob_hand is not None else ["Delay"],
            battlefield=["Island", "Island", "Island", "Island", "Mind Stone"],
            library=LIBRARY,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def advance_to_upkeep_of(scenario: PlayedScenario, owner: str) -> None:
    """Walk the real turn machine to `owner`'s next upkeep, resolving whatever
    is on the stack on the way, and stop with the upkeep's own triggers
    unresolved."""
    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == owner):
        resolve_everything(scenario)
        scenario.advance()


def resolve_everything(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def delay_alices(scenario: PlayedScenario, name: str, **kwargs) -> CardState:
    spell = scenario.cast_onto_stack(name, username="alice", auto=True, **kwargs)
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Delay", username="bob", auto=True, targets=[spell])
    return spell


# -- Delay -----------------------------------------------------------------


def test_delay_exiles_the_spell_with_three_time_counters_and_suspend():
    scenario = delay_board(["Grizzly Bears"])
    bears = delay_alices(scenario, "Grizzly Bears")

    assert bears.zone is Zone.EXILE
    assert bears.counter_count(Counter.TIME) == 3
    assert bears.is_suspended, "CR 702.62b: in exile, has suspend, has a time counter"
    assert scenario.stack_names() == []


def test_a_delayed_creature_comes_back_free_with_haste_after_three_owner_upkeeps():
    scenario = delay_board(["Grizzly Bears"])
    bears = delay_alices(scenario, "Grizzly Bears")

    for remaining in (2, 1):
        advance_to_upkeep_of(scenario, "alice")
        resolve_everything(scenario)
        assert bears.counter_count(Counter.TIME) == remaining
        assert bears.zone is Zone.EXILE

    advance_to_upkeep_of(scenario, "alice")
    lands_before = [land.tapped for land in scenario.game.permanents_controlled_by("alice")]
    resolve_everything(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert [land.tapped for land in scenario.game.permanents_controlled_by("alice")][
        : len(lands_before)
    ] == lands_before, "cast without paying its mana cost"
    assert scenario.can_attack(bears), "CR 702.62a: a creature cast this way gains haste"


def test_the_time_counters_come_off_on_the_owners_upkeep_not_the_delayers():
    """Bob cast Delay, but the exiled card is Alice's: CR 702.62a's "your
    upkeep" is its owner's (a card in exile has no controller), so Bob's own
    upkeep takes nothing off."""
    scenario = delay_board(["Grizzly Bears"])
    bears = delay_alices(scenario, "Grizzly Bears")

    advance_to_upkeep_of(scenario, "bob")
    resolve_everything(scenario)
    assert bears.counter_count(Counter.TIME) == 3

    advance_to_upkeep_of(scenario, "alice")
    resolve_everything(scenario)
    assert bears.counter_count(Counter.TIME) == 2


def test_a_delayed_instant_is_cast_free_when_the_last_counter_comes_off():
    scenario = delay_board(["Opt"])
    opt = delay_alices(scenario, "Opt")
    assert opt.is_suspended

    for _ in range(3):
        advance_to_upkeep_of(scenario, "alice")
        resolve_everything(scenario)

    assert opt.zone is Zone.GRAVEYARD, "cast free and resolved"
    assert opt.counter_count(Counter.TIME) == 0


def test_declining_the_free_cast_leaves_it_exiled_and_no_longer_suspended():
    scenario = delay_board(["Grizzly Bears"])
    bears = delay_alices(scenario, "Grizzly Bears")
    scenario.will_take_the_may(False, source="Grizzly Bears")

    for _ in range(3):
        advance_to_upkeep_of(scenario, "alice")
        resolve_everything(scenario)

    assert bears.zone is Zone.EXILE
    assert bears.counter_count(Counter.TIME) == 0
    assert not bears.is_suspended


def test_a_spell_that_already_has_suspend_keeps_just_the_one():
    """Rift Bolt prints "Suspend 1-{R}". "If it doesn't have suspend" is
    false, so nothing is granted - it is still suspended off its own keyword,
    with Delay's three counters rather than its own one."""
    scenario = delay_board(["Rift Bolt"])
    bolt = delay_alices(scenario, "Rift Bolt", targets=["bob"])

    assert bolt.zone is Zone.EXILE
    assert bolt.counter_count(Counter.TIME) == 3
    assert bolt.is_suspended
    assert not any(line.lower() == "suspend" for line in bolt.granted_ability_texts)


def test_an_uncounterable_spell_is_neither_countered_nor_exiled():
    """Inevitable Defeat can't be countered (CR 113.6g), so "if the spell is
    countered this way" never holds: it stays on the stack with no time
    counters, then resolves."""
    scenario = delay_board(["Inevitable Defeat"])
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    defeat = delay_alices(scenario, "Inevitable Defeat", targets=[stone])

    assert defeat.zone is Zone.STACK
    assert defeat.counter_count(Counter.TIME) == 0
    assert not defeat.is_suspended
    scenario.resolve_top()
    assert stone.zone is Zone.EXILE
    assert defeat.zone is Zone.GRAVEYARD


def test_a_target_gone_from_the_stack_is_not_exiled():
    """CR 608.2b: the second Delay resolves first; the first has no legal
    target and does nothing to the already-exiled card."""
    scenario = delay_board(["Grizzly Bears"], bob_hand=["Delay", "Delay"])
    bears = scenario.cast_onto_stack("Grizzly Bears", username="alice", auto=True)
    scenario.pass_priority("alice")
    first = scenario.cast_onto_stack("Delay", username="bob", auto=True, targets=[bears])
    scenario.cast_and_resolve("Delay", username="bob", auto=True, targets=[bears])
    scenario.resolve_top()

    assert first.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.EXILE
    assert bears.counter_count(Counter.TIME) == 3


def test_the_granted_suspend_does_not_follow_the_card_out_of_exile():
    """CR 400.7: the permanent the free cast makes is a new object, and the
    suspend Delay granted was the exiled card's."""
    scenario = delay_board(["Grizzly Bears"])
    bears = delay_alices(scenario, "Grizzly Bears")
    for _ in range(3):
        advance_to_upkeep_of(scenario, "alice")
        resolve_everything(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert not any(line.lower() == "suspend" for line in bears.granted_ability_texts)


# -- Suspend (the card): exile from the battlefield, two counters ------------


def suspend_board() -> PlayedScenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Suspend"], battlefield=["Island"], library=LIBRARY)
        .player("bob", battlefield=["Grizzly Bears", "Forest", "Forest"], library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_suspend_exiles_a_creature_with_two_time_counters_and_suspend():
    scenario = suspend_board()
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Suspend", username="alice", auto=True, targets=[bears])

    assert bears.zone is Zone.EXILE
    assert bears.counter_count(Counter.TIME) == 2
    assert bears.is_suspended


def test_a_suspended_creature_returns_to_its_owner_with_haste():
    scenario = suspend_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Suspend", username="alice", auto=True, targets=[bears])

    advance_to_upkeep_of(scenario, "bob")
    resolve_everything(scenario)
    assert bears.counter_count(Counter.TIME) == 1
    advance_to_upkeep_of(scenario, "alice")
    resolve_everything(scenario)
    assert bears.counter_count(Counter.TIME) == 1, "alice's upkeep is not the owner's"
    advance_to_upkeep_of(scenario, "bob")
    resolve_everything(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "bob"
    assert scenario.can_attack(bears)

"""A triggered ability that sacrifices its own source (CR 701.21a).

CR 701.21a: "To sacrifice a permanent, its controller moves it from the
battlefield directly to its owner's graveyard. A player can't sacrifice
something that isn't a permanent, or something that's a permanent they don't
control."

The self-reference is printed three ways, and all three are one mechanic:
"sacrifice it" (The Millennium Calendar's state trigger), "sacrifice this
<card type or 'permanent'>" (Dress Down's "this enchantment", Ball
Lightning's "this creature"), and a card's own name, which
`trigger_effect_for` normalises to "this permanent" before reading it again.
Dress Down resolved "CHANGED NOTHING" in a live game because only "sacrifice
it" was read.

Corner cases:

- CR 603.2b: "When a phase or step begins, all abilities that trigger 'at the
  beginning of' that phase or step trigger." A permanent that arrives after
  the end step began missed that moment and waits for the next end step.
- CR 113.7a: "Once activated or triggered, an ability exists on the stack
  independently of its source." A source gone in response leaves the ability
  to resolve with nothing to sacrifice - CR 701.21a cannot sacrifice what is
  not a permanent - and CR 400.7 makes a source that left and came back "a
  new object with no memory of, or relation to, its previous existence", so
  the old trigger does not sacrifice the new object either.

Every CR number here was read with `mise run rules:find` in the session that
wrote this file: 701.21a, 603.2b, 113.7a, 400.7. Dress Down (in the deck
pool) and Ball Lightning (off-pool, a different noun) are real Scryfall
printings.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def board(**alice) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"] * 5, **alice)
        .player("bob", library=["Island"] * 5)
    )


def resolve_stack(scenario: PlayedScenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def advance_to(scenario: PlayedScenario, step: Step, active: str = "alice") -> None:
    """Advance, resolving everything on the way, until `step` of `active`'s turn."""
    while not (scenario.step is step and scenario.turn.active_player == active):
        scenario.advance()
        resolve_stack(scenario)


def advance_into_end_step(scenario: PlayedScenario) -> None:
    """Advance to alice's end step and stop with its triggers still on the stack."""
    while scenario.step is not Step.END_STEP:
        resolve_stack(scenario)
        scenario.advance()


def test_dress_down_cast_in_the_main_phase_is_sacrificed_at_that_end_step():
    scenario = board(hand=["Dress Down"], battlefield=["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    dress_down = scenario.cast_and_resolve(
        "Dress Down", *scenario.untapped_sources("Island", "Island")
    )
    resolve_stack(scenario)
    assert dress_down.zone is Zone.BATTLEFIELD

    advance_into_end_step(scenario)
    assert scenario.stack_names() == ["Dress Down's triggered ability"]
    resolve_stack(scenario)

    assert dress_down.zone is Zone.GRAVEYARD


def test_dress_down_flashed_in_during_the_end_step_waits_for_the_next_one():
    """CR 603.2b: the end step had already begun, so its "at the beginning
    of" moment has passed for a permanent that arrives during it."""
    scenario = board(hand=["Dress Down"], battlefield=["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    advance_into_end_step(scenario)
    assert scenario.game.stack_is_empty

    dress_down = scenario.cast_and_resolve(
        "Dress Down", *scenario.untapped_sources("Island", "Island")
    )
    resolve_stack(scenario)
    assert dress_down.zone is Zone.BATTLEFIELD

    advance_to(scenario, Step.CLEANUP)
    assert dress_down.zone is Zone.BATTLEFIELD

    advance_to(scenario, Step.END_STEP, active="bob")
    assert dress_down.zone is Zone.GRAVEYARD


def test_a_source_exiled_in_response_leaves_nothing_else_sacrificed():
    """CR 113.7a: the trigger still resolves. CR 701.21a: an exiled card is
    not a permanent, so there is nothing to sacrifice - and nothing else is."""
    scenario = board(
        hand=["Utter End"],
        battlefield=["Dress Down", "Plains", "Swamp", "Island", "Island", "Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dress_down = scenario.find("Dress Down", Zone.BATTLEFIELD, "alice")
    advance_into_end_step(scenario)
    assert scenario.stack_names() == ["Dress Down's triggered ability"]

    scenario.cast_and_resolve(
        "Utter End",
        *scenario.untapped_sources("Plains", "Swamp", "Island", "Island"),
        targets=[dress_down],
    )
    assert dress_down.zone is Zone.EXILE
    before = sorted(scenario.battlefield_names())

    resolve_stack(scenario)

    assert dress_down.zone is Zone.EXILE
    assert sorted(scenario.battlefield_names()) == before
    assert [card.name for card in scenario.player("alice").graveyard] == ["Utter End"]


def test_a_source_bounced_and_recast_in_response_is_a_new_object_the_trigger_skips():
    """CR 400.7: the Dress Down that comes back is a new object, so the first
    one's end step trigger has no source to sacrifice. CR 603.2b: the new one
    arrived after the end step began and survives it."""
    scenario = board(
        hand=["Cryptic Command"],
        battlefield=["Dress Down", *["Island"] * 6, "Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dress_down = scenario.find("Dress Down", Zone.BATTLEFIELD, "alice")
    advance_into_end_step(scenario)
    assert scenario.stack_names() == ["Dress Down's triggered ability"]

    casting = scenario.cast("Cryptic Command")
    casting.choose_modes([2, 4])
    casting.choose_targets([dress_down])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert dress_down.zone is Zone.HAND

    scenario.cast_onto_stack("Dress Down", *scenario.untapped_sources("Island", "Island"))
    scenario.resolve_top()  # Dress Down enters
    scenario.resolve_top()  # its enters trigger draws
    assert dress_down.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == ["Dress Down's triggered ability"]

    scenario.resolve_top()  # the first object's end step trigger

    assert dress_down.zone is Zone.BATTLEFIELD
    advance_to(scenario, Step.CLEANUP)
    assert dress_down.zone is Zone.BATTLEFIELD


def test_ball_lightning_sacrifices_this_creature_at_the_end_step():
    """Off-pool generality: "sacrifice this creature", a different card type
    after "this", on a creature rather than an enchantment."""
    scenario = board(
        hand=["Ball Lightning"], battlefield=["Mountain", "Mountain", "Mountain"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    ball = scenario.cast_and_resolve(
        "Ball Lightning", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )
    assert ball.zone is Zone.BATTLEFIELD

    advance_into_end_step(scenario)
    assert scenario.stack_names() == ["Ball Lightning's triggered ability"]
    resolve_stack(scenario)

    assert ball.zone is Zone.GRAVEYARD

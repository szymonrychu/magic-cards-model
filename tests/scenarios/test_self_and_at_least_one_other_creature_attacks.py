""" "Whenever `<self>` and at least one other creature[ token] attack, ..." -
a compound self-plus-group attack trigger condition (CR 508.3a's ordinary
per-attacker reading, widened to require a *second* attacker too).

- **Invasion of Kylem // Valor's Reach Tag Team** (the reported card) grants
  its own Warrior tokens "Whenever this token and at least one other
  creature token attack, put a +1/+1 counter on this token." - narrowed to
  "creature token" rather than a bare "creature". Before this session, the
  generic self-attack reader (`matches_condition`'s own `mine: return event.
  subject_id == source.id` fallback) silently dropped the whole "and at
  least one other creature token" qualifier, so the ability fired the
  instant the token attacked *alone* - the same class of bug the identical
  fallback's own docstring warns every other event reader about.
- **Sokka, Lateral Strategist** (proof printing, Modern/Standard-legal, not
  the reported card and not in any deck pool) proves the shape generally:
  a real, differently-worded printing ("Sokka" - CR 201.5c's own shortened
  name - rather than "this token"; a bare "creature", not "creature token";
  drawing a card, not placing a counter).

CR numbers verified this session with `mise run rules:find`:

- **CR 508.3a** - "Whenever [a creature] attacks, ..." triggers if that
  creature is declared as an attacker.
- **CR 111.1** - a token is a marker used to represent a permanent.
- **CR 310.12b** / **CR 115.4** / **CR 310.6** - a Siege's own defeat
  trigger; damage to a battle removes defense counters.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _advance_to_alices_next_declare_attackers(scenario: PlayedScenario) -> None:
    """Crosses from turn 1 into a later turn where alice's tokens have lost
    summoning sickness (CR 302.6) - `start_at` alone cannot cross a turn
    boundary (`TurnMachine.advance_to`'s own docstring: "raises if it has
    already passed"), so this drives the raw turn machine forward with
    `advance()` until alice is active and back at her own declare-attackers
    step, having passed through at least one of bob's turns on the way."""
    seen_bob = False
    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "bob":
            seen_bob = True
        if (
            seen_bob
            and scenario.turn.active_player == "alice"
            and scenario.step is Step.DECLARE_ATTACKERS
        ):
            return
    raise AssertionError("never reached alice's next declare-attackers step")


def _resolve_whole_stack(scenario: PlayedScenario) -> None:
    while scenario.stack_names():
        scenario.pass_until_resolved()


def _defeat_siege_with_bolts(scenario: PlayedScenario, siege, mountains: list) -> None:
    scenario.cast_and_resolve("Lightning Bolt", mountains[0], username="alice", targets=[siege])
    scenario.cast_and_resolve("Lightning Bolt", mountains[1], username="alice", targets=[siege])
    scenario.game.check_state_based_actions()
    assert siege.counter_count("defense") == 0
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # CR 310.12b's defeat trigger: exile, then cast
    scenario.pass_until_resolved()  # the transformed sorcery resolves: two Warrior tokens


def _two_warrior_tokens(scenario: PlayedScenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.put_onto_battlefield("Invasion of Kylem", "alice")
    scenario.pass_until_resolved()  # the Siege's own enters trigger: no legal target
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _defeat_siege_with_bolts(scenario, siege, mountains)
    return scenario.creatures("Warrior Token", "Warrior Token", username="alice")


def test_both_warrior_tokens_get_a_counter_when_they_attack_together():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Invasion of Kylem", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    warriors = _two_warrior_tokens(scenario)
    _advance_to_alices_next_declare_attackers(scenario)

    scenario.attack_with(*warriors)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    _resolve_whole_stack(scenario)

    assert warriors[0].counter_count("+1/+1") == 1
    assert warriors[1].counter_count("+1/+1") == 1


def test_a_warrior_token_attacking_alone_gets_no_counter():
    """CR 508.3a's ordinary self-attack trigger still needs "at least one
    other creature token" too - a lone attacker never satisfies it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Invasion of Kylem", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    warriors = _two_warrior_tokens(scenario)
    _advance_to_alices_next_declare_attackers(scenario)

    scenario.attack_with(warriors[0])
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    assert scenario.stack_names() == []  # the trigger never even goes on the stack
    assert warriors[0].counter_count("+1/+1") == 0
    assert warriors[1].counter_count("+1/+1") == 0


def test_a_warrior_attacking_with_a_nontoken_creature_gets_no_counter():
    """ "at least one other creature **token**" (CR 111.1) - a non-token
    Grizzly Bears attacking alongside does not satisfy it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Invasion of Kylem", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    warriors = _two_warrior_tokens(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    _advance_to_alices_next_declare_attackers(scenario)

    scenario.attack_with(warriors[0], bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    assert scenario.stack_names() == []
    assert warriors[0].counter_count("+1/+1") == 0


def test_sokka_off_pool_proof_draws_a_card_attacking_with_another_creature():
    """Sokka, Lateral Strategist's own "Whenever Sokka and at least one
    other creature attack, draw a card." - the bare "creature" form (no
    "token" restriction), proving the shape generally on a real, unrelated,
    Modern/Standard-legal printing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Mountain"],
            battlefield=["Sokka, Lateral Strategist", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    sokka = scenario.creature("Sokka, Lateral Strategist", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(sokka, bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    _resolve_whole_stack(scenario)

    assert scenario.find("Mountain", Zone.HAND, "alice") is not None


def test_sokka_off_pool_proof_draws_nothing_attacking_alone():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Mountain"], battlefield=["Sokka, Lateral Strategist"])
        .player("bob")
        .build()
    )
    sokka = scenario.creature("Sokka, Lateral Strategist", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(sokka)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    assert scenario.stack_names() == []
    assert scenario.player("alice").cards_in(Zone.HAND) == []

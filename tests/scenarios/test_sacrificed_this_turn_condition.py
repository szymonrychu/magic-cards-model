"""Scenario: "if you sacrificed a permanent this turn" - a per-turn history
condition (CR 701.21a's sacrifice: "its controller moves it from the
battlefield directly to its owner's graveyard").

Phoenix Fleet Airship: "At the beginning of your end step, if you sacrificed a
permanent this turn, create a token that's a copy of this Vehicle." - an
intervening if (CR 603.4) read off `Game.permanents_sacrificed_this_turn`,
which only a sacrifice writes: a creature that dies to damage was never
sacrificed, a permanent the *opponent* sacrificed was not sacrificed by you,
and a sacrifice last turn is not one this turn. The token is a copy of the
Airship (CR 707.2's copiable values - name, types, rules text).

Goblin Blast-Runner's "This creature gets +2/+0 and has menace as long as you
sacrificed a permanent this turn." is the second printing: the same condition
on a static ability's "as long as" (CR 611.3a: re-read continuously, never
locked in), off the same record.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _airship_board(*alice_battlefield: str, bob_battlefield: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Phoenix Fleet Airship", *alice_battlefield],
            library=["Swamp"] * 6,
        )
        .player(
            "bob",
            battlefield=list(bob_battlefield),
            hand=["Lightning Bolt"],
            library=["Island"] * 6,
        )
        .build()
    )


def _airships(scenario: Scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Phoenix Fleet Airship"
    ]


def _bombard(scenario: Scenario, victim, *, username: str = "alice", target="bob") -> None:
    """Goblin Bombardment's "Sacrifice a creature: ... deals 1 damage to any
    target" - the sacrifice is the activation's cost (CR 601.2h)."""
    bombardment = scenario.creature("Goblin Bombardment", username)
    scenario.activate(bombardment, username=username, sacrificing=[victim], targets=[target])
    scenario.pass_until_resolved()


def _to_end_step(scenario: Scenario) -> None:
    """CR 500.6's "at the beginning of" triggers are emitted by `advance`."""
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def test_no_sacrifice_no_copy():
    scenario = _airship_board("Goblin Bombardment", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_end_step(scenario)

    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []
    assert len(_airships(scenario)) == 1


def test_a_sacrifice_this_turn_makes_a_token_copy_at_end_step():
    scenario = _airship_board("Goblin Bombardment", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bombard(scenario, scenario.creature("Grizzly Bears", "alice"))
    _to_end_step(scenario)

    assert scenario.stack_names() == ["Phoenix Fleet Airship's triggered ability"]
    scenario.resolve_top()

    airships = _airships(scenario)
    assert len(airships) == 2
    (token,) = [airship for airship in airships if airship.token]
    chars = scenario.game.computed_board().of(token)
    assert chars.name == "Phoenix Fleet Airship"
    assert "Vehicle" in chars.subtypes
    assert "Flying" in token.card.keywords


def test_two_sacrifices_still_make_one_copy_per_airship():
    scenario = _airship_board("Goblin Bombardment", "Grizzly Bears", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    _bombard(scenario, first)
    _bombard(scenario, second)
    _to_end_step(scenario)
    scenario.resolve_top()

    assert len(_airships(scenario)) == 2


def test_a_creature_dying_to_damage_was_not_sacrificed():
    scenario = _airship_board("Grizzly Bears", bob_battlefield=("Mountain",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert bears.zone is Zone.GRAVEYARD
    _to_end_step(scenario)

    assert scenario.stack_names() == []
    assert len(_airships(scenario)) == 1


def test_the_opponents_sacrifice_is_not_yours():
    scenario = _airship_board(bob_battlefield=("Goblin Bombardment", "Grizzly Bears"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    _bombard(scenario, scenario.creature("Grizzly Bears", "bob"), username="bob", target="alice")
    _to_end_step(scenario)

    assert scenario.stack_names() == []
    assert len(_airships(scenario)) == 1


def test_a_sacrifice_last_turn_does_not_count_this_turn():
    """The record is per turn: Alice sacrifices on her turn, then on her next
    turn (nothing sacrificed) the Airship makes no copy."""
    scenario = _airship_board("Goblin Bombardment", "Grizzly Bears")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bombard(scenario, scenario.creature("Grizzly Bears", "alice"))
    _to_end_step(scenario)
    scenario.resolve_top()
    assert len(_airships(scenario)) == 2

    while not (scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    _to_end_step(scenario)

    assert scenario.stack_names() == []
    assert len(_airships(scenario)) == 2


def test_a_sacrifice_paid_for_a_mana_ability_counts_too():
    """Any sacrifice counts, whatever it paid for: Skirk Prospector's
    "Sacrifice a Goblin: Add {R}." is a mana ability (CR 605.1a) that never
    uses the stack, and sacrificing Skirk Prospector itself to it is still a
    sacrifice (CR 701.21a)."""
    scenario = _airship_board("Skirk Prospector")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prospector = scenario.creature("Skirk Prospector", "alice")
    scenario.activate(prospector, sacrificing=[prospector])
    assert prospector.zone is Zone.GRAVEYARD
    _to_end_step(scenario)
    scenario.resolve_top()

    assert len(_airships(scenario)) == 2


# -- Goblin Blast-Runner: the same condition on a static "as long as" -------


def _blast_runner_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Blast-Runner", "Goblin Bombardment", "Grizzly Bears"],
            library=["Mountain"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )


def test_blast_runner_is_a_plain_1_2_before_any_sacrifice():
    scenario = _blast_runner_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    runner = scenario.creature("Goblin Blast-Runner", "alice")

    chars = scenario.game.computed_board().of(runner)
    assert chars.power_toughness == (1, 2)
    assert not chars.has_ability("Menace")
    assert scenario.game.continuous_effects.layer_notices == []


def test_blast_runner_gets_bigger_and_menace_after_a_sacrifice():
    scenario = _blast_runner_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bombard(scenario, scenario.creature("Grizzly Bears", "alice"))
    runner = scenario.creature("Goblin Blast-Runner", "alice")

    chars = scenario.game.computed_board().of(runner)
    assert chars.power_toughness == (3, 2)
    assert chars.has_ability("Menace")


def test_blast_runner_is_back_to_normal_on_the_next_turn():
    scenario = _blast_runner_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bombard(scenario, scenario.creature("Grizzly Bears", "alice"))
    while scenario.turn.active_player != "bob":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    runner = scenario.creature("Goblin Blast-Runner", "alice")

    assert scenario.game.computed_board().of(runner).power_toughness == (1, 2)

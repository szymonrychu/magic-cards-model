"""Scenario: Kang the Conqueror's power-up rider, "Take an extra turn after
this one. During that turn, power-up abilities can't be activated."

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 500.7** - "Some effects can give a player extra turns. They do this
  by adding the turns directly after the specified turn... The most
  recently created turn will be taken first."
- **CR 702.193a** - power-up's own "Activate this ability only once".

"Take an extra turn after this one" is pre-existing, general machinery
(`machines/effects.py::_TAKE_EXTRA_TURNS_RE`), already proven elsewhere in
the pool against Teferi, Master of Time and Savor the Moment - not
reproven here. What this file proves is the second sentence: "During that
turn, power-up abilities can't be activated." - power-up is Marvel Super
Heroes-exclusive (CR 702.193 names no other set), so this rider has no
off-pool proof printing to stand beside Kang; recorded per this campaign's
own rule (k) in a dated MEMORY.md line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _advance_until(scenario: Scenario, predicate) -> None:
    """Advance until `predicate(scenario)` holds - the identical helper
    `test_delayed_attack_pump_until_your_next_turn.py` already uses for
    walking a scenario into a later turn."""
    while not predicate(scenario):
        scenario.advance()


def test_kang_power_up_puts_the_counter_and_grants_an_extra_turn():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kang the Conqueror"] + ["Island"] * 8)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kang = scenario.creature("Kang the Conqueror", "alice")
    sources = scenario.untapped_sources(*["Island"] * 8)
    turns_before = scenario.game.turn.turns_taken

    scenario.activate(kang, *sources)
    scenario.pass_until_resolved()

    assert kang.counters[Counter.PLUS_ONE] == 1
    # CR 500.7: the extra turn is inserted directly after this one - queued,
    # not yet taken.
    assert scenario.game.turn.extra_turns == ["alice"]
    assert scenario.game.turn.turns_taken == turns_before


def test_power_up_abilities_of_any_permanent_are_refused_during_the_restricted_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Kang the Conqueror", "Abomination, Terrifying Titan"] + ["Island"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kang = scenario.creature("Kang the Conqueror", "alice")
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")
    sources = scenario.untapped_sources(*["Island"] * 8)
    turns_before = scenario.game.turn.turns_taken

    assert scenario.why_cannot_activate(abomination) is None
    scenario.activate(kang, *sources)
    scenario.pass_until_resolved()

    # Walk into the granted extra turn (CR 500.7 inserts it directly after
    # this one, so it is the very next turn taken - alice's again).
    _advance_until(
        scenario,
        lambda s: s.game.turn.turns_taken > turns_before and s.game.turn.active_player == "alice",
    )

    reason = scenario.why_cannot_activate(abomination)
    assert reason is not None and "power-up ability can't be activated this turn" in reason


def test_the_restriction_ends_after_the_extra_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 10,
            battlefield=["Kang the Conqueror", "Abomination, Terrifying Titan"] + ["Island"] * 8,
        )
        .player("bob", library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kang = scenario.creature("Kang the Conqueror", "alice")
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")
    sources = scenario.untapped_sources(*["Island"] * 8)
    turns_before = scenario.game.turn.turns_taken

    scenario.activate(kang, *sources)
    scenario.pass_until_resolved()

    _advance_until(
        scenario,
        lambda s: s.game.turn.turns_taken > turns_before and s.game.turn.active_player == "alice",
    )
    assert scenario.why_cannot_activate(abomination) is not None
    restricted_turn = scenario.game.turn.turns_taken

    # bob's ordinary turn, after the granted extra one.
    _advance_until(
        scenario,
        lambda s: s.game.turn.turns_taken > restricted_turn and s.game.turn.active_player == "bob",
    )

    assert scenario.why_cannot_activate(abomination) is None


def test_a_permanent_not_controlled_by_kangs_controller_is_also_restricted():
    """The rider names no "you control" - "power-up abilities can't be
    activated" is a blanket restriction for the turn, not scoped to Kang's
    own controller."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Kang the Conqueror"] + ["Island"] * 8)
        .player("bob", battlefield=["Hulk, Gamma Goliath"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kang = scenario.creature("Kang the Conqueror", "alice")
    hulk = scenario.creature("Hulk, Gamma Goliath", "bob")
    sources = scenario.untapped_sources(*["Island"] * 8)
    turns_before = scenario.game.turn.turns_taken

    scenario.activate(kang, *sources)
    scenario.pass_until_resolved()
    _advance_until(
        scenario,
        lambda s: s.game.turn.turns_taken > turns_before and s.game.turn.active_player == "alice",
    )

    reason = scenario.why_cannot_activate(hulk)
    assert reason is not None and "power-up ability can't be activated this turn" in reason

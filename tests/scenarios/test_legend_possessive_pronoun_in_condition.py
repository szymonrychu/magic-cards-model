"""Scenario: a legend's own possessive pronoun in a condition - "If her power
is 4 or greater" (T-136 b1).

CR 201.5c lets a card name itself by a shortened name; a legend's printed
"his"/"her" is the same self-reference. `abilities.legendary_self_pronoun_
normalized` turned every "her" into the object pronoun "it", so Jett Reno's
"If her power is 4 or greater, instead draw a card." became "If it power is
..." and no condition reader accepted it: the whole trigger was silent. A
possessive before "power" and the like is now read as "this permanent's" (the
form the legend's own name already normalises to), and only then is a bare
"her" read as the object.

- Jett Reno, Problem Solver (trk): the trigger's "instead" pair (CR 614.1a)
  keyed on her own power, which her second ability raises by +1/+1 counters.
- Viv Vision, Teen Synthezoid (the off-set proof, a different template): a
  trailing "draw a card if her power is 4 or greater" on an attack trigger,
  already read through the same pronoun path and kept as a regression proof.

Every CR number was looked up with `mise run rules:find`:

- **CR 201.5c** - a shortened name is treated as the full name.
- **CR 614.1a** - "instead" effects are replacement effects.
- **CR 701.25a** - surveil (the base instruction Jett's alternative replaces).
- **CR 122.1a** - a +X/+Y counter adds to power and toughness.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import PlayedScenario, Scenario


def _jett(*, counters: int = 0) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jett Reno, Problem Solver"],
            library=["Island", "Plains", "Swamp", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    if counters:
        jett = scenario.creature("Jett Reno, Problem Solver", "alice")
        scenario.game.add_counters(jett, "+1/+1", counters)
    return scenario


def _tap_jett(scenario: PlayedScenario) -> None:
    jett = scenario.creature("Jett Reno, Problem Solver", "alice")
    scenario.attack_with(jett, defending="bob")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _hand(scenario: PlayedScenario) -> int:
    return len(scenario.player("alice").hand)


def _surveils(scenario: PlayedScenario) -> list:
    return [q for q in scenario.questions_asked() if q.source == "Jett Reno, Problem Solver"]


def test_jett_reno_below_four_power_surveils_and_does_not_draw():
    scenario = _jett()
    _tap_jett(scenario)
    assert _hand(scenario) == 0
    assert len(_surveils(scenario)) == 1


def test_jett_reno_at_three_power_is_still_the_base_instruction():
    scenario = _jett(counters=2)
    jett = scenario.creature("Jett Reno, Problem Solver", "alice")
    assert scenario.game.characteristics_of(jett).power == 3
    _tap_jett(scenario)
    assert _hand(scenario) == 0
    assert len(_surveils(scenario)) == 1


def test_jett_reno_at_four_power_draws_instead_of_surveilling():
    """Power exactly 4 (1 + three counters): the alternative replaces the
    surveil whole - a card is drawn and no surveil question is asked."""
    scenario = _jett(counters=3)
    jett = scenario.creature("Jett Reno, Problem Solver", "alice")
    assert scenario.game.characteristics_of(jett).power == 4
    top = scenario.top_of_library(1)[0]
    _tap_jett(scenario)
    assert _hand(scenario) == 1
    assert scenario.player("alice").hand[0] is top
    assert _surveils(scenario) == []


def test_jett_reno_well_above_four_power_still_draws_a_single_card():
    scenario = _jett(counters=6)
    _tap_jett(scenario)
    assert _hand(scenario) == 1
    assert _surveils(scenario) == []


def test_jett_reno_reads_her_own_power_not_the_opponents_creature():
    """The condition is about Jett Reno: a large creature on the other side
    does not make her draw."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jett Reno, Problem Solver"],
            library=["Island", "Plains", "Swamp"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.add_counters(giant, "+1/+1", 6)
    _tap_jett(scenario)
    assert _hand(scenario) == 0
    assert len(_surveils(scenario)) == 1


def test_viv_vision_draws_only_when_her_power_is_four_or_greater():
    """A different template of the same pronoun: a trailing "if her power is
    4 or greater" on an attack trigger."""
    for counters, drawn in ((0, 0), (2, 1)):
        scenario = (
            Scenario()
            .player("alice", battlefield=["Viv Vision, Teen Synthezoid"], library=["Island"] * 3)
            .player("bob")
            .build()
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        viv = scenario.creature("Viv Vision, Teen Synthezoid", "alice")
        if counters:
            scenario.game.add_counters(viv, "+1/+1", counters)
        scenario.attack_with(viv, defending="bob")
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()
        assert len(scenario.player("alice").hand) == drawn
        assert viv.zone is Zone.BATTLEFIELD

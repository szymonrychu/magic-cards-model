"""Riot: choose a +1/+1 counter or haste as the permanent enters (CR 702.136).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 702.136a** - "Riot is a static ability. 'Riot' means 'You may have this
  permanent enter with an additional +1/+1 counter on it. If you don't, it
  gains haste.'"
- **CR 702.136b** - "If a permanent has multiple instances of riot, each works
  separately."
- **CR 614.1c** - "[This permanent] enters with ...," "As [this permanent]
  enters ...," or "[This permanent] enters as ..." are replacement effects.
- **CR 614.12** / **CR 614.12a** - such an effect may come from the permanent
  itself, applies however the permanent enters (cast or not), and any choice
  it requires is made before the permanent is on the battlefield.
- **CR 611.3d** - a continuous effect from a static ability that grants an
  ability functioning only on the battlefield lasts as long as the effect
  states; with no duration stated, it lasts until the end of the game -
  riot's own reminder text states none, so the haste grant is indefinite.
- **CR 400.7** - "An object that moves from one zone to another becomes a new
  object with no memory of, or relation to, its previous existence" - a
  blinked permanent is asked again, and an earlier haste grant (scoped to the
  incarnation it was made for) does not carry over.
- **CR 302.6** - the "summoning sickness" rule: a creature can't attack unless
  it has been under its controller's control continuously since their most
  recent turn began, which haste is an exception to.

Skarrgan Hellkite is the printing already in the pool, with a second ability
("Activate only if this creature has a +1/+1 counter on it") that is proof
riot places a real counter rather than a flag - the engine's own generic
"Activate only if [this] has a/an N counter on it" reader
(`machines/conditions/board.py`) is what makes that ability legal or not,
with no riot-specific or card-specific code involved. Zhur-Taa Goblin
(`{R}{G}`, a vanilla riot creature with no other abilities) is the second
printing proving the mechanic is read off the keyword rather than off
Skarrgan Hellkite's own sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Zhur-Taa Goblin", "Ephemerate"],
            battlefield=["Mountain", "Forest", "Plains"],
        )
        .player("bob", battlefield=["Mountain"] * 6)
    )


def _cast_goblin(scenario):
    (mountain, forest) = scenario.untapped_sources("Mountain", "Forest")
    scenario.cast_and_resolve("Zhur-Taa Goblin", mountain, forest)
    return scenario.creature("Zhur-Taa Goblin")


def test_choosing_the_counter_enters_with_a_counter_and_no_haste():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)

    assert goblin.counter_count("+1/+1") == 1
    assert not has_keyword(goblin, Keyword.HASTE, scenario.game)


def test_choosing_the_counter_cannot_attack_the_turn_it_entered():
    """CR 302.6: no haste, so summoning sickness still applies."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)

    assert goblin.summoning_sick
    assert not scenario.can_attack(goblin)


def test_declining_enters_with_no_counter_and_haste():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)

    assert goblin.counter_count("+1/+1") == 0
    assert has_keyword(goblin, Keyword.HASTE, scenario.game)


def test_declining_can_attack_the_turn_it_entered():
    """CR 702.136a's haste is exactly CR 302.6's exception."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)

    assert goblin.summoning_sick
    assert scenario.can_attack(goblin)


def test_declining_still_has_haste_after_the_turn_it_entered_ends():
    """CR 611.3d: no duration is stated, so the grant is indefinite - not an
    "until end of turn" effect that cleanup would clear."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)
    scenario.turn.advance_to(Step.CLEANUP)

    assert has_keyword(goblin, Keyword.HASTE, scenario.game)


def test_riot_applies_to_a_permanent_put_onto_the_battlefield_too():
    """CR 614.12: the replacement modifies the entering permanent itself,
    however it gets there - cast or not."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Zhur-Taa Goblin")

    scenario.put_onto_battlefield("Zhur-Taa Goblin", "alice")
    goblin = scenario.find("Zhur-Taa Goblin", Zone.BATTLEFIELD, "alice")

    assert goblin.counter_count("+1/+1") == 1


def test_the_question_goes_to_the_entering_permanents_controller():
    """CR 608.2d/614.12a: the choice belongs to the permanent's controller,
    not to whoever else is at the table. alice and bob are queued opposite
    answers; the permanent (bob's own) enters under bob's control, so bob's
    answer - haste, no counter - is the one that must apply."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", hand=["Zhur-Taa Goblin"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source="Zhur-Taa Goblin")
    scenario.will_take_the_may(False, username="bob", source="Zhur-Taa Goblin")

    scenario.put_onto_battlefield("Zhur-Taa Goblin", "bob")
    goblin = scenario.find("Zhur-Taa Goblin", Zone.BATTLEFIELD, "bob")

    assert goblin.counter_count("+1/+1") == 0
    assert has_keyword(goblin, Keyword.HASTE, scenario.game)


def test_a_blinked_permanent_is_a_new_object_and_is_asked_again():
    """CR 400.7: a permanent that leaves and returns is a new object. The
    goblin declines the counter (gets haste) the first time it enters, then
    Ephemerate exiles and returns it - the second entrance takes the counter
    instead, and the earlier haste grant, scoped to the incarnation before
    the blink, does not carry over to the new one."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Zhur-Taa Goblin")

    goblin = _cast_goblin(scenario)
    assert has_keyword(goblin, Keyword.HASTE, scenario.game)
    stamp_before = goblin.zone_change_stamp

    scenario.will_take_the_may(True, source="Zhur-Taa Goblin")
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Ephemerate", plains, targets=[goblin])

    blinked = scenario.creature("Zhur-Taa Goblin")
    assert blinked.zone_change_stamp != stamp_before  # CR 400.7: a new object
    assert blinked.counter_count("+1/+1") == 1  # asked again, chose the counter this time
    assert not has_keyword(blinked, Keyword.HASTE, scenario.game)  # no carried-over grant


def test_a_second_printing_shares_the_mechanic():
    """Skarrgan Hellkite: the printing already in the pool, proof the counter
    riot places is a real one - its own activated ability is legal only with
    a +1/+1 counter actually on it, read by the engine's generic "Activate
    only if [this] has a/an N counter on it" reader with no riot-specific or
    card-specific code."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Skarrgan Hellkite"],
            battlefield=["Mountain"] * 9,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Skarrgan Hellkite")

    mountains = scenario.untapped_sources(*["Mountain"] * 5)
    scenario.cast_and_resolve("Skarrgan Hellkite", *mountains)
    hellkite = scenario.creature("Skarrgan Hellkite")

    assert hellkite.counter_count("+1/+1") == 1
    assert scenario.why_cannot_activate(hellkite, index=0) is None


def test_declining_on_the_second_printing_leaves_its_activated_ability_illegal():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Skarrgan Hellkite"],
            battlefield=["Mountain"] * 9,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, source="Skarrgan Hellkite")

    mountains = scenario.untapped_sources(*["Mountain"] * 5)
    scenario.cast_and_resolve("Skarrgan Hellkite", *mountains)
    hellkite = scenario.creature("Skarrgan Hellkite")

    assert hellkite.counter_count("+1/+1") == 0
    assert has_keyword(hellkite, Keyword.HASTE, scenario.game)
    assert scenario.why_cannot_activate(hellkite, index=0) is not None

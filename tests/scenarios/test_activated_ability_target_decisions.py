"""Scenario: an activated ability's own controller is asked for its targets
(CR 601.2c, CR 602.2b).

The defect this file is written against: `Game.activate_ability` only
*validated* whatever `targets` a caller happened to pass in
(`profile.check(list(targets or []), ...)`); it never asked for them. Two
concrete probes on a real board proved it:

- Karn, the Great Creator's +1 ("Until your next turn, up to one target
  noncreature artifact becomes an artifact creature ...") activated with
  `targets=None` and a legal Sol Ring on the battlefield went on the stack
  with `targets: []` and `game.decisions.asked` was empty - the player was
  never offered the choice, so "up to one" silently became zero.
- Mother of Runes's mandatory `{T}: Target creature you control gains
  protection ...` activated with `targets=None` and a legal creature present
  raised `ValueError: too few targets: 0 chosen where the spell requires 1`
  instead of asking who to protect.

CR 602.2b: "the remainder of the process for activating an ability is
identical to the process for casting a spell listed in rules 601.2b-i" -
which pulls in CR 601.2c, "the player announces their choice of an
appropriate object or player for each target the [ability] requires." CR
115.6's "up to N" is the only thing that makes zero a legal announcement;
it does not make the announcement optional to ask for in the first place.

The fix, in `Game.activate_ability` / `Game._ask_targets`: when the caller
supplies no `targets` at all, the ability's own controller is asked, through
the ordinary `Game.ask` `CHOOSE_TARGETS` question, exactly the way a
triggered ability's own CR 603.3d announcement is already asked
(`Game._ask_trigger_targets`, `tests/scenarios/test_trigger_target_decisions.py`)
- both now share `Game._ask_targets` so the two paths (602.2b and 603.3d, both
importing 601.2c) do not carry two implementations of the same question. An
explicit `targets` list - even an empty one - is a real answer already given
and is checked exactly as it always was, never re-asked.

A mandatory requirement (CR 115.6's "up to N" does not apply) with no legal
target at all makes the activation illegal outright (CR 601.2e, imported by
602.2b: "if the proposed spell is illegal, the game returns to the moment
before ... was proposed"), the same refusal `Game.cast_free_from_exile`
already gives a spell with no legal target for the identical reason
(CR 601.2c) - not CR 603.3d's "removed from the stack" (that rule is about a
*triggered* ability, which the game puts on the stack unconditionally and
only then discovers has nothing to point at; an activation is a player's own
proposed action and CR 601.2e refuses the whole proposal before anything
beyond cost payment happens).

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file, against the CR release
`knowledge_search(type="cr_versions")` names current (`2026-08-19`,
sha256 `4381ad1b...423f`).
"""

from dataclasses import dataclass, field

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import NOT_ANSWERED, Decision, DecisionKind
from magic_cards_model.models import Color, Zone

from .harness import Scenario


@dataclass
class QueueProvider:
    """A `DecisionProvider` that answers `CHOOSE_TARGETS` questions in order.

    Not a mock: a real implementation of the one-method `DecisionProvider`
    protocol `Game.ask` calls, standing in for what a live player at a
    keyboard would be behind - the same stub
    `tests/scenarios/test_trigger_target_decisions.py` already uses for the
    sibling, triggered-ability question.
    """

    answers: list[tuple[object, ...]] = field(default_factory=list)
    asked: list[Decision] = field(default_factory=list)

    def decide(self, decision: Decision) -> object:
        self.asked.append(decision)
        if decision.kind is not DecisionKind.CHOOSE_TARGETS or not self.answers:
            return NOT_ANSWERED
        return self.answers.pop(0)


# --------------------------------------------------------------------------
# Karn, the Great Creator's +1: "up to one target noncreature artifact"
# --------------------------------------------------------------------------


def _karn_and_sol_ring() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, the Great Creator", "Sol Ring"],
            library=["Mountain"] * 5,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )


def test_karns_plus_one_asks_for_its_target_when_none_is_supplied():
    """The exact reported probe: `targets=None` used to skip the question
    entirely. It must now be asked, addressed to alice, offering Sol Ring."""
    scenario = _karn_and_sol_ring()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    sol_ring = scenario.creature("Sol Ring", "alice")

    provider = QueueProvider(answers=[(sol_ring,)])
    scenario.game.decisions.provider = provider

    scenario.activate(karn, index=0)

    assert len(provider.asked) == 1, "the reported defect: this used to be empty"
    decision = provider.asked[0]
    assert decision.kind is DecisionKind.CHOOSE_TARGETS
    assert decision.player == "alice"
    assert decision.source == "Karn, the Great Creator"
    assert decision.target_minimum == 0, "CR 115.6: 'up to one' is optional"
    assert decision.target_maximum == 1

    scenario.pass_until_resolved()
    computed = scenario.game.computed_board().of(sol_ring)
    assert computed.is_creature, "answering with Sol Ring must animate it"
    assert computed.power == 1 and computed.toughness == 1, "Sol Ring's mana value is 1"


def test_karns_plus_one_answered_with_nothing_changes_nothing_and_never_animates_karn():
    """CR 115.6: choosing zero out of an "up to one" question is legal, and
    the ability must then affect nothing - never fall back to animating
    Karn himself, the exact defect `test_type_changing_and_pt_setting_
    effects.py::test_karns_plus_one_with_no_target_chosen_changes_nothing`
    already guards for the explicit-empty-list path. This is the same
    guarantee through the newly-added ask path instead."""
    scenario = _karn_and_sol_ring()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    sol_ring = scenario.creature("Sol Ring", "alice")
    assert karn.loyalty == 5

    scenario.game.decisions.provider = QueueProvider(answers=[()])
    scenario.activate(karn, index=0)
    assert karn.loyalty == 6, "CR 606.4: the +1 cost is paid on activation regardless"
    scenario.pass_until_resolved()

    computed_karn = scenario.game.computed_board().of(karn)
    assert not computed_karn.is_creature, "declining must never redirect onto the source"
    assert computed_karn.power is None and computed_karn.toughness is None
    assert not karn.summoning_sick

    computed_sol_ring = scenario.game.computed_board().of(sol_ring)
    assert not computed_sol_ring.is_creature, "the untargeted artifact stays untouched"
    assert computed_sol_ring.power is None and computed_sol_ring.toughness is None


def test_an_explicit_target_list_is_still_used_without_being_asked():
    """The fallback must be exactly that - a fallback. A caller that already
    supplies targets (the whole existing scenario harness, and the pre-fix
    contract) must see no question at all."""
    scenario = _karn_and_sol_ring()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    sol_ring = scenario.creature("Sol Ring", "alice")

    provider = QueueProvider()
    scenario.game.decisions.provider = provider

    scenario.activate(karn, index=0, targets=[sol_ring])

    assert provider.asked == [], "an explicit target list is not asked for"
    scenario.pass_until_resolved()
    computed = scenario.game.computed_board().of(sol_ring)
    assert computed.is_creature


# --------------------------------------------------------------------------
# Mother of Runes: a mandatory "{T}: Target creature you control ..."
# --------------------------------------------------------------------------


def _mother_of_runes() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Mother of Runes", "Grizzly Bears"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )


def test_mother_of_runes_mandatory_target_is_asked_rather_than_raised():
    """The exact reported probe: `targets=None` used to raise `ValueError:
    too few targets: 0 chosen where the spell requires 1` instead of asking.
    A legal creature is present, so CR 601.2c requires the question be put,
    not skipped."""
    scenario = _mother_of_runes()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")

    provider = QueueProvider(answers=[(bears,)])
    scenario.game.decisions.provider = provider

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    ability = scenario.activate(mother, index=0)

    assert len(provider.asked) == 1, "the reported defect: this used to raise instead"
    decision = provider.asked[0]
    assert decision.kind is DecisionKind.CHOOSE_TARGETS
    assert decision.player == "alice"
    assert decision.target_minimum == 1, "a plain 'target creature' is mandatory"
    assert ability is not None
    assert len(ability.targets) == 1


def test_mother_of_runes_empty_answer_is_refused_while_a_legal_target_exists():
    """CR 601.2c: "the player announces their choice ... for each target the
    [ability] requires" - not a "you may" once a legal target exists, so an
    empty answer is refused the same way `Game.ask` already refuses one for a
    triggered ability's identical CR 603.3d announcement
    (`test_trigger_target_decisions.py::test_an_empty_answer_is_refused_
    while_a_legal_target_exists`)."""
    scenario = _mother_of_runes()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")

    scenario.game.decisions.provider = QueueProvider(answers=[()])
    with pytest.raises(ValueError, match="601.2c"):
        scenario.activate(mother, index=0)

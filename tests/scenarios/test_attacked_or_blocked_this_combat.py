"""Scenario: "At end of combat, if this `<subject>` attacked or blocked this
combat, `<effect>`." (CR 511.2, CR 508.1, CR 509.1g) - Clockwork Steed's own
trigger, and the standalone "remove a `<kind>` counter from it" effect its
resolution needs. The activated ability ("{X}, {T}: Put up to X +1/+0
counters ...") and its own effect are out of scope for this file; only its
printed "Activate only during your upkeep" restriction is touched, and only
to confirm it needed no fix at all.

Verified with `mise run rules:find` in this session:

- **CR 511.2**: "at end of combat" is the beginning of the end of combat step
  (`Step.END_OF_COMBAT`, already read as a `BEGINNING_OF_STEP` trigger - no
  change needed there).
- **CR 508.1** / **CR 509.1g**: declaring attackers and blockers.
- **CR 122.5**: removing a counter.
- **CR 602.1b**: `Game.read_activation_instructions` already splits "during
  your upkeep" into a timing window (`Step.UPKEEP`), read generically for any
  step - this restriction needed no new code, which
  `test_activate_only_during_your_upkeep_needed_no_fix` below documents
  rather than asserts a change.

**This clause is distinct from `_ATTACKS_OR_BLOCKS_RE`'s "this `<kind>`
attacks or blocks"** (`tests/scenarios/test_this_kind_self_reference_
triggers.py`): that is a present-tense trigger *event* alternation (CR
603.2), checked as the attack or block is declared; this is a past-tense
*intervening if* (CR 603.4) checked at end of combat, after the declarations
that decided it are long done. The two share no code.

Cards staged straight onto the battlefield (`battlefield=[...]`) skip CR
614.1c's own "enters with N counters" replacement effect - the scenario
builder places the `CardState` directly, with no zone-change replacement of
any kind, which is also what keeps a staged creature from being summoning
sick. Since neither Clockwork Steed's own "enters with four +1/+0 counters"
line nor Encumbered Reejerey's is the clause this file is testing,
`Game.add_counters` sets the count directly instead of routing the card
through a real cast just to get there.

Oracle text pulled with `scripts/add_card.py`:

- **Clockwork Steed** (the reported card): "At end of combat, if this
  creature attacked or blocked this combat, remove a +1/+0 counter from it."
- **Daredevil Dragster** (Modern/Pioneer legal, the second printing of the
  intervening-if template, on a Vehicle rather than a creature and a
  different effect - "put a velocity counter on it. Then if it has two or
  more velocity counters on it, sacrifice it and draw two cards."): the
  "Then if" tail is out of scope here; only the shared leading intervening
  if and its own resolution getting as far as raising the velocity counter
  is under test.
- **Encumbered Reejerey** (Modern/Pioneer/Standard legal, the second
  printing of the *effect* template - "remove a `<kind>` counter from it" -
  on a different counter kind and a different trigger entirely, "Whenever
  this creature becomes tapped while it has a -1/-1 counter on it, remove a
  -1/-1 counter from it").
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from tests.scenarios.harness import PlayedScenario, Scenario


def _resolve_everything(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _walk_to(scenario: PlayedScenario, step: Step) -> None:
    """Advance - never jump - to `step`, resolving whatever fires on the way
    (CR 511.2's own end-of-combat trigger is only proven by walking there)."""
    while scenario.step is not step:
        scenario.advance()
        _resolve_everything(scenario)


def test_clockwork_steed_loses_a_counter_after_it_attacked():
    scenario = Scenario().player("alice", battlefield=["Clockwork Steed"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    steed = scenario.creature("Clockwork Steed", "alice")
    scenario.game.add_counters(steed, "+1/+0", 4)
    scenario.attack_with(steed)
    scenario.no_blocks()

    _walk_to(scenario, Step.END_OF_COMBAT)
    _resolve_everything(scenario)

    assert steed.counter_count("+1/+0") == 3
    assert not scenario.game.intervening_if_notices


def test_clockwork_steed_loses_a_counter_after_it_blocked():
    """Alice attacks so she stays the default active player; bob's Clockwork
    Steed is the blocker whose own trigger is under test."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Clockwork Steed"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    steed = scenario.creature("Clockwork Steed", "bob")
    scenario.game.add_counters(steed, "+1/+0", 4)
    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, steed)

    _walk_to(scenario, Step.END_OF_COMBAT)
    _resolve_everything(scenario)

    assert steed.counter_count("+1/+0") == 3


def test_clockwork_steed_keeps_its_counters_if_it_did_neither():
    scenario = Scenario().player("alice", battlefield=["Clockwork Steed"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    steed = scenario.creature("Clockwork Steed", "alice")
    scenario.game.add_counters(steed, "+1/+0", 4)

    _walk_to(scenario, Step.END_OF_COMBAT)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert steed.counter_count("+1/+0") == 4


def test_daredevil_dragster_reads_the_identical_intervening_if():
    """A Vehicle, crewed and attacking, not a creature by nature - proves
    the reader is not keyed to Clockwork Steed's own subject word.

    Daredevil Dragster's own resolution effect ("put a velocity counter on
    it. Then if it has two or more velocity counters on it, sacrifice it and
    draw two cards.") is a compound this file does not implement - out of
    scope, per the reported card's own effect being someone else's job too.
    What is under test is only that the shared intervening if answers True
    here exactly as it does for Clockwork Steed: the ability reaches the
    stack rather than being silently dropped, and with no `InterveningIfNotice`
    at all - the fail-closed signal CR 603.4 gives an unread condition, which
    an unrelated unread *effect* is not."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Daredevil Dragster", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dragster = scenario.creature("Daredevil Dragster", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = crew_activation(scenario.game, dragster, [bears], "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragster)
    scenario.no_blocks()

    while scenario.step is not Step.END_OF_COMBAT:
        scenario.advance()
        if scenario.step is Step.END_OF_COMBAT:
            break
        _resolve_everything(scenario)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Daredevil Dragster's triggered ability"]
    assert not scenario.game.intervening_if_notices


def test_encumbered_reejerey_removes_a_negative_counter_from_itself():
    """Off-Clockwork-Steed proof of the standalone counter-removal effect: a
    different kind ("-1/-1"), a different trigger entirely (CR 603.2's own
    event qualifier, "becomes tapped while it has a counter", not this
    file's end-of-combat intervening if)."""
    scenario = Scenario().player("alice", battlefield=["Encumbered Reejerey"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reejerey = scenario.creature("Encumbered Reejerey", "alice")
    scenario.game.add_counters(reejerey, "-1/-1", 3)

    scenario.game.tap_permanent(reejerey)
    _resolve_everything(scenario)

    assert reejerey.counter_count("-1/-1") == 2


def test_activate_only_during_your_upkeep_needed_no_fix():
    """Documentation, not a change: `Game.read_activation_instructions`
    already reads "during your upkeep" as a timing window for any step name,
    so this restriction was never the gap - only the trigger and its effect
    were."""
    scenario = (
        Scenario().player("alice", battlefield=["Clockwork Steed"], library=["Island"] * 5).build()
    )
    scenario.start_at(Step.UPKEEP)
    steed = scenario.creature("Clockwork Steed", "alice")

    assert scenario.why_cannot_activate(steed, index=0) is None

    scenario.advance()  # draw

    assert scenario.why_cannot_activate(steed, index=0) is not None

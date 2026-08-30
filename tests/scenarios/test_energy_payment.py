"""Scenario: energy ({E}) as a payable cost (CR 107.14, CR 118.3).

CR 107.14: "The energy symbol is {E}. It represents one energy counter. To pay
{E}, a player removes one energy counter from themselves." `Player.energy` and
`Player.add_counters`/`remove_counters` already model the counter itself
(`tests/scenarios/test_counters.py` covers that half); this file covers the
other half - a resolving spell or ability actually *asking* CR 608.2d's
question and paying what comes back, which up to now nothing in the pool did.

Three distinct shapes, each read off a card's own printed text with no
per-card table row (`machines/effects.py`):

- **Galvanic Discharge** - "you may pay any amount of {E}", a variable-amount
  payment referenced by the damage it deals downstream
  (`_parse_target_get_energy_pay_damage`).
- **Wrath of the Skies** - the same variable-amount shape, referenced by a
  mass-destruction clause instead of a single target's damage
  (`_parse_x_energy_pay_destroy_by_mana_value`).
- **Static Prison** - "sacrifice this enchantment unless you pay {E}", a
  fixed-amount cost that averts a bad outcome rather than causing a bonus
  (`_parse_sacrifice_unless_pay_energy`).

Guide of Souls's "you may pay {E}{E}{E}. When you do, ..." is a fourth shape -
CR 603.12's reflexive trigger - and is deliberately **not** built here. A
sibling wave landed the reflexive-trigger machinery itself
(`machines/effects.py`'s `_parse_reflexive_sacrifice_clause`,
`ReflexiveClauseNotice`) against Grist, the Hunger Tide while this wave was in
flight, so the piece genuinely missing for Guide of Souls is narrower than it
first looked: not "no reflexive trigger support" and not "no may-pay-a-cost
decision" (this wave built that one, `DecisionKind.PAY_ENERGY`/
`Game.may_pay_energy`), but that `_parse_reflexive_sacrifice_clause` only
reads a reflexive **sacrifice**, never an arbitrary paid cost - so "you may
pay {E}{E}{E}" still falls through to the general `_unreadable_reflexive_
clause` and records a `ReflexiveClauseNotice` rather than resolving.
`test_guide_of_souls_records_a_notice_instead_of_resolving_silently` below
proves it now leaves a trace instead of doing nothing with no record
anywhere - the same "unreadable is not the same as no effect" discipline
every other notice in `machines/effects.py` already keeps.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 107.14** - the energy symbol and its payment.
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully."
- **CR 608.2d** - a resolving effect's own choices are announced while
  applying the effect, and "The player can't choose an option that's illegal
  or impossible."
- **CR 505.1** - "the first main phase (also known as the precombat main
  phase)" - Static Prison's own "your first main phase" needs this synonym
  read by `machines/triggers.py`'s step table before its trigger condition
  matches anything at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import ReflexiveClauseNotice
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def walk_to(scenario, step: Step) -> None:
    """Advance turn-by-turn - never jump - until `step`, resolving anything
    that fires along the way.

    CR 500.6's "a step began" event is emitted by `Game.advance`, not by
    `start_at`, which moves the turn machine directly and fires nothing - so a
    "beginning of your first main phase" trigger can only be proven by walking
    there. Copied from `test_delayed_trigger_clause_parsing.py`'s own helper
    rather than imported, so this file about one mechanic does not reach into
    another's test module for its plumbing.
    """
    while scenario.step is not step:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# --------------------------------------------------------------------------
# Galvanic Discharge: "Choose target creature or planeswalker. You get
# {E}{E}{E} (three energy counters), then you may pay any amount of {E}.
# Galvanic Discharge deals that much damage to that permanent."
# --------------------------------------------------------------------------


def _galvanic_discharge_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Galvanic Discharge"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_galvanic_discharge_pays_the_full_amount_and_deals_full_damage():
    """The happy path: alice pays all three energy she was just granted, and
    Grizzly Bears (2/2) takes lethal damage from it.

    `cast_and_resolve` already runs the state-based action that kills a
    lethally-damaged creature (CR 704.5g), which clears its marked damage as
    part of the zone change (CR 121.3's "damage marked on a permanent" is a
    fact about the permanent, gone once it is a new object elsewhere) - so
    the assertion here is the zone, not a `.damage` reading that would race
    the cleanup.
    """
    scenario = _galvanic_discharge_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_pay_energy_amount(3)

    scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    assert scenario.player("alice").energy == 0
    assert bears.zone is Zone.GRAVEYARD


def test_galvanic_discharge_declining_the_payment_deals_no_damage_but_keeps_the_energy():
    """CR 608.2d's choice is real: declining (paying 0) is always legal and is
    the unscripted default (`DecisionKind.PAY_ENERGY_AMOUNT`'s `default_answer`
    in `machines/decisions.py`), not an error and not the maximum. Trap: an
    engine that auto-paid whenever it was affordable would pass this test's
    happy-path sibling above and only fail here."""
    scenario = _galvanic_discharge_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    assert scenario.player("alice").energy == 3, "declining never spends the granted energy"
    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_galvanic_discharge_pays_a_partial_amount():
    """Paying 1 of the 3 available is a real choice distinct from both 0 and
    the maximum - not just a boolean "pay or don't"."""
    scenario = _galvanic_discharge_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_pay_energy_amount(1)

    scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    assert scenario.player("alice").energy == 2, "exactly 1 of the 3 granted energy is spent"
    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD, "1 damage does not kill a 2/2"


def test_galvanic_discharge_refuses_to_pay_more_energy_than_was_granted():
    """CR 118.3: a player cannot pay a cost without the resources to pay it
    fully. Three energy is all Galvanic Discharge grants, so a scripted
    answer of 4 is not a legal option - `Game.ask` raises naming CR 118.3
    rather than letting a player reach negative energy, and nothing is spent
    on the way to raising it (CR 118.3's all-or-nothing payment)."""
    import pytest

    scenario = _galvanic_discharge_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_pay_energy_amount(4)

    with pytest.raises(ValueError, match="CR 118.3"):
        scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    assert scenario.player("alice").energy == 3, "the illegal answer spent nothing"


# --------------------------------------------------------------------------
# Wrath of the Skies: "You get X {E} (energy counters), then you may pay any
# amount of {E}. Destroy each artifact, creature, and enchantment with mana
# value less than or equal to the amount of {E} paid this way."
# --------------------------------------------------------------------------


def _wrath_of_the_skies_board() -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Wrath of the Skies"], battlefield=["Plains"] * 4)
        .player("bob", battlefield=["Raging Goblin", "Grizzly Bears", "Hill Giant"])
    )


def test_wrath_of_the_skies_destroys_only_permanents_at_or_under_the_amount_paid():
    """X=2 grants 2 energy; paying all of it destroys Raging Goblin (mana
    value 1) and Grizzly Bears (mana value 2) but leaves Hill Giant (mana
    value 3) alone - the mana-value ceiling is the amount *paid*, not the X
    chosen or the energy granted, though here they are all equal."""
    scenario = _wrath_of_the_skies_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin, bears, giant = scenario.creatures(
        "Raging Goblin", "Grizzly Bears", "Hill Giant", username="bob"
    )
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.will_pay_energy_amount(2)

    casting = scenario.cast("Wrath of the Skies")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").energy == 0
    assert goblin.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD, "mana value 3 is over the amount paid"


def test_wrath_of_the_skies_paying_nothing_destroys_nothing():
    """Declining the variable payment is legal even though X energy was just
    granted for exactly this purpose - CR 608.2d's choice is not "why would
    you not". The engine must not treat "affordable and obviously good" as a
    reason to pay on the player's behalf."""
    scenario = _wrath_of_the_skies_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin, bears, giant = scenario.creatures(
        "Raging Goblin", "Grizzly Bears", "Hill Giant", username="bob"
    )
    plains = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    casting = scenario.cast("Wrath of the Skies")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.player("alice").energy == 2, "the unscripted default declines to pay"
    for permanent in (goblin, bears, giant):
        assert permanent.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# Static Prison: "At the beginning of your first main phase, sacrifice this
# enchantment unless you pay {E}."
#
# Static Prison's own ETB ("exile target nonland permanent ... until this
# enchantment leaves the battlefield. You get {E}{E}.") mixes a targeted
# clause with a duration this wave does not read - a pre-existing,
# out-of-scope gap `tests/test_effects.py::test_static_prisons_enters_
# trigger_does_not_parse_as_a_whole` already documents. Placed directly on
# the battlefield here instead of cast, with alice's energy staged by hand -
# the same kind of staging a rigged library is - so this file tests only the
# second ability, the one this wave actually builds.
# --------------------------------------------------------------------------


def _static_prison_board(energy: int) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Static Prison"])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    return scenario


def test_static_prison_survives_when_its_controller_pays_the_energy():
    """Paying the {E} averts the sacrifice (CR 107.14, CR 118.3)."""
    scenario = _static_prison_board(energy=1)
    prison = scenario.creature("Static Prison", "alice")
    scenario.start_at(Step.UPKEEP)
    scenario.will_pay_the_energy(True)

    walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").energy == 0
    assert prison.zone is Zone.BATTLEFIELD


def test_static_prison_is_sacrificed_when_its_controller_declines_to_pay():
    """Declining is always legal (CR 608.2d) even with the energy in hand -
    the same "optional is not mandatory" trap the variable-amount cards
    above test, on the fixed-amount shape instead."""
    scenario = _static_prison_board(energy=1)
    prison = scenario.creature("Static Prison", "alice")
    scenario.start_at(Step.UPKEEP)
    scenario.will_pay_the_energy(False)

    walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").energy == 1, "declining never spends the energy"
    assert prison.zone is Zone.GRAVEYARD


def test_static_prison_is_sacrificed_when_its_controller_cannot_pay():
    """CR 118.3: with 0 energy, "yes" is not a legal answer at all - the
    unscripted default (`default_answer` takes the affirmative only when
    `affirmative_is_legal`) correctly falls through to "no", and the
    enchantment is sacrificed exactly as if its controller had declined."""
    scenario = _static_prison_board(energy=0)
    prison = scenario.creature("Static Prison", "alice")
    scenario.start_at(Step.UPKEEP)

    walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").energy == 0
    assert prison.zone is Zone.GRAVEYARD


def test_static_prison_refuses_a_scripted_yes_it_cannot_afford():
    """CR 118.3/CR 608.2d together: a player with 0 energy cannot choose to
    pay {E}, even if a scenario scripts "yes" anyway. `Game.ask` raises
    rather than letting energy go negative."""
    import pytest

    scenario = _static_prison_board(energy=0)
    scenario.creature("Static Prison", "alice")
    scenario.start_at(Step.UPKEEP)
    scenario.will_pay_the_energy(True)

    with pytest.raises(ValueError, match="CR 608.2d"):
        walk_to(scenario, Step.PRECOMBAT_MAIN)

    assert scenario.player("alice").energy == 0


# --------------------------------------------------------------------------
# Guide of Souls: "Whenever you attack, you may pay {E}{E}{E}. When you do,
# put two +1/+1 counters and a flying counter on target attacking creature.
# It becomes an Angel in addition to its other types." - CR 603.12's
# reflexive trigger, out of scope for this wave.
# --------------------------------------------------------------------------


def test_guide_of_souls_records_a_notice_instead_of_resolving_silently():
    """The trigger fires and goes on the stack correctly (CR 508.3d) - only
    its *resolution* is unread. Both primitives it once lacked now exist (a
    reflexive trigger, built by a sibling wave against Grist, the Hunger
    Tide; a may-pay-a-cost decision, built by this wave - `may_pay_energy`
    already asks and pays exactly this fixed amount correctly, as
    `test_static_prison_survives_when_its_controller_pays_the_energy` above
    proves for the same call) but nothing yet connects a reflexive trigger to
    a non-sacrifice paid cost, so this still falls through to the general
    `ReflexiveClauseNotice` (CR 603.12) rather than resolving. Before either
    wave this resolved with no effect and no trace at all; alice's energy -
    untouched either way, since nothing here ever asks the question - is
    asserted directly so a future regression that *did* silently drain it
    would be caught."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Guide of Souls", "Raging Goblin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide, goblin = scenario.creatures("Guide of Souls", "Raging Goblin", username="alice")

    scenario.attack_with(guide, goblin)
    scenario.resolve_top()

    assert scenario.player("alice").energy == 0
    notices = scenario.game.reflexive_clause_notices
    assert len(notices) == 1
    notice = notices[0]
    assert isinstance(notice, ReflexiveClauseNotice)
    assert notice.source_name == "Guide of Souls"
    assert "when you do" in notice.text.lower()

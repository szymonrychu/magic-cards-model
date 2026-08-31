"""Counterspell shapes beyond the plain "Counter target spell." (CR 701.6a).

`test_stack.py` already covers the generic mechanics of countering - CR 608.2b's
fizzle recheck, a countered spell's own graveyard, a counterspell countered in
response - using Counterspell as its vehicle. This file is about the *other*
shapes a counterspell's own printed text can take, each read straight off
oracle text rather than a per-card registry row:

- a qualifier on the target ("Counter target noncreature spell." - Force of
  Negation)
- "Counter target spell unless its controller pays {N}." (CR 118.12a) - Censor,
  Mystical Dispute
- the CR 118.9 pitch alternative cost ("You may pay 1 life and exile a blue
  card from your hand rather than pay this spell's mana cost." - Force of
  Will; "If it's not your turn, you may exile a blue card ..." - Force of
  Negation)
- a rider computed from the countered spell itself (Access Denied's token
  count; Force of Negation's own exile-instead-of-graveyard redirect)
- a compound target across two different noun *kinds* (Consign to Memory's
  "target triggered ability or colorless spell" - an ability or a
  colour-restricted spell) and a redirect this engine refuses outright
  rather than half-apply (Delay's suspend redirect)

Every CR number here was looked up with `knowledge_search(type="rules")` in
this session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import SuspendRedirectNotice
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def board(alice_hand: list[str], *, bob_hand: list[str], bob_battlefield: list[str]) -> Scenario:
    """Alice holds the spell to counter; Bob holds the counterspell.

    Alice gets a generous mixed battlefield so `auto=True` can always pay
    for whichever spell a test hands her, whatever its colour.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=["Island", "Island", "Mountain", "Mountain", "Forest"],
        )
        .player("bob", hand=bob_hand, battlefield=bob_battlefield)
    )


# --------------------------------------------------------------------------
# A qualifier on the target: "Counter target noncreature spell."
# --------------------------------------------------------------------------


def test_force_of_negation_counters_a_noncreature_spell():
    """CR 701.6a's target restriction is read off the qualifier, not ignored.

    Force of Negation's own second sentence - "If that spell is countered
    this way, exile it instead of putting it into its owner's graveyard." -
    overrides CR 701.6a's default *unconditionally*, whether or not the
    pitch cost was the one paid for Force of Negation itself; the pitch-cost
    tests below exercise the alternative-cost half separately.
    """
    scenario = board(
        ["Lightning Bolt"],
        bob_hand=["Force of Negation"],
        bob_battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    scenario.cast_and_resolve("Force of Negation", *bob_islands, username="bob", targets=[bolt])

    assert bolt.zone is Zone.EXILE, "Force of Negation's own redirect, not the graveyard"
    assert scenario.stack_names() == []


def test_force_of_negation_cannot_target_a_creature_spell():
    """ "Noncreature" is CR 109.2b's own kind of restriction, read by
    `machines/targeting.py` off the card's own qualifier - Memnite is a
    creature spell, so the announcement is refused before it ever reaches
    resolution (CR 601.2c).
    """
    scenario = board(
        ["Memnite"],
        bob_hand=["Force of Negation"],
        bob_battlefield=["Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.cast_onto_stack("Memnite", username="alice", auto=True)
    scenario.pass_priority("alice")

    with pytest.raises(ValueError):
        scenario.cast("Force of Negation", username="bob").choose_targets([memnite])


# --------------------------------------------------------------------------
# "Counter target spell unless its controller pays {N}." (CR 118.12a)
# --------------------------------------------------------------------------


def censor_board() -> Scenario:
    return board(["Opt"], bob_hand=["Censor"], bob_battlefield=["Island", "Island"])


def test_censor_counters_the_spell_when_its_controller_cannot_pay():
    """CR 118.12a: "[Do something] unless [a player does something else]"
    means "[a player] may [do something else]. If [that player] doesn't,
    [effect]." Alice has no floating mana at all, so paying {1} is not a
    legal choice (`DecisionKind.PAY_MANA.affirmative_is_legal` is False) and
    the spell is countered without anybody being asked to decide anything.
    """
    scenario = censor_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Censor", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.GRAVEYARD
    asked = scenario.game.decisions.asked
    (decision,) = [q for q in asked if q.kind is DecisionKind.PAY_MANA]
    assert decision.affirmative_is_legal is False


def test_censor_is_countered_when_its_controller_can_pay_and_does():
    """The controller's own floating mana pays it - CR 608.2g lets a mana
    ability be activated right here, but this engine only reads mana already
    floating (see `Game.may_pay_mana`'s own docstring); staging it directly on
    the pool is the same kind of setup a rigged library already is.
    """
    scenario = censor_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 1)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(True, username="alice", source="Censor")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Censor", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.STACK, "paid, so Censor never countered it"
    assert alice.mana_pool.total == 0, "the {1} was actually spent"


def test_censor_still_counters_when_its_controller_can_pay_but_declines():
    """Paying is optional (CR 118.12a's "may"): a controller who could afford
    {1} is still allowed to let the spell be countered instead.
    """
    scenario = censor_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 1)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(False, username="alice", source="Censor")
    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Censor", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.GRAVEYARD
    assert alice.mana_pool.total == 1, "declined, so nothing was spent"


def test_mystical_dispute_reads_its_own_higher_amount():
    """Same shape as Censor, a different {N} - proof the amount is read off
    each card's own text rather than hardcoded to Censor's {1}.
    """
    scenario = board(
        ["Opt"], bob_hand=["Mystical Dispute"], bob_battlefield=["Island", "Island", "Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 2)  # one short of Mystical Dispute's {3}
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    scenario.cast_and_resolve("Mystical Dispute", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.GRAVEYARD, "two mana can't pay a {3} unless"
    (decision,) = [q for q in scenario.game.decisions.asked if q.source == "Mystical Dispute"]
    assert decision.amount == 3


def test_mystical_disputes_own_target_spell_restriction_is_enforced():
    """`targeting_profile` used to come back `understood=False` for the whole
    card: the leading cost-reduction sentence's verb "it targets" was fed to
    the same `_TARGET_WORD` scan as a real "target ..." noun phrase and
    failed to parse, which took the second sentence's genuine "target spell"
    requirement down with it - so *any* target, including a permanent, would
    have been silently accepted. `_SELF_COST_REDUCTION_LINE` strips the cost
    sentence before the scan now, so a permanent (not a spell on the stack at
    all, CR 109.2b) is refused as an illegal target."""
    scenario = board(
        [], bob_hand=["Mystical Dispute"], bob_battlefield=["Island", "Island", "Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Alice's own battlefield already carries a land (see `board`'s own
    # setup) - a permanent, not a spell on the stack, is exactly the illegal
    # target this fix now catches.
    island = scenario.find("Island", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.cast("Mystical Dispute", username="bob", targets=[island])


def test_censor_unless_pay_target_already_gone_does_nothing():
    """CR 608.2b: a target that has already left the stack fizzles the whole
    spell before the "unless" question is ever put to anyone.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt"], battlefield=["Island"])
        .player(
            "bob",
            hand=["Censor", "Counterspell"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources("Island", "Island", "Island", "Island", username="bob")
    censor = scenario.cast_onto_stack(
        "Censor", bob_islands[0], bob_islands[1], username="bob", targets=[opt]
    )
    scenario.cast_and_resolve(
        "Counterspell", bob_islands[2], bob_islands[3], username="bob", targets=[censor]
    )

    assert censor.zone is Zone.GRAVEYARD, "Counterspell got Censor first"
    assert not [q for q in scenario.game.decisions.asked if q.source == "Censor"]
    assert opt.zone is Zone.STACK, "Censor never got a turn to resolve at all"


# --------------------------------------------------------------------------
# The pitch alternative cost (CR 118.9): Force of Will and Force of Negation
# --------------------------------------------------------------------------


def test_force_of_will_pitches_life_and_a_blue_card():
    """CR 118.9: the printed mana cost is skipped entirely (CR 118.9c) in
    favour of "pay 1 life and exile a blue card from your hand".
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt"], battlefield=["Island"])
        .player("bob", hand=["Force of Will", "Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    opt = scenario.find("Opt", Zone.HAND, "bob")
    starting_life = bob.life

    (island,) = scenario.untapped_sources("Island", username="alice")
    bolt_stand_in = scenario.cast_onto_stack("Opt", island, username="alice", auto=True)
    scenario.pass_priority("alice")

    casting = scenario.cast("Force of Will", username="bob")
    casting.use_pitch_cost(choosing=[opt])
    casting.choose_targets([bolt_stand_in])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bolt_stand_in.zone is Zone.GRAVEYARD
    assert bob.life == starting_life - 1
    assert opt.zone is Zone.EXILE


def test_force_of_will_pitch_refuses_with_no_blue_card_to_exile():
    """The exile component still enforces CR 118.3: nothing blue in hand
    means the alternative cost simply cannot be paid.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt"], battlefield=["Island"])
        .player("bob", hand=["Force of Will", "Lightning Bolt"])  # red, not blue
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    target = scenario.cast_onto_stack("Opt", island, username="alice", auto=True)
    scenario.pass_priority("alice")

    casting = scenario.cast("Force of Will", username="bob")
    casting.use_pitch_cost(choosing=[])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        payment.pay()


def test_force_of_negation_pitch_cost_needs_it_to_be_someone_elses_turn():
    """ "If it's not your turn" is a real gate, not decoration: on the caster's
    own turn the option does not exist at all.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Force of Negation", "Opt"], battlefield=["Island"])
        .player("bob", hand=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice's own turn
    opt = scenario.find("Opt", Zone.HAND, "alice")
    casting = scenario.cast("Force of Negation", username="alice")

    with pytest.raises(ValueError):
        casting.use_pitch_cost(choosing=[opt])


def test_force_of_negation_pitch_cost_works_on_an_opponents_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", hand=["Force of Negation", "Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # alice is active; bob is not
    bob_opt = scenario.find("Opt", Zone.HAND, "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    target = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")

    casting = scenario.cast("Force of Negation", username="bob")
    casting.use_pitch_cost(choosing=[bob_opt])
    casting.choose_targets([target])
    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert target.zone is Zone.EXILE, "Force of Negation's own redirect, not the graveyard"
    assert bob_opt.zone is Zone.EXILE


# --------------------------------------------------------------------------
# A rider computed from the countered spell: Access Denied
# --------------------------------------------------------------------------


def test_access_denied_creates_a_thopter_per_mana_value_of_the_countered_spell():
    """ "Create X ... tokens ..., where X is that spell's mana value" - Sol
    Ring is mana value 1, so exactly one Thopter, not a fixed number.
    """
    scenario = board(
        ["Sol Ring"], bob_hand=["Access Denied"], bob_battlefield=["Island"] * 5
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources(*(["Island"] * 5), username="bob")
    scenario.cast_and_resolve("Access Denied", *bob_islands, username="bob", targets=[sol_ring])

    assert sol_ring.zone is Zone.GRAVEYARD
    thopters = [
        c for c in scenario.game.battlefield if c.name == "Thopter Token" and c.controller == "bob"
    ]
    assert len(thopters) == 1


def test_access_denied_scales_the_token_count_with_a_higher_mana_value():
    scenario = board(
        ["Karn, the Great Creator"], bob_hand=["Access Denied"], bob_battlefield=["Island"] * 5
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.cast_onto_stack("Karn, the Great Creator", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources(*(["Island"] * 5), username="bob")
    scenario.cast_and_resolve("Access Denied", *bob_islands, username="bob", targets=[karn])

    thopters = [
        c for c in scenario.game.battlefield if c.name == "Thopter Token" and c.controller == "bob"
    ]
    assert len(thopters) == 4


def test_access_denied_creates_nothing_when_the_target_is_already_gone():
    """CR 608.2b's fizzle recheck applies to the whole spell, so a target
    that left the stack first-in-first-out means no counter *and* no tokens -
    not a partial reading that pays out the rider anyway.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Opt"], battlefield=["Island"])
        .player(
            "bob",
            hand=["Access Denied", "Counterspell"],
            battlefield=["Island"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources(*(["Island"] * 7), username="bob")
    access_denied = scenario.cast_onto_stack(
        "Access Denied", *bob_islands[:5], username="bob", targets=[opt]
    )
    scenario.cast_and_resolve(
        "Counterspell", bob_islands[5], bob_islands[6], username="bob", targets=[access_denied]
    )

    assert access_denied.zone is Zone.GRAVEYARD, "Counterspell got it first"
    assert opt.zone is Zone.STACK, "Access Denied never got a turn to resolve at all"
    assert not [c for c in scenario.game.battlefield if c.name == "Thopter Token"]


# --------------------------------------------------------------------------
# A compound target across two noun kinds: Consign to Memory
#
# "Counter target triggered ability or colorless spell." used to come back
# `understood=False` for the whole compound - or worse, before that fix, a
# bare prefix match on the ability phrase silently claimed the entire target
# was "an ability" and dropped "or colorless spell" on the floor
# (`docs/engine-coverage.md`'s "A compound target this engine cannot fully
# read fails open rather than wrongly enforced" row). `_ABILITY_OR_COLOR_
# COUNT_SPELL_RE` now reads the genuine disjunction: one `TargetRequirement`
# with `allows_abilities=True` and `allows_cards=True`/`color_count=
# "colorless"` together, since `rejects` already dispatches an ability
# target to `_rejects_ability` and a card target to `_rejects_card` before
# either field is consulted, so the two halves never interfere.
# --------------------------------------------------------------------------


def test_consign_to_memory_counters_a_colorless_spell():
    """ "Counter target triggered ability or colorless spell." - Sol Ring has
    no colored mana symbols at all (CR 202.2b), so it is CR 105.2c's
    colorless and a legal target; the counter verb itself does not care
    which half of the "or" was targeted (see `counter_targets`'s own
    docstring)."""
    scenario = board(
        ["Sol Ring"], bob_hand=["Consign to Memory"], bob_battlefield=["Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)
    scenario.pass_priority("alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.cast_and_resolve("Consign to Memory", island, username="bob", targets=[sol_ring])

    assert sol_ring.zone is Zone.GRAVEYARD


def test_consign_to_memory_cannot_target_a_colored_spell():
    """The other direction: Lightning Bolt is red, not colorless (CR 105.2c
    is "no color at all"), so it is not a legal target for the "colorless
    spell" half - the whole announcement is refused (CR 601.2c)."""
    scenario = board(
        ["Lightning Bolt"], bob_hand=["Consign to Memory"], bob_battlefield=["Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Consign to Memory", island, username="bob", targets=[bolt])


def test_consign_to_memory_can_target_a_triggered_ability():
    """The other noun kind in the compound: a triggered ability on the stack
    (CR 113.1c) is a legal target for the "triggered ability" half, the same
    way Repudiate's "activated or triggered ability" already reaches one
    (`test_countering_an_ability.py`)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            hand=["Solemn Simulacrum"],
            battlefield=["Forest"] * 4,
        )
        .player("bob", hand=["Consign to Memory"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)
    scenario.cast_onto_stack("Solemn Simulacrum", *sources, username="alice")
    scenario.pass_until_resolved()
    assert scenario.stack_names() == ["Solemn Simulacrum's triggered ability"]
    trigger = scenario.game.stack[-1]
    scenario.pass_priority("alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.cast_and_resolve("Consign to Memory", island, username="bob", targets=[trigger])

    assert scenario.stack_names() == [], "the trigger was countered rather than resolving"


# --------------------------------------------------------------------------
# A redirect this engine refuses outright: Delay's suspend rider
# --------------------------------------------------------------------------


def test_delay_fails_closed_with_a_notice_instead_of_half_applying():
    """CR 702.62a's suspend is not built anywhere in this engine (`docs/
    engine-coverage.md`), and countering the spell while dropping "it gains
    suspend" on the floor would leave a spell exiled with no way back when the
    card says it eventually has one - the forbidden "looks right, isn't"
    shape. So the whole paragraph does nothing at all, and records why.
    """
    scenario = board(["Opt"], bob_hand=["Delay"], bob_battlefield=["Island", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    bob_islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_and_resolve("Delay", *bob_islands, username="bob", targets=[opt])

    assert opt.zone is Zone.STACK, "Delay never actually countered it"
    (notice,) = scenario.game.suspend_redirect_notices
    assert isinstance(notice, SuspendRedirectNotice)
    assert notice.source_name == "Delay"


# --------------------------------------------------------------------------
# The amount is {X}: "Counter target spell unless its controller pays {X}."
# --------------------------------------------------------------------------


def syncopate_board() -> Scenario:
    """Bob holds Syncopate and four Islands - enough for {X}{U} at X up to 3."""
    return board(
        ["Opt"],
        bob_hand=["Syncopate"],
        bob_battlefield=["Island", "Island", "Island", "Island"],
    )


def cast_syncopate(scenario, target, x_value: int):
    """Announce Syncopate with X (CR 601.2b), pay {X}{U}, and resolve it.

    CR 107.3a: X has no value until the caster announces one, and that value
    holds "while that spell ... is on the stack" - so the amount the targeted
    spell's controller is asked for on resolution is this X, not zero.
    """
    casting = scenario.cast("Syncopate", username="bob", targets=[target])
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    islands = scenario.untapped_sources(*(["Island"] * (x_value + 1)), username="bob")
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_syncopate_counters_and_exiles_when_x_cannot_be_paid():
    """CR 118.12a's "unless" question is put for the announced X, and
    Syncopate's own second sentence replaces CR 701.6a's graveyard with
    exile. Alice has no floating mana, so paying {2} is not a legal choice.
    """
    scenario = syncopate_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    cast_syncopate(scenario, opt, 2)

    assert opt.zone is Zone.EXILE, "Syncopate exiles instead of binning (CR 701.6a overridden)"
    (decision,) = [q for q in scenario.game.decisions.asked if q.source == "Syncopate"]
    assert decision.amount == 2, "the announced X, not the printed {X}"
    assert decision.affirmative_is_legal is False


def test_syncopate_does_not_counter_when_x_is_paid():
    """The controller of the targeted spell pays the announced X and keeps it
    (CR 118.12a's "[a player] may [do something else]").
    """
    scenario = syncopate_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    alice.mana_pool.add(Color.COLORLESS, 2)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(True, username="alice", source="Syncopate")
    cast_syncopate(scenario, opt, 2)

    assert opt.zone is Zone.STACK, "paid, so Syncopate never countered it"
    assert alice.mana_pool.total == 0, "the {2} was actually spent"


def test_syncopate_at_x_zero_asks_for_a_payment_anyone_can_make():
    """CR 118.3a: "Players can always pay 0 mana." At X=0 the "unless" is a
    question with a legal affirmative answer for a player with an empty pool,
    so the spell survives - X=0 is not the same as no question at all.
    """
    scenario = syncopate_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    cast_syncopate(scenario, opt, 0)

    (decision,) = [q for q in scenario.game.decisions.asked if q.source == "Syncopate"]
    assert decision.amount == 0
    assert decision.affirmative_is_legal is True
    assert opt.zone is Zone.STACK, "an empty pool still pays {0}"


def test_syncopate_at_x_zero_still_exiles_a_controller_who_declines():
    """Paying is optional even at {0} (CR 118.12a's "may"), and declining
    takes Syncopate's own exile rider with it.
    """
    scenario = syncopate_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.cast_onto_stack("Opt", username="alice", auto=True)
    scenario.pass_priority("alice")

    scenario.will_pay_the_mana_cost(False, username="alice", source="Syncopate")
    cast_syncopate(scenario, opt, 0)

    assert opt.zone is Zone.EXILE

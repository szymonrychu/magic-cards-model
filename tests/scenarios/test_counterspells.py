"""Counterspell shapes beyond the plain "Counter target spell." (CR 701.5a).

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
- a compound target this engine cannot fully read (Consign to Memory's
  "target triggered ability or colorless spell") and a redirect this engine
  refuses outright rather than half-apply (Delay's suspend redirect)

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
    """CR 701.5a's target restriction is read off the qualifier, not ignored.

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
# A compound target this engine cannot fully read: Consign to Memory
# --------------------------------------------------------------------------


def test_consign_to_memory_counters_a_colorless_spell():
    """ "Counter target triggered ability or colorless spell." - the counter
    verb itself does not care which half of the "or" was targeted (see
    `counter_targets`'s own docstring), so a colorless spell is still
    countered even though the "colorless"/"ability" restriction is not
    enforced at announcement (CR 115's own legality check) - see
    `docs/engine-coverage.md` for that gap.
    """
    scenario = board(
        ["Sol Ring"], bob_hand=["Consign to Memory"], bob_battlefield=["Island"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.cast_onto_stack("Sol Ring", username="alice", auto=True)
    scenario.pass_priority("alice")

    (island,) = scenario.untapped_sources("Island", username="bob")
    scenario.cast_and_resolve("Consign to Memory", island, username="bob", targets=[sol_ring])

    assert sol_ring.zone is Zone.GRAVEYARD


@pytest.mark.xfail(
    reason=(
        "Consign to Memory's own targeting restriction ('triggered ability or "
        "colorless spell') is not enforced: machines/targeting.py reports "
        "understood=False for the compound rather than a wrong one (see the "
        "fix to _ABILITY_PHRASE's matching), so CR 115 legality is simply not "
        "checked, and a spell-side announcement has no path to choose an "
        "ability as a target at all yet (docs/engine-coverage.md)."
    )
)
def test_consign_to_memory_can_target_a_triggered_ability():
    raise NotImplementedError


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

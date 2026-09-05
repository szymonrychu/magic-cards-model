"""Flashback: casting a card out of the graveyard (CR 702.34a).

CR 702.34a: "Flashback appears on some instants and sorceries. It represents two
static abilities: one that functions while the card is in a player's graveyard
and another that functions while the card is on the stack."

The graveyard half is *permission*, not a discount - CR 601.3 says a player can
begin to cast a spell only if a rule or effect allows it, and for a card in a
graveyard nothing otherwise does. The flashback cost is then an alternative cost
under CR 118.9, paid rather than the mana cost.

Both printed forms are in the pool: Faithless Looting's `Flashback {2}{R}` and
Lava Dart's `Flashback—Sacrifice a Mountain.`, which is the em-dash form.

The stack half - "Then exile it" - is a replacement applied as the spell
resolves, and lands in the xfail at the bottom.

**A live-game defect, closed here**: `why_cannot_cast_from` answers CR 601.3's
existence question - "could *anything* allow this cast from here" - which is
right for what it is, but nothing downstream ever asked the *second*
question CR 601.2b/CR 118.9a require: did the announcement actually *claim*
one of those options. A caster who cast Faithful Mending (mana cost `{W}{U}`,
Flashback `{1}{W}{U}`) from the graveyard **without ever announcing
Flashback** got it on the stack anyway, `Casting.keyword_used` stayed `None`,
`total_cost` fell back to the printed `{W}{U}`, and `CastRecord.keyword`
stayed `None` too - so `machines/replacement.py`'s "if the flashback cost was
paid, exile this card" never fired and the card went back to the graveyard,
castable for `{W}{U}` forever. `test_casting_it_from_the_graveyard_without_
announcing_flashback_is_refused` below through `test_the_loop_is_closed_the_
card_cannot_be_recast_for_the_face_cost` are that report, made concrete.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options, why_cannot_cast_from
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    return Scenario().manual_turn_based_actions().player("alice", **kwargs).player("bob")


# -- what the keyword offers ------------------------------------------------


def test_flashback_offers_a_cast_from_the_graveyard():
    (option,) = keyword_cast_options(card("Faithless Looting"))

    assert option.zone is Zone.GRAVEYARD
    assert option.pays_mana_cost is False
    assert str(option.cost) == "{2}{R}"


def test_the_em_dash_form_reads_as_a_sacrifice_and_not_as_mana():
    """Lava Dart's flashback cost is a Mountain, not a mana symbol."""
    (option,) = keyword_cast_options(card("Lava Dart"))

    assert option.zone is Zone.GRAVEYARD
    assert str(option.cost) == "Sacrifice a Mountain"


# -- casting it -------------------------------------------------------------


def test_a_card_with_flashback_is_cast_out_of_the_graveyard():
    scenario = board(graveyard=["Faithless Looting"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    looting = scenario.put_on_stack(casting)

    assert looting.zone is Zone.STACK
    assert looting not in scenario.player("alice").graveyard


def test_the_em_dash_flashback_cost_sacrifices_the_named_land():
    """CR 601.2h: the Mountain is sacrificed as the total cost is paid."""
    scenario = board(graveyard=["Lava Dart"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Lava Dart", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback", choosing=[mountain])
    casting.begin_paying().pay()

    assert mountain.zone is Zone.GRAVEYARD
    assert casting.total_cost.mana == ManaCost()


def test_the_wrong_land_cannot_pay_a_sacrifice_a_mountain_cost():
    """CR 118.3: the cost names a Mountain, and a Forest is not one."""
    scenario = board(graveyard=["Lava Dart"], battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (forest,) = scenario.untapped_sources("Forest")
    casting = scenario.cast("Lava Dart", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback", choosing=[forest])

    with pytest.raises(ValueError, match="not a Mountain"):
        casting.begin_paying().pay()
    assert forest.zone is Zone.BATTLEFIELD


def test_a_flashback_cost_that_cannot_be_paid_leaves_the_card_in_the_graveyard():
    """CR 733.1: cancelling rewinds the whole announcement."""
    scenario = board(graveyard=["Faithless Looting"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    payment = casting.begin_paying()
    payment.tap_for_mana(mountain, [Color.RED])

    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()

    casting.cancel()
    assert scenario.find("Faithless Looting", Zone.GRAVEYARD).zone is Zone.GRAVEYARD
    assert mountain.untapped


# -- permission, and what has none ------------------------------------------


def test_a_card_without_flashback_cannot_be_cast_from_the_graveyard():
    """CR 601.3: nothing allows it, so it may not begin to be cast."""
    scenario = board(graveyard=["Lightning Bolt"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD)
    reason = why_cannot_cast_from(bolt, "alice", Zone.GRAVEYARD, scenario.game)

    assert reason is not None
    assert "CR 601.3" in reason


def test_a_card_in_hand_needs_no_permission():
    """CR 302.1: the hand is where the rules cast from by default."""
    scenario = board(hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bolt = scenario.find("Lightning Bolt", Zone.HAND)

    assert why_cannot_cast_from(bolt, "alice", Zone.HAND, scenario.game) is None


def test_flashback_cannot_be_used_on_a_card_still_in_hand():
    """The graveyard half functions in the graveyard, and nowhere else."""
    scenario = board(hand=["Faithless Looting"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Faithless Looting")

    with pytest.raises(ValueError, match="from the graveyard"):
        casting.use_keyword("Flashback")


def test_casting_it_normally_from_hand_still_costs_its_mana_cost():
    """Flashback adds an option; it does not take the printed one away."""
    scenario = board(hand=["Faithless Looting"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    casting = scenario.cast("Faithless Looting")

    assert casting.total_cost.mana == ManaCost.parse("{R}")
    scenario.pay_with(casting.begin_paying(), mountain)
    assert scenario.put_on_stack(casting).zone is Zone.STACK


# -- the live-game defect: casting from the graveyard without a claim ------


def _faithful_mending_board() -> Scenario:
    """alice, three lands - enough for `{W}{U}` and NOT for `{1}{W}{U}` - is
    what makes the undercharge visible: a three-land board can legally pay
    Faithful Mending's face cost but not its Flashback cost."""
    return board(graveyard=["Faithful Mending"], battlefield=["Plains", "Island", "Island"])


def test_casting_it_from_the_graveyard_without_announcing_flashback_is_refused():
    """The live-game report itself: a caster who taps the lands and pays
    Faithful Mending's `{W}{U}` face cost from the graveyard, without ever
    announcing Flashback, must be refused - `KeywordCastOption`'s mere
    *existence* for this zone is not CR 601.2b's announced choice. CR 601.6/
    CR 733.1: the whole cast is reversed, including the payment, so the card
    stays in the graveyard and the lands used to pay for it come back
    untapped.
    """
    scenario = _faithful_mending_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains, island, _ = scenario.untapped_sources("Plains", "Island", "Island")

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    scenario.pay_with(casting.begin_paying(), plains, island)

    with pytest.raises(ValueError, match="Flashback") as excinfo:
        casting.cast()
    assert "CR 702.34a" in str(excinfo.value)
    casting.cancel()

    assert scenario.find("Faithful Mending", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert plains.untapped
    assert island.untapped


def test_announcing_flashback_charges_the_flashback_cost_not_the_face_cost():
    """This is the assertion that would have caught the report: once
    Flashback is actually announced, the cost is the printed Flashback
    `{1}{W}{U}` (mana value 3), not the face cost `{W}{U}` (mana value 2) the
    buggy engine charged - so the two lands that used to be enough for the
    face cost (the undercharge itself) fall one mana short of the real one.
    """
    scenario = _faithful_mending_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains, island, _ = scenario.untapped_sources("Plains", "Island", "Island")

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")

    assert str(casting.total_cost.mana) == "{1}{W}{U}"
    payment = casting.begin_paying()
    payment.tap_for_mana(plains, [Color.WHITE])
    payment.tap_for_mana(island, [Color.BLUE])
    with pytest.raises(ValueError, match="cannot pay"):
        payment.pay()


def test_the_announced_flashback_cast_resolves_and_is_exiled():
    """With a fourth land, the announced Flashback cast can actually be paid,
    resolves, and CR 702.34a's second half exiles it - and the cast record
    says why."""
    scenario = board(
        graveyard=["Faithful Mending"],
        battlefield=["Plains", "Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Island", "Island", "Island")

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    mending = scenario.resolve_top()

    assert mending.zone is Zone.EXILE


def test_the_loop_is_closed_the_card_cannot_be_recast_for_the_face_cost():
    """The report's own loop: after the flashback cast resolves and the card
    is exiled, it is not in the graveyard any more and cannot be cast again
    from there for its face cost - or at all, since nothing gives exile a
    permission for it."""
    scenario = board(
        graveyard=["Faithful Mending"],
        battlefield=["Plains", "Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Island", "Island", "Island")

    casting = scenario.cast("Faithful Mending", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    mending = scenario.resolve_top()

    assert mending not in scenario.player("alice").graveyard
    assert why_cannot_cast_from(mending, "alice", Zone.EXILE, scenario.game) is not None


# -- the half that is not modelled ------------------------------------------


def test_a_flashed_back_spell_is_exiled_instead_of_going_to_the_graveyard():
    scenario = board(graveyard=["Faithless Looting"], battlefield=["Mountain"] * 3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    casting = scenario.cast("Faithless Looting", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    looting = scenario.resolve_top()

    assert looting.zone is Zone.EXILE

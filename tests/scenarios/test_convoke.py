"""Convoke: tapping creatures instead of spending mana (CR 702.51).

CR 702.51a: "Convoke is a static ability that functions while the spell with
convoke is on the stack. 'Convoke' means 'For each colored mana in this spell's
total cost, you may tap an untapped creature of that color rather than pay that
mana. For each generic mana in this spell's total cost, you may tap an untapped
creature rather than pay that mana.'" Conclave Tribunal prints the same thing
as reminder text: "Each creature you tap while casting this spell pays for {1}
or one mana of that creature's color."

CR 702.51b is the corner case that shapes the implementation: "The convoke
ability isn't an additional or alternative cost and applies only after the
total cost of the spell with convoke is determined." So convoke never touches
what the spell *costs* - only which resource pays one symbol of it - and the
engine applies it to an already-open `CostPayment`.

CR 702.51c names the creatures that did it ("convoked"), and CR 702.51d makes
multiple instances redundant.

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import transform_permanent
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def board(*battlefield: str) -> Scenario:
    """Conclave Tribunal is `{3}{W}` with convoke - three generic symbols and
    one coloured one, which is exactly the split CR 702.51a draws."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Conclave Tribunal"], battlefield=list(battlefield))
        .player("bob", battlefield=["Grizzly Bears"])
    )


def four_creatures() -> Scenario:
    return board(
        "Savannah Lions",
        "Savannah Lions",
        "Grizzly Bears",
        "Grizzly Bears",
    )


def test_four_creatures_convoke_the_whole_cost():
    """Two white 2/1s and two green 2/2s cover `{3}{W}`: the white one pays the
    `{W}` and the other three each pay one generic."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures("Savannah Lions", "Savannah Lions", username="alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)
    convoke(payment, casting.spell, lions[1])
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])

    assert payment.mana_owed.converted == 0
    payment.pay()
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert all(creature.tapped for creature in [*lions, *bears])


def test_convoke_is_not_a_cost_reduction():
    """CR 702.51b: the total cost is still `{3}{W}` - convoke only changes what
    pays one of its symbols. Anything asking what the spell cost gets the real
    number, which is why `mana_owed` is a separate reading from `cost`."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])

    assert str(payment.cost) == "{3}{W}"
    assert str(payment.mana_owed) == "{1}{W}"


def test_a_creature_of_the_right_colour_pays_the_coloured_symbol():
    """CR 702.51a: "you may tap an untapped creature **of that color**"."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lion = scenario.creatures("Savannah Lions", username="alice")[0]

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lion, Color.WHITE)

    assert str(payment.mana_owed) == "{3}"


def test_a_creature_of_the_wrong_colour_cannot_pay_the_coloured_symbol():
    """A green bear is not "a creature of that color" for `{W}`."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creatures("Grizzly Bears", username="alice")[0]

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="cannot pay"):
        convoke(payment, casting.spell, bear, Color.WHITE)

    assert str(payment.mana_owed) == "{3}{W}"
    assert not bear.tapped


def test_a_creature_of_the_wrong_colour_still_pays_a_generic_symbol():
    """The generic half of CR 702.51a asks nothing about colour: "For each
    generic mana in this spell's total cost, you may tap an untapped creature"
    - full stop."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creatures("Grizzly Bears", username="alice")[0]

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bear)

    assert str(payment.mana_owed) == "{2}{W}"


def test_a_creature_that_entered_this_turn_can_convoke():
    """CR 302.6/CR 602.5a restrict a creature's own activated ability with `{T}`
    in its cost. Convoke has no `{T}` symbol and is the *spell's* static
    ability, so a summoning-sick creature convokes."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Conclave Tribunal", "Serra Angel"],
            battlefield=["Plains"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 5)
    angel = scenario.cast_and_resolve("Serra Angel", *sources)
    assert angel.is_summoning_sick(scenario.game)

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, angel, Color.WHITE)

    assert str(payment.mana_owed) == "{3}"
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 3))
    assert angel.tapped


def test_an_already_tapped_creature_cannot_convoke():
    """ "an **untapped** creature" (CR 702.51a). A creature that attacked this
    turn is no help."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creatures("Grizzly Bears", username="alice")[0]
    bear.tap()

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="already tapped"):
        convoke(payment, casting.spell, bear)


def test_an_opponents_creature_cannot_convoke():
    """The reminder text says "**Your** creatures can help cast this spell"."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not control"):
        convoke(payment, casting.spell, theirs)

    assert not theirs.tapped


def test_a_noncreature_permanent_cannot_convoke():
    """Convoke taps creatures. A Plains is a mana source, not a convoker - and
    the distinction matters, because improvise (CR 702.126a) is the keyword
    that taps artifacts and Conclave Tribunal does not have it."""
    scenario = board("Plains").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="not a creature"):
        convoke(payment, casting.spell, plains)


def test_the_same_creature_cannot_convoke_twice():
    """One creature, one untap, one symbol."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creatures("Grizzly Bears", username="alice")[0]

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bear)

    with pytest.raises(ValueError, match="already paying"):
        convoke(payment, casting.spell, bear)


def test_more_creatures_than_the_cost_has_symbols_is_refused():
    """CR 702.51a bounds itself to "each colored mana **in this spell's total
    cost**" and "each generic mana in this spell's total cost". A fifth creature
    offered to a `{3}{W}` has nothing left to pay, so it is turned away rather
    than tapped for nothing."""
    scenario = board(
        "Savannah Lions",
        "Savannah Lions",
        "Savannah Lions",
        "Grizzly Bears",
        "Grizzly Bears",
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures(
        "Savannah Lions", "Savannah Lions", "Savannah Lions", username="alice"
    )
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)
    for creature in (lions[1], lions[2], bears[0]):
        convoke(payment, casting.spell, creature)

    with pytest.raises(ValueError, match="has no"):
        convoke(payment, casting.spell, bears[1])

    assert not bears[1].tapped


def test_a_second_white_symbol_is_not_there_to_convoke():
    """Only one `{W}` is printed, so only one creature may convoke for white -
    the second is refused even though the cost still has generic mana left,
    because it was offered against a colour the cost no longer holds."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures("Savannah Lions", "Savannah Lions", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)

    with pytest.raises(ValueError, match="has no"):
        convoke(payment, casting.spell, lions[1], Color.WHITE)


def test_convoke_mixes_with_real_mana():
    """Nothing says a convoked spell must be wholly convoked: the untapped
    Plains pays the `{W}` and two bears pay two of the three generic."""
    scenario = board("Plains", "Plains", "Grizzly Bears", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    plains = scenario.untapped_sources("Plains", "Plains", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])

    assert str(payment.mana_owed) == "{1}{W}"
    scenario.pay_with(payment, *plains)
    scenario.put_on_stack(casting)

    assert all(source.tapped for source in [*bears, *plains])


def test_cancelling_the_cast_untaps_the_convoked_creatures():
    """CR 733.1: "the entire action is reversed and any payments already made
    are canceled". A cast that falls over gives the creatures back untapped."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures("Savannah Lions", "Savannah Lions", username="alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)
    convoke(payment, casting.spell, lions[1])
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])
    payment.pay()
    assert all(creature.tapped for creature in [*lions, *bears])

    casting.cancel()

    assert not any(creature.tapped for creature in [*lions, *bears])
    assert scenario.find("Conclave Tribunal", Zone.HAND, "alice") is casting.spell


def test_nothing_is_tapped_until_the_cost_is_paid():
    """CR 601.2h pays the total cost; CR 702.51a's tapping is part of paying
    it, not part of announcing. A payment left open has tapped nothing."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])

    assert not any(bear.tapped for bear in bears)


def test_a_spell_without_convoke_refuses_the_offer():
    """CR 702.51a functions "while the spell **with convoke**" is on the stack."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Grizzly Bears", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not have convoke"):
        convoke(payment, casting.spell, bear)


def test_a_convoked_creature_still_produced_no_mana():
    """CR 702.51a says "rather than pay that mana", so nothing was added to the
    pool and nothing floats afterwards - a convoked creature is not a mana
    source and `mana_from` is never consulted for one."""
    scenario = four_creatures().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures("Savannah Lions", "Savannah Lions", username="alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Conclave Tribunal")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)
    convoke(payment, casting.spell, lions[1])
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])
    payment.pay()

    assert payment.tapped_for_mana == []
    assert scenario.player("alice").mana_pool.is_empty


# -- Granted convoke: "`<quality>` spells you cast have convoke." -----------------


def test_caetus_grants_convoke_to_a_noncreature_spell():
    """Invasion of Segovia // Caetus, Sea Tyrant of Segovia's "Noncreature
    spells you cast have convoke." - `has_convoke_now`'s own granted-convoke
    branch, read off the battlefield the same "continuous, never locked in"
    way any other static ability is (CR 611.3a). Sol Ring is `{1}`, an
    artifact (a noncreature spell), so any untapped creature covers its
    whole cost."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sol Ring"], battlefield=["Invasion of Segovia", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    caetus = scenario.creature("Invasion of Segovia", "alice")
    transform_permanent(scenario.game, caetus)
    assert caetus.name == "Caetus, Sea Tyrant of Segovia"
    bear = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Sol Ring")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, bear)

    assert str(payment.mana_owed) == ""
    payment.pay()
    spell = scenario.put_on_stack(casting)

    assert spell.zone is Zone.STACK
    assert bear.tapped


def test_caetus_does_not_grant_convoke_to_a_creature_spell():
    """ "Noncreature spells" excludes a creature spell (CR 205.2a) - Grizzly
    Bears itself gets no convoke from Caetus."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Invasion of Segovia", "Savannah Lions"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    caetus = scenario.creature("Invasion of Segovia", "alice")
    transform_permanent(scenario.game, caetus)
    lion = scenario.creature("Savannah Lions", "alice")

    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="does not have convoke"):
        convoke(payment, casting.spell, lion)


def test_eirdu_off_pool_proof_grants_convoke_to_a_creature_spell():
    """Eirdu, Carrier of Dawn's own "Creature spells you cast have convoke." -
    a real printing this engine already carried before this session, proving
    the same grant reader generally rather than only for the reported battle
    card: the opposite quality (creature, not noncreature) on an unrelated
    card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Eirdu, Carrier of Dawn", "Savannah Lions"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lion = scenario.creature("Savannah Lions", "alice")

    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lion)

    # {1}{G}: the lion (white, not green) covers only the generic symbol -
    # CR 702.51a's colour restriction still applies to a granted convoke the
    # same as a printed one, and the accepted offer (no `ValueError`) is
    # already proof this quality is genuinely read for a creature spell.
    assert str(payment.mana_owed) == "{G}"
    assert not lion.tapped  # CR 601.2h: not tapped until the payment is paid.

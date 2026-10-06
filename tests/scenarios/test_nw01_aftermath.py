"""Scenario: Aftermath (CR 702.127a) on split cards (CR 709.3).

CR 702.127a, read in full with `mise run rules:find 702.127a`: "Aftermath is
an ability found on some split cards (see rule 709, "Split Cards"). It
represents three static abilities. "Aftermath" means "You may cast this half
of this split card from your graveyard," "This half of this split card can't
be cast from any zone other than a graveyard," and "If this spell was cast
from a graveyard, exile it instead of putting it anywhere else any time it
would leave the stack.""

CR 709.3 - "A player chooses which half of a split card they are casting
before putting it onto the stack." CR 709.3a - "Only the chosen half is
evaluated to see if it can be cast." CR 709.3b - "While on the stack, only the
characteristics of the half being cast exist."

Printings: Insult // Injury (the listed card: Injury deals damage), and three
proof printings whose aftermath half differs in shape - Claim // Fame (a pump
on a target creature) and Start // Finish (an Instant // Sorcery split with an
additional sacrifice cost on the aftermath half).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import card_support, executed_keywords
from tests.cards import card

from .harness import Scenario


def _board(*, hand=(), graveyard=(), battlefield=(), bob_battlefield=("Grizzly Bears",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            graveyard=list(graveyard),
            battlefield=list(battlefield),
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_half(scenario, name, face, zone, sources, targets=None, sacrificing=None):
    casting = scenario.cast(name, from_zone=zone, sacrificing=sacrificing)
    if zone is Zone.GRAVEYARD:
        casting.use_keyword("Aftermath")
    casting.cast_as_split_half(face)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    return scenario.put_on_stack(casting)


# -- the keyword is executed --------------------------------------------------


@pytest.mark.parametrize("name", ["Insult // Injury", "Claim // Fame", "Start // Finish"])
def test_aftermath_is_an_executed_keyword(name):
    assert "aftermath" in executed_keywords(card(name))
    aftermath = [c for c in card_support(card(name)).clauses if c.text.startswith("Aftermath")]
    assert aftermath
    assert {c.outcome for c in aftermath} == {"handled"}


# -- the aftermath half: graveyard only ---------------------------------------


def test_injury_is_cast_from_the_graveyard_and_then_exiled():
    scenario = _board(graveyard=["Insult // Injury"], battlefield=["Mountain"] * 3)
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = scenario.untapped_sources(*["Mountain"] * 3)

    spell = _cast_half(
        scenario, "Insult", "Injury", Zone.GRAVEYARD, mountains, targets=[bears, "bob"]
    )
    assert spell.zone is Zone.STACK
    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD
    injury = scenario.find("Insult", Zone.EXILE, "alice")
    assert injury.zone is Zone.EXILE, "CR 702.127a: exiled instead of the graveyard"


def test_injury_cannot_be_cast_from_hand():
    scenario = _board(hand=["Insult // Injury"], battlefield=["Mountain"] * 3)

    casting = scenario.cast("Insult")
    with pytest.raises(ValueError, match="CR 702.127a"):
        casting.cast_as_split_half("Injury")


def test_injury_cannot_be_named_at_construction_from_hand():
    from magic_cards_model.machines.casting import Casting

    scenario = _board(hand=["Insult // Injury"], battlefield=["Mountain"] * 3)
    spell = scenario.find("Insult", Zone.HAND, "alice")
    with pytest.raises(ValueError, match="CR 702.127a"):
        Casting(
            spell=spell, caster="alice", origin_zone=Zone.HAND, game=scenario.game, face="Injury"
        )
    assert spell.zone is Zone.HAND


def test_insult_cannot_be_cast_from_the_graveyard_with_aftermath():
    scenario = _board(graveyard=["Insult // Injury"], battlefield=["Mountain"] * 3)

    casting = scenario.cast("Insult", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Aftermath")
    with pytest.raises(ValueError, match="CR 702.127a"):
        casting.cast_as_split_half("Insult")


def test_insult_from_graveyard_without_naming_a_half_is_refused():
    scenario = _board(graveyard=["Insult // Injury"], battlefield=["Mountain"] * 3)
    mountains = scenario.untapped_sources(*["Mountain"] * 3)

    casting = scenario.cast("Insult", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Aftermath")
    with pytest.raises(ValueError, match="CR 702.127a"):
        payment = casting.begin_paying()
        scenario.pay_with(payment, *mountains)
        casting.cast()


def test_insult_cast_from_hand_goes_to_the_graveyard():
    """The other half has no aftermath of its own: cast from hand, it is put
    into the graveyard as usual (CR 608.2n), where Injury can later be cast."""
    scenario = _board(hand=["Insult // Injury"], battlefield=["Mountain"] * 3)
    mountains = scenario.untapped_sources(*["Mountain"] * 3)

    _cast_half(scenario, "Insult", "Insult", Zone.HAND, mountains)
    scenario.resolve_top()

    assert scenario.find("Insult", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_a_countered_aftermath_spell_is_exiled_too():
    """ "any time it would leave the stack" - countered is leaving it too."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Insult // Injury"],
            battlefield=["Mountain"] * 3,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=["Counterspell"],
            battlefield=["Island", "Island", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = _cast_half(
        scenario,
        "Insult",
        "Injury",
        Zone.GRAVEYARD,
        scenario.untapped_sources(*["Mountain"] * 3),
        targets=[bears, "bob"],
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[spell],
    )

    assert spell.zone is Zone.EXILE
    assert scenario.player("bob").life == 20


def test_legal_actions_offer_only_the_aftermath_half_from_the_graveyard():
    scenario = _board(graveyard=["Insult // Injury"], battlefield=["Mountain"] * 3)

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.CAST and action.from_zone is Zone.GRAVEYARD
    }
    assert faces == {"Injury"}


def test_legal_actions_offer_only_the_other_half_from_hand():
    scenario = _board(hand=["Insult // Injury"], battlefield=["Mountain"] * 3)

    faces = {
        action.spell_face
        for action in scenario.game.legal_actions("alice")
        if action.kind is ActionKind.CAST
    }
    assert faces == {"Insult"}


# -- generality: other printings ----------------------------------------------


def test_fame_pumps_and_grants_haste_then_is_exiled():
    scenario = _board(
        graveyard=["Claim // Fame"],
        battlefield=["Mountain", "Mountain", "Grizzly Bears"],
        bob_battlefield=(),
    )
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_half(
        scenario,
        "Claim",
        "Fame",
        Zone.GRAVEYARD,
        scenario.untapped_sources("Mountain", "Mountain"),
        targets=[bears],
    )
    scenario.resolve_top()

    assert scenario.game.power_of(bears) == 4
    assert scenario.find("Claim", Zone.EXILE, "alice").zone is Zone.EXILE


def test_claim_is_cast_from_hand_and_fame_is_not_castable_from_hand():
    scenario = _board(
        hand=["Claim // Fame"],
        graveyard=["Grizzly Bears"],
        battlefield=["Swamp"],
        bob_battlefield=(),
    )
    with pytest.raises(ValueError, match="CR 702.127a"):
        scenario.cast("Claim").cast_as_split_half("Fame")


def test_finish_pays_its_own_additional_cost_from_the_graveyard():
    scenario = _board(
        graveyard=["Start // Finish"],
        battlefield=["Swamp", "Swamp", "Swamp", "Llanowar Elves"],
    )
    elves = scenario.creature("Llanowar Elves", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_half(
        scenario,
        "Start",
        "Finish",
        Zone.GRAVEYARD,
        scenario.untapped_sources(*["Swamp"] * 3),
        targets=[bears],
        sacrificing=[elves],
    )
    scenario.resolve_top()

    assert elves.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Start", Zone.EXILE, "alice").zone is Zone.EXILE

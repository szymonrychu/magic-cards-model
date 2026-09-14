"""A card payable only by activating a mana ability that also costs life.

`auto_tap` never activates a mana ability whose cost is more than a bare {T}
on a player's behalf (`cost.free_tap_mana_abilities`): CR 118.3c makes
activating a mana ability optional, so the engine does not spend life the
player did not choose to pay. The player may still activate it themselves.
`legal_actions` lists it as an `ACTIVATE_MANA` action, and a cast it would pay
for is refused with "activate it manually to include it". A what-if
payability answer is about what the player could do, so `payability` and
`payability_matrix` count that activation, report the life it costs, and never
count a payment that would lose the game.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 601.2g / 605.3a** - a player casting a spell that needs mana may
  activate mana abilities first.
- **CR 118.3c** - activating a mana ability is not mandatory, which is why
  auto-tap withholds one with an extra cost.
- **CR 602.2b** - an activated ability's costs are paid like a spell's.
- **CR 119.4** - life may be paid only while the life total is at least the
  amount paid.
- **CR 704.5a** - a player at 0 or less life loses the game, so a payment
  that leaves them there is not a way to cast anything.

The template is "{T}, Pay N life: Add ...". Fiery Islet, Nurturing Peatland and
Sunbaked Canyon are in the deck pool. Silent Clearing, another horizon land,
and Mana Confluence, whose effect reads "one mana of any color" instead of
two colours, are not in any registered deck. Lotus Petal's "{T}, Sacrifice
this artifact" is the other extra cost, and it fails closed.
"""

from magic_cards_model.machines import Step, payability, payability_matrix
from magic_cards_model.models import ActionKind, Affordability, Zone
from tests.scenarios.harness import Scenario


def _board(hand=(), battlefield=(), library=(), life=20):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=list(battlefield),
            library=list(library),
            life=life,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _payable(scenario, name, assuming=None, assuming_zone=Zone.HAND):
    card = scenario.find(name, Zone.HAND, "alice")
    land = scenario.find(assuming, assuming_zone, "alice") if assuming is not None else None
    return payability(scenario.game, "alice", card, assuming_land=land)


# --------------------------------------------------------------------------
# A hypothetical land from hand
# --------------------------------------------------------------------------


def test_fiery_islet_makes_preordain_payable_for_one_life():
    """Izzet prowess, turn 1: Fiery Islet is the only land in hand."""
    scenario = _board(hand=["Preordain", "Fiery Islet"])

    report = _payable(scenario, "Preordain", assuming="Fiery Islet")

    assert report.payable
    assert report.life_paid == 1
    (cast,) = report.options
    assert cast.kind is ActionKind.CAST
    assert cast.affordable is Affordability.YES
    assert [entry.name for entry in cast.pays_with] == ["Fiery Islet"]
    assert any("Fiery Islet" in notice and "1 life" in notice for notice in report.notices)


def test_without_the_islet_nothing_pays():
    scenario = _board(hand=["Preordain", "Fiery Islet"])

    report = _payable(scenario, "Preordain")

    assert not report.payable
    assert report.life_paid == 0


def test_nurturing_peatland_makes_birds_of_paradise_payable():
    """Devoted combo, turn 1."""
    scenario = _board(hand=["Birds of Paradise", "Nurturing Peatland"])

    report = _payable(scenario, "Birds of Paradise", assuming="Nurturing Peatland")

    assert report.payable
    assert report.life_paid == 1


def test_at_one_life_the_islet_does_not_make_preordain_payable():
    """CR 119.4 allows paying 1 life at 1 life, but CR 704.5a then ends the
    game, so the payment casts nothing."""
    scenario = _board(hand=["Preordain", "Fiery Islet"], life=1)

    report = _payable(scenario, "Preordain", assuming="Fiery Islet")

    assert not report.payable
    assert report.life_paid == 0
    assert report.options[0].affordable is Affordability.NO
    assert any("Fiery Islet" in notice and "704.5a" in notice for notice in report.notices)


# --------------------------------------------------------------------------
# A horizon land already on the battlefield
# --------------------------------------------------------------------------


def test_sunbaked_canyon_on_the_battlefield_pays_for_lightning_bolt_now():
    scenario = _board(hand=["Lightning Bolt"], battlefield=["Sunbaked Canyon"])

    report = _payable(scenario, "Lightning Bolt")

    assert report.payable
    assert report.life_paid == 1


def test_a_free_source_is_spent_before_life():
    """An Island pays for Preordain with no life, so the Islet is not needed."""
    scenario = _board(hand=["Preordain"], battlefield=["Island", "Fiery Islet"])

    report = _payable(scenario, "Preordain")

    assert report.payable
    assert report.life_paid == 0
    assert [entry.name for entry in report.options[0].pays_with] == ["Island"]


def test_two_life_payments_are_counted_together():
    """Psychic Frog's {U}{B} needs both lands: 2 life, fine at 3 and lethal
    at 2 (CR 704.5a)."""
    battlefield = ["Fiery Islet", "Nurturing Peatland"]

    at_three = _payable(
        _board(hand=["Psychic Frog"], battlefield=battlefield, life=3), "Psychic Frog"
    )
    at_two = _payable(
        _board(hand=["Psychic Frog"], battlefield=battlefield, life=2), "Psychic Frog"
    )

    assert at_three.payable
    assert at_three.life_paid == 2
    assert not at_two.payable
    assert at_two.life_paid == 0


# --------------------------------------------------------------------------
# Off-pool proof: the same template on cards no registered deck plays
# --------------------------------------------------------------------------


def test_silent_clearing_from_the_library_makes_fatal_push_payable():
    scenario = _board(hand=["Fatal Push"], library=["Silent Clearing"])

    report = _payable(
        scenario, "Fatal Push", assuming="Silent Clearing", assuming_zone=Zone.LIBRARY
    )

    assert report.payable
    assert report.life_paid == 1


def test_mana_confluence_pays_for_birds_of_paradise():
    scenario = _board(hand=["Birds of Paradise"], battlefield=["Mana Confluence"])

    report = _payable(scenario, "Birds of Paradise")

    assert report.payable
    assert report.life_paid == 1


# --------------------------------------------------------------------------
# Any other extra cost fails closed
# --------------------------------------------------------------------------


def test_a_sacrifice_mana_ability_is_not_counted_and_is_named():
    """Lotus Petal's cost sacrifices it: a permanent resource the answer does
    not spend for the player, so the card reads not payable, with a notice."""
    scenario = _board(hand=["Preordain"], battlefield=["Lotus Petal"])

    report = _payable(scenario, "Preordain")

    assert not report.payable
    assert report.life_paid == 0
    assert any("Lotus Petal" in notice for notice in report.notices)


# --------------------------------------------------------------------------
# Batching and purity
# --------------------------------------------------------------------------


def _shape(report):
    return (
        report.payable,
        report.life_paid,
        [
            (o.kind, o.affordable, o.alternative_cost, o.keyword, o.pays_with)
            for o in report.options
        ],
        report.assumed_land,
        report.notices,
    )


def test_the_matrix_agrees_with_one_question_at_a_time():
    scenario = _board(
        hand=[
            "Preordain",
            "Birds of Paradise",
            "Psychic Frog",
            "Fiery Islet",
            "Nurturing Peatland",
        ],
        battlefield=["Lotus Petal"],
        library=["Silent Clearing", "Island"],
        life=3,
    )
    game = scenario.game
    me = game.player("alice")
    cards = [card for card in me.hand if not card.card.is_land]
    lands = [card for card in (*me.hand, *me.library) if card.card.is_land]

    matrix = payability_matrix(game, "alice", cards, lands)

    for card in cards:
        assert _shape(matrix.get(card.id)) == _shape(payability(game, "alice", card))
        for land in lands:
            single = payability(game, "alice", card, assuming_land=land)
            assert _shape(matrix.get(card.id, land.id)) == _shape(single), (card.name, land.name)


def test_asking_mutates_nothing():
    scenario = _board(
        hand=["Psychic Frog", "Fiery Islet"], battlefield=["Nurturing Peatland"], life=3
    )
    before = scenario.game.model_dump_json()

    _payable(scenario, "Psychic Frog")
    _payable(scenario, "Psychic Frog", assuming="Fiery Islet")

    assert scenario.game.model_dump_json() == before

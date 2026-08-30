"""Scenario: a cost that names the permanent its own ability is printed on.

"Sacrifice this land", "Discard this card" - CR 700.7: "If an ability uses a
phrase such as 'this [something]' to identify an object, ... it is referring to
that particular object". There is no choice for a player to make (CR 601.2b has
nothing to announce), because the object is fixed by the sentence itself.

A `bob` who tried to activate Flooded Strand and was told "sacrifice needs 1
card(s) chosen, 0 given" hit exactly this: `Game.activation_cost` classified
"Sacrifice this land" as a quality-based `CostKind.SACRIFICE` piece and asked a
caller to nominate a card, when CR 700.7 leaves nothing to nominate. The fix
lives in `Game._object_cost_component` (`models/game.py`) and the exile phrase
reader in `machines/cost.py`; every test below activates the ability with
**nothing nominated**, which is the shape that used to fail.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 700.7** - "this [quality]" always means "that particular object".
- **CR 201.5** - text naming an object by its own printed name means the same
  thing: "just that particular object".
- **CR 602.1a** - the activation cost is everything before the colon, and its
  source is the object the ability is printed on.
- **CR 701.21a** - to sacrifice a permanent, its controller moves it to its
  owner's graveyard; **CR 702.48b** is the general shape for a sacrifice that
  *is* a real choice: "You choose which permanent to sacrifice as you make
  choices for the spell ... and you sacrifice that permanent as you pay the
  total cost."
- **CR 701.9a** - to discard a card, move it from its owner's hand to that
  player's graveyard - discarding is hand-only by definition, unlike exiling.
- **CR 406.2** - to exile an object is to put it into the exile zone from
  whatever zone it is currently in - nothing here ties an exile cost to the
  hand, so Seasoned Pyromancer's "Exile this card from your graveyard" is a
  perfectly ordinary exile cost, not a special case.
- **CR 118.3** - a cost cannot be paid without the resources to pay it in full,
  checked before anything is spent; a nominated card that does not match a
  printed quality ("Sacrifice a Goblin") is exactly such a resource shortfall.

Two of the cards below (Seasoned Pyromancer's graveyard ability, Boseiju's
Channel) print an activated ability that functions from a zone other than the
battlefield. `Game.why_cannot_activate` gates every activation on
`permanent.zone is Zone.BATTLEFIELD` (CR 113.6's flat rule - see
`docs/engine-coverage.md`'s entries for both cards), so the full
`begin_activating`/`activate_ability` path cannot reach them yet; that gap is
pre-existing and out of scope here. Those two tests build and pay the
`TotalCost` directly instead, which is enough to prove the cost itself -
CR 118.3's question - now has an answer.
"""

import pytest

from magic_cards_model.machines import CostPayment, Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario, mana_from

# -- the exact reported case ------------------------------------------------


def test_flooded_strand_sacrifices_itself_with_no_card_nominated():
    """The reported bug, word for word: activating Flooded Strand with nothing
    nominated used to fail with "sacrifice needs 1 card(s) chosen, 0 given".

    "{T}, Pay 1 life, Sacrifice this land: Search your library for a Plains or
    Island card, put it onto the battlefield, then shuffle."
    """
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Flooded Strand"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)

    scenario.activate(strand)  # no `sacrificing=` at all

    assert strand.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 19

    scenario.pass_until_resolved()

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.zone is Zone.BATTLEFIELD


# -- the same shape, different cards -----------------------------------------


def test_a_different_fetchland_also_needs_no_card_nominated():
    """Windswept Heath, to prove the fix is on the shape and not on one card."""
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Windswept Heath"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    heath = scenario.find("Windswept Heath", Zone.BATTLEFIELD)

    scenario.activate(heath)
    scenario.pass_until_resolved()

    assert heath.zone is Zone.GRAVEYARD
    assert scenario.find("Forest", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_tinder_farm_sacrifices_itself_for_mana_with_no_card_nominated():
    """Tinder Farm: "{T}, Sacrifice this land: Add {R}{W}."

    A mana ability (CR 605.1a), so it never touches the stack (CR 605.3b) -
    the sacrifice still has to happen with nothing nominated.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Tinder Farm"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    farm = scenario.find("Tinder Farm", Zone.BATTLEFIELD)

    ability = scenario.activate(farm, index=1)

    assert ability is None, "a mana ability produces no object on the stack"
    assert farm.zone is Zone.GRAVEYARD
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1
    assert scenario.player("alice").mana_pool.floating.get(Color.WHITE) == 1


def test_mishras_bauble_sacrifices_itself_with_no_card_nominated():
    """Mishra's Bauble: "{T}, Sacrifice this artifact: Look at the top card of
    target player's library. Draw a card at the beginning of the next turn's
    upkeep."
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Mishra's Bauble"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)

    scenario.activate(bauble, targets=["alice"])

    assert bauble.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Mishra's Bauble's activated ability"]


def test_ranger_captain_of_eos_sacrifices_itself_with_no_card_nominated():
    """Ranger-Captain of Eos: "Sacrifice this creature: Your opponents can't
    cast noncreature spells this turn."
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Ranger-Captain of Eos", "Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.find("Ranger-Captain of Eos", Zone.BATTLEFIELD)

    scenario.activate(captain)

    assert captain.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Ranger-Captain of Eos's activated ability"]


# -- the contrast: a quality still needs a real choice -----------------------


def _rites_board(sacrificial: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", *sacrificial],
        )
        .player("bob", library=["Forest"])
    )


def test_sacrifice_a_creature_still_refuses_with_no_creature_nominated():
    """Vampiric Rites: "Sacrifice a creature" names a *quality*, not "this" -
    CR 700.7 does not apply, so CR 118.3's choice is still required.
    """
    scenario = _rites_board(sacrificial=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.activate(rites, *swamps)


def test_sacrifice_a_creature_still_lets_the_player_choose_which():
    """Two creatures on the battlefield: only the nominated one goes."""
    scenario = _rites_board(sacrificial=["Grizzly Bears", "Raging Goblin"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Raging Goblin", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    scenario.activate(rites, *swamps, sacrificing=[goblin])

    assert goblin.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD


def test_a_nominated_card_that_does_not_match_the_printed_quality_is_refused():
    """Skirk Prospector: "Sacrifice a Goblin: Add {R}." A Grizzly Bears is not
    one, so CR 118.3 refuses it - a component built with no `requirement` at
    all would have accepted anything, which was the bug in cleanup #2.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Skirk Prospector", "Grizzly Bears"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prospector = scenario.creature("Skirk Prospector", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="Grizzly Bears is not a Goblin"):
        scenario.activate(prospector, sacrificing=[bears])

    assert bears.zone is Zone.BATTLEFIELD, "the refused cost spent nothing"


# -- exiling is not hand-only, and discarding follows the same shape --------


def test_seasoned_pyromancers_exile_from_graveyard_cost_is_payable():
    """Seasoned Pyromancer: "{3}{R}{R}, Exile this card from your graveyard:
    Create two 1/1 red Elemental creature tokens."

    Before this fix, `machines/cost.py` hardcoded an exile cost's zone check to
    the hand, so this would have been refused with "is in the graveyard, not
    the hand" even after the self-reference was filled in. `Game.why_cannot_activate`
    gates every activation on being on the battlefield (CR 113.6's flat rule),
    so a graveyard-functioning ability cannot reach it yet - that is a
    pre-existing, separately documented gap (`docs/engine-coverage.md`). This
    builds and pays the `TotalCost` directly, which is the part CR 118.3 asks
    about and the part this fix changes.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Seasoned Pyromancer"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pyromancer = scenario.find("Seasoned Pyromancer", Zone.GRAVEYARD)
    mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    total = scenario.game.activation_cost(pyromancer, 0, "alice")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice")
    for mountain in mountains:
        payment.tap_for_mana(mountain, mana_from(mountain))
    payment.pay()

    assert pyromancer.zone is Zone.EXILE
    assert pyromancer in scenario.game.exile


def test_boseijus_channel_discards_itself_with_no_card_nominated():
    """Boseiju, Who Endures: "Channel - {1}{G}, Discard this card: ...".

    "Discard this card" is `CostKind.DISCARD`, classified separately from
    `CostKind.SACRIFICE` but needing exactly the same self-reference fill-in -
    this is the test that pins the discard half of the fix. Channel functions
    from hand (CR 701.9a: discarding always is), and `why_cannot_activate`'s
    battlefield-only gate is a separate, documented gap
    (`docs/engine-coverage.md`), so this builds and pays the cost directly.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Boseiju, Who Endures"], battlefield=["Forest", "Mountain"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND)
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)

    total = scenario.game.activation_cost(boseiju, 1, "alice")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice")
    payment.tap_for_mana(forest, mana_from(forest))
    payment.tap_for_mana(mountain, mana_from(mountain))
    payment.pay()

    assert boseiju.zone is Zone.GRAVEYARD
    assert boseiju in scenario.player("alice").graveyard

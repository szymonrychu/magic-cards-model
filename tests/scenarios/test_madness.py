"""Madness: discarding into exile and casting from there (CR 702.35).

CR 702.35a: "Madness is a keyword that represents **two abilities**. The first is
a static ability that functions while the card with madness is in a player's
hand. The second is a triggered ability that functions when the first ability is
applied. 'Madness [cost]' means "If a player would discard this card, that
player discards it, but exiles it instead of putting it into their graveyard"
and "When this card is exiled this way, its owner may cast it by paying [cost]
rather than paying its mana cost. If that player doesn't, they put this card
into their graveyard.""

Three things in that wording decide the whole implementation, and each has a
test here:

- The card **is discarded**. "That player discards it, but exiles it instead of
  putting it into their graveyard" - only the destination changes, so anything
  that watches for a discard still sees one, and a discard paid as a *cost* is
  still a discard.
- The exile is its own pile (CR 406.4). The trigger is about "this card ...
  exiled **this way**", and CR 702.35a's cast permission goes with it.
- CR 702.35b: "Casting a spell using its madness ability follows the rules for
  paying alternative costs in rules 601.2b and 601.2f-h" - so it is an
  alternative cost, like flashback and evoke, not an additional one.

The discard here is Wild Mongrel's activation cost, which is a real discard
through `machines/cost.py`. `Player.discard` is the *other* way a card gets
discarded and it has no game to hand, so it cannot apply a replacement effect;
`machines/keywords.discard` is where the rule lives, and the hook that would
send `Player.discard` there is named in `docs/engine-coverage.md`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent, keyword_ability
from magic_cards_model.machines.casting import keyword_cast_options, why_cannot_cast_from
from magic_cards_model.machines.keywords import discard, keyword_triggered_abilities
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.mana import ManaCost
from tests.cards import card
from tests.scenarios.harness import Scenario

NO_KEYWORD_EFFECT_DISPATCH = (
    "The madness trigger is generated and put on the stack, and then resolves doing "
    "nothing: Game._effect_of looks an ability's effect up by (card name, event) in "
    "machines/effects.TRIGGER_EFFECTS, and a keyword ability belongs to no card name. "
    "machines/keywords.KEYWORD_TRIGGER_EFFECTS holds the effect and nothing consults "
    "it. See docs/engine-coverage.md."
)

NO_DISCARD_HOOK_ON_PLAYER = (
    "Player.discard takes no game, so it moves the card straight to the graveyard "
    "with nothing consulted on the way. CR 702.35a's first ability is a replacement "
    "on that move. machines/keywords.discard is the whole rule and needs a caller; "
    "see docs/engine-coverage.md."
)


def board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Basking Rootwalla"],
            battlefield=["Wild Mongrel", "Forest", "Forest"],
        )
        .player("bob")
    )


def discard_it(scenario):
    """Discard the Rootwalla as Wild Mongrel's activation cost (CR 602.1a)."""
    rootwalla = scenario.find("Basking Rootwalla", Zone.HAND, "alice")
    mongrel = scenario.creature("Wild Mongrel")
    scenario.activate(mongrel, discarding=[rootwalla])
    return rootwalla


def test_the_madness_cost_is_printed_and_parsed():
    """CR 702.1a: `Madness {0}` is read, count and all."""
    ability = keyword_ability(card("Basking Rootwalla"), "madness")
    assert ability is not None
    assert ability.cost == "{0}"


def test_madness_casts_the_card_out_of_its_own_pile_of_exile():
    """CR 702.35a's second ability, as a CR 601.3 permission.

    `keyword_cast_options` is where flashback, foretell, plot and warp live, and
    madness belongs there for the same reason: the card is in exile, and nothing
    lets a card be cast from exile unless some effect says so. The pile matters -
    CR 406.4 keeps exiled cards in separate piles, and only a card exiled *this
    way* may be cast for the madness cost.
    """
    (option,) = keyword_cast_options(card("Basking Rootwalla"))
    assert option.keyword.lower() == "madness"
    assert option.zone is Zone.EXILE
    assert option.marker is ExileMarker.MADNESS
    assert option.pays_mana_cost is False  # CR 702.35b: an alternative cost
    assert option.later_turn is False  # unlike plot, foretell and warp


def test_madness_is_two_abilities_and_the_second_is_a_trigger():
    """CR 702.35a, read carefully: a static ability *and* a triggered one."""
    (ability,) = keyword_triggered_abilities(card("Basking Rootwalla"))
    assert ability.keyword == "madness"
    assert ability.event is TriggerEvent.EXILED
    assert ability.condition == "this card is exiled this way"


def test_discarding_a_madness_card_exiles_it_instead():
    """CR 702.35a's first ability: discarded into exile, not into the graveyard."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    rootwalla = discard_it(scenario)

    assert rootwalla.zone is Zone.EXILE
    assert rootwalla in scenario.game.exile
    assert rootwalla not in scenario.player("alice").graveyard
    assert rootwalla.exile_annotation is not None
    assert rootwalla.exile_annotation.marker is ExileMarker.MADNESS
    assert rootwalla.exile_annotation.owner == "alice"


def test_the_exile_puts_the_madness_trigger_on_the_stack():
    """CR 702.35a: "When this card is exiled this way", CR 603.3 puts it up.

    Nothing in this test drives madness - the trigger comes off the discard,
    which was a cost being paid three lines earlier.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    discard_it(scenario)

    assert "Basking Rootwalla's triggered ability" in scenario.stack_names()


def test_a_card_without_madness_is_discarded_into_the_graveyard():
    """The control: only the card with madness has its discard replaced."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Wild Mongrel", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")

    scenario.activate(scenario.creature("Wild Mongrel"), discarding=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert bears.exile_annotation is None


def test_the_madness_trigger_lets_it_be_cast_for_its_madness_cost():
    """CR 702.35a's second ability, and CR 702.35b's alternative cost."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = discard_it(scenario)

    casting = scenario.cast("Basking Rootwalla", from_zone=Zone.EXILE)
    casting.use_keyword("Madness")
    # `Madness {0}` costs nothing, in place of the printed {G}: an alternative
    # cost, not a reduction (CR 702.35b, CR 118.9c).
    assert casting.base_cost == ManaCost.parse("{G}")
    assert str(casting.total_cost.mana) == ""

    payment = casting.begin_paying()
    payment.pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert rootwalla.zone is Zone.BATTLEFIELD


def test_madness_cannot_cast_a_card_that_reached_the_graveyard():
    """CR 406.4: the permission is about the pile, not about the card.

    A Rootwalla milled or destroyed into the graveyard has no madness pile to be
    cast out of, and CR 601.3 then allows nothing.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Basking Rootwalla"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = scenario.find("Basking Rootwalla", Zone.GRAVEYARD, "alice")

    refusal = why_cannot_cast_from(rootwalla, "alice", Zone.GRAVEYARD, scenario.game)
    assert refusal is not None
    assert "graveyard" in refusal

    casting = scenario.cast("Basking Rootwalla", from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError, match="exile"):
        casting.use_keyword("Madness")


def test_discarding_it_a_second_time_is_not_possible_from_exile():
    """CR 702.35a's first ability "functions while the card ... is in a player's
    hand", so a card already in exile is past it."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = discard_it(scenario)

    with pytest.raises(ValueError, match="not in alice's hand"):
        discard(scenario.game, rootwalla, "alice")


def test_declining_madness_puts_the_card_into_the_graveyard():
    """The other branch of the trigger: "or put it into your graveyard".

    Casting is a choice with nobody to ask, so the trigger takes the branch that
    needs no answer. CR 702.35c is why it matters: "if the exiled card wasn't
    cast and was moved to a public zone, effects referencing the discarded card
    can find that card" (CR 400.7k).
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = discard_it(scenario)
    assert rootwalla.zone is Zone.EXILE

    scenario.resolve_top()  # the madness trigger

    assert rootwalla.zone is Zone.GRAVEYARD


def test_a_discard_through_player_discard_is_replaced_too():
    """The same rule, reached by the other road (CR 701.9a).

    `Player.discard` is what the cleanup step's CR 514.1 discard uses, so until
    it goes through the replacement a madness card discarded to hand size lands
    in the graveyard.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = scenario.find("Basking Rootwalla", Zone.HAND, "alice")

    scenario.player("alice").discard(rootwalla)

    assert rootwalla.zone is Zone.EXILE

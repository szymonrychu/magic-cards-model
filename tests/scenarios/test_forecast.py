"""Forecast: an activated ability that functions only from a hand, and only
during its owner's upkeep (CR 702.57).

CR 702.57a: "A forecast ability is an activated ability that can be activated
only from a player's hand. It's written 'Forecast — [Activated ability].'"

CR 702.57b: "A forecast ability may be activated only during the upkeep step
of the card's owner and only once each turn. The controller of the forecast
ability reveals the card with that ability from their hand as the ability is
activated. That player plays with that card revealed in their hand until it
leaves the player's hand or until a step or phase that isn't an upkeep step
begins, whichever comes first."

CR 113.6j is what pins the ability to the hand at all: "An object's activated
ability that has a cost that can't be paid while the object is on the
battlefield functions from any zone in which its cost can be paid." Forecast's
own printed cost always includes "Reveal this card from your hand" (CR 701.20a:
revealing shows the card, CR 701.20b: it never moves), which a permanent on the
battlefield has no hand card to pay - `_REVEALS_ITSELF_FROM_HAND`
(`machines/abilities.py`) reads that phrase the same general way
`_DISCARDS_ITSELF`/`_EXILES_ITSELF_FROM_ZONE` already read a self-discarding or
self-exiling cost.

The upkeep-only, once-each-turn timing (CR 702.57b) is the keyword's own
meaning rather than printed instruction text - Scryfall's own reminder text,
"(Activate only during your upkeep and only once each turn.)", is reminder text
and is stripped before any ability is parsed - so it is read off
`ActivatedAbility.forecast` (set whenever the CR 207.2c-shaped "Forecast —"
prefix is the ability's own `ability_word`) rather than off
`ActivatedAbility.instructions`, the same way Boast's and Exhaust's own
keyword-inherent restrictions are read off `ability_word`/a dedicated flag
instead of off printed text.

Cards (real printings, `src/magic_cards_model/data/printings/`):

- **Writ of Passage** (Dissension) - "Enchant creature\\nWhenever enchanted
  creature attacks, if its power is 2 or less, it can't be blocked this turn.
  \\nForecast — {1}{U}, Reveal this card from your hand: Target creature with
  power 2 or less can't be blocked this turn." A noncreature Aura, so its
  Forecast line reveals "this card"; its own attack-triggered ability is a
  separate, pre-existing gap unrelated to Forecast (not this file's concern).
- **Pride of the Clouds** - "Flying\\nThis creature gets +1/+1 for each other
  creature on the battlefield with flying.\\nForecast — {2}{W}{U}, Reveal this
  creature from your hand: Create a 1/1 white and blue Bird creature token
  with flying." A creature, so its Forecast line reveals "this creature" - a
  different self-noun, proving `_REVEALS_ITSELF_FROM_HAND` reads the shape
  generally rather than "Writ of Passage's own sentence".

Every CR number in this file was looked up with `mise run rules:find` in the
session that wrote it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation, off_zone_abilities
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import card_support, ignored_keywords
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

WRIT = "Writ of Passage"
PRIDE = "Pride of the Clouds"


def _writ_board(*, alice_first: bool = True, bob_battlefield: list[str] | None = None) -> Scenario:
    """Alice holds Writ of Passage; Bob has a creature to target. Turn order
    follows player-add order, so `alice_first=False` makes Bob the active
    player - the shape the "opponent's upkeep" refusal needs."""
    scenario = Scenario().manual_turn_based_actions()
    alice = ("alice", dict(hand=[WRIT], battlefield=["Island", "Island", "Island"]))
    bob = ("bob", dict(battlefield=bob_battlefield or ["Grizzly Bears"]))
    first, second = (alice, bob) if alice_first else (bob, alice)
    scenario.player(first[0], **first[1])
    scenario.player(second[0], **second[1])
    return scenario


def _activate_writ(scenario: Scenario, targets: list | None = None):
    writ = scenario.find(WRIT, Zone.HAND, "alice")
    return off_battlefield_activation(scenario.game, writ, "alice", targets=targets)


def _pay_and_activate(scenario: Scenario, activation) -> None:
    payment = activation.begin_paying()
    for island in scenario.untapped_sources("Island", "Island"):
        payment.tap_for_mana(island, mana_from(island))
    payment.pay()
    activation.activate()


# -- CR 702.57a: read as an off-zone hand ability ----------------------------


def test_forecast_is_read_as_an_off_zone_activated_ability_in_the_hand():
    (entry,) = off_zone_abilities(card(WRIT))
    assert entry.family == "printed"
    assert entry.keyword == "Forecast"
    assert entry.zone is Zone.HAND
    assert entry.rule == "CR 113.6j"


def test_a_creature_forecast_reveals_this_creature_not_this_card():
    """Pride of the Clouds' own self-noun ("this creature") is read the same
    general way Writ of Passage's ("this card") is - proof the reader is not
    fitted to one card's exact sentence."""
    (entry,) = off_zone_abilities(card(PRIDE))
    assert entry.keyword == "Forecast"
    assert entry.zone is Zone.HAND
    assert "Reveal this creature from your hand" in entry.ability.cost


# -- CR 702.57b: only the owner's upkeep, and the card stays in hand,
# revealed --------------------------------------------------------------------


def test_forecast_activates_during_its_owners_upkeep_and_the_card_stays_revealed_in_hand():
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    activation = _activate_writ(scenario, targets=[bears])
    assert activation.why_not() is None
    assert str(activation.cost.mana) == "{1}{U}"
    _pay_and_activate(scenario, activation)

    writ = scenario.find(WRIT, Zone.HAND, "alice")
    assert writ.zone is Zone.HAND, "CR 701.20b: revealing never moves the card"
    assert writ in scenario.player("alice").hand

    activation.resolve()

    (reveal,) = scenario.game.reveals
    assert reveal.card_id == writ.id
    assert reveal.card_name == WRIT
    assert reveal.revealed_by == "alice"
    assert reveal.zone is Zone.HAND
    assert reveal.source == WRIT


@pytest.mark.parametrize("step", [Step.PRECOMBAT_MAIN, Step.DRAW])
def test_forecast_is_refused_outside_the_upkeep_step(step: Step):
    scenario = _writ_board().build()
    scenario.start_at(step)
    bears = scenario.creature("Grizzly Bears", "bob")

    activation = _activate_writ(scenario, targets=[bears])

    refusal = activation.why_not()
    assert refusal is not None
    assert "upkeep" in refusal
    assert "CR 702.57b" in refusal


def test_forecast_is_refused_during_the_opponents_upkeep():
    scenario = _writ_board(alice_first=False).build()
    scenario.start_at(Step.UPKEEP)
    assert scenario.turn.active_player == "bob"
    bears = scenario.creature("Grizzly Bears", "bob")

    activation = _activate_writ(scenario, targets=[bears])

    refusal = activation.why_not()
    assert refusal is not None
    assert "alice's upkeep" in refusal
    assert "CR 702.57b" in refusal


def test_forecast_is_refused_the_second_time_in_the_same_upkeep():
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    first = _activate_writ(scenario, targets=[bears])
    _pay_and_activate(scenario, first)
    first.resolve()

    second = _activate_writ(scenario, targets=[bears])
    refusal = second.why_not()
    assert refusal is not None
    assert "already been activated this turn" in refusal
    assert "CR 702.57b" in refusal


def test_forecast_may_be_activated_again_the_following_upkeep():
    """CR 702.57b's once-each-turn is per turn, not forever - `activations`'
    own sibling `forecast_activations` is cleared exactly like it is."""
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    first = _activate_writ(scenario, targets=[bears])
    _pay_and_activate(scenario, first)
    first.resolve()

    scenario.advance()
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        if scenario.turn.active_player == "bob" and scenario.step is Step.UPKEEP:
            # Still not alice's own upkeep - refused, per CR 702.57b, exactly
            # as the dedicated opponent's-upkeep test already checks.
            assert _activate_writ(scenario, targets=[bears]).why_not() is not None
        scenario.advance()

    second = _activate_writ(scenario, targets=[bears])
    assert second.why_not() is None


# -- CR legal_actions offers it only in that window --------------------------


def _forecast_offered(scenario: Scenario) -> bool:
    actions = legal_actions(scenario.game, "alice")
    return any(
        action.kind is ActionKind.ACTIVATE_OFF_ZONE
        and action.keyword == "Forecast"
        and action.card_id == scenario.find(WRIT, Zone.HAND, "alice").id
        for action in actions
    )


def test_legal_actions_offers_forecast_only_during_the_owners_upkeep():
    scenario = _writ_board().build()

    scenario.start_at(Step.UPKEEP)
    assert _forecast_offered(scenario) is True

    scenario.start_at(Step.DRAW)
    assert _forecast_offered(scenario) is False

    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _forecast_offered(scenario) is False


def test_legal_actions_stops_offering_forecast_once_activated_this_turn():
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    assert _forecast_offered(scenario) is True
    bears = scenario.creature("Grizzly Bears", "bob")

    activation = _activate_writ(scenario, targets=[bears])
    _pay_and_activate(scenario, activation)
    activation.resolve()

    assert _forecast_offered(scenario) is False


# -- Writ of Passage's own resolution and targeting restriction -------------


def test_writ_of_passage_forecast_makes_a_low_power_creature_unblockable():
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")
    assert bears.card.power == "2"

    activation = _activate_writ(scenario, targets=[bears])
    _pay_and_activate(scenario, activation)
    activation.resolve()

    board = scenario.game.computed_board()
    assert board.of(bears).has_ability("This creature can't be blocked.")


def test_writ_of_passage_forecast_refuses_a_power_three_creature_target():
    """Accorder Paladin is a real 3-power creature - CR 115.1's own "power 2
    or less" comparison restriction refuses it as a target."""
    scenario = _writ_board(bob_battlefield=["Accorder Paladin"]).build()
    scenario.start_at(Step.UPKEEP)
    paladin = scenario.creature("Accorder Paladin", "bob")
    assert paladin.card.power == "3"

    with pytest.raises(ValueError, match="power 2 or less"):
        _activate_writ(scenario, targets=[paladin])


def test_writ_of_passage_can_still_be_cast_normally_after_its_forecast_is_used():
    """CR 701.20b: revealing does not consume, tap, or exile the card - it is
    an ordinary Aura in hand, castable as ever, the same turn."""
    scenario = _writ_board().build()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")

    activation = _activate_writ(scenario, targets=[bears])
    _pay_and_activate(scenario, activation)
    activation.resolve()

    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    enchanted = scenario.cast_and_resolve(WRIT, island, targets=[bears])

    assert enchanted.zone is Zone.BATTLEFIELD
    assert enchanted.attached_to == bears.id


# -- Pride of the Clouds: a creature's Forecast, and its own static pump -----


def test_pride_of_the_clouds_forecast_creates_a_flying_bird_token():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[PRIDE], battlefield=["Plains", "Island", "Plains", "Island"])
        .build()
    )
    scenario.start_at(Step.UPKEEP)
    pride = scenario.find(PRIDE, Zone.HAND, "alice")

    activation = off_battlefield_activation(scenario.game, pride, "alice")
    assert activation.why_not() is None
    assert str(activation.cost.mana) == "{2}{W}{U}"
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains", "Island", "Plains", "Island"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()

    (bird,) = [state for state in scenario.game.battlefield if state.name == "Bird Token"]
    chars = scenario.game.computed_board().of(bird)
    assert chars.power == 1
    assert chars.toughness == 1
    assert chars.controller == "alice"
    assert "flying" in [ability.lower() for ability in chars.abilities]
    assert pride.zone is Zone.HAND, "revealing the creature never cast or discarded it"


def test_pride_of_the_clouds_gets_plus_one_plus_one_for_each_other_flyer():
    """The card's own static ability, unrelated to Forecast but named in the
    same printing's oracle text - CR 604.2, applied off the live board."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[PRIDE, "Aerial Doombot", "Grizzly Bears"],
        )
        .build()
    )
    pride = scenario.creature(PRIDE)
    board = scenario.game.computed_board()
    assert board.of(pride).numeric_power_toughness == (2, 2), "one other flyer: Aerial Doombot"


def test_forecast_and_the_static_pump_are_both_off_ignored_keywords():
    """The corner case both cards share: neither Forecast keyword, nor
    (Pride of the Clouds') Flying, is left unaudited."""
    assert ignored_keywords(card(WRIT)) == []
    assert ignored_keywords(card(PRIDE)) == []
    assert card_support(card(PRIDE)).status == "handled"

"""Scenario: "If <condition>, <source> deals N damage to each opponent." - the
damage rider is gated by its own condition, never run with the condition
dropped.

The each-opponent damage reader used to swallow a leading "If <condition>, " into
the damage source, so every such rider dealt its damage unconditionally. The
reader now refuses a leading "if" and the generic condition clause gates it,
which made two real oracle cards depend on a reader of their own condition:

- Grab the Prize (DSK): "As an additional cost to cast this spell, discard a
  card. Draw two cards. If the discarded card wasn't a land card, Grab the Prize
  deals 2 damage to each opponent." - "the discarded card" is the card the
  additional cost discarded (`CastRecord.additional_cost_cards`).
- Beckett Mariner, Impetuous Ensign (Reckless Behavior): "Whenever Beckett Mariner
  becomes tapped, put a promotion counter on her. Then if there are three or more
  promotion counters on her, remove those counters and she deals 2 damage to each
  opponent." - the counter-threshold shape with the source named "her".

The riders that were already gated keep their behaviour; the corner cases of
each stay in their own files (Balin, Loremaster: `test_discard_hand_draw_x`;
Chandra, Torch of Defiance: `test_fra_s8_exile_top_may_x_if_you_dont_y`;
Dathon: `test_enchantment_cast_draw_saga_damage`). Reckless Handling is played
end to end below.

Rules, each looked up with `mise run rules:find` in the session that wrote this
file:

- **CR 608.2c** - the controller follows a spell's or ability's instructions
  in the order written; a conditional instruction does what it says only when
  its condition holds.
- **CR 118.8a / CR 601.2h** - an additional cost is announced and paid as the
  spell is cast, so the discarded card is already in the graveyard when the
  spell resolves.
- **CR 120.3a** - damage dealt to a player by a source without infect causes
  that player to lose that much life.
- **CR 122.1** - a counter is a marker placed on an object; Beckett's "those
  counters" are the promotion counters the threshold just counted.
- **CR 701.9b** - effects may require a random discard, so the game, not the
  player, picks the card.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GRAB = "Grab the Prize"
BECKETT = "Beckett Mariner, Impetuous Ensign"


def _grab_board(*, discard: str, opponents=("bob",)) -> Scenario:
    scenario = Scenario().player(
        "alice",
        library=["Forest"] * 5,
        hand=[GRAB, discard],
        battlefield=["Mountain", "Mountain"],
    )
    for name in opponents:
        scenario = scenario.player(name, library=["Forest"] * 3)
    scenario = scenario.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_grab(scenario, discard: str):
    card = scenario.find(discard, Zone.HAND, "alice")
    scenario.cast_onto_stack(
        GRAB, *scenario.untapped_sources("Mountain", "Mountain"), discarding=[card]
    )
    scenario.resolve_top()
    return card


# -- Grab the Prize: "the discarded card" -----------------------------------


@pytest.mark.parametrize("discard", ["Grizzly Bears", "Lightning Bolt", "Sol Ring"])
def test_a_nonland_discard_deals_two_damage_to_each_opponent(discard):
    scenario = _grab_board(discard=discard, opponents=("bob", "carol"))

    _cast_grab(scenario, discard)

    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18
    assert scenario.player("alice").life == 20, "each opponent, never the caster"
    # Hand: both cards left (-2) and two cards were drawn (+2).
    assert len(scenario.player("alice").hand) == 2


def test_a_land_discard_still_draws_two_and_deals_no_damage():
    scenario = _grab_board(discard="Forest")

    card = _cast_grab(scenario, "Forest")

    assert card.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20
    assert len(scenario.player("alice").hand) == 2


def test_the_discarded_card_is_judged_after_the_discard_whatever_zone_it_is_in():
    """Judged as a card in the graveyard: a nonbasic land is still a land."""
    scenario = _grab_board(discard="Stomping Ground")

    _cast_grab(scenario, "Stomping Ground")

    assert scenario.player("bob").life == 20


def _holds(scenario, condition):
    spell = scenario.game.stack[-1]
    return scenario.game.condition_holds("alice", condition, spell)


def test_the_discarded_card_reader_answers_any_quality_and_negation():
    """The reader is "the discarded card <was/wasn't> a <quality> card", not
    land: other qualities and the positive form answer from the same cost."""
    scenario = _grab_board(discard="Grizzly Bears")
    card = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.cast_onto_stack(
        GRAB, *scenario.untapped_sources("Mountain", "Mountain"), discarding=[card]
    )

    assert _holds(scenario, "the discarded card wasn't a land card") is True
    assert _holds(scenario, "the discarded card was a land card") is False
    assert _holds(scenario, "the discarded card was a creature card") is True
    assert _holds(scenario, "the discarded card was a green card") is True
    assert _holds(scenario, "the discarded card was a red card") is False


def test_a_spell_with_no_discard_cost_has_no_discarded_card():
    """Nothing was discarded to cast it, so neither the positive nor the
    negative form can be answered: the engine says so rather than guessing."""
    scenario = _grab_board(discard="Forest")
    spell = scenario.find(GRAB, Zone.HAND, "alice")

    holds = scenario.game.condition_holds("alice", "the discarded card was a land card", spell)
    assert holds is not True


def test_only_the_discarded_card_takes_a_card_noun():
    """ "it was a creature card" is about some other card than the source (an
    exiled card, a revealed one), which this reader cannot name: it stays
    unread (None) rather than being judged against the source."""
    scenario = _grab_board(discard="Grizzly Bears")
    spell = scenario.find(GRAB, Zone.HAND, "alice")

    assert scenario.game.condition_holds("alice", "it was a creature card", spell) is None


# -- Reckless Handling: "If an artifact card was discarded this way" -----------


def test_reckless_handling_deals_two_damage_when_the_discarded_card_is_an_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Sol Ring", "Forest"],
            hand=["Reckless Handling"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"] * 3)
        .player("carol", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Reckless Handling", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.resolve_top()

    # The only card in hand after the search is the tutored Sol Ring.
    assert scenario.find("Sol Ring", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18
    assert scenario.player("alice").life == 20


def test_reckless_handling_deals_no_damage_when_the_discarded_card_is_no_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 3,
            hand=["Reckless Handling", "Forest"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Reckless Handling", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.resolve_top()

    assert scenario.find("Forest", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_reckless_handling_judges_the_card_the_random_discard_actually_moved():
    """With the tutored artifact and a land both in hand the random discard
    may take either (CR 701.9b); the damage follows the card that went, so the
    result is right whichever the game's seed picks."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Sol Ring", "Forest"],
            hand=["Reckless Handling", "Forest"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Reckless Handling", *scenario.untapped_sources("Mountain", "Mountain")
    )
    scenario.resolve_top()

    graveyard = [card.name for card in scenario.player("alice").graveyard]
    hand = [card.name for card in scenario.player("alice").hand]
    assert len(hand) == 1, "the tutored card and the Forest were two; one was discarded"
    if "Sol Ring" in graveyard:
        assert scenario.player("bob").life == 18
    else:
        assert "Forest" in graveyard
        assert scenario.player("bob").life == 20


# -- Beckett Mariner: the counter threshold with a named source ---------------


def _beckett_board() -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[BECKETT])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _tap_beckett(scenario):
    beckett = scenario.creature(BECKETT, "alice")
    beckett.summoning_sick = False
    scenario.game.end_of_combat()  # CR 511.3: the earlier attack is over
    beckett.untap()
    scenario.attack_with(beckett, defending="bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    return beckett


def test_beckett_deals_damage_and_resets_on_the_third_tap_only():
    scenario = _beckett_board()

    beckett = _tap_beckett(scenario)
    assert beckett.counter_count("promotion") == 1
    assert scenario.player("bob").life == 20

    _tap_beckett(scenario)
    assert scenario.player("bob").life == 20, "two counters are below the threshold"

    _tap_beckett(scenario)
    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 18
    assert scenario.player("alice").life == 20
    assert beckett.counter_count("promotion") == 0, "those counters were removed"


def test_beckett_starts_counting_again_after_the_reset():
    scenario = _beckett_board()
    for _ in range(3):
        beckett = _tap_beckett(scenario)

    _tap_beckett(scenario)

    assert beckett.counter_count("promotion") == 1
    assert scenario.player("bob").life == 18, "one more tap is no second payout"

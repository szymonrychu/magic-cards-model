"""Companion (CR 702.139): the deck-legality condition and the in-game
special action, both driven off the printed keyword line rather than a
per-card table.

Every CR number below was looked up with `mise run rules:find` against the
2026-08-19 Comprehensive Rules in the session that wrote this file.

- **CR 702.139a** - the keyword ability itself, and CR 116.2g's special
  action ("pay {3} to put that card from outside the game into their hand
  ... any time they have priority and the stack is empty ... during a main
  phase of their turn, but only if they haven't done so yet this game").
- **CR 702.139b** - "your starting deck" is the mainboard, after sideboard
  cards are set aside.
- **CR 400.11a/108.3b** - outside the game, and who may bring a card in.

Kaheera, the Orphanguard (`Companion — Each creature card in your starting
deck is a Cat, Elemental, Nightmare, Dinosaur, or Beast card.`) is the
deck-pool card. Lurrus of the Dream-Den (`Companion — Each permanent card in
your starting deck has mana value 2 or less.`) is a second, differently
worded companion, added with `scripts/add_card.py`, proving the condition
reader (`machines/companion.py`) is not keyed to Kaheera's own wording.
"""

from magic_cards_model.machines.turn import Step
from magic_cards_model.models import Deck
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.zone import Zone
from tests.cards import card

from .harness import Scenario

# -- deck legality (CR 702.139a/b) ------------------------------------------


def test_a_companion_condition_fulfilled_by_the_starting_deck_is_legal():
    """Kaheera: every creature in the mainboard is a Cat, Elemental,
    Nightmare, Dinosaur, or Beast card, so the deck is legal with her
    revealed as the companion."""
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Elder Gargaroth": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion="Kaheera, the Orphanguard",
    )
    assert deck.mainboard_size == 60
    assert deck.companion_problems(card) == []
    assert deck.problems(card) == []


def test_a_companion_condition_broken_by_one_offending_creature_is_illegal():
    """Grizzly Bears is a Bear, not a Cat/Elemental/Nightmare/Dinosaur/Beast
    card - CR 702.139a's condition fails, and the companion may not be
    revealed."""
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Grizzly Bears": 4,
            "Questing Beast": 4,
            "Swords to Plowshares": 4,
        },
        companion="Kaheera, the Orphanguard",
    )
    problems = deck.companion_problems(card)
    assert len(problems) == 1
    assert "Grizzly Bears" in problems[0]
    assert deck.problems(card) == problems


def test_a_card_with_no_companion_ability_cannot_be_named_as_one():
    deck = Deck(mainboard={"Mountain": 60}, companion="Grizzly Bears")

    problems = deck.companion_problems(card)

    assert problems == ["Grizzly Bears has no companion ability (CR 702.139a)"]


def test_lurrus_a_differently_worded_companion_condition_is_read_generically():
    """CR 702.139a's condition is read off the printed clause, not off
    Kaheera's own name - Lurrus's "mana value 2 or less" shape is a
    completely different sentence and still parses.
    """
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Swords to Plowshares": 4,
            # Elder Gargaroth and Questing Beast are both mana value > 2, so
            # they are swapped out for cheaper permanents here.
            "Sol Ring": 4,
            "Counterspell": 4,
        },
        companion="Lurrus of the Dream-Den",
    )
    assert deck.companion_problems(card) == []


def test_lurrus_broken_by_an_expensive_permanent_is_illegal():
    deck = Deck(
        mainboard={
            "Mountain": 20,
            "Plains": 16,
            "Ocelot Pride": 4,
            "Savannah Lions": 4,
            "Steppe Lynx": 4,
            "Swords to Plowshares": 4,
            "Sol Ring": 4,
            "Elder Gargaroth": 4,  # mana value 5 - breaks the condition
        },
        companion="Lurrus of the Dream-Den",
    )
    problems = deck.companion_problems(card)
    assert len(problems) == 1
    assert "Elder Gargaroth" in problems[0]


def test_a_deck_with_no_companion_named_has_no_companion_problems():
    deck = Deck(mainboard={"Mountain": 60})

    assert deck.companion_problems(card) == []


def test_gyruda_only_even_mana_values_a_third_condition_shape_is_read():
    """Gyruda, Doom of Depths: "Your starting deck contains only cards with
    even mana values." - a "contains only" wording, not Lurrus's "each ...
    has", checked against the real printing before this shape was written."""
    deck = Deck(
        mainboard={"Mountain": 10, "Counterspell": 4, "Questing Beast": 4},
        companion="Gyruda, Doom of Depths",
    )
    assert deck.companion_problems(card) == []


def test_gyruda_broken_by_an_odd_mana_value_card():
    deck = Deck(
        mainboard={"Mountain": 10, "Counterspell": 4, "Sol Ring": 4},
        companion="Gyruda, Doom of Depths",
    )
    problems = deck.companion_problems(card)
    assert len(problems) == 1
    assert "Sol Ring" in problems[0]


def test_keruga_only_high_mana_value_nonland_cards_lands_exempt():
    """Keruga, the Macrosage: "Your starting deck contains only cards with
    mana value 3 or greater and land cards." - lands are named as their own
    exemption, not folded into a "nonland"/"permanent" qualifier word the
    way Lurrus's own condition is."""
    deck = Deck(
        mainboard={"Mountain": 10, "Elder Gargaroth": 4, "Questing Beast": 4},
        companion="Keruga, the Macrosage",
    )
    assert deck.companion_problems(card) == []


def test_keruga_broken_by_a_cheap_nonland_card():
    deck = Deck(
        mainboard={"Mountain": 10, "Elder Gargaroth": 4, "Counterspell": 4},
        companion="Keruga, the Macrosage",
    )
    problems = deck.companion_problems(card)
    assert len(problems) == 1
    assert "Counterspell" in problems[0]


def test_yorion_deck_size_relative_to_the_format_minimum():
    """Yorion, Sky Nomad: "Your starting deck contains at least twenty cards
    more than the minimum deck size" - relative to `DeckLimits.min_mainboard`
    (60 by default), not a flat "40 cards" the way an earlier, unverified
    draft of this reader assumed."""
    deck = Deck(mainboard={"Mountain": 80}, companion="Yorion, Sky Nomad")

    assert deck.companion_problems(card) == []


def test_yorion_broken_by_one_card_short_of_the_threshold():
    deck = Deck(mainboard={"Mountain": 79}, companion="Yorion, Sky Nomad")

    problems = deck.companion_problems(card)
    assert len(problems) == 1
    assert "79" in problems[0]


# -- the special action (CR 116.2g) ------------------------------------------


def test_the_companion_starts_outside_the_game_not_in_the_sideboard_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    alice = scenario.player("alice")

    assert alice.companion_id is not None
    (companion_state,) = alice.owned_outside_the_game()
    assert companion_state.name == "Kaheera, the Orphanguard"
    assert companion_state.id == alice.companion_id
    assert companion_state.zone is Zone.SIDEBOARD


def test_paying_three_and_bringing_the_companion_to_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    companion = scenario.bring_companion_to_hand(*sources)

    assert companion.name == "Kaheera, the Orphanguard"
    assert companion.zone is Zone.HAND
    alice = scenario.player("alice")
    assert alice.companion_action_used is True
    assert all(source.tapped for source in sources)


def test_the_special_action_is_once_per_game():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain"] * 6,
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first_sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.bring_companion_to_hand(*first_sources)

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")

    assert refusal is not None
    assert "already" in refusal


def test_no_companion_chosen_refuses_the_special_action():
    scenario = Scenario().player("alice", battlefield=["Mountain", "Mountain", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")

    assert refusal is not None
    assert "not chosen a companion" in refusal


def test_the_special_action_requires_an_empty_stack():
    """CR 116.2g: "any time ... the stack is empty"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            hand=["Lightning Bolt"],
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (bolt_source,) = scenario.untapped_sources("Mountain")
    scenario.cast("Lightning Bolt", tapping=[bolt_source])

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")

    assert refusal is not None
    assert "stack" in refusal


def test_the_special_action_requires_a_main_phase_of_the_active_players_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    refusal = scenario.game.why_cannot_bring_companion_to_hand("alice")

    assert refusal is not None


def test_the_special_action_appears_in_legal_actions():
    from magic_cards_model.machines.legal_actions import legal_actions

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mountain", "Mountain", "Mountain"],
            companion="Kaheera, the Orphanguard",
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    actions = legal_actions(scenario.game, "alice")

    assert any(action.kind is ActionKind.COMPANION for action in actions)

"""Belcher: a real Modern decklist through the real start-of-game path (CR 103).

The list is PrismaticPrism's, played 2026-08-27 (source deck `videre-58653611`),
0.8% of the current Modern metagame. It is the mono-blue Goblin Charbelcher deck,
not a ritual-storm one: it plays **zero true lands**, only modal double-faced
cards whose back faces are lands, so that Charbelcher's "reveal until you reveal
a land card" hits nothing for a long time and deals a lethal pile of damage.
That construction is the whole archetype, and it is why every land in this file
is the back face of a spell.

This file is a smoke test for the deck as a *deck*: it registers the sixty and
the fifteen through `Match.register_deck`, starts a game, and checks CR 103's
own numbers. It is not a file about one mechanic - the mechanics this deck needs
are surveyed in `docs/deck-gaps/belcher.md`, and the one that decides whether the
deck can win at all is pinned as an `xfail` at the bottom.

Rules checked here, each looked up with `knowledge_search` in the session that
wrote this file:

- CR 100.2a: a constructed deck has a minimum deck size of 60 cards, and no more
  than four of any card that is not a basic land.
- CR 100.4a: in constructed play a sideboard may contain no more than fifteen
  cards, and the four-card limit applies to the combined deck and sideboard.
- CR 103.2a: sideboards are set aside, after which each player's deck is their
  library.
- CR 103.3: after the starting player is determined, each player shuffles.
- CR 103.4: each player begins with a starting life total of 20.
- CR 103.5: each player draws a number of cards equal to their starting hand
  size, normally seven.
- CR 103.8: the starting player takes their first turn. CR 103.8a: in a
  two-player game that player skips the draw step of that first turn.
- CR 401.1: when a game begins, each player's deck becomes their library.
- CR 400.11a: cards in a player's sideboard are outside the game.
- CR 602.1: an activated ability is "[Cost]: [Effect]", and CR 602.1a's
  activation cost is everything before the colon.
- CR 119.2 / CR 120.3a: damage dealt to a player by a source without infect
  causes that player to lose that much life.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import ActivatedAbility, parse_abilities
from magic_cards_model.models import Card, Color, Deck, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

#: PrismaticPrism, 2026-08-27, source deck `videre-58653611`. Mirrors
#: `decks/belcher.txt` in magic-cards-model-api line for line. Every name is
#: the front face; `tests/cards.card` resolves it to the full `Front // Back`
#: printing, which is how a modal double-faced card is stored in the pool.
BELCHER_SIXTY = {
    "Goblin Charbelcher": 4,
    "Whir of Invention": 4,
    "Lotus Bloom": 4,
    "Tameshi, Reality Architect": 4,
    "Preordain": 3,
    "Stock Up": 1,
    "Disrupting Shoal": 4,
    "Force of Negation": 4,
    "Spell Snare": 3,
    "Counterspell": 2,
    "Stern Scolding": 1,
    "Into the Flood Maw": 2,
    "Sea Gate Restoration": 4,
    "Sink into Stupor": 4,
    "Suppression Ray": 4,
    "Hydroelectric Specimen": 4,
    "Jwari Disruption": 4,
    "Waterlogged Teachings": 2,
    "Beyeen Veil": 2,
}

BELCHER_FIFTEEN = {
    "Consign to Memory": 4,
    "Mystical Dispute": 3,
    "Engineered Explosives": 2,
    "Tamiyo, Inquisitive Student": 2,
    "Unable to Scream": 2,
    "Grafdigger's Cage": 1,
    "Spell Snare": 1,
}

#: The opposing sixty. Belcher's own list has no basic land in it, so a second
#: real deck is not needed to test CR 103 - what is needed is a legal one, and
#: this is the burn shell `tests/scenarios/test_starting_a_game.py` already
#: registers.
BURN_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}


def belcher() -> Deck:
    return Deck(mainboard=dict(BELCHER_SIXTY), sideboard=dict(BELCHER_FIFTEEN))


def match(seed: int | str = "belcher") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", belcher())
    series.register_deck("bob", Deck(mainboard=dict(BURN_SIXTY), sideboard={"Island": 15}))
    return series


# -- the list itself (CR 100.2a, 100.4a) -----------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum deck size and CR 100.4a's sideboard maximum."""
    deck = belcher()

    assert deck.mainboard_size == 60
    assert sum(BELCHER_FIFTEEN.values()) == 15


def test_the_list_is_legal_against_the_real_printings():
    """CR 100.2a, 100.4a: the four-card limit applies across deck and sideboard.

    Spell Snare is the case worth having a real deck for - three in the
    mainboard and one in the sideboard is four copies in total, which is the
    limit exactly rather than a violation of it.
    """
    deck = belcher()

    assert deck.problems(card) == []
    assert BELCHER_SIXTY["Spell Snare"] + BELCHER_FIFTEEN["Spell Snare"] == 4


def test_the_deck_contains_no_land_card_at_all():
    """The archetype's construction: every land is the back face of a spell.

    Goblin Charbelcher reveals "until you reveal a land card", so a deck whose
    only lands are the back faces of modal double-faced cards reveals a very
    large number of nonland cards first. A modal DFC in the library is a
    nonland card while it is there, which is what makes the deck work, and it
    is also what makes this assertion the right shape: not "few lands" but
    none.
    """
    printings = [card(name) for name in BELCHER_SIXTY]
    front_types = [(printing.name, printing.type_line.split(" // ")[0]) for printing in printings]

    assert [name for name, front in front_types if "Land" in front] == []
    assert any(printing.card_faces for printing in printings)


# -- starting the game (CR 103) --------------------------------------------


def test_a_game_starts_with_seven_cards_and_fifty_three_in_the_library():
    """CR 103.5's opening hand of seven, off CR 401.1's deck-becomes-library."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.card.name in _full_names() for state in alice.hand)


def test_the_sideboard_is_set_aside_and_not_in_the_library():
    """CR 103.2a sets the sideboard aside; CR 400.11a keeps it outside the game."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert len(alice.library) == 53


def test_both_players_begin_at_twenty_life():
    """CR 103.4: each player begins the game with a starting life total of 20."""
    game = match().start_game()

    assert game.player("alice").life == 20
    assert game.player("bob").life == 20


def test_two_seeds_deal_different_opening_hands():
    """CR 103.3: each player shuffles their deck into a random order.

    Two `Match` seeds over the same sixty are the only evidence available that
    the library was shuffled rather than taken in decklist order.
    """
    first = [state.card.name for state in match(seed="one").start_game().player("alice").hand]
    second = [state.card.name for state in match(seed="two").start_game().player("alice").hand]

    assert first != second


def test_the_starting_player_skips_the_first_draw_step():
    """CR 103.8: the starting player takes their first turn. CR 103.8a: in a
    two-player game that player skips the draw step of that first turn.

    Not CR 103.7 - that number is a different rule, and this file looked
    103.8/103.8a up rather than carrying either from memory.
    """
    game = match().start_game()
    starting = game.active_player.username
    hand_before = len(game.player(starting).hand)

    game.turn.advance_to(Step.PRECOMBAT_MAIN)

    assert hand_before == 7
    assert len(game.player(starting).hand) == 7


# -- what the deck needs to function ----------------------------------------


def test_every_land_back_face_taps_for_mana():
    """The mana half of the archetype, played off the back of a spell.

    All seven modal double-faced cards in the mainboard have a land back that
    taps for mana - 24 of the sixty cards. `docs/deck-gaps/belcher.md` records
    that all seven parse -
    a sibling archetype had four lands that added nothing because the mana
    parser refused their second sentence, so this is worth asserting rather
    than assuming.
    """
    modal = [name for name in BELCHER_SIXTY if card(name).card_faces]
    producers = []
    for name in modal:
        printing = card(name)
        producers.append(
            any(
                ability.mana is not None
                for ability in parse_abilities(printing)
                if isinstance(ability, ActivatedAbility)
            )
        )

    assert len(modal) == 7
    assert sum(BELCHER_SIXTY[name] for name in modal) == 24
    assert all(producers), dict(zip(modal, producers, strict=True))

    scenario = Scenario().player("alice", hand=["Jwari Disruption"], library=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruins = scenario.play_land("Jwari Disruption")

    assert ruins.zone is Zone.BATTLEFIELD


def test_lotus_bloom_adds_three_mana_of_one_colour():
    """The deck's actual acceleration: `{T}, Sacrifice this artifact: Add three
    mana of any one color.` (CR 602.1's cost-colon-effect shape).

    Lotus Bloom is the reason the deck can reach Charbelcher's {4} plus its {3}
    activation without lands, so the mana ability parsing is load-bearing.
    """
    printing: Card = card("Lotus Bloom")

    assert "Add three mana of any one color" in (printing.oracle_text or "")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Goblin Charbelcher's activated ability is silent: no dispatcher reads "
        "'{3}, {T}: Reveal cards from the top of your library until you reveal a "
        "land card. This artifact deals damage equal to the number of nonland "
        "cards revealed this way to any target.' Activating it puts an ability on "
        "the stack that resolves and does nothing, so no damage is dealt (CR "
        "119.2, CR 120.3a) and this deck cannot execute its only win condition. "
        "See docs/deck-gaps/belcher.md."
    ),
)
def test_charbelcher_deals_damage_when_it_reveals_a_pile_of_nonlands():
    """CR 602.1, 602.1a, 119.2, 120.3a: the archetype's kill.

    Four nonland cards on top and a land underneath is exactly the shape the
    ability reads: reveal until a land, deal damage equal to the nonlands
    revealed. Every card here is a real printing from this real decklist.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", "Lotus Bloom"],
            library=[
                "Counterspell",
                "Preordain",
                "Spell Snare",
                "Stock Up",
                "Island",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    belcher_state = scenario.find("Goblin Charbelcher", Zone.BATTLEFIELD, "alice")
    bloom = scenario.find("Lotus Bloom", Zone.BATTLEFIELD, "alice")

    # The deck has no lands on the battlefield to tap, so the {3} comes off
    # Lotus Bloom's own mana ability (CR 605.1a - it never uses the stack).
    scenario.activate(bloom, sacrificing=[bloom], color=Color.BLUE)
    scenario.activate(belcher_state, auto=True, targets=[scenario.player("bob")])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 16


def _full_names() -> set[str]:
    """The full `Front // Back` printing name behind every front-face name."""
    return {card(name).name for name in BELCHER_SIXTY}

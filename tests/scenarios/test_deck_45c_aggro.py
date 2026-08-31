"""The Modern "45c aggro" deck: it registers, it deals a game, and its lands
actually make mana.

The decklist is a real tournament list - **pilot Pleyboy, 2026-08-29, source
deck `videre-58655679`** - pulled with `statistics_decks(format="modern",
archetype_name="45c aggro", ...)` and legality-checked with
`resolve_cards(format="modern", fields="legality")` in the session that wrote
this. The same sixty and fifteen are in the API repo as `decks/45c_aggro.txt`.

A four-or-five-colour deck lives or dies on whether the manabase produces the
right colours, so the bulk of this file is the land-by-land check rather than
the opening-hand arithmetic: a land whose second sentence the mana parser
refuses would produce **nothing at all** while every other test still passed.

The engine gaps this deck exposes are written up in
`docs/deck-gaps/45c-aggro.md`; the three that stop this from being a working
five-colour deck are `xfail(strict=True)` at the bottom of this file.

CR numbers looked up with `knowledge_search(type="rules")` in the session that
wrote this file:

- **CR 100.2a** - "In constructed play ... each deck has a minimum deck size of
  60 cards. A constructed deck may contain any number of basic land cards and
  no more than four of any card with a particular English name other than basic
  land cards."
- **CR 100.4a** - "In constructed play, a sideboard may contain no more than
  fifteen cards. The four-card limit (see rule 100.2a) applies to the combined
  deck and sideboard."
- **CR 103.2a** - "If any players are using sideboards ... those cards are set
  aside."
- **CR 103.3** - "each player shuffles their deck so that the cards are in a
  random order."
- **CR 103.4** - "Each player begins the game with a starting life total of 20."
- **CR 103.5** - "Each player draws a number of cards equal to their starting
  hand size, which is normally seven."
- **CR 401.1** - "When a game begins, each player's deck becomes their library."
- **CR 305.1** - "A player who has priority may play a land card from their hand
  during a main phase of their turn when the stack is empty. Playing a land is a
  special action; it doesn't use the stack."
- **CR 305.6** - "The basic land types are Plains, Island, Swamp, Mountain, and
  Forest ... An object with the land card type and a basic land type has the
  intrinsic ability [to tap for the matching mana]."
- **CR 605.1a** - an activated ability is a mana ability if "it doesn't require
  a target ..., it could add mana to a player's mana pool when it resolves,
  [and] it's not a loyalty ability."
- **CR 605.3b** - "An activated mana ability doesn't go on the stack ... it
  resolves immediately after it is activated."
- **CR 613.1d** - "Layer 4: Type-changing effects are applied."
- **CR 614.1c** - "Effects that read '[This permanent] enters with . . . ,' 'As
  [this permanent] enters . . . ,' or '[This permanent] enters as . . .' are
  replacement effects."
- **CR 614.12a** - "If a replacement effect that modifies how a permanent enters
  the battlefield requires a choice, that choice is made before the permanent
  enters the battlefield."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Deck, Match, Player, Zone
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

#: 45c aggro, pilot Pleyboy, tournament date 2026-08-29, source deck
#: `videre-58655679`. Sixty cards; every name resolved legal in Modern.
MAINBOARD = {
    "Phelia, Exuberant Shepherd": 3,
    "Territorial Kavu": 4,
    "Scion of Draco": 4,
    "Lightning Bolt": 4,
    "Arena of Glory": 2,
    "Flooded Strand": 4,
    "Mountain": 1,
    "Plains": 1,
    "Temple Garden": 1,
    "Wooded Foothills": 4,
    "Steam Vents": 2,
    "Thundering Falls": 1,
    "Arid Mesa": 4,
    "Indatha Triome": 1,
    "Leyline Binding": 4,
    "Consign to Memory": 2,
    "Quantum Riddler": 4,
    "Blood Crypt": 1,
    "Leyline of the Guildpact": 4,
    "Lush Portico": 1,
    "Teferi, Time Raveler": 1,
    "Ragavan, Nimble Pilferer": 4,
    "Stubborn Denial": 3,
}

#: The registered fifteen.
SIDEBOARD = {
    "Rest in Peace": 1,
    "Wrath of the Skies": 2,
    "Mystical Dispute": 3,
    "Wear // Tear": 1,
    "Obsidian Charmaw": 2,
    "Containment Priest": 1,
    "Consign to Memory": 2,
    "Teferi, Time Raveler": 1,
    "Brotherhood's End": 1,
    "High Noon": 1,
}

#: The opposing sixty, so `start_game` has two real decks to deal from. Also a
#: registered Modern list: **pilot Tetsubou, 2026-08-29, source deck
#: `videre-58655389`** - the same archetype's Tribal Flames build, minus the
#: cards this pool does not carry. It is only here to be shuffled and dealt.
OPPONENT_SIXTY = {
    "Lightning Bolt": 4,
    "Ragavan, Nimble Pilferer": 4,
    "Scion of Draco": 4,
    "Territorial Kavu": 4,
    "Quantum Riddler": 4,
    "Leyline Binding": 4,
    "Leyline of the Guildpact": 4,
    "Stubborn Denial": 2,
    "Arid Mesa": 4,
    "Flooded Strand": 4,
    "Steam Vents": 2,
    "Temple Garden": 1,
    "Thundering Falls": 1,
    "Indatha Triome": 1,
    "Lush Portico": 1,
    "Arena of Glory": 2,
    "Mountain": 7,
    "Plains": 7,
}

#: Every land in the mainboard that prints a `{T}: Add ...` ability, and the
#: colours it must be able to add (CR 305.6 for the ones that get theirs from a
#: basic land type, the printed line for the rest).
MANA_LANDS = [
    ("Mountain", (Color.RED,)),
    ("Plains", (Color.WHITE,)),
    ("Blood Crypt", (Color.BLACK, Color.RED)),
    ("Steam Vents", (Color.BLUE, Color.RED)),
    ("Temple Garden", (Color.GREEN, Color.WHITE)),
    ("Thundering Falls", (Color.BLUE, Color.RED)),
    ("Lush Portico", (Color.GREEN, Color.WHITE)),
    ("Indatha Triome", (Color.WHITE, Color.BLACK, Color.GREEN)),
    ("Arena of Glory", (Color.RED,)),
]

#: The fetchlands. None of them makes mana - their only ability sacrifices them
#: for a land - so "produces nothing" is the correct answer here, not a gap.
FETCHLANDS = ["Arid Mesa", "Flooded Strand", "Wooded Foothills"]


def deck() -> Deck:
    return Deck(mainboard=dict(MAINBOARD), sideboard=dict(SIDEBOARD))


def match(seed: int | str = 45) -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", deck())
    series.register_deck("bob", Deck(mainboard=dict(OPPONENT_SIXTY)))
    return series


# -- the list itself (CR 100.2a, CR 100.4a) -------------------------------


def test_the_registered_list_is_sixty_and_fifteen():
    """CR 100.2a's minimum sixty, CR 100.4a's fifteen-card sideboard."""
    registered = deck()

    assert registered.mainboard_size == 60
    assert sum(SIDEBOARD.values()) == 15
    assert registered.problems(card) == []
    assert registered.is_legal(card)


def test_every_name_in_the_list_is_a_real_printing():
    """No hand-written card json: every name resolves in the fixture pool."""
    for name in list(MAINBOARD) + list(SIDEBOARD):
        printing = card(name)
        assert printing.name == name


def test_the_four_copy_limit_counts_the_sideboard_too():
    """CR 100.4a: "The four-card limit ... applies to the combined deck and
    sideboard." Teferi and Consign to Memory are split across both boards here,
    so this is the list's own live case rather than a constructed one."""
    combined = {}
    for board in (MAINBOARD, SIDEBOARD):
        for name, count in board.items():
            combined[name] = combined.get(name, 0) + count

    assert combined["Teferi, Time Raveler"] == 2
    assert combined["Consign to Memory"] == 4
    assert Deck(mainboard=dict(MAINBOARD), sideboard=dict(SIDEBOARD)).problems(card) == []


# -- dealing a game from it (CR 103) --------------------------------------


def test_a_game_deals_seven_and_leaves_fifty_three():
    """CR 103.5's opening hand of seven, out of CR 401.1's library of sixty."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)


def test_the_opening_hand_is_dealt_from_this_decklist_only():
    """CR 103.3 shuffles *this* deck: nothing from anywhere else can appear."""
    game = match().start_game()
    alice = game.player("alice")

    for state in alice.hand + alice.library:
        assert state.card.name in MAINBOARD
        assert state.owner == "alice"


def test_the_sideboard_is_set_aside_rather_than_shuffled_in():
    """CR 103.2a: sideboard cards are set aside before the deck becomes the
    library, so the fifteen are never among the sixty."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) + len(alice.library) == 60
    assert "Wear // Tear" not in {state.card.name for state in alice.library + alice.hand}


def test_both_players_start_at_twenty():
    """CR 103.4: each player begins the game with a starting life total of 20."""
    game = match().start_game()

    assert game.player("alice").life == 20
    assert game.player("bob").life == 20


def test_the_same_seed_deals_the_same_opening_hand():
    """CR 103.3's shuffle is randomised, not arbitrary: one seed, one game."""
    first = [state.card.name for state in match(seed=7).start_game().player("alice").hand]
    again = [state.card.name for state in match(seed=7).start_game().player("alice").hand]

    assert first == again


# -- the manabase actually makes mana -------------------------------------


@pytest.mark.parametrize(("land", "colors"), MANA_LANDS, ids=[name for name, _ in MANA_LANDS])
def test_each_land_adds_every_colour_it_prints(land: str, colors: tuple[Color, ...]):
    """CR 605.1a's mana ability, read off the real printing.

    This is the check a greedy manabase needs: a land whose *second* sentence
    the parser refuses - "This land enters tapped", a shockland's CR 614.1c
    "As this land enters, you may pay 2 life", Arena of Glory's exert clause -
    must still produce from its first one. A land that produced nothing would
    fail here and nowhere else.
    """
    scenario = Scenario().player("alice", battlefield=[land]).build()
    (source,) = scenario.untapped_sources(land)

    for color in colors:
        assert mana_from(source, color) == [color]


@pytest.mark.parametrize("land", FETCHLANDS)
def test_a_fetchland_makes_no_mana_at_all(land: str):
    """The counterpart: the three fetchlands print no `{T}: Add ...` line, so
    "no mana ability" is the right answer and not a parser miss (CR 605.1a -
    a sacrifice-and-search ability could never add mana)."""
    scenario = Scenario().player("alice", battlefield=[land]).build()
    (source,) = scenario.untapped_sources(land)

    with pytest.raises(ValueError, match="has no mana ability"):
        mana_from(source)


def test_the_manabase_covers_all_five_colours_between_them():
    """The whole point of the archetype: WUBRG off the mainboard's lands."""
    produced: set[Color] = set()
    scenario = Scenario().player("alice", battlefield=[name for name, _ in MANA_LANDS]).build()
    for name, colors in MANA_LANDS:
        source = scenario.find(name, Zone.BATTLEFIELD)
        for color in colors:
            produced.update(mana_from(source, color))

    assert produced == {Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN}


def test_a_land_from_this_deck_can_be_played_as_a_special_action():
    """CR 305.1: playing a land is a special action taken from the hand during
    a main phase with an empty stack - the way every land in this list arrives."""
    scenario = Scenario().player("alice", hand=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.play_land("Mountain")

    assert mountain.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


# -- the gaps this deck exposes (see docs/deck-gaps/45c-aggro.md) ---------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Leyline of the Guildpact's 'Lands you control are every basic land type "
        "in addition to their other types' generates no CR 613.1d layer-4 effect. "
        "The identical sentence is modelled for Dryad of the Ilysian Grove, but only "
        "as a name-keyed LAYER_EFFECTS row, and `parsed_layer_effects` does not read "
        "the shape off oracle text - so the Leyline is inert and CR 305.6's intrinsic "
        "mana abilities are never granted."
    ),
)
def test_leyline_of_the_guildpact_makes_every_land_every_basic_land_type():
    scenario = (
        Scenario().player("alice", battlefield=["Leyline of the Guildpact", "Mountain"]).build()
    )
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)

    subtypes = scenario.game.characteristics_of(mountain).subtypes

    assert {"Plains", "Island", "Swamp", "Mountain", "Forest"} <= set(subtypes)


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Territorial Kavu's domain characteristic-defining ability (CR 604.3) - "
        "'power and toughness are each equal to the number of basic land types among "
        "lands you control' - is not one of `machines/layers.py`'s parsed shapes, so "
        "the Kavu keeps its printed */* and has no power at all."
    ),
)
def test_territorial_kavu_has_power_equal_to_its_domain():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Territorial Kavu", "Mountain", "Plains", "Blood Crypt"])
        .build()
    )
    kavu = scenario.find("Territorial Kavu", Zone.BATTLEFIELD)

    # Mountain, Plains, Blood Crypt (Swamp Mountain): three basic land types.
    assert scenario.game.power_of(kavu) == 3


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Stubborn Denial is silent end to end: neither its 'Counter target "
        "noncreature spell unless its controller pays {1}' clause nor its ferocious "
        "upgrade produces an effect from any dispatcher, so it resolves and does "
        "nothing."
    ),
)
def test_stubborn_denial_counters_a_noncreature_spell():
    from magic_cards_model.machines.effects import effect_for

    printing = card("Stubborn Denial")

    assert effect_for(printing.name, printing.oracle_text or "") is not None

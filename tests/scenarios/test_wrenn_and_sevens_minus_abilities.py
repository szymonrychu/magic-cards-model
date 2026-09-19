"""Scenario: Wrenn and Seven's own -3 and -8.

-3 ("Create a green Treefolk creature token with reach and 'This token's
power and toughness are each equal to the number of lands you control.'")
used to fail closed for two independent reasons, both fixed generally:

1. `machines/effects.py::_parse_token_tail` read a token's "with ..." tail
   as *either* a single quoted ability *or* a comma/"and"-joined list of
   bare keywords, never both together - "reach and '<ability>'" mixes the
   two, and the whole token-creation clause failed to parse at all (no
   token, no keyword, nothing).
2. Even with the token created, its quoted ability - CR 111.3's own
   "power and toughness are each equal to the number of `<type>` you
   control" - is a real, heavily templated "lands matter" shape (Molimo,
   Maro-Sorcerer; Old Man Willow; Titania, Gaea Incarnate; Ulvenwald Hydra;
   Cultivator Colossus; Ashaya, Soul of the Wild are real printings of the
   same sentence) with no reader in `machines/layers.py` at all -
   `_QUALIFIER_COUNT_CDA_RE`/`_qualifier_count_cda_builder` is the new one,
   the general (any CR 205.2a type, not only lands) sibling of
   `_BASIC_LAND_TYPE_COUNT_CDA_RE`'s own domain reader right beside it.

-8 ("Return all permanent cards from your graveyard to your hand. You get
an emblem with 'You have no maximum hand size.'") needed a subsystem this
engine had none of at all: CR 114's emblems. `Player.emblems` is the new
field (CR 109.4c: owned and controlled by the player who gets it, CR 114.5:
not a card and not a permanent, so it lives beside the player rather than
in any zone list); `Player.has_no_maximum_hand_size` reads the emblem text
generally - CR 114.2's own template, "[Player] gets an emblem with
[ability]" - not a card-name gate, so any future emblem-granting card
printing this exact ability text is covered too (Tamiyo, Inquisitive
Student's own -7 prints the identical sentence, already in this pool).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 111.3** - a token's quoted ability is its own printed text, "the
  characteristic value... functionally equivalent to" a printed card's.
- **CR 604.3a** - a characteristic-defining ability "defines an object's
  colors, subtypes, power, or toughness" and "is printed on the card it
  affects" (a token's own granted text counts, CR 111.3).
- **CR 613.4a** - sublayer 7a is where characteristic-defining P/T effects
  apply.
- **CR 613.5** - "you control" is read off the *computed* board as that
  sublayer sees it.
- **CR 109.4c** - "An emblem is controlled by the player who puts it into
  the command zone."
- **CR 114.2** - "[Player] gets an emblem with [ability]... puts an emblem
  with [ability] into the command zone. The emblem is both owned and
  controlled by that player."
- **CR 114.3/114.5** - an emblem has no characteristics but its granted
  ability, is not a card, and is not a permanent.
- **CR 402.2** - "Each player has a maximum hand size, which is normally
  seven cards."
- **CR 514.1/CR 703.4n** - the cleanup step's discard down to maximum hand
  size, which "no maximum hand size" makes moot.
- **CR 700.4/CR 701.19a's neighbour, CR 701.21a's neighbour** - not used
  here; graveyard-to-hand is CR 400.7's ordinary zone change, no keyword
  action of its own.
- **CR 606.4** - a loyalty ability's cost.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def test_wrenn_and_sevens_minus_three_creates_a_landfall_treefolk_token():
    """Four lands on alice's side: the Treefolk's power and toughness are
    each 4, reach is granted, and it is green - none of which existed
    before either fix (no token was created at all).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wrenn and Seven", "Forest", "Forest", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wrenn = scenario.creature("Wrenn and Seven", "alice")

    scenario.activate(wrenn, index=2)
    scenario.resolve_top()

    assert wrenn.loyalty == 2, "CR 606.4: 5 printed, minus 3"
    treefolk = next(
        state
        for state in scenario.game.battlefield
        if state.card.subtypes and "Treefolk" in state.card.subtypes
    )
    assert treefolk.card.colors == [Color.GREEN]
    assert has_keyword(treefolk, Keyword.REACH, scenario.game)
    board = computed(scenario)
    assert board.of(treefolk).power_toughness == (4, 4)


def test_wrenn_and_sevens_minus_three_treefolk_grows_with_more_lands():
    """A fifth land, played after the token exists, still counts - CR
    613.5's "continually and automatically" recomputation, not a value
    fixed when the token was created.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wrenn and Seven", "Forest", "Forest", "Forest"],
            hand=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wrenn = scenario.creature("Wrenn and Seven", "alice")
    scenario.activate(wrenn, index=2)
    scenario.resolve_top()
    treefolk = next(
        state
        for state in scenario.game.battlefield
        if state.card.subtypes and "Treefolk" in state.card.subtypes
    )
    assert computed(scenario).of(treefolk).power_toughness == (3, 3)

    scenario.game.play_land(scenario.find("Forest", Zone.HAND, "alice"), "alice")

    assert computed(scenario).of(treefolk).power_toughness == (4, 4)


def test_wrenn_and_sevens_minus_eight_returns_graveyard_permanents_and_grants_no_max_hand_size():
    """Two permanent cards and one instant in alice's graveyard: only the
    two permanents come back to hand; the instant stays put. The emblem
    then lets alice's hand grow past seven with no cleanup discard.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wrenn and Seven"],
            graveyard=["Grizzly Bears", "Mishra's Bauble", "Lightning Bolt"],
            hand=["Mountain"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wrenn = scenario.creature("Wrenn and Seven", "alice")
    alice = scenario.player("alice")
    # 5 printed -> 10, so paying -8 leaves 2 rather than 0 - CR 704.5i puts a
    # planeswalker at 0 loyalty into its owner's graveyard, which is not
    # what this test is about.
    scenario.game.add_counters(wrenn, Counter.LOYALTY, 5)

    scenario.activate(wrenn, index=3)
    scenario.resolve_top()

    assert wrenn.loyalty == 2, "CR 606.4: 10, minus 8"
    assert {c.name for c in alice.hand if c.name != "Mountain"} == {
        "Grizzly Bears",
        "Mishra's Bauble",
    }
    assert [c.name for c in alice.graveyard] == ["Lightning Bolt"]
    assert alice.has_no_maximum_hand_size
    assert len(alice.emblems) == 1
    assert alice.emblems[0].text == "You have no maximum hand size."

    # CR 514.1/402.2: nine cards in hand, no discard, because CR 613.11's
    # continuous effect on the game rule itself makes the maximum moot.
    assert alice.cards_over_maximum_hand_size == 0

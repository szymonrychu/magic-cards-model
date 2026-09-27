"""Invasion of Alara's Siege ETB: mill until two matching cards are found,
optionally cast one of them for free, put one into hand, bottom the rest.

Card text, confirmed with `resolve_cards` in the session that wrote this
file:

Invasion of Alara (Battle - Siege, defense 7):
    When this Siege enters, exile cards from the top of your library until
    you exile two nonland cards with mana value 4 or less. You may cast one
    of those two cards without paying its mana cost. Put one of them into
    your hand. Then put the other cards exiled this way on the bottom of
    your library in a random order.

A Scryfall search for "you may cast one of those" turns up no other real
printing of this exact multi-card impulse shape, so the count and quality
are still read generally (`{COUNT}`/`_bounded_quality_matcher`, the same
readers every other exile-until quality already uses in
`machines/effects.py`) rather than hardcoded to "two"/"4" - see that
module's own `_EXILE_UNTIL_N_QUALITY_CAST_ONE_FREE_RE` docstring.

Every rule below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 310.12b** - a Siege's own intrinsic defeat trigger; unrelated to this
  ETB, but the reason `Invasion of Alara` alone (never staged pre-transformed)
  is what these tests put on the battlefield.
- **CR 608.2c** - a resolving ability follows its printed instructions, in
  order, as one instruction chain.
- **CR 608.2g** - "If an effect specifically instructs or allows a player to
  cast a spell during resolution, they do so ... without paying its mana
  cost" when the effect says so (CR 118.9).
- **CR 406.1/406.2** - exile is one shared zone; a card there is public
  (CR 406.3) until moved.
- **CR 701.24a** - "shuffle" mixes a pile with no other order implied; the
  cards this ability bottoms are put there "in a random order" instead,
  which is not CR 701.24a's shuffle verb at all (nothing here calls
  `Game.shuffle_library`, matching `puts_graveyard_on_bottom_of_library`'s
  own un-shuffled bottoming for the identical printed phrase).

The printing's own Scryfall rulings (2023-04-14, quoted in
`machines/effects.py`'s own docstring) are what fix what happens to the
*other* matching card once one is cast or handed: it stays in exile forever,
never bottomed - the second test below is built to catch a fix that instead
bottomed it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

ALARA = "Invasion of Alara"


def test_casting_one_free_leaves_the_other_to_hand_and_bottoms_the_mill_fodder():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ALARA],
            library=["Mountain", "Lightning Bolt", "Island", "Grizzly Bears", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")
    swamp = scenario.find("Swamp", Zone.LIBRARY, "alice")

    scenario.put_onto_battlefield(ALARA, "alice")

    scenario.will_take_the_may(True, source=ALARA)
    scenario.will_choose_cards(bolt, username="alice", source=ALARA)
    # `cast_free_from_exile`'s own CHOOSE_TARGETS decision is asked with the
    # card being cast as its source (CR 601.2c), not the ability that grants
    # the cast - the same convention Possibility Storm's own free cast uses.
    scenario.will_choose_targets("bob", username="alice", source="Lightning Bolt")
    scenario.pass_until_resolved()  # the Siege's own ETB
    scenario.pass_until_resolved()  # Lightning Bolt, cast free during resolution

    bob = scenario.player("bob")
    alice = scenario.player("alice")

    assert bolt.zone is Zone.GRAVEYARD, "cast and resolved, dealing its damage"
    assert bob.life == 17

    assert bears.zone is Zone.HAND, "the one match not cast - automatic, only one was left"
    assert bears in alice.hand

    assert mountain.zone is Zone.LIBRARY, "mill fodder, bottomed in a random order"
    assert island.zone is Zone.LIBRARY
    assert mountain in alice.library[-2:]
    assert island in alice.library[-2:]
    assert swamp.zone is Zone.LIBRARY, "never seen by the mill - still on top of the bottomed pair"
    assert alice.library.index(swamp) < alice.library.index(mountain)
    assert alice.library.index(swamp) < alice.library.index(island)


def test_declining_the_cast_leaves_the_unchosen_match_in_exile_forever():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ALARA],
            library=["Mountain", "Lightning Bolt", "Island", "Grizzly Bears", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.LIBRARY, "alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "alice")

    scenario.put_onto_battlefield(ALARA, "alice")

    scenario.will_take_the_may(False, source=ALARA)  # decline the free cast entirely
    scenario.will_choose_cards(bears, username="alice", source=ALARA)  # put Bears into hand
    scenario.pass_until_resolved()

    alice = scenario.player("alice")

    assert bears.zone is Zone.HAND
    assert bears in alice.hand

    assert bolt.zone is Zone.EXILE, (
        "the ruling: 'the one you don't put into your hand will remain in exile. "
        "It won't be put on the bottom of your library.'"
    )

    assert mountain.zone is Zone.LIBRARY
    assert island.zone is Zone.LIBRARY
    assert bolt not in alice.library, "never bottomed, unlike the mill fodder"

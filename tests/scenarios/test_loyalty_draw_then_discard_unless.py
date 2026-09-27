""" "Draw N. Then discard M cards unless you discard a <quality> card." on a
loyalty ability, not only a spell.

Verified this session with `mise run rules:find`:

- **CR 606.2** - "An activated ability with a loyalty symbol in its cost is a
  loyalty ability."
- **CR 118.12a** - "Some spells, activated abilities, and triggered
  abilities read, '[Do something] unless [a player does something else].'
  This means the same thing as '[A player may do something else]. If [that
  player doesn't], [do something].'"

`machines/effects._parse_draw_then_discard_unless` already reads this shape
off a resolving *spell* (Winternight Stories, Mystic Meditation, Thirst for
Identity all print it word for word) through `_DRAW_THEN_DISCARD_UNLESS_RE`.
Nothing about that regex or its predicate reader is spell-specific - CR
118.12a's "unless" reading applies the same way to an activated or triggered
ability - so Invasion of New Phyrexia // Teferi Akosa of Zhalfir's own "+1:
Draw two cards. Then discard two cards unless you discard a creature card."
is the identical mechanic on a loyalty ability instead of a spell, which
`_ability_effect_or_notice` could not read at all before this file's fix.

Teferi Akosa is the only real printing of this exact sentence on an
ability rather than a spell (verified by Scryfall search on the printed
text), so generality is proven the way the mechanic itself is general -
the shared regex/predicate reader already reads three differently-worded
"discard unless" spells - rather than by a second ability-bearing card,
which does not exist in print.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TEFERI = "Invasion of New Phyrexia // Teferi Akosa of Zhalfir"


def _teferi_board(**alice_kwargs) -> Scenario:
    return Scenario().player("alice", **alice_kwargs).player("bob")


def test_plus_one_draws_two_then_discards_a_chosen_creature_card_instead_of_two():
    """CR 118.12a: declared "unless", so a creature card offered and chosen
    to discard replaces the two-card discard entirely."""
    scenario = _teferi_board(
        hand=[TEFERI, "Grizzly Bears", "Mountain", "Island"],
        library=["Forest", "Plains", "Swamp", "Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Phyrexia", Zone.HAND, "alice")
    teferi = scenario.game.put_onto_battlefield(card, "alice", transformed=True)
    hand_before = list(scenario.player("alice").hand)

    scenario.will_take_the_may(True, username="alice", source="Teferi Akosa of Zhalfir")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    scenario.will_choose_cards(bears, username="alice", source="Teferi Akosa of Zhalfir")
    scenario.activate(teferi, index=0, username="alice")
    scenario.pass_until_resolved()

    hand = scenario.player("alice").hand
    assert bears not in hand
    assert bears.zone is Zone.GRAVEYARD
    # Drew 2 (Forest, Plains), discarded exactly the chosen creature (1
    # card), so the hand grew from 3 (Mountain/Island/Bears, Teferi cast
    # away) by 2 drawn minus 1 discarded = net +1.
    assert len(hand) == len(hand_before) + 2 - 1
    for card_state in hand_before:
        if card_state.name != "Grizzly Bears":
            assert card_state in hand


def test_plus_one_discards_two_when_declining_the_creature_card():
    """Declining the "unless" branch (CR 118.12a) falls through to the plain
    two-card discard."""
    scenario = _teferi_board(
        hand=[TEFERI, "Grizzly Bears", "Mountain", "Island"],
        library=["Forest", "Plains", "Swamp", "Grizzly Bears"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Phyrexia", Zone.HAND, "alice")
    teferi = scenario.game.put_onto_battlefield(card, "alice", transformed=True)

    scenario.will_take_the_may(False, username="alice", source="Teferi Akosa of Zhalfir")
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    island = scenario.find("Island", Zone.HAND, "alice")
    scenario.will_discard(mountain, island, username="alice")
    scenario.activate(teferi, index=0, username="alice")
    scenario.pass_until_resolved()

    hand = scenario.player("alice").hand
    assert mountain.zone is Zone.GRAVEYARD
    assert island.zone is Zone.GRAVEYARD
    names = sorted(state.name for state in hand)
    assert names == ["Forest", "Grizzly Bears", "Plains"]


def test_plus_one_falls_through_with_no_creature_card_to_offer():
    """No creature card in hand: nothing to offer at all (CR 608.2d), so the
    plain discard happens without a `MAY` question ever being asked."""
    scenario = _teferi_board(
        hand=[TEFERI, "Mountain", "Island"],
        library=["Forest", "Plains", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Invasion of New Phyrexia", Zone.HAND, "alice")
    teferi = scenario.game.put_onto_battlefield(card, "alice", transformed=True)

    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    island = scenario.find("Island", Zone.HAND, "alice")
    scenario.will_discard(mountain, island, username="alice")
    scenario.activate(teferi, index=0, username="alice")
    scenario.pass_until_resolved()

    hand = scenario.player("alice").hand
    assert mountain.zone is Zone.GRAVEYARD
    assert island.zone is Zone.GRAVEYARD
    names = sorted(state.name for state in hand)
    assert names == ["Forest", "Plains"]

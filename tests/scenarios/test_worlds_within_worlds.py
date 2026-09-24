"""Worlds Within Worlds (task C02-T7): "Exile all creatures. Each player may
put any number of creature cards from their hand onto the battlefield. Then
put all cards exiled this way into their owners' hands. Exile Worlds Within
Worlds."

Four CR 608.2c instructions in sequence, each already generalized past the
one printing that exposed the shape:

1. A mass exile with no target, `_EXILE_ALL_CREATURES_THEN_HAND_REFILL_RE`'s
   own antecedent, is the same primitive Containment Construct's own "Exile
   all creatures" (`test_exile_and_cast_msh.py`) reads for a static effect
   rather than a one-shot; here it is one-shot.
2. "Each player may put any number of creature cards from their hand onto
   the battlefield" is a wholly separate pool of cards (hand, not what was
   just exiled) - opting into it never reduces what step 3 returns.
3. "Then put all cards exiled this way into their owners' hands" reads
   `state.zone is Zone.EXILE` on every creature step 1 actually exiled
   (CR 111.8: a token that couldn't move is skipped, since it never has a
   hand to return to), independent of step 2's own choices.
4. "Exile Worlds Within Worlds" is CR 201.5's plain self-reference, the same
   primitive Burning Wish's identical closing sentence already reads
   (`_resolve_top`'s own `spell.zone is Zone.EXILE` check).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2c** - a resolving spell performs its instructions in order.
- **CR 111.8** - a token that would change zones and can't stays put.
- **CR 601.2i/608.3** - the spell is on the stack, then a permanent, as its
  own instructions run; CR 201.5's self-reference names it by its own
  printed name either way.
- **CR 700.2** - "may" leaves each choice up to the player it addresses,
  independently.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_each_players_creatures_are_exiled_then_returned_to_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Worlds Within Worlds", "Grizzly Bears"],
            battlefield=[
                "Craw Wurm",
                "Forest",
                "Island",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", hand=["Llanowar Elves"], battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    craw_wurm = scenario.creature("Craw Wurm", "alice")
    elvish_mystic = scenario.creature("Elvish Mystic", "bob")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    elves = scenario.find("Llanowar Elves", Zone.HAND, "bob")
    sources = scenario.untapped_sources(
        "Forest", "Island", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    # alice opts in and puts Grizzly Bears onto the battlefield; bob declines.
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bears, source="Worlds Within Worlds", username="alice")
    scenario.will_take_the_may(False, username="bob")

    casting = scenario.cast("Worlds Within Worlds")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # Both original battlefield creatures were exiled and then returned to
    # their owners' hands, regardless of what either player did with the
    # separate "put a creature card from hand" choice.
    assert craw_wurm.zone is Zone.HAND
    assert craw_wurm.owner == "alice"
    assert elvish_mystic.zone is Zone.HAND
    assert elvish_mystic.owner == "bob"

    # alice's own choice put Grizzly Bears onto the battlefield for free.
    assert bears.zone is Zone.BATTLEFIELD

    # bob declined, so Llanowar Elves is still sitting in his hand.
    assert elves.zone is Zone.HAND

    # Worlds Within Worlds exiled itself (CR 201.5 self-reference).
    worlds = scenario.find("Worlds Within Worlds", Zone.EXILE)
    assert worlds.zone is Zone.EXILE


def test_a_player_with_no_creatures_on_either_side_is_unaffected():
    """CR 111.8/700.2's own edge: a player offered the "may" with nothing in
    hand to put down, and a battlefield with nothing exiled from it, is
    simply asked nothing further - the instruction still resolves cleanly."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Worlds Within Worlds"],
            battlefield=[
                "Forest",
                "Island",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Forest", "Island", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )

    casting = scenario.cast("Worlds Within Worlds")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    worlds = scenario.find("Worlds Within Worlds", Zone.EXILE)
    assert worlds.zone is Zone.EXILE
    assert scenario.player("alice").hand == []

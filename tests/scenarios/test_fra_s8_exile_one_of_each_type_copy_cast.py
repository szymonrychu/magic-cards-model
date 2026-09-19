"""FRA stream S8: "Exile up to one target nonland card of each card type
from your graveyard. Copy those cards. You may cast any number of spells
with total mana value `<n>` or less from among the copies without paying
their mana costs." (CR 601.2c's per-type targets, CR 707.2/707.12's copying
and casting a copy, CR 707.12a's individual per-object choice.)

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 601.2c** - target announcement; "of each card type" reads as one
  independent "up to one" requirement per nonland CR 300.1 type
  (`machines/targeting.py`'s own `_up_to_one_of_each_card_type_profile`).
- **CR 707.2** - copying: the copy acquires the original's copiable values.
- **CR 707.12** - casting a copy of an object during resolution follows the
  ordinary casting steps.
- **CR 707.12a** - "allows that player to choose individually, for each of
  those objects, whether or not to cast it."
- **CR 707.10a** - a copy of a card in a zone other than the stack or the
  battlefield ceases to exist - any copy never cast.
- **CR 111.13 / CR 707.10f** - a copy of a permanent spell becomes a token
  as it resolves.
- **CR 112.2a** - the owner of a cast copy is whoever was given permission
  to cast it.

Uldaros Theorix's own ETB is the reported card. It is the only card in the
pool with this shape, so there is no off-set proof for the whole merged
clause; the two capabilities it composes are each proven general on their
own elsewhere in this stream's own work - `_up_to_one_of_each_card_type_
profile` is itself the general targeting reader (not keyed to this card's
name), and the copy-then-cast-during-resolution machinery is the same
`Game.exile_cards`/`Game.may_cast_during_resolution` funnel Isochron
Scepter's own "copy the exiled card. If you do, you may cast the copy
without paying its mana cost" already uses.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_uldaros_theorix_exiles_copies_and_casts_both_within_budget():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Uldaros Theorix"],
            battlefield=["Island", "Swamp", "Swamp", "Forest", "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Swamp", "Swamp", "Forest", "Forest", "Forest")
    bob = scenario.player("bob")
    bob_life_before = bob.life

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    # In order: the ETB's own CR 601.2c target announcement, then (CR
    # 707.12a) one MAY per copy in the order the copies were made (the
    # target-resolution order), then Lightning Bolt copy's own "any target".
    scenario.will_choose_targets(bears, bolt, username="alice")
    scenario.will_take_the_may(True, times=2)
    scenario.will_choose_targets("bob", username="alice")

    scenario.cast_and_resolve("Uldaros Theorix", *sources)
    scenario.game.put_triggers_on_stack()
    # CR 608.2g: each copy cast during resolution goes on top of the stack
    # and "the currently resolving spell or ability continues to resolve" -
    # both copies end up stacked on top of the ETB ability itself, so
    # finishing the whole instruction takes one resolution pass per object,
    # not one.
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.EXILE, "CR 701.13a: the original, not the copy"
    assert bolt.zone is Zone.EXILE

    bear_token = next(
        (p for p in scenario.game.battlefield if p.name == "Grizzly Bears" and p.token), None
    )
    assert bear_token is not None
    assert bear_token.zone is Zone.BATTLEFIELD
    assert bear_token.token, "CR 111.13: a copy of a permanent spell becomes a token as it resolves"

    assert bob.life == bob_life_before - 3, "the Lightning Bolt copy resolved for its usual 3"

    # CR 707.10a: no copy is left sitting in exile once the ability is done
    # offering them - both were cast, so nothing remains to clean up, but the
    # check proves the cleanup ran rather than merely that nothing was left.
    assert not any(card.is_copy and card.zone is Zone.EXILE for card in scenario.game.exile)


def test_uldaros_theorix_declines_the_second_copy():
    """CR 707.12a's own choice is per object: declining the Lightning Bolt
    copy leaves the Grizzly Bears copy cast, and the declined copy ceases to
    exist (CR 707.10a) rather than lingering in exile."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Uldaros Theorix"],
            battlefield=["Island", "Swamp", "Swamp", "Forest", "Forest", "Forest"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Swamp", "Swamp", "Forest", "Forest", "Forest")
    bob = scenario.player("bob")
    bob_life_before = bob.life

    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    scenario.will_choose_targets(bears, bolt, username="alice")
    scenario.will_take_the_may(True, times=1)
    scenario.will_take_the_may(False, times=1)

    scenario.cast_and_resolve("Uldaros Theorix", *sources)
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    bear_token = next(
        (p for p in scenario.game.battlefield if p.name == "Grizzly Bears" and p.token), None
    )
    assert bear_token is not None
    assert bob.life == bob_life_before, "the Lightning Bolt copy was declined"
    assert not any(
        card.is_copy and card.name == "Lightning Bolt" for card in scenario.game.exile
    ), "CR 707.10a: the declined copy ceased to exist rather than lingering"

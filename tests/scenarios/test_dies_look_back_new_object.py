"""Scenario: the CR 400.7/400.7e fix shared by every dead-self reader in
`machines/effects.py`'s dead-self family (`_dead_self_found`) - proved here
on the two siblings that predate G6's own library-placement reader:
`_parse_exile_dead_self_clause`'s "exile it" (Ancient Adamantoise) and
`_parse_return_dead_self_to_hand_clause`'s "return it to its owner's hand"
(Rancor).

Before this fix, both readers checked only `source.zone is not Zone.
BATTLEFIELD` - true of an object sitting in exile just as much as one still
in the graveyard, so a card a graveyard-hate printing had already exiled in
response to the dies trigger was touched a second time: Ancient Adamantoise
was re-exiled (a fresh, unwarranted CR 400.7 zone-change stamp on an object
already accounted for), and Rancor was pulled straight out of exile and into
its owner's hand - a real, visible bug (see `test_dies_trigger_self_
reference.py` for the plain, uninterrupted case both readers already
handled correctly).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.4** - "dies" means "is put into a graveyard from the
  battlefield."
- **CR 603.10a** - a dies trigger looks back in time at the object as it
  last existed.
- **CR 400.7** - an object that moves from one zone to another becomes a
  new object with no memory of, or relation to, its previous existence.
- **CR 400.7e** - a look-back ability "can find the new object that it
  became in the zone it moved to when the ability triggered, if that zone
  is a public zone" - the graveyard the dies event just put it into, and
  only that incarnation.

Card text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Ancient Adamantoise**: "When this creature dies, exile it and create ten
  tapped Treasure tokens."
- **Rancor**: "When Rancor is put into a graveyard from the battlefield,
  return Rancor to its owner's hand."
- **Tormod's Crypt** (the real pool graveyard-hate printing used to exile a
  dead creature's graveyard incarnation in response): "{T}, Sacrifice this
  artifact: Exile target player's graveyard."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ancient_adamantoise_exiled_from_graveyard_in_response_is_not_touched_again():
    """CR 400.7/400.7e: by the time Adamantoise's own "exile it" resolves,
    Tormod's Crypt has already made it a new object in exile - not the
    incarnation the dies event stamped - so the clause finds nothing and
    leaves it exactly where the Crypt put it. The Treasure creation is an
    independent CR 608.2c clause and still happens either way."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ancient Adamantoise"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turtle = scenario.creature("Ancient Adamantoise", "alice")

    scenario.game.destroy(turtle)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")

    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert turtle.zone is Zone.EXILE
    stamp_after_the_crypt = turtle.zone_change_stamp
    exile_count_after_the_crypt = len(scenario.game.exile)

    scenario.resolve_top()  # Adamantoise's own dies trigger: nothing left to exile

    assert turtle.zone is Zone.EXILE
    assert turtle.zone_change_stamp == stamp_after_the_crypt, "not touched a second time"
    assert len(scenario.game.exile) == exile_count_after_the_crypt
    treasures = [
        state
        for state in scenario.game.battlefield
        if state.name == "Treasure Token" and state.controller == "alice"
    ]
    assert len(treasures) == 10, "the Treasure clause is independent and still runs"


def test_rancor_exiled_from_graveyard_in_response_does_not_return_to_hand():
    """The same CR 400.7e response case, on the destination the old, looser
    check actually got wrong: before the fix, Rancor was pulled straight out
    of exile and into Alice's hand; after it, an object the trigger can no
    longer find is left exactly where the Crypt put it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Rancor"], battlefield=["Forest", "Grizzly Bears"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest")
    rancor = scenario.cast_and_resolve("Rancor", forest, targets=[bears])
    assert rancor.zone is Zone.BATTLEFIELD

    scenario.game.destroy(rancor)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")

    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert rancor.zone is Zone.EXILE

    scenario.resolve_top()  # Rancor's own dies trigger: nothing left to return

    assert rancor.zone is Zone.EXILE, "the old bug pulled it into hand here"
    assert rancor not in scenario.player("alice").hand

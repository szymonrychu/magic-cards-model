"""Scenario: G6's dead-object-to-library family - "put it on the top/bottom
of its owner's library" (Murderous Rider, Dark Revenant, Fell Horseman) and
"shuffle it into its owner's library[, then scry N]" (Cavalier of Gales) -
CR 603.10a's own look-back "it", read the same way `_parse_exile_dead_self_
clause`'s "exile it" already is, alongside the CR 400.7/400.7e look-back
fix this same reader carries from day one (`_dead_self_found`,
`machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 700.4** - "dies" means "is put into a graveyard from the
  battlefield" - naming no card type, so an Aura or a permanent under
  another player's control dies the same way a creature under its owner's
  own control does.
- **CR 603.10a** - a dies trigger looks back in time at the object as it
  last existed, which is what lets its own ability still find and move "it"
  once the object itself already sits in the graveyard.
- **CR 108.3** - the owner of a card is who started the game with it in
  their deck, unaffected by who controls it later (CR 108.4's controller is
  a different question) - Murderous Rider's own "its owner's library" sends
  the card to whoever owns it, not whoever controlled it when it died.
- **CR 400.7** - an object that moves from one zone to another becomes a
  new object with no memory of, or relation to, its previous existence.
- **CR 400.7e** - a look-back ability "can find the new object that it
  became in the zone it moved to when the ability triggered, if that zone
  is a public zone" - the graveyard the dies event just put it into, and
  only that incarnation, not wherever the card has gone since.
- **CR 701.24c** - "If an effect would cause a player to shuffle one or
  more specific objects into a library, that library is shuffled even if
  none of those objects are in the zone they're expected to be in" -
  Cavalier of Gales's own "shuffle it into its owner's library" still
  shuffles even when the trigger cannot find "it" any more.
- **CR 111.7/111.8** - a token that is not on the battlefield ceases to
  exist as a state-based action, and one that has already left the
  battlefield can't move to another zone at all - a token copy of one of
  these cards dying has nowhere for "put it .../shuffle it ..." to send it.

Card text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Murderous Rider // Swift End**: "When this creature dies, put it on the
  bottom of its owner's library."
- **Dark Revenant**: "When this creature dies, put it on top of its owner's
  library."
- **Cavalier of Gales**: "When this creature dies, shuffle it into its
  owner's library, then scry 2."
- **Fell Horseman // Deathly Ride**: "When this creature dies, put it on
  the bottom of its owner's library."
- **Tormod's Crypt** (the real pool graveyard-hate printing used to exile a
  dead creature's graveyard incarnation in response): "{T}, Sacrifice this
  artifact: Exile target player's graveyard."
- **Act of Treason** (the real pool control-change printing used to prove
  "its owner's library" reads the owner, not the controller): "Gain control
  of target creature until end of turn. Untap that creature. It gains
  haste until end of turn."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import token_copy_of
from tests.scenarios.harness import Scenario


def test_murderous_rider_goes_to_bottom_of_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Murderous Rider"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rider = scenario.creature("Murderous Rider", "alice")

    scenario.game.destroy(rider)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert rider.zone is Zone.LIBRARY
    alice = scenario.player("alice")
    assert alice.library[-1] is rider
    assert [state.name for state in alice.library[:-1]] == ["Forest", "Island"]


def test_murderous_rider_goes_to_its_owners_library_even_controlled_by_another_player():
    """CR 108.3: "its owner's library" is Alice's, not Bob's, even though
    Bob controls the Rider when it dies (Act of Treason's own control
    change, until end of turn - CR 108.4's controller is a different
    question from ownership)."""
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Act of Treason"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Island"],
        )
        .player("alice", battlefield=["Murderous Rider"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's own main phase, so his sorcery is legal
    rider = scenario.creature("Murderous Rider", "alice")
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob")
    scenario.cast_and_resolve("Act of Treason", *mountains, username="bob", targets=[rider])
    assert rider.controller == "bob"
    assert rider.owner == "alice"

    scenario.game.destroy(rider)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert rider.zone is Zone.LIBRARY
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert rider in alice.library
    assert rider not in bob.library
    assert alice.library[-1] is rider


def test_dark_revenant_goes_to_top_of_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dark Revenant"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    revenant = scenario.creature("Dark Revenant", "alice")

    scenario.game.destroy(revenant)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert revenant.zone is Zone.LIBRARY
    alice = scenario.player("alice")
    assert alice.library[0] is revenant
    assert [state.name for state in alice.library[1:]] == ["Forest", "Island"]


def test_fell_horseman_goes_to_bottom_of_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fell Horseman"], library=["Forest", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    horseman = scenario.creature("Fell Horseman", "alice")

    scenario.game.destroy(horseman)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert horseman.zone is Zone.LIBRARY
    alice = scenario.player("alice")
    assert alice.library[-1] is horseman


def test_cavalier_of_gales_is_shuffled_in_and_then_its_owner_scries():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cavalier of Gales"], library=["Forest", "Island", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    cavalier = scenario.creature("Cavalier of Gales", "alice")
    shuffles_before = scenario.game.shuffles_performed
    library_size_before = len(alice.library)
    # Order-agnostic: legal regardless of what the shuffle actually put on
    # top, since this test is not trying to predict a seeded shuffle's
    # output, only that a scry genuinely happened.
    scenario.scry_keeping_everything_on_top(username="alice")

    scenario.game.destroy(cavalier)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert cavalier.zone is Zone.LIBRARY
    assert len(alice.library) == library_size_before + 1
    assert cavalier in alice.library
    assert scenario.game.shuffles_performed == shuffles_before + 1, "CR 701.24a: shuffled in"
    assert "alice" in scenario.game.turn_facts.get("scried_or_surveilled", ())


def test_murderous_rider_exiled_from_graveyard_in_response_does_not_move():
    """CR 400.7/400.7e: Tormod's Crypt exiles Alice's graveyard - including
    the Rider - while the Rider's own dies trigger is still on the stack.
    By the time that trigger resolves, the Rider is a new object in exile,
    not the incarnation the dies event stamped, so CR 608.2c's instruction
    finds nothing and does nothing."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Murderous Rider"], library=["Forest"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rider = scenario.creature("Murderous Rider", "alice")

    scenario.game.destroy(rider)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")

    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert rider.zone is Zone.EXILE

    scenario.resolve_top()  # the Rider's own dies trigger, nothing left to move

    assert rider.zone is Zone.EXILE, "an ability whose card has moved on does nothing"
    assert rider not in scenario.player("alice").library


def test_cavalier_of_gales_exiled_from_graveyard_in_response_still_shuffles_and_scries():
    """The same CR 400.7e response case as Murderous Rider's own, but for
    the shuffle destination: CR 701.24c means the shuffle - and the
    trailing scry, an independent clause of its own (CR 608.2c) - still
    happen even though Cavalier itself is no longer found."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Cavalier of Gales"], library=["Forest", "Island"])
        .player("bob", battlefield=["Tormod's Crypt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    cavalier = scenario.creature("Cavalier of Gales", "alice")
    shuffles_before = scenario.game.shuffles_performed
    scenario.scry_keeping_everything_on_top(username="alice")

    scenario.game.destroy(cavalier)
    scenario.game.put_triggers_on_stack()
    scenario.pass_priority("alice")

    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "bob")
    scenario.activate(crypt, username="bob", targets=["alice"])
    scenario.resolve_top()  # the Crypt exiles alice's graveyard

    assert cavalier.zone is Zone.EXILE

    scenario.resolve_top()  # Cavalier's own dies trigger: shuffles and scries anyway

    assert cavalier.zone is Zone.EXILE, "not found any more, so not moved"
    assert cavalier not in alice.library
    assert scenario.game.shuffles_performed == shuffles_before + 1, "CR 701.24c: shuffles anyway"
    assert "alice" in scenario.game.turn_facts.get("scried_or_surveilled", ())


def test_murderous_rider_leaves_and_returns_to_the_graveyard_as_a_new_object():
    """CR 400.7: even back in the very same graveyard, the Rider that
    returns from hand is a new object - not the incarnation the original
    dies event stamped - so the still-pending trigger finds nothing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Murderous Rider"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rider = scenario.creature("Murderous Rider", "alice")

    scenario.game.destroy(rider)
    scenario.game.put_triggers_on_stack()
    assert rider.zone is Zone.GRAVEYARD
    stamp_when_it_died = rider.zone_change_stamp

    scenario.game.return_to_hand(rider)
    scenario.game.discard_cards("alice", [rider])
    assert rider.zone is Zone.GRAVEYARD
    assert rider.zone_change_stamp != stamp_when_it_died

    scenario.pass_until_resolved()

    assert rider.zone is Zone.GRAVEYARD, "a fresh CR 400.7 object, not the one that died"
    assert rider not in scenario.player("alice").library


def test_token_copy_dying_does_nothing():
    """CR 111.7/111.8: a token copy of Murderous Rider has nowhere to send
    "it" - it either ceases to exist before the trigger resolves, or, if
    still found, cannot move to a library at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Murderous Rider"], library=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rider = scenario.creature("Murderous Rider", "alice")
    (token,) = token_copy_of(scenario.game, rider, "alice")
    alice = scenario.player("alice")
    library_size_before = len(alice.library)

    scenario.game.destroy(token)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert token not in alice.library
    assert len(alice.library) == library_size_before

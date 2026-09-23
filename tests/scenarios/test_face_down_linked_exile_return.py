"""Scenario: cards exiled face down with a permanent, turned face up and put
onto the battlefield by its linked ability (CR 607.2a, CR 406.3).

Pyxis of Pandemonium: "{T}: Each player exiles the top card of their library
face down.\n{7}, {T}, Sacrifice this artifact: Each player turns face up all
cards they own exiled with this artifact, then puts all permanent cards among
them onto the battlefield."

- CR 406.3 / CR 406.3a: "Cards 'exiled face down' can't be examined by any
  player except when instructions allow it" and "a card exiled face down has
  no characteristics" - so until the second ability turns them over they have
  no name, type or mana value.
- CR 607.2a: the second ability reads only the cards the first one exiled -
  a second Pyxis's pile stays face down.
- CR 400.7: Pyxis is sacrificed as part of the cost (CR 602.2), so by the
  time the ability resolves it is a new object in the graveyard; the ability
  still reads the pile of the object it was activated from (CR 113.7a).
- CR 110.4a: "permanent card" - artifact, battle, creature, enchantment,
  land, or planeswalker. An instant stays in exile, now face up.
- CR 110.2a: "If an effect instructs a player to put an object onto the
  battlefield, that object enters the battlefield under that player's
  control" - each player puts their own cards, so each enters under its
  owner's control.

A card_search for "turns face up all cards" on 2026-09-23 found Pyxis alone;
no second printing carries this template, recorded in MEMORY.md.

CR numbers verified with `mise run rules:find` this session: 406.3, 406.3a,
607.2a, 400.7, 602.2, 113.7a, 110.4a, 110.2a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState, ExileMarker

from .harness import PlayedScenario, Scenario


def _board(*, alice_library: list[str], bob_library: list[str], pyxes: int = 1):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[*["Pyxis of Pandemonium"] * pyxes, *["Mountain"] * 7],
            library=[*alice_library, *["Mountain"] * 6],
        )
        .player("bob", library=[*bob_library, *["Forest"] * 6])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _exile_face_down(scenario: PlayedScenario, pyxis: CardState) -> list[CardState]:
    tops = [scenario.player(name).library[0] for name in ("alice", "bob")]
    scenario.activate(pyxis, index=0)
    scenario.pass_until_resolved()
    return tops


def _alices_next_main_phase(scenario: PlayedScenario) -> None:
    start = scenario.game.turn.turns_taken
    for _ in range(80):
        scenario.advance()
        if (
            scenario.game.turn.turns_taken > start + 1
            and scenario.turn.active_player == "alice"
            and scenario.step is Step.PRECOMBAT_MAIN
        ):
            return
    raise AssertionError("never reached alice's next main phase")


def _sacrifice(scenario: PlayedScenario, pyxis: CardState) -> None:
    mountains = scenario.untapped_sources(*["Mountain"] * 7, username="alice")
    scenario.activate(pyxis, *mountains, index=1, sacrificing=[pyxis])
    scenario.pass_until_resolved()


def test_each_player_exiles_their_top_card_face_down_with_no_characteristics():
    scenario = _board(alice_library=["Grizzly Bears"], bob_library=["Llanowar Elves"])
    (pyxis,) = scenario.game.permanents_controlled_by("alice")[:1]
    bears, elves = _exile_face_down(scenario, pyxis)

    for card in (bears, elves):
        assert card.zone is Zone.EXILE
        assert not card.face_up
        assert card.has_no_characteristics, "CR 406.3a"
        assert card.types == ()
        assert card.exile_annotation is not None
        assert card.exile_annotation.marker is ExileMarker.LINKED
        assert card.exile_annotation.linked_permanent_id == pyxis.id


def test_sacrificing_it_puts_each_permanent_card_onto_the_battlefield_under_its_owner():
    scenario = _board(alice_library=["Grizzly Bears"], bob_library=["Llanowar Elves"])
    pyxis = scenario.creature("Pyxis of Pandemonium", "alice")
    bears, elves = _exile_face_down(scenario, pyxis)
    _alices_next_main_phase(scenario)

    _sacrifice(scenario, pyxis)

    assert pyxis.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD and bears.face_up
    assert elves.zone is Zone.BATTLEFIELD and elves.face_up
    assert scenario.game.controller_of(bears).username == "alice"
    assert scenario.game.controller_of(elves).username == "bob", "CR 110.2a"


def test_a_nonpermanent_card_is_turned_face_up_and_stays_in_exile():
    """CR 110.4a: an instant is not a permanent card."""
    scenario = _board(alice_library=["Lightning Bolt"], bob_library=["Forest"])
    pyxis = scenario.creature("Pyxis of Pandemonium", "alice")
    bolt, forest = _exile_face_down(scenario, pyxis)
    _alices_next_main_phase(scenario)

    _sacrifice(scenario, pyxis)

    assert bolt.zone is Zone.EXILE
    assert bolt.face_up
    assert not bolt.has_no_characteristics
    assert bolt.name == "Lightning Bolt"
    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.game.controller_of(forest).username == "bob"


def test_another_pyxiss_pile_stays_face_down():
    """CR 607.2a: each Pyxis's second ability reads only its own first
    ability's cards."""
    scenario = _board(
        alice_library=["Grizzly Bears", "Ornithopter"],
        bob_library=["Llanowar Elves", "Forest"],
        pyxes=2,
    )
    first, second = scenario.creatures(
        "Pyxis of Pandemonium", "Pyxis of Pandemonium", username="alice"
    )
    first_pile = _exile_face_down(scenario, first)
    second_pile = _exile_face_down(scenario, second)
    _alices_next_main_phase(scenario)

    _sacrifice(scenario, first)

    for card in first_pile:
        assert card.zone is Zone.BATTLEFIELD
    for card in second_pile:
        assert card.zone is Zone.EXILE
        assert not card.face_up
        assert card.has_no_characteristics
    assert second.zone is Zone.BATTLEFIELD


def test_every_card_from_every_earlier_activation_is_returned():
    """ "All cards they own exiled with this artifact" (CR 607.3's plural):
    two turns of exiling build one pile, and the sacrifice turns all of it
    over at once."""
    scenario = _board(
        alice_library=["Grizzly Bears", "Mountain", "Ornithopter"],
        bob_library=["Llanowar Elves", "Forest", "Shock"],
    )
    pyxis = scenario.creature("Pyxis of Pandemonium", "alice")
    first = _exile_face_down(scenario, pyxis)
    _alices_next_main_phase(scenario)
    second = _exile_face_down(scenario, pyxis)
    _alices_next_main_phase(scenario)

    _sacrifice(scenario, pyxis)

    for card in (*first, *second):
        assert card.face_up
        expected = Zone.EXILE if card.name == "Shock" else Zone.BATTLEFIELD
        assert card.zone is expected, card.name
        if expected is Zone.BATTLEFIELD:
            assert scenario.game.controller_of(card).username == card.owner

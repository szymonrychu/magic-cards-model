"""Scenario: "look at target opponent's hand. You may choose a nonland card
from it. If you do, that player exiles that card, then draws a card."

The caster looks at a hand (looking is not revealing: CR 701.20e shows the
cards only to the looker), may choose a qualifying card from it (the chooser is
the caster, CR 608.2d; an impossible option is never offered), and the gated
consequence moves that card out of the target's hand and refills it with a draw
(CR 121.2) - the draw belongs to the "If you do" sentence, so nothing chosen
means nothing drawn.

Cards, all from the real printings in `data/printings`:

- **Salt Vampire** (trk): the consequence exiles the chosen card.
- **Vendilion Clique** (a25), differently worded: "that player reveals the
  chosen card, puts it on the bottom of their library, then draws a card" -
  the same look / may choose / if you do run with a different destination.
- **Thought-Knot Seer** and **Thoughtseize** keep the ungated "you choose" run
  and are regression proofs (see `test_reveal_hand_and_choose.py`).

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 701.20a, CR 701.20e, CR 701.13a, CR 608.2d, CR 121.2, CR 701.9b, CR 401.4.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario


def _salt_vampire(bob_hand: list[str], bob_library: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", hand=["Salt Vampire"], battlefield=["Swamp", "Swamp"])
        .player(
            "bob",
            hand=bob_hand,
            library=["Island", "Plains", "Forest"] if bob_library is None else bob_library,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Salt Vampire", ["bob"])
    return scenario, scenario.untapped_sources("Swamp", "Swamp")


def _cast_salt_vampire(scenario, sources) -> None:
    scenario.cast_and_resolve("Salt Vampire", *sources)
    scenario.pass_until_resolved()


def test_the_chosen_card_is_exiled_and_its_owner_draws():
    scenario, sources = _salt_vampire(["Lightning Bolt", "Mountain"])
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    top = bob.library[0]
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bolt, username="alice")

    _cast_salt_vampire(scenario, sources)

    assert bolt.zone is Zone.EXILE
    assert bolt.owner == "bob"
    assert sorted(state.name for state in bob.hand) == sorted(["Mountain", top.name])


def test_the_caster_chooses_not_the_hands_owner():
    scenario, sources = _salt_vampire(["Lightning Bolt", "Counterspell"])
    scenario.will_take_the_may(True, username="alice")

    _cast_salt_vampire(scenario, sources)

    choose = next(d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS)
    assert choose.player == "alice"
    assert len(choose.cards) == 2


def test_declining_the_may_takes_nothing_and_draws_nothing():
    scenario, sources = _salt_vampire(["Lightning Bolt", "Mountain"])
    bob = scenario.player("bob")
    scenario.will_take_the_may(False, username="alice")

    _cast_salt_vampire(scenario, sources)

    assert sorted(state.name for state in bob.hand) == ["Lightning Bolt", "Mountain"]
    assert len(bob.library) == 3
    assert scenario.game.exile == []


def test_lands_are_not_offered_and_no_card_is_drawn():
    """CR 608.2d: no nonland card means the choice is impossible, so nothing is
    asked and "If you do" is not met - no draw either."""
    scenario, sources = _salt_vampire(["Mountain", "Forest"])
    bob = scenario.player("bob")

    _cast_salt_vampire(scenario, sources)

    assert not any(d.kind is DecisionKind.CHOOSE_CARDS for d in scenario.questions_asked())
    assert len(bob.hand) == 2
    assert len(bob.library) == 3


def test_an_empty_hand_gives_nothing_to_choose_and_no_draw():
    scenario, sources = _salt_vampire([])
    bob = scenario.player("bob")

    _cast_salt_vampire(scenario, sources)

    assert bob.hand == []
    assert len(bob.library) == 3


def test_only_a_nonland_card_is_chosen_among_mixed_cards():
    scenario, sources = _salt_vampire(["Mountain", "Lightning Bolt", "Forest"])
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_take_the_may(True, username="alice")

    _cast_salt_vampire(scenario, sources)

    assert bolt.zone is Zone.EXILE
    assert {state.name for state in bob.hand} >= {"Mountain", "Forest"}
    assert len(bob.hand) == 3


def test_an_empty_library_still_exiles_and_the_failed_draw_is_recorded():
    """CR 608.2d: drawing from an empty library is not an impossible action, so
    the exile still happens and the failed draw is what CR 704.5b later checks."""
    scenario, sources = _salt_vampire(["Lightning Bolt"], bob_library=[])
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_take_the_may(True, username="alice")

    _cast_salt_vampire(scenario, sources)

    assert bolt.zone is Zone.EXILE
    assert bob.hand == []
    assert bob.tried_to_draw_from_empty_library


# -- Vendilion Clique: the same run, the chosen card goes to the library bottom --


def _clique(bob_hand: list[str], bob_library: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=["Vendilion Clique"], battlefield=["Island"] * 3)
        .player("bob", hand=bob_hand, library=bob_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Vendilion Clique", ["bob"])
    return scenario, scenario.untapped_sources("Island", "Island", "Island")


def test_clique_puts_the_chosen_card_on_the_bottom_and_the_player_draws():
    scenario, sources = _clique(["Lightning Bolt", "Mountain"], ["Island", "Plains", "Forest"])
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    drawn = bob.library[0]
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(bolt, username="alice")

    scenario.cast_and_resolve("Vendilion Clique", *sources)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.LIBRARY
    assert bob.library[-1] is bolt
    assert sorted(state.name for state in bob.hand) == sorted(["Mountain", drawn.name])
    assert len(bob.library) == 3


def test_clique_declined_changes_nothing():
    scenario, sources = _clique(["Lightning Bolt"], ["Island", "Plains"])
    bob = scenario.player("bob")
    scenario.will_take_the_may(False, username="alice")

    scenario.cast_and_resolve("Vendilion Clique", *sources)
    scenario.pass_until_resolved()

    assert [state.name for state in bob.hand] == ["Lightning Bolt"]
    assert len(bob.library) == 2


def test_clique_with_a_one_card_library_draws_back_the_bottomed_card():
    """The chosen card goes to the bottom first (CR 401.4's position), then the
    draw takes the top card - which is that same card when it is alone."""
    scenario, sources = _clique(["Lightning Bolt"], [])
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_take_the_may(True, username="alice")

    scenario.cast_and_resolve("Vendilion Clique", *sources)
    scenario.pass_until_resolved()

    assert bolt in bob.hand
    assert bob.library == []


def test_the_caster_looks_but_nothing_is_revealed_to_the_opponent():
    """CR 701.20e: a look shows the cards only to the looking player, so bob's
    remaining card is known to alice and to nobody else."""
    scenario, sources = _salt_vampire(["Lightning Bolt", "Mountain"])
    scenario.will_take_the_may(False, username="alice")

    _cast_salt_vampire(scenario, sources)

    assert any(known.card_name == "Mountain" for known in scenario.game.known_to("alice"))
    assert not any(known.card_name == "Mountain" for known in scenario.game.known_to("bob"))

"""What cascade shows everyone, and what hideaway shows only its controller.

- **CR 702.85a** - "'Cascade' means 'When you cast this spell, exile cards
  from the top of your library until you exile a nonland card whose mana value
  is less than this spell's mana value. You may cast that card without paying
  its mana cost if the resulting spell's mana value is less than this spell's
  mana value. Then put all cards exiled this way that weren't cast on the
  bottom of your library in a random order.'" The cards are exiled face up
  (CR 406.3: "Exiled cards are, by default, kept face up and may be examined
  by any player at any time"), so every one is recorded as a reveal to all
  players (CR 701.20a).
- **CR 702.75a** - "'Hideaway N' means 'When this permanent enters, look at
  the top N cards of your library. Exile one of them face down and put the
  rest on the bottom of your library in a random order. The exiled card gains
  'The player who controls the permanent that exiled this card may look at
  this card in the exile zone.''" A look (CR 701.20e) is for its controller
  only.
- **CR 406.3** - "if a player is instructed to look at a card and then exile
  it face down ... that player may continue to look at that card until it
  leaves the exile zone or is part of a pile of cards that are shuffled". So
  the face-down card stays known to its controller through a shuffle of the
  library, and stops being known when it leaves exile (CR 400.7: "An object
  that moves from one zone to another becomes a new object").
- **CR 701.20d** - the cards bottomed "in a random order" are put into a
  library and reordered; nobody knows where they are.

Bloodbraid Elf (cascade), Mosswort Bridge and Fight Rigging (hideaway) are in
neither deck pool; Shardless Agent is, and is here beside Bloodbraid Elf.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, int | None, bool]]:
    return [
        (entry.card_name, entry.zone, entry.index_from_top, entry.carried)
        for entry in game.known_to(viewer)
    ]


# -- cascade (CR 702.85a) ------------------------------------------------------


def _shardless_agent(*library: str) -> Scenario:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shardless Agent"],
            library=list(library),
            battlefield=["Forest", "Island", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_every_card_cascade_exiles_is_revealed_to_all_players():
    scenario = _shardless_agent("Forest", "Kitchen Finks", "Lightning Bolt", "Island")
    scenario.will_take_the_may(True, source="Shardless Agent")
    scenario.cast_onto_stack(
        "Shardless Agent", *scenario.untapped_sources("Forest", "Island", "Forest")
    )

    scenario.resolve_top()  # the cascade trigger

    assert [(r.card_name, r.zone, r.viewers) for r in scenario.game.reveals] == [
        ("Forest", Zone.EXILE, None),
        ("Kitchen Finks", Zone.EXILE, None),
        ("Lightning Bolt", Zone.EXILE, None),
    ]
    assert all(r.source == "Shardless Agent" for r in scenario.game.reveals)
    bolt = scenario.find("Lightning Bolt", Zone.EXILE)
    assert bolt.zone is Zone.EXILE
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.EXILE, None, False)]
    assert known(scenario.game, "bob") == [("Lightning Bolt", Zone.EXILE, None, False)]


def test_cards_cascade_puts_on_the_bottom_are_no_longer_known_to_anyone():
    scenario = _shardless_agent("Forest", "Kitchen Finks", "Lightning Bolt", "Island")
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, source="Shardless Agent")
    scenario.cast_onto_stack(
        "Shardless Agent", *scenario.untapped_sources("Forest", "Island", "Forest")
    )
    epoch_before = alice.library_epoch

    scenario.resolve_top()

    assert len(scenario.game.reveals) == 3
    assert sorted(state.name for state in alice.library) == [
        "Forest",
        "Island",
        "Kitchen Finks",
        "Lightning Bolt",
    ]
    assert alice.library_epoch > epoch_before, "CR 701.20d: a random order is a reordering"
    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []


def test_bloodbraid_elf_cascade_reveals_the_hit_and_forgets_the_bottomed_land():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Bloodbraid Elf"],
            library=["Mountain", "Kitchen Finks", "Island"],
            battlefield=["Mountain", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Bloodbraid Elf")
    scenario.cast_onto_stack(
        "Bloodbraid Elf", *scenario.untapped_sources("Mountain", "Forest", "Forest", "Forest")
    )

    scenario.resolve_top()

    assert [(r.card_name, r.viewers) for r in scenario.game.reveals] == [
        ("Mountain", None),
        ("Kitchen Finks", None),
    ]
    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Island", "Mountain"]
    assert known(scenario.game, "bob") == [("Kitchen Finks", Zone.EXILE, None, False)]
    assert known(scenario.game, "alice") == [("Kitchen Finks", Zone.EXILE, None, False)]


# -- hideaway (CR 702.75a) -----------------------------------------------------


def test_mosswort_bridge_hideaway_looks_are_its_controllers_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mosswort Bridge"],
            library=[
                "Lightning Bolt",
                "Opt",
                "Goblin Guide",
                "Craterous Stomp",
                "Faithless Looting",
            ],
            battlefield=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin_guide = scenario.find("Goblin Guide", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(goblin_guide, source="Mosswort Bridge")

    scenario.play_land("Mosswort Bridge", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert goblin_guide.zone is Zone.EXILE and goblin_guide.face_up is False
    reveals = scenario.game.reveals
    assert all(r.viewers == ["alice"] for r in reveals), "CR 701.20e: looks, not reveals"
    assert all(r.source == "Mosswort Bridge" for r in reveals)
    assert [r.card_name for r in reveals if r.zone is Zone.LIBRARY] == [
        "Lightning Bolt",
        "Opt",
        "Goblin Guide",
        "Craterous Stomp",
    ]
    assert known(scenario.game, "alice") == [("Goblin Guide", Zone.EXILE, None, False)]
    assert known(scenario.game, "bob") == []


def test_fight_rigging_hidden_card_stays_known_through_a_shuffle_until_it_leaves_exile():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fight Rigging"],
            battlefield=["Forest", "Forest", "Forest", "Flooded Strand"],
            library=["Lightning Bolt", "Forest", "Forest", "Forest", "Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.player("alice").library[0]
    scenario.will_choose_cards(bolt, source="Fight Rigging")
    scenario.cast_and_resolve(
        "Fight Rigging", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.EXILE and bolt.face_up is False
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.EXILE, None, False)]
    assert known(scenario.game, "bob") == []

    strand = scenario.find("Flooded Strand", Zone.BATTLEFIELD)
    scenario.activate(strand)
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").library] == ["Forest"] * 4
    assert known(scenario.game, "alice") == [("Lightning Bolt", Zone.EXILE, None, False)], (
        "CR 406.3: the shuffled library is not the pile the hidden card is in"
    )

    scenario.game.return_to_hand(bolt)

    assert bolt.zone is Zone.HAND
    assert known(scenario.game, "alice") == [], "CR 400.7: it left the exile zone"
    assert known(scenario.game, "bob") == []


def test_a_player_who_gains_control_of_the_hideaway_permanent_may_look_at_the_hidden_card():
    """CR 702.75a: the exiled card gains "The player who controls the permanent
    that exiled this card may look at this card in the exile zone" - whoever
    controls it now, not whoever controlled it when the ability resolved. And
    CR 406.3: "once a player is allowed to look at a card exiled face down,
    that player may continue to look at that card until it leaves the exile
    zone", so the thief keeps knowing it after control goes back.

    Watcher for Tomorrow and Threaten are in neither deck pool."""
    scenario = (
        Scenario()
        .player("alice", hand=["Threaten"], battlefield=["Mountain"] * 3)
        .player(
            "bob",
            hand=["Watcher for Tomorrow"],
            library=["Lightning Bolt", "Opt", "Goblin Guide", "Craterous Stomp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hidden = scenario.find("Goblin Guide", Zone.LIBRARY, "bob")
    scenario.will_choose_cards(hidden, source="Watcher for Tomorrow")
    watcher = scenario.put_onto_battlefield("Watcher for Tomorrow", "bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert hidden.zone is Zone.EXILE and hidden.face_up is False
    assert known(scenario.game, "bob") == [("Goblin Guide", Zone.EXILE, None, False)]
    assert known(scenario.game, "alice") == []

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Threaten", *sources, targets=[watcher])

    assert scenario.game.controller_of(watcher).username == "alice"
    assert known(scenario.game, "alice") == [("Goblin Guide", Zone.EXILE, None, False)], (
        "CR 702.75a: the permanent's controller may look at the hidden card"
    )
    assert known(scenario.game, "bob") == [("Goblin Guide", Zone.EXILE, None, False)], (
        "CR 406.3: the first controller keeps looking"
    )

    scenario.game.cleanup_step()

    assert scenario.game.controller_of(watcher).username == "bob"
    assert known(scenario.game, "alice") == [("Goblin Guide", Zone.EXILE, None, False)], (
        "CR 406.3: a player once allowed to look keeps looking after control goes back"
    )

    scenario.game.return_to_hand(hidden)

    assert known(scenario.game, "alice") == []
    assert known(scenario.game, "bob") == []

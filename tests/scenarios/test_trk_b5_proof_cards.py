"""Scenario: trk B5 proofs. Each reader the B5 batch added or widened is shown
on a real, non-trk card of the same text shape (Modern, Standard or Pioneer
legal), so the reader is not tuned to one Star Trek printing.

Reader, trk card it was written for, non-trk proof here:

- "Target opponent gains control of target permanent you control" (Rules of
  Acquisition): Harmless Offering.
- "a basic land card or <Name> card" without a second article (Genesis Device,
  70,000 Light-Years from Home): Open the Gates, District Guide.
- "gets +P/+T until end of turn and can't be blocked this turn" (Lore): Distortion
  Strike.
- "deals N damage to each opponent and each creature your opponents control"
  (Khan): Sarkhan, Dragonsoul.
- "You have no maximum hand size until your next turn" (Deep Space Scan): Enter the
  Infinite.

CR rules cited here were looked up with `mise run rules:find` in the writing session.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def test_harmless_offering_gives_a_permanent_to_the_target_opponent() -> None:
    """CR 115.1: the first target is the player who receives the permanent, the
    second is the permanent given away; control lasts indefinitely (CR 611.2a)."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Harmless Offering"], battlefield=["Mountain"] * 3 + ["Grizzly Bears"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Harmless Offering", *scenario.untapped_sources(*["Mountain"] * 3), targets=["bob", bears]
    )
    assert scenario.game.controller_of(bears).username == "bob"


def test_open_the_gates_finds_a_gate_with_no_second_article() -> None:
    """ "a basic land card or Gate card": a Gate is as good as a basic land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Open the Gates"],
            library=["Grizzly Bears", "Azorius Guildgate"],
            battlefield=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gate = scenario.find("Azorius Guildgate", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(gate, username="alice", source="Open the Gates")
    scenario.cast_and_resolve("Open the Gates", *scenario.untapped_sources("Forest"))
    assert gate in scenario.player("alice").hand
    assert "Grizzly Bears" in [c.name for c in scenario.player("alice").library]


def test_distortion_strike_pumps_and_makes_the_creature_unblockable() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Distortion Strike"], battlefield=["Island", "Grizzly Bears"])
        .player("bob", battlefield=["Wurmcoil Engine"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Wurmcoil Engine", "bob")
    scenario.cast_and_resolve(
        "Distortion Strike", *scenario.untapped_sources("Island"), targets=[bears]
    )
    assert scenario.game.power_of(bears) == 3
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(bears)
    assert not scenario.game.can_block(wurm, bears)


def test_sarkhan_dragonsoul_pings_each_opponent_and_each_creature_they_control() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Sarkhan, Dragonsoul", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sarkhan = scenario.find("Sarkhan, Dragonsoul", Zone.BATTLEFIELD, "alice")
    scenario.activate(sarkhan, index=0)
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20
    assert scenario.creature("Grizzly Bears", "bob").damage == 1
    assert scenario.creature("Grizzly Bears", "alice").damage == 0
    assert "Llanowar Elves" not in scenario.battlefield_names()


def test_enter_the_infinite_lifts_the_hand_size_limit_until_your_next_turn() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Enter the Infinite"],
            library=["Forest"] * 3,
            battlefield=["Island"] * 12,
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    assert not alice.has_no_maximum_hand_size
    scenario.cast_and_resolve("Enter the Infinite", *scenario.untapped_sources(*["Island"] * 12))
    assert alice.has_no_maximum_hand_size
    for _ in range(40):
        scenario.advance()
        if scenario.turn.turns_taken >= 2 and scenario.turn.active_player == "alice":
            break
    assert not alice.has_no_maximum_hand_size, "ended as alice's next turn began"


def test_district_guide_fetches_a_gate_into_hand_when_it_enters() -> None:
    """The optional ETB form of "a basic land card or Gate card"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["District Guide"],
            library=["Grizzly Bears", "Azorius Guildgate"],
            battlefield=["Forest"] * 3,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gate = scenario.find("Azorius Guildgate", Zone.LIBRARY, "alice")
    scenario.will_take_the_may(True, username="alice", source="District Guide")
    scenario.will_choose_cards(gate, username="alice", source="District Guide")
    scenario.cast_onto_stack("District Guide", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert gate in scenario.player("alice").hand

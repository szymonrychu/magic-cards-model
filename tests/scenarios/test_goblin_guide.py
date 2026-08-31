"""Goblin Guide's attack trigger (CR 508.1, CR 701.20a).

"Whenever this creature attacks, defending player reveals the top card of
their library. If it's a land card, that player puts it into their hand."

The rule this file exists to pin down: **the defending player's** library is
read, never Goblin Guide's own controller's - a "wrong player" bug this class
of card is exactly built to catch (CR 508.1a names a defending player per
attack, `machines.combat.defending_player`, read off the trigger's own
`GameEvent.defender`).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 508.1 (attacking), CR 701.20a (reveal), CR 205.2a (land card type).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(defender_library: list[str], attacker_library: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Guide"],
            library=attacker_library if attacker_library is not None else ["Lightning Bolt"],
        )
        .player("bob", library=defender_library)
    )


def resolve_all(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_a_land_on_top_of_the_defending_players_library_goes_to_their_hand():
    scenario = board(defender_library=["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guide = scenario.creature("Goblin Guide", "alice")

    scenario.attack_with(guide)
    resolve_all(scenario)

    forest = scenario.find("Forest", Zone.HAND, "bob")
    assert forest.zone is Zone.HAND
    assert [card.name for card in scenario.player("bob").library] == ["Island"]


def test_a_nonland_on_top_stays_on_top_and_nothing_moves():
    scenario = board(defender_library=["Lava Dart", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guide = scenario.creature("Goblin Guide", "alice")

    scenario.attack_with(guide)
    resolve_all(scenario)

    assert scenario.player("bob").hand == []
    assert [card.name for card in scenario.player("bob").library] == ["Lava Dart", "Forest"]


def test_it_reads_the_defending_players_library_not_the_attacking_players():
    """The wrong-player bug this file guards against: a Goblin Guide whose
    own controller's library starts with a land must not put *that* land
    into anyone's hand - only a land on top of bob's library, the player
    being attacked, counts.
    """
    scenario = board(
        defender_library=["Forest"], attacker_library=["Mountain", "Lightning Bolt"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    guide = scenario.creature("Goblin Guide", "alice")

    scenario.attack_with(guide)
    resolve_all(scenario)

    # bob's land moved to bob's hand.
    assert scenario.find("Forest", Zone.HAND, "bob").zone is Zone.HAND
    # alice's own library - topped with a land too - was never touched.
    assert scenario.player("alice").hand == []
    assert [card.name for card in scenario.player("alice").library] == [
        "Mountain",
        "Lightning Bolt",
    ]

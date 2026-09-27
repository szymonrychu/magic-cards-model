"""A battle's defense, and defeating a Siege.

Verified this session with `mise run rules:find` against the current CR:

- **CR 310.4b** - "A battle has the intrinsic ability 'This permanent enters
  with a number of defense counters on it equal to its printed defense
  number.'"; **310.4c** - its defense on the battlefield is the number of
  defense counters on it.
- **CR 310.6** / **120.3h** - "Damage dealt to a battle results in that many
  defense counters being removed from it."
- **CR 115.4** - "any target" may be a creature, player, planeswalker, or
  battle.
- **CR 310.7** / **704.5v** - "If a Siege battle has defense 0 and it isn't
  the source of an ability that has triggered but not yet left the stack,
  it's put into its owner's graveyard."
- **CR 310.12b** - "Sieges have the intrinsic ability 'When the last defense
  counter is removed from this permanent, exile it, then you may cast it
  transformed without paying its mana cost.'"
- **CR 712.8c** / **712.11a** - a double-faced card cast transformed is put
  on the stack with its back face up and has only its back face's
  characteristics; **712.13** - it enters with the same face up.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Type, Zone
from tests.scenarios.harness import PlayedScenario, Scenario

ZENDIKAR = "Invasion of Zendikar"
"""Battle - Siege, defense 3 // Awakened Skyclave, a 4/4 Elemental that is a
land as long as it is on the battlefield."""

ERGAMON = "Invasion of Ergamon"
"""Battle - Siege, defense 5 // Truga Cliffcharger, a 3/3 trampling Rhino
with an enters trigger. Its own enters trigger may loot, so its controller
is given a library to draw from."""


def _enter_siege(scenario: PlayedScenario, name: str, username: str):
    if name == ERGAMON:
        # Its enters trigger's "Then you may discard a card" - declined.
        scenario.will_take_the_may(False, username=username, source=ERGAMON)
    siege = scenario.put_onto_battlefield(name, username)
    scenario.pass_until_resolved()  # the Siege's own enters trigger
    return siege


def _attack_own_siege(scenario: PlayedScenario, siege, *attackers: str) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*scenario.creatures(*attackers, username="alice"), defending=siege)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()


def test_a_siege_enters_with_its_printed_defense_in_defense_counters():
    """CR 310.4b / 310.4c."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR, ERGAMON], library=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    zendikar = _enter_siege(scenario, ZENDIKAR, "alice")
    ergamon = _enter_siege(scenario, ERGAMON, "alice")

    assert zendikar.counter_count("defense") == 3
    assert ergamon.counter_count("defense") == 5


def test_a_battle_staged_on_the_battlefield_has_its_defense_counters():
    scenario = Scenario().player("alice", battlefield=[ERGAMON]).player("bob").build()

    (siege,) = scenario.game.battlefield

    assert siege.counter_count("defense") == 5


def test_a_copy_entering_as_a_siege_enters_with_the_copied_defense():
    """CR 310.4b is an intrinsic ability of a battle, so a permanent entering
    as a copy of a Siege (CR 614.1c) enters with that Siege's defense."""
    scenario = (
        Scenario()
        .player("alice", hand=["Clever Impersonator"])
        .player("bob", battlefield=[ERGAMON])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(ERGAMON, Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(siege, username="alice", source="Clever Impersonator")

    copy = scenario.put_onto_battlefield("Clever Impersonator", "alice")

    assert copy.counter_count("defense") == 5


def test_a_transformed_back_face_has_no_defense():
    """The back face is a creature, not a battle: nothing gives it defense."""
    scenario = Scenario().player("alice", hand=[ZENDIKAR]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find(ZENDIKAR, Zone.HAND, "alice")

    skyclave = scenario.game.put_onto_battlefield(card, "alice", transformed=True)

    assert skyclave.counter_count("defense") == 0
    assert skyclave.protector is None


def test_combat_damage_to_a_battle_removes_that_many_defense_counters():
    """CR 310.6 / 120.3h: a 2/2 attacking a defense-3 Siege leaves it at 1."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")

    _attack_own_siege(scenario, siege, "Grizzly Bears")

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.counter_count("defense") == 1
    assert siege.damage == 0


def test_burn_to_any_target_can_hit_a_battle():
    """CR 115.4: "any target" includes a battle, and CR 120.3h turns the
    damage into removed defense counters."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=[ERGAMON, "Lightning Bolt"], library=["Island"], battlefield=["Mountain"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ERGAMON, "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[siege],
    )

    assert siege.counter_count("defense") == 2


def test_a_defeated_siege_is_exiled_and_cast_transformed():
    """CR 310.12b: the last defense counter goes, the Siege stays until its
    own trigger resolves (CR 704.5v), is exiled, and is cast transformed
    (CR 712.11a) for free - entering as Awakened Skyclave (CR 712.13)."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")

    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.game.check_state_based_actions()

    assert siege.counter_count("defense") == 0
    assert siege.zone is Zone.BATTLEFIELD  # CR 704.5v: its trigger is pending
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # the defeat trigger: exile, then cast
    assert scenario.stack_names() == ["Awakened Skyclave"]
    scenario.pass_until_resolved()  # the transformed spell

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.transformed
    assert siege.name == "Awakened Skyclave"
    assert scenario.game.controller_of(siege).username == "alice"
    types = scenario.game.characteristics_of(siege).types
    assert Type.CREATURE in types and Type.LAND in types
    assert siege.counter_count("defense") == 0
    assert siege.protector is None


def test_declining_to_cast_a_defeated_siege_leaves_it_in_exile():
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")

    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.will_take_the_may(False, username="alice")
    scenario.pass_until_resolved()

    assert siege.zone is Zone.EXILE
    assert scenario.stack_names() == []


def test_a_defeated_siege_back_face_enters_and_its_own_enters_trigger_fires():
    """Invasion of Ergamon defeated by Lightning Bolt's 3 plus a 2/2's 2:
    Truga Cliffcharger enters and its "When this creature enters" triggers."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ERGAMON, "Lightning Bolt"],
            library=["Island", "Island"],
            battlefield=["Grizzly Bears", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ERGAMON, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[siege],
    )

    _attack_own_siege(scenario, siege, "Grizzly Bears")
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # the defeat trigger
    scenario.pass_until_resolved()  # Truga Cliffcharger, cast transformed

    assert siege.name == "Truga Cliffcharger"
    assert siege.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == ["Truga Cliffcharger's triggered ability"]


def test_a_siege_at_zero_defense_with_nothing_triggered_goes_to_the_graveyard():
    """CR 704.5v: a Siege with defense 0 that is not the source of a pending
    or stacked triggered ability is put into its owner's graveyard."""
    scenario = Scenario().player("alice", battlefield=[ERGAMON]).player("bob").build()
    (siege,) = scenario.game.battlefield
    # Staged: the counters taken off by hand, so no removal event fires.
    siege.counters.remove("defense", 5)

    scenario.game.check_state_based_actions()

    assert siege.zone is Zone.GRAVEYARD


def test_the_defeat_trigger_is_asked_of_the_sieges_controller():
    """CR 310.12b: "you" is the Siege's controller - alice, who attacked it -
    not its protector."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")
    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.will_take_the_may(True, username="alice")

    scenario.pass_until_resolved()

    (question,) = [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.MAY and "transformed" in decision.prompt
    ]
    assert question.player == "alice"


def test_a_copy_of_a_siege_has_the_defeat_trigger_and_is_exiled_when_defeated():
    """A permanent that entered as a copy of a Siege is a Siege (CR 707.2), so
    it has CR 310.12b's intrinsic trigger: defeated, it is exiled rather than
    put into the graveyard by CR 704.5v. Clever Impersonator has no back face
    to cast transformed (CR 712.11a), so nothing is cast."""
    scenario = (
        Scenario()
        .player("alice", hand=["Clever Impersonator", "Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=[ZENDIKAR])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(ZENDIKAR, Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(siege, username="alice", source="Clever Impersonator")
    copy = scenario.put_onto_battlefield("Clever Impersonator", "alice")
    scenario.pass_until_resolved()  # the copied enters trigger
    assert copy.counter_count("defense") == 3

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[copy],
    )
    scenario.pass_until_resolved()  # the defeat trigger

    assert copy.zone is Zone.EXILE
    assert scenario.stack_names() == []

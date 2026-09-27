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


def test_a_copy_of_a_copy_of_a_siege_enters_with_the_original_defense():
    """CR 310.4 makes defense a characteristic, and CR 707.2's copiable
    values are "as modified by other copy effects": Clever Impersonator
    copying a Clever Impersonator that copies Invasion of Ergamon enters as
    Invasion of Ergamon, with its 5 defense."""
    scenario = (
        Scenario()
        .player("alice", hand=["Clever Impersonator", "Clever Impersonator"])
        .player("bob", battlefield=[ERGAMON])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(ERGAMON, Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(siege, username="alice", source="Clever Impersonator")
    first = scenario.put_onto_battlefield("Clever Impersonator", "alice")
    scenario.will_take_the_may(False, username="alice")  # the copied loot
    scenario.pass_until_resolved()
    scenario.will_choose_cards(first, username="alice", source="Clever Impersonator")

    second = scenario.put_onto_battlefield("Clever Impersonator", "alice")

    assert scenario.game.characteristics_of(second).name == ERGAMON
    assert second.counter_count("defense") == 5


def test_only_the_back_face_is_evaluated_for_the_transformed_cast():
    """CR 712.11c: "Only the face that will be face up on the stack is
    evaluated to determine if it can be cast." Soulless Jailer stops
    noncreature spells being cast from exile - the Siege face is a battle,
    but Awakened Skyclave is a creature, so the cast is allowed."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob", battlefield=["Soulless Jailer"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")

    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Awakened Skyclave"]
    (question,) = [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.MAY and "transformed" in decision.prompt
    ]
    assert question.affirmative_is_legal


def test_removing_the_counters_any_other_way_also_defeats_a_siege():
    """CR 310.12b triggers on the last defense counter being removed, not on
    damage: Vampire Hexmage's "Remove all counters from target permanent"."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Vampire Hexmage"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")
    hexmage = scenario.creature("Vampire Hexmage", "alice")

    scenario.activate(hexmage, sacrificing=[hexmage], targets=[siege])
    scenario.pass_until_resolved()  # the Hexmage ability
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()  # the defeat trigger

    assert scenario.stack_names() == ["Awakened Skyclave"]


def test_infect_damage_to_a_battle_removes_defense_counters_only():
    """CR 120.3h is the battle result whatever the source: Glistener Elf's
    infect (CR 702.90) puts no -1/-1 counters on a battle."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Glistener Elf"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")

    _attack_own_siege(scenario, siege, "Glistener Elf")

    assert siege.counter_count("defense") == 2
    assert siege.counter_count("-1/-1") == 0


def test_a_siege_whose_defeat_trigger_is_countered_goes_to_the_graveyard():
    """CR 704.5v spares a defense-0 Siege only while its trigger has not
    left the stack: Consign to Memory counters it, and the Siege is put into
    its owner's graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ZENDIKAR, "Consign to Memory"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")
    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.game.put_triggers_on_stack()
    (trigger,) = [item for item in scenario.game.stack if item.source_id == siege.id]

    scenario.cast_onto_stack(
        "Consign to Memory",
        *scenario.untapped_sources("Island", username="alice"),
        username="alice",
        targets=[trigger],
    )
    scenario.pass_until_resolved()

    assert siege.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_the_transformed_spell_has_the_front_faces_mana_value():
    """CR 712.8c: back face up on the stack, but its mana value is still
    calculated from the front face's mana cost."""
    scenario = (
        Scenario()
        .player("alice", hand=[ZENDIKAR], battlefield=["Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, ZENDIKAR, "alice")
    front_mana_value = siege.mana_value
    _attack_own_siege(scenario, siege, "Grizzly Bears", "Grizzly Bears")
    scenario.will_take_the_may(True, username="alice")
    scenario.pass_until_resolved()

    assert scenario.stack_names() == ["Awakened Skyclave"]
    assert siege.mana_value == front_mana_value == 4
    assert Type.CREATURE in scenario.game.characteristics_of(siege).types or Type.CREATURE in (
        siege.types
    )


def test_a_bare_its_a_type_sentence_is_not_read_as_a_self_type_grant():
    """Only "As long as this ... is on the battlefield, it's a ..." is the
    static self grant; the bare sentence is resolution text about another
    object (Infernal Vessel's returned creature)."""
    from magic_cards_model.machines.layers import _self_type_grant

    assert _self_type_grant("It's a Demon in addition to its other types.") is None
    assert (
        _self_type_grant(
            "As long as this creature is on the battlefield, it's a land in addition to "
            "its other types."
        )
        is not None
    )

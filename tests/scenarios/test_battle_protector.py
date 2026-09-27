"""A battle's protector, and who defends it when it is attacked.

A battle is attacked like a planeswalker, but the player defending it is not
necessarily the player who controls it: a Siege is protected by an opponent
of its controller, and its own controller may attack it. Everything combat
derives from "the defending player" - who may block, who an attack trigger's
"defending player" is, who annihilator makes sacrifice - follows the
protector, not the controller.

Verified this session with `mise run rules:find` against the current CR:

- **CR 310.9** / **310.9a** - each battle has a protector, chosen by its
  controller as it enters; an untyped battle's protector can only be its
  controller.
- **CR 310.9b** - "A battle's protector can never attack it. A battle can be
  attacked by any attacking player for whom its protector is a defending
  player. Notably, a Siege battle can be attacked by its own controller."
- **CR 310.9c** - only the protector's creatures may block creatures
  attacking that battle.
- **CR 310.9d** / **508.5** - "defending player" relative to an attacked
  battle is its protector, not its controller.
- **CR 310.12a** - a Siege's protector is chosen from among its controller's
  opponents.
- **CR 205.3q** - Siege is the only battle type.
- **CR 509.1a** / **802.4a** - a defending player blocks with creatures they
  control, creatures attacking them, a planeswalker they control, or a battle
  they protect.
- **CR 704.5x** / **704.5y** (**310.11**) - a battle with no protector, or one
  who can't be its protector, has a new one chosen by its controller; with
  nobody choosable it goes to its owner's graveyard.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import defending_player
from magic_cards_model.models import TargetRef, Zone
from tests.scenarios.harness import PlayedScenario, Scenario

SIEGE = "Invasion of Zendikar"
"""Battle - Siege, defense 3; its enters trigger searches for up to two basic
lands, which an empty library turns into a no-op."""

OTHER_SIEGE = "Invasion of Ergamon"


def _enter_siege(scenario: PlayedScenario, name: str, username: str):
    siege = scenario.put_onto_battlefield(name, username)
    scenario.pass_until_resolved()  # the Siege's own enters trigger
    return siege


def test_a_siege_is_protected_by_its_controllers_only_opponent():
    """CR 310.12a: with one opponent there is nothing to choose."""
    scenario = Scenario().player("alice", hand=[SIEGE]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    siege = _enter_siege(scenario, SIEGE, "alice")

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.protector == "bob"


def test_a_siege_controller_chooses_among_several_opponents():
    """CR 310.12a in a three-player game: the controller picks the protector
    from among their opponents as the Siege enters."""
    scenario = Scenario().player("alice", hand=[SIEGE]).player("bob").player("carol").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("carol", username="alice", source=SIEGE)

    siege = _enter_siege(scenario, SIEGE, "alice")

    assert siege.protector == "carol"


def test_the_controller_may_attack_their_own_siege_and_its_protector_defends():
    """CR 310.9b: "a Siege battle can be attacked by its own controller", and
    CR 310.9d / 508.5 make its protector the defending player."""
    scenario = (
        Scenario()
        .player("alice", hand=[SIEGE], battlefield=["Goblin Guide"])
        .player("bob", library=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")

    scenario.attack_with(guide, defending=siege)

    assert defending_player(scenario.game, TargetRef.coerce(siege)) == "bob"
    scenario.pass_until_resolved()  # Goblin Guide's attack trigger
    # "defending player reveals the top card of their library. If it's a land
    # card, that player puts it into their hand" - bob, never alice.
    bob = scenario.player("bob")
    assert [card.name for card in bob.hand] == ["Forest"]
    assert scenario.player("alice").hand == []


def test_the_protector_can_never_attack_the_battle_it_protects():
    """CR 310.9b: bob's Siege is protected by alice, so alice may not attack
    it - and the refusal says which rule."""
    scenario = (
        Scenario().player("alice", battlefield=["Goblin Guide"]).player("bob", hand=[SIEGE]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "bob")
    assert siege.protector == "alice"
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")

    assert not scenario.can_attack(guide, defending=siege)
    with pytest.raises(ValueError, match=r"CR 310\.9b"):
        scenario.attack_with(guide, defending=siege)


def test_the_protector_blocks_a_creature_attacking_the_battle():
    """CR 310.9c / 509.1a: only the protector's creatures may block a creature
    attacking the battle it protects."""
    scenario = (
        Scenario()
        .player("alice", hand=[SIEGE], battlefield=["Goblin Guide", "Grizzly Bears"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.attack_with(guide, defending=siege)
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_BLOCKERS)

    scenario.block(guide, scenario.creature("Llanowar Elves", "bob"))

    assert [blocker.name for blocker in scenario.blockers()] == ["Llanowar Elves"]


def test_annihilator_makes_the_protector_sacrifice():
    """Annihilator's "defending player sacrifices" (CR 702.86a) attacking a
    Siege its own controller controls: the protector sacrifices."""
    scenario = (
        Scenario()
        .player("alice", hand=[SIEGE], battlefield=["Ulamog's Crusher"])
        .player("bob", battlefield=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crusher = scenario.creature("Ulamog's Crusher", "alice")

    scenario.attack_with(crusher, defending=siege)
    scenario.pass_until_resolved()  # annihilator 2

    assert scenario.game.permanents_controlled_by("bob") == []
    assert {card.name for card in scenario.game.battlefield} == {"Ulamog's Crusher", SIEGE}


def test_an_intervening_if_on_the_defending_player_reads_the_protector():
    """Septic Rats: "Whenever this creature attacks, if defending player is
    poisoned, it gets +1/+1 until end of turn." Attacking alice's own Siege,
    the defending player is bob (CR 310.9d) - poisoned - not alice."""
    scenario = (
        Scenario().player("alice", hand=[SIEGE], battlefield=["Septic Rats"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "alice")
    scenario.game.add_player_counters("bob", "poison", 1)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rats = scenario.creature("Septic Rats", "alice")

    scenario.attack_with(rats, defending=siege)

    assert scenario.stack_names() == ["Septic Rats's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.power_of(rats) == 3


# -- three players -----------------------------------------------------------


def _three_player_siege_board() -> tuple[PlayedScenario, object]:
    """carol's Siege, protected by bob; alice (the active player) attacks it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", library=["Forest"], battlefield=["Llanowar Elves"])
        .player("carol", hand=[SIEGE], library=["Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("bob", username="carol", source=SIEGE)
    siege = _enter_siege(scenario, SIEGE, "carol")
    return scenario, siege


def test_multiplayer_attack_on_a_battle_defended_by_its_protector_not_its_controller():
    """CR 310.9d / 508.5a: carol controls the Siege, bob protects it - the
    attack trigger's "defending player" is bob."""
    scenario, siege = _three_player_siege_board()
    assert siege.protector == "bob"
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")

    scenario.attack_with(guide, defending=siege)
    scenario.pass_until_resolved()

    assert [card.name for card in scenario.player("bob").hand] == ["Forest"]
    assert scenario.player("carol").hand == []


def test_multiplayer_only_the_protector_may_block_for_the_battle():
    """CR 310.9c, 802.4a: carol controls the battle, but only bob - its
    protector - declares blockers against the creature attacking it."""
    scenario, siege = _three_player_siege_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.attack_with(guide, defending=siege)
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_BLOCKERS)

    with pytest.raises(ValueError, match="not controlled by bob"):
        scenario.block(guide, scenario.creature("Grizzly Bears", "carol"))
    scenario.block(guide, scenario.creature("Llanowar Elves", "bob"))
    assert [blocker.name for blocker in scenario.blockers()] == ["Llanowar Elves"]


def test_a_protector_who_leaves_the_game_is_replaced():
    """CR 704.5x / 310.11: bob concedes, so he can no longer protect carol's
    Siege, and carol's only remaining opponent becomes its protector."""
    scenario, siege = _three_player_siege_board()

    scenario.game.concede("bob")
    scenario.game.check_state_based_actions()

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.protector == "alice"


def test_sieges_whose_controllers_become_their_protectors_get_new_ones():
    """CR 704.5y with CR 310.12a: a Siege's protector must be an opponent of
    its controller. Exchanging control of two Sieges hands each to its own
    protector, and each new controller then chooses one of their opponents."""
    scenario = (
        Scenario()
        .player("alice", hand=[SIEGE, "Shifting Loyalties"], battlefield=["Island"] * 6)
        .player("bob", hand=[OTHER_SIEGE])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alices = _enter_siege(scenario, SIEGE, "alice")
    bobs = scenario.put_onto_battlefield(OTHER_SIEGE, "bob")
    scenario.pass_until_resolved()  # Invasion of Ergamon's enters trigger
    assert (alices.protector, bobs.protector) == ("bob", "alice")

    casting = scenario.cast("Shifting Loyalties", username="alice")
    casting.choose_targets([alices, bobs])
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 6, username="alice")
    )
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert scenario.game.controller_of(alices).username == "bob"
    assert scenario.game.controller_of(bobs).username == "alice"
    assert (alices.protector, bobs.protector) == ("alice", "bob")


def test_a_staged_siege_with_no_protector_is_given_one():
    """CR 704.5x: a battle nobody protects and nobody is attacking gets one
    chosen by its controller as a state-based action."""
    scenario = Scenario().player("alice", battlefield=[OTHER_SIEGE]).player("bob").build()
    siege = scenario.game.battlefield[0]
    assert siege.protector is None

    scenario.game.check_state_based_actions()

    assert siege.protector == "bob"


def test_a_copy_entering_as_a_siege_chooses_its_protector_as_it_enters():
    """CR 310.9a: "As a battle enters the battlefield, its controller chooses a
    player to be its protector." Clever Impersonator entering as a copy of a
    Siege (CR 614.1c) enters as a battle, so the choice is made as it enters,
    not left to a later state-based action (CR 704.5x)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Clever Impersonator"])
        .player("bob", battlefield=[OTHER_SIEGE])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = scenario.find(OTHER_SIEGE, Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(siege, username="alice", source="Clever Impersonator")

    copy = scenario.put_onto_battlefield("Clever Impersonator", "alice")

    assert scenario.game.characteristics_of(copy).name == OTHER_SIEGE
    assert copy.protector == "bob"


def test_no_new_protector_while_the_battle_is_being_attacked():
    """CR 704.5x applies only if "no attacking creatures are currently
    attacking that battle": bob concedes while alice attacks the Siege he
    protects, so it keeps no protector in the game until combat is over."""
    scenario, siege = _three_player_siege_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"), defending=siege)
    scenario.pass_until_resolved()

    scenario.game.concede("bob")
    scenario.game.check_state_based_actions()

    assert siege.zone is Zone.BATTLEFIELD
    assert siege.protector == "bob"


def test_the_defending_player_outlives_the_battle_leaving_the_battlefield():
    """CR 508.5: the defending player is "the protector of the battle that
    creature was attacking before it was removed from combat"."""
    scenario = (
        Scenario().player("alice", hand=[SIEGE], battlefield=["Goblin Guide"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    siege = _enter_siege(scenario, SIEGE, "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"), defending=siege)
    defender = TargetRef.coerce(siege)

    scenario.game.destroy(siege)

    assert siege.zone is Zone.GRAVEYARD
    assert defending_player(scenario.game, defender) == "bob"


def test_a_siege_controller_cannot_choose_themselves_as_protector():
    """CR 310.12a: the protector is chosen "from among its controller's
    opponents" - alice is not one of hers."""
    scenario = Scenario().player("alice", hand=[SIEGE]).player("bob").player("carol").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("alice", username="alice", source=SIEGE)

    with pytest.raises(ValueError, match="'alice' is not among the legal choices"):
        scenario.put_onto_battlefield(SIEGE, "alice")

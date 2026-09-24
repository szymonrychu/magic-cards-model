"""Equipment statics that key off the equipped creature (CR 301.5a), plus the
two triggered abilities that scale with equipped creatures.

- My Precious: "Equipped creature has hexproof and can't be blocked." - the
  bare `_ATTACHED_CREATURE_STATIC_RE` keyword-list shape
  (`machines/layers.py`), proven here rather than newly built.
- My Precious // Allure of Power's Adventure half: "As an additional cost to
  cast this spell, sacrifice a creature. Draw two cards." - an ordinary
  additional-cost spell, proven so the Adventure face resolves correctly
  (its own classification as an Adventure face is C01-T8's).
- Orcrist, Goblin-cleaver: "Whenever equipped creature deals combat damage to
  a player, choose a creature type. Create a Treasure token for each
  creature you control of that type."
- Dain Ironfoot: "Whenever Dain attacks, each equipped attacking creature
  gains double strike until end of turn."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import evasion_restriction_refusal, has_keyword
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def _equip(scenario, equipment, target, *mana_sources, username="alice"):
    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in mana_sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def test_my_precious_grants_hexproof_and_unblockable_to_equipped_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["My Precious", "Grizzly Bears", "Swamp", "Swamp"])
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    precious = scenario.find("My Precious", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    assert not has_keyword(bears, "hexproof", scenario.game)
    assert evasion_restriction_refusal(scenario.game, bears, watchwolf) is None

    _equip(scenario, precious, bears, *swamps)

    assert has_keyword(bears, "hexproof", scenario.game)
    assert evasion_restriction_refusal(scenario.game, bears, watchwolf) is not None


def test_allure_of_power_sacrifices_a_creature_and_draws_two():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["My Precious // Allure of Power"],
            battlefield=["Grizzly Bears", "Swamp", "Swamp"],
            library=["Mountain", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    starting_hand = len(alice.hand)

    casting = scenario.cast("My Precious", sacrificing=[bears])
    casting.cast_as_adventure()
    assert casting.face == "Allure of Power"
    scenario.pay_with(casting.begin_paying(), *swamps)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    # -1 for the Adventure card itself leaving the hand to the stack, +2 drawn.
    assert len(alice.hand) == starting_hand - 1 + 2


def test_orcrist_creates_a_treasure_per_creature_of_the_chosen_type_on_combat_damage():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Orcrist, Goblin-cleaver",
                "Raging Goblin",
                "Goblin Guide",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goblin = scenario.creature("Raging Goblin", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="alice")
    _equip(
        scenario,
        scenario.find("Orcrist, Goblin-cleaver", Zone.BATTLEFIELD, "alice"),
        goblin,
        *sources,
    )

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose("Goblin")
    scenario.attack_with(goblin)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.pass_until_resolved()

    treasures = [
        state
        for state in scenario.game.battlefield
        if state.name == "Treasure Token" and state.controller == "alice"
    ]
    # 2 Goblins: Raging Goblin and Goblin Guide.
    assert len(treasures) == 2


def test_dain_gives_double_strike_to_every_equipped_attacker_only():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Dáin Ironfoot",
                "Dwarven Shortsword",
                "Grizzly Bears",
                "Raging Goblin",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dain = scenario.creature("Dáin Ironfoot", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    goblin = scenario.creature("Raging Goblin", "alice")
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    _equip(scenario, sword, bears, *sources)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dain, bears, goblin)
    scenario.pass_until_resolved()

    assert has_keyword(bears, "double strike", scenario.game)
    assert not has_keyword(goblin, "double strike", scenario.game)
    assert not has_keyword(dain, "double strike", scenario.game)

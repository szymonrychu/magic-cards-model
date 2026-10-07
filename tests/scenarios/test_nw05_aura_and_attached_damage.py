"""Damage dealt by an Aura or Equipment, by the permanent it is attached to,
and by a creature an ability names ("that creature", "it", "each creature you
control") rather than by the ability's own source.

- Fatal Attraction: "When this Aura enters, it deals 2 damage to enchanted
  creature." / "At the beginning of your upkeep, this Aura deals 4 damage to
  enchanted creature."
- Tilonalli's Crown: "When this Aura enters, it deals 1 damage to enchanted
  creature."
- Enslave: "At the beginning of your upkeep, enchanted creature deals 1 damage
  to its owner."
- Pain for All: "When this Aura enters, enchanted creature deals damage equal
  to its power to any other target."
- Hunter's Bow: "When this Equipment enters, attach it to target creature you
  control. That creature deals damage equal to its power to up to one target
  creature you don't control."
- Stalking Yeti: "When this creature enters, if it's on the battlefield, it
  deals damage equal to its power to target creature an opponent controls and
  that creature deals damage equal to its power to this creature."
- Case of the Gateway Express: "When this Case enters, choose target creature
  you don't control. Each creature you control deals 1 damage to that
  creature." / "To solve - Three or more creatures attacked this turn."
- Tiger-Tribe Hunter: "... you may sacrifice another creature. When you do,
  this creature deals damage equal to the sacrificed creature's power to
  target creature."

Second printings: Form of the Dinosaur (the "and that creature deals damage
equal to its power to ..." return half, read by the same reader as Stalking
Yeti's), Legolas, Master Archer (a self-bite to "up to one target creature"),
Heart-Piercer Manticore (the reflexive sacrifice bite, "that creature's
power"). No other legal printing carries an Aura's own damage to "enchanted
creature", "enchanted creature deals ... to its owner", "attach it to target
creature you control. That creature deals ...", "Each creature you control
deals N damage to that creature" or "creatures attacked this turn" - see
MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 120.3** - damage's results depend on its source and its recipient;
  lifelink and deathtouch follow the source.
- **CR 303.4b** - the object an Aura is attached to is "enchanted".
- **CR 115.4** - "any target" is a creature, player, planeswalker or battle.
- **CR 701.14a** - fight is each creature dealing damage to the other; a bite
  is one-sided and Stalking Yeti's two halves are not the fight keyword.
- **CR 115.1** - "choose target creature" is a targeted choice.
- **CR 719.3a** - "To solve - [Condition]" is checked at the beginning of
  your end step.
- **CR 603.12** - "When you do" is a reflexive triggered ability.
- **CR 608.2h** - the sacrificed creature's power is its last known power.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import attach_permanent
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LANDS = ["Mountain"] * 4 + ["Swamp"] * 2 + ["Plains"] * 2 + ["Forest"] * 2


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _walk_to(scenario, step: Step) -> None:
    while scenario.step is not step:
        scenario.advance()
        _drain(scenario)


def _main(alice=(), bob=(), hand=(), *, lands=True) -> object:
    scenario = (
        Scenario()
        .player("alice", battlefield=[*(LANDS if lands else []), *alice], hand=list(hand))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def test_every_listed_and_proof_card_reads_handled():
    for name in (
        "Fatal Attraction",
        "Tilonalli's Crown",
        "Enslave",
        "Pain for All",
        "Hunter's Bow",
        "Stalking Yeti",
        "Case of the Gateway Express",
        "Tiger-Tribe Hunter",
        "Form of the Dinosaur",
        "Legolas, Master Archer",
        "Heart-Piercer Manticore",
    ):
        assert set(_outcomes(name)) == {"handled"}, (name, _outcomes(name))


# -- an Aura's own damage to enchanted creature -------------------------------


def test_fatal_attraction_enters_and_deals_two_to_enchanted_creature():
    scenario = _main(bob=["Craw Wurm"], hand=["Fatal Attraction"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack("Fatal Attraction", targets=[wurm], auto=True)
    scenario.resolve_top()
    _drain(scenario)
    assert wurm.damage == 2
    assert _notices(scenario) == []


def test_fatal_attraction_damage_has_the_aura_as_source_not_the_creature():
    """CR 120.3: a lifelink creature dealt damage by the Aura gains nobody
    life - the Aura, not the creature, dealt it."""
    scenario = _main(bob=["Vampire Nighthawk"], hand=["Fatal Attraction"])
    nighthawk = scenario.creature("Vampire Nighthawk", "bob")
    scenario.cast_onto_stack("Fatal Attraction", targets=[nighthawk], auto=True)
    scenario.resolve_top()
    _drain(scenario)
    assert nighthawk.damage == 2
    assert scenario.player("bob").life == 20 and scenario.player("alice").life == 20


def test_fatal_attraction_upkeep_deals_four_in_its_controllers_upkeep():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fatal Attraction"])
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    attach_permanent(scenario.game, scenario.find("Fatal Attraction", Zone.BATTLEFIELD), dreadmaw)
    _walk_to(scenario, Step.UPKEEP)
    assert dreadmaw.damage == 4


def test_fatal_attraction_does_not_trigger_in_the_opponents_upkeep():
    scenario = (
        Scenario()
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .player("alice", battlefield=["Fatal Attraction"])
        .build()
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    attach_permanent(scenario.game, scenario.find("Fatal Attraction", Zone.BATTLEFIELD), dreadmaw)
    _walk_to(scenario, Step.UPKEEP)
    assert scenario.turn.active_player == "bob"
    assert dreadmaw.damage == 0


def test_fatal_attraction_upkeep_does_nothing_once_the_creature_is_gone():
    """The trigger is on the stack when the creature leaves: the Aura has
    nothing to damage, and no player is dealt the damage instead."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fatal Attraction", "Craw Wurm"])
        .player("bob")
        .build()
    )
    wurm = scenario.creature("Craw Wurm", "alice")
    attach_permanent(scenario.game, scenario.find("Fatal Attraction", Zone.BATTLEFIELD), wurm)
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Fatal Attraction's triggered ability"]
    scenario.game.sacrifice(wurm)
    scenario.resolve_top()
    assert scenario.player("alice").life == 20 and scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_tilonallis_crown_pings_its_own_creature_after_the_boost():
    scenario = _main(alice=["Grizzly Bears"], hand=["Tilonalli's Crown"])
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack("Tilonalli's Crown", targets=[bears], auto=True)
    scenario.resolve_top()
    _drain(scenario)
    assert bears.damage == 1
    assert scenario.game.power_of(bears) == 5
    assert bears.zone is Zone.BATTLEFIELD


# -- "enchanted creature deals" -----------------------------------------------


def _enslaved(creature: str = "Vampire Nighthawk"):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Enslave"])
        .player("bob", battlefield=[creature])
        .build()
    )
    stolen = scenario.creature(creature, "bob")
    attach_permanent(scenario.game, scenario.find("Enslave", Zone.BATTLEFIELD), stolen)
    return scenario, stolen


def test_enslave_upkeep_damages_the_owner_not_the_controller():
    scenario, stolen = _enslaved("Grizzly Bears")
    assert scenario.game.controller_of(stolen).username == "alice"
    _walk_to(scenario, Step.UPKEEP)
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20


def test_enslave_damage_is_dealt_by_the_enchanted_creature_lifelink_follows_it():
    """CR 120.3 / lifelink: the stolen Nighthawk is the source, so its
    controller (alice) gains the life, while its owner loses it."""
    scenario, _ = _enslaved()
    _walk_to(scenario, Step.UPKEEP)
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21


def test_pain_for_all_enchanted_creature_bites_any_other_target():
    scenario = _main(alice=["Hill Giant"], hand=["Pain for All"])
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_onto_stack("Pain for All", targets=[giant], auto=True)
    scenario.will_choose_targets("bob")
    scenario.resolve_top()
    _drain(scenario)
    assert scenario.player("bob").life == 17
    assert giant.damage == 0


def test_pain_for_all_bite_is_dealt_by_the_creature_deathtouch_and_lifelink():
    scenario = _main(alice=["Vampire Nighthawk"], bob=["Craw Wurm"], hand=["Pain for All"])
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack("Pain for All", targets=[nighthawk], auto=True)
    scenario.will_choose_targets(wurm)
    scenario.resolve_top()
    _drain(scenario)
    scenario.state_based_actions()
    assert wurm.zone is Zone.GRAVEYARD, "deathtouch from the enchanted creature"
    assert scenario.player("alice").life == 22


# -- Hunter's Bow: attach, then "that creature" bites --------------------------


def test_hunters_bow_attaches_then_the_creature_bites():
    scenario = _main(alice=["Hill Giant"], bob=["Grizzly Bears"], hand=["Hunter's Bow"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Hunter's Bow", auto=True)
    scenario.will_choose_targets(giant, bears)
    scenario.resolve_top()
    _drain(scenario)
    bow = scenario.find("Hunter's Bow", Zone.BATTLEFIELD)
    assert bow.attached_to == giant.id
    assert bears.zone is Zone.GRAVEYARD, "3 damage from the 3-power Giant"
    assert giant.damage == 0, "a bite, not a fight"


def test_hunters_bow_up_to_one_may_choose_no_victim():
    scenario = _main(alice=["Hill Giant"], bob=["Grizzly Bears"], hand=["Hunter's Bow"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Hunter's Bow", auto=True)
    scenario.will_choose_targets(giant)
    scenario.resolve_top()
    _drain(scenario)
    assert scenario.find("Hunter's Bow", Zone.BATTLEFIELD).attached_to == giant.id
    assert bears.damage == 0 and giant.damage == 0


def test_hunters_bow_bite_source_is_the_creature_lifelink():
    scenario = _main(alice=["Vampire Nighthawk"], bob=["Craw Wurm"], hand=["Hunter's Bow"])
    nighthawk = scenario.creature("Vampire Nighthawk", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack("Hunter's Bow", auto=True)
    scenario.will_choose_targets(nighthawk, wurm)
    scenario.resolve_top()
    _drain(scenario)
    assert wurm.zone is Zone.GRAVEYARD, "deathtouch follows the biter"
    assert scenario.player("alice").life == 22


def test_hunters_bow_illegal_first_target_bites_nothing():
    """CR 608.2b: "that creature" is the first target; gone, it deals nothing,
    and the victim is not hurt by anything else."""
    scenario = _main(alice=["Hill Giant"], bob=["Grizzly Bears"], hand=["Hunter's Bow"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Hunter's Bow", auto=True)
    scenario.will_choose_targets(giant, bears)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.game.sacrifice(giant)
    scenario.resolve_top()
    assert bears.damage == 0


# -- mutual bite ---------------------------------------------------------------


def test_stalking_yeti_and_its_victim_damage_each_other():
    scenario = _main(bob=["Grizzly Bears"], hand=["Stalking Yeti"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Stalking Yeti", auto=True)
    scenario.will_choose_targets(bears)
    scenario.resolve_top()
    _drain(scenario)
    yeti = scenario.creature("Stalking Yeti", "alice")
    assert bears.zone is Zone.GRAVEYARD
    assert yeti.damage == 2


def test_stalking_yeti_damage_is_simultaneous_both_deal_their_power():
    """Both halves resolve before state-based actions (CR 704.3): the Hill
    Giant, lethally damaged by the first half, still deals its power back."""
    scenario = _main(bob=["Hill Giant"], hand=["Stalking Yeti"])
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Stalking Yeti", auto=True)
    scenario.will_choose_targets(giant)
    scenario.resolve_top()
    _drain(scenario)
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.find("Stalking Yeti", Zone.GRAVEYARD) is not None


def test_stalking_yeti_illegal_target_means_neither_half_happens():
    scenario = _main(bob=["Grizzly Bears"], hand=["Stalking Yeti"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Stalking Yeti", auto=True)
    scenario.will_choose_targets(bears)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()
    scenario.game.sacrifice(bears)
    scenario.resolve_top()
    assert scenario.creature("Stalking Yeti", "alice").damage == 0


def test_form_of_the_dinosaur_proof_the_return_half_hits_you():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Form of the Dinosaur"])
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_choose_targets(wurm)
    _walk_to(scenario, Step.UPKEEP)
    assert wurm.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 14, "the Wurm's 6 power back at alice"


# -- Case of the Gateway Express -----------------------------------------------


def test_case_each_creature_you_control_deals_one_to_the_chosen_creature():
    scenario = _main(
        alice=["Grizzly Bears", "Elite Vanguard", "Vampire Nighthawk"],
        bob=["Craw Wurm", "Hill Giant"],
        hand=["Case of the Gateway Express"],
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Case of the Gateway Express", auto=True)
    scenario.will_choose_targets(wurm)
    scenario.resolve_top()
    _drain(scenario)
    scenario.state_based_actions()
    assert wurm.zone is Zone.GRAVEYARD, "the Nighthawk's 1 damage has deathtouch"
    assert giant.damage == 0
    assert scenario.player("alice").life == 21, "lifelink: each creature is its own source"


def test_case_with_no_creatures_you_control_deals_nothing():
    scenario = _main(bob=["Craw Wurm"], hand=["Case of the Gateway Express"])
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.cast_onto_stack("Case of the Gateway Express", auto=True)
    scenario.will_choose_targets(wurm)
    scenario.resolve_top()
    _drain(scenario)
    assert wurm.damage == 0
    assert _notices(scenario) == []


def _case_attack(attackers: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Case of the Gateway Express", *attackers])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*[scenario.creature(name, "alice") for name in attackers])
    scenario.no_blocks()
    _walk_to(scenario, Step.END_STEP)
    return scenario, scenario.find("Case of the Gateway Express", Zone.BATTLEFIELD)


def test_case_is_solved_when_three_creatures_attacked_this_turn():
    scenario, case = _case_attack(["Grizzly Bears", "Elite Vanguard", "Raging Goblin"])
    assert case.solved is True
    assert scenario.game.power_of(scenario.creature("Grizzly Bears", "alice")) == 3


def test_case_is_not_solved_with_two_attackers():
    scenario, case = _case_attack(["Grizzly Bears", "Elite Vanguard"])
    assert case.solved is False
    assert _notices(scenario) == []


# -- up to one target: Legolas (proof) -----------------------------------------


def test_legolas_bites_up_to_one_target_creature():
    scenario = _main(alice=["Legolas, Master Archer"], bob=["Grizzly Bears"], hand=["Shock"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Shock", targets=[bears], auto=True)
    scenario.will_choose_targets(bears)
    _drain(scenario)
    assert bears.zone is Zone.GRAVEYARD or bears.damage >= 3


def test_legolas_may_choose_no_target():
    scenario = _main(
        alice=["Legolas, Master Archer"], bob=["Craw Wurm", "Hill Giant"], hand=["Shock"]
    )
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_onto_stack("Shock", targets=[wurm], auto=True)
    scenario.will_choose_targets()
    _drain(scenario)
    assert wurm.damage == 2 and giant.damage == 0


# -- reflexive sacrifice bite ----------------------------------------------------


def _tiger_attack(alice: list[str], bob: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tiger-Tribe Hunter", *alice])
        .player("bob", battlefield=bob)
    ).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_tiger_tribe_hunter_sacrifices_and_bites_for_the_sacrificed_power():
    scenario = _tiger_attack(["Hill Giant", "Grizzly Bears"], ["Craw Wurm"])
    hunter = scenario.creature("Tiger-Tribe Hunter", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(bears)
    scenario.will_choose_targets(wurm)
    scenario.attack_with(hunter, giant)
    _drain(scenario)
    assert bears.zone is Zone.GRAVEYARD
    assert wurm.damage == 2


def test_tiger_tribe_hunter_declined_sacrifice_bites_nothing():
    scenario = _tiger_attack(["Hill Giant", "Grizzly Bears"], ["Craw Wurm"])
    hunter = scenario.creature("Tiger-Tribe Hunter", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    scenario.will_take_the_may(False)
    scenario.attack_with(hunter, giant)
    _drain(scenario)
    assert wurm.damage == 0
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_tiger_tribe_hunter_pack_tactics_condition_is_still_read():
    """Total attacking power 4 is below 6: no trigger, no sacrifice offered."""
    scenario = _tiger_attack(["Grizzly Bears"], ["Craw Wurm"])
    hunter = scenario.creature("Tiger-Tribe Hunter", "alice")
    scenario.attack_with(hunter)
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack_is_empty


def test_tiger_tribe_hunter_uses_last_known_power_of_a_pumped_sacrifice():
    """CR 608.2h: Tilonalli's Crown made the Bears 5/2; that is the power the
    bite reads after it is sacrificed."""
    scenario = _tiger_attack(
        ["Hill Giant", "Grizzly Bears", "Tilonalli's Crown"], ["Colossal Dreadmaw"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    attach_permanent(scenario.game, scenario.find("Tilonalli's Crown", Zone.BATTLEFIELD), bears)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(bears)
    scenario.will_choose_targets(dreadmaw)
    scenario.attack_with(
        scenario.creature("Tiger-Tribe Hunter", "alice"), scenario.creature("Hill Giant", "alice")
    )
    _drain(scenario)
    assert dreadmaw.damage == 5


def test_heart_piercer_manticore_proof_bites_any_target_for_that_creatures_power():
    scenario = _main(alice=["Hill Giant"], hand=["Heart-Piercer Manticore"])
    giant = scenario.creature("Hill Giant", "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(giant)
    scenario.will_choose_targets("bob")
    scenario.cast_onto_stack("Heart-Piercer Manticore", auto=True)
    scenario.resolve_top()
    _drain(scenario)
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17

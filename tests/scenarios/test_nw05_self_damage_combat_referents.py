"""A creature's own combat trigger damaging what the combat names: the
creatures blocking it, the creatures it blocked, the blocker that just
blocked it, the defending player, the player or planeswalker it is attacking.

- Battle-Scarred Goblin: "Whenever this creature becomes blocked, it deals 1
  damage to each creature blocking it."
- Cathedral Membrane: "When this creature dies during combat, it deals 6
  damage to each creature it blocked this combat."
- Acolyte of the Inferno: "Whenever this creature becomes blocked by a
  creature, it deals 2 damage to that creature."
- Falkenrath Perforator: "Whenever this creature attacks, it deals 1 damage to
  defending player."
- Rakdos Roustabout: "Whenever this creature becomes blocked, it deals 1
  damage to the player or planeswalker it's attacking."
- Scorch Spitter: "Whenever this creature attacks, it deals 1 damage to the
  player or planeswalker it's attacking."

Second printings (proof the readers are templates, not rows): Kolaghan
Aspirant and Inferno Elemental ("that creature", one trigger per blocker),
Assembled Alphas ("that creature and ... that creature's controller"), Mage
Slayer and Generous Plunderer ("damage equal to ..." to the attacked player
or the defending player). Lord of Shatterskull Pass's and Simian Sling's
damage sentences (the keyword machines are another task's) must read handled
from these readers.

No second legal printing carries "each creature blocking it" (Fire Juggler
needs clash, Ib Halfheart a sacrifice-reflexive on a condition no reader
matches) or "each creature it blocked this combat" - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 509.3c** - "becomes blocked" triggers once each combat for that
  creature, even when it is blocked by several.
- **CR 509.3d** - "becomes blocked by a creature" triggers once for each
  creature that blocks it.
- **CR 509.1h** - an attacker stays blocked once blockers were declared, even
  when every blocker is gone.
- **CR 508.5** - "defending player": the player attacked, the controller of
  the planeswalker attacked.
- **CR 120.3c** - damage to a planeswalker removes that many loyalty counters.
- **CR 603.10a** - "dies" looks back to the creature as it was.
- **CR 120.3** - each recipient is its own damage event.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import attach_permanent
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _drain(scenario) -> None:
    """Resolve every triggered ability until the stack is empty."""
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


def _combat(alice, bob, *, extra=()) -> Scenario:
    """Alice's battlefield against bob's, ready to declare attackers."""
    builder = (
        Scenario().player("alice", battlefield=list(alice)).player("bob", battlefield=list(bob))
    )
    for username, board in extra:
        builder = builder.player(username, battlefield=list(board))
    scenario = builder.build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _loyalty(permanent) -> int:
    return permanent.counter_count("loyalty")


def _supported(name: str) -> list[str]:
    return [
        clause.outcome for clause in card_support(card(name)).clauses if clause.kind != "keyword"
    ]


# -- Battle-Scarred Goblin: "each creature blocking it" ----------------------


def test_battle_scarred_goblin_hits_every_creature_blocking_it():
    scenario = _combat(["Battle-Scarred Goblin"], ["Giant Spider", "Hill Giant"])
    goblin = scenario.creature("Battle-Scarred Goblin", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(goblin)
    scenario.block(goblin, spider, giant)
    _drain(scenario)

    assert spider.damage == 1 and giant.damage == 1
    assert goblin.damage == 0
    assert _notices(scenario) == []


def test_battle_scarred_goblin_triggers_once_however_many_block_it():
    """CR 509.3c: "becomes blocked" is once per combat for the creature."""
    scenario = _combat(["Battle-Scarred Goblin"], ["Giant Spider", "Hill Giant"])
    goblin = scenario.creature("Battle-Scarred Goblin", "alice")
    scenario.attack_with(goblin)
    scenario.block(
        goblin, scenario.creature("Giant Spider", "bob"), scenario.creature("Hill Giant", "bob")
    )
    scenario.game.put_triggers_on_stack()

    assert len(scenario.game.stack) == 1
    _drain(scenario)
    assert scenario.creature("Giant Spider", "bob").damage == 1, "one trigger, not one per blocker"


def test_battle_scarred_goblin_does_not_hit_a_creature_blocking_something_else():
    scenario = _combat(["Battle-Scarred Goblin", "Grizzly Bears"], ["Giant Spider", "Hill Giant"])
    goblin = scenario.creature("Battle-Scarred Goblin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(goblin, bears)
    scenario.block(goblin, spider)
    scenario.block(bears, giant)
    _drain(scenario)

    assert spider.damage == 1
    assert giant.damage == 0, "blocking the Bears, not the Goblin"


def test_battle_scarred_goblin_unblocked_never_triggers():
    scenario = _combat(["Battle-Scarred Goblin"], ["Giant Spider"])
    scenario.attack_with(scenario.creature("Battle-Scarred Goblin", "alice"))
    scenario.no_blocks()
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty


def test_battle_scarred_goblin_stays_blocked_when_the_trigger_kills_every_blocker():
    """CR 509.1h: the attacker deals no combat damage to the player."""
    scenario = _combat(["Battle-Scarred Goblin"], ["Ornery Goblin"])
    goblin = scenario.creature("Battle-Scarred Goblin", "alice")
    blocker = scenario.creature("Ornery Goblin", "bob")
    scenario.attack_with(goblin)
    scenario.block(goblin, blocker)
    _drain(scenario)
    scenario.state_based_actions()

    assert blocker.zone is Zone.GRAVEYARD
    scenario.combat_damage()
    assert scenario.player("bob").life == 20


def test_battle_scarred_goblin_reads_handled():
    assert _supported("Battle-Scarred Goblin") == ["handled"]


# -- Cathedral Membrane: "each creature it blocked this combat" --------------


def test_cathedral_membrane_dying_in_combat_hits_the_creature_it_blocked():
    scenario = _combat(["Hill Giant"], ["Cathedral Membrane"])
    giant = scenario.creature("Hill Giant", "alice")
    membrane = scenario.creature("Cathedral Membrane", "bob")
    scenario.attack_with(giant)
    scenario.block(giant, membrane)
    scenario.combat_damage()  # Hill Giant's 3 damage kills the 0/3 Membrane
    _drain(scenario)

    assert membrane.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD, "6 damage from the dying Membrane"
    assert _notices(scenario) == []


def test_cathedral_membrane_leaves_an_unblocked_attacker_alone():
    scenario = _combat(["Hill Giant", "Grizzly Bears"], ["Cathedral Membrane"])
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    membrane = scenario.creature("Cathedral Membrane", "bob")
    scenario.attack_with(giant, bears)
    scenario.block(giant, membrane)
    scenario.combat_damage()
    _drain(scenario)

    assert giant.zone is Zone.GRAVEYARD
    assert bears.damage == 0 and bears.zone is Zone.BATTLEFIELD


def test_cathedral_membrane_dying_outside_combat_does_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain", "Hill Giant"])
        .player("bob", battlefield=["Cathedral Membrane"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    membrane = scenario.creature("Cathedral Membrane", "bob")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=[membrane],
    )
    _drain(scenario)

    assert membrane.zone is Zone.GRAVEYARD
    assert scenario.creature("Hill Giant", "alice").damage == 0


def test_cathedral_membrane_reads_handled():
    assert _supported("Cathedral Membrane") == ["handled"]


# -- Acolyte of the Inferno and its second printings: "that creature" --------


def test_acolyte_of_the_inferno_hits_each_blocker_once_each():
    """CR 509.3d: one trigger per blocker, each damaging only its own blocker."""
    scenario = _combat(["Acolyte of the Inferno"], ["Giant Spider", "Hill Giant"])
    acolyte = scenario.creature("Acolyte of the Inferno", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(acolyte)
    scenario.block(acolyte, spider, giant)
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 2
    _drain(scenario)

    assert spider.damage == 2 and giant.damage == 2
    assert acolyte.damage == 0
    assert _notices(scenario) == []


def test_acolyte_of_the_inferno_spares_a_creature_that_did_not_block():
    scenario = _combat(["Acolyte of the Inferno"], ["Giant Spider", "Hill Giant"])
    acolyte = scenario.creature("Acolyte of the Inferno", "alice")
    scenario.attack_with(acolyte)
    scenario.block(acolyte, scenario.creature("Giant Spider", "bob"))
    _drain(scenario)

    assert scenario.creature("Hill Giant", "bob").damage == 0


def test_kolaghan_aspirant_proves_the_same_template_on_a_second_printing():
    scenario = _combat(["Kolaghan Aspirant"], ["Giant Spider"])
    aspirant = scenario.creature("Kolaghan Aspirant", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(aspirant)
    scenario.block(aspirant, spider)
    _drain(scenario)

    assert spider.damage == 1
    assert _notices(scenario) == []


def test_inferno_elemental_hits_the_creature_it_blocks():
    scenario = _combat(["Hill Giant"], ["Inferno Elemental"])
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant)
    scenario.block(giant, scenario.creature("Inferno Elemental", "bob"))
    _drain(scenario)

    assert giant.zone is Zone.GRAVEYARD or giant.damage == 3


def test_inferno_elemental_hits_the_creature_blocking_it():
    scenario = _combat(["Inferno Elemental"], ["Giant Spider"])
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(scenario.creature("Inferno Elemental", "alice"))
    scenario.block(scenario.creature("Inferno Elemental", "alice"), spider)
    _drain(scenario)

    assert spider.damage == 3
    assert scenario.creature("Inferno Elemental", "alice").damage == 0


def test_assembled_alphas_hits_that_creature_and_its_controller():
    scenario = _combat(["Assembled Alphas"], ["Giant Spider"])
    alphas = scenario.creature("Assembled Alphas", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(alphas)
    scenario.block(alphas, spider)
    _drain(scenario)

    assert spider.damage == 3
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20
    assert _notices(scenario) == []


def test_assembled_alphas_blocking_hits_the_attacker_and_its_controller():
    scenario = _combat(["Hill Giant"], ["Assembled Alphas"])
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant)
    scenario.block(giant, scenario.creature("Assembled Alphas", "bob"))
    _drain(scenario)

    assert scenario.player("alice").life == 17, "the attacker's controller"
    assert scenario.player("bob").life == 20


def test_assembled_alphas_still_hits_the_controller_when_the_creature_has_gone():
    """Scryfall ruling: the controller is dealt damage even when the creature
    has left the battlefield (last known information)."""
    scenario = _combat(["Assembled Alphas"], ["Giant Spider"])
    alphas = scenario.creature("Assembled Alphas", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(alphas)
    scenario.block(alphas, spider)
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(spider)
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


# -- defending player: Falkenrath Perforator ---------------------------------


def test_falkenrath_perforator_hits_the_defending_player():
    scenario = _combat(["Falkenrath Perforator"], [])
    scenario.attack_with(scenario.creature("Falkenrath Perforator", "alice"))
    _drain(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 20
    assert _notices(scenario) == []


def test_falkenrath_perforator_in_multiplayer_hits_only_the_player_it_attacks():
    scenario = _combat(["Falkenrath Perforator"], [], extra=[("carol", [])])
    scenario.attack_with(scenario.creature("Falkenrath Perforator", "alice"), defending="carol")
    _drain(scenario)

    assert scenario.player("carol").life == 19
    assert scenario.player("bob").life == 20


def test_falkenrath_perforator_attacking_a_planeswalker_hits_that_planeswalkers_controller():
    """CR 508.5: the controller of the planeswalker is the defending player."""
    scenario = _combat(["Falkenrath Perforator"], ["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    loyalty = _loyalty(liliana)
    scenario.attack_with(scenario.creature("Falkenrath Perforator", "alice"), defending=liliana)
    _drain(scenario)

    assert scenario.player("bob").life == 19
    assert _loyalty(liliana) == loyalty


def test_falkenrath_perforator_removed_from_combat_still_names_who_it_attacked():
    """CR 508.5: no longer attacking, the defending player is whoever it was
    attacking before it was removed from combat."""
    scenario = _combat(["Falkenrath Perforator"], [])
    perforator = scenario.creature("Falkenrath Perforator", "alice")
    scenario.attack_with(perforator)
    scenario.game.put_triggers_on_stack()
    scenario.game.combat.remove(perforator.id)
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_generous_plunderer_hits_the_defending_player_for_their_artifacts():
    scenario = _combat(["Generous Plunderer"], ["Treasure Map", "Sol Ring", "Hill Giant"])
    scenario.attack_with(scenario.creature("Generous Plunderer", "alice"))
    _drain(scenario)

    assert scenario.player("bob").life == 18, "two artifacts they control"
    assert _notices(scenario) == []


# -- the attacked player or planeswalker: Rakdos Roustabout, Scorch Spitter --


def test_scorch_spitter_hits_the_player_it_attacks():
    scenario = _combat(["Scorch Spitter"], [])
    scenario.attack_with(scenario.creature("Scorch Spitter", "alice"))
    _drain(scenario)

    assert scenario.player("bob").life == 19
    assert _notices(scenario) == []


def test_scorch_spitter_hits_the_planeswalker_it_attacks_not_its_controller():
    """CR 120.3c: the planeswalker loses loyalty; its controller does not lose
    life."""
    scenario = _combat(["Scorch Spitter"], ["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    loyalty = _loyalty(liliana)
    scenario.attack_with(scenario.creature("Scorch Spitter", "alice"), defending=liliana)
    _drain(scenario)

    assert _loyalty(liliana) == loyalty - 1
    assert scenario.player("bob").life == 20


def test_scorch_spitter_with_its_planeswalker_gone_deals_nothing():
    scenario = _combat(["Scorch Spitter"], ["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Scorch Spitter", "alice"), defending=liliana)
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(liliana)
    scenario.resolve_top()

    assert scenario.player("bob").life == 20


def test_rakdos_roustabout_hits_the_attacked_player_once_however_many_block():
    scenario = _combat(["Rakdos Roustabout"], ["Giant Spider", "Hill Giant"])
    roustabout = scenario.creature("Rakdos Roustabout", "alice")
    scenario.attack_with(roustabout)
    scenario.block(
        roustabout, scenario.creature("Giant Spider", "bob"), scenario.creature("Hill Giant", "bob")
    )
    scenario.game.put_triggers_on_stack()
    assert len(scenario.game.stack) == 1
    _drain(scenario)

    assert scenario.player("bob").life == 19


def test_rakdos_roustabout_hits_the_planeswalker_it_attacks():
    scenario = _combat(["Rakdos Roustabout"], ["Liliana of the Veil", "Giant Spider"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    loyalty = _loyalty(liliana)
    roustabout = scenario.creature("Rakdos Roustabout", "alice")
    scenario.attack_with(roustabout, defending=liliana)
    scenario.block(roustabout, scenario.creature("Giant Spider", "bob"))
    _drain(scenario)

    assert _loyalty(liliana) == loyalty - 1
    assert scenario.player("bob").life == 20


def test_mage_slayer_equipped_creature_deals_damage_equal_to_its_power_to_the_attacked_player():
    scenario = (
        Scenario().player("alice", battlefield=["Mage Slayer", "Hill Giant"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mage_slayer = scenario.find("Mage Slayer", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    attach_permanent(scenario.game, mage_slayer, giant)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    _drain(scenario)

    assert scenario.player("bob").life == 17, (
        "Hill Giant's power, from the attacker not the Equipment"
    )
    assert _notices(scenario) == []


# -- the two keyword-machine cards whose sentences these readers must read ----


def test_lord_of_shatterskull_pass_damage_sentence_reads_handled():
    outcomes = {
        clause.text: clause.outcome
        for clause in card_support(card("Lord of Shatterskull Pass")).clauses
    }
    damage = [outcome for text, outcome in outcomes.items() if "defending player controls" in text]
    assert damage == ["handled"]


def test_simian_sling_damage_sentence_reads_handled():
    outcomes = {
        clause.text: clause.outcome for clause in card_support(card("Simian Sling")).clauses
    }
    damage = [outcome for text, outcome in outcomes.items() if "defending player" in text]
    assert damage == ["handled"]


def test_every_listed_combat_referent_card_reads_handled():
    for name in (
        "Battle-Scarred Goblin",
        "Cathedral Membrane",
        "Acolyte of the Inferno",
        "Falkenrath Perforator",
        "Rakdos Roustabout",
        "Scorch Spitter",
    ):
        assert set(_supported(name)) == {"handled"}, name

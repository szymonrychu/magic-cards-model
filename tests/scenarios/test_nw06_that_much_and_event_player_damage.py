"""Damage that refers back to the triggering event: its dealer, its amount, the
player it named - and a discard's card, read by the sentence after it.

- Greatbow Doyen: "Whenever an Archer you control deals damage to a creature,
  that Archer deals that much damage to that creature's controller."
- Rampaging Raptor: "Whenever this creature deals combat damage to an
  opponent, it deals that much damage to target planeswalker that player
  controls or battle that player protects."
- Oath of Kaya: "Whenever an opponent attacks a planeswalker you control with
  one or more creatures, Oath of Kaya deals 2 damage to that player and you
  gain 2 life."
- Hellhole Rats: "When this creature enters, target player discards a card.
  This creature deals damage to that player equal to that card's mana value."

Second printings: Questing Beast ("it deals that much damage to target
planeswalker that player controls" - the same event-player target without the
battle half), Satyr Firedancer ("this creature deals that much damage to
target creature that player controls", off a spell's damage), Mordant Dragon
(the same target under "you may have it deal"). No other legal printing
carries "that `<type>` deals that much damage to that creature's controller",
the "deals N damage to that player and you gain N life" pair, or the discard-
then-"that card's mana value" damage - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 603.2** - the trigger event names the dealer, the amount and the
  player the effect refers back to.
- **CR 603.3d** - a trigger's targets are chosen as it is put on the stack.
- **CR 608.2b** - a target illegal on resolution is not affected.
- **CR 608.2c** - later text refers back to what earlier text did.
- **CR 608.2h** - "that creature's controller" is read as the effect applies.
- **CR 310.9e** - "the player who protects a battle" is its protector.
- **CR 202.3, 202.3a** - mana value; a land's is 0.
- **CR 615.6** - prevented damage is never dealt.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects.registries import trigger_effect_for
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


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


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def _life(scenario, username: str) -> int:
    return scenario.player(username).life


def test_every_listed_card_reads_handled():
    for name in (
        "Greatbow Doyen",
        "Rampaging Raptor",
        "Oath of Kaya",
        "Hellhole Rats",
        "Satyr Firedancer",
        "Mordant Dragon",
    ):
        outcomes = _outcomes(name)
        assert outcomes and set(outcomes) == {"handled"}, (name, outcomes)


def test_questing_beast_trigger_reads_handled():
    clauses = [c for c in card_support(card("Questing Beast")).clauses if c.kind == "triggered"]
    assert [c.outcome for c in clauses] == ["handled"]


# -- Greatbow Doyen ---------------------------------------------------------


def _doyen_combat(attackers: list[str], blockers: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Greatbow Doyen", *attackers])
        .player("bob", battlefield=blockers)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_doyen_an_archer_dealing_combat_damage_to_a_creature_hits_its_controller():
    scenario = _doyen_combat(["Meria's Outrider"], ["Hill Giant"])
    outrider = scenario.creature("Meria's Outrider", "alice")
    scenario.attack_with(outrider)
    scenario.block(outrider, scenario.creature("Hill Giant", "bob"))
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 15, "the Outrider's 4, +1 from Doyen's anthem = 5"
    assert _notices(scenario) == []


def test_doyen_the_damage_is_the_amount_actually_dealt_after_toughness():
    scenario = _doyen_combat(["Meria's Outrider"], ["Grizzly Bears"])
    outrider = scenario.creature("Meria's Outrider", "alice")
    scenario.attack_with(outrider)
    scenario.block(outrider, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 15, "all 5 is dealt to the 2/2: damage is not capped"


def test_doyen_a_non_archer_dealing_damage_does_not_trigger():
    scenario = _doyen_combat(["Hill Giant"], ["Grizzly Bears"])
    giant = scenario.creature("Hill Giant", "alice")
    scenario.attack_with(giant)
    scenario.block(giant, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 20


def test_doyen_itself_is_an_archer_and_its_damage_to_its_own_creature_hits_alice():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Greatbow Doyen", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.advance()
    scenario.game.deal_damage(
        scenario.creature("Grizzly Bears", "alice"),
        2,
        source=scenario.creature("Greatbow Doyen", "alice"),
    )
    _drain(scenario)

    assert _life(scenario, "alice") == 18, "that creature's controller is alice herself"
    assert _life(scenario, "bob") == 20


def test_doyen_damage_to_a_player_does_not_trigger():
    scenario = _doyen_combat(["Meria's Outrider"], [])
    scenario.attack_with(scenario.creature("Meria's Outrider", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 15, "only the combat damage itself"


def test_doyen_the_dealer_deals_it_so_an_archer_with_lifelink_would_gain():
    effect = trigger_effect_for(
        "Greatbow Doyen",
        TriggerEvent.DEALS_DAMAGE,
        "that Archer deals that much damage to that creature's controller.",
    )
    assert effect is not None
    assert not getattr(effect, "__name__", "").endswith("_notice_only")


# -- Rampaging Raptor / Questing Beast: event-player targets ----------------


def _raptor(defender_board: list[str], attacker: str = "Rampaging Raptor", mine=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, *mine])
        .player("bob", battlefield=defender_board)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_raptor_hits_a_planeswalker_the_damaged_opponent_controls():
    scenario = _raptor(["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Rampaging Raptor", "alice"))
    scenario.no_blocks()
    scenario.will_choose_targets(liliana)
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 16
    assert scenario.find("Liliana of the Veil", Zone.GRAVEYARD, "bob") is not None
    assert _notices(scenario) == []


def test_raptor_hits_a_battle_the_opponent_protects_even_one_its_controller_owns():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rampaging Raptor"], hand=["Invasion of Belenon"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battle = scenario.put_onto_battlefield("Invasion of Belenon", "alice")
    _drain(scenario)
    assert battle.protector == "bob"
    scenario.advance()
    scenario.advance()
    scenario.attack_with(scenario.creature("Rampaging Raptor", "alice"), defending="bob")
    scenario.no_blocks()
    scenario.will_choose_targets(battle)
    scenario.combat_damage()
    _drain(scenario)

    assert battle.counter_count("defense") == 1, "5 defense, 4 damage"


def test_raptor_cannot_target_a_planeswalker_its_own_controller_controls():
    scenario = _raptor(["Liliana of the Veil"], mine=["Liliana of the Veil"])
    mine = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    scenario.attack_with(scenario.creature("Rampaging Raptor", "alice"))
    scenario.no_blocks()
    scenario.will_choose_targets(mine)

    with pytest.raises(ValueError):
        scenario.combat_damage()
        scenario.game.put_triggers_on_stack()


def test_raptor_with_no_legal_target_does_nothing_more():
    scenario = _raptor(["Hill Giant"])
    raptor = scenario.creature("Rampaging Raptor", "alice")
    scenario.attack_with(raptor)
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 16
    assert scenario.creature("Hill Giant", "bob").damage == 0


def test_raptor_trample_damage_through_a_blocker_counts_only_what_reached_the_player():
    scenario = _raptor(["Grizzly Bears", "Liliana of the Veil"])
    raptor = scenario.creature("Rampaging Raptor", "alice")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(raptor)
    scenario.block(raptor, scenario.creature("Grizzly Bears", "bob"))
    scenario.will_choose_targets(liliana)
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 18
    assert liliana.counter_count("loyalty") == 1, "3 loyalty, 2 trample damage reached bob"


def test_questing_beast_same_template_without_the_battle_half():
    scenario = _raptor(["Liliana of the Veil"], attacker="Questing Beast")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Questing Beast", "alice"))
    scenario.no_blocks()
    scenario.will_choose_targets(liliana)
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 16
    assert scenario.find("Liliana of the Veil", Zone.GRAVEYARD, "bob") is not None


def test_satyr_firedancer_spell_damage_to_an_opponent_hits_their_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Satyr Firedancer", "Mountain"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _drain(scenario)

    assert _life(scenario, "bob") == 17
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None


def test_mordant_dragon_may_decline():
    scenario = _raptor(["Hill Giant"], attacker="Mordant Dragon")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(scenario.creature("Mordant Dragon", "alice"))
    scenario.no_blocks()
    scenario.will_choose_targets(giant)
    scenario.will_take_the_may(False)
    scenario.combat_damage()
    _drain(scenario)

    assert _life(scenario, "bob") == 15
    assert giant.damage == 0


def test_mordant_dragon_may_accept():
    scenario = _raptor(["Hill Giant"], attacker="Mordant Dragon")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(scenario.creature("Mordant Dragon", "alice"))
    scenario.no_blocks()
    scenario.will_choose_targets(giant)
    scenario.will_take_the_may(True)
    scenario.combat_damage()
    _drain(scenario)

    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None


# -- Oath of Kaya -----------------------------------------------------------


def _oath(attackers: list[str], walkers: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=attackers)
        .player("bob", battlefield=["Oath of Kaya", *walkers])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_oath_attacking_a_planeswalker_costs_the_attacker_and_gains_bob_life():
    scenario = _oath(["Grizzly Bears", "Hill Giant"], ["Liliana of the Veil"])
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(
        *scenario.creatures("Grizzly Bears", "Hill Giant", username="alice"), defending=liliana
    )
    _drain(scenario)

    assert _life(scenario, "alice") == 18, "once for the attack, not per creature"
    assert _life(scenario, "bob") == 22
    assert _notices(scenario) == []


def test_oath_attacking_the_player_does_not_trigger():
    scenario = _oath(["Grizzly Bears"], ["Liliana of the Veil"])
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")
    _drain(scenario)

    assert _life(scenario, "alice") == 20
    assert _life(scenario, "bob") == 20


# -- Hellhole Rats ----------------------------------------------------------


def _rats(bob_hand: list[str]):
    scenario = (
        Scenario().player("alice", hand=["Hellhole Rats"]).player("bob", hand=bob_hand).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    scenario.put_onto_battlefield("Hellhole Rats", "alice")
    return scenario


def test_rats_damage_equals_the_discarded_cards_mana_value():
    scenario = _rats(["Hill Giant"])
    _drain(scenario)

    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None
    assert _life(scenario, "bob") == 16
    assert _notices(scenario) == []


def test_rats_discarding_a_land_deals_nothing():
    scenario = _rats(["Mountain"])
    _drain(scenario)

    assert scenario.find("Mountain", Zone.GRAVEYARD, "bob") is not None
    assert _life(scenario, "bob") == 20


def test_rats_empty_hand_discards_nothing_and_deals_nothing():
    scenario = _rats([])
    _drain(scenario)

    assert _life(scenario, "bob") == 20


def test_rats_the_discarding_player_chooses_and_takes_that_cards_value():
    scenario = _rats(["Lightning Bolt", "Hill Giant"])
    scenario.will_discard(scenario.find("Lightning Bolt", Zone.HAND, "bob"), username="bob")
    _drain(scenario)

    assert _life(scenario, "bob") == 19
    assert scenario.find("Hill Giant", Zone.HAND, "bob") is not None

"""A trigger's own pronoun subject dealing damage equal to its power, or to each
opponent equal to a game count, and an Aura's "it deals damage to you equal to
its power".

- Goblin Fireleaper: "When this creature dies, it deals damage equal to its
  power to target creature an opponent controls."
- Stalking Vengeance: "Whenever another creature you control dies, it deals
  damage equal to its power to target player or planeswalker." - "it" is the
  creature that died, not Stalking Vengeance.
- Pyrotechnic Performer: "Whenever this creature or another creature you
  control is turned face up, that creature deals damage equal to its power to
  each opponent."
- Meria's Outrider: "it deals damage to each opponent equal to the number of
  basic land types among lands you control."
- Fanatic of Mogis: "it deals damage to each opponent equal to your devotion
  to red."
- Bind the Monster: "tap enchanted creature. It deals damage to you equal to
  its power."
- Cross-task sentences (Flametongue Yearling, Chainweb Aracnir, Flayer of the
  Hatebound) read by the same template.

Second printings: Warstorm Surge ("Whenever a creature you control enters, it
deals damage equal to its power to any target" - the entering creature is the
source), Heartfire Hero ("When this creature dies, it deals damage equal to
its power to each opponent" - last known power with its counters). No other
legal printing carries the "to each opponent equal to <count>" order with a
count that is not per-player, nor Bind the Monster's to-you-first rider - see
MEMORY.md; Stormbreath Dragon's per-player count and Molten Psyche's
metalcraft condition are the negative proofs that this reader leaves them to
their own readers.

Rules verified with `mise run rules:find`:

- **CR 603.2** - a trigger's event names the object the effect's pronoun
  refers back to.
- **CR 608.2h** - power is read as the effect is applied; an object that left
  its zone is read by its last known information.
- **CR 113.7a** - a source that left still performs the action.
- **CR 603.10a** - a dies trigger looks back in time.
- **CR 120.3** - each recipient of one damage instruction is dealt its damage
  at the same time.
- **CR 700.5** - devotion counts mana symbols among permanents' mana costs.
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


# -- support ----------------------------------------------------------------


def test_every_listed_card_reads_handled():
    for name in (
        "Goblin Fireleaper",
        "Stalking Vengeance",
        "Pyrotechnic Performer",
        "Meria's Outrider",
        "Fanatic of Mogis",
        "Bind the Monster",
        "Warstorm Surge",
        "Heartfire Hero",
    ):
        outcomes = _outcomes(name)
        assert outcomes and set(outcomes) == {"handled"}, (name, outcomes)


def test_cross_task_sentences_read_through_the_same_template():
    for name, event, sentence in (
        (
            "Flametongue Yearling",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            "it deals damage equal to its power to target creature.",
        ),
        (
            "Chainweb Aracnir",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            "it deals damage equal to its power to target creature with flying an opponent "
            "controls.",
        ),
        (
            "Flayer of the Hatebound",
            TriggerEvent.ENTERS_THE_BATTLEFIELD,
            "that creature deals damage equal to its power to any target.",
        ),
    ):
        effect = trigger_effect_for(name, event, sentence)
        assert effect is not None, name
        assert not getattr(effect, "__name__", "").endswith("_notice_only"), name


# -- Goblin Fireleaper: dies, last known power ------------------------------


def _fireleaper_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Fireleaper", "Mountain", "Mountain", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant", "Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_fireleaper_dies_and_deals_its_last_known_power_including_a_pump():
    scenario = _fireleaper_board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    scenario.activate(leaper, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.resolve_top()
    assert scenario.game.power_of(leaper) == 2
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.game.destroy(leaper)
    _drain(scenario)

    assert giant.damage == 2, "the pumped power it last had on the battlefield (CR 608.2h)"
    assert _notices(scenario) == []


def test_fireleaper_unpumped_deals_one():
    scenario = _fireleaper_board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.will_choose_targets(spider)
    scenario.game.destroy(leaper)
    _drain(scenario)

    assert spider.damage == 1
    assert scenario.creature("Grizzly Bears", "alice").damage == 0


def test_fireleaper_cannot_target_its_own_controllers_creature():
    scenario = _fireleaper_board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(leaper)

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Goblin Fireleaper", [bears])


def test_fireleaper_target_gone_before_resolution_does_nothing():
    scenario = _fireleaper_board()
    leaper = scenario.creature("Goblin Fireleaper", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.game.destroy(leaper)
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(giant)
    _drain(scenario)

    assert _life(scenario, "bob") == 20
    assert scenario.creature("Giant Spider", "bob").damage == 0


# -- Stalking Vengeance: "it" is the creature that died ---------------------


def test_stalking_vengeance_deals_the_dead_creatures_power_not_its_own():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stalking Vengeance", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    scenario.game.destroy(scenario.creature("Hill Giant", "alice"))
    _drain(scenario)

    assert _life(scenario, "bob") == 17, "Hill Giant's 3, not Stalking Vengeance's 5"
    assert _notices(scenario) == []


def test_stalking_vengeance_the_dead_creature_is_the_source_so_its_lifelink_applies():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stalking Vengeance", "Vampire Nighthawk"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob")
    scenario.game.destroy(scenario.creature("Vampire Nighthawk", "alice"))
    _drain(scenario)

    assert _life(scenario, "bob") == 18
    assert _life(scenario, "alice") == 22, "the Nighthawk deals it, with lifelink (CR 113.7a)"


def test_stalking_vengeance_can_hit_a_planeswalker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stalking Vengeance", "Grizzly Bears"])
        .player("bob", battlefield=["Liliana of the Veil"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(liliana)
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    _drain(scenario)

    assert liliana.counter_count("loyalty") == 1
    assert _life(scenario, "bob") == 20


def test_stalking_vengeance_does_not_trigger_on_itself_or_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stalking Vengeance"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature("Hill Giant", "bob"))
    scenario.game.destroy(scenario.creature("Stalking Vengeance", "alice"))
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty
    assert _life(scenario, "bob") == 20


# -- Pyrotechnic Performer: turned face up ----------------------------------


def _performer_board(*others: str, players=("bob",)):
    builder = Scenario().player(
        "alice", battlefield=["Pyrotechnic Performer", *others, *("Mountain",) * 4, "Plains"]
    )
    for username in players:
        builder = builder.player(username)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_performer_turned_face_up_deals_its_power_to_each_opponent():
    scenario = _performer_board(players=("bob", "carol"))
    performer = scenario.creature("Pyrotechnic Performer", "alice")
    performer.turn_face_down()
    scenario.turn_face_up(performer, *scenario.untapped_sources("Mountain"))
    _drain(scenario)

    assert _life(scenario, "bob") == 17
    assert _life(scenario, "carol") == 17
    assert _life(scenario, "alice") == 20
    assert _notices(scenario) == []


def test_performer_another_creature_turned_up_deals_that_creatures_power():
    scenario = _performer_board("Essence of Antiquity")
    essence = scenario.creature("Essence of Antiquity", "alice")
    essence.turn_face_down()
    scenario.turn_face_up(essence, *scenario.untapped_sources("Mountain", "Mountain", "Plains"))
    _drain(scenario)

    assert _life(scenario, "bob") == 19, "Essence of Antiquity's power 1, not the Performer's 3"


def test_two_performers_each_trigger_off_the_one_turned_up():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Pyrotechnic Performer", "Pyrotechnic Performer", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures(
        "Pyrotechnic Performer", "Pyrotechnic Performer", username="alice"
    )
    second.turn_face_down()
    scenario.turn_face_up(second, *scenario.untapped_sources("Mountain"))
    _drain(scenario)

    assert _life(scenario, "bob") == 14, "both triggers name the creature turned up: 3 + 3"


def test_performer_turned_up_creature_gone_uses_last_known_power():
    scenario = _performer_board()
    performer = scenario.creature("Pyrotechnic Performer", "alice")
    performer.turn_face_down()
    scenario.turn_face_up(performer, *scenario.untapped_sources("Mountain"))
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(performer)
    _drain(scenario)

    assert _life(scenario, "bob") == 17


# -- Meria's Outrider: each opponent equal to a count -----------------------


def test_outrider_counts_basic_land_types_and_hits_each_opponent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Meria's Outrider"],
            battlefield=["Mountain", "Forest", "Hallowed Fountain"],
        )
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Meria's Outrider", "alice")
    _drain(scenario)

    assert _life(scenario, "bob") == 16, "Mountain, Forest, Plains, Island"
    assert _life(scenario, "carol") == 16
    assert _life(scenario, "alice") == 20
    assert _notices(scenario) == []


def test_outrider_with_no_basic_land_types_deals_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Meria's Outrider"], battlefield=["Wastes"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Meria's Outrider", "alice")
    _drain(scenario)

    assert _life(scenario, "bob") == 20


def test_outrider_counts_only_its_controllers_lands():
    scenario = (
        Scenario()
        .player("alice", hand=["Meria's Outrider"], battlefield=["Mountain"])
        .player("bob", battlefield=["Island", "Swamp", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Meria's Outrider", "alice")
    _drain(scenario)

    assert _life(scenario, "bob") == 19


# -- Fanatic of Mogis: devotion ---------------------------------------------


def test_fanatic_counts_its_own_red_symbol_and_other_permanents():
    scenario = (
        Scenario()
        .player("alice", hand=["Fanatic of Mogis"], battlefield=["Ash Zealot", "Grizzly Bears"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Fanatic of Mogis", "alice")
    _drain(scenario)

    assert _life(scenario, "bob") == 17, "Fanatic's {R} + Ash Zealot's {R}{R}"
    assert _life(scenario, "carol") == 17
    assert _notices(scenario) == []


def test_fanatic_gone_before_resolution_reads_devotion_then():
    scenario = (
        Scenario()
        .player("alice", hand=["Fanatic of Mogis"], battlefield=["Ash Zealot"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fanatic = scenario.put_onto_battlefield("Fanatic of Mogis", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(fanatic)
    _drain(scenario)

    assert _life(scenario, "bob") == 18, "devotion read on resolution: only Ash Zealot remains"


# -- Bind the Monster -------------------------------------------------------


def _bind(target_power_card: str = "Hill Giant"):
    scenario = (
        Scenario()
        .player("alice", hand=["Bind the Monster"], battlefield=["Island"])
        .player("bob", battlefield=[target_power_card])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_bind_the_monster_taps_and_its_creature_deals_damage_to_you():
    scenario = _bind()
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Bind the Monster", *scenario.untapped_sources("Island"), targets=[giant]
    )
    _drain(scenario)

    assert giant.tapped
    assert _life(scenario, "alice") == 17
    assert _life(scenario, "bob") == 20
    assert _notices(scenario) == []


def test_bind_the_monster_creature_gone_still_deals_its_last_known_power():
    scenario = _bind()
    giant = scenario.creature("Hill Giant", "bob")
    scenario.cast_and_resolve(
        "Bind the Monster", *scenario.untapped_sources("Island"), targets=[giant]
    )
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(giant)
    scenario.state_based_actions()
    _drain(scenario)

    assert _life(scenario, "alice") == 17, "the ruling: damage is dealt even if it has left"


# -- second printings -------------------------------------------------------


def test_warstorm_surge_the_entering_creature_is_the_source():
    scenario = (
        Scenario()
        .player("alice", hand=["Hill Giant"], battlefield=["Warstorm Surge"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")
    scenario.will_choose_targets(spider)
    scenario.put_onto_battlefield("Hill Giant", "alice")
    _drain(scenario)

    assert spider.damage == 3


def test_heartfire_hero_dies_with_counters_and_deals_its_last_known_power():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Heartfire Hero"])
        .player("bob")
        .player("carol")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hero = scenario.creature("Heartfire Hero", "alice")
    scenario.game.add_counters(hero, "+1/+1", 3)
    scenario.game.destroy(hero)
    _drain(scenario)

    assert _life(scenario, "bob") == 16, "1 printed + 3 counters, as it last existed"
    assert _life(scenario, "carol") == 16


def test_stormbreath_per_player_count_stays_with_its_own_reader():
    effect = trigger_effect_for(
        "Stormbreath Dragon",
        TriggerEvent.BECOMES_MONSTROUS,
        "it deals damage to each opponent equal to the number of cards in that player's hand.",
    )
    assert effect is not None
    assert _outcomes("Stormbreath Dragon") == ["handled", "handled"]


def test_molten_psyche_metalcraft_condition_is_not_swallowed():
    scenario = (
        Scenario()
        .player("alice", hand=["Molten Psyche"], battlefield=["Mountain", "Mountain", "Mountain"])
        .player("bob", library=["Island"] * 5, hand=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Molten Psyche", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )

    assert _life(scenario, "bob") == 20, "no metalcraft: no damage"


def test_blazing_bomb_sacrificed_as_a_cost_deals_its_last_known_power():
    """An activated ability has no trigger event: "it" is the source, which
    the sacrifice cost already moved - its counters still count (CR 608.2h)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Blazing Bomb"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bomb = scenario.creature("Blazing Bomb", "alice")
    bomb.summoning_sick = False  # staged: on the battlefield since alice's turn began
    scenario.game.add_counters(bomb, "+1/+1", 2)
    giant = scenario.creature("Giant Spider", "bob")
    scenario.activate(bomb, sacrificing=[bomb], targets=[giant])
    scenario.resolve_top()

    assert giant.damage == 3, "1 printed + 2 counters, as it last existed"
    assert set(_outcomes("Blazing Bomb")) == {"handled"}

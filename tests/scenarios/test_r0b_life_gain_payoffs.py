"""R0b proofs: "whenever you gain life" payoffs and the life-gain engines.

Hinterland Sanctifier, Starscape Cleric, Leonardo Cutting Edge, Moseo Vein's
New Dean and Professor Dellian Fel are already handled; each ability is proven
here through the engine. Rules, each read with `mise run rules:find`:

- **CR 702.175a** - offspring: an optional additional cost, and a 1/1 token
  copy on enter if it was paid.
- **CR 702.190a** - sneak: cast for the sneak cost, returning an unblocked
  attacker to hand.
- **CR 702.15b / 120.3f** - lifelink damage makes its controller gain that
  much life, as one event.
- **CR 603.4** - an intervening "if" is checked on trigger and on resolution.
- **CR 114.4** - an emblem's abilities function in the command zone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve(scenario) -> None:
    """Stack the pending triggers (CR 603.3b), then resolve until quiet."""
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- Hinterland Sanctifier ---------------------------------------------------


def test_sanctifier_gains_one_when_another_creature_you_control_enters():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Hinterland Sanctifier", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")

    scenario.cast_and_resolve("Grizzly Bears", *sources, username="alice")
    _resolve(scenario)

    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 20


def test_sanctifier_does_not_trigger_on_its_own_entering():
    scenario = (
        Scenario()
        .player("alice", hand=["Hinterland Sanctifier"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.cast_and_resolve("Hinterland Sanctifier", plains, username="alice")
    _resolve(scenario)

    assert scenario.player("alice").life == 20


def test_sanctifier_ignores_creatures_an_opponent_controls():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hinterland Sanctifier"])
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    scenario.game.put_onto_battlefield(bears, "bob")
    _resolve(scenario)

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_sanctifier_triggers_once_per_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Hill Giant"],
            battlefield=["Hinterland Sanctifier"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    scenario.put_onto_battlefield("Hill Giant", "alice")
    _resolve(scenario)
    assert scenario.player("alice").life == 22


# -- Starscape Cleric --------------------------------------------------------


def test_cleric_drains_each_opponent_for_one_whenever_you_gain_life():
    scenario = Scenario().player("alice", battlefield=["Starscape Cleric"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 5)
    _resolve(scenario)

    assert scenario.player("alice").life == 25
    assert scenario.player("bob").life == 19, "once per life-gain event, not per point"


def test_cleric_triggers_once_per_event_not_per_point_across_two_events():
    scenario = Scenario().player("alice", battlefield=["Starscape Cleric"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 1)
    _resolve(scenario)
    scenario.game.gain_life("alice", 3)
    _resolve(scenario)

    assert scenario.player("bob").life == 18


def test_cleric_ignores_the_opponents_life_gain():
    scenario = Scenario().player("alice", battlefield=["Starscape Cleric"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("bob", 4)
    _resolve(scenario)

    assert scenario.player("bob").life == 24
    assert scenario.player("alice").life == 20


def test_cleric_cannot_block():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Starscape Cleric"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    cleric = scenario.creature("Starscape Cleric", "bob")

    try:
        scenario.block(bears, cleric)
    except ValueError as error:
        assert "block" in str(error).lower()
    else:
        raise AssertionError("Starscape Cleric blocked")


def test_cleric_offspring_token_copy_also_drains_per_life_gain():
    """CR 702.175a: the paid offspring makes a 1/1 token copy, which carries the
    same trigger - one life gain, two triggers (original plus token)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Starscape Cleric"], battlefield=["Swamp"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5, username="alice")

    casting = scenario.cast("Starscape Cleric", username="alice")
    casting.pay_offspring()
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    token = next(s for s in scenario.game.battlefield if s.name == "Starscape Cleric" and s.token)
    assert scenario.game.power_of(token) == 1 and scenario.game.toughness_of(token) == 1

    scenario.game.gain_life("alice", 2)
    _resolve(scenario)
    assert scenario.player("bob").life == 18


def test_cleric_without_offspring_makes_no_token():
    scenario = (
        Scenario()
        .player("alice", hand=["Starscape Cleric"], battlefield=["Swamp"] * 2)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Starscape Cleric", *sources, username="alice")

    assert [s for s in scenario.game.battlefield if s.name == "Starscape Cleric" and s.token] == []
    scenario.game.gain_life("alice", 1)
    _resolve(scenario)
    assert scenario.player("bob").life == 19


def test_cleric_counts_a_lifelink_damage_event_once():
    """CR 120.3f: lifelink damage is a single life-gain event, so one drain."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Starscape Cleric", "Leonardo, Cutting Edge"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leonardo = scenario.creature("Leonardo, Cutting Edge", "alice")
    leonardo.summoning_sick = False
    scenario.attack_with(leonardo)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve(scenario)

    assert scenario.player("alice").life == 21
    assert scenario.player("bob").life == 20 - 1 - 1, "1 combat damage, then one drain"


# -- Leonardo, Cutting Edge --------------------------------------------------


def test_leonardo_grows_when_you_gain_life():
    scenario = (
        Scenario().player("alice", battlefield=["Leonardo, Cutting Edge"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leonardo = scenario.creature("Leonardo, Cutting Edge", "alice")

    scenario.game.gain_life("alice", 4)
    _resolve(scenario)

    assert leonardo.counters[Counter.PLUS_ONE] == 1
    assert scenario.game.power_of(leonardo) == 2


def test_leonardo_ignores_opponent_life_gain():
    scenario = (
        Scenario().player("alice", battlefield=["Leonardo, Cutting Edge"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leonardo = scenario.creature("Leonardo, Cutting Edge", "alice")
    scenario.game.gain_life("bob", 4)
    _resolve(scenario)
    assert leonardo.counters[Counter.PLUS_ONE] == 0


def test_leonardo_lifelink_damage_gains_life_and_adds_a_counter():
    scenario = (
        Scenario().player("alice", battlefield=["Leonardo, Cutting Edge"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leonardo = scenario.creature("Leonardo, Cutting Edge", "alice")
    leonardo.summoning_sick = False
    scenario.attack_with(leonardo)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.combat_damage()
    _resolve(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    assert leonardo.counters[Counter.PLUS_ONE] == 1


def test_leonardo_sneaks_in_for_w_tapped_and_attacking():
    """CR 702.190a/b: sneak {W}, returning an unblocked attacker."""
    scenario = (
        Scenario()
        .player("alice", hand=["Leonardo, Cutting Edge"], battlefield=["Grizzly Bears", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()

    card = scenario.find("Leonardo, Cutting Edge", Zone.HAND, "alice")
    scenario.game.cast(
        card,
        "alice",
        keyword="Sneak",
        choosing=[bears],
        mana_sources=scenario.game.permanents_controlled_by("alice"),
    )
    assert bears.zone is Zone.HAND
    scenario.pass_until_resolved()

    leonardo = scenario.find("Leonardo, Cutting Edge", Zone.BATTLEFIELD, "alice")
    assert leonardo.tapped
    assert scenario.game.combat.attack_by(leonardo.id) is not None
    scenario.combat_damage()
    _resolve(scenario)
    assert scenario.player("bob").life == 19
    assert scenario.player("alice").life == 21
    assert leonardo.counters[Counter.PLUS_ONE] == 1, "lifelink gained life, Leonardo grew"


# -- Moseo, Vein's New Dean --------------------------------------------------


def _moseo_scenario(graveyard=("Grizzly Bears",)):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Moseo, Vein's New Dean"],
            graveyard=list(graveyard),
        )
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )


def test_moseo_enter_makes_a_pest_that_gains_life_when_it_attacks():
    scenario = (
        Scenario()
        .player("alice", hand=["Moseo, Vein's New Dean"], battlefield=["Swamp"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Moseo, Vein's New Dean", *sources, username="alice")
    _resolve(scenario)

    pest = scenario.creature("Pest Token", "alice")
    assert pest.token
    assert scenario.game.power_of(pest) == 1 and scenario.game.toughness_of(pest) == 1

    pest.summoning_sick = False
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(pest)
    _resolve(scenario)
    assert scenario.player("alice").life == 21


def test_moseo_infusion_returns_a_creature_with_mv_up_to_life_gained():
    scenario = _moseo_scenario(graveyard=("Grizzly Bears", "Hill Giant"))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.game.gain_life("alice", 2)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_choose_targets(bears)
    scenario.advance()
    _resolve(scenario)

    assert bears.zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.GRAVEYARD


def test_moseo_infusion_cannot_return_a_creature_costing_more_than_life_gained():
    scenario = _moseo_scenario(graveyard=("Hill Giant",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.game.gain_life("alice", 2)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    _resolve(scenario)

    assert giant.zone is Zone.GRAVEYARD, "mana value 3 > 2 life gained"


def test_moseo_infusion_does_not_trigger_when_no_life_was_gained():
    """CR 603.4: the intervening if is false at the end step, so nothing triggers."""
    scenario = _moseo_scenario()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    assert scenario.stack_names() == []
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.zone is Zone.GRAVEYARD


def test_moseo_infusion_with_no_target_is_legal():
    """ "Up to one": zero targets still resolves, with the trigger on the stack."""
    scenario = _moseo_scenario(graveyard=())
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("alice", 3)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    _resolve(scenario)
    assert scenario.game.stack == []


def test_moseo_infusion_uses_the_total_life_gained_this_turn():
    scenario = _moseo_scenario(graveyard=("Hill Giant",))
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")

    scenario.game.gain_life("alice", 1)
    scenario.game.gain_life("alice", 3)
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.will_choose_targets(giant)
    scenario.advance()
    _resolve(scenario)

    assert giant.zone is Zone.BATTLEFIELD


# -- Professor Dellian Fel ---------------------------------------------------


def _dellian(**kwargs):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Professor Dellian Fel"],
            library=["Forest"] * 5,
            **kwargs,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dellian = scenario.find("Professor Dellian Fel", Zone.BATTLEFIELD, "alice")
    return scenario, dellian


def test_dellian_plus_two_gains_three_life():
    scenario, dellian = _dellian()
    start = dellian.counters[Counter.LOYALTY]
    scenario.activate(dellian, index=0)
    _resolve(scenario)
    assert scenario.player("alice").life == 23
    assert dellian.counters[Counter.LOYALTY] == start + 2


def test_dellian_zero_draws_a_card_and_loses_a_life():
    scenario, dellian = _dellian()
    hand = len(scenario.player("alice").hand)
    scenario.activate(dellian, index=1)
    _resolve(scenario)
    assert len(scenario.player("alice").hand) == hand + 1
    assert scenario.player("alice").life == 19


def test_dellian_minus_three_destroys_target_creature():
    scenario, dellian = _dellian()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.activate(dellian, index=2, targets=[bears])
    _resolve(scenario)
    assert bears.zone is Zone.GRAVEYARD


def _ultimate(scenario, dellian):
    dellian.add_counters(Counter.LOYALTY, 6 - dellian.counters[Counter.LOYALTY])
    scenario.activate(dellian, index=3)
    _resolve(scenario)
    scenario.game.check_state_based_actions()


def test_dellian_minus_six_makes_an_emblem_that_drains_by_the_life_gained():
    scenario, dellian = _dellian()
    _ultimate(scenario, dellian)

    (emblem,) = scenario.game.emblems_of("alice")
    assert emblem.zone is Zone.COMMAND
    assert dellian.zone is Zone.GRAVEYARD, "CR 704.5i: 0 loyalty"

    scenario.game.gain_life("alice", 4)
    _resolve(scenario)
    assert scenario.player("bob").life == 16, "target opponent loses that much"
    assert scenario.player("alice").life == 24


def test_dellian_emblem_ignores_the_opponents_life_gain_and_stacks():
    scenario, dellian = _dellian()
    _ultimate(scenario, dellian)
    scenario.game.gain_life("bob", 5)
    _resolve(scenario)
    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 25


# -- the "loses that much life" reader on a second printing ------------------


def test_vito_drains_the_opponent_by_the_life_gained():
    """Vito, Thorn of the Dusk Rose (Modern/Pioneer): "Whenever you gain life,
    target opponent loses that much life." - the same reader Dellian's emblem
    needs, on a creature, not an emblem."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vito, Thorn of the Dusk Rose"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_life("alice", 3)
    _resolve(scenario)
    assert scenario.player("bob").life == 17

    scenario.game.gain_life("alice", 1)
    _resolve(scenario)
    assert scenario.player("bob").life == 16


def test_vito_ignores_the_opponents_life_gain():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vito, Thorn of the Dusk Rose"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life("bob", 3)
    _resolve(scenario)
    assert scenario.player("bob").life == 23
    assert scenario.player("alice").life == 20

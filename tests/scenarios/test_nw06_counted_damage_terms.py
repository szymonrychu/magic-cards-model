"""Counted amount terms behind "deals damage equal to / X damage, where X is"
(NW-06, task T2).

Each term is a count the effect reads once, as it resolves (CR 608.2h), off
the computed board (CR 613.5) or a per-turn record:

- Barret Wallace / Jor Kadeen, First Goldwarden: "the number of equipped
  creatures you control" - a creature with any Equipment attached, counted
  once however many it carries.
- Basalt Ravager / Skemfar Shadowsage: "the greatest number of creatures you
  control that have a creature type in common" - changeling is every creature
  type (CR 702.73a).
- Deathforge Shaman: "twice the number of times it was kicked" - read from the
  cast record (CR 702.33d), never live; 0 when the permanent was not cast.
- Ember-Fist Zubera: "the number of Zubera that died this turn" - the turn's
  graveyard arrivals with their last-known subtypes (CR 700.4, CR 603.10a),
  the dying creature itself included.
- Outrage Shaman / Heartlash Cinder: "the number of red mana symbols in the
  mana costs of permanents you control" - hybrid and Phyrexian symbols count
  (CR 107.4e, CR 700.5).
- Thundering Raiju: "modified creatures you control other than this creature"
  (CR 700.9).
- Urabrask's Anointer / Kuldotha Cackler: "permanents you control with oil
  counters on them".
- Summon: Bahamut: "the total mana value of other permanents you control".
- Summon: Esper Ramuh / The Lord Master of Hell: "noncreature, nonland cards
  in your graveyard".
- Sorcerer Class: "the number of instant and sorcery spells you've cast this
  turn", the triggering spell dealing the damage.
- Mjolnir, Storm Hammer: "the number of tapped creatures that opponent
  controls" - counted per opponent, every amount fixed as the effect applies (CR 608.2h).
- Thundercloud Shaman: "damage equal to <count> to each non-Giant creature".

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects import trigger_effect_for
from magic_cards_model.machines.effects.amounts import amount_expression, count_expression
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

LANDS = ["Mountain"] * 8


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _life(scenario: Scenario, username: str) -> int:
    return scenario.player(username).life


def _board(
    *,
    hand=(),
    battlefield=(),
    graveyard=(),
    bob=(),
    bob_hand=(),
    bob_graveyard=(),
    lands=LANDS,
    library=(),
) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[*lands, *battlefield],
            graveyard=list(graveyard),
            library=list(library) or ["Mountain"] * 5,
        )
        .player(
            "bob",
            battlefield=list(bob),
            hand=list(bob_hand),
            graveyard=list(bob_graveyard),
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _attack(scenario: Scenario, *attackers, defending=None) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers, defending=defending)
    _resolve_everything(scenario)


def _enter(scenario: Scenario, name: str, target=None) -> None:
    """Cast a creature, then let its enters trigger resolve (target chosen)."""
    scenario.cast_onto_stack(name, auto=True)
    if target is not None:
        scenario.choose_trigger_targets(name, [target])
    scenario.resolve_top()  # the creature spell
    _resolve_everything(scenario)


# -- every listed card now reads handled on every clause ------------------------

LISTED = [
    "Arabella, Abandoned Doll",
    "Barret Wallace",
    "Basalt Ravager",
    "Deathforge Shaman",
    "Ember-Fist Zubera",
    "Outrage Shaman",
    "Thundercloud Shaman",
    "Thundering Raiju",
    "Urabrask's Anointer",
    "Summon: Bahamut",
    "Summon: Esper Ramuh",
    "Sorcerer Class",
    "Mjölnir, Storm Hammer",
    "Niv-Mizzet, Guildpact",
]


@pytest.mark.parametrize("name", LISTED)
def test_every_clause_of_the_listed_card_is_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, bad


@pytest.mark.parametrize(
    "name",
    [
        "Welcoming Vampire",
        "Jor Kadeen, First Goldwarden",
        "Skemfar Shadowsage",
        "Heartlash Cinder",
        "Kuldotha Cackler",
    ],
)
def test_every_clause_of_the_proof_printing_is_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, bad


def test_the_cross_task_starfall_sentence_reads_through_the_noncreature_nonland_term():
    """The Lord Master of Hell's Starfall (owned by NW06-T3; full-card check
    at integration) reads through this task's graveyard term."""
    effect = trigger_effect_for(
        "The Lord Master of Hell",
        TriggerEvent.ATTACKS,
        "it deals X damage to each opponent, where X is the number of noncreature, "
        "nonland cards in your graveyard.",
    )
    assert effect is not None


# -- creatures with power N or less ---------------------------------------------


def _power_board():
    return _board(
        battlefield=["Llanowar Elves", "Grizzly Bears", "Hill Giant", "Serra Angel"],
        bob=["Llanowar Elves", "Llanowar Elves"],
    )


def test_power_bound_count_reads_the_computed_power_of_your_creatures_only():
    counted = count_expression("the number of creatures you control with power 2 or less")
    assert counted is not None
    scenario = _power_board()
    assert counted(scenario.game, "alice") == 2  # Elves 1, Bears 2; Giant 3 and Angel 4 are out
    assert counted(scenario.game, "bob") == 2


def test_power_bound_count_follows_counters_that_change_the_power():
    counted = count_expression("the number of creatures you control with power 2 or less")
    scenario = _power_board()
    scenario.creature("Grizzly Bears", "alice").add_counters(Counter.PLUS_ONE, 1)
    assert counted(scenario.game, "alice") == 1


def test_power_bound_count_has_a_greater_direction_and_a_toughness_form():
    scenario = _power_board()
    at_least = count_expression("the number of creatures you control with power 3 or greater")
    assert at_least is not None and at_least(scenario.game, "alice") == 2
    toughness = count_expression("the number of creatures you control with toughness 2 or less")
    assert toughness is not None and toughness(scenario.game, "alice") == 2


def test_other_than_this_creature_needs_the_resolving_source():
    """`count_expression` has no source to exclude, so the "other than this
    creature" form is an amount-expression term only."""
    phrase = "the number of modified creatures you control other than this creature"
    assert count_expression(phrase) is None
    assert amount_expression(phrase) is not None


# -- equipped creatures: Barret Wallace, Jor Kadeen -------------------------------


def _equip(scenario, creature_name, username="alice"):
    free = [
        p
        for p in scenario.game.permanents_controlled_by(username)
        if p.name == "Bonesplitter" and p.attached_to is None
    ]
    free[0].attach_to(scenario.creature(creature_name, username))


def _barret_board(**kwargs):
    return _board(
        battlefield=[
            "Barret Wallace",
            "Grizzly Bears",
            "Llanowar Elves",
            "Hill Giant",
            "Bonesplitter",
            "Bonesplitter",
            "Bonesplitter",
        ],
        **kwargs,
    )


def test_barret_wallace_deals_damage_equal_to_the_equipped_creatures_you_control():
    scenario = _barret_board(bob=["Grizzly Bears"])
    _equip(scenario, "Grizzly Bears")
    _equip(scenario, "Llanowar Elves")
    _attack(scenario, scenario.creature("Barret Wallace", "alice"))
    assert _life(scenario, "bob") == 18


def test_a_creature_carrying_two_equipment_counts_once():
    scenario = _barret_board()
    _equip(scenario, "Grizzly Bears")
    _equip(scenario, "Grizzly Bears")
    _attack(scenario, scenario.creature("Barret Wallace", "alice"))
    assert _life(scenario, "bob") == 19


def test_barret_counts_itself_when_equipped():
    scenario = _barret_board()
    _equip(scenario, "Barret Wallace")
    _attack(scenario, scenario.creature("Barret Wallace", "alice"))
    assert _life(scenario, "bob") == 19


def test_an_opponents_equipped_creature_is_not_counted():
    scenario = _board(
        battlefield=["Barret Wallace", "Grizzly Bears"],
        bob=["Grizzly Bears", "Bonesplitter"],
    )
    scenario.find("Bonesplitter", Zone.BATTLEFIELD, "bob").attach_to(
        scenario.creature("Grizzly Bears", "bob")
    )
    _attack(scenario, scenario.creature("Barret Wallace", "alice"))
    assert _life(scenario, "bob") == 20


def test_with_nothing_equipped_barret_deals_no_damage():
    scenario = _barret_board()
    _attack(scenario, scenario.creature("Barret Wallace", "alice"))
    assert _life(scenario, "bob") == 20


def test_equipped_count_phrase_reads_through_count_expression():
    counted = count_expression("the number of equipped creatures you control")
    assert counted is not None
    scenario = _barret_board()
    _equip(scenario, "Hill Giant")
    assert counted(scenario.game, "alice") == 1
    assert counted(scenario.game, "bob") == 0


def test_jor_kadeen_gets_plus_x_plus_x_for_each_equipped_creature_you_control():
    scenario = _board(
        battlefield=["Jor Kadeen, First Goldwarden", "Grizzly Bears", "Llanowar Elves"]
        + ["Bonesplitter"] * 2,
        bob=["Grizzly Bears"],
    )
    _equip(scenario, "Grizzly Bears")
    _equip(scenario, "Llanowar Elves")
    jor = scenario.creature("Jor Kadeen, First Goldwarden", "alice")
    base = scenario.game.power_of(jor)
    toughness = scenario.game.toughness_of(jor)
    _attack(scenario, jor)
    assert scenario.game.power_of(jor) == base + 2
    assert scenario.game.toughness_of(jor) == toughness + 2


# -- greatest number of creatures sharing a creature type --------------------------


def test_basalt_ravager_deals_the_largest_group_sharing_a_creature_type():
    scenario = _board(
        hand=["Basalt Ravager"],
        battlefield=["Hill Giant", "Llanowar Elves", "Birds of Paradise"],
    )
    _enter(scenario, "Basalt Ravager", "bob")
    assert _life(scenario, "bob") == 18  # Hill Giant + Basalt Ravager (Giant Wizard)


def test_a_changeling_has_every_creature_type_so_it_joins_the_largest_group():
    scenario = _board(
        hand=["Basalt Ravager"],
        battlefield=["Hill Giant", "Llanowar Elves", "Changeling Outcast"],
    )
    _enter(scenario, "Basalt Ravager", "bob")
    assert _life(scenario, "bob") == 17  # Giants: Hill Giant, Ravager, the changeling


def test_changelings_alone_with_the_ravager_all_share_every_type():
    scenario = _board(
        hand=["Basalt Ravager"],
        battlefield=["Changeling Outcast", "Changeling Outcast"],
    )
    _enter(scenario, "Basalt Ravager", "bob")
    assert _life(scenario, "bob") == 17


def test_the_ravager_alone_shares_a_type_with_itself():
    scenario = _board(hand=["Basalt Ravager"])
    _enter(scenario, "Basalt Ravager", "bob")
    assert _life(scenario, "bob") == 19


def test_an_opponents_creatures_do_not_join_your_group():
    scenario = _board(hand=["Basalt Ravager"], bob=["Hill Giant", "Hill Giant", "Hill Giant"])
    _enter(scenario, "Basalt Ravager", "bob")
    assert _life(scenario, "bob") == 19


def test_basalt_ravager_can_target_a_creature():
    scenario = _board(
        hand=["Basalt Ravager"],
        battlefield=["Hill Giant"],
        bob=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _enter(scenario, "Basalt Ravager", bears)
    assert bears.zone is Zone.GRAVEYARD  # 2 damage


SHADOWSAGE_DRAIN = (
    "Each opponent loses X life, where X is the greatest number of creatures you control "
    "that have a creature type in common."
)
SHADOWSAGE_GAIN = (
    "You gain X life, where X is the greatest number of creatures you control "
    "that have a creature type in common."
)


def test_skemfar_shadowsage_reads_the_same_count_in_either_mode():
    scenario = _board(
        hand=["Skemfar Shadowsage"],
        battlefield=["Llanowar Elves", "Birds of Paradise", "Elvish Mystic"],
        lands=["Swamp"] * 5,
    )
    scenario.will_choose_mode(SHADOWSAGE_DRAIN)
    _enter(scenario, "Skemfar Shadowsage")
    assert _life(scenario, "bob") == 17  # Elves, Mystic and Shadowsage are all Elves
    assert _life(scenario, "alice") == 20


def test_skemfar_shadowsage_gain_mode_counts_the_same_group():
    scenario = _board(
        hand=["Skemfar Shadowsage"],
        battlefield=["Llanowar Elves", "Elvish Mystic"],
        lands=["Swamp"] * 5,
    )
    scenario.will_choose_mode(SHADOWSAGE_GAIN)
    _enter(scenario, "Skemfar Shadowsage")
    assert _life(scenario, "alice") == 23
    assert _life(scenario, "bob") == 20


# -- twice the number of times it was kicked ------------------------------------------


def _deathforge(*, kicks: int, target="bob"):
    scenario = _board(hand=["Deathforge Shaman"], lands=["Mountain"] * 10)
    casting = scenario.cast("Deathforge Shaman")
    for _ in range(kicks):
        casting.pay_kicker()
    scenario.auto_pay(casting.begin_paying())
    scenario.choose_trigger_targets("Deathforge Shaman", [target])
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    _resolve_everything(scenario)
    return scenario


def test_deathforge_shaman_deals_twice_the_times_it_was_kicked():
    scenario = _deathforge(kicks=3)
    assert _life(scenario, "bob") == 14


def test_deathforge_shaman_kicked_once_deals_two():
    scenario = _deathforge(kicks=1)
    assert _life(scenario, "bob") == 18


def test_deathforge_shaman_unkicked_deals_nothing():
    scenario = _deathforge(kicks=0)
    assert _life(scenario, "bob") == 20


def test_a_deathforge_shaman_that_was_never_cast_was_kicked_zero_times():
    """CR 702.33d reads the cast record; a permanent put onto the battlefield
    has none."""
    scenario = _board(hand=["Deathforge Shaman"])
    scenario.choose_trigger_targets("Deathforge Shaman", ["bob"])
    scenario.put_onto_battlefield("Deathforge Shaman", "alice")
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 20


def test_deathforge_shaman_cannot_aim_at_a_creature():
    """ "target player or planeswalker" - a creature is not a legal target."""
    scenario = _board(hand=["Deathforge Shaman"], bob=["Grizzly Bears"])
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(
            "Deathforge Shaman", [scenario.creature("Grizzly Bears", "bob")]
        )


def test_times_it_was_kicked_phrase_reads_through_amount_expression():
    assert amount_expression("twice the number of times it was kicked") is not None
    assert amount_expression("the number of times it was kicked") is not None


# -- Zubera that died this turn -----------------------------------------------------


def _kill(scenario, creature):
    scenario.game.deal_damage(creature, 20)
    scenario.state_based_actions()


def test_ember_fist_zubera_counts_itself_among_the_zubera_that_died():
    scenario = _board(battlefield=["Ember-Fist Zubera"])
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["bob"])
    _kill(scenario, scenario.creature("Ember-Fist Zubera", "alice"))
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 19


def test_a_zubera_that_died_earlier_this_turn_counts_too():
    scenario = _board(battlefield=["Ember-Fist Zubera", "Ember-Fist Zubera"])
    first, second = scenario.creatures("Ember-Fist Zubera", "Ember-Fist Zubera", username="alice")
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["bob"])
    _kill(scenario, first)
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 19
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["bob"])
    _kill(scenario, second)
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 17  # two Zubera had died by then


def test_non_zubera_deaths_do_not_count():
    scenario = _board(battlefield=["Ember-Fist Zubera", "Grizzly Bears"])
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["bob"])
    _kill(scenario, scenario.creature("Ember-Fist Zubera", "alice"))
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 19


def test_an_opponents_zubera_that_died_counts_as_well():
    scenario = _board(
        battlefield=["Ember-Fist Zubera"],
        bob=["Ember-Fist Zubera"],
    )
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["alice"])
    _kill(scenario, scenario.creature("Ember-Fist Zubera", "bob"))
    _resolve_everything(scenario)
    scenario.choose_trigger_targets("Ember-Fist Zubera", ["bob"])
    _kill(scenario, scenario.creature("Ember-Fist Zubera", "alice"))
    _resolve_everything(scenario)
    assert _life(scenario, "alice") == 19
    assert _life(scenario, "bob") == 18


def test_it_can_hit_a_creature():
    scenario = _board(battlefield=["Ember-Fist Zubera"], bob=["Llanowar Elves"])
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.choose_trigger_targets("Ember-Fist Zubera", [elves])
    _kill(scenario, scenario.creature("Ember-Fist Zubera", "alice"))
    _resolve_everything(scenario)
    assert elves.zone is Zone.GRAVEYARD


def test_died_this_turn_phrases_read_through_count_expression():
    scenario = _board(battlefield=["Grizzly Bears", "Ember-Fist Zubera"], bob=["Hill Giant"])
    creatures = count_expression("the number of creatures that died this turn")
    zubera = count_expression("the number of Zubera that died this turn")
    nontoken = count_expression("the number of nontoken creatures that died this turn")
    assert creatures is not None and zubera is not None and nontoken is not None
    assert creatures(scenario.game, "alice") == 0
    _kill(scenario, scenario.creature("Grizzly Bears", "alice"))
    _kill(scenario, scenario.creature("Hill Giant", "bob"))
    assert creatures(scenario.game, "alice") == 2
    assert creatures(scenario.game, "bob") == 2, "whoever controlled them"
    assert zubera(scenario.game, "alice") == 0
    assert nontoken(scenario.game, "alice") == 2


# -- red mana symbols in the mana costs of permanents you control -----------------


def _outrage(battlefield, bob=("Elder Gargaroth",)):
    scenario = _board(hand=["Outrage Shaman"], battlefield=battlefield, bob=bob)
    target = scenario.creature(bob[0], "bob")
    _enter(scenario, "Outrage Shaman", target)
    return target


def test_outrage_shaman_counts_hybrid_red_symbols():
    # Boros Reckoner {R/W}{R/W}{R/W} is three red symbols; Outrage Shaman's {3}{R}{R} two.
    assert _outrage(["Boros Reckoner"]).damage == 5


def test_outrage_shaman_adds_every_permanent_you_control():
    target = _outrage(["Boros Reckoner", "Goblin Guide", "Grizzly Bears"])
    assert target.zone is Zone.GRAVEYARD  # 3 + 1 + 2 = 6 damage to a 6/6


def test_phyrexian_symbols_count_as_their_colour():
    """CR 107.4e/700.5: Cathedral Membrane's {W/P} is a white symbol."""
    counted = count_expression(
        "the number of white mana symbols in the mana costs of permanents you control"
    )
    assert counted is not None
    scenario = _board(battlefield=["Cathedral Membrane", "Plains"])
    assert counted(scenario.game, "alice") == 1


def test_outrage_shaman_ignores_an_opponents_symbols_and_other_colours():
    target = _outrage(
        ["Grizzly Bears", "Serra Angel"],
        bob=("Elder Gargaroth", "Goblin Guide", "Boros Reckoner"),
    )
    assert target.damage == 2, "only Outrage Shaman's own {R}{R}"


def test_red_symbol_phrase_reads_through_count_expression():
    counted = count_expression(
        "the number of red mana symbols in the mana costs of permanents you control"
    )
    assert counted is not None
    scenario = _board(battlefield=["Boros Reckoner", "Goblin Guide"], bob=["Goblin Guide"])
    assert counted(scenario.game, "alice") == 4
    assert counted(scenario.game, "bob") == 1


def test_heartlash_cinder_gets_plus_x_plus_zero_from_the_same_symbols():
    scenario = _board(hand=["Heartlash Cinder"], battlefield=["Goblin Guide"])
    scenario.cast_onto_stack("Heartlash Cinder", auto=True)
    scenario.resolve_top()
    _resolve_everything(scenario)
    cinder = scenario.creature("Heartlash Cinder", "alice")
    # Cinder {1}{R} = 1, Guide {R} = 1 -> +2/+0 on a 2/1... base power from the printing.
    assert scenario.game.power_of(cinder) == int(card("Heartlash Cinder").power) + 2


# -- modified creatures other than this creature: Thundering Raiju --------------------


def test_raiju_counts_modified_creatures_other_than_itself_after_its_counter_lands():
    scenario = _board(
        battlefield=["Thundering Raiju", "Hill Giant", "Llanowar Elves", "Bonesplitter"],
        bob=["Grizzly Bears"],
    )
    _equip(scenario, "Llanowar Elves")
    giant = scenario.creature("Hill Giant", "alice")
    raiju = scenario.creature("Thundering Raiju", "alice")
    scenario.choose_trigger_targets("Thundering Raiju", [giant])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raiju)
    _resolve_everything(scenario)
    assert giant.counters[Counter.PLUS_ONE] == 1
    assert _life(scenario, "bob") == 18  # the equipped Elves and the countered Giant


def test_raiju_does_not_count_itself_even_when_it_is_the_modified_one():
    scenario = _board(battlefield=["Thundering Raiju", "Hill Giant"])
    raiju = scenario.creature("Thundering Raiju", "alice")
    scenario.choose_trigger_targets("Thundering Raiju", [raiju])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raiju)
    _resolve_everything(scenario)
    assert raiju.counters[Counter.PLUS_ONE] == 1
    assert _life(scenario, "bob") == 20


def test_an_aura_you_do_not_control_does_not_modify_the_creature():
    """CR 700.9: an Aura counts only when its controller also controls the
    enchanted creature."""
    scenario = _board(
        battlefield=["Thundering Raiju", "Hill Giant", "Llanowar Elves"],
        bob=["Pacifism"],
    )
    scenario.find("Pacifism", Zone.BATTLEFIELD, "bob").attach_to(
        scenario.creature("Hill Giant", "alice")
    )
    raiju = scenario.creature("Thundering Raiju", "alice")
    scenario.choose_trigger_targets(
        "Thundering Raiju", [scenario.creature("Llanowar Elves", "alice")]
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raiju)
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 19, "only the countered Elves is modified"


def test_an_aura_you_control_on_your_creature_modifies_it():
    scenario = _board(
        battlefield=["Thundering Raiju", "Hill Giant", "Llanowar Elves", "Rancor"],
    )
    scenario.find("Rancor", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Hill Giant", "alice")
    )
    raiju = scenario.creature("Thundering Raiju", "alice")
    scenario.choose_trigger_targets(
        "Thundering Raiju", [scenario.creature("Llanowar Elves", "alice")]
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(raiju)
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 18


def test_modified_phrase_reads_through_amount_expression():
    assert (
        amount_expression("the number of modified creatures you control other than this creature")
        is not None
    )
    counted = count_expression("the number of modified creatures you control")
    assert counted is not None
    scenario = _board(battlefield=["Hill Giant", "Llanowar Elves"])
    scenario.creature("Hill Giant", "alice").add_counters("oil", 1)
    assert counted(scenario.game, "alice") == 1


# -- permanents with oil counters ----------------------------------------------------


def test_urabrasks_anointer_counts_permanents_with_oil_counters_on_them():
    scenario = _board(
        hand=["Urabrask's Anointer"],
        battlefield=["Hill Giant", "Llanowar Elves", "Mountain"],
    )
    scenario.creature("Hill Giant", "alice").add_counters("oil", 2)
    scenario.creature("Llanowar Elves", "alice").add_counters("oil", 1)
    scenario.find("Mountain", Zone.BATTLEFIELD, "alice").add_counters("oil", 1)
    _enter(scenario, "Urabrask's Anointer", "bob")
    assert _life(scenario, "bob") == 17  # three permanents, however many counters each


def test_oil_counters_on_an_opponents_permanent_do_not_count():
    scenario = _board(hand=["Urabrask's Anointer"], bob=["Hill Giant"])
    scenario.creature("Hill Giant", "bob").add_counters("oil", 3)
    _enter(scenario, "Urabrask's Anointer", "bob")
    assert _life(scenario, "bob") == 20


def test_other_counters_are_not_oil():
    scenario = _board(hand=["Urabrask's Anointer"], battlefield=["Hill Giant"])
    scenario.creature("Hill Giant", "alice").add_counters(Counter.PLUS_ONE, 1)
    _enter(scenario, "Urabrask's Anointer", "bob")
    assert _life(scenario, "bob") == 20


def test_kuldotha_cackler_gets_plus_x_for_each_permanent_with_oil():
    scenario = _board(battlefield=["Kuldotha Cackler", "Hill Giant", "Llanowar Elves"])
    scenario.creature("Hill Giant", "alice").add_counters("oil", 1)
    scenario.creature("Llanowar Elves", "alice").add_counters("oil", 1)
    cackler = scenario.creature("Kuldotha Cackler", "alice")
    base = scenario.game.power_of(cackler)
    _attack(scenario, cackler)
    assert scenario.game.power_of(cackler) == base + 2


# -- total mana value of other permanents: Summon: Bahamut ------------------------------


def test_bahamut_chapter_four_deals_the_total_mana_value_of_other_permanents_you_control():
    scenario = _board(
        hand=["Summon: Bahamut"],
        battlefield=["Serra Angel", "Grizzly Bears", "Mountain"],
        bob=["Serra Angel"],
    )
    bahamut = scenario.put_onto_battlefield("Summon: Bahamut", "alice")
    _resolve_everything(scenario)
    for _ in range(3):
        scenario.game.add_counters(bahamut, Counter.LORE, 1)
        _resolve_everything(scenario)
    assert bahamut.zone is Zone.GRAVEYARD  # sacrificed after chapter IV
    # Angel 5 + Bears 2; the lands are 0 and Bahamut itself (9) is excluded.
    assert _life(scenario, "bob") == 13


def test_a_permanent_that_left_is_not_counted_and_lands_add_nothing():
    scenario = _board(
        hand=["Summon: Bahamut"],
        battlefield=["Serra Angel", "Grizzly Bears"],
    )
    scenario.creature("Grizzly Bears", "alice").tapped = True  # tapped permanents still count
    bahamut = scenario.put_onto_battlefield("Summon: Bahamut", "alice")
    _resolve_everything(scenario)
    scenario.game.destroy(scenario.creature("Serra Angel", "alice"))
    for _ in range(3):
        scenario.game.add_counters(bahamut, Counter.LORE, 1)
        _resolve_everything(scenario)
    assert _life(scenario, "bob") == 18  # only Grizzly Bears (2) is left to count


def test_total_mana_value_phrase_needs_the_source_when_it_says_other():
    phrase = "the total mana value of other permanents you control"
    assert count_expression(phrase) is None
    assert amount_expression(phrase) is not None
    plain = count_expression("the total mana value of permanents you control")
    assert plain is not None
    scenario = _board(battlefield=["Serra Angel"], bob=["Grizzly Bears"])
    assert plain(scenario.game, "alice") == 5
    assert plain(scenario.game, "bob") == 2


# -- noncreature, nonland cards in your graveyard --------------------------------------


def test_esper_ramuh_judgment_bolt_counts_noncreature_nonland_cards_in_your_graveyard():
    scenario = _board(
        hand=["Summon: Esper Ramuh"],
        graveyard=["Lightning Bolt", "Grizzly Bears", "Mountain", "Bonesplitter", "Divination"],
        bob=["Serra Angel"],
    )
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Summon: Esper Ramuh", [angel])
    scenario.put_onto_battlefield("Summon: Esper Ramuh", "alice")
    _resolve_everything(scenario)
    assert angel.damage == 3  # Bolt, Bonesplitter, Divination


def test_an_opponents_graveyard_is_not_counted():
    counted = count_expression("the number of noncreature, nonland cards in your graveyard")
    assert counted is not None
    scenario = _board(
        graveyard=["Lightning Bolt", "Mountain", "Grizzly Bears"], bob_graveyard=["Divination"] * 2
    )
    assert counted(scenario.game, "alice") == 1
    assert counted(scenario.game, "bob") == 2


# -- instant and sorcery spells you've cast this turn: Sorcerer Class ---------------------


def test_sorcerer_class_counts_the_spells_cast_this_turn_including_the_trigger_spell():
    scenario = _board(
        hand=["Shock", "Shock", "Lightning Bolt"],
        battlefield=["Sorcerer Class"],
        bob=["Grizzly Bears"],
    )
    scenario.find("Sorcerer Class", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.cast_and_resolve("Shock", auto=True, targets=["bob"])
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 20 - 2 - 1  # Shock, plus 1 from the first spell
    scenario.cast_and_resolve("Shock", auto=True, targets=["bob"])
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 20 - 3 - 2 - 2


def test_sorcerer_class_below_level_three_does_nothing():
    scenario = _board(hand=["Shock"], battlefield=["Sorcerer Class"])
    scenario.cast_and_resolve("Shock", auto=True, targets=["bob"])
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 18


def test_a_creature_spell_is_not_counted_and_does_not_trigger():
    scenario = _board(
        hand=["Grizzly Bears", "Shock"],
        battlefield=["Sorcerer Class"],
        lands=["Mountain"] * 4 + ["Forest"] * 2,
    )
    scenario.find("Sorcerer Class", Zone.BATTLEFIELD, "alice").class_level = 3
    scenario.cast_and_resolve("Grizzly Bears", auto=True)
    _resolve_everything(scenario)
    scenario.cast_and_resolve("Shock", auto=True, targets=["bob"])
    _resolve_everything(scenario)
    assert _life(scenario, "bob") == 20 - 2 - 1


# -- tapped creatures that opponent controls: Mjolnir, Storm Hammer -------------------------


def test_mjolnir_counts_each_opponents_own_tapped_creatures():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Mjölnir, Storm Hammer", "Isamaru, Hound of Konda"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant", "Llanowar Elves"])
        .player("carol", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.find("Mjölnir, Storm Hammer", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Isamaru, Hound of Konda", "alice")
    )
    scenario.creature("Llanowar Elves", "bob").tapped = True
    scenario.creature("Hill Giant", "carol").tapped = True
    target = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Mjölnir, Storm Hammer", [target])
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Isamaru, Hound of Konda", "alice"), defending="bob")
    _resolve_everything(scenario)
    assert target.tapped
    assert target.counters[Counter.STUN] == 1
    assert _life(scenario, "bob") == 18  # Bears (just tapped) and Elves
    assert _life(scenario, "carol") == 19  # Hill Giant only
    assert _life(scenario, "alice") == 20


def test_tapped_creatures_that_opponent_controls_is_a_per_player_count():
    scenario = _board(
        battlefield=["Grizzly Bears"],
        bob=["Hill Giant", "Llanowar Elves"],
    )
    scenario.creature("Hill Giant", "bob").tapped = True
    scenario.creature("Grizzly Bears", "alice").tapped = True
    counted = count_expression("the number of tapped creatures you control")
    assert counted(scenario.game, "alice") == 1
    assert counted(scenario.game, "bob") == 1


# -- non-<type> creatures: Thundercloud Shaman ------------------------------------------------


def test_thundercloud_shaman_hits_every_non_giant_creature_for_the_giants_you_control():
    scenario = _board(
        hand=["Thundercloud Shaman"],
        battlefield=["Hill Giant", "Grizzly Bears", "Serra Angel"],
        bob=["Grizzly Bears", "Serra Angel", "Hill Giant"],
    )
    _enter(scenario, "Thundercloud Shaman")
    # Two Giants (Hill Giant, Thundercloud Shaman) -> 2 damage to each non-Giant.
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Serra Angel", "alice").damage == 2
    assert scenario.creature("Serra Angel", "bob").damage == 2
    assert scenario.creature("Hill Giant", "alice").damage == 0
    assert scenario.creature("Hill Giant", "bob").damage == 0
    assert scenario.creature("Thundercloud Shaman", "alice").damage == 0


def test_an_opponents_giants_are_not_counted_but_are_still_spared():
    scenario = _board(
        hand=["Thundercloud Shaman"],
        battlefield=["Grizzly Bears"],
        bob=["Hill Giant", "Hill Giant", "Llanowar Elves"],
    )
    _enter(scenario, "Thundercloud Shaman")
    assert scenario.find("Llanowar Elves", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice").damage == 1
    assert all(p.damage == 0 for p in scenario.game.battlefield if p.name == "Hill Giant")

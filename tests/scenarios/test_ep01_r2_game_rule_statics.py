"""Game-rule statics: effects that change the rules of the game, not an object.

CR 611.1 puts these in its third category, "affects players or the rules of
the game", and CR 613.11 applies them "after all other continuous effects".
Each is read off the printed line by `machines/game_rule_statics.py` (or the
reader named in its section) and asked where the rule it changes is applied:

- **the legend rule** (CR 704.5j) - Mirror Gallery's "The "legend rule"
  doesn't apply." for everyone, Spider-Verse's "... doesn't apply to Spiders
  you control." for one subtype and one controller;
- **zero loyalty** (CR 704.5i's exemption) - Sanctum Lurker;
- **winning and losing** (CR 101.2, CR 104.3b, CR 704.5a) - Abyssal
  Persecutor's reversed "You can't win the game and your opponents can't
  lose the game.", Phyrexian Unlife's "You don't lose the game for having 0
  or less life." and its damage-as-infect line (CR 702.90b);
- **life totals** (CR 119.7, CR 119.8) - Platinum Emperion;
- **counters and infect** (CR 101.2, CR 122.1, CR 613.1f) - Melira, Sylvok
  Outcast's three lines;
- **uncounterable spells** (CR 101.2) - Gaea's Herald, Leyline of Lifeforce,
  Lier, Disciple of the Drowned and Spellbreaker Behemoth;
- **maximum hand size** (CR 402.2, CR 613.11) - Minamo Scrollkeeper, Gnat
  Miser, Locust Miser, Jin-Gitaxias, Core Augur, Winter, Misanthropic Guide.

Every CR number here was looked up with `mise run rules:find`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def build(alice=None, bob=None, *, alice_life=20, bob_life=20, alice_hand=None, bob_hand=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice or [],
            hand=alice_hand or [],
            life=alice_life,
            library=["Island"] * 10,
        )
        .player(
            "bob",
            battlefield=bob or [],
            hand=bob_hand or [],
            life=bob_life,
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def on_field(scenario, name, username="alice"):
    return [
        s
        for s in scenario.game.battlefield
        if s.name == name and scenario.game.controller_of(s).username == username
    ]


def handled(name: str, line: str) -> None:
    clauses = [c for c in card_support(card(name)).clauses if c.text == line]
    assert clauses, (name, line)
    for clause in clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome, clause.reason)


# -- the legend rule (CR 704.5j) ---------------------------------------------


def test_mirror_gallery_keeps_both_copies_of_a_legend():
    scenario = build(["Mirror Gallery", "Isamaru, Hound of Konda", "Isamaru, Hound of Konda"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Isamaru, Hound of Konda")) == 2


def test_mirror_gallery_switches_the_rule_off_for_its_controllers_opponent_too():
    """No "you control": the rule doesn't apply to anyone."""
    scenario = build(["Mirror Gallery"], ["Isamaru, Hound of Konda", "Isamaru, Hound of Konda"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Isamaru, Hound of Konda", "bob")) == 2


def test_without_mirror_gallery_the_legend_rule_applies():
    scenario = build(["Isamaru, Hound of Konda", "Isamaru, Hound of Konda"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Isamaru, Hound of Konda")) == 1


def test_spider_verse_exempts_spiders_you_control():
    scenario = build(["Spider-Verse", "Spider-Man 2099", "Spider-Man 2099"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Spider-Man 2099")) == 2


def test_spider_verse_does_not_exempt_a_non_spider_legend():
    scenario = build(["Spider-Verse", "Isamaru, Hound of Konda", "Isamaru, Hound of Konda"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Isamaru, Hound of Konda")) == 1


def test_spider_verse_does_not_exempt_an_opponents_spiders():
    scenario = build(["Spider-Verse"], ["Spider-Man 2099", "Spider-Man 2099"])
    scenario.state_based_actions()
    assert len(on_field(scenario, "Spider-Man 2099", "bob")) == 1


def test_legend_rule_lines_are_handled():
    handled("Mirror Gallery", 'The "legend rule" doesn\'t apply.')
    handled("Spider-Verse", 'The "legend rule" doesn\'t apply to Spiders you control.')


# -- zero loyalty (CR 704.5i) -------------------------------------------------


def test_sanctum_lurker_keeps_a_zero_loyalty_planeswalker():
    scenario = build(["Sanctum Lurker", "Jace, the Mind Sculptor"])
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "alice")
    jace.counters.remove(Counter.LOYALTY, jace.counter_count(Counter.LOYALTY))
    scenario.state_based_actions()
    assert jace.zone is Zone.BATTLEFIELD


def test_without_sanctum_lurker_a_zero_loyalty_planeswalker_dies():
    scenario = build(["Jace, the Mind Sculptor"])
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "alice")
    jace.counters.remove(Counter.LOYALTY, jace.counter_count(Counter.LOYALTY))
    scenario.state_based_actions()
    assert jace.zone is Zone.GRAVEYARD


def test_sanctum_lurker_does_not_keep_an_opponents_planeswalker():
    scenario = build(["Sanctum Lurker"], ["Jace, the Mind Sculptor"])
    jace = scenario.find("Jace, the Mind Sculptor", Zone.BATTLEFIELD, "bob")
    jace.counters.remove(Counter.LOYALTY, jace.counter_count(Counter.LOYALTY))
    scenario.state_based_actions()
    assert jace.zone is Zone.GRAVEYARD


def test_sanctum_lurker_line_is_handled():
    handled(
        "Sanctum Lurker",
        "Planeswalkers you control aren't put into their owners' graveyards for having 0 loyalty.",
    )


# -- winning and losing (CR 101.2, CR 104.3b, CR 704.5a) ----------------------


def test_abyssal_persecutors_opponent_at_zero_life_stays_in_the_game():
    scenario = build(["Abyssal Persecutor"])
    scenario.game.lose_life("bob", 20)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("bob")
    assert scenario.game.winner is None


def test_abyssal_persecutors_controller_still_loses_at_zero_life():
    scenario = build(["Abyssal Persecutor"])
    scenario.game.lose_life("alice", 20)
    scenario.state_based_actions()
    assert not scenario.game.is_in_game("alice")


def test_abyssal_persecutors_controller_cant_win_by_an_effect():
    scenario = build(["Abyssal Persecutor"])
    scenario.game.player_wins_the_game("alice")
    assert not scenario.game.is_over
    assert scenario.game.why_cant_win_the_game("alice") is not None


def test_once_abyssal_persecutor_leaves_the_opponent_at_zero_loses():
    scenario = build(["Abyssal Persecutor"])
    scenario.game.lose_life("bob", 20)
    scenario.state_based_actions()
    persecutor = scenario.find("Abyssal Persecutor", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(persecutor)
    scenario.state_based_actions()
    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"


def test_abyssal_persecutor_line_is_handled():
    handled("Abyssal Persecutor", "You can't win the game and your opponents can't lose the game.")


def test_phyrexian_unlife_keeps_its_controller_in_at_zero_life():
    scenario = build(["Phyrexian Unlife"], alice_life=3)
    scenario.game.lose_life("alice", 5)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")
    assert scenario.player("alice").life == -2


def test_phyrexian_unlife_does_not_stop_a_poison_loss():
    """Only CR 704.5a is switched off - ten poison counters still lose."""
    scenario = build(["Phyrexian Unlife"])
    scenario.player("alice").add_counters(Counter.POISON, 10)
    scenario.state_based_actions()
    assert not scenario.game.is_in_game("alice")


def test_phyrexian_unlife_does_not_protect_the_opponent():
    scenario = build(["Phyrexian Unlife"])
    scenario.game.lose_life("bob", 20)
    scenario.state_based_actions()
    assert not scenario.game.is_in_game("bob")


def test_phyrexian_unlife_damage_at_zero_life_is_poison():
    scenario = build(["Phyrexian Unlife"], ["Grizzly Bears"], alice_life=0)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.deal_damage(scenario.player("alice"), 2, source=bears)
    assert scenario.player("alice").life == 0
    assert scenario.player("alice").counters[Counter.POISON] == 2


def test_phyrexian_unlife_damage_above_zero_life_is_ordinary():
    """The condition "as long as you have 0 or less life" is read, not dropped."""
    scenario = build(["Phyrexian Unlife"], ["Grizzly Bears"], alice_life=5)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.deal_damage(scenario.player("alice"), 2, source=bears)
    assert scenario.player("alice").life == 3
    assert scenario.player("alice").counters[Counter.POISON] == 0


def test_phyrexian_unlife_lines_are_handled():
    handled("Phyrexian Unlife", "You don't lose the game for having 0 or less life.")
    handled(
        "Phyrexian Unlife",
        "As long as you have 0 or less life, all damage is dealt to you as though its "
        "source had infect.",
    )


# -- life totals (CR 119.7, CR 119.8) -----------------------------------------


def test_platinum_emperion_stops_life_loss_and_gain():
    scenario = build(["Platinum Emperion"])
    scenario.game.lose_life("alice", 5)
    scenario.game.gain_life("alice", 5)
    assert scenario.player("alice").life == 20


def test_platinum_emperion_damage_is_dealt_but_no_life_is_lost():
    scenario = build(["Platinum Emperion"], ["Grizzly Bears"])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.deal_damage(scenario.player("alice"), 3, source=bears)
    assert scenario.player("alice").life == 20


def test_platinum_emperion_does_not_protect_the_opponent():
    scenario = build(["Platinum Emperion"])
    scenario.game.lose_life("bob", 5)
    assert scenario.player("bob").life == 15


def test_platinum_emperion_forbids_paying_life():
    """CR 119.8: "a cost that involves having that player pay life can't be paid"."""
    from magic_cards_model.machines.cost import pay_life_cost

    scenario = build(["Platinum Emperion"])
    assert pay_life_cost(2, "alice").why_not(scenario.game) is not None
    assert pay_life_cost(0, "alice").why_not(scenario.game) is None
    assert pay_life_cost(2, "bob").why_not(scenario.game) is None


def test_platinum_emperion_line_is_handled():
    handled("Platinum Emperion", "Your life total can't change.")


# -- Melira, Sylvok Outcast (CR 101.2, CR 122.1, CR 613.1f) -------------------


def test_melira_stops_poison_counters():
    scenario = build(["Melira, Sylvok Outcast"])
    scenario.game.add_player_counters("alice", Counter.POISON, 3)
    scenario.game.add_player_counters("bob", Counter.POISON, 3)
    assert scenario.player("alice").counters[Counter.POISON] == 0
    assert scenario.player("bob").counters[Counter.POISON] == 3


def test_melira_stops_minus_counters_on_your_creatures_only():
    scenario = build(["Melira, Sylvok Outcast", "Grizzly Bears"], ["Grizzly Bears"])
    mine = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(mine, Counter.MINUS_ONE, 1)
    scenario.game.add_counters(theirs, Counter.MINUS_ONE, 1)
    scenario.game.add_counters(mine, Counter.PLUS_ONE, 1)
    assert mine.counter_count(Counter.MINUS_ONE) == 0
    assert mine.counter_count(Counter.PLUS_ONE) == 1
    assert theirs.counter_count(Counter.MINUS_ONE) == 1


def test_melira_takes_infect_from_opponents_creatures():
    scenario = build(["Melira, Sylvok Outcast", "Glistener Elf"], ["Glistener Elf"])
    mine = scenario.find("Glistener Elf", Zone.BATTLEFIELD, "alice")
    theirs = scenario.find("Glistener Elf", Zone.BATTLEFIELD, "bob")
    scenario.game.deal_damage(scenario.player("alice"), 1, source=theirs)
    assert scenario.player("alice").life == 19
    scenario.game.deal_damage(scenario.player("bob"), 1, source=mine)
    assert scenario.player("bob").counters[Counter.POISON] == 1


@pytest.mark.parametrize(
    "line",
    [
        "You can't get poison counters.",
        "Creatures you control can't have -1/-1 counters put on them.",
        "Creatures your opponents control lose infect.",
    ],
)
def test_melira_lines_are_handled(line):
    handled("Melira, Sylvok Outcast", line)


# -- uncounterable spells (CR 101.2) ------------------------------------------


def _counter_war(spell: str, *, alice=(), bob=()):
    """Alice casts `spell`; Bob answers with Counterspell."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=[*alice, *["Forest"] * 6, *["Island"] * 3],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Counterspell"], battlefield=[*bob, "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast = scenario.cast_onto_stack(spell, auto=True, username="alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Counterspell", auto=True, username="bob", targets=[cast])
    scenario.resolve_top()
    return cast


def test_gaeas_herald_stops_a_creature_spell_being_countered():
    assert _counter_war("Grizzly Bears", alice=["Gaea's Herald"]).zone is Zone.STACK


def test_gaeas_herald_covers_every_players_creature_spells():
    """No "you control": Bob's own Herald protects Alice's creature spell."""
    assert _counter_war("Grizzly Bears", bob=["Gaea's Herald"]).zone is Zone.STACK


def test_gaeas_herald_does_not_cover_a_noncreature_spell():
    assert _counter_war("Divination", alice=["Gaea's Herald"]).zone is Zone.GRAVEYARD


def test_lier_stops_any_spell_being_countered():
    assert _counter_war("Divination", bob=["Lier, Disciple of the Drowned"]).zone is Zone.STACK


def test_spellbreaker_behemoth_protects_a_power_five_creature_spell():
    assert _counter_war("Craw Wurm", alice=["Spellbreaker Behemoth"]).zone is Zone.STACK


def test_spellbreaker_behemoth_does_not_protect_a_small_creature_spell():
    """The "with power 5 or greater" rider is read, never dropped."""
    assert _counter_war("Grizzly Bears", alice=["Spellbreaker Behemoth"]).zone is Zone.GRAVEYARD


def test_spellbreaker_behemoth_does_not_protect_an_opponents_spell():
    """ "you control": Bob's Behemoth does not cover Alice's Craw Wurm."""
    assert _counter_war("Craw Wurm", bob=["Spellbreaker Behemoth"]).zone is Zone.GRAVEYARD


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("Gaea's Herald", "Creature spells can't be countered."),
        ("Leyline of Lifeforce", "Creature spells can't be countered."),
        ("Lier, Disciple of the Drowned", "Spells can't be countered."),
        (
            "Spellbreaker Behemoth",
            "Creature spells you control with power 5 or greater can't be countered.",
        ),
    ],
)
def test_uncounterable_lines_are_handled(name, line):
    handled(name, line)


# -- maximum hand size (CR 402.2, CR 613.11) ----------------------------------


def _hands(alice=(), bob=(), *, alice_graveyard=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            hand=["Island"] * 10,
            graveyard=list(alice_graveyard),
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), hand=["Island"] * 10, library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def over(scenario, username):
    return scenario.player(username).cards_over_maximum_hand_size


def test_minamo_scrollkeeper_increases_only_its_controllers_maximum():
    scenario = _hands(["Minamo Scrollkeeper"])
    assert over(scenario, "alice") == 2  # ten cards, maximum eight
    assert over(scenario, "bob") == 3


def test_gnat_miser_reduces_each_opponents_maximum_only():
    scenario = _hands(["Gnat Miser"])
    assert over(scenario, "bob") == 4  # maximum six
    assert over(scenario, "alice") == 3


def test_two_misers_stack():
    scenario = _hands(["Gnat Miser", "Locust Miser"])
    assert over(scenario, "bob") == 6  # 7 - 1 - 2


def test_jin_gitaxias_reduces_to_zero():
    scenario = _hands(["Jin-Gitaxias, Core Augur"])
    assert over(scenario, "bob") == 10


def test_a_reduction_and_an_increase_add_up():
    scenario = _hands(["Minamo Scrollkeeper"], ["Gnat Miser"])
    assert over(scenario, "alice") == 3  # 7 + 1 - 1


def test_winter_with_delirium_sets_each_opponents_maximum():
    graveyard = ["Island", "Grizzly Bears", "Lightning Bolt", "Divination", "Mirror Gallery"]
    scenario = _hands(["Winter, Misanthropic Guide"], alice_graveyard=graveyard)
    # land, creature, instant, sorcery, artifact: five types, maximum two
    assert over(scenario, "bob") == 8
    assert over(scenario, "alice") == 3


def test_winter_without_delirium_changes_nothing():
    """The "as long as" condition is read, never dropped."""
    scenario = _hands(["Winter, Misanthropic Guide"], alice_graveyard=["Island", "Grizzly Bears"])
    assert over(scenario, "bob") == 3


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("Minamo Scrollkeeper", "Your maximum hand size is increased by one."),
        ("Gnat Miser", "Each opponent's maximum hand size is reduced by one."),
        ("Locust Miser", "Each opponent's maximum hand size is reduced by two."),
        ("Jin-Gitaxias, Core Augur", "Each opponent's maximum hand size is reduced by seven."),
        (
            "Winter, Misanthropic Guide",
            "Delirium — As long as there are four or more card types among cards in your "
            "graveyard, each opponent's maximum hand size is equal to seven minus the number "
            "of those card types.",
        ),
    ],
)
def test_hand_size_lines_are_handled(name, line):
    handled(name, line)


def test_trusted_advisor_increases_by_two():
    scenario = _hands(["Trusted Advisor"])
    assert over(scenario, "alice") == 1


def test_midnight_oil_maximum_is_its_hour_counters_read_live():
    scenario = _hands(["Midnight Oil"])
    oil = scenario.find("Midnight Oil", Zone.BATTLEFIELD, "alice")
    oil.counters.remove("hour", oil.counter_count("hour"))
    scenario.game.add_counters(oil, "hour", 4)
    assert over(scenario, "alice") == 6
    oil.counters.remove("hour", 2)
    assert over(scenario, "alice") == 8
    assert over(scenario, "bob") == 3


def test_marina_vendrells_grimoire_no_maximum_and_no_zero_life_loss():
    scenario = _hands(["Marina Vendrell's Grimoire"])
    assert over(scenario, "alice") == 0
    assert over(scenario, "bob") == 3
    scenario.game.lose_life("alice", 25)
    scenario.state_based_actions()
    assert scenario.game.is_in_game("alice")


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("Trusted Advisor", "Your maximum hand size is increased by two."),
        (
            "Midnight Oil",
            "Your maximum hand size is equal to the number of hour counters on this enchantment.",
        ),
        (
            "Marina Vendrell's Grimoire",
            "You have no maximum hand size and don't lose the game for having 0 or less life.",
        ),
    ],
)
def test_x_card_hand_size_lines_are_handled(name, line):
    handled(name, line)


# -- poisonous, printed by a grant (CR 702.70a/b, CR 104.3d) -----------------
#
# CR 702.70a: "Poisonous N" means "Whenever this creature deals combat damage
# to a player, that player gets N poison counters." CR 702.70b: several
# instances trigger separately. Virulent Sliver grants it to every Sliver on
# the battlefield (both players'), Snake Cult Initiation to the creature it
# enchants - two wordings of the same counted-keyword grant.


def _attack_and_resolve(scenario, *attackers):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.game.stack or scenario.game.pending_triggers:
        scenario.game.put_triggers_on_stack()
        if scenario.game.stack:
            scenario.resolve_top()


def test_virulent_sliver_gives_a_poison_counter_on_combat_damage():
    scenario = build(["Virulent Sliver"])
    _attack_and_resolve(scenario, scenario.creature("Virulent Sliver"))
    assert scenario.player("bob").life == 19
    assert scenario.player("bob").poison == 1


def test_two_virulent_slivers_give_each_sliver_two_instances():
    """CR 702.70b: each instance triggers separately - one attacker with two
    grants of poisonous 1 gives two counters."""
    scenario = build(["Virulent Sliver", "Virulent Sliver"])
    attacker = scenario.creatures("Virulent Sliver")[0]
    _attack_and_resolve(scenario, attacker)
    assert scenario.player("bob").poison == 2


def test_virulent_sliver_grants_an_opponents_sliver_too():
    scenario = build(["Virulent Sliver"], ["Cautery Sliver"])
    theirs = scenario.creature("Cautery Sliver", "bob")
    assert "Poisonous 1" in scenario.game.characteristics_of(theirs).abilities


def test_virulent_sliver_does_not_grant_a_non_sliver():
    scenario = build(["Virulent Sliver", "Grizzly Bears"])
    _attack_and_resolve(scenario, scenario.creature("Grizzly Bears"))
    assert scenario.player("bob").life == 18
    assert scenario.player("bob").poison == 0


def test_snake_cult_initiation_gives_three_poison_counters():
    scenario = build(["Grizzly Bears"], alice_hand=["Snake Cult Initiation"])
    bears = scenario.creature("Grizzly Bears")
    aura = scenario.put_onto_battlefield("Snake Cult Initiation")
    aura.attach_to(bears)
    _attack_and_resolve(scenario, bears)
    assert scenario.player("bob").poison == 3


def test_snake_cult_initiation_blocked_gives_no_poison():
    scenario = build(["Grizzly Bears"], ["Wall of Omens"], alice_hand=["Snake Cult Initiation"])
    bears = scenario.creature("Grizzly Bears")
    aura = scenario.put_onto_battlefield("Snake Cult Initiation")
    aura.attach_to(bears)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.block(bears, scenario.creature("Wall of Omens", "bob"))
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    assert not scenario.game.stack
    assert scenario.player("bob").poison == 0


def test_snake_cult_initiation_poison_alone_can_end_the_game():
    """CR 104.3d: ten poison counters lose the game."""
    scenario = build(["Grizzly Bears"], alice_hand=["Snake Cult Initiation"])
    scenario.game.add_player_counters("bob", "poison", 7)
    bears = scenario.creature("Grizzly Bears")
    aura = scenario.put_onto_battlefield("Snake Cult Initiation")
    aura.attach_to(bears)
    _attack_and_resolve(scenario, bears)
    scenario.state_based_actions()
    assert not scenario.game.is_in_game("bob")


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("Virulent Sliver", "All Sliver creatures have poisonous 1."),
        ("Snake Cult Initiation", "Enchanted creature has poisonous 3."),
    ],
)
def test_poisonous_grant_lines_are_handled(name, line):
    handled(name, line)


# -- base power and toughness from a life total (CR 613.4b, CR 109.5) --------
#
# Aettir and Priwen: "Equipped creature has base power and toughness X/X,
# where X is your life total." A sublayer 7b set (CR 613.4b), X read live off
# the Equipment's controller's life total ("your", CR 109.5); 7c pumps and
# counters still apply on top (CR 613.4c). No other legal printing carries
# the X-from-life wording.


def _pt(scenario, state):
    chars = scenario.game.computed_board().of(state)
    return chars.power, chars.toughness


def _equipped_bears(alice_life=20, bob_life=20):
    scenario = build(
        ["Grizzly Bears", "Aettir and Priwen"], alice_life=alice_life, bob_life=bob_life
    )
    bears = scenario.creature("Grizzly Bears")
    on_field(scenario, "Aettir and Priwen")[0].attach_to(bears)
    return scenario, bears


def test_aettir_sets_base_power_and_toughness_to_your_life_total():
    scenario, bears = _equipped_bears(alice_life=17, bob_life=5)
    assert _pt(scenario, bears) == (17, 17)


def test_aettir_tracks_the_life_total_live():
    scenario, bears = _equipped_bears()
    scenario.game.lose_life("alice", 6)
    assert _pt(scenario, bears) == (14, 14)
    scenario.game.gain_life("alice", 3)
    assert _pt(scenario, bears) == (17, 17)


def test_aettir_counters_apply_on_top_of_the_set_value():
    scenario, bears = _equipped_bears(alice_life=10)
    bears.counters.add(Counter.PLUS_ONE, 2)
    assert _pt(scenario, bears) == (12, 12)


def test_aettir_unattached_leaves_the_creature_alone():
    scenario = build(["Grizzly Bears", "Aettir and Priwen"], alice_life=30)
    assert _pt(scenario, scenario.creature("Grizzly Bears")) == (2, 2)


def test_aettir_line_is_handled():
    handled(
        "Aettir and Priwen",
        "Equipped creature has base power and toughness X/X, where X is your life total.",
    )


# -- Spider-Verse's copy trigger (CR 603.2h, CR 707.10, CR 707.10c) ----------
#
# "Whenever you cast a spell from anywhere other than your hand, you may copy
# it. If you do, you may choose new targets for the copy. If the copy is a
# permanent spell, it gains haste. Do this only once each turn." The copy of
# a permanent spell becomes a token as it resolves (CR 707.10, CR 608.3f);
# CR 603.2h spends "only once each turn" on the copy, so declining leaves it
# untaken.


def _verse(graveyard, lands, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Spider-Verse", *lands],
            graveyard=list(graveyard),
            hand=list(hand),
            library=["Island"] * 10,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _flashback(scenario, name, *lands):
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*lands))
    return scenario.put_on_stack(casting)


def _resolve_trigger(scenario):
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()


def test_spider_verse_copies_a_spell_cast_from_the_graveyard():
    scenario = _verse(["Faithless Looting"], ["Mountain"] * 3)
    original = _flashback(scenario, "Faithless Looting", "Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    _resolve_trigger(scenario)
    spells = [s for s in scenario.game.stack if s.name == "Faithless Looting"]
    assert len(spells) == 2
    assert original in spells


def test_spider_verse_declined_copy_leaves_the_once_each_turn_untaken():
    scenario = _verse(["Faithless Looting", "Faithless Looting"], ["Mountain"] * 6)
    _flashback(scenario, "Faithless Looting", "Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(False)
    _resolve_trigger(scenario)
    assert len([s for s in scenario.game.stack if s.name == "Faithless Looting"]) == 1
    _flashback(scenario, "Faithless Looting", "Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    _resolve_trigger(scenario)
    assert len([s for s in scenario.game.stack if s.name == "Faithless Looting"]) == 3


def test_spider_verse_copies_only_once_each_turn():
    scenario = _verse(["Faithless Looting", "Faithless Looting"], ["Mountain"] * 6)
    _flashback(scenario, "Faithless Looting", "Mountain", "Mountain", "Mountain")
    scenario.will_take_the_may(True)
    _resolve_trigger(scenario)
    _flashback(scenario, "Faithless Looting", "Mountain", "Mountain", "Mountain")
    scenario.game.put_triggers_on_stack()
    assert len([s for s in scenario.game.stack if s.name == "Faithless Looting"]) == 3
    assert all(s.name == "Faithless Looting" for s in scenario.game.stack)


def test_spider_verse_ignores_a_spell_cast_from_the_hand():
    scenario = _verse([], ["Mountain"], hand=["Faithless Looting"])
    casting = scenario.cast("Faithless Looting")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.game.put_triggers_on_stack()
    assert [s.name for s in scenario.game.stack] == ["Faithless Looting"]


def test_spider_verse_copy_of_a_permanent_spell_is_a_hasty_token():
    scenario = _verse(["Beloved Beggar"], ["Plains"] * 6)
    casting = scenario.cast("Beloved Beggar", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Disturb")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Plains"] * 6))
    scenario.put_on_stack(casting)
    scenario.will_take_the_may(True)
    _resolve_trigger(scenario)
    scenario.resolve_top()  # the copy
    tokens = [s for s in scenario.game.battlefield if s.token and s.name == "Generous Soul"]
    assert len(tokens) == 1
    assert has_keyword(tokens[0], Keyword.HASTE, scenario.game)
    scenario.resolve_top()  # the original
    (original,) = [
        s for s in scenario.game.battlefield if not s.token and s.name == "Generous Soul"
    ]
    assert not has_keyword(original, Keyword.HASTE, scenario.game)


def test_spider_verse_copy_line_is_handled():
    handled(
        "Spider-Verse",
        "Whenever you cast a spell from anywhere other than your hand, you may copy it. If "
        "you do, you may choose new targets for the copy. If the copy is a permanent spell, "
        "it gains haste. Do this only once each turn.",
    )

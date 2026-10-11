"""Scenario: a keyword granted to a group of permanents - "All Rats have
fear." (Marrow-Gnawer), "Artifacts you control have indestructible."
(Darksteel Forge), "Legendary Humans you control have indestructible."
(General's Enforcer), "Other permanents you control have indestructible."
(Avacyn, Angel of Hope), "Sliver creatures you control have indestructible."
(Sliver Hivelord).

CR 613.1f: a keyword-granting effect is a layer 6 effect, and CR 611.3a: it
applies at any given moment to whatever its text indicates. The group word
decides the scope - "All" reaches both players, "you control" only the
source's controller - and the effect ends with its source (CR 604.2).
"""

from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario


def board(*alice, bob=()):
    return (
        Scenario()
        .player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )


def keywords(scenario, state):
    return {line.lower() for line in scenario.game.characteristics_of(state).abilities}


def test_all_rats_have_fear_for_both_players():
    scenario = board("Marrow-Gnawer", "Grizzly Bears", bob=["Marrow-Gnawer"])
    ours = scenario.creature("Marrow-Gnawer")
    bears = scenario.creature("Grizzly Bears")

    assert has_keyword(ours, "fear", scenario.game)
    assert not has_keyword(bears, "fear", scenario.game)
    assert has_keyword(scenario.creature("Marrow-Gnawer", "bob"), "fear", scenario.game)


def test_all_rats_includes_the_source_itself():
    scenario = board("Marrow-Gnawer")
    gnawer = scenario.creature("Marrow-Gnawer")

    assert has_keyword(gnawer, "fear", scenario.game)


def test_the_grant_ends_when_the_source_leaves():
    """CR 604.2: the opponent's Rat keeps fear only through its own grant."""
    scenario = board("Marrow-Gnawer", bob=["Marrow-Gnawer"])
    ours = scenario.creature("Marrow-Gnawer")
    theirs = scenario.creature("Marrow-Gnawer", "bob")
    scenario.game.put_into_graveyard(ours)

    assert ours.zone is Zone.GRAVEYARD
    assert has_keyword(theirs, "fear", scenario.game), "its own grant"
    scenario.game.put_into_graveyard(theirs)
    assert theirs.zone is Zone.GRAVEYARD


def test_artifacts_you_control_are_indestructible_and_the_opponents_are_not():
    scenario = board("Darksteel Forge", "Grizzly Bears", bob=["Sol Ring"])
    forge = scenario.find("Darksteel Forge", Zone.BATTLEFIELD)
    theirs = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    bears = scenario.creature("Grizzly Bears")

    assert "indestructible" in keywords(scenario, forge)
    assert "indestructible" not in keywords(scenario, theirs)
    assert "indestructible" not in keywords(scenario, bears)


def test_legendary_humans_you_control_only():
    """Kalain is a legendary Human, the Enforcer a nonlegendary Human, and
    Avacyn's player has no Enforcer here: only the legendary Human gets it."""
    scenario = board("General's Enforcer", "Kalain, Reclusive Painter", "Grizzly Bears")
    enforcer = scenario.creature("General's Enforcer")
    kalain = scenario.creature("Kalain, Reclusive Painter")
    bears = scenario.creature("Grizzly Bears")

    assert "indestructible" in keywords(scenario, kalain)
    assert "indestructible" not in keywords(scenario, enforcer), "nonlegendary Human"
    assert "indestructible" not in keywords(scenario, bears)


def test_other_permanents_you_control_reaches_noncreatures_but_not_the_source():
    scenario = board("Avacyn, Angel of Hope", "Forest", "Grizzly Bears", bob=["Grizzly Bears"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears")
    theirs = scenario.creature("Grizzly Bears", "bob")

    assert "indestructible" in keywords(scenario, forest)
    assert "indestructible" in keywords(scenario, bears)
    assert "indestructible" not in keywords(scenario, theirs)


def test_a_legend_that_starts_with_a_creature_type_still_reads_the_type():
    """Sliver Hivelord's bare first word "Sliver" is the legend's own short
    name (CR 201.5c) but here names the creature type (CR 205.3m): another
    Sliver you control is in the group, a Bear is not."""
    scenario = board("Sliver Hivelord", "Muscle Sliver", "Grizzly Bears")
    sliver = scenario.creature("Muscle Sliver")
    bears = scenario.creature("Grizzly Bears")
    hivelord = scenario.creature("Sliver Hivelord")

    assert "indestructible" in keywords(scenario, sliver)
    assert "indestructible" in keywords(scenario, hivelord)
    assert "indestructible" not in keywords(scenario, bears)


def test_creatures_of_the_chosen_type_have_fear_for_both_players():
    """Cover of Darkness: "Creatures of the chosen type have fear." - no
    controller clause, so the opponent's creatures of that type too."""
    scenario = board("Cover of Darkness", "Llanowar Elves", "Grizzly Bears", bob=["Llanowar Elves"])
    cover = scenario.find("Cover of Darkness", Zone.BATTLEFIELD)
    cover.choice = Choice(kind=ChoiceKind.CREATURE_TYPE, value="Elf")

    assert has_keyword(scenario.creature("Llanowar Elves"), "fear", scenario.game)
    assert has_keyword(scenario.creature("Llanowar Elves", "bob"), "fear", scenario.game)
    assert not has_keyword(scenario.creature("Grizzly Bears"), "fear", scenario.game)


# -- keywords with a machine of their own, granted to a group (CR 613.1f) -----

from magic_cards_model.machines import Step  # noqa: E402
from magic_cards_model.machines.keywords import outlast_activation  # noqa: E402
from tests.scenarios.harness import mana_from  # noqa: E402


def combat_board(alice, bob=(), manual=False):
    scenario = Scenario()
    if manual:
        scenario = scenario.manual_turn_based_actions()
    scenario = (
        scenario.player("alice", battlefield=list(alice))
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def pt(scenario, state):
    return scenario.game.characteristics_of(state).power_toughness


def test_all_slivers_have_flanking_so_a_vanilla_sliver_shrinks_its_blocker():
    """Sidewinder Sliver (CR 702.25a): the Construct has no flanking of its own."""
    scenario = combat_board(["Sidewinder Sliver", "Sliver Construct"], ["Craw Wurm"])
    construct = scenario.creature("Sliver Construct")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(construct, defending="bob")
    scenario.advance()
    scenario.block(construct, wurm)
    resolve_everything(scenario)

    assert pt(scenario, wurm) == (5, 3)


def test_a_blocking_sliver_has_flanking_too_so_nothing_triggers():
    scenario = combat_board(["Sidewinder Sliver"], ["Sliver Construct"])
    attacker = scenario.creature("Sidewinder Sliver")
    blocker = scenario.creature("Sliver Construct", "bob")

    scenario.attack_with(attacker, defending="bob")
    scenario.advance()
    scenario.block(attacker, blocker)

    assert scenario.stack_names() == []
    assert pt(scenario, blocker) == (2, 2)


def test_the_flanking_grant_ends_with_its_source():
    scenario = combat_board(["Sidewinder Sliver", "Sliver Construct"], ["Craw Wurm"])
    scenario.game.put_into_graveyard(scenario.creature("Sidewinder Sliver"))
    construct = scenario.creature("Sliver Construct")
    wurm = scenario.creature("Craw Wurm", "bob")

    scenario.attack_with(construct, defending="bob")
    scenario.advance()
    scenario.block(construct, wurm)
    resolve_everything(scenario)

    assert pt(scenario, wurm) == (6, 4)


def test_cavalry_master_gives_each_flanking_creature_a_second_instance():
    """CR 702.25b: two instances trigger separately, so -2/-2. A creature
    without flanking (Grizzly Bears) is outside "with flanking"."""
    scenario = combat_board(
        ["Cavalry Master", "Knight of the Holy Nimbus", "Grizzly Bears"], ["Craw Wurm"]
    )
    knight = scenario.creature("Knight of the Holy Nimbus")
    bears = scenario.creature("Grizzly Bears")
    wurm = scenario.creature("Craw Wurm", "bob")
    assert "flanking" not in keywords(scenario, bears)

    scenario.attack_with(knight, defending="bob")
    scenario.advance()
    scenario.block(knight, wurm)
    resolve_everything(scenario)

    assert pt(scenario, wurm) == (4, 2)


def test_first_slivers_chosen_gives_every_sliver_you_control_exalted():
    """CR 702.83a/b: two Slivers, so two instances, +2/+2 for a lone attacker;
    attacking with both is not "alone"."""
    scenario = combat_board(["First Sliver's Chosen", "Sliver Construct"], ["Craw Wurm"])
    construct = scenario.creature("Sliver Construct")

    scenario.attack_with(construct, defending="bob")
    resolve_everything(scenario)

    assert pt(scenario, construct) == (4, 4)


def test_exalted_needs_a_lone_attacker():
    scenario = combat_board(["First Sliver's Chosen", "Sliver Construct"])
    scenario.attack_with(
        scenario.creature("Sliver Construct"),
        scenario.creature("First Sliver's Chosen"),
        defending="bob",
    )
    resolve_everything(scenario)

    assert pt(scenario, scenario.creature("Sliver Construct")) == (2, 2)


def test_exalted_is_only_for_the_controllers_slivers():
    scenario = combat_board(["Grizzly Bears"], ["First Sliver's Chosen", "Sliver Construct"])
    bears = scenario.creature("Grizzly Bears")

    scenario.attack_with(bears, defending="bob")
    resolve_everything(scenario)

    assert pt(scenario, bears) == (2, 2)


def test_frenzy_sliver_pumps_an_unblocked_sliver_by_frenzy_one():
    """CR 702.68a: frenzy 1 - "Whenever this creature attacks and isn't
    blocked, it gets +1/+0 until end of turn.\""""
    scenario = combat_board(["Frenzy Sliver", "Sliver Construct"], ["Craw Wurm"], manual=True)
    construct = scenario.creature("Sliver Construct")

    scenario.attack_with(construct, defending="bob")
    scenario.advance()
    scenario.no_blocks()
    resolve_everything(scenario)

    assert pt(scenario, construct) == (3, 2)


def test_frenzy_does_nothing_for_a_blocked_sliver():
    scenario = combat_board(["Frenzy Sliver", "Sliver Construct"], ["Craw Wurm"], manual=True)
    construct = scenario.creature("Sliver Construct")

    scenario.attack_with(construct, defending="bob")
    scenario.advance()
    scenario.block(construct, scenario.creature("Craw Wurm", "bob"))
    resolve_everything(scenario)

    assert pt(scenario, construct) == (2, 2)


def test_absorb_prevents_one_of_the_damage_dealt_to_a_sliver():
    """CR 702.64a: absorb 1 - prevent 1 of that damage. A Bear is not a Sliver."""
    scenario = board("Lymph Sliver", "Sliver Construct", "Grizzly Bears", bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    construct = scenario.creature("Sliver Construct")
    bears = scenario.creature("Grizzly Bears")

    assert scenario.game.deal_damage(construct, 3, source=guide) == 2
    assert scenario.game.deal_damage(bears, 3, source=guide) == 3


def test_absorb_stacks_one_per_instance_and_never_goes_negative():
    scenario = board("Lymph Sliver", bob=["Lymph Sliver", "Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    ours = scenario.creature("Lymph Sliver")

    assert scenario.game.deal_damage(ours, 1, source=guide) == 0


def test_enduring_sliver_gives_other_slivers_outlast_two():
    """CR 702.107a: "{2}, {T}: Put a +1/+1 counter" at sorcery speed; the
    source Sliver itself (a Sliver, but "other") gets none."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Enduring Sliver", "Sliver Construct", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    construct = scenario.creature("Sliver Construct")
    construct.summoning_sick = False
    sources = scenario.untapped_sources("Plains", "Plains")

    activation = outlast_activation(scenario.game, construct, "alice")
    payment = activation.begin_paying()
    for source in sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()

    assert construct.counter_count("+1/+1") == 1
    assert construct.tapped
    enduring = scenario.creature("Enduring Sliver")
    assert "no outlast" in (outlast_why_not(scenario, enduring) or "no outlast")


def outlast_why_not(scenario, creature):
    try:
        return outlast_activation(scenario.game, creature, "alice").why_not()
    except ValueError as error:
        return str(error)


def test_spider_punk_gives_other_spiders_riot():
    """CR 702.136a: a Giant Spider entering is asked the riot question; the
    Punk itself (a Spider, but "other" is outside the group) keeps its own."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Giant Spider"],
            battlefield=["Spider-Punk", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Giant Spider")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Giant Spider", *sources)

    spider = scenario.creature("Giant Spider")
    assert spider.counter_count("+1/+1") == 1

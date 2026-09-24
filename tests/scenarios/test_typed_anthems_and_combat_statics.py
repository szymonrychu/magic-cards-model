"""Static abilities that pick out a group by type, token status, attack
status or keyword (CR 611.3, CR 613), and the combat restrictions statics
impose on declarations (CR 508.1c, CR 509.1a, CR 509.1b).

- "Heroes you control get +2/+2." (Avengers Assemble!) - the typed anthem
  for a creature type whose plural adds "-es" ("Hero", "Heroes"); Yotian
  Tactician's "Other Soldiers you control get +1/+1." is the second printing
  of the typed anthem.
- "Enchanted creature gets +2/+2, has first strike and vigilance, and is a
  legendary Soldier in addition to its other types." (Super-Soldier Serum);
  Raven Wings (an Equipment, "has flying, and is a Bird") and Tall as a
  Beanstalk (an Aura, "has reach, and is a Giant") as second printings.
- "Attacking creature tokens you control have first strike." (Okoye, Dora
  Milaje Leader); Starry-Eyed Skyrider's "Attacking tokens you control have
  flying." as the second printing.
- "Creatures with flying can't attack you or block creatures you control."
  (Storm, Windrider); Sandwurm Convergence's "Creatures with flying can't
  attack you or planeswalkers you control." as the second printing.
- "`<this>` can't be blocked if her power is 1 or less." (Stature, Size
  Shifter); Thieves' Tools' "Equipped creature can't be blocked as long as
  its power is 3 or less." as the second printing.
- "Intangibility - Ghost can't be blocked." (Ghost, Spectral Saboteur) - an
  ability word (CR 207.2c) in front of the plain restriction.
- "As long as there are two or more creature cards in your graveyard,
  `<this>` gets +2/+1." (Killmonger, Scourge of Wakanda); Mind Drill
  Assailant's threshold "As long as there are seven or more cards in your
  graveyard, this creature gets +3/+0." as the second printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import evasion_restriction_refusal, has_keyword
from magic_cards_model.machines.effects import create_tokens
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Supertype, Type
from magic_cards_model.models.token import TokenDefinition
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- typed anthem --------------------------------------------------------------


def test_avengers_assemble_pumps_heroes_you_control_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Avengers Assemble!", "Okoye, Dora Milaje Leader", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Captain America, Wings of Freedom"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    captain = scenario.creature("Captain America, Wings of Freedom", "bob")

    assert _pt(scenario, okoye) == (5, 4)
    assert _pt(scenario, bears) == (2, 2), "not a Hero"
    assert _pt(scenario, captain) == (3, 1), "a Hero, but not one alice controls"


def test_yotian_tactician_pumps_other_soldiers_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Yotian Tactician", "U.S.Agent, John Walker", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tactician = scenario.creature("Yotian Tactician", "alice")
    agent = scenario.creature("U.S.Agent, John Walker", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _pt(scenario, agent) == (4, 3)
    assert _pt(scenario, tactician) == (3, 4), "Other Soldiers: not itself"
    assert _pt(scenario, bears) == (2, 2)


# -- attached pump, keywords and type ------------------------------------------


def test_super_soldier_serum_pumps_grants_and_makes_a_legendary_soldier():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Super-Soldier Serum"], battlefield=["Grizzly Bears", "Plains", "Plains"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Super-Soldier Serum", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )

    chars = scenario.game.characteristics_of(bears)
    assert _pt(scenario, bears) == (4, 4)
    assert has_keyword(bears, "first strike", scenario.game)
    assert has_keyword(bears, "vigilance", scenario.game)
    assert Supertype.LEGENDARY in chars.supertypes
    assert "Soldier" in chars.subtypes and "Bear" in chars.subtypes, "in addition to"


def test_the_serum_soldier_is_counted_by_a_soldier_anthem():
    """Layer 4's type grant (CR 613.1d) is in place before layer 7c's
    anthem (CR 613.4c) asks who is a Soldier."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Super-Soldier Serum"],
            battlefield=["Grizzly Bears", "Yotian Tactician", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _pt(scenario, bears) == (2, 2)

    scenario.cast_and_resolve(
        "Super-Soldier Serum", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )

    assert _pt(scenario, bears) == (5, 5)


def test_the_legendary_serum_soldier_is_subject_to_the_legend_rule():
    """CR 704.5j: two legendary permanents with the same name - the Serum
    makes a Grizzly Bears legendary, and a second legendary Grizzly Bears
    puts the pair under the legend rule."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Super-Soldier Serum", "Super-Soldier Serum"],
            battlefield=["Grizzly Bears", "Grizzly Bears"] + ["Plains"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    scenario.cast_and_resolve(
        "Super-Soldier Serum", *scenario.untapped_sources("Plains", "Plains"), targets=[first]
    )
    assert first.zone is Zone.BATTLEFIELD and second.zone is Zone.BATTLEFIELD

    scenario.cast_and_resolve(
        "Super-Soldier Serum", *scenario.untapped_sources("Plains", "Plains"), targets=[second]
    )
    scenario.state_based_actions()

    bears = [s for s in scenario.game.battlefield if s.name == "Grizzly Bears"]
    assert len(bears) == 1


def test_raven_wings_makes_the_equipped_creature_a_flying_bird():
    scenario = Scenario().player("alice", battlefield=["Raven Wings", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wings = scenario.find("Raven Wings", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(bears, "flying", scenario.game)

    wings.attach_to(bears)

    chars = scenario.game.characteristics_of(bears)
    assert _pt(scenario, bears) == (3, 2)
    assert has_keyword(bears, "flying", scenario.game)
    assert "Bird" in chars.subtypes and "Bear" in chars.subtypes
    assert Supertype.LEGENDARY not in chars.supertypes


def test_tall_as_a_beanstalk_makes_the_enchanted_creature_a_giant_with_reach():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Tall as a Beanstalk"], battlefield=["Grizzly Bears"] + ["Forest"] * 4
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Tall as a Beanstalk", *scenario.untapped_sources(*["Forest"] * 4), targets=[bears]
    )

    chars = scenario.game.characteristics_of(bears)
    assert _pt(scenario, bears) == (5, 5)
    assert has_keyword(bears, "reach", scenario.game)
    assert "Giant" in chars.subtypes


# -- attacking tokens ----------------------------------------------------------


def _soldier_token(scenario, username="alice"):
    """A creature token that has been under `username`'s control since the
    turn began (CR 302.6), so it may attack this turn."""
    (token,) = create_tokens(
        scenario.game,
        TokenDefinition(
            types=(Type.CREATURE,), subtypes=("Soldier",), power=1, toughness=1, name="Soldier"
        ),
        username,
        1,
    )
    token.summoning_sick = False
    return token


def test_okoye_tokens_created_on_entering_are_not_first_strikers_at_home():
    scenario = (
        Scenario()
        .player("alice", hand=["Okoye, Dora Milaje Leader"], battlefield=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Okoye, Dora Milaje Leader", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()
    tokens = [s for s in scenario.game.battlefield if s.token and "Soldier" in s.subtypes]
    assert len(tokens) == 2
    assert not any(has_keyword(token, "first strike", scenario.game) for token in tokens)


def test_okoye_first_strike_applies_only_while_the_token_is_attacking():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Okoye, Dora Milaje Leader"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    token = _soldier_token(scenario)
    idle = _soldier_token(scenario)
    scenario.advance()
    scenario.advance()
    scenario.attack_with(token, okoye)

    assert has_keyword(token, "first strike", scenario.game)
    assert not has_keyword(okoye, "first strike", scenario.game), "Okoye is no token"
    assert not has_keyword(idle, "first strike", scenario.game), "a token, but not attacking"

    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.advance()
    scenario.block(token, bears)
    scenario.advance()
    scenario.combat_damage()
    # First strike: the 1/1 token deals its damage first and still dies to
    # the 2/2's regular damage; the Bears took 1 in the first-strike step.
    assert bears.damage == 1


def test_starry_eyed_skyrider_gives_attacking_tokens_flying():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Starry-Eyed Skyrider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    token = _soldier_token(scenario)
    assert not has_keyword(token, "flying", scenario.game)
    scenario.advance()
    scenario.advance()
    scenario.attack_with(token)
    assert has_keyword(token, "flying", scenario.game)


# -- creatures with flying can't attack you / block ----------------------------


def test_storm_stops_an_opponents_flier_attacking_her_controller():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Captain America, Wings of Freedom", "Grizzly Bears"])
        .player("alice", battlefield=["Storm, Windrider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.creature("Captain America, Wings of Freedom", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.advance()
    scenario.advance()

    assert not scenario.can_attack(captain, "alice")
    assert scenario.can_attack(bears, "alice"), "no flying, no restriction"
    with pytest.raises(ValueError, match="CR 508.1c"):
        scenario.attack_with(captain, defending="alice")


def test_storm_stops_a_flier_blocking_her_controllers_creatures():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Storm, Windrider", "Grizzly Bears"])
        .player("bob", battlefield=["Captain America, Wings of Freedom", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    captain = scenario.creature("Captain America, Wings of Freedom", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.advance()

    with pytest.raises(ValueError, match="CR 509.1b"):
        scenario.block(bears, captain)
    scenario.block(bears, giant)
    assert giant.id in scenario.game.combat.attack_by(bears.id).blockers


def test_storm_does_not_stop_her_controllers_own_fliers():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Storm, Windrider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    storm = scenario.creature("Storm, Windrider", "alice")
    scenario.advance()
    scenario.advance()
    assert scenario.can_attack(storm, "bob")


def test_sandwurm_convergence_stops_fliers_attacking_you():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=["Captain America, Wings of Freedom", "Grizzly Bears"])
        .player("alice", battlefield=["Sandwurm Convergence"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    captain = scenario.creature("Captain America, Wings of Freedom", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.advance()
    scenario.advance()
    assert not scenario.can_attack(captain, "alice")
    assert scenario.can_attack(bears, "alice")


# -- can't be blocked while power is small ------------------------------------


def test_stature_cant_be_blocked_while_her_power_is_one_or_less():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stature, Size Shifter"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stature = scenario.creature("Stature, Size Shifter", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    assert evasion_restriction_refusal(scenario.game, stature, bears) is not None

    stature.add_counters("+1/+1", 1)
    assert scenario.game.power_of(stature) == 2
    assert evasion_restriction_refusal(scenario.game, stature, bears) is None


def test_thieves_tools_makes_a_small_equipped_creature_unblockable():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Thieves' Tools", "Grizzly Bears", "Hill Giant"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tools = scenario.find("Thieves' Tools", Zone.BATTLEFIELD, "alice")
    mine = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    blocker = scenario.creature("Grizzly Bears", "bob")

    assert evasion_restriction_refusal(scenario.game, mine, blocker) is None
    tools.attach_to(mine)
    assert evasion_restriction_refusal(scenario.game, mine, blocker) is not None

    tools.attach_to(giant)
    giant.add_counters("+1/+1", 1)
    assert scenario.game.power_of(giant) == 4
    assert evasion_restriction_refusal(scenario.game, giant, blocker) is None
    assert evasion_restriction_refusal(scenario.game, mine, blocker) is None


def test_ghost_cant_be_blocked_behind_its_ability_word():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ghost, Spectral Saboteur"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ghost = scenario.creature("Ghost, Spectral Saboteur", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert evasion_restriction_refusal(scenario.game, ghost, bears) is not None


# -- graveyard-count gate ------------------------------------------------------


def test_killmonger_turns_on_when_the_second_creature_card_hits_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Killmonger, Scourge of Wakanda", "Grizzly Bears"],
            graveyard=["Hill Giant", "Lightning Bolt", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    killmonger = scenario.creature("Killmonger, Scourge of Wakanda", "alice")
    assert _pt(scenario, killmonger) == (3, 3), "only one creature card"

    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))

    assert _pt(scenario, killmonger) == (5, 4)


def test_killmonger_counts_only_creature_cards_in_your_own_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Killmonger, Scourge of Wakanda"],
            graveyard=["Grizzly Bears", "Hill Giant"],
        )
        .player("bob", graveyard=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    killmonger = scenario.creature("Killmonger, Scourge of Wakanda", "alice")
    assert _pt(scenario, killmonger) == (5, 4)


def test_killmonger_with_only_opponents_creature_cards_is_unpumped():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Killmonger, Scourge of Wakanda"], graveyard=["Grizzly Bears"]
        )
        .player("bob", graveyard=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    killmonger = scenario.creature("Killmonger, Scourge of Wakanda", "alice")
    assert _pt(scenario, killmonger) == (3, 3)


def test_mind_drill_assailant_threshold_leads_with_its_condition():
    seven = ["Plains"] * 6 + ["Lightning Bolt"]
    scenario = (
        Scenario().player("alice", battlefield=["Mind Drill Assailant"], graveyard=seven).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assailant = scenario.creature("Mind Drill Assailant", "alice")
    assert _pt(scenario, assailant) == (5, 5)


def test_mind_drill_assailant_below_threshold_is_unpumped():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mind Drill Assailant"], graveyard=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assailant = scenario.creature("Mind Drill Assailant", "alice")
    assert _pt(scenario, assailant) == (2, 5)


# -- the sweep credits every static line ---------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "Avengers Assemble!",
        "Super-Soldier Serum",
        "Okoye, Dora Milaje Leader",
        "Storm, Windrider",
        "Stature, Size Shifter",
        "Ghost, Spectral Saboteur",
        "Killmonger, Scourge of Wakanda",
        "Raven Wings",
        "Tall as a Beanstalk",
        "Starry-Eyed Skyrider",
        "Sandwurm Convergence",
        "Thieves' Tools",
        "Mind Drill Assailant",
    ],
)
def test_every_static_line_is_handled(name):
    for clause in card_support(card(name)).clauses:
        if clause.kind == "static":
            assert clause.outcome == "handled", (name, clause.text, clause.outcome)


# -- Storm's cast trigger --------------------------------------------------------


def test_storm_gives_the_targeted_creatures_flying():
    """ "Whenever you cast a spell that targets one or more creatures, those
    creatures gain flying until end of turn." - "those creatures" are the
    spell's own creature targets (CR 601.2c)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Storm, Windrider", "Grizzly Bears", "Hill Giant", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_onto_stack("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])
    while scenario.stack_names():
        scenario.pass_until_resolved()

    assert has_keyword(bears, "flying", scenario.game)
    assert not has_keyword(giant, "flying", scenario.game), "not a target"


def test_storm_ignores_a_spell_targeting_only_a_player():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Storm, Windrider", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.stack_names() == ["Lightning Bolt"]
    assert scenario.game.cast_condition_notices == []

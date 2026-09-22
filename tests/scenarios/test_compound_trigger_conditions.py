"""Scenario: one triggered ability with more than one trigger condition.

"When you cast this spell and whenever this creature attacks, destroy up to
one target nonland permanent." (Cityscape Leveler) is one ability, printed
once, that triggers on two different events. Every CR number below was read
whole off the Comprehensive Rules on disk this session (`mise run rules:find`,
rules effective September 25, 2026):

- **CR 603.1b** - "A triggered ability may have more than one trigger
  condition, ..."
- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers."
- **CR 603.2c** - "An ability triggers only once each time its trigger event
  occurs."
- **CR 113.6k** - "A trigger condition that can't trigger from the battlefield
  functions in all zones it can trigger from. Other trigger conditions of the
  same triggered ability may function in different zones." The cast half
  functions on the stack, the attack half on the battlefield.
- **CR 601.2i** - "... the spell becomes cast. Any abilities that trigger when
  a spell is cast or put onto the stack trigger at this time." It goes on the
  stack above the spell (CR 603.3: "The ability becomes the topmost object on
  the stack.") and so resolves first.
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen." ("up to one target")
- **CR 608.2b** - an illegal target leaves the ability unresolved; a legal one
  "will resolve normally".
- **CR 702.12b** - "A permanent with indestructible can't be destroyed."
- **CR 111.10h** - "A Powerstone token is a colorless Powerstone artifact
  token with '{T}: Add {C}. This mana can't be spent to cast a nonartifact
  spell.'"
- **CR 702.84a** - unearth is an *activated* ability that returns the card;
  nothing is cast, so a cast trigger does not fire (Cityscape Leveler's own
  2022-10-14 ruling says exactly this).
- **CR 504.1** / **CR 121.2** - the draw step's turn-based draw, and every
  card drawn being its own draw (Orcish Bowmasters' "except the first one they
  draw in each of their draw steps").

The indestructible corner is decided by the printed rulings of the identical
"Destroy target permanent. Its controller creates ..." templating: Beast
Within (2021-03-19) - "If the target is legal but not destroyed (most likely
because it has indestructible), its controller does create a Beast token" -
and Assassin's Trophy (2024-02-02), the same for its search. "Its controller"
names the target's controller, which a legal, surviving target still has.

The gap this file is the regression test for: the parser cut the condition at
its first comma and filed the whole compound under the first event word it
recognised, so Cityscape Leveler's cast half, Orcish Bowmasters' draw half and
Voice of Resurgence's opponent-casts half never triggered at all (prod game
0cf08288: Leveler cast and resolved with no trigger).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import unearth_activation
from magic_cards_model.machines.triggers import (
    TriggerEvent,
    triggered_abilities_of,
    zones_ability_functions_in,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario, mana_from

WASTES = ["Wastes"] * 8


def _names(scenario, username):
    return [state.name for state in scenario.game.permanents_controlled_by(username)]


def _powerstones(scenario, username):
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Powerstone Token"
    ]


# -- the parse: one printed line, one ability per trigger condition ---------


def test_the_compound_condition_parses_into_each_of_its_trigger_events():
    abilities = triggered_abilities_of(card("Cityscape Leveler"))
    assert [(a.event, a.condition) for a in abilities] == [
        (TriggerEvent.CAST_SPELL, "you cast this spell"),
        (TriggerEvent.ATTACKS, "this creature attacks"),
    ]
    assert len({a.effect for a in abilities}) == 1, "both conditions share one effect"
    assert len({a.text for a in abilities}) == 1, "both are the one printed ability"


def test_and_when_joins_conditions_the_same_way_as_and_whenever():
    abilities = triggered_abilities_of(card("Eldrazi Repurposer"))
    assert [(a.word.value, a.event) for a in abilities] == [
        ("when", TriggerEvent.CAST_SPELL),
        ("when", TriggerEvent.DIES),
    ]


def test_each_condition_functions_in_its_own_zone():
    """CR 113.6k's last sentence: the cast half from the stack, the attack
    half from the battlefield."""
    scenario = Scenario().player("alice", battlefield=["Cityscape Leveler"]).player("bob").build()
    leveler = scenario.creature("Cityscape Leveler", "alice")
    cast, attack = triggered_abilities_of(leveler.card)
    assert zones_ability_functions_in(cast, leveler) == frozenset({Zone.STACK})
    assert zones_ability_functions_in(attack, leveler) == frozenset({Zone.BATTLEFIELD})


# -- Cityscape Leveler: the cast half --------------------------------------


def _leveler_in_hand(**bob):
    scenario = (
        Scenario()
        .player("alice", hand=["Cityscape Leveler"], battlefield=WASTES + ["Memnite"])
        .player("bob", **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_cast_trigger_goes_on_the_stack_above_the_spell_and_resolves_first():
    scenario = _leveler_in_hand(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])

    scenario.cast_onto_stack("Cityscape Leveler", *scenario.untapped_sources(*WASTES))

    assert scenario.stack_names() == [
        "Cityscape Leveler",
        "Cityscape Leveler's triggered ability",
    ]
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    (powerstone,) = _powerstones(scenario, "bob")
    assert powerstone.tapped, "a tapped Powerstone token"
    assert scenario.stack_names() == ["Cityscape Leveler"], "the spell is still waiting"

    scenario.pass_until_resolved()
    assert "Cityscape Leveler" in _names(scenario, "alice")


def test_the_cast_trigger_with_no_target_chosen_destroys_nothing_and_makes_no_token():
    """CR 115.6: "up to one" may choose zero. With no target there is no "its
    controller" to create anything."""
    scenario = _leveler_in_hand(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [])

    scenario.cast_onto_stack("Cityscape Leveler", *scenario.untapped_sources(*WASTES))
    assert scenario.stack_names() == [
        "Cityscape Leveler",
        "Cityscape Leveler's triggered ability",
    ], "a zero-target ability is still put on the stack (CR 115.6)"
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert _powerstones(scenario, "bob") == []
    assert _powerstones(scenario, "alice") == []


def test_destroying_your_own_permanent_gives_you_the_powerstone():
    scenario = _leveler_in_hand()
    memnite = scenario.creature("Memnite", "alice")
    scenario.choose_trigger_targets("Cityscape Leveler", [memnite])

    scenario.cast_onto_stack("Cityscape Leveler", *scenario.untapped_sources(*WASTES))
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.GRAVEYARD
    assert len(_powerstones(scenario, "alice")) == 1
    assert _powerstones(scenario, "bob") == []


def test_an_indestructible_target_survives_but_its_controller_still_gets_the_powerstone():
    """CR 702.12b refuses the destroy; the target is still legal (CR 608.2b),
    so "its controller creates" still happens - Beast Within's ruling for the
    identical templating."""
    scenario = _leveler_in_hand(battlefield=["Darksteel Relic"])
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [relic])

    scenario.cast_onto_stack("Cityscape Leveler", *scenario.untapped_sources(*WASTES))
    scenario.pass_until_resolved()

    assert relic.zone is Zone.BATTLEFIELD
    assert len(_powerstones(scenario, "bob")) == 1


def test_a_land_cannot_be_chosen():
    scenario = _leveler_in_hand(battlefield=["Wastes"])
    wastes = scenario.find("Wastes", Zone.BATTLEFIELD, "bob")
    try:
        scenario.choose_trigger_targets("Cityscape Leveler", [wastes])
    except ValueError:
        return
    raise AssertionError("a land is not a nonland permanent (CR 601.2c, 603.3d)")


def test_the_cast_trigger_resolves_even_if_the_spell_is_countered_in_response():
    """The trigger is independent of its source once it is on the stack
    (Titans' Vanguard/Eldrazi Repurposer's rulings for the same shape)."""
    scenario = _leveler_in_hand(
        hand=["Counterspell"], battlefield=["Grizzly Bears", "Island", "Island"]
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])
    leveler = scenario.cast_onto_stack("Cityscape Leveler", *scenario.untapped_sources(*WASTES))

    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[leveler],
    )
    scenario.pass_until_resolved()
    assert leveler.zone is Zone.GRAVEYARD, "countered"

    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert len(_powerstones(scenario, "bob")) == 1


def test_putting_it_onto_the_battlefield_is_not_casting_it():
    scenario = _leveler_in_hand(battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])

    scenario.put_onto_battlefield("Cityscape Leveler", "alice")

    assert scenario.game.stack_is_empty
    assert scenario.pending_triggers == []
    assert bears.zone is Zone.BATTLEFIELD


# -- Cityscape Leveler: the attack half ------------------------------------


def test_the_attack_trigger_fires_from_the_battlefield():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cityscape Leveler"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])

    scenario.attack_with(scenario.creature("Cityscape Leveler", "alice"))
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert len(_powerstones(scenario, "bob")) == 1


def test_an_unearthed_leveler_triggers_on_attack_but_not_on_unearth():
    """CR 702.84a: unearth is activated, not cast - the Leveler's own ruling."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Cityscape Leveler"], battlefield=WASTES)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Cityscape Leveler", [bears])

    leveler = scenario.find("Cityscape Leveler", Zone.GRAVEYARD, "alice")
    activation = unearth_activation(scenario.game, leveler, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*WASTES):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    entered = activation.resolve()

    assert scenario.game.stack_is_empty and scenario.pending_triggers == []
    assert bears.zone is Zone.BATTLEFIELD

    scenario.attack_with(entered)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.GRAVEYARD
    assert len(_powerstones(scenario, "bob")) == 1


# -- generality: other printings with the same compound templating ---------


def test_titans_vanguard_counts_the_board_at_cast_and_again_at_attack():
    """ "When you cast this spell and whenever this creature attacks, put a
    +1/+1 counter on each colorless creature you control." The cast half
    resolves before Titans' Vanguard itself does, so only Memnite gets one
    (the card's own 2024-06-07 ruling); the attack half reaches both."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Titans' Vanguard"],
            battlefield=["Memnite", "Mountain", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")

    sources = scenario.untapped_sources("Mountain", "Forest", "Forest", "Forest", "Forest")
    scenario.cast_onto_stack("Titans' Vanguard", *sources)
    assert scenario.stack_names() == ["Titans' Vanguard", "Titans' Vanguard's triggered ability"]
    scenario.pass_until_resolved()
    assert memnite.counters[Counter.PLUS_ONE] == 1
    scenario.pass_until_resolved()
    vanguard = scenario.creature("Titans' Vanguard", "alice")
    assert vanguard.counters[Counter.PLUS_ONE] == 0

    vanguard.summoning_sick = False
    scenario.attack_with(vanguard)
    scenario.pass_until_resolved()
    assert memnite.counters[Counter.PLUS_ONE] == 2
    assert vanguard.counters[Counter.PLUS_ONE] == 1


def test_eldrazi_repurposer_makes_a_spawn_on_cast_and_another_when_it_dies():
    """ "When you cast this spell and when this creature dies" - the "and when"
    joint, and a cast half paired with a look-back (dies) half."""
    scenario = (
        Scenario()
        .player("alice", hand=["Eldrazi Repurposer"], battlefield=["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Eldrazi Repurposer", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    assert _names(scenario, "alice").count("Eldrazi Spawn Token") == 1
    scenario.pass_until_resolved()

    repurposer = scenario.creature("Eldrazi Repurposer", "alice")
    scenario.game.destroy(repurposer)
    scenario.pass_until_resolved()
    assert _names(scenario, "alice").count("Eldrazi Spawn Token") == 2


def test_voice_of_resurgence_triggers_on_an_opponent_casting_during_your_turn():
    """ "Whenever an opponent casts a spell during your turn and when this
    creature dies" - the first half used to be swallowed by the second."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Voice of Resurgence"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )

    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Voice of Resurgence's triggered ability",
    ]
    scenario.pass_until_resolved()
    assert "Elemental Token" in _names(scenario, "alice")


def test_voice_of_resurgence_ignores_its_controllers_own_spells():
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Voice of Resurgence", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    assert scenario.stack_names() == ["Lightning Bolt"]


# -- Orcish Bowmasters: a qualified second condition -----------------------


def _bowmasters_on_bobs_turn():
    scenario = (
        Scenario()
        .player("bob", library=["Island"] * 5, battlefield=["Grizzly Bears"])
        .player("alice", library=["Island"] * 2, battlefield=["Orcish Bowmasters"])
        .build()
    )
    return scenario


def test_bowmasters_ignores_the_first_card_drawn_in_the_opponents_draw_step():
    scenario = _bowmasters_on_bobs_turn()
    scenario.start_at(Step.DRAW)
    scenario.draw(1, "bob")
    assert scenario.pending_triggers == [] and scenario.game.stack_is_empty


def test_bowmasters_triggers_on_the_second_card_drawn_in_that_draw_step():
    scenario = _bowmasters_on_bobs_turn()
    scenario.start_at(Step.DRAW)
    scenario.draw(1, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])
    scenario.draw(1, "bob")
    scenario.pass_until_resolved()
    assert bears.damage == 1


def test_bowmasters_triggers_on_a_draw_outside_the_draw_step():
    scenario = _bowmasters_on_bobs_turn()
    scenario.start_at(Step.UPKEEP)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Orcish Bowmasters", [bears])
    scenario.draw(1, "bob")
    scenario.pass_until_resolved()
    assert bears.damage == 1


def test_bowmasters_ignores_its_controllers_own_draws():
    scenario = _bowmasters_on_bobs_turn()
    scenario.start_at(Step.UPKEEP)
    scenario.draw(1, "alice")
    assert scenario.pending_triggers == [] and scenario.game.stack_is_empty

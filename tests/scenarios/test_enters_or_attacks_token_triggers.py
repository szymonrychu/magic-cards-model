"""Token-creating triggers read behind any ability word, and tokens created
for an opponent (CR 111.2).

- "Do You Like Squirrels? - Whenever The Unbeatable Squirrel Girl enters or
  attacks, create a 1/1 green Squirrel creature token." (The Unbeatable
  Squirrel Girl) - CR 603.2's "enters or attacks" trigger behind a flavor
  word label that ends in punctuation; the sweep used to read the whole line
  as a static ability. Infestation Expert's "Whenever this creature enters or
  attacks, create a 1/1 green Insect creature token." is the second printing.
- "When The Sentry enters, target opponent creates The Void, a legendary 5/5
  black Horror Villain creature token with flying, indestructible, and "The
  Void attacks each combat if able."" (The Sentry, Golden Guardian) - CR
  111.2: the player the effect names creates the token and controls it.
  Hunted Horror's "When this creature enters, target opponent creates two 3/3
  green Centaur creature tokens with protection from black." is the second
  printing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card import Supertype
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _tokens(scenario, username, subtype):
    return [
        state
        for state in scenario.game.battlefield
        if state.token and subtype in state.subtypes and state.controller == username
    ]


def test_squirrel_girls_trigger_is_parsed_behind_its_flavor_word():
    abilities = parse_abilities(card("The Unbeatable Squirrel Girl"))
    triggered = [ability for ability in abilities if isinstance(ability, TriggeredAbility)]
    assert len(triggered) == 1
    assert triggered[0].ability_word == "Do You Like Squirrels?"


def test_squirrel_girl_creates_a_squirrel_when_she_enters():
    scenario = (
        Scenario()
        .player("alice", hand=["The Unbeatable Squirrel Girl"], battlefield=["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "The Unbeatable Squirrel Girl", *scenario.untapped_sources(*["Forest"] * 4)
    )
    scenario.pass_until_resolved()

    (squirrel,) = _tokens(scenario, "alice", "Squirrel")
    assert (squirrel.power, squirrel.toughness) == (1, 1)


def test_squirrel_girl_creates_a_squirrel_each_time_she_attacks():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["The Unbeatable Squirrel Girl"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    girl = scenario.creature("The Unbeatable Squirrel Girl", "alice")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(girl)
    scenario.pass_until_resolved()

    assert len(_tokens(scenario, "alice", "Squirrel")) == 1


def test_squirrel_girls_activated_ability_counts_the_new_squirrels():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["The Unbeatable Squirrel Girl"] + ["Forest"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    girl = scenario.creature("The Unbeatable Squirrel Girl", "alice")
    scenario.activate(girl, *scenario.untapped_sources(*["Forest"] * 4))
    scenario.pass_until_resolved()
    # She is herself a Squirrel: X is 1.
    assert len(_tokens(scenario, "alice", "Squirrel")) == 1


def test_infestation_expert_creates_an_insect_on_entering_and_attacking():
    scenario = (
        Scenario()
        .player("alice", hand=["Infestation Expert"], battlefield=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Infestation Expert", *scenario.untapped_sources(*["Forest"] * 5))
    scenario.pass_until_resolved()
    assert len(_tokens(scenario, "alice", "Insect")) == 1


def test_the_sentry_makes_the_opponent_create_the_void():
    scenario = (
        Scenario()
        .player("alice", hand=["The Sentry, Golden Guardian"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("The Sentry, Golden Guardian", ["bob"])
    scenario.cast_and_resolve(
        "The Sentry, Golden Guardian", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()

    assert _tokens(scenario, "alice", "Horror") == []
    (void,) = _tokens(scenario, "bob", "Horror")
    chars = scenario.game.characteristics_of(void)
    assert void.name == "The Void"
    assert Supertype.LEGENDARY in chars.supertypes
    assert "Villain" in chars.subtypes
    assert (scenario.game.power_of(void), scenario.game.toughness_of(void)) == (5, 5)
    assert has_keyword(void, "flying", scenario.game)
    assert has_keyword(void, "indestructible", scenario.game)
    assert any("attacks each combat if able" in line for line in chars.abilities)


def test_the_void_must_attack_each_combat():
    """CR 508.1d: on the opponent's next turn the token's own "attacks each
    combat if able" is a requirement their declaration has to obey."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["The Sentry, Golden Guardian"], battlefield=["Plains"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("The Sentry, Golden Guardian", ["bob"])
    scenario.cast_and_resolve(
        "The Sentry, Golden Guardian", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()
    (void,) = _tokens(scenario, "bob", "Horror")
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.DECLARE_ATTACKERS):
        scenario.advance()

    with pytest.raises(ValueError, match=r"CR 508\.1d"):
        scenario.attack_with(defending="alice")
    scenario.attack_with(void, defending="alice")
    assert scenario.attackers() == [void]


def test_a_second_void_puts_the_opponent_under_the_legend_rule():
    """CR 704.5j applies to the opponent, who controls both legendary
    tokens named The Void."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Sentry, Golden Guardian", "The Sentry, Golden Guardian"],
            battlefield=["Plains"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("The Sentry, Golden Guardian", ["bob"])
    scenario.cast_and_resolve(
        "The Sentry, Golden Guardian", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.choose_trigger_targets("The Sentry, Golden Guardian", ["bob"])
    scenario.cast_and_resolve(
        "The Sentry, Golden Guardian", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert len(_tokens(scenario, "bob", "Horror")) == 1


def test_hunted_horror_gives_the_opponent_two_centaurs():
    scenario = (
        Scenario()
        .player("alice", hand=["Hunted Horror"], battlefield=["Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Hunted Horror", ["bob"])
    scenario.cast_and_resolve("Hunted Horror", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    centaurs = _tokens(scenario, "bob", "Centaur")
    assert len(centaurs) == 2
    assert _tokens(scenario, "alice", "Centaur") == []
    for centaur in centaurs:
        assert (scenario.game.power_of(centaur), scenario.game.toughness_of(centaur)) == (3, 3)
        assert has_keyword(centaur, "protection from black", scenario.game) or any(
            "protection from black" in line.lower()
            for line in scenario.game.characteristics_of(centaur).abilities
        )


@pytest.mark.parametrize(
    "name",
    [
        "The Unbeatable Squirrel Girl",
        "Infestation Expert // Infested Werewolf",
        "The Sentry, Golden Guardian",
        "Hunted Horror",
    ],
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)

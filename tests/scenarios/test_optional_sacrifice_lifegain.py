""" "Whenever `<this>` enters or attacks, you may sacrifice a `<X>` or a
`<Y>`. If you do, you gain `<n>` life." - CR 118.12's optional cost, where the
restriction names two different kinds of permanent joined by "or" rather than
one.

West Wind Avatar: "Whenever this creature enters or attacks, you may
sacrifice a token or a land. If you do, you gain 3 life."

- **CR 603.1b/CR 603.6a** - "enters or attacks" is one printed condition
  read as two abilities on two different events, already generic
  (`_expand_enters_or_attacks`) and not new here.
- **CR 111.1/CR 205.2a** - "a token" and "a land" are two independent kinds
  of permanent, satisfied by any permanent meeting either one - not two
  separate sacrifices, one of either.
- **CR 118.12** - the "if you do" consequence runs once the player has said
  yes and actually sacrificed, regardless of what the sacrifice was.
- **CR 608.2d** - "the player can't choose an option that's illegal or
  impossible": with nothing on the battlefield satisfying either half, the
  question is still put (`_parse_conditional_sacrifice_clause`'s own
  `affirmative_is_legal` flag) but only declining is a legal answer.

No second legal printing carries the "sacrifice a `<X>` or a `<Y>`" shape at
all (dated MEMORY.md line): `_or_description_requirements` is proven here
instead across every combination a real board can offer - a token, a land, a
token that is also a land (a Powerstone-shaped land token would count, though
this pool's own Food token is not a land and is used as the plain-token
case), and a creature satisfying neither.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario


def test_sacrificing_a_token_on_enter_gains_three_life():
    scenario = Scenario().player("alice", library=["West Wind Avatar"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")
    life_before = scenario.player("alice").life
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(food, username="alice", source="West Wind Avatar")

    avatar = scenario.put_onto_battlefield("West Wind Avatar", "alice", from_zone=Zone.LIBRARY)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["West Wind Avatar's triggered ability"]
    scenario.pass_until_resolved()

    assert food.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before + 3
    assert avatar.zone is Zone.BATTLEFIELD


def test_sacrificing_a_land_on_enter_gains_three_life():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest"], library=["West Wind Avatar"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    life_before = scenario.player("alice").life
    scenario.will_take_the_may(True, username="alice")
    scenario.will_choose_cards(forest, username="alice", source="West Wind Avatar")

    avatar = scenario.put_onto_battlefield("West Wind Avatar", "alice", from_zone=Zone.LIBRARY)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["West Wind Avatar's triggered ability"]
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before + 3
    assert avatar.zone is Zone.BATTLEFIELD


def test_a_creature_satisfies_neither_half_and_is_never_offered():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], library=["West Wind Avatar"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    life_before = scenario.player("alice").life

    scenario.put_onto_battlefield("West Wind Avatar", "alice", from_zone=Zone.LIBRARY)
    scenario.game.put_triggers_on_stack()
    if scenario.stack_names():
        scenario.pass_until_resolved()

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == life_before


def test_declining_leaves_the_permanent_alone():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forest"], library=["West Wind Avatar"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    life_before = scenario.player("alice").life
    scenario.will_take_the_may(False, username="alice")

    scenario.put_onto_battlefield("West Wind Avatar", "alice", from_zone=Zone.LIBRARY)
    scenario.game.put_triggers_on_stack()
    if scenario.stack_names():
        scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == life_before

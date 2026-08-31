"""Sacrificing N of a group (CR 701.21a, CR 608.2d) - Lotus Field.

"Hexproof / This land enters tapped. / When this land enters, sacrifice two
lands. / {T}: Add three mana of any one color."

The clause under test is "sacrifice two lands": no target, no "you control"
qualifier, just a count and a card type. Three rules decide what it can reach:

- CR 701.21a: "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard. A player can't sacrifice
  something that isn't a permanent, or something that's a permanent they
  don't control." That last half is why an opponent's lands are never
  candidates, even though the printed text never says "you control".
- CR 205.2a's card types are the group, so a nonland permanent is never a
  candidate however green it is.
- CR 608.2d: which two is a choice made by the ability's controller as it
  resolves, so the scenarios script the answer rather than letting the engine
  pick a favourite.

Lotus Field is a legal candidate for its own trigger - it is on the battlefield
by then (CR 603.6a's trigger fires on the enter event and resolves afterwards),
so with only one other land it can and must be one of the two, and alone it is
the only thing there is to sacrifice at all. CR 101.3 covers the shortfall:
the part of the instruction that can't be performed is simply ignored.

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 701.21a, CR 404.1, CR 603.6a, CR 603.6d, CR 608.2d, CR 101.3, CR 605.1a,
CR 605.3b, CR 400.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario

LOTUS_FIELD = "Lotus Field"
TRIGGER = f"{LOTUS_FIELD}'s triggered ability"


def board(
    *,
    alice_battlefield: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=alice_battlefield or [], hand=[LOTUS_FIELD])
        .player("bob", battlefield=bob_battlefield or [])
    )


def test_the_trigger_sacrifices_the_two_lands_its_controller_chose():
    """The happy path: three other lands on the board, alice names two of
    them, and exactly those two are sacrificed (CR 608.2d, CR 701.21a)."""
    scenario = board(
        alice_battlefield=["Forest", "Mountain", "Island", "Grizzly Bears"],
        bob_battlefield=["Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    mountain = scenario.creature("Mountain", "alice")
    island = scenario.creature("Island", "alice")
    scenario.will_choose_cards(forest, mountain, username="alice")

    field = scenario.play_land(LOTUS_FIELD)
    assert scenario.stack_names() == [TRIGGER]
    scenario.resolve_top()

    assert forest.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.GRAVEYARD
    assert island.zone is Zone.BATTLEFIELD
    assert field.zone is Zone.BATTLEFIELD


def test_it_enters_tapped_before_its_own_trigger_resolves():
    """CR 603.6d's "enters tapped" is a replacement effect applied as it
    enters, not something the trigger does - so Lotus Field is already tapped
    while its own enter trigger is still on the stack."""
    scenario = board(alice_battlefield=["Forest", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    mountain = scenario.creature("Mountain", "alice")
    scenario.will_choose_cards(forest, mountain, username="alice")

    field = scenario.play_land(LOTUS_FIELD)

    assert not field.untapped
    assert scenario.stack_names() == [TRIGGER]


def test_with_only_one_other_land_lotus_field_is_one_of_the_two():
    """Lotus Field is on the battlefield by the time its own trigger resolves,
    so it is a candidate for it. With one other land, the two sacrificed are
    that land and Lotus Field itself."""
    scenario = board(alice_battlefield=["Forest"], bob_battlefield=["Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    field = scenario.play_land(LOTUS_FIELD)
    scenario.will_choose_cards(forest, field, username="alice")
    scenario.resolve_top()

    assert forest.zone is Zone.GRAVEYARD
    assert field.zone is Zone.GRAVEYARD
    assert scenario.battlefield_names() == ["Swamp"]


def test_alone_on_the_battlefield_it_sacrifices_just_itself():
    """CR 101.3: the part of the instruction that can't be performed is
    ignored. Only one land exists to sacrifice, so the question put is
    "sacrifice 1", not a refusal to do anything at all."""
    scenario = board(bob_battlefield=["Swamp", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    field = scenario.play_land(LOTUS_FIELD)
    scenario.resolve_top()

    assert field.zone is Zone.GRAVEYARD
    assert [decision.amount for decision in scenario.questions_asked()] == [1]
    assert [decision.cards for decision in scenario.questions_asked()] == [(field.id,)]


def test_an_opponents_lands_are_never_candidates():
    """CR 701.21a: "A player can't sacrifice ... something that's a permanent
    they don't control." Bob's two Swamps are never offered, so the only
    candidates are alice's own two lands and they both go."""
    scenario = board(
        alice_battlefield=["Forest"],
        bob_battlefield=["Swamp", "Swamp", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    field = scenario.play_land(LOTUS_FIELD)
    scenario.resolve_top()

    (question,) = scenario.questions_asked()
    assert set(question.cards or ()) == {forest.id, field.id}
    assert sorted(scenario.battlefield_names()) == ["Island", "Swamp", "Swamp"]


def test_nonland_permanents_are_never_candidates():
    """The group is CR 205.2a's land type. Grizzly Bears and Birds of Paradise
    are permanents alice controls and neither is ever offered."""
    scenario = board(
        alice_battlefield=["Forest", "Mountain", "Grizzly Bears", "Birds of Paradise"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    mountain = scenario.creature("Mountain", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    birds = scenario.creature("Birds of Paradise", "alice")

    field = scenario.play_land(LOTUS_FIELD)
    scenario.will_choose_cards(forest, mountain, username="alice")
    scenario.resolve_top()

    (question,) = scenario.questions_asked()
    assert set(question.cards or ()) == {forest.id, mountain.id, field.id}
    assert bears.zone is Zone.BATTLEFIELD
    assert birds.zone is Zone.BATTLEFIELD


def test_the_sacrificed_lands_go_to_their_owners_graveyard():
    """CR 701.21a moves them "directly to its owner's graveyard", and CR 404.1
    agrees. Each sacrificed card ends up in exactly one zone (CR 400.1) - the
    graveyard - and nothing is left behind on the battlefield."""
    scenario = board(alice_battlefield=["Forest", "Mountain", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    mountain = scenario.creature("Mountain", "alice")
    scenario.will_choose_cards(forest, mountain, username="alice")

    scenario.play_land(LOTUS_FIELD)
    scenario.resolve_top()

    assert [card.name for card in scenario.player("alice").graveyard] == ["Forest", "Mountain"]
    assert scenario.player("bob").graveyard == []
    scenario.assert_in_exactly_one_zone(forest, mountain)


def test_lotus_fields_own_mana_ability_still_works_if_it_survives():
    """Sacrificing two *other* lands leaves Lotus Field on the battlefield.
    Once it untaps, `{T}: Add three mana of any one color.` is a mana ability
    like any other - CR 605.3b keeps it off the stack, and all three mana are
    the one colour chosen."""
    scenario = board(alice_battlefield=["Forest", "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.creature("Forest", "alice")
    mountain = scenario.creature("Mountain", "alice")
    scenario.will_choose_cards(forest, mountain, username="alice")

    field = scenario.play_land(LOTUS_FIELD)
    scenario.resolve_top()
    assert field.zone is Zone.BATTLEFIELD
    assert not field.untapped

    scenario.game.untap_step()
    returned = scenario.activate(field, color=Color.BLUE)

    assert returned is None
    assert scenario.stack_names() == []
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 3}

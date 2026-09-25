"""Graveyard and exile conditions: "there's a Lesson card in your graveyard",
"fewer than six creature cards", "five or more mana values among cards in
your graveyard", "this card is in your graveyard", "the only creature card",
"you own a card in exile", "you control a Desert or there is a Desert card in
your graveyard", "the number of other Caves you control plus the number of
Cave cards in your graveyard", and "the same name as ... a creature card in
your graveyard".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 404.1** - a player's graveyard is their discard pile; every count here
  is of that zone as the condition is asked.
- **CR 202.3** - "The mana value of an object is a number equal to the total
  amount of mana in its mana cost" - a land's is 0.
- **CR 108.3** - the owner of a card is the player who started the game with
  it; CR 406.1 is the exile zone "you own a card in exile" looks through.
- **CR 700.7** - "this [something]" is that particular object; **CR 400.7** -
  an object that moves zones becomes a new object.
- **CR 201.2a** - two objects have the same name if they have at least one
  name in common.
- **CR 603.4** / **CR 608.2a** - an intervening "if" is checked as the
  trigger event occurs and again as the ability resolves.
- **CR 602.5b** - "Activate only if <condition>" keeps applying after a
  control change.
- **CR 613.5** - a count of permanents reads the computed board.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _next_upkeep(scenario) -> None:
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # untap
    scenario.advance()  # upkeep


# -- "there's a <subtype> card in your graveyard" -----------------------------


def _sentries_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Walltop Sentries"],
            graveyard=graveyard,
            library=["Plains"] * 3,
        )
        .player("bob", battlefield=["Mountain"], hand=["Lightning Bolt"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bolt_the_sentries(scenario) -> None:
    sentries = scenario.creature("Walltop Sentries", "alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=[sentries])
    scenario.resolve_top()


def test_a_lesson_card_in_your_graveyard_triggers_and_resolves():
    """Walltop Sentries: "When this creature dies, if there's a Lesson card in
    your graveyard, you gain 2 life." """
    scenario = _sentries_board(["Airbending Lesson"])
    _bolt_the_sentries(scenario)
    assert scenario.stack_names() == ["Walltop Sentries's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 22
    assert scenario.game.intervening_if_notices == []


def test_no_lesson_card_never_triggers():
    """CR 603.4: a graveyard with no Lesson in it - the dying Sentries itself
    is not one - and the ability never triggers."""
    scenario = _sentries_board(["Grizzly Bears"])
    _bolt_the_sentries(scenario)
    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20
    assert scenario.game.intervening_if_notices == []


def test_the_lesson_leaving_before_resolution_removes_the_ability():
    """CR 608.2a: the Lesson is exiled with the trigger waiting - the recheck
    is false and alice gains nothing."""
    scenario = _sentries_board(["Airbending Lesson"])
    _bolt_the_sentries(scenario)
    (trigger,) = scenario.game.stack
    scenario.game.exile_cards([scenario.find("Airbending Lesson", Zone.GRAVEYARD, "alice")])
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20


def _dignitary_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Lys Alana Dignitary"],
            graveyard=graveyard,
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_an_elf_card_in_your_graveyard_unlocks_the_mana_ability():
    """Lys Alana Dignitary: "{T}: Add {G}{G}. Activate only if there is an Elf
    card in your graveyard." - a second printing of the subtype-card shape,
    on a mana ability."""
    scenario = _dignitary_board(["Llanowar Elves"])
    dignitary = scenario.creature("Lys Alana Dignitary", "alice")
    assert scenario.why_cannot_activate(dignitary) is None
    scenario.activate(dignitary)
    assert scenario.game.mana_pool_receiving("alice").floating  # {G}{G} added


def test_no_elf_card_refuses_the_mana_ability():
    """An Elf on the battlefield is not an Elf card in the graveyard - the
    Dignitary itself is an Elf, and does not count."""
    scenario = _dignitary_board(["Grizzly Bears"])
    dignitary = scenario.creature("Lys Alana Dignitary", "alice")
    refusal = scenario.why_cannot_activate(dignitary)
    assert refusal == "Lys Alana Dignitary's activation restriction is not met (CR 602.5b)"


def test_an_elf_card_in_an_opponents_graveyard_is_not_yours():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Lys Alana Dignitary"], library=["Plains"] * 3)
        .player("bob", graveyard=["Llanowar Elves"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dignitary = scenario.creature("Lys Alana Dignitary", "alice")
    assert scenario.why_cannot_activate(dignitary) is not None


# -- "you control a Desert or there is a Desert card in your graveyard" -------


def _pharaohs_board(*, battlefield=(), graveyard=(), bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Wall of Forgotten Pharaohs", *battlefield],
            graveyard=list(graveyard),
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=["Island", "Island", "Swamp", "Swamp"],
            library=["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_desert_neither_controlled_nor_in_the_graveyard_is_refused():
    """Wall of Forgotten Pharaohs: "{T}: This creature deals 1 damage to target
    player or planeswalker. Activate only if you control a Desert or there is
    a Desert card in your graveyard." """
    scenario = _pharaohs_board()
    wall = scenario.creature("Wall of Forgotten Pharaohs", "alice")
    refusal = scenario.why_cannot_activate(wall)
    assert refusal == "Wall of Forgotten Pharaohs's activation restriction is not met (CR 602.5b)"


def test_a_desert_card_in_the_graveyard_alone_is_enough():
    """The graveyard half on its own: the combinator reads "or" as either."""
    scenario = _pharaohs_board(graveyard=["Desert of the True"])
    wall = scenario.creature("Wall of Forgotten Pharaohs", "alice")
    assert scenario.why_cannot_activate(wall) is None
    scenario.activate(wall, targets=["bob"])
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 19


def test_a_controlled_desert_alone_is_enough():
    scenario = _pharaohs_board(battlefield=["Sunscorched Desert"])
    wall = scenario.creature("Wall of Forgotten Pharaohs", "alice")
    assert scenario.why_cannot_activate(wall) is None


def test_the_desert_restriction_follows_the_new_controller():
    """CR 602.5b: bob takes the Wall with Soul Ransom. Alice's graveyard Desert
    is not his - "your" is bob's graveyard now - so he is refused."""
    scenario = _pharaohs_board(graveyard=["Desert of the True"], bob_hand=["Soul Ransom"])
    wall = scenario.creature("Wall of Forgotten Pharaohs", "alice")
    assert scenario.why_cannot_activate(wall) is None
    _next_upkeep(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Soul Ransom",
        *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp", username="bob"),
        targets=[wall],
        username="bob",
    )
    assert scenario.game.controller_of(wall).username == "bob"
    refusal = scenario.why_cannot_activate(wall, username="bob")
    assert refusal == "Wall of Forgotten Pharaohs's activation restriction is not met (CR 602.5b)"


@pytest.mark.parametrize(("graveyard", "triggers"), [(["Desert of the True"], True), ([], False)])
def test_desert_compound_as_an_intervening_if(graveyard, triggers):
    """Sand Strangler: "When this creature enters, if you control a Desert or
    there is a Desert card in your graveyard, you may have this creature deal
    3 damage to target creature." - the same compound, triggered."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Sand Strangler"], graveyard=graveyard, battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Sand Strangler", *scenario.untapped_sources(*["Mountain"] * 4))
    assert len(scenario.game.stack) + len(scenario.pending_triggers) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


# -- "you have N or more creature cards in your graveyard" ------------------


@pytest.mark.parametrize(("creatures", "triggers"), [(4, True), (3, False)])
def test_you_have_n_or_more_creature_cards_in_your_graveyard(creatures, triggers):
    """Pit Keeper: "When this creature enters, if you have four or more
    creature cards in your graveyard, you may return target creature card from
    your graveyard to your hand." - lands in the graveyard do not count."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Pit Keeper"],
            graveyard=["Grizzly Bears"] * creatures + ["Forest"] * 3,
            battlefield=["Swamp"] * 2,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Pit Keeper", *scenario.untapped_sources("Swamp", "Swamp"))
    assert len(scenario.game.stack) + len(scenario.pending_triggers) == (1 if triggers else 0)
    assert scenario.game.intervening_if_notices == []


@pytest.mark.parametrize(("creatures", "triggers"), [(5, True), (6, False), (0, True)])
def test_fewer_than_n_creature_cards_in_your_graveyard(creatures, triggers):
    """Shadowborn Demon: "At the beginning of your upkeep, if there are fewer
    than six creature cards in your graveyard, sacrifice a creature." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Shadowborn Demon"],
            graveyard=["Grizzly Bears"] * creatures,
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == (["Shadowborn Demon's triggered ability"] if triggers else [])
    assert scenario.game.intervening_if_notices == []


# -- "there are N or more mana values among cards in your graveyard" ---------


def _spy_at_end_step(graveyard: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sanguine Spy"], graveyard=graveyard, library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step
    return scenario


def test_five_mana_values_among_cards_in_your_graveyard():
    """Sanguine Spy: "At the beginning of your end step, if there are five or
    more mana values among cards in your graveyard, you may pay 2 life. If you
    do, draw a card." - 0 (a land), 1, 2, 3 and 4 are five values."""
    scenario = _spy_at_end_step(
        ["Forest", "Llanowar Elves", "Grizzly Bears", "Airbending Lesson", "Soul Ransom"]
    )
    assert scenario.stack_names() == ["Sanguine Spy's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_repeated_mana_values_count_once():
    """Six cards, but only four distinct mana values (1, 1, 2, 2, 0, 0)."""
    scenario = _spy_at_end_step(
        ["Llanowar Elves", "Lightning Bolt", "Grizzly Bears", "Pit Keeper", "Forest", "Island"]
    )
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


# -- "this card is in your graveyard" -----------------------------------------


def _master_board(*, graveyard=(), battlefield=(), exile=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=list(graveyard),
            battlefield=list(battlefield),
            exile=list(exile),
            library=["Plains"] * 4,
        )
        .player("bob", library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_this_card_in_your_graveyard_triggers():
    """Master of Death: "At the beginning of your upkeep, if this card is in
    your graveyard, you may pay 1 life. If you do, return it to your hand." """
    scenario = _master_board(graveyard=["Master of Death"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == ["Master of Death's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_this_card_in_your_graveyard_does_not_trigger_from_the_battlefield():
    """CR 113.6b: an ability that states the zone it functions in functions
    only from there - Master of Death on the battlefield asks nothing."""
    scenario = _master_board(battlefield=["Master of Death"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_firemane_angel_triggers_from_the_graveyard_too():
    """Firemane Angel's "if Firemane Angel is in your graveyard or on the
    battlefield" names both zones (CR 113.6b), by the card's own name (CR
    201.5) - from the graveyard it triggers and resolves."""
    scenario = _master_board(graveyard=["Firemane Angel"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == ["Firemane Angel's triggered ability"]
    scenario.will_take_the_may()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 21


def test_a_graveyard_count_does_not_move_the_source_into_the_graveyard():
    """Sanguine Spy's "among cards in your graveyard" counts the pile; it does
    not say the Spy functions there, so a Spy in the graveyard never triggers."""
    scenario = _master_board(
        graveyard=[
            "Sanguine Spy",
            "Forest",
            "Llanowar Elves",
            "Grizzly Bears",
            "Airbending Lesson",
            "Soul Ransom",
        ]
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step
    assert scenario.stack_names() == []


def test_this_card_is_a_new_object_once_it_has_left_the_graveyard():
    """CR 608.2a and CR 400.7: the recheck reads the object the ability came
    from, by its zone-change stamp - exiled, it is not in the graveyard, and
    it is not that object any more either."""
    from magic_cards_model.machines.conditions import ConditionContext, read_condition

    scenario = _master_board(graveyard=["Master of Death"])
    master = scenario.find("Master of Death", Zone.GRAVEYARD, "alice")
    game = scenario.game
    context = ConditionContext(
        game=game, controller="alice", source=master, source_stamp=master.zone_change_stamp
    )
    clause = "this card is in your graveyard"
    assert read_condition(context, clause) is True
    game.exile_cards([master])
    assert read_condition(context, clause) is False


def test_this_card_is_in_your_graveyard_read_against_each_zone():
    """The same clause asked of the card in each zone: only the graveyard is
    true, and only the owner's own ("your") graveyard."""
    scenario = _master_board(graveyard=["Master of Death"])
    master = scenario.find("Master of Death", Zone.GRAVEYARD, "alice")
    game = scenario.game
    assert game.condition_holds("alice", "this card is in your graveyard", master) is True
    assert game.condition_holds("bob", "this card is in your graveyard", master) is False
    game.exile_cards([master])
    assert game.condition_holds("alice", "this card is in your graveyard", master) is False


def test_on_the_battlefield_or_in_your_graveyard():
    """Skyblade's Boon's "Activate only if Skyblade's Boon is on the
    battlefield or in your graveyard" and Firemane Angel's "if Firemane Angel
    is in your graveyard or on the battlefield" - the card's own name (CR
    201.5), and any one of the places named."""
    scenario = _master_board(graveyard=["Skyblade's Boon"], battlefield=["Firemane Angel"])
    game = scenario.game
    boon = scenario.find("Skyblade's Boon", Zone.GRAVEYARD, "alice")
    angel = scenario.creature("Firemane Angel", "alice")
    boon_clause = "skyblade's boon is on the battlefield or in your graveyard"
    angel_clause = "firemane angel is in your graveyard or on the battlefield"
    assert game.condition_holds("alice", boon_clause, boon) is True
    assert game.condition_holds("alice", angel_clause, angel) is True
    game.exile_cards([boon, angel])
    assert game.condition_holds("alice", boon_clause, boon) is False
    assert game.condition_holds("alice", angel_clause, angel) is False


def test_firemane_angel_on_the_battlefield_triggers_and_resolves():
    """Firemane Angel: "At the beginning of your upkeep, if Firemane Angel is
    in your graveyard or on the battlefield, you may gain 1 life." """
    scenario = _master_board(battlefield=["Firemane Angel"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == ["Firemane Angel's triggered ability"]
    scenario.will_take_the_may()
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 21
    assert scenario.game.intervening_if_notices == []


def test_the_only_creature_card_in_your_graveyard():
    """Nether Spirit: "At the beginning of your upkeep, if this card is the
    only creature card in your graveyard, you may return this card to the
    battlefield." - lands beside it do not matter; another creature card
    does."""
    scenario = _master_board(graveyard=["Nether Spirit", "Forest"])
    spirit = scenario.find("Nether Spirit", Zone.GRAVEYARD, "alice")
    game = scenario.game
    clause = "this card is the only creature card in your graveyard"
    assert game.condition_holds("alice", clause, spirit) is True
    assert game.condition_holds("bob", clause, spirit) is False

    other = _master_board(graveyard=["Nether Spirit", "Grizzly Bears"])
    lonely = other.find("Nether Spirit", Zone.GRAVEYARD, "alice")
    assert other.game.condition_holds("alice", clause, lonely) is False


def test_the_only_creature_card_triggers_from_the_graveyard():
    scenario = _master_board(graveyard=["Nether Spirit", "Forest"])
    _next_upkeep(scenario)
    _next_upkeep(scenario)
    assert scenario.stack_names() == ["Nether Spirit's triggered ability"]


# -- "you own a card in exile" -------------------------------------------------


def test_you_own_a_card_in_exile():
    """Dreadlight Monstrosity: "{3}{U}{U}: This creature can't be blocked this
    turn. Activate only if you own a card in exile." - CR 108.3: bob's card in
    exile is not alice's."""
    scenario = _master_board(battlefield=["Dreadlight Monstrosity"])
    monstrosity = scenario.creature("Dreadlight Monstrosity", "alice")
    refusal = scenario.why_cannot_activate(monstrosity)
    assert refusal == "Dreadlight Monstrosity's activation restriction is not met (CR 602.5b)"

    scenario.game.exile_cards([scenario.player("bob").library[0]])
    assert scenario.why_cannot_activate(monstrosity) is not None

    scenario.game.exile_cards([scenario.player("alice").library[0]])
    assert scenario.why_cannot_activate(monstrosity) is None


# -- "the number of other Caves you control plus the number of Cave cards in
# your graveyard is three or greater" -----------------------------------------


@pytest.mark.parametrize(
    ("battlefield", "graveyard", "allowed"),
    [
        (["Captivating Cave", "Echoing Deeps"], ["Captivating Cave"], True),
        (["Captivating Cave"], ["Captivating Cave", "Echoing Deeps"], True),
        (["Captivating Cave", "Echoing Deeps"], [], False),
        ([], ["Captivating Cave", "Forest"], False),
    ],
)
def test_other_caves_plus_cave_cards(battlefield, graveyard, allowed):
    """Cavernous Maw: "{2}: This land becomes a 3/3 Elemental creature until
    end of turn. It's still a Cave land. Activate only if the number of other
    Caves you control plus the number of Cave cards in your graveyard is three
    or greater." - Cavernous Maw is a Cave, and "other" leaves it out."""
    scenario = _master_board(battlefield=["Cavernous Maw", *battlefield], graveyard=graveyard)
    maw = scenario.creature("Cavernous Maw", "alice")
    refusal = scenario.why_cannot_activate(maw, index=1)
    assert (refusal is None) == allowed


# -- "it doesn't have the same name as another creature you control or a
# creature card in your graveyard" ---------------------------------------------


def _project_board(*, battlefield=(), graveyard=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Guardian Project", "Forest", "Forest", *battlefield],
            graveyard=list(graveyard),
            library=["Plains"] * 3,
        )
        .player("bob", battlefield=["Mountain"], hand=["Lightning Bolt"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_bears(scenario) -> None:
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))


def test_a_new_name_draws_a_card():
    """Guardian Project: "Whenever a nontoken creature you control enters, if
    it doesn't have the same name as another creature you control or a
    creature card in your graveyard, draw a card." """
    scenario = _project_board(battlefield=["Llanowar Elves"], graveyard=["Llanowar Elves"])
    _cast_bears(scenario)
    assert scenario.stack_names() == ["Guardian Project's triggered ability"]
    scenario.pass_until_resolved()
    assert [card.name for card in scenario.player("alice").hand] == ["Plains"]


def test_the_same_name_on_the_battlefield_does_not_trigger():
    scenario = _project_board(battlefield=["Grizzly Bears"])
    _cast_bears(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_the_same_name_in_the_graveyard_does_not_trigger():
    scenario = _project_board(graveyard=["Grizzly Bears"])
    _cast_bears(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_the_creature_dying_in_response_puts_its_own_name_in_the_graveyard():
    """CR 608.2a with last known information: bob bolts the new Bears with the
    trigger waiting. Its card is now a creature card in alice's graveyard with
    its name, so the recheck is false and nothing is drawn."""
    scenario = _project_board()
    _cast_bears(scenario)
    (trigger,) = scenario.game.stack
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=[bears])
    scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert scenario.player("alice").hand == []


# -- the template, read directly -----------------------------------------------


def test_every_graveyard_form_is_read_against_the_live_graveyard():
    scenario = _master_board(
        graveyard=["Grizzly Bears", "Llanowar Elves", "Lightning Bolt", "Airbending Lesson"],
        battlefield=["Sunscorched Desert"],
    )
    game = scenario.game
    expected = {
        "there's a lesson card in your graveyard": True,
        "there is an elf card in your graveyard": True,
        "there is a desert card in your graveyard": False,
        "there are two or more creature cards in your graveyard": True,
        "there are fewer than two creature cards in your graveyard": False,
        "there are no land cards in your graveyard": True,
        "there are three or more mana values among cards in your graveyard": True,
        "there are four or more mana values among cards in your graveyard": False,
        "you have four or more cards in your graveyard": True,
        "an opponent has a card in their graveyard": False,
        "you control a desert or there is a desert card in your graveyard": True,
        "you own a card in exile": False,
    }
    for clause, holds in expected.items():
        assert game.condition_holds("alice", clause) is holds, clause

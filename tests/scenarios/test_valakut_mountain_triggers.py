"""Scenario: Valakut, the Molten Pinnacle's entry trigger and its intervening *if*.

One mechanic: a triggered ability whose *condition* names a land **subtype**
and whose intervening *if* **counts** that subtype across the board. Both
halves are questions about the computed board (CR 613.5), which is what makes
this card a combo piece rather than a Mountain: Dryad of the Ilysian Grove
turns every land its controller has into a Mountain, so lands that print no red
mana at all both fire the trigger and count towards it.

Card text, verified with `resolve_cards` in the session that wrote this file:

- **Valakut, the Molten Pinnacle** (Land): "This land enters tapped. /
  Whenever a Mountain you control enters, if you control at least five other
  Mountains, you may have this land deal 3 damage to any target. / {T}: Add
  {R}."
- **Dryad of the Ilysian Grove** (Enchantment Creature - Nymph Dryad): "You may
  play an additional land on each of your turns. / Lands you control are every
  basic land type in addition to their other types."
- **Blood Moon** (Enchantment): "Nonbasic lands are Mountains."

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.4** - an intervening *if* clause: "When the trigger event occurs,
  the ability checks whether the stated condition is true. The ability triggers
  only if it's true."
- **CR 608.2a** - the same clause is checked **again** as the ability resolves:
  if it is false then, the ability is removed from the stack and does nothing.
  That second check is the one a naive implementation skips, and it has its own
  test below.
- **CR 613.5** - the layer system is "continually and automatically" applied,
  so both the entering permanent's subtypes and the count of Mountains are read
  off the computed board.
- **CR 613.1d** - layer 4, where Dryad's and Blood Moon's type changes live.
- **CR 305.6** - a land with a basic land type has the intrinsic "{T}: Add
  [mana symbol]".
- **CR 305.7** - an effect that *sets* a land's subtype to a basic land type
  takes away its old land types and "all abilities generated from its rules
  text, its old land types, and any..." - **`knowledge_search` truncates this
  rule at "and any" on every phrasing tried in this session**, and nothing here
  relies on the missing tail; the rules-text clause that does come back is what
  the Blood Moon test below rests on.
- **CR 700.4** - ""Other" means any object other than the object being referred
  to", which is what makes "five **other** Mountains" exclude Valakut itself
  and so demand six Mountains on the battlefield.
- **CR 205.3i** - Mountain is a land type (a subtype), not a card type, which
  is why reading this condition needs the subtype and not the type line.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _scenario(*, hand, battlefield, opponent=()):
    scenario = (
        Scenario()
        .player("alice", life=20, hand=list(hand), battlefield=list(battlefield))
        .player("bob", life=20, battlefield=list(opponent))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _valakut(scenario):
    return scenario.find("Valakut, the Molten Pinnacle", Zone.BATTLEFIELD)


def _mountains(scenario, username="alice"):
    """Every permanent that permanent-counts as a Mountain right now (CR 613.5)."""
    return [
        state
        for state in scenario.game.battlefield
        if state.controller == username
        and "Mountain" in scenario.game.characteristics_of(state).subtypes
    ]


# --------------------------------------------------------------------------
# The plain card: six Mountains, no help
# --------------------------------------------------------------------------


def test_a_sixth_mountain_entering_triggers_valakut():
    """Five *other* Mountains besides Valakut (CR 700.4) - four already there
    and the fifth entering - so CR 603.4's condition is true and the ability
    triggers."""
    scenario = _scenario(
        hand=["Mountain"],
        battlefield=[
            "Valakut, the Molten Pinnacle",
            "Mountain",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
    )
    scenario.play_land("Mountain")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Valakut, the Molten Pinnacle's triggered ability"]


def test_one_mountain_short_does_not_trigger_it():
    """The same board one Mountain short, so CR 603.4's clause is false and the
    ability never triggers - the count is a real count.

    Note Valakut prints the type line "Land" with **no** Mountain subtype, so
    on a board of plain Mountains it is not one of the things being counted and
    CR 700.4's "other" changes nothing. The "other" only bites once something
    has made Valakut itself a Mountain, which is
    `test_under_dryad_valakut_itself_does_not_count` below.
    """
    scenario = _scenario(
        hand=["Mountain"],
        battlefield=[
            "Valakut, the Molten Pinnacle",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
    )
    assert len(_mountains(scenario)) == 3, "Valakut is a plain Land, not a Mountain"

    scenario.play_land("Mountain")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_a_nonmountain_land_entering_does_not_trigger_it():
    """The condition names a *subtype* (CR 205.3i). A Forest entering with six
    Mountains already out is not "a Mountain you control enters", so nothing
    triggers however true the intervening *if* would have been."""
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Valakut, the Molten Pinnacle",
            "Mountain",
            "Mountain",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
    )
    assert len(_mountains(scenario)) == 5, "the five printed Mountains; Valakut is not one"

    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_an_opponents_mountain_entering_does_not_trigger_it():
    """ "a Mountain **you control**" - Bob's land is not Alice's business, even
    though Alice's own five Mountains would satisfy the intervening *if*."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            battlefield=[
                "Valakut, the Molten Pinnacle",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", life=20, hand=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert len(_mountains(scenario)) == 5

    scenario.put_onto_battlefield("Mountain", "bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_the_trigger_deals_three_to_a_chosen_target():
    """The payload, once the trigger is on the stack: "you may have this land
    deal 3 damage to any target" - a real target chosen as the ability goes on
    the stack, not a default."""
    scenario = _scenario(
        hand=["Mountain"],
        battlefield=[
            "Valakut, the Molten Pinnacle",
            "Mountain",
            "Mountain",
            "Mountain",
            "Mountain",
        ],
    )
    scenario.will_choose_targets("bob", source="Valakut, the Molten Pinnacle")
    scenario.play_land("Mountain")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


# --------------------------------------------------------------------------
# Dryad of the Ilysian Grove: the whole point of the card
# --------------------------------------------------------------------------


def test_dryad_makes_every_land_you_control_count_as_a_mountain():
    """Layer 4 (CR 613.1d): "Lands you control are every basic land type in
    addition to their other types", so an Island, a Swamp and a Wastes are all
    Mountains for CR 613.5's purposes - and each carries the {R} that comes
    with the type (CR 305.6)."""
    scenario = _scenario(
        hand=[],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
            "Wastes",
        ],
    )

    assert len(_mountains(scenario)) == 5
    assert (
        "Mountain"
        in scenario.game.characteristics_of(scenario.find("Island", Zone.BATTLEFIELD)).subtypes
    )


def test_a_forest_entering_under_dryad_fires_the_trigger():
    """The combo, end to end: the land that enters is a Forest on the card and
    a Mountain on the board, so the *condition* is met by a land that prints no
    red mana - and the five other lands already out meet the intervening *if*
    the same way."""
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
            "Wastes",
        ],
    )
    assert len(_mountains(scenario)) == 5, "Valakut plus four, so four *other* Mountains"

    scenario.will_choose_targets("bob", source="Valakut, the Molten Pinnacle")
    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Valakut, the Molten Pinnacle's triggered ability"]

    scenario.resolve_top()
    assert scenario.player("bob").life == 17


def test_under_dryad_one_land_short_still_does_not_trigger():
    """The count is real, not a shortcut that fires whenever Dryad is out. One
    fewer land and the intervening *if* is false, so CR 603.4 refuses to let
    the ability trigger at all."""
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
        ],
    )

    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_under_dryad_valakut_itself_does_not_count():
    """CR 700.4's "other", finally load-bearing.

    Under Dryad, Valakut *is* a Mountain, so a board with exactly five
    Mountains on it - Valakut and four others, once the fifth land enters -
    would satisfy "at least five Mountains" but not "at least five **other**
    Mountains". It must not trigger, and the count that matters is five
    besides Valakut, meaning six Mountains in play.
    """
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
        ],
    )
    scenario.play_land("Forest")

    mountains = _mountains(scenario)
    assert len(mountains) == 5, "five Mountains, one of which is Valakut"
    assert _valakut(scenario) in mountains

    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [], "only four *other* Mountains"


def test_dryad_does_not_make_itself_a_mountain():
    """Dryad is an Enchantment Creature, not a land, so "lands you control"
    passes it by and it is not one of the Mountains being counted."""
    scenario = _scenario(
        hand=[],
        battlefield=["Dryad of the Ilysian Grove", "Valakut, the Molten Pinnacle", "Island"],
    )

    dryad = scenario.find("Dryad of the Ilysian Grove", Zone.BATTLEFIELD)
    assert "Mountain" not in scenario.game.characteristics_of(dryad).subtypes
    assert dryad not in _mountains(scenario)


# --------------------------------------------------------------------------
# CR 608.2a: the intervening *if* checked again on resolution
# --------------------------------------------------------------------------


def test_the_intervening_if_going_false_before_resolution_does_nothing():
    """The case a naive implementation gets wrong.

    CR 603.4 checks the clause when the trigger event occurs, and the ability
    goes on the stack. CR 608.2a then checks it **again** as the ability
    resolves - "if it isn't [true], the ability is removed from the stack and
    does nothing". Here the board shrinks below five other Mountains in
    between, so no damage is dealt even though the trigger was perfectly legal
    when it fired.

    Written against Dryad rather than six real Mountains on purpose: removing
    Dryad takes four Mountains away at once, in one legal game action, without
    needing anything that destroys lands.
    """
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
            "Wastes",
        ],
    )
    scenario.will_choose_targets("bob", source="Valakut, the Molten Pinnacle")
    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Valakut, the Molten Pinnacle's triggered ability"], (
        "it did trigger"
    )

    # Dryad leaves; CR 604.2 ends its continuous effect with it, so every land
    # stops being a Mountain - Valakut prints no Mountain subtype of its own.
    dryad = scenario.find("Dryad of the Ilysian Grove", Zone.BATTLEFIELD)
    scenario.game.put_into_graveyard(dryad)
    assert _mountains(scenario) == [], "nothing is a Mountain any more"

    scenario.resolve_top()

    assert scenario.player("bob").life == 20, "CR 608.2a removed it from the stack"
    assert scenario.game.stack == []


def test_the_intervening_if_still_true_on_resolution_deals_the_damage():
    """The control for the test above: the same sequence with the board left
    alone does deal the 3, so the previous test is measuring CR 608.2a and not
    a trigger that never worked."""
    scenario = _scenario(
        hand=["Forest"],
        battlefield=[
            "Dryad of the Ilysian Grove",
            "Valakut, the Molten Pinnacle",
            "Island",
            "Swamp",
            "Plains",
            "Wastes",
        ],
    )
    scenario.will_choose_targets("bob", source="Valakut, the Molten Pinnacle")
    scenario.play_land("Forest")
    scenario.game.put_triggers_on_stack()

    scenario.resolve_top()

    assert scenario.player("bob").life == 17


# --------------------------------------------------------------------------
# Valakut under Blood Moon
# --------------------------------------------------------------------------


def test_blood_moon_takes_valakuts_trigger_away_entirely():
    """Valakut is a nonbasic land, so Blood Moon's layer 4 setting effect
    (CR 613.1d) applies CR 305.7 to it: its subtype becomes Mountain and it
    loses every ability its rules text generated - the entry trigger among
    them. All that is left is the Mountain's intrinsic "{T}: Add {R}"
    (CR 305.6), which it happened to print anyway.

    So the card that wants a board full of Mountains is switched off by the
    card that makes a board full of Mountains, which is the joke worth pinning.
    """
    scenario = _scenario(
        hand=["Mountain"],
        battlefield=[
            "Blood Moon",
            "Valakut, the Molten Pinnacle",
            "Ancient Tomb",
            "Ancient Tomb",
            "Ancient Tomb",
            "Ancient Tomb",
            "Ancient Tomb",
        ],
    )
    valakut = _valakut(scenario)
    characteristics = scenario.game.characteristics_of(valakut)
    assert set(characteristics.subtypes) == {"Mountain"}
    assert set(characteristics.abilities) == {"{T}: Add {R}."}
    assert len(_mountains(scenario)) == 6, "every nonbasic land is one, the count is met"

    scenario.play_land("Mountain")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == [], "the trigger is not there to fire"

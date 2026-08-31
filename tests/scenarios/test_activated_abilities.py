"""CR 602: activating an ability, paying for it, and what does not use the stack.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file.

- **CR 602.2** - "To activate an ability is to put it onto the stack and pay its
  costs, so that it will eventually resolve and have its effect."
- **CR 602.1a** - the activation cost is everything before the colon.
- **CR 602.5 / 602.5b** - a player cannot begin to activate a prohibited ability,
  and "Activate only once each turn" is such a prohibition.
- **CR 605.1a / 605.3b** - a mana ability does not use the stack at all: it
  "can't be targeted, countered, or otherwise responded to. Rather, it resolves
  immediately after it is activated."
- **CR 118.3** - a player cannot pay a cost without the resources to pay it in
  full, which is checked before anything is spent.
- **CR 608.2n** - the ability is removed from the stack as it finishes resolving.

The triggered half is in `test_triggered_abilities.py`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _rites_board(sacrificial: str = "Grizzly Bears", swamps: int = 2) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Forest"],
            battlefield=[
                "Vampiric Rites",
                *(["Swamp"] * swamps),
                *([sacrificial] if sacrificial else []),
            ],
        )
        .player("bob", library=["Forest"])
        .build()
    )


# -- the stack (CR 602.2, 405.1) ------------------------------------------


def test_activating_puts_the_ability_on_the_stack():
    """Vampiric Rites: `{1}{B}, Sacrifice a creature: You gain 1 life and draw a card.`

    CR 602.2 puts the ability on the stack; CR 405.1 gives it no card behind it.
    The cost is paid on activation, so the creature is already gone while the
    ability is still waiting to resolve.
    """
    scenario = _rites_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    ability = scenario.activate(rites, *swamps, sacrificing=[bears])

    assert isinstance(ability, AbilityOnStack)
    assert scenario.stack_names() == ["Vampiric Rites's activated ability"]
    assert bears.zone is Zone.GRAVEYARD, "CR 602.2b: the cost is paid on activation"
    assert scenario.player("alice").life == 20, "the effect has not happened yet"


def test_the_ability_resolves_and_does_what_it_says():
    scenario = _rites_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    hand_before = len(scenario.player("alice").hand)

    scenario.activate(rites, *swamps, sacrificing=[bears])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21
    assert len(scenario.player("alice").hand) == hand_before + 1
    assert scenario.game.stack_is_empty, "CR 608.2n: it is removed and ceases to exist"


def test_an_activated_ability_can_be_responded_to():
    """CR 117.7: an ability on the stack is an ordinary object to respond to.

    A spell cast while the ability waits goes above it and resolves first. Note
    that a Bolt cannot be aimed at the Vampiric Rites at all - "any target" is a
    creature, planeswalker, battle, or player (CR 115.1) - so the response here
    goes at alice's face instead, and the ability resolves afterwards either way.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Forest"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", library=["Forest"], hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    scenario.activate(rites, *swamps, sacrificing=[bears])
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.stack_names() == ["Vampiric Rites's activated ability", "Lightning Bolt"]

    scenario.pass_until_resolved()  # the Bolt resolves first
    assert scenario.player("alice").life == 17

    scenario.pass_until_resolved()  # then the ability
    assert scenario.player("alice").life == 18


# -- costs that cannot be paid (CR 118.3, 602.5) --------------------------


def test_an_ability_whose_cost_cannot_be_paid_is_not_activated():
    """No creature to sacrifice, so the cost cannot be paid in full (CR 118.3).

    Nothing is spent and nothing goes on the stack: CR 601.2h and CR 118.3 check
    the whole cost before any of it is paid, so the two Swamps that were tapped
    for mana are the only trace, and the mana is still in the payment's pool.
    """
    scenario = _rites_board(sacrificial="")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.activate(rites, *swamps)

    assert scenario.game.stack_is_empty
    assert scenario.player("alice").life == 20


def test_a_cost_short_on_mana_is_refused_too():
    """One Swamp cannot pay `{1}{B}` (CR 118.3, 601.2h)."""
    scenario = _rites_board(swamps=1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    with pytest.raises(ValueError, match="cannot pay"):
        scenario.activate(rites, swamp, sacrificing=[bears])

    assert scenario.game.stack_is_empty
    assert bears.zone is Zone.BATTLEFIELD, "nothing was spent"


def test_sacrificing_a_creature_to_a_cost_still_fires_its_dies_trigger():
    """CR 700.4: sacrificed is put into a graveyard from the battlefield, so it dies.

    The trigger waits until a player would receive priority (CR 603.3), which is
    after the activation is complete - so the dies trigger ends up *above* the
    ability it paid for, and resolves first.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Lightning Bolt", "Forest", "Island"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Solemn Simulacrum"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")
    solemn = scenario.creature("Solemn Simulacrum", "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    scenario.activate(rites, *swamps, sacrificing=[solemn])

    assert scenario.stack_names() == [
        "Vampiric Rites's activated ability",
        "Solemn Simulacrum's triggered ability",
    ]
    assert solemn.zone is Zone.GRAVEYARD


# -- activation restrictions (CR 602.5b) ----------------------------------


def test_activate_only_once_each_turn_refuses_the_second_activation():
    """Basking Rootwalla: `{1}{G}: ... Activate only once each turn.`

    CR 602.5: "A player can't begin to activate an ability that's prohibited from
    being activated", and CR 602.5b names this exact restriction. The parser puts
    the sentence in `ActivatedAbility.instructions`; this is the runtime honouring
    it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Basking Rootwalla", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = scenario.creature("Basking Rootwalla", "alice")

    first = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(rootwalla, *first)
    assert scenario.why_cannot_activate(rootwalla) == (
        "Basking Rootwalla's ability has already been activated this turn"
    )

    second = scenario.untapped_sources("Forest", "Forest")
    with pytest.raises(ValueError, match="already been activated this turn"):
        scenario.activate(rootwalla, *second)


def test_the_restriction_lifts_on_the_next_turn():
    """ "once each turn" is per turn, so a new turn allows it again (CR 602.5b)."""
    scenario = (
        Scenario()
        .player(
            "alice", library=["Forest"] * 5, battlefield=["Basking Rootwalla", "Forest", "Forest"]
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rootwalla = scenario.creature("Basking Rootwalla", "alice")
    scenario.activate(rootwalla, *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()

    while scenario.turn.turn_number == 1 or scenario.turn.active_player != "alice":
        scenario.advance()

    assert scenario.why_cannot_activate(rootwalla) is None


def test_a_summoning_sick_creature_cannot_activate_a_tap_ability():
    """CR 602.5a, 302.6: a `{T}` cost needs the creature to have been here.

    Llanowar Elves' ability is a mana ability, so this is also the check that
    the prohibition is applied before the mana-ability shortcut, not after.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Llanowar Elves"], battlefield=["Forest"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Llanowar Elves", forest)
    elves = scenario.creature("Llanowar Elves", "alice")

    assert elves.summoning_sick
    reason = scenario.why_cannot_activate(elves)
    assert reason is not None and "most recent turn began" in reason


# -- mana abilities do not use the stack (CR 605.1a, 605.3b) --------------


def test_a_mana_ability_with_a_sacrifice_cost_never_uses_the_stack():
    """Skirk Prospector: `Sacrifice a Goblin: Add {R}.`

    CR 605.1a makes this a mana ability - no target, it could add mana, it is not
    a loyalty ability - even though its cost is not `{T}`. CR 605.3b: it "doesn't
    go on the stack, so it can't be targeted, countered, or otherwise responded
    to. Rather, it resolves immediately after it is activated."

    `parse_mana_abilities` still does not see it, because that parser only reads
    `{T}: Add ...`; the activation path reads the parsed activated ability's
    `mana` instead, which is why this works at all.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Skirk Prospector", "Raging Goblin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prospector = scenario.creature("Skirk Prospector", "alice")
    goblin = scenario.creature("Raging Goblin", "alice")

    ability = scenario.activate(prospector, sacrificing=[goblin])

    assert ability is None, "a mana ability produces no object on the stack"
    assert scenario.game.stack_is_empty
    assert goblin.zone is Zone.GRAVEYARD
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1


def test_a_mana_ability_can_sacrifice_the_permanent_that_has_it():
    """Skirk Prospector is itself a Goblin, so it can eat itself for mana.

    CR 113.7a again: the cost is paid on activation and the ability resolves
    immediately, so a source that sacrificed itself still produces the mana.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Skirk Prospector"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    prospector = scenario.creature("Skirk Prospector", "alice")

    assert scenario.activate(prospector, sacrificing=[prospector]) is None
    assert prospector.zone is Zone.GRAVEYARD
    assert scenario.player("alice").mana_pool.floating.get(Color.RED) == 1
    assert scenario.game.stack_is_empty


def test_a_mana_ability_whose_cost_mills_a_card_does_not_take_the_no_stack_path():
    """Millikin: `{T}, Mill a card: Add {C}.` is not a mana ability (CR 605.1a).

    The 2026-08-19 release gave CR 605.1a a fourth criterion: "its cost and
    effect don't move any card to or from a library". A mill cost moves a card
    out of one, so the ability "doesn't go on the stack" is false of it (CR
    605.5: "Abilities that don't meet the criteria specified in rules
    605.1a-b ... aren't mana abilities") and it resolves as an ordinary
    activated ability - targetable, counterable, and producing its mana only
    when it resolves.

    The criteria are evaluated on the printed text - CR 605.1a: "Do not take
    into account replacement effects that may apply, other than
    self-replacement effects, when evaluating these criteria" - so no
    replacement is consulted anywhere in the decision.

    **The announcement is the reachable boundary.** The full activation cannot
    be driven yet: "Mill a card" parses as a cost the engine has no reader for,
    which the xfail below records. Classification happens before payment is a
    problem - `activate_ability` is the half of CR 602.2 that produces the
    object on the stack - so this test drives that half alone and asserts what
    it classifies as.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Island"], battlefield=["Millikin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    millikin = scenario.find("Millikin", Zone.BATTLEFIELD)

    ability = scenario.game.activate_ability(millikin)

    assert ability is not None, "a mill-cost ability is not a mana ability (CR 605.1a)"
    assert ability.kind is AbilityKind.ACTIVATED
    assert not scenario.game.stack_is_empty


def test_activating_millikin_pays_its_mill_cost():
    """The whole path: announce `{T}, Mill a card: Add {C}.` and pay it (CR 602.2).

    Millikin's ability is an ordinary activated ability (CR 605.1a's fourth
    criterion - the test above), so activating it announces the ability, opens
    payment, and pays a {T} component and a mill component (CR 601.2h).

    CR 701.17a is the mill: "For a player to mill a number of cards, that
    player puts that many cards from the top of their library into their
    graveyard." CR 601.2h's second sentence is why it is the *last* part of the
    cost paid - "Then they pay all remaining costs in any order", the remaining
    ones being those that move objects from a library to a public zone.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Island"], battlefield=["Millikin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    millikin = scenario.find("Millikin", Zone.BATTLEFIELD)

    ability = scenario.activate(millikin)

    assert ability is not None
    assert scenario.find("Forest", Zone.GRAVEYARD) is not None, "the mill cost moved a card"
    assert millikin.tapped


def test_an_empty_library_refuses_millikins_mill_cost_rather_than_milling_fewer():
    """CR 701.17b: "A player can't mill a number of cards greater than the
    number of cards in their library. **If given the choice to do so, they
    can't choose to take that action.** If instructed to do so, they mill as
    many as possible."

    Choosing to pay a cost is the first sentence's choice, not the second's
    instruction, so an empty library does not mill zero and let the ability
    through - it refuses the payment, and CR 118.3's whole-cost check means
    nothing else is spent either: Millikin stays untapped.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Millikin"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    millikin = scenario.find("Millikin", Zone.BATTLEFIELD)

    with pytest.raises(ValueError, match="cannot mill 1 card"):
        scenario.activate(millikin)

    assert millikin.untapped
    assert scenario.game.stack_is_empty


def test_a_plain_tap_add_ability_still_takes_the_no_stack_path():
    """Llanowar Elves: `{T}: Add {G}.` meets all four of CR 605.1a's criteria -
    no target, mana when it resolves, no loyalty symbol, and nothing in the
    printed cost or effect moves a library card - so CR 605.3b still applies.

    This is the guard against the new fourth criterion eating abilities it
    must not: the printed text names no library movement, and the ability
    resolves immediately as before.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Llanowar Elves"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    ability = scenario.activate(elves)

    assert ability is None, "a mana ability produces no object on the stack"
    assert scenario.game.stack_is_empty
    assert scenario.player("alice").mana_pool.floating.get(Color.GREEN) == 1


def test_an_ability_may_only_be_activated_by_the_permanents_controller():
    """CR 602.2: "Only an object's controller ... may activate its ability.\""""
    scenario = _rites_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.creature("Vampiric Rites", "alice")

    assert scenario.why_cannot_activate(rites, username="bob") == (
        "bob does not control Vampiric Rites"
    )

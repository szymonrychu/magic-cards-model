""" "You may sacrifice `<restriction>`. When you do, `<consequence>`." (CR
603.12), read off a card's own printed text with no per-card table row -
`_parse_reflexive_sacrifice_clause` in `machines/effects.py`.

**Grist, the Hunger Tide** is the primary vehicle: "-2: You may sacrifice a
creature. When you do, destroy target creature or planeswalker." Sacrifice
was already a modelled cost with a working `MAY` decision
(`_parse_conditional_sacrifice_clause`, CR 118.12); what this file exercises
is everything CR 603.12 adds on top of that, and CR 118.12 does not have:

- a **second, independent triggered ability**, created only once the
  sacrifice has actually happened;
- put on the stack **the next time a player would receive priority**
  (CR 603.3), which is a real object an opponent can respond to (CR 405.6a) -
  the whole reason "When you do" and "If you do" are not the same shape,
  however similar they read;
- its own target, chosen **when it goes on the stack** (CR 603.3d), not when
  the parent activates and not when the parent resolves.

Before this wave, reflexive triggered abilities did not exist in the model at
all: an ability with a "When you do" clause fell through to `parse_mixed_
effect`, found nothing it understood, and resolved doing nothing - silently,
the same shape every other `*Notice` in this codebase exists to catch.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 603.12** - "A resolving spell or ability may allow or instruct a
  player to take an action and create a triggered ability that triggers
  'when [a player] [does or doesn't]' take that action or 'when [something
  happens] this way.' These reflexive triggered abilities follow the rules
  for delayed triggered abilities (see rule 603.7), except that they're
  checked immediately after being created and trigger based on whether the
  trigger event or events occurred earlier during the resolution of the
  spell or ability that created them."
- **CR 405.6a** - "Effects don't go on the stack; they're the result of
  spells and abilities resolving. Effects may create delayed triggered
  abilities, however, and these may go on the stack when they trigger."
- **CR 603.3** - "Once an ability has triggered, its controller puts it on
  the stack ... the next time a player would receive priority."
- **CR 603.3d** - "The remainder of the process for putting a triggered
  ability on the stack is identical to the process for casting a spell
  listed in rules 601.2c-d." - targets are announced then, not earlier.
- **CR 608.2b** - "If the spell or ability specifies targets, it checks
  whether the targets are still legal ... Other changes to the game state
  may cause a target to no longer be legal." A spell or ability with every
  target illegal "doesn't resolve" - CR 608.2n still removes it from the
  stack.
- **CR 118.12** - the *different* family this shape is easily confused with:
  "[A player] may [do something]. If [that player] [does, doesn't, or
  can't], [effect]." No second object, no stack, no priority in between -
  `test_conditional_sacrifice_clauses.py`'s cards, and
  `test_an_if_you_do_card_still_has_no_separate_stack_object` below, are the
  regression guard that the two stay distinct.
- **CR 608.2d** - a resolving ability's "you may" cannot offer an impossible
  option: no creature to sacrifice makes "yes" illegal, not merely unwise.
- **CR 306.5b** - a planeswalker enters with a number of loyalty counters
  equal to its printed loyalty (Grist prints 3, so `-2` is affordable at once).
- **CR 510.1a** - lethal combat damage is not needed here, but Lightning
  Bolt's own 3 damage to Hill Giant's 3 toughness is what makes the
  "target dies in response" scenario below a state-based destruction
  (CR 704.5g), not something this file has to force by hand.

Guide of Souls and Ajani, Nacatl Avenger also print "When you do" clauses,
each a shape `_parse_reflexive_sacrifice_clause` alone cannot read - one is a
paid cost rather than a sacrifice, the other a mandatory action rather than a
"you may" - and a later wave (W4) generalised the dispatcher to cover both:

- **Guide of Souls** - "you may pay {E}{E}{E}. When you do, ..." -
  `_parse_reflexive_pay_energy_clause`, built on `DecisionKind.PAY_ENERGY`/
  `Game.may_pay_energy` (Static Prison's own primitive).
  `test_guide_of_souls_pays_energy_and_the_reflexive_ability_resolves` below
  is the happy path; `test_guide_of_souls_declining_the_energy_creates_no_
  trigger_and_spends_nothing` and `test_guide_of_souls_target_removed_in_
  response_fizzles_the_reflexive_ability` are its corner cases.
- **Ajani, Nacatl Avenger** - "Create a token. When you do, if you control a
  red permanent other than Ajani, he deals damage ..." -
  `_parse_reflexive_mandatory_token_clause`, CR 603.12's "instruct" half (no
  `MAY` decision at all) with CR 603.4's intervening *if* checked once,
  immediately after the token exists. `test_ajani_...` below covers both the
  condition holding and failing, driven through a real activation: a sibling
  wave taught CR 712's transform to reach `Game.activated_abilities`, so
  Ajani is transformed for real (CR 701.27a) and the `0` is activated the
  ordinary way, rather than this file building the back face's
  `AbilityOnStack` by hand the way it had to before that landed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

GUIDE = "Guide of Souls"
AJANI = "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger"

GRIST = "Grist, the Hunger Tide"


def grist_board() -> Scenario:
    """Alice with Grist (loyalty 3, CR 306.5b) and a creature to sacrifice;
    bob with a creature to destroy and the mana to answer on the stack."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[],
            library=["Forest"],
            battlefield=[GRIST, "Grizzly Bears"],
        )
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Mountain"],
            battlefield=["Hill Giant", "Mountain"],
        )
    )


def _activate_grist_minus_two(scenario: Scenario):
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")
    return scenario.activate(grist, index=1, username="alice")


# --------------------------------------------------------------------------
# Taking the sacrifice: a real, separate stack object (CR 603.12, 603.3)
# --------------------------------------------------------------------------


def test_taking_the_sacrifice_creates_a_second_stack_object():
    """Right after `-2` resolves, the reflexive ability is on the stack on its
    own - not folded into `-2`'s own resolution the way CR 118.12 would fold
    it - with `-2` already gone (CR 608.2n) and the sacrifice already done.
    """
    scenario = grist_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, source=GRIST)
    scenario.choose_trigger_targets(GRIST, [giant])

    _activate_grist_minus_two(scenario)
    scenario.pass_until_resolved()  # -2 itself: sacrifices, creates the reflexive ability

    assert bears.zone is Zone.GRAVEYARD, "the sacrifice already happened, inside -2's resolution"
    assert scenario.stack_names() == [f"{GRIST}'s triggered ability"], (
        "CR 603.12/603.3: a second, independent object - not part of -2 any more"
    )
    assert giant.zone is Zone.BATTLEFIELD, "the reflexive ability has not resolved yet"

    scenario.pass_until_resolved()  # the reflexive ability itself

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_declining_the_sacrifice_leaves_everything_untouched():
    """CR 608.2d: declining is legal. No sacrifice, no reflexive ability, no
    second object ever created."""
    scenario = grist_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(False, source=GRIST)

    _activate_grist_minus_two(scenario)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


def test_no_creature_to_sacrifice_makes_the_choice_illegal_not_merely_declined():
    """CR 608.2d: with nothing to sacrifice, "yes" is not a legal answer at
    all - `affirmative_is_legal` is False, not just unanswered. The question
    is still put (so a scenario can tell "nothing to decide" from "never
    asked"), and the unscripted default of "no" leaves the board alone."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[], library=["Forest"], battlefield=[GRIST])
        .player("bob", hand=[], library=["Mountain"], battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _activate_grist_minus_two(scenario)
    scenario.pass_until_resolved()

    from magic_cards_model.machines.decisions import DecisionKind

    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert len(asked) == 1
    assert asked[0].affirmative_is_legal is False
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


# --------------------------------------------------------------------------
# A real stack object: opponents get priority and may respond (CR 405.6a)
# --------------------------------------------------------------------------


def test_an_opponent_can_respond_to_the_reflexive_ability_on_the_stack():
    """CR 405.6a's whole point: bob answers with Lightning Bolt, aimed at
    alice, while the reflexive ability waits underneath - and CR 608 LIFO
    resolves the Bolt first, before Grist's own effect.

    If the reflexive ability were folded into `-2`'s own resolution (the
    CR 118.12 shape), there would be no stack object here at all for bob to
    respond to.
    """
    scenario = grist_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, source=GRIST)
    scenario.choose_trigger_targets(GRIST, [giant])

    _activate_grist_minus_two(scenario)
    scenario.pass_until_resolved()  # -2 resolves; the reflexive ability is now on top
    assert scenario.stack_names() == [f"{GRIST}'s triggered ability"]

    scenario.pass_priority("alice")  # CR 117.3c already gave it back; hand it to bob
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert alice.life == 17, "the Bolt resolved first (CR 608 LIFO)"
    assert scenario.stack_names() == [f"{GRIST}'s triggered ability"], (
        "the reflexive ability was merely responded to, not consumed"
    )
    assert giant.zone is Zone.BATTLEFIELD, "still waiting below the Bolt"

    scenario.pass_until_resolved()
    assert giant.zone is Zone.GRAVEYARD, "the reflexive ability resolves once the response clears"


def test_a_target_that_dies_in_response_fizzles_but_the_sacrifice_stays_paid():
    """CR 608.2b: bob kills his own Hill Giant in response (Lightning Bolt, 3
    damage, CR 704.5g) - the reflexive ability's only target is now illegal,
    so it does not resolve at all. The sacrifice already happened *inside*
    `-2`'s own resolution, long before the reflexive ability was even
    created, so there is no path back to un-sacrifice Grizzly Bears: CR 118.12
    would refund nothing here either, and CR 603.12 gives no more of a refund
    than that.
    """
    scenario = grist_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_take_the_may(True, source=GRIST)
    scenario.choose_trigger_targets(GRIST, [giant])

    _activate_grist_minus_two(scenario)
    scenario.pass_until_resolved()  # -2 resolves: sacrifice paid, reflexive ability created
    assert bears.zone is Zone.GRAVEYARD

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[giant])
    assert giant.zone is Zone.GRAVEYARD, "bob's own Bolt already dealt with it"

    scenario.pass_until_resolved()  # the reflexive ability: fizzles (CR 608.2b)

    assert scenario.stack_names() == []
    assert bears.zone is Zone.GRAVEYARD, "the cost stays paid - there is no refund on a fizzle"


# --------------------------------------------------------------------------
# CR 118.12 stays on its own, no-stack path
# --------------------------------------------------------------------------


def test_an_if_you_do_card_still_has_no_separate_stack_object():
    """Sanctum of Ugin's "you may sacrifice this land. If you do, search ..."
    (CR 118.12) resolves and is gone in the same breath - never a second
    stack object, unlike Grist's "When you do" just above. Full coverage of
    this card's own mechanics is `test_conditional_sacrifice_clauses.py`'s
    job; this is only the contrast this file's shape depends on staying true.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Devourer of Destiny"],
            battlefield=["Sanctum of Ugin"] + ["Wastes"] * 7,
            library=["Thought-Knot Seer"],
        )
        .player("bob", library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Sanctum of Ugin")

    scenario.cast_onto_stack("Devourer of Destiny", *scenario.untapped_sources(*(["Wastes"] * 7)))
    scenario.game.put_triggers_on_stack()
    before = len(scenario.game.stack)

    scenario.resolve_top()  # the cast trigger: sacrifices Sanctum and searches, in one breath

    assert len(scenario.game.stack) == before - 1, (
        "CR 118.12: resolving the trigger removed exactly one object (itself, "
        "CR 608.2n) and created no second one - unlike CR 603.12's Grist above"
    )


# --------------------------------------------------------------------------
# Guide of Souls: a non-sacrifice paid cost (CR 107.14, CR 118.3, CR 603.12)
# --------------------------------------------------------------------------


def _guide_board(energy: int = 3) -> "Scenario":
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GUIDE, "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, energy)
    return scenario


def test_guide_of_souls_pays_energy_and_the_reflexive_ability_resolves():
    """Paying {E}{E}{E} creates a second, independent stack object (CR
    603.12, same as Grist above), and its own consequence - two +1/+1
    counters, a flying counter (CR 122.1b), and "becomes an Angel in
    addition to its other types" (layer 4, CR 613.1d, no stated duration so
    it lasts for as long as the permanent exists, CR 611.2c) - runs once
    *that* ability resolves, not before.
    """
    scenario = _guide_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()  # the outer "Whenever you attack" trigger only
    # CR 603.3d: queued *after* the outer trigger's own batch, which shares
    # Guide's name and would otherwise consume-and-discard this answer before
    # the reflexive ability - not created until the outer trigger resolves,
    # below - ever exists to ask for it (`Game.put_triggers_on_stack`'s own
    # docstring: "consumed by this one batch and no other").
    scenario.choose_trigger_targets(GUIDE, [bears])
    scenario.will_pay_the_energy(True, source=GUIDE)
    scenario.resolve_top()  # "Whenever you attack": pays energy, creates the reflexive ability

    assert scenario.player("alice").energy == 0
    assert scenario.stack_names() == [f"{GUIDE}'s triggered ability"]
    assert scenario.game.reflexive_clause_notices == []

    scenario.resolve_top()  # the reflexive ability itself

    assert bears.counters[Counter.PLUS_ONE] == 2
    assert bears.counters["flying"] == 1
    assert "Angel" in scenario.game.characteristics_of(bears).subtypes
    from magic_cards_model.models.card import Type

    assert Type.CREATURE in scenario.game.characteristics_of(bears).types, (
        "additive (CR 205.1b): still a Bear, now an Angel too"
    )

    from magic_cards_model.machines.combat import Keyword, has_keyword

    assert has_keyword(bears, Keyword.FLYING, scenario.game), "CR 122.1b: the counter grants it"


def test_guide_of_souls_declining_the_energy_creates_no_trigger_and_spends_nothing():
    """CR 608.2d: declining is legal - no energy spent, no reflexive ability,
    no second stack object, the same shape Grist's own decline test proves."""
    scenario = _guide_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.will_pay_the_energy(False, source=GUIDE)
    scenario.resolve_top()

    assert scenario.player("alice").energy == 3
    assert bears.counters.as_dict() == {}
    assert scenario.stack_names() == []


def test_guide_of_souls_target_removed_in_response_fizzles_the_reflexive_ability():
    """CR 608.2b: bob's Lightning Bolt kills the chosen attacker in response.
    The energy stays spent - there is no path back to refund a cost, the same
    "no refund on a fizzle" rule `test_a_target_that_dies_in_response_
    fizzles_but_the_sacrifice_stays_paid` proves for Grist's sacrifice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GUIDE, "Raging Goblin"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 3)
    goblin = scenario.creature("Raging Goblin", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(goblin)
    scenario.game.put_triggers_on_stack()
    scenario.will_pay_the_energy(True, source=GUIDE)
    scenario.resolve_top()
    scenario.choose_trigger_targets(GUIDE, [goblin])

    assert scenario.player("alice").energy == 0

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[goblin])
    assert goblin.zone is Zone.GRAVEYARD

    scenario.pass_until_resolved()  # the reflexive ability: fizzles (CR 608.2b)

    assert scenario.stack_names() == []
    assert scenario.player("alice").energy == 0, "the cost stays paid - there is no refund"


# --------------------------------------------------------------------------
# Ajani, Nacatl Avenger: a mandatory action with a nested intervening if
# (CR 603.4, CR 603.12)
# --------------------------------------------------------------------------


def _ajani_activated_zero_ability(scenario: "Scenario"):
    """Driven through a real activation now that CR 712's transform reaches
    characteristics: Ajani is transformed (CR 701.27a), which makes him the
    planeswalker Ajani, Nacatl Avenger with that face's loyalty abilities and
    only those (CR 712.8e, CR 109.3), and the `0` is activated through the
    ordinary path - `Game.activated_abilities` now reads the up face, so this
    no longer needs the hand-built `AbilityOnStack` this file used before that
    landed.
    """
    # CR 201.1: an untransformed double-faced permanent has only the front
    # face's name ("Ajani, Nacatl Pariah") - `machines/triggers.py`'s own name
    # fix, unrelated to this file.
    ajani = scenario.find("Ajani, Nacatl Pariah", Zone.BATTLEFIELD, "alice")
    ajani.transform()  # CR 701.27a
    ajani.add_counters(Counter.LOYALTY, 3)  # CR 306.5b, as if he had entered so
    zero_ability = scenario.game.activated_abilities(ajani)[1]
    assert zero_ability.cost == "0"
    scenario.activate(ajani, index=1)
    return ajani


def test_ajani_deals_damage_when_the_intervening_if_holds():
    """A red permanent other than Ajani (Raging Goblin) makes CR 603.4's
    condition true - checked once, immediately after the mandatory token
    exists (CR 603.12) - so the reflexive ability is created and, once it
    resolves, deals damage equal to the number of creatures alice controls
    to whatever it targets. Transformed Ajani is a planeswalker, not a
    creature (CR 712.8e, CR 109.3), so that count is the goblin and the
    fresh token - two, not three - the same characteristic-boundary case
    the CR 712 transform wave's own fix makes visible here.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[AJANI, "Raging Goblin"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    ajani = _ajani_activated_zero_ability(scenario)
    # CR 603.3d: queued ahead of time - `resolve_top` below both resolves the
    # "0" ability and (CR 603.3, `Game._before_priority`) puts the reflexive
    # ability it creates on the stack in the same call, asking its target then.
    scenario.choose_trigger_targets(ajani.name, ["bob"])
    scenario.resolve_top()  # "0": creates the token, checks the if, creates the reflexive ability

    tokens = [state for state in scenario.game.battlefield if state.name == "Cat Warrior Token"]
    assert len(tokens) == 1
    assert scenario.game.reflexive_clause_notices == []
    assert scenario.stack_names() == [f"{ajani.name}'s triggered ability"]

    scenario.resolve_top()  # the reflexive ability itself

    assert bob.life == 18, (
        "2 creatures: Raging Goblin and the fresh token - Ajani is a planeswalker"
    )


def test_ajani_creates_no_reflexive_ability_when_the_intervening_if_fails():
    """With no other red permanent, CR 603.4's condition is false the moment
    it is checked - the token is still created (CR 603.12's "instruct" half
    has no `MAY` to decline), but no reflexive ability, no stack object, and
    no damage follow it, rather than a reflexive ability that resolves and
    silently does nothing.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[AJANI])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    _ajani_activated_zero_ability(scenario)
    scenario.resolve_top()

    tokens = [state for state in scenario.game.battlefield if state.name == "Cat Warrior Token"]
    assert len(tokens) == 1, "CR 603.12: the mandatory action still happens"
    assert scenario.game.reflexive_clause_notices == []
    assert not scenario.game.pending_triggers
    assert scenario.stack_names() == []
    assert bob.life == 20


def test_one_or_more_then_that_many_carries_the_sacrificed_count():
    """Swashbuckler Extraordinaire: "Whenever you attack, you may sacrifice
    one or more Treasures. When you do, up to that many target creatures gain
    double strike until end of turn." One Treasure sacrificed is a reflexive
    ability allowing up to one target (CR 603.12, the count carried into its
    text); the two-Treasure case is in `test_that_many_count_channel.py`."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swashbuckler Extraordinaire"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Swashbuckler Extraordinaire", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # "When this creature enters, create a Treasure token."
    treasures = [p for p in scenario.game.battlefield if p.name == "Treasure Token"]
    assert len(treasures) == 1
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_targets(bears, source="Swashbuckler Extraordinaire")
    scenario.resolve_top()

    assert treasures[0].zone is not Zone.BATTLEFIELD
    assert scenario.game.reflexive_clause_notices == []
    scenario.game.put_triggers_on_stack()
    (reflexive,) = scenario.game.stack
    assert reflexive.ability.text.startswith("up to 1 target creatures")

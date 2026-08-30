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
and both are deliberately **not** built out here:

- Guide of Souls' "you may pay {E}{E}{E}" is blocked on energy being
  gainable but not payable at all (no general may-pay-a-cost decision
  exists yet - see `docs/engine-coverage.md`). `test_guide_of_souls_...`
  below checks the *other* thing this wave fixes for it: the failure is now
  a recorded `ReflexiveClauseNotice`, not silence.
- Ajani, Nacatl Avenger's "Create a token. When you do, if ..., he deals
  damage ..." is a *mandatory* action (not "you may") with an intervening
  *if* (CR 603.4) nested inside the reflexive clause - a second missing
  primitive on top of the first. `test_ajani_...` below checks the same
  notice, not the intervening-if.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

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
# Silence must become a notice (Guide of Souls, Ajani, Nacatl Avenger)
# --------------------------------------------------------------------------


def test_guide_of_souls_attack_trigger_records_a_notice_instead_of_nothing():
    """ "Whenever you attack, you may pay {E}{E}{E}. When you do, ..." -
    paying energy is a missing primitive (`docs/engine-coverage.md`), so
    `_parse_reflexive_sacrifice_clause` cannot read this shape at all. Before
    this wave the trigger resolved and did nothing, with no trace anywhere;
    now `_unreadable_reflexive_clause` records why.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Guide of Souls", "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert len(scenario.game.reflexive_clause_notices) == 1
    notice = scenario.game.reflexive_clause_notices[0]
    assert notice.source_name == "Guide of Souls"
    assert "pay {E}{E}{E}" in notice.text
    assert scenario.stack_names() == [], "no reflexive ability was ever created"


def test_ajani_nacatl_avengers_mandatory_reflexive_clause_records_a_notice():
    """Avenger's "0: Create a 2/1 ... token. When you do, if you control a red
    permanent other than Ajani, he deals damage ... to any target." - a
    *mandatory* action (not "you may") with an intervening *if* (CR 603.4)
    nested in the reflexive clause, so `_parse_reflexive_sacrifice_clause`
    (which only reads "you may sacrifice ...") correctly refuses it too.

    Ajani cannot actually *activate* this ability through the ordinary path
    while front-face-up: CR 712.8d gives an untransformed double-faced
    permanent only its front face's characteristics, and this engine's own
    `Game._still_has_ability` (layer 6, CR 613.1f) already enforces that much
    - `game.begin_activating` correctly refuses it with "no longer has that
    ability". Transforming Ajani for real is a separate, already-documented
    gap (`test_double_faced_creature_characteristics.py`'s own docstring -
    "Nothing here reads `CardState.transformed` yet"), out of scope for this
    wave. So this test reaches resolution the way `Game._resolve_ability`
    would once that gap is closed: it builds the real `AbilityOnStack` for
    the back face's own printed "0:" ability directly and resolves it,
    exercising exactly the CR 603.12 parsing and notice this file is about
    without depending on CR 712 transform support existing yet.
    """
    from magic_cards_model.machines import AbilityKind, abilities_of_kind
    from magic_cards_model.machines.triggers import AbilityOnStack

    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Ajani, Nacatl Pariah // Ajani, Nacatl Avenger"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # CR 201.1: an untransformed double-faced permanent has only the front
    # face's name ("Ajani, Nacatl Pariah") - `machines/triggers.py`'s own name
    # fix, unrelated to this file.
    ajani = scenario.find("Ajani, Nacatl Pariah", Zone.BATTLEFIELD, "alice")
    zero_ability = abilities_of_kind(ajani.card, AbilityKind.ACTIVATED)[1]
    assert zero_ability.cost == "0"

    scenario.game.stack.append(
        AbilityOnStack(
            kind=AbilityKind.ACTIVATED,
            ability=zero_ability,
            source_id=ajani.id,
            source_name=ajani.name,
            controller="alice",
        )
    )
    scenario.resolve_top()

    assert len(scenario.game.reflexive_clause_notices) == 1
    notice = scenario.game.reflexive_clause_notices[0]
    assert "Create a 2/1" in notice.text
    assert "When you do" in notice.text

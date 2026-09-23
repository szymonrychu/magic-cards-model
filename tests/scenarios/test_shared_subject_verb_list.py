"""G7: a shared-subject verb list carries its subject across every item.

"`<SUBJ>` `<verb1>`[, `<verb2>`, ...][,] and `<verbN>`." is one CR 608.2c
instruction naming several actions for a single subject - Archon of
Cruelty's own trigger ("target opponent sacrifices a creature or
planeswalker of their choice, discards a card, and loses 3 life. You draw
a card and gain 3 life."). `_CLAUSE_SEPARATOR`'s own bare "and"/comma split
has no notion that a list like this shares one subject: split apart, only
the first fragment still carries it, and every later item arrives as an
orphaned bare verb phrase.

Before this reader existed, that orphaned fragment reached
`_parse_mixed_clause`'s own last resort, `_parse_optional_player_clause`,
whose generic "you " retry exists for a genuinely subjectless sentence
("You gain 2 life, draw two cards" - the subject really is "you"). That
retry has no memory of what the true subject actually was a clause back, so
for a sentence whose real subject was "each opponent" or "target opponent"
it silently ran the orphaned verb against the resolving ability's own
*controller* instead - a fail-open, not a miss: something ran, just against
the wrong player, with no notice. Arbiter of Woe (below) is the regression
proof this reader fixes: before it, "each opponent discards a card and
loses 2 life" cost its own *controller* 2 life instead of the opponent.

CR numbers looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 115.1** ("These targets are declared as part of the process of
  putting the spell or ability on the stack.") / **CR 115.1d** (a triggered
  ability's targets "are chosen as the ability is put on the stack"): the
  target is announced once, not once per verb, so every later item in the
  list refers to that identical player.
- **CR 608.2b**: a target is rechecked for legality when the spell or
  ability resolves, not re-announced - a player target essentially never
  becomes illegal mid-resolution (nothing between this ability's own
  clauses can remove a player from the game), so it stays legal even after
  a permanent it controlled is gone by the time the later verbs run.
- **CR 609.3**: "If an effect attempts to do something impossible, it does
  only as much as possible" - a player with nothing to sacrifice simply
  sacrifices nothing (CR 608.2d's own "no impossible choice"), and the
  list's other items still run.
- **CR 701.21a**: to sacrifice a permanent is to move it from the
  battlefield to its owner's graveyard, always the controller's own choice
  among what they control.
- **CR 101.4**: the "each opponent"/"each player" shape runs in APNAP
  order.

Archon of Cruelty is the reported card. Dusk Mangler ("each opponent
sacrifices a creature of their choice, discards a card, and loses 4 life.")
is the off-pool proof: the identical "each opponent" three-item shape as
Archon's own "target opponent" one, on an unrelated card, with a higher
count. Arbiter of Woe ("each opponent discards a card and loses 2 life.")
is the two-item shape with no comma at all, and the regression this reader
fixes.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# ---------------------------------------------------------------------------
# (a) Archon of Cruelty - target opponent sacrifices/discards/loses life,
#     while the controller draws and gains life. Both the ETB and the
#     attack trigger read the identical printed sentence.
# ---------------------------------------------------------------------------


def _archon_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice", hand=["Archon of Cruelty"], library=["Mountain"] * 3, battlefield=["Swamp"] * 8
        )
        .player(
            "bob",
            hand=["Island"],
            battlefield=["Grizzly Bears", "Elspeth, Sun's Champion"],
        )
    )


def test_archon_of_cruelty_etb_makes_bob_sacrifice_discard_and_lose_life():
    """Bob (the target) sacrifices a permanent of HIS OWN choice among the
    creature and the planeswalker, discards a card, and loses 3 life - all
    three verbs bound to the same targeted player. Alice (the controller,
    "you" in the second sentence) draws a card and gains 3 life - the
    identical shared-subject shape, with subject "you"."""
    scenario = _archon_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    elspeth = scenario.find("Elspeth, Sun's Champion", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 8), username="alice")
    scenario.choose_trigger_targets("Archon of Cruelty", ["bob"])
    scenario.will_choose_cards(bears, username="bob")
    scenario.will_discard(bob.hand[0], username="bob")
    bob_life_before = bob.life
    alice_life_before = alice.life
    alice_hand_before = len(alice.hand)

    scenario.cast_and_resolve("Archon of Cruelty", *sources, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "bob's own choice, not alice's"
    assert elspeth.zone is Zone.BATTLEFIELD
    assert bob.life == bob_life_before - 3
    assert bob.hand == []
    assert alice.life == alice_life_before + 3
    # -1 for Archon itself leaving alice's hand to be cast, +1 for the draw.
    assert len(alice.hand) == alice_hand_before


def test_archon_of_cruelties_attack_trigger_reads_the_same_sentence():
    """The attack half of "Whenever this creature enters or attacks, ..."
    is the identical printed sentence as the ETB half - it behaves the same
    way, proving the reader is keyed off the trigger's own effect text, not
    off which event fired it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", library=["Mountain"] * 3, battlefield=["Archon of Cruelty"] + ["Swamp"] * 8
        )
        .player("bob", hand=["Island"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    archon = scenario.find("Archon of Cruelty", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    bob_life_before = bob.life
    alice_life_before = alice.life
    alice_hand_before = len(alice.hand)

    scenario.choose_trigger_targets("Archon of Cruelty", ["bob"])
    scenario.will_discard(bob.hand[0], username="bob")
    scenario.attack_with(archon)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Archon of Cruelty's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "bob's only creature, no real choice to ask"
    assert bob.life == bob_life_before - 3
    assert bob.hand == []
    assert alice.life == alice_life_before + 3
    assert len(alice.hand) == alice_hand_before + 1


def test_bob_with_no_creature_or_planeswalker_still_discards_and_loses_life():
    """CR 609.3: nothing to sacrifice is not a reason to skip the rest of
    the list - the sacrifice item does as much as possible (nothing), and
    the discard and life-loss items still run against bob."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Archon of Cruelty"], library=["Mountain"] * 3, battlefield=["Swamp"] * 8
        )
        .player("bob", hand=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 8), username="alice")
    scenario.choose_trigger_targets("Archon of Cruelty", ["bob"])
    scenario.will_discard(bob.hand[0], username="bob")
    life_before = bob.life

    scenario.cast_and_resolve("Archon of Cruelty", *sources, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bob.life == life_before - 3
    assert bob.hand == []


def test_target_stays_legal_after_its_permanent_is_sacrificed_in_response():
    """CR 608.2b: bob (a player) stays a legal target even though the
    permanent he would have sacrificed to this same effect is already gone
    by the time the ability resolves - he still discards and loses life."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Archon of Cruelty"], library=["Mountain"] * 3, battlefield=["Swamp"] * 8
        )
        .player(
            "bob",
            hand=["Island", "Lightning Bolt"],
            battlefield=["Grizzly Bears", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*(["Swamp"] * 8), username="alice")
    scenario.choose_trigger_targets("Archon of Cruelty", ["bob"])
    scenario.will_discard(scenario.find("Island", Zone.HAND, "bob"), username="bob")
    life_before = bob.life

    casting = scenario.cast("Archon of Cruelty", "alice")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # Archon resolves and enters the battlefield.
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Archon of Cruelty's triggered ability"]
    # Bob sacrifices his own Grizzly Bears in response, outside the effect -
    # by the time the trigger resolves, there is nothing left to sacrifice.
    scenario.game.sacrifice(bears)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert bob.life == life_before - 3
    assert bob.hand == [scenario.find("Lightning Bolt", Zone.HAND, "bob")]


# ---------------------------------------------------------------------------
# (b) Dusk Mangler - "each opponent" instead of "target opponent": the same
#     three-item list, no target announcement at all (CR 115.10a).
#
# Dusk Mangler's own additional cost ("sacrifice a creature, discard a card,
# or pay 4 life") is a pre-existing, unrelated gap - a three-way alternative
# cost this engine's cost parser does not read at all (`docs/engine-
# coverage.md`), out of scope for this reader. `put_onto_battlefield` (CR
# 603.6d: an "enters the battlefield" trigger fires however the permanent
# got there) reaches the ETB trigger itself without going through the
# unrelated cost gap, the same way `test_player_exiles_from_own_graveyard.
# py`'s own `test_relics_second_ability_is_unchanged` reaches an ability
# the harness has no cost-driven path to.
# ---------------------------------------------------------------------------


def test_dusk_manglers_etb_each_opponent_sacrifices_discards_and_loses_four():
    scenario = (
        Scenario()
        .player("alice", hand=["Dusk Mangler"])
        .player("bob", hand=["Island"], battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_cards(bears, username="bob")
    scenario.will_discard(bob.hand[0], username="bob")
    life_before = bob.life

    scenario.put_onto_battlefield("Dusk Mangler", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Dusk Mangler's triggered ability"]
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "bob's own choice, not alice's"
    assert giant.zone is Zone.BATTLEFIELD
    assert bob.life == life_before - 4
    assert bob.hand == []


# ---------------------------------------------------------------------------
# (c) Arbiter of Woe - the regression test for the fail-open this reader
#     closes: "each opponent discards a card and loses 2 life" used to cost
#     the resolving ability's own controller 2 life, never the opponent.
# ---------------------------------------------------------------------------


def test_arbiter_of_woes_etb_costs_the_opponent_life_not_the_controller():
    scenario = (
        Scenario()
        .player("alice", hand=["Arbiter of Woe"], library=["Mountain"] * 3)
        .player("bob", hand=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    scenario.will_discard(bob.hand[0], username="bob")
    bob_life_before = bob.life
    alice_life_before = alice.life
    alice_hand_before = len(alice.hand)

    scenario.put_onto_battlefield("Arbiter of Woe", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Arbiter of Woe's triggered ability"]
    scenario.pass_until_resolved()

    assert bob.life == bob_life_before - 2, "the opponent, not alice, loses the 2 life"
    assert bob.hand == []
    assert alice.life == alice_life_before + 2, "alice's own separate 'you gain 2 life' sentence"
    # -1 for Arbiter of Woe itself leaving alice's hand, +1 for the draw.
    assert len(alice.hand) == alice_hand_before

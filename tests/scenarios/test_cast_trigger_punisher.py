"""The "punisher" cast-trigger template: "When you cast this spell, any
player may `<action>`. If a player does, counter `<this spell>`." - Dash
Hopes ("pay 5 life"), Temporal Extortion ("pay half their life, rounded
up"), Brain Gorgers ("sacrifice a creature of their choice"), and
Phantasmagorian ("discard three cards").

Every CR number below was looked up with `mise run rules:find <number>` in
the session that wrote this file.

- **CR 603.2** - a triggered ability triggers automatically when its trigger
  event occurs; **CR 601.2i** - "Any abilities that trigger when a spell is
  cast ... trigger at this time" - the moment the spell becomes cast, before
  it is put on the stack; **CR 113.6k** confirms the ability functions in
  every zone it can trigger from.
- **CR 101.4** - the APNAP order: the active player makes any choice
  required first, then each other player in turn order.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - a player who cannot pay/sacrifice/discard is not offered the
  choice at all.
- **CR 119.4 / CR 118.3** - a life payment is legal only down to zero, and a
  player can't pay a cost without the resources to pay it fully.
- **CR 107.1a** - a spell or ability that could generate a fractional number
  says whether to round up or down; Temporal Extortion says up.
- **CR 701.6a** - to counter a spell means to remove it from the stack; a
  countered spell goes to its owner's graveyard.

The Oracle rulings for all four cards (verified against Scryfall's own
rulings text for each, this session) read: "As the triggered ability
resolves, the active player gets the option to perform the action. If that
player declines, the next player in turn order gets the option. As soon as
any player performs the action, the spell is countered, but the remaining
players still get the option. If all players decline, the spell remains on
the stack." - so every player is asked, in APNAP order, every time, never
stopping early once someone has already paid: a later "yes" still pays its
own cost even though there is nothing left on the stack to counter (the
identical "still resolves as normal" shape Hope-Ender Coatl's own ruling
gives its own cast trigger once its target is already gone).

Brain Gorgers' and Phantasmagorian's own 2013-07-01 ruling is the CR 608.2d
proof: "A player can't choose to sacrifice a creature unless they actually
control a creature that can be sacrificed. For example, if the action were
'discard three cards,' a player with two or fewer cards in hand couldn't
take the option."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

# ---------------------------------------------------------------------------
# Dash Hopes: "any player may pay 5 life. If a player does, counter Dash
# Hopes." - the flat-life-amount shape, and the fullest APNAP/gone-before-
# resolution coverage, proved against a real Lightning Bolt targeting the
# same stack rather than an isolated no-op spell.
# ---------------------------------------------------------------------------


def _dash_hopes_board(*, alice_life: int = 20, bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=alice_life,
            hand=["Dash Hopes", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Mountain"],
        )
        .player("bob", life=bob_life)
    )


def test_nobody_pays_and_dash_hopes_resolves_and_counters_the_bolt():
    scenario = _dash_hopes_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bob])
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    dash_hopes = scenario.cast_onto_stack("Dash Hopes", *swamps, username="alice", targets=[bolt])

    scenario.will_pay_the_life(False, username="alice", source="Dash Hopes")
    scenario.will_pay_the_life(False, username="bob", source="Dash Hopes")

    scenario.resolve_top()  # Dash Hopes' own cast trigger: both decline

    assert scenario.stack_names() == ["Lightning Bolt", "Dash Hopes"]

    scenario.resolve_top()  # Dash Hopes resolves and counters the Bolt

    assert bolt.zone is Zone.GRAVEYARD
    assert dash_hopes.zone is Zone.GRAVEYARD
    assert bob.life == 20


def test_the_active_player_pays_and_counters_dash_hopes_letting_the_bolt_through():
    scenario = _dash_hopes_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bob])
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    dash_hopes = scenario.cast_onto_stack("Dash Hopes", *swamps, username="alice", targets=[bolt])

    scenario.will_pay_the_life(True, username="alice", source="Dash Hopes")
    scenario.will_pay_the_life(False, username="bob", source="Dash Hopes")

    scenario.resolve_top()  # alice (active player, CR 101.4) is asked first

    assert alice.life == 15
    assert dash_hopes.zone is Zone.GRAVEYARD, "countered - CR 701.6a"
    assert scenario.stack_names() == ["Lightning Bolt"]

    scenario.resolve_top()  # the Bolt, no longer countered, resolves normally

    assert bob.life == 17


def test_a_later_player_pays_after_the_active_player_declines():
    scenario = _dash_hopes_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bob])
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    dash_hopes = scenario.cast_onto_stack("Dash Hopes", *swamps, username="alice", targets=[bolt])

    scenario.will_pay_the_life(False, username="alice", source="Dash Hopes")
    scenario.will_pay_the_life(True, username="bob", source="Dash Hopes")

    scenario.resolve_top()  # alice declines, then bob (CR 101.4's next player) pays

    assert alice.life == 20
    assert bob.life == 15
    assert dash_hopes.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_a_player_below_the_life_cost_cannot_choose_to_pay():
    """CR 608.2d/CR 119.4: 4 life cannot pay 5 - bob is offered no such
    option at all, unlike a merely unwise "no"."""
    scenario = _dash_hopes_board(bob_life=4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bob])
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Dash Hopes", *swamps, username="alice", targets=[bolt])

    scenario.will_pay_the_life(False, username="alice", source="Dash Hopes")
    # bob is left unscripted: the only legal answer is "no" (CR 608.2d), and
    # the unscripted default takes exactly that legal option.

    scenario.resolve_top()

    (bob_question,) = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.PAY_LIFE and question.player == "bob"
    ]
    assert not bob_question.affirmative_is_legal
    assert bob.life == 4
    assert scenario.stack_names() == ["Lightning Bolt", "Dash Hopes"]


def test_dash_hopes_countered_before_its_own_trigger_resolves_still_asks_normally():
    """CR 603.3: the trigger sits *above* Dash Hopes on the stack, so a
    second counterspell can answer Dash Hopes itself while the trigger is
    still waiting - and, per Hope-Ender Coatl's own ruling for the identical
    shape, the trigger still resolves as normal even though there is nothing
    left to counter by the time it does."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dash Hopes", "Lightning Bolt"],
            battlefield=["Swamp", "Swamp", "Mountain"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[bob])
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    dash_hopes = scenario.cast_onto_stack("Dash Hopes", *swamps, username="alice", targets=[bolt])
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Dash Hopes",
        "Dash Hopes's triggered ability",
    ]
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[dash_hopes])

    scenario.resolve_top()  # Counterspell counters Dash Hopes first

    assert dash_hopes.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == ["Lightning Bolt", "Dash Hopes's triggered ability"]

    scenario.will_pay_the_life(False, username="alice", source="Dash Hopes")
    scenario.will_pay_the_life(True, username="bob", source="Dash Hopes")

    scenario.resolve_top()  # the trigger still resolves; nothing left to counter

    assert bob.life == 15, "bob's payment still happened - CR 608.2d is a real choice either way"
    assert dash_hopes.zone is Zone.GRAVEYARD, "still gone, from Counterspell - never double-moved"
    assert scenario.stack_names() == ["Lightning Bolt"]

    scenario.resolve_top()

    assert bob.life == 12


# ---------------------------------------------------------------------------
# Temporal Extortion: "any player may pay half their life, rounded up." -
# CR 107.1a's rounding direction, computed fresh off each player's own
# current life total rather than a flat amount.
# ---------------------------------------------------------------------------


def _temporal_extortion_board(*, alice_life: int = 15, bob_life: int = 20) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            life=alice_life,
            hand=["Temporal Extortion"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", life=bob_life)
    )


def test_paying_half_life_rounded_up_counters_temporal_extortion():
    """15 life halved is 7.5, rounded up (CR 107.1a) to 8."""
    scenario = _temporal_extortion_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Temporal Extortion", *swamps, username="alice")

    scenario.will_pay_the_life(True, username="alice", source="Temporal Extortion")
    scenario.will_pay_the_life(False, username="bob", source="Temporal Extortion")

    scenario.resolve_top()

    assert alice.life == 7
    assert scenario.stack_names() == [], "countered before it ever got to resolve"


def test_declining_leaves_temporal_extortion_on_the_stack():
    scenario = _temporal_extortion_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Temporal Extortion", *swamps, username="alice")

    scenario.will_pay_the_life(False, username="alice", source="Temporal Extortion")
    scenario.will_pay_the_life(False, username="bob", source="Temporal Extortion")

    scenario.resolve_top()

    assert scenario.stack_names() == ["Temporal Extortion"]
    assert alice.life == 15
    assert bob.life == 20


def test_half_life_rounded_up_is_always_payable_even_at_one_life():
    """CR 119.4b: players can always pay 0 life, and half of any life total
    rounded up is never more than that total - unlike Dash Hopes' flat 5,
    nobody is ever unable to choose this action."""
    scenario = _temporal_extortion_board(alice_life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Temporal Extortion", *swamps, username="alice")

    scenario.will_pay_the_life(True, username="alice", source="Temporal Extortion")
    scenario.will_pay_the_life(False, username="bob", source="Temporal Extortion")

    scenario.resolve_top()

    (alice_question,) = [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.PAY_LIFE and question.player == "alice"
    ]
    assert alice_question.affirmative_is_legal
    assert alice.life == 0
    assert scenario.stack_names() == []


# ---------------------------------------------------------------------------
# Brain Gorgers: "any player may sacrifice a creature of their choice." -
# reuses `_sacrifice_of_choice_clause_effect` (CR 701.21a).
# ---------------------------------------------------------------------------


def test_a_player_with_a_creature_may_sacrifice_it_to_counter_brain_gorgers():
    scenario = (
        Scenario()
        .player("alice", hand=["Brain Gorgers"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    brain_gorgers = scenario.cast_onto_stack("Brain Gorgers", *swamps, username="alice")

    # alice controls no creature at all - CR 608.2d offers her nothing, so
    # she is never even asked (no script needed for her).
    scenario.will_take_the_may(True, username="bob", source="Brain Gorgers")

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert brain_gorgers.zone is Zone.GRAVEYARD
    assert [q for q in scenario.questions_asked() if q.player == "alice"] == []


def test_a_player_with_no_creature_cannot_choose_to_sacrifice_one():
    """CR 608.2d/2013-07-01 ruling: bob controls no creature, so he is never
    offered the choice, and Brain Gorgers resolves onto the battlefield."""
    scenario = (
        Scenario()
        .player("alice", hand=["Brain Gorgers"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Brain Gorgers", *swamps, username="alice")

    scenario.resolve_top()  # nobody is asked anything at all
    scenario.resolve_top()  # Brain Gorgers itself resolves, uncountered

    assert scenario.questions_asked() == []
    assert "Brain Gorgers" in scenario.battlefield_names()


def test_declining_to_sacrifice_lets_brain_gorgers_resolve():
    scenario = (
        Scenario()
        .player("alice", hand=["Brain Gorgers"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.cast_onto_stack("Brain Gorgers", *swamps, username="alice")

    scenario.will_take_the_may(False, username="bob", source="Brain Gorgers")

    scenario.resolve_top()
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
    assert "Brain Gorgers" in scenario.battlefield_names()


# ---------------------------------------------------------------------------
# Phantasmagorian: "any player may discard three cards." - reuses
# `_discard_cards` (CR 701.9a/701.9b).
# ---------------------------------------------------------------------------


def test_a_player_with_enough_cards_may_discard_three_to_counter_phantasmagorian():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Phantasmagorian"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Grizzly Bears", "Shock", "Memnite", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bears = scenario.find("Grizzly Bears", Zone.HAND, "bob")
    shock = scenario.find("Shock", Zone.HAND, "bob")
    memnite = scenario.find("Memnite", Zone.HAND, "bob")
    swamps = scenario.untapped_sources(*(["Swamp"] * 7), username="alice")
    phantasmagorian = scenario.cast_onto_stack("Phantasmagorian", *swamps, username="alice")

    # alice's hand is empty after casting - never offered the choice at all.
    scenario.will_take_the_may(True, username="bob", source="Phantasmagorian")
    scenario.will_choose_cards(bears, shock, memnite, username="bob", source="Phantasmagorian")

    scenario.resolve_top()

    assert [state.name for state in bob.hand] == ["Watchwolf"]
    assert phantasmagorian.zone is Zone.GRAVEYARD
    assert "Phantasmagorian" not in scenario.battlefield_names()
    assert [q for q in scenario.questions_asked() if q.player == "alice"] == []


def test_a_player_with_fewer_than_three_cards_cannot_choose_to_discard():
    """The 2013-07-01 ruling's own example: two (or fewer) cards in hand
    cannot pay the "discard three cards" action, so bob is never asked."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Phantasmagorian"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Grizzly Bears", "Shock"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    swamps = scenario.untapped_sources(*(["Swamp"] * 7), username="alice")
    scenario.cast_onto_stack("Phantasmagorian", *swamps, username="alice")

    scenario.resolve_top()
    scenario.resolve_top()

    assert scenario.questions_asked() == []
    assert len(bob.hand) == 2
    assert "Phantasmagorian" in scenario.battlefield_names()


def test_declining_to_discard_lets_phantasmagorian_resolve():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Phantasmagorian"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Grizzly Bears", "Shock", "Memnite", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    swamps = scenario.untapped_sources(*(["Swamp"] * 7), username="alice")
    scenario.cast_onto_stack("Phantasmagorian", *swamps, username="alice")

    scenario.will_take_the_may(False, username="bob", source="Phantasmagorian")

    scenario.resolve_top()
    scenario.resolve_top()

    assert len(bob.hand) == 4
    assert "Phantasmagorian" in scenario.battlefield_names()

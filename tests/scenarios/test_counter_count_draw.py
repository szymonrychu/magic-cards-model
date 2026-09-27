"""One clause defining two things at once (CR 608.2c): "At the beginning of
combat on your turn, put a +1/+1 counter on <this>. Then <clause>, where X is
the number of counters on <this>." - Savanti Romero, Time's Exile's own "you
draw X cards and lose X life".

The trigger condition itself, "At the beginning of combat on your turn", is
already generic (Agent Bishop, Man in Black and Old Hob, Alleycat Blues both
already print it and are already `handled`); this file is only about the
resolution `machines/counter_payoffs._put_counter_then_x_clause_where_x_is_
counters_on_self` reads.

Spider-Man Noir is the off-pool generality proof, on every axis that
matters: a different trigger condition ("attacks alone" rather than "beginning
of combat"), a different `<clause>` ("surveil X" rather than "draw X cards and
lose X life"), and the bare pronoun "it" rather than the name-normalised "this
creature" for the self-reference - proving the reader generalises over the
clause that follows "then", not merely re-confirming Savanti Romero's own
sentence.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.1** - a counter's own open set of kinds; "the number of counters"
  with no kind named counts every one of them.
- **CR 608.2c** - the controller follows an instruction's clauses in the
  order written, so "then" fixes X *after* the counter this same sentence
  just placed lands, not before.
- **CR 107.3a** - X has no value until it is defined; here it is defined by
  the ability's own text rather than announced.
- **CR 506.5** - a creature "attacks alone" when it is the only attacking
  creature that combat.
- **CR 701.25a** - surveil.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_savanti_romero_draws_and_loses_life_equal_to_her_own_counters():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Savanti Romero, Time's Exile"], library=["Mountain"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    savanti = scenario.creature("Savanti Romero, Time's Exile", "alice")
    alice = scenario.player("alice")
    assert savanti.counter_count(Counter.PLUS_ONE) == 0
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.advance()  # beginning of combat

    assert scenario.stack_names() == ["Savanti Romero, Time's Exile's triggered ability"]
    scenario.resolve_top()

    assert savanti.counter_count(Counter.PLUS_ONE) == 1
    assert len(alice.hand) == hand_before + 1
    assert alice.life == life_before - 1


def test_savanti_romero_counts_every_kind_of_counter_not_only_plus_one_plus_one():
    """CR 122.1's open set of kinds: X is the *total*, counted after this
    same instruction's own +1/+1 counter lands."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Savanti Romero, Time's Exile"], library=["Mountain"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    savanti = scenario.creature("Savanti Romero, Time's Exile", "alice")
    scenario.game.add_counters(savanti, Counter.CHARGE, 2)
    alice = scenario.player("alice")
    life_before = alice.life
    hand_before = len(alice.hand)

    scenario.advance()  # beginning of combat
    scenario.resolve_top()

    # 2 charge counters + the 1 +1/+1 counter this trigger just placed = 3.
    assert savanti.counter_count(Counter.PLUS_ONE) == 1
    assert savanti.counter_count(Counter.CHARGE) == 2
    assert len(alice.hand) == hand_before + 3
    assert alice.life == life_before - 3


def test_savanti_romero_does_not_draw_or_lose_life_on_an_opponents_combat():
    """ "on your turn" - CR 603.2's condition is bound to the controller's own
    turn, not any beginning of combat. `bob` is added first (and so is turn
    1's active player) while Savanti Romero is alice's - the beginning of
    combat this reaches is bob's, not hers, with no turn-crossing needed."""
    scenario = (
        Scenario()
        .player("bob")
        .player("alice", battlefield=["Savanti Romero, Time's Exile"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.advance()  # bob's own beginning of combat

    assert scenario.stack_names() == []


def test_spider_man_noir_off_pool_proof_surveils_for_its_own_counters_when_attacking_alone():
    """A different trigger condition, a different `<clause>`, and the bare
    pronoun "it" rather than a name-normalised self-reference - none of which
    is Savanti Romero's own sentence."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Spider-Man Noir"], library=["Mountain", "Forest", "Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    spidey = scenario.find("Spider-Man Noir", Zone.BATTLEFIELD)
    scenario.surveil_keeping_everything_on_top()

    scenario.attack_with(spidey)

    assert scenario.stack_names() == ["Spider-Man Noir's triggered ability"]
    scenario.resolve_top()

    assert spidey.counter_count(Counter.PLUS_ONE) == 1
    assert len(scenario.questions_asked()) == 1


def test_spider_man_noir_off_pool_proof_does_not_trigger_attacking_with_company():
    """CR 506.5: not alone the moment a second creature also attacks."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Spider-Man Noir", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    spidey = scenario.find("Spider-Man Noir", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)

    scenario.attack_with(spidey, bears)

    assert scenario.stack_names() == []
    assert spidey.counter_count(Counter.PLUS_ONE) == 0

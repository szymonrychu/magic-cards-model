"""Scenario: putting a permanent card from hand onto the battlefield.

Kona, Rescue Beastie: "Survival - At the beginning of your second main phase,
if Kona is tapped, you may put a permanent card from your hand onto the
battlefield."

Nothing here is a cast. CR 601.2 is never entered, so no cost is paid, no
spell ever exists, and nothing that watches for a spell being cast sees
anything at all.

Every CR number below was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.

- **CR 110.4a** - "The term 'permanent card' is used to refer to a card that
  could be put onto the battlefield. Specifically, it means an artifact,
  battle, creature, enchantment, land, or planeswalker card." Instants and
  sorceries are excluded by **CR 110.4** - they "can't enter the battlefield
  and thus can't be permanents".
- **CR 400.7** - a card in a hand is its own object, with its printed
  characteristics; the card that reaches the battlefield is a new one again.
- **CR 601.2a** / **CR 601.2i** - what casting is, and the moment a spell
  becomes cast and cast triggers fire. Neither happens here.
- **CR 608.2d** - a resolving ability may require its controller to make a
  choice, and "the player can't choose an option that's illegal or
  impossible" - which is why a hand with no permanent card is never asked.
- **CR 603.4** - the intervening *if* ("if Kona is tapped") is checked when
  the trigger event occurs, and the ability triggers only if it is true.
- **CR 608.2a** - the same clause is checked again as the ability resolves.
- **CR 500.6** - "When a phase or step begins, any abilities that trigger 'at
  the beginning of' that phase or step trigger."
- **CR 505.1** - the first main phase is also known as the precombat main
  phase; the postcombat main phase is the second one this card names.
- **CR 508.1f** - attacking taps the creature, which is how Kona ends up
  tapped in time for its own trigger.

No `xfail` here: `machines/triggers._STEP_PHRASES` reads "second main phase"
as CR 505.1's postcombat main phase, `_source_tapped_holds` reads the
"Kona is tapped" intervening *if*, and
`machines/effects._parse_put_permanent_card_from_hand_clause` does the rest.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

_TRIGGER = "Kona, Rescue Beastie's triggered ability"


def _board(*hand: str) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            battlefield=["Kona, Rescue Beastie", "Forest", "Forest"],
            library=["Forest"] * 10,
        )
        .player("bob", library=["Forest"] * 10)
    )


def _attack_then_reach_the_second_main_phase(scenario: PlayedScenario) -> None:
    """Kona attacks - CR 508.1f taps it - and the turn runs on to the
    postcombat main phase, which is the "second main phase" its own trigger
    names (CR 505.1, CR 500.6)."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    kona = scenario.creature("Kona, Rescue Beastie", "alice")
    scenario.attack_with(kona, defending="bob")
    assert kona.tapped
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    scenario.combat_damage()
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()


# -- the happy path ---------------------------------------------------------


def test_a_permanent_card_arrives_from_hand_without_being_cast():
    """The whole path: Kona attacks, the survival trigger resolves, and the
    creature card in hand is on the battlefield having paid nothing.

    Ulamog, the Ceaseless Hunger is the card in hand on purpose: it prints
    "When you cast this spell, exile two target permanents", and CR 601.2i's
    cast event never happens here, so that trigger must stay silent.
    """
    scenario = _board("Ulamog, the Ceaseless Hunger").build()
    _attack_then_reach_the_second_main_phase(scenario)

    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")
    assert ulamog.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").hand == []
    assert scenario.game.spells_cast_this_turn.get("alice", []) == []
    assert all(state.untapped for state in scenario.untapped_sources("Forest", "Forest"))
    assert scenario.game.stack_is_empty  # no cast trigger followed it in


# -- corner cases -----------------------------------------------------------


def test_an_instant_in_hand_is_never_a_candidate():
    """CR 110.4a: a permanent card is an artifact, battle, creature,
    enchantment, land, or planeswalker card. Lightning Bolt is none of those
    (CR 110.4), so the only card the choice may offer is Grizzly Bears - and
    the Bolt stays in hand.
    """
    scenario = _board("Lightning Bolt", "Grizzly Bears").build()
    _attack_then_reach_the_second_main_phase(scenario)

    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]


def test_a_hand_of_only_instants_is_never_asked_the_question():
    """CR 608.2d: "the player can't choose an option that's illegal or
    impossible". With no permanent card in hand there is nothing to choose
    between, so the ability resolves without putting the question at all -
    not even the "you may" half.
    """
    scenario = _board("Lightning Bolt", "Counterspell").build()
    _attack_then_reach_the_second_main_phase(scenario)

    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    sources = [question.source for question in scenario.questions_asked()]
    assert "Kona, Rescue Beastie" not in sources
    assert len(scenario.player("alice").hand) == 2


def test_an_empty_hand_is_never_asked_the_question():
    """The same CR 608.2d refusal with nothing in hand at all. The ability
    still resolves; it simply does nothing.
    """
    scenario = _board().build()
    _attack_then_reach_the_second_main_phase(scenario)

    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert "Kona, Rescue Beastie" not in [
        question.source for question in scenario.questions_asked()
    ]
    assert scenario.game.stack_is_empty


def test_declining_the_you_may_leaves_the_hand_untouched():
    """CR 608.2d's plain "you may": refusing is always a legal answer, and the
    rest of the ability - the choice of card - is never reached.
    """
    scenario = _board("Grizzly Bears").build()
    scenario.will_take_the_may(False, username="alice")
    _attack_then_reach_the_second_main_phase(scenario)

    assert scenario.stack_names() == [_TRIGGER]
    scenario.pass_until_resolved()

    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]
    assert "Grizzly Bears" not in scenario.battlefield_names()


def test_an_untapped_kona_never_triggers_at_all():
    """CR 603.4: with the intervening *if* false when the phase begins, the
    ability does not trigger - it is not a trigger that resolves and does
    nothing. Kona never attacked, so it is untapped when the second main
    phase begins.

    The paired happy-path test above is what makes this one mean something:
    the same board reaching the same phase with Kona *tapped* does put a
    trigger on the stack, so the difference here is the clause and nothing
    else.
    """
    scenario = _board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kona = scenario.creature("Kona, Rescue Beastie", "alice")
    assert kona.untapped

    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    assert kona.untapped
    assert scenario.stack_names() == []
    assert scenario.pending_triggers == []
    assert [state.name for state in scenario.player("alice").hand] == ["Grizzly Bears"]

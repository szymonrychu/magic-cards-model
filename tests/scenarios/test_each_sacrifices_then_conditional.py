""" "Each player/opponent sacrifices N of a description. If you sacrificed N of
it this way, <consequence>." (`_parse_each_sacrifices_then_conditional_whole_text`,
`_EACH_SACRIFICES_THEN_CONDITIONAL_RE` in `machines/effects.py`).

CR 608.2c: the second sentence's "this way" ties the consequence to the first
sentence's own outcome, and the fact it reads is binary and *personal* to the
ability's own controller - did "you" actually part with a matching permanent -
not a count of how many permanents were sacrificed in total, and not whether
any *other* player sacrificed one.

Two real printings, two different consequences:

- **Garruk, Veiled Butcher**'s own `-2`: "Each player sacrifices a creature of
  their choice. If you sacrificed a creature this way, create a 4/4 green
  Beast creature token with trample." - the consequence is a token creation.
- **Rise of the Witch-king** (off-set sorcery): "Each player sacrifices a
  creature of their choice. If you sacrificed a creature this way, you may
  return another permanent card from your graveyard to the battlefield." -
  the consequence is CR 608.2d's own optional reanimation, exercised here as
  a real "you may" question a scenario can answer either way. Reading this
  sentence needed `_RETURN_CARDS_FROM_YOUR_GRAVEYARD_RE` widened for a
  leading "you may " and for "another" as `{COUNT}`'s synonym for one
  (CR 400.7's "another object", not a real quantity word).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 608.2c, 608.2d, 101.4, 701.21a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

GARRUK = "Garruk, Veiled Butcher"
RISE = "Rise of the Witch-king"


def _may_questions(scenario, username: str, source: str) -> list:
    return [
        decision
        for decision in scenario.questions_asked()
        if decision.kind is DecisionKind.MAY
        and decision.player == username
        and decision.source == source
    ]


# -- Garruk, Veiled Butcher's own -2: token creation --------------------------


def test_the_controller_sacrificing_a_creature_creates_the_beast_token():
    """Both alice (Garruk's controller) and bob each have exactly one
    creature; both are sacrificed (CR 101.4, CR 701.21a), and because alice
    herself sacrificed one, her own "if you sacrificed" rider fires."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GARRUK, "Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find(GARRUK, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(garruk, index=1, username="alice")  # -2
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    # Garruk's own static "if a creature an opponent controls would die,
    # exile it instead" replaces bob's own death with exile - CR 700.4's
    # "dies" already covers a sacrifice, so this is expected, not a miss.
    assert giant.zone is Zone.EXILE
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.token and "Beast" in state.subtypes and state.controller == "alice"
    ]
    assert len(tokens) == 1
    beast = tokens[0]
    assert (beast.power, beast.toughness) == (4, 4)


def test_the_controller_with_nothing_to_sacrifice_gets_no_token_even_though_bob_did():
    """Alice controls only Garruk himself - no creature to sacrifice, so CR
    608.2d's "no impossible choice" leaves her own share of the edict undone.
    Bob still sacrifices his own Hill Giant, but that is not "you sacrificed
    this way": the rider is personal to Garruk's own controller, not a count
    of how many permanents went in total."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GARRUK])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    garruk = scenario.find(GARRUK, Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.activate(garruk, index=1, username="alice")  # -2
    scenario.pass_until_resolved()

    assert giant.zone is Zone.EXILE  # Garruk's own replacement, see above
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.token and "Beast" in state.subtypes and state.controller == "alice"
    ]
    assert tokens == []


# -- Rise of the Witch-king: optional reanimation ------------------------------


def _rise_board(*, has_own_creature: bool, graveyard: list[str]) -> Scenario:
    lands = ["Swamp", "Swamp", "Forest", "Forest"]
    battlefield = [*lands, "Grizzly Bears"] if has_own_creature else lands
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[RISE], battlefield=battlefield, graveyard=graveyard)
        .player("bob", battlefield=["Hill Giant"])
    )


def _cast_rise(scenario) -> None:
    sources = scenario.untapped_sources("Swamp", "Swamp", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve(RISE, *sources, username="alice")


def test_the_controller_sacrificing_a_creature_asks_a_real_may_question_and_returns_the_card():
    scenario = _rise_board(has_own_creature=True, graveyard=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, username="alice", source=RISE)
    # Bears joins the graveyard as this same resolution sacrifices it, so
    # naming the card explicitly (rather than trusting a default answer)
    # is what keeps this a return of Llanowar Elves and not of Bears itself.
    scenario.will_choose_cards(elves, username="alice", source=RISE)

    _cast_rise(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert len(_may_questions(scenario, "alice", RISE)) == 1
    assert elves.zone is Zone.BATTLEFIELD


def test_declining_the_may_leaves_the_graveyard_card_alone():
    """CR 608.2d's "may" is a real choice, not a forced return: answering no
    still fires the rider (a question was put) but changes nothing else."""
    scenario = _rise_board(has_own_creature=True, graveyard=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Grizzly Bears", "alice")
    scenario.will_take_the_may(False, username="alice", source=RISE)

    _cast_rise(scenario)

    assert len(_may_questions(scenario, "alice", RISE)) == 1
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert elves.zone is Zone.GRAVEYARD


def test_the_controller_with_nothing_to_sacrifice_is_never_asked_the_may_question():
    """Alice has no creature; bob's Hill Giant still goes, but alice's own
    rider never fires, so CR 608.2d never puts the "you may" question at
    all - not asked and answered no, simply not asked."""
    scenario = _rise_board(has_own_creature=False, graveyard=["Llanowar Elves"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _cast_rise(scenario)

    assert giant.zone is Zone.GRAVEYARD
    assert _may_questions(scenario, "alice", RISE) == []
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    assert elves.zone is Zone.GRAVEYARD

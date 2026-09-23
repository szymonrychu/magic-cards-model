"""Scenario: "<player> mill(s) N cards, then [you] return a <description> card
from your graveyard to your hand." - the mandatory form.

CR 701.17a: "For a player to mill a number of cards, that player puts that
many cards from the top of their library into their graveyard." CR 608.2c:
the instructions are followed in the order written, so the return's candidate
pool is read *after* the mill - a card this same resolution just milled is
itself a candidate. CR 608.2d: the card to return is chosen while the effect
is applied (it is never a target), and a choice with no legal option is not
offered. There is no "you may": with a candidate in the graveyard, one card
is returned.

The same reader serves every form the sentence is printed in:

- **Takenuma, Abandoned Mire** - an activated ability from a hand (Channel,
  CR 113.6j): "Mill three cards, then return a creature or planeswalker card
  from your graveyard to your hand."
- **Inspiration from Beyond** (proof printing, a spell, not in any api deck):
  "Mill three cards, then return an instant or sorcery card from your
  graveyard to your hand."
- **Fell Gravship** (proof printing, a triggered ability, not in any api
  deck): "When this Spacecraft enters, mill three cards, then return a
  creature or Spacecraft card from your graveyard to your hand."
- **Witherbloom Command** - a mode (CR 700.2a) whose mill is done by a
  *targeted* player while the return is "you", the spell's controller, from
  "your" graveyard: "Target player mills three cards, then you return a land
  card from your graveyard to your hand."

Overlord of the Balemurk's optional "then you may return" twin is covered in
`test_milling_into_a_choice.py` and keeps passing through the same reader.

Every CR number above was read with `mise run rules:find` in the session that
wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

TAKENUMA = "Takenuma, Abandoned Mire"
INSPIRATION = "Inspiration from Beyond"
GRAVSHIP = "Fell Gravship"
COMMAND = "Witherbloom Command"


def _choose_questions(scenario, source: str):
    return [
        asked
        for asked in scenario.questions_asked()
        if asked.source == source and asked.kind is DecisionKind.CHOOSE_CARDS
    ]


def _may_questions(scenario, source: str):
    return [
        asked
        for asked in scenario.questions_asked()
        if asked.source == source and asked.kind is DecisionKind.MAY
    ]


# -- Takenuma: the ability form -------------------------------------------


def _takenuma_board(*, library: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[TAKENUMA],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
            library=list(library),
            graveyard=list(graveyard or []),
        )
        .player("bob", library=["Island"], graveyard=["Grizzly Bears"])
        .build()
    )


def _channel_takenuma(scenario) -> None:
    takenuma = scenario.find(TAKENUMA, Zone.HAND, "alice")
    activation = off_battlefield_activation(scenario.game, takenuma, "alice")
    payment = activation.begin_paying()
    for swamp in scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp"):
        payment.tap_for_mana(swamp, mana_from(swamp))
    payment.pay()
    activation.activate()
    activation.resolve()


def test_takenuma_returns_a_creature_card_it_just_milled():
    """CR 608.2c: the pool is read after the mill, so Grizzly Bears - in the
    library when the ability began resolving - can be the card returned."""
    scenario = _takenuma_board(library=["Island", "Grizzly Bears", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    milled = scenario.top_of_library(3)
    bears = milled[1]
    scenario.will_choose_cards(bears, source=TAKENUMA)

    _channel_takenuma(scenario)

    (question,) = _choose_questions(scenario, TAKENUMA)
    assert question.cards == (bears.id,)
    assert bears.zone is Zone.HAND
    assert milled[0].zone is Zone.GRAVEYARD and milled[2].zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_takenuma_offers_creatures_and_planeswalkers_but_nothing_else():
    """ "A creature or planeswalker card": both halves are candidates, a land
    and an instant are not."""
    scenario = _takenuma_board(
        library=["Lightning Bolt", "Island", "Grizzly Bears", "Island"],
        graveyard=["Teferi, Time Raveler", "Forest"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.find("Teferi, Time Raveler", Zone.GRAVEYARD, "alice")
    bears = scenario.top_of_library(3)[2]
    scenario.will_choose_cards(teferi, source=TAKENUMA)

    _channel_takenuma(scenario)

    (question,) = _choose_questions(scenario, TAKENUMA)
    assert set(question.cards) == {teferi.id, bears.id}
    assert teferi.zone is Zone.HAND
    assert bears.zone is Zone.GRAVEYARD


def test_takenuma_return_is_mandatory_not_a_may():
    """No "you may" is printed: nothing asks whether to return, only which -
    and an unscripted player still returns one."""
    scenario = _takenuma_board(library=["Grizzly Bears", "Island", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.top_of_library(1)[0]

    _channel_takenuma(scenario)

    assert _may_questions(scenario, TAKENUMA) == []
    assert bears.zone is Zone.HAND


def test_takenuma_with_no_candidate_asks_nothing_and_returns_nothing():
    """CR 608.2d: with no creature or planeswalker card in the graveyard after
    the mill there is no option to choose, so no question is put."""
    scenario = _takenuma_board(library=["Island", "Island", "Lightning Bolt", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    milled = scenario.top_of_library(3)

    _channel_takenuma(scenario)

    assert _choose_questions(scenario, TAKENUMA) == []
    assert all(state.zone is Zone.GRAVEYARD for state in milled)
    assert scenario.player("alice").hand == []


def test_takenuma_never_reaches_into_an_opponents_graveyard():
    """ "Your graveyard": bob's Grizzly Bears is no candidate for alice."""
    scenario = _takenuma_board(library=["Island", "Island", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bobs_bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    _channel_takenuma(scenario)

    assert _choose_questions(scenario, TAKENUMA) == []
    assert bobs_bears.zone is Zone.GRAVEYARD


def test_takenuma_mills_what_it_can_from_a_short_library_then_still_returns():
    """A library of one card mills one (CR 701.17a can only move what is
    there), and the return still happens off the graveyard it left behind."""
    scenario = _takenuma_board(library=["Grizzly Bears"], graveyard=["Questing Beast"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.top_of_library(1)[0]
    beast = scenario.find("Questing Beast", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(beast, source=TAKENUMA)

    _channel_takenuma(scenario)

    assert scenario.player("alice").library == []
    assert bears.zone is Zone.GRAVEYARD
    assert beast.zone is Zone.HAND


# -- Inspiration from Beyond: the spell form --------------------------------


def _inspiration_board(*, library: list[str], graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[INSPIRATION],
            battlefield=["Island", "Island", "Island"],
            library=list(library),
            graveyard=list(graveyard or []),
        )
        .player("bob", library=["Island"])
        .build()
    )


def test_inspiration_returns_an_instant_it_just_milled():
    scenario = _inspiration_board(library=["Island", "Lightning Bolt", "Grizzly Bears", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.top_of_library(3)[1]
    scenario.will_choose_cards(bolt, source=INSPIRATION)

    islands = scenario.untapped_sources("Island", "Island", "Island")
    spell = scenario.cast_and_resolve(INSPIRATION, *islands)

    (question,) = _choose_questions(scenario, INSPIRATION)
    assert question.cards == (bolt.id,)
    assert bolt.zone is Zone.HAND
    assert spell.zone is Zone.GRAVEYARD


def test_inspiration_cannot_return_itself():
    """A spell is on the stack while it resolves (CR 608.2) and only reaches
    the graveyard afterwards, so it is never among its own candidates - with
    only lands milled there is nothing to return at all."""
    scenario = _inspiration_board(library=["Island", "Island", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    islands = scenario.untapped_sources("Island", "Island", "Island")
    spell = scenario.cast_and_resolve(INSPIRATION, *islands)

    assert _choose_questions(scenario, INSPIRATION) == []
    assert spell.zone is Zone.GRAVEYARD
    assert scenario.player("alice").hand == []


def test_inspiration_offers_a_sorcery_already_in_the_graveyard_but_not_a_creature():
    scenario = _inspiration_board(
        library=["Grizzly Bears", "Island", "Island", "Island"],
        graveyard=["Inquisition of Kozilek"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    inquisition = scenario.find("Inquisition of Kozilek", Zone.GRAVEYARD, "alice")

    islands = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve(INSPIRATION, *islands)

    (question,) = _choose_questions(scenario, INSPIRATION)
    assert question.cards == (inquisition.id,)
    assert inquisition.zone is Zone.HAND


# -- Fell Gravship: the triggered form --------------------------------------


def test_fell_gravship_enters_trigger_returns_a_creature_card():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[GRAVSHIP], library=["Island", "Grizzly Bears", "Island", "Island"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.top_of_library(2)[1]
    scenario.will_choose_cards(bears, source=GRAVSHIP)

    scenario.put_onto_battlefield(GRAVSHIP, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    assert bears.zone is Zone.HAND


def test_fell_gravship_offers_a_spacecraft_card_by_its_subtype_alone():
    """ "A creature or Spacecraft card": a Spacecraft is an artifact, not a
    creature card (it only becomes one on the battlefield at 8+ charge
    counters), so the second half is read off the subtype (CR 205.3). A
    plain artifact with no such subtype - Sol Ring - is no candidate."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[GRAVSHIP],
            library=["Island", "Island", "Island", "Island"],
            graveyard=[GRAVSHIP, "Sol Ring"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    old_ship = scenario.find(GRAVSHIP, Zone.GRAVEYARD, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.GRAVEYARD, "alice")
    scenario.will_choose_cards(old_ship, source=GRAVSHIP)

    scenario.put_onto_battlefield(GRAVSHIP, "alice")
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    (question,) = _choose_questions(scenario, GRAVSHIP)
    assert question.cards == (old_ship.id,)
    assert old_ship.zone is Zone.HAND
    assert sol_ring.zone is Zone.GRAVEYARD


# -- Witherbloom Command: the mode form, the mill done by a target player ---


def _command_board(
    *,
    alice_library: list[str],
    bob_library: list[str],
    alice_graveyard: list[str] | None = None,
    bob_battlefield: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[COMMAND],
            battlefield=["Swamp", "Forest"],
            library=list(alice_library),
            graveyard=list(alice_graveyard or []),
        )
        .player("bob", library=list(bob_library), battlefield=list(bob_battlefield or []))
        .build()
    )


def _cast_command(scenario, modes: list[int], targets: list, before_resolving=None) -> None:
    casting = scenario.cast(COMMAND)
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    payment = casting.determine_cost()
    scenario.auto_pay(payment, username=casting.caster)
    casting.begin_paying()
    casting.cast()
    if before_resolving is not None:
        before_resolving()
    scenario.resolve_top()


def test_command_mode_one_on_yourself_returns_a_land_you_just_milled():
    """Alice targets herself with mode one (and bob with mode four): the
    Forest she mills is in her graveyard when the return reads it."""
    scenario = _command_board(
        alice_library=["Lightning Bolt", "Forest", "Grizzly Bears", "Island"],
        bob_library=["Island"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(3)[1]
    scenario.will_choose_cards(forest, source=COMMAND)

    _cast_command(scenario, [1, 4], ["alice", "bob"])

    (question,) = _choose_questions(scenario, COMMAND)
    assert question.cards == (forest.id,)
    assert forest.zone is Zone.HAND
    assert _may_questions(scenario, COMMAND) == []
    assert scenario.game.mode_notices == []


def test_command_mode_one_on_an_opponent_mills_them_but_returns_from_your_graveyard():
    """ "Target player mills", "then *you* return ... from *your* graveyard":
    bob mills three lands, and alice returns her own land - never one of
    bob's. Modes one and four may both target bob (CR 700.2f: each mode has
    its own targeting requirement)."""
    scenario = _command_board(
        alice_library=["Island"],
        bob_library=["Forest", "Forest", "Forest", "Island"],
        alice_graveyard=["Swamp"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob_milled = list(scenario.player("bob").library[:3])
    alice_swamp = scenario.find("Swamp", Zone.GRAVEYARD, "alice")
    bob_life = scenario.player("bob").life
    scenario.will_choose_cards(alice_swamp, source=COMMAND)

    _cast_command(scenario, [1, 4], ["bob", "bob"])

    assert all(state.zone is Zone.GRAVEYARD for state in bob_milled)
    (question,) = _choose_questions(scenario, COMMAND)
    assert question.cards == (alice_swamp.id,)
    assert alice_swamp.zone is Zone.HAND
    assert len(scenario.player("alice").library) == 1, "alice milled nothing"
    assert scenario.player("bob").life == bob_life - 2


def test_command_mode_one_on_an_opponent_with_no_land_in_your_graveyard_returns_nothing():
    scenario = _command_board(
        alice_library=["Island"], bob_library=["Forest", "Forest", "Forest", "Island"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _cast_command(scenario, [1, 4], ["bob", "bob"])

    assert _choose_questions(scenario, COMMAND) == []
    assert scenario.player("alice").hand == []
    assert len(scenario.player("bob").graveyard) == 3


def test_command_mode_one_still_resolves_alone_when_the_other_modes_target_is_gone():
    """ "Choose two" means mode one is never *cast* alone, but it can resolve
    alone: Sol Ring leaving the battlefield makes mode two's only target
    illegal, and CR 608.2b lets the rest of the spell resolve normally."""
    scenario = _command_board(
        alice_library=["Forest", "Island", "Island", "Island"],
        bob_library=["Island"],
        bob_battlefield=["Sol Ring"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(forest, source=COMMAND)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_command(
        scenario,
        [1, 2],
        ["alice", sol_ring],
        before_resolving=lambda: scenario.game.return_to_hand(sol_ring),
    )

    assert forest.zone is Zone.HAND
    assert sol_ring.zone is Zone.HAND
    assert scenario.game.mode_notices == []


def test_command_modes_one_and_two_mill_return_and_destroy():
    scenario = _command_board(
        alice_library=["Forest", "Island", "Island", "Island"],
        bob_library=["Island"],
        bob_battlefield=["Sol Ring"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(forest, source=COMMAND)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_command(scenario, [1, 2], ["alice", sol_ring])

    assert forest.zone is Zone.HAND
    assert sol_ring.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_command_modes_one_and_three_mill_return_and_shrink():
    """-3/-1 leaves Ragavan (2/1) at 0 toughness: state-based actions put it
    into the graveyard (CR 704.5f)."""
    scenario = _command_board(
        alice_library=["Forest", "Island", "Island", "Island"],
        bob_library=["Island"],
        bob_battlefield=["Ragavan, Nimble Pilferer"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(forest, source=COMMAND)
    ragavan = scenario.find("Ragavan, Nimble Pilferer", Zone.BATTLEFIELD, "bob")

    _cast_command(scenario, [1, 3], ["alice", ragavan])
    scenario.game.check_state_based_actions()

    assert forest.zone is Zone.HAND
    assert ragavan.zone is Zone.GRAVEYARD
    assert scenario.game.mode_notices == []


def test_command_modes_one_and_four_mill_return_and_drain():
    scenario = _command_board(
        alice_library=["Forest", "Island", "Island", "Island"],
        bob_library=["Island"],
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.top_of_library(1)[0]
    scenario.will_choose_cards(forest, source=COMMAND)
    alice_life = scenario.player("alice").life
    bob_life = scenario.player("bob").life

    _cast_command(scenario, [1, 4], ["alice", "bob"])

    assert forest.zone is Zone.HAND
    assert scenario.player("alice").life == alice_life + 2
    assert scenario.player("bob").life == bob_life - 2
    assert scenario.game.mode_notices == []

"""A token-creation replacement that makes the tokens copies instead, the
first time each turn - Mirrormind Crown: "As long as this Equipment is
attached to a creature, the first time you would create one or more tokens
each turn, you may instead create that many tokens that are copies of
equipped creature."

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 614.1a** "instead" makes it a replacement effect; **CR 614.5** it
  gets one opportunity at the event.
- **CR 111.2** the player who creates a token is its owner and it enters
  under their control.
- **CR 707.2** a copy takes the copiable values - never counters or
  non-copy effects on the original.
- **CR 603.6a** a token entering is an enters event - the copy's own enters
  ability triggers.

"The first time ... each turn" is the whole gate: declining the replacement,
or the Equipment not being attached the first time, uses the turn's first
time up just the same. Proven below, and on the second printing.

Second printing (legal in Modern, Pioneer and Standard, in no deck list,
Scryfall printing read 2026-09-27): Moonlit Meditation - "Enchant artifact
or creature you control. The first time you would create one or more tokens
each turn, you may instead create that many tokens that are copies of
enchanted permanent." (an Aura, no "as long as" gate, "enchanted permanent").
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

CROWN = "Mirrormind Crown"
MEDITATION = "Moonlit Meditation"
PROCESSION = "Spectral Procession"


def _chars(scenario: Scenario, permanent):
    return scenario.game.characteristics_of(permanent)


def _tokens(scenario: Scenario, username: str = "alice"):
    return [
        permanent
        for permanent in scenario.game.permanents_controlled_by(username)
        if getattr(permanent, "token", False)
    ]


def _crown(*, alice=("Grizzly Bears",), hand=(PROCESSION,), lands=("Plains",) * 6, attach=True):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=list(hand),
            battlefield=[CROWN, *lands, *alice],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Plains"] * 3, hand=[PROCESSION], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crown = scenario.find(CROWN, Zone.BATTLEFIELD, "alice")
    if attach and alice:
        crown.attach_to(scenario.creature(alice[0], "alice"))
    return scenario


def _procession(scenario: Scenario, *, take: bool | None = True, username: str = "alice"):
    if take is not None:
        scenario.will_take_the_may(take, source=CROWN)
    scenario.cast_and_resolve(
        PROCESSION,
        *scenario.untapped_sources("Plains", "Plains", "Plains", username=username),
        username=username,
    )


def test_the_first_tokens_are_copies_of_the_equipped_creature():
    scenario = _crown()

    _procession(scenario)

    tokens = _tokens(scenario)
    assert len(tokens) == 3
    assert {_chars(scenario, token).name for token in tokens} == {"Grizzly Bears"}
    assert all((_chars(scenario, t).power, _chars(scenario, t).toughness) == (2, 2) for t in tokens)


def test_declining_creates_the_ordinary_tokens():
    scenario = _crown()

    _procession(scenario, take=False)

    tokens = _tokens(scenario)
    assert len(tokens) == 3
    assert all("Spirit" in _chars(scenario, token).subtypes for token in tokens)


def test_only_the_first_time_each_turn():
    """The second creation this turn is not the first time - no copies."""
    scenario = _crown(hand=(PROCESSION, PROCESSION))
    _procession(scenario)

    _procession(scenario, take=None)

    names = sorted(_chars(scenario, token).name for token in _tokens(scenario))
    assert names.count("Grizzly Bears") == 3
    assert len(names) == 6


def test_declining_still_uses_up_the_first_time():
    scenario = _crown(hand=(PROCESSION, PROCESSION))
    _procession(scenario, take=False)

    _procession(scenario, take=None)

    assert not any(_chars(scenario, t).name == "Grizzly Bears" for t in _tokens(scenario))


def test_unattached_the_first_time_uses_it_up_for_the_turn():
    """The first time came while the Crown was attached to nothing, so
    equipping it afterwards the same turn is too late."""
    scenario = _crown(hand=(PROCESSION, PROCESSION), attach=False)
    _procession(scenario, take=None)
    scenario.find(CROWN, Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Grizzly Bears", "alice")
    )

    _procession(scenario, take=None)

    assert not any(_chars(scenario, t).name == "Grizzly Bears" for t in _tokens(scenario))


def _next_turn(scenario: Scenario) -> None:
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_it_works_again_next_turn():
    """The first time is per turn: alice's next turn has a first time of
    its own."""
    scenario = _crown(hand=(PROCESSION, PROCESSION))
    _procession(scenario)

    _next_turn(scenario)  # bob's turn
    _next_turn(scenario)  # alice's again
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _procession(scenario)

    names = [_chars(scenario, token).name for token in _tokens(scenario)]
    assert names.count("Grizzly Bears") == 6


def test_the_opponents_tokens_are_not_replaced():
    """ "You would create" - bob creating tokens is not alice's event, and
    it does not use up alice's first time either."""
    scenario = _crown(hand=(PROCESSION,))
    _next_turn(scenario)  # bob's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        PROCESSION,
        *scenario.untapped_sources("Plains", "Plains", "Plains", username="bob"),
        username="bob",
    )

    bob_tokens = _tokens(scenario, "bob")
    assert len(bob_tokens) == 3
    assert all("Spirit" in _chars(scenario, token).subtypes for token in bob_tokens)
    assert scenario.game.turn_count("token creation", "alice") == 0


def test_the_copies_do_not_copy_counters():
    """CR 707.2: the copiable values only."""
    scenario = _crown()
    scenario.creature("Grizzly Bears", "alice").add_counters("+1/+1", 2)

    _procession(scenario)

    assert {
        (_chars(scenario, t).power, _chars(scenario, t).toughness) for t in _tokens(scenario)
    } == {(2, 2)}


def test_copies_of_a_creature_with_an_enters_ability_trigger_it():
    """CR 603.6a: three Kitchen Finks tokens enter, three triggers."""
    scenario = _crown(alice=("Kitchen Finks",))
    life = scenario.player("alice").life

    _procession(scenario)
    scenario.pass_until_resolved()
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("alice").life == life + 6


def test_equipping_with_the_equip_ability_works_too():
    scenario = _crown(attach=False, lands=("Plains",) * 5)
    crown = scenario.find(CROWN, Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    activation = equip_activation(scenario.game, crown, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains", "Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    assert crown.attached_to == bears.id

    _procession(scenario)

    assert {_chars(scenario, t).name for t in _tokens(scenario)} == {"Grizzly Bears"}


def _copy_holder(copier: str, *, holder: str = CROWN, lands=("Island",) * 5, hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[copier, PROCESSION, *hand],
            battlefield=[holder, *lands, "Plains", "Plains", "Plains"],
            library=["Plains"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_cards(bears, username="alice", source=copier)
    copy = scenario.cast_and_resolve(copier, *scenario.untapped_sources(*["Island"] * 5))
    return scenario, copy


def _copy_choices(scenario: Scenario, source: str) -> int:
    return sum(
        1
        for question in scenario.questions_asked()
        if question.source == source and question.kind is DecisionKind.CHOOSE_CARDS
    )


def test_equipped_to_a_copy_the_tokens_copy_what_it_copies():
    """CR 707.2: the copiable values are "as modified by other copy effects".
    The card's own ruling: equipped to a creature copying something else,
    the tokens copy what that creature copies. Omni-Changeling copying
    Grizzly Bears "except it has changeling" makes 2/2 changeling Bears,
    never 0/0 Omni-Changelings that die."""
    scenario, omni = _copy_holder("Omni-Changeling")
    scenario.find(CROWN, Zone.BATTLEFIELD, "alice").attach_to(omni)

    _procession(scenario)
    scenario.state_based_actions()

    tokens = _tokens(scenario)
    assert len(tokens) == 3
    for token in tokens:
        chars = _chars(scenario, token)
        assert chars.name == "Grizzly Bears"
        assert (chars.power, chars.toughness) == (2, 2)
        assert "Changeling" in chars.abilities
        assert "Goblin" in chars.subtypes
    # The tokens enter as Bears; they never get Omni-Changeling's own
    # "enter as a copy" choice, which only the printed card has.
    assert _copy_choices(scenario, "Omni-Changeling") == 1


def test_moonlit_meditation_on_a_clone_copies_what_the_clone_copies():
    """The same CR 707.2 reading on the second printing, through Clone."""
    scenario, clone = _copy_holder(
        "Clone", holder="Island", lands=("Island",) * 7, hand=(MEDITATION,)
    )
    scenario.cast_and_resolve(
        MEDITATION, *scenario.untapped_sources("Island", "Island", "Island"), targets=[clone]
    )
    scenario.will_take_the_may(True, source=MEDITATION)

    scenario.cast_and_resolve(PROCESSION, *scenario.untapped_sources("Plains", "Plains", "Plains"))

    tokens = _tokens(scenario)
    assert len(tokens) == 3
    assert {(_chars(scenario, t).name, _chars(scenario, t).power) for t in tokens} == {
        ("Grizzly Bears", 2)
    }
    assert _copy_choices(scenario, "Clone") == 1


# --------------------------------------------------------------------------
# Moonlit Meditation
# --------------------------------------------------------------------------


def test_moonlit_meditation_copies_the_enchanted_permanent_the_first_time():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MEDITATION, PROCESSION, PROCESSION],
            battlefield=["Island"] * 3 + ["Plains"] * 6 + ["Sol Ring"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve(
        MEDITATION, *scenario.untapped_sources("Island", "Island", "Island"), targets=[ring]
    )
    scenario.will_take_the_may(True, source=MEDITATION)

    scenario.cast_and_resolve(PROCESSION, *scenario.untapped_sources("Plains", "Plains", "Plains"))

    tokens = _tokens(scenario)
    assert len(tokens) == 3
    assert {_chars(scenario, token).name for token in tokens} == {"Sol Ring"}

    scenario.cast_and_resolve(PROCESSION, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    assert sum(1 for t in _tokens(scenario) if _chars(scenario, t).name == "Sol Ring") == 3


@pytest.mark.parametrize("name", [CROWN, MEDITATION])
def test_the_sweep_handles_every_clause(name):
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    support = card_support(card(name))
    assert support.effect_outcome == HANDLED, support.effect_detail

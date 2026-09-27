"""Scenario: a mass, untargeted "return each other `<qualifier>` permanent
that entered this turn to its owner's hand" (no reader in this file read a
mass "entered this turn" subject before this wave - only a *targeted*
restriction, `machines/targeting.py`'s `must_have_entered_this_turn`).

Renet, Temporal Apprentice: "When Renet enters, return each other nonland
permanent that entered this turn to its owner's hand." `CardState.
turn_entered` (stamped once, in `Game.enter_the_battlefield`) against the
live `Game.turn.turn_number` is the same "entered this turn" reading
`machines/targeting.py` already gives a *targeted* restriction with this
exact phrase; `_parse_mass_type_qualifier` ("nonland permanent") is the same
CR 205.2a type-list reader a mass destruction's own subject already shares.
"Each other" excludes only Renet's own id - "nonland permanent" already
excludes lands, and Renet's own name never needs to appear in the exclusion
because there is nothing else to exclude a permanent that is neither.

Proof printing: no second real printing shares this exact "return each
other nonland permanent that entered this turn to its owner's hand" wording
at all - verified by several Scryfall full-text oracle searches ("that
entered this turn" + "owner's hand", "entered the battlefield this turn" +
"return", and the exact phrase itself), every one of which returns Renet
alone among Modern/Pioneer/Standard-legal printings; recorded as a dated
line in `MEMORY.md`. This file instead leans on corner cases on the listed
card itself: several permanents that entered this turn at once, a permanent
that entered on an *earlier* turn staying put, a land staying put despite
having entered this turn, and Renet's own exclusion of itself.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 205.2a (the fifteen card types "nonland permanent" excludes
lands from), 400.7 ("entered this turn" is a fact about the specific
incarnation on the battlefield right now - a permanent that left and came
back this same turn is a new object, freshly stamped), 603.2c (one
instruction, several permanents, one event), 108.3 (a card returns to hand
under its own owner, not necessarily its controller).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

RENET = "Renet, Temporal Apprentice"


def test_listed_printing_is_handled():
    bad = [c for c in card_support(card(RENET)).clauses if c.outcome != "handled"]
    assert not bad, bad


def _cast_renet(scenario, *sources):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(RENET, *sources)
    scenario.pass_until_resolved()  # the ETB trigger


def test_renet_bounces_a_creature_that_entered_this_turn_to_its_owners_hand():
    scenario = (
        Scenario()
        .player("alice", hand=[RENET], battlefield=["Island"] * 5)
        .player("bob", hand=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")
    assert bears.zone is Zone.BATTLEFIELD

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    scenario.cast_and_resolve(RENET, *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND
    assert bears.owner == "bob", "CR 108.3: to its own owner"


def test_renet_bounces_several_nonland_permanents_that_entered_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[RENET, "Mind Stone"],
            battlefield=["Island"] * 5 + ["Plains"] * 2,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone_sources = scenario.untapped_sources("Plains", "Plains")
    stone = scenario.cast_and_resolve("Mind Stone", *stone_sources)
    assert stone.zone is Zone.BATTLEFIELD

    renet_sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    scenario.cast_and_resolve(RENET, *renet_sources)
    scenario.pass_until_resolved()

    assert stone.zone is Zone.HAND, "entered this same turn - bounced too, not only creatures"


def test_a_permanent_from_an_earlier_turn_stays_put():
    scenario = (
        Scenario()
        .player("alice", hand=[RENET], battlefield=["Island"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    # Advance a full turn so Grizzly Bears no longer "entered this turn".
    while scenario.turn.active_player != "alice" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    _cast_renet(scenario, *sources)

    assert bears.zone is Zone.BATTLEFIELD, "entered on an earlier turn - untouched"


def test_lands_are_never_bounced_even_though_they_entered_this_turn():
    scenario = (
        Scenario()
        .player("alice", hand=[RENET, "Forest"], battlefield=["Island"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.play_land("Forest")
    assert forest.zone is Zone.BATTLEFIELD

    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    _cast_renet(scenario, *sources)

    assert forest.zone is Zone.BATTLEFIELD, '"nonland permanent" never reaches a land'


def test_renet_never_bounces_herself():
    scenario = (
        Scenario().player("alice", hand=[RENET], battlefield=["Island"] * 5).player("bob").build()
    )
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island", "Island")
    _cast_renet(scenario, *sources)

    renet = scenario.creature(RENET, "alice")
    assert renet.zone is Zone.BATTLEFIELD, '"each OTHER" excludes Renet\'s own arrival'

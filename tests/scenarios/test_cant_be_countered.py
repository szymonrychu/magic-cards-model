"""Scenario: Supreme Verdict's "This spell can't be countered."

CR 113.6g: "An object's ability that states it can't be countered or can't be
copied functions on the stack." CR 604.5 is the general permission for it:
"Some static abilities apply while a spell is on the stack. These are often
abilities that refer to countering the spell." So unlike every other
prohibition in `machines/casting_restrictions.py`, this one is read off the
spell rather than off a player or a permanent.

What it makes impossible is CR 701.6a's verb: "To counter a spell or ability
means to cancel it, removing it from the stack. It doesn't resolve and none of
its effects occur."

**It is not a targeting restriction.** Nothing in CR 608.2b's legality check
knows about counterability, so a Counterspell aimed at Supreme Verdict is
announced legally, resolves normally, finds a legal target - and then simply
fails to counter it. (The plan sketched this as a CR 601.2c announcement
refusal; the rules do not support that reading, and the scenario below asserts
the resolution-time one instead.)

Measured before this file existed: `machines/effects.py`'s
`_CANT_BE_COUNTERED_LINE_RE` **strips** the sentence so the "Destroy all
creatures." clause parses, and nothing anywhere records that the spell has the
quality. Counterspell countered Supreme Verdict - a wrong board state, not an
absent one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting_restrictions import cannot_be_countered
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Supreme Verdict"],
            battlefield=["Plains", "Plains", "Plains", "Island", "Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player(
            "bob",
            hand=["Counterspell"],
            battlefield=["Island", "Island", "Grizzly Bears"],
            library=["Island"] * 5,
        )
        .build()
    )


def _verdict_on_the_stack(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Island")
    return scenario.cast_onto_stack("Supreme Verdict", *sources, username="alice")


# -- the quality itself -----------------------------------------------------


def test_a_spell_on_the_stack_reports_that_it_cannot_be_countered():
    """CR 113.6g: the ability functions on the stack, so the object there is
    what answers for it."""
    scenario = _board()
    verdict = _verdict_on_the_stack(scenario)

    assert verdict.zone is Zone.STACK
    assert cannot_be_countered(verdict) is True


def test_an_ordinary_spell_reports_nothing_of_the_kind():
    """The other side of the same reader - a counterspell that answered True
    for everything would pass the test above and nothing else."""
    scenario = _board()
    _verdict_on_the_stack(scenario)
    scenario.pass_priority("alice")
    (island,) = scenario.untapped_sources("Island", username="bob")[:1]
    counterspell = scenario.find("Counterspell", Zone.HAND, "bob")

    assert cannot_be_countered(counterspell) is False
    assert island.zone is Zone.BATTLEFIELD


# -- what it stops ----------------------------------------------------------


def test_a_counterspell_resolves_against_supreme_verdict_and_does_nothing():
    """CR 113.6g's ability, enforced where CR 701.6a's verb lives.

    `Game.counter` refuses to remove the spell from the stack and emits no
    counter event; the Counterspell itself was legally cast and legally
    resolved, and simply fails to do the one thing it says."""
    scenario = _board()
    verdict = _verdict_on_the_stack(scenario)
    scenario.pass_priority("alice")

    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[verdict])
    scenario.resolve_top()

    # CR 701.6a never happened: the Verdict is still on the stack, not in a
    # graveyard, and it goes on to resolve.
    assert verdict.zone is Zone.STACK
    scenario.resolve_top()
    assert verdict.zone is Zone.GRAVEYARD
    assert [c.name for c in scenario.game.battlefield if c.name == "Grizzly Bears"] == []

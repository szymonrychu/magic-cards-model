"""Scarblade's Malice: "Target creature you control gains deathtouch and
lifelink until end of turn. When that creature dies this turn, create a 2/2
black and green Elf creature token."

Two CR 608.2c instructions in one card: an ordinary single-target grant
(already generally read by `_parse_targeted_clause`), and a delayed watch on
that same object for the rest of the turn - CR 400.7's "that creature"
anaphora, CR 603.7's delayed triggered ability, implemented as a one-shot
`TriggerEvent.DIES` delayed trigger scoped to the target's own id
(`expires_end_of_turn=True`, the same "this turn" ending `Game.
delayed_triggers.expire_this_turn` already gives every other such trigger)
rather than a replacement effect - nothing here changes what dying means for
the creature, it only reacts afterward.

The gap this closes was not the grant, nor the delayed-trigger machinery
(`earthbend`'s own subject-scoped `DIES` watch already proved that generally)
- it was that the first sentence's own bare "and" ("gains deathtouch and
lifelink") could never survive `_prepare_effect_clauses`'s split far enough
to reach the second sentence at all, the identical "power and toughness"
problem `_DOUBLE_TARGET_POWER_AND_TOUGHNESS_RE`'s own docstring documents.
The fix reads both sentences whole, ahead of the splitter, the same way
that shape already does.

Proof printing: **Make Your Mark** (real Scryfall data, added with
`scripts/add_card.py`, Pioneer/Modern `legal`, not a listed ecl-T8 card, not
in any deck list) - "Target creature gets +1/+0 until end of turn. When
that creature dies this turn, create a 3/2 red and white Spirit creature
token." proves the shape generally: a pump instead of a keyword grant for
the first sentence (no bare "and" at all, so it also confirms the ordinary,
un-split case still works), a different token, and no "you control"
restriction on the target.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 400.7** - "that creature" is anaphora onto the first sentence's own
  target, not a second target of its own.
- **CR 603.7 / 603.7b** - a delayed triggered ability, one-shot unless it
  carries a stated duration; "this turn" is that duration.
- **CR 603.7d** - the delayed trigger's controller and source are the
  creating spell's own, as it resolved.
- **CR 608.2b** - a target no longer legal by the time the spell resolves
  means the grant, and the delayed watch, never happen at all.
- **CR 514.2** - "this turn" effects, delayed triggers included, end in the
  cleanup step if they never fired.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

SCARBLADES_MALICE = "Scarblade's Malice"
MAKE_YOUR_MARK = "Make Your Mark"


def test_both_printings_are_fully_handled():
    for name in (SCARBLADES_MALICE, MAKE_YOUR_MARK):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def test_scarblades_malice_grants_keywords_and_makes_a_token_when_it_dies():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[SCARBLADES_MALICE],
            battlefield=["Swamp", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.cast_and_resolve(SCARBLADES_MALICE, swamp, targets=[bears])

    assert has_keyword(bears, "deathtouch", scenario.game)
    assert has_keyword(bears, "lifelink", scenario.game)
    assert scenario.game.delayed_triggers.triggers, "the delayed watch was created"

    scenario.game.destroy(bears)
    scenario.game.check_state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Elf Token"
    ]
    assert len(tokens) == 1
    assert tokens[0].power == 2 and tokens[0].toughness == 2


def test_scarblades_malice_makes_no_token_if_the_creature_survives_the_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[SCARBLADES_MALICE],
            battlefield=["Swamp", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.cast_and_resolve(SCARBLADES_MALICE, swamp, targets=[bears])
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.game.cleanup_step()

    assert not scenario.game.delayed_triggers.triggers, "CR 514.2: an unused 'this turn' watch ends"
    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Elf Token"
    ]
    assert tokens == []


# -- proof printing: Make Your Mark, a pump instead of a keyword grant ------


def test_make_your_mark_pumps_and_makes_a_token_when_it_dies():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[MAKE_YOUR_MARK],
            battlefield=["Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Grizzly Bears", "bob")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.cast_and_resolve(MAKE_YOUR_MARK, plains, targets=[target])

    assert target.power == 3, "+1/+0 on a 2/2"
    assert scenario.game.delayed_triggers.triggers

    scenario.game.destroy(target)
    scenario.game.check_state_based_actions()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Spirit Token"
    ]
    assert len(tokens) == 1
    assert tokens[0].power == 3 and tokens[0].toughness == 2

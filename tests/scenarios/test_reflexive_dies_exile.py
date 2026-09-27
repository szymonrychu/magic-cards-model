"""Scenario: a reflexive dies trigger (CR 603.12) that exiles its own
source, then a brand-new ability puts a target card on top of a library.

Paramecia Coloniex: "When this creature dies, you may exile it. When you
do, put target creature card from your graveyard on top of your library."
"It" is CR 603.10a's look-back to the ability's own source, now sitting in
the graveyard - `_dead_self_found`, already built for `_parse_exile_dead_
self_clause`'s own unconditional "exile it" - and the reflexive half is a
brand-new CR 603.3d ability that announces its own target only once it goes
on the stack, never anything the dies trigger itself chose.

The only new *reader* here is a small, generic building block:
"put target `<X>` card from your graveyard on top of your library" had no
reader in this file at all (only its "bottom of your library" sibling did) -
`_PUT_TARGET_FROM_GRAVEYARD_TOP_OF_LIBRARY_RE`, tried by the ordinary
targeted-clause dispatch that "When you do, `<consequence>`" already routes
any reflexive ability's own text through
(`reflexive_consequence_effect` -> `parse_mixed_effect` -> `_parse_targeted_
clause`). The "you may exile it. When you do, ..." wrapper itself
(`_parse_reflexive_may_exile_dead_self_clause`) is new too, but it is only
plumbing: CR 603.12's reflexive-ability machinery (`Game.
create_reflexive_trigger`, `ReflexiveConsequence`) is exactly what
`test_reflexive_triggered_abilities.py`'s Grist already exercises for a
"you may sacrifice ..." antecedent.

Proof printing (Modern-legal, added with `scripts/add_card.py`, not
Paramecia Coloniex and not in any deck list): **Golgari Thug** - "When this
creature dies, put target creature card from your graveyard on top of your
library." The same new "put target ... on top of your library" clause, on
an *unconditional* dies trigger with no reflexive wrapper at all - proving
that half of the shape generalises on its own, independent of the "you may
exile it. When you do" antecedent Paramecia Coloniex alone provides.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 603.12 (the reflexive-ability rule, quoted in full in
`test_reflexive_triggered_abilities.py`), 603.10a ("it" is a look-back
pronoun to the ability's own source), 603.3d (the reflexive ability's own
target is announced only as it goes on the stack), 608.2d (a "you may"
cannot offer an impossible option - though "exile it" is always possible
here, since the source is always sitting right there in the graveyard),
401.2 (a library stays face down and in whatever order cards are put into
it - "on top" is a plain move, never a shuffle).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

PARAMECIA = "Paramecia Coloniex"
GOLGARI_THUG = "Golgari Thug"


def test_listed_and_proof_printings_are_handled():
    for name in (PARAMECIA, GOLGARI_THUG):
        bad = [
            c
            for c in card_support(card(name)).clauses
            if c.outcome not in ("handled", "static_unaudited")
        ]
        assert not bad, (name, bad)


def _paramecia_board():
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[PARAMECIA],
            graveyard=["Hill Giant"],
            library=["Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )


def test_taking_the_exile_puts_the_chosen_graveyard_creature_on_top():
    scenario = _paramecia_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paramecia = scenario.creature(PARAMECIA)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(True, source=PARAMECIA)
    scenario.choose_trigger_targets(PARAMECIA, [giant])

    scenario.game.destroy(paramecia)
    scenario.pass_until_resolved()  # the dies trigger: exile Paramecia itself

    assert paramecia.zone is Zone.EXILE
    assert scenario.stack_names() == [f"{PARAMECIA}'s triggered ability"], (
        "CR 603.12/603.3: a second, independent reflexive ability"
    )

    scenario.pass_until_resolved()  # the reflexive ability: put Hill Giant on top

    assert scenario.player("alice").library[0].id == giant.id
    assert giant.zone is Zone.LIBRARY


def test_declining_the_exile_leaves_it_in_the_graveyard_with_no_reflexive_ability():
    scenario = _paramecia_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paramecia = scenario.creature(PARAMECIA)
    scenario.will_take_the_may(False, source=PARAMECIA)

    scenario.game.destroy(paramecia)
    scenario.pass_until_resolved()

    assert paramecia.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_exiling_with_no_legal_target_creates_no_effective_reflexive_ability():
    """CR 601.2c/603.3d: a mandatory-target ability with nothing legal to
    name is removed from the stack rather than resolving against nothing."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[PARAMECIA], library=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    paramecia = scenario.creature(PARAMECIA)
    scenario.will_take_the_may(True, source=PARAMECIA)

    scenario.game.destroy(paramecia)
    scenario.pass_until_resolved()  # the dies trigger: exile Paramecia (nothing else in the yard)
    assert paramecia.zone is Zone.EXILE

    scenario.pass_until_resolved()  # the reflexive ability, with no legal target

    assert [c.name for c in scenario.player("alice").library[:1]] == ["Grizzly Bears"], (
        "nothing was moved - there was no legal target to put anywhere"
    )


# -- proof printing: Golgari Thug's own unconditional, non-reflexive form ---


def test_golgari_thug_unconditionally_puts_the_target_on_top():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[GOLGARI_THUG],
            graveyard=["Hill Giant"],
            library=["Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thug = scenario.creature(GOLGARI_THUG)
    giant = scenario.find("Hill Giant", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets(GOLGARI_THUG, [giant])

    scenario.game.destroy(thug)
    scenario.pass_until_resolved()  # the dies trigger: no "may", no reflexive ability

    assert scenario.player("alice").library[0].id == giant.id
    assert giant.zone is Zone.LIBRARY

"""Strategic Betrayal: "Target opponent exiles a creature they control and
their graveyard." - one CR 601.2c instruction with two unrelated objects of
the same verb, joined by a bare "and" that `split_effect_clauses` would
otherwise cut into a verbless "their graveyard" fragment.

CR 701.21a's ordinary edict grammar ("target opponent sacrifices/exiles a
`<description>`", `machines/effects.py`'s `_TARGET_PLAYER_SACRIFICES_RE`)
already reads the creature half generally; `machines/spell_texts_r0a.py`'s
`parse_target_player_exiles_creature_and_graveyard_clause` reads the whole
sentence so the graveyard half - `exile_target_players_graveyard`'s own
move - is not lost.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.10a** - "'Exile' means to put an object into the exile zone from
  wherever it is."
- **CR 701.21a** - an edict: "that player ... exiles/sacrifices" is *their*
  own choice among what they control.
- **CR 404.1** - "A player's graveyard is their discard pile."
- **CR 608.2b** - a target rechecked for legality (still in the game) the
  instant it would be affected.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_strategic_betrayal_exiles_a_creature_and_the_whole_graveyard():
    scenario = (
        Scenario()
        .player("alice", hand=["Strategic Betrayal"], battlefield=["Swamp", "Swamp"])
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Serra Angel"],
            graveyard=["Lightning Bolt", "Opt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    bob = scenario.player("bob")
    bolt, opt = bob.graveyard

    casting = scenario.cast("Strategic Betrayal")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.will_choose_cards(bears, username="bob", source="Strategic Betrayal")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE, "bob's own choice among his creatures"
    assert angel.zone is Zone.BATTLEFIELD, "not chosen, and never touched"
    assert bolt.zone is Zone.EXILE
    assert opt.zone is Zone.EXILE
    assert bob.graveyard == []


def test_strategic_betrayal_with_one_creature_asks_nothing():
    """CR 608.2d: with exactly one legal candidate, exiling it is not a
    choice."""
    scenario = (
        Scenario()
        .player("alice", hand=["Strategic Betrayal"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"], graveyard=["Opt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    (opt,) = bob.graveyard

    casting = scenario.cast("Strategic Betrayal")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert opt.zone is Zone.EXILE


def test_strategic_betrayal_with_no_creatures_still_exiles_the_graveyard():
    """CR 608.2d: no creature to exile is a legal, empty answer to the first
    half; the second - the graveyard - is unconditional and still happens."""
    scenario = (
        Scenario()
        .player("alice", hand=["Strategic Betrayal"], battlefield=["Swamp", "Swamp"])
        .player("bob", graveyard=["Opt", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    opt, bolt = bob.graveyard

    casting = scenario.cast("Strategic Betrayal")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert opt.zone is Zone.EXILE
    assert bolt.zone is Zone.EXILE
    assert bob.graveyard == []


def test_strategic_betrayal_never_touches_the_targeted_opponents_own_hand():
    """Only "a creature they control" and "their graveyard" move - nothing
    else about the target changes."""
    scenario = (
        Scenario()
        .player("alice", hand=["Strategic Betrayal"], battlefield=["Swamp", "Swamp"])
        .player("bob", hand=["Opt"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    opt_in_hand = scenario.find("Opt", Zone.HAND, "bob")

    casting = scenario.cast("Strategic Betrayal")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert opt_in_hand.zone is Zone.HAND

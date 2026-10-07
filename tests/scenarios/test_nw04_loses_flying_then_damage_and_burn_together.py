"""Scenario: "Target creature [with flying] loses flying until end of turn.
<self> deals damage to that creature equal to <amount>." (Crash Landing), the
bite with "Then sacrifice it." (Burn Together), and its adventurer's "enters
with a +1/+1 counter on it for each creature that died under your control this
turn" (Callous Sell-Sword).

Rules, each read in full with `mise run rules:find`:

- CR 113.10 - "An effect that removes an ability will state that the object
  "loses" that ability."
- CR 613.1f - "Layer 6: Ability-adding effects, keyword counters,
  ability-removing effects, and effects that say an object can't have an
  ability are applied."
- CR 608.2c - the instructions are followed in order; "that creature" is the
  first sentence's target.
- CR 608.2h - the count ("the number of Forests you control", a creature's
  power) is determined once, as the effect is applied.
- CR 608.2b - an illegal target is not affected; if every target is illegal
  the spell does nothing.
- CR 701.21a - "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard. A player can't sacrifice
  something that isn't a permanent, or something that's a permanent they don't
  control."
- CR 715.4 - an adventurer card has only its normal characteristics except on
  the stack as an Adventure.
- CR 614.1c - "[This permanent] enters with ..." is a replacement effect.
- CR 700.4 - "The term dies means "is put into a graveyard from the
  battlefield."" - a token dies too.

Listed printings: Crash Landing, Callous Sell-Sword // Burn Together. Proof
printings (not listed, in no api deck, legal in Modern): Adarkar Windform's
activated "Target creature loses flying until end of turn." (no "with flying"
on the target, a snow activation), Gravity Well's triggered "Whenever a
creature with flying attacks, it loses flying until end of turn." (the
attacker, untargeted) and Liliana's Standard Bearer's ETB "draw X cards, where
X is the number of creatures that died under your control this turn." (the
same count read by a draw, not a counter replacement). No other target-format
printing carries "Then sacrifice it." after a bite or "deals damage to that
creature equal to" after a layer sentence (MEMORY.md).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ["Crash Landing", "Callous Sell-Sword // Burn Together"]
PROOF = ["Adarkar Windform", "Gravity Well", "Liliana's Standard Bearer"]


@pytest.mark.parametrize("name", LISTED + PROOF)
def test_every_listed_and_proof_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), forests=2):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[
                *["Forest"] * forests,
                "Mountain",
                "Swamp",
                "Plains",
                "Snow-Covered Island",
                *alice_battlefield,
            ],
            library=["Plains"] * 10,
        )
        .player(
            "bob",
            battlefield=[*["Mountain"] * 2, *bob_battlefield],
            library=["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _flies(scenario, creature):
    return has_keyword(creature, Keyword.FLYING, scenario.game)


# -- Crash Landing --------------------------------------------------------------


def test_crash_landing_removes_flying_and_deals_damage_per_forest():
    scenario = _board(alice_hand=["Crash Landing"], bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve("Crash Landing", targets=[angel], auto=True)

    assert angel.zone is Zone.BATTLEFIELD
    assert angel.damage == 2
    assert not _flies(scenario, angel)


def test_crash_landing_kills_with_enough_forests():
    scenario = _board(alice_hand=["Crash Landing"], bob_battlefield=["Serra Angel"], forests=4)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve("Crash Landing", targets=[angel], auto=True)

    assert angel.zone is Zone.GRAVEYARD


def test_crash_landing_with_no_forests_only_grounds_it():
    scenario = _board(
        alice_hand=["Crash Landing"],
        alice_battlefield=["Llanowar Elves"],
        bob_battlefield=["Serra Angel"],
        forests=0,
    )
    angel = scenario.creature("Serra Angel", "bob")
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.cast_and_resolve(
        "Crash Landing", elves, *scenario.untapped_sources("Mountain", "Plains"), targets=[angel]
    )

    assert angel.damage == 0
    assert not _flies(scenario, angel)


def test_the_forest_count_is_taken_as_it_resolves():
    scenario = _board(alice_hand=["Crash Landing"], bob_battlefield=["Serra Angel"], forests=3)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_onto_stack("Crash Landing", targets=[angel], auto=True)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(forest)

    scenario.resolve_top()

    assert angel.damage == 2  # two Forests left as it resolved (CR 608.2h)


def test_crash_landing_cannot_target_a_creature_without_flying():
    scenario = _board(alice_hand=["Crash Landing"], bob_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Crash Landing", targets=[bears], auto=True)


def test_a_target_that_lost_flying_before_resolution_is_illegal():
    """CR 608.2b: no longer "a creature with flying", so the spell does
    nothing - not even the damage."""
    scenario = _board(
        alice_hand=["Crash Landing"],
        alice_battlefield=["Adarkar Windform"],
        bob_battlefield=["Serra Angel"],
    )
    angel = scenario.creature("Serra Angel", "bob")
    windform = scenario.creature("Adarkar Windform", "alice")
    scenario.cast_onto_stack(
        "Crash Landing", *scenario.untapped_sources("Forest", "Forest", "Mountain"), targets=[angel]
    )
    scenario.activate(
        windform,
        *scenario.untapped_sources("Snow-Covered Island", "Plains"),
        index=0,
        username="alice",
        targets=[angel],
    )
    scenario.resolve_top()
    assert not _flies(scenario, angel)

    scenario.resolve_top()

    assert angel.damage == 0


def test_flying_comes_back_at_cleanup():
    scenario = _board(alice_hand=["Crash Landing"], bob_battlefield=["Serra Angel"], forests=2)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.cast_and_resolve("Crash Landing", targets=[angel], auto=True)
    assert not _flies(scenario, angel)

    while scenario.turn.active_player == "alice":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert _flies(scenario, angel)


# -- Adarkar Windform: the activated twin --------------------------------------


def test_adarkar_windform_grounds_any_target_creature():
    scenario = _board(alice_battlefield=["Adarkar Windform"], bob_battlefield=["Serra Angel"])
    angel = scenario.creature("Serra Angel", "bob")
    windform = scenario.creature("Adarkar Windform", "alice")

    scenario.activate(
        windform,
        *scenario.untapped_sources("Snow-Covered Island", "Plains"),
        index=0,
        username="alice",
        targets=[angel],
    )
    scenario.resolve_top()

    assert not _flies(scenario, angel)
    assert _flies(scenario, windform)


# -- Gravity Well: the triggered twin ------------------------------------------


def test_gravity_well_grounds_a_flying_attacker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Plains", "Serra Angel", "Savannah Lions"])
        .player("bob", battlefield=["Forest", "Gravity Well", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "alice")
    lions = scenario.creature("Savannah Lions", "alice")

    scenario.attack_with(angel, lions, defending="bob")
    while scenario.game.pending_triggers or not scenario.game.stack_is_empty:
        scenario.game.put_triggers_on_stack()
        if not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert not _flies(scenario, angel)
    assert not _flies(scenario, lions)


# -- Burn Together: the bite, then sacrifice it ---------------------------------


def _burn_together(scenario, biter, victim):
    casting = scenario.cast("Callous Sell-Sword")
    casting.cast_as_adventure()
    casting.choose_targets([biter, victim])
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    return scenario.put_on_stack(casting)


def test_burn_together_bites_then_sacrifices_the_biter():
    scenario = _board(
        alice_hand=["Callous Sell-Sword"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    spell = _burn_together(scenario, giant, bears)

    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD  # sacrificed (CR 701.21a)
    assert spell.zone is Zone.EXILE  # CR 715.3d: an Adventure goes to exile


def test_burn_together_may_hit_a_player():
    scenario = _board(alice_hand=["Callous Sell-Sword"], alice_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    _burn_together(scenario, giant, scenario.player("bob"))

    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert giant.zone is Zone.GRAVEYARD


def test_burn_together_biter_cannot_be_its_own_other_target():
    """CR 115.3: "any other target" is a target other than the one chosen for
    "target creature you control", so naming the biter twice is refused at
    announcement rather than letting it bite itself."""
    scenario = _board(alice_hand=["Callous Sell-Sword"], alice_battlefield=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    casting = scenario.cast("Callous Sell-Sword")
    casting.cast_as_adventure()

    with pytest.raises(ValueError, match="CR 115.3"):
        casting.choose_targets([giant, giant])


def test_burn_together_still_sacrifices_when_the_victim_is_gone():
    """CR 608.2b: the victim is illegal and dealt nothing; the biter is still
    a legal target, so "Then sacrifice it." still happens."""
    scenario = _board(
        alice_hand=["Callous Sell-Sword"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _burn_together(scenario, giant, bears)
    scenario.game.destroy(bears)

    scenario.resolve_top()

    assert giant.zone is Zone.GRAVEYARD


def test_burn_together_sacrifices_a_biter_that_dealt_no_damage():
    """A 0-power biter deals no damage (CR 120.8), and is still sacrificed."""
    scenario = _board(
        alice_hand=["Callous Sell-Sword"],
        alice_battlefield=["Ornithopter"],
        bob_battlefield=["Grizzly Bears"],
    )
    thopter = scenario.creature("Ornithopter", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _burn_together(scenario, thopter, bears)

    scenario.resolve_top()

    assert bears.damage == 0
    assert thopter.zone is Zone.GRAVEYARD


def test_an_illegal_biter_is_neither_dealt_from_nor_sacrificed():
    """CR 608.2b: the biter left and came back - a new object (CR 400.7) - so
    it deals nothing and "it" names nothing to sacrifice."""
    scenario = _board(
        alice_hand=["Callous Sell-Sword"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _burn_together(scenario, giant, bears)
    scenario.game.return_to_hand(giant)
    returned = scenario.put_onto_battlefield("Hill Giant", "alice", from_zone=Zone.HAND)

    scenario.resolve_top()

    assert bears.damage == 0
    assert returned.zone is Zone.BATTLEFIELD


# -- Callous Sell-Sword: enters with a counter per creature that died ----------


def _cast_sell_sword(scenario):
    casting = scenario.cast("Callous Sell-Sword")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Swamp", "Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return scenario.creature("Callous Sell-Sword", "alice")


def test_sell_sword_counts_token_and_nontoken_creatures_that_died_under_your_control():
    scenario = _board(
        alice_hand=["Callous Sell-Sword", "Raise the Alarm"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve("Raise the Alarm", *scenario.untapped_sources("Plains", "Forest"))
    tokens = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    scenario.game.destroy(tokens[0])
    scenario.game.destroy(bears)
    scenario.game.destroy(scenario.creature("Hill Giant", "bob"))  # not yours

    sell_sword = _cast_sell_sword(scenario)

    assert sell_sword.counters["+1/+1"] == 2


def test_sell_sword_enters_with_no_counters_when_nothing_died():
    scenario = _board(alice_hand=["Callous Sell-Sword"])

    sell_sword = _cast_sell_sword(scenario)

    assert sell_sword.counters["+1/+1"] == 0


def test_sell_sword_counts_this_turn_only():
    scenario = _board(alice_hand=["Callous Sell-Sword"], alice_battlefield=["Grizzly Bears"])
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    while scenario.turn.active_player == "alice":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    while scenario.turn.active_player != "alice" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    sell_sword = _cast_sell_sword(scenario)

    assert sell_sword.counters["+1/+1"] == 0


# -- Liliana's Standard Bearer: the same count, read by an ETB draw --------------


def _flash_in_standard_bearer(scenario):
    casting = scenario.cast("Liliana's Standard Bearer")
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources("Swamp", "Forest", "Forest")
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()  # the creature spell
    scenario.resolve_top()  # its enters trigger
    return scenario.player("alice")


def test_standard_bearer_draws_one_per_creature_that_died_under_your_control():
    """CR 700.4: a token dies too; bob's creature did not die under alice's
    control, so it is not counted."""
    scenario = _board(
        alice_hand=["Liliana's Standard Bearer", "Raise the Alarm"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
        forests=3,
    )
    scenario.cast_and_resolve("Raise the Alarm", *scenario.untapped_sources("Plains", "Forest"))
    tokens = [p for p in scenario.game.permanents_controlled_by("alice") if p.token]
    scenario.game.destroy(tokens[0])
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))
    scenario.game.destroy(scenario.creature("Hill Giant", "bob"))
    hand_before = len(scenario.player("alice").hand)

    alice = _flash_in_standard_bearer(scenario)

    assert len(alice.hand) == hand_before - 1 + 2


def test_standard_bearer_draws_nothing_when_nothing_died():
    scenario = _board(alice_hand=["Liliana's Standard Bearer"], forests=3)

    alice = _flash_in_standard_bearer(scenario)

    assert len(alice.hand) == 0
    assert len(alice.library) == 10

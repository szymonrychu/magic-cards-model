"""Scenario: "If this spell was cast from a graveyard, <alternative or extra>."

A flashback spell reading the zone it was actually cast from. CR 601.2a
moves the card "from where it is to the stack", and that zone is what
`CastRecord.origin_zone` records - so the condition asks where *this* spell
started, not whether it has flashback or whether the caster paid a flashback
cost. CR 614.1a makes the "instead" form a replacement of the base
instruction; the "also" form (Moment of Glory) is an extra instruction run
after the base one (CR 608.2c).

Printings: Plunder the Trollshaws (draw one / two instead), Tidings of War
(amass 1 / amass 3 instead, CR 701.47a), Moment of Glory (also counters on
each other creature you control), and off-set Secrets of the Key (investigate
/ investigate twice instead) - not a listed card and not in any deck pool,
which proves the condition reader is the template and not one sentence.

CR numbers verified with `mise run rules:find`: 601.2a, 702.34a, 614.1a,
608.2c, 701.47a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _board(*, hand=(), graveyard=(), battlefield=(), library=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            graveyard=list(graveyard),
            battlefield=list(battlefield),
            library=library if library is not None else ["Island"] * 6,
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _flashback(scenario, name: str, targets=None):
    casting = scenario.cast(name, from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    if targets is not None:
        casting.choose_targets(targets)
    scenario.auto_pay(casting.begin_paying())
    scenario.put_on_stack(casting)
    return scenario.resolve_top()


def test_listed_and_proof_printings_are_handled():
    for name in (
        "Plunder the Trollshaws",
        "Tidings of War",
        "Moment of Glory",
        "Secrets of the Key",
    ):
        support = card_support(card(name))
        assert support.status == "handled", (name, support)


# -- Plunder the Trollshaws: "Draw a card. ... draw two cards instead." ------


def test_plunder_from_hand_draws_one():
    scenario = _board(hand=["Plunder the Trollshaws"], battlefield=["Island"] * 2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    before = len(alice.hand)
    scenario.cast_and_resolve("Plunder the Trollshaws", auto=True)
    assert len(alice.hand) == before - 1 + 1


def test_plunder_flashed_back_draws_two_instead_and_is_exiled():
    scenario = _board(graveyard=["Plunder the Trollshaws"], battlefield=["Island"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    before = len(alice.hand)
    _flashback(scenario, "Plunder the Trollshaws")
    assert len(alice.hand) == before + 2
    assert [c.name for c in scenario.game.exile] == ["Plunder the Trollshaws"]


# -- Tidings of War: "Amass Goblins 1. ... amass Goblins 3 instead." ---------


def _army(scenario):
    (army,) = [c for c in scenario.game.battlefield if "Army" in (c.card.type_line or "")]
    return army


def test_tidings_from_hand_amasses_one():
    scenario = _board(hand=["Tidings of War"], battlefield=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Tidings of War", auto=True)
    assert _army(scenario).counter_count("+1/+1") == 1


def test_tidings_flashed_back_amasses_three_instead():
    scenario = _board(graveyard=["Tidings of War"], battlefield=["Mountain"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _flashback(scenario, "Tidings of War")
    assert _army(scenario).counter_count("+1/+1") == 3


# -- Moment of Glory: "... also put a +1/+1 counter on each other creature" -


def test_moment_of_glory_from_hand_counters_only_the_target():
    scenario = _board(
        hand=["Moment of Glory"], battlefield=["Plains", "Grizzly Bears", "Hill Giant"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_and_resolve("Moment of Glory", auto=True, targets=[bears])
    assert bears.counter_count("+1/+1") == 1
    assert giant.counter_count("+1/+1") == 0


def test_moment_of_glory_flashed_back_also_counters_each_other_creature_you_control():
    scenario = _board(
        graveyard=["Moment of Glory"],
        battlefield=["Plains"] * 5 + ["Grizzly Bears", "Hill Giant"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    opposing = scenario.creature("Grizzly Bears", "bob")
    _flashback(scenario, "Moment of Glory", targets=[bears])
    # The target gets exactly one: the extra instruction says "each *other*".
    assert bears.counter_count("+1/+1") == 1
    assert giant.counter_count("+1/+1") == 1
    assert opposing.counter_count("+1/+1") == 0


# -- Secrets of the Key: off-set proof of the same condition -----------------


def _clues(scenario):
    return [c for c in scenario.game.battlefield if c.name.startswith("Clue")]


def test_secrets_of_the_key_from_hand_investigates_once():
    scenario = _board(hand=["Secrets of the Key"], battlefield=["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Secrets of the Key", auto=True)
    assert len(_clues(scenario)) == 1


def test_secrets_of_the_key_flashed_back_investigates_twice_instead():
    scenario = _board(graveyard=["Secrets of the Key"], battlefield=["Island"] * 4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _flashback(scenario, "Secrets of the Key")
    assert len(_clues(scenario)) == 2


def test_a_copy_of_a_flashed_back_spell_was_not_cast_from_a_graveyard():
    """CR 707.10: a copy of a spell isn't cast, so the copy of a flashed-back
    Plunder the Trollshaws draws one card while the original draws two."""
    scenario = _board(
        hand=["Increasing Vengeance"],
        graveyard=["Plunder the Trollshaws"],
        battlefield=["Island"] * 4 + ["Mountain"] * 2,
        library=["Island"] * 10,
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    casting = scenario.cast("Plunder the Trollshaws", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 4))
    plunder = scenario.put_on_stack(casting)
    scenario.cast_onto_stack(
        "Increasing Vengeance",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[plunder],
    )
    hand_before = len(alice.hand)
    scenario.resolve_top()  # Increasing Vengeance: one copy of Plunder
    scenario.resolve_top()  # the copy draws one
    assert len(alice.hand) == hand_before + 1
    scenario.resolve_top()  # the flashed-back original draws two
    assert len(alice.hand) == hand_before + 3

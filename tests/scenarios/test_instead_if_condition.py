"""Scenario: G2a's "instead if" reader (CR 614.1a) on `Game.condition_holds`.

Two word orders print the identical replacement-effect shape, and this file
covers both:

- Galvanic Blast: "Galvanic Blast deals 2 damage to any target. Metalcraft —
  Galvanic Blast deals 4 damage instead if you control three or more
  artifacts." - the condition printed *last*, after "instead" (Metalcraft, an
  ability word, CR 207.2c - stripped before this ever sees it). The
  alternative clause elides "to any target" entirely: CR 601.2c already fixed
  the spell's target once, when it was announced, so the alternative reuses
  the base clause's own target rather than naming a new one.
- Brimstone Volley: "Brimstone Volley deals 3 damage to any target. Morbid —
  Brimstone Volley deals 5 damage instead if a creature died this turn." - the
  same shape, gated on a different ability word's condition (Morbid, CR
  207.2c), the proof that this reader is not fitted to either card by name.

Both conditions are read by `Game.condition_holds`, not a private table:
Metalcraft's "you control three or more artifacts" was already one of
`condition_holds`' own patterns (built for "Activate only if ..."); Morbid's
"a creature died this turn" is moved into `condition_holds` by this same
change, off the former `machines/effects._INSTEAD_CONDITIONS` dict.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 207.2c** - an ability word has "no special rules meaning"; it is only
  a label.
- **CR 601.2c** - a spell's target is announced once, as it is cast.
- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - a multi-clause instruction (or, here,
  a base-and-alternative pair) is read and checked as the object actually
  resolves, not before.
- **CR 614.1a** - "Effects that use the word 'instead' are replacement
  effects."
- **CR 700.4** - "The term dies means 'is put into a graveyard from the
  battlefield.'"

Regression coverage for every card `_INSTEAD_CONDITIONS` used to serve
(Gruesome Discovery's own "a creature died this turn", Twinned Vision's own
"this spell wasn't cast from your hand") stays in their own existing files -
`tests/scenarios/test_reveal_hand_and_choose.py` and
`tests/scenarios/test_modal_mode_composition.py` - and is re-run, not
duplicated here, to prove the retirement of that dict is behaviour-
preserving.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# ---------------------------------------------------------------------------
# Galvanic Blast - Metalcraft, "<alt> instead if <cond>."
# ---------------------------------------------------------------------------


def _blast_board(artifacts: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Galvanic Blast"], battlefield=["Mountain"] + artifacts)
        .player("bob")
    )


def test_galvanic_blast_deals_2_with_two_artifacts():
    """Metalcraft needs three or more; two is not enough - the base clause's
    own 2 damage applies."""
    scenario = _blast_board(["Ornithopter", "Mind Stone"]).build()
    _to_main(scenario)
    bob = scenario.player("bob")
    life_before = bob.life

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Galvanic Blast", mountain, targets=["bob"])

    assert bob.life == life_before - 2


def test_galvanic_blast_deals_4_with_three_artifacts_at_the_same_target():
    """Three artifacts satisfy Metalcraft: the alternative's own 4 damage
    replaces the base instruction whole (CR 614.1a), landing on the exact
    same target the base clause's own "to any target" named - the
    alternative clause never announces one of its own."""
    scenario = _blast_board(["Ornithopter", "Mind Stone", "Springleaf Drum"]).build()
    _to_main(scenario)
    bob = scenario.player("bob")
    life_before = bob.life

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Galvanic Blast", mountain, targets=["bob"])

    assert bob.life == life_before - 4


def test_galvanic_blast_checks_metalcraft_at_resolution_not_at_cast():
    """CR 608.2c: the condition is read as the spell *resolves*, not as it is
    announced. Galvanic Blast is cast with three artifacts on the board; in
    response, Abrade (a real pool removal spell) destroys one of them. By the
    time Galvanic Blast resolves only two artifacts remain, and the base
    clause's 2 damage applies - not the 4 Metalcraft would have given at cast
    time.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Galvanic Blast", "Abrade"],
            battlefield=[
                "Mountain",
                "Mountain",
                "Mountain",
                "Ornithopter",
                "Mind Stone",
                "Springleaf Drum",
            ],
        )
        .player("bob")
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    life_before = bob.life
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")

    (blast_mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_onto_stack("Galvanic Blast", blast_mountain, targets=["bob"])

    # In response: Abrade destroys one of the three artifacts.
    casting = scenario.cast("Abrade")
    casting.choose_modes(["Destroy target artifact"])
    casting.choose_targets([ornithopter])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain"))
    scenario.put_on_stack(casting)

    scenario.resolve_top()  # Abrade resolves first (LIFO).
    assert ornithopter.zone is Zone.GRAVEYARD

    scenario.resolve_top()  # Galvanic Blast now sees only two artifacts.

    assert bob.life == life_before - 2


# ---------------------------------------------------------------------------
# Brimstone Volley - Morbid, the same "<alt> instead if <cond>." shape gated
# on a different, unrelated condition - the proof this reader is not fitted
# to Galvanic Blast's own card.
# ---------------------------------------------------------------------------


def _volley_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Brimstone Volley"],
            battlefield=["Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
    )


def test_brimstone_volley_deals_3_with_no_creature_dead_this_turn():
    scenario = _volley_board().build()
    _to_main(scenario)
    bob = scenario.player("bob")
    life_before = bob.life

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Brimstone Volley", *sources, targets=["bob"])

    assert bob.life == life_before - 3


def test_brimstone_volley_deals_5_after_a_creature_died_this_turn():
    """Morbid (CR 700.4's "dies"): a different condition than Metalcraft, off
    the same `Game.condition_holds` dispatch, not a name-keyed table."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Brimstone Volley"],
            battlefield=["Mountain", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    _to_main(scenario)
    bob = scenario.player("bob")
    life_before = bob.life
    scenario.game.destroy(scenario.creature("Grizzly Bears", "alice"))

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Brimstone Volley", *sources, targets=["bob"])

    assert bob.life == life_before - 5

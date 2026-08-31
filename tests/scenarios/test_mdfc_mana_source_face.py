"""Scenario: a modal double-faced permanent's mana ability follows the face
that is up (CR 712.8d, 712.8f), not the whole printing.

The defect this covers, found in a real game (log seq 335-336): Witch
Enchanter // Witch-Blessed Meadow was on the battlefield front face up - a 2/2
creature with no mana ability of its own. Casting Starfield Shepherd
({3}{W}{W}) tapped it anyway, in the same `mana_sources` list as the real
lands, because the mana-payment path read the *whole card's* oracle text
(front and back) instead of the face that is actually up. Only the back face,
Witch-Blessed Meadow, prints `{T}: Add {W}.`; the front face's own text is
just "When this creature enters, destroy target artifact or enchantment an
opponent controls."

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 712.8d** - "While a double-faced permanent has its front face up, it
  has only the characteristics of its front face."
- **CR 712.8f** - "While a modal double-faced spell is on the stack or a modal
  double-faced permanent is on the battlefield, it has only the
  characteristics of the face that's up."
- **CR 712.12** - "A player playing a modal double-faced card ... as a land
  chooses one of its faces that's a land before putting it onto the
  battlefield. It enters the battlefield with that face up."
- **CR 109.3** - an object's characteristics include its abilities, so CR
  712.8d/712.8f's "only the characteristics of the face that's up" reaches a
  mana ability exactly the way it reaches a creature's power or a land's
  subtype.
- **CR 106.12** - "To 'tap [a permanent] for mana' is to activate a mana
  ability of that permanent that includes the {T} symbol in its activation
  cost."
- **CR 305.6** - the basic land types and the intrinsic `{T}: Add [colour].`
  ability they carry; exercised here to prove the fix does not special-case
  Witch Enchanter by name (`intrinsic_land_ability` is now face-aware too).

The root cause reached three call sites, all fixed the same way - by threading
`CardState.up_face_name` through, the same convention `activated_abilities_of`
already used for triggered and activated abilities:

- `machines/abilities.py::parse_mana_abilities` (and `intrinsic_land_ability`,
  its own fallback for a card with no *printed* mana ability).
- `machines/cost.py::free_tap_mana_abilities`/`free_tap_mana_ability`, and
  their callers `_auto_tap_candidates` (the auto-tap solver) and
  `_withheld_mana_sources` (the refusal message that names a withheld source).
- `machines/cost.py::CostPayment.tap_for_mana` itself, which used to trust an
  explicit, hand-picked source completely - exactly the path the real game's
  `mana_sources` list came in on. It now re-derives the source's own mana
  abilities off its up face and refuses a source that cannot actually make
  what it is being asked to make.

A second, related symptom shares the same shape: `machines/replacement.py`'s
`_self_enters_modifiers` (which reads a permanent's own "as this enters, you
may pay N life" ETB choice) read `parse_replacement_effects(card_state.card)`
unfiltered too, so casting Witch Enchanter's *creature* front face asked the
"pay 3 life" choice printed only on Witch-Blessed Meadow's *land* back face.
That is fixed the same way, filtered to `card_state.up_face_name`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_mana_abilities
from magic_cards_model.machines.cost import free_tap_mana_abilities
from magic_cards_model.models import Color, Type, Zone

from .harness import Scenario

# --------------------------------------------------------------------------
# The parser itself: the creature face has no mana ability at all
# --------------------------------------------------------------------------


def test_witch_enchanters_creature_face_parses_no_mana_ability():
    """Read straight off the face, with no game involved at all.

    `up_face_name` for a battlefield permanent sitting front face up is the
    front face's own name ("Witch Enchanter"), and neither `parse_mana_abilities`
    nor `free_tap_mana_abilities` may find Witch-Blessed Meadow's `{T}: Add
    {W}.` under that filter - it is printed on the other face entirely.
    """
    scenario = Scenario().player("alice", battlefield=["Witch Enchanter"]).build()
    witch = scenario.find("Witch Enchanter", Zone.BATTLEFIELD)

    assert witch.name == "Witch Enchanter"
    assert witch.up_face_name == "Witch Enchanter"
    assert witch.types == (Type.CREATURE,)

    assert parse_mana_abilities(witch.card, witch.up_face_name) == []
    assert free_tap_mana_abilities(witch.card, witch.up_face_name) == []

    # The unfiltered read (what the old code did) does find it - proving the
    # fix is the filter, not that the back face's ability stopped parsing.
    assert parse_mana_abilities(witch.card) != []


def test_witch_enchanters_creature_face_has_no_activatable_ability():
    """`Game.activated_abilities` - what a player is actually offered to
    activate - is empty for the creature face. There is nothing at index 0 to
    tap for {W} or for anything else.
    """
    scenario = Scenario().player("alice", battlefield=["Witch Enchanter"]).build()
    witch = scenario.find("Witch Enchanter", Zone.BATTLEFIELD)

    assert scenario.game.activated_abilities(witch) == []


# --------------------------------------------------------------------------
# The real defect: auto-tap must never reach for it
# --------------------------------------------------------------------------


def test_witch_enchanter_is_never_auto_tapped_and_an_underfunded_cast_fails():
    """The log's exact shape: Starfield Shepherd ({3}{W}{W}, 5 mana) with only
    4 real white sources on the battlefield plus Witch Enchanter sitting there
    as a creature.

    With the bug, `auto_tap` counted Witch Enchanter as a fifth white source
    (reading Witch-Blessed Meadow's `{T}: Add {W}.` off the back face) and the
    cast went through, tapping a creature with no mana ability for mana. Fixed,
    the four Plains are the only real mana on the board - one short of the
    cost - so the cast must fail, and Witch Enchanter must never be tapped at
    all, proven by asserting on the untapped flag afterward.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Starfield Shepherd"],
            battlefield=["Witch Enchanter", "Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    witch = scenario.find("Witch Enchanter", Zone.BATTLEFIELD)
    witch.summoning_sick = False  # isolate the mana-ability check from CR 302.6
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Starfield Shepherd", username="alice", auto=True)

    assert witch.untapped, "Witch Enchanter has no mana ability and must never be tapped"
    for plains in scenario.game.permanents_controlled_by("alice"):
        if plains.name == "Plains":
            assert plains.untapped, "a failed payment must leave every source untapped (CR 733.1)"
    assert scenario.player("alice").mana_pool.floating == {}


def test_witch_enchanter_plus_enough_real_lands_pays_without_touching_it():
    """The positive control: five real Plains cover Starfield Shepherd on
    their own, and Witch Enchanter - present on the battlefield the whole
    time - is still never tapped, because auto-tap never needed it and it was
    never a legal candidate regardless.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Starfield Shepherd"],
            battlefield=["Witch Enchanter"] + ["Plains"] * 5,
        )
        .player("bob")
        .build()
    )
    witch = scenario.find("Witch Enchanter", Zone.BATTLEFIELD)
    witch.summoning_sick = False
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Starfield Shepherd", username="alice", auto=True)

    assert witch.untapped
    tapped_plains = [
        p
        for p in scenario.game.permanents_controlled_by("alice")
        if p.name == "Plains" and p.tapped
    ]
    assert len(tapped_plains) == 5


def test_an_explicit_mana_sources_list_naming_witch_enchanter_is_refused():
    """The other half of the log's bug: an *explicit* source list, the shape
    the real API's `mana_sources` argument takes, must be validated exactly
    as strictly as the auto-tap solver - `CostPayment.tap_for_mana` itself now
    checks the source's own up-face abilities rather than trusting the caller.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Starfield Shepherd"], battlefield=["Witch Enchanter"])
        .player("bob")
        .build()
    )
    witch = scenario.find("Witch Enchanter", Zone.BATTLEFIELD)
    witch.summoning_sick = False
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Starfield Shepherd", username="alice")
    payment = casting.begin_paying()

    with pytest.raises(ValueError, match="Witch Enchanter"):
        payment.tap_for_mana(witch, [Color.WHITE])

    assert witch.untapped


# --------------------------------------------------------------------------
# The shared-cause ETB symptom: casting the creature face must not ask the
# land back face's "pay 3 life" choice
# --------------------------------------------------------------------------


def test_casting_the_creature_face_does_not_ask_the_lands_pay_life_choice():
    """Witch-Blessed Meadow's "As this land enters, you may pay 3 life. If you
    don't, it enters tapped." is printed on the back face alone. Casting the
    front face as a creature must never surface that choice - life must be
    unchanged and no decision pending - because `_self_enters_modifiers` must
    read only the face that is actually up (CR 712.8d), the same fix as the
    mana-ability path above, applied to `machines/replacement.py`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Witch Enchanter"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Witch Enchanter", [sol_ring])
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    before_life = scenario.player("alice").life
    witch = scenario.cast_and_resolve("Witch Enchanter", *sources)

    assert witch.zone is Zone.BATTLEFIELD
    assert witch.types == (Type.CREATURE,)
    assert scenario.player("alice").life == before_life, (
        "the land back face's pay-3-life ETB choice must not fire off the creature front"
    )


# --------------------------------------------------------------------------
# The converse: played as its land face, the mana ability DOES work
# --------------------------------------------------------------------------


def test_witch_blessed_meadow_the_land_face_auto_taps_for_white():
    """Played for its land face (CR 712.12), Witch-Blessed Meadow is now the
    face that's up (CR 712.8f) and its `{T}: Add {W}.` is exactly the ability
    the auto-tap solver must find - proving the fix filters *to* the up face,
    not just away from the other one.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter", "Swords to Plowshares"], library=["Plains"])
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_pay_the_life(True)

    meadow = scenario.play_land("Witch Enchanter")
    assert meadow.name == "Witch-Blessed Meadow"
    assert meadow.types == (Type.LAND,)
    assert meadow.untapped

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    scenario.cast_onto_stack("Swords to Plowshares", username="alice", targets=[bears], auto=True)

    assert meadow.tapped, "the land face's own mana ability paid the cost"
    assert scenario.player("alice").mana_pool.floating == {}

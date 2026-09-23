"""Scenario: playing the land face of a modal double-faced card (CR 712.12).

The user's report: Witch Enchanter // Witch-Blessed Meadow, played as a land,
was refused with "Witch Enchanter // Witch-Blessed Meadow is not a land". The
cause is a mirror image of the bug `Casting.base_cost` already had to work
around: Scryfall leaves an MDFC with no useful top-level reading for the face
that is not the front - `Card.is_land` only ever parses `front_type_line`
(CR 712.8a: outside the battlefield or stack, a double-faced card "has only
the characteristics of its front face"), so a creature-front, land-back card
like this one reads as a non-land no matter which face a player means to play.

- **CR 712.12** - "A player playing a modal double-faced card or a copy of a
  modal double-faced card as a land chooses one of its faces that's a land
  before putting it onto the battlefield. It enters the battlefield with that
  face up." Verified this session against the live CR search and cross-checked
  against the 2026-02-27 text at `mtg-legacy/data/comprehensive-rules.txt`,
  which agrees word for word.
- **CR 712.8f** - "While a modal double-faced spell is on the stack or a modal
  double-faced permanent is on the battlefield, it has only the characteristics
  of the face that's up." So once Witch-Blessed Meadow is the face that is up,
  the permanent is a land with that name and that `{T}: Add {W}` ability, not a
  creature with "when this creature enters, destroy target artifact or
  enchantment an opponent controls" - that line was printed on Witch
  Enchanter's face, not the one that's up.
- There is no separate "play the land face" special action: CR 712.12 sits
  inside the same CR 305.1 land drop as ordinary land plays, so it is refused
  and counted exactly like any other land.

Every fixture below is a real MDFC with a land back face:
Witch Enchanter // Witch-Blessed Meadow, Valakut Awakening // Valakut
Stoneforge, Shatterskull Smashing // Shatterskull, the Hammer Pass, Sink into
Stupor // Soporific Springs, and Turntimber Symbiosis // Turntimber,
Serpentine Wood - covering both shapes of land back (an unconditional "enters
tapped" and the "you may pay 3 life" shockland-style choice) and both shapes
of front (a creature and three spells).

## The observer-side half of the same bug

The tests above cover *the entering permanent's own* trigger - CR 712.8f
correctly denies Witch-Blessed Meadow the creature face's "when this creature
enters" line. A second, real-game defect was a different object entirely:
Guide of Souls ("Whenever another creature you control enters, you gain 1 life
and get {E}") fired anyway when a player played Witch Enchanter for its land
face - a Land entered, not a Creature, and Guide of Souls should never have
triggered.

The cause was `Game._enters_event` handing `condition_matches` the raw
`Card` (`permanent.card`), whose `.types` reads `Card.front_type_line`
(structurally the front face, CR 712.8a) rather than `CardState.types`, which
is already up-face aware (`land_face_played`/`up_face`). `GameEvent` now
carries `subject_types`/`subject_subtypes` computed from the `CardState` at
the moment each event is built, and every type-or-subtype check in
`machines/triggers.py` (`_types_match`, `_subtype_matches`, and
`_first_spell_this_turn_holds`'s `_category_matches`) reads those instead of
the raw printing - CR 603.10 checks the object "as it exists" at the trigger
event, and for an entering permanent that is the face that's actually up.

The same bug has an unreported mirror image: "Landfall — Whenever a land you
control enters, ..." (an ordinary CR 603.6a enters-the-battlefield trigger,
Landfall being an ability word with no rules meaning of its own, CR 207.2c)
could never fire off *any* MDFC-with-a-land-face fixture, because their
front faces are
Creature/Instant/Sorcery and the raw `Card.types` read never saw the land that
actually entered. Both directions are tested together below, in one game,
because a fix that only silences the false positive and leaves the false
negative unnoticed is half a fix wearing a passing test suite.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Type, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- the user's report -------------------------------------------------------


def test_the_creature_front_mdfcs_land_face_can_be_played():
    """Witch Enchanter // Witch-Blessed Meadow, played for its land, CR 712.12."""
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    meadow = scenario.play_land("Witch Enchanter")

    assert meadow.zone is Zone.BATTLEFIELD
    assert meadow.name == "Witch-Blessed Meadow"
    assert meadow.types == (Type.LAND,)
    assert not scenario.game.can_play_land("alice"), "the land drop is used"


def test_the_land_face_enters_untapped_by_default_paying_the_life():
    """CR 119.4/608.2d default: an unanswered "you may pay life" is paid when
    legal, so Witch-Blessed Meadow enters untapped at 20 life and can tap for
    its own mana the same turn - lands have no summoning sickness restriction.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    meadow = scenario.play_land("Witch Enchanter")

    assert meadow.untapped
    assert scenario.player("alice").life == 17, "paid 3 life to skip entering tapped"

    scenario.activate(meadow)
    assert scenario.player("alice").mana_pool.floating == {Color.WHITE: 1}


def test_the_land_face_enters_tapped_when_the_life_is_refused():
    """The other branch of the same choice: refuse the life, enter tapped."""
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)
    scenario.will_pay_the_life(False)

    meadow = scenario.play_land("Witch Enchanter")

    assert meadow.tapped
    assert scenario.player("alice").life == 20


def test_the_land_face_does_not_carry_the_creature_faces_trigger():
    """CR 712.8f: only the face that's up has characteristics, so the "when
    this creature enters, destroy target artifact" line - printed on Witch
    Enchanter, not Witch-Blessed Meadow - never triggers off a land drop.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Witch Enchanter"], library=["Plains"])
        .player("bob", library=["Plains"], battlefield=["Sol Ring"])
        .build()
    )
    _to_main(scenario)

    scenario.play_land("Witch Enchanter")

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty, "the creature face's trigger did not fire off a land drop"
    assert scenario.find("Sol Ring", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_the_same_card_cast_normally_still_fires_its_creature_trigger():
    """The control for the test above: cast as a creature, front face up, the
    trigger is exactly as live as it always was - the land-face filter only
    ever applies to a permanent that actually entered via `play_land`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Witch Enchanter"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
            library=["Plains"],
        )
        .player("bob", library=["Plains"], battlefield=["Sol Ring"])
        .build()
    )
    _to_main(scenario)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Witch Enchanter", [sol_ring])
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    witch = scenario.cast_and_resolve("Witch Enchanter", *sources)
    assert witch.zone is Zone.BATTLEFIELD
    assert witch.types == (Type.CREATURE,)

    scenario.pass_until_resolved()

    assert sol_ring.zone is Zone.GRAVEYARD, "the enters trigger fired and destroyed it"


# -- the other shape: an instant/sorcery front, no other trigger to leak -----


def test_valakut_awakenings_land_face_enters_tapped_unconditionally():
    """Valakut Stoneforge just says "This land enters tapped." - no choice."""
    scenario = (
        Scenario()
        .player("alice", hand=["Valakut Awakening"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    stoneforge = scenario.play_land("Valakut Awakening")

    assert stoneforge.zone is Zone.BATTLEFIELD
    assert stoneforge.name == "Valakut Stoneforge"
    assert stoneforge.types == (Type.LAND,)
    assert stoneforge.tapped
    assert not scenario.game.can_play_land("alice")


def test_shatterskull_smashings_land_face_can_be_played_and_taps_for_red():
    scenario = (
        Scenario()
        .player("alice", hand=["Shatterskull Smashing"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    hammer_pass = scenario.play_land("Shatterskull Smashing")

    assert hammer_pass.name == "Shatterskull, the Hammer Pass"
    assert hammer_pass.types == (Type.LAND,)
    assert hammer_pass.untapped, "paid the life by default"

    scenario.activate(hammer_pass)
    assert scenario.player("alice").mana_pool.floating == {Color.RED: 1}


def test_sink_into_stupors_land_face_can_be_played_and_taps_for_blue():
    scenario = (
        Scenario()
        .player("alice", hand=["Sink into Stupor"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    springs = scenario.play_land("Sink into Stupor")

    assert springs.name == "Soporific Springs"
    assert springs.types == (Type.LAND,)
    scenario.activate(springs)
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}


def test_turntimber_symbiosiss_land_face_can_be_played_and_taps_for_green():
    scenario = (
        Scenario()
        .player("alice", hand=["Turntimber Symbiosis"], library=["Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    wood = scenario.play_land("Turntimber Symbiosis")

    assert wood.name == "Turntimber, Serpentine Wood"
    assert wood.types == (Type.LAND,)
    scenario.activate(wood)
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 1}


# -- an ordinary land is unaffected -------------------------------------------


def test_a_plain_land_is_still_unaffected_by_the_land_face_lookup():
    """A single-faced card has no `card_faces`, so `Card.land_face` is None and
    the ordinary `Card.is_land` branch is the one that admits it - unchanged.
    """
    scenario = Scenario().player("alice", hand=["Forest"]).player("bob").build()
    _to_main(scenario)

    forest = scenario.play_land("Forest")

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.name == "Forest"


# -- the observer-side bug: an MDFC land drop is not a creature entering -----


def test_witch_blessed_meadow_does_not_trigger_guide_of_souls_but_a_real_creature_still_does():
    """The exact real-game defect, both halves in one game.

    Alice controls Guide of Souls ("Whenever another creature you control
    enters, you gain 1 life and get {E}") at 18 life with 2 energy already -
    the numbers from the reported game. Playing Witch Enchanter for its land
    face must change neither: a Land entered, not a Creature (CR 712.8f), so
    `_types_match`'s "creature" requirement must see `CardState.types` (the up
    face) and refuse. Then, in the same game, casting an ordinary creature
    (Grizzly Bears) must still trigger Guide of Souls exactly once - proving
    the type check was actually evaluated and not simply forced closed, which
    is trap #6: a test that only checks "no trigger on the land" would pass
    just as well if the type check were broken into always-False.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            life=18,
            hand=["Witch Enchanter", "Grizzly Bears"],
            battlefield=["Guide of Souls", "Forest", "Forest"],
            library=["Plains"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.player("alice").add_counters(Counter.ENERGY, 2)
    _to_main(scenario)
    scenario.will_pay_the_life(False)  # isolate the trigger check from the life-payment choice

    meadow = scenario.play_land("Witch Enchanter")

    assert meadow.zone is Zone.BATTLEFIELD
    assert meadow.types == (Type.LAND,)
    assert scenario.pending_triggers == [], (
        "a Land entering is not a Creature entering (CR 712.8f) - Guide of "
        "Souls must not have triggered"
    )
    assert scenario.game.stack_is_empty, (
        "no trigger should have gone on the stack, so nothing is left "
        "unresolved for the land drop to have caused"
    )
    assert scenario.player("alice").life == 18
    assert scenario.player("alice").energy == 2

    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Grizzly Bears", *sources)
    assert scenario.stack_names() == ["Guide of Souls's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 19, "a real creature entering still triggers it"
    assert scenario.player("alice").energy == 3


def test_landfall_fires_when_an_mdfcs_land_face_is_played():
    """The unreported false-negative half: Icetill Explorer's Landfall
    ("Whenever a land you control enters, mill a card", CR 603.6a - an
    ordinary enters-the-battlefield trigger) must fire off Witch-Blessed
    Meadow entering exactly as it does off a plain Forest
    (`test_icetill_explorer_mills_a_card_on_landfall` in
    `test_player_effect_parser.py`) - the land actually on the battlefield,
    not the front face's Creature type nobody asked the permanent to have.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Witch Enchanter"],
            library=["Mountain"],
            battlefield=["Icetill Explorer"],
        )
        .player("bob", library=["Plains"])
        .build()
    )
    _to_main(scenario)

    scenario.play_land("Witch Enchanter")
    scenario.pass_until_resolved()

    assert [state.card.name for state in scenario.player("alice").graveyard] == ["Mountain"]


def test_hydroelectric_laboratory_enters_untapped_for_three_life():
    """Hydroelectric Specimen // Hydroelectric Laboratory's land face: "As
    this land enters, you may pay 3 life. If you don't, it enters tapped."
    Paid, it enters untapped and taps for {U} at once."""
    scenario = (
        Scenario()
        .player("alice", hand=["Hydroelectric Specimen"], library=["Island"])
        .player("bob", library=["Island"])
        .build()
    )
    _to_main(scenario)
    scenario.will_pay_the_life(True)

    laboratory = scenario.play_land("Hydroelectric Specimen")

    assert laboratory.name == "Hydroelectric Laboratory"
    assert laboratory.untapped
    assert scenario.player("alice").life == 17
    scenario.activate(laboratory)
    assert scenario.player("alice").mana_pool.floating == {Color.BLUE: 1}


def test_hydroelectric_laboratory_enters_tapped_when_the_life_is_refused():
    scenario = (
        Scenario()
        .player("alice", hand=["Hydroelectric Specimen"], library=["Island"])
        .player("bob", library=["Island"])
        .build()
    )
    _to_main(scenario)
    scenario.will_pay_the_life(False)

    laboratory = scenario.play_land("Hydroelectric Specimen")

    assert laboratory.tapped
    assert scenario.player("alice").life == 20

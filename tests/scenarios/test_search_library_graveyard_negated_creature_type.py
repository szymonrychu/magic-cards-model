""" "Search your library and/or graveyard for a non-`<subtype>` creature card
[with mana value X or less] and put it onto the battlefield. If you search
your library this way, shuffle." - Invasion of Ikoria's own ETB, and the
identical negated-creature-type quality on Kinnan, Bonder Prodigy's activated
ability (a different macro-shape: a look-at-the-top-N-and-may-put-onto-the-
battlefield search, not a tutor).

Verified this session with `mise run rules:find`:

- **CR 701.23a** - "find a card that matches the given description" is the
  meaning of "search ... for a[n] `<quality>` card".
- **CR 701.23d** - searching more than one zone in the same instruction
  ("library and/or graveyard") is one search, and "and/or" makes searching
  each named zone optional independently.
- **CR 701.24a** - a library that was searched (whether or not a legal card
  was found) is shuffled afterward.
- **CR 107.3a** - X is fixed as the spell announcing it is cast, and every
  later reference to that X (including a triggered ability its resolution
  raises once the spell becomes a permanent) reads the same fixed value.
- **CR 205.3m** - creature types (e.g. Human) are subtypes, not card types.
- **CR 702.140a** - mutate's own rules text is Wizards' own official use of
  "a non-Human creature" as the templated description of a card lacking a
  named creature type, confirming "non-`<subtype>`" is read as a negation of
  that one subtype rather than of a card type (CR 109.2 covers card-type
  negation like "nonland"; this is the parallel reading one level down, at
  CR 205.3's subtype).

`_named_type_matcher`/`_search_quality_is_readable`
(`magic_cards_model.machines.effects`) previously read a bare "non`<type>`"
word only as CR 109.2's card-type negation (Ugin, Eye of the Storms' own
"colorless nonland cards"), so "non-Human creature" fell through to "matches
nothing" - a search that silently never offered a real candidate. The fix
reuses `_parse_card_group_qualifier`'s own `_NON_SUBTYPE_PREFIX_RE` (already
proven on Overlord of the Balemurk's "non-Avatar creature card" and
Sunderflock's "non-Elemental creatures" in a *mass-instruction* context)
rather than a second copy, so the identical negated-subtype grammar now
reads the same way whether it appears in a search's stated quality or a mass
instruction's.

Kinnan, Bonder Prodigy's own "{5}{G}{U}: Look at the top five cards of your
library. You may put a non-Human creature card from among them onto the
battlefield. Put the rest on the bottom of your library in a random order."
is the generality proof: a different macro-shape (an impulsive look-at-the-
top-N, not a tutor search of two zones) sharing only the one piece this wave
actually changed - the negated-creature-type quality word - and a card this
wave's own author had never looked at while writing the fix above.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

IKORIA = "Invasion of Ikoria"
"""Battle - Siege, {X}{G}{G}, defense 6 // Zilortha, Apex of Ikoria."""

KINNAN = "Kinnan, Bonder Prodigy"


def _cast_ikoria(scenario, x_value: int, *sources):
    casting = scenario.cast(IKORIA, username="alice")
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.game.put_triggers_on_stack()


def test_finds_a_non_human_creature_and_skips_a_human_one_in_the_graveyard():
    """Both cards are legal candidates by mana value (X=2); only the
    non-Human one (Memnite, a 0-mana Construct) may be offered - Thraben
    Inspector, a Human, never appears among the choices at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            graveyard=["Memnite", "Thraben Inspector"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "alice")
    thraben_inspector = scenario.find("Thraben Inspector", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.will_take_the_may(False, username="alice", source=IKORIA)  # decline the library too
    scenario.will_choose_cards(memnite, username="alice")
    _cast_ikoria(scenario, 2, *sources)
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.BATTLEFIELD
    assert memnite.controller == "alice"
    assert thraben_inspector.zone is Zone.GRAVEYARD, "a Human creature is never a legal candidate"


def test_a_graveyard_creature_over_x_is_never_offered_and_library_shuffles_when_searched():
    """Solemn Simulacrum (mana value 4, a Construct) is over X=2 and is never
    a candidate; Elvish Mystic (mana value 1, an Elf) in the library is
    within X and is found, and searching the library shuffles it (CR
    701.24a) regardless of what was found."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[IKORIA],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            graveyard=["Solemn Simulacrum"],
            library=["Elvish Mystic", "Mountain", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    solemn = scenario.find("Solemn Simulacrum", Zone.GRAVEYARD, "alice")
    elvish_mystic = scenario.find("Elvish Mystic", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.will_take_the_may(True, username="alice", source=IKORIA)  # search the library too
    scenario.will_choose_cards(elvish_mystic, username="alice")
    _cast_ikoria(scenario, 2, *sources)
    scenario.pass_until_resolved()

    assert elvish_mystic.zone is Zone.BATTLEFIELD
    assert elvish_mystic.controller == "alice"
    assert solemn.zone is Zone.GRAVEYARD, "mana value 4 is over X=2"
    remaining_library = scenario.player("alice").library
    assert {state.name for state in remaining_library} == {"Mountain", "Island"}


def test_kinnan_offers_only_the_non_human_creature_among_the_top_five():
    """A different macro-shape (impulsive look-at-the-top-five, not a search
    of two zones) sharing the identical negated-creature-type quality word -
    the generality proof for this wave's own fix."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                KINNAN,
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Island",
                "Island",
            ],
            library=["Thraben Inspector", "Memnite", "Mountain", "Plains", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    thraben_inspector, memnite = alice.library[0], alice.library[1]
    kinnan = scenario.creature(KINNAN, "alice")
    sources = scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Forest", "Island", "Island"
    )

    scenario.will_take_the_may(True, username="alice", source=KINNAN)
    scenario.will_choose_cards(memnite, username="alice")
    scenario.activate(kinnan, *sources)
    scenario.pass_until_resolved()

    assert memnite.zone is Zone.BATTLEFIELD
    assert thraben_inspector.zone is Zone.LIBRARY, "a Human creature is never a legal candidate"


def test_kinnans_triggered_mana_ability_doubles_a_nonland_source_only():
    """Kinnan's first ability, a triggered mana ability (CR 605.1b): tapping
    Llanowar Elves adds one more {G}; tapping a Forest (a land) adds none."""
    from magic_cards_model.models.card import Color

    scenario = (
        Scenario()
        .player("alice", battlefield=["Kinnan, Bonder Prodigy", "Llanowar Elves", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    elves.summoning_sick = False

    scenario.activate(elves)
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 2}
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(forest)
    assert scenario.player("alice").mana_pool.floating == {Color.GREEN: 3}

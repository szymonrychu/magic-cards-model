"""Scenario: Green Sun's Zenith - CR 107.3a's `{X}` bound into a library
search (CR 701.23a/701.23b), and a spell that shuffles *itself* into its
owner's library instead of the ordinary trip to the graveyard.

Reported live: casting Green Sun's Zenith for X=1 with Delighted Halfling (a
green, mana value 1 creature) on the battlefield logged `resolved: "Green
Sun's Zenith", changed: false` - no search decision offered, no creature
entered, the card went to the graveyard, and no notice was recorded anywhere.

Searching itself is not unbuilt - `Game.search_library`, `_search_library`,
`parse_search_and_put_effect`, and the fetchland family all already work (see
`test_search_as_a_clause.py`, `test_shuffling.py`). Two separate things in
this one card's text broke the whole resolution, and either alone would have
been enough on its own:

1. **The X was never substituted into the search's own bound.**
   `_SEARCH_AND_PUT_RE`'s `max_mv` group is `\\d+` - it cannot match the
   letter X - and CR 107.3a's chosen X, though it *was* already being
   recorded on the cast record (`Casting.x_value`, read back by
   `Game.cast_record`, and already used by Wrath of the Skies and Kozilek's
   Command's own X-reading effects), was never substituted into a plain
   spell's resolution text before dispatch. `effect_for` now does that
   substitution - see its own docstring for why the *unsubstituted* text is
   tried first (Wrath of the Skies's own X-reading parser needs the literal
   word "X" left alone, or it stops matching its own shape).
2. **The second sentence poisoned the first.** "Search your library ... put
   it onto the battlefield, then shuffle." and "Shuffle Green Sun's Zenith
   into its owner's library." are two CR 608.2c clauses, and the second
   matches no clause shape `_parse_mixed_clause` reads - so
   `_parse_mixed_clauses`' fail-closed policy (correctly: CR 608.2c has no
   notion of running half an effect) took the *whole* text down, search
   included, even once X was fixed. `effect_for` now strips that one sentence
   by the resolving card's own name before dispatch (`_strip_self_shuffle_
   clause`) - genuinely by name, not a per-card row, so any future card
   printed the same way reads for free - and `machines/replacement.py`'s
   `_stack_replacements` reads the *same* sentence off the same oracle text
   to redirect where the card actually goes as it leaves the stack (CR
   304.2/307.2, CR 715.3d's own "instead of graveyard, elsewhere" shape).

Both fixes are independent and both were necessary: fixing only (1) still
left the whole effect `None` (the self-shuffle sentence still poisoned the
search clause), and fixing only (2) still left the search unable to read "or
less" than a digit it never had.

Every CR number below was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.

- **CR 701.23a** - to search a zone (hidden or not) is to look at every card
  in it and find one matching the description.
- **CR 701.23b** - a search for a *stated quality* (a green creature card
  with mana value X or less) is never required to find one, even if one is
  there.
- **CR 701.24a/c** - to shuffle is to randomize; "if an effect would cause a
  player to shuffle one or more specific objects into a library, that library
  is shuffled even if none of those objects are in the zone they're expected
  to be in" - Green Sun's Zenith shuffling *itself* in, straight off the
  stack, is exactly this.
- **CR 107.3a** - X for a spell with `{X}` in its own mana cost is fixed at
  announcement, by the caster, and applies throughout the spell's text while
  it is on the stack.
- **CR 304.2/307.2** - "the actions stated in [a sorcery's] rules text are
  followed. Then it's put into its owner's graveyard" - the ordering that
  lets an earlier one-shot effect (the self-shuffle) pre-empt the later one.
- **CR 701.6a** - countering removes a spell from the stack; "it doesn't
  resolve and none of its effects occur" - so a countered Green Sun's Zenith
  is never shuffled anywhere but the graveyard, the ordinary way.
- **CR 302.6** - a creature has not been under its controller's control
  since their most recent turn began the instant it enters.

**Not attempted here**: a copied Green Sun's Zenith. CR 707.10a/CR 111.13
already make this a non-issue in a different, pre-existing way - a copy of a
non-permanent spell "in a zone other than the stack ... ceases to exist", and
this engine has no spell-copying primitive at all (no card, no harness call,
nothing in `machines/` builds one), so there is no real board this file could
stage without inventing a mock copy effect, which CLAUDE.md bans outright.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- The reported defect: X=1, a legal green creature at mana value 1 -------


def test_green_suns_zenith_finds_a_legal_creature_at_x_one():
    """The exact reported case: X=1, Delighted Halfling (green, mana value 1)
    in the library. The search must actually run and put it onto the
    battlefield - not into hand, and not left for a decision that is never
    asked, since the printed text has no "you may" in front of "search".
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest"],
            library=["Delighted Halfling"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    zenith = scenario.resolve_top()

    halfling = scenario.find("Delighted Halfling", Zone.BATTLEFIELD)
    assert halfling.zone is Zone.BATTLEFIELD
    assert zenith.zone is Zone.LIBRARY


def test_the_found_creature_enters_summoning_sick():
    """CR 302.6: found onto the battlefield is still entering it - the
    creature has not been under alice's control since her most recent turn
    began, so it cannot attack or use a `{T}` ability this turn.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest"],
            library=["Delighted Halfling"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    halfling = scenario.find("Delighted Halfling", Zone.BATTLEFIELD)
    assert halfling.is_summoning_sick is True


def test_a_different_x_scales_the_search_bound():
    """X=2 legally finds Grizzly Bears (green, mana value 2) where X=1 could
    not have - not a coincidence that one particular X happens to work.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


# -- X=0, and a legal-but-empty search ---------------------------------------


def test_x_zero_is_a_legal_search_that_finds_nothing_above_its_own_bound():
    """CR 701.23b: "mana value 0 or less" excludes Delighted Halfling (mana
    value 1) - a legal search that simply finds nothing, not a refusal to
    search at all. The card stays in the library, no permanent enters, and
    the self-shuffle still runs (the search's own failure and the spell's own
    resolution are two different things - CR 608.2c's clauses both still run).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest"],
            library=["Delighted Halfling"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    zenith = scenario.resolve_top()

    assert scenario.battlefield_names() == ["Forest"]
    assert zenith.zone is Zone.LIBRARY
    assert scenario.find("Delighted Halfling", Zone.LIBRARY).zone is Zone.LIBRARY


def test_a_creature_of_the_wrong_color_is_not_a_legal_find_whatever_x_is():
    """The stated quality is "a **green** creature card", not just a mana
    value ceiling - Delver of Secrets (blue, mana value 1) is under any X
    chosen here but is never a legal find, the same as a shockland's own
    printed land types exclude Wastes.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Delver of Secrets"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    zenith = scenario.resolve_top()

    assert scenario.battlefield_names() == ["Forest", "Forest", "Forest", "Forest"]
    assert scenario.find("Delver of Secrets", Zone.LIBRARY).zone is Zone.LIBRARY
    assert zenith.zone is Zone.LIBRARY


def test_an_empty_library_still_self_shuffles():
    """CR 701.24d/e: shuffling happens even with nothing (or one card) to
    shuffle - an empty library is searched (finds nothing, legally, CR
    701.23b) and then still receives exactly one card: Green Sun's Zenith
    itself.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest"],
            library=[],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    zenith = scenario.resolve_top()

    assert [state.card.name for state in scenario.player("alice").library] == ["Green Sun's Zenith"]
    assert zenith.zone is Zone.LIBRARY


# -- The self-shuffle replaces the graveyard trip, only when it happens -----


def test_a_countered_green_suns_zenith_goes_to_the_graveyard_not_the_library():
    """CR 701.6a: a countered spell "doesn't resolve and none of its effects
    occur". The self-shuffle is one of those effects - it is stated in the
    spell's own rules text, which a countered spell never follows - so this
    is the ordinary graveyard trip, not the replaced one. No search happens
    either: Delighted Halfling stays exactly where it started.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Green Sun's Zenith"],
            battlefield=["Forest", "Forest"],
            library=["Delighted Halfling"],
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Green Sun's Zenith")
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    zenith = scenario.put_on_stack(casting)

    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[zenith])
    scenario.pass_until_resolved()  # Counterspell resolves, countering Zenith

    assert zenith.zone is Zone.GRAVEYARD
    assert [state.card.name for state in scenario.player("alice").library] == ["Delighted Halfling"]


def test_no_x_and_no_self_shuffle_row_shadows_the_dispatcher():
    """`EFFECTS` must not have re-grown a Green Sun's Zenith row - the fix is
    the generic X-substitution-then-dispatch path in `effect_for` plus the
    generic self-shuffle detection in `machines/replacement.py`, not a
    per-card entry, and an explicit row would silently shadow both.
    """
    from magic_cards_model.machines.effects import EFFECTS

    assert "Green Sun's Zenith" not in EFFECTS


# -- Nature's Rhythm: the same X-valued search, poisoned by a second keyword
# ability on its own second line rather than by a missing X substitution ----
#
# "Search your library for a creature card with mana value X or less, put it
# onto the battlefield, then shuffle.\nHarmonize {X}{G}{G}{G}{G} (...)" -
# `docs/engine-coverage.md` already named this gap: the X-substitution half of
# the Green Sun's Zenith fix (above) already made "mana value X or less"
# readable, but Harmonize's own line (CR 702.180, CR 702.180a - a static
# ability granting an alternative cast permission from the graveyard, never a
# CR 608.2c resolution instruction) was not one of `_strip_non_effect_
# preamble`'s recognised keyword lines, so `split_effect_clauses` read it as a
# second, unparseable clause and `_parse_mixed_clauses`'s fail-closed policy
# took the real search down with it - exactly the Suspend/Cascade/Replicate/
# Cycling bug this file's own module docstring already describes, for a
# keyword this engine still does not otherwise build (casting from the
# graveyard, tapping a creature to discount the cost - `_HARMONIZE_LINE_RE`
# only stops the line from poisoning an unrelated sentence, same as those).


def test_natures_rhythm_finds_a_legal_creature_at_x_two():
    """The exact shape `docs/engine-coverage.md` named as still broken: X=2
    legally finds Grizzly Bears (mana value 2), and the Harmonize line below
    the real effect must not have taken the search down with it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nature's Rhythm"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    casting = scenario.cast("Nature's Rhythm")
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    rhythm = scenario.resolve_top()

    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert rhythm.zone is Zone.GRAVEYARD


def test_natures_rhythm_at_x_zero_finds_nothing_above_its_own_bound():
    """CR 701.23b again: a legal search that simply finds nothing, since
    Grizzly Bears (mana value 2) is over an X=0 ceiling. Nature's Rhythm's
    own cost is {X}{G}{G}, so X=0 still needs two green mana to cast at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nature's Rhythm"],
            battlefield=["Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    casting = scenario.cast("Nature's Rhythm")
    casting.determine_cost(x_value=0)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.battlefield_names() == ["Forest", "Forest"]
    assert scenario.find("Grizzly Bears", Zone.LIBRARY).zone is Zone.LIBRARY


def test_no_natures_rhythm_row_shadows_the_dispatcher():
    """The same guard as Green Sun's Zenith's own row check above: the fix is
    the generic `_HARMONIZE_LINE_RE` strip, not a per-card `EFFECTS` entry."""
    from magic_cards_model.machines.effects import EFFECTS

    assert "Nature's Rhythm" not in EFFECTS

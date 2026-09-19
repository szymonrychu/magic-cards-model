"""Regression tests for `scripts/sweep_pool.py`.

The sweeper's silent count is the project's headline work-queue metric
(`CLAUDE.md`, `docs/engine-coverage.md`), and it drifted twice in the same way:
`classify_card` called the production dispatchers with no chosen X (CR
107.3a) and with a combined "A // B" name/text for a split or modal
double-faced card, so a card that works end to end in a real game
(`tests/scenarios/test_x_valued_search_and_self_shuffle.py`,
`tests/scenarios/test_split_cards.py`) still read as silent here. Nothing
caught that because the sweeper itself had no tests - these do, and each
regression below is paired with the scenario file that already proves the
underlying engine behaviour works, so a future change to `scripts/sweep_pool.py`
cannot silently reopen the same gap.

The second half of the file pins the three measurement defects that made a
whole day of gap reports wrong: `has_rules_text` skipping a permanent's static
lines (so Grafdigger's Cage read as clean), `classify_card` reporting the best
outcome per card (so Territorial Kavu's dead characteristic-defining ability
hid behind its working trigger), and the layer near-miss detector failing
*open* on a real unmodelled anthem (so Stormscale Scion produced no notice at
all). Each is paired with the card that exposed it.
"""

import pytest
from scripts.sweep_pool import (
    HANDLED,
    NOTICE,
    QUOTED_EFFECT,
    SILENT,
    STATIC_UNAUDITED,
    UNMATCHABLE_CONDITION,
    _condition_can_fire,
    _effect_matched_inside_quotes,
    _intended_token_requirement,
    _spell_faces,
    _worse,
    _x_candidates,
    classify_card,
    classify_clauses,
    has_rules_text,
    ignored_keywords,
    missed_layer_shape,
)

from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.effects import (
    _DAMAGE_EACH_CREATURE_RE,
    _DAMAGE_EACH_OPPONENT_RE,
    trigger_effect_for,
)
from magic_cards_model.machines.triggers import (
    _STATE_COUNTER_TRIGGER_RE,
    _unread_trigger_events,
)
from tests.cards import card, pool

# -- The baseline: a plain card must classify honestly in both directions ---


def test_a_card_that_works_classifies_as_handled():
    """Lightning Bolt has no X, no extra faces, and a plain targeted-damage
    row - the sweeper's simplest possible "this really does something" case.
    """
    category, _ = classify_card(card("Lightning Bolt"))
    assert category == HANDLED


def test_a_card_with_a_genuine_gap_still_classifies_as_silent():
    """Keen-Eyed Curator's "As long as there are four or more card types among
    cards exiled with this creature, it gets +4/+4 and has trample." is a
    still-open gap: `machines/layers._GRAVEYARD_CARD_TYPES_GATED_SELF_STATIC_RE`
    reads the delirium-shaped twin of this sentence, but nothing in
    `LayerContext` knows which cards were exiled *with a particular permanent*,
    so the whole bonus happens nowhere. Fixing the classifier must never make a
    genuinely-dead card look alive: this is the control for that.

    (Rancor stood here while "Enchanted creature ..." was unreadable. It is
    read now - see `tests/scenarios/test_attached_creature_statics.py` - so it
    would be a control that controls nothing.)

    (Grand Arbiter Augustin IV used to be this control, on the reading that
    its cost-modifier statics reached no notice at all. Measured today, two of
    its three lines are read by `machines/cost.cost_modifier_effect` and the
    third records a `CostModifierNotice` - see
    `test_a_cost_modifier_static_that_fails_closed_is_a_notice`, which now
    pins that card instead. Three earlier examples of the identical kind had
    already been closed the same way: March of Otherworldly Light's
    two-sentence additional-cost preamble, Blood Artist's back-to-back
    "target player loses 1 life and you gain 1 life" clauses, and History of
    Benalia's Saga chapters.)
    """
    category, _ = classify_card(card("Keen-Eyed Curator"))
    assert category == SILENT


def test_a_cost_modifier_static_that_fails_closed_is_a_notice():
    """Grand Arbiter Augustin IV: "White/Blue spells you cast cost {1} less to
    cast" is read by `machines/cost.cost_modifier_effect`, and "Spells your
    opponents cast cost {1} more to cast" is controller-relative in a way its
    shapes do not cover - `looks_like_unparsed_cost_modifier` catches it and
    `Game.total_cost_for` records a `CostModifierNotice`. That is fail-closed
    behaviour, not silence, and the sweep must read a permanent's static line
    through the same two functions the engine reads it with.
    """
    clauses = classify_clauses(card("Grand Arbiter Augustin IV"))
    assert [clause.category for clause in clauses] == [HANDLED, HANDLED, NOTICE]
    assert classify_card(card("Grand Arbiter Augustin IV"))[0] == NOTICE


# -- Defect 1: a permanent's static line is not "no rules text" -------------


def test_a_permanent_with_an_unmodelled_static_is_not_reported_as_clean():
    """Grafdigger's Cage is two real static abilities (CR 604.2: "Static
    abilities create continuous effects"; CR 113.3d: "Static abilities are
    written as statements. They're simply true") and neither is modelled
    anywhere. `has_rules_text` used to return `False` for it, which put it in
    the survey's `no_rules_text` bucket beside a vanilla creature - a count of
    cards nobody looked at, reading as coverage. It must now be judged, and
    the judgement must be the explicit unknown, never `HANDLED`.
    """
    printing = card("Grafdigger's Cage")
    assert has_rules_text(printing)
    category, detail = classify_card(printing)
    assert category == STATIC_UNAUDITED
    assert detail


@pytest.mark.parametrize(
    "name",
    [
        "Mox Opal",  # a mana ability (CR 605.1a) with an activation restriction
        "Craw Wurm",  # a vanilla creature
    ],
)
def test_a_card_with_nothing_to_judge_still_has_no_rules_text(name):
    """The fourth bucket must not swallow the cards `no_rules_text` is *right*
    about. Mox Opal's only line is a mana ability, which never reaches a
    dispatcher (CR 605.1a) and whose "Activate only if you control three or
    more artifacts" gate `Game._activation_condition_holds` really does
    enforce; Craw Wurm has no text at all.
    """
    assert not has_rules_text(card(name))


def test_a_permanent_spells_own_resolution_is_not_counted_as_a_dead_clause():
    """CR 608.3a: a permanent spell "becomes a permanent and enters the
    battlefield under the control of the spell's controller" - there is no
    resolution text to run, so `effect_for` answering `None` for one is
    correct. With the worst-clause rule in force, counting that `None` would
    make every permanent in the pool silent.
    """
    sources = {clause.source for clause in classify_clauses(card("Grafdigger's Cage"))}
    assert sources == {"static"}


# -- Defect 2: the worst clause wins, not the best --------------------------


def test_a_dead_clause_cannot_hide_behind_a_working_one():
    """Obsidian Charmaw's enters-trigger is read and its cost-reduction static
    line is not, so reporting the best outcome per card would call the whole
    card handled. The card-level verdict must be the worse of the two.

    This case was originally written against Territorial Kavu, whose domain
    characteristic-defining ability (CR 613.4a) was unread at the time. The
    text-keyed layer work landed in the same wave and reads it now - Kavu is
    `handled` on both clauses, pinned below - so the case moved to a card that
    still has the split rather than being deleted along with the gap it found.
    """
    by_source = {c.source: c.category for c in classify_clauses(card("Obsidian Charmaw"))}
    assert by_source["triggered"] == HANDLED
    assert by_source["static"] == STATIC_UNAUDITED

    assert classify_card(card("Obsidian Charmaw"))[0] == STATIC_UNAUDITED


def test_the_formerly_unread_layer_shapes_are_read_now():
    """The six cards `test_an_unread_continuous_effect_is_flagged_rather_than_failing_open`
    was written against are all read since the text-keyed layer work, and
    Territorial Kavu with them. Pinned so the gain cannot silently regress -
    without this, re-parametrising that case would have quietly discarded the
    evidence that it was ever closed.
    """
    for name in (
        "Stormscale Scion",
        "Kaheera, the Orphanguard",
        "Harbinger of the Seas",
        "Yavimaya, Cradle of Growth",
        "Leyline of the Guildpact",
        "Toph, the First Metalbender",
        "Territorial Kavu",
    ):
        statics = [c.category for c in classify_clauses(card(name)) if c.source == "static"]
        assert statics, f"{name} has no static clause to judge"
        # At least one, not all: Kaheera carries a second static line -
        # companion (CR 702.139a) - which is still genuinely unmodelled and
        # correctly reads `static_unaudited`. The claim here is that the
        # continuous effect this case was written about is read now, not that
        # every card on the list is finished.
        assert HANDLED in statics, f"{name}'s continuous effect regressed to {statics}"


def test_the_x_probes_are_the_one_place_the_best_answer_wins():
    """CR 107.3a's X probes are several askings of *one* clause, not several
    clauses: Green Sun's Zenith is a legal cast at X=0 that finds nothing and
    a real search at X=3, and one dispatcher answer for it is enough. The
    worst-clause rule must not turn the unreadable probe into a gap.
    """
    assert classify_card(card("Green Sun's Zenith"))[0] == HANDLED


# -- Defect 3: the layer-effect near-miss detector fails open ---------------


#: The six cards this case was written against - Stormscale Scion, Kaheera,
#: Harbinger of the Seas, Yavimaya, Leyline of the Guildpact and Toph - were
#: all genuinely unread when it was written, and are all read now: the
#: text-keyed layer work landed in the same wave and closed every one of
#: them. `test_the_formerly_unread_layer_shapes_are_read_now` below pins that
#: gain so it cannot silently regress. The parameters here were re-picked
#: from shapes the detector still flags today, because a fail-open test whose
#: every example has been implemented stops testing anything at all.
@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        # Angel of Jubilation used to stand here. Its "Other nonblack creatures
        # you control get +1/+1." is read now - the colour negation is one of
        # the qualifiers `_QUALIFIED_CREATURE_SUBJECT` learned - and
        # `tests/scenarios/test_qualified_anthems.py` pins it.
        (
            "Keen-Eyed Curator",
            "As long as there are four or more card types among cards exiled "
            "with this creature, it gets +4/+4 and has trample.",
        ),
        # Bloodghast used to stand here. Its landfall trigger ("you may return
        # this card from your graveyard to the battlefield") is read now, so
        # the card's worst clause is its unaudited static one and it reports
        # `STATIC_UNAUDITED` rather than `SILENT` - which is the tool telling
        # the truth, not a regression, but it no longer exercises this case.
        # Caretaker's Talent has the same shape and is still silent outright.
        ("Caretaker's Talent", "Creature tokens you control get +2/+2."),
        ("Caged Sun", "Creatures you control of the chosen color get +1/+1."),
    ],
)
def test_an_unread_continuous_effect_is_flagged_rather_than_failing_open(name, phrase):
    """Six permanents in the pool carry a real, unmodelled continuous effect -
    an anthem restricted to a subtype (CR 613.4c), a board-wide type grant (CR
    613.1d), a colour change (CR 613.1e) - that `machines/layers.py` neither
    parses nor recognises as a near-miss, so it records no `LayerNotice` and
    the card reads clean. Three of the six were each found by hand,
    independently, by a different deck agent; a detector that fails open is
    what makes every other layer gap invisible.

    A card here must never read `HANDLED` or `STATIC_UNAUDITED`. It is
    `SILENT` today because the engine genuinely records nothing; once
    `machines/layers.py` widens its own regex it will record a `LayerNotice`
    and become `NOTICE`, which `_static_ability_category` asks about *first*.
    """
    assert missed_layer_shape(phrase) is not None
    assert classify_card(card(name))[0] in (SILENT, NOTICE)


def test_the_near_miss_detector_does_not_fire_on_a_working_trigger():
    """Kraul Harpooner is the canary `machines/layers.py`'s own
    `static_only=True` exists for: its undergrowth pump lives inside a
    *triggered* ability that resolves correctly through its own parser. The
    near-miss table is only ever asked about a permanent's static lines, so
    widening it must not turn that trigger into a reported gap.
    """
    assert classify_card(card("Kraul Harpooner"))[0] == HANDLED


# -- Defect 4: ability words are not unexecuted keywords ---------------------


@pytest.mark.parametrize(
    ("name", "word"),
    [
        ("Prismatic Ending", "Converge"),
        ("Fatal Push", "Revolt"),
        ("Kraul Harpooner", "Undergrowth"),
        ("Territorial Kavu", "Domain"),
    ],
)
def test_an_ability_word_is_not_reported_as_an_unexecuted_keyword(name, word):
    """CR 207.2c: an ability word "ties together cards that have similar
    functionality, but [has] no special rules meaning". `knowledge_search`
    returns no numbered rule for converge, revolt, undergrowth or domain, and
    the engine reads three of the four clauses outright
    (`_parse_converge_exile_by_colors_spent`, `Game.revolt_active_for`,
    `_parse_undergrowth_pump_and_fight_clause`). Reporting them as keywords
    with no execution path produced seven false gap findings across four deck
    reports in one day.
    """
    assert word not in ignored_keywords(card(name))


# -- CR 107.3a's X: Green Sun's Zenith, Nature's Rhythm, Fiend Artisan -------


def test_green_suns_zenith_classifies_as_handled():
    """Reported live as silent; `test_green_suns_zenith_finds_a_legal_creature_at_x_one`
    and its siblings in test_x_valued_search_and_self_shuffle.py already prove
    the engine reads it correctly once X is substituted."""
    category, _ = classify_card(card("Green Sun's Zenith"))
    assert category == HANDLED


def test_natures_rhythm_classifies_as_handled():
    """Same X-substitution gap as Green Sun's Zenith, on a card whose second
    line (Harmonize) is a cast-permission keyword rather than a search
    poison - see `test_natures_rhythm_finds_a_legal_creature_at_x_two`."""
    category, _ = classify_card(card("Nature's Rhythm"))
    assert category == HANDLED


def test_fiend_artisan_classifies_as_handled():
    """The same X-bounded search, on an *activated* ability's own cost
    (`{X}{B/G}, {T}, Sacrifice another creature`) rather than a spell's mana
    cost - `activated_effect_for` needed the same `x_value` the real
    `Game.activate_ability` already records on `AbilityOnStack`."""
    category, _ = classify_card(card("Fiend Artisan"))
    assert category == HANDLED


def test_x_candidates_only_probes_when_the_cost_carries_x():
    """CR 107.3a's X is only ever substituted for a clause whose own paying
    cost carries `{X}` - a bare "X" defined elsewhere in the text (CR 107.3f)
    must be left untouched, so a cost with no `{X}` gets exactly one
    candidate: `None`."""
    assert _x_candidates(None) == (None,)
    assert _x_candidates("{1}{G}") == (None,)
    probed = _x_candidates("{X}{G}")
    assert None not in probed
    assert 0 in probed
    assert any(value != 0 for value in probed)


# -- Face handling: split cards and modal DFCs -------------------------------


def test_wear_tear_classifies_as_handled():
    """Wear // Tear's own top-level `oracle_text` is `None` on real Scryfall
    data (CR 709.3b: only the chosen half's characteristics exist), so
    reading it directly always looked silent - `test_split_cards.py` already
    proves both halves work once each is read off its own face."""
    category, _ = classify_card(card("Wear // Tear"))
    assert category == HANDLED


def test_sink_into_stupor_classifies_as_handled():
    """The modal-DFC sibling of the same bug: the front (spell) face's own
    text must be read, and the back (land) face must not be asked about as a
    spell at all (CR 305.1 - a land is played, never cast)."""
    category, _ = classify_card(card("Sink into Stupor // Soporific Springs"))
    assert category == HANDLED


def test_spell_faces_returns_both_halves_of_a_split_card():
    faces = _spell_faces(card("Wear // Tear"))
    assert {face.name for face in faces} == {"Wear", "Tear"}


def test_spell_faces_drops_the_land_face_of_a_modal_dfc():
    faces = _spell_faces(card("Sink into Stupor // Soporific Springs"))
    assert [face.name for face in faces] == ["Sink into Stupor"]


def test_spell_faces_is_a_single_entry_for_an_ordinary_card():
    faces = _spell_faces(card("Lightning Bolt"))
    assert len(faces) == 1
    assert faces[0].name == "Lightning Bolt"
    assert faces[0].text == card("Lightning Bolt").oracle_text
    assert faces[0].mana_cost == "{R}"
    assert not faces[0].is_permanent


def test_spell_faces_records_whether_the_face_is_a_permanent():
    """CR 608.3a needs the face's *own* type line, not the printing's:
    `classify_clauses` drops a permanent face's missing resolution effect and
    keeps an instant's. Wear // Tear is two instants; Sink into Stupor's
    castable face is one too, and its land face is already dropped above.
    """
    assert not any(face.is_permanent for face in _spell_faces(card("Wear // Tear")))
    assert _spell_faces(card("Grafdigger's Cage"))[0].is_permanent


# -- The condition-matching closure (docs/2026-09-08-trigger-findings.md,
# "The sweeper's blind spot, which matters beyond this card") -------------
#
# `classify_clauses` used to ask only whether `trigger_effect_for` produced a
# callable, never whether `machines/triggers.condition_matches` could ever be
# satisfied by a real permanent, and never whether that callable's own match
# came from inside a quoted span rather than the clause's own text. Weapons
# Manufacturing's "a nontoken artifact you control enters" scored two
# `handled` clauses this way while doing nothing at all in a real game: the
# substring guard `machines/triggers.py` uses for "one or more tokens you
# control enter" also matches "nontoken", inverting the restriction, and the
# damage effect it "found" is `_DAMAGE_TARGET_RE` reading the tail of the
# token's own quoted granted ability, not anything Weapons Manufacturing's
# own trigger clause says.


def _triggered_ability(name: str, *, condition_contains: str) -> TriggeredAbility:
    for ability in parse_abilities(card(name)):
        if isinstance(ability, TriggeredAbility) and condition_contains in ability.condition:
            return ability
    raise AssertionError(
        f"{name} has no triggered ability whose condition names {condition_contains!r}"
    )


def test_intended_token_requirement_reads_nontoken_before_token():
    """The interpreter this closure uses to decide whether a synthetic
    permanent should be a token has to get "nontoken" right on its own -
    reusing `machines/triggers.py`'s own substring check would just inherit
    the bug this test exists to catch.
    """
    assert _intended_token_requirement("a nontoken artifact you control enters") is False
    assert _intended_token_requirement("another nontoken Dragon you control enters") is False
    assert _intended_token_requirement("one or more tokens you control enter") is True
    assert _intended_token_requirement("a token you control enters") is True
    assert _intended_token_requirement("a Human you control enters") is None


def test_ygras_food_graveyard_condition_can_never_fire():
    """Ygra, Eater of All's "a Food is put into a graveyard from the
    battlefield" hits a different bug than Weapons Manufacturing's, in the
    same `condition_matches` `DIES` branch: a condition naming neither a
    self-reference nor "another"/"other" never matches anything, self or
    other (`docs/2026-09-08-trigger-findings.md` traces the same escaping
    shape - readable event, unmatched condition - to a second, independent
    cause). Nobody is fixing this one, which is what makes it a stable
    fixture: Weapons Manufacturing's own condition now fires correctly since
    `main`'s nontoken substring fix (see the sibling test below), so this
    closure's fixtures have to point at a gap that is still actually open.
    """
    ability = _triggered_ability("Ygra, Eater of All", condition_contains="Food is put into")
    assert _condition_can_fire(card("Ygra, Eater of All"), ability) is False


def test_blade_of_the_bloodchiefs_creature_dies_condition_now_fires():
    """Blade of the Bloodchief's "a creature dies" (no "this", no
    "another"/"other") used to hit the same `DIES`-branch gap Ygra's own
    fixture still does - but the two are not actually the same bug. Ygra's
    condition names no card *type* at all ("a Food is put into a graveyard",
    Food being a subtype `_types_match` cannot see), so the guard's type
    check never had anything to bite on and Ygra stays open on purpose (see
    that test's own docstring). Blade of the Bloodchief's condition names
    "creature" outright, and Blade of the Bloodchief is Equipment - never a
    candidate for its own condition - which is exactly the FRA "trigger
    events and per-turn history" stream's own fix (Gardenize, Way of the
    Necromancer): the "another"/"other" requirement only applies when the
    source could plausibly have been the subject.
    """
    ability = _triggered_ability("Blade of the Bloodchief", condition_contains="a creature dies")
    assert _condition_can_fire(card("Blade of the Bloodchief"), ability) is not False


def test_weapons_manufacturings_condition_now_fires_after_the_nontoken_fix():
    """The other half of the story: `main`'s nontoken substring fix
    (`30f2b07`) means a real nontoken artifact entering Weapons Manufacturing
    now genuinely satisfies its own condition, so this closure - which asks
    the *production* `condition_matches` directly rather than re-deriving an
    answer - must track that change with no code change of its own. Pinned
    so a future regression in either direction is caught: if the engine fix
    is ever reverted, or if this closure stops calling production code, this
    test moves.
    """
    ability = _triggered_ability("Weapons Manufacturing", condition_contains="nontoken artifact")
    assert _condition_can_fire(card("Weapons Manufacturing"), ability) is not False


def test_miirym_condition_now_fires_after_the_nontoken_fix():
    """Miirym's "another nontoken Dragon you control enters" is fixed by the
    same `main` change - the condition hole this closure was built to catch
    is closed for this card now, even though the card still has no effect
    reader at all (it still reports `SILENT`, not `HANDLED`; see
    `test_miirym_still_reports_silent_for_its_missing_effect` below)."""
    ability = _triggered_ability("Miirym, Sentinel Wyrm", condition_contains="nontoken Dragon")
    assert _condition_can_fire(card("Miirym, Sentinel Wyrm"), ability) is not False


def test_belladonna_tooks_token_condition_is_genuinely_reachable():
    """The control for the token axis: "a token you control enters" is a
    condition a real token entering the battlefield satisfies every day, so
    this closure must not report it unmatchable just because it names
    "token" at all - only the inverted "nontoken" shape is the bug.
    """
    ability = _triggered_ability("Belladonna Took", condition_contains="a token you control enters")
    assert _condition_can_fire(card("Belladonna Took"), ability) is True


def test_amulet_of_vigors_enters_tapped_condition_is_genuinely_reachable():
    """The control for the entry-qualifier axis (CR 603.6d): "a permanent you
    control enters tapped" is satisfied by any real permanent that actually
    does enter tapped, every day - this closure has to build a synthetic
    permanent that enters *tapped* to prove it, not only an untapped one.
    """
    ability = _triggered_ability("Amulet of Vigor", condition_contains="enters tapped")
    assert _condition_can_fire(card("Amulet of Vigor"), ability) is True


def test_caretakers_talents_unread_condition_is_not_reclassified():
    """`ability.event is None` (CR 603.2's condition this module cannot read
    at all, `docs/engine-coverage.md`'s own documented gap) is a different,
    pre-existing hole - `classify_clauses` must keep reporting it through the
    `"triggered (unread condition)"` source it already has, not fold it into
    the new `UNMATCHABLE_CONDITION` bucket this closure adds.
    """
    by_source = {c.source: c.category for c in classify_clauses(card("Caretaker's Talent"))}
    assert by_source["triggered (unread condition)"] == SILENT


def test_ygra_reports_unmatchable_condition_not_handled():
    """The requirement, end to end: this card's own triggered clause must
    stop scoring `handled`, and it must score a bucket distinct from
    `silent` - the two mean different things to whoever reads the report.
    Ygra was previously scored fully `handled` - a card the sweeper had
    never flagged at all, which the condition-matching closure is what
    finds.
    """
    by_source = {c.source: c.category for c in classify_clauses(card("Ygra, Eater of All"))}
    assert by_source["triggered"] == UNMATCHABLE_CONDITION
    assert classify_card(card("Ygra, Eater of All"))[0] == UNMATCHABLE_CONDITION


def test_blade_of_the_bloodchief_reports_silent_again_now_the_condition_fires():
    """The condition hole is closed (see the `_condition_can_fire` test
    above); the effect itself - "put a +1/+1 counter on equipped creature...
    two if Vampire" - still has no `TRIGGER_EFFECTS` entry or clause parser,
    so the card reports `SILENT` once more rather than `UNMATCHABLE_
    CONDITION` - the same shape `test_miirym_still_reports_silent_for_its_
    missing_effect` already pins for the nontoken fix's own sibling case.
    """
    assert classify_card(card("Blade of the Bloodchief"))[0] == SILENT


def test_miirym_still_reports_silent_for_its_missing_effect():
    """Miirym's *condition* fires correctly since the nontoken fix, but the
    card still has no `TRIGGER_EFFECTS` entry or parser reading "create a
    token that's a copy of it" - the two holes are independent, and closing
    one must not paper over the other still being open.
    """
    by_source = {c.source: c.category for c in classify_clauses(card("Miirym, Sentinel Wyrm"))}
    assert by_source["triggered"] == SILENT
    assert classify_card(card("Miirym, Sentinel Wyrm"))[0] == SILENT


# -- The quoted-text closure: an effect matched out of a granted ability's
# own quoted reminder text, not the clause's own. --------------------------
#
# Weapons Manufacturing was this closure's original example - `main`'s
# nontoken fix (`30f2b07`) turned out to close *both* of its holes, not just
# the condition one: it anchored `_DAMAGE_TARGET_RE` to refuse a prefix that
# crosses into a quote, and added a dedicated `create a ... token named X
# with "<ability>"` parser, so Weapons Manufacturing's own effect no longer
# misparses either. A real search (the fixture pool, `--effects`, plus over
# a dozen other real Scryfall printings sharing the same "create a token /
# gains an ability with a quoted payload ending in a damage clause" shape -
# Mysidian Elder, Queen Brahne, Judith Carnage Connoisseur, Circle of Power,
# and others) found **no card that still reaches the misparse end to end**
# through `trigger_effect_for`'s own dispatch order: the new parser and the
# anchored regex intercept every one of them.
#
# The three other unanchored-prefix damage regexes still in
# `machines/effects.py` (`_DAMAGE_EACH_OPPONENT_RE`, `_DAMAGE_EACH_CREATURE_
# RE`, `_DIVIDED_DAMAGE_RE`) turn out not to be reachable through a quote at
# all, on inspection: unlike the pre-fix `_DAMAGE_TARGET_RE`, whose
# `.*target.+` tail could absorb trailing punctuation (the closing `."` a
# quoted grant always ends with), these three end `\.?$` - an optional
# single period and then the *literal end of the string*, which a trailing
# `"` character always breaks. `_DAMAGE_EACH_OPPONENT_RE.fullmatch('...each
# opponent."')` is `None`, confirmed directly below. There is currently no
# live regex in this codebase, not just no live card, that this specific
# quote-crossing shape could still exploit - which is a real, useful finding
# in its own right, not a reason to weaken the closure's own test coverage.
# `_effect_matched_inside_quotes` is pinned instead with a direct unit test
# of its own contract, shaped after the real bug but not claiming any
# specific card or regex is presently vulnerable.


def test_weapons_manufacturings_effect_no_longer_matches_inside_quotes():
    """The positive regression: Weapons Manufacturing's own trigger no
    longer misparses, now that `_DAMAGE_TARGET_RE` is anchored and a
    dedicated token-creation-with-quoted-ability parser exists.
    """
    ability = _triggered_ability("Weapons Manufacturing", condition_contains="nontoken artifact")

    def dispatch(text: str) -> object:
        return trigger_effect_for("Weapons Manufacturing", ability.event, text)

    assert not _effect_matched_inside_quotes(dispatch, ability.effect)


def test_the_remaining_unanchored_damage_regexes_cannot_cross_a_quote():
    """Confirms the claim in the section docstring above with the real regex
    objects: each of the three still-unanchored-prefix damage regexes
    refuses to match text a quoted grant's own closing `"` sits after,
    because each ends `\\.?$` rather than the old, tail-permissive
    `.*target.+` `_DAMAGE_TARGET_RE` had before it was anchored.
    """
    quoted = 'create a token with "it deals 1 damage to each opponent."'
    assert _DAMAGE_EACH_OPPONENT_RE.fullmatch(quoted) is None
    quoted_creature = 'create a token with "it deals 1 damage to each creature."'
    assert _DAMAGE_EACH_CREATURE_RE.fullmatch(quoted_creature) is None


def test_effect_matched_inside_quotes_detects_a_dispatcher_reading_into_a_quote():
    """A direct unit test of the detector's own contract - `dispatch`
    modelled after the real, now-fixed bug shape (an unanchored match that
    reads whatever a quoted span says, regardless of what precedes it), but
    not tied to any specific card or regex, live or otherwise: no printing
    or regex in the codebase currently exhibits this any more (see the
    section docstring above), and this closure's own coverage must not
    depend on one continuing to.
    """
    text = 'create a token with "it deals 2 damage to any target."'

    def dispatch(t: str) -> object:
        return object() if "deals 2 damage to any target" in t else None

    assert _effect_matched_inside_quotes(dispatch, text)
    assert not _effect_matched_inside_quotes(dispatch, "create a token with no quote at all")


def test_urzas_sagas_gains_ability_clause_is_not_flagged():
    """The negative control: "This Saga gains "{2}, {T}: Create a ... token
    with '...'"" (CR 113.10) genuinely needs its quoted text - `_GAINS_
    ABILITY_RE` reads the whole quote as the ability being granted, on
    purpose, and refuses an empty one. Blanking the quote to a neutral
    non-empty placeholder must leave this dispatcher's answer non-`None`, so
    this real, working card is never reported as a quoted-text misparse.
    """
    for ability in parse_abilities(card("Urza's Saga")):
        if not isinstance(ability, TriggeredAbility) or '"' not in ability.effect:
            continue

        def dispatch(text: str, event=ability.event) -> object:
            return trigger_effect_for("Urza's Saga", event, text)

        assert not _effect_matched_inside_quotes(dispatch, ability.effect)


def test_unmatchable_condition_outranks_quoted_effect():
    """When a clause is both unreachable *and* its effect was matched out of
    quoted text, the more fundamental diagnosis wins: nothing else about the
    clause matters if it can never fire at all. Weapons Manufacturing used to
    be the one live card exhibiting both at once; now that its own condition
    and its own effect are both fixed on `main` (see the tests above and
    below), this pins the precedence rule directly rather than through a
    card no longer in that state.
    """
    assert _worse(UNMATCHABLE_CONDITION, QUOTED_EFFECT) == UNMATCHABLE_CONDITION
    assert _worse(QUOTED_EFFECT, UNMATCHABLE_CONDITION) == UNMATCHABLE_CONDITION


def test_hydro_mans_becomes_a_land_and_gains_clause_is_not_flagged():
    """A second negative control, of a different shape than Urza's Saga:
    Hydro-Man's "he becomes a land and gains "{T}: Add {U}."" dispatches to
    the `create_continuous_effect_of_ability` sentinel, whose real verdict
    `_dispatch_category` reads back off the *card's whole printed text* via
    `_layer_category` - never off whatever `dispatch(text)` itself returns
    for one blanked or unblanked string. Blanking the quote can change that
    raw dispatch answer without the sentinel path's own verdict being wrong
    at all, so the quoted-text closure must not ask the question here in the
    first place.
    """
    categories = {c.category for c in classify_clauses(card("Hydro-Man, Fluid Felon"))}
    assert QUOTED_EFFECT not in categories


# -- The sweeper must ask the same readability question the runtime does ---
#
# `machines/triggers.triggered_abilities_of` keeps a `TriggeredAbility` whose
# condition parser left `event=None` as long as `_unread_trigger_events` can
# still read the condition text (CR 603.1b), and `_state_trigger_abilities`
# keeps one whose condition matches `_STATE_COUNTER_TRIGGER_RE` (CR 603.8).
# Both routes reach `condition_matches`/`_state_condition_holds` and go on the
# stack in a real game. `classify_clauses` used to stamp every `event is
# None` triggered clause SILENT under `"triggered (unread condition)"`
# without ever asking either question, so a trigger the runtime actually
# fires read as dead here - Murktide Regent among them.


def test_sweeper_readability_matches_the_runtime_for_every_pooled_card():
    """Direct parity check, run over the whole pool so the two questions
    cannot drift apart again: whenever `triggered_abilities_of`'s own gate -
    `ability.event is not None or _unread_trigger_events(ability.condition)`
    - or `_state_trigger_abilities`'s `_STATE_COUNTER_TRIGGER_RE` says a
    triggered ability's condition is readable, the sweeper's clause for it
    must not be filed as an unread condition.
    """
    for printing in pool().values():
        for ability in parse_abilities(printing):
            if not isinstance(ability, TriggeredAbility):
                continue
            runtime_reads_it = (
                ability.event is not None
                or bool(_unread_trigger_events(ability.condition))
                or _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip()) is not None
            )
            if not runtime_reads_it:
                continue
            for clause in classify_clauses(printing):
                if clause.text.strip() == ability.text.strip():
                    assert clause.source != "triggered (unread condition)", (
                        f"{printing.name}: {ability.text!r} reaches the "
                        "stack in a real game but the sweeper still reports "
                        "it as an unread condition"
                    )


def test_murktide_regents_leaves_graveyard_condition_is_no_longer_unread():
    """The marquee case named in the triage: Murktide Regent's "an instant
    or sorcery card leaves your graveyard" is `_LEAVES_GRAVEYARD_CONDITION`'s
    own shape inside `_unread_trigger_events`, read by the runtime, and this
    pins the sweeper's clause for it directly rather than through the
    whole-pool sweep above.
    """
    for clause in classify_clauses(card("Murktide Regent")):
        if "leaves your graveyard" in clause.text:
            assert clause.source != "triggered (unread condition)"
            break
    else:
        raise AssertionError("Murktide Regent's leaves-graveyard clause was not found")


def test_four_cards_with_no_other_gap_leave_the_silent_list():
    """Basking Broodscale, Emperor of Bones, Hardened Academic and Murktide
    Regent each have exactly one dead-looking clause on the card - the
    misclassified unread-condition trigger - and no other silent clause.
    Once the sweeper reads the same condition the runtime does,
    `classify_card`'s worst-clause verdict must stop being SILENT for all
    four; a card still genuinely broken elsewhere (Caged Sun's dead anthem,
    say) is not part of this claim and is not asserted here.
    """
    for name in (
        "Basking Broodscale",
        "Emperor of Bones",
        "Hardened Academic",
        "Murktide Regent",
    ):
        category, _ = classify_card(card(name))
        assert category != SILENT, name


def test_watcher_for_tomorrows_leaves_the_battlefield_clause_is_not_silent():
    """Watcher for Tomorrow's "When this creature leaves the battlefield, put
    the exiled card into its owner's hand." is the CR 607.2a linked reference
    Ugin's Labyrinth prints as "Return the exiled card to its owner's hand."
    Adding the card to the fixtures for the hideaway knowledge scenarios put
    one more silent card on the sweep's headline count until the "put ...
    into" wording was read - see
    `tests/scenarios/test_cascade_and_hideaway_reveals_are_known.py`.

    Its "This creature enters tapped." static is a separate line the sweeper
    does not audit, so the card as a whole is static_unaudited, never silent."""
    watcher = card("Watcher for Tomorrow")
    outcomes = {outcome.text: outcome.category for outcome in classify_clauses(watcher)}
    clause = "When this creature leaves the battlefield, put the exiled card into its owner's hand."
    assert outcomes[clause] == HANDLED
    assert classify_card(watcher)[0] != SILENT

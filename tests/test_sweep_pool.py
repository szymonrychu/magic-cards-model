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
    SILENT,
    STATIC_UNAUDITED,
    _spell_faces,
    _x_candidates,
    classify_card,
    classify_clauses,
    has_rules_text,
    ignored_keywords,
    missed_layer_shape,
)

from tests.cards import card

# -- The baseline: a plain card must classify honestly in both directions ---


def test_a_card_that_works_classifies_as_handled():
    """Lightning Bolt has no X, no extra faces, and a plain targeted-damage
    row - the sweeper's simplest possible "this really does something" case.
    """
    category, _ = classify_card(card("Lightning Bolt"))
    assert category == HANDLED


def test_a_card_with_a_genuine_gap_still_classifies_as_silent():
    """Rancor's "Enchanted creature gets +2/+0 and has trample." is a
    still-open, documented gap: `machines/layers.py`'s own `LAYER_EFFECTS`
    comment says "'Enchanted creature' is a third subject
    `parsed_layer_effects` does not read ... left for a later wave", and
    `looks_like_unparsed_layer_effect` does not open on it either, so the
    Aura's whole bonus happens nowhere and is logged nowhere. Fixing the
    classifier must never make a genuinely-dead card look alive: this is the
    control for that.

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
    category, _ = classify_card(card("Rancor"))
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
        ("Angel of Jubilation", "Other nonblack creatures you control get +1/+1."),
        ("Bloodghast", "This creature has haste as long as an opponent has 10 or less life."),
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

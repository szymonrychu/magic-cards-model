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
"""

from scripts.sweep_pool import (
    HANDLED,
    SILENT,
    _spell_faces,
    _x_candidates,
    classify_card,
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
    """History of Benalia is a Saga: its whole text is chapter abilities
    (I, II - create a token; III - a team pump), which nothing in the engine
    reads, so it genuinely does nothing when played. Fixing the classifier
    must never make a genuinely-dead card look alive: this is the control
    for that.

    (Two earlier examples of the identical kind have since been closed and
    so stopped being valid controls here: March of Otherworldly Light's
    two-sentence additional-cost preamble, and Blood Artist's back-to-back
    "target player loses 1 life and you gain 1 life" clauses.)
    """
    category, _ = classify_card(card("History of Benalia"))
    assert category == SILENT


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
    names = {name for name, _, _ in faces}
    assert names == {"Wear", "Tear"}


def test_spell_faces_drops_the_land_face_of_a_modal_dfc():
    faces = _spell_faces(card("Sink into Stupor // Soporific Springs"))
    assert [name for name, _, _ in faces] == ["Sink into Stupor"]


def test_spell_faces_is_a_single_entry_for_an_ordinary_card():
    faces = _spell_faces(card("Lightning Bolt"))
    assert len(faces) == 1
    name, text, mana_cost = faces[0]
    assert name == "Lightning Bolt"
    assert text == card("Lightning Bolt").oracle_text
    assert mana_cost == "{R}"

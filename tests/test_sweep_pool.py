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
from scripts.sweep_pool import legal_cards_failing_closed

from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
from magic_cards_model.machines.effects import (
    _DAMAGE_EACH_CREATURE_RE,
    _DAMAGE_EACH_OPPONENT_RE,
    parse_mode_effect,
    trigger_effect_for,
)
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.machines.triggers import (
    _STATE_COUNTER_TRIGGER_RE,
    _unread_trigger_events,
)
from magic_cards_model.support import (
    HANDLED,
    NOTICE,
    QUOTED_EFFECT,
    SILENT,
    STATIC_UNAUDITED,
    UNMATCHABLE_CONDITION,
    _condition_can_fire,
    _effect_matched_inside_quotes,
    _intended_token_requirement,
    _modal_category,
    _modal_trigger_category,
    _spell_faces,
    _worse,
    _x_candidates,
    classify_card,
    classify_clauses,
    flavor_words,
    has_rules_text,
    ignored_keywords,
    in_target_formats,
    missed_layer_shape,
)
from tests.cards import card, gap_example, pool

# -- The baseline: a plain card must classify honestly in both directions ---


def test_a_card_that_works_classifies_as_handled():
    """Lightning Bolt has no X, no extra faces, and a plain targeted-damage
    row - the sweeper's simplest possible "this really does something" case.
    """
    category, _ = classify_card(card("Lightning Bolt"))
    assert category == HANDLED


def test_a_card_with_a_genuine_gap_still_classifies_as_silent():
    """A card the engine genuinely cannot read still does nothing - fixing
    the classifier must never make a genuinely-dead card look alive: this is
    the control for that.

    (Keen-Eyed Curator stood here until S09 read its "card types among cards
    exiled with this creature" static - `tests/scenarios/test_linked_exile_
    card_type_threshold.py` pins it. Rancor and Grand Arbiter Augustin IV
    stood here earlier and were closed the same way - so the control is now
    chosen by `gap_example`, never named.)
    """
    printing = gap_example("silent", lambda p: classify_card(p)[0] == SILENT)
    category, _ = classify_card(printing)
    assert category == SILENT


def test_a_rejected_proof_candidate_is_not_left_in_the_pool():
    """`tests.cards.pool()` globs every file under
    `src/magic_cards_model/data/printings`, so an abandoned proof-candidate
    printing joins the swept card pool exactly as if it had been chosen.

    Argentum Masticore was tried as the "sacrifice ~ unless you discard a
    card" proof printing for T5 (the combat-restrictions task) and explicitly
    rejected: its first sentence matches the new trigger reader, but its
    second sentence ("When you discard a card this way, destroy target
    nonland permanent...") is outside that task's scope and nothing reads it,
    so leaving its printing in the pool would make it a new `notice`/`silent`
    card in `sweep_pool.py --effects`'s before/after diff. Molten-Tail
    Masticore (no second sentence) was used instead; see `MEMORY.md`.
    """
    assert "Argentum Masticore" not in {p.name for p in pool().values()}


def test_charging_rhinos_blocked_by_at_most_one_static_classifies_as_handled():
    """Charging Rhino's unconditional "This creature can't be blocked by more
    than one creature." (CR 509.1b, the mirror of menace) is fully enforced
    by `combat.declaration_refusal` via `blocked_by_at_most_one_refusal`
    (`tests/scenarios/test_blocked_by_at_most_one.py`), but `_static_ability_
    category` never asked about that shape at all, so the printed line
    reported `STATIC_UNAUDITED` despite the engine reading it correctly in a
    real game.
    """
    category, _ = classify_card(card("Charging Rhino"))
    assert category == HANDLED


def test_festerhide_boars_morbid_enters_with_counters_classifies_as_handled():
    """Festerhide Boar's Morbid "This creature enters with two +1/+1 counters
    on it if a creature died this turn." (CR 207.2c ability word, CR 614.1c
    enters-with) is fully handled in a real game
    (`tests/scenarios/test_morbid.py`), but `_self_enters_line_category`'s
    synthetic single-permanent board never has a creature die, so Morbid's
    own board-state condition always reads false there and the clause
    reported `STATIC_UNAUDITED` even though the engine genuinely applies it.
    """
    category, _ = classify_card(card("Festerhide Boar"))
    assert category == HANDLED


@pytest.mark.parametrize(
    "name",
    ["Mockingbird", "Echoing Deeps", "Phantasmal Image", "Clever Impersonator", "Vesuva"],
)
def test_an_enter_as_a_copy_clause_is_judged_by_what_the_engine_does(name):
    """CR 614.1c / CR 707.9: the copy clause's "except ..." tail is part of the
    copy's copiable values, not a missed layer 4/6 effect, and its candidate
    phrase is judged by the engine's own `enters_as_copy_outcome` - so a
    readable clause is `HANDLED` (`tests/scenarios/test_enter_as_copy_*.py`
    play each of these), where Mockingbird and Echoing Deeps used to be
    `SILENT` on their tails alone."""
    category, _ = classify_card(card(name))
    assert category == HANDLED


def test_an_enter_as_a_copy_clause_with_an_unreadable_tail_is_a_notice():
    """Sakashima of a Thousand Faces' "except it has Sakashima's other
    abilities" fails closed with an `UnreadableCopyExceptionNotice`."""
    outcomes = {
        outcome.category for outcome in classify_clauses(card("Sakashima of a Thousand Faces"))
    }
    assert NOTICE in outcomes


def test_grand_arbiters_three_cost_modifier_statics_are_all_handled():
    """Grand Arbiter Augustin IV: "White/Blue spells you cast cost {1} less to
    cast" was already read by `machines/cost.cost_modifier_effect`; "Spells
    your opponents cast cost {1} more to cast" - controller-relative the
    other way round - is now too (`CostModifierKind.OPPONENT_TYPE_INCREASE`,
    S10 survey 2026-09-19, read for Thalia, the Survivor's qualified sibling
    "Noncreature spells your opponents cast cost {1} more to cast"). All
    three lines are HANDLED; the sweep must read a permanent's static line
    through the same two functions the engine reads it with.
    """
    clauses = classify_clauses(card("Grand Arbiter Augustin IV"))
    assert [clause.category for clause in clauses] == [HANDLED, HANDLED, HANDLED]
    assert classify_card(card("Grand Arbiter Augustin IV"))[0] == HANDLED


# -- Defect 1: a permanent's static line is not "no rules text" -------------


def test_a_permanent_with_an_unmodelled_static_is_not_reported_as_clean():
    """Grafdigger's Cage is two real static abilities (CR 604.2: "Static
    abilities create continuous effects"; CR 113.3d: "Static abilities are
    written as statements. They're simply true") and neither is modelled
    anywhere. `has_rules_text` used to return `False` for it, which put it in
    the survey's `no_rules_text` bucket beside a vanilla creature - a count of
    cards nobody looked at, reading as coverage. It must now be judged, and
    the judgement must be the explicit unknown, never `HANDLED`.

    The Cage's lines are read now (C00), so the example is chosen, never
    named: any printing whose worst clause is still an unaudited static.
    """
    printing = gap_example(
        "an unaudited static",
        lambda p: bool(p.type_line) and classify_card(p)[0] == STATIC_UNAUDITED,
    )
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
    """A card whose enters-trigger is read and whose static line is not
    (Obsidian Charmaw's cost reduction stood here; the card is now chosen by
    `gap_example`): reporting the best outcome per card would call the whole
    card handled. The card-level verdict must be the worse of the two.

    This case was originally written against Territorial Kavu, whose domain
    characteristic-defining ability (CR 613.4a) was unread at the time. The
    text-keyed layer work landed in the same wave and reads it now - Kavu is
    `handled` on both clauses, pinned below - so the case moved to a card that
    still has the split rather than being deleted along with the gap it found.
    """

    def split(printing) -> bool:
        by_source = {c.source: c.category for c in classify_clauses(printing)}
        return by_source.get("triggered") == HANDLED and by_source.get("static") == (
            STATIC_UNAUDITED
        )

    printing = gap_example("a read trigger beside an unaudited static", split)
    assert classify_card(printing)[0] == STATIC_UNAUDITED


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
        # Keen-Eyed Curator used to stand here; S09 reads its linked-exile
        # threshold static now (`test_linked_exile_card_type_threshold.py`).
        # Bloodghast used to stand here. Its landfall trigger ("you may return
        # this card from your graveyard to the battlefield") is read now, so
        # the card's worst clause is its unaudited static one and it reports
        # `STATIC_UNAUDITED` rather than `SILENT` - which is the tool telling
        # the truth, not a regression, but it no longer exercises this case.
        # Caretaker's Talent used to stand here; its only silent clause was
        # the level 2 "becomes level" trigger, read now (S19,
        # `tests/scenarios/test_class_level_triggers.py`), and its static
        # anthem reads handled.
        # Caged Sun stood here after it. S23 reads "Creatures you control of
        # the chosen color get +1/+1." (`tests/scenarios/test_chosen_colour_
        # anthem.py`); Armed with Proof's layer 4 type grant is still unread.
        (
            "Armed with Proof",
            "Clues you control are Equipment in addition to their other types.",
        ),
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


@pytest.mark.parametrize(
    "name",
    [
        "Barbarian Ring",
        "Werebear",
        "Loot, the Anomaly",
        "Null Summoner",
        "Proft, Sinister Mastermind",
    ],
)
def test_thresholds_ability_word_is_not_reported_as_an_unexecuted_keyword(name):
    """fra-final-audit batch A item 2: Reality Fracture's "Threshold —
    <condition>." is CR 207.2c's own ability-word shape - `machines/
    casting.py`'s own `_CANNOT_CAST_UNLESS_RE` comment says so outright: "The
    ability word ('Threshold') carries no rules meaning of its own (CR
    207.2c) and is not part of the match; the restriction is the sentence
    after it." The word labels four different clause shapes across the pool
    (a cast restriction, an "Activate only if" activation gate, and a static
    conditional pump), each already read by its own existing, unrelated
    parser - exactly the converge/revolt/undergrowth/domain shape above, not
    a keyword with a code path of its own.
    """
    assert "Threshold" not in ignored_keywords(card(name))


@pytest.mark.parametrize(
    ("name", "word"),
    [
        ("Emergency Phytomedic", "Prepared"),
        ("Countersculpt", "Behold"),
        ("Greenbelt Guardian", "Exhaust"),
        ("Fuel for the Cause", "Proliferate"),
    ],
)
def test_a_genuinely_executed_keyword_is_not_reported_as_unexecuted(name, word):
    """fra-final-audit batch A item 2: unlike Threshold, each of these four
    keywords has real, dedicated machinery keyed off the word itself, not
    just an ordinary clause a generic parser happens to read - Prepared
    (`Game.become_prepared`/`become_unprepared`, CR 722), Behold
    (`machines/cost.behold_cost`, CR 701.4a), Exhaust (`Game.exhausted`
    gating `activate_ability`, CR 702.177a), and Proliferate
    (`machines/effects._parse_proliferate_clause`, CR 701.34a). Each is
    proven live by its own scenario test (`test_prepare.py`, `test_behold.py`,
    `test_exhaust.py`, `test_proliferate.py`), so reporting the keyword
    itself as having no execution path was purely a measurement gap in
    `executed_keywords`.
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


def test_ygras_food_graveyard_condition_now_fires():
    """Ygra, Eater of All's "a Food is put into a graveyard from the
    battlefield" names neither a self-reference nor "another"/"other". The
    `condition_matches` `DIES` branch used to read such a condition as
    self-only and never matched it; a condition naming no object of its own
    is about any such object, and this closure tracks the production answer.
    """
    ability = _triggered_ability("Ygra, Eater of All", condition_contains="Food is put into")
    assert _condition_can_fire(card("Ygra, Eater of All"), ability) is not False


def test_blade_of_the_bloodchiefs_creature_dies_condition_now_fires():
    """Blade of the Bloodchief's "a creature dies" - the same `DIES`-branch
    fix as Ygra's, on a plainer card."""
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


def test_tetsuko_umezawa_pursuers_power_or_toughness_condition_now_fires():
    """Tetsuko's own "a creature an opponent controls with power or
    toughness 1 or less blocks" is a BLOCKS probe, and none of `_cards_by_
    type()[Type.CREATURE]`'s capped first five real printings happen to be
    that small - `_power_or_toughness_probe_cards` adds real creatures
    (found by scanning the whole pool once, cached) that actually satisfy
    the numeric qualifier the condition names, on top of that fixed cache,
    so a probe genuinely exists to try."""
    ability = _triggered_ability(
        "Tetsuko Umezawa, Pursuer", condition_contains="power or toughness"
    )
    assert _condition_can_fire(card("Tetsuko Umezawa, Pursuer"), ability) is not False
    assert classify_card(card("Tetsuko Umezawa, Pursuer"))[0] != UNMATCHABLE_CONDITION


def test_an_unread_condition_is_not_reclassified():
    """`ability.event is None` (CR 603.2's condition this module cannot read
    at all, `docs/engine-coverage.md`'s own documented gap) is a different,
    pre-existing hole - `classify_clauses` must keep reporting it through the
    `"triggered (unread condition)"` source it already has, not fold it into
    the new `UNMATCHABLE_CONDITION` bucket this closure adds.
    """

    # Caretaker's Talent stood here until S19 read its "When this Class
    # becomes level 2"; the card is chosen now, never named. Round 4 (S28's
    # cycle/activation events, S29's day and night) read the last in-pool
    # ones, so Grudge Keeper (Conspiracy, voting - out of every target
    # format) was added as the out-of-format vehicle.
    def unread(printing) -> bool:
        return any(c.source == "triggered (unread condition)" for c in classify_clauses(printing))

    printing = gap_example("carrying an unread trigger condition", unread)
    by_source = {c.source: c.category for c in classify_clauses(printing)}
    assert by_source["triggered (unread condition)"] == SILENT


def test_ygra_no_longer_reports_an_unmatchable_condition():
    """End to end: with the condition fixed, Ygra's triggered clause is no
    longer in the can-never-fire bucket."""
    by_source = {c.source: c.category for c in classify_clauses(card("Ygra, Eater of All"))}
    assert by_source["triggered"] != UNMATCHABLE_CONDITION


def test_blade_of_the_bloodchief_no_longer_reports_an_unmatchable_condition():
    """The condition hole is closed (see the `_condition_can_fire` test
    above). Its effect - "put a +1/+1 counter on equipped creature... two if
    Vampire" - is read by the num-g0b line's own "put a counter on X. If X
    is a `<Subtype>`, put N counters on it instead" parser, landed
    independently of this fix, so the card reports `HANDLED` rather than
    `SILENT` or `UNMATCHABLE_CONDITION`; this only pins the condition half.
    """
    assert classify_card(card("Blade of the Bloodchief"))[0] != UNMATCHABLE_CONDITION


def test_dawn_blessed_pennant_chosen_type_entry_trigger_is_reachable():
    """Dawn-Blessed Pennant's own "Whenever a permanent you control of the
    chosen type enters, you gain 1 life." names CR 614.12a's own choice
    (`ChoiceKind.CREATURE_TYPE`) back rather than a literal, capitalised
    subtype word - the shape `_ENTERING_SUBTYPE` (`machines/triggers.py`)
    reads for a plain "a Mountain you control enters" never matches "of the
    chosen type", so `_probe_cards` found no real permanent to test the
    condition against and no synthetic source ever had `CardState.choice`
    set to compare it with - the trigger read as `UNMATCHABLE_CONDITION`
    even though a real Elemental/Elf/Faerie/Giant/Goblin/Kithkin/Merfolk/
    Treefolk entering after the chosen-type replacement effect resolves
    fires it every game.
    """
    by_source = {c.source: c.category for c in classify_clauses(card("Dawn-Blessed Pennant"))}
    assert by_source["triggered"] != UNMATCHABLE_CONDITION
    assert by_source["triggered"] == HANDLED
    assert classify_card(card("Dawn-Blessed Pennant"))[0] == HANDLED


def test_miirym_reports_handled_now_its_copy_effect_is_read():
    """Miirym's *condition* fires correctly since the nontoken fix, and its
    "create a token that's a copy of it, except the token isn't legendary"
    is read since C01-T7 (`_SELF_COPY_TOKEN_RE`, "it" the entering Dragon -
    `tests/scenarios/test_token_copies_not_legendary.py`)."""
    by_source = {c.source: c.category for c in classify_clauses(card("Miirym, Sentinel Wyrm"))}
    assert by_source["triggered"] == HANDLED
    assert classify_card(card("Miirym, Sentinel Wyrm"))[0] == HANDLED


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


def test_modal_category_is_worst_mode_not_best_mode():
    """`_modal_category` used to score `HANDLED` the moment *any* chosen
    mode's text parsed, on the reading that a card with at least one working
    mode is not dead - but that scores a card `HANDLED` when a real, chosen
    mode of it does nothing (CR 700.2a lets a player choose *any* mode with
    no minimum-usefulness rule), which is exactly the "best clause wins" bug
    `classify_card`'s own docstring already rejects for an ordinary card
    (Territorial Kavu, Obsidian Charmaw, Engineered Explosives).

    The half-read example is chosen from the pool rather than named: this
    campaign's goal is every legal modal card fully read, so any one named
    card stops demonstrating the rule the moment its last mode lands - which
    is what happened to Cryptic Command (S18 read its tap-all mode). The test
    only fails outright if no pool card is left with one mode read and one
    not, the one state in which the rule can no longer be shown at all.
    Vraska's Final Mercy and Cryptic Command, both fully read now, keep
    asserting `HANDLED` so a regression in any of their modes is caught.
    """
    half_read = [
        printing
        for printing in pool().values()
        if (modal := modal_profile(printing)) is not None
        and modal.understood
        and len({parse_mode_effect(mode, 0) is None for mode in modal.modes}) == 2
    ]
    assert half_read, "no pool card has one mode read and one unread - the rule is unshowable"
    for printing in half_read:
        assert _modal_category(printing) == NOTICE, printing.name
    assert _modal_category(card("Cryptic Command")) == HANDLED
    assert _modal_category(card("Vraska's Final Mercy")) == HANDLED


def test_ingris_stingerquills_permanent_spell_records_no_phantom_notice():
    """Ingris Stingerquill: "{4}: Create a 2/2 ... Cadet. Then creatures you
    control gain haste until end of turn." is its *activated* ability's own
    line, read correctly through `activated_effect_for`. `effect_for` is
    still called on the whole permanent's raw printed text for its own
    (nonexistent, CR 608.3a) spell resolution, and the group-haste sentence
    embedded in that text is now genuinely readable
    (`_MASS_PUMP_UNTIL_EOT_RE`'s own keyword-only widening) - which used to
    make `_compose_layer_effect_with_remainder` treat the activated
    ability's own cost line as an unread sibling instruction of the spell's
    resolution and record a `LayerRemainderNotice` for a permanent spell
    that has no resolution text to run at all.
    """
    outcomes = classify_clauses(card("Ingris Stingerquill"))
    assert all(outcome.source != "spell" for outcome in outcomes)
    assert {outcome.category for outcome in outcomes} == {HANDLED}


# -- fra-final-audit batch A item 2: classify_clauses stopped crediting a --
# -- permanent face just because effect_for happened to parse something ----


def test_a_permanent_faces_spell_clause_is_never_credited_even_when_effect_for_parses_it():
    """Screeching Soulbreaker, Ghalta the Immovable, Garruk, Veiled Butcher
    and Proft, Sinister Mastermind are the fra-final-audit's own proof: each
    used to keep a "spell" `ClauseOutcome` (`HANDLED` for Soulbreaker,
    `NOTICE` for the other three) purely because `effect_for` could parse
    *something* out of the permanent's raw printed text - the sweeper's own
    "a permanent face that does get an effect keeps it: the credit is real"
    exception. `models/game.py::_resolve_top` never calls `effect_for` for a
    permanent spell any more (CR 608.3a; see
    `tests/scenarios/test_permanent_spell_resolution.py`), so that exception
    now credits a code path the engine literally never runs - every one of
    these must drop the "spell" clause entirely and be judged only on its
    real, battlefield-facing abilities below.
    """
    for name in (
        "Screeching Soulbreaker",
        "Ghalta the Immovable",
        "Garruk, Veiled Butcher",
        "Proft, Sinister Mastermind",
    ):
        outcomes = classify_clauses(card(name))
        assert all(outcome.source != "spell" for outcome in outcomes), (
            f"{name} still carries a phantom spell-resolution clause: {outcomes}"
        )

    # And the real abilities underneath are still judged, and still handled -
    # dropping the phantom "spell" clause must not also drop real coverage.
    soulbreaker_categories = {
        outcome.category for outcome in classify_clauses(card("Screeching Soulbreaker"))
    }
    assert soulbreaker_categories == {HANDLED}


def test_self_enters_line_category_reads_past_the_reminder_text():
    """`_self_enters_line_category` compared `ReplacementEffect.raw` - "the
    whole ability paragraph as printed, reminder text included"
    (`machines/replacement.py`'s own docstring) - against `_static_ability_
    category`'s per-sentence `text`, which never carries the reminder. Every
    "This creature enters prepared." line failed that comparison and fell
    through to `STATIC_UNAUDITED`, even though `_self_enters_modifiers`
    genuinely performs it (`tests/scenarios/test_prepare.py`). The fix reads
    `ReplacementEffect.text` - "the one sentence this effect was parsed from,
    reminder text removed" - instead.

    Emergency Phytomedic is the off-report proof: it already has a scenario
    test naming "enters prepared" directly (`test_prepare.py`), so it was
    never one of the 7 the audit named as untested, and it still misclassified
    the same way - the bug was in the classifier's field choice, not specific
    to any one card.
    """
    for name in ("Blossom-Blessed Angel", "Emergency Phytomedic"):
        by_source = {outcome.source: outcome.category for outcome in classify_clauses(card(name))}
        assert by_source["static"] == HANDLED, f"{name}: {by_source}"


def test_modal_trigger_category_follows_the_same_fallback_chain_as_resolution():
    """Yuriko, Hope from the Shadows: mode 1, "Target creature gets -X/-0
    until end of turn, where X is the number of cards in your graveyard.",
    is CR 107.3f's own X - not `parse_mixed_effect`'s business at all.
    `_resolve_modal_triggered_ability_clause` (`machines/effects.py`) tries
    three readers per mode in order - `parse_mixed_effect`, then
    `_compose_layer_effect_with_remainder_for_ability_mode`, then
    `_parse_where_x_is_continuous_effect` - and the third is what actually
    reads this mode (`tests/scenarios/test_modal_mode_composition.py::
    test_yuriko_mode_one_shrinks_by_the_graveyard_count` proves it live).
    `_modal_trigger_category` only ever tried the first, so a genuinely
    handled modal trigger read as `NOTICE`.
    """
    (yuriko_trigger,) = (
        ability
        for ability in parse_abilities(card("Yuriko, Hope from the Shadows"))
        if isinstance(ability, TriggeredAbility)
    )
    assert _modal_trigger_category(yuriko_trigger.effect) == HANDLED


# -- CR 107.3m: an ETB trigger reading the announced X --------------------


def test_fblthp_knows_the_ways_etb_trigger_reads_the_announced_x():
    """Fblthp, Knows the Way is `{X}{G}{G}`, and its ETB trigger - "search
    your library for up to X basic land cards with different names" - is
    unreadable with a literal "X" left in it, the same gap `trigger_effect_
    for`'s own `x_value` parameter exists to close (its docstring names this
    exact card). `Game._effect_of` substitutes the cast record's own X
    before calling `trigger_effect_for`, gated on CR 107.3m (verified this
    session with `mise run rules:find 107.3`): the ability's event is CR
    603.6a's `ENTERS_THE_BATTLEFIELD`, its effect text carries a bare "X",
    and the permanent's own mana cost carries "{X}" (CR 107.3a) - never a
    card that defines X in its own text instead (CR 107.3f, Craterhoof
    Behemoth's and Yuriko's shape, which CR 107.3m does not touch).
    `classify_clauses` never simulated that substitution before calling
    `trigger_effect_for`, so this genuinely-handled trigger
    (`tests/scenarios/test_fra_s8_search_distinct_names.py` proves it live)
    read `SILENT`.
    """
    by_source = {
        outcome.source: outcome.category
        for outcome in classify_clauses(card("Fblthp, Knows the Way"))
    }
    assert by_source["triggered"] == HANDLED, by_source


def test_ajanis_anguish_is_not_a_second_misreport_of_the_same_shape():
    """Ajani's Anguish is the other `{X}` mana cost / bare-"X" ETB trigger
    in the pool (a full scan of every printing with `{X}` in its own mana
    cost found exactly these two) - and it was never actually misreported:
    its damage clause already classifies `HANDLED` with no X plumbing at
    all, because the targeted-damage parser reads a literal "X" as CR
    107.3a's own deferred amount directly (the real value is read at
    resolution time off the ability's source, not substituted into the text
    first). Pinned here so a future change to the CR 107.3m fix cannot
    silently stop asking about this card too.
    """
    by_source = {
        outcome.source: outcome.category for outcome in classify_clauses(card("Ajani's Anguish"))
    }
    assert by_source["triggered"] == HANDLED, by_source


# -- `_self_enters_line_category` reads a multi-sentence "as this enters" --
# -- paragraph, not only a single reminder-carrying sentence ---------------

#: The 18 real pool printings a prior fix to `_self_enters_line_category`
#: moved from `HANDLED` to `STATIC_UNAUDITED`: every one of them prints a
#: two-sentence "As this `<permanent>` enters, ..." static line (a choice
#: plus its own consequence), which `parse_replacement_effects` reads as two
#: `ReplacementEffect`s, each `.text` only its own half of the sentence -
#: comparing that against the *whole* two-sentence line (`_static_ability_
#: category`'s own `text` argument) never matched either half, so the
#: paragraph fell through to the honest-looking but wrong `STATIC_UNAUDITED`
#: even though `Game`/`machines/replacement.py` already play every one of
#: these correctly (`test_fra_lands.py`, `test_shockland_replacement.py` and
#: their siblings already prove the runtime behaviour; this file is only
#: about what the sweeper *reports*).
_SELF_ENTERS_MULTI_SENTENCE_CARDS = (
    "Blood Crypt",
    "Breeding Pool",
    "Godless Shrine",
    "Hallowed Fountain",
    "Overgrown Tomb",
    "Sacred Foundry",
    "Steam Vents",
    "Stomping Ground",
    "Temple Garden",
    "Watery Grave",
    "Port Town",
    "Gilt-Leaf Palace",
    "Sunken Citadel",
    "Room of Refuge",
    "Devouring Hellion",
    "Rhizome Lurcher",
    "Shimatsu the Bloodcloaked",
    "Superior Spider-Man",
)


@pytest.mark.parametrize("name", _SELF_ENTERS_MULTI_SENTENCE_CARDS)
def test_self_enters_multi_sentence_paragraphs_classify_as_handled(name):
    category, clause = classify_card(card(name))
    assert category == HANDLED, (name, clause)


def test_self_enters_still_reports_a_reminder_carrying_single_sentence_as_handled():
    """The shape the prior fix was originally written for must not regress
    while fixing the multi-sentence one: "This creature enters prepared."
    prints CR 722.3a's own reminder text immediately after it on the same
    line, and still has to classify `HANDLED`."""
    category, clause = classify_card(card("Emergency Phytomedic"))
    assert category == HANDLED, clause


def test_self_enters_line_category_does_not_match_an_unrelated_paragraph():
    """The honesty check the other direction: `_self_enters_line_category`
    must not credit a card for a paragraph it does not actually print -
    the widened match still has to find the effect's own paragraph among
    `printing`'s real replacement effects, not merely resemble it."""
    from magic_cards_model.support import _self_enters_line_category

    printing = card("Blood Crypt")
    result = _self_enters_line_category(
        printing,
        "As this land enters, you may pay 2 life. If you don't, it deals 2 damage to you.",
    )
    assert result is None


# -- T01: format filter (Modern/Pioneer/Standard, banned counts as in) ------


@pytest.mark.parametrize(
    "name",
    [
        "Corpseweaver Prodigy",  # digital-only Alchemy card, no CR text at all
        "Snowfall",
        "Séance Board",
        "Gut, True Soul Zealot",
        "Sakashima of a Thousand Faces",
        "Silas Renn, Seeker Adept",
        "Primaris Chaplain",
        "Celestine, the Living Saint",
        "Astral Dragon",
        "Frenzied Gorespawn",
        "Enigma Thief",
        "Elvish Lookout",
        "Nevinyrral, Urborg Tyrant",
    ],
)
def test_cards_not_legal_in_any_target_format_are_excluded(name):
    """`in_target_formats` clamps to Modern/Pioneer/Standard, the three
    formats `CLAUDE.md` says this engine targets - not_legal in all three
    means excluded from the format-filtered reports."""
    from magic_cards_model.support import in_target_formats

    printing = card(name)
    assert printing.legalities.modern == "not_legal"
    assert printing.legalities.pioneer == "not_legal"
    assert printing.legalities.standard == "not_legal"
    assert in_target_formats(printing) is False


def test_a_card_banned_in_one_target_format_but_legal_in_another_is_included():
    """Amalia Benavides Aguirre is banned in Pioneer but legal in Modern and
    Standard: banned counts as "exists in the format" (a banned card was
    printed into the format's card pool and can be unbanned), so the format
    filter must not drop it."""
    from magic_cards_model.support import in_target_formats

    printing = card("Amalia Benavides Aguirre")
    assert printing.legalities.pioneer == "banned"
    assert printing.legalities.modern == "legal"
    assert in_target_formats(printing) is True


def test_a_card_legal_in_only_one_target_format_is_included():
    """Vexing Sphinx is legal in Modern alone (not_legal in Pioneer and
    Standard) - any one of the three formats is enough."""
    from magic_cards_model.support import in_target_formats

    printing = card("Vexing Sphinx")
    assert printing.legalities.modern == "legal"
    assert printing.legalities.pioneer == "not_legal"
    assert printing.legalities.standard == "not_legal"
    assert in_target_formats(printing) is True


def test_main_keywords_report_drops_out_of_format_cards():
    """`main`'s default run filters `--keywords`'s own `names` through
    `in_target_formats` - Elvish Lookout (Shroud, out of format) must not
    appear in the report even though Shroud itself is registered."""
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--keywords"])
    output = buffer.getvalue()
    assert "Elvish Lookout" not in output
    assert "excluded" in output


def test_main_all_formats_flag_disables_the_filter():
    """`--all-formats` reports on the whole pool - the footer's own excluded
    count must read zero, and it prints no footer line at all (the filter is
    off, so there is nothing to report about it)."""
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--keywords", "--all-formats"])
    output = buffer.getvalue()
    assert "excluded" not in output


def test_report_card_notes_when_the_filter_would_drop_the_card():
    """`--card` always reports on the named card regardless of format, but
    prints the "not counted" line when the format filter would have dropped
    it from the pool-wide reports."""
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--card", "Elvish Lookout"])
    assert "outside Modern/Pioneer/Standard - not counted" in buffer.getvalue()


def test_report_card_does_not_note_an_in_format_card():
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import main

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--card", "Lightning Bolt"])
    assert "not counted" not in buffer.getvalue()


# -- T01: CR 207.2c ability words, verbatim and complete ---------------------


def test_ability_words_is_the_complete_verbatim_cr_207_2c_list():
    """60 entries (`descend 4`/`descend 8` collapsed to one `descend` entry -
    see `_normalized_ability_word`), verified 2026-09-23 with
    `mise run rules:find 207.2c`."""
    from magic_cards_model.support import ABILITY_WORDS

    assert len(ABILITY_WORDS) == 60
    assert "adamant" in ABILITY_WORDS
    assert "will of the council" in ABILITY_WORDS
    assert "descend" in ABILITY_WORDS
    assert "descend 4" not in ABILITY_WORDS
    assert "descend 8" not in ABILITY_WORDS


@pytest.mark.parametrize(
    ("name", "word"),
    [
        ("Basking Capybara", "Descend"),
        ("Bellowing Aegisaur", "Enrage"),
        ("Corpseweaver Prodigy", "Infusion"),
        ("Deepwater Hypnotist", "Inspired"),
        ("Gruesome Discovery", "Morbid"),
        ("Stirring Hopesinger", "Repartee"),
        ("Launch the Fleet", "Strive"),
        ("Kona, Rescue Beastie", "Survival"),
    ],
)
def test_cr_207_2c_ability_words_are_not_reported_as_unexecuted_keywords(name, word):
    """The eight ability words the flow-2 brief classified by CR 207.2c,
    each on its own reported card - a card carrying one is never carrying an
    unexecuted keyword (CR 207.2c: ability words "have no special rules
    meaning")."""
    assert word not in ignored_keywords(card(name))


def test_descend_4_and_descend_8_both_match_the_collapsed_ability_word():
    """Scryfall prints `Descend 4` and `Descend 8` as two different keyword
    strings (the count is CR 700.11's own designated amount); both have to
    reach `ABILITY_WORDS`'s single `descend` entry."""
    from magic_cards_model.support import _normalized_ability_word

    assert _normalized_ability_word("Descend 4") == "descend"
    assert _normalized_ability_word("Descend 8") == "descend"


def test_councils_dilemma_curly_apostrophe_normalizes_to_the_cr_spelling():
    from magic_cards_model.support import _normalized_ability_word

    assert _normalized_ability_word("Council’s dilemma") == "council's dilemma"


def test_waterbend_is_not_a_cr_207_2c_ability_word():
    """CR 701.67 waterbend is a keyword *action*, not an ability word - it
    must not be swallowed by the ability-word table."""
    from magic_cards_model.support import ABILITY_WORDS, _normalized_ability_word

    assert _normalized_ability_word("Waterbend") not in ABILITY_WORDS


def test_ascend_is_not_a_cr_207_2c_ability_word():
    """CR 702.131 ascend is a real keyword ability with its own machinery
    (`machines/keywords.py`) - the pre-existing `ABILITY_WORDS` table used to
    carry an uncited "ascend" entry that hid this real keyword behind a false
    "no special rules meaning" claim. It must not be in the verbatim CR
    207.2c list."""
    from magic_cards_model.support import ABILITY_WORDS

    assert "ascend" not in ABILITY_WORDS


def test_ascend_is_registered_as_executed():
    """`machines/keywords.py` already builds ascend (`has_ascend`,
    `_has_computed_ascend`, `ascend_as_a_spell_resolves`, CR 702.131) -
    replacing the stale `ABILITY_WORDS` entry with the real CR 207.2c list
    must not turn a built keyword into a false gap report."""
    assert "Ascend" not in ignored_keywords(card("Ocelot Pride"))


# -- T01: flavor words (CR 207.2d), generalized past the bullet-mode shape --


@pytest.mark.parametrize(
    ("name", "word"),
    [
        ("Mister Negative", "Darkforce Inversion"),
        ("Superior Spider-Man", "Mind Swap"),
        ("Sephiroth, Fabled SOLDIER", "Super Nova"),
    ],
)
def test_generalized_flavor_word_labels_are_recognised(name, word):
    """CR 207.2d's other shape - an ability line labelled `<Label> — <text>`
    with no bullet - is a flavor word when the label is one of the card's own
    Scryfall keywords and is neither a CR 701/702 keyword name nor a CR
    207.2c ability word. None of these three labels has a CR entry
    (`knowledge_search`/`rules:find` return nothing for any of them), and
    each is proven `handled` by its own clause outcome, not by this table."""
    assert word.lower() in flavor_words(card(name))
    assert word not in ignored_keywords(card(name))


def test_power_up_label_is_not_swallowed_as_a_flavor_word():
    """Aerial Doombot's "Power-up — {5}{U}: ..." has the identical printed
    shape (label, em dash with spaces, text) as a real flavor word, but
    "Power-up" is CR 702.193's own keyword ability name - the generalized
    flavor-word rule must not treat it as decorative. It is executed
    (`tests/scenarios/test_power_up.py`), so it is not reported as ignored
    either."""
    assert "power-up" not in flavor_words(card("Aerial Doombot"))
    assert "Power-up" not in ignored_keywords(card("Aerial Doombot"))


def test_cumulative_upkeep_label_is_not_swallowed_as_a_flavor_word():
    """Vexing Sphinx's "Cumulative upkeep—Discard a card." has no space
    around its em dash at all (unlike Power-up above), so it never even
    reaches the generalized flavor-word regex - and "cumulative upkeep" is
    also a CR 702.24 keyword name, a second, independent reason it must not
    be treated as a flavor word. `machines/keywords.executes` claims it since
    cumulative upkeep is built (CR 702.24a)."""
    assert "cumulative upkeep" not in flavor_words(card("Vexing Sphinx"))
    assert "Cumulative upkeep" not in ignored_keywords(card("Vexing Sphinx"))


def test_cr_keyword_names_covers_both_701_and_702_headings():
    from magic_cards_model.support import CR_KEYWORD_NAMES

    assert "power-up" in CR_KEYWORD_NAMES  # CR 702.193
    assert "cumulative upkeep" in CR_KEYWORD_NAMES  # CR 702.24
    assert "recruit" in CR_KEYWORD_NAMES  # CR 701.70
    assert "endure" in CR_KEYWORD_NAMES  # CR 701.63
    assert "daybound" in CR_KEYWORD_NAMES  # split half of CR 702.145's heading
    assert "nightbound" in CR_KEYWORD_NAMES


# -- T01: Partner / Choose a Background (CR 702.124a, deck construction) ----


def test_partner_needs_no_code():
    """CR 702.124a: partner abilities "modify the rules for deck construction
    in the Commander variant ... and function before the game begins" -
    inert in Modern/Pioneer/Standard."""
    from magic_cards_model.support import NEEDS_NO_CODE

    assert "partner" in NEEDS_NO_CODE
    assert "Partner" not in ignored_keywords(card("Sakashima of a Thousand Faces"))
    assert "Partner" not in ignored_keywords(card("Silas Renn, Seeker Adept"))


def test_choose_a_background_needs_no_code():
    from magic_cards_model.support import NEEDS_NO_CODE

    assert "choose a background" in NEEDS_NO_CODE
    assert "Choose a background" not in ignored_keywords(card("Gut, True Soul Zealot"))


# -- T01: the six built-but-unregistered keywords get named branches --------


def test_shroud_is_registered_as_executed():
    assert "Shroud" not in ignored_keywords(card("Elvish Lookout"))


def test_split_second_is_registered_as_executed():
    assert "Split second" not in ignored_keywords(card("Sudden Shock"))


@pytest.mark.parametrize("name", ["Fortress Kin-Guard", "Krumar Initiate"])
def test_endure_is_registered_as_executed(name):
    """Fortress Kin-Guard's endure has a literal printed count ("endures
    1"); Krumar Initiate's is an announced X ("endures X.") - both have to
    reach `_parse_endure_clause` through the same CR 107.3a substitution
    `classify_clauses` itself performs."""
    assert "Endure" not in ignored_keywords(card(name))


def test_recruit_is_registered_as_executed():
    assert "Recruit" not in ignored_keywords(card("Lake-town Lookout"))


def test_tiered_is_registered_as_executed():
    assert "Tiered" not in ignored_keywords(card("Fire Magic"))


def test_spree_is_registered_as_executed():
    assert "Spree" not in ignored_keywords(card("Insatiable Avarice"))


def test_tiered_registration_is_conditioned_on_the_profile_being_understood(monkeypatch):
    """The review focus: a registration must be conditioned on the machinery
    actually reading the card, never on the keyword name alone. Faking an
    unread modal profile for a Tiered card must make the registration
    disappear even though the keyword is still printed."""
    import magic_cards_model.support as support

    real_modal_profile = support.modal_profile

    def fake_modal_profile(printing):
        profile = real_modal_profile(printing)
        if profile is None:
            return None
        return profile.model_copy(update={"understood": False})

    monkeypatch.setattr(support, "modal_profile", fake_modal_profile)
    assert "tiered" not in support.executed_keywords(card("Fire Magic"))


# -- T01: OWNER RULE - a legal card cannot rest on a fail-closed notice -----


def _a_legal_notice_card() -> str:
    """The first pool card legal in Modern, Pioneer or Standard whose worst
    clause is `NOTICE`. Chosen dynamically: the owner rule makes every such
    card the next one the campaign reads, so any fixed name here goes stale
    (Final Showdown stood here until S21 read its last two Spree modes)."""
    for name in sorted(pool()):
        printing = card(name)
        if in_target_formats(printing) and classify_card(printing)[0] == NOTICE:
            return name
    pytest.fail("no legal pool card fails closed with a notice any more - pick a new vehicle")


def test_legal_cards_failing_closed_lists_a_legal_notice_card_as_a_gap():
    """A legal card that classifies `NOTICE` is a gap under the owner rule, not
    a clean pass, so it must be listed. Metamorphic Blast reads both modes
    since T05 (`test_changeling.py`), so it is not one."""
    vehicle = _a_legal_notice_card()
    gaps = dict(legal_cards_failing_closed([vehicle, "Metamorphic Blast"]))
    assert vehicle in gaps
    assert "Metamorphic Blast" not in gaps


def test_legal_cards_failing_closed_excludes_an_out_of_format_notice_card():
    """Bank Job is not_legal in Modern, Pioneer or Standard and also
    classifies `NOTICE` - the owner rule does not apply to it, so it must not
    be reported as a gap even when it is in the input list. (Frenzied
    Gorespawn was the example until T11 read its goad clause.)"""
    printing = card("Bank Job")
    assert not in_target_formats(printing)
    assert classify_card(printing)[0] == NOTICE
    gaps = dict(legal_cards_failing_closed(["Bank Job"]))
    assert "Bank Job" not in gaps


def test_legal_cards_failing_closed_excludes_a_handled_card():
    """A legal card whose worst clause is `HANDLED` is not a gap."""
    gaps = dict(legal_cards_failing_closed(["Lightning Bolt"]))
    assert "Lightning Bolt" not in gaps


def test_report_effects_prints_the_legal_gap_section():
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import report_effects

    vehicle = _a_legal_notice_card()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        report_effects([vehicle, "Metamorphic Blast", "Lightning Bolt"])
    output = buffer.getvalue()
    assert "Legal cards (Modern/Pioneer/Standard) failing closed with a notice" in output
    assert vehicle in output
    # Metamorphic Blast reads both modes since T05, so only the vehicle is left.
    assert "1 legal card(s) failing closed" in output


# -- T01: acceptance - the honest unbuilt-keyword list -----------------------


def test_the_pool_wide_ignored_keyword_report_matches_the_expected_gap_list():
    """The acceptance check for the whole rewrite: with every ability word,
    flavor word, format exclusion and registration above in place, the
    in-format pool's own unexecuted-keyword list is exactly the
    genuinely unbuilt CR 701/702 keywords - the pre-existing false
    positives (ability words, flavor words, Partner/Choose a Background,
    the seven now-registered built keywords (T01's six plus T02's Waterbend),
    the stale "ascend" entry) are all gone, and no new false positive has
    appeared in their place. Explore is off this list as of T08:
    `machines/effects._parse_explores_clause` reads the generic "<subject>
    explores[, then it explores again]" shape (CR 701.44a-d) off triggered,
    activated, and spell text alike, so the reported Amalia Benavides Aguirre
    and every other explore-bearing pool card resolve rather than falling
    through unexecuted. Discover is off it as of T09 (`machines/keywords.
    discover`, reached through `effects._parse_discover_clause`). Monstrosity
    is off it as of T10 (`Game.become_monstrous`, reached through
    `effects._parse_monstrosity_clause`). Sneak is off it as of T13
    (`machines/casting.keyword_cast_options`, CR 702.190a). Miracle is off it
    as of T14 (`machines/keywords._miracle_ability`/`_miracle_effect`, the
    reveal asked from `Game.draw_cards`). Compleated is off it as of T17:
    `machines/replacement._compleated_modifier` reads the keyword directly
    (CR 702.150a), the same hand-named shape Sunburst already used, and every
    compleated pool printing resolves through it rather than falling through
    unexecuted. Saddle (CR 702.171a), Suspect and Venture into the dungeon
    (CR 701.60a, CR 701.49a), Bloodthirst (CR 702.54a), Increment (CR
    702.191a) and Web-slinging (CR 702.188a) are built. Flanking (CR
    702.25a), Forecast (CR 702.57a), Riot (CR 702.136a), Vanishing (CR
    702.63a) and Decayed (CR 702.147a) came in with the condition campaign's
    proof printings and were listed here as expected gaps until the
    regression audit built them: the list is empty again."""
    from magic_cards_model.support import in_target_formats

    names = [name for name in pool() if in_target_formats(card(name))]
    by_keyword: dict[str, list[str]] = {}
    for name in names:
        for keyword in ignored_keywords(card(name)):
            by_keyword.setdefault(keyword, []).append(name)
    assert by_keyword == {}


# -- CR 702.11d: "Hexproof from" has an execution path ----------------------


@pytest.mark.parametrize(
    "name", ["Knight of Grace", "Knight of Malice", "Nevinyrral, Urborg Tyrant"]
)
def test_hexproof_from_is_executed_by_the_shared_hexproof_check(name: str) -> None:
    """`Game.hexproof_refusal` enforces CR 702.11d for spells and abilities
    (`tests/scenarios/test_hexproof_abilities.py`), so the keyword is not
    ignored."""
    assert "Hexproof from" not in ignored_keywords(card(name))


@pytest.mark.parametrize(
    "name", ["Leyline of Sanctity", "Aegis of the Gods", "True Believer", "Ivory Mask"]
)
def test_a_player_hexproof_or_shroud_static_line_is_handled(name: str) -> None:
    """ "You have hexproof." / "You have shroud." are read by
    `Game.player_hexproof`/`Game.player_has_shroud`
    (`tests/scenarios/test_player_hexproof_shroud.py`)."""
    statics = {
        c.text.split(".")[0]: c.category
        for c in classify_clauses(card(name))
        if c.source == "static"
    }
    grant = next(text for text in statics if text.startswith("You have"))
    assert statics[grant] == HANDLED


def test_knight_of_graces_conditional_pump_is_handled() -> None:
    """ "This creature gets +1/+0 as long as any player controls a black
    permanent." is read by `machines/layers.py`
    (`tests/scenarios/test_hexproof_abilities.py`)."""
    statics = [
        c.category for c in classify_clauses(card("Knight of Grace")) if c.source == "static"
    ]
    assert statics == [HANDLED]


# -- T12: the "you and <group>" player half is granted, so it reads HANDLED --


def test_veil_of_summers_player_subject_split_classifies_as_handled() -> None:
    """Veil of Summer's third sentence, "You and permanents you control gain
    hexproof from blue and from black until end of turn", is a compound
    subject `_parse_you_and_group_gain_clause` (`machines/effects.py`) splits
    in two. T5/G2b granted the group half for real but left the player half
    recorded as a `PlayerSubjectSplitNotice` (`Game.player_subject_split_
    notices`) rather than applied - a deliberately separate task's scope at
    the time (`docs/engine-coverage.md`'s T5/G2b row). T12 closed that gap:
    the player half is now handed to `parse_clause_effect`, the same reader
    that already read this exact sentence
    (`tests/scenarios/test_player_hexproof_shroud.py::
    test_the_clause_parser_reads_hexproof_from_two_qualities_on_you`), so
    both halves of the split now apply and `classify_card`'s worst-clause
    verdict is `HANDLED`
    (`tests/scenarios/test_player_hexproof_from_quality.py`,
    `tests/scenarios/test_veil_of_summer.py::
    test_the_player_half_is_granted_too`).
    """
    category, _ = classify_card(card("Veil of Summer"))
    assert category == HANDLED


def test_a_you_and_group_gain_clause_is_handled_once_both_halves_apply() -> None:
    """The same compound-subject shape, read directly off Veil's own spell
    face by `classify_clauses`: the clause itself must never read `SILENT`
    (the group half is a real, working grant), and now that T12 grants the
    player half too, it reads `HANDLED` rather than the `NOTICE` it fell back
    to while only the group half applied
    (`_leaves_you_and_group_player_half_unread` now actually tries
    `parse_clause_effect` on the player-half predicate instead of
    downgrading the clause unconditionally)."""
    clauses = [
        c
        for c in classify_clauses(card("Veil of Summer"))
        if "you and permanents you control gain" in c.text.lower()
    ]
    assert clauses, "Veil's compound-subject sentence must still be its own clause"
    assert [c.category for c in clauses] == [HANDLED]


# -- F6 W1: the sweep reports `card_support`'s verdict, not its own ----------


def test_the_effect_report_counts_are_card_supports_own_verdicts():
    """`report_effects` prints `magic_cards_model.support.card_support`'s
    per-card verdict for every pool card with rules text - the one source of
    truth a deck checker also reads - so its closing counts line is exactly
    the tally of `card_support(...).effect_outcome` over the same names."""
    import io
    from collections import Counter
    from contextlib import redirect_stdout

    from scripts.sweep_pool import report_effects

    from magic_cards_model.support import card_support

    names = sorted(pool())
    tally = Counter(
        support.effect_outcome
        for support in (card_support(card(name)) for name in names)
        if support.has_rules_text
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        silent = report_effects(names)
    output = buffer.getvalue()
    assert silent == tally[SILENT]
    assert f"({tally[HANDLED]} handled by a registry row or a parser" in output
    assert f"{tally[NOTICE]} fail closed with a notice" in output
    assert f"{tally[STATIC_UNAUDITED]} rest on a static ability nobody here audits" in output


def test_the_keyword_report_lists_card_supports_silent_keyword_clauses():
    """`report_keywords` lists every keyword `card_support` judges silent,
    with the cards carrying it, and nothing else."""
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import report_keywords

    from magic_cards_model.support import card_support

    names = sorted(pool())
    expected: dict[str, set[str]] = {}
    for name in names:
        for clause in card_support(card(name)).clauses:
            if clause.kind == "keyword" and clause.status == "silent":
                expected.setdefault(clause.text, set()).add(name)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        count = report_keywords(names)
    output = buffer.getvalue()
    assert count == len(expected)
    for keyword, cards in expected.items():
        assert f"  {keyword:<18} {', '.join(sorted(cards))}" in output


def test_the_card_report_prints_card_supports_clauses():
    """`--card` prints each of `card_support`'s clause verdicts and its
    worst-clause outcome."""
    import io
    from contextlib import redirect_stdout

    from scripts.sweep_pool import main

    from magic_cards_model.support import card_support

    support = card_support(card("Bloodghast"))
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        main(["--card", "Bloodghast"])
    output = buffer.getvalue()
    for clause in support.clauses:
        if clause.kind == "keyword":
            continue
        assert f"    {clause.outcome:<17} [{clause.source}] {clause.text[:60]}" in output
    assert f"outcome (worst clause): {support.effect_outcome}" in output


def test_no_abandoned_proof_candidate_printings_pollute_the_pool():
    """ecl-T3 review finding: while searching for a second printing to prove
    a reader on, an agent fetches several candidates with
    `scripts/add_card.py` and keeps only the one actually used in a scenario -
    but a candidate that loses out (Suncleanser, Decimator Beetle and
    Cauldron Haze here, plus Tam, Mindful First-Year, which turned out not to
    carry the needed shape at all) is still real Scryfall json sitting in
    `src/magic_cards_model/data/printings/`, so `sweep_pool.py`'s pool-wide
    walk (`tests.cards.pool`, a bare glob of that directory) counts its own
    unhandled clauses as new silent/notice regressions on a card no test
    exercises and no task claims. COMMON ACCEPTANCE (i): no card outside a
    task becomes silent or notice. A losing candidate search is recorded in
    `MEMORY.md`, not kept as a live pool entry."""
    abandoned = {
        "Suncleanser",
        "Decimator Beetle",
        "Cauldron Haze",
        "Tam, Mindful First-Year",
    }
    present = abandoned & set(pool())
    assert not present, f"abandoned proof-candidate printings still in the pool: {sorted(present)}"

"""Reading replacement (CR 614) and prevention (CR 615) effects off real cards.

Every card here is a real Scryfall printing from `tests/fixtures/cards`. The
bulk of the file is the boundary: text that looks like a replacement effect and
is not one - triggered abilities, alternative costs, reminder text, and
conditionals inside a resolving effect.

Every CR number cited below was looked up with the spellslinger
`knowledge_search` tool rather than recalled.
"""

import pytest

from magic_cards_model.machines.replacement import (
    ReplacementKind,
    effects_of_kind,
    parse_replacement_effects,
    prevention_effects,
    replacements_of,
    strip_reminder_text,
    unparsed_effects,
)
from tests.cards import card


def kinds(name: str) -> list[ReplacementKind]:
    return [effect.kind for effect in parse_replacement_effects(card(name))]


def only(name: str, kind: ReplacementKind | None = None):
    """The single effect a card reports, optionally asserting its kind."""
    effects = parse_replacement_effects(card(name))
    assert len(effects) == 1, f"{name} reported {[e.kind.value for e in effects]}"
    if kind is not None:
        assert effects[0].kind is kind
    return effects[0]


# --------------------------------------------------------------------------
# CR 614.1a - "If ... would ..., ... instead"
# --------------------------------------------------------------------------


def test_if_would_instead_splits_the_event_from_the_replacement():
    """CR 614.1a: effects that use the word "instead" are replacement effects."""
    effect = only("Rest in Peace", ReplacementKind.IF_WOULD_INSTEAD)

    assert effect.event == "a card or token would be put into a graveyard from anywhere"
    assert effect.replacement == "exile it"


def test_instead_may_lead_the_replacement_clause():
    """Kalitas puts "instead" before the replacement, not after it.

    Both orders mean the same thing, so both must yield the same shape.
    """
    effect = only("Kalitas, Traitor of Ghet", ReplacementKind.IF_WOULD_INSTEAD)

    assert effect.event == "a nontoken creature an opponent controls would die"
    assert effect.replacement == "exile that card and create a 2/2 black Zombie creature token"
    assert "instead" not in effect.replacement


def test_instead_may_sit_mid_clause_and_mark_the_effect_optional():
    """Abundance reads "you may instead choose ...", the third placement."""
    effect = only("Abundance", ReplacementKind.IF_WOULD_INSTEAD)

    assert effect.event == "you would draw a card"
    assert effect.replacement.startswith("you may choose land or nonland")
    assert effect.optional


def test_an_event_clause_with_commas_still_ends_at_the_right_one():
    """Sanctifier en-Vec's replaced event lists three object kinds, comma separated.

    A naive "up to the first comma" split would cut the event to
    "a black or red permanent", which is a different card.
    """
    effects = effects_of_kind(card("Sanctifier en-Vec"), ReplacementKind.IF_WOULD_INSTEAD)

    (effect,) = effects
    assert effect.event == (
        "a black or red permanent, spell, or card not on the battlefield "
        "would be put into a graveyard"
    )


def test_a_card_can_carry_two_replacement_effects():
    assert kinds("Doubling Season") == [
        ReplacementKind.IF_WOULD_INSTEAD,
        ReplacementKind.IF_WOULD_INSTEAD,
    ]
    assert kinds("Alhammarret's Archive") == [
        ReplacementKind.IF_WOULD_INSTEAD,
        ReplacementKind.IF_WOULD_INSTEAD,
    ]


# --------------------------------------------------------------------------
# Self-replacement versus a general effect (CR 614.12)
# --------------------------------------------------------------------------


def test_an_effect_about_the_card_itself_is_marked_self_replacement():
    """CR 614.12: such effects "may come from the permanent itself if they
    affect only that permanent"."""
    effect = only("Mox Diamond", ReplacementKind.IF_WOULD_INSTEAD)

    assert effect.event == "this artifact would enter"
    assert effect.self_replacement
    assert effect.optional  # "you may discard a land card instead"


def test_an_effect_about_other_objects_is_not_self_replacement():
    """Gather Specimens replaces an event affecting somebody else's creatures."""
    effect = only("Gather Specimens", ReplacementKind.IF_WOULD_INSTEAD)

    assert effect.event == (
        "a creature would enter the battlefield under an opponent's control this turn"
    )
    assert not effect.self_replacement


def test_a_card_naming_itself_counts_as_self_replacement():
    """Older templating spells the card's own name out instead of "this land"."""
    effect = only("Lupine Harbingers", ReplacementKind.ENTERS_WITH)

    assert effect.subject == "Lupine Harbingers"
    assert effect.self_replacement


# --------------------------------------------------------------------------
# CR 614.1c - entering the battlefield
# --------------------------------------------------------------------------


def test_enters_tapped_new_wording():
    effect = only("Tinder Farm", ReplacementKind.ENTERS_TAPPED)

    assert effect.text == "This land enters tapped."
    assert effect.tapped
    assert effect.self_replacement
    assert effect.condition is None


def test_enters_tapped_old_wording():
    """WOTC shortened "enters the battlefield" to "enters" in 2024.

    Scryfall rewrote oracle text wholesale, so the long form is now rare, but
    Forsaken Crossroads still carries it - and carries the long form of the
    CR 614.1c "As [this] enters" template too.
    """
    effects = parse_replacement_effects(card("Forsaken Crossroads"))

    assert [effect.kind for effect in effects] == [
        ReplacementKind.ENTERS_TAPPED,
        ReplacementKind.AS_ENTERS,
    ]
    assert effects[0].text == "Forsaken Crossroads enters the battlefield tapped."
    assert effects[1].replacement == "choose a color"


def test_a_conditional_enters_tapped_keeps_its_condition():
    """The modal double-faced lands split the choice across two sentences."""
    (effect,) = effects_of_kind(card("Shatterskull Smashing"), ReplacementKind.ENTERS_TAPPED)

    assert effect.condition == "you don't"
    assert effect.face == "Shatterskull, the Hammer Pass"


def test_enters_with_a_fixed_number_of_counters():
    effect = only("Kalonian Hydra", ReplacementKind.ENTERS_WITH)

    assert effect.amount == 4
    assert effect.counter_kind == "+1/+1"
    assert not effect.variable_amount


def test_enters_with_x_counters_is_variable():
    effect = only("Hangarback Walker", ReplacementKind.ENTERS_WITH)

    assert effect.amount is None
    assert effect.variable_amount
    assert effect.counter_kind == "+1/+1"


def test_enters_with_a_single_counter_reads_the_article_as_one():
    (effect,) = effects_of_kind(card("Diamond City"), ReplacementKind.ENTERS_WITH)

    assert effect.amount == 1
    assert effect.counter_kind == "shield"


def test_enters_as_a_copy():
    """CR 616.1c singles out entering as a copy, so it gets its own kind."""
    effect = only("Clone", ReplacementKind.ENTERS_AS_COPY)

    assert effect.copy_of == "any creature on the battlefield"
    assert effect.optional
    assert not effect.tapped


def test_entering_tapped_as_a_copy_is_one_effect_not_two():
    """Vesuva folds tapped and copy into a single sentence.

    Reading it as an ENTERS_TAPPED would lose the copy, and reading it twice
    would double-count one replacement effect.
    """
    effect = only("Vesuva", ReplacementKind.ENTERS_AS_COPY)

    assert effect.copy_of == "any land on the battlefield"
    assert effect.tapped


def test_echoing_deeps_except_clause_reads_as_added_types_with_no_pt():
    """ "except it's a Cave in addition to its other types" has no body.

    `_COPY_EXCEPT_PT_AND_TYPES` used to require a power/toughness pair before
    the type list, so this clause fell all the way through to `None` -
    conflated downstream with "no exception at all" by `effect.copy_exception
    or CopyException()`, which is what let Echoing Deeps silently copy a
    graveyard land without ever becoming a Cave. It now reads as a types-only
    exception: no name, no power/toughness, `added_subtypes=("Cave",)` (CR
    205.3: "Cave" is not one of CR 300.1's card types, so it lands as a
    subtype, not a type).
    """
    effect = only("Echoing Deeps", ReplacementKind.ENTERS_AS_COPY)

    assert effect.copy_of == "any land card in a graveyard"
    assert effect.tapped
    assert effect.copy_exception_unparsed is None
    exception = effect.copy_exception
    assert exception is not None
    assert exception.name is None
    assert exception.power is None
    assert exception.toughness is None
    assert exception.added_types == ()
    assert exception.added_subtypes == ("Cave",)


def test_mockingbirds_except_clause_grants_an_ability_as_part_of_the_copy():
    """ "... and it has flying" is CR 707.9a's gained ability: the whole tail
    reads, the Bird subtype and the Flying ability line both, so nothing is
    left in `copy_exception_unparsed`."""
    effect = only("Mockingbird", ReplacementKind.ENTERS_AS_COPY)

    assert effect.copy_exception_unparsed is None
    assert effect.copy_exception is not None
    assert effect.copy_exception.added_subtypes == ("Bird",)
    assert effect.copy_exception.added_abilities == ("Flying",)


def test_superior_spider_mans_except_clause_is_unaffected():
    """A name plus a power/toughness-and-types clause: readable before and
    after the power/toughness group became optional, and untouched by the new
    `copy_exception_unparsed` field - it is only ever set when parsing fails.
    """
    effect = only("Superior Spider-Man", ReplacementKind.ENTERS_AS_COPY)

    assert effect.copy_exception_unparsed is None
    exception = effect.copy_exception
    assert exception is not None
    assert exception.name == "Superior Spider-Man"
    assert (exception.power, exception.toughness) == (4, 4)
    assert exception.added_subtypes == ("Spider", "Human", "Hero")


def test_as_this_enters():
    effect = only("Runed Halo", ReplacementKind.AS_ENTERS)

    assert effect.subject == "this enchantment"
    assert effect.replacement == "choose a card name"
    assert effect.self_replacement


def test_as_this_enters_alongside_a_static_ability():
    """Voice of All's third line is a static ability, not a second effect."""
    effect = only("Voice of All", ReplacementKind.AS_ENTERS)

    assert effect.replacement == "choose a color"


# --------------------------------------------------------------------------
# CR 614.1e - "As [this] is turned face up"
# --------------------------------------------------------------------------


def test_as_enters_or_is_turned_face_up_is_two_effects():
    """Aquamorph Entity folds CR 614.1c and CR 614.1e into one sentence.

    They watch two different events, so both are reported off the same
    sentence rather than one arbitrarily winning.
    """
    effects = parse_replacement_effects(card("Aquamorph Entity"))

    assert [effect.kind for effect in effects] == [
        ReplacementKind.AS_ENTERS,
        ReplacementKind.AS_TURNED_FACE_UP,
    ]
    assert {effect.subject for effect in effects} == {"this creature"}
    assert {effect.replacement for effect in effects} == {"it becomes your choice of 5/1 or 1/5"}
    assert {effect.text for effect in effects} == {
        "As this creature enters or is turned face up, it becomes your choice of 5/1 or 1/5."
    }


def test_when_turned_face_up_is_a_trigger_not_a_replacement():
    """CR 614.1e is "As ... is turned face up"; "When ..." is CR 603.1.

    Brine Elemental's line contains "skips", which is a CR 614.1b keyword. The
    skip is the trigger's *effect*, so it is reported with `from_trigger` set
    and compiles to nothing - `replacements_of` stays empty, and no battlefield
    scan can mistake it for a static ability the permanent generates.

    This asserted a flat empty parse before the "[player] skips ..." template
    existed. The boundary that assertion was protecting is the behavioural one,
    and it is asserted here directly instead of by proxy.
    """
    (effect,) = parse_replacement_effects(card("Brine Elemental"))
    assert effect.kind is ReplacementKind.SKIP
    assert effect.from_trigger
    assert effect.subject == "each opponent"
    assert effect.event == "their next untap step"
    assert replacements_of(card("Brine Elemental")) == []


# --------------------------------------------------------------------------
# CR 614.1b / 614.10 - skip effects
# --------------------------------------------------------------------------


def test_skip_your_draw_step():
    """CR 614.10: "Skip [something]" is "Instead of doing [something], do nothing"."""
    (effect,) = effects_of_kind(card("Dragon Appeasement"), ReplacementKind.SKIP)

    assert effect.event == "your draw step"
    assert effect.replacement is None


def test_skip_the_untap_step_mid_paragraph():
    """Savor the Moment's skip is the second sentence of one ability."""
    effect = only("Savor the Moment", ReplacementKind.SKIP)

    assert effect.event == "the untap step of that turn"


def test_a_skip_alongside_a_trigger_and_a_replacement():
    """Necrodominance carries four abilities; two of them are ours."""
    assert kinds("Necrodominance") == [
        ReplacementKind.SKIP,
        ReplacementKind.IF_WOULD_INSTEAD,
    ]


# --------------------------------------------------------------------------
# CR 614.1a variants - "instead of" and "rather than"
# --------------------------------------------------------------------------


def test_instead_of_leading_the_sentence():
    effect = only("Agent of Acquisitions", ReplacementKind.INSTEAD_OF)

    assert effect.event == "drafting a card from a booster pack"
    assert effect.replacement == "you may draft each card in that booster pack, one at a time"
    assert effect.optional


def test_instead_of_trailing_the_sentence():
    """Delay replaces where a countered spell goes."""
    (effect,) = effects_of_kind(card("Delay"), ReplacementKind.INSTEAD_OF)

    assert effect.event == "putting it into its owner's graveyard"
    assert effect.replacement == "exile it with three time counters on it"
    assert effect.condition == "the spell is countered this way"


def test_rather_than_gets_its_own_kind():
    """CR 604.2: static abilities create continuous effects, "some of which"
    are replacement effects - some, not all.

    Doran modifies the combat damage assignment rule of CR 510.1a rather than
    replacing an event, so it is reported as RATHER_THAN and not folded in with
    the genuine "instead" replacements.
    """
    effect = only("Doran, the Siege Tower", ReplacementKind.RATHER_THAN)

    assert effect.replacement == "Each creature assigns combat damage equal to its toughness"
    assert effect.event == "its power"


def test_an_alternative_cost_is_not_a_replacement_effect():
    """CR 118.9: an alternative cost is paid "rather than paying the spell's
    mana cost". It reads like a replacement effect and is not one, so it is
    dropped entirely rather than reported as unparsed.
    """
    assert parse_replacement_effects(card("Allosaurus Rider")) == []


# --------------------------------------------------------------------------
# CR 615 - prevention
# --------------------------------------------------------------------------


def test_prevent_the_next_n_damage_reads_the_number_and_the_target():
    """CR 615.1a: effects that use the word "prevent" are prevention effects."""
    (effect,) = prevention_effects(card("Bandage"))

    assert effect.kind is ReplacementKind.PREVENT_NEXT
    assert effect.amount == 1
    assert effect.damage_target == "any target"
    assert not effect.combat_only
    assert effect.is_prevention


def test_prevent_all_damage_has_no_number():
    """A shield with a number and a blanket shield are different effects.

    Fog prevents all combat damage; Bandage prevents exactly 1. A parser that
    reported both as "prevention" with no amount would lose the distinction.
    """
    effect = only("Fog", ReplacementKind.PREVENT_ALL)

    assert effect.amount is None
    assert not effect.variable_amount
    assert effect.combat_only
    assert effect.event == "all combat damage that would be dealt this turn"


def test_prevent_all_damage_alongside_a_keyword():
    """Angelsong prints the same effect with cycling under it."""
    assert kinds("Angelsong") == [ReplacementKind.PREVENT_ALL]


def test_the_next_time_a_source_would_deal_damage():
    """CR 615.8 covers prevention aimed at the next damage from one source.

    Awe Strike's second sentence refers back to "the damage prevented this
    way" (CR 615.5) and is part of this effect, not a second one.
    """
    effect = only("Awe Strike", ReplacementKind.PREVENT_NEXT_TIME)

    assert effect.subject == "target creature"
    assert effect.event == "target creature would deal damage this turn"


def test_prevention_written_as_if_would():
    """Angel of Suffering uses the CR 614.1a frame with a CR 615 payload.

    It has no "instead", so classifying by frame alone would call it a plain
    replacement effect. The presence of "prevent" is what decides it.
    """
    effect = only("Angel of Suffering", ReplacementKind.PREVENT_IF_WOULD)

    assert effect.event == "damage would be dealt to you"
    assert effect.replacement == "prevent that damage and mill twice that many cards"
    assert effect.is_prevention


def test_damage_that_cant_be_prevented_is_not_a_prevention_effect():
    """CR 615.12: unpreventable damage still has prevention effects applied to
    it, they just prevent nothing. The line is not itself a prevention effect.

    Questing Beast is the awkward case: the sentence contains both "would" and
    "prevented" and is neither a replacement nor a prevention effect, so it
    comes back UNPARSED rather than claimed.
    """
    assert prevention_effects(card("Questing Beast")) == []

    (effect,) = unparsed_effects(card("Questing Beast"))
    assert effect.text == (
        "Combat damage that would be dealt by creatures you control can't be prevented."
    )


# --------------------------------------------------------------------------
# The boundary against triggered abilities (CR 603.1)
# --------------------------------------------------------------------------


def test_a_trigger_and_a_replacement_on_one_card_yield_only_the_replacement():
    """Rest in Peace's first line is a trigger, its second a replacement effect."""
    effects = parse_replacement_effects(card("Rest in Peace"))

    assert len(effects) == 1
    assert "exile all graveyards" not in effects[0].raw


def test_a_triggers_trailing_instructions_belong_to_the_trigger():
    """CR 603.1 writes a trigger as "[When/Whenever/At] [condition], [effect].
    [Instructions (if any).]".

    Forsaken Crossroads' trigger runs across two sentences and the second one
    ends in "instead". Claiming it would invent a replacement effect the card
    does not have.
    """
    effects = parse_replacement_effects(card("Forsaken Crossroads"))

    assert all("scry 1" not in effect.raw for effect in effects)
    assert all("you may untap" not in effect.text for effect in effects)


@pytest.mark.parametrize(
    "name",
    [
        "Kalonian Hydra",  # "Whenever this creature attacks, double the number of counters"
        "Hangarback Walker",  # "When this creature dies, create ... for each +1/+1 counter"
        "Sanctifier en-Vec",  # "When this creature enters, exile all cards that are black or red"
    ],
)
def test_no_trigger_paragraph_is_ever_claimed(name):
    for effect in parse_replacement_effects(card(name)):
        assert not effect.raw.startswith(("When", "Whenever", "At "))


def test_a_purely_triggered_card_reports_nothing():
    assert parse_replacement_effects(card("Ragavan, Nimble Pilferer")) == []
    assert parse_replacement_effects(card("Delver of Secrets")) == []


# --------------------------------------------------------------------------
# Reminder text (CR 207.2a)
# --------------------------------------------------------------------------


def test_reminder_text_is_stripped_and_kept():
    """Diamond City's reminder text is a complete "... instead" sentence.

    The shield counter's reminder describes a replacement effect the *counter*
    creates, not one the card's rules text states. Parsing it would report a
    second effect that is not in the card's text box as rules text.
    """
    (effect,) = effects_of_kind(card("Diamond City"), ReplacementKind.ENTERS_WITH)

    assert effect.text == "This land enters with a shield counter on it."
    assert (
        effect.reminder
        == "If it would be dealt damage or destroyed, remove a shield counter from it instead."
    )
    assert "instead" in effect.raw  # still there in the raw paragraph


def test_dredge_reminder_text_is_not_read_as_a_replacement_effect():
    """Dredge's reminder is a textbook "If you would draw a card ... instead".

    Dakmor Salvage's only replacement effect is that it enters tapped. The
    dredge replacement applies from the graveyard and is created by the dredge
    keyword, not by the reminder sentence.
    """
    assert kinds("Dakmor Salvage") == [ReplacementKind.ENTERS_TAPPED]


def test_strip_reminder_text_returns_both_halves():
    rules_text, reminder = strip_reminder_text(card("Angelsong").oracle_text)

    assert rules_text == "Prevent all combat damage that would be dealt this turn.\nCycling {2}"
    assert reminder == "{2}, Discard this card: Draw a card."


# --------------------------------------------------------------------------
# Multifaced cards
# --------------------------------------------------------------------------


def test_both_faces_are_parsed_and_labelled():
    """Shatterskull Smashing's replacement effect is only on the back face."""
    effects = parse_replacement_effects(card("Shatterskull Smashing"))
    by_face: dict[str, list[ReplacementKind]] = {}
    for effect in effects:
        by_face.setdefault(effect.face, []).append(effect.kind)

    assert by_face == {
        "Shatterskull Smashing": [ReplacementKind.UNPARSED],
        "Shatterskull, the Hammer Pass": [
            ReplacementKind.AS_ENTERS,
            ReplacementKind.ENTERS_TAPPED,
        ],
    }


def test_a_single_faced_card_has_no_face_label():
    assert only("Fog").face is None


# --------------------------------------------------------------------------
# Refusing to guess
# --------------------------------------------------------------------------


def test_instead_without_would_is_not_claimed_as_a_replacement():
    """Urza's Tower's "add {C}{C}{C} instead" is a conditional inside a mana
    ability's effect, not a replacement of an event.

    CR 614.1a says effects using "instead" are replacement effects, but that
    describes the templating of effects that watch an event. This one watches
    nothing, so it is reported UNPARSED rather than claimed.
    """
    (effect,) = unparsed_effects(card("Urza's Tower"))

    assert effect.text.endswith("add {C}{C}{C} instead.")
    assert not effect.parsed
    assert effect.event is None
    assert effect.replacement is None


def test_a_spell_that_modifies_its_own_effect_is_not_claimed():
    """Shatterskull Smashing's front face doubles its own damage on resolution.

    That is CR 614.15 self-replacement, which this parser does not model - the
    honest answer is UNPARSED, not a wrong IF_WOULD_INSTEAD.
    """
    (effect,) = [
        effect
        for effect in unparsed_effects(card("Shatterskull Smashing"))
        if effect.face == "Shatterskull Smashing"
    ]

    assert "twice X damage" in effect.text


def test_an_opening_hand_effect_is_not_claimed():
    """CR 103.6a lets Leyline start on the battlefield. It is not CR 614."""
    assert kinds("Leyline of the Void") == [ReplacementKind.IF_WOULD_INSTEAD]


def test_a_card_with_no_cue_words_reports_nothing():
    for name in ("Grizzly Bears", "Lightning Bolt", "Counterspell", "Sol Ring", "Forest"):
        assert parse_replacement_effects(card(name)) == [], name


def test_a_player_skips_wording_is_parsed():
    """CR 614.1b's other wording, read off the one card in the pool with it.

    Brine Elemental puts it inside a triggered ability, so it comes back
    flagged `from_trigger` and performs nothing - see
    `test_when_turned_face_up_is_a_trigger_not_a_replacement` above. The shape
    itself is parsed either way, which is what this asserts.
    """
    assert effects_of_kind(card("Brine Elemental"), ReplacementKind.SKIP)

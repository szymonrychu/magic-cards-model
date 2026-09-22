"""Reading abilities off real oracle text.

Every card here is a real Scryfall printing from tests/fixtures/cards. The
corner cases are the point of the file: reminder text that contains a colon, a
cost that is a comma-separated list, an intervening `if`, a keyword list on one
line, and an ability a card grants to something else rather than has.
"""

import pytest

from magic_cards_model.machines import (
    AbilityKind,
    CostKind,
    TriggerEvent,
    TriggerWord,
    abilities_of_kind,
    intrinsic_land_ability,
    parse_abilities,
    parse_mana_abilities,
)
from magic_cards_model.models import Color
from tests.cards import card

# --------------------------------------------------------------------------
# Mana abilities (CR 605) - the behaviour the mana payment path depends on
# --------------------------------------------------------------------------


def test_a_basic_land_adds_one_of_its_colour():
    (ability,) = parse_mana_abilities(card("Forest"))

    assert ability.produces() == [Color.GREEN]
    assert ability.amount == 1
    assert not ability.is_choice


def test_sol_ring_adds_two():
    """The case Scryfall's produced_mana cannot express."""
    (ability,) = parse_mana_abilities(card("Sol Ring"))

    assert ability.produces() == [Color.COLORLESS, Color.COLORLESS]
    assert ability.amount == 2


def test_a_creature_with_a_mana_ability_is_read_like_a_land():
    (ability,) = parse_mana_abilities(card("Llanowar Elves"))

    assert ability.produces() == [Color.GREEN]


def test_a_card_with_two_mana_abilities_yields_both():
    green, red_white = parse_mana_abilities(card("Tinder Farm"))

    assert green.produces() == [Color.GREEN]
    assert red_white.produces() == [Color.RED, Color.WHITE]
    assert red_white.costs_mana is False  # sacrificing is not a mana cost


def test_a_card_with_no_mana_ability_yields_nothing():
    assert parse_mana_abilities(card("Grizzly Bears")) == []
    assert parse_mana_abilities(card("Lightning Bolt")) == []


def test_asking_an_ability_for_a_colour_it_cannot_make_is_an_error():
    """Corner case: no silently returning the wrong colour."""
    green = parse_mana_abilities(card("Tinder Farm"))[0]

    with pytest.raises(ValueError, match=r"adds \['G'\], not R"):
        green.produces(Color.RED)


def test_asking_for_the_colour_an_ability_makes_is_fine():
    (ability,) = parse_mana_abilities(card("Island"))

    assert ability.produces(Color.BLUE) == [Color.BLUE]


def test_any_colour_sources_insist_on_a_choice():
    """Corner case: `Add one mana of any color` cannot be resolved for you."""
    (ability,) = parse_mana_abilities(card("Birds of Paradise"))

    assert ability.any_color
    assert ability.is_choice
    assert ability.amount == 1
    assert ability.produces(Color.BLUE) == [Color.BLUE]

    with pytest.raises(ValueError, match="pass the colour chosen"):
        ability.produces()


def test_keyword_lines_are_not_mistaken_for_abilities():
    """Birds has `Flying` above its mana ability; only the ability is read."""
    abilities = parse_mana_abilities(card("Birds of Paradise"))

    assert len(abilities) == 1


def test_granted_abilities_are_not_the_cards_own():
    """Chromatic Lantern grants a mana ability to lands and also has one.

    The granted one is printed in quotes, so only the unquoted one counts.
    """
    (ability,) = parse_mana_abilities(card("Chromatic Lantern"))

    assert ability.any_color


def test_a_granted_ability_reads_as_a_static_ability():
    """CR 604.1: `Lands you control have "..."` is a statement, not an ability
    this permanent can activate."""
    granted, own = parse_abilities(card("Chromatic Lantern"))

    assert granted.kind is AbilityKind.STATIC
    assert granted.text == 'Lands you control have "{T}: Add one mana of any color."'
    assert own.kind is AbilityKind.ACTIVATED


def test_a_mana_ability_with_a_non_tap_cost_is_activated_but_not_a_mana_source():
    """Skirk Prospector's `Sacrifice a Goblin: Add {R}.` is a mana ability by
    CR 605.1a, but `parse_mana_abilities` only reads `{T}: Add ...`."""
    (ability,) = parse_abilities(card("Skirk Prospector"))

    assert ability.kind is AbilityKind.ACTIVATED
    assert ability.mana is not None
    assert ability.mana.produces() == [Color.RED]
    assert parse_mana_abilities(card("Skirk Prospector")) == []


# --------------------------------------------------------------------------
# Activated abilities (CR 602)
# --------------------------------------------------------------------------


def test_an_activated_ability_splits_at_the_colon():
    """CR 602.1a: the activation cost is everything before the colon."""
    (ability,) = parse_abilities(card("Wild Mongrel"))

    assert ability.kind is AbilityKind.ACTIVATED
    assert ability.cost == "Discard a card"
    assert ability.effect == (
        "This creature gets +1/+1 and becomes the color of your choice until end of turn."
    )
    assert [c.kind for c in ability.costs] == [CostKind.DISCARD]


def test_a_comma_separated_cost_is_split_into_its_pieces():
    (ability,) = parse_abilities(card("Vampiric Rites"))

    assert ability.cost == "{1}{B}, Sacrifice a creature"
    assert [(c.kind, c.text) for c in ability.costs] == [
        (CostKind.MANA, "{1}{B}"),
        (CostKind.SACRIFICE, "Sacrifice a creature"),
    ]


def test_tapping_is_told_apart_from_paying_mana():
    tap_only = [a for a in parse_abilities(card("Tinder Farm")) if a.kind is AbilityKind.ACTIVATED]

    assert [c.kind for c in tap_only[0].costs] == [CostKind.TAP]
    assert [c.kind for c in tap_only[1].costs] == [CostKind.TAP, CostKind.SACRIFICE]


def test_paying_life_is_a_cost_kind_of_its_own():
    (ability,) = abilities_of_kind(card("Griselbrand"), AbilityKind.ACTIVATED)

    assert [(c.kind, c.text) for c in ability.costs] == [(CostKind.PAY_LIFE, "Pay 7 life")]
    assert ability.effect == "Draw seven cards."


def test_a_loyalty_symbol_is_a_cost_kind_of_its_own():
    """CR 606.2: "An activated ability with a loyalty symbol in its cost is a
    loyalty ability." CR 107.7: `[+N]` puts N loyalty counters on, `[−N]`
    removes N, `[0]` puts zero."""
    abilities = abilities_of_kind(card("Ugin, Eye of the Storms"), AbilityKind.ACTIVATED)

    assert [ability.loyalty.amount for ability in abilities] == [2, 0, -11]
    assert all([c.kind for c in ability.costs] == [CostKind.LOYALTY] for ability in abilities)


def test_a_zero_loyalty_cost_can_still_read_as_an_add_effect():
    """Corner case: Ugin's `0: Add {C}{C}{C}.` is both at once.

    The cost is CR 107.7's neutral loyalty symbol, so CR 606.2 makes it a
    loyalty ability; the effect is `Add ...`, so the mana parse links too.
    CR 605.1a's third mana-ability criterion is "it's not a loyalty ability",
    so the activation path must read the loyalty flag, not the mana one.
    """
    abilities = abilities_of_kind(card("Ugin, Eye of the Storms"), AbilityKind.ACTIVATED)

    zero = abilities[1]
    assert zero.loyalty.amount == 0
    assert zero.mana is not None and zero.mana.amount == 3


def test_a_variable_loyalty_cost_has_no_amount_to_pay():
    """Tamiyo, Compleated Sage: `−X`, CR 107.7's "a minus sign followed by a
    number or an X". The X is a player's choice, not a number."""
    abilities = abilities_of_kind(card("Tamiyo, Compleated Sage"), AbilityKind.ACTIVATED)

    minus_x = abilities[1]
    assert minus_x.loyalty.printed == "−X"
    assert minus_x.loyalty.amount is None
    assert minus_x.loyalty.variable


def test_a_transforming_planeswalkers_back_face_is_parsed_too():
    """Ajani, Nacatl Pariah's back face, Ajani, Nacatl Avenger, carries the
    loyalty abilities - parse_abilities reads every face."""
    abilities = abilities_of_kind(card("Ajani, Nacatl Pariah"), AbilityKind.ACTIVATED)

    assert {(ability.face, ability.loyalty.amount) for ability in abilities} == {
        ("Ajani, Nacatl Avenger", 2),
        ("Ajani, Nacatl Avenger", 0),
        ("Ajani, Nacatl Avenger", -4),
    }


def test_activation_instructions_are_split_off_the_effect():
    """CR 602.1b: text after the colon may restrict when the ability may be
    activated. It is not part of the effect."""
    (ability,) = abilities_of_kind(card("Basking Rootwalla"), AbilityKind.ACTIVATED)

    assert ability.effect == "This creature gets +2/+2 until end of turn."
    assert ability.instructions == "Activate only once each turn."


def test_a_colon_inside_reminder_text_is_not_the_activation_colon():
    """Corner case: Cycling's reminder text is `({U}, Discard this card: Draw a
    card.)`. The line is a keyword, not an activated ability."""
    counter, cycling = parse_abilities(card("Censor"))

    assert counter.kind is AbilityKind.STATIC
    assert cycling.kind is AbilityKind.KEYWORD
    assert cycling.keyword == "Cycling"
    assert cycling.cost == "{U}"
    assert "Discard this card: Draw a card." in cycling.reminder


# --------------------------------------------------------------------------
# Triggered abilities (CR 603)
# --------------------------------------------------------------------------


def test_when_and_whenever_and_at_are_told_apart():
    """CR 603.1: the three trigger words are not interchangeable."""
    (when,) = abilities_of_kind(card("Archive Dragon"), AbilityKind.TRIGGERED)
    whenever, _ = abilities_of_kind(card("Sheoldred, the Apocalypse"), AbilityKind.TRIGGERED)
    (at,) = abilities_of_kind(card("Delver of Secrets"), AbilityKind.TRIGGERED)

    assert when.word is TriggerWord.WHEN
    assert whenever.word is TriggerWord.WHENEVER
    assert at.word is TriggerWord.AT


def test_the_condition_and_the_effect_are_split_at_the_first_comma():
    (ability,) = abilities_of_kind(card("Guttersnipe"), AbilityKind.TRIGGERED)

    assert ability.condition == "you cast an instant or sorcery spell"
    assert ability.effect == "this creature deals 2 damage to each opponent."
    assert ability.event is TriggerEvent.CAST_SPELL
    assert ability.intervening_if is None


def test_a_thousands_separator_comma_is_not_a_clause_boundary():
    """The Millennium Calendar (verified with `resolve_cards`): "When there
    are 1,000 or more time counters on The Millennium Calendar, sacrifice it
    and each opponent loses 1,000 life."

    CR 603.1 templates a triggered ability as "[When/Whenever/At] [trigger
    condition or event], [effect]", and the boundary is the comma after the
    condition - not the one inside the number. Split on the number's comma,
    the condition came out as "there are 1" and the whole state trigger
    (CR 603.8) was unreadable.
    """
    triggers = abilities_of_kind(card("The Millennium Calendar"), AbilityKind.TRIGGERED)
    state_trigger = triggers[-1]

    assert state_trigger.condition == (
        "there are 1,000 or more time counters on The Millennium Calendar"
    )
    assert state_trigger.effect == "sacrifice it and each opponent loses 1,000 life."


def test_the_same_card_still_splits_on_its_real_commas():
    """The other half of the fix: a comma that is a genuine boundary still
    cuts. The Millennium Calendar's own first ability is CR 603.1's
    "[condition], [effect]", and its activated ability's cost is CR 601.2's
    comma-separated list "{2}, {T}" - two costs, not one.
    """
    (first, _state) = abilities_of_kind(card("The Millennium Calendar"), AbilityKind.TRIGGERED)
    (activated,) = abilities_of_kind(card("The Millennium Calendar"), AbilityKind.ACTIVATED)

    assert first.condition == "you untap one or more permanents during your untap step"
    assert first.effect == "put that many time counters on The Millennium Calendar."
    assert [cost.kind for cost in activated.costs] == [CostKind.MANA, CostKind.TAP]


def test_enters_and_dies_triggers_on_one_card():
    """CR 603.6a enters-the-battlefield, and a dies trigger, both with `When`."""
    enters, dies = abilities_of_kind(card("Solemn Simulacrum"), AbilityKind.TRIGGERED)

    assert enters.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
    assert enters.condition == "this creature enters"
    assert dies.event is TriggerEvent.DIES
    assert dies.effect == "you may draw a card."


def test_an_attack_trigger_is_recognised():
    """CR 508.3c: `Whenever [a creature] attacks`."""
    (ability,) = abilities_of_kind(card("Hellrider"), AbilityKind.TRIGGERED)

    assert ability.event is TriggerEvent.ATTACKS
    assert ability.condition == "a creature you control attacks"


def test_a_block_trigger_is_recognised_including_becomes_blocked():
    (ability,) = abilities_of_kind(card("Ashmouth Hound"), AbilityKind.TRIGGERED)

    assert ability.event is TriggerEvent.BLOCKS
    assert ability.condition == "this creature blocks or becomes blocked by a creature"


def test_a_step_trigger_keeps_the_step_in_the_condition():
    (ability,) = abilities_of_kind(card("Delver of Secrets"), AbilityKind.TRIGGERED)

    assert ability.event is TriggerEvent.BEGINNING_OF_STEP
    assert ability.condition == "the beginning of your upkeep"
    assert ability.effect.startswith("look at the top card of your library.")


def test_an_intervening_if_is_kept_apart_from_the_effect():
    """CR 603.4: `At [trigger event], if [condition], [effect].` The condition
    is checked when the event happens and again on resolution."""
    (ability,) = abilities_of_kind(card("Thopter Assembly"), AbilityKind.TRIGGERED)

    assert ability.condition == "the beginning of your upkeep"
    assert ability.intervening_if == "you control no Thopters other than this creature"
    assert ability.effect.startswith("return this creature to its owner's hand")


def test_an_if_that_is_not_intervening_stays_in_the_effect():
    """Delver's `If an instant or sorcery card is revealed this way` is part of
    the effect, not a CR 603.4 condition - it does not follow the comma."""
    (ability,) = abilities_of_kind(card("Delver of Secrets"), AbilityKind.TRIGGERED)

    assert ability.intervening_if is None
    assert "If an instant or sorcery card is revealed this way" in ability.effect


def test_an_ability_word_is_stripped_and_kept():
    """CR 207.2c: an ability word has no rules meaning, but it names the
    mechanic, so it is not thrown away."""
    (ability,) = parse_abilities(card("Steppe Lynx"))

    assert ability.ability_word == "Landfall"
    assert ability.kind is AbilityKind.TRIGGERED
    assert ability.condition == "a land you control enters"
    assert ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD


def test_a_combat_damage_trigger_parses_with_its_event():
    """Ragavan's combat damage trigger is one of the recognised shapes. The
    condition is still there; `event` is honestly DEALS_DAMAGE."""
    (trigger,) = abilities_of_kind(card("Ragavan, Nimble Pilferer"), AbilityKind.TRIGGERED)

    assert trigger.event is TriggerEvent.DEALS_DAMAGE
    assert trigger.condition == "Ragavan deals combat damage to a player"


def test_an_intervening_if_with_internal_commas_splits_correctly():
    """W14 fix: `_INTERVENING_IF_CAST_THIS_TURN_BOUNDARY` reads Alania,
    Divergent Storm's own "if it's the first instant spell, the first
    sorcery spell, or the first Otter spell other than Alania you've cast
    this turn" clause whole, by matching its "you('ve| have) cast this turn"
    closing phrase, instead of cutting at the clause's own first internal
    comma the way a plain `_split_top_level` cut would."""
    (ability,) = abilities_of_kind(card("Alania, Divergent Storm"), AbilityKind.TRIGGERED)

    assert ability.intervening_if == (
        "it's the first instant spell, the first sorcery spell, or the first "
        "Otter spell other than Alania you've cast this turn"
    )
    assert ability.effect.startswith("you may have target opponent draw a card.")


# --------------------------------------------------------------------------
# Keyword abilities (CR 702)
# --------------------------------------------------------------------------


def test_a_keyword_on_its_own_line():
    flying, vigilance = parse_abilities(card("Serra Angel"))

    assert flying.kind is AbilityKind.KEYWORD
    assert flying.keyword == "Flying"
    assert flying.cost is None
    assert vigilance.canonical == "Vigilance"


def test_a_keyword_list_on_one_line_yields_one_ability_each():
    """CR 702: `Vigilance, deathtouch, haste` is three abilities, not one."""
    keywords = abilities_of_kind(card("Questing Beast"), AbilityKind.KEYWORD)

    assert [k.keyword for k in keywords] == ["Vigilance", "deathtouch", "haste"]
    assert [k.canonical for k in keywords] == ["Vigilance", "Deathtouch", "Haste"]
    assert {k.text for k in keywords} == {"Vigilance, deathtouch, haste"}


def test_a_semicolon_separated_keyword_list_is_split_too():
    defender, reach = abilities_of_kind(card("Aether Membrane"), AbilityKind.KEYWORD)

    assert defender.canonical == "Defender"
    assert reach.canonical == "Reach"


def test_a_keyword_with_a_mana_cost():
    (flashback,) = abilities_of_kind(card("Faithless Looting"), AbilityKind.KEYWORD)

    assert flashback.keyword == "Flashback"
    assert flashback.cost == "{2}{R}"


def test_ward_and_kicker_costs_are_read_the_same_way():
    (ward,) = [k for k in abilities_of_kind(card("Archive Dragon"), AbilityKind.KEYWORD) if k.cost]
    (kicker,) = abilities_of_kind(card("Burst Lightning"), AbilityKind.KEYWORD)

    assert (ward.canonical, ward.cost) == ("Ward", "{2}")
    assert (kicker.canonical, kicker.cost) == ("Kicker", "{4}")


def test_a_two_word_keyword_is_not_split_at_the_space():
    (first_strike,) = parse_abilities(card("Youthful Knight"))

    assert first_strike.kind is AbilityKind.KEYWORD
    assert first_strike.canonical == "First strike"
    assert first_strike.cost is None
    assert first_strike.parameter is None


def test_a_keyword_parameter_that_is_not_a_cost_is_kept_separately():
    (protection,) = [
        a for a in parse_abilities(card("Sanctifier en-Vec")) if a.kind is AbilityKind.KEYWORD
    ]

    assert protection.canonical == "Protection"
    assert protection.cost is None
    assert protection.parameter == "from black and from red"


def test_a_sentence_that_merely_starts_with_a_keyword_is_not_a_keyword_line():
    """Corner case: `Combat damage that would be dealt ...` and `Questing Beast
    can't be blocked ...` are statements, and Questing Beast has `haste`."""
    statics = abilities_of_kind(card("Questing Beast"), AbilityKind.STATIC)

    assert len(statics) == 2
    assert all("can't be" in s.text for s in statics)


# --------------------------------------------------------------------------
# Static abilities (CR 604) and reminder text (CR 207.2a)
# --------------------------------------------------------------------------


def test_a_leftover_statement_is_static():
    boost, deckbuilding = parse_abilities(card("Relentless Rats"))

    assert boost.kind is AbilityKind.STATIC
    assert boost.text.startswith("This creature gets +1/+1")
    assert deckbuilding.kind is AbilityKind.STATIC


def test_a_spell_ability_is_reported_as_static():
    """Known deviation: CR 113.3a calls an instant's text a spell ability. The
    type line tells the two apart and this parser does not read type lines."""
    (ability,) = parse_abilities(card("Lightning Bolt"))

    assert ability.kind is AbilityKind.STATIC
    assert ability.text == "Lightning Bolt deals 3 damage to any target."


def test_a_vanilla_creature_has_no_abilities():
    assert parse_abilities(card("Grizzly Bears")) == []


def test_a_basic_land_prints_no_abilities_but_still_makes_mana():
    """Corner case: Forest's whole oracle text is `({T}: Add {G}.)` - reminder
    text, which is not rules text. The ability is intrinsic, not printed, so
    `parse_abilities` reports nothing while `parse_mana_abilities` still reads
    it."""
    assert parse_abilities(card("Forest")) == []
    assert parse_mana_abilities(card("Forest"))[0].produces() == [Color.GREEN]


def test_intrinsic_land_ability_reads_the_printed_type_line_by_default():
    """CR 305.6 grants the mana ability to a land with a basic land type. Urborg,
    Tomb of Yawgmoth's own printed type line is "Legendary Land" with no basic
    land type on it - it prints its own real rules text ("Each land is a Swamp
    in addition to its other land types") instead of reminder text, which is
    exactly why it needs no intrinsic ability of its own off the printing.
    """
    assert intrinsic_land_ability(card("Urborg, Tomb of Yawgmoth")) is None


def test_intrinsic_land_ability_reads_computed_subtypes_when_given():
    """The fix: a `computed_subtypes` override reads CR 613's layer-4 answer
    instead of the printed type line - Urborg's own ability applies to every
    land, itself included, so a land Urborg is the source of gains {T}: Add
    {B} even though its printed line carries no basic land type at all.
    Nothing here builds the layer effect that would produce this override in
    a real game (`cost.py`/`triggers.py`'s own call sites do that, and they
    are out of this file's scope) - only that the primitive itself reads the
    override it is given.
    """
    ability = intrinsic_land_ability(card("Urborg, Tomb of Yawgmoth"), computed_subtypes=("Swamp",))
    assert ability is not None
    assert ability.mana is not None
    assert ability.mana.produces() == [Color.BLACK]
    assert ability.cost == "{T}"


def test_intrinsic_land_ability_ignores_a_stale_printed_subtype_when_overridden():
    """The inverse: a real basic land's own printed subtype must not leak
    through once a caller supplies a computed override - a Forest Blood Moon
    (CR 305.7) turned into "just a Mountain" gains {T}: Add {R}, never a
    second, phantom {T}: Add {G} alongside it.
    """
    ability = intrinsic_land_ability(card("Forest"), computed_subtypes=("Mountain",))
    assert ability is not None
    assert ability.mana is not None
    assert ability.mana.produces() == [Color.RED]


def test_reminder_text_is_stripped_but_kept():
    """CR 207.2a: reminder text has no game function, but it says what the
    keyword means, so it stays on the model."""
    (_, ward, _) = parse_abilities(card("Archive Dragon"))

    assert ward.text == "Ward {2}"
    assert ward.raw == (
        "Ward {2} (Whenever this creature becomes the target of a spell or "
        "ability an opponent controls, counter it unless that player pays {2}.)"
    )
    assert ward.reminder.startswith("(Whenever this creature becomes the target")


def test_a_line_that_is_only_reminder_text_is_not_an_ability():
    """History of Benalia's first line is the Saga lore-counter note."""
    abilities = parse_abilities(card("History of Benalia"))

    assert all("lore counter" not in a.raw for a in abilities)
    # CR 107.15a: "I, II —" is one printed line but two chapter abilities
    # (one per threshold, same effect), "III —" is the third - three
    # `TriggeredAbility` in all, not two `UnparsedAbility` lines. See
    # `test_saga_chapters_are_read_as_triggered_abilities` below.
    assert len(abilities) == 3


# --------------------------------------------------------------------------
# Whole cards, faces, and what is admittedly not parsed
# --------------------------------------------------------------------------


def test_a_card_with_four_kinds_of_ability_reports_them_in_printed_order():
    kinds = [a.kind for a in parse_abilities(card("Kalitas, Traitor of Ghet"))]

    assert kinds == [AbilityKind.KEYWORD, AbilityKind.STATIC, AbilityKind.ACTIVATED]


def test_both_faces_of_a_transforming_card_are_parsed():
    front, back = parse_abilities(card("Delver of Secrets"))

    assert front.face == "Delver of Secrets"
    assert front.kind is AbilityKind.TRIGGERED
    assert back.face == "Insectile Aberration"
    assert back.kind is AbilityKind.KEYWORD
    assert back.keyword == "Flying"


def test_saga_chapters_are_read_as_triggered_abilities():
    """CR 714.2's chapter symbol "is a keyword ability that represents a
    triggered ability" (CR 714.2), and CR 107.15a spells out exactly which
    one: "When one or more lore counters are put onto this Saga, if the
    number of lore counters on it was less than N and became at least N,
    [effect]." `_parse_chapter_line` (`machines/abilities.py`) reads the
    printed `I, II —`/`III —` markers into that shape rather than leaving
    them `UnparsedAbility` - one `TriggeredAbility` per chapter *number*,
    `TriggeredAbility.chapter` carrying `N`, `TriggerEvent.LORE_COUNTERS_
    ADDED` standing in for CR 107.15a's own paraphrase since no printed
    condition text exists to read an ordinary event off.
    """
    first, second, third = parse_abilities(card("History of Benalia"))

    assert first.kind is AbilityKind.TRIGGERED
    assert first.chapter == 1
    assert first.effect == "Create a 2/2 white Knight creature token with vigilance."
    assert second.kind is AbilityKind.TRIGGERED
    assert second.chapter == 2
    assert second.effect == first.effect, "I, II share the identical effect text"
    assert third.kind is AbilityKind.TRIGGERED
    assert third.chapter == 3
    assert third.effect == "Knights you control get +2/+1 until end of turn."
    assert {a.event for a in (first, second, third)} == {TriggerEvent.LORE_COUNTERS_ADDED}


def test_abilities_of_kind_filters():
    triggered = abilities_of_kind(card("Sheoldred, the Apocalypse"), AbilityKind.TRIGGERED)

    assert len(triggered) == 2
    assert all(a.kind is AbilityKind.TRIGGERED for a in triggered)


def test_a_while_condition_with_a_comma_side_if_still_parses_as_a_trigger():
    """A "while" intervening clause (CR 603.4, printed in the condition) next
    to a comma-side "if" has no printing yet (Scryfall, 2026-09-22), so this
    reads the line through `parse_granted_ability_lines`, the path a granted
    quoted ability takes. It must not vanish: the "while" clause is the
    intervening *if*, and the comma-side "if" stays in the effect text for
    the effect reader to judge, as before compound splitting."""
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_granted_ability_lines

    (ability,) = parse_granted_ability_lines(
        ["Whenever this creature attacks while saddled, if you control an artifact, draw a card."]
    )
    assert isinstance(ability, TriggeredAbility)
    assert ability.condition == "this creature attacks"
    assert ability.intervening_if == "saddled"
    assert ability.effect == "if you control an artifact, draw a card."

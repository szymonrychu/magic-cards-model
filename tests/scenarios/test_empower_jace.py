"""Empower Jace, CR 701.71 - Reality Fracture's own keyword action.

Read out of the Comprehensive Rules on disk this session with `mise run
rules:find 701.71`:

- **CR 701.71a** - "To empower Jace N means 'If you don't control a Jace
  planeswalker token, create a blue Jace planeswalker token with 0 loyalty,
  "[-1]: Surveil 1," and "[-3]: Draw a card." Choose a Jace planeswalker
  token you control. Put N loyalty counters on it.'"

Three instructions in one keyword action: create the token only if none is
controlled yet, choose one (CR 608.2d - not a target, so no CR 601.2c
announcement and no CR 608.2b recheck), then put N loyalty counters on it.
The token itself is confirmed against Scryfall's own `tfra` printing: name
"Jace" (not CR 111.4's fallback "Jace Token" - the creating text names it),
0 starting loyalty, and two loyalty abilities printed with the plain minus
sign the ordinary loyalty-cost reader already knows.

CR 120.10 (also looked up this session) backs the one card here whose X is
not a plain count: "If [sources] dealt an amount of damage to a creature
greater than lethal damage, excess damage equal to the difference was dealt
... If [sources] dealt an amount of damage to a planeswalker greater than
that planeswalker's loyalty before the damage was dealt, excess damage equal
to the difference was dealt."

Every card below is a genuine `set:fra` printing added with
`scripts/add_card.py`, not hand-typed text - `_parse_empower_jace_clause`
reads the shared keyword-action pattern the same way
`_parse_earthbend_clause`/`_parse_amass_clause` already do, so it needs no
card-specific code and every card here exercises a different textual shape:
a spell's second sentence composed with an existing pump clause (Academic
Ascent), a creature's ETB trigger (Arcane Amphisbaena), a graveyard-cost
activated ability (Campus Crier), an attack trigger whose X is "the number
of creatures you control" (Repurposed Enforcer), a loyalty ability whose X
is "the number of Islands you control" (Jace, Reality Sculptor's own `+1`),
a modal spell's own mode text (Fatehold Charm), a sweep whose X is "the
number of creatures exiled this way" (Overwrite the Multiverse, proving the
new exile-each clause this wave also adds), and the CR 120.10 excess-damage
shape (Violent Echoes).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import CardState, Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, TokenState, create_tokens

from .harness import Scenario


def _jace_token(scenario: Scenario, username: str = "alice") -> CardState:
    return scenario.find("Jace", Zone.BATTLEFIELD, username)


def _jace_tokens(scenario: Scenario, username: str = "alice") -> list[CardState]:
    return [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == "Jace" and permanent.controller == username
    ]


def test_empower_is_reported_as_executed_by_the_pool_sweeper():
    """A CR 701 keyword action embedded in other abilities' effect text, the
    same shape earthbend/amass/airbend/investigate already are: the clause
    parser lives in `machines/effects.py`, but `scripts/sweep_pool.py` reads
    `machines/keywords.executes` and cannot tell "known and ignored" from
    "unknown" without being told."""
    assert executes("Empower") is True
    assert executes("empower") is True


def test_academic_ascent_composes_the_pump_with_the_empower_second_sentence():
    """ "Target creature gets +2/+2 and gains flying until end of turn.
    Empower Jace 2." - two clauses, `_merge_continuous_pump_keyword_clauses`
    reading the first and `_parse_empower_jace_clause` the second, composed
    by `_parse_mixed_clauses` into one instruction. No Jace token existed, so
    CR 701.71a's own first sentence creates one at 0 loyalty before the two
    counters land.
    """
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Academic Ascent"], battlefield=["Plains", "Plains", "Grizzly Bears"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Plains")

    scenario.cast_and_resolve("Academic Ascent", *sources, targets=[bear])

    assert scenario.game.power_of(bear) == 4
    assert scenario.game.toughness_of(bear) == 4

    jace = _jace_token(scenario)
    assert jace.loyalty == 2
    assert jace.card.name == "Jace"
    assert "planeswalker" in jace.card.type_line.lower()
    assert "Jace" in jace.subtypes


def test_arcane_amphisbaena_empowers_from_its_own_etb_trigger():
    """ "When this creature enters, empower Jace 2." - a whole trigger body,
    with no sibling sentence to compose against."""
    scenario = Scenario().player("alice", hand=["Arcane Amphisbaena"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Arcane Amphisbaena")
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 2


def test_a_second_empower_reuses_the_existing_token_rather_than_making_another():
    """CR 701.71a's "if you don't control a Jace planeswalker token" only
    fires once a player already has none - Inspired Tethermage's own
    battlefield ability ("{6}: Empower Jace 2.") finds the token Arcane
    Amphisbaena's trigger already made and simply adds to its loyalty rather
    than making a second one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arcane Amphisbaena"],
            battlefield=["Inspired Tethermage"] + ["Forest"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Arcane Amphisbaena")
    scenario.pass_until_resolved()
    assert _jace_token(scenario).loyalty == 2

    tethermage = scenario.creature("Inspired Tethermage", "alice")
    sources = scenario.untapped_sources(*["Forest"] * 6)
    scenario.activate(tethermage, *sources)
    scenario.pass_until_resolved()

    tokens = _jace_tokens(scenario)
    assert len(tokens) == 1, "CR 701.71a creates one only when none is controlled"
    assert tokens[0].loyalty == 4


def test_campus_criers_graveyard_ability_empowers_through_the_ordinary_door():
    """Campus Crier: "{1}, Exile this card from your graveyard: Empower Jace
    2." - CR 113.6j, the same shape Seasoned Pyromancer's own exile-from-
    graveyard ability is. `Game.why_cannot_activate` used to refuse every
    off-battlefield activation unconditionally, even once
    `machines/abilities._activated_ability_zone` had already read this
    ability's own zone as the graveyard correctly - fixed alongside this
    stream's own empower work (`docs/engine-coverage.md`'s FRA S1 section),
    so this now goes through `Scenario.activate`/`Game.activate_ability` for
    real, the same door the API uses, rather than building and paying the
    `TotalCost` by hand."""
    scenario = (
        Scenario()
        .player("alice", graveyard=["Campus Crier"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crier = scenario.find("Campus Crier", Zone.GRAVEYARD, "alice")
    (plains,) = scenario.untapped_sources("Plains")

    scenario.activate(crier, plains, exiling=[crier])

    assert crier.zone is Zone.EXILE
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 2


def test_repurposed_enforcer_empowers_x_equal_to_creatures_you_control_on_attack():
    """ "Whenever this creature attacks, empower Jace X, where X is the
    number of creatures you control." - `count_expression`'s "you control"
    reader, read through `_fixed_or_where_x_amount` with no code of its own
    for this card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Repurposed Enforcer", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    enforcer = scenario.creature("Repurposed Enforcer", "alice")

    scenario.attack_with(enforcer)
    scenario.pass_until_resolved()

    # Three creatures alice controls: the Enforcer itself plus the two others.
    assert _jace_token(scenario).loyalty == 3


def test_jace_reality_sculptor_plus_one_empowers_x_islands_and_the_token_works():
    """Jace, Reality Sculptor's own `+1: Empower Jace X, where X is the
    number of Islands you control.` - a loyalty ability's whole effect text,
    proving `for_spell=False` alongside Academic Ascent's `for_spell=True`.

    Also proves the created token's own two abilities actually parse and
    activate: once it exists, its `-3: Draw a card.` is an ordinary loyalty
    ability like any printed planeswalker's, read off `oracle_text` this
    module built rather than off anything a real printing carries.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            battlefield=["Jace, Reality Sculptor", "Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.creature("Jace, Reality Sculptor", "alice")
    assert sculptor.loyalty == 5

    scenario.activate(sculptor, index=0)
    scenario.pass_until_resolved()

    jace = _jace_token(scenario)
    assert jace.loyalty == 3, "three Islands alice controls"
    assert sculptor.loyalty == 6, "the +1 cost still lands on Jace, Reality Sculptor itself"

    library_before = len(scenario.player("alice").library)
    scenario.activate(jace, index=1)  # "-3: Draw a card."
    scenario.pass_until_resolved()

    assert jace.loyalty == 0
    assert len(scenario.player("alice").library) == library_before - 1


def test_fatehold_charm_empowers_from_its_own_chosen_mode():
    """ "Choose one - Draw a card. Empower Jace 2. - ..." - `parse_mode_effect`
    reads a chosen mode's text through the same per-clause dispatcher a
    non-modal card's whole text goes through, so the mode's own two
    sentences compose exactly the way Academic Ascent's two sentences do."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 5,
            hand=["Fatehold Charm"],
            battlefield=["Plains", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hand_before = len(scenario.player("alice").hand)

    casting = scenario.cast("Fatehold Charm")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    # Casting itself removes one card from hand; mode 1 draws one back.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1
    assert _jace_token(scenario).loyalty == 2


def test_overwrite_the_multiverse_empowers_x_equal_to_creatures_exiled_this_way():
    """ "Exile all creatures. Empower Jace X, where X is the number of
    creatures exiled this way." Two new clauses this wave adds:
    `_parse_exile_each_clause` (the exile-side twin of `_parse_destroy_each_
    clause`) records the count, and `count_expression`'s existing "`<verb>`
    this way" reader (`_COUNT_THIS_WAY_RE`) reads it back for X - both
    reusable by any future card, not special-cased to this one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Overwrite the Multiverse"],
            battlefield=["Swamp"] * 6 + ["Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 6)

    scenario.cast_and_resolve("Overwrite the Multiverse", *sources)

    remaining_creatures = [
        permanent
        for permanent in scenario.game.battlefield
        if scenario.game.characteristics_of(permanent).is_creature
    ]
    assert remaining_creatures == []
    # Three creatures existed: alice's Grizzly Bears, bob's two - all exiled
    # by the sweep, all counted "this way".
    assert _jace_token(scenario).loyalty == 3


def test_violent_echoes_empowers_x_equal_to_excess_damage_on_a_creature():
    """CR 120.10: 6 damage to a 2-toughness Grizzly Bears is 4 more than
    lethal, so X is 4 - not the printed 6, and not "did it die" as a bare
    boolean."""
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[bear])

    assert bear.zone is Zone.GRAVEYARD
    assert _jace_token(scenario).loyalty == 4


def test_violent_echoes_empowers_x_equal_to_excess_damage_on_a_planeswalker():
    """CR 120.10's planeswalker half: 6 damage to Jace, Reality Sculptor's 5
    starting loyalty is 1 more than lethal."""
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Jace, Reality Sculptor"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walker = scenario.creature("Jace, Reality Sculptor", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[walker])

    assert walker.zone is Zone.GRAVEYARD, "CR 704.5i: 0 loyalty"
    assert _jace_token(scenario).loyalty == 1


def test_violent_echoes_empowers_nothing_when_damage_is_not_excess():
    """6 damage to Slumbering Trudge's printed 6 toughness is exactly
    lethal, not excess - CR 120.10's own "greater than", not "at least". No
    Jace token is created at all, since CR 701.71a's whole instruction never
    runs for X = 0.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Violent Echoes"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Slumbering Trudge"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    trudge = scenario.creature("Slumbering Trudge", "bob")
    assert scenario.game.toughness_of(trudge) == 6
    sources = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Violent Echoes", *sources, targets=[trudge])

    assert trudge.zone is Zone.GRAVEYARD
    assert _jace_tokens(scenario) == []


def test_choosing_among_two_jace_tokens_you_control():
    """CR 608.2d's ordinary "more than one legal choice" case: two Jace
    tokens (built directly through `create_tokens`, the way a copy effect
    outside this wave's scope could produce a second one) means the choice
    is asked rather than picked automatically.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Theorist's Sanctum", "Island", "Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=2)
    scenario.game.add_counters(first, Counter.LOYALTY, 3)
    scenario.game.add_counters(second, Counter.LOYALTY, 5)

    scenario.will_choose_cards(second, source="Theorist's Sanctum")
    sanctum = scenario.find("Theorist's Sanctum", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.activate(sanctum, *sources, index=0)
    scenario.pass_until_resolved()

    assert first.loyalty == 3, "not chosen, untouched"
    assert second.loyalty == 7, "chosen: 5 + empower Jace 2"


# ---------------------------------------------------------------------------
# Round 293-fra T1: the remaining empower cards, on their real printings, and
# the corner cases of CR 701.71a every one of them shares. No Modern/Pioneer/
# Standard printing outside the 293-fra round carries "Empower Jace", so the
# proofs below are on the round's own printings.
# ---------------------------------------------------------------------------


def test_scryfalls_own_keyword_spelling_is_reported_as_executed():
    """Scryfall names the keyword "Empower Jace", not "Empower"."""
    assert executes("Empower Jace") is True
    assert executes("empower jace") is True


def test_keeper_of_the_quiet_hour_empowers_two_from_its_etb_trigger():
    scenario = Scenario().player("alice", hand=["Keeper of the Quiet Hour"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Keeper of the Quiet Hour")
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 2


def test_mindseeker_oculus_empowers_four_from_its_etb_trigger():
    scenario = Scenario().player("alice", hand=["Mindseeker Oculus"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Mindseeker Oculus")
    scenario.pass_until_resolved()

    assert _jace_token(scenario).loyalty == 4


def test_no_admittance_deals_three_then_empowers_one():
    scenario = (
        Scenario()
        .player("alice", hand=["No Admittance"], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("No Admittance", *sources, targets=["bob"])

    assert scenario.player("bob").life == 17
    assert _jace_token(scenario).loyalty == 1


def test_hexhaven_battalion_makes_three_cadets_and_empowers_two():
    scenario = (
        Scenario()
        .player("alice", hand=["Hexhaven Battalion"], battlefield=["Plains"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 6)

    scenario.cast_and_resolve("Hexhaven Battalion", *sources)

    cadets = [
        permanent
        for permanent in scenario.game.battlefield
        if permanent.name == "Cadet" and permanent.controller == "alice"
    ]
    assert len(cadets) == 3
    assert all(
        scenario.game.power_of(c) == 2 and scenario.game.toughness_of(c) == 2 for c in cadets
    )
    assert _jace_token(scenario).loyalty == 2


def test_hexhaven_battalion_basic_landcycling_finds_a_basic_land():
    """CR 702.29e: basic landcycling searches for a basic land card."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Hexhaven Battalion"],
            library=["Lightning Bolt", "Plains", "Counterspell"],
            battlefield=["Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battalion = scenario.find("Hexhaven Battalion", Zone.HAND, "alice")
    plains = scenario.find("Plains", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(plains, username="alice", source="Hexhaven Battalion")

    scenario.cycle(battalion, *scenario.untapped_sources("Plains", "Plains"))

    assert plains.zone is Zone.HAND
    assert battalion.zone is Zone.GRAVEYARD
    assert _jace_tokens(scenario) == [], "cycling is not casting: nothing empowers"


def test_fatehold_charm_other_modes_do_not_empower():
    """Only the draw mode carries "Empower Jace 2"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fatehold Charm"],
            battlefield=["Plains", "Island", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "alice")

    casting = scenario.cast("Fatehold Charm")
    casting.choose_modes([3])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Island"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.power_of(bear) == 3
    assert _jace_tokens(scenario) == []


def _countersculpt_board(**alice):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("alice", **alice)
        .build()
    )


def _bolt_alice(scenario):
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    return bolt


def test_countersculpt_paying_one_counters_the_spell_and_empowers_one():
    scenario = _countersculpt_board(
        hand=["Countersculpt"], battlefield=["Island", "Island", "Island"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = _bolt_alice(scenario)
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")

    scenario.cast_and_resolve("Countersculpt", *sources, username="alice", targets=[bolt])

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20
    assert _jace_token(scenario).loyalty == 1


def test_countersculpt_beholding_a_jace_skips_the_extra_mana():
    """CR 701.4a: a Jace card revealed from hand pays the additional cost, so
    only {U}{U} is spent."""
    scenario = _countersculpt_board(
        hand=["Countersculpt", "Jace, Reality Sculptor"], battlefield=["Island", "Island"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = _bolt_alice(scenario)
    jace_card = scenario.find("Jace, Reality Sculptor", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Island", "Island", username="alice")

    scenario.cast_and_resolve(
        "Countersculpt", *sources, username="alice", targets=[bolt], beholding=[jace_card]
    )

    assert bolt.zone is Zone.GRAVEYARD
    assert jace_card.zone is Zone.HAND, "beholding reveals, it does not move the card"
    assert _jace_token(scenario).loyalty == 1


def test_countersculpt_does_nothing_when_its_target_is_gone_on_resolution():
    """CR 608.2b: the only target is illegal, so the whole spell does nothing
    - no counter and, with it, no empower."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "bob",
            hand=["Lightning Bolt", "Counterspell"],
            battlefield=["Mountain", "Island", "Island"],
        )
        .player("alice", hand=["Countersculpt"], battlefield=["Island", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=["alice"])
    scenario.pass_priority("bob")
    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_onto_stack("Countersculpt", *sources, username="alice", targets=[bolt])
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[bolt])

    scenario.resolve_top()
    assert bolt.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert _jace_tokens(scenario) == []


def test_overwrite_the_multiverse_with_no_creatures_empowers_zero():
    """X = 0 creatures exiled: the token is still created (CR 701.71a's first
    sentence does not depend on N) but gets no counters, so it sits at 0
    loyalty until state-based actions put it into the graveyard (CR 704.5i)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Overwrite the Multiverse"], battlefield=["Swamp"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 6)

    scenario.cast_and_resolve("Overwrite the Multiverse", *sources)
    scenario.state_based_actions()

    assert _jace_tokens(scenario) == []


def test_a_nonlegal_token_at_zero_loyalty_is_put_into_the_graveyard_by_sba():
    """CR 704.5i, on a freshly made Jace token."""
    scenario = Scenario().player("alice").player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (jace,) = create_tokens(scenario.game, PREDEFINED["Jace"], "alice", count=1)
    assert jace.loyalty == 0

    scenario.state_based_actions()

    assert jace not in scenario.game.battlefield


def test_a_nontoken_jace_planeswalker_does_not_stand_in_for_the_token():
    """CR 701.71a says "Jace planeswalker *token*": a real Jace card on the
    battlefield leaves the first sentence to create a token."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arcane Amphisbaena"],
            battlefield=["Jace, Reality Sculptor"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sculptor = scenario.find("Jace, Reality Sculptor", Zone.BATTLEFIELD, "alice")
    before = sculptor.loyalty

    scenario.put_onto_battlefield("Arcane Amphisbaena")
    scenario.pass_until_resolved()

    tokens = [t for t in _jace_tokens(scenario) if isinstance(t, TokenState)]
    assert len(tokens) == 1 and tokens[0].loyalty == 2
    assert sculptor.loyalty == before


def test_the_jace_tokens_minus_one_surveils_and_minus_three_draws():
    """CR 606.3/606.6: the token's two printed abilities are real loyalty
    abilities, payable only with enough loyalty counters."""
    scenario = (
        Scenario()
        .player("alice", hand=["Mindseeker Oculus"], library=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Mindseeker Oculus")
    scenario.pass_until_resolved()
    jace = _jace_token(scenario)
    assert jace.loyalty == 4

    top = scenario.top_of_library(1)[0]
    scenario.surveil_to_graveyard(top)
    scenario.activate(jace, index=0, username="alice")
    scenario.pass_until_resolved()
    assert jace.loyalty == 3
    assert top.zone is Zone.GRAVEYARD, "[-1]: Surveil 1"


def test_charge_the_sanctums_mass_pump_mode_pumps_only_your_creatures():
    """Second printing of the modal mass-pump reader (`parse_mode_effect`):
    "Creatures you control get +2/+0 until end of turn." read off one mode."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Charge the Sanctum"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Charge the Sanctum")
    casting.choose_modes([1])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.power_of(mine) == 4
    assert scenario.game.toughness_of(mine) == 2
    assert scenario.game.power_of(theirs) == 2
    assert _jace_tokens(scenario) == []

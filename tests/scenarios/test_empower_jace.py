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
from magic_cards_model.models.token import PREDEFINED, create_tokens

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

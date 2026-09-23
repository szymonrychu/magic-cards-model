"""Scenario: "Put N <kind> counter(s) on each <group> you control." (CR 122.1)
- a computed *group*, not something targeted (CR 115.1 has nothing to check
here at all). Leyline of Abundance's activated ability and Ouroboroid's own
variable-X triggered ability are the two cards in the pool with this shape;
Ajani, Nacatl Pariah's own "+2: Put a +1/+1 counter on each Cat you control."
prints the identical shape with a subtype instead of a card type. That ability
sits on his *back* face (Ajani, Nacatl Avenger), and is now reachable through a
live game: CR 712.8e gives a transformed permanent only its back face's
characteristics, abilities included (CR 109.3), which is what
`test_ajanis_plus_two_puts_a_counter_on_each_cat_he_controls` below drives. The
same subtype read is also proven against Ocelot Pride, a real single-faced Cat
creature, going through the exact same generalised parser.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import parse_abilities
from magic_cards_model.machines.effects import _parse_put_counters_on_group_clause
from magic_cards_model.machines.triggers import AbilityKind, AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.cards import card
from tests.scenarios.harness import Scenario


def leyline_board() -> Scenario:
    """Alice with Leyline of Abundance already in play, enough green for its
    activation cost ({6}{G}{G}), and two of her own creatures plus one of
    bob's."""
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Leyline of Abundance",
                "Grizzly Bears",
                "Grizzly Bears",
                *["Forest"] * 8,
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_leyline_of_abundance_puts_a_counter_on_each_creature_alice_controls():
    """CR 122.1: both of alice's Bears get one +1/+1 counter each."""
    scenario = leyline_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leyline = scenario.find("Leyline of Abundance", Zone.BATTLEFIELD)
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    scenario.activate(leyline, auto=True)
    scenario.resolve_top()

    for bear in bears:
        assert bear.counter_count(Counter.PLUS_ONE) == 1


def test_leyline_of_abundance_does_not_touch_an_opponents_creature():
    """CR 122.1's "each creature you control" excludes bob's Bears - the
    corner case the wave brief calls out by name."""
    scenario = leyline_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leyline = scenario.find("Leyline of Abundance", Zone.BATTLEFIELD)
    bobs_bear = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(leyline, auto=True)
    scenario.resolve_top()

    assert bobs_bear.counter_count(Counter.PLUS_ONE) == 0


def test_leyline_of_abundance_with_no_creatures_to_pump_does_nothing():
    """An empty group: alice controls Leyline itself (not a creature) and
    nothing else creature-shaped. Putting counters on an empty group must not
    raise."""
    scenario = (
        Scenario().player("alice", battlefield=["Leyline of Abundance", *["Forest"] * 8]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leyline = scenario.find("Leyline of Abundance", Zone.BATTLEFIELD)

    scenario.activate(leyline, auto=True)
    scenario.resolve_top()  # must not raise

    assert scenario.battlefield_names().count("Leyline of Abundance") == 1


def test_leyline_of_abundances_counters_survive_the_cleanup_step():
    """Counters are a real, permanent mutation (CR 122.1), not a continuous
    effect - `ContinuousEffects.end_the_turn` (CR 514.2's "until end of turn"
    sweep) must not touch them, unlike a duration-bearing pump."""
    scenario = leyline_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leyline = scenario.find("Leyline of Abundance", Zone.BATTLEFIELD)
    (bear,) = scenario.creatures("Grizzly Bears", username="alice")[:1]

    scenario.activate(leyline, auto=True)
    scenario.resolve_top()
    assert bear.counter_count(Counter.PLUS_ONE) == 1

    scenario.game.continuous_effects.end_the_turn()
    assert bear.counter_count(Counter.PLUS_ONE) == 1


def test_ouroboroids_x_is_its_own_power():
    """ "put X +1/+1 counters on each creature you control, where X is this
    creature's power." Ouroboroid is a 1/3, so X = 1: itself and any other
    creature alice controls each get one counter."""
    scenario = Scenario().player("alice", battlefield=["Ouroboroid", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ouroboroid = scenario.creature("Ouroboroid", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.advance()  # precombat main -> beginning of combat
    assert scenario.stack_names() == ["Ouroboroid's triggered ability"]
    scenario.pass_until_resolved()

    assert ouroboroid.counter_count(Counter.PLUS_ONE) == 1
    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_ouroboroids_own_x_is_zero_if_it_has_already_left_the_battlefield():
    """CR 603.10a: a triggered ability still resolves once its source is gone,
    but `game.power_of` has no board entry left to read - the effect must
    read that as zero (CR 208.5's own floor for "no value"), not raise or
    silently put a huge number of counters."""
    effect = _parse_put_counters_on_group_clause(
        "put X +1/+1 counters on each creature you control, where X is this creature's power."
    )
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Ouroboroid", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ouroboroid = scenario.creature("Ouroboroid", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(ouroboroid)
    assert ouroboroid.zone is Zone.GRAVEYARD

    stand_in_ability = parse_abilities(card("Ouroboroid"))[0]  # unread by this effect
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=stand_in_ability,
        source_id=ouroboroid.id,
        source_name="Ouroboroid",
        controller="alice",
    )
    effect(scenario.game, ability)  # must not raise

    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_the_cat_subtype_shape_reads_the_computed_board_not_the_printed_type_line():
    """Ajani's own template - "each Cat you control" - against Ocelot Pride, a
    real single-faced Cat creature, with the clause called directly rather than
    through an activation. The live-game half is
    `test_ajanis_plus_two_puts_a_counter_on_each_cat_he_controls` below; this
    one pins the parser's own subtype read against the *computed* board
    (CR 613.4, CR 613.5, CR 205.3) with no transform in the way."""
    effect = _parse_put_counters_on_group_clause("Put a +1/+1 counter on each Cat you control.")
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Ocelot Pride", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cat = scenario.creature("Ocelot Pride", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    stand_in_ability = parse_abilities(card("Ocelot Pride"))[-1]  # unread by this effect
    ability = AbilityOnStack(
        kind=AbilityKind.ACTIVATED,
        ability=stand_in_ability,
        source_id=cat.id,
        source_name="Ocelot Pride",
        controller="alice",
    )
    effect(scenario.game, ability)

    assert cat.counter_count(Counter.PLUS_ONE) == 1
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_ajanis_plus_two_puts_a_counter_on_each_cat_he_controls():
    """Ajani, Nacatl Pariah's own printed shape, driven through a live game.

    CR 701.27a turns him over; CR 712.8e then gives him "only the
    characteristics of his back face", so Ajani, Nacatl Avenger's `+2` is an
    ability he actually has (CR 109.3 counts abilities among an object's
    characteristics) and CR 606.4's loyalty cost is payable against the loyalty
    counters CR 306.5b put on as he entered transformed.

    He is no longer a Cat himself once transformed (CR 205.3: the back face's
    type line is "Legendary Planeswalker — Ajani"), so the counter lands on
    Ocelot Pride alone - the group read is against the *computed* board
    (CR 613.5), which is what makes that fall out rather than needing a check.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah", "Ocelot Pride"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani = scenario.creature("Ajani, Nacatl Pariah", "alice")
    cat = scenario.creature("Ocelot Pride", "alice")

    # CR 712.14a's "return him to the battlefield transformed" is his own
    # trigger's wording; entering transformed is what brings the loyalty
    # counters with it (CR 306.5b), so it is the route used here too.
    ajani = scenario.game.put_onto_battlefield(
        scenario.game.exile_permanent(ajani), "alice", transformed=True
    )
    assert ajani.name == "Ajani, Nacatl Avenger"
    assert ajani.loyalty == 3
    plus_two = scenario.game.activated_abilities(ajani)[0]
    assert plus_two.cost == "+2"

    scenario.activate(ajani, index=0)  # the +2
    scenario.resolve_top()

    assert cat.counter_count(Counter.PLUS_ONE) == 1
    assert ajani.counter_count(Counter.PLUS_ONE) == 0, "a transformed Ajani is not a Cat"
    assert ajani.loyalty == 5, "CR 606.4: +2 puts two loyalty counters on as its cost"


def test_vojas_x_is_the_number_of_elves_she_controls():
    """Voja, Jaws of the Conclave's own attack trigger: "put X +1/+1 counters
    on each creature you control, where X is the number of Elves you
    control." Before this wave, `_COUNTER_EACH_GROUP_RE`'s "where X is"
    reader only ever recognised the single literal string "this creature's
    power" - any other expression, Voja's included, silently placed nothing.

    Number-sweep G12-1. Two real Elves (Llanowar Elves, Elvish Mystic; CR
    205.3) put X at 2 - not Voja herself, a Wolf - so all three of alice's
    creatures (Voja included) get two +1/+1 counters each (CR 122.1a).

    Driven through `_parse_put_counters_on_group_clause` directly against a
    real board rather than a live attack: Voja's own printed ability is two
    CR 608.2c clauses ("put X counters ...", then "Draw a card for each Wolf
    you control"), and the second is the number sweep's G1 family's own
    "for each" gap on the *player*-clause shape, not this one - unrelated to
    G12 and not yet landed on this branch. `_parse_mixed_clauses`' own
    all-or-nothing-per-ability rule (CR 608.2c has no notion of running half
    an instruction) means the whole trigger cannot resolve live until G1
    lands too; this proves G12's own half of it works, the same direct-call
    technique `test_ouroboroids_own_x_is_zero_if_it_has_already_left_the_
    battlefield` above already uses.
    """
    effect = _parse_put_counters_on_group_clause(
        "Put X +1/+1 counters on each creature you control, where X is the "
        "number of Elves you control."
    )
    assert effect is not None

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Voja, Jaws of the Conclave",
                "Llanowar Elves",
                "Elvish Mystic",
                "Grizzly Bears",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    voja = scenario.creature("Voja, Jaws of the Conclave", "alice")
    elves = scenario.creatures("Llanowar Elves", "Elvish Mystic", username="alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    stand_in_ability = parse_abilities(card("Voja, Jaws of the Conclave"))[-1]
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=stand_in_ability,
        source_id=voja.id,
        source_name="Voja, Jaws of the Conclave",
        controller="alice",
    )
    effect(scenario.game, ability)

    assert voja.counter_count(Counter.PLUS_ONE) == 2
    for elf in elves:
        assert elf.counter_count(Counter.PLUS_ONE) == 2
    assert bears.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.game.unreadable_counter_amount_notices == []


def test_an_unreadable_group_where_x_is_expression_fails_closed_with_a_notice():
    """No silent skip (number-sweep G12-1): an "X, where X is `<expr>`" this
    wave's `amount_expression` cannot read must not guess - it places no
    counters and records an `UnreadableCounterAmountNotice`, the same
    fail-closed shape `tests/scenarios/test_counters_equal_to_an_expression.
    py`'s own unreadable-expression test already exercises for the "equal to"
    phrasing."""
    effect = _parse_put_counters_on_group_clause(
        "Put X +1/+1 counters on each creature you control, where X is the "
        "number of dreams you had last night."
    )
    assert effect is not None

    scenario = Scenario().player("alice", battlefield=["Ouroboroid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ouroboroid = scenario.creature("Ouroboroid", "alice")

    stand_in_ability = parse_abilities(card("Ouroboroid"))[0]
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=stand_in_ability,
        source_id=ouroboroid.id,
        source_name="Ouroboroid",
        controller="alice",
    )
    effect(scenario.game, ability)

    assert ouroboroid.counter_count(Counter.PLUS_ONE) == 0
    (notice,) = scenario.game.unreadable_counter_amount_notices
    assert notice.source_name == "Ouroboroid"
    assert notice.expression == "the number of dreams you had last night"


# --------------------------------------------------------------------------
# "Put N counters [equal to <expr>] on each [other] creature you control
# named <Name>" - CR 201.5's own name-based group, not a type or subtype
# --------------------------------------------------------------------------


def test_baloth_packhunter_counters_another_baloth_packhunter_not_itself():
    """Off-set: Baloth Packhunter: "When this creature enters, put two +1/+1
    counters on each other creature you control named Baloth Packhunter." A
    fixed literal count, and "other" excludes the newly entering creature
    itself from its own trigger.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Baloth Packhunter"],
            battlefield=["Baloth Packhunter", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    original = scenario.creature("Baloth Packhunter", "alice")
    sources = scenario.untapped_sources(*["Forest"] * 4, username="alice")
    scenario.cast_and_resolve("Baloth Packhunter", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger

    new_one = next(
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Baloth Packhunter" and state is not original
    )
    assert original.counter_count(Counter.PLUS_ONE) == 2
    assert new_one.counter_count(Counter.PLUS_ONE) == 0


def test_gruff_triplets_dies_trigger_counters_its_own_token_copies():
    """On-set: Gruff Triplets: "When this creature enters, if it isn't a
    token, create two tokens that are copies of it. When this creature
    dies, put a number of +1/+1 counters equal to its power on each
    creature you control named Gruff Triplets." Differently worded from
    Baloth Packhunter (no "other" at all - the dead original is never part
    of the battlefield scan to begin with - and "equal to its power" instead
    of a flat count) - proof the reader is not fitted to either card's own
    sentence. `its power` is read off `AbilityOnStack.event` (CR 603.10a's
    look-back onto the dying original), not off the token copies receiving
    the counters.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gruff Triplets"],
            battlefield=["Forest"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6, username="alice")
    original = scenario.cast_and_resolve("Gruff Triplets", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger, making two token copies

    copies = [
        state
        for state in scenario.game.battlefield
        if state.name == "Gruff Triplets" and state is not original
    ]
    assert len(copies) == 2
    assert original.power == 3

    scenario.game.destroy(original)
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()  # the dies trigger

    assert all(copy.counter_count(Counter.PLUS_ONE) == 3 for copy in copies)
    assert all(copy.power == 6 for copy in copies)


# --------------------------------------------------------------------------
# "... on each tapped/untapped creature you control" - a CR 110.5 status
# filter on `_COUNTER_EACH_GROUP_RE`'s group noun, general to any group word
# the clause already reads (a card type or a subtype), proven here on a card
# type ("creature"). Aang and La, Ocean's Fury's own attack trigger is the
# reported shape; Effie, Fast Learner - a real printing outside the deck pool
# and not legal in Modern, Pioneer or Standard - proves it is the tap-state
# word doing the work, not anything specific to Aang's own card.
# --------------------------------------------------------------------------


def test_effies_survival_puts_a_counter_on_each_tapped_creature_she_controls():
    """Effie, Fast Learner (off-pool proof, not the reported card): "put a
    +1/+1 counter on each tapped creature you control" - an untapped creature
    alice controls is skipped, a tapped one is not, and an opponent's tapped
    creature never counts (CR 110.5's status belongs to the permanent, "you
    control" is still CR 109.5's own read)."""
    effect = _parse_put_counters_on_group_clause(
        "put a +1/+1 counter on each tapped creature you control"
    )
    assert effect is not None

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Effie, Fast Learner", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    effie = scenario.creature("Effie, Fast Learner", "alice")
    tapped_bear, untapped_bear = scenario.creatures(
        "Grizzly Bears", "Grizzly Bears", username="alice"
    )
    bobs_bear = scenario.creature("Grizzly Bears", "bob")
    effie.tapped = True
    tapped_bear.tapped = True
    bobs_bear.tapped = True

    stand_in_ability = parse_abilities(card("Effie, Fast Learner"))[-1]  # unread by this effect
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=stand_in_ability,
        source_id=effie.id,
        source_name="Effie, Fast Learner",
        controller="alice",
    )
    effect(scenario.game, ability)

    assert effie.counter_count(Counter.PLUS_ONE) == 1, "Effie herself is tapped and a creature"
    assert tapped_bear.counter_count(Counter.PLUS_ONE) == 1
    assert untapped_bear.counter_count(Counter.PLUS_ONE) == 0
    assert bobs_bear.counter_count(Counter.PLUS_ONE) == 0, "not alice's to put a counter on"


def test_aang_and_las_attack_trigger_counters_every_tapped_creature_alice_controls():
    """Aang and La, Ocean's Fury's own printed trigger, driven through a live
    game: CR 701.27a transforms Aang, CR 712.8e gives the back face's own
    abilities (CR 109.3), and attacking taps the attacker itself (CR 508.1a)
    before the trigger it causes ever resolves - so Aang and La counts
    itself along with any other tapped creature alice controls, and not her
    own untapped one."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Aang, Swift Savior", "Grizzly Bears", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    aang = scenario.find("Aang, Swift Savior", Zone.BATTLEFIELD)
    tapped_bear, untapped_bear = scenario.creatures(
        "Grizzly Bears", "Grizzly Bears", username="alice"
    )
    aang.transform()
    assert aang.name == "Aang and La, Ocean's Fury"
    aang.summoning_sick = False
    tapped_bear.tapped = True

    scenario.attack_with(aang)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Aang and La, Ocean's Fury's triggered ability"]
    scenario.resolve_top()

    assert aang.counter_count(Counter.PLUS_ONE) == 1, "attacking taps Aang and La itself"
    assert tapped_bear.counter_count(Counter.PLUS_ONE) == 1
    assert untapped_bear.counter_count(Counter.PLUS_ONE) == 0

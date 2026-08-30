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

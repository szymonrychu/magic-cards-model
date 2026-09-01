"""Creatures put onto the battlefield already attacking (CR 508.4).

Parhelion II: "Whenever Parhelion II attacks, create two 4/4 white Angel
creature tokens with flying and vigilance that are attacking."

CR 508.4: "If a creature is put onto the battlefield attacking, its controller
chooses which defending player, planeswalker a defending player controls, or
battle a defending player protects it's attacking as it enters the
battlefield." CR 508.4c adds the half that matters most here: "A creature
that's put onto the battlefield attacking or that is stated to be attacking
isn't affected by requirements or restrictions that apply to the declaration
of attackers" - it was never declared, so CR 508.1's declaration rules never
looked at it. And because it was never declared, CR 508.1f's "The active
player taps the chosen creatures" never applied either: these Angels arrive
untapped, which is a visible difference from a real attacker.

The trigger itself is CR 508.3a - "An ability that reads 'Whenever [a
creature] attacks, . . .' triggers if that creature is declared as an
attacker."

**Crew is not modelled** (see `docs/engine-coverage.md`'s keyword report:
`scripts/sweep_pool.py --keywords` still lists Crew as having no execution
path), so Parhelion II - a Vehicle, and not a creature until crewed - cannot
be declared as an attacker on its own. Every scenario here animates it with
Karn, the Great Creator's `+1` instead ("Until your next turn, up to one
target noncreature artifact becomes an artifact creature with power and
toughness each equal to its mana value"), which is a real card doing a real
thing and is the same route `test_type_changing_and_pt_setting_effects.py`
already uses. That makes Parhelion II an 8/8 rather than its printed 5/5,
which none of these assertions depend on.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario


def parhelion_board(bob_battlefield: list[str] | None = None) -> Scenario:
    """Alice with Karn and Parhelion II already in play, so nothing is
    summoning sick and the Vehicle can be animated and attack the same turn."""
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Karn, the Great Creator", "Parhelion II"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob_battlefield or []), library=["Mountain"] * 5)
    )


def animate_and_attack(scenario) -> object:
    """Karn's +1 onto Parhelion II, then declare it as an attacker and put the
    resulting trigger on the stack."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    parhelion = scenario.creature("Parhelion II", "alice")
    scenario.activate(karn, index=0, targets=[parhelion])
    scenario.pass_until_resolved()
    assert scenario.game.computed_board().of(parhelion).is_creature, "Karn's +1 landed"

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(parhelion)
    scenario.game.put_triggers_on_stack()
    return parhelion


def angels(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name.startswith("Angel")]


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_two_angels_arrive_attacking_the_player_parhelion_is_attacking():
    """CR 508.4: the tokens choose a defending player as they enter. Nothing
    on the card names one, so they join the attack their controller has
    already declared."""
    scenario = parhelion_board().build()
    parhelion = animate_and_attack(scenario)

    assert scenario.stack_names() == ["Parhelion II's triggered ability"]
    scenario.pass_until_resolved()

    created = angels(scenario)
    assert len(created) == 2
    assert all(is_token(angel) for angel in created)
    assert all(scenario.game.is_attacking(angel) for angel in created)
    assert scenario.game.is_attacking(parhelion)


# --------------------------------------------------------------------------
# Corner cases
# --------------------------------------------------------------------------


def test_the_angels_are_not_tapped_the_way_a_declared_attacker_is():
    """CR 508.1f taps the creatures *chosen* in the declaration - "Tapping a
    creature when it's declared as an attacker isn't a cost; attacking simply
    causes creatures to become tapped." Nothing was declared here, and the
    printed text says only "that are attacking", so these Angels arrive
    untapped.

    Parhelion II itself is untapped too, but for a different reason -
    CR 702.20b's vigilance, which it prints - so this asserts the Angels'
    state rather than contrasting the two.
    """
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()

    assert all(not angel.tapped for angel in angels(scenario))


def test_the_angels_have_the_printed_characteristics():
    """CR 701.7a's "put the specified number of tokens with the specified
    characteristics onto the battlefield", read off the card's own noun
    phrase: two 4/4 white Angel creature tokens with flying and vigilance."""
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()

    for angel in angels(scenario):
        computed = scenario.game.computed_board().of(angel)
        assert computed.power == 4
        assert computed.toughness == 4
        assert computed.is_creature
        assert [color.value for color in computed.colors] == ["W"]
        assert "Angel" in angel.subtypes
        assert angel.card.keywords == ["Flying", "Vigilance"]


def test_a_defender_that_could_never_be_declared_as_an_attacker_still_arrives_attacking():
    """CR 508.4c: "A creature that's put onto the battlefield attacking ...
    isn't affected by requirements or restrictions that apply to the
    declaration of attackers." The Angels are brand new this turn and so
    would be summoning sick (CR 302.6, CR 508.1a) if they had to be declared -
    they are attacking anyway."""
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()

    created = angels(scenario)
    assert created, "the tokens exist"
    assert all(angel.summoning_sick for angel in created), "they arrived this turn"
    assert all(scenario.game.is_attacking(angel) for angel in created)


def test_the_angels_deal_their_combat_damage_in_the_same_step():
    """Once attacking, they are ordinary attackers for the rest of combat -
    unblocked, they hit the defending player alongside Parhelion II."""
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.start_at(Step.COMBAT_DAMAGE)
    scenario.combat_damage()

    # 8 from the animated Parhelion II (its mana value) plus 4 from each Angel.
    assert scenario.player("bob").life == 20 - 8 - 4 - 4


def test_the_angels_leave_combat_when_the_combat_phase_ends():
    """CR 511.3: "As soon as the end of combat step ends, all creatures,
    battles, and planeswalkers are removed from combat." Being *put onto* the
    battlefield attacking buys no exemption from that."""
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()
    assert all(scenario.game.is_attacking(angel) for angel in angels(scenario))

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.no_blocks()
    scenario.start_at(Step.COMBAT_DAMAGE)
    scenario.combat_damage()
    scenario.game.end_of_combat()

    assert scenario.attackers() == []
    assert all(angel.zone is Zone.BATTLEFIELD for angel in angels(scenario)), (
        "leaving combat is not leaving the battlefield"
    )


def test_the_trigger_fires_again_on_a_second_attack():
    """CR 508.3a is an ordinary "whenever this attacks" trigger, with no
    once-per-turn clause, so a second combat makes two more Angels.

    Karn's +1 lasts "until your next turn", which ends exactly as
    alice's next turn begins, so the Vehicle has to be animated again before
    it can attack again - which is itself the point: the trigger is on
    Parhelion II, not on the animation, and it fires each time the *attack*
    happens.
    """
    scenario = parhelion_board().build()
    animate_and_attack(scenario)
    scenario.pass_until_resolved()
    assert len(angels(scenario)) == 2

    parhelion = scenario.creature("Parhelion II", "alice")
    while scenario.turn.active_player != "alice" or scenario.turn.turn_number == 1:
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    scenario.activate(karn, index=0, targets=[parhelion])
    scenario.pass_until_resolved()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.game.computed_board().of(parhelion).is_creature, "animated again"
    scenario.attack_with(parhelion)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(angels(scenario)) == 4


def test_no_attack_means_no_angels():
    """CR 603.2: "Whenever a game event or game state matches a triggered
    ability's trigger event, that ability automatically triggers." No attack
    is declared here, so nothing matches and nothing is created."""
    scenario = parhelion_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    parhelion = scenario.creature("Parhelion II", "alice")
    scenario.activate(karn, index=0, targets=[parhelion])
    scenario.pass_until_resolved()

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert angels(scenario) == []


# --------------------------------------------------------------------------
# CR 508.8 - the step this creature's own combat needs in order to exist
# --------------------------------------------------------------------------


def test_a_token_created_attacking_deals_its_combat_damage_across_an_advanced_turn():
    """CR 508.8, from the side that matters: the combat damage step happens.

    "If no creatures are declared as attackers or put onto the battlefield
    attacking, skip the declare blockers and combat damage steps." `Game.advance`
    performs that skip as it steps out of the declare attackers step, so a
    creature that is attacking without the step existing deals no damage at all
    - the silent failure this test is here to catch.

    Fire Navy Trebuchet (confirmed with `resolve_cards`): "Defender, reach /
    Whenever you attack, create a 2/1 colorless Construct artifact creature
    token with flying named Ballistic Boulder that's tapped and attacking.
    Sacrifice that token at the beginning of the next end step." The Trebuchet
    itself has defender and cannot attack, so Grizzly Bears is the declared
    attacker and the Boulder is the one CR 508.4 puts in - and unlike every
    test above, this one walks the steps with `Game.advance` rather than moving
    the pointer by hand, which is the only route that consults CR 508.8.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Fire Navy Trebuchet", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()
    boulder = scenario.creature("Ballistic Boulder", "alice")
    assert is_token(boulder) and scenario.game.is_attacking(boulder)

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    # 2 from the bear, 2 from the Boulder - the second only if its own combat
    # damage step happened.
    assert scenario.player("bob").life == 20 - 2 - 2


def test_a_creature_put_onto_the_battlefield_attacking_is_itself_enough_to_keep_the_steps():
    """CR 508.8's second clause, on its own: no creature was ever *declared*.

    The rule is a union of two histories - "If no creatures are declared as
    attackers **or put onto the battlefield attacking**" - and CR 508.4c says
    the second kind was never declared ("A creature that's put onto the
    battlefield attacking or that is stated to be attacking isn't affected by
    requirements or restrictions that apply to the declaration of attackers").
    So a combat in which the declaration found nothing and an effect then put a
    creature in still has a declare blockers step and a combat damage step.

    Every card in the pool that puts a creature onto the battlefield attacking
    does so from an "attacks"/"whenever you attack" trigger, which cannot fire
    without a declared attacker, so the declared half of CR 508.8 would answer
    for those boards on its own. This one reaches the second clause directly
    through the engine's own CR 508.4 primitive - the same call Parhelion II's
    Angels and Ilharg's creature card arrive by - on a real Grizzly Bears in a
    real game.
    """
    from magic_cards_model.models.card_state import TargetRef
    from magic_cards_model.models.token import _put_onto_the_battlefield_attacking

    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], library=["Mountain"] * 5)
        .player("bob", library=["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.attackers() == [], "nobody was declared"

    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice", tapped=True)
    _put_onto_the_battlefield_attacking(scenario.game, bears, TargetRef.coerce("bob"))
    assert scenario.game.is_attacking(bears)

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    assert scenario.player("bob").life == 20 - 2, "the combat damage step was not skipped"

"""Fight (CR 701.14) and its one-directional twin, "deals damage equal to
its power/loyalty to", read for three shapes `_parse_pump_then_fight_clause_
pair`/`_RIDER_FIGHTS_TARGET_RE` did not cover: no antecedent sentence at all
(a plain CR 109.2 self-reference), both participants independently targeted
by one clause, and a one-directional damage event where CR 701.14's "fight"
is never printed.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.14a** - "A spell or ability may instruct a creature to fight
  another creature ... Each of those creatures deals damage equal to its
  power to the other creature."
- **CR 701.14b** - a participant no longer on the battlefield or no longer a
  creature means neither fights or deals damage.
- **CR 109.2** - "it"/"this creature" is the self-reference of the object
  whose ability this is, absent any other antecedent.
- **CR 115.6** - "up to one target" legally chooses zero.
- **CR 119.2** - dealing damage is an event with no CR 701.14 restrictions
  of its own when the word "fights" is not printed.
- **CR 608.2c** - a resolving ability's or spell's instructions run in
  printed order; a rider's referent comes from its antecedent's own subject.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_mind_meanderer_fights_the_chosen_opposing_creature() -> None:
    """ "When this creature enters, it fights up to one target creature an
    opponent controls." - CR 109.2's "it" with no antecedent sentence: the
    trigger source itself.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Meanderer"], battlefield=["Forest"] * 4 + ["Island"] * 2)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Mind Meanderer", [bears])
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Island", "Island")
    meanderer = scenario.cast_and_resolve("Mind Meanderer", *sources)
    scenario.resolve_top()  # the enters-the-battlefield trigger

    assert bears.zone is Zone.GRAVEYARD, "4 damage is lethal to a 2/2"
    assert meanderer.zone is Zone.BATTLEFIELD
    assert meanderer.damage == 2


def test_mind_meanderer_with_no_legal_target_still_enters_safely() -> None:
    """CR 115.6: "up to one" with no opposing creature chooses zero, and the
    trigger does nothing - not a notice, not a crash.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mind Meanderer"], battlefield=["Forest"] * 4 + ["Island"] * 2)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Island", "Island")
    meanderer = scenario.cast_and_resolve("Mind Meanderer", *sources)
    scenario.resolve_top()

    assert meanderer.zone is Zone.BATTLEFIELD
    assert meanderer.damage == 0


def test_yoshimaru_puts_a_controlled_creature_into_a_fight() -> None:
    """ "When Yoshimaru enters, another target creature you control fights up
    to one target creature an opponent controls." - both fighters are this
    one clause's own, independently chosen targets.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Yoshimaru, Scrappy Stray"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest"],
            library=["Elder Gargaroth"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # A second creature already on alice's board so "another target creature
    # you control" has a legal target distinct from Yoshimaru itself. 6/6 so
    # it survives what a 2/2 deals back.
    scenario.put_onto_battlefield("Elder Gargaroth", "alice", from_zone=Zone.LIBRARY)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Yoshimaru, Scrappy Stray", [gargaroth, bob_bears])
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Yoshimaru, Scrappy Stray", *sources)
    scenario.resolve_top()

    assert gargaroth.damage == 2
    assert bob_bears.zone is Zone.GRAVEYARD, "6 damage is lethal to a 2/2"


def test_prey_upon_off_set_target_fights_target() -> None:
    """Prey Upon (not in this pool, not the reported card): "Target creature
    you control fights target creature you don't control." - the same
    grammar as Yoshimaru's own trigger, proven on a plain sorcery.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prey Upon"],
            battlefield=["Forest"],
            library=["Elder Gargaroth"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Elder Gargaroth", "alice", from_zone=Zone.LIBRARY)
    gargaroth = scenario.creature("Elder Gargaroth", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    forest = scenario.untapped_sources("Forest")[0]
    scenario.cast_and_resolve("Prey Upon", forest, targets=[gargaroth, bob_bears])

    assert gargaroth.damage == 2
    assert bob_bears.zone is Zone.GRAVEYARD, "6 damage is lethal to a 2/2"


def test_compel_brutality_mode_one_bites_with_a_creatures_power() -> None:
    """ "Target creature you control deals damage equal to its power to
    target creature or planeswalker an opponent controls." - CR 701.14's
    "fight" is never printed, so only the targeted victim takes damage.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Compel Brutality"],
            battlefield=["Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice", from_zone=Zone.LIBRARY)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")

    casting = scenario.cast("Compel Brutality")
    casting.choose_modes([1])
    casting.choose_targets([alice_bears, bob_angel])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob_angel.damage == 2
    assert alice_bears.damage == 0, "one-directional: the biter takes nothing back"


def test_compel_brutality_mode_two_bites_with_a_planeswalkers_loyalty() -> None:
    """Mode two: "Target planeswalker you control deals damage equal to its
    loyalty to target creature or planeswalker an opponent controls." - the
    same clause shape, "loyalty" standing in for "power".
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Compel Brutality"],
            battlefield=["Forest", "Forest"],
            library=["Karn, the Great Creator"],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Karn, the Great Creator", "alice", from_zone=Zone.LIBRARY)
    karn = scenario.creature("Karn, the Great Creator", "alice")
    bob_gargaroth = scenario.creature("Elder Gargaroth", "bob")
    starting_loyalty = karn.loyalty

    casting = scenario.cast("Compel Brutality")
    casting.choose_modes([2])
    casting.choose_targets([karn, bob_gargaroth])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bob_gargaroth.damage == starting_loyalty
    assert karn.loyalty == starting_loyalty, "the biting planeswalker keeps its own loyalty"


def test_aggressive_instinct_off_set_direct_two_target_bite() -> None:
    """Aggressive Instinct (not in this pool, not the reported card): "Target
    creature you control deals damage equal to its power to target creature
    you don't control." - a plain sorcery proving the same grammar Compel
    Brutality's mode one reads.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aggressive Instinct"],
            battlefield=["Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice", from_zone=Zone.LIBRARY)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_angel = scenario.creature("Serra Angel", "bob")
    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Aggressive Instinct", *sources, targets=[alice_bears, bob_angel])

    assert bob_angel.damage == 2
    assert alice_bears.damage == 0


def test_flourishing_grapple_debuffs_then_bites_with_a_second_target() -> None:
    """ "Target creature or planeswalker an opponent controls that's red or
    white loses all abilities until end of turn. Target creature you control
    deals damage equal to its power to that permanent." - the anaphoric-
    object twin of Compel Brutality's own direct-target shape: the rider
    names its own biter, and "that permanent" is the antecedent's target.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flourishing Grapple"],
            battlefield=["Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Ashling, the Limitless"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice", from_zone=Zone.LIBRARY)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    ashling = scenario.creature("Ashling, the Limitless", "bob")
    forest = scenario.untapped_sources("Forest")[0]
    scenario.cast_and_resolve("Flourishing Grapple", forest, targets=[ashling, alice_bears])

    assert ashling.damage == 2
    assert ashling.zone is Zone.BATTLEFIELD


def test_vigorbloom_charm_mode_three_counters_target_then_fights() -> None:
    """Regression proof that mode three's counter-then-fight shape already
    composes correctly through `_parse_pump_then_fight_clause_pair` (the
    counter-placing antecedent), independent of the new parsers this file
    otherwise exercises.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Vigorbloom Charm"],
            battlefield=["Forest", "Plains"],
            library=["Grizzly Bears"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Grizzly Bears", "alice", from_zone=Zone.LIBRARY)
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    bob_bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Vigorbloom Charm")
    casting.choose_modes([3])
    casting.choose_targets([alice_bears, bob_bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Forest", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert alice_bears.counters["+1/+1"] == 1
    assert alice_bears.damage == 2, "the pumped 3/3 survives the bear's own 2 power"
    assert bob_bears.zone is Zone.GRAVEYARD, "the pumped bear's 3 power is lethal to a 2/2"

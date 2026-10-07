"""Prevention shields a triggered or activated ability builds: divided among
any number of targets, around the ability's own source, around and from one
object at once, and around a creature type.

- Angel of Salvation: "When this creature enters, prevent the next 5 damage
  that would be dealt this turn to any number of targets, divided as you
  choose."
- Favored Hoplite: "Heroic - Whenever you cast a spell that targets this
  creature, put a +1/+1 counter on this creature and prevent all damage that
  would be dealt to it this turn."
- Goblin Snowman: "Whenever this creature blocks, prevent all combat damage
  that would be dealt to and dealt by it this turn."
- Pack Leader: "Whenever this creature attacks, prevent all combat damage that
  would be dealt this turn to Dogs you control."

Second printings: Moonlight Geist ("... dealt to and dealt by this creature
this turn", an activated ability), Soratami Cloud Chariot ("... dealt to and
dealt by target creature you control this turn"), Ith, High Arcanist ("Untap
target attacking creature. ... dealt to and dealt by that creature this
turn"); Djeru's Resolve's "Prevent all damage that would be dealt to it this
turn" on a spell is the regression. No other legal printing divides a
prevention shield, puts "to it" after a self clause on an ability, or names a
creature type as the shielded group - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 615.1a** - "prevent" makes a prevention effect.
- **CR 615.3** - a prevention effect lasts until used up or its duration ends.
- **CR 615.7** - "prevent the next N damage" is a shield reduced as it is used.
- **CR 601.2d** - a division is announced with the targets; each target gets
  at least 1.
- **CR 603.3d** - a trigger's targets and division are chosen as it is put on
  the stack.
- **CR 608.2b** - an illegal target's share is not created.
- **CR 611.2c** - a prevention effect from a resolved ability changes no
  characteristics, so it covers objects that were not covered when it began.
- **CR 400.7** - a creature that leaves and returns is a new object.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _outcomes(name: str) -> list[str]:
    return [c.outcome for c in card_support(card(name)).clauses if c.kind != "keyword"]


def _life(scenario, username: str) -> int:
    return scenario.player(username).life


def test_every_listed_card_reads_handled():
    for name in (
        "Angel of Salvation",
        "Favored Hoplite",
        "Goblin Snowman",
        "Pack Leader",
        "Moonlight Geist",
        "Soratami Cloud Chariot",
        "Ith, High Arcanist",
        "Djeru's Resolve",
    ):
        outcomes = _outcomes(name)
        assert outcomes and set(outcomes) == {"handled"}, (name, outcomes)


# -- Angel of Salvation: a divided shield -----------------------------------


def _angel(*, mine=("Grizzly Bears",), theirs=(), hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Angel of Salvation", *hand], battlefield=list(mine))
        .player(
            "bob", hand=["Lightning Bolt", "Shock"], battlefield=["Mountain", "Mountain", *theirs]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _bob_casts(scenario, name: str, target) -> None:
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(name, username="bob", targets=[target], auto=True)
    _drain(scenario)


def test_angel_division_reads_as_up_to_five_targets_dividing_five():
    profile = profile_for_text(
        "prevent the next 5 damage that would be dealt this turn to any number of targets, "
        "divided as you choose."
    )
    assert profile.understood
    assert profile.division is not None and profile.division.amount == 5
    (requirement,) = profile.requirements
    assert requirement.minimum == 0 and requirement.count == 5 and requirement.allows_players


def test_angel_divides_three_to_alice_and_two_to_her_bears():
    scenario = _angel()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets("alice", bears)
    scenario.will_choose_an_amount(2)
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    scenario.game.put_triggers_on_stack()
    (ability,) = scenario.game.stack
    assert ability.division == [3, 2], "announced as it went on the stack (CR 603.3d)"
    _drain(scenario)

    _bob_casts(scenario, "Lightning Bolt", "alice")
    _bob_casts(scenario, "Shock", bears)

    assert _life(scenario, "alice") == 20, "3 of the Bolt's 3 prevented"
    assert bears.damage == 0, "2 of the Shock's 2 prevented"
    assert _notices(scenario) == []


def test_angel_a_shield_is_used_up_and_the_rest_is_dealt():
    scenario = _angel(mine=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "alice")
    scenario.will_choose_targets("alice", giant)
    scenario.will_choose_an_amount(3)
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    _drain(scenario)

    _bob_casts(scenario, "Lightning Bolt", giant)

    assert giant.damage == 2, "a 1 shield against 3: 1 prevented, 2 dealt"
    assert scenario.game.active_prevention_shields()[0].player == "alice"


def test_angel_unanswered_division_gives_each_target_one_and_the_last_the_rest():
    scenario = _angel()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets("alice", bears)
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    scenario.game.put_triggers_on_stack()
    (ability,) = scenario.game.stack

    assert ability.division == [1, 4]


def test_angel_one_target_takes_all_five():
    scenario = _angel()
    scenario.will_choose_targets("alice")
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    _drain(scenario)

    _bob_casts(scenario, "Lightning Bolt", "alice")
    _bob_casts(scenario, "Shock", "alice")

    assert _life(scenario, "alice") == 20, "5 prevented across two sources"


def test_angel_an_illegal_target_loses_its_share_and_nobody_gets_it():
    scenario = _angel()
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_targets("alice", bears)
    scenario.will_choose_an_amount(0)
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(bears)
    _drain(scenario)

    _bob_casts(scenario, "Lightning Bolt", "alice")

    assert _life(scenario, "alice") == 18, "alice's share stays 1; the Bears' 4 is not created"


def test_angel_can_shield_an_opponents_creature_too():
    scenario = _angel(mine=(), theirs=("Hill Giant",))
    giant = scenario.creature("Hill Giant", "bob")
    scenario.will_choose_targets(giant)
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    _drain(scenario)

    _bob_casts(scenario, "Lightning Bolt", giant)

    assert giant.damage == 0


def test_angel_shields_last_only_this_turn():
    scenario = _angel()
    scenario.will_choose_targets("alice")
    scenario.put_onto_battlefield("Angel of Salvation", "alice")
    _drain(scenario)

    (shield,) = scenario.game.active_prevention_shields()
    assert shield.until_end_of_turn and shield.amount == 5 and shield.player == "alice"


# -- Favored Hoplite: heroic, "it" is this creature -------------------------


def _hoplite():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shock", "Lightning Bolt"],
            battlefield=["Favored Hoplite", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_hoplite_heroic_shield_prevents_the_targeting_spells_own_damage():
    scenario = _hoplite()
    hoplite = scenario.creature("Favored Hoplite", "alice")
    scenario.cast_onto_stack("Shock", targets=[hoplite], auto=True)
    _drain(scenario)

    assert hoplite.zone is Zone.BATTLEFIELD
    assert hoplite.counter_count("+1/+1") == 1
    assert hoplite.damage == 0
    assert _notices(scenario) == []


def test_hoplite_shield_lasts_the_turn_and_covers_a_later_source():
    scenario = _hoplite()
    hoplite = scenario.creature("Favored Hoplite", "alice")
    scenario.cast_onto_stack("Shock", targets=[hoplite], auto=True)
    _drain(scenario)
    scenario.cast_onto_stack("Lightning Bolt", targets=[hoplite], auto=True)
    _drain(scenario)

    assert hoplite.zone is Zone.BATTLEFIELD
    assert hoplite.damage == 0
    assert hoplite.counter_count("+1/+1") == 2


def test_hoplite_shields_only_itself():
    scenario = _hoplite()
    hoplite = scenario.creature("Favored Hoplite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack("Shock", targets=[hoplite], auto=True)
    _drain(scenario)
    scenario.cast_onto_stack("Lightning Bolt", targets=[bears], auto=True)
    _drain(scenario)

    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None


# -- Goblin Snowman: to and by itself, combat only --------------------------


def _snowman_blocks(attacker: str = "Hill Giant"):
    scenario = (
        Scenario()
        .player("bob", battlefield=[attacker])
        .player("alice", battlefield=["Goblin Snowman"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature(attacker, "bob")
    snowman = scenario.creature("Goblin Snowman", "alice")
    scenario.attack_with(giant, defending="alice")
    scenario.block(giant, snowman)
    _drain(scenario)
    return scenario, giant, snowman


def test_snowman_blocking_takes_and_deals_no_combat_damage():
    scenario, giant, snowman = _snowman_blocks()
    scenario.combat_damage()

    assert snowman.zone is Zone.BATTLEFIELD and snowman.damage == 0
    assert giant.damage == 0
    assert _notices(scenario) == []


def test_snowman_its_tap_ability_is_noncombat_damage_and_still_dealt():
    scenario, giant, snowman = _snowman_blocks()
    snowman.summoning_sick = False  # staged: on the battlefield since alice's last turn
    scenario.pass_priority("bob")
    scenario.activate(snowman, username="alice", targets=[giant])
    scenario.resolve_top()

    assert giant.damage == 1


def test_snowman_noncombat_damage_to_it_is_not_prevented():
    scenario = (
        Scenario()
        .player("bob", hand=["Shock"], battlefield=["Hill Giant", "Mountain"])
        .player("alice", battlefield=["Goblin Snowman"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = scenario.creature("Hill Giant", "bob")
    snowman = scenario.creature("Goblin Snowman", "alice")
    scenario.attack_with(giant, defending="alice")
    scenario.block(giant, snowman)
    _drain(scenario)
    scenario.cast_and_resolve(
        "Shock",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[snowman],
    )

    assert scenario.find("Goblin Snowman", Zone.GRAVEYARD, "alice") is not None


# -- Pack Leader: Dogs you control -------------------------------------------


def _pack(mine: list[str], theirs: list[str]):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Pack Leader", *mine])
        .player("bob", battlefield=theirs)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_pack_leader_shields_every_dog_alice_controls_in_combat():
    scenario = _pack(
        ["Codecracker Hound", "Grizzly Bears"], ["Hill Giant", "Giant Spider", "Hill Giant"]
    )
    leader = scenario.creature("Pack Leader", "alice")
    hound = scenario.creature("Codecracker Hound", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    giant_one, giant_two = scenario.creatures("Hill Giant", "Hill Giant", username="bob")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(leader, hound, bears)
    _drain(scenario)
    scenario.block(leader, giant_one)
    scenario.block(hound, spider)
    scenario.block(bears, giant_two)
    scenario.combat_damage()

    assert leader.zone is Zone.BATTLEFIELD and leader.damage == 0
    assert hound.zone is Zone.BATTLEFIELD and hound.damage == 0
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None, "not a Dog"
    assert giant_one.damage == 2, "damage dealt by Dogs is not prevented"
    assert _notices(scenario) == []


def test_pack_leader_gone_still_shields_the_dogs():
    scenario = _pack(["Codecracker Hound"], ["Hill Giant"])
    leader = scenario.creature("Pack Leader", "alice")
    hound = scenario.creature("Codecracker Hound", "alice")
    scenario.attack_with(leader, hound)
    _drain(scenario)
    scenario.game.return_to_hand(leader)
    scenario.block(hound, scenario.creature("Hill Giant", "bob"))
    scenario.combat_damage()

    assert hound.zone is Zone.BATTLEFIELD and hound.damage == 0


def test_pack_leader_noncombat_damage_to_a_dog_is_not_prevented():
    scenario = (
        Scenario()
        .player("alice", hand=["Shock"], battlefield=["Pack Leader", "Ashmouth Hound", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    hound = scenario.creature("Ashmouth Hound", "alice")
    scenario.attack_with(scenario.creature("Pack Leader", "alice"))
    _drain(scenario)
    scenario.cast_onto_stack("Shock", targets=[hound], auto=True)
    _drain(scenario)

    assert scenario.find("Ashmouth Hound", Zone.GRAVEYARD, "alice") is not None


def test_pack_leader_does_not_shield_an_opponents_dog():
    scenario = _pack([], ["Codecracker Hound"])
    leader = scenario.creature("Pack Leader", "alice")
    scenario.attack_with(leader)
    _drain(scenario)
    bobs_hound = scenario.creature("Codecracker Hound", "bob")
    scenario.block(leader, bobs_hound)
    scenario.combat_damage()

    assert scenario.find("Codecracker Hound", Zone.GRAVEYARD, "bob") is not None


# -- second printings -------------------------------------------------------


def test_moonlight_geist_shield_is_both_ways():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Moonlight Geist", "Plains", "Plains", "Plains", "Plains"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    geist = scenario.creature("Moonlight Geist", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(geist)
    scenario.activate(geist, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    scenario.resolve_top()
    scenario.block(geist, spider)
    scenario.combat_damage()

    assert geist.zone is Zone.BATTLEFIELD and geist.damage == 0
    assert spider.damage == 0


def test_soratami_chariot_shields_its_target_both_ways():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Soratami Cloud Chariot", "Grizzly Bears", "Island", "Island"]
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(bears)
    chariot = scenario.find("Soratami Cloud Chariot", Zone.BATTLEFIELD, "alice")
    scenario.activate(
        chariot, *scenario.untapped_sources("Island", "Island"), index=1, targets=[bears]
    )
    scenario.resolve_top()
    scenario.block(bears, giant)
    scenario.combat_damage()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert giant.damage == 0


def test_ith_untaps_and_shields_that_creature_both_ways():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Ith, High Arcanist", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.attack_with(bears)
    ith = scenario.creature("Ith, High Arcanist", "bob")
    ith.summoning_sick = False  # staged: on the battlefield since bob's last turn
    scenario.pass_priority("alice")
    scenario.activate(ith, username="bob", targets=[bears])
    scenario.resolve_top()
    scenario.block(bears, scenario.creature("Hill Giant", "bob"))
    scenario.combat_damage()

    assert not bears.tapped
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert scenario.creature("Hill Giant", "bob").damage == 0


def test_djerus_resolve_spell_anaphor_still_shields_its_target():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Djeru's Resolve", "Lightning Bolt"],
            battlefield=["Grizzly Bears", "Plains", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_and_resolve(
        "Djeru's Resolve", *scenario.untapped_sources("Plains"), targets=[bears]
    )
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0

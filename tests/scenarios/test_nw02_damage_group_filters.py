"""Scenario: damage to a group named by a token, history or name predicate.

Listed: Incandescent Aria ("each nontoken creature"), Inflame ("each creature
dealt damage this turn") and Homing Lightning ("target creature and each other
creature with the same name as that creature"). Izzet Staticaster (already
handled as an ability) shares Homing Lightning's group reader and is the
second printing of that template; no other Modern/Pioneer/Standard printing
carries the nontoken or dealt-damage-this-turn group (Scryfall `o:/damage to
each (nontoken|.* dealt damage this turn)/` returns Aria and Inflame alone).

Verified this session with `mise run rules:find`:

- **CR 111.1** - a token is a marker used to represent a permanent that
  isn't represented by a card; "nontoken" excludes exactly those.
- **CR 120.1** - the damage events of the turn are the history Inflame reads.
- **CR 608.2f** - a group instruction is processed simultaneously: the
  recipients are fixed before any damage is dealt.
- **CR 608.2b** - a spell with only illegal targets doesn't resolve, so the
  name group is not damaged either.
- **CR 708.2** - a face-down permanent has no name, so it shares none.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_hand=(), alice_battlefield=(), bob_battlefield=(), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            life=20,
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _creatures_named(scenario, name, username):
    return [card for card in scenario.game.permanents_controlled_by(username) if card.name == name]


# -- Incandescent Aria: each nontoken creature ---------------------------------


def test_aria_hits_card_creatures_and_spares_tokens():
    scenario = _board(
        alice_hand=["Raise the Alarm", "Incandescent Aria"],
        alice_battlefield=["Plains", "Plains", "Mountain", "Forest", "Plains", "Grizzly Bears"],
        bob_battlefield=["Elvish Mystic", "Hill Giant"],
    )
    scenario.cast_and_resolve("Raise the Alarm", *scenario.untapped_sources("Plains", "Plains"))
    soldiers = [c for c in scenario.game.permanents_controlled_by("alice") if c.token]
    assert len(soldiers) == 2
    scenario.cast_and_resolve(
        "Incandescent Aria", *scenario.untapped_sources("Mountain", "Forest", "Plains")
    )
    scenario.state_based_actions()

    assert all(s.zone is Zone.BATTLEFIELD and s.damage == 0 for s in soldiers)
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None


def test_aria_hits_the_casters_own_nontoken_creatures_too():
    scenario = _board(
        alice_hand=["Incandescent Aria"],
        alice_battlefield=["Mountain", "Forest", "Plains", "Elvish Mystic"],
    )
    scenario.cast_and_resolve(
        "Incandescent Aria", *scenario.untapped_sources("Mountain", "Forest", "Plains")
    )
    scenario.state_based_actions()
    assert scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice") is not None


def test_aria_does_not_touch_players_or_noncreature_permanents():
    scenario = _board(
        alice_hand=["Incandescent Aria"],
        alice_battlefield=["Mountain", "Forest", "Plains", "Sol Ring"],
        bob_battlefield=["Jace Beleren"],
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")
    loyalty = jace.counter_count("loyalty")
    scenario.cast_and_resolve(
        "Incandescent Aria", *scenario.untapped_sources("Mountain", "Forest", "Plains")
    )
    assert scenario.player("alice").life == 20 and scenario.player("bob").life == 20
    assert jace.counter_count("loyalty") == loyalty


# -- Inflame: each creature dealt damage this turn -------------------------------


def test_inflame_hits_only_creatures_already_dealt_damage_this_turn():
    scenario = _board(
        alice_hand=["Lightning Bolt", "Inflame"],
        alice_battlefield=["Mountain", "Mountain"],
        bob_battlefield=["Colossal Dreadmaw", "Grizzly Bears", "Elvish Mystic"],
    )
    giant = scenario.find("Colossal Dreadmaw", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "bob")
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=[giant])
    scenario.cast_and_resolve("Inflame", second)
    scenario.state_based_actions()

    assert giant.zone is Zone.BATTLEFIELD and giant.damage == 5, "Bolt's 3 plus Inflame's 2"
    assert bears.damage == 0 and mystic.damage == 0, "never dealt damage this turn"


def test_inflame_with_nothing_damaged_does_nothing():
    scenario = _board(
        alice_hand=["Inflame"],
        alice_battlefield=["Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    scenario.cast_and_resolve("Inflame", *scenario.untapped_sources("Mountain"))
    scenario.state_based_actions()
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


def test_inflame_ignores_a_player_dealt_damage_this_turn():
    """ "Each creature dealt damage this turn" - a player dealt damage is not a
    creature, and a creature never dealt damage stays clear."""
    scenario = _board(
        alice_hand=["Lightning Bolt", "Inflame"],
        alice_battlefield=["Mountain", "Mountain"],
        bob_battlefield=["Grizzly Bears"],
    )
    first, second = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Lightning Bolt", first, targets=["bob"])
    scenario.cast_and_resolve("Inflame", second)
    assert scenario.player("bob").life == 17
    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob").damage == 0


def test_inflame_reaches_a_creature_dealt_damage_by_the_opponents_spell_too():
    """The damage need not come from the caster: any damage dealt this turn."""
    scenario = _board(
        alice_hand=["Inflame"],
        alice_battlefield=["Mountain", "Grizzly Bears"],
        bob_hand=["Lightning Bolt"],
        bob_battlefield=["Mountain"],
    )
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    assert bears.zone is Zone.GRAVEYARD, "a 2/2 dies to Bolt before Inflame matters"


# -- Homing Lightning: the target and each other creature with its name ------------


def test_homing_lightning_hits_the_target_and_every_creature_with_its_name():
    scenario = _board(
        alice_hand=["Homing Lightning"],
        alice_battlefield=["Mountain"] * 4 + ["Grizzly Bears"],
        bob_battlefield=["Grizzly Bears", "Grizzly Bears", "Hill Giant"],
    )
    bob_bears = _creatures_named(scenario, "Grizzly Bears", "bob")
    mine = _creatures_named(scenario, "Grizzly Bears", "alice")[0]
    scenario.cast_and_resolve(
        "Homing Lightning",
        *scenario.untapped_sources(*["Mountain"] * 4),
        targets=[bob_bears[0]],
    )
    scenario.state_based_actions()

    assert all(b.zone is Zone.GRAVEYARD for b in bob_bears)
    assert mine.zone is Zone.GRAVEYARD, "'each other creature' includes the caster's own"
    assert scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob").damage == 0


def test_homing_lightning_ignores_creatures_with_a_different_name():
    scenario = _board(
        alice_hand=["Homing Lightning"],
        alice_battlefield=["Mountain"] * 4,
        bob_battlefield=["Hill Giant", "Grizzly Bears"],
    )
    giant = scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    scenario.cast_and_resolve(
        "Homing Lightning", *scenario.untapped_sources(*["Mountain"] * 4), targets=[giant]
    )
    assert giant.zone is Zone.GRAVEYARD, "4 damage kills the 3/3 target"
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0


def test_a_face_down_creature_shares_no_name_with_another_face_down_creature():
    """CR 708.2: face-down permanents have no name, so two of them do not
    "have the same name"; the target alone is damaged."""
    scenario = _board(
        alice_hand=["Homing Lightning", "Brine Elemental", "Brine Elemental"],
        alice_battlefield=["Mountain"] * 4 + ["Island"] * 6,
    )
    for _ in range(2):
        casting = scenario.cast("Brine Elemental", username="alice")
        casting.use_keyword("Morph")
        payment = casting.begin_paying()
        scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
        scenario.put_on_stack(casting)
        scenario.resolve_top()
    down = [c for c in scenario.game.permanents_controlled_by("alice") if c.face_down]
    assert len(down) == 2
    scenario.cast_and_resolve(
        "Homing Lightning", *scenario.untapped_sources(*["Mountain"] * 4), targets=[down[0]]
    )
    assert down[0].zone is Zone.GRAVEYARD, "4 damage kills the 2/2 target"
    assert down[1].zone is Zone.BATTLEFIELD and down[1].damage == 0


def test_the_name_group_is_not_damaged_when_the_only_target_is_gone():
    """CR 608.2b: the target is the only one; with it illegal nothing happens."""
    scenario = _board(
        alice_hand=["Homing Lightning"],
        alice_battlefield=["Mountain"] * 4,
        bob_battlefield=["Grizzly Bears", "Grizzly Bears", "Island"],
        bob_hand=["Unsummon"],
    )
    bears = _creatures_named(scenario, "Grizzly Bears", "bob")
    spell = scenario.cast_onto_stack(
        "Homing Lightning", *scenario.untapped_sources(*["Mountain"] * 4), targets=[bears[0]]
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Unsummon",
        *scenario.untapped_sources("Island", username="bob"),
        username="bob",
        targets=[bears[0]],
    )
    assert bears[0].zone is Zone.HAND
    scenario.resolve_top()
    assert spell.zone is Zone.GRAVEYARD
    assert bears[1].damage == 0, "CR 608.2b: the spell didn't resolve"


def test_izzet_staticaster_shares_the_name_group_reader_second_printing():
    scenario = _board(
        alice_battlefield=["Izzet Staticaster"],
        bob_battlefield=["Grizzly Bears", "Grizzly Bears", "Hill Giant"],
    )
    bears = _creatures_named(scenario, "Grizzly Bears", "bob")
    staticaster = scenario.find("Izzet Staticaster", Zone.BATTLEFIELD, "alice")
    staticaster.summoning_sick = False
    scenario.activate(staticaster, targets=[bears[0]])
    scenario.pass_until_resolved()
    assert [b.damage for b in bears] == [1, 1]
    assert scenario.find("Hill Giant", Zone.BATTLEFIELD, "bob").damage == 0

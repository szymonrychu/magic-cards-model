"""A permanent's own trigger or activated ability dealing damage to a filtered
group, to two recipients at once, or to up to one target of each of three
kinds - and then tapping the group.

- Chaos Maw, Raging Swordtooth: "When this creature enters, it deals N damage
  to each other creature."
- Dagger Caster: "it deals 1 damage to each opponent and 1 damage to each
  creature your opponents control."
- Forge Devil: "it deals 1 damage to target creature and 1 damage to you."
- Swathcutter Giant, Gouged Zealot: "it deals 1 damage to each creature
  defending player controls."
- Shockmaw Dragon: "Whenever this creature deals combat damage to a player, it
  deals 1 damage to each creature that player controls."
- Thundermaw Hellkite: "it deals 1 damage to each creature with flying your
  opponents control. Tap those creatures."
- Volatile Arsonist // Dire-Strain Anarchist: "it deals 1|2 damage to each of
  up to one target creature, up to one target player, and/or up to one target
  planeswalker."

Second printings (proof the readers are templates): Harbinger of the Hunt and
Scourge of Kher Ridges ("each other creature with flying", an activated
ability), Balefire Dragon ("that much damage to each
creature that player controls"), Assembled Alphas (the two-recipient shape,
in the combat-referents file).

No second legal printing carries "Tap those creatures" after a group hit or
the three-optional-slot target list - see MEMORY.md.

Rules verified with `mise run rules:find`:

- **CR 120.3** - each recipient of a damage instruction is its own event.
- **CR 508.5** - "defending player": the player attacked, or the controller of
  the planeswalker attacked.
- **CR 608.2b** - a target that is illegal on resolution is skipped, and an
  ability whose every target is illegal does nothing at all.
- **CR 608.2c** - "Tap those creatures" is the group the sentence before it
  named, whether or not that sentence's damage was dealt.
- **CR 115.1d** - a triggered ability is targeted when it says "target".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.effects.registries import trigger_effect_for
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


def _enters(entering, *, mine=(), theirs=(), also=(), hand_zone=True) -> Scenario:
    """`entering` is put onto alice's battlefield from her hand."""
    builder = (
        Scenario()
        .player("alice", hand=[entering], battlefield=list(mine))
        .player("bob", battlefield=list(theirs))
    )
    for username, board in also:
        builder = builder.player(username, battlefield=list(board))
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield(entering, "alice")
    _drain(scenario)
    return scenario


# -- "each other creature": Chaos Maw, Raging Swordtooth ---------------------


def test_chaos_maw_hits_every_other_creature_and_not_itself():
    scenario = (
        Scenario()
        .player("alice", hand=["Chaos Maw"], battlefield=[*("Mountain",) * 7, "Giant Spider"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*("Mountain",) * 7, username="alice")
    scenario.cast_and_resolve("Chaos Maw", *sources, username="alice")
    _drain(scenario)

    assert scenario.creature("Chaos Maw", "alice").damage == 0
    assert scenario.creature("Giant Spider", "alice").damage == 3
    assert scenario.creature("Giant Spider", "bob").damage == 3
    assert _notices(scenario) == []


def test_chaos_maw_spares_noncreature_permanents_and_kills_what_it_can():
    scenario = _enters(
        "Chaos Maw",
        mine=["Sol Ring", "Grizzly Bears"],
        theirs=["Liliana of the Veil", "Hill Giant"],
    )
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice") is not None
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice").damage == 0
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    assert liliana.counter_count("loyalty") == 3, "a planeswalker is not a creature"


def test_chaos_maw_gone_before_its_trigger_resolves_still_hits_everything_else():
    scenario = (
        Scenario()
        .player("alice", hand=["Chaos Maw"], battlefield=["Giant Spider"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maw = scenario.put_onto_battlefield("Chaos Maw", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(maw)
    scenario.resolve_top()

    assert scenario.creature("Giant Spider", "alice").damage == 3
    assert scenario.creature("Giant Spider", "bob").damage == 3


def test_raging_swordtooth_deals_one_to_each_other_creature():
    scenario = _enters("Raging Swordtooth", mine=["Giant Spider"], theirs=["Giant Spider"])

    assert scenario.creature("Raging Swordtooth", "alice").damage == 0
    assert scenario.creature("Giant Spider", "alice").damage == 1
    assert scenario.creature("Giant Spider", "bob").damage == 1


def test_harbinger_of_the_hunt_activation_hits_each_other_flyer():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Harbinger of the Hunt", "Serra Angel", "Forest", "Forest", "Mountain"],
        )
        .player("bob", battlefield=["Serra Angel", "Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    harbinger = scenario.creature("Harbinger of the Hunt", "alice")
    scenario.activate(harbinger, auto=True, index=1)
    scenario.resolve_top()

    assert harbinger.damage == 0
    assert scenario.creature("Serra Angel", "alice").damage == 1
    assert scenario.creature("Serra Angel", "bob").damage == 1
    assert scenario.creature("Giant Spider", "bob").damage == 0, "no flying"
    assert _notices(scenario) == []


def test_scourge_of_kher_ridges_activation_hits_each_other_flyer_for_six():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Scourge of Kher Ridges", *("Mountain",) * 6])
        .player("bob", battlefield=["Serra Angel", "Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scourge = scenario.creature("Scourge of Kher Ridges", "alice")
    scenario.activate(scourge, auto=True, index=1)
    scenario.resolve_top()

    assert scenario.find("Serra Angel", Zone.GRAVEYARD, "bob") is not None
    assert scourge.damage == 0
    assert scenario.creature("Giant Spider", "bob").damage == 0


def test_each_other_creature_cards_read_handled():
    for name in (
        "Chaos Maw",
        "Raging Swordtooth",
        "Harbinger of the Hunt",
        "Scourge of Kher Ridges",
    ):
        assert set(_outcomes(name)) == {"handled"}, name


# -- two recipients: Dagger Caster, Forge Devil ------------------------------


def test_dagger_caster_hits_each_opponent_and_each_creature_they_control():
    scenario = _enters(
        "Dagger Caster",
        mine=["Giant Spider"],
        theirs=["Giant Spider", "Hill Giant"],
        also=[("carol", ["Grizzly Bears"])],
    )

    assert scenario.player("bob").life == 19
    assert scenario.player("carol").life == 19
    assert scenario.player("alice").life == 20
    assert scenario.creature("Giant Spider", "bob").damage == 1
    assert scenario.creature("Hill Giant", "bob").damage == 1
    assert scenario.creature("Grizzly Bears", "carol").damage == 1
    assert scenario.creature("Giant Spider", "alice").damage == 0
    assert scenario.creature("Dagger Caster", "alice").damage == 0
    assert _notices(scenario) == []


def test_dagger_caster_both_halves_land_together():
    """One instruction, both recipients read before either is hit (CR 608.2f)."""
    scenario = _enters("Dagger Caster", theirs=["Ornery Goblin"])

    assert scenario.player("bob").life == 19
    assert scenario.find("Ornery Goblin", Zone.GRAVEYARD, "bob") is not None


def test_forge_devil_hits_the_target_and_its_own_controller():
    scenario = (
        Scenario()
        .player("alice", hand=["Forge Devil"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")
    scenario.choose_trigger_targets("Forge Devil", [spider])
    scenario.put_onto_battlefield("Forge Devil", "alice")
    _drain(scenario)

    assert spider.damage == 1
    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_forge_devil_target_gone_deals_nothing_at_all():
    """CR 608.2b: with its only target illegal the ability does not resolve, so
    even the damage to its controller is not dealt."""
    scenario = (
        Scenario()
        .player("alice", hand=["Forge Devil"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spider = scenario.creature("Giant Spider", "bob")
    scenario.choose_trigger_targets("Forge Devil", [spider])
    scenario.put_onto_battlefield("Forge Devil", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(spider)
    scenario.resolve_top()

    assert scenario.player("alice").life == 20


def test_forge_devil_can_kill_itself_and_still_deals_its_second_half():
    scenario = (
        Scenario()
        .player("alice", hand=["Forge Devil"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Forge Devil", [bears])
    scenario.put_onto_battlefield("Forge Devil", "alice")
    _drain(scenario)

    assert bears.damage == 1
    assert scenario.player("alice").life == 19


def test_two_recipient_cards_read_handled():
    for name in ("Dagger Caster", "Forge Devil"):
        assert set(_outcomes(name)) == {"handled"}, name


# -- "each creature defending player controls": Swathcutter Giant, Gouged Zealot


def _attacker_board(attacker, *, theirs=(), mine=(), also=(), graveyard=()) -> Scenario:
    builder = (
        Scenario()
        .player("alice", battlefield=[attacker, *mine], graveyard=list(graveyard))
        .player("bob", battlefield=list(theirs))
    )
    for username, board in also:
        builder = builder.player(username, battlefield=list(board))
    scenario = builder.build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def test_swathcutter_giant_hits_each_creature_the_defending_player_controls():
    scenario = _attacker_board(
        "Swathcutter Giant", theirs=["Giant Spider", "Hill Giant"], mine=["Giant Spider"]
    )
    scenario.attack_with(scenario.creature("Swathcutter Giant", "alice"))
    _drain(scenario)

    assert scenario.creature("Giant Spider", "bob").damage == 1
    assert scenario.creature("Hill Giant", "bob").damage == 1
    assert scenario.creature("Giant Spider", "alice").damage == 0, "the attacker's own side"
    assert _notices(scenario) == []


def test_swathcutter_giant_in_multiplayer_hits_only_the_player_it_attacks():
    scenario = _attacker_board(
        "Swathcutter Giant", theirs=["Giant Spider"], also=[("carol", ["Giant Spider"])]
    )
    scenario.attack_with(scenario.creature("Swathcutter Giant", "alice"), defending="carol")
    _drain(scenario)

    assert scenario.creature("Giant Spider", "carol").damage == 1
    assert scenario.creature("Giant Spider", "bob").damage == 0


def test_swathcutter_giant_attacking_a_planeswalker_hits_its_controllers_creatures():
    """CR 508.5: the planeswalker's controller is the defending player; the
    planeswalker itself is not a creature and is untouched."""
    scenario = _attacker_board(
        "Swathcutter Giant",
        theirs=["Giant Spider", "Liliana of the Veil"],
        also=[("carol", ["Giant Spider"])],
    )
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Swathcutter Giant", "alice"), defending=liliana)
    _drain(scenario)

    assert scenario.creature("Giant Spider", "bob").damage == 1
    assert scenario.creature("Giant Spider", "carol").damage == 0
    assert liliana.counter_count("loyalty") == 3


def test_swathcutter_giant_with_no_defending_creatures_does_nothing():
    scenario = _attacker_board("Swathcutter Giant", mine=["Giant Spider"])
    scenario.attack_with(scenario.creature("Swathcutter Giant", "alice"))
    _drain(scenario)

    assert scenario.creature("Giant Spider", "alice").damage == 0


def test_gouged_zealot_with_delirium_hits_the_defending_creatures():
    scenario = _attacker_board(
        "Gouged Zealot",
        theirs=["Giant Spider"],
        graveyard=["Lightning Bolt", "Grizzly Bears", "Sol Ring", "Forest"],
    )
    scenario.attack_with(scenario.creature("Gouged Zealot", "alice"))
    _drain(scenario)

    assert scenario.creature("Giant Spider", "bob").damage == 1
    assert _notices(scenario) == []


def test_gouged_zealot_without_delirium_never_triggers():
    scenario = _attacker_board(
        "Gouged Zealot",
        theirs=["Giant Spider"],
        graveyard=["Lightning Bolt", "Grizzly Bears", "Sol Ring"],
    )
    scenario.attack_with(scenario.creature("Gouged Zealot", "alice"))
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty


def test_defending_group_cards_read_handled():
    for name in (
        "Swathcutter Giant",
        "Gouged Zealot",
        "Lord of Shatterskull Pass",
    ):
        assert set(_outcomes(name)) == {"handled"}, name


# -- "each creature that player controls": Shockmaw Dragon, Balefire Dragon ---


def test_shockmaw_dragon_hits_each_creature_the_damaged_player_controls():
    scenario = _attacker_board(
        "Shockmaw Dragon",
        theirs=["Giant Spider"],
        mine=["Giant Spider"],
        also=[("carol", ["Giant Spider"])],
    )
    scenario.attack_with(scenario.creature("Shockmaw Dragon", "alice"), defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)

    assert scenario.player("bob").life == 16
    assert scenario.creature("Giant Spider", "bob").damage == 1
    assert scenario.creature("Giant Spider", "carol").damage == 0, "not the damaged player"
    assert scenario.creature("Giant Spider", "alice").damage == 0
    assert _notices(scenario) == []


def test_shockmaw_dragon_blocked_deals_no_combat_damage_to_a_player_and_never_triggers():
    scenario = _attacker_board("Shockmaw Dragon", theirs=["Serra Angel", "Giant Spider"])
    dragon = scenario.creature("Shockmaw Dragon", "alice")
    angel = scenario.creature("Serra Angel", "bob")
    scenario.attack_with(dragon)
    scenario.block(dragon, angel)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack_is_empty
    assert scenario.creature("Giant Spider", "bob").damage == 0
    assert scenario.player("bob").life == 20


def test_balefire_dragon_deals_that_much_to_each_creature_that_player_controls():
    scenario = _attacker_board(
        "Balefire Dragon", theirs=["Giant Spider", "Hill Giant"], mine=["Giant Spider"]
    )
    scenario.attack_with(scenario.creature("Balefire Dragon", "alice"))
    scenario.no_blocks()
    scenario.combat_damage()
    _drain(scenario)

    assert scenario.player("bob").life == 14
    assert scenario.find("Giant Spider", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Hill Giant", Zone.GRAVEYARD, "bob") is not None
    assert scenario.creature("Giant Spider", "alice").damage == 0
    assert _notices(scenario) == []


def test_that_player_group_cards_read_handled():
    for name in ("Shockmaw Dragon", "Balefire Dragon"):
        assert set(_outcomes(name)) == {"handled"}, name


# -- "Tap those creatures": Thundermaw Hellkite ------------------------------


def test_thundermaw_hellkite_damages_and_taps_the_opposing_flyers():
    scenario = _enters(
        "Thundermaw Hellkite",
        mine=["Serra Angel"],
        theirs=["Serra Angel", "Giant Spider", "Birds of Paradise"],
    )
    angel = scenario.creature("Serra Angel", "bob")

    assert angel.damage == 1 and angel.tapped
    assert scenario.find("Birds of Paradise", Zone.GRAVEYARD, "bob") is not None
    spider = scenario.creature("Giant Spider", "bob")
    assert spider.damage == 0 and not spider.tapped
    mine = scenario.creature("Serra Angel", "alice")
    assert mine.damage == 0 and not mine.tapped, "only your opponents' flyers"
    assert _notices(scenario) == []


def test_thundermaw_hellkite_taps_every_opposing_flyer_even_when_it_kills_none():
    scenario = _enters("Thundermaw Hellkite", theirs=["Serra Angel", "Serra Angel"])
    angels = [s for s in scenario.game.battlefield if s.name == "Serra Angel"]

    assert len(angels) == 2 and all(a.tapped and a.damage == 1 for a in angels)


def test_thundermaw_hellkite_reads_handled():
    assert set(_outcomes("Thundermaw Hellkite")) == {"handled"}


# -- up to one target of each of three kinds: Volatile Arsonist --------------


def _arsonist_board(theirs=("Giant Spider",)) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Volatile Arsonist // Dire-Strain Anarchist"])
        .player("bob", battlefield=[*theirs, "Liliana of the Veil"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    return scenario


def _arsonist(scenario):
    return scenario.creature("Volatile Arsonist", "alice")


def test_volatile_arsonist_hits_one_creature_one_player_and_one_planeswalker():
    scenario = _arsonist_board()
    spider = scenario.creature("Giant Spider", "bob")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    scenario.choose_trigger_targets("Volatile Arsonist", [spider, "bob", liliana])
    scenario.attack_with(_arsonist(scenario))
    _drain(scenario)

    assert spider.damage == 1
    assert scenario.player("bob").life == 19
    assert liliana.counter_count("loyalty") == 2
    assert _notices(scenario) == []


def test_volatile_arsonist_with_no_targets_chosen_deals_nothing():
    scenario = _arsonist_board()
    scenario.choose_trigger_targets("Volatile Arsonist", [])
    scenario.attack_with(_arsonist(scenario))
    _drain(scenario)

    assert scenario.creature("Giant Spider", "bob").damage == 0
    assert scenario.player("bob").life == 20


def test_volatile_arsonist_with_only_a_player_chosen_hits_just_the_player():
    scenario = _arsonist_board()
    scenario.choose_trigger_targets("Volatile Arsonist", ["bob"])
    scenario.attack_with(_arsonist(scenario))
    _drain(scenario)

    assert scenario.player("bob").life == 19
    assert scenario.creature("Giant Spider", "bob").damage == 0


def test_volatile_arsonist_can_hit_its_own_controller_and_own_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Volatile Arsonist // Dire-Strain Anarchist", "Giant Spider"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    own = scenario.creature("Giant Spider", "alice")
    scenario.choose_trigger_targets("Volatile Arsonist", [own, "alice"])
    scenario.attack_with(_arsonist(scenario))
    _drain(scenario)

    assert own.damage == 1 and scenario.player("alice").life == 19


def test_volatile_arsonist_target_gone_on_resolution_leaves_the_others_hit():
    """CR 608.2b: an illegal target is skipped; the rest still take damage."""
    scenario = _arsonist_board()
    spider = scenario.creature("Giant Spider", "bob")
    scenario.choose_trigger_targets("Volatile Arsonist", [spider, "bob"])
    scenario.attack_with(_arsonist(scenario))
    scenario.game.put_triggers_on_stack()
    scenario.game.return_to_hand(spider)
    scenario.resolve_top()

    assert scenario.player("bob").life == 19


def test_volatile_arsonist_cannot_pick_two_creatures_for_its_one_creature_slot():
    scenario = _arsonist_board(theirs=("Giant Spider", "Hill Giant"))
    spider = scenario.creature("Giant Spider", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Volatile Arsonist", [spider, giant])


def test_volatile_arsonist_slots_are_three_optional_ones():
    profile = profile_for_text(
        "it deals 1 damage to each of up to one target creature, up to one target player, "
        "and/or up to one target planeswalker."
    )
    assert [r.minimum for r in profile.requirements] == [0, 0, 0]
    assert [r.count for r in profile.requirements] == [1, 1, 1]


def test_volatile_arsonist_both_faces_read_handled():
    assert set(_outcomes("Volatile Arsonist // Dire-Strain Anarchist")) == {"handled"}


# -- a sentence's own condition is never swallowed, and "other" needs a dealer -


@pytest.mark.parametrize(
    "text",
    [
        "it deals 1 damage to each other creature if the moon is full.",
        "it deals 1 damage to each creature defending player controls unless you control a Dragon.",
        "it deals 1 damage to defending player if the moon is full.",
        "it deals 1 damage to each of up to one target creature, up to one target player, "
        "and/or up to one target planeswalker if the moon is full.",
        "it deals 1 damage to each opponent and 1 damage to you if the moon is full.",
    ],
)
def test_a_trailing_condition_is_not_dropped_by_the_new_readers(text):
    """The new readers refuse a sentence carrying an "if"/"unless" rather than
    deal its damage unconditionally."""
    assert trigger_effect_for("Some Card", TriggerEvent.ATTACKS, text) is None


def test_an_equipments_each_other_creature_is_not_read_as_other_than_the_equipment():
    """Kusari-Gama's "this Equipment deals that much damage to each other
    creature defending player controls": "other" means other than the blocking
    creature the sentence before it named, which this reader cannot know, so it
    stays unread instead of hitting that creature too."""
    text = "this Equipment deals that much damage to each other creature defending player controls."
    assert trigger_effect_for("Some Card", TriggerEvent.DEALS_DAMAGE, text) is None


def test_a_printed_name_never_reads_an_event_referent():
    """A spell's "<name> deals 2 damage to defending player" has no trigger
    event to name a player; only an ability's own "it"/"this <noun>" does."""
    text = "Another Card deals 1 damage to each creature defending player controls."
    assert trigger_effect_for("Some Card", TriggerEvent.ATTACKS, text) is None

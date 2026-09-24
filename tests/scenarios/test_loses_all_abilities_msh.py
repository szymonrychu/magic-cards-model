"""Losing all abilities and being locked tapped, from an Aura's static
ability and from an enters trigger with a "for as long as" duration.

- Frozen in Ice: "When this Aura enters, tap enchanted creature. / Enchanted
  creature loses all abilities and can't become untapped." Layer 6 removes
  the abilities (CR 613.1f). "Can't become untapped" is not an ability the
  creature has - it stops every untap, the untap step's (CR 502.3) and an
  effect's alike, and a later "loses all abilities" does not end it.
- The Wondrous Wasp: "When The Wondrous Wasp enters, tap up to one target
  creature. It loses all abilities for as long as The Wondrous Wasp remains
  on the battlefield." CR 611.2b: the duration ends when the Wasp leaves.
- Spider-Woman, Secret Agent: "When Spider-Woman enters, tap target creature
  an opponent controls. That creature can't become untapped for as long as
  you control Spider-Woman."

Off-set proofs (legal, in no deck list):

- Dungeon Geists: "When this creature enters, tap target creature an
  opponent controls. That creature doesn't untap during its controller's
  untap step for as long as you control this creature." - the same reader
  with the untap-step-only rider.
- Ty Lee, Chi Blocker: "... tap up to one target creature. It doesn't untap
  during its controller's untap step for as long as you control Ty Lee." -
  "up to one", the pronoun "It", the card's own name.
- Kenrith's Transformation: "Enchanted creature loses all abilities and is a
  green Elk creature with base power and toughness 3/3." - the Aura's static
  loss of abilities on another printing.

"Can't become untapped" and "loses all abilities" each print only on
Marvel Super Heroes cards in their untap-lock form; Frozen in Ice and
Spider-Woman are two wordings of the same lock.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _next_turn_of(scenario, username):
    """Walk on until `username`'s next turn is past its untap step."""
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns or scenario.turn.active_player != username:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
    scenario.start_at(Step.UPKEEP)


# -- Frozen in Ice ---------------------------------------------------------------


def _frozen(scenario, creature):
    scenario.choose_trigger_targets("Frozen in Ice", [])
    casting = scenario.cast("Frozen in Ice", username="alice", targets=[creature])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()  # the Aura
    scenario.pass_until_resolved()  # its enters trigger


def test_frozen_in_ice_taps_and_strips_every_ability():
    scenario = (
        Scenario()
        .player("alice", hand=["Frozen in Ice"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _frozen(scenario, angel)

    assert angel.tapped
    chars = _chars(scenario, angel)
    assert "Flying" not in chars.abilities
    assert "Vigilance" not in chars.abilities


def test_frozen_in_ice_keeps_it_tapped_through_its_controllers_untap_step():
    scenario = (
        Scenario()
        .player("alice", hand=["Frozen in Ice"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _frozen(scenario, angel)

    _next_turn_of(scenario, "bob")

    assert angel.tapped


def test_frozen_in_ice_stops_an_effect_untapping_it_too():
    """ "Can't become untapped" is wider than "doesn't untap during its
    controller's untap step": an untap effect does nothing either."""
    scenario = (
        Scenario()
        .player("alice", hand=["Frozen in Ice"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _frozen(scenario, angel)

    angel.untap()

    assert angel.tapped


def test_frozen_in_ice_leaving_frees_the_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Frozen in Ice"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _frozen(scenario, angel)
    aura = scenario.find("Frozen in Ice", Zone.BATTLEFIELD, "alice")

    scenario.game.destroy(aura)
    _next_turn_of(scenario, "bob")

    assert not angel.tapped
    assert "Flying" in _chars(scenario, angel).abilities


def test_the_untap_lock_is_not_an_ability_a_later_loss_can_remove():
    """Humility makes every creature lose all abilities; the frozen creature
    still can't become untapped - the lock is an effect on it, not one of its
    abilities."""
    scenario = (
        Scenario()
        .player("alice", hand=["Frozen in Ice", "Humility"], battlefield=["Island"] * 3)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _frozen(scenario, angel)
    scenario.put_onto_battlefield("Humility", "alice")

    angel.untap()

    assert angel.tapped


# -- Kenrith's Transformation (off-set proof) ------------------------------------


def test_kenriths_transformation_makes_a_vanilla_three_three_elk():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kenrith's Transformation"],
            battlefield=["Forest", "Forest"],
            library=["Forest"],
        )
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Kenrith's Transformation",
        *scenario.untapped_sources("Forest", "Forest"),
        targets=[angel],
    )
    scenario.pass_until_resolved()  # draw a card

    chars = _chars(scenario, angel)
    assert chars.abilities == ()
    assert chars.subtypes == ("Elk",)
    assert chars.power_toughness == (3, 3)


# -- The Wondrous Wasp ---------------------------------------------------------------


def _wasp(scenario, target):
    scenario.choose_trigger_targets("The Wondrous Wasp", [target] if target else [])
    wasp = scenario.put_onto_battlefield("The Wondrous Wasp", "alice")
    scenario.pass_until_resolved()
    return wasp


def test_the_wondrous_wasp_taps_and_silences_its_target():
    scenario = (
        Scenario()
        .player("alice", hand=["The Wondrous Wasp"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _wasp(scenario, angel)

    assert angel.tapped
    assert "Flying" not in _chars(scenario, angel).abilities


def test_the_wondrous_wasp_leaving_gives_the_abilities_back():
    scenario = (
        Scenario()
        .player("alice", hand=["The Wondrous Wasp"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    wasp = _wasp(scenario, angel)

    scenario.game.destroy(wasp)

    assert "Flying" in _chars(scenario, angel).abilities


def test_the_wondrous_wasp_leaving_before_resolution_means_no_loss():
    """CR 611.2b: a "for as long as" duration that never starts does
    nothing - the tap still happens, the ability loss does not."""
    scenario = (
        Scenario()
        .player("alice", hand=["The Wondrous Wasp"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("The Wondrous Wasp", [angel])
    wasp = scenario.put_onto_battlefield("The Wondrous Wasp", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(wasp)
    scenario.pass_until_resolved()

    assert angel.tapped
    assert "Flying" in _chars(scenario, angel).abilities


def test_the_wondrous_wasp_may_target_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["The Wondrous Wasp"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _wasp(scenario, None)

    assert not angel.tapped
    assert "Flying" in _chars(scenario, angel).abilities


def test_the_silenced_creature_that_left_and_returned_is_a_new_object():
    """CR 400.7: the loss followed the creature it hit, not the card."""
    scenario = (
        Scenario()
        .player("alice", hand=["The Wondrous Wasp"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    _wasp(scenario, angel)

    scenario.game.return_to_hand(angel)
    returned = scenario.put_onto_battlefield("Serra Angel", "bob")

    assert "Flying" in _chars(scenario, returned).abilities


# -- Spider-Woman, Secret Agent ------------------------------------------------------


def _spider_woman(scenario, target):
    scenario.choose_trigger_targets("Spider-Woman, Secret Agent", [target])
    woman = scenario.put_onto_battlefield("Spider-Woman, Secret Agent", "alice")
    scenario.pass_until_resolved()
    return woman


def test_spider_woman_locks_the_creature_tapped_while_she_is_controlled():
    scenario = (
        Scenario()
        .player("alice", hand=["Spider-Woman, Secret Agent"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _spider_woman(scenario, angel)
    _next_turn_of(scenario, "bob")

    assert angel.tapped
    angel.untap()
    assert angel.tapped


def test_spider_woman_leaving_ends_the_lock():
    scenario = (
        Scenario()
        .player("alice", hand=["Spider-Woman, Secret Agent"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    woman = _spider_woman(scenario, angel)

    scenario.game.destroy(woman)
    _next_turn_of(scenario, "bob")

    assert not angel.tapped


# -- Dungeon Geists / Ty Lee (off-set proofs) ---------------------------------------


def test_dungeon_geists_keeps_it_tapped_only_through_the_untap_step():
    """ "Doesn't untap during its controller's untap step" is narrower: an
    untap effect still untaps it."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dungeon Geists"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Dungeon Geists", [angel])
    scenario.put_onto_battlefield("Dungeon Geists", "alice")
    scenario.pass_until_resolved()

    _next_turn_of(scenario, "bob")
    assert angel.tapped

    angel.untap()
    assert not angel.tapped


def test_dungeon_geists_changing_control_ends_the_lock():
    """ "For as long as you control this creature" - control lost is the
    duration over (CR 611.2b)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dungeon Geists"], library=["Island"] * 5)
        .player(
            "bob",
            hand=["Act of Treason"],
            battlefield=["Serra Angel"] + ["Mountain"] * 3,
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Dungeon Geists", [angel])
    geists = scenario.put_onto_battlefield("Dungeon Geists", "alice")
    scenario.pass_until_resolved()

    _next_turn_of(scenario, "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Act of Treason",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", username="bob"),
        username="bob",
        targets=[geists],
    )
    _next_turn_of(scenario, "alice")
    _next_turn_of(scenario, "bob")

    assert not angel.tapped


def test_ty_lee_may_lock_up_to_one_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Ty Lee, Chi Blocker"], library=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    scenario.choose_trigger_targets("Ty Lee, Chi Blocker", [angel])
    scenario.put_onto_battlefield("Ty Lee, Chi Blocker", "alice")
    scenario.pass_until_resolved()

    _next_turn_of(scenario, "bob")

    assert angel.tapped

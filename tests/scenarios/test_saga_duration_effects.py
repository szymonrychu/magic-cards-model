"""Chapter effects that last "for as long as this Saga remains on the
battlefield" (CR 611.2b) - Old Fat Spider Can't See Me:

- I - "Target creature you control gains hexproof for as long as this Saga
  remains on the battlefield." (a layer 6 grant, CR 613.1f);
- II - "Prevent all damage that would be dealt by up to one target creature
  for as long as this Saga remains on the battlefield." (a prevention effect,
  CR 615.1a, keyed to one source).

CR 611.2b: the duration ends when the Saga leaves - including when it is put
into its owner's graveyard after its last chapter (CR 714.4) - and if it has
already left before the chapter ability resolves, the duration never starts
and the effect does nothing. A creature that changes zones is a new object
(CR 400.7) the effect never applied to.

Off-set proofs, not in any deck list:

- Aegis Angel: "When this creature enters, another target permanent gains
  indestructible for as long as you control this creature." - the same
  keyword-grant reader with the other "for as long as" duration.
- Boros Fury-Shield: "Prevent all combat damage that would be dealt by target
  attacking or blocking creature this turn. If {R} was spent to cast this
  spell, Boros Fury-Shield deals damage to that creature's controller equal
  to the creature's power." - the same source-keyed prevention reader, combat
  damage only and "this turn" (CR 514.2).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

SPIDER = "Old Fat Spider Can't See Me"


def _abilities(scenario, permanent):
    return scenario.game.computed_board().of(permanent).abilities


def _cast_spider(scenario, target):
    scenario.choose_trigger_targets(SPIDER, [target] if target is not None else [])
    scenario.cast_and_resolve(
        SPIDER, *scenario.untapped_sources("Island", "Island", "Island", username="alice")
    )
    scenario.pass_until_resolved()  # chapter I
    return scenario.find(SPIDER, Zone.BATTLEFIELD, "alice")


def _chapter_two(scenario, target):
    scenario.choose_trigger_targets(SPIDER, [target] if target is not None else [])
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _board(*, alice=(), bob=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[SPIDER],
            battlefield=["Island", "Island", "Island", *alice],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )


# -- Chapter I: hexproof for as long as the Saga remains --------------------


def test_chapter_one_grants_hexproof_while_the_saga_remains():
    scenario = _board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _cast_spider(scenario, bears)

    assert "Hexproof" in _abilities(scenario, bears)


def test_hexproof_survives_the_turn_but_not_the_saga():
    scenario = _board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    saga = _cast_spider(scenario, bears)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2) - not an "until end of turn" effect
    assert "Hexproof" in _abilities(scenario, bears)

    scenario.game.destroy(saga)
    assert saga.zone is Zone.GRAVEYARD
    assert "Hexproof" not in _abilities(scenario, bears)


def test_hexproof_ends_when_the_saga_is_put_into_the_graveyard_after_chapter_four():
    scenario = _board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    saga = _cast_spider(scenario, bears)

    for _ in range(3):
        scenario.choose_trigger_targets(SPIDER, [])
        scenario.game.saga_lore_step()
        scenario.game.put_triggers_on_stack()
        while scenario.game.stack:
            scenario.resolve_top()

    assert saga.zone is Zone.GRAVEYARD  # CR 714.4
    assert "Hexproof" not in _abilities(scenario, bears)


def test_a_saga_gone_before_chapter_one_resolves_grants_nothing():
    """CR 611.2b: "If the 'for as long as' duration never starts, the effect
    does nothing." The Saga is destroyed with chapter I still on the stack."""
    scenario = _board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets(SPIDER, [bears])
    scenario.cast_and_resolve(
        SPIDER, *scenario.untapped_sources("Island", "Island", "Island", username="alice")
    )
    saga = scenario.find(SPIDER, Zone.BATTLEFIELD, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.game.stack

    scenario.game.destroy(saga)
    scenario.resolve_top()

    assert "Hexproof" not in _abilities(scenario, bears)


def test_a_creature_that_left_and_came_back_is_a_new_object_without_hexproof():
    scenario = _board(alice=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_spider(scenario, bears)

    scenario.game.return_to_hand(bears)
    returned = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert "Hexproof" not in _abilities(scenario, returned)


# -- Chapter II: prevent all damage dealt by one creature -------------------


def test_chapter_two_prevents_all_damage_the_target_would_deal():
    scenario = _board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_spider(scenario, None)

    _chapter_two(scenario, giant)
    dealt = scenario.game.deal_damage(scenario.player("alice"), 3, source=giant)

    assert dealt == 0
    assert scenario.player("alice").life == 20


def test_chapter_two_prevents_combat_and_noncombat_damage_alike_but_not_damage_to_it():
    scenario = _board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_spider(scenario, None)
    _chapter_two(scenario, giant)

    assert scenario.game.deal_damage(bears, 3, source=giant) == 0
    assert bears.damage == 0
    # Damage dealt *to* the giant is not prevented - only damage it deals.
    assert scenario.game.deal_damage(giant, 2, source=bears) == 2


def test_chapter_two_leaves_other_sources_alone():
    scenario = _board(bob=["Hill Giant", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_spider(scenario, None)
    _chapter_two(scenario, giant)

    assert scenario.game.deal_damage(scenario.player("alice"), 2, source=bears) == 2


def test_chapter_two_prevention_ends_when_the_saga_leaves():
    scenario = _board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    saga = _cast_spider(scenario, None)
    _chapter_two(scenario, giant)
    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=giant) == 0

    scenario.game.destroy(saga)

    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=giant) == 3


def test_chapter_two_prevention_outlives_the_turn():
    scenario = _board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_spider(scenario, None)
    _chapter_two(scenario, giant)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=giant) == 0


def test_chapter_two_does_not_follow_the_creature_to_a_new_object():
    scenario = _board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_spider(scenario, None)
    _chapter_two(scenario, giant)

    scenario.game.return_to_hand(giant)
    returned = scenario.put_onto_battlefield("Hill Giant", "bob")

    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=returned) == 3


def test_chapter_two_with_no_target_chosen_prevents_nothing():
    """ "up to one" (CR 115.6)."""
    scenario = _board(bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    saga = _cast_spider(scenario, None)
    _chapter_two(scenario, None)

    assert saga.counters[Counter.LORE] == 2
    assert scenario.game.deal_damage(scenario.player("alice"), 3, source=giant) == 3


# -- Aegis Angel (off-set proof, "for as long as you control this creature") -


def test_aegis_angel_grants_indestructible_while_its_controller_keeps_it():
    scenario = (
        Scenario()
        .player("alice", hand=["Aegis Angel"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.choose_trigger_targets("Aegis Angel", [bears])
    angel = scenario.put_onto_battlefield("Aegis Angel", "alice")
    scenario.pass_until_resolved()

    assert "Indestructible" in _abilities(scenario, bears)
    scenario.game.destroy(bears)
    assert bears.zone is Zone.BATTLEFIELD

    scenario.game.destroy(angel)  # the angel itself is not indestructible
    assert angel.zone is Zone.GRAVEYARD
    assert "Indestructible" not in _abilities(scenario, bears)


def test_aegis_angel_grant_ends_when_its_controller_loses_control_of_it():
    """ "for as long as you control this creature": a control change ends it
    even though the Angel never left the battlefield - here Switcheroo
    trades the Angel for bob's Hill Giant."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aegis Angel", "Switcheroo"],
            battlefield=["Grizzly Bears", *["Island"] * 5],
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    scenario.choose_trigger_targets("Aegis Angel", [bears])
    angel = scenario.put_onto_battlefield("Aegis Angel", "alice")
    scenario.pass_until_resolved()
    assert "Indestructible" in _abilities(scenario, bears)

    scenario.cast_and_resolve(
        "Switcheroo", *scenario.untapped_sources(*["Island"] * 5), targets=[angel, giant]
    )

    assert scenario.game.controller_of(angel).username == "bob"
    assert "Indestructible" not in _abilities(scenario, bears)


# -- Boros Fury-Shield (off-set proof, combat damage this turn) --------------


def _attack_and_shield(scenario, *, red: bool):
    giant = scenario.creature("Hill Giant", "bob")
    scenario.attack_with(giant)
    scenario.pass_priority("bob")
    sources = (
        scenario.untapped_sources("Mountain", "Plains", "Plains", username="alice")
        if red
        else scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")
    )
    scenario.cast_and_resolve("Boros Fury-Shield", *sources, username="alice", targets=[giant])
    return giant


def _fury_board():
    # bob is listed first, so it is bob's turn and bob attacks alice.
    return (
        Scenario()
        .player("bob", battlefield=["Hill Giant"])
        .player(
            "alice",
            hand=["Boros Fury-Shield"],
            battlefield=["Plains", "Plains", "Plains", "Mountain"],
        )
        .build()
    )


def test_boros_fury_shield_prevents_the_attackers_combat_damage():
    scenario = _fury_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    giant = _attack_and_shield(scenario, red=False)

    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("alice").life == 20
    # Only combat damage: a noncombat hit from the same creature still lands.
    assert scenario.game.deal_damage(scenario.player("alice"), 1, source=giant) == 1


def test_boros_fury_shield_with_red_spent_also_hits_the_controller_for_its_power():
    scenario = _fury_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    _attack_and_shield(scenario, red=True)

    assert scenario.player("bob").life == 20 - 3

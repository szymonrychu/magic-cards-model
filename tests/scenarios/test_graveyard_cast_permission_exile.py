"""Permission to cast spells out of a graveyard, handed out by a resolving
ability, and the exile replacement that rides on it.

Two shapes, both read off the printed sentence:

- **one targeted card, this turn** - Jace, Telepath Unbound's -3: "You may
  cast target instant or sorcery card from your graveyard this turn. If that
  spell would be put into your graveyard, exile it instead." Second printing:
  **Vohar, Vodalian Desecrator** (Modern and Pioneer legal on Scryfall, in no
  deck list): "{2}, Sacrifice Vohar: You may cast target instant or sorcery
  card from your graveyard this turn. If that spell would be put into your
  graveyard, exile it instead. Activate only as a sorcery." - a sacrifice
  cost on a creature rather than a loyalty cost on a planeswalker.
- **every qualifying spell, until the turn ends** - The Great Work's chapter
  III: "Until end of turn, you may cast instant and sorcery spells from any
  graveyard. If a spell cast this way would be put into a graveyard, exile it
  instead." Second printing: **Liliana, Untouched by Death** (Modern and
  Pioneer legal, in no deck list): "-3: You may cast Zombie spells from your
  graveyard this turn." - a subtype rather than card types, only its
  controller's own graveyard, "this turn" at the end instead of "Until end of
  turn" at the front, and no exile rider.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 601.3** - "A player can begin to cast a spell only if a rule or effect
  allows that player to cast it and no rule or effect prohibits that player
  from casting it."
- **CR 611.2a** - a resolution's continuous effect lasts as long as stated.
- **CR 611.2c** - an effect that "doesn't modify the characteristics or
  change the controller of any objects modifies the rules of the game, so it
  can affect objects that weren't affected when that continuous effect
  began" - a card that reaches a graveyard after chapter III resolved is
  castable too.
- **CR 614.1a** - "instead" makes the exile a replacement effect.
- **CR 400.7h** - the permission can find the new object the card becomes on
  the stack, which is how "that spell" in the rider is known.
- **CR 307.1** - a sorcery cast this way still waits for its controller's
  main phase with an empty stack.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _resolve_everything(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast_from_graveyard(scenario, card, caster, *, targets=(), keyword=None):
    """Announce `card` out of whichever graveyard it is in, pay automatically
    and put it on the stack."""
    casting = Casting(spell=card, caster=caster, origin_zone=Zone.GRAVEYARD, game=scenario.game)
    if keyword is None:
        casting.use_permission()
    else:
        casting.use_keyword(keyword)
    if targets:
        casting.choose_targets(list(targets))
    scenario.auto_pay(casting.begin_paying(), username=caster)
    return scenario.put_on_stack(casting)


# -- Jace, Telepath Unbound's -3: one targeted card ------------------------


def _jace(*, graveyard=("Lightning Bolt", "Opt"), bob_graveyard=("Shock",), hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Jace, Vryn's Prodigy", *hand],
            battlefield=["Mountain"] * 3 + ["Island"] * 2,
            graveyard=list(graveyard),
            library=["Island"] * 5,
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            graveyard=list(bob_graveyard),
            library=["Mountain"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jace = scenario.find("Jace, Vryn's Prodigy", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(jace, "alice", transformed=True)
    assert jace.name == "Jace, Telepath Unbound"
    return scenario, jace


def _minus_three(scenario, jace, target):
    scenario.activate(jace, index=1, username="alice", targets=[target])
    scenario.pass_until_resolved()


def test_the_targeted_instant_can_be_cast_and_is_exiled_after_it_resolves():
    scenario, jace = _jace()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _minus_three(scenario, jace, bolt)
    assert jace.counters[Counter.LOYALTY] == 2

    bolt = _cast_from_graveyard(scenario, bolt, "alice", targets=[scenario.player("bob")])
    scenario.resolve_top()

    assert scenario.player("bob").life == 17
    assert bolt.zone is Zone.EXILE


def test_the_rider_exiles_the_spell_when_it_is_countered_by_the_rules_too():
    """ "Would be put into your graveyard" is not only resolution: a spell
    whose only target is gone is removed from the stack (CR 608.2b) and is
    exiled all the same."""
    scenario, jace = _jace()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _minus_three(scenario, jace, bolt)
    bears = scenario.creature("Grizzly Bears", "bob")

    bolt = _cast_from_graveyard(scenario, bolt, "alice", targets=[bears])
    scenario.game.destroy(bears)
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE


def test_only_the_targeted_card_is_castable():
    scenario, jace = _jace()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    _minus_three(scenario, jace, bolt)

    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, opt, "alice")
    assert opt.zone is Zone.GRAVEYARD


def test_the_permission_ends_with_the_turn():
    scenario, jace = _jace()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _minus_three(scenario, jace, bolt)
    while scenario.game.turn.active_player == "alice":
        scenario.advance()

    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, bolt, "alice", targets=[scenario.player("bob")])
    assert bolt.zone is Zone.GRAVEYARD


def test_the_target_must_be_an_instant_or_sorcery_card_in_your_own_graveyard():
    scenario, jace = _jace(graveyard=("Grizzly Bears",), bob_graveyard=("Shock",))
    with pytest.raises(ValueError):
        _minus_three(scenario, jace, scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice"))
    with pytest.raises(ValueError):
        _minus_three(scenario, jace, scenario.find("Shock", Zone.GRAVEYARD, "bob"))


def test_a_second_copy_cast_from_hand_goes_to_the_graveyard_as_usual():
    """The rider is about "that spell" - the one cast this way (CR 400.7h) -
    not about every spell with that name."""
    scenario, jace = _jace(graveyard=("Lightning Bolt",), hand=("Lightning Bolt",))
    in_graveyard = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    _minus_three(scenario, jace, in_graveyard)

    from_hand = scenario.cast_and_resolve(
        "Lightning Bolt", auto=True, targets=[scenario.player("bob")]
    )
    recast = _cast_from_graveyard(scenario, in_graveyard, "alice", targets=[scenario.player("bob")])
    scenario.resolve_top()

    assert from_hand.zone is Zone.GRAVEYARD
    assert recast.zone is Zone.EXILE
    assert scenario.player("bob").life == 14


# -- Vohar, Vodalian Desecrator: the same grant on a sacrifice ability -----


def test_vohars_sacrifice_grants_the_same_permission_and_rider():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Vohar, Vodalian Desecrator"] + ["Swamp"] * 5,
            graveyard=["Lightning Bolt", "Mind Rot"],
            library=["Swamp"] * 5,
        )
        .player("bob", hand=["Island", "Island"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vohar = scenario.find("Vohar, Vodalian Desecrator", Zone.BATTLEFIELD, "alice")
    rot = scenario.find("Mind Rot", Zone.GRAVEYARD, "alice")
    swamps = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.activate(vohar, *swamps, index=1, username="alice", targets=[rot])
    scenario.pass_until_resolved()
    assert vohar.zone is Zone.GRAVEYARD

    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, bolt, "alice", targets=[scenario.player("bob")])

    rot = _cast_from_graveyard(scenario, rot, "alice", targets=[scenario.player("bob")])
    scenario.resolve_top()
    assert rot.zone is Zone.EXILE
    assert len(scenario.player("bob").hand) == 0


# -- The Great Work III: every instant and sorcery, any graveyard, this turn


def _great_work_at_chapter_three(*, alice_graveyard=("Opt",), bob_graveyard=("Lightning Bolt",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Urabrask", "Shock"],
            battlefield=["Mountain"] * 4 + ["Island"] * 2,
            graveyard=list(alice_graveyard),
            library=["Island"] * 6,
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears"],
            graveyard=list(bob_graveyard) + ["Watchwolf"],
            library=["Mountain"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    urabrask = scenario.find("Urabrask", Zone.HAND, "alice")
    scenario.game.put_onto_battlefield(urabrask, "alice", transformed=True)
    scenario.choose_trigger_targets("The Great Work", [scenario.player("bob")])
    _resolve_everything(scenario)
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)
    scenario.game.saga_lore_step()
    _resolve_everything(scenario)
    return scenario, urabrask


def test_chapter_three_returns_urabrask_front_face_up():
    scenario, urabrask = _great_work_at_chapter_three()
    assert urabrask.zone is Zone.BATTLEFIELD
    assert urabrask.name == "Urabrask"
    assert urabrask.transformed is False


def test_an_opponents_instant_can_be_cast_and_is_exiled():
    """The returned Urabrask pings for every instant or sorcery cast, so bob
    takes chapter I's 3, the Bolt's 3 and Urabrask's 1."""
    scenario, _ = _great_work_at_chapter_three()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    bolt = _cast_from_graveyard(
        scenario, bolt, "alice", targets=[scenario.player("bob")], keyword=CAST_PERMISSION
    )
    _resolve_everything(scenario)

    assert bolt.zone is Zone.EXILE
    assert bolt.owner == "bob"
    assert scenario.player("bob").life == 20 - 3 - 3 - 1


def test_the_casters_own_graveyard_is_open_too():
    scenario, _ = _great_work_at_chapter_three()
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    opt = _cast_from_graveyard(scenario, opt, "alice", keyword=CAST_PERMISSION)
    _resolve_everything(scenario)
    assert opt.zone is Zone.EXILE


def test_a_creature_card_in_a_graveyard_is_not_covered():
    scenario, _ = _great_work_at_chapter_three()
    wolf = scenario.find("Watchwolf", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, wolf, "alice", keyword=CAST_PERMISSION)


def test_a_card_that_reaches_the_graveyard_afterwards_is_castable_too():
    """CR 611.2c: a rules-modifying effect reaches objects that were not
    there when it began - Shock cast from hand after chapter III goes to the
    graveyard normally (it was not cast "this way") and can then be recast."""
    scenario, _ = _great_work_at_chapter_three(bob_graveyard=())
    shock = scenario.cast_onto_stack("Shock", auto=True, targets=[scenario.player("bob")])
    _resolve_everything(scenario)
    assert shock.zone is Zone.GRAVEYARD

    shock = _cast_from_graveyard(
        scenario, shock, "alice", targets=[scenario.player("bob")], keyword=CAST_PERMISSION
    )
    _resolve_everything(scenario)

    # Chapter I's 3, then Shock's 2 and Urabrask's 1, twice.
    assert scenario.player("bob").life == 20 - 3 - (2 + 1) * 2
    assert shock.zone is Zone.EXILE


def test_the_opponent_gets_no_permission_from_it():
    scenario, _ = _great_work_at_chapter_three()
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, bolt, "bob", keyword=CAST_PERMISSION)


def test_the_permission_is_gone_next_turn():
    scenario, _ = _great_work_at_chapter_three()
    scenario.game.automatic_turn_based_actions = True
    while scenario.game.turn.active_player == "alice":
        scenario.advance()
    while scenario.game.turn.active_player != "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opt = scenario.find("Opt", Zone.GRAVEYARD, "alice")
    with pytest.raises(ValueError):
        _cast_from_graveyard(scenario, opt, "alice", keyword=CAST_PERMISSION)


# -- Liliana, Untouched by Death's -3: a subtype, your graveyard, no rider --


def _liliana():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Liliana, Untouched by Death", "Swamp", "Swamp"],
            graveyard=["Carrion Feeder", "Grizzly Bears"],
            library=["Swamp"] * 5,
        )
        .player("bob", graveyard=["Rank Rat"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana, Untouched by Death", Zone.BATTLEFIELD, "alice")
    scenario.activate(liliana, index=2, username="alice")
    scenario.pass_until_resolved()
    return scenario, liliana


def test_liliana_lets_a_zombie_be_cast_from_her_controllers_graveyard():
    scenario, _ = _liliana()
    feeder = scenario.find("Carrion Feeder", Zone.GRAVEYARD, "alice")
    feeder = _cast_from_graveyard(scenario, feeder, "alice", keyword=CAST_PERMISSION)
    scenario.resolve_top()
    assert feeder.zone is Zone.BATTLEFIELD


def test_liliana_has_no_exile_rider_so_the_zombie_dies_to_the_graveyard():
    scenario, _ = _liliana()
    feeder = scenario.find("Carrion Feeder", Zone.GRAVEYARD, "alice")
    feeder = _cast_from_graveyard(scenario, feeder, "alice", keyword=CAST_PERMISSION)
    scenario.resolve_top()
    scenario.game.destroy(feeder)
    assert feeder.zone is Zone.GRAVEYARD


def test_liliana_reaches_neither_a_non_zombie_nor_an_opponents_graveyard():
    scenario, _ = _liliana()
    with pytest.raises(ValueError):
        _cast_from_graveyard(
            scenario,
            scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice"),
            "alice",
            keyword=CAST_PERMISSION,
        )
    with pytest.raises(ValueError):
        _cast_from_graveyard(
            scenario,
            scenario.find("Rank Rat", Zone.GRAVEYARD, "bob"),
            "alice",
            keyword=CAST_PERMISSION,
        )

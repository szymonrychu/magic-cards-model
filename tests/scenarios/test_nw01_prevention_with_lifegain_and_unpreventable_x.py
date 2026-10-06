"""Scenario: a resolving spell's turn-long prevention of damage dealt by a
group of sources, with CR 615.5's life-gain rider, and damage that can't be
prevented once X is big enough.

Rules, each read in full with `mise run rules:find`:

- CR 615.1a - "Effects that use the word "prevent" are prevention effects.
  Prevention effects use "prevent" to indicate what damage will not be dealt."
- CR 615.5 - "Some prevention effects also include an additional effect,
  which may refer to the amount of damage that was prevented. The prevention
  takes place at the time the original event would have happened; the rest of
  the effect takes place immediately afterward."
- CR 609.7b - "Some effects from resolved spells and abilities prevent or
  replace damage from sources with certain properties, such as a creature or a
  source of a particular color. When the source would deal damage, the
  "shield" rechecks the source's properties."
- CR 615.12 - "Some effects state that damage "can't be prevented." If
  unpreventable damage would be dealt, any applicable prevention effects are
  still applied to it. Those effects won't prevent any damage, but any
  additional effects they have will take place."
- CR 702.51a - convoke.
- CR 107.3a - "While a spell is on the stack, any X in its mana cost ...
  equals the announced value."
- CR 113.6g - "An object's ability that states it can't be countered or can't
  be copied functions on the stack."

Printings: Chant of Vitu-Ghazi (listed: convoke, prevention by creatures,
life gained), Ethereal Haze (proof: the same prevention with no rider),
Banefire (listed: "If X is 5 or more, this spell can't be countered and the
damage can't be prevented."), Demonfire (proof: the same line behind a
hellbent condition, CR 207.2c's ability word).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import convoke
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import Color
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _outcomes(name):
    return {clause.outcome for clause in card_support(card(name)).clauses}


def test_every_listed_and_proof_card_is_handled():
    for name in ("Chant of Vitu-Ghazi", "Ethereal Haze", "Banefire", "Demonfire"):
        assert _outcomes(name) == {"handled"}, name


# -- Chant of Vitu-Ghazi ------------------------------------------------------


def _chant_board(**alice):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chant of Vitu-Ghazi", *alice.get("hand", [])],
            battlefield=["Plains"] * 8 + alice.get("battlefield", []),
            library=["Plains"] * 5,
        )
        .player(
            "bob",
            hand=alice.get("bob_hand", []),
            battlefield=alice.get("bob_battlefield", ["Grizzly Bears", "Hill Giant"]),
            library=["Island"] * 5,
        )
        .build()
    )
    return scenario


def _cast_chant(scenario):
    plains = scenario.untapped_sources(*["Plains"] * 8, username="alice")
    return scenario.cast_and_resolve("Chant of Vitu-Ghazi", *plains, username="alice")


def test_chant_prevents_combat_damage_by_creatures_and_gains_that_much_life():
    scenario = _chant_board(battlefield=["Savannah Lions"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_chant(scenario)
    lions = scenario.creature("Savannah Lions", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(lions, defending="bob")
    scenario.block(lions, bears)
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert lions.damage == 0 and bears.damage == 0
    # Lions' 2 and Bears' 2 were both prevented this way (CR 615.5).
    assert scenario.player("alice").life == 24


def test_chant_does_not_prevent_damage_from_a_noncreature_source():
    scenario = _chant_board(hand=["Lightning Bolt"], battlefield=["Mountain"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_chant(scenario)
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_chant_prevents_noncombat_damage_dealt_by_a_creature():
    """ "by creatures" - any damage a creature deals, not combat damage only."""
    scenario = _chant_board(battlefield=["Mogg Fanatic"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_chant(scenario)
    fanatic = scenario.creature("Mogg Fanatic", "alice")

    scenario.activate(fanatic, sacrificing=[fanatic], targets=["bob"])
    scenario.resolve_top()

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 21


def test_chant_is_cast_with_convoke():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Chant of Vitu-Ghazi"],
            battlefield=["Plains"] * 4 + ["Savannah Lions"] * 2 + ["Grizzly Bears"] * 2,
            library=["Plains"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lions = scenario.creatures("Savannah Lions", "Savannah Lions", username="alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    casting = scenario.cast("Chant of Vitu-Ghazi")
    payment = casting.begin_paying()
    convoke(payment, casting.spell, lions[0], Color.WHITE)
    convoke(payment, casting.spell, lions[1], Color.WHITE)
    convoke(payment, casting.spell, bears[0])
    convoke(payment, casting.spell, bears[1])
    scenario.pay_with(payment, *scenario.untapped_sources(*["Plains"] * 4))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert all(creature.tapped for creature in [*lions, *bears])
    assert len(scenario.game.created_replacements) == 1


def test_chant_ends_at_cleanup():
    scenario = _chant_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_chant(scenario)
    assert scenario.game.created_replacements

    active = scenario.turn.active_player
    while scenario.turn.active_player == active:
        scenario.advance()

    assert scenario.game.created_replacements == []


def test_chant_against_damage_that_cannot_be_prevented_gains_nothing():
    """CR 615.12: the prevention effect still applies, prevents nothing, so
    "the damage prevented this way" is 0 and no life is gained."""
    scenario = _chant_board(battlefield=["Savannah Lions", "Leyline of Punishment"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_chant(scenario)
    lions = scenario.creature("Savannah Lions", "alice")

    scenario.attack_with(lions, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_ethereal_haze_prevents_damage_by_creatures_with_no_life_gain():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ethereal Haze"],
            battlefield=["Plains", "Savannah Lions"],
            library=["Plains"] * 5,
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve("Ethereal Haze", plains)
    lions = scenario.creature("Savannah Lions", "alice")

    scenario.attack_with(lions, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20


# -- Banefire: X is 5 or more ---------------------------------------------------


def _banefire_board(lands, *, bob_hand=(), bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=["Banefire"], battlefield=lands, library=["Mountain"] * 5)
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_banefire(scenario, x, target):
    return scenario.game.cast(
        scenario.find("Banefire", Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=[target],
        mana_sources=scenario.untapped_sources(*["Mountain"] * (x + 1)),
    )


def _counter(scenario, spell):
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Counterspell",
        *scenario.untapped_sources("Island", "Island", username="bob"),
        username="bob",
        targets=[spell],
    )


def test_banefire_x_below_five_can_be_countered():
    scenario = _banefire_board(
        ["Mountain"] * 4, bob_hand=["Counterspell"], bob_battlefield=["Island", "Island"]
    )
    spell = _cast_banefire(scenario, 3, "bob")
    _counter(scenario, spell)

    assert spell.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_banefire_x_five_cannot_be_countered():
    scenario = _banefire_board(
        ["Mountain"] * 6, bob_hand=["Counterspell"], bob_battlefield=["Island", "Island"]
    )
    spell = _cast_banefire(scenario, 5, "bob")
    _counter(scenario, spell)

    assert spell.zone is Zone.STACK
    scenario.resolve_top()
    assert scenario.player("bob").life == 15


def test_banefire_x_below_five_damage_is_prevented():
    scenario = _banefire_board(["Mountain"] * 4, bob_battlefield=["Purity"])

    _cast_banefire(scenario, 3, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 23  # prevented, and Purity's rider


def test_banefire_x_five_damage_cannot_be_prevented():
    """CR 615.12: Purity still applies, prevents nothing, so its "gain life
    equal to the damage prevented this way" gains nothing."""
    scenario = _banefire_board(["Mountain"] * 6, bob_battlefield=["Purity"])

    _cast_banefire(scenario, 5, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 15


# -- Demonfire: the same line behind a different condition -------------------


def _demonfire_board(*, hand=(), bob_battlefield=("Purity",), bob_hand=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Demonfire", *hand],
            battlefield=["Mountain"] * 4,
            library=["Mountain"] * 5,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=list(bob_battlefield),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_demonfire(scenario, x, target):
    return scenario.game.cast(
        scenario.find("Demonfire", Zone.HAND, "alice"),
        "alice",
        x_value=x,
        targets=[target],
        mana_sources=scenario.untapped_sources(*["Mountain"] * (x + 1)),
    )


def test_demonfire_hellbent_damage_cannot_be_prevented():
    scenario = _demonfire_board()

    _cast_demonfire(scenario, 3, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_demonfire_with_a_card_in_hand_is_prevented():
    scenario = _demonfire_board(hand=["Mountain"])

    _cast_demonfire(scenario, 3, "bob")
    scenario.resolve_top()

    assert scenario.player("bob").life == 23


def test_demonfire_hellbent_cannot_be_countered():
    scenario = _demonfire_board(bob_battlefield=["Island", "Island"], bob_hand=["Counterspell"])
    spell = _cast_demonfire(scenario, 2, "bob")
    _counter(scenario, spell)

    assert spell.zone is Zone.STACK


def test_demonfire_exiles_a_creature_it_kills():
    scenario = _demonfire_board(bob_battlefield=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_demonfire(scenario, 2, bears)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert bears.zone is Zone.EXILE


# -- Finale of Eternity: "If X is 10 or more" read by the same condition reader --


def _finale(x):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Finale of Eternity"],
            graveyard=["Serra Angel"],
            battlefield=["Swamp"] * (x + 2),
            library=["Swamp"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Finale of Eternity")
    casting.x_value = x  # CR 601.2b: X is announced before targets (CR 601.2c)
    casting.choose_targets([bears])
    payment = casting.determine_cost(x_value=x)
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * (x + 2)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    scenario.state_based_actions()
    return scenario, bears


def test_finale_of_eternity_x_below_ten_only_destroys():
    scenario, bears = _finale(2)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Serra Angel", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_finale_of_eternity_x_ten_also_returns_creature_cards():
    scenario, bears = _finale(10)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.creature("Serra Angel", "alice").zone is Zone.BATTLEFIELD

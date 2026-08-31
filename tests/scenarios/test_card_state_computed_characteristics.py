"""Scenario: what `CardState.power` and `.toughness` answer, and who asks.

`CardState` is one physical card in a game, and on its own it can only report
what is printed on the face that is up plus what its own counters do to it
(CR 122.1a: "A +X/+Y counter on a creature or on a creature card in a zone
other than the battlefield, where X and Y are numbers, adds X to that object's
power and Y to that object's toughness"). That is not what the rules mean by a
creature's power - CR 302.4c is: "To determine a creature's power and
toughness, start with the numbers printed in its lower right corner, then apply
any applicable continuous effects."
CR 613.5: "The application of continuous effects as described by the layer
system is continually and automatically performed by the game. All resulting
changes to an object's characteristics are instantaneous." The engine's layer
system is `machines/layers.py`, and `Game.characteristics_of` is what runs it.

Two of the numbers that matter most are read straight off a `CardState` rather
than off the game: combat damage is assigned equal to a creature's power
(CR 510.1a), and CR 704.5g's lethal damage compares marked damage against its
toughness. So a `CardState` that cannot ask the layer engine is a `CardState`
that gets both wrong the moment any continuous effect is in play - and there is
one case where it has no number at all: CR 208.2a's printed `*` is a
characteristic-defining ability (CR 604.3), applied in layer 7a (CR 613.4a),
and nothing but the layer engine can turn it into a number.

`CardState.bind_to_game` is the hook that closes that. Bound, a permanent on
the battlefield answers with the computed characteristics; unbound, or in any
other zone, it answers exactly as it did before. This file covers both sides of
that switch, and the corner cases around it.

**Who calls it**: `Game.enter_the_battlefield` binds a permanent as it enters,
which is every route onto the battlefield in a real game, and `Scenario.build`
binds a staged board the same way so a scenario is not the one place in the
engine reading printed characteristics. A `CardState` is therefore unbound only
when it was built outside a game, or rebuilt by `model_validate` - both of which
this file still covers, because that fallback is half of the contract.

Every CR number here was verified with `knowledge_search(q="...", type="rules")`
in the session that wrote it: CR 122.1a, CR 202.3a, CR 208.2a, CR 300.1,
CR 302.4c, CR 400.7, CR 406.3a, CR 510.1a, CR 604.3, CR 613.4a, CR 613.4c,
CR 613.5, CR 701.27c, CR 701.27d, CR 704.5g, CR 708.2a, CR 712.9, CR 712.10.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def bound(scenario, permanent):
    """Bind one object to the game it is actually on, and hand it back.

    A permanent staged onto the battlefield is bound already, so this is a
    no-op there and stays only to say at each call site which game the reading
    below is being taken against. It does real work for a card in another zone,
    which nothing binds.
    """
    permanent.bind_to_game(scenario.game)
    return permanent


# --------------------------------------------------------------------------
# A characteristic-defining ability (CR 604.3, layer 7a)
# --------------------------------------------------------------------------


def test_an_unbound_goyf_has_no_power_at_all():
    """The printed value is `*` (CR 208.2a), and `*` is not a number.

    No permanent on a real board is in this state any more - `Game.
    enter_the_battlefield` binds one as it enters, and `Scenario.build` binds a
    staged board the same way - so this constructs the `CardState` directly
    rather than through `Scenario`. It is still worth pinning, because it is
    the fallback half of `bind_to_game`'s contract: the properties answer
    `None` rather than guessing a number when there is no board to ask, and
    that is the reading a card carries after `CardState.model_validate` drops
    the binding (see the round-trip test at the foot of this file) and in every
    zone where CR 613.5's layer system has nothing to say.
    """
    goyf = card_state("Tarmogoyf", Zone.BATTLEFIELD, controller="alice", owner="alice")

    assert (goyf.card.power, goyf.card.toughness) == ("*", "1+*"), "the printing"
    assert (goyf.power, goyf.toughness) == (None, None)


def test_a_bound_goyf_reads_its_own_characteristic_defining_ability():
    """CR 604.3, CR 613.4a: layer 7a is where a `*` becomes a number.

    An instant and a land among the graveyards is two card types, so
    Tarmogoyf is a 2/3 - "Tarmogoyf's power is equal to the number of card
    types among cards in all graveyards and its toughness is equal to that
    number plus 1" - CR 300.1's card types, counted across every graveyard.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt", "Forest"])
        .build()
    )
    goyf = bound(scenario, scenario.creature("Tarmogoyf", "alice"))

    assert (goyf.power, goyf.toughness) == (2, 3)
    assert (goyf.power, goyf.toughness) == (
        scenario.game.power_of(goyf),
        scenario.game.toughness_of(goyf),
    )


def test_the_answer_moves_when_the_graveyard_does():
    """CR 613.5: "continually and automatically", so it is asked every time.

    A binding is a reference to the game, not a cached number: the same
    `CardState` read twice either side of a card reaching a graveyard gives
    two different answers.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Tarmogoyf", "Mountain"],
            graveyard=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goyf = bound(scenario, scenario.creature("Tarmogoyf", "alice"))

    assert (goyf.power, goyf.toughness) == (1, 2), "a land among the graveyards"

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert (goyf.power, goyf.toughness) == (2, 3), "the Bolt made it land plus instant"


# --------------------------------------------------------------------------
# An anthem (layer 7d) and counters (layer 7c, CR 122.1a)
# --------------------------------------------------------------------------


def test_a_bound_creature_sees_the_anthem_over_it():
    """Glorious Anthem's "Creatures you control get +1/+1" is layer 7c.

    CR 613.4c is the sublayer for effects that modify power and/or toughness
    without setting them to a specific number. Unbound - which is what the same
    `CardState` is when it is built outside a game - the Bears is the 2/2 its
    printing says; on a board with the anthem it is a 3/3.
    """
    loose = card_state("Grizzly Bears", Zone.BATTLEFIELD, controller="alice", owner="alice")
    assert (loose.power, loose.toughness) == (2, 2), "unbound: the printed value"

    scenario = Scenario().player("alice", battlefield=["Glorious Anthem", "Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")

    assert (bears.card.power, bears.card.toughness) == ("2", "2"), "the printing is still a 2/2"
    assert (bears.power, bears.toughness) == (3, 3)


def test_counters_still_reach_a_bound_permanent():
    """CR 122.1a's counters are layer 7c, so the layer engine already applies
    them - the bound reading must not lose them, and must not count them
    twice on top of the printed-plus-counters path this replaces."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("+1/+1", 2)

    assert (bears.power, bears.toughness) == (4, 4), "unbound: printed plus counters"

    bound(scenario, bears)

    assert (bears.power, bears.toughness) == (4, 4)


def test_lethal_damage_is_measured_against_the_computed_toughness():
    """CR 704.5g compares marked damage against toughness, and `CardState.
    has_lethal_damage` is what `Game.check_state_based_actions` reads.

    Two damage is lethal to a 2/2 Grizzly Bears and is not lethal to the same
    Bears under a Glorious Anthem - a difference only the bound reading can
    make, because the printed toughness is 2 either way.
    """
    scenario = Scenario().player("alice", battlefield=["Glorious Anthem", "Grizzly Bears"]).build()
    bears = bound(scenario, scenario.creature("Grizzly Bears", "alice"))
    bears.mark_damage(2)

    assert bears.toughness == 3
    assert not bears.has_lethal_damage
    assert bears.lethal_damage_remaining == 1


# --------------------------------------------------------------------------
# Where the binding deliberately says nothing
# --------------------------------------------------------------------------


def test_a_card_off_the_battlefield_reads_its_printing():
    """CR 613.5's layer system applies to permanents, and `Game.
    characteristics_of` refuses anything else - so a bound card in a hand or a
    graveyard answers with the printing, anthem or no anthem."""
    scenario = (
        Scenario().player("alice", hand=["Grizzly Bears"], battlefield=["Glorious Anthem"]).build()
    )
    bears = bound(scenario, scenario.find("Grizzly Bears", Zone.HAND, "alice"))

    assert (bears.power, bears.toughness) == (2, 2)


def test_a_binding_to_a_game_this_card_is_not_on_falls_back_rather_than_raising():
    """CR 400.7 makes a card that leaves the battlefield a new object, and a
    binding left over from a game this object is not on any more has no answer
    to give. `ComputedBoard.of` raises `KeyError` for it; the fallback is the
    printing, not an exception raised out of a property every state-based
    action check reads.
    """
    home = Scenario().player("alice", battlefield=["Grizzly Bears"]).build()
    elsewhere = Scenario().player("bob", battlefield=["Glorious Anthem"]).build()
    bears = home.creature("Grizzly Bears", "alice")
    bears.bind_to_game(elsewhere.game)

    assert (bears.power, bears.toughness) == (2, 2)


def test_a_bound_face_down_permanent_is_still_a_two_two():
    """CR 708.2a's listed characteristics are copiable values, so the layer
    engine starts from them in layer 1b rather than from the printing - the
    bound reading agrees with the unbound one that a face-down Brine Elemental
    is a 2/2 and not a 3/5."""
    scenario = Scenario().player("alice", battlefield=["Brine Elemental"]).build()
    elemental = scenario.creature("Brine Elemental", "alice")
    elemental.turn_face_down()

    assert (elemental.power, elemental.toughness) == (2, 2)

    bound(scenario, elemental)

    assert (elemental.power, elemental.toughness) == (2, 2)


def test_the_binding_does_not_survive_a_round_trip_through_the_model():
    """`_board_source` is a private attribute, not a field: a game that is
    serialised and validated back carries no reference to the process that
    dumped it, and the rebuilt object is unbound.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tarmogoyf"], graveyard=["Lightning Bolt", "Forest"])
        .build()
    )
    goyf = bound(scenario, scenario.creature("Tarmogoyf", "alice"))
    assert goyf.power == 2

    from magic_cards_model.models.card_state import CardState

    rebuilt = CardState.model_validate(goyf.model_dump())

    assert "_board_source" not in goyf.model_dump()
    assert rebuilt.power is None

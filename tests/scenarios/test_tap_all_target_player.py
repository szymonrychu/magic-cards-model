"""Scenario: "Tap all `<group>` `<whose>`." - a mass tap of every matching
permanent one player (or every opponent) controls.

Readers under test (`machines/effects._parse_tap_all_group_clause`):

- **"Tap all creatures target player controls."** - Suppression Ray's own
  first sentence; **Dawnglare Invoker** ("{8}: Tap all creatures target
  player controls.", Modern-legal, not in any deck) is the off-set proof on
  an *activated* ability rather than a sorcery.
- **"Tap all creatures your opponents control."** - Cryptic Command's third
  mode, proven in every mode pair it can sit in; **Subjugator Angel**
  ("When this creature enters, tap all creatures your opponents control.",
  Modern/Pioneer-legal, not in any deck) is the off-set proof on a
  *triggered* ability with no target at all.

Rules, each read with `mise run rules:find` in the session that wrote this
file:

- **CR 701.26a** - "To tap a permanent, turn it sideways from an upright
  position. Only untapped permanents can be tapped." An already-tapped
  creature is not an error, it is simply not tapped again.
- **CR 115.10a** - the creatures are affected but not targeted; only the
  player is (Suppression Ray, Dawnglare Invoker), so hexproof on a creature
  does not stop it being tapped.
- **CR 608.2b** - a target player who is no longer legal leaves the
  instruction undone.
- **CR 700.2a** - a modal spell's modes are chosen as it is cast.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# "Tap all creatures target player controls." - Dawnglare Invoker
# --------------------------------------------------------------------------


def _dawnglare_board(*, bob_creatures=("Grizzly Bears", "Serra Angel")) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Dawnglare Invoker", "Elvish Mystic"] + ["Plains"] * 8)
        .player("bob", battlefield=list(bob_creatures) + ["Island"])
    )


def _eight_plains(scenario):
    return scenario.untapped_sources(*["Plains"] * 8, username="alice")


def test_dawnglare_invoker_taps_every_creature_the_target_player_controls():
    scenario = _dawnglare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.activate(invoker, *_eight_plains(scenario), targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.tapped and angel.tapped


def test_only_the_target_players_creatures_are_tapped():
    """alice's own Elvish Mystic and bob's Island are untouched: the group is
    creatures, and only the ones the *target* player controls."""
    scenario = _dawnglare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    scenario.activate(invoker, *_eight_plains(scenario), targets=["bob"])
    scenario.pass_until_resolved()

    assert not mystic.tapped
    assert not island.tapped


def test_targeting_yourself_taps_your_own_creatures():
    """ "Target player" includes the controller (CR 115.1): alice may aim it at
    herself, and then it is her creatures, not bob's, that tap."""
    scenario = _dawnglare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    invoker.tapped = False

    scenario.activate(invoker, *_eight_plains(scenario), targets=["alice"])
    scenario.pass_until_resolved()

    assert mystic.tapped
    assert not bears.tapped


def test_an_already_tapped_creature_stays_tapped_and_is_not_an_error():
    """CR 701.26a: only untapped permanents can be tapped - a tapped one is
    silently left as it is, never a refusal of the whole instruction."""
    scenario = _dawnglare_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    bears.tapped = True

    scenario.activate(invoker, *_eight_plains(scenario), targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.tapped and angel.tapped


def test_a_player_with_no_creatures_is_a_legal_target_and_nothing_happens():
    scenario = _dawnglare_board(bob_creatures=()).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    scenario.activate(invoker, *_eight_plains(scenario), targets=["bob"])
    scenario.pass_until_resolved()

    assert not mystic.tapped
    assert not island.tapped


def test_a_creature_that_arrives_after_resolution_is_not_tapped():
    """The group is read once, as the ability resolves (CR 608.2h) - it is
    not a continuous "creatures stay tapped" effect."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dawnglare Invoker"] + ["Plains"] * 8)
        .player("bob", hand=["Grizzly Bears"], battlefield=["Serra Angel", "Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    invoker = scenario.creature("Dawnglare Invoker", "alice")

    scenario.activate(invoker, *_eight_plains(scenario), targets=["bob"])
    scenario.pass_until_resolved()
    bears = scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert scenario.creature("Serra Angel", "bob").tapped
    assert not bears.tapped


# --------------------------------------------------------------------------
# "Tap all creatures your opponents control." - Subjugator Angel
# --------------------------------------------------------------------------


def test_subjugator_angel_taps_every_opponents_creature_and_none_of_yours():
    scenario = (
        Scenario()
        .player("alice", hand=["Subjugator Angel"], battlefield=["Elvish Mystic"])
        .player("bob", battlefield=["Grizzly Bears", "Serra Angel", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mystic = scenario.creature("Elvish Mystic", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    island = scenario.find("Island", Zone.BATTLEFIELD, "bob")

    subjugator = scenario.put_onto_battlefield("Subjugator Angel", "alice")
    scenario.pass_until_resolved()  # its own enters trigger

    assert bears.tapped and angel.tapped
    assert not mystic.tapped, "your opponents' creatures only"
    assert not subjugator.tapped, "the Angel itself is alice's"
    assert not island.tapped, "creatures only"


# --------------------------------------------------------------------------
# Cryptic Command: "Tap all creatures your opponents control." in every pair
# --------------------------------------------------------------------------

TAP_MODE = "Tap all creatures your opponents control."


def _cryptic_board(alice_hand=("Cryptic Command",)) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=["Island"] * 4 + ["Mountain", "Elvish Mystic"],
            library=["Island", "Island"],
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Serra Angel"],
            library=["Island"],
        )
    )


def _cast_cryptic(scenario, modes, targets=None):
    casting = scenario.cast("Cryptic Command", "alice")
    casting.choose_modes(modes)
    if targets is not None:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", "Island", "Island"))
    return scenario.put_on_stack(casting)


def test_cryptic_tap_and_draw():
    scenario = _cryptic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    mystic = scenario.creature("Elvish Mystic", "alice")
    hand_before = len(scenario.player("alice").hand)

    _cast_cryptic(scenario, [TAP_MODE, "Draw a card."])
    scenario.resolve_top()

    assert bears.tapped and angel.tapped
    assert not mystic.tapped
    assert len(scenario.player("alice").hand) == hand_before  # -1 cast, +1 draw


def test_cryptic_bounce_and_tap_taps_after_the_bounce():
    """Return bob's Angel, then tap the rest - the bounced creature is gone,
    the Bears are tapped (CR 608.2c, instructions in the order written)."""
    scenario = _cryptic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    _cast_cryptic(
        scenario,
        ["Return target permanent to its owner's hand.", TAP_MODE],
        targets=[angel],
    )
    scenario.resolve_top()

    assert angel.zone is Zone.HAND
    assert bears.tapped


def test_cryptic_counter_and_tap():
    """alice counters her own Lightning Bolt (still on the stack, aimed at
    bob's Bears) and taps bob's team in the same resolution."""
    scenario = _cryptic_board(alice_hand=("Cryptic Command", "Lightning Bolt")).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[bears])

    _cast_cryptic(scenario, ["Counter target spell.", TAP_MODE], targets=[bolt])
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0, "the Bolt never resolved"
    assert bears.tapped and angel.tapped


def test_cryptic_pairs_without_the_tap_mode_tap_nothing():
    """The tap is a mode, not a rider: bounce + draw leaves every creature
    untapped."""
    scenario = _cryptic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    _cast_cryptic(
        scenario,
        ["Return target permanent to its owner's hand.", "Draw a card."],
        targets=[angel],
    )
    scenario.resolve_top()

    assert angel.zone is Zone.HAND
    assert not bears.tapped


def test_cryptic_whose_only_target_is_gone_does_not_tap():
    """Cryptic Command's own ruling (2017-11-17): with a target whose every
    target is illegal on resolution, the whole spell does not resolve - so
    bounce + tap with the bounced permanent already gone taps nothing
    (CR 608.2b)."""
    scenario = _cryptic_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    _cast_cryptic(
        scenario,
        ["Return target permanent to its owner's hand.", TAP_MODE],
        targets=[angel],
    )
    scenario.game.return_to_hand(angel)
    scenario.resolve_top()

    assert not bears.tapped

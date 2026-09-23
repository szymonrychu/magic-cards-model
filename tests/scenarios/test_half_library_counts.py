"""Scenario: counts read as "half" of a library, rounded up or down.

Three printings, three verbs, one reader. Tamiyo, Seasoned Scholar's -7
draws "cards equal to half the number of cards in your library, rounded
up"; Traumatize (off-pool proof printing: a different verb, a targeted
player, and rounding *down*) has its target mill "half their library,
rounded down"; Ulamog, the Defiler's cast trigger has its target opponent
exile "the top half of their library, rounded up".

Every CR number below was read with `mise run rules:find` in the session
that wrote this file:

- **CR 107.1a** - "If a spell or ability could generate a fractional number,
  the spell or ability will tell you whether to round up or down."
- **CR 608.2h** - information from the game (here, the size of a library) is
  determined once, when the effect is applied.
- **CR 701.17a** - "For a player to mill a number of cards, that player puts
  that many cards from the top of their library into their graveyard."
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
- **CR 402.2** - "Each player has a maximum hand size, which is normally
  seven cards."
- **CR 514.1** - the cleanup discard down to that maximum.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

TAMIYO = "Tamiyo, Inquisitive Student"
SEASONED_SCHOLAR = "Tamiyo, Seasoned Scholar"
ULAMOG = "Ulamog, the Defiler"


def _resolve_stack(scenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def _tamiyo_flipped(library_size: int, *, hand: list[str] | None = None):
    """Tamiyo on the battlefield, flipped the real way: her own third-draw
    trigger (CR 121.2) exiles her and returns her transformed. Three extra
    library cards feed those three draws, so `library_size` is what is left
    once she has flipped."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[TAMIYO],
            hand=hand or [],
            library=["Island"] * (library_size + 3),
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.draw_cards("alice", 3)
    scenario.game.put_triggers_on_stack()
    _resolve_stack(scenario)
    tamiyo = scenario.find(SEASONED_SCHOLAR, Zone.BATTLEFIELD, "alice")
    assert tamiyo.up_face_name == SEASONED_SCHOLAR
    # 2 printed loyalty; enough for -7 with some left over (CR 704.5i).
    scenario.game.add_counters(tamiyo, Counter.LOYALTY, 8)
    return scenario, tamiyo


# -- Tamiyo, Seasoned Scholar's -7: half your library, rounded up ------------


def test_minus_seven_draws_half_an_odd_library_rounded_up():
    """Seven cards left: half is 3.5, and the card says round up - four."""
    scenario, tamiyo = _tamiyo_flipped(7)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    scenario.activate(tamiyo, index=2)
    scenario.resolve_top()

    assert len(alice.hand) == hand_before + 4
    assert len(alice.library) == 3


def test_minus_seven_draws_exactly_half_an_even_library():
    """Eight cards: half is exactly four, nothing to round."""
    scenario, tamiyo = _tamiyo_flipped(8)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    scenario.activate(tamiyo, index=2)
    scenario.resolve_top()

    assert len(alice.hand) == hand_before + 4
    assert len(alice.library) == 4


def test_minus_seven_on_a_one_card_library_draws_it():
    """Half of one rounded up is one - the last card, and no empty-library
    draw (which CR 704.5b would punish) happens."""
    scenario, tamiyo = _tamiyo_flipped(1)
    alice = scenario.player("alice")

    scenario.activate(tamiyo, index=2)
    scenario.resolve_top()

    assert alice.library == []
    assert not alice.tried_to_draw_from_empty_library


def test_minus_seven_on_an_empty_library_draws_nothing():
    """Half of zero is zero: no draw is attempted at all."""
    scenario, tamiyo = _tamiyo_flipped(0)
    alice = scenario.player("alice")
    hand_before = len(alice.hand)

    scenario.activate(tamiyo, index=2)
    scenario.resolve_top()

    assert len(alice.hand) == hand_before
    assert not alice.tried_to_draw_from_empty_library


def test_minus_seven_counts_the_library_as_it_resolves_not_as_it_is_activated():
    """CR 608.2h: the count is taken when the effect applies. Two cards drawn
    in response shrink an eleven-card library to nine - five, not six."""
    scenario, tamiyo = _tamiyo_flipped(11)
    alice = scenario.player("alice")

    scenario.activate(tamiyo, index=2)
    scenario.game.draw_cards("alice", 2)
    hand_before = len(alice.hand)
    scenario.resolve_top()

    assert len(alice.hand) == hand_before + 5
    assert len(alice.library) == 4


def test_minus_seven_also_gives_the_no_maximum_hand_size_emblem():
    """The second sentence still resolves: alice gets the emblem, and a hand
    far past seven survives the cleanup check (CR 514.1)."""
    scenario, tamiyo = _tamiyo_flipped(20, hand=["Mountain"] * 6)
    alice = scenario.player("alice")

    scenario.activate(tamiyo, index=2)
    scenario.resolve_top()

    assert len(alice.hand) > alice.maximum_hand_size
    assert [emblem.card.oracle_text for emblem in alice.emblems] == [
        "You have no maximum hand size."
    ]
    assert alice.has_no_maximum_hand_size
    assert alice.cards_over_maximum_hand_size == 0


# -- Traumatize: half their library, rounded down (off-pool proof) ---------


def _traumatize(bobs_library: int, *, target: str = "bob", alices_library: int = 0):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Traumatize"],
            battlefield=["Island"] * 5,
            library=["Island"] * alices_library,
        )
        .player("bob", library=["Forest"] * bobs_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources(*["Island"] * 5, username="alice")
    scenario.cast_and_resolve("Traumatize", *islands, targets=[target])
    return scenario


def test_traumatize_mills_half_an_odd_library_rounded_down():
    """Nine cards: half is 4.5, and this card says round down - four."""
    scenario = _traumatize(9)
    bob = scenario.player("bob")

    assert len(bob.graveyard) == 4
    assert len(bob.library) == 5


def test_traumatize_mills_exactly_half_an_even_library():
    scenario = _traumatize(10)
    bob = scenario.player("bob")

    assert len(bob.graveyard) == 5
    assert len(bob.library) == 5


def test_traumatize_on_a_one_card_library_mills_nothing():
    """Half of one rounded down is zero - the direction of rounding is the
    whole difference from Tamiyo's own count."""
    scenario = _traumatize(1)
    bob = scenario.player("bob")

    assert bob.graveyard == []
    assert len(bob.library) == 1


def test_traumatize_counts_the_targeted_players_library_not_the_casters():
    """ "Their library" is the target's: alice's own twelve-card library is
    neither counted nor milled when bob is the target."""
    scenario = _traumatize(6, alices_library=12)

    assert len(scenario.player("bob").graveyard) == 3
    assert len(scenario.player("alice").library) == 12


def test_traumatize_can_target_its_own_caster():
    """ "Target player" includes the caster: alice mills half of her own."""
    scenario = _traumatize(6, target="alice", alices_library=8)

    assert len(scenario.player("alice").graveyard) == 1 + 4  # Traumatize itself, then four
    assert len(scenario.player("bob").library) == 6


# -- Ulamog, the Defiler's cast trigger: the top half, rounded up ----------


def _ulamog(bobs_library: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=[ULAMOG], battlefield=["Mountain"] * 10)
        .player("bob", library=bobs_library)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(ULAMOG, ["bob"])
    mountains = scenario.untapped_sources(*["Mountain"] * 10, username="alice")
    scenario.cast_onto_stack(ULAMOG, *mountains)
    return scenario


def test_ulamogs_cast_trigger_exiles_the_top_half_of_an_odd_library_rounded_up():
    """Seven cards: half rounded up is four, taken off the top, in order."""
    library = ["Forest", "Island", "Swamp", "Mountain", "Plains", "Forest", "Island"]
    scenario = _ulamog(library)
    bob = scenario.player("bob")
    top_four = list(bob.library[:4])

    scenario.resolve_top()  # the cast trigger sits above Ulamog (CR 603.3)

    assert [state.zone for state in top_four] == [Zone.EXILE] * 4
    assert len(bob.library) == 3
    assert ULAMOG in scenario.stack_names()


def test_ulamogs_cast_trigger_on_a_one_card_library_exiles_it():
    scenario = _ulamog(["Forest"])

    scenario.resolve_top()

    assert scenario.player("bob").library == []
    assert [state.name for state in scenario.game.exile] == ["Forest"]


def test_ulamogs_cast_trigger_on_an_empty_library_exiles_nothing():
    scenario = _ulamog([])

    scenario.resolve_top()

    assert scenario.game.exile == []


def test_ulamog_enters_with_counters_equal_to_the_greatest_mana_value_it_exiled():
    """The exile feeds Ulamog's own enters-with replacement: of the two cards
    exiled, Traumatize's mana value of five is the greatest, so Ulamog
    enters with five +1/+1 counters."""
    scenario = _ulamog(["Lightning Bolt", "Traumatize", "Forest"])

    _resolve_stack(scenario)

    ulamog = scenario.find(ULAMOG, Zone.BATTLEFIELD, "alice")
    assert sorted(state.name for state in scenario.game.exile) == [
        "Lightning Bolt",
        "Traumatize",
    ]
    assert ulamog.counters[Counter.PLUS_ONE] == 5

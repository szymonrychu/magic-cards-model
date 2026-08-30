"""Mass destruction and mass sacrifice: an effect that destroys or sacrifices
every permanent matching a printed description, rather than a target CR
601.2c would announce and CR 608.2b would recheck (CR 701.8a, CR 701.21a).

Four cards carry the mechanic here:

- **Culling Ritual** - "Destroy each nonland permanent with mana value 2 or
  less. Add {B} or {G} for each permanent destroyed this way." The
  comparison's right-hand side is a printed constant.
- **Engineered Explosives** - "{2}, Sacrifice this artifact: Destroy each
  nonland permanent with mana value equal to the number of charge counters on
  this artifact." The right-hand side is a count of counters on the ability's
  own source, which has already sacrificed itself as part of the same cost.
- **Oblivion Stone** - "{5}, {T}, Sacrifice this artifact: Destroy each
  nonland permanent without a fate counter on it, then remove all fate
  counters from all permanents." The qualifier is an absence of a named
  counter, and the ability is two instructions in one sentence.
- **All Is Dust** - "Each player sacrifices all permanents they control that
  are one or more colors." Sacrifice, not destroy (CR 701.21a), and "each
  player" rather than "each permanent".

Wrath of the Skies shares the same "destroy each <qualifier> with mana value
<cmp>" shape and already has its own scenario coverage from the energy-payment
wave that added it; it is not repeated here.

The corner cases are the point, not the happy path:

- **Indestructible** (CR 702.12b) stops `destroy`, but not `sacrifice` -
  All Is Dust ignores it entirely, and a destroy-shaped effect's own count of
  "permanents destroyed this way" (Culling Ritual) must not count one that
  refused to leave.
- **The ability's own source**: Engineered Explosives has already left the
  battlefield as this activation's own cost by the time its ability
  resolves, so it is never a candidate for its own destroy-each - and its
  "the number of charge counters on this artifact" reads `last_known_
  counters` rather than the fresh, empty object CR 400.7 makes of anything
  that changes zones.
- **A permanent the sweep marked but did not destroy** keeps that mark only
  until Oblivion Stone's own second, unconditional instruction strips it
  from *every* permanent, not only the ones just destroyed.
- **Mana value of a double-faced permanent** - `machines/layers.printed_
  characteristics` is checked directly for a modal double-faced land, which
  this project has repeatedly gotten wrong by reading the raw `Card.cmc`
  instead of the face that is actually up (CR 712.8f).
- **An empty board** is a legal no-op for every one of these effects.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import is_indestructible
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

# -- Culling Ritual: destroy each nonland permanent with mana value <= 2,
# -- then add {B} or {G} for each one actually destroyed ------------------


def _culling_ritual_board() -> Scenario:
    return Scenario().player(
        "alice",
        hand=["Culling Ritual"],
        battlefield=[
            "Forest",
            "Forest",
            "Swamp",
            "Swamp",
            "Memnite",
            "Grizzly Bears",
            "Ulamog, the Ceaseless Hunger",
        ],
    )


def test_culling_ritual_destroys_nonland_permanents_at_or_under_the_threshold():
    scenario = _culling_ritual_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve(
        "Culling Ritual", *scenario.untapped_sources("Forest", "Swamp"), auto=True
    )

    assert memnite.zone is Zone.GRAVEYARD, "mana value 0 is at or under 2"
    assert bears.zone is Zone.GRAVEYARD, "mana value 2 is at or under 2"


def test_culling_ritual_spares_lands_and_higher_mana_value_permanents():
    scenario = _culling_ritual_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.creature("Ulamog, the Ceaseless Hunger", "alice")

    scenario.cast_and_resolve("Culling Ritual", auto=True)

    assert "Forest" in scenario.battlefield_names()
    assert "Swamp" in scenario.battlefield_names()
    assert ulamog.zone is Zone.BATTLEFIELD, "mana value 10 is well over the threshold"


def test_culling_ritual_adds_one_mana_for_each_permanent_actually_destroyed():
    """The mana total counts what was destroyed, not what was targeted - an
    indestructible candidate (CR 702.12b) never leaves, so it is not one of
    the "permanent[s] destroyed this way" the second sentence counts.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Culling Ritual"],
            battlefield=["Forest", "Forest", "Swamp", "Swamp", "Memnite", "Darksteel Relic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")
    relic = scenario.find("Darksteel Relic", Zone.BATTLEFIELD, "alice")
    assert is_indestructible(relic)

    scenario.cast_and_resolve("Culling Ritual", auto=True)

    assert memnite.zone is Zone.GRAVEYARD
    assert relic.zone is Zone.BATTLEFIELD, "indestructible refuses the destroy"
    pool = scenario.player("alice").mana_pool
    assert sum(pool.floating.values()) == 1, "only the one permanent that actually died"
    assert pool.floating == {Color.BLACK: 1}, "the unscripted default takes the first offered color"


def test_culling_ritual_is_a_legal_no_op_on_an_empty_qualifying_set():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Culling Ritual"], battlefield=["Forest", "Forest", "Swamp", "Swamp"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Culling Ritual", auto=True)

    assert set(scenario.battlefield_names()) == {"Forest", "Swamp"}
    assert scenario.player("alice").mana_pool.floating == {}


# -- Engineered Explosives: destroy each nonland permanent with mana value
# -- equal to the number of charge counters on the (already-sacrificed) source


def _explosives_board() -> Scenario:
    return Scenario().player(
        "alice",
        battlefield=["Engineered Explosives", "Memnite", "Grizzly Bears", "Forest", "Forest"],
    )


def test_engineered_explosives_destroys_only_the_matching_mana_value():
    scenario = _explosives_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    explosives = scenario.find("Engineered Explosives", Zone.BATTLEFIELD, "alice")
    explosives.add_counters(Counter.CHARGE, 2)
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.activate(explosives, *forests, sacrificing=[explosives])
    scenario.pass_until_resolved()

    assert explosives.zone is Zone.GRAVEYARD, "paid as the activation's own cost"
    assert memnite.zone is Zone.BATTLEFIELD, "mana value 0 does not equal 2 charge counters"
    assert bears.zone is Zone.GRAVEYARD, "mana value 2 equals 2 charge counters"


def test_engineered_explosives_reads_its_own_counters_after_it_has_already_left():
    """The ability's source has already been sacrificed as this activation's
    own cost (CR 602.2b: costs are paid on activation, before the ability
    even resolves), so by the time "the number of charge counters on this
    artifact" is read, the object CR 400.7 calls a new one in the graveyard
    has none - the count this ability actually means is the one it had the
    instant it left, kept on `last_known_counters` for exactly this "look
    back" case. Zero charge counters also proves the source is never a
    candidate for its own effect: Engineered Explosives' own mana value off
    the stack is 0 (CR 202.3e's `{X}` is 0 when not on the stack), which
    would match a zero-counter threshold if it were still around to be
    destroyed - it is not, because it already left as the cost.
    """
    scenario = _explosives_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    explosives = scenario.find("Engineered Explosives", Zone.BATTLEFIELD, "alice")
    memnite = scenario.creature("Memnite", "alice")
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.activate(explosives, *forests, sacrificing=[explosives])
    scenario.pass_until_resolved()

    assert explosives.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.GRAVEYARD, "mana value 0 equals the 0 charge counters it left with"


def test_engineered_explosives_is_a_legal_no_op_with_no_matching_permanents():
    scenario = _explosives_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    explosives = scenario.find("Engineered Explosives", Zone.BATTLEFIELD, "alice")
    explosives.add_counters(Counter.CHARGE, 9)
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.activate(explosives, *forests, sacrificing=[explosives])
    scenario.pass_until_resolved()

    assert "Memnite" in scenario.battlefield_names()
    assert "Grizzly Bears" in scenario.battlefield_names()


# -- Oblivion Stone: mark permanents with fate counters, then destroy every
# -- nonland permanent that was not marked, and strip every fate counter -----


def _oblivion_stone_board() -> Scenario:
    return Scenario().player(
        "alice",
        battlefield=[
            "Oblivion Stone",
            "Memnite",
            "Grizzly Bears",
            "Forest",
            "Forest",
            "Forest",
            "Forest",
            "Forest",
        ],
    )


def test_oblivion_stones_first_ability_marks_a_permanent_with_a_fate_counter():
    scenario = _oblivion_stone_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Oblivion Stone", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    scenario.activate(stone, *sources, targets=[bears])
    scenario.pass_until_resolved()

    assert bears.counters == {"fate": 1}


def test_oblivion_stones_second_ability_spares_a_marked_permanent_but_still_strips_its_counter():
    """The fate counter is staged directly here (CR 122.1's own counter, not
    the target-choosing ability itself, which the previous test already
    proves reaches the battlefield correctly) so that the one `{T}` this
    scenario spends is the second ability's own, not the first ability's.
    """
    scenario = _oblivion_stone_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Oblivion Stone", Zone.BATTLEFIELD, "alice")
    memnite = scenario.creature("Memnite", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters("fate", 1)

    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    scenario.activate(stone, *sources, index=1, sacrificing=[stone])
    scenario.pass_until_resolved()

    assert stone.zone is Zone.GRAVEYARD, "paid as the second activation's own cost"
    assert memnite.zone is Zone.GRAVEYARD, "unmarked, so it has no fate counter to spare it"
    assert bears.zone is Zone.BATTLEFIELD, "marked, so the destroy half never touches it"
    assert bears.counters == {}, "the sweep strips the counter from every permanent, marked or not"


def test_oblivion_stones_second_ability_is_a_legal_no_op_with_no_nonland_permanents():
    """No nonland permanent to destroy - the lands paying for the activation
    are the only other permanents there, and the qualifier excludes them.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Oblivion Stone", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Oblivion Stone", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")

    scenario.activate(stone, *sources, index=1, sacrificing=[stone])
    scenario.pass_until_resolved()

    assert stone.zone is Zone.GRAVEYARD
    assert set(scenario.battlefield_names()) == {"Forest"}


# -- All Is Dust: each player sacrifices their own colored permanents -------


def _all_is_dust_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["All Is Dust"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Mountain", "Grizzly Bears", "Sol Ring"])
    )


def test_all_is_dust_sacrifices_only_colored_permanents_per_player():
    scenario = _all_is_dust_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("All Is Dust", auto=True)

    assert bears.zone is Zone.GRAVEYARD, "green is a color"
    assert sol_ring.zone is Zone.BATTLEFIELD, "a colorless artifact is not"
    assert "Mountain" in scenario.battlefield_names(), "a basic land is colorless too"
    alices_permanents = [
        state.name for state in scenario.game.battlefield if state.controller == "alice"
    ]
    assert alices_permanents == ["Forest"] * 7, "alice's own board is all colorless lands"


def test_all_is_dust_sacrifices_ignore_indestructible():
    """CR 701.21a's sacrifice is not CR 701.8a's destroy, so CR 702.12b never
    applies - the single easiest thing to get wrong about this card.
    Predator Ooze prints indestructible outright, so this needs no separate
    granting effect to make the point.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["All Is Dust"], battlefield=["Forest"] * 7)
        .player("bob", battlefield=["Predator Ooze"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ooze = scenario.creature("Predator Ooze", "bob")
    assert is_indestructible(ooze)

    scenario.cast_and_resolve("All Is Dust", auto=True, username="alice")

    assert ooze.zone is Zone.GRAVEYARD, "sacrificed despite indestructible"


def test_all_is_dust_is_a_legal_no_op_with_no_colored_permanents():
    scenario = (
        Scenario()
        .player("alice", hand=["All Is Dust"], battlefield=["Forest"] * 7)
        .player("bob", battlefield=["Mountain", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("All Is Dust", auto=True)

    assert "Mountain" in scenario.battlefield_names()
    assert "Sol Ring" in scenario.battlefield_names()


# -- Mana value of a modal double-faced permanent (CR 712.8f) --------------


def test_mana_value_of_an_mdfc_land_is_its_own_land_faces_not_the_spell_faces():
    """`machines/layers.printed_characteristics` used to read `Card.cmc`
    unconditionally, which Scryfall always reports as the *spell* face's
    mana value for a modal double-faced card (Valakut Awakening's own {2}{R},
    mana value 3) even when the land face is the one actually up. CR 712.8f:
    "While a modal double-faced permanent is on the battlefield, it has only
    the characteristics of the face that's up" - a land prints no mana cost
    at all, so its mana value is 0 (CR 202.3a), not 3. None of this file's
    four mass-destruction cards happens to compare a land's mana value (all
    either exclude lands outright or do not test mana value at all), so this
    is checked directly against the computed board rather than through one
    of them.
    """
    scenario = Scenario().player("alice", hand=["Valakut Awakening"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    valakut = scenario.play_land("Valakut Awakening", "alice")

    assert valakut.land_face_played == "Valakut Stoneforge"
    assert scenario.game.characteristics_of(valakut).mana_value == 0

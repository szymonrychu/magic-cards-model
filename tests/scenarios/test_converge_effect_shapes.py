"""Scenario: Converge (an ability word, CR 207.2c - verified 2026-09-26 with
`mise run rules:find 207.2c`; "Ability words ... have no special rules
meaning and no individual entries in the Comprehensive Rules") in every
position the Secrets of Strixhaven pool prints it, beyond Prismatic Ending's
own target-restriction shape (`test_prismatic_ending.py`):

- **Effect position** - "X is the number of colors of mana spent to cast
  this spell", applied to a discard (Arcane Omens), a damage-then-exile-
  excess pair (Archaic's Agony), a token-creation-then-counters-and-life
  compound (Snarl Song), a three-actor compound (Together as One), and a
  target-less "you" clause (Painful Truths, the proof printing).
- **Target-legality position** - Sundering Archaic's own ETB exile, where
  the count is read off the *source* (the entering creature), not off the
  target, because CR 603.3d puts a triggered ability's targets on the stack
  only after the creature that triggered it has already resolved and been
  cast.
- **Enters-with-counters position** - Magmablood/Rancorous/Wildgrowth
  Archaic's own "This creature enters with a +1/+1 counter on it for each
  color of mana spent to cast it," and Skyrider Elf as the proof printing.
- **An enters-with replacement created by a cast trigger** - Wildgrowth
  Archaic's own "Whenever you cast a creature spell, that creature enters
  with X additional +1/+1 counters on it."
- **A mass-pump trigger scaled by a different spell's own colors spent** -
  Magmablood Archaic's own "Whenever you cast an instant or sorcery spell,
  creatures you control get +1/+0 until end of turn for each color of mana
  spent to cast that spell."

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 105.1/105.2c** - the five colors; colorless is not one of them.
- **CR 601.2h** - the total cost's mana is paid here; `CastRecord.mana_spent`
  is what was actually spent.
- **CR 400.7a/400.7b** - a permanent spell becoming a permanent is the one
  zone change CR 400.7's "new object" rule exempts from losing its cast
  record and its granted ability texts.
- **CR 603.3b** - a triggered ability goes on the stack directly above the
  spell whose casting triggered it, and so resolves first.
- **CR 603.3d** - the remainder of putting a triggered ability on the stack
  (including its own target announcement) follows CR 601.2c-d, i.e. after
  the ability's own source has already finished being cast.
- **CR 120.4a/120.10** - excess damage: the amount dealt to a creature in
  excess of what would have been lethal.
- **CR 107.1b** - a negative or undefined calculation result is treated as
  zero.

No second real printing shares Arcane Omens/Snarl Song/Together as One's own
exact combined templates (verified against Scryfall's bulk data this
session - see the dated MEMORY.md line); Skyrider Elf and Painful Truths are
the proof printings this file uses instead, each sharing the underlying
"colors of mana spent" reader with a genuinely different surrounding
template (a different cost shape, and a target-less "you" clause).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# ---------------------------------------------------------------------------
# Arcane Omens - "Converge - Target player discards X cards, where X is the
# number of colors of mana spent to cast this spell."
# ---------------------------------------------------------------------------


def test_arcane_omens_discards_a_card_per_color_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arcane Omens"],
            battlefield=["Swamp", "Mountain", "Forest", "Swamp", "Mountain"],
        )
        .player("bob", hand=["Lightning Bolt", "Divination", "Grizzly Bears"])
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Swamp", "Mountain", "Forest", "Swamp", "Mountain")
    scenario.cast_and_resolve("Arcane Omens", *sources, targets=["bob"])
    bob = scenario.player("bob")
    # Three colors spent (B, R, G) among the five mana that pay {4}{B}.
    assert len(bob.hand) == 0


def test_arcane_omens_discards_only_for_the_colors_the_generic_cost_forces():
    """CR 105.2c: colorless mana is not one of the five colors. {4}{B}'s own
    coloured pip forces at least one color spent (the {B}); paying the rest
    with colorless sources adds no further color to the count, so only one
    card is discarded rather than five."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arcane Omens"],
            battlefield=["Swamp", "Wastes", "Wastes", "Wastes", "Wastes"],
        )
        .player("bob", hand=["Lightning Bolt", "Divination"])
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Swamp", "Wastes", "Wastes", "Wastes", "Wastes")
    scenario.cast_and_resolve("Arcane Omens", *sources, targets=["bob"])
    assert len(scenario.player("bob").hand) == 1


# ---------------------------------------------------------------------------
# Archaic's Agony - "Converge - Archaic's Agony deals X damage to target
# creature, where X is the number of colors of mana spent to cast this
# spell. Exile cards from the top of your library equal to the excess damage
# dealt to that creature this way. You may play those cards until the end of
# your next turn."
# ---------------------------------------------------------------------------


def test_archaics_agony_exiles_excess_damage_and_grants_play_permission():
    """A 1-toughness creature takes 3 damage: 2 is excess (CR 120.4a), so two
    cards are exiled off the top and alice may play them until the end of
    her next turn (CR 601.3)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Archaic's Agony"],
            battlefield=["Mountain", "Island", "Plains", "Mountain", "Island"],
            library=["Mountain", "Forest", "Swamp", "Plains", "Island"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    _to_main(scenario)
    elves = scenario.creature("Llanowar Elves", "bob")
    assert scenario.game.characteristics_of(elves).toughness == 1
    sources = scenario.untapped_sources("Mountain", "Island", "Plains", "Mountain", "Island")
    scenario.cast_and_resolve("Archaic's Agony", *sources, targets=[elves])

    assert elves.zone is Zone.GRAVEYARD
    exiled = [card for card in scenario.game.exile if card.owner == "alice"]
    assert len(exiled) == 2
    granted_ids = {permission.card_id for permission in scenario.game.play_permissions}
    for card in exiled:
        assert card.id in granted_ids


def test_archaics_agony_exiles_nothing_when_damage_is_not_excess():
    """One color spent deals exactly 1 damage to a 4-toughness creature -
    nothing is lethal, so CR 120.4a's excess is zero and nothing is exiled."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Archaic's Agony"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Mountain"],
            library=["Forest", "Swamp", "Plains"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Archaic's Agony", *sources, targets=[bears])

    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD
    assert len(scenario.game.exile) == 0


# ---------------------------------------------------------------------------
# Snarl Song - "Converge - Create two 0/0 green and blue Fractal creature
# tokens. Put X +1/+1 counters on each of them and you gain X life, where X
# is the number of colors of mana spent to cast this spell."
# ---------------------------------------------------------------------------


def test_snarl_song_creates_two_fractals_sized_by_colors_spent_and_gains_life():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Snarl Song"],
            battlefield=["Forest", "Mountain", "Island", "Plains", "Swamp", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    life_before = scenario.player("alice").life
    sources = scenario.untapped_sources("Forest", "Mountain", "Island", "Plains", "Swamp", "Forest")
    scenario.cast_and_resolve("Snarl Song", *sources)

    fractals = [state for state in scenario.game.battlefield if state.name == "Fractal Token"]
    assert len(fractals) == 2
    for token in fractals:
        assert token.counters["+1/+1"] == 5
        assert scenario.game.characteristics_of(token).power == 5
        assert scenario.game.characteristics_of(token).toughness == 5
    assert scenario.player("alice").life == life_before + 5


# ---------------------------------------------------------------------------
# Together as One - "Converge - Target player draws X cards, Together as One
# deals X damage to any target, and you gain X life, where X is the number
# of colors of mana spent to cast this spell."
# ---------------------------------------------------------------------------


def test_together_as_one_draws_damages_and_gains_life_together():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Together as One"],
            battlefield=["Mountain", "Island", "Plains", "Forest", "Swamp", "Mountain"],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 10)
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    life_before = scenario.player("alice").life
    sources = scenario.untapped_sources(
        "Mountain", "Island", "Plains", "Forest", "Swamp", "Mountain"
    )
    # `machines/targeting._parse` collects every "any target" occurrence
    # before its ordinary left-to-right scan, so the announcement order is
    # [any target, target player] even though the card prints them the
    # other way round.
    scenario.cast_and_resolve("Together as One", *sources, targets=[bears, "bob"])

    assert len(scenario.player("bob").hand) == 5
    # 5 damage is lethal for a 2/2 Grizzly Bears - it dies to the state-based
    # action rather than merely marking damage (CR 704.5g).
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before + 5


# ---------------------------------------------------------------------------
# Transcendent Archaic - "Converge - When this creature enters, you may draw
# X cards, where X is the number of colors of mana spent to cast this spell.
# If you draw one or more cards this way, discard two cards."
# ---------------------------------------------------------------------------


def test_transcendent_archaic_draws_then_discards_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Transcendent Archaic", "Mountain", "Forest", "Plains"],
            battlefield=["Swamp", "Island", "Forest", "Swamp", "Island", "Forest", "Swamp"],
            library=["Mountain"] * 10,
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(
        "Swamp", "Island", "Forest", "Swamp", "Island", "Forest", "Swamp"
    )
    scenario.cast_and_resolve("Transcendent Archaic", *sources)
    _resolve_all(scenario)

    # Three colors spent (B, U, G) among the seven mana that pay {7}: draw
    # three, then discard two, net +1 card, minus the creature itself
    # having left the hand to be cast.
    assert len(scenario.player("alice").hand) == 3 + 3 - 2


def test_transcendent_archaic_skips_the_discard_with_no_colors_spent():
    """Paid entirely with colorless mana: X is zero, so there is nothing to
    draw and CR 608.2c's "if you draw one or more cards this way" is false -
    no discard either."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Transcendent Archaic", "Mountain", "Forest"],
            battlefield=["Wastes", "Wastes", "Wastes", "Wastes", "Wastes", "Wastes", "Wastes"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Wastes"] * 7))
    scenario.cast_and_resolve("Transcendent Archaic", *sources)
    _resolve_all(scenario)

    assert len(scenario.player("alice").hand) == 2


# ---------------------------------------------------------------------------
# Magmablood/Rancorous/Wildgrowth Archaic - "Converge - This creature enters
# with a +1/+1 counter on it for each color of mana spent to cast it."
# ---------------------------------------------------------------------------


def test_rancorous_archaic_enters_with_a_counter_per_color_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rancorous Archaic"],
            battlefield=["Mountain", "Island", "Plains", "Forest", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Mountain", "Island", "Plains", "Forest", "Swamp")
    creature = scenario.cast_and_resolve("Rancorous Archaic", *sources)
    assert creature.counters["+1/+1"] == 5


def test_wildgrowth_archaic_enters_with_a_counter_per_color_spent():
    """`{2/G}{2/G}` paid entirely with four non-green sources forces both
    hybrid symbols to take their "2 generic" half rather than their "G"
    half, so all four lands are spent and all four colors count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wildgrowth Archaic"],
            battlefield=["Mountain", "Island", "Plains", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Mountain", "Island", "Plains", "Swamp")
    creature = scenario.cast_and_resolve("Wildgrowth Archaic", *sources)
    assert creature.counters["+1/+1"] == 4


def test_skyrider_elf_enters_with_a_counter_per_color_spent():
    """Proof printing: the same converge enters-with template, a genuinely
    different creature with an `{X}` in its own cost."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Skyrider Elf"], battlefield=["Forest", "Island", "Mountain", "Plains"]
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Forest", "Island", "Mountain", "Plains")
    casting = scenario.cast("Skyrider Elf")
    # {X}{G}{U} with X=2, paid with all four lands: the {G}/{U} pips take
    # Forest/Island, and the two generic from X take Mountain/Plains -
    # four colors spent in total.
    casting.determine_cost(x_value=2)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    elf = scenario.resolve_top()

    assert elf.counters["+1/+1"] == 4


# ---------------------------------------------------------------------------
# Wildgrowth Archaic's own second ability - "Whenever you cast a creature
# spell, that creature enters with X additional +1/+1 counters on it, where
# X is the number of colors of mana spent to cast it."
# ---------------------------------------------------------------------------


def test_wildgrowth_archaic_grants_counters_to_a_creature_spell_cast_after_it():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Wildgrowth Archaic", "Mountain", "Island", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Mountain", "Island", "Forest")
    scenario.cast_onto_stack("Grizzly Bears", *sources)
    _resolve_all(scenario)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    assert bears.counters["+1/+1"] == 2


def test_wildgrowth_archaic_grants_nothing_with_only_generic_mana():
    """CR 105.2c: colorless is not one of the five colors. A creature spell
    with an all-generic cost - Juggernaut's own `{4}` - spends zero colors no
    matter what pays it, so Wildgrowth Archaic's grant works out to zero
    counters (CR 107.1b)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Juggernaut"],
            battlefield=["Wildgrowth Archaic", "Wastes", "Wastes", "Wastes", "Wastes"],
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes")
    scenario.cast_onto_stack("Juggernaut", *sources)
    _resolve_all(scenario)

    juggernaut = scenario.find("Juggernaut", Zone.BATTLEFIELD)
    assert juggernaut.counters["+1/+1"] == 0


# ---------------------------------------------------------------------------
# Magmablood Archaic's own second ability - "Whenever you cast an instant or
# sorcery spell, creatures you control get +1/+0 until end of turn for each
# color of mana spent to cast that spell."
# ---------------------------------------------------------------------------


def test_magmablood_archaic_pumps_creatures_per_color_spent_on_that_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Divination"],
            battlefield=["Magmablood Archaic", "Grizzly Bears", "Mountain", "Island", "Plains"],
            library=["Forest"] * 10,
        )
        .build()
    )
    _to_main(scenario)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    magmablood = scenario.find("Magmablood Archaic", Zone.BATTLEFIELD)
    bears_power_before = scenario.game.characteristics_of(bears).power
    magmablood_power_before = scenario.game.characteristics_of(magmablood).power
    sources = scenario.untapped_sources("Mountain", "Island", "Plains")
    scenario.cast_onto_stack("Divination", *sources)
    _resolve_all(scenario)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD)
    magmablood = scenario.find("Magmablood Archaic", Zone.BATTLEFIELD)
    # Three colors spent (R, U, W) -> +3/+0, and Magmablood itself is a
    # creature "you control" too, so it is pumped as well.
    assert scenario.game.characteristics_of(bears).power == bears_power_before + 3
    assert scenario.game.characteristics_of(magmablood).power == magmablood_power_before + 3


# ---------------------------------------------------------------------------
# Sundering Archaic - "Converge - When this creature enters, exile target
# nonland permanent an opponent controls with mana value less than or equal
# to the number of colors of mana spent to cast this creature."
# ---------------------------------------------------------------------------


def test_sundering_archaic_exiles_a_permanent_within_the_colors_spent_bound():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sundering Archaic"],
            battlefield=["Mountain", "Island", "Plains", "Forest", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Servant of the Conduit"])
        .build()
    )
    _to_main(scenario)
    servant = scenario.creature("Servant of the Conduit", "bob")
    assert servant.card.cmc == 2.0
    sources = scenario.untapped_sources("Mountain", "Island", "Plains", "Forest", "Swamp", "Swamp")
    scenario.cast_onto_stack("Sundering Archaic", *sources)
    _resolve_all(scenario)

    assert servant.zone is Zone.EXILE


def test_sundering_archaic_cannot_target_a_permanent_above_the_bound():
    """Two colors spent bounds the exile at mana value 2 - a mana value 5
    permanent is not a legal target for the ETB ability's own announcement
    (CR 601.2c/603.3d), so it is never offered at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sundering Archaic"],
            battlefield=["Mountain", "Mountain", "Mountain", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    _to_main(scenario)
    angel = scenario.creature("Serra Angel", "bob")
    assert angel.card.cmc == 5.0
    sources = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Island", "Island", "Island"
    )
    scenario.cast_onto_stack("Sundering Archaic", *sources)
    _resolve_all(scenario)

    # No legal target at all when the trigger is put on the stack (two
    # colors spent, mana value 5 out of bound) - the ability is removed
    # rather than exiling anything (CR 603.3d).
    assert angel.zone is Zone.BATTLEFIELD


# ---------------------------------------------------------------------------
# Painful Truths - proof printing for the effect position, in a plain
# target-less "you" clause: "Converge - You draw X cards and lose X life,
# where X is the number of colors of mana spent to cast this spell."
# ---------------------------------------------------------------------------


def test_painful_truths_draws_and_loses_life_per_color_spent():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Painful Truths"],
            battlefield=["Swamp", "Mountain", "Forest"],
            library=["Mountain"] * 10,
        )
        .build()
    )
    _to_main(scenario)
    life_before = scenario.player("alice").life
    sources = scenario.untapped_sources("Swamp", "Mountain", "Forest")
    scenario.cast_and_resolve("Painful Truths", *sources)

    assert len(scenario.player("alice").hand) == 3
    assert scenario.player("alice").life == life_before - 3

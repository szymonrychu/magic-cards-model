"""Scenario: a general "target creature becomes a `<color>` `<creature
type>` with base power and toughness `<n>`/`<m>`[ until end of turn]" layer
reader (`machines/layers._BECOMES_CREATURE_TYPE_WITH_BASE_PT_RE`,
`_becomes_creature_type_with_base_pt_builder`) - one ability applying in four
layers (CR 613.6): colour in layer 5, creature type in layer 4 (replacing
whatever creature types the target already had), and base power/toughness in
sublayer 7b.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 613.1d** - "Layer 4: Type-changing effects are applied."
- **CR 205.1a** - a type-changing effect that sets a new type replaces the
  object's existing ones of that kind, rather than adding to them - so the
  target stops being whatever creature type it was printed with.
- **CR 613.1e** - "Layer 5: Color-changing effects are applied."
- **CR 613.4b** - "Sublayer 7b: Effects that set power and/or toughness to a
  specific number or value are applied."
- **CR 613.6** - "If an effect should be applied in different layers and/or
  sublayers, the parts of the effect each apply in their appropriate ones."
- **CR 702.172a** - Spree: "Choose one or more modes. As an additional cost
  to cast this spell, pay the costs associated with those modes."
- **CR 700.2a** - a modal spell's chosen modes each resolve.

Metamorphic Blast's own first Spree mode - "Until end of turn, target
creature becomes a white Rabbit with base power and toughness 0/1." - prints
its duration *leading*, ahead of the "becomes" clause; the general reader
reads a leading or a trailing "until end of turn" the same way (leading
duration is moved to the end before the layer sentence is matched).

Startling Development (off-pool, confirmed with `scripts/add_card.py`,
Modern- and Pioneer-legal) is the proof this reads generally rather than
Metamorphic Blast's own exact sentence: a different colour (blue, not
white), a different creature type (Serpent, not Rabbit), and a different
base power/toughness (4/4, not 0/1), on a plain instant rather than a Spree
mode.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_metamorphic_blast_mode_one_alone_turns_the_target_into_a_white_rabbit():
    scenario = (
        Scenario()
        .player("alice", hand=["Metamorphic Blast"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Island", "Island")

    casting = scenario.cast("Metamorphic Blast")
    casting.choose_modes([1])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    board = scenario.game.computed_board()
    characteristics = board.of(bears)
    # CR 205.1a: the Bear subtype is replaced, not kept alongside Rabbit.
    assert characteristics.subtypes == ("Rabbit",)
    assert "W" in characteristics.colors
    assert "G" not in characteristics.colors
    assert characteristics.power_toughness == (0, 1)


def test_metamorphic_blast_both_modes_transform_the_creature_and_draw_the_player():
    """Modes 1 and 2 chosen together (CR 700.2a): mode 1's own "target
    creature" and mode 2's own "target player" are two independent targets
    of the same cast (CR 700.2f), resolved in the order printed."""
    scenario = (
        Scenario()
        .player("alice", hand=["Metamorphic Blast"], battlefield=["Island"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bob = scenario.player("bob")
    hand_before = len(bob.hand)
    sources = scenario.untapped_sources(*(["Island"] * 5))

    casting = scenario.cast("Metamorphic Blast")
    casting.choose_modes([1, 2])
    casting.choose_targets([bears, "bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    board = scenario.game.computed_board()
    characteristics = board.of(bears)
    assert characteristics.subtypes == ("Rabbit",)
    assert characteristics.power_toughness == (0, 1)
    assert len(bob.hand) == hand_before + 2


def test_startling_development_turns_a_bear_into_a_blue_serpent():
    """Off-pool, non-modal proof: a different colour, creature type and
    base power/toughness than Metamorphic Blast's own printing, and no
    Spree wrapper at all - the general reader, not the Spree card's exact
    sentence."""
    scenario = (
        Scenario()
        .player("alice", hand=["Startling Development"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Island", "Island")

    casting = scenario.cast("Startling Development")
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    board = scenario.game.computed_board()
    characteristics = board.of(bears)
    assert characteristics.subtypes == ("Serpent",)
    assert "U" in characteristics.colors
    assert "G" not in characteristics.colors
    assert characteristics.power_toughness == (4, 4)

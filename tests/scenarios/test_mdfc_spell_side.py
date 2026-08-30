"""Scenario: casting the spell face of a modal double-faced card (CR 712.8c,
712.8f, 712.11).

The defect this covers: `Game.resolve_top` read `spell.card.oracle_text` - the
raw Scryfall field - to find a resolving spell's effect. Scryfall leaves that
field null for a `modal_dfc` or `transform` layout and puts each face's own
text on `card_faces` instead, so every modal-DFC spell silently resolved to
nothing: it left the stack, went to the graveyard, and did whatever
`spell_fizzles`/state-based actions do around it, but its printed effect never
ran.

- **CR 712.11** - "A double-faced spell is cast with its front face up by
  default." A modal DFC's spell side is always its front face; casting it "as
  a land" is not a thing CR 712.12 describes (that is a battlefield-only
  special action), so the caster never gets to choose the back face for these
  cards while casting a spell.
- **CR 712.8c** - "Normally, a nonmodal double-faced spell has its front face
  up while on the stack and has only the characteristics of its front face."
- **CR 712.8f** - "While a modal double-faced spell is on the stack ... it has
  only the characteristics of the face that's up." Combined with CR 712.11,
  that face is always the front for every card fixture here.

`CardState.oracle_text` already reads `up_face` correctly (an earlier pass
fixed it); the bug was call sites still reaching past it to `card.oracle_text`
directly. Two more call sites had the identical defect and are fixed alongside
`Game.resolve_top`:

- `Game.cost_reduction_for` and `Game.static_cost_modifiers_for` read
  `spell.card.oracle_text`/`permanent.card.oracle_text` for a cost-changing
  clause, same blank field, same fix (`spell.oracle_text`/`permanent.oracle_text`).
- `machines/targeting.targeting_profile` and `machines/modes.modal_profile`
  parse a spell's targeting/modal shape straight off `Card.oracle_text` before
  a `CardState` exists at all, so they needed their own fallback -
  `Card.front_oracle_text`, mirroring the fallback `Casting.base_cost` already
  has for `mana_cost`. Without it, a modal-DFC spell had no target requirement
  read from its text: casting one and passing any target raised "too many
  targets ... at most 0" instead of accepting the printed target.

Sink into Stupor // Soporific Springs is the one of these four fixtures whose
spell-side text is a shape `machines/effects.py`'s clause parser already
reads end to end, so it is the only one proven all the way through here.
Shatterskull Smashing, Valakut Awakening and Turntimber Symbiosis are proven
up to the fix's actual boundary - their spell-side oracle text is now read
correctly (`effect_for` receives the real sentence, not `None`) - and then
marked `xfail`: none of their clause shapes exist in the parser yet
(`docs/engine-coverage.md`'s "Recording an announced division" row already
documents that `_DIVIDED_DAMAGE_RE` only reads a fixed damage amount, not an
"X damage, doubled if X is 6 or more" clause; the other two are an impulsive
draw-and-mill-back and a look-seven-put-a-creature-onto-the-battlefield
effect, neither of which has a registry row or a generic shape either). That
gap predates this fix and is unrelated to it - the same three sentences would
be just as unparsed on a normal, single-faced card.
"""

import pytest

from magic_cards_model.models import Zone

from .harness import Scenario


def _to_main(scenario: Scenario) -> None:
    from magic_cards_model.machines import Step

    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- Sink into Stupor: proven end to end -------------------------------------


def test_sink_into_stupor_bounces_a_spell_on_the_stack():
    """Sink into Stupor: "Return target spell or nonland permanent an
    opponent controls to its owner's hand."

    Before the fix, `effect_for` never saw this sentence at all -
    `spell.card.oracle_text` was `None` for this `modal_dfc` card, so the
    spell resolved and did nothing. Bob's Lightning Bolt, still on the stack
    targeting Alice's Grizzly Bears, is the target: a spell, controlled by an
    opponent, exactly the shape the printed text names.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sink into Stupor"],
            battlefield=["Island", "Island", "Island", "Grizzly Bears"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    _to_main(scenario)
    scenario.pass_priority("alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt"]
    scenario.pass_priority("bob")

    sources = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    sink = scenario.cast_and_resolve("Sink into Stupor", *sources, username="alice", targets=[bolt])

    assert bolt.zone is Zone.HAND, "the targeted spell went back to its owner's hand"
    assert bolt.controller_or_owner == "bob"
    assert sink.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD, "the Bolt that would have killed it never resolved"


# -- the other three: oracle text now reads correctly, effect still unmodelled --


@pytest.mark.xfail(
    strict=True,
    reason="Shatterskull Smashing's spell side now has its real oracle text read "
    "(the DFC-null-field bug this file covers is fixed - `effect_for` sees the "
    "printed sentence, not `None`), but `machines/effects.py` has no clause shape "
    'for "X damage divided as you choose among up to two targets, doubled if X is '
    "6 or more\" - `docs/engine-coverage.md`'s 'Recording an announced division' row "
    "already documents that `_DIVIDED_DAMAGE_RE` only reads a fixed damage amount, "
    "never an X. Unrelated to the DFC fix: the same sentence would be just as "
    "unparsed on a single-faced card.",
)
def test_shatterskull_smashing_deals_its_divided_damage():
    """Shatterskull Smashing: "deals X damage divided as you choose among up
    to two target creatures and/or planeswalkers."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Shatterskull Smashing"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")

    casting = scenario.cast("Shatterskull Smashing")
    casting.choose_targets([bears])
    casting.determine_cost(x_value=3)
    payment = casting.begin_paying()
    scenario.pay_with(
        payment,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain", "Mountain"),
    )
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD, "3 damage is lethal to a 2/2"


@pytest.mark.xfail(
    strict=True,
    reason="Valakut Awakening's spell side now has its real oracle text read (same "
    "DFC-null-field fix as the rest of this file), but its loot-for-more effect - "
    '"Put any number of cards from your hand on the bottom of your library, then '
    'draw that many cards plus one" - has no `EFFECTS` row and matches no shape '
    "`machines/effects.py`'s clause parser reads, so `effect_for` still returns "
    "None. Unrelated to the DFC fix: the same sentence is unparsed regardless of "
    "which face it is printed on.",
)
def test_valakut_awakening_loots_cards_away():
    """Valakut Awakening: put any number of hand cards on the bottom of the
    library, then draw that many plus one - net card advantage, not just a
    filter.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Valakut Awakening", "Forest", "Forest"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Forest"] * 10,
        )
        .build()
    )
    _to_main(scenario)
    hand_before_casting = len(scenario.player("alice").hand)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Valakut Awakening", *sources)

    # Casting Valakut Awakening itself removes it from hand (1 card, not a
    # target - "put any number of cards" is the caster's own choice during
    # resolution, CR 608.2d, not a CR 601.2c target). Putting both Forests on
    # the bottom and drawing three back (2 + 1) is +2 cards net.
    after = len(scenario.player("alice").hand)
    assert after == hand_before_casting - 1 + 3, "both Forests bottomed, three cards drawn back"


@pytest.mark.xfail(
    strict=True,
    reason="Turntimber Symbiosis's spell side now has its real oracle text read "
    "(same DFC-null-field fix as the rest of this file), but its impulsive-draw "
    'shape - "Look at the top seven cards of your library. You may put a creature '
    'card from among them onto the battlefield ..." - has no `EFFECTS` row and '
    "matches no generic clause shape either, so `effect_for` still returns None. "
    "Unrelated to the DFC fix: the same sentence is unparsed regardless of which "
    "face it is printed on.",
)
def test_turntimber_symbiosis_puts_a_creature_onto_the_battlefield():
    """Turntimber Symbiosis: look at the top seven, may put a creature onto
    the battlefield, cheap ones (mana value 3 or less) arrive with three
    extra +1/+1 counters.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Turntimber Symbiosis"],
            battlefield=["Forest"] * 7,
            library=["Grizzly Bears"] + ["Mountain"] * 6,
        )
        .build()
    )
    _to_main(scenario)

    sources = scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"
    )
    scenario.cast_and_resolve("Turntimber Symbiosis", *sources)

    bears = scenario.creature("Grizzly Bears", "alice")
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counters.plus_one_plus_one == 3, (
        "mana value 2, so it gets the three bonus counters"
    )

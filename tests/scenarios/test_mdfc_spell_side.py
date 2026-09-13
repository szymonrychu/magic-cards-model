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

Sink into Stupor // Soporific Springs was already the one of these four
fixtures whose spell-side text is a shape `machines/effects.py`'s clause
parser reads end to end. **W13** closes the other three, which used to be
`xfail` here up to the DFC fix's own boundary (their oracle text read
correctly, but no clause shape existed for their effects):

- **Shatterskull Smashing** - "X damage divided as you choose among up to two
  targets, doubled if X is 6 or more" needed CR 601.2d's announced division
  recorded somewhere real: `Casting.announce_division`, `CardState.division`,
  and `TargetingProfile.Division.amount` widened to `int | None` for a
  variable (X) amount, with `doubled_if_x_at_least` as the generalised
  "doubled if X is N or more" condition. `_parse_x_damage_divided_and_
  doubled_clause` in `machines/effects.py` reads X off `Game.cast_record` at
  resolution and pays out through the same `_deal_divided_damage_shares` a
  plain fixed-amount division (Electrolyze) now also goes through - the
  caster's real announcement if there is one, an even split otherwise, which
  is what keeps every existing Electrolyze scenario byte-for-byte unchanged.
- **Valakut Awakening** - "put any number of cards from your hand on the
  bottom of your library, then draw that many plus one" is CR 608.2d's plain
  choice among the caster's own hand, `CHOOSE_CARDS` widened with a new
  `Decision.exact=False` for CR 107.1c's "any number" (zero up to every card
  offered, default answer none rather than all of them).
- **Turntimber Symbiosis** - "look at the top seven ... may put a creature
  card ... onto the battlefield [with bonus counters if cheap] ... put the
  rest on the bottom in a random order" is `_parse_look_top_n_may_
  battlefield_creature_bonus_clause`, close kin to
  `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s
  "reveal the top four ... may put a permanent card into your hand" but with
  the battlefield (not the hand) as the kept card's destination and the
  library's bottom (not the graveyard) for the rest.

None of the three effects are keyed to these cards by name - each is a
generalised clause shape any future card in the same phrasing would also
reach, per this project's "parse off oracle text, no card-name keys" rule.
"""

from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

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


def test_shatterskull_smashing_deals_its_divided_damage():
    """Shatterskull Smashing: "deals X damage divided as you choose among up
    to two target creatures and/or planeswalkers."

    W13 gives CR 601.2d's announced division somewhere to live -
    `Casting.announce_division`, checked by `TargetingProfile.check_division`
    and carried to the stack on `CardState.division` - and reads Shatterskull
    Smashing's own X-based amount off `machines/targeting.py`'s `Division.
    amount=None` (variable) case. `casting.x_value` is set directly, ahead of
    `choose_targets`, because `Casting.targeting` substitutes X into the whole
    oracle text once it knows one (needed for "up to X target" cards) and
    would otherwise read this card's own "X damage divided ..." as "0 damage
    divided ...", same as CR 601.2b's real order: X is announced before
    targets.
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
    casting.x_value = 3
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


def test_shatterskull_smashing_divides_x_across_two_targets_as_announced():
    """The caster's own CR 601.2d announcement, not an even split: X=5 across
    a 2-toughness and a 3-toughness creature, 1 and 4, kills only the second.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Shatterskull Smashing"], battlefield=["Mountain"] * 7)
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")  # 2/2
    wolf = scenario.creature("Watchwolf", "bob")  # 3/3

    casting = scenario.cast("Shatterskull Smashing")
    casting.x_value = 5
    casting.choose_targets([bears, wolf])
    casting.announce_division([1, 4])
    casting.determine_cost(x_value=5)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Mountain"] * 7)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 1, "1 damage does not kill a 2/2"
    assert wolf.zone is Zone.GRAVEYARD, "4 damage kills a 3/3"


def test_shatterskull_smashing_doubles_at_x_six_or_more():
    """CR 601.2d's "twice X" branch: X=6 deals 12, not 6.

    Emrakul, the Promised End's printed 13 toughness survives either number,
    so the marked-damage count itself (not just "did it die") is what tells
    the doubled total apart from the plain one - and its own "protection from
    instants" does not apply, since Shatterskull Smashing is a sorcery.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Shatterskull Smashing"], battlefield=["Mountain"] * 8)
        .player("bob", battlefield=["Emrakul, the Promised End"])
        .build()
    )
    _to_main(scenario)
    emrakul = scenario.creature("Emrakul, the Promised End", "bob")

    casting = scenario.cast("Shatterskull Smashing")
    casting.x_value = 6
    casting.choose_targets([emrakul])
    casting.determine_cost(x_value=6)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*(["Mountain"] * 8)))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert emrakul.zone is Zone.BATTLEFIELD, "13 toughness survives even the doubled 12"
    assert emrakul.damage == 12, "X is 6, so twice X (12) is dealt, not X"


def test_valakut_awakening_loots_cards_away():
    """Valakut Awakening: put any number of hand cards on the bottom of the
    library, then draw that many plus one - a filter, not card advantage.

    W13: putting N cards on the bottom and then drawing N plus one always
    nets exactly +1 card relative to the moment before the bottoming (CR
    608.2c: the two sentences are one instruction, the draw count linked to
    however many actually went to the bottom) - so relative to *before
    casting the spell*, hand size is unchanged: the one card spent casting
    Valakut Awakening is exactly replaced by the "plus one" of the draw, no
    matter how many of the caster's own cards they choose to bottom first.
    That is what makes this a *filter* (find better cards, keep the same hand
    size) rather than card advantage the way a plain draw spell is. Which
    cards go is CR 608.2d's plain choice - `scenario.will_choose_cards`
    scripts both Forests so the test proves the choice actually moved them,
    not just that *some* draw happened.
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
    forests = [card for card in scenario.player("alice").hand if card.name == "Forest"]
    scenario.will_choose_cards(*forests, username="alice", source="Valakut Awakening")

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Valakut Awakening", *sources)

    # Casting Valakut Awakening itself removes it from hand (1 card, not a
    # target - "put any number of cards" is the caster's own choice during
    # resolution, CR 608.2d, not a CR 601.2c target). Bottoming both Forests
    # and drawing three back (2 + 1) leaves hand size exactly where it
    # started - the spell is a wash on card count, by design.
    after = len(scenario.player("alice").hand)
    assert after == hand_before_casting, (
        "bottoming N and drawing N+1 is always a net +1, wash overall"
    )
    assert all(forest.zone is Zone.LIBRARY for forest in forests), "both Forests actually moved"
    assert all(forest not in scenario.player("alice").hand for forest in forests)


def test_turntimber_symbiosis_puts_a_creature_onto_the_battlefield():
    """Turntimber Symbiosis: look at the top seven, may put a creature onto
    the battlefield, cheap ones (mana value 3 or less) arrive with three
    extra +1/+1 counters.

    W13: `_parse_look_top_n_may_battlefield_creature_bonus_clause`
    (`machines/effects.py`) reads this shape - CR 608.2d's plain "you may",
    close kin to `_merge_reveal_top_to_hand_rest_to_graveyard_clauses`'s
    "reveal the top four ... may put a
    permanent card into your hand", except the kept card's destination is the
    battlefield (CR 110.2a, no casting) and the rest go to the *bottom* of the
    library in a random order rather than the graveyard. With exactly one
    creature among the seven looked at, both the `MAY` and the `CHOOSE_CARDS`
    default answers (take it; the sole candidate) put it onto the battlefield
    with no scripting needed.
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
    assert bears.counter_count(Counter.PLUS_ONE) == 3, (
        "mana value 2, so it gets the three bonus counters"
    )

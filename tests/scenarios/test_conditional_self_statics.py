"""Scenario: FRA S9's conditional self-statics - a permanent's own static
ability, present or absent depending on something `LayerContext` carries
rather than the board alone.

`machines/layers.py` had no reader for any of these five shapes before this
file:

- **Skilled Battlecarver** (Reality Fracture), "During your turn, this
  creature has first strike." - whose turn it is
  (`LayerContext.active_player`). **Blood Burglar** (off-set, a different
  keyword) proves the shape: "During your turn, this creature has lifelink."
- **Mind Meanderer** (Reality Fracture), "This creature has vigilance as long
  as you control a Jace planeswalker." - a board-only condition
  (`SelfIfControls`). **Arisen Gorgon** (off-set, a different Planeswalker
  subtype and keyword) proves it: "This creature has deathtouch as long as
  you control a Liliana planeswalker."
- **Surveillance Phantasm** / **Whiplash Wordsmith** (Reality Fracture), "As
  long as you've scried or surveilled this turn, ... can attack as though it
  didn't have defender." / "As long as an opponent was dealt noncombat damage
  this turn, ... has flying and haste." - two different `Game.turn_facts`
  entries (`LayerContext.turn_facts`/`has_turn_fact`/
  `has_turn_fact_for_opponent`) read through the same shared parser and
  builder, each card proving the other is not a hardcode of its own name: one
  reads "you", the other "an opponent"; one grants a fixed ability line, the
  other an ordinary keyword list. Neither condition has a real-Magic static
  printing to add as a genuinely separate off-set card - both are this
  fictional set's own predicates - so the two FRA cards are each other's
  proof that the shared machinery is not keyed to either one's name.
- **Ruric Thar, Magecrusher** (Reality Fracture), "Ruric Thar has hexproof as
  long as they haven't dealt combat damage yet." - a per-object "this turn"
  fact (`Game.combat_damage_dealt_this_turn_by`, via
  `LayerContext.combat_damage_dealt_this_turn`), written by
  `machines/combat.py`'s `_deal_combat_damage` for every source that deals
  combat damage, not only Ruric Thar - proven generic by dealing combat
  damage with a second, unrelated creature and confirming that creature's own
  ledger entry, not Ruric Thar's name, is what the condition reads.
- **Theorix Metamage** / **Void Extrapolator** (Reality Fracture), *Threshold*
  - "This creature gets +1/+0 and has flying as long as there are seven or
  more cards in your graveyard." / "...gets +1/+1 as long as..." - handed
  over from S2 (whose own scope is each card's "enters prepared" half; this
  file covers only the static Threshold half, per the coordinator's
  instruction to "test the static parts on your branch"). The reader
  (`_GRAVEYARD_CARD_COUNT_GATED_SELF_STATIC_RE`/
  `_graveyard_card_count_gated_self_static_builder`) already existed from
  this file's earlier sections; **Werebear** (off-set, real Odyssey-block
  Threshold, `resolve_cards`-confirmed identical "this creature gets +N/+N
  ... as long as there are seven or more cards in your graveyard" wording,
  pump only, no keyword) proves the two fra cards are not what the parser was
  fitted to.

The rules these five rest on:

- **CR 604.2** - a static ability's effects "are active as long as the
  permanent with the ability remains on the battlefield and has the ability",
  and **CR 611.3a** - such an effect "isn't 'locked in'; it applies at any
  given moment to whatever its text indicates". Every one of these five is
  checked fresh every time `effects_for` runs (CR 613.5), never stored with a
  `Duration`.
- **CR 702.3b** - "A creature with defender can't attack" - the rule
  Surveillance Phantasm's grant overrides.
- **CR 702.11b** - "hexproof on a permanent means this permanent can't be the
  target of spells or abilities your opponents control" - Ruric Thar's own
  grant, gated on the combat-damage fact.
- **CR 510.2** - combat damage is dealt simultaneously, which is why
  `combat_damage_dealt_this_turn_by` is written once per source in
  `_deal_combat_damage`, the same call site deathtouch and lifelink already
  key off.
- **CR 207.2c** - *threshold* is one of the named ability words: no rules
  meaning of its own, so the whole of Theorix Metamage's and Void
  Extrapolator's abilities is the trailing "as long as..." condition once
  "Threshold — " is stripped.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import LayerContext, compute_board, static_effects
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice", **kwargs):
    return card_state(
        name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller, **kwargs
    )


def board_of(*permanents, context: LayerContext | None = None):
    """The characteristics of a battlefield with only its static abilities
    applied, over an optional `LayerContext` - CR 613.7a's timestamp order is
    the argument order."""
    cards = list(permanents)
    return compute_board(cards, static_effects(cards, context=context))


# --------------------------------------------------------------------------
# "During your turn, this creature has first strike." (Skilled Battlecarver)
# --------------------------------------------------------------------------


def test_skilled_battlecarver_has_first_strike_during_its_controllers_turn():
    battlecarver = permanent("Skilled Battlecarver")
    board = board_of(battlecarver, context=LayerContext(active_player="alice"))
    assert board.of(battlecarver).has_ability("First strike")


def test_skilled_battlecarver_has_no_first_strike_on_the_opponents_turn():
    battlecarver = permanent("Skilled Battlecarver")
    board = board_of(battlecarver, context=LayerContext(active_player="bob"))
    assert not board.of(battlecarver).has_ability("First strike")


def test_blood_burglar_grants_lifelink_during_its_controllers_turn_off_set():
    """Off-set proof: a different keyword (lifelink, not first strike)."""
    burglar = permanent("Blood Burglar")
    board = board_of(burglar, context=LayerContext(active_player="alice"))
    assert board.of(burglar).has_ability("Lifelink")

    board = board_of(burglar, context=LayerContext(active_player="bob"))
    assert not board.of(burglar).has_ability("Lifelink")


# --------------------------------------------------------------------------
# "This creature has vigilance as long as you control a Jace planeswalker."
# (Mind Meanderer)
# --------------------------------------------------------------------------


def flipped_jace(controller: str = "alice"):
    """ "Jace, Vryn's Prodigy" transformed into its back face, "Jace, Telepath
    Unbound" - a genuine Jace *planeswalker* (CR 712.8e: the back face is the
    one that has this text), unlike the front face's creature half.
    """
    jace = permanent("Jace, Vryn's Prodigy", controller=controller)
    jace.transform()
    return jace


def test_mind_meanderer_has_vigilance_while_controlling_a_jace_planeswalker():
    meanderer = permanent("Mind Meanderer")
    jace = flipped_jace()
    assert not board_of(meanderer).of(meanderer).has_ability("Vigilance")
    assert board_of(meanderer, jace).of(meanderer).has_ability("Vigilance")


def test_mind_meanderer_ignores_a_jace_that_is_not_a_planeswalker():
    meanderer = permanent("Mind Meanderer")
    creature_jace = permanent("Jace, Vryn's Prodigy")
    assert not board_of(meanderer, creature_jace).of(meanderer).has_ability("Vigilance")


def test_mind_meanderer_ignores_a_planeswalker_that_is_not_named_jace():
    meanderer = permanent("Mind Meanderer")
    other_walker = permanent("Ashiok, Dream Render")
    assert not board_of(meanderer, other_walker).of(meanderer).has_ability("Vigilance")


def test_mind_meanderer_ignores_an_opponents_jace():
    meanderer = permanent("Mind Meanderer")
    theirs = flipped_jace(controller="bob")
    assert not board_of(meanderer, theirs).of(meanderer).has_ability("Vigilance")


def test_arisen_gorgon_deathtouch_while_controlling_a_liliana_planeswalker_off_set():
    """Off-set proof: a different Planeswalker subtype (Liliana, not Jace)
    and a different keyword (deathtouch, not vigilance)."""
    gorgon = permanent("Arisen Gorgon")
    liliana = permanent("Liliana, Waker of the Dead")

    assert not board_of(gorgon).of(gorgon).has_ability("Deathtouch")
    assert board_of(gorgon, liliana).of(gorgon).has_ability("Deathtouch")


# --------------------------------------------------------------------------
# Turn-fact-gated grants: Surveillance Phantasm and Whiplash Wordsmith
# --------------------------------------------------------------------------


def test_surveillance_phantasm_can_attack_once_its_controller_scried_this_turn():
    phantasm = permanent("Surveillance Phantasm")
    context = LayerContext(turn_facts={"scried_or_surveilled": frozenset({"alice"})})
    assert (
        board_of(phantasm, context=context)
        .of(phantasm)
        .has_ability("Can attack as though it didn't have defender.")
    )


def test_surveillance_phantasm_cannot_attack_with_no_scry_or_surveil_yet():
    phantasm = permanent("Surveillance Phantasm")
    assert (
        not board_of(phantasm)
        .of(phantasm)
        .has_ability("Can attack as though it didn't have defender.")
    )


def test_surveillance_phantasm_reads_its_own_controllers_scry_not_an_opponents():
    phantasm = permanent("Surveillance Phantasm")
    context = LayerContext(turn_facts={"scried_or_surveilled": frozenset({"bob"})})
    assert (
        not board_of(phantasm, context=context)
        .of(phantasm)
        .has_ability("Can attack as though it didn't have defender.")
    )


def test_surveillance_phantasm_actually_lets_a_defender_attack_end_to_end():
    """Wired all the way through `Game`: a real `scry` call records the fact
    (`Game.scry` -> `record_turn_fact`), `_compute_board` carries it into
    `LayerContext`, and `attack_refusal` reads the granted text off the
    computed board (CR 613.5) instead of the printed defender keyword alone.
    """
    scenario = (
        Scenario().player("alice", battlefield=["Surveillance Phantasm"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    phantasm = scenario.creature("Surveillance Phantasm", "alice")

    assert not scenario.can_attack(phantasm), "defender, and nothing scried yet"

    scenario.game.scry("alice", 1, source="Surveillance Phantasm")

    assert scenario.can_attack(phantasm)


def test_whiplash_wordsmith_gains_flying_and_haste_after_an_opponent_takes_noncombat_damage():
    wordsmith = permanent("Whiplash Wordsmith")
    context = LayerContext(turn_facts={"dealt_noncombat_damage": frozenset({"bob"})})
    board = board_of(wordsmith, context=context)
    assert board.of(wordsmith).has_ability("Flying")
    assert board.of(wordsmith).has_ability("Haste")


def test_whiplash_wordsmith_stays_grounded_with_no_noncombat_damage_dealt():
    wordsmith = permanent("Whiplash Wordsmith")
    assert not board_of(wordsmith).of(wordsmith).has_ability("Flying")


def test_whiplash_wordsmith_ignores_its_own_controller_taking_noncombat_damage():
    """ "An opponent" - alice's own noncombat damage does not turn this on."""
    wordsmith = permanent("Whiplash Wordsmith")
    context = LayerContext(turn_facts={"dealt_noncombat_damage": frozenset({"alice"})})
    assert not board_of(wordsmith, context=context).of(wordsmith).has_ability("Flying")


def test_whiplash_wordsmith_actually_flies_after_real_noncombat_damage_end_to_end():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Whiplash Wordsmith"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wordsmith = scenario.creature("Whiplash Wordsmith", "alice")
    bob = scenario.player("bob")

    assert not scenario.game.characteristics_of(wordsmith).has_ability("Flying")

    scenario.game.deal_damage(bob, 1)

    assert scenario.game.characteristics_of(wordsmith).has_ability("Flying")
    assert scenario.game.characteristics_of(wordsmith).has_ability("Haste")


# --------------------------------------------------------------------------
# "Ruric Thar has hexproof as long as they haven't dealt combat damage yet."
# --------------------------------------------------------------------------


def test_ruric_thar_has_hexproof_before_it_deals_combat_damage():
    ruric = permanent("Ruric Thar, Magecrusher")
    assert board_of(ruric).of(ruric).has_ability("Hexproof")


def test_ruric_thar_loses_hexproof_after_it_deals_combat_damage():
    ruric = permanent("Ruric Thar, Magecrusher")
    context = LayerContext(combat_damage_dealt_this_turn=frozenset({ruric.id}))
    assert not board_of(ruric, context=context).of(ruric).has_ability("Hexproof")


def test_ruric_thars_ledger_entry_is_by_object_id_not_by_name():
    """The condition reads `source.id`, never the card's own name - a
    *different* creature having dealt combat damage this turn must not turn
    Ruric Thar's hexproof off."""
    ruric = permanent("Ruric Thar, Magecrusher")
    bears = permanent("Grizzly Bears")
    context = LayerContext(combat_damage_dealt_this_turn=frozenset({bears.id}))
    assert board_of(ruric, bears, context=context).of(ruric).has_ability("Hexproof")


def test_ruric_thar_loses_hexproof_after_real_combat_damage_end_to_end():
    """Wired through `machines/combat.py`'s `_deal_combat_damage`, which
    records the source for *every* creature that deals combat damage, proven
    here with a second attacker (Grizzly Bears) whose own combat damage must
    not be what flips Ruric Thar's ledger entry."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ruric Thar, Magecrusher", "Grizzly Bears"])
        .player("bob", battlefield=["Runeclaw Bear"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ruric = scenario.creature("Ruric Thar, Magecrusher", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    assert scenario.game.characteristics_of(ruric).has_ability("Hexproof")

    scenario.attack_with(bears, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert bears.id in scenario.game.combat_damage_dealt_this_turn_by
    assert scenario.game.characteristics_of(ruric).has_ability("Hexproof"), (
        "a different creature's combat damage does not touch Ruric Thar's own ledger entry"
    )

    scenario.start_at(Step.COMBAT_DAMAGE)
    scenario.attack_with(ruric, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()

    assert ruric.id in scenario.game.combat_damage_dealt_this_turn_by
    assert not scenario.game.characteristics_of(ruric).has_ability("Hexproof")


# --------------------------------------------------------------------------
# Threshold: "This creature gets +N/+N [and has <keyword>] as long as there
# are seven or more cards in your graveyard." (Theorix Metamage; Void
# Extrapolator) - handed over from S2's Prepare work (their own "enters
# prepared" clause is S2's, tested there; this file covers only the static
# half). Werebear (off-set, Odyssey block) proves the shared parser reads the
# graveyard-count condition itself rather than either fra card's name -
# `resolve_cards` confirms its oracle text is the identical ability-word
# shape, pump only, no keyword.
# --------------------------------------------------------------------------


def sevencard_graveyard_context(controller: str = "alice") -> LayerContext:
    filler = tuple(card_state("Mountain", zone=Zone.GRAVEYARD) for _ in range(7))
    return LayerContext(graveyard_by_controller={controller: filler})


def test_theorix_metamage_gets_pump_and_flying_at_threshold():
    theorix = permanent("Theorix Metamage")
    board = board_of(theorix, context=sevencard_graveyard_context())
    chars = board.of(theorix)
    assert chars.power == int(theorix.card.power) + 1
    assert chars.toughness == int(theorix.card.toughness)
    assert chars.has_ability("Flying")


def test_theorix_metamage_stays_vanilla_below_threshold():
    theorix = permanent("Theorix Metamage")
    board = board_of(theorix)
    chars = board.of(theorix)
    assert chars.power == int(theorix.card.power)
    assert not chars.has_ability("Flying")


def test_void_extrapolator_gets_pump_at_threshold_no_keyword():
    """A different pump and no keyword at all - proves the builder does not
    assume a keyword clause is always present."""
    extrapolator = permanent("Void Extrapolator")
    board = board_of(extrapolator, context=sevencard_graveyard_context())
    chars = board.of(extrapolator)
    assert chars.power == int(extrapolator.card.power) + 1
    assert chars.toughness == int(extrapolator.card.toughness) + 1


def test_void_extrapolator_stays_vanilla_below_threshold():
    extrapolator = permanent("Void Extrapolator")
    board = board_of(extrapolator)
    chars = board.of(extrapolator)
    assert chars.power == int(extrapolator.card.power)
    assert chars.toughness == int(extrapolator.card.toughness)


def test_werebear_gets_pump_at_threshold_off_set():
    """Off-set proof: a real Odyssey-block Threshold creature, same "this
    creature gets +N/+N ... as long as there are seven or more cards in your
    graveyard" shape, pump only."""
    werebear = permanent("Werebear")
    board = board_of(werebear, context=sevencard_graveyard_context())
    chars = board.of(werebear)
    assert chars.power == int(werebear.card.power) + 3
    assert chars.toughness == int(werebear.card.toughness) + 3


def test_theorix_metamage_reads_its_own_controllers_graveyard_not_an_opponents():
    theorix = permanent("Theorix Metamage")
    board = board_of(theorix, context=sevencard_graveyard_context(controller="bob"))
    assert not board.of(theorix).has_ability("Flying")


def test_theorix_metamage_actually_crosses_threshold_end_to_end():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Theorix Metamage"],
            graveyard=["Mountain"] * 6,
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theorix = scenario.creature("Theorix Metamage", "alice")

    assert not scenario.game.characteristics_of(theorix).has_ability("Flying")

    scenario.game.put_into_graveyard(scenario.player("alice").library[0])

    assert scenario.game.characteristics_of(theorix).has_ability("Flying")
    assert scenario.game.characteristics_of(theorix).power == int(theorix.card.power) + 1

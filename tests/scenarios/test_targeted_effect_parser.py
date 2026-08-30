"""Scenario: single-clause TARGETED effects, read off a card's own printed
text instead of a per-card `machines/effects.py` table row.

Wave 2 of the effect-parser work: wave 1
(`tests/scenarios/test_player_effect_parser.py`) covers untargeted player
effects; this wave covers `Destroy target X.`, `Exile target X.`, `<Source>
deals N damage to target X.` (and "to any target"), `Return target X to its
owner's hand.`, `Tap`/`Untap target X.`, and `Put N +1/+1 counters on target
X.` The restriction is enforced by `machines/targeting.py`'s own parser, the
same one `Game.legal_target` rechecks on resolution - this file exists to
prove that enforcement actually reaches the board, not just the unit-level
parser in `tests/test_targeted_effects.py`.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 608.2b** - "If the spell or ability specifies targets, it checks
  whether the targets are still legal. A target that's no longer in the zone
  it was in when it was targeted is illegal." A spell whose only target
  becomes illegal this way does not resolve at all.
- **CR 702.12b** - "A permanent with indestructible can't be destroyed."
- **CR 701.8a** - "To destroy a permanent, move it from the battlefield to
  its owner's graveyard."
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is" - indestructible has nothing to say about it.
- **CR 701.26a/b** - to tap/untap a permanent, turn it sideways/upright.
- **CR 115.4** - "any target" reaches a creature, player, planeswalker, or
  battle.
- **CR 118.8a** - an additional cost is paid on the way to the stack, before
  the spell's own effect - Bone Splinters' sacrifice.
- **CR 603.3d** - a triggered ability's targets are chosen "following the
  rules for announcing targets" as it goes on the stack - the same check a
  spell's targets get, which is why `choose_trigger_targets` raises for an
  illegal one instead of silently recording it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostPayment, TotalCost, sacrifice_cost
from magic_cards_model.machines.targeting import profile_for_text
from magic_cards_model.models import Zone
from tests.cards import card

from .harness import Scenario

# --------------------------------------------------------------------------
# Destroy (CR 701.8a) - and an additional cost stripped ahead of the clause
# --------------------------------------------------------------------------


def test_bone_splinters_destroys_its_target_after_the_sacrifice_is_paid():
    """Bone Splinters: "As an additional cost to cast this spell, sacrifice a
    creature. Destroy target creature." The cost line is not part of the
    effect (CR 118.8a) and is stripped before the "Destroy target creature."
    clause is read.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Bone Splinters"], battlefield=["Swamp", "Grizzly Bears"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fodder = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Bone Splinters")
    casting.add_additional_cost(TotalCost.of(None, sacrifice_cost(fodder)))
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert fodder.zone is Zone.GRAVEYARD, "the additional cost was paid"
    assert target.zone is Zone.GRAVEYARD, "the effect destroyed its target"


def test_ravenous_chupacabra_destroys_a_creature_an_opponent_controls():
    """Ravenous Chupacabra: "When this creature enters, destroy target
    creature an opponent controls." The controller restriction comes from
    Chupacabra's own printed text (CR 603.3d), read the same way
    `Anafenza, the Foremost`'s "you control" is below.

    Whether *announcing* an illegal target is refused this early depends on
    `Game.why_cannot_target_with_trigger` finding the source card among the
    battlefield or the stack (CR 603.6a) - which it cannot for an
    enters-the-battlefield trigger queued before the creature is even cast.
    That gap belongs to `Game.choose_trigger_targets`, not to this wave's
    parser, and `test_anafenzas_trigger_cannot_target_an_untapped_creature`
    below proves the restriction *is* read correctly once the source already
    exists on the battlefield.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ravenous Chupacabra"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    opponents_creature = scenario.creature("Elvish Mystic", "bob")

    scenario.choose_trigger_targets("Ravenous Chupacabra", [opponents_creature])
    scenario.cast_and_resolve(
        "Ravenous Chupacabra", *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()

    assert opponents_creature.zone is Zone.GRAVEYARD


def test_destroy_does_not_affect_an_indestructible_permanent():
    """Ravenous Chupacabra's destroy is refused by CR 702.12b for an
    indestructible permanent - Ulamog, the Ceaseless Hunger stays right where
    it is, undamaged in the bookkeeping sense: nothing moved, nothing died.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ravenous Chupacabra"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", hand=["Ulamog, the Ceaseless Hunger"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.put_onto_battlefield("Ulamog, the Ceaseless Hunger", "bob")

    scenario.choose_trigger_targets("Ravenous Chupacabra", [ulamog])
    scenario.cast_and_resolve(
        "Ravenous Chupacabra", *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()

    assert ulamog.zone is Zone.BATTLEFIELD, "indestructible can't be destroyed (CR 702.12b)"


# --------------------------------------------------------------------------
# Exile (CR 701.13a) - ignores indestructible entirely
# --------------------------------------------------------------------------


def test_utter_end_exiles_a_nonland_permanent_even_when_it_is_indestructible():
    scenario = (
        Scenario()
        .player("alice", hand=["Utter End"], battlefield=["Plains", "Swamp", "Forest", "Mountain"])
        .player("bob", hand=["Ulamog, the Ceaseless Hunger"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ulamog = scenario.put_onto_battlefield("Ulamog, the Ceaseless Hunger", "bob")

    sources = scenario.untapped_sources("Plains", "Swamp", "Forest", "Mountain")
    scenario.cast_and_resolve("Utter End", *sources, targets=[ulamog])

    assert ulamog.zone is Zone.EXILE, "exile does not check indestructible"


def test_utter_end_cannot_target_a_land():
    """ "Target nonland permanent" - `machines/targeting.py` reads the
    "non-" prefix (CR 300.1's list of card types) and refuses a land.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utter End"], battlefield=["Plains", "Swamp", "Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.cast("Utter End", targets=[forest])


# --------------------------------------------------------------------------
# A target that becomes illegal before resolution does not resolve (CR 608.2b)
# --------------------------------------------------------------------------


def test_a_spell_whose_only_target_leaves_the_battlefield_before_resolution_fizzles():
    """CR 608.2b: "A target that's no longer in the zone it was in when it
    was targeted is illegal." Utter End's only target is exiled by something
    else while the spell waits on the stack; the spell itself then does
    nothing and simply goes to its owner's graveyard, rather than raising or
    exiling something it was never told to.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Utter End"], battlefield=["Plains", "Swamp", "Forest", "Mountain"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "bob")
    sources = scenario.untapped_sources("Plains", "Swamp", "Forest", "Mountain")
    spell = scenario.cast_onto_stack("Utter End", *sources, targets=[target])

    scenario.game.exile_permanent(target)  # something else removes it in response

    resolved = scenario.resolve_top()

    assert resolved is spell
    assert spell.zone is Zone.GRAVEYARD, "the spell itself still goes to the graveyard"
    assert target.zone is Zone.EXILE, "nothing tried to move it a second time"


# --------------------------------------------------------------------------
# Damage to any target (CR 115.4) - newly reachable with no table row
# --------------------------------------------------------------------------


def test_lightning_bolt_still_deals_damage_with_its_registry_row_removed():
    """Lightning Bolt no longer has an `EFFECTS` row (see `machines/effects.py`)
    - `parse_targeted_effect_for_spell` reaches it instead. Aimed at a player,
    the way "any target" (CR 115.4) most often gets used.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=["bob"])

    assert scenario.player("bob").life == 17


def test_footlight_fiends_dies_trigger_deals_damage_to_any_target():
    """Footlight Fiend never had a table row at all - "When this creature
    dies, it deals 1 damage to any target" reaches the model for the first
    time through this wave's fallback.
    """
    scenario = Scenario().player("alice", battlefield=["Footlight Fiend"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "alice")
    scenario.choose_trigger_targets("Footlight Fiend", ["bob"])

    scenario.game.destroy(fiend)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19


# --------------------------------------------------------------------------
# Return to hand (CR 701.19)
# --------------------------------------------------------------------------


def test_aether_adept_returns_its_target_to_its_owners_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Aether Adept"], battlefield=["Island", "Island", "Island"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "bob")
    scenario.choose_trigger_targets("Aether Adept", [target])

    scenario.cast_and_resolve(
        "Aether Adept", *scenario.untapped_sources("Island", "Island", "Island")
    )
    scenario.pass_until_resolved()

    assert target.zone is Zone.HAND
    assert scenario.game.find_owner(target).username == "bob"


# --------------------------------------------------------------------------
# Tap / Untap (CR 701.26a, 701.26b)
# --------------------------------------------------------------------------


def test_icy_manipulator_taps_its_target():
    """ "Tap target artifact, creature, or land."

    This comma-separated three-noun list used to be a known gap:
    `_read_phrase` only joined nouns across a bare "or", not across the
    Oxford comma before it, so "artifact, creature, or land" came back
    `understood=True` with `card_types={ARTIFACT}` alone - fixed in
    `machines/targeting.py`'s noun-reading loop (see
    `scenarios/test_oxford_comma_target_lists.py` for the dedicated
    coverage). This test still only targets an artifact - the fix is proven
    elsewhere, not reshaped into here.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Icy Manipulator", "Swamp"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    icy = scenario.find("Icy Manipulator", Zone.BATTLEFIELD, "alice")
    target = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    assert not target.tapped

    scenario.activate(icy, *scenario.untapped_sources("Swamp"), targets=[target])
    scenario.pass_until_resolved()

    assert target.tapped


def test_kioras_follower_untaps_another_target_permanent():
    """ "Untap another target permanent." - "another" sits before the word
    "target" (`TargetRequirement.excludes_source`, `machines/targeting.py`) and
    just means Kiora's Follower cannot target itself; a different permanent is
    still a legal target.
    """
    scenario = Scenario().player("alice", battlefield=["Kiora's Follower", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kiora = scenario.creature("Kiora's Follower", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    forest.tap()
    assert forest.tapped

    scenario.activate(kiora, targets=[forest])
    scenario.pass_until_resolved()

    assert not forest.tapped


# --------------------------------------------------------------------------
# Counters (CR 122.1)
# --------------------------------------------------------------------------


def test_anafenza_puts_a_counter_on_another_tapped_creature_she_controls():
    """Anafenza, the Foremost: "Whenever Anafenza attacks, put a +1/+1
    counter on another target tapped creature you control." Two restrictions
    at once: "tapped" (a game-state adjective) and "you control".
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Anafenza, the Foremost", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anafenza = scenario.creature("Anafenza, the Foremost", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    scenario.choose_trigger_targets("Anafenza, the Foremost", [bears])

    scenario.attack_with(anafenza)
    scenario.pass_until_resolved()

    assert bears.counters == {"+1/+1": 1}


def test_anafenzas_trigger_cannot_target_an_untapped_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Anafenza, the Foremost", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not bears.tapped

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Anafenza, the Foremost", [bears])


# --------------------------------------------------------------------------
# The activated-ability half of Goblin Bombardment, without its old row
# --------------------------------------------------------------------------


def test_goblin_bombardment_still_deals_damage_with_its_registry_row_removed():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Bombardment", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Grizzly Bears", "alice")

    scenario.activate(bombardment, sacrificing=[fodder], targets=["bob"])
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 19
    assert fodder.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Fail-closed on the board, not just at the parser
# --------------------------------------------------------------------------


def test_abrupt_decay_destroys_a_legal_target_end_to_end():
    """Abrupt Decay's mana-value restriction used to be dropped by
    `machines/targeting.py` (see `tests/test_targeted_effects.py`) - fixed
    now: `TargetRequirement` reads and enforces the comparison for real, and
    `_targets_understood` no longer blanket-refuses on the word "mana value".
    Elvish Mystic (mana value 1) is a legal target, so the destroy goes
    through end to end, not just at the parser.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Abrupt Decay"], battlefield=["Swamp", "Forest"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "bob")

    scenario.cast_and_resolve(
        "Abrupt Decay", *scenario.untapped_sources("Swamp", "Forest"), targets=[target]
    )

    assert target.zone is Zone.GRAVEYARD


def test_abrupt_decay_refuses_a_target_over_the_mana_value_line():
    """The comparison cuts both ways: a legal target (mana value 2 or less)
    reads as legal and one over the line (Craterhoof Behemoth, mana value 8)
    is refused - both against the actual `TargetRequirement`
    `machines/targeting.py` reads off Abrupt Decay's own printed text, so
    this is the same restriction `Game.legal_target` enforces on resolution
    (CR 608.2b), not a hand-built stand-in for it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Craterhoof Behemoth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    profile = profile_for_text(card("Abrupt Decay").oracle_text)
    (requirement,) = profile.requirements
    bears = scenario.creature("Grizzly Bears", "bob")
    behemoth = scenario.creature("Craterhoof Behemoth", "bob")

    assert requirement.rejects(bears, "alice", scenario.game) is None, "mana value 2 is legal"
    assert requirement.rejects(behemoth, "alice", scenario.game) is not None, (
        "mana value 8 is over the line"
    )


def test_faerie_macabre_exiles_a_graveyard_card_end_to_end():
    """ "Discard this card: Exile up to two target cards from graveyards."
    used to be refused outright: `_targets_understood` forced every exile
    ability's `zones` to be exactly `{Zone.BATTLEFIELD}`, and
    `exile_ability_targets` separately hard-filtered to
    `Zone.BATTLEFIELD` too. CR 406.2/701.13a exile "from whatever zone it's
    currently in", so both are relaxed now, and `Game.legal_target` reads the
    ability's own printed text to recheck the target is still where it needs
    to be on resolution (CR 608.2b) - Raise Dead is the other card the
    inventory named for this trap; its "to your hand" phrasing still fails
    `_RETURN_TARGET_RE` outright, for an unrelated reason.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Faerie Macabre"])
        .player("bob", library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.LIBRARY, "bob")
    scenario.player("bob").zones[Zone.LIBRARY].remove(bears)
    scenario.player("bob").add(bears, Zone.GRAVEYARD)
    faerie_macabre = scenario.find("Faerie Macabre", Zone.HAND, "alice")

    # Faerie Macabre's ability functions from hand, and `why_cannot_activate`
    # gates every activation on being on the battlefield (CR 113.6) - the same
    # pre-existing, documented gap `test_self_referential_costs.py` routes
    # around for Boseiju's Channel. `activate_ability` itself carries no such
    # gate, so paying the cost directly and calling it reaches the real path.
    total = scenario.game.activation_cost(faerie_macabre, 0, "alice")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice")
    payment.pay()
    scenario.game.activate_ability(faerie_macabre, 0, "alice", targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE
    assert faerie_macabre.zone is Zone.GRAVEYARD, "the discard cost is still paid"


def test_keen_eyed_curator_exiles_a_graveyard_card_end_to_end():
    """ "{1}: Exile target card from a graveyard." - the same graveyard-target
    shape as Faerie Macabre, on an activated ability that stays on the
    battlefield the whole time (so none of Faerie Macabre's from-hand
    activation wrinkle applies here).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Keen-Eyed Curator", "Forest"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    curator = scenario.creature("Keen-Eyed Curator", "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    total = scenario.game.activation_cost(curator, 0, "alice")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice")
    payment.auto_tap(scenario.untapped_sources("Forest", username="alice"))
    payment.pay()
    scenario.game.activate_ability(curator, 0, "alice", targets=[bears])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE


def test_tormod_and_bojuka_now_exile_the_targeted_players_graveyard():
    """Tormod's Crypt and Bojuka Bog say "exile target player's graveyard" -
    they target the *player*, not a card (`allows_cards=False`), which is why
    `exile_ability_targets`'s `isinstance(target, CardState)` check can never
    reach this shape. That is no longer a silent gap: `exile_target_players_
    graveyard` (`machines/effects.py`) is the clause `_parse_targeted_clause`
    now routes "target player's graveyard" phrases to, ahead of the generic
    exile-target regex. See `tests/scenarios/test_exile_a_players_graveyard.py`
    for the corner cases (empty graveyard, own graveyard, ordering).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tormod's Crypt"])
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crypt = scenario.find("Tormod's Crypt", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    total = scenario.game.activation_cost(crypt, 0, "alice")
    payment = CostPayment.for_total(total, game=scenario.game, payer="alice")
    payment.pay()
    scenario.game.activate_ability(crypt, 0, "alice", targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE, "targeting the player now reaches their graveyard"


def test_prismatic_ending_resolves_without_exiling_a_legal_looking_target():
    """Prismatic Ending: "Exile target nonland permanent if its mana value is
    less than or equal to the number of colors of mana spent to cast this
    spell." names a count `_extract_comparison` cannot pin down at all (no
    digit, no X) - `profile_for_text` reports `understood=False` for the
    whole clause, so `_targets_understood` refuses before its own "if" check
    is even reached, retirement of the old blanket mana-value/power/toughness
    guard notwithstanding. Elvish Mystic (mana value 1) would satisfy the
    comparison in the best case, but the spell still resolves and does
    nothing to it (CR 608.2c has to put the spell somewhere) - a wrong game
    state that looks right would be worse than this silence.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismatic Ending"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Prismatic Ending")
    casting.choose_targets([target])
    casting.determine_cost(x_value=1)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert target.zone is Zone.BATTLEFIELD, "an unreadable comparison is refused, not widened"

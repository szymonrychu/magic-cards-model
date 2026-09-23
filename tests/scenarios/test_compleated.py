"""Compleated (CR 702.150a): a planeswalker's own entering-loyalty replacement.

Every rule cited here was read in full from `.rules/MagicCompRules.txt` (the
Comprehensive Rules effective September 25, 2026) with `mise run rules:find`
in the session that wrote this file.

- **CR 702.150a** - "Compleated is a static ability found on some planeswalker
  cards. Compleated means 'If this permanent would enter with one or more
  loyalty counters on it and the player who cast it chose to pay life for any
  part of its cost represented by Phyrexian mana symbols, it instead enters
  the battlefield with that many loyalty counters minus two for each of those
  mana symbols.'"
- **CR 107.4f** - "A Phyrexian mana symbol represents a cost that can be paid
  either with one mana of its color or by paying 2 life ... A hybrid
  Phyrexian mana symbol represents a cost that can be paid with one mana of
  either of its component colors or by paying 2 life."
- **CR 118.13a** - the choice of how to pay a symbol payable multiple ways is
  the caster's own, made as the spell is proposed (CR 601.2b).
- **CR 601.2h** - the total cost is paid at CR 601.2h, the same moment every
  other `CastRecord` field (`mana_spent`, `kicked`, ...) is filled from the
  settled payment.
- **CR 306.5a/306.5b/306.5c** - a planeswalker's printed loyalty, its own
  "enters with N loyalty counters" intrinsic ability ("This ability creates a
  replacement effect (see rule 614.1c)" - the same CR 614 machinery
  compleated's own replacement stacks with), and that its loyalty on the
  battlefield is its counters.
- **CR 707.10/707.2** - a copy of a spell "isn't cast", so a copy never
  carries a payment to read a Phyrexian life count off.
- **CR 306.8/120.3c** - damage removes loyalty counters; **CR 704.5i** - a
  planeswalker at 0 loyalty is a state-based action.

**The proofs.** Nahiri, the Unforgiving and Ajani, Sleeper Agent both print
one Phyrexian symbol (one plain colored, one hybrid) and are the two
proof cards this task named; Tamiyo, Compleated Sage is the reported card
(previously tested paying only with mana, never with life). Nissa, Ascended
Animist - not in the deck pool, added for this file - is the one real
printing with *two* compleated symbols on the same cost, and is what proves
"minus two for each" is a count, not a flag: paying life for only one of her
two symbols removes exactly one instance's worth, not both.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

NAHIRI = "Nahiri, the Unforgiving"
AJANI = "Ajani, Sleeper Agent"
TAMIYO = "Tamiyo, Compleated Sage"
NISSA = "Nissa, Ascended Animist"


def _board(name: str, lands: list[str], *, life: int = 20) -> Scenario:
    """Alice holds one compleated planeswalker, with exactly enough lands to
    pay its cost in full - no more, so a test that taps fewer than all of
    them genuinely leaves a symbol short of mana rather than merely choosing
    not to use what is lying around unused."""
    return (
        Scenario()
        .player("alice", life=life, hand=[name], battlefield=list(lands))
        .player("bob")
        .build()
    )


# -- CR 306.5b's baseline: cast and paid entirely with mana -----------------


def test_paying_the_phyrexian_symbol_with_mana_enters_at_full_printed_loyalty():
    """Nahiri, {1}{R}{R/W/P}{W}: every land tapped, so the {R/W/P} symbol is
    paid with {R} or {W} rather than life (CR 118.13a's choice defaults to
    whichever resource is there). CR 702.150a never applies - no life was
    paid for any Phyrexian symbol - so CR 306.5b's plain printed loyalty (5)
    stands."""
    scenario = _board(NAHIRI, ["Mountain", "Mountain", "Plains", "Plains"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains", "Plains")

    nahiri = scenario.cast_and_resolve(NAHIRI, *lands)

    assert nahiri.loyalty == 5, "CR 306.5b: printed loyalty, nothing paid with life"
    assert scenario.player("alice").life == 20
    record = scenario.game.cast_record(nahiri)
    assert record.phyrexian_life_symbols_paid == 0


# -- Nahiri, the Unforgiving (proof card) ------------------------------------


def test_nahiri_paying_life_for_its_phyrexian_symbol_enters_two_lower():
    """Nahiri, {1}{R}{R/W/P}{W}, printed loyalty 5: tap only the three lands
    that cover {1}{R}{W}, leaving the {R/W/P} symbol with no mana to pay it -
    CR 107.4f pays the shortfall with 2 life, and CR 702.150a takes two
    loyalty counters off as she enters, landing at 3."""
    scenario = _board(NAHIRI, ["Mountain", "Mountain", "Plains", "Plains"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains")

    nahiri = scenario.cast_and_resolve(NAHIRI, *lands)

    assert scenario.player("alice").life == 18, "CR 107.4f: 2 life for the one symbol"
    assert nahiri.loyalty == 3, "CR 702.150a: 5 printed minus 2"
    assert nahiri.counter_count(Counter.LOYALTY) == 3
    record = scenario.game.cast_record(nahiri)
    assert record.phyrexian_life_symbols_paid == 1


# -- Ajani, Sleeper Agent (proof card, hybrid Phyrexian) ---------------------


def test_ajani_sleeper_agent_hybrid_phyrexian_life_payment():
    """Ajani, {1}{G}{G/W/P}{W}, printed loyalty 4: the same shape as Nahiri
    but on a *hybrid* Phyrexian symbol (G or W or 2 life) - CR 107.4f's
    second sentence, not its first."""
    scenario = _board(AJANI, ["Forest", "Forest", "Plains", "Plains"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest", "Plains")

    ajani = scenario.cast_and_resolve(AJANI, *lands)

    assert scenario.player("alice").life == 18
    assert ajani.loyalty == 2, "CR 702.150a: 4 printed minus 2"
    record = scenario.game.cast_record(ajani)
    assert record.phyrexian_life_symbols_paid == 1


def test_ajani_sleeper_agent_paid_with_mana_enters_at_full_loyalty():
    """The same card, every land tapped: no life paid, full 4 loyalty."""
    scenario = _board(AJANI, ["Forest", "Forest", "Plains", "Plains"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest", "Plains", "Plains")

    ajani = scenario.cast_and_resolve(AJANI, *lands)

    assert scenario.player("alice").life == 20
    assert ajani.loyalty == 4


# -- Tamiyo, Compleated Sage (the reported card) -----------------------------


def test_tamiyo_compleated_sage_the_reported_card_paying_life():
    """The reported gap: Tamiyo's own scenario test previously paid only with
    mana, so `phyrexian_life_symbols_paid` never had a real payment to read
    and the reduction never had a reason to fire. {2}{G}{G/U/P}{U}, printed
    loyalty 5: leave the {G/U/P} symbol short of mana."""
    scenario = _board(TAMIYO, ["Forest", "Forest", "Forest", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest", "Forest", "Island")

    tamiyo = scenario.cast_and_resolve(TAMIYO, *lands)

    assert scenario.player("alice").life == 18
    assert tamiyo.loyalty == 3, "CR 702.150a: 5 printed minus 2"
    record = scenario.game.cast_record(tamiyo)
    assert record.phyrexian_life_symbols_paid == 1


def test_tamiyo_compleated_sage_paid_with_mana_enters_at_full_loyalty():
    """Tamiyo again, every land tapped: full 5 loyalty, no life paid."""
    scenario = _board(TAMIYO, ["Forest", "Forest", "Forest", "Island", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Forest", "Forest", "Forest", "Island", "Island")

    tamiyo = scenario.cast_and_resolve(TAMIYO, *lands)

    assert scenario.player("alice").life == 20
    assert tamiyo.loyalty == 5


# -- Nissa, Ascended Animist (off-pool, two Phyrexian symbols on one cost) --


def test_nissa_ascended_animist_paying_life_for_both_symbols_removes_four():
    """Nissa, {3}{G}{G}{G/P}{G/P}, printed loyalty 7 - not in the deck pool,
    not the reported card, and the only real printing with two compleated
    symbols in one cost. Leave *both* {G/P} short of mana: CR 702.150a's
    "minus two for each" removes four, landing at 3, and proves the count is
    read per symbol rather than capped at one regardless of how many were
    paid with life."""
    scenario = _board(NISSA, ["Forest"] * 7)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*(["Forest"] * 5))

    nissa = scenario.cast_and_resolve(NISSA, *lands)

    assert scenario.player("alice").life == 16, "CR 107.4f: 2 life apiece, two symbols"
    assert nissa.loyalty == 3, "CR 702.150a: 7 printed minus 2*2"
    record = scenario.game.cast_record(nissa)
    assert record.phyrexian_life_symbols_paid == 2


def test_nissa_ascended_animist_paying_life_for_only_one_symbol_removes_two():
    """The same card, but only one of the two {G/P} symbols is left short of
    mana (the other is paid with an actual {G}) - proof that "for each" reads
    the real per-symbol payment rather than "any Phyrexian symbol was paid
    with life" as a single flag: exactly one instance's worth comes off."""
    scenario = _board(NISSA, ["Forest"] * 7)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources(*(["Forest"] * 6))

    nissa = scenario.cast_and_resolve(NISSA, *lands)

    assert scenario.player("alice").life == 18, "CR 107.4f: one symbol's worth of life"
    assert nissa.loyalty == 5, "CR 702.150a: 7 printed minus 2*1"
    record = scenario.game.cast_record(nissa)
    assert record.phyrexian_life_symbols_paid == 1


# -- corners ------------------------------------------------------------


def test_put_onto_the_battlefield_without_casting_enters_at_full_loyalty():
    """CR 702.150a's condition is "the player **who cast it** chose to pay
    life" - a card put straight onto the battlefield (Tooth and Nail's own
    path, CR 110.2a) was never cast at all (CR 601.2), so there is no
    `CastRecord` to read a life payment off and no reduction ever applies,
    whatever the card's own Phyrexian symbol says. Full printed loyalty."""
    scenario = Scenario().player("alice", hand=[NAHIRI]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    nahiri = scenario.put_onto_battlefield(NAHIRI, "alice")

    assert nahiri.loyalty == 5, "CR 306.5b: printed loyalty; CR 702.150a never applies uncast"
    assert scenario.player("alice").life == 20
    record = scenario.game.cast_record(nahiri)
    assert record.phyrexian_life_symbols_paid == 0


def test_a_copy_entering_is_not_affected_by_the_originals_life_payment():
    """CR 707.10: "a copy of a spell isn't cast." A copy's own `CastRecord`
    (`Game.copy_spell` -> `Game.note_cast(..., is_copy=True)`) never carries
    `phyrexian_life_symbols_paid` - the same CR 707.2 exclusion the record's
    own docstring already gives `mana_spent`/`spend_effects`, since no mana or
    life was ever spent casting a copy - so the copy enters at full printed
    loyalty even though the real cast beneath it paid life for its symbol.

    The copy is put under bob's control (CR 707.10's own "controlled by the
    player under whose control it was put on the stack") rather than
    alice's: putting two permanents *she* controls on the battlefield with
    the same name would trigger CR 704.5j's legend rule the instant the
    second one entered, which has nothing to do with compleated and would
    kill one of them before this test ever got to compare their loyalty. A
    different controller sidesteps that rule entirely (it reads "controlled
    by the same player") while still proving the point: the same `Card`,
    copied mid-cast, enters at full loyalty regardless of how the real cast
    beneath it paid.

    CR 707.10d puts the copy on top of the stack, so it resolves first,
    while the real, life-paid Nahiri is still underneath, unresolved.
    """
    scenario = _board(NAHIRI, ["Mountain", "Mountain", "Plains", "Plains"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain", "Plains")

    casting = scenario.cast(NAHIRI)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *lands)
    original = scenario.put_on_stack(casting)
    assert scenario.player("alice").life == 18, "the real cast paid 2 life for its symbol"

    copy = scenario.game.copy_spell(original, controller="bob")
    copy_record = scenario.game.cast_record(copy)
    assert copy_record.is_copy is True
    assert copy_record.phyrexian_life_symbols_paid == 0, "CR 707.2: never copied"

    resolved_copy = scenario.resolve_top()
    assert resolved_copy.loyalty == 5, "the copy enters at full printed loyalty"
    assert resolved_copy.controller == "bob"
    assert original.zone is Zone.STACK, "CR 707.10d: the copy resolves first"

    resolved_original = scenario.resolve_top()
    assert resolved_original.loyalty == 3, "the real cast still paid life; still reduced"
    assert resolved_original is original


def test_life_payment_reducing_loyalty_low_enough_dies_to_the_state_based_action():
    """No real compleated printing's own symbols reduce it all the way to
    zero on their own (the lowest, Ajani at printed 4 with one symbol,
    bottoms out at 2) - so this proves the rest of the chain genuinely
    fires by finishing the job with ordinary loyalty-removing damage
    (CR 306.8/120.3c), the same mechanism `test_damage_to_planeswalkers.py`
    covers on its own: a reduced-entry planeswalker is a perfectly ordinary
    one afterwards, and CR 704.5i's state-based action does not need the
    zero to have come from any one particular source.

    Ajani enters at 2 (4 printed minus 2, life paid for its one symbol);
    Lightning Bolt for 3 removes more loyalty counters than are there
    (CR 306.8: "that many ... removed", clamped to what is actually on it),
    landing exactly on 0, and CR 704.5i puts him in the graveyard.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[AJANI, "Lightning Bolt"],
            battlefield=["Forest", "Forest", "Plains", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ajani_lands = scenario.untapped_sources("Forest", "Forest", "Plains")

    ajani = scenario.cast_and_resolve(AJANI, *ajani_lands)
    assert ajani.loyalty == 2, "CR 702.150a: 4 printed minus 2"
    assert ajani.zone is Zone.BATTLEFIELD

    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[ajani])

    assert ajani.counter_count(Counter.LOYALTY) == 0, "CR 306.8: clamped, not negative"
    assert ajani.zone is Zone.GRAVEYARD, "CR 704.5i"

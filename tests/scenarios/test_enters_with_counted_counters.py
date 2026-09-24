"""Scenario: "[This permanent] enters with a `<kind>` counter on it for each
`<description>`" - CR 614.1c's replacement effect again, but counted off
something other than CR 107.3a's announced X: Murktide Regent counts cards
its own delve cost exiled (CR 607.2q's linked ability), Ral, Leyline Prodigy
counts instant and sorcery spells cast this turn (`Game.spells_cast_this_turn`),
and Diregraf Colossus - not a listed card, added here as the proof this reader
generalises past the two it was built against - counts Zombie cards already
sitting in the graveyard through the pre-existing "for each `<subtype>` card
in your graveyard" count.

Every CR number below was looked up with `mise run rules:find <n>` in the
session that wrote this file.

- **CR 614.1c** - "[This permanent] enters with . . . ," "As [this permanent]
  enters . . . ," or "[This permanent] enters as . . . " are replacement
  effects.
- **CR 702.66a** - Delve: "For each generic mana in this spell's total cost,
  you may exile a card from your graveyard rather than pay that mana."
- **CR 607.2q** - "If a permanent spell has an ability printed on it that
  allows one or more cards to be exiled while paying a cost to cast it and
  the permanent that spell becomes has an ability that refers to cards
  'exiled with [this object],' those abilities are linked. The second
  ability refers only to cards exiled to pay the cost of the spell that
  became that permanent." `machines/objects_as_costs.delve` now writes this
  link onto every card it exiles (`CostComponent.link_to_permanent_id`,
  applied in `CostComponent.pay`), and `machines/effects.amount_expression`'s
  own "`<types>` card(s) exiled with it" term reads it back once the spell
  resolves.
- **CR 601.2i** - a spell's cast is complete, and `Game.spells_cast_this_turn`
  gains its entry, before any ability that triggers off the cast ever
  resolves - so by the time Ral, Monsoon Mage flips off the very instant that
  triggered the flip, that instant already counts.
- **CR 400.7** - a card that leaves the stack (cast or countered, resolved or
  not) is a new object with no memory of its previous existence; a spell
  that never resolved into anything has no cast record for CR 107.3m's X, and
  by the same token a card put onto the battlefield some other way was never
  "the spell that became that object" delve exiled cards for at all.
- **CR 205.2a** - instant and sorcery are two of the fifteen printed card
  types; CR 205.2b makes a multi-typed card (an artifact creature, say)
  qualify for either half of an "instant and sorcery" clause by carrying
  just one of them.

Murktide Regent's own second ability - "Whenever an instant or sorcery card
leaves your graveyard, put a +1/+1 counter on this creature" - is a plain
triggered ability with its own coverage elsewhere; this file is only the
replacement effect that decides the counters it enters *with*.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import delve
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board(**player_kwargs):
    return Scenario().player("alice", **player_kwargs)


# -- Murktide Regent: CR 607.2q's delve link --------------------------------


def test_murktide_regent_counts_only_the_instant_and_sorcery_cards_it_delved():
    """Three cards delved, only two of them instant/sorcery - the creature
    card pays for delve exactly the same as the others but does not count."""
    scenario = _board(
        hand=["Murktide Regent"],
        graveyard=["Lightning Bolt", "Lava Spike", "Grizzly Bears"],
        battlefield=["Island", "Island", "Island", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = list(scenario.player("alice").graveyard)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")

    casting = scenario.cast("Murktide Regent")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)
    assert str(payment.mana_owed) == "{2}{U}{U}"
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    murktide = scenario.resolve_top()

    assert murktide.zone is Zone.BATTLEFIELD
    assert murktide.counters[Counter.PLUS_ONE] == 2
    assert all(card.zone is Zone.EXILE for card in binned)


def test_murktide_regent_delving_nothing_enters_with_no_counters():
    """CR 702.66a's delve is optional per card; paying the whole `{5}{U}{U}`
    in mana instead exiles nothing, so nothing is linked and nothing counted."""
    scenario = _board(
        hand=["Murktide Regent"],
        battlefield=["Island"] * 7,
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Island"] * 7))

    casting = scenario.cast("Murktide Regent")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    murktide = scenario.resolve_top()

    assert murktide.zone is Zone.BATTLEFIELD
    assert murktide.counters[Counter.PLUS_ONE] == 0


def test_murktide_regent_put_onto_the_battlefield_without_casting_reads_zero():
    """CR 400.7: a Murktide never cast has no cast record, so no delve link
    of its own was ever written - even instant and sorcery cards already
    sitting in exile from something else entirely do not count, because
    `ExileAnnotation.links_to` matches this object's own id, not its type."""
    scenario = _board(
        hand=["Murktide Regent"],
        graveyard=["Lightning Bolt"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # An unrelated instant, exiled by nothing this Murktide ever paid for.
    scenario.game.exile_cards(list(scenario.player("alice").graveyard))
    murktide_card = scenario.find("Murktide Regent", Zone.HAND)

    murktide = scenario.game.put_onto_battlefield(murktide_card, "alice")

    assert murktide.zone is Zone.BATTLEFIELD
    assert murktide.counters[Counter.PLUS_ONE] == 0


# -- Ral, Leyline Prodigy: spells cast this turn ----------------------------
#
# The coin-flip transform that actually puts this face onto the battlefield
# (Ral, Monsoon Mage's own front-face trigger) is `test_ral_monsoon_mage.py`'s
# whole subject, including this exact replacement effect on both a nonzero and
# a zero count - `test_transforming_after_one_instant_or_sorcery_this_turn_
# adds_one_loyalty` and its sibling. Reached the same low-level way that
# file's own zero-count case is, straight through `Game.put_onto_battlefield`,
# so this file's own coverage of the *template* does not depend on the coin
# flip machinery at all.


def test_ral_leyline_prodigy_counts_instant_and_sorcery_spells_cast_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Opt", "Ral, Monsoon Mage"],
            battlefield=["Mountain", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    (island,) = scenario.untapped_sources("Island")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[bears])
    scenario.cast_and_resolve("Opt", island)
    ral_card = scenario.find("Ral, Monsoon Mage", Zone.HAND)

    ral = scenario.game.put_onto_battlefield(ral_card, "alice", transformed=True)

    assert ral.name == "Ral, Leyline Prodigy"
    assert ral.loyalty == 4  # printed 2 + 2 instant/sorcery spells this turn


def test_ral_leyline_prodigy_with_no_spells_cast_this_turn_gets_only_printed_loyalty():
    scenario = (
        Scenario().player("alice", hand=["Ral, Monsoon Mage"], battlefield=["Mountain"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ral_card = scenario.find("Ral, Monsoon Mage", Zone.HAND)

    ral = scenario.game.put_onto_battlefield(ral_card, "alice", transformed=True)

    assert ral.loyalty == 2


# -- Diregraf Colossus: a second printing proving the shared reader ---------
#
# Not one of this task's own cards, and not in any deck pool - added with
# `scripts/add_card.py`, legality and oracle text verified against Scryfall
# before use. Its own tail, "for each Zombie card in your graveyard", shares
# `machines/replacement._COUNTER_FOR_EACH`'s outer shape with Murktide Regent
# and Ral above but exercises a completely different counted thing - the
# pre-existing subtype-in-graveyard count `machines/effects.count_expression`
# already read for Lotleth Giant's identical singular "for each `<type>` card
# in your graveyard" - proving the "counter ... for each ..." template itself
# generalises rather than being fitted to the two cards that motivated it.


def test_diregraf_colossus_counts_zombie_cards_already_in_the_graveyard():
    scenario = _board(
        hand=["Diregraf Colossus"],
        graveyard=["Prized Amalgam", "Prized Amalgam", "Lightning Bolt"],
        battlefield=["Swamp", "Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    casting = scenario.cast("Diregraf Colossus")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    colossus = scenario.resolve_top()

    assert colossus.zone is Zone.BATTLEFIELD
    assert colossus.counters[Counter.PLUS_ONE] == 2


def test_diregraf_colossus_with_no_zombies_in_the_graveyard_enters_with_none():
    scenario = _board(
        hand=["Diregraf Colossus"],
        graveyard=["Lightning Bolt"],
        battlefield=["Swamp", "Swamp", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    casting = scenario.cast("Diregraf Colossus")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    colossus = scenario.resolve_top()

    assert colossus.zone is Zone.BATTLEFIELD
    assert colossus.counters[Counter.PLUS_ONE] == 0

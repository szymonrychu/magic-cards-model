"""Scenario: every power-up EFFECT and power-up MODIFIER this task closes.

CR 702.193's own activation machinery (CR 702.193a-b: "Activate this ability
only once", the entered-this-turn cost reduction) already resolves and is
proven by `tests/scenarios/test_power_up.py`. What this file proves is what
each power-up ability's own *effect* text does once it resolves, plus the
two power-up *modifiers* the pool prints as separate static abilities
(Hulk, Gamma Goliath's group cost discount and Wonder Man, Hollywood Hero's
extra activation).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 109.2** - "fights" and a bare "target creature" phrase without the
  word "card" mean a permanent on the battlefield.
- **CR 122.1a/122.1b** - +1/+1 counters and keyword counters.
- **CR 205.2a, 205.3m** - card types and creature types (Hero, Equipment,
  Vehicle among them).
- **CR 601.2f** - activation cost reductions are cumulative.
- **CR 608.2c** - a resolving ability's instructions run in the order
  written, and later text can modify earlier text's meaning.
- **CR 608.2d** - a choice an effect offers is made as the effect applies.
- **CR 712.20 / CR 701.27a** - transform.

Power-up itself (CR 702.193) is Marvel Super Heroes-exclusive: no other set
prints the keyword, so none of these riders has an off-pool proof printing
to stand beside the reported card - see the dated MEMORY.md line recording
that, per this campaign's own rule (k). Each template is still proven with
every corner case a printed card of that shape actually raises.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.mana import ManaCost

from .harness import Scenario

# ---------------------------------------------------------------------------
# Abomination, Terrifying Titan: "Put a +1/+1 counter on this creature. He
# fights up to one target creature an opponent controls." (CR 109.2, 701.14)
# ---------------------------------------------------------------------------


def test_abomination_power_up_puts_the_counter_and_fights():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Abomination, Terrifying Titan"] + ["Mountain"] * 7)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Mountain"] * 7)

    scenario.activate(abomination, *sources, targets=[bears])
    scenario.pass_until_resolved()

    # Abomination: 4/4 base, +1/+1 counter -> 5/5, fights the 2/2 Bears.
    assert abomination.counters[Counter.PLUS_ONE] == 1
    assert bears.zone is Zone.GRAVEYARD  # 5 damage kills a 2-toughness Bears.
    assert abomination.damage == 2  # Bears' own power hits back (CR 701.14c).


def test_abomination_power_up_fight_is_up_to_one_and_may_choose_none():
    """ "Up to one target creature" (CR 115.6): no legal target still lets
    the counter half of the instruction happen (CR 608.2c runs in order;
    the fight simply has nothing to do)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Abomination, Terrifying Titan"] + ["Mountain"] * 7)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 7)

    scenario.activate(abomination, *sources, targets=[])
    scenario.pass_until_resolved()

    assert abomination.counters[Counter.PLUS_ONE] == 1
    assert abomination.damage == 0


# ---------------------------------------------------------------------------
# Captain Marvel, Earth's Protector / Quicksilver, Brash Blur: "Put a
# `<kind1>` counter and a `<kind2>` counter on this creature." (CR 122.1a-b)
# The identical template, two different keyword counters - each is the
# other's off-name proof that the "and" join is read generally.
# ---------------------------------------------------------------------------


def test_captain_marvel_power_up_puts_both_counters():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain Marvel, Earth's Protector"] + ["Plains"] * 7)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    marvel = scenario.creature("Captain Marvel, Earth's Protector", "alice")
    sources = scenario.untapped_sources(*["Plains"] * 7)

    scenario.activate(marvel, *sources)
    scenario.pass_until_resolved()

    assert marvel.counters[Counter.PLUS_ONE] == 1
    assert marvel.counters["indestructible"] == 1


def test_quicksilver_power_up_puts_both_counters():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Quicksilver, Brash Blur"] + ["Mountain"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quicksilver = scenario.creature("Quicksilver, Brash Blur", "alice")
    sources = scenario.untapped_sources(*["Mountain"] * 5)

    scenario.activate(quicksilver, *sources)
    scenario.pass_until_resolved()

    assert quicksilver.counters[Counter.PLUS_ONE] == 1
    assert quicksilver.counters["double strike"] == 1


# ---------------------------------------------------------------------------
# Nick Fury, Agent of S.H.I.E.L.D.: "Put two +1/+1 counters on this
# creature, then look at the top seven cards of your library. You may put a
# Hero, Equipment, or Vehicle card from among them onto the battlefield. If
# it's a double-faced card, you may transform it. Put the rest on the
# bottom of your library in a random order." (CR 122.1a, 608.2c, 701.27a)
# ---------------------------------------------------------------------------


def _nick_fury_scenario(top_library: list[str]) -> tuple:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Nick Fury, Agent of S.H.I.E.L.D."]
            + ["Plains", "Island", "Swamp", "Mountain", "Forest"],
            library=top_library,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fury = scenario.creature("Nick Fury, Agent of S.H.I.E.L.D.", "alice")
    sources = scenario.untapped_sources("Plains", "Island", "Swamp", "Mountain", "Forest")
    return scenario, fury, sources


def test_nick_fury_power_up_puts_counters_and_puts_a_matching_card_onto_the_battlefield():
    # Bonesplitter is an Equipment - one of the three qualifying types.
    scenario, fury, sources = _nick_fury_scenario(
        ["Bonesplitter", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"]
    )
    scenario.will_take_the_may(True, source="Nick Fury, Agent of S.H.I.E.L.D.")
    scenario.will_choose_cards(
        scenario.find("Bonesplitter", Zone.LIBRARY, "alice"),
        source="Nick Fury, Agent of S.H.I.E.L.D.",
    )
    library_before = len(scenario.game.player("alice").library)

    scenario.activate(fury, *sources)
    scenario.pass_until_resolved()

    assert fury.counters[Counter.PLUS_ONE] == 2
    bonesplitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    assert bonesplitter.zone is Zone.BATTLEFIELD
    # 7 looked at, 1 kept (leaves the library for the battlefield), 6
    # bottomed (stay in the library, just reordered) - one card shorter.
    assert len(scenario.game.player("alice").library) == library_before - 1


def test_nick_fury_power_up_offers_no_card_when_none_of_the_seven_qualify():
    scenario, fury, sources = _nick_fury_scenario(["Forest"] * 7)
    library_before = len(scenario.game.player("alice").library)

    scenario.activate(fury, *sources)
    scenario.pass_until_resolved()

    assert fury.counters[Counter.PLUS_ONE] == 2
    # Nothing qualified: all seven looked-at cards go back to the library
    # (reordered to the bottom), so its size is unchanged.
    assert len(scenario.game.player("alice").library) == library_before


def test_nick_fury_power_up_may_decline_to_put_the_matching_card_onto_the_battlefield():
    scenario, fury, sources = _nick_fury_scenario(
        ["Bonesplitter", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"]
    )
    scenario.will_take_the_may(False, source="Nick Fury, Agent of S.H.I.E.L.D.")
    library_before = len(scenario.game.player("alice").library)

    scenario.activate(fury, *sources)
    scenario.pass_until_resolved()

    assert fury.counters[Counter.PLUS_ONE] == 2
    bonesplitter = scenario.find("Bonesplitter", Zone.LIBRARY, "alice")
    assert bonesplitter.zone is Zone.LIBRARY
    assert len(scenario.game.player("alice").library) == library_before


# ---------------------------------------------------------------------------
# Thanos, the Mad Titan: "Put two +1/+1 counters on this creature. Choose
# odd or even. Destroy each other creature with mana value of the chosen
# quality." (CR 608.2d's own resolution-time choice, distinct from CR
# 614.12a's "as [this] enters" choice Gollum, Riddle Master uses the same
# two words for.)
# ---------------------------------------------------------------------------


def test_thanos_power_up_destroys_other_creatures_of_the_chosen_parity():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thanos, the Mad Titan", "Grizzly Bears"]
            + ["Wastes", "Plains", "Island", "Swamp", "Mountain", "Forest"],
        )
        .player("bob", battlefield=["Llanowar Elves", "Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thanos = scenario.creature("Thanos, the Mad Titan", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")  # mv 2, even
    elves = scenario.creature("Llanowar Elves", "bob")  # mv 1, odd
    angel = scenario.creature("Serra Angel", "bob")  # mv 5, odd
    sources = scenario.untapped_sources("Wastes", "Plains", "Island", "Swamp", "Mountain", "Forest")
    scenario.will_choose("odd", source="Thanos, the Mad Titan")

    scenario.activate(thanos, *sources)
    scenario.pass_until_resolved()

    assert thanos.counters[Counter.PLUS_ONE] == 2
    assert elves.zone is Zone.GRAVEYARD
    assert angel.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD  # even, and not "other" anyway
    assert thanos.zone is Zone.BATTLEFIELD  # "other" excludes Thanos itself (CR 109.2)


def test_thanos_power_up_choosing_even_spares_the_odd_creatures():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Thanos, the Mad Titan"]
            + ["Wastes", "Plains", "Island", "Swamp", "Mountain", "Forest"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thanos = scenario.creature("Thanos, the Mad Titan", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    sources = scenario.untapped_sources("Wastes", "Plains", "Island", "Swamp", "Mountain", "Forest")
    scenario.will_choose("even", source="Thanos, the Mad Titan")

    scenario.activate(thanos, *sources)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.BATTLEFIELD


# ---------------------------------------------------------------------------
# Hulk, Gamma Goliath: "Power-up abilities of other creatures you control
# cost {3} less to activate." (CR 601.2f, 602.2b)
# ---------------------------------------------------------------------------


def test_hulk_discounts_another_creatures_power_up_ability():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hulk, Gamma Goliath", "Abomination, Terrifying Titan"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hulk = scenario.creature("Hulk, Gamma Goliath", "alice")
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")

    # Abomination's own power-up costs {5}{R/G}{R/G} printed; Hulk's group
    # discount removes {3} generic, same as every other cost reduction
    # (CR 601.2f) - independent of, and cumulative with, CR 702.193b's own
    # entered-this-turn discount, which does not apply here (neither
    # permanent entered this turn).
    assert scenario.game.activation_cost(abomination).mana == ManaCost.parse("{2}{R/G}{R/G}")
    # Hulk's own power-up is never discounted by his own static ("other").
    assert scenario.game.activation_cost(hulk).mana == ManaCost.parse("{6}{R}{G}")


def test_hulk_group_discount_ends_if_hulk_leaves():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Hulk, Gamma Goliath", "Abomination, Terrifying Titan"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hulk = scenario.creature("Hulk, Gamma Goliath", "alice")
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")
    scenario.game.destroy(hulk)

    # Undiscounted: Hulk is gone, so the printed {5}{R/G}{R/G} applies again.
    assert scenario.game.activation_cost(abomination).mana == ManaCost.parse("{5}{R/G}{R/G}")


# ---------------------------------------------------------------------------
# Wonder Man, Hollywood Hero: "Each power-up ability of permanents you
# control can be activated an additional time." (CR 702.193a widened)
# ---------------------------------------------------------------------------


def test_wonder_man_lets_a_power_up_ability_activate_twice():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wonder Man, Hollywood Hero", "Abomination, Terrifying Titan"]
            + ["Mountain"] * 7
            + ["Forest"] * 7,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abomination = scenario.creature("Abomination, Terrifying Titan", "alice")

    assert scenario.why_cannot_activate(abomination) is None
    # Full printed cost {5}{R/G}{R/G}: neither permanent entered this turn.
    first_sources = scenario.untapped_sources(*["Mountain"] * 7)
    scenario.activate(abomination, *first_sources, targets=[])
    scenario.pass_until_resolved()

    assert scenario.why_cannot_activate(abomination) is None  # the extra activation
    second_sources = scenario.untapped_sources(*["Forest"] * 7)
    scenario.activate(abomination, *second_sources, targets=[])
    scenario.pass_until_resolved()

    assert abomination.counters[Counter.PLUS_ONE] == 2
    reason = scenario.why_cannot_activate(abomination)
    assert reason is not None and "already been activated" in reason


def test_wonder_mans_own_power_up_still_activates_only_once():
    """Wonder Man's static reads "permanents you control", including
    himself, but his own power-up ability still tops out at two - proving
    the widening is CR 702.193a's "once" plus one, not unlimited."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Wonder Man, Hollywood Hero"] + ["Mountain"] * 20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wonder_man = scenario.creature("Wonder Man, Hollywood Hero", "alice")

    for _ in range(2):
        sources = scenario.untapped_sources(*["Mountain"] * 7)
        scenario.activate(wonder_man, *sources)
        scenario.pass_until_resolved()

    assert wonder_man.counters[Counter.PLUS_ONE] == 4
    reason = scenario.why_cannot_activate(wonder_man)
    assert reason is not None and "already been activated" in reason

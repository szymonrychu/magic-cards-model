"""Scenario: single-clause player effects, read off a card's own printed text
instead of a per-card `machines/effects.py` table row.

This is the fix for a real playtest bug: bob controlled Guide of Souls
("Whenever another creature you control enters, you gain 1 life and get {E}
(an energy counter).") and cast a creature. The trigger fired and resolved -
and changed nothing, because no table row taught the model either half of
what it says. `test_guide_of_souls_gains_life_and_gets_energy_when_another_
creature_enters` below is that exact case.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 608.2c** - "The controller of the spell or ability follows its
  instructions in the order written" - why a multi-clause effect runs each
  clause in printed order rather than as one blob.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly."
- **CR 107.14** - "The energy symbol is {E}. It represents one energy
  counter."
- **CR 121.1/121.2** - drawing a card, one at a time.
- **CR 701.17a** - milling: "that player puts that many cards from the top of
  their library into their graveyard."
- **CR 701.22a** - scry.
- **CR 701.25a** - surveil.
- **CR 118.3b** - paying life is a cost, subtracted from the life total -
  Griselbrand's "Pay 7 life".

One clause parsed alone proves the shape works; the fail-closed section at the
bottom proves a clause this wave cannot read (a target, a choice) takes the
*whole* effect down with it rather than running the part it understood.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# The reported bug, exactly as played
# --------------------------------------------------------------------------


def test_guide_of_souls_gains_life_and_gets_energy_when_another_creature_enters():
    """Guide of Souls: "Whenever another creature you control enters, you
    gain 1 life and get {E} (an energy counter)." Two clauses, joined by
    "and" (CR 608.2c), both from one trigger.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Guide of Souls", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_and_resolve("Grizzly Bears", *sources)
    assert scenario.stack_names() == ["Guide of Souls's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21
    assert scenario.player("alice").energy == 1


# --------------------------------------------------------------------------
# Each verb, on a different real card, through a different resolution path
# --------------------------------------------------------------------------


def test_kitchen_finks_gains_life_when_it_enters():
    """Kitchen Finks: "When this creature enters, you gain 2 life." One
    clause, through the triggered-ability path.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Kitchen Finks"], battlefield=["Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_and_resolve("Kitchen Finks", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 22


def test_vexing_bauble_draws_a_card_when_sacrificed():
    """Vexing Bauble: "{1}, {T}, Sacrifice this artifact: Draw a card." One
    clause, through the activated-ability path - and a card that never had a
    table row for this ability at all.
    """
    scenario = (
        Scenario()
        .player("alice", library=["Mountain"], battlefield=["Vexing Bauble", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Vexing Bauble", Zone.BATTLEFIELD)
    (forest,) = scenario.untapped_sources("Forest")

    scenario.activate(bauble, forest, sacrificing=[bauble])
    scenario.pass_until_resolved()

    assert "Mountain" in [state.card.name for state in scenario.player("alice").hand]
    assert bauble.zone is Zone.GRAVEYARD


def test_griselbrand_draws_seven_cards_for_seven_life():
    """Griselbrand: "Pay 7 life: Draw seven cards." A spelled-out number, not
    a digit, and a cost that is life rather than mana (CR 118.3b).
    """
    scenario = (
        Scenario()
        .player("alice", library=["Forest"] * 7, battlefield=["Griselbrand"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    griselbrand = scenario.find("Griselbrand", Zone.BATTLEFIELD)

    scenario.activate(griselbrand)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 13
    assert len(scenario.player("alice").hand) == 7
    assert scenario.player("alice").library == []


def test_icetill_explorer_mills_a_card_on_landfall():
    """Icetill Explorer: "Landfall - Whenever a land you control enters, mill
    a card." One clause, through the triggered-ability path, off an ability
    word line.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest"],
            library=["Mountain"],
            battlefield=["Icetill Explorer"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest")
    scenario.pass_until_resolved()

    assert [state.card.name for state in scenario.player("alice").graveyard] == ["Mountain"]


def test_commercial_district_surveils_when_it_enters():
    """Commercial District: "When this land enters, surveil 1." Never had a
    table row - Elegant Parlor and Thundering Falls did, and this is the same
    shape reaching the model for free.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Commercial District"], library=["Mountain", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (top,) = scenario.top_of_library(1)
    scenario.surveil_to_graveyard(top)

    scenario.play_land("Commercial District")
    scenario.pass_until_resolved()

    assert [state.card.name for state in scenario.player("alice").graveyard] == ["Mountain"]
    assert [state.card.name for state in scenario.player("alice").library] == ["Island"]


def test_archive_dragon_scries_when_it_enters():
    """Archive Dragon: "When this creature enters, scry 2." One clause,
    through the triggered-ability path.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Archive Dragon"],
            library=["Mountain", "Swamp"],
            battlefield=["Island"] * 6,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain, swamp = scenario.top_of_library(2)
    scenario.scry_bottoming(mountain)
    sources = scenario.untapped_sources(*["Island"] * 6)

    scenario.cast_and_resolve("Archive Dragon", *sources)
    scenario.pass_until_resolved()

    assert [state.card.name for state in scenario.player("alice").library] == [
        swamp.card.name,
        mountain.card.name,
    ]


# --------------------------------------------------------------------------
# Multi-clause, through the activated path too
# --------------------------------------------------------------------------


def test_vampiric_rites_gains_life_and_draws_a_card_in_order():
    """Vampiric Rites: "{1}{B}, Sacrifice a creature: You gain 1 life and draw
    a card." Two clauses, joined by "and", through the activated-ability
    path - Guide of Souls proves the trigger path does this, this proves the
    activated path does too.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            battlefield=["Vampiric Rites", "Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rites = scenario.find("Vampiric Rites", Zone.BATTLEFIELD)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.activate(rites, *sources, sacrificing=[bears])
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21
    assert "Mountain" in [state.card.name for state in scenario.player("alice").hand]


# --------------------------------------------------------------------------
# Fail-closed: one bad clause runs none of the effect
# --------------------------------------------------------------------------


def test_blood_artist_gains_no_life_because_its_other_clause_is_targeted():
    """Blood Artist: "target player loses 1 life and you gain 1 life." The
    "you gain 1 life" half is exactly this wave's shape, but the "target
    player loses 1 life" half names a target this wave does not resolve.
    CR 608.2c has no notion of running half an effect, so the trigger still
    goes on the stack and still resolves (CR 608.2n) - it just does nothing,
    the same silence a card with no entry at all gets. A regression that ran
    only the parseable half would show up here as alice's life changing.
    """
    scenario = Scenario().player("alice", battlefield=["Blood Artist"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    artist = scenario.creature("Blood Artist", "alice")

    scenario.game.destroy(artist)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Blood Artist's triggered ability"]
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20
    assert scenario.player("bob").life == 20


def test_thoughtseize_reveals_chooses_discards_and_loses_life():
    """Thoughtseize: "Target player reveals their hand. You choose a nonland
    card from it. That player discards that card. You lose 2 life." A
    non-owner choosing from a revealed hand (CR 701.20a, CR 701.9b) is now
    read as one anaphoric run of clauses by
    `_merge_reveal_hand_choose_discard_clauses` in `machines/effects.py` -
    see `test_reveal_hand_and_choose.py` for the full corner-case coverage of
    this shape; this test only needs to prove the gap this docstring used to
    describe is closed.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob", hand=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    assert scenario.player("alice").life == 18
    assert bolt.zone is Zone.GRAVEYARD
    assert "Lightning Bolt" not in [state.card.name for state in scenario.player("bob").hand]


def test_galvanic_discharge_grants_energy_even_when_its_unscripted_payment_declines():
    """Galvanic Discharge: "Choose target creature or planeswalker. You get
    {E}{E}{E} (three energy counters), then you may pay any amount of {E}.
    Galvanic Discharge deals that much damage to that permanent."

    This once read as this wave's blind spot - "choose target" and the
    variable-amount payment were both outside a plain player-effect clause,
    so the whole spell did nothing and even the energy grant was lost with
    it. Energy-as-a-payable-cost (`_parse_target_get_energy_pay_damage` in
    `machines/effects.py`) now reads the whole thing: the target was already
    chosen at CR 601.2c announcement, the energy is granted regardless, and
    CR 608.2d's "you may pay any amount" is asked for real. An unscripted
    answer declines (CR 608.2d's own default is 0, not the maximum - see
    `machines/decisions.py`), so alice keeps her granted energy and bears
    takes no damage. `tests/scenarios/test_energy_payment.py` is where the
    full range of that payment - paying some, paying all, paying too much -
    is covered; this file only needs to prove the multi-clause shape is read
    at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Galvanic Discharge"], battlefield=["Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Galvanic Discharge", mountain, targets=[bears])

    assert scenario.player("alice").energy == 3
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_soul_warden_still_gains_life_now_that_its_table_row_is_gone():
    """Soul Warden's `TRIGGER_EFFECTS` row - `gain_life_on_trigger(1)` - was
    fully subsumed by this parser and deleted; this is the regression check
    that its trigger still does what it always did, off its own printed text
    ("Whenever another creature enters, you gain 1 life.") rather than a
    table row. A regression here - a resolve-and-do-nothing silently
    reintroduced - would show up as alice's life not moving at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Grizzly Bears"], battlefield=["Soul Warden", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_and_resolve("Grizzly Bears", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 21

"""Scenario: the "descend 4"/"descend 8" ability words (CR 207.2c - listed
by name among the ability words, with no rules meaning of their own).

Two grammatically different shapes carry the same "N or more permanent cards
in your graveyard" condition (CR 110.4a's "permanent card"), unrelated to CR
700.11's own per-turn "descended this turn" event count - the two mechanics
only share the English word "descend":

- **A static "as long as" clause** (`machines/layers.py`'s gated-self-static
  builders), proven below on Basking Capybara, Akawalli, the Seething Tower,
  and Didact Echo.
- **A triggered ability's intervening *if*** (CR 603.4/608.2a,
  `machines/triggers.py`'s `_descend_permanent_card_count_holds`), proven
  below on Coati Scavenger and Starving Revenant: "When/Whenever ..., if
  there are N or more permanent cards in your graveyard, <effect>."

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Basking Capybara**: "Descend 4 — This creature gets +3/+0 as long as
  there are four or more permanent cards in your graveyard." Condition
  trailing, pump only.
- **Akawalli, the Seething Tower** (off-pool, proves the parser generalises
  rather than reading Basking Capybara's exact sentence): "Descend 4 — As
  long as there are four or more permanent cards in your graveyard, Akawalli
  gets +2/+2 and has trample.\nDescend 8 — As long as there are eight or more
  permanent cards in your graveyard, Akawalli gets an additional +2/+2 and
  can't be blocked by more than one creature." Condition leading,
  self-referenced by literal name (normalised to "this permanent" before
  this module ever sees it), pump plus a keyword grant, and (Descend 8) an
  "an additional" pump plus a non-keyword literal grant - the block-cap half
  of that clause is proven in combat in `test_blocked_by_at_most_one.py`;
  this file proves the pump and the raw graveyard-count gating only.
- **Didact Echo** (off-pool, the grant-only shape): "Descend 4 — This
  creature has flying as long as there are four or more permanent cards in
  your graveyard." No pump at all, condition trailing.
- **Coati Scavenger** (off-pool, the intervening-*if* shape, ETB): "Descend 4
  — When this creature enters, if there are four or more permanent cards in
  your graveyard, return target permanent card from your graveyard to your
  hand." CR 603.4: the condition is checked *when the event occurs* - below
  the threshold, the ability never triggers at all.
- **Starving Revenant** (off-pool, the intervening-*if* shape on a
  non-self-referential trigger): "Descend 8 — Whenever you draw a card, if
  there are eight or more permanent cards in your graveyard, target opponent
  loses 1 life and you gain 1 life." Its own ETB ("surveil 2. Then for each
  card you put on top of your library, you draw a card and you lose 3 life.")
  is answered to keep nothing on top, so it draws nothing and cannot fire
  this same descend-8 trigger by itself - the scenario draws separately,
  after the ETB has resolved, to isolate the one clause under test.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _computed(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def test_basking_capybara_is_pumped_with_four_permanent_cards_in_the_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Basking Capybara"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring", "Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    capybara = scenario.creature("Basking Capybara", "alice")

    chars = _computed(scenario, capybara)
    assert chars.power == 4  # 1 base + 3
    assert chars.toughness == 3  # unchanged


def test_basking_capybara_is_not_pumped_with_only_three_permanent_cards():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Basking Capybara"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    capybara = scenario.creature("Basking Capybara", "alice")

    chars = _computed(scenario, capybara)
    assert chars.power == 1
    assert chars.toughness == 3


def test_off_pool_akawallis_leading_condition_pumps_and_grants_trample():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Akawalli, the Seething Tower"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring", "Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    akawalli = scenario.creature("Akawalli, the Seething Tower", "alice")

    chars = _computed(scenario, akawalli)
    assert chars.power == 5  # printed 3 + 2 (Descend 4 only; Descend 8 needs 8)
    assert chars.toughness == 5
    assert "Trample" in chars.abilities


def test_off_pool_didact_echo_grant_only_has_flying_while_descended():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Didact Echo"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring", "Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    echo = scenario.creature("Didact Echo", "alice")

    chars = _computed(scenario, echo)
    assert "Flying" in chars.abilities
    assert chars.power == echo.power
    assert chars.toughness == echo.toughness


def test_off_pool_didact_echo_has_no_flying_without_descending():
    scenario = (
        Scenario().player("alice", battlefield=["Didact Echo"], graveyard=["Mountain"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    echo = scenario.creature("Didact Echo", "alice")

    chars = _computed(scenario, echo)
    assert "Flying" not in chars.abilities


def test_off_pool_akawalli_at_eight_permanent_cards_stacks_both_pumps():
    """Descend 4 and Descend 8 are two independent static abilities (CR
    604.2, each active exactly while its own condition holds) that happen to
    share a controller and a threshold ladder - both apply at once once the
    graveyard clears eight, for a total of +4/+4 over the printed 3/3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Akawalli, the Seething Tower"],
            graveyard=[
                "Grizzly Bears",
                "Mountain",
                "Sol Ring",
                "Elvish Mystic",
                "Watchwolf",
                "Hill Giant",
                "Llanowar Elves",
                "Forest",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    akawalli = scenario.creature("Akawalli, the Seething Tower", "alice")

    chars = _computed(scenario, akawalli)
    assert chars.power == 7  # printed 3 + 2 (descend 4) + 2 (descend 8)
    assert chars.toughness == 7
    assert "Trample" in chars.abilities
    assert "Can't be blocked by more than one creature" in chars.abilities


# -- the intervening-if shape: a triggered ability's own condition ----------


def test_off_pool_coati_scavenger_returns_a_permanent_card_at_four():
    """The ETB shape: "When this creature enters, if there are four or more
    permanent cards in your graveyard, return target permanent card from
    your graveyard to your hand." - checked once, at CR 603.4 trigger time."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Coati Scavenger"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring", "Elvish Mystic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.choose_trigger_targets("Coati Scavenger", [bears])

    scenario.put_onto_battlefield("Coati Scavenger")
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND


def test_off_pool_coati_scavenger_does_not_trigger_with_only_three_permanent_cards():
    """CR 603.4: "The ability triggers only if [the condition is] true" -
    below the threshold this never becomes a pending trigger at all, not a
    trigger that fires and does nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Coati Scavenger"],
            graveyard=["Grizzly Bears", "Mountain", "Sol Ring"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Coati Scavenger")

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty


def test_off_pool_starving_revenant_descend_eight_drains_on_a_later_draw():
    """The non-self-referential shape: "Whenever you draw a card, if there
    are eight or more permanent cards in your graveyard, target opponent
    loses 1 life and you gain 1 life." The card's own ETB is answered to keep
    nothing on top (`surveil_to_graveyard` with every looked-at card named),
    so it draws nothing and cannot fire this trigger itself - the isolated
    draw below is what does. The library is instants, not permanent cards, so
    the ETB's own surveil never changes the graveyard's permanent-card count
    out from under the threshold this test means to set up."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Starving Revenant"],
            library=["Lightning Bolt", "Opt", "Shock"],
            graveyard=[
                "Grizzly Bears",
                "Sol Ring",
                "Elvish Mystic",
                "Llanowar Elves",
                "Watchwolf",
                "Hill Giant",
                "Bloodghast",
                "Carrion Feeder",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.surveil_to_graveyard(*scenario.top_of_library(2, "alice"))
    scenario.put_onto_battlefield("Starving Revenant")
    scenario.pass_until_resolved()  # the ETB: surveil only, nothing kept on top

    alice_life_before = scenario.player("alice").life
    bob_life_before = scenario.player("bob").life
    scenario.choose_trigger_targets("Starving Revenant", ["bob"])
    scenario.draw(1, "alice")
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == bob_life_before - 1
    assert scenario.player("alice").life == alice_life_before + 1


def test_off_pool_starving_revenant_does_not_drain_with_only_seven_permanent_cards():
    """The library is instants, not permanent cards, for the same reason the
    positive test above uses them: the ETB's own surveil must not move any
    permanent card into the graveyard and change the count this test means
    to hold at seven."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Starving Revenant"],
            library=["Lightning Bolt", "Opt", "Shock"],
            graveyard=[
                "Grizzly Bears",
                "Sol Ring",
                "Elvish Mystic",
                "Llanowar Elves",
                "Watchwolf",
                "Hill Giant",
                "Bloodghast",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.surveil_to_graveyard(*scenario.top_of_library(2, "alice"))
    scenario.put_onto_battlefield("Starving Revenant")
    scenario.pass_until_resolved()  # the ETB: surveil only, nothing kept on top

    bob_life_before = scenario.player("bob").life
    scenario.draw(1, "alice")

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    assert scenario.player("bob").life == bob_life_before

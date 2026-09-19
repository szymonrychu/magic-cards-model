"""Scenario: the "descend 4"/"descend 8" ability words (CR 207.2c - listed
by name among the ability words, with no rules meaning of their own): "As
long as there are N or more permanent cards in your graveyard, <effect>."
A live graveyard count (CR 110.4a's "permanent card"), unrelated to CR
700.11's own per-turn "descended this turn" event count - the two mechanics
only share the English word "descend".

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Basking Capybara**: "Descend 4 — This creature gets +3/+0 as long as
  there are four or more permanent cards in your graveyard." Condition
  trailing, pump only.
- **Akawalli, the Seething Tower** (off-pool, proves the parser generalises
  rather than reading Basking Capybara's exact sentence): "Descend 4 — As
  long as there are four or more permanent cards in your graveyard, Akawalli
  gets +2/+2 and has trample." Condition leading, self-referenced by literal
  name (normalised to "this permanent" before this module ever sees it),
  pump plus a keyword grant.
- **Didact Echo** (off-pool, the grant-only shape): "Descend 4 — This
  creature has flying as long as there are four or more permanent cards in
  your graveyard." No pump at all, condition trailing.
"""

from magic_cards_model.machines import Step

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

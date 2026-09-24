"""Proof on a second printing: "You may activate abilities of creatures you
control as though those creatures had haste." (CR 609.4, CR 702.10c).

Tyvar, Jubilant Brawler and Shang-Chi, Master of Kung Fu are the listed cards;
`test_activation_as_though_haste.py` covers them. This file proves the same
reader on **Thousand-Year Elixir** - an artifact, not a creature, not a listed
card and not in any deck - and pins the corners that file does not reach:
legal_actions offering the permitted activation, an `{T}` ability the
permission does not need to reach (the Elixir's own), and every clause of all
three printings reading `handled`.

Rules, looked up with `mise run rules:find`:

- **CR 609.4** - an "as though" effect "applies only to the stated effect".
- **CR 702.10c** - haste lets its controller activate `{T}`/`{Q}` abilities
  of a creature not controlled continuously since their most recent turn began.
- **CR 602.5a** - the restriction itself, ignored for creatures with haste.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

ELIXIR = "Thousand-Year Elixir"
DRUID = "Devoted Druid"


def board(*battlefield: str, opponent: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", hand=[DRUID], battlefield=list(battlefield), library=["Forest"] * 5)
        .player("bob", battlefield=list(opponent or []), library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def fresh_druid(scenario: PlayedScenario):
    druid = scenario.cast_and_resolve(DRUID, *scenario.untapped_sources("Forest", "Forest"))
    assert druid.summoning_sick
    return druid


def offered_indexes(scenario: PlayedScenario, permanent) -> set[int | None]:
    return {
        action.ability_index
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == permanent.id
        and action.kind in {ActionKind.ACTIVATE, ActionKind.ACTIVATE_MANA}
    }


def test_thousand_year_elixir_lets_a_fresh_druid_tap():
    scenario = board(ELIXIR, "Forest", "Forest")
    druid = fresh_druid(scenario)

    assert scenario.game.activation_haste_permission(druid) == ELIXIR
    assert scenario.why_cannot_activate(druid, index=0) is None
    scenario.activate(druid, index=0)
    assert druid.tapped


def test_legal_actions_offer_the_permitted_tap_ability():
    """Without the Elixir the fresh Druid's `{T}: Add {G}` is not offered;
    with it, it is."""
    without = board("Forest", "Forest")
    assert 0 not in offered_indexes(without, fresh_druid(without))

    with_elixir = board(ELIXIR, "Forest", "Forest")
    assert 0 in offered_indexes(with_elixir, fresh_druid(with_elixir))


def test_an_opponents_elixir_does_not_reach_your_creature():
    scenario = board("Forest", "Forest", opponent=[ELIXIR])
    druid = fresh_druid(scenario)

    refusal = scenario.why_cannot_activate(druid, index=0)
    assert refusal is not None and "most recent turn began" in refusal


def test_the_elixir_does_not_let_the_creature_attack():
    """CR 609.4: only activating is treated as though the creature had haste."""
    scenario = board(ELIXIR, "Forest", "Forest")
    druid = fresh_druid(scenario)

    assert not scenario.can_attack(druid)


def test_the_permission_ends_when_the_elixir_leaves():
    scenario = board(ELIXIR, "Forest", "Forest")
    druid = fresh_druid(scenario)
    scenario.game.destroy(scenario.find(ELIXIR, Zone.BATTLEFIELD, "alice"))

    assert scenario.why_cannot_activate(druid, index=0) is not None


def test_the_elixirs_own_untap_ability_untaps_the_druid():
    """The Elixir's `{1}, {T}: Untap target creature.` - the artifact's own `{T}`
    is never held back by CR 302.6, which restricts creatures only."""
    scenario = board(ELIXIR, "Forest", "Forest", "Forest")
    druid = fresh_druid(scenario)
    scenario.activate(druid, index=0)
    assert druid.tapped

    elixir = scenario.find(ELIXIR, Zone.BATTLEFIELD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(elixir, forest, targets=[druid])
    scenario.pass_until_resolved()

    assert not druid.tapped


def test_every_clause_of_every_printing_is_handled():
    for name in (ELIXIR, "Tyvar, Jubilant Brawler", "Shang-Chi, Master of Kung Fu"):
        for clause in card_support(card(name)).clauses:
            assert clause.outcome == "handled", (name, clause.text, clause.outcome)

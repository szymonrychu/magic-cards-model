"""FRA stream S8: "Return this card from your graveyard to the battlefield
with a finality counter on it." (CR 110.2a, CR 122.1h), gated by a new
"Activate only if" restriction (CR 602.5b).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 110.2a** - the returned permanent enters under its own controller.
- **CR 122.1h** - a finality counter's own replacement effect: destined for
  exile instead of a graveyard from then on.
- **CR 602.5b** - "Activate only if" restrictions.
- **CR 120.2a** - combat vs. noncombat damage (Grim Repriser's own gate).
- **CR 701.22a/701.25a** - scry and surveil (Proctor of Potential's own
  gate, reading either verb as satisfying the printed "scried or
  surveilled").
- **CR 613** - the layer system computes a *battlefield* permanent's
  characteristics; a card anywhere else (a graveyard-zone activated
  ability's own source, among others) has only its printed ones
  (`machines.layers.printed_characteristics`), which `Game.characteristics_
  of` now falls back to rather than crashing the moment any activation cost
  needed to read them off a permanent that was never on the battlefield to
  begin with - a general gate, not scoped to either card below, that this
  stream's own two handed-off cards were the first to actually exercise.

Grim Repriser and Proctor of Potential are the reported cards - the first
new "Activate only if" conditions this engine reads (`Game.
noncombat_damage_recipients_this_turn`, `Game.scried_or_surveilled_this_
turn`, both new per-turn history, schema bump 22 -> 23). Balustrade Wurm
(Duskmourn, real, non-FRA, non-pool) is the off-set proof for the
self-reanimation-with-a-finality-counter rider itself, gated by a
*different*, already-general condition (Delirium's own "four or more card
types among cards in your graveyard") this stream's own new conditions
never touch.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_grim_repriser_returns_only_after_an_opponent_takes_noncombat_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp", "Mountain"], graveyard=["Grim Repriser"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    repriser = scenario.find("Grim Repriser", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Mountain")

    assert scenario.why_cannot_activate(repriser, 0) is not None

    scenario.game.deal_damage(scenario.player("bob"), 3)

    assert scenario.why_cannot_activate(repriser, 0) is None
    scenario.activate(repriser, *sources)
    scenario.pass_until_resolved()

    assert repriser.zone is Zone.BATTLEFIELD
    assert repriser.counter_count("finality") == 1


def test_grim_repriser_stays_gated_by_combat_damage_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Swamp", "Mountain", "Grizzly Bears"],
            graveyard=["Grim Repriser"],
        )
        .player("bob", battlefield=["Goblin Guide"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    repriser = scenario.find("Grim Repriser", Zone.GRAVEYARD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.why_cannot_activate(repriser, 0) is not None, (
        "combat damage alone does not satisfy 'noncombat damage'"
    )


def test_proctor_of_potential_returns_only_after_scrying_or_surveilling():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Plains", "Island"],
            graveyard=["Proctor of Potential"],
            library=["Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    proctor = scenario.find("Proctor of Potential", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Plains", "Island")

    assert scenario.why_cannot_activate(proctor, 0) is not None

    scenario.game.surveil("alice", 1)

    assert scenario.why_cannot_activate(proctor, 0) is None
    scenario.activate(proctor, *sources)
    scenario.pass_until_resolved()

    assert proctor.zone is Zone.BATTLEFIELD
    assert proctor.counter_count("finality") == 1


def test_balustrade_wurm_off_set_uses_a_different_condition_entirely():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            graveyard=["Balustrade Wurm", "Lightning Bolt", "Grizzly Bears", "Swamp", "Sol Ring"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.find("Balustrade Wurm", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    # instant, creature, land, artifact in the graveyard alongside the wurm
    # itself (a creature card) - four card types, Delirium's own threshold.
    assert scenario.why_cannot_activate(wurm, 0) is None

    scenario.activate(wurm, *sources)
    scenario.pass_until_resolved()

    assert wurm.zone is Zone.BATTLEFIELD
    assert wurm.counter_count("finality") == 1

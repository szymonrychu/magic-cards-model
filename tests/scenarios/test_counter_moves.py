"""Counter-moving templates (CR 122.1): moving a dying permanent's own
counters onto a target, removing an unspecified number of unspecified-kind
counters from a target, and two board-wide "put a counter on X" selectors
("each other creature you control", "each creature you control with a
counter on it").

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 122.1** - what a counter is; no rule requires a stated kind.
- **CR 122.5** - "to 'move' a counter ... means to remove that counter from
  its current object or player and put it onto the second."
- **CR 603.10a / CR 704.8** - a dies trigger looks back at last known
  information, including the counters the permanent last had.
- **CR 115.6** - "up to one target" legally chooses zero.
- **CR 118.12** - "[A player] may [do something]. If [that player] [does],
  [effect]" - the optional-cost shape Guiding Hydra's own trigger reads.
- **CR 608.2f** - the set of objects an effect selects is fixed once, at
  the start of that instruction.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_graft_surgeon_moves_its_counter_onto_a_target_on_death() -> None:
    """ "When this creature dies, put its counters on up to one target
    creature you control." - CR 603.10a's last-known-information for a
    source already gone by the time the trigger resolves.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Graft Surgeon"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    surgeon = scenario.cast_and_resolve(
        "Graft Surgeon", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    assert surgeon.counters["+1/+1"] == 1

    scenario.choose_trigger_targets("Graft Surgeon", [bears])
    scenario.game.destroy(surgeon)
    scenario.game._before_priority()  # CR 603.3: stack the dies trigger
    scenario.resolve_top()  # the dies trigger

    assert surgeon.zone is Zone.GRAVEYARD
    assert bears.counters["+1/+1"] == 1


def test_dockworker_drone_off_set_moves_its_counter_too() -> None:
    """Dockworker Drone (not in this pool, not the reported card): "When this
    creature dies, put its counters on target creature you control." - the
    same grammar without "up to one", proven on a plain, real printing.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dockworker Drone"],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    drone = scenario.cast_and_resolve(
        "Dockworker Drone", *scenario.untapped_sources("Plains", "Plains")
    )
    assert drone.counters["+1/+1"] == 1

    scenario.choose_trigger_targets("Dockworker Drone", [bears])
    scenario.game.destroy(drone)
    scenario.game._before_priority()  # CR 603.3: stack the dies trigger
    scenario.resolve_top()

    assert drone.zone is Zone.GRAVEYARD
    assert bears.counters["+1/+1"] == 1


def test_mabel_removes_up_to_three_counters_of_whatever_kind_is_present() -> None:
    """ "When Mabel enters, remove up to three counters from another target
    creature or planeswalker." - taken as the maximum available, up to the
    stated limit (this wave's own scoped simplification of CR 608.2d's
    "may choose fewer", see `docs/engine-coverage.md`).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mabel, Bitter Recluse"], battlefield=["Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.counters.root["+1/+1"] = 5
    swamp = scenario.untapped_sources("Swamp")[0]

    scenario.choose_trigger_targets("Mabel, Bitter Recluse", [bears])
    scenario.cast_and_resolve("Mabel, Bitter Recluse", swamp)
    scenario.resolve_top()

    assert bears.counters["+1/+1"] == 2, "5 present, only 3 come off"


def test_mabel_takes_no_counters_it_does_not_need_to() -> None:
    """A permanent with only one counter loses only that one, never more
    than what is actually there (CR 122.5 has nothing to remove past zero).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Mabel, Bitter Recluse"], battlefield=["Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.counters.root["+1/+1"] = 1
    swamp = scenario.untapped_sources("Swamp")[0]

    scenario.choose_trigger_targets("Mabel, Bitter Recluse", [bears])
    scenario.cast_and_resolve("Mabel, Bitter Recluse", swamp)
    scenario.resolve_top()

    assert bears.counters["+1/+1"] == 0


def test_heartless_act_off_set_removes_up_to_three_counters() -> None:
    """Heartless Act (not in this pool, not the reported card): mode two,
    "Remove up to three counters from target creature." - the same grammar
    with a single stated kind on the target instead of Mabel's mixed one.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Heartless Act"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.add_counters("+1/+1", 2)
    swamps = scenario.untapped_sources("Swamp", "Swamp")

    casting = scenario.cast("Heartless Act")
    casting.choose_modes([2])
    casting.choose_targets([bears])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *swamps)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.counters["+1/+1"] == 0


def test_guiding_hydra_reflexive_remove_counter_pumps_the_rest_of_the_team() -> None:
    """ "You may remove a +1/+1 counter from this creature. If you do, put a
    +1/+1 counter on each other creature you control." (CR 118.12) - the
    optional cost, then the consequence, both against the real board.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Guiding Hydra"],
            battlefield=["Plains", "Plains", "Plains", "Grizzly Bears", "Serra Angel"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "alice")
    casting = scenario.cast("Guiding Hydra")
    casting.x_value = 2  # "enters with X +1/+1 counters" - 0 toughness at X=0 is lethal
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Plains", "Plains", "Plains"))
    scenario.put_on_stack(casting)
    hydra = scenario.resolve_top()
    assert hydra.zone is Zone.BATTLEFIELD

    scenario.will_take_the_may(True, source="Guiding Hydra")
    scenario.advance()  # combat begins - the trigger goes on the stack
    scenario.resolve_top()

    assert hydra.counters["+1/+1"] == 1
    assert bears.counters["+1/+1"] == 1
    assert angel.counters["+1/+1"] == 1


def test_generous_pup_off_set_pumps_every_other_creature_too() -> None:
    """Generous Pup (not in this pool, not the reported card): "put a +1/+1
    counter on each other creature you control" - the same group selector,
    triggered a different way (a counter landing on the Pup itself, not a
    reflexive cost).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Generous Pup"],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    pup = scenario.cast_and_resolve("Generous Pup", *scenario.untapped_sources("Plains", "Plains"))
    scenario.game.add_counters(pup, "+1/+1", 1)
    scenario.game._before_priority()  # CR 603.3: stack whatever just triggered
    scenario.resolve_top()  # the trigger from that counter landing

    assert bears.counters["+1/+1"] == 1
    assert pup.counters["+1/+1"] == 1, 'the effect excludes the pup itself - "other"'


def test_edgar_activated_ability_pumps_only_creatures_already_countered() -> None:
    """ "{4}{G}: Put a +1/+1 counter on each creature you control with a
    +1/+1 counter on it." - a bear with no counter is skipped; Edgar himself,
    once countered, is not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Edgar, Moonlit Sovereign"],
            battlefield=["Forest"] * 10 + ["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    edgar = scenario.cast_and_resolve(
        "Edgar, Moonlit Sovereign",
        *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"),
    )
    edgar.add_counters("+1/+1", 1)

    # {4}{G}: no tap symbol, so Edgar's own summoning sickness (it was just
    # cast) does not block this activation (CR 302.6 gates tap abilities and
    # attacking only).
    scenario.activate(
        edgar, *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest"), index=0
    )
    scenario.resolve_top()

    assert edgar.counters["+1/+1"] == 2
    assert bears.counters["+1/+1"] == 0


def test_dueling_coach_off_set_activated_ability_reads_the_same_grammar() -> None:
    """Dueling Coach (not in this pool, not the reported card): "{4}{W}, {T}:
    Put a +1/+1 counter on each creature you control with a +1/+1 counter on
    it." - the same selector, a real printing. Placed straight onto the
    initial battlefield (already under alice's control since before the
    game started, CR 302.6) so its own {T} symbol is legal to pay right away
    - the ETB counter this same printing also carries is proven separately
    by `test_edgar_activated_ability_pumps_only_creatures_already_countered`'s
    own family of grammar, not re-tested here.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Plains"] * 5 + ["Grizzly Bears", "Dueling Coach"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    coach = scenario.creature("Dueling Coach", "alice")
    coach.add_counters("+1/+1", 1)

    scenario.activate(
        coach, *scenario.untapped_sources("Plains", "Plains", "Plains", "Plains", "Plains"), index=0
    )
    scenario.resolve_top()

    assert coach.counters["+1/+1"] == 2
    assert bears.counters["+1/+1"] == 0

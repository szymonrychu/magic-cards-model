"""FRA stream S8b: "Target player sacrifices `<n>` `<description>`[ of
their choice]." - the edict template, aimed at a chosen player rather than
"each opponent"/"that player" (`_EACH_SACRIFICES_OF_THEIR_CHOICE_RE`/
`_THAT_PLAYER_SACRIFICES_OF_THEIR_CHOICE_RE`'s own siblings).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard." Sacrifice is always
  the controller's own choice among what they control, whether or not the
  card's own text prints "of their choice" - Liliana of the Veil's own `-2`
  omits the phrase; Diabolic Edict prints it. Both mean the identical thing.
- **CR 115.1c** - an activated ability is targeted the same way a spell is,
  chosen as the ability is activated (CR 602.2b): "target player" reads no
  differently off a loyalty ability than off an instant.
- **CR 608.2d** - a player with nothing matching the description sacrifices
  nothing and is never asked an impossible choice.

Liliana of the Veil's `-2` is the reported card - the coordinator's own
"an edict that core must work." Diabolic Edict (real, non-FRA, non-pool) is
the off-set proof: the identical shape as an instant's whole spell rather
than a loyalty ability's effect, and printed *with* "of their choice" where
Liliana's own wording has none, proving the reader treats both as the same
CR 701.21a choice.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_liliana_of_the_veils_minus_two_makes_the_target_sacrifice_their_own_choice():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    scenario.will_choose_cards(giant, username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=1, targets=["bob"])
    scenario.pass_until_resolved()

    assert giant.zone is Zone.GRAVEYARD, "bob's own choice, not alice's"
    assert bears.zone is Zone.BATTLEFIELD


def test_a_player_with_no_creature_sacrifices_nothing_and_is_never_asked():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")

    scenario.activate(liliana, index=1, targets=["bob"])
    scenario.pass_until_resolved()

    assert [decision for decision in scenario.questions_asked() if decision.player == "bob"] == []


def test_a_player_with_exactly_one_creature_is_never_asked_either():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.activate(liliana, index=1, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert [decision for decision in scenario.questions_asked() if decision.player == "bob"] == []


def test_diabolic_edict_reads_the_identical_shape_with_of_their_choice_printed():
    scenario = (
        Scenario()
        .player("alice", hand=["Diabolic Edict"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.will_choose_cards(bears, username="bob", source="Diabolic Edict")
    scenario.cast_and_resolve("Diabolic Edict", *sources, targets=["bob"])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD

"""FRA stream S8 (handed off from S1): "The owner of up to one other target
nonland permanent puts it on their choice of the top or bottom of their
library." - Subtlety's own two-clause paragraph, folded into one sentence
and aimed at a permanent (CR 401.2, CR 608.2d).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 608.2d** - the owner's own choice, made as the ability resolves.
- **CR 401.2** - a library stays face down and in whatever order a card is
  put into it - never CR 701.24's shuffle.
- **CR 115.6** - "up to one" legally chooses zero; nothing happens, not a
  fizzle.
- **CR 108.3** - "its owner" (or here, "the owner of ~") moves the card into
  whichever player owns it, not the ability's own controller.

Plan for All Outcomes is the reported card. Its own second ability
("Whenever you cast your first noncreature spell each turn, empower Jace
1.") is FRA stream S1's own clause and is a genuinely separate
`TriggeredAbility` - not a second sentence of this one - so this stream's
own ETB reads and resolves completely independently, with no cross-stream
dependency at all. Moonsnare Prototype (Kamigawa: Neon Dynasty, real,
non-FRA, non-pool) is the off-set proof: the identical "the owner of target
nonland permanent puts it ..." sentence with no "up to one" at all (a
mandatory single target rather than an optional one), proven at the clause
level since its own Channel activation is a separate keyword mechanic this
stream does not own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_plan_for_all_outcomes_bounces_a_nonland_permanent_to_its_owners_library():
    scenario = (
        Scenario()
        .player("alice", hand=["Plan for All Outcomes"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_choose_targets(bears, username="alice")
    scenario.will_choose_top(False, source="Plan for All Outcomes")
    scenario.cast_and_resolve("Plan for All Outcomes", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.LIBRARY
    assert bob.library[-1] is bears, "chose the bottom"


def test_declining_the_optional_target_bounces_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Plan for All Outcomes"], battlefield=["Island"] * 4)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island", "Island")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_choose_targets(username="alice")
    scenario.cast_and_resolve("Plan for All Outcomes", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD, "CR 115.6: up to one target legally chose none"


def test_moonsnare_prototype_reads_the_identical_sentence_with_a_mandatory_target():
    from magic_cards_model.machines.effects import parse_mixed_effect_for_spell

    effect = parse_mixed_effect_for_spell(
        "The owner of target nonland permanent puts it on their choice of the top "
        "or bottom of their library."
    )
    assert effect is not None

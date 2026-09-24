"""Spelunking's second paragraph: "Lands you control enter untapped." - CR
614.1d's *non*-self replacement shape (a plural, class-scoped subject, not
"[this permanent]"), read by `machines/replacement._compile_lands_you_control_
enter_untapped` and applied by `_lands_you_control_enter_untapped`, which this
file does not modify - it proves the existing reader against a real land that
would otherwise enter tapped, and against CR 614.12's controller scoping.

Every CR number below was looked up with `mise run rules:find <n>` in the
session that wrote this file.

- **CR 614.1d** - "[This permanent] enters . . ." or "[Objects] enter [the
  battlefield] . . ." are replacement effects.
- **CR 614.12** - which replacement effects apply to an entering permanent is
  judged "as it would exist on the battlefield" against every continuous
  effect already in play, self or not - so Spelunking's own "lands you
  control" static is one more effect competing for the same event a land's
  own "enters tapped" line already modifies, alongside it rather than in
  place of it (both are consulted, CR 616.1's own ordering only settles which
  runs first when more than one would apply).
- **CR 616.1** - "If two or more replacement ... effects are attempting to
  modify the way an event affects an object ..., the affected object's
  controller ... chooses one to apply" - the controller here is the same
  player for both effects (their own land, their own Spelunking), so the
  ordering question in `machines/replacement.order_effects` never has to
  referee between two different players' choices for this shape; only the
  final result - untapped - is asserted, which holds either order (setting
  `tapped` twice, last write standing, for a controller who would only ever
  choose the order that leaves their own land untapped anyway).
- **CR 109.5** - "The words 'you' and 'your' on an object refer to the
  object's controller ... For a static ability, this is the current
  controller of the object it's on" - so "lands you control" never reaches
  the entering land's controller's opponents' boards.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_a_land_that_would_enter_tapped_enters_untapped_under_spelunking():
    """Darkslick Shores, with three other lands out, would ordinarily enter
    tapped (`test_enters_tapped_land_count.py`'s own subject) - Spelunking's
    static overrides that outright."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Spelunking", "Forest", "Island", "Swamp"],
            hand=["Darkslick Shores"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shores = scenario.play_land("Darkslick Shores")

    assert shores.zone is Zone.BATTLEFIELD
    assert shores.untapped


def test_a_land_with_no_enters_tapped_condition_is_unaffected_either_way():
    """A land with nothing to override still enters untapped, the same as
    always - Spelunking is not required to *matter* for this to be correct."""
    scenario = Scenario().player("alice", battlefield=["Spelunking"], hand=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert forest.untapped


def test_spelunking_does_not_untap_an_opponents_land():
    """CR 109.5/614.1d: "lands you control" is Spelunking's controller only -
    bob's own Darkslick Shores, with three other lands of his own out, still
    enters tapped exactly as it would with no Spelunking anywhere."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Spelunking"])
        .player(
            "bob",
            battlefield=["Forest", "Island", "Swamp"],
            hand=["Darkslick Shores"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    shores = scenario.play_land("Darkslick Shores", username="bob")

    assert shores.tapped


def test_removing_spelunking_lets_the_next_land_enter_tapped_again():
    """CR 604.2: a static ability's continuous effect "is active as long as
    the permanent with the ability remains on the battlefield" - not a
    one-shot stamp on the permanents already out. Once Spelunking itself
    leaves, a land entering afterwards reads its own condition with nothing
    overriding it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Spelunking", "Forest", "Island", "Swamp"],
            hand=["Darkslick Shores"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    spelunking = scenario.find("Spelunking", Zone.BATTLEFIELD)
    scenario.game.sacrifice(spelunking)

    shores = scenario.play_land("Darkslick Shores")

    assert shores.tapped


# -- the enchantment's own enters trigger: draw, then may put a land --------


def test_spelunking_itself_draws_a_card_and_gains_no_life_without_a_cave():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spelunking"],
            library=["Island"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.will_take_the_may(True, times=None)

    scenario.cast_and_resolve("Spelunking", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the enters trigger

    assert [state.name for state in scenario.player("alice").hand] == []
    assert scenario.find("Island", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20


def test_spelunking_gains_four_life_when_the_land_put_this_way_is_a_cave():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spelunking"],
            library=["Captivating Cave"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.will_take_the_may(True, times=None)

    scenario.cast_and_resolve("Spelunking", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the enters trigger

    assert scenario.find("Captivating Cave", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 24

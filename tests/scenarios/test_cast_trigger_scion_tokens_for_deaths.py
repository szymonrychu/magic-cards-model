"""Scenario: a cast trigger's optional payment creates one token for each
nontoken creature that died under its controller's control this turn -
Vile Redeemer's own count, read generically off `Game.nontoken_creatures_
died_under_control_this_turn` rather than the global, every-controller
`creatures_died_this_turn` morbid already keeps.

Vile Redeemer: "When you cast this spell, you may pay {C}. If you do, create
a 1/1 colorless Eldrazi Scion creature token for each nontoken creature that
died under your control this turn. Those tokens have 'Sacrifice this token:
Add {C}.'" (Modern, Pioneer).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".
- **CR 111.1** - a token is a marker that may represent a permanent; a
  nontoken creature is a permanent represented by a card.
- **CR 118.12** - the optional {C} is a cost paid as the trigger resolves;
  the token creation only happens if it was paid.
- **CR 107.4c/106.1b** - {C} can be paid only with colorless mana.
- **CR 608.2c** - the controller follows instructions in the printed order;
  the count is read once, as the trigger resolves, over deaths that already
  happened earlier this same turn.

Before this session, `_fold_following_token_grant` only folded a following
"It has/They have '<ability>'" sentence onto a token clause with no "for
each" tail of its own; a token descriptor carrying both (Vile Redeemer's own
shape) reached no reader at all, and `count_expression` had no branch for
"nontoken creature that died under your control this turn" regardless.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(*, alice_creatures: list[str], wastes: int = 1) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Vile Redeemer"],
            battlefield=["Forest"] * 3 + ["Wastes"] * wastes + alice_creatures,
        )
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )


def _scion_tokens(scenario: Scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Eldrazi Scion Token"
    ]


def test_paid_creates_a_scion_for_each_nontoken_creature_that_died_this_turn():
    scenario = _board(alice_creatures=["Grizzly Bears", "Watchwolf"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    wolf = scenario.creature("Watchwolf", "alice")
    scenario.game.destroy(bears)
    scenario.game.destroy(wolf)
    assert scenario.game.nontoken_creatures_died_under_control_this_turn["alice"] == 2

    scenario.will_pay_the_mana_cost(True)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Vile Redeemer", *sources)
    scenario.pass_until_resolved()  # the cast trigger

    tokens = _scion_tokens(scenario)
    assert len(tokens) == 2
    assert all(state.power == 1 and state.toughness == 1 for state in tokens)


def test_declined_creates_no_tokens_even_though_creatures_died():
    scenario = _board(alice_creatures=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)

    scenario.will_pay_the_mana_cost(False)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Vile Redeemer", *sources)
    scenario.pass_until_resolved()

    assert _scion_tokens(scenario) == []


def test_without_a_colorless_source_the_payment_is_never_offered():
    scenario = _board(alice_creatures=["Grizzly Bears"], wastes=0)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.destroy(bears)

    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Vile Redeemer", *sources)
    scenario.pass_until_resolved()

    assert _scion_tokens(scenario) == []


def test_a_creature_dying_under_the_opponents_control_does_not_count():
    """`Game.nontoken_creatures_died_under_control_this_turn` is keyed by
    controller (CR 603.10a's look-back controller), so Bob's own dead
    creature never inflates Alice's count."""
    scenario = _board(alice_creatures=[])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.destroy(giant)
    assert "alice" not in scenario.game.nontoken_creatures_died_under_control_this_turn

    scenario.will_pay_the_mana_cost(True)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Vile Redeemer", *sources)
    scenario.pass_until_resolved()

    assert _scion_tokens(scenario) == []


def test_a_creature_that_left_by_exile_never_died_and_never_counts():
    """CR 700.4/614.6: exile is not the graveyard, so a creature exiled
    instead of destroyed never dies and never joins the count."""
    scenario = _board(alice_creatures=["Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.exile_permanent(bears)
    assert bears.zone is Zone.EXILE
    assert "alice" not in scenario.game.nontoken_creatures_died_under_control_this_turn

    scenario.will_pay_the_mana_cost(True)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.cast_onto_stack("Vile Redeemer", *sources)
    scenario.pass_until_resolved()

    assert _scion_tokens(scenario) == []

""" "Activated abilities of `<group>` you control cost `{N}` less to
activate." (CR 601.2f via CR 602.2b) - Mutagen Man, Living Ooze's own
"artifact tokens", a board-wide static that discounts *other* permanents'
activation costs the way `Game.static_cost_modifiers_for` already discounts
spells, but for CR 602.2b's activation-cost analog instead - read generically
off the group phrase (`Game._permanent_matches_group_quality`), not hardcoded
to "artifact tokens".

This static was `static_unaudited` before this file: nothing in the engine
read the shape at all, so it neither applied the discount nor recorded a
notice for it - and it stays true whether the discount is proven only on the
one card that prints it or on a genuinely different group phrase too, which
is the whole reason Forensic Gadgeteer (a real, off-set, in-format printing,
not in this task's card list and not in the deck pool) is here: "artifacts"
is a different group than "artifact tokens", and it carries its own
"can't reduce ... to less than one mana" floor Mutagen Man's own printing
does not, proving both the group reader and the floor generalise rather than
being fitted to Mutagen Man's one sentence.

`Game.activation_cost(...).mana` is asserted directly - the numeric answer
CR 601.2f/602.2b's cost determination step produces - rather than through
`why_cannot_activate`, which (by design, `models/game.py`'s own docstring on
`legal_actions`) never gates on affordability at all: an unpayable activation
is still a *legal* one (CR 118.6), so it is the wrong question to ask about a
cost reduction. One end-to-end test per side (Mutagen Man's and Forensic
Gadgeteer's own group) also pays the reduced cost and resolves the ability,
proving the number is not just computed but actually charged.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 602.2b** - "An activated ability's analog to a spell's mana cost (as
  referenced in rule 601.2f) is its activation cost."
- **CR 601.2f** - cost reductions are applied before the total cost is
  locked in, and the mana component can be reduced to {0} but no less.
- **CR 111.1 / CR 111.10a / CR 111.10b / CR 111.10v** - a token, and the
  Treasure/Food/Mutagen predefined tokens this file activates.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.token import PREDEFINED, create_tokens
from tests.scenarios.harness import Scenario


def test_mutagen_mans_static_reduces_its_own_tokens_activation_to_zero() -> None:
    """ "Activated abilities of artifact tokens you control cost {1} less to
    activate." applied to the Mutagen token's own printed "{1}, {T},
    Sacrifice this token: ..." - reduced all the way to {0}."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mutagen Man, Living Ooze", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (token,) = create_tokens(scenario.game, PREDEFINED["Mutagen"], "alice")

    cost = scenario.game.activation_cost(token, 0, "alice")
    assert cost.mana.converted == 0

    # End to end: payable with no mana sources at all.
    scenario.activate(token, targets=[bears])
    scenario.resolve_top()
    assert bears.counters["+1/+1"] == 1


def test_mutagen_mans_static_also_discounts_a_food_tokens_ability() -> None:
    """The static names "artifact tokens" generically - CR 111.10b's Food
    token (a different predefined token than Mutagen Man's own) qualifies
    too. Food's printed "{2}, {T}, Sacrifice this token: You gain 3 life."
    is reduced to {1}."""
    scenario = Scenario().player("alice", battlefield=["Mutagen Man, Living Ooze"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (food,) = create_tokens(scenario.game, PREDEFINED["Food"], "alice")

    cost = scenario.game.activation_cost(food, 0, "alice")
    assert cost.mana.converted == 1


def test_mutagen_mans_static_discounts_a_clue_tokens_ability_and_pays_it() -> None:
    """Clue's printed "{2}, {T}, Sacrifice this token: Draw a card." - {1}
    off leaves a payable {1}, provable end to end with exactly one mana
    source."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mutagen Man, Living Ooze", "Island"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (clue,) = create_tokens(scenario.game, PREDEFINED["Clue"], "alice")

    cost = scenario.game.activation_cost(clue, 0, "alice")
    assert cost.mana.converted == 1

    hand_before = len(scenario.player("alice").hand)
    scenario.activate(clue, *scenario.untapped_sources("Island"))
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_mutagen_mans_static_does_not_discount_a_nontoken_artifacts_ability() -> None:
    """ "Artifact tokens" excludes a non-token artifact permanent - Sewer-
    veillance Cam's own "{3}{U}, Sacrifice this artifact: Draw two cards."
    stays at its full printed cost."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mutagen Man, Living Ooze", "Sewer-veillance Cam"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cam = scenario.creature("Sewer-veillance Cam", "alice")

    cost = scenario.game.activation_cost(cam, 0, "alice")
    assert cost.mana.converted == 4


# -- Off-set proof: Forensic Gadgeteer's "artifacts" group, plus its own floor -


def test_forensic_gadgeteers_static_discounts_a_clue_tokens_ability_and_pays_it() -> None:
    """Forensic Gadgeteer's own "Activated abilities of artifacts you
    control cost {1} less to activate." - a different group phrase
    ("artifacts", not "artifact tokens") than Mutagen Man's, off a real,
    in-format printing that is neither this task's reported card nor in the
    deck pool. Clue's {2} ability is reduced to a payable {1}, paid end to
    end."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Forensic Gadgeteer", "Island"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (clue,) = create_tokens(scenario.game, PREDEFINED["Clue"], "alice")

    cost = scenario.game.activation_cost(clue, 0, "alice")
    assert cost.mana.converted == 1

    hand_before = len(scenario.player("alice").hand)
    scenario.activate(clue, *scenario.untapped_sources("Island"))
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_forensic_gadgeteers_floor_stops_a_stacked_discount_reaching_zero() -> None:
    """ "This effect can't reduce the mana in that cost to less than one
    mana." - two copies of the static (two Forensic Gadgeteers) would
    together take {2} off a Clue's {2} ability, but the floor holds it at
    {1} instead of {0}."""
    scenario = (
        Scenario().player("alice", battlefield=["Forensic Gadgeteer", "Forensic Gadgeteer"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (clue,) = create_tokens(scenario.game, PREDEFINED["Clue"], "alice")

    cost = scenario.game.activation_cost(clue, 0, "alice")
    assert cost.mana.converted == 1

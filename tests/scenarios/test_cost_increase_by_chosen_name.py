"""A cost increase scoped by a chosen card name, landing on a free cast.

Disruptor Flute (verified with `resolve_cards`): "Flash / As this artifact
enters, choose a card name. / Spells with the chosen name cost {3} more to
cast. / Activated abilities of sources with the chosen name can't be activated
unless they're mana abilities."

The middle line is the mechanic this file is about, and the interesting board
for it is the Living End one, because every rule involved pulls in a different
direction:

- **CR 118.6** - "Some objects have no mana cost. This represents an unpayable
  cost." Living End's mana cost is the empty string, so nothing can hardcast it
  at all, whatever mana is available.
- **CR 118.6a** - "If an alternative cost is applied to an unpayable cost,
  including an effect that allows a player to cast a spell without paying its
  mana cost, ... the cost becomes payable." Cascade's grant is that effect, so
  the *only* reason Living End is castable here is CR 702.85a.
- **CR 118.9d** - "If an alternative cost is being paid to cast a spell, any
  additional costs, cost increases, and cost reductions that affect that spell
  are applied to that alternative cost." So the Flute's {3} is *not* washed
  away by "without paying its mana cost": it lands on top of the empty
  alternative cost, and the total cost (CR 601.2f) is exactly {3}.
- **CR 118.9c** - the alternative cost "doesn't change a spell's mana cost", so
  Living End's printed cost is still blank while the register reads {3}.
- **CR 702.85a** - cascade's own sentence ends "Then put all cards exiled this
  way that weren't cast on the bottom of your library in a random order", which
  is where a Living End that could not be paid for actually goes. It does *not*
  stay in exile.
- **CR 608.2g** - the cast happens while the cascade trigger resolves, and "If
  an effect gives a player the option to pay mana, they may activate mana
  abilities before taking that action", so the {3} is asked for right there
  (`Game.cast_during_resolution`, battle 8 B8-01).

So Disruptor Flute stops a cascaded Living End without prohibiting anything: it
is a tax, and the player who tapped out for Shardless Agent simply cannot pay
it. The control case at the bottom of this file - the same board with the Flute
naming something else - is what proves that is what is being measured, since
there the free cast goes through for nothing and reanimates.

The engine used to get this wrong in exactly the way `CostModifierNotice` was
built to make visible: `machines/cost._FLAT_COST_INCREASE` wants "spells cost
{N} more to cast" contiguously and cannot read "Spells **with the chosen name**
cost {3} more to cast", so the line was recorded as unparsed and applied to
nothing - the measured total cost of the cascaded Living End was empty, and it
resolved for free with a Flute naming it on the battlefield.
`CostModifierKind.NAMED_INCREASE` (`machines/cost.py`) now reads it, and
`Game.static_cost_modifiers_for` compares CR 614.12a's recorded choice
(`CardState.choice`) against the spell's name.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import CostModifierKind, cost_modifier_effect
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario


def board(*extra_lands: str) -> Scenario:
    """Alice's Flute against Bob's cascade deck.

    Bob's three lands are exactly what Shardless Agent's `{1}{G}{U}` costs, so
    he is tapped out the moment it is announced; `extra_lands` is what the
    affordable case adds on top.
    """
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Disruptor Flute"], battlefield=["Forest", "Forest"])
        .player(
            "bob",
            hand=["Shardless Agent"],
            library=["Island", "Forest", "Living End"],
            graveyard=["Grizzly Bears"],
            battlefield=["Island", "Island", "Forest", *extra_lands],
        )
    )


def flute_naming(scenario: PlayedScenario, name: str) -> None:
    """Alice casts the Flute on her own turn, naming `name` as it enters
    (CR 614.12a), then the turn passes to Bob."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(name, source="Disruptor Flute")
    scenario.cast_and_resolve("Disruptor Flute", *scenario.untapped_sources("Forest", "Forest"))
    while scenario.turn.active_player == "alice":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)


def cascade_into_living_end(scenario: PlayedScenario) -> tuple[object, object]:
    """Bob taps his three lands for Shardless Agent and the cascade trigger
    resolves, casting Living End if Bob can pay for it (CR 608.2g). Returns
    (agent, the hit), wherever the hit went."""
    agent = scenario.cast_onto_stack(
        "Shardless Agent",
        *scenario.untapped_sources("Island", "Island", "Forest", username="bob"),
        username="bob",
    )
    scenario.resolve_top()  # the cascade trigger (CR 702.85a)
    hit = next(state for state in scenario.all_card_states() if state.name == "Living End")
    return agent, hit


def tax_question(scenario: PlayedScenario):
    """The mana payment asked while the cascade trigger resolved, if any."""
    return [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.PAY_MANA and question.source == "Living End"
    ]


# -- the printed line, read on its own ------------------------------------


def test_the_chosen_name_line_is_read_as_a_cost_increase():
    """Before anything is played: the sentence parses at all. It used to fall
    through every shape in `cost_modifier_effect` and come back None, which is
    what made the tax invisible on a real board."""
    (line,) = [
        text
        for text in (card("Disruptor Flute").oracle_text or "").splitlines()
        if "more to cast" in text
    ]
    effect = cost_modifier_effect(line)

    assert effect is not None
    assert effect.kind is CostModifierKind.NAMED_INCREASE
    assert effect.amount == 3


def test_living_end_has_no_mana_cost_at_all():
    """CR 118.6's unpayable cost, straight off the printing - the premise the
    whole file rests on. `{0}` would be a real, payable, empty cost (CR 118.5);
    this is no cost."""
    assert card("Living End").mana_cost == ""


# -- the tax on the cascade cast ------------------------------------------


def test_the_cascaded_living_end_costs_exactly_three():
    """CR 118.9d and CR 601.2f: the {3} is applied *to the alternative cost*,
    and it is the whole of what the cast asks to be paid. Living End's own
    mana cost stays blank (CR 118.9c, `test_living_end_has_no_mana_cost_at_all`),
    so the {3} is the increase landing on the empty alternative cost rather
    than being swallowed by "without paying its mana cost"."""
    scenario = board().build()
    flute_naming(scenario, "Living End")
    cascade_into_living_end(scenario)

    (question,) = tax_question(scenario)
    assert question.amount == 3
    assert "{3}" in question.prompt


def test_the_tax_lands_even_though_the_flute_belongs_to_the_opponent():
    """ "Spells with the chosen name cost {3} more to cast." names no
    controller, unlike the Medallion cycle's "spells *you* cast", so Alice's
    Flute taxes Bob. Asserted separately from the cost arithmetic above so a
    controller-scoping mistake cannot hide behind it."""
    scenario = board().build()
    flute_naming(scenario, "Living End")
    (flute,) = [state for state in scenario.game.battlefield if state.name == "Disruptor Flute"]
    assert flute.controller == "alice"

    _, hit = cascade_into_living_end(scenario)
    increases, _, _ = scenario.game.static_cost_modifiers_for(hit, "bob")

    assert [str(cost) for cost in increases] == ["{3}"]


def test_only_the_named_spell_is_taxed():
    """The Agent that started all this is not named, and pays its printed
    `{1}{G}{U}` and nothing more - three lands is exactly enough, which is
    what leaves Bob with no mana for the {3}."""
    scenario = board().build()
    flute_naming(scenario, "Living End")

    casting = scenario.cast("Shardless Agent", username="bob")
    assert str(casting.total_cost.mana) == "{1}{G}{U}"


def test_a_player_tapped_out_for_the_agent_cannot_pay_the_three():
    """The refusal has to be *about the cost*. Disruptor Flute prohibits
    nothing on the casting side, so the cast was proposed and only the {3}
    stopped it: the payment question was asked and could not be accepted
    (CR 118.3)."""
    scenario = board().build()
    flute_naming(scenario, "Living End")
    _, hit = cascade_into_living_end(scenario)

    (question,) = tax_question(scenario)
    assert question.affirmative_is_legal is False
    assert hit.zone is Zone.LIBRARY
    assert scenario.stack_names() == ["Shardless Agent"]


def test_the_uncast_living_end_goes_to_the_bottom_of_the_library():
    """CR 702.85a's last sentence: "put all cards exiled this way that weren't
    cast on the bottom of your library in a random order". A Living End nobody
    could pay for is one of those cards - it goes there with the two lands the
    moment the trigger finishes, and it does not reanimate anything."""
    scenario = board().build()
    flute_naming(scenario, "Living End")
    _, hit = cascade_into_living_end(scenario)

    assert hit.zone is Zone.LIBRARY
    assert scenario.game.exile == []
    assert sorted(state.name for state in scenario.player("bob").library) == [
        "Forest",
        "Island",
        "Living End",
    ]
    assert [state.name for state in scenario.player("bob").cards_in(Zone.GRAVEYARD)] == [
        "Grizzly Bears"
    ]


def test_the_agent_resolves_onto_the_battlefield_anyway():
    """Cascade is a triggered ability on the stack (CR 702.85a), a separate
    object from the spell that made it - whether its hit gets cast changes
    nothing about the Agent, which resolves as an ordinary creature spell."""
    scenario = board().build()
    flute_naming(scenario, "Living End")
    agent, _ = cascade_into_living_end(scenario)
    scenario.resolve_top()

    assert agent.zone is Zone.BATTLEFIELD


# -- the two cases that prove the Flute is what is being measured ---------


def test_a_flute_naming_something_else_lets_the_free_cast_through():
    """The control. Same board, same tapped-out Bob, Flute naming Sol Ring:
    the cascaded Living End costs nothing, is cast for nothing while the
    trigger resolves, and reanimates."""
    scenario = board().build()
    flute_naming(scenario, "Sol Ring")
    _, hit = cascade_into_living_end(scenario)

    assert tax_question(scenario) == []
    assert scenario.stack_names() == ["Shardless Agent", "Living End"]
    scenario.resolve_top()

    assert hit.zone is Zone.GRAVEYARD
    assert "Grizzly Bears" in [state.name for state in scenario.game.battlefield]


def test_three_spare_lands_pay_the_tax_and_the_cast_goes_through():
    """The {3} is generic (CR 107.4b), so any three untapped lands cover it.
    Paying it is a real cast: Living End resolves, reanimates, and the three
    Islands end up tapped."""
    scenario = board("Island", "Island", "Island").build()
    flute_naming(scenario, "Living End")
    spare = scenario.untapped_sources("Island", "Island", "Island", username="bob")
    _, hit = cascade_into_living_end(scenario)

    (question,) = tax_question(scenario)
    assert question.affirmative_is_legal is True
    assert scenario.stack_names() == ["Shardless Agent", "Living End"]
    scenario.resolve_top()

    assert hit.zone is Zone.GRAVEYARD
    assert "Grizzly Bears" in [state.name for state in scenario.game.battlefield]
    assert all(land.tapped for land in spare)

"""Once during each of your turns, cast a spell without paying its mana cost.

Zaffai and the Tempests: "Once during each of your turns, you may cast an
instant or sorcery spell from your hand without paying its mana cost." One
with the Multiverse, the off-pool proof with a different quality and a second
zone: "Once during each of your turns, you may cast a spell from your hand or
the top of your library without paying its mana cost."

Both are CR 118.9's alternative cost applied from another effect - read whole
with `mise run rules:find` in the session that wrote this file: "An
alternative cost is a cost listed in a spell's text, or applied to it from
another effect, that its controller may pay rather than paying the spell's
mana cost. Alternative costs are usually phrased, '... You may cast [this
object] without paying its mana cost.'" CR 118.9a: "Only one alternative cost
can be applied to any one spell as it's being cast." The rulings add that a
spell with {X} cast this way has X of 0 (CR 107.3b), and that additional
costs may still be paid.

"Once during each of your turns" is one use per turn of *that* permanent,
only while its controller is the active player - the same bookkeeping Kess,
Dissident Mage's once-per-turn graveyard permission already keeps
(`Game.once_per_turn_cast_permissions_used`).

Casting from the top of the library is not something this engine models for
any card yet, so only One with the Multiverse's hand half is played here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import AlternativeCostSource
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def board(*alice_hand: str, battlefield: tuple[str, ...] = ("Zaffai and the Tempests",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            library=["Island"] * 10,
            battlefield=[*battlefield, "Island", "Island", "Island", "Forest", "Forest"],
        )
        .player("bob", life=20, library=["Island"] * 10, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def free_options(casting, source: str = "Zaffai and the Tempests"):
    return [
        option
        for option in casting.alternative_costs
        if option.source is AlternativeCostSource.STATIC and option.source_name == source
    ]


def cast_free(scenario: PlayedScenario, name: str, source: str = "Zaffai and the Tempests"):
    casting = scenario.cast(name)
    casting.use_alternative_cost(source)
    payment = casting.begin_paying()
    scenario.pay_with(payment)
    return scenario.put_on_stack(casting)


def untapped_lands(scenario: PlayedScenario) -> int:
    return sum(
        1
        for permanent in scenario.game.battlefield
        if permanent.controller == "alice"
        and permanent.name in ("Island", "Forest")
        and not permanent.tapped
    )


def test_zaffai_casts_a_sorcery_from_hand_for_nothing():
    scenario = board("Divination")
    divination = cast_free(scenario, "Divination")
    assert divination.zone is Zone.STACK
    assert untapped_lands(scenario) == 5
    scenario.resolve_top()
    assert len(scenario.player("alice").hand) == 2


def test_only_once_each_turn():
    scenario = board("Divination", "Opt")
    cast_free(scenario, "Divination")
    scenario.resolve_top()
    casting = scenario.cast("Opt")
    (option,) = free_options(casting)
    assert option.unavailable is not None and "once" in option.unavailable
    casting.cancel()


def test_paying_normally_does_not_use_up_the_once():
    scenario = board("Opt", "Divination")
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Opt", island)
    divination = cast_free(scenario, "Divination")
    assert divination.zone is Zone.STACK


def test_not_during_an_opponents_turn():
    scenario = board("Opt")
    scenario.start_at(Step.CLEANUP)
    while scenario.turn.active_player != "bob" or scenario.step is not Step.UPKEEP:
        scenario.advance()
    casting = scenario.cast("Opt", username="alice")
    (option,) = free_options(casting)
    assert option.unavailable is not None and "your turns" in option.unavailable


def test_a_creature_spell_is_not_an_instant_or_sorcery_spell():
    scenario = board("Grizzly Bears")
    casting = scenario.cast("Grizzly Bears")
    (option,) = free_options(casting)
    assert option.unavailable is not None


def test_available_again_on_the_next_turn():
    scenario = board("Divination", "Divination")
    cast_free(scenario, "Divination")
    scenario.resolve_top()
    scenario.start_at(Step.CLEANUP)
    while scenario.turn.active_player != "alice" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()
    divination = cast_free(scenario, "Divination")
    assert divination.zone is Zone.STACK


def test_each_granting_permanent_has_its_own_once():
    """Zaffai and One with the Multiverse are two permanents, each with its
    own "once" (CR 400.7: the granting object itself) - two free spells."""
    scenario = board(
        "Divination",
        "Opt",
        battlefield=("Zaffai and the Tempests", "One with the Multiverse"),
    )
    cast_free(scenario, "Divination")
    scenario.resolve_top()

    casting = scenario.cast("Opt")
    (zaffai,) = free_options(casting)
    (multiverse,) = free_options(casting, source="One with the Multiverse")
    assert zaffai.unavailable is not None
    assert multiverse.available
    casting.use_alternative_cost(multiverse.index)
    scenario.pay_with(casting.begin_paying())
    assert scenario.put_on_stack(casting).zone is Zone.STACK
    assert untapped_lands(scenario) == 5


def test_an_x_spell_cast_for_nothing_has_x_of_zero():
    scenario = board("Fireball", battlefield=("Zaffai and the Tempests", "Mountain"))
    casting = scenario.cast("Fireball")
    casting.use_alternative_cost("Zaffai and the Tempests")
    casting.choose_targets(["bob"])
    payment = casting.determine_cost(x_value=0)
    scenario.pay_with(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == 20


def test_legal_actions_list_the_free_cast_until_it_is_used():
    scenario = board("Divination", "Opt")
    opt = scenario.find("Opt", Zone.HAND, "alice")

    def free_casts_of(card_id):
        return [
            action
            for action in legal_actions(scenario.game, "alice")
            if action.kind.value == "cast"
            and action.card_id == card_id
            and action.alternative_cost is not None
        ]

    assert free_casts_of(opt.id)
    cast_free(scenario, "Divination")
    scenario.resolve_top()
    assert not free_casts_of(opt.id)


def test_one_with_the_multiverse_casts_any_spell_from_hand_once():
    """A different quality ("a spell") and a second zone named: Grizzly
    Bears, a creature spell, is cast from hand for nothing."""
    scenario = board(
        "Grizzly Bears", "Opt", battlefield=("One with the Multiverse",)
    )
    bears = cast_free(scenario, "Grizzly Bears", source="One with the Multiverse")
    assert bears.zone is Zone.STACK
    assert untapped_lands(scenario) == 5
    scenario.resolve_top()
    casting = scenario.cast("Opt")
    (option,) = free_options(casting, source="One with the Multiverse")
    assert option.unavailable is not None

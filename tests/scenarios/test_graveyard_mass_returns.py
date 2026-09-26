"""Scenario: mass graveyard returns by type and by mana value (Secrets of
Strixhaven, T8).

Two shapes:

- Wisdom of Ages: "Return all instant and sorcery cards from your graveyard
  to your hand. You have no maximum hand size for the rest of the game.
  Exile Wisdom of Ages." A mass return filtered by a two-type list, CR
  613.11's rule-modifying hand size removed for the rest of the game, and
  the spell exiling itself - three independent instructions read whole.
- Fix What's Broken: "As an additional cost to cast this spell, pay X life.
  Return each artifact and creature card with mana value X from your
  graveyard to the battlefield." CR 107.3f's own additional-cost X, read
  fresh at resolution, filtering a two-type list by an *exact* mana value
  rather than a printed ceiling.

Both share one widened primitive: `_parse_card_group_qualifier`'s new
"`<A>` and `<B>` cards" branch (CR 205.2a's two-type union, never a card
that is somehow both at once), plus the `split_effect_clauses` masking that
keeps that phrase from being cut into two clauses by its own internal "and".
Proved a second time, independently of both listed cards, on Brilliant
Restoration - "Return all artifact and enchantment cards from your graveyard
to the battlefield." - a different card, a different destination
(`_parse_mass_return_from_graveyard_to_battlefield_clause`'s own "all"
family rather than Fix What's Broken's dynamic-X "each" reader), and a
different pair of types.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2f** - a group named by one instruction moves as one action, so
  it is fixed before any of it arrives.
- **CR 110.2a** - a permanent an effect puts onto the battlefield with
  nobody else named enters under that effect's own controller's control.
- **CR 400.7** - a card that changes zones becomes a new object.
- **CR 118.8a** - an additional cost is paid on the way to the stack, before
  the spell resolves.
- **CR 119.4/119.4b** - paying life is legal down to (but not below) zero,
  and paying zero is always legal.
- **CR 107.3f** - an X undefined anywhere but an additional cost is chosen
  as that cost is paid.
- **CR 402.2/613.11** - the default maximum hand size, and a continuous
  effect that overrides it for the rest of the game.
- **CR 406.2/701.13a** - exiling a card moves it to the exile zone from
  wherever it currently is.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def _cast_paying_x_life(
    scenario: PlayedScenario, name: str, x_value: int, *sources, username: str = "alice"
) -> Casting:
    """Announce a "pay X life" additional-cost spell for a chosen X and pay
    that much life - the same recipe `test_toxic_deluge.py` uses for its own
    identical additional-cost shape."""
    casting = scenario.cast(name, username=username)
    casting.game = scenario.game
    casting.determine_cost(x_value=x_value)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    return casting


# -- Wisdom of Ages -------------------------------------------------------


def test_wisdom_of_ages_returns_instants_and_sorceries_and_removes_max_hand_size():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wisdom of Ages"],
            battlefield=["Island"] * 4 + ["Swamp"] * 3,
            graveyard=["Lightning Bolt", "Divination", "Grizzly Bears"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    assert not alice.has_no_maximum_hand_size
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Swamp"] * 3))
    scenario.cast_and_resolve("Wisdom of Ages", *sources)
    assert sorted(card.name for card in alice.hand) == ["Divination", "Lightning Bolt"]
    assert [card.name for card in alice.graveyard] == ["Grizzly Bears"]
    assert alice.has_no_maximum_hand_size


def test_wisdom_of_ages_exiles_itself_after_resolving():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wisdom of Ages"],
            battlefield=["Island"] * 4 + ["Swamp"] * 3,
            graveyard=["Lightning Bolt"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Swamp"] * 3))
    wisdom = scenario.cast_and_resolve("Wisdom of Ages", *sources)
    assert wisdom.zone is Zone.EXILE
    assert wisdom not in alice.graveyard


def test_wisdom_of_ages_with_no_instant_or_sorcery_returns_nothing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wisdom of Ages"],
            battlefield=["Island"] * 4 + ["Swamp"] * 3,
            graveyard=["Grizzly Bears"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Swamp"] * 3))
    scenario.cast_and_resolve("Wisdom of Ages", *sources)
    assert alice.hand == []
    assert [card.name for card in alice.graveyard] == ["Grizzly Bears"]
    assert alice.has_no_maximum_hand_size


# -- Fix What's Broken ------------------------------------------------------


def test_fix_what_is_broken_returns_artifacts_and_creatures_at_exactly_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Fix What's Broken"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp"],
            graveyard=["Grizzly Bears", "Ornithopter", "Llanowar Elves"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    bears = next(card for card in alice.graveyard if card.name == "Grizzly Bears")
    ornithopter = next(card for card in alice.graveyard if card.name == "Ornithopter")
    elves = next(card for card in alice.graveyard if card.name == "Llanowar Elves")
    assert bears.mana_value == 2
    assert ornithopter.mana_value == 0
    assert elves.mana_value == 1
    sources = scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp")
    _cast_paying_x_life(scenario, "Fix What's Broken", 2, *sources)
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.controller == "alice"
    assert ornithopter.zone is Zone.GRAVEYARD, "mana value 0, not 2"
    assert elves.zone is Zone.GRAVEYARD, "mana value 1, not 2"
    assert alice.life == 18


def test_fix_what_is_broken_pays_life_as_an_additional_cost():
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Fix What's Broken"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp"],
            graveyard=["Ornithopter"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp")
    _cast_paying_x_life(scenario, "Fix What's Broken", 0, *sources)
    assert alice.life == 20, "X=0 pays no life (CR 119.4b)"
    scenario.resolve_top()
    returned = next(
        (state for state in scenario.game.battlefield if state.card.name == "Ornithopter"), None
    )
    assert returned is not None, "mana value 0 matches X=0"
    assert returned.controller == "alice"


def test_fix_what_is_broken_ignores_a_matching_mana_value_of_the_wrong_type():
    """A land at mana value 0 does not qualify - only artifact and creature
    cards do (CR 205.2a's own two types, never a third)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Fix What's Broken"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp"],
            graveyard=["Forest"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Swamp", "Swamp")
    _cast_paying_x_life(scenario, "Fix What's Broken", 0, *sources)
    scenario.resolve_top()
    assert sorted(card.name for card in alice.graveyard) == ["Fix What's Broken", "Forest"]


# -- Brilliant Restoration (proof: a second printing of the widened
# "`<A>` and `<B>` cards" qualifier, over the "return all ... to the
# battlefield" family Fix What's Broken does not use) ----------------------


def test_brilliant_restoration_proves_the_type_list_qualifier_on_a_mass_return():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Brilliant Restoration"],
            battlefield=["Plains"] * 7,
            graveyard=["Ornithopter", "Runed Halo", "Grizzly Bears", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    ornithopter = next(card for card in alice.graveyard if card.name == "Ornithopter")
    halo = next(card for card in alice.graveyard if card.name == "Runed Halo")
    bears = next(card for card in alice.graveyard if card.name == "Grizzly Bears")
    sources = scenario.untapped_sources(*(["Plains"] * 7))
    scenario.cast_and_resolve("Brilliant Restoration", *sources)
    assert ornithopter.zone is Zone.BATTLEFIELD, "artifact"
    assert halo.zone is Zone.BATTLEFIELD, "enchantment"
    assert bears.zone is Zone.GRAVEYARD, "creature, neither artifact nor enchantment"
    assert ornithopter.controller == "alice"
    assert halo.controller == "alice"

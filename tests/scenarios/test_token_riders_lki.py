"""Token-creation riders that read an object's *last-known* state (CR 603.10a
look-back, CR 400.7's "new object", CR 704.8) rather than its live one:

- "Whenever a creature you control with a +1/+1 counter on it leaves the
  battlefield, create a Mutagen token for each +1/+1 counter on it." - The
  Ooze: the counter *qualifier* on the leaves-the-battlefield condition
  itself (CR 122.1), and the "for each ... counter on it" multiplier reading
  the *departed* creature's own last-known counters, not the ability's own
  source's.
- "{T}: Exile target card from a graveyard. Create a Mutagen token." - The
  Ooze's second ability, an ordinary two-clause activation once Mutagen is a
  predefined token.
- "Target creature's owner puts it on their choice of the top or bottom of
  their library. You create a Mutagen token." - Return to the Sewers
  (CR 110.2's owner, already read by `effects._owner_puts_it_into_library_
  effect`; only the trailing token-creation sentence is new once Mutagen
  exists).
- "Destroy target `<X>`. If its mana value was `<N>` or less,
  `<consequence>`." - Tainted Treats' own "create a Food token" and, off the
  reported card and off the deck pool, Extinguish the Light's "you gain 3
  life" - one shared reader, proven on two different consequences.
- "You may search your library for a `<quality>` card, reveal it, put it
  into your hand, then shuffle. If you don't put a card into your hand this
  way, create a `<token>`." - Courier of Comestibles (CR 118.12's "if you
  don't" reading the search's own outcome, not last-known information, but
  the same `machines/token_riders.py` module the rest of this file covers).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 122.1** - a counter modifies the object it is placed on; CR 122.1a is
  the +1/+1 kind specifically.
- **CR 603.10a** - leaves-the-battlefield triggers look back in time.
- **CR 704.8** - a state-based action or replacement effect that looks back
  at a permanent's last existence before it changed zones uses the
  characteristics, and counters, it had then.
- **CR 110.2** - a permanent's owner, distinct from its controller.
- **CR 601.2f / 602.2b** - determining a spell or ability's total cost (not
  used directly here, cited only because `Game.destroy` and `Game.gain_life`
  sit downstream of it in the same resolution).
- **CR 400.7 / 400.7d** - an object that changes zones is a new object; an
  ability may still reference the object's last-known information.
- **CR 118.12** - an "if you don't" instruction asks whether an earlier cost
  or action in the same resolution actually happened.
- **CR 701.23a / 701.23b** - searching a hidden zone, and a stated-quality
  search that a player is never required to find with.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _mutagen_tokens(scenario: Scenario, username: str = "alice") -> list:
    return [
        p
        for p in scenario.game.battlefield
        if p.name == "Mutagen Token" and p.controller == username
    ]


# -- The Ooze: LKI +1/+1-counter count off the departed creature --------------


def test_the_ooze_creates_a_mutagen_token_per_counter_on_the_departed_creature() -> None:
    scenario = Scenario().player("alice", battlefield=["The Ooze", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.PLUS_ONE, 2)

    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert len(_mutagen_tokens(scenario)) == 2
    assert bears.zone is Zone.GRAVEYARD


def test_the_ooze_does_not_trigger_off_a_creature_with_no_counter() -> None:
    """The condition's own "with a +1/+1 counter on it" qualifier (CR 122.1)
    - a plain creature leaving does not satisfy it at all."""
    scenario = Scenario().player("alice", battlefield=["The Ooze", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert _mutagen_tokens(scenario) == []


def test_the_ooze_ignores_minus_one_counters_when_asked_for_plus_one() -> None:
    """A -1/-1 counter is a different kind (CR 122.1) - it does not satisfy
    "with a +1/+1 counter on it" even though the creature is carrying one."""
    scenario = Scenario().player("alice", battlefield=["The Ooze", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.add_counters(bears, Counter.MINUS_ONE, 1)

    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert _mutagen_tokens(scenario) == []


def test_the_ooze_own_activated_ability_exiles_and_creates_a_mutagen_token() -> None:
    """The Ooze's second ability: "{T}: Exile target card from a graveyard.
    Create a Mutagen token." - an ordinary two-clause activation, generic
    once Mutagen is a predefined token."""
    scenario = (
        Scenario().player("alice", battlefield=["The Ooze"], graveyard=["Lightning Bolt"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ooze = scenario.creature("The Ooze", "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    scenario.activate(ooze, targets=[bolt])
    scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert len(_mutagen_tokens(scenario)) == 1


# -- Return to the Sewers: owner's choice of top or bottom --------------------


def test_return_to_the_sewers_tucks_to_the_top_and_creates_a_mutagen_token() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Return to the Sewers"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_top(True, username="bob")

    scenario.cast_and_resolve("Return to the Sewers", auto=True, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[0].id == bears.id
    assert len(_mutagen_tokens(scenario)) == 1


def test_return_to_the_sewers_tucks_to_the_bottom() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Return to the Sewers"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_top(False, username="bob")

    scenario.cast_and_resolve("Return to the Sewers", auto=True, targets=[bears])

    assert bears.zone is Zone.LIBRARY
    assert scenario.player("bob").library[-1].id == bears.id
    assert len(_mutagen_tokens(scenario)) == 1


# -- "Destroy target X. If its mana value was N or less, <consequence>." ------


def test_tainted_treats_creates_a_food_token_off_a_cheap_permanent() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tainted Treats"],
            battlefield=["Swamp", "Swamp", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])  # mana value 2
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Tainted Treats", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    food = [
        p for p in scenario.game.battlefield if p.name == "Food Token" and p.controller == "alice"
    ]
    assert len(food) == 1


def test_tainted_treats_creates_no_food_token_off_an_expensive_permanent() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tainted Treats"],
            battlefield=["Swamp", "Swamp", "Forest"],
        )
        .player("bob", battlefield=["Serra Angel"])  # mana value 5
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve("Tainted Treats", auto=True, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
    food = [p for p in scenario.game.battlefield if p.name == "Food Token"]
    assert food == []


def test_extinguish_the_light_gains_life_off_a_cheap_permanent() -> None:
    """Off the reported card, off the deck pool: the identical "if its mana
    value was N or less" antecedent with a different consequence - proof
    this reader is not fitted to Tainted Treats' token alone."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Extinguish the Light"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"]
        )
        .player("bob", battlefield=["Grizzly Bears"])  # mana value 2
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    life_before = scenario.player("alice").life

    scenario.cast_and_resolve("Extinguish the Light", auto=True, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before + 3


def test_extinguish_the_light_gains_no_life_off_an_expensive_permanent() -> None:
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Extinguish the Light"], battlefield=["Swamp", "Swamp", "Swamp", "Swamp"]
        )
        .player("bob", battlefield=["Serra Angel"])  # mana value 5
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    life_before = scenario.player("alice").life

    scenario.cast_and_resolve("Extinguish the Light", auto=True, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == life_before


# -- Courier of Comestibles: search, else create a token ----------------------


def test_courier_of_comestibles_finds_a_food_card_and_creates_no_token() -> None:
    """A real Food card (Gingerbrute, off the deck pool) is in the library:
    finding it puts it into hand and CR 118.12's "if you don't" never fires."""
    scenario = (
        Scenario()
        .player("alice", hand=["Courier of Comestibles"], library=["Gingerbrute", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gingerbrute = scenario.find("Gingerbrute", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(gingerbrute, username="alice")

    scenario.put_onto_battlefield("Courier of Comestibles", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert gingerbrute.zone is Zone.HAND
    food = [p for p in scenario.game.battlefield if p.name == "Food Token"]
    assert food == []


def test_courier_of_comestibles_creates_a_food_token_when_no_food_card_is_found() -> None:
    """No Food card anywhere in the library: the search comes up empty and
    CR 118.12's "if you don't put a card into your hand this way" creates the
    Food token instead."""
    scenario = (
        Scenario().player("alice", hand=["Courier of Comestibles"], library=["Mountain"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Courier of Comestibles", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("alice").hand == []
    food = [p for p in scenario.game.battlefield if p.name == "Food Token"]
    assert len(food) == 1

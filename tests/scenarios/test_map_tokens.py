"""Scenario: the Map token (CR 111.10s) and Explore riding in on it (CR 701.44).

Every CR number below was looked up this session with `mise run rules:find
<n>` against `.rules/MagicCompRules.txt` (effective 2026-09-25).

- **CR 111.10s** - "A Map token is a colorless Map artifact token with '{1},
  {T}, Sacrifice this token: Target creature you control explores. Activate
  only as a sorcery.' See rule 701.44, "Explore.""
- **CR 701.44a-d** - explore itself: reveal the top card, a land goes to
  hand, anything else gets a +1/+1 counter and may go to the graveyard. Fully
  covered already in `test_explore.py` off Amalia Benavides Aguirre; this
  file's own explore assertions exist only to prove the *token's* activated
  ability really reaches that same machinery, not to re-litigate CR 701.44
  itself.
- **CR 601.2f** - an additional cost, paid as part of casting (Fanatical
  Offering's own sacrifice).
- **CR 400.7 / CR 608.2c** - "Its controller" (Get Lost) is anaphora back to
  whatever the first sentence's own verb found, not a second target of its
  own - the destroyed permanent's controller, never the caster.

Five real printings carry this task's own rows: Spyglass Siren and Sentinel
of the Nameless City (a Map off a trigger, with the token's own ability spelled
out only in the card's own reminder text), Get Lost (a referent "Its
controller creates two Map tokens" pointed at whoever the destroy found, not
the caster), Fanatical Offering (an additional-cost sacrifice ahead of a
compound "draw two and create a Map" resolution), and Restless Anchorage (an
attack trigger with no reminder text on the card at all - the whole thing
rests on `PREDEFINED["Map"]`).

Cartographer's Companion (Lost Caverns of Ixalan, Standard/Pioneer/Modern
legal, not one of this task's own cards and not in any `code/
magic-cards-model-api/decks/*.txt` list) is the second, unrelated printing
that proves the Map-token machinery is not fitted to the five cards above:
its own "When this creature enters, create a Map token." reaches the exact
same `PREDEFINED["Map"]` row with no card-specific code anywhere.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from magic_cards_model.models.card_state import Counter, TargetRef
from magic_cards_model.models.token import MAP, PREDEFINED
from tests.scenarios.harness import Scenario


def _map_tokens(scenario, username: str) -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if "Map" in state.subtypes
    ]


# -- CR 111.10s: the predefined token itself --------------------------------


def test_map_is_a_predefined_colorless_artifact_token():
    """The row this whole task hangs off: a real `TokenDefinition`, not a
    string constant - `create_tokens` turns this into a `CardState` the exact
    way it turns Treasure or Clue into one."""
    assert PREDEFINED["Map"] is MAP
    assert MAP.types == (Type.ARTIFACT,)
    assert MAP.subtypes == ("Map",)
    assert MAP.colors == ()
    assert MAP.rules_text == (
        "{1}, {T}, Sacrifice this token: Target creature you control explores. "
        "Activate only as a sorcery."
    )


# -- Spyglass Siren: a trigger whose token ability is only in the reminder --


def test_spyglass_siren_creates_a_map_token_on_etb():
    """ "When this creature enters, create a Map token." The card's own oracle
    text never uses the word "explore" outside the reminder parenthetical -
    proof that this does not depend on the card's own text carrying an
    explore clause, only on the token it creates."""
    scenario = (
        Scenario()
        .player("alice", hand=["Spyglass Siren"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island")
    scenario.cast_and_resolve("Spyglass Siren", island)
    assert scenario.stack_names() == ["Spyglass Siren's triggered ability"]
    scenario.resolve_top()

    (token,) = _map_tokens(scenario, "alice")
    assert token.name == "Map Token"
    assert token.zone is Zone.BATTLEFIELD


def test_spyglass_sirens_map_token_explores_a_nonland_for_a_counter():
    """The created token's own activated ability really reaches CR 701.44a's
    machinery: sacrifice it, target the Siren itself, get a counter off a
    nonland reveal."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spyglass Siren"],
            battlefield=["Island", "Island"],
            library=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    island_for_spell, island_for_map = scenario.untapped_sources("Island", "Island")
    siren = scenario.cast_and_resolve("Spyglass Siren", island_for_spell)
    scenario.resolve_top()
    (token,) = _map_tokens(scenario, "alice")

    scenario.activate(
        token,
        island_for_map,
        sacrificing=[token],
        targets=[TargetRef.coerce(siren)],
    )
    scenario.pass_until_resolved()

    assert token.zone is Zone.GRAVEYARD
    assert siren.counters[Counter.PLUS_ONE] == 1
    # CR 701.44a's nonland branch defaults to keeping the revealed card on
    # top when nobody answers the back-or-graveyard question (the same
    # default `test_explore.py` documents for Amalia).
    assert [state.card.name for state in scenario.player("alice").library] == ["Llanowar Elves"]


# -- Sentinel of the Nameless City: "enters or attacks" -----------------------


def test_sentinel_of_the_nameless_city_creates_a_map_on_attack():
    """The "or attacks" half of its trigger - a second real event, not the
    ETB half `Spyglass Siren` already proves."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Sentinel of the Nameless City"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    sentinel = scenario.creature("Sentinel of the Nameless City", "alice")
    scenario.attack_with(sentinel)
    assert scenario.stack_names() == ["Sentinel of the Nameless City's triggered ability"]
    scenario.resolve_top()

    (token,) = _map_tokens(scenario, "alice")
    assert token.name == "Map Token"


# -- Get Lost: the referent is the destroyed permanent's controller ---------


def test_get_lost_gives_the_map_tokens_to_the_destroyed_creatures_controller():
    """ "Its controller creates two Map tokens." Alice casts Get Lost on Bob's
    creature; the tokens belong to Bob, never to Alice, who cast the spell."""
    scenario = (
        Scenario()
        .player("alice", hand=["Get Lost"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains = scenario.untapped_sources("Plains", "Plains")
    bear = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Get Lost", *plains, targets=[TargetRef.coerce(bear)])

    assert bear.zone is Zone.GRAVEYARD
    assert _map_tokens(scenario, "bob") != []
    assert len(_map_tokens(scenario, "bob")) == 2
    assert _map_tokens(scenario, "alice") == []


# -- Fanatical Offering: additional cost, then a compound resolution -------


def test_fanatical_offering_sacrifices_draws_two_and_makes_a_map():
    """ "As an additional cost to cast this spell, sacrifice an artifact or
    creature. Draw two cards and create a Map token." All three effects of
    one card, or none of them - CR 608.2c has no notion of running half of
    this."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fanatical Offering"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
            library=["Mountain", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swamps = scenario.untapped_sources("Swamp", "Swamp")
    bear = scenario.creature("Grizzly Bears", "alice")

    scenario.cast_and_resolve("Fanatical Offering", *swamps, sacrificing=[bear])

    assert bear.zone is Zone.GRAVEYARD
    assert [state.card.name for state in scenario.player("alice").hand] == [
        "Mountain",
        "Forest",
    ]
    (token,) = _map_tokens(scenario, "alice")
    assert token.name == "Map Token"


# -- Restless Anchorage: no reminder text at all, PREDEFINED does the work -


def test_restless_anchorage_creates_a_map_when_it_attacks():
    """ "Whenever this land attacks, create a Map token." No reminder text on
    this printing to fall back on - the only reason this works at all is
    that "Map" now has a real row in `PREDEFINED`."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Restless Anchorage", "Plains", "Island", "Wastes"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anchorage = scenario.find("Restless Anchorage", Zone.BATTLEFIELD)
    wastes, plains, island = scenario.untapped_sources("Wastes", "Plains", "Island")
    scenario.activate(anchorage, wastes, plains, island, index=1)
    scenario.pass_until_resolved()
    assert Type.CREATURE in scenario.game.characteristics_of(anchorage).types

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(anchorage)
    assert scenario.stack_names() == ["Restless Anchorage's triggered ability"]
    scenario.resolve_top()

    (token,) = _map_tokens(scenario, "alice")
    assert token.name == "Map Token"


def test_restless_anchorages_own_animation_clause_is_unaffected():
    """The static-unaudited animation clause this task's own notes say to
    "verify" - it must still turn the land into a 2/3 white and blue Bird
    with flying, independent of anything this task changed about Map."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Restless Anchorage", "Plains", "Island", "Wastes"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    anchorage = scenario.find("Restless Anchorage", Zone.BATTLEFIELD)
    wastes, plains, island = scenario.untapped_sources("Wastes", "Plains", "Island")

    scenario.activate(anchorage, wastes, plains, island, index=1)
    scenario.pass_until_resolved()

    characteristics = scenario.game.characteristics_of(anchorage)
    assert Type.CREATURE in characteristics.types
    assert scenario.game.power_of(anchorage) == 2
    assert scenario.game.toughness_of(anchorage) == 3


# -- Cartographer's Companion: the second, unrelated printing --------------


def test_cartographers_companion_proves_map_token_creation_is_not_card_specific():
    """Lost Caverns of Ixalan's own "When this creature enters, create a Map
    token." - Standard/Pioneer/Modern legal, not one of this task's own
    cards, not in any deck list this pool plays. If Map token creation only
    worked for the five named cards, this one would come up silent too."""
    scenario = (
        Scenario()
        .player("alice", hand=["Cartographer's Companion"], battlefield=["Wastes"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes")
    scenario.cast_and_resolve("Cartographer's Companion", *sources)
    assert scenario.stack_names() == ["Cartographer's Companion's triggered ability"]
    scenario.resolve_top()

    (token,) = _map_tokens(scenario, "alice")
    assert token.name == "Map Token"
    assert "explores" in (token.card.oracle_text or "").lower()

"""Scenario: library search-to-hand-or-graveyard and look/select readers
(Secrets of Strixhaven, T8).

Six shapes, all CR 608.2d choices over cards the resolving spell or ability
looked at (or searched out) itself:

- Dina's Guidance: "Search your library for a creature card, reveal it, put
  it into your hand or graveyard, then shuffle." A mandatory search (no
  "you may" printed) whose *find* stays optional per CR 701.23b regardless,
  landing in a real two-zone choice once one is found.
- Flow State: "Look at the top three cards of your library. Put one of them
  into your hand and the rest on the bottom of your library in any order. If
  there is an instant card and a sorcery card in your graveyard, instead put
  two of them into your hand and the rest on the bottom of your library in
  any order." One shared look, an amount that depends on a live board
  condition read at resolution (CR 608.2c).
- Paradox Surveyor: ETB "look at the top five cards of your library. You may
  reveal a land card or a card with {X} in its mana cost from among them and
  put it into your hand. Put the rest on the bottom of your library in a
  random order." A two-noun-phrase "or" quality, not a bare type list.
- Stirring Honormancer: ETB "look at the top X cards of your library, where
  X is the number of creatures you control. Put one of those cards into your
  hand and the rest into your graveyard." A dynamic (CR 107.3f) count.
- Zimone's Experiment: "Look at the top five cards of your library. You may
  reveal up to two creature and/or land cards from among them, then put the
  rest on the bottom of your library in a random order. Put all land cards
  revealed this way onto the battlefield tapped and put all creature cards
  revealed this way into your hand." One reveal, two destinations by type.
- Stress Dream: "Stress Dream deals 5 damage to up to one target creature.
  Look at the top two cards of your library. Put one of those cards into
  your hand and the other on the bottom of your library." An independent
  damage clause ahead of the identical Waker-of-Waves-family split.
- Visionary's Dance: "Create two 3/3 blue and red Elemental creature tokens
  with flying. {2}, Discard this card: Look at the top two cards of your
  library. Put one of them into your hand and the other into your
  graveyard." A printed activated ability that functions from hand
  (CR 113.6j), trailing a sorcery's own resolution text - proved general
  (not fitted to this one printing) on Elemental Masterpiece, a different
  card with the identical two-part shape.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 701.23a/701.23b/701.23g** - searching a hidden zone for a stated
  quality is never a required find, and the search is offered to the player
  the text names.
- **CR 701.24a/701.24b** - the shuffle happens once the find is taken out.
- **CR 701.20a/701.20e** - reveal shows a card to everyone; look shows it
  only to the specified player.
- **CR 608.2c/608.2d** - instructions run in the order written, and CR
  608.2d choices are announced as the effect applies.
- **CR 401.4** - "in any order" is the owning player's own arrangement, once
  two or more cards go to the same library position at once.
- **CR 107.3f** - an undefined X in effect text is defined by a trailing
  "where X is" clause.
- **CR 110.2a** - a permanent an effect puts onto the battlefield with
  nobody else named enters under that effect's own controller's control.
- **CR 113.6j** - some activated abilities function only from a zone other
  than the battlefield, printed on the card itself.
- **CR 120.3e/704.5g** - damage marked on a creature that is lethal is a
  state-based action.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario, mana_from


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


# -- Dina's Guidance ----------------------------------------------------


def test_dinas_guidance_puts_the_found_creature_into_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dina's Guidance"],
            battlefield=["Swamp", "Forest", "Plains"],
            library=["Island", "Grizzly Bears", "Mountain"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Forest", "Plains")
    scenario.will_choose_hand_or_graveyard(True)
    scenario.cast_and_resolve("Dina's Guidance", *sources)
    assert [card.name for card in alice.hand] == ["Grizzly Bears"]
    assert [card.name for card in alice.graveyard] == ["Dina's Guidance"]
    assert "Grizzly Bears" not in [card.name for card in alice.library]


def test_dinas_guidance_puts_the_found_creature_into_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dina's Guidance"],
            battlefield=["Swamp", "Forest", "Plains"],
            library=["Island", "Grizzly Bears", "Mountain"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Forest", "Plains")
    scenario.will_choose_hand_or_graveyard(False)
    scenario.cast_and_resolve("Dina's Guidance", *sources)
    assert alice.hand == []
    assert sorted(card.name for card in alice.graveyard) == sorted(
        ["Dina's Guidance", "Grizzly Bears"]
    )


def test_dinas_guidance_may_find_nothing_and_still_shuffles():
    """CR 701.23b: a stated-quality search never has to find anything, even
    with no "you may" printed - the search itself is mandatory, only the
    find is optional. `search_library`'s own decline leaves the whole
    library, still shuffled (CR 701.24a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dina's Guidance"],
            battlefield=["Swamp", "Forest", "Plains"],
            library=["Island", "Grizzly Bears", "Mountain"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Swamp", "Forest", "Plains")
    scenario.will_choose_cards(username="alice")  # decline the search: choose none
    scenario.cast_and_resolve("Dina's Guidance", *sources)
    assert alice.hand == []
    assert [card.name for card in alice.graveyard] == ["Dina's Guidance"]
    assert len(alice.library) == 3


# -- Flow State -----------------------------------------------------------


def test_flow_state_base_puts_one_into_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flow State"],
            battlefield=["Island", "Mountain"],
            library=["Mountain", "Plains", "Forest", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    island, mountain = scenario.untapped_sources("Island", "Mountain")
    top_three = list(alice.library[:3])
    scenario.scry_bottoming(top_three[0])
    scenario.cast_and_resolve("Flow State", island, mountain)
    assert [card.name for card in alice.hand] == [top_three[0].name]
    # the other two go to the bottom, under "Swamp" which was already there
    assert [card.name for card in alice.library] == [
        "Swamp",
        top_three[1].name,
        top_three[2].name,
    ]


def test_flow_state_instead_puts_two_into_hand_with_instant_and_sorcery_in_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flow State"],
            battlefield=["Island", "Mountain"],
            graveyard=["Lightning Bolt", "Divination"],
            library=["Mountain", "Plains", "Forest", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    assert any(Type.INSTANT in card.types for card in alice.graveyard)
    assert any(Type.SORCERY in card.types for card in alice.graveyard)
    island, mountain = scenario.untapped_sources("Island", "Mountain")
    top_three = list(alice.library[:3])
    scenario.scry_bottoming(top_three[0], top_three[1])
    scenario.cast_and_resolve("Flow State", island, mountain)
    assert sorted(card.name for card in alice.hand) == sorted(
        [top_three[0].name, top_three[1].name]
    )
    assert [card.name for card in alice.library] == ["Swamp", top_three[2].name]


def test_flow_state_without_both_instant_and_sorcery_still_only_puts_one():
    """Only a sorcery in the graveyard - not "an instant card *and* a
    sorcery card" - so the condition fails and the base amount (one) stands."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flow State"],
            battlefield=["Island", "Mountain"],
            graveyard=["Opt"],
            library=["Mountain", "Plains", "Forest"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    island, mountain = scenario.untapped_sources("Island", "Mountain")
    top_three = list(alice.library[:3])
    scenario.scry_bottoming(top_three[0])
    scenario.cast_and_resolve("Flow State", island, mountain)
    assert len(alice.hand) == 1


# -- Paradox Surveyor -------------------------------------------------------


def test_paradox_surveyor_reveals_a_land_from_among_the_top_five():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Paradox Surveyor"],
            battlefield=["Forest", "Island"],
            library=["Grizzly Bears", "Mountain", "Opt", "Shock", "Plains"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_five = list(alice.library[:5])
    mountain = next(card for card in top_five if card.name == "Mountain")
    scenario.scry_bottoming(mountain)
    scenario.put_onto_battlefield("Paradox Surveyor")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert [card.name for card in alice.hand] == ["Mountain"]
    assert mountain not in alice.library


def test_paradox_surveyor_reveals_a_card_with_x_in_its_mana_cost():
    """ "a card with {X} in its mana cost" - Fireball has {X}{R} printed, and
    is not itself a land, proving the second half of the "or" independently
    of the first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Paradox Surveyor"],
            battlefield=["Forest", "Island"],
            library=["Grizzly Bears", "Fireball", "Opt", "Shock", "Island"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_five = list(alice.library[:5])
    fireball = next(card for card in top_five if card.name == "Fireball")
    scenario.scry_bottoming(fireball)
    scenario.put_onto_battlefield("Paradox Surveyor")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert [card.name for card in alice.hand] == ["Fireball"]


def test_paradox_surveyor_may_decline_and_puts_all_five_to_the_bottom():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Paradox Surveyor"],
            battlefield=["Forest", "Island"],
            library=["Grizzly Bears", "Mountain", "Opt", "Shock", "Plains"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_five = [card.name for card in alice.library[:5]]
    scenario.scry_keeping_everything_on_top()  # declines: nothing moves to hand
    scenario.put_onto_battlefield("Paradox Surveyor")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert alice.hand == []
    assert len(alice.library) == 5
    assert sorted(card.name for card in alice.library) == sorted(top_five)


# -- Stirring Honormancer ----------------------------------------------------


def test_stirring_honormancer_x_is_creatures_you_control():
    """Two creatures on the board (Stirring Honormancer itself plus one more)
    means X=2: look at the top two, one to hand, the other to the
    graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stirring Honormancer"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Swamp", "Swamp"],
            library=["Mountain", "Island"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_two = list(alice.library[:2])
    scenario.scry_bottoming(top_two[0])
    scenario.put_onto_battlefield("Stirring Honormancer")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert [card.name for card in alice.hand] == [top_two[0].name]
    assert [card.name for card in alice.graveyard] == [top_two[1].name]


def test_stirring_honormancer_with_no_other_creatures_looks_at_only_itself():
    """X is the number of creatures *you control* - Stirring Honormancer
    counts itself the instant its own ETB trigger resolves."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stirring Honormancer"],
            battlefield=["Plains", "Plains", "Swamp", "Swamp"],
            library=["Mountain", "Island"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_one = alice.library[0]
    scenario.scry_bottoming(top_one)
    scenario.put_onto_battlefield("Stirring Honormancer")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert [card.name for card in alice.hand] == [top_one.name]
    assert alice.graveyard == []


# -- Zimone's Experiment -----------------------------------------------------


def test_zimones_experiment_splits_lands_to_battlefield_and_creatures_to_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zimone's Experiment"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Mountain", "Opt", "Shock", "Plains"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_five = list(alice.library[:5])
    bears = next(card for card in top_five if card.name == "Grizzly Bears")
    mountain = next(card for card in top_five if card.name == "Mountain")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.scry_bottoming(bears, mountain)
    scenario.cast_and_resolve("Zimone's Experiment", *sources)
    assert [card.name for card in alice.hand] == ["Grizzly Bears"]
    battlefield_names = [
        state.card.name for state in scenario.game.battlefield if state.controller == "alice"
    ]
    assert "Mountain" in battlefield_names
    tapped_mountain = next(
        state
        for state in scenario.game.battlefield
        if state.card.name == "Mountain" and state.id == mountain.id
    )
    assert tapped_mountain.tapped
    assert len(alice.library) == 3


def test_zimones_experiment_may_reveal_fewer_than_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Zimone's Experiment"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
            library=["Grizzly Bears", "Opt", "Shock", "Island", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_five = list(alice.library[:5])
    bears = next(card for card in top_five if card.name == "Grizzly Bears")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    scenario.scry_bottoming(bears)
    scenario.cast_and_resolve("Zimone's Experiment", *sources)
    assert [card.name for card in alice.hand] == ["Grizzly Bears"]
    assert len(alice.library) == 4


# -- Stress Dream -------------------------------------------------------


def test_stress_dream_deals_damage_and_splits_the_top_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stress Dream"],
            battlefield=["Island", "Island", "Mountain", "Mountain", "Forest"],
            library=["Forest", "Swamp"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    _to_main(scenario)
    bears = scenario.creature("Grizzly Bears", "bob")
    alice = scenario.player("alice")
    top_two = list(alice.library[:2])
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain", "Forest")
    scenario.scry_bottoming(top_two[0])
    scenario.cast_and_resolve("Stress Dream", *sources, targets=[bears])
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD, "a 2/2 takes 5 damage"
    assert [card.name for card in alice.hand] == [top_two[0].name]
    assert [card.name for card in alice.library] == [top_two[1].name]


def test_stress_dream_with_no_target_still_looks_at_the_top_two():
    """ "up to one target creature" - zero is legal (CR 601.2c), and the
    library-select half still happens (CR 608.2c runs every instruction the
    text prints)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stress Dream"],
            battlefield=["Island", "Island", "Mountain", "Mountain", "Forest"],
            library=["Forest", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    top_two = list(alice.library[:2])
    sources = scenario.untapped_sources("Island", "Island", "Mountain", "Mountain", "Forest")
    scenario.scry_bottoming(top_two[0])
    scenario.cast_and_resolve("Stress Dream", *sources, targets=[])
    assert [card.name for card in alice.hand] == [top_two[0].name]


# -- Visionary's Dance --------------------------------------------------


def test_visionary_dance_casts_for_tokens():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Visionary's Dance"],
            battlefield=["Island", "Island"] + ["Mountain"] * 5,
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(
        "Island", "Island", "Mountain", "Mountain", "Mountain", "Mountain", "Mountain"
    )
    scenario.cast_and_resolve("Visionary's Dance", *sources)
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Elemental" in state.subtypes
    ]
    assert len(tokens) == 2
    assert all(token.power == 3 and token.toughness == 3 for token in tokens)
    assert alice.hand == []
    assert [card.name for card in alice.graveyard] == ["Visionary's Dance"]


def test_visionary_dance_discard_ability_splits_top_two():
    """The printed off-zone activated ability ("{2}, Discard this card: ...")
    functions only while the card is in hand (CR 113.6j) - here activated
    instead of casting the spell at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Visionary's Dance"],
            battlefield=["Island", "Island"],
            library=["Forest", "Swamp"],
        )
        .build()
    )
    _to_main(scenario)
    alice = scenario.player("alice")
    dance = scenario.find("Visionary's Dance", Zone.HAND, "alice")
    top_two = list(alice.library[:2])
    islands = scenario.untapped_sources("Island", "Island")
    scenario.scry_bottoming(top_two[0])

    activation = off_battlefield_activation(scenario.game, dance, "alice")
    assert activation.zone is Zone.HAND
    payment = activation.begin_paying()
    for island in islands:
        payment.tap_for_mana(island, mana_from(island))
    payment.pay()
    activation.activate()
    activation.resolve()

    assert dance.zone is Zone.GRAVEYARD
    assert [card.name for card in alice.hand] == [top_two[0].name]
    assert top_two[1].zone is Zone.GRAVEYARD
    assert alice.library == []


def test_elemental_masterpiece_proves_the_same_trailing_ability_shape():
    """Elemental Masterpiece: "Create two 4/4 blue and red Elemental
    creature tokens. / {U/R}{U/R}, Discard this card: Create a Treasure
    token." - a different card sharing Visionary's Dance's exact "spell body
    plus a trailing off-zone activated ability" shape, proving `effect_for`'s
    strip of that trailing ability is not fitted to one printing: without it,
    the token-creation sentence would fail closed along with it (CR 608.2c
    has no notion of running half a card)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Elemental Masterpiece"],
            battlefield=["Island"] * 4 + ["Mountain"] * 3,
        )
        .build()
    )
    _to_main(scenario)
    sources = scenario.untapped_sources(*(["Island"] * 4 + ["Mountain"] * 3))
    scenario.cast_and_resolve("Elemental Masterpiece", *sources)
    tokens = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and "Elemental" in state.subtypes
    ]
    assert len(tokens) == 2
    assert all(token.power == 4 and token.toughness == 4 for token in tokens)

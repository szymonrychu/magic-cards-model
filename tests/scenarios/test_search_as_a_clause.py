"""Scenario: a library search as one clause among several, read off a card's
own printed text with no per-card table row.

`machines/effects.py`'s `_parse_search_clause` (built on `_SEARCH_AND_PUT_RE`)
used to only `fullmatch` a whole effect, which meant a card whose search was
just *one* instruction among several - "Destroy target land. Its controller
may search their library for a basic land card, put it onto the battlefield,
then shuffle." - needed a table row even though every individual clause was
independently readable. W3 folded the search shape into `parse_mixed_effect`'s
per-clause dispatcher (`_parse_mixed_clause`), which is what lets Ghost
Quarter, White Orchid Phantom, and Ranger-Captain of Eos drop their rows in
`TRIGGER_EFFECTS`/`ACTIVATED_EFFECTS`.

Every CR number below was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.

- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.23b** - a search for a stated quality "isn't required to find some
  or all of those cards even if they're present in that zone."
- **CR 701.23g** - "If an effect offers a player a choice to search a zone and
  take additional actions with the cards found, that player may choose to
  search even if the additional actions are illegal or impossible" - the
  printed "may" is a choice to search at all, asked of whichever player the
  sentence names.
- **CR 701.24a** - shuffling a library randomizes it; that only happens as
  part of an actual search, which is why declining the "may" leaves the
  library's order untouched.
- **CR 202.3** - mana value, "the total amount of mana in its mana cost" -
  Ranger-Captain of Eos's bound.
- **CR 202.3e** - while an object with `{X}` in its cost is not on the stack,
  X is treated as 0 - part of why Green Sun's Zenith and Fiend Artisan's
  "mana value X or less" cannot be read as a fixed number here and are
  deliberately left unscripted rather than silently bound to 0.
- **CR 608.2c** - a spell or ability's instructions run "in the order
  written", which is why a destroy clause and a search clause are two
  instructions, not one, and why one unreadable clause takes the whole
  effect down (CR 608.2c has no notion of running half an effect).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import effect_for, parse_mixed_effect
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

# -- Ghost Quarter: "its controller" is not the activator -------------------


def test_ghost_quarter_destroys_and_lets_its_victim_search():
    """`{T}, Sacrifice this land: Destroy target land. Its controller may
    search their library for a basic land card, put it onto the battlefield,
    then shuffle.`

    Alice activates it against Bob's Mountain. The search is *Bob's* choice,
    not Alice's (CR 701.23g), and the land he finds enters untapped (Ghost
    Quarter's template says nothing about "tapped").
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ghost Quarter"])
        .player("bob", battlefield=["Mountain"], library=["Plains", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quarter = scenario.find("Ghost Quarter", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    scenario.will_take_the_may(True, username="bob")

    scenario.activate(quarter, index=1, sacrificing=[quarter], targets=[mountain])
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.GRAVEYARD
    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.tapped is False
    assert [state.card.name for state in scenario.player("bob").library] == ["Forest"]


def test_ghost_quarters_victim_can_decline_and_the_library_stays_unshuffled():
    """CR 701.23g's "may" covers the search itself, not just finding a card -
    declining it means no search event happens at all, so CR 701.24a's shuffle
    never fires either. The library Bob was stacked with stays in that exact
    order.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ghost Quarter"])
        .player("bob", battlefield=["Mountain"], library=["Plains", "Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    quarter = scenario.find("Ghost Quarter", Zone.BATTLEFIELD)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    scenario.will_take_the_may(False, username="bob")

    scenario.activate(quarter, index=1, sacrificing=[quarter], targets=[mountain])
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.GRAVEYARD
    assert [state.card.name for state in scenario.player("bob").library] == [
        "Plains",
        "Forest",
        "Island",
    ]


def test_no_fetchland_or_ghost_quarter_row_shadows_the_dispatcher():
    """`ACTIVATED_EFFECTS` must not have re-grown a Ghost Quarter row - an
    explicit row always wins over `activated_effect_for`'s fallback, so a
    re-added entry would silently shadow `parse_mixed_effect` exactly the way
    the old table shadowed `parse_search_and_put_effect` for the nine
    fetchlands before this project's earlier waves deleted their rows.
    """
    from magic_cards_model.machines.effects import ACTIVATED_EFFECTS

    assert ("Ghost Quarter", 1) not in ACTIVATED_EFFECTS


# -- White Orchid Phantom: the same shape, off a triggered ability ----------


def test_white_orchid_phantom_destroys_and_finds_a_basic_tapped():
    """`When this creature enters, destroy up to one target nonbasic land.
    Its controller may search their library for a basic land card, put it
    onto the battlefield tapped, then shuffle.`

    Unlike Ghost Quarter, White Orchid Phantom's found land enters **tapped**
    - its own addition to the shared template, read off the word "tapped" in
    its own printed text rather than a hardcoded difference between two
    registry rows.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["White Orchid Phantom"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Sacred Foundry"], library=["Mountain", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains")
    foundry = scenario.find("Sacred Foundry", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("White Orchid Phantom", [foundry])
    scenario.will_take_the_may(True, username="bob")

    scenario.cast_and_resolve("White Orchid Phantom", *sources)
    scenario.pass_until_resolved()

    assert foundry.zone is Zone.GRAVEYARD
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert mountain.tapped is True
    assert [state.card.name for state in scenario.player("bob").library] == ["Forest"]


def test_no_white_orchid_phantom_row_shadows_the_dispatcher():
    """The `TRIGGER_EFFECTS` twin of the Ghost Quarter guard above."""
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.effects import TRIGGER_EFFECTS

    assert ("White Orchid Phantom", TriggerEvent.ENTERS_THE_BATTLEFIELD, "") not in TRIGGER_EFFECTS


# -- Ranger-Captain of Eos: destination hand, and a mana-value bound --------


def test_ranger_captain_of_eos_finds_a_low_cost_creature_into_hand():
    """`When this creature enters, you may search your library for a creature
    card with mana value 1 or less, reveal it, put it into your hand, then
    shuffle.`

    Delver of Secrets is mana value 1 (CR 202.3), and this template's
    destination is the hand, not the battlefield - the other half of what W3
    added to the search-clause parser.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ranger-Captain of Eos"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Delver of Secrets"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.will_take_the_may(True, username="alice")

    scenario.cast_and_resolve("Ranger-Captain of Eos", *sources)
    scenario.pass_until_resolved()

    found = scenario.find("Delver of Secrets // Insectile Aberration", Zone.HAND, "alice")
    assert found.zone is Zone.HAND


def test_ranger_captain_of_eos_cannot_find_a_creature_above_the_bound():
    """Grizzly Bears is mana value 2 - above Ranger-Captain's "mana value 1 or
    less" - so the search finds nothing (CR 701.23b makes that a legal
    result) and it stays in the library.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ranger-Captain of Eos"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Grizzly Bears"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.will_take_the_may(True, username="alice")

    scenario.cast_and_resolve("Ranger-Captain of Eos", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert [state.card.name for state in scenario.player("alice").library] == ["Grizzly Bears"]


def test_ranger_captain_of_eos_declined_search_leaves_the_library_unshuffled():
    """Declining the "you may search" leaves the stacked library order intact,
    the same CR 701.23g/CR 701.24a distinction Ghost Quarter's decline test
    above proves.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ranger-Captain of Eos"],
            battlefield=["Plains", "Plains", "Plains"],
            library=["Delver of Secrets", "Forest", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", "Plains")
    scenario.will_take_the_may(False, username="alice")

    scenario.cast_and_resolve("Ranger-Captain of Eos", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert [state.card.name for state in scenario.player("alice").library] == [
        "Delver of Secrets // Insectile Aberration",
        "Forest",
        "Island",
    ]


def test_no_ranger_captain_of_eos_row_shadows_the_dispatcher():
    from magic_cards_model.machines.abilities import TriggerEvent
    from magic_cards_model.machines.effects import TRIGGER_EFFECTS

    assert ("Ranger-Captain of Eos", TriggerEvent.ENTERS_THE_BATTLEFIELD, "") not in TRIGGER_EFFECTS


# -- fail-closed: one bad clause, or an X, takes the whole effect down ------


def test_a_multi_clause_effect_with_one_unreadable_clause_parses_to_nothing():
    """A synthetic two-clause text: a destroy clause `_parse_targeted_clause`
    reads fine, then a search bounded by "mana value X or less" - the same
    unbound quantity Green Sun's Zenith and Fiend Artisan print, which
    `_SEARCH_AND_PUT_RE`'s `max_mv` group (`\\d+`) never matches.

    CR 608.2c: a spell or ability's instructions run in the order written with
    no notion of running half of them, so the whole thing has to come back
    `None` rather than destroying the land and silently skipping the search.
    """
    text = (
        "Destroy target land. Its controller may search their library for a "
        "creature card with mana value X or less, put it onto the "
        "battlefield, then shuffle."
    )
    assert parse_mixed_effect(text) is None


def test_green_suns_zenith_x_search_still_fails_closed():
    """Green Sun's Zenith: "Search your library for a green creature card
    with mana value X or less, put it onto the battlefield, then shuffle.
    Shuffle Green Sun's Zenith into its owner's library."

    CR 202.3e: while an object with {X} in its cost is not on the stack, X is
    treated as 0 - but this engine does not track the X chosen for a spell on
    the stack either (see `docs/engine-coverage.md`), so silently reading "X
    or less" as "0 or less" would be a guess, not a rule. `effect_for` comes
    back `None` rather than guessing.
    """
    zenith = card("Green Sun's Zenith")
    assert effect_for(zenith.name, zenith.oracle_text) is None


def test_fiend_artisans_x_search_still_fails_closed():
    """The activated-ability twin of the Zenith test above: "{X}{B/G}, {T},
    Sacrifice another creature: Search your library for a creature card with
    mana value X or less, put it onto the battlefield, then shuffle. Activate
    only as a sorcery." Read directly off the card's own parsed ability, not
    retyped, so a future change to its printed text is what this test sees.
    """
    from magic_cards_model.machines.abilities import ActivatedAbility, parse_abilities

    (search_ability,) = [
        ability
        for ability in parse_abilities(card("Fiend Artisan"))
        if isinstance(ability, ActivatedAbility) and "search" in ability.effect.lower()
    ]
    assert parse_mixed_effect(search_ability.effect) is None

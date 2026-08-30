"""W7a: the long tail of activated abilities - nine cards whose activated
ability's *effect clause* `machines/effects.py` could not read, each verified
against real Scryfall printings from `tests/fixtures/cards`.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file.

- **Walking Ballista** - `{4}: Put a +1/+1 counter on this creature.` - a
  self-referential counter placement with no target at all (CR 122.1),
  `_parse_put_counters_on_self_clause`.
- **Devoted Druid** - `Put a -1/-1 counter on this creature: Untap this
  creature.` - the cost side (`PLACE_COUNTERS`) already worked; only the
  untap effect was missing (CR 701.26b), `_parse_untap_self_clause`.
- **The Filigree Sylex** - `{T}: Put an oil counter on The Filigree Sylex.`
  and `{T}, Sacrifice The Filigree Sylex: Destroy each nonland permanent with
  mana value equal to the number of oil counters on The Filigree Sylex.` -
  both self-reference the permanent **by its own printed name** rather than
  "this artifact" (CR 201.5, CR 700.7), read via
  `Game._self_normalized_effect_text`/`Game._cost_refers_to_self`. The third
  ability's "Remove ten oil counters from among permanents you control" cost
  is a distribution problem `cost_component_for_phrase` explicitly declines
  (CR 602.5), and stays a raised refusal.
- **The Legend of Roku // Avatar Roku** - `{8}: Create a 4/4 red Dragon
  creature token with flying and firebending 4.` - CR 702.189a's "Firebending
  N" keyword, read via a whole-text token-clause parser
  (`_parse_whole_text_token_clause`) that sidesteps `split_effect_clauses`'
  bare-"and" cut.
- **Abstergo Entertainment** - `{3}, {T}, Exile Abstergo Entertainment:
  Return up to one target historic card from your graveyard to your hand,
  then exile all graveyards.` - CR 700.6's "historic" qualifier
  (`TargetRequirement.historic`), and the ability's own self-reference-by-name
  cost (`Game._self_normalized_cost_text`).
- **Agatha's Soul Cauldron** - `{T}: Exile target card from a graveyard. When
  a creature card is exiled this way, put a +1/+1 counter on target creature
  you control.` - CR 603.12's reflexive-trigger shape, conditioned on the
  *type* of what was exiled rather than a player's choice
  (`_parse_exile_target_card_reflexive_creature_counter`).
- **Grist, the Hunger Tide** - `+1: Create a 1/1 black and green Insect
  creature token, then mill a card. If an Insect card was milled this way,
  put a loyalty counter on Grist and repeat this process.` - a
  self-terminating loop reading the specific card just milled
  (`_parse_create_token_mill_repeat_clause`).
- **Tyvar, Jubilant Brawler** - `-2: Mill three cards, then you may return a
  creature card with mana value 2 or less from your graveyard to the
  battlefield.` - a resolution-time choice among the whole graveyard, not a
  target (CR 608.2d, `_parse_mill_then_may_return_creature_clause`).
- **Fiend Artisan** - `{X}{B/G}, {T}, Sacrifice another creature: Search your
  library for a creature card with mana value X or less, put it onto the
  battlefield, then shuffle. Activate only as a sorcery.` - CR 107.3a's X,
  extended from spells onto activated abilities (`AbilityOnStack.x_value`,
  `Game.activate_ability`'s new `x_value` parameter).

Rules cited:

- **CR 122.1, 122.1a** - counters, and how `+1/+1`/`-1/-1` change power and
  toughness.
- **CR 701.26b** - "To 'untap' a permanent means to turn it faceup ... if it
  wasn't already untapped."
- **CR 201.5** - "Text that refers to the object it's on by name means just
  that particular object."
- **CR 700.7** - "this [something]" self-reference.
- **CR 602.5** - "A player can't begin to activate an ability that's
  prohibited from being activated."
- **CR 702.189a** - "Firebending is a triggered ability. 'Firebending N'
  means 'Whenever this creature attacks, add N {R}. ...'"
- **CR 700.6** - "The term historic refers to an object that has the
  legendary supertype, the artifact card type, or the Saga subtype."
- **CR 603.12** - reflexive triggered abilities, checked immediately after
  being created.
- **CR 400.2** - the graveyard is a public zone, with no "just arrived"
  exception for what a resolving ability may act on.
- **CR 107.3a** - "Some effects allow a player to choose the value of a
  variable, usually represented by X ... The player announces the value of X
  ... as part of casting a spell or activating an ability that includes it."
- **CR 704.5f** - a creature with toughness 0 or less is put into its owner's
  graveyard (the Devoted Druid loop's own termination).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Walking Ballista - {4}: Put a +1/+1 counter on this creature.
# --------------------------------------------------------------------------


def test_walking_ballistas_four_ability_adds_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Walking Ballista", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob", library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "alice")
    ballista.add_counters(Counter.PLUS_ONE, 1)  # a live 1/1, not a fresh 0/0
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.activate(ballista, *sources)
    scenario.pass_until_resolved()

    assert ballista.counter_count(Counter.PLUS_ONE) == 2
    assert ballista.power == 2 and ballista.toughness == 2


def test_walking_ballistas_removal_ability_is_undisturbed():
    """The pre-existing "remove a counter: deal 1 damage" ability (index 1)
    still works after this wave, unaffected by the new `{4}` ability."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Walking Ballista"])
        .player("bob", library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista", "alice")
    ballista.add_counters(Counter.PLUS_ONE, 2)
    bob = scenario.player("bob")

    scenario.activate(ballista, index=1, targets=["bob"])
    scenario.pass_until_resolved()

    assert ballista.counter_count(Counter.PLUS_ONE) == 1
    assert bob.life == 19


# --------------------------------------------------------------------------
# Devoted Druid - Put a -1/-1 counter on this creature: Untap this creature.
# --------------------------------------------------------------------------


def _devoted_druid_board() -> Scenario:
    return (
        Scenario().player("alice", battlefield=["Devoted Druid"]).player("bob", library=["Island"])
    )


def test_paying_the_cost_untaps_devoted_druid():
    scenario = _devoted_druid_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid", "alice")
    alice = scenario.player("alice")

    scenario.activate(druid, index=0)  # {T}: Add {G} - taps it
    assert druid.tapped
    assert alice.mana_pool.floating

    scenario.activate(druid, index=1)  # the untap ability
    scenario.pass_until_resolved()

    assert druid.counter_count(Counter.MINUS_ONE) == 1
    assert druid.toughness == 1, "CR 122.1a: one -1/-1 counter off a 0/2"
    assert not druid.tapped, "CR 701.26b: the effect untapped it"


def test_the_devoted_druid_loop_terminates_by_state_based_action():
    """Tap for G, untap by paying a -1/-1 counter, repeat - CR 704.5f kills
    the Druid once its toughness reaches 0, so the loop cannot run forever.
    One cycle is affordable from a starting toughness of 2 (down to 1); the
    second cycle's cost counter brings it to 0 and ends the creature instead.

    `Game.retain_priority` checks state-based actions as soon as the cost is
    paid and the ability is put on the stack (CR 704.3, CR 117.3c) - the same
    "already dead before its own ability resolves" timing
    `test_loyalty_abilities.py`'s Nahiri test relies on - so the Druid is
    gone before `pass_until_resolved` is even needed for the second cycle.
    """
    scenario = _devoted_druid_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid", "alice")

    scenario.activate(druid, index=0)
    scenario.activate(druid, index=1)
    scenario.pass_until_resolved()

    assert druid.counter_count(Counter.MINUS_ONE) == 1, "the counters actually accumulate"
    assert druid.toughness == 1
    assert druid.zone is Zone.BATTLEFIELD

    scenario.activate(druid, index=0)
    scenario.activate(druid, index=1)  # the second -1/-1 counter brings toughness to 0

    assert druid.zone is Zone.GRAVEYARD, "CR 704.5f: 0 toughness is dead, not merely untappable"
    assert druid.last_known_counters[Counter.MINUS_ONE] == 2, "both counters landed before it died"


# --------------------------------------------------------------------------
# The Filigree Sylex
# --------------------------------------------------------------------------


def test_filigree_sylexs_first_ability_adds_an_oil_counter():
    scenario = Scenario().player("alice", battlefield=["The Filigree Sylex"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sylex = scenario.creature("The Filigree Sylex", "alice")

    scenario.activate(sylex, index=0)
    scenario.pass_until_resolved()

    assert sylex.counter_count("oil") == 1
    assert sylex.tapped


def test_filigree_sylexs_second_ability_destroys_by_oil_count():
    """Two oil counters, so it destroys every nonland permanent with mana
    value 2 - Grizzly Bears - and spares a Mountain (nonland restriction) and
    Elvish Mystic (mana value 1)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Filigree Sylex", "Grizzly Bears", "Elvish Mystic", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sylex = scenario.creature("The Filigree Sylex", "alice")
    sylex.add_counters("oil", 2)
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    mountain = scenario.creature("Mountain", "alice")

    scenario.activate(sylex, index=1)
    scenario.pass_until_resolved()

    assert sylex.zone is Zone.GRAVEYARD, "the ability sacrificed it as a cost"
    assert bears.zone is Zone.GRAVEYARD, "mana value 2, matches the oil count"
    assert mystic.zone is Zone.BATTLEFIELD, "mana value 1, does not match"
    assert mountain.zone is Zone.BATTLEFIELD, "a land is never a nonland permanent"


def test_filigree_sylexs_third_ability_refuses_a_distribution_cost():
    """ "Remove ten oil counters from among permanents you control" is a
    distribution `cost_component_for_phrase` explicitly declines (CR 602.5) -
    this must stay a raised refusal, never a silent free activation."""
    scenario = Scenario().player("alice", battlefield=["The Filigree Sylex"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sylex = scenario.creature("The Filigree Sylex", "alice")
    sylex.add_counters("oil", 10)

    with pytest.raises(ValueError, match="cannot build a cost for"):
        scenario.activate(sylex, index=2, targets=["bob"])

    assert sylex.zone is Zone.BATTLEFIELD, "the refused activation spent nothing"
    assert sylex.counter_count("oil") == 10


# --------------------------------------------------------------------------
# The Legend of Roku // Avatar Roku - {8}: Create a 4/4 red Dragon creature
# token with flying and firebending 4.
# --------------------------------------------------------------------------


def test_avatar_rokus_eight_ability_creates_the_dragon_token():
    """Reached through a real `.transform()` and `Game.activate_ability`, not
    an `AbilityOnStack` built by hand: a sibling wave's "Transforming a
    permanent" fix (`docs/engine-coverage.md`) makes `CardState.up_face`
    follow `.transformed` now, so `activated_abilities`/`Game._still_has_
    ability` both read the back face's `{8}` ability once Avatar Roku is
    actually the face that is up (CR 712.8d, 712.8e).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Legend of Roku // Avatar Roku"] + ["Mountain"] * 8,
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    roku = scenario.creature("The Legend of Roku", "alice")  # CardState.name reads the front face
    roku.transform()  # CR 714: this ability is only Avatar Roku's
    sources = scenario.untapped_sources(*(["Mountain"] * 8))

    before = {state.id for state in scenario.game.battlefield}
    scenario.activate(roku, *sources)
    scenario.pass_until_resolved()

    dragons = [state for state in scenario.game.battlefield if state.id not in before]
    assert len(dragons) == 1
    dragon = dragons[0]
    assert dragon.name == "Dragon Token"
    assert dragon.power == 4 and dragon.toughness == 4
    assert "Flying" in dragon.card.keywords
    assert "Firebending 4" in dragon.card.keywords


# --------------------------------------------------------------------------
# Abstergo Entertainment - {3}, {T}, Exile Abstergo Entertainment: Return up
# to one target historic card from your graveyard to your hand, then exile
# all graveyards.
# --------------------------------------------------------------------------


def _abstergo_board(alice_graveyard: list[str], bob_graveyard: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            battlefield=["Abstergo Entertainment", "Forest", "Forest", "Forest"],
            graveyard=alice_graveyard,
        )
        .player("bob", library=["Island"], graveyard=bob_graveyard or [])
    )


def test_abstergo_returns_a_historic_card_and_exiles_every_graveyard():
    """Walking Ballista is historic through CR 700.6's artifact clause."""
    scenario = _abstergo_board(["Walking Ballista"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abstergo = scenario.find("Abstergo Entertainment", Zone.BATTLEFIELD, "alice")
    ballista = scenario.find("Walking Ballista", Zone.GRAVEYARD, "alice")
    alice = scenario.player("alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.activate(abstergo, *sources, index=2, targets=[ballista])
    scenario.pass_until_resolved()

    assert ballista in alice.cards_in(Zone.HAND), "returned before the exile-all-graveyards half"
    assert abstergo.zone is Zone.EXILE, "exiled as its own cost"
    assert scenario.player("bob").cards_in(Zone.GRAVEYARD) == [], (
        "every graveyard, not only alice's"
    )


def test_abstergo_cannot_target_a_non_historic_card():

    scenario = _abstergo_board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abstergo = scenario.find("Abstergo Entertainment", Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    with pytest.raises(ValueError, match="historic"):
        scenario.activate(abstergo, *sources, index=2, targets=[bears])


def test_abstergo_may_choose_zero_targets_without_fizzling():
    """ "Up to one" (CR 115.6) includes zero, and choosing it must not stop
    the second instruction - "exile all graveyards" - from running."""
    scenario = _abstergo_board(["Walking Ballista"], ["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    abstergo = scenario.find("Abstergo Entertainment", Zone.BATTLEFIELD, "alice")
    ballista = scenario.find("Walking Ballista", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")

    scenario.activate(abstergo, *sources, index=2, targets=[])
    scenario.pass_until_resolved()

    assert ballista.zone is Zone.EXILE, "not returned, but still swept by the second clause"
    assert scenario.player("bob").cards_in(Zone.GRAVEYARD) == []


# --------------------------------------------------------------------------
# Agatha's Soul Cauldron - {T}: Exile target card from a graveyard. When a
# creature card is exiled this way, put a +1/+1 counter on target creature
# you control.
# --------------------------------------------------------------------------


CAULDRON = "Agatha's Soul Cauldron"


def test_exiling_a_creature_card_creates_the_reflexive_trigger():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[CAULDRON, "Elvish Mystic"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cauldron = scenario.find(CAULDRON, Zone.BATTLEFIELD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")
    # CR 603.3d: the reflexive ability's target is announced as it goes on the
    # stack, which is *after* the {T} ability has already resolved - so, the
    # same way `test_reflexive_triggered_abilities.py` scripts Grist's own
    # reflexive target, this has to be registered before activating at all.
    scenario.choose_trigger_targets(CAULDRON, [mystic])

    scenario.activate(cauldron, targets=[bears])
    scenario.pass_until_resolved()  # the {T} ability: exiles, creates the reflexive trigger

    assert bears.zone is Zone.EXILE
    assert scenario.stack_names() == [f"{CAULDRON}'s triggered ability"]

    scenario.pass_until_resolved()  # the reflexive ability itself

    assert mystic.counter_count(Counter.PLUS_ONE) == 1


def test_exiling_a_noncreature_card_creates_no_reflexive_trigger():
    scenario = (
        Scenario()
        .player("alice", battlefield=[CAULDRON, "Elvish Mystic"], graveyard=["Mountain"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cauldron = scenario.find(CAULDRON, Zone.BATTLEFIELD, "alice")
    mountain = scenario.find("Mountain", Zone.GRAVEYARD, "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")

    scenario.activate(cauldron, targets=[mountain])
    scenario.pass_until_resolved()

    assert mountain.zone is Zone.EXILE
    assert scenario.game.stack_is_empty, "no creature card was exiled, so no reflexive trigger"
    assert mystic.counter_count(Counter.PLUS_ONE) == 0


# --------------------------------------------------------------------------
# Grist, the Hunger Tide - +1: Create a 1/1 black and green Insect creature
# token, then mill a card. If an Insect card was milled this way, put a
# loyalty counter on Grist and repeat this process.
# --------------------------------------------------------------------------

GRIST = "Grist, the Hunger Tide"


def _insect_tokens(scenario: Scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Insect Token"]


def test_grists_plus_one_stops_after_a_non_insect_mill():
    scenario = (
        Scenario()
        .player("alice", battlefield=[GRIST], library=["Grizzly Bears", "Mountain"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.activate(grist, index=0)
    scenario.pass_until_resolved()

    assert len(_insect_tokens(scenario)) == 1
    assert [state.name for state in alice.cards_in(Zone.GRAVEYARD)] == ["Grizzly Bears"]
    assert grist.loyalty == 4, "CR 606.4's +1 cost, no repeat bonus"


def test_grists_plus_one_repeats_when_an_insect_is_milled_then_terminates():
    """One Insect (Icetill Explorer), then an empty library - the loop makes
    a second token on the strength of the repeat, then stops on its own once
    there is nothing left to mill (CR 701.17a), never spinning forever."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[GRIST], library=["Icetill Explorer"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    grist = scenario.find(GRIST, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.activate(grist, index=0)
    scenario.pass_until_resolved()

    assert len(_insect_tokens(scenario)) == 2, "one for the first pass, one for the repeat"
    assert [state.name for state in alice.cards_in(Zone.GRAVEYARD)] == ["Icetill Explorer"]
    assert grist.loyalty == 5, "3 printed + 1 activation cost + 1 for the Insect milled"
    assert alice.library == [], "the empty library is what stopped the loop, not a guard rail"


# --------------------------------------------------------------------------
# Tyvar, Jubilant Brawler - -2: Mill three cards, then you may return a
# creature card with mana value 2 or less from your graveyard to the
# battlefield.
# --------------------------------------------------------------------------

TYVAR = "Tyvar, Jubilant Brawler"


def test_tyvars_minus_two_mills_then_returns_an_eligible_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=[TYVAR], library=["Grizzly Bears", "Mountain", "Mountain"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tyvar = scenario.find(TYVAR, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.activate(tyvar, index=1)
    scenario.pass_until_resolved()

    assert len(alice.cards_in(Zone.GRAVEYARD)) == 2, "the two Mountains stayed; Bears came back"
    assert any(state.name == "Grizzly Bears" for state in scenario.game.battlefield)
    assert tyvar.loyalty == 1, "CR 606.4: printed 3, minus the -2 cost"


def test_tyvars_minus_two_declines_with_no_eligible_creature():
    """Every milled card is too expensive (Hill Giant, mana value 4) or not
    a creature at all - nothing to return, and nothing crashes over it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[TYVAR], library=["Hill Giant", "Mountain", "Mountain"])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tyvar = scenario.find(TYVAR, Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")

    scenario.activate(tyvar, index=1)
    scenario.pass_until_resolved()

    assert len(alice.cards_in(Zone.GRAVEYARD)) == 3, "all three stayed milled"
    assert not any(state.name == "Hill Giant" for state in scenario.game.battlefield)


def test_tyvars_minus_two_may_return_a_creature_already_in_the_graveyard():
    """CR 400.2: the graveyard is read as it stands after the mill, with no
    "just arrived" exception - a creature already there before this
    resolution is just as eligible as one this mill just put there."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[TYVAR],
            library=["Mountain", "Mountain", "Mountain"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tyvar = scenario.find(TYVAR, Zone.BATTLEFIELD, "alice")

    scenario.activate(tyvar, index=1)
    scenario.pass_until_resolved()

    assert any(state.name == "Grizzly Bears" for state in scenario.game.battlefield)


# --------------------------------------------------------------------------
# Fiend Artisan - {X}{B/G}, {T}, Sacrifice another creature: Search your
# library for a creature card with mana value X or less, put it onto the
# battlefield, then shuffle. Activate only as a sorcery.
# --------------------------------------------------------------------------


def test_fiend_artisan_finds_a_creature_at_exactly_x():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fiend Artisan", "Elvish Mystic"] + ["Forest"] * 4,
            library=["Hill Giant", "Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    artisan = scenario.find("Fiend Artisan", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Elvish Mystic", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    ability = scenario.activate(artisan, *sources, x_value=2, sacrificing=[fodder])
    assert isinstance(ability, AbilityOnStack)
    assert ability.x_value == 2
    assert fodder.zone is Zone.GRAVEYARD, "the sacrifice is paid on activation"

    scenario.pass_until_resolved()

    assert any(state.name == "Grizzly Bears" for state in scenario.game.battlefield), (
        "mana value 2, matches X"
    )
    assert not any(state.name == "Hill Giant" for state in scenario.game.battlefield), (
        "mana value 4, above X"
    )


def test_fiend_artisan_at_x_zero_finds_nothing_above_zero():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fiend Artisan", "Elvish Mystic"] + ["Forest"] * 4,
            library=["Grizzly Bears"],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    artisan = scenario.find("Fiend Artisan", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Elvish Mystic", "alice")
    sources = scenario.untapped_sources("Forest")

    scenario.activate(artisan, *sources, x_value=0, sacrificing=[fodder])
    scenario.pass_until_resolved()

    assert not any(state.name == "Grizzly Bears" for state in scenario.game.battlefield)

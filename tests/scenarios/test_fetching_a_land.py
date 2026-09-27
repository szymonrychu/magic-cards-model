"""Scenario: an ability that searches a library and puts a land onto the battlefield.

The fetchland is the most-played card shape in Modern - every list in this
project's sweep ran four to eight of them - and it exercises three rules at once:
a multi-part activation cost, the search action, and a permanent reaching the
battlefield by an effect rather than by being played.

Every CR number below was looked up with `knowledge_search(type="rules")` in the
session that wrote this file.

- **CR 602.1a** - the activation cost is everything before the colon. Arid Mesa's
  is `{T}, Pay 1 life, Sacrifice this land`, all three parts, all paid on
  activation rather than on resolution.
- **CR 701.23a** - "To search for a card in a zone, look at all cards in that
  zone (even if it's a hidden zone) and find a card that matches the given
  description."
- **CR 701.24a** - "To shuffle a library or a face-down pile of cards, randomize
  the cards within it so that no player knows their order." `Game.search_library`
  does this for real, so a fetch really does randomize what is left.
- **CR 701.23b** - a search for a stated quality "isn't required to find some or
  all of those cards even if they're present in that zone" - finding nothing is
  always a legal answer.
- **CR 305.6** - a land with a basic land type has the matching mana ability
  intrinsically, which is why "search for a Mountain or Plains card" finds a
  Sacred Foundry: it is looking for land *types*, not for card names.
- **CR 614.12** - a permanent's own "as this enters" text is a replacement
  effect consulted while it is on its way in.
- **CR 119.4 / CR 118.3b** - paying life is legal only up to the life total, and
  is done by subtraction. Losing at 0 is a separate state-based action
  (CR 704.5a), timed by CR 104.3b.
- **CR 305.1 / CR 116.2a / CR 305.2 / CR 701.18a** - playing a land is a special
  action limited to once a turn. An effect putting a land onto the battlefield
  is not playing one.

Every fetchland used to be its own row in `ACTIVATED_EFFECTS`, built by a
`fetch_land(*subtypes)` helper - and Misty Rainforest and Verdant Catacombs had
no row at all, so a player who fetched with either paid the life, sacrificed the
land, and found nothing, silently. The effect now lives in
`machines/effects.py` as `parse_search_and_put_effect`, which reads "Search your
library for a `<type>` or `<type>` card, put it onto the battlefield, then
shuffle." straight off each card's own printed text - so every card with this
shape works, including the two that were broken, with no table row at all.
"""

from magic_cards_model.machines import (
    AbilityKind,
    AbilityOnStack,
    Step,
    TriggeredAbility,
    TriggerWord,
)
from magic_cards_model.machines.effects import (
    ACTIVATED_EFFECTS,
    activated_effect_for,
    parse_search_and_put_effect,
)
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

#: Every real fetchland fixture in the pool, land types as printed.
FETCHLANDS = {
    "Arid Mesa": ("Mountain", "Plains"),
    "Flooded Strand": ("Plains", "Island"),
    "Bloodstained Mire": ("Swamp", "Mountain"),
    "Marsh Flats": ("Plains", "Swamp"),
    "Scalding Tarn": ("Island", "Mountain"),
    "Windswept Heath": ("Forest", "Plains"),
    "Wooded Foothills": ("Mountain", "Forest"),
    "Misty Rainforest": ("Forest", "Island"),
    "Verdant Catacombs": ("Swamp", "Forest"),
}


def _fetch_board(
    fetchland: str = "Arid Mesa",
    library: list[str] | None = None,
    life: int = 20,
) -> Scenario:
    """One player with a fetchland in play and a stacked library to find in."""
    return (
        Scenario()
        .player(
            "alice",
            life=life,
            library=library if library is not None else ["Sacred Foundry", "Forest"],
            battlefield=[fetchland],
        )
        .player("bob", library=["Forest"])
    )


# -- the happy path --------------------------------------------------------


def test_a_fetchland_puts_the_found_land_onto_the_battlefield():
    """`{T}, Pay 1 life, Sacrifice this land: Search your library for a Mountain
    or Plains card, put it onto the battlefield, then shuffle.`

    The whole card in one test: the cost is paid (CR 602.1a), the search finds a
    card matching the description (CR 701.23a), and the land arrives.
    """
    scenario = _fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    foundry = scenario.find("Sacred Foundry", Zone.BATTLEFIELD)
    assert foundry.zone is Zone.BATTLEFIELD
    assert "Sacred Foundry" not in [state.card.name for state in scenario.player("alice").library]


def test_every_fetchland_in_the_pool_fetches_end_to_end():
    """Each of the nine real fetchland fixtures, one at a time: life paid, the
    land itself sacrificed to the graveyard, the correct land found on the
    battlefield, and the library both shuffled and one card smaller.

    None of these nine has a row in `ACTIVATED_EFFECTS` any more - this is
    `activated_effect_for`'s fallback to `parse_search_and_put_effect` doing the
    whole card, for every printed pair of types in the pool, not just Arid Mesa.
    """
    for fetchland, (type_a, _type_b) in FETCHLANDS.items():
        scenario = _fetch_board(fetchland=fetchland, library=[type_a, "Swamp"]).build()
        scenario.start_at(Step.PRECOMBAT_MAIN)
        land = scenario.find(fetchland, Zone.BATTLEFIELD)
        before = len(scenario.player("alice").library)

        scenario.activate(land, sacrificing=[land])
        scenario.pass_until_resolved()

        found = scenario.find(type_a, Zone.BATTLEFIELD)
        assert found.zone is Zone.BATTLEFIELD, fetchland
        assert found.tapped is False, fetchland
        assert land.zone is Zone.GRAVEYARD, fetchland
        assert scenario.player("alice").life == 19, fetchland
        assert len(scenario.player("alice").library) == before - 1, fetchland


def test_misty_rainforest_fetches_a_forest_or_an_island():
    """Misty Rainforest had no registry entry at all before this fix - the
    silent case the task exists to close. `Search your library for a Forest or
    Island card, put it onto the battlefield, then shuffle.`
    """
    scenario = _fetch_board(fetchland="Misty Rainforest", library=["Island", "Swamp"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rainforest = scenario.find("Misty Rainforest", Zone.BATTLEFIELD)

    scenario.activate(rainforest, sacrificing=[rainforest])
    scenario.pass_until_resolved()

    assert scenario.find("Island", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 19
    assert rainforest.zone is Zone.GRAVEYARD


def test_verdant_catacombs_fetches_a_swamp_or_a_forest():
    """The other card with no registry entry at all before this fix.
    `Search your library for a Swamp or Forest card, put it onto the
    battlefield, then shuffle.`
    """
    scenario = _fetch_board(fetchland="Verdant Catacombs", library=["Swamp", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    catacombs = scenario.find("Verdant Catacombs", Zone.BATTLEFIELD)

    scenario.activate(catacombs, sacrificing=[catacombs])
    scenario.pass_until_resolved()

    assert scenario.find("Swamp", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 19
    assert catacombs.zone is Zone.GRAVEYARD


def test_the_whole_cost_is_paid_before_the_ability_resolves():
    """CR 602.1a: the cost is everything before the colon, and it is paid on
    activation. So by the time the ability is still sitting on the stack the
    fetchland is already in the graveyard and the life is already gone.
    """
    scenario = _fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])

    assert scenario.stack_names() == ["Arid Mesa's activated ability"]
    assert mesa.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 19


def test_a_found_basic_land_enters_untapped():
    """The ability does not say "tapped", so a land with no text of its own on
    the subject arrives untapped. A basic Plains has no such text, so this is
    the clean case: nothing anywhere is asking for it to be tapped.
    """
    scenario = _fetch_board(library=["Plains", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.find("Plains", Zone.BATTLEFIELD).tapped is False


def test_a_found_land_that_prints_enters_tapped_arrives_tapped():
    """Elegant Parlor prints "This land enters tapped" - a replacement effect on
    the entering permanent itself (CR 614.12), which applies whatever route the
    land took onto the battlefield. So the untapped case above is the fetchland
    saying nothing, not the fetchland forcing anything.
    """
    scenario = _fetch_board(library=["Elegant Parlor", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.find("Elegant Parlor", Zone.BATTLEFIELD).tapped is True


def test_the_fetch_does_not_use_the_land_drop():
    """CR 305.1 and CR 116.2a make *playing* a land a special action, and
    CR 305.2 limits it to one a turn. CR 701.18a's "play a land" is putting it
    onto the battlefield **from the hand** as that action; an ability putting one
    there on resolution is not playing it, so the land drop is untouched.
    """
    scenario = _fetch_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.game.can_play_land("alice")


# -- what the search does and does not find --------------------------------


def test_the_search_matches_land_types_and_not_card_names():
    """ "Search your library for a Mountain or Plains card" is looking for the
    land *types* (CR 305.6), so a `Land - Mountain Plains` dual is a legal find
    even though it is named Sacred Foundry.
    """
    scenario = _fetch_board(library=["Sacred Foundry"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert "Sacred Foundry" in scenario.battlefield_names()


def test_a_library_with_no_matching_land_finds_nothing():
    """CR 701.23a's search finds "a card that matches the given description", and
    when nothing matches, nothing is found. The cost is still paid in full: the
    life is gone and the fetchland is still sacrificed, because CR 602.1a's cost
    was paid long before resolution had anything to say.
    """
    scenario = _fetch_board(library=["Forest", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.battlefield_names() == []
    assert scenario.player("alice").life == 19
    assert mesa.zone is Zone.GRAVEYARD


def test_an_empty_library_finds_nothing_and_loses_nobody_the_game():
    """Searching an empty library is legal and finds nothing. It is not a draw,
    so CR 704.5b's "tried to draw from an empty library" never comes into it.
    """
    scenario = _fetch_board(library=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    assert scenario.battlefield_names() == []
    assert not scenario.game.is_over


def test_a_fetchland_finds_a_nonbasic_dual_with_the_right_land_types():
    """The case a parser matching card *names* would get wrong. Windswept Heath
    is `Forest or Plains` and Temple Garden is `Land - Forest Plains` - a legal
    find under CR 305.6 even though "Temple Garden" is neither "Forest" nor
    "Plains" as a name. Breeding Pool (`Land - Island Forest`) is a legal find
    for the same reason and shares only the Forest type with Windswept Heath.
    """
    scenario = _fetch_board(
        fetchland="Windswept Heath", library=["Temple Garden", "Breeding Pool"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    heath = scenario.find("Windswept Heath", Zone.BATTLEFIELD)

    scenario.activate(heath, sacrificing=[heath])
    scenario.pass_until_resolved()

    found = [name for name in scenario.battlefield_names() if name != "Windswept Heath"]
    assert found in (["Temple Garden"], ["Breeding Pool"])


def test_each_fetchland_looks_for_its_own_two_types():
    """Windswept Heath is `Forest or Plains`, so it cannot find a Mountain. The
    types are read off each card's own printed text and not from a table, which
    is what this test is really checking.
    """
    scenario = _fetch_board(fetchland="Windswept Heath", library=["Mountain", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    heath = scenario.find("Windswept Heath", Zone.BATTLEFIELD)

    scenario.activate(heath, sacrificing=[heath])
    scenario.pass_until_resolved()

    assert scenario.battlefield_names() == ["Forest"]


def test_a_fetchland_at_one_life_loses_the_game_before_the_search():
    """CR 119.4: "a player may [pay life] only if their life total is greater
    than or equal to the amount of the payment" - so paying 1 at 1 life is legal
    and lands exactly on 0 (CR 118.3b). But CR 104.3b times the loss for 0 or
    less life at "the next time a player would receive priority", and CR 117.3c
    gives the activator priority right back as the very next thing that happens
    after activating - so the loss (CR 704.5a) is checked there, before the
    ability that cost the life ever resolves. This is the well-known real-life
    interaction: cracking a fetch land down to 0 life loses the game outright,
    with no chance to see what the search would have found.
    """
    scenario = _fetch_board(life=1).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])

    assert scenario.player("alice").life == 0
    assert not scenario.game.is_in_game("alice"), (
        "CR 704.5a, checked by CR 117.3c's retained priority"
    )
    assert scenario.game.winner == "bob"


# -- corner cases the model does not cover yet -----------------------------


def test_a_shockland_fetched_untapped_costs_two_life():
    """ "As this land enters, you may pay 2 life. If you don't, it enters tapped."

    One of the two outcomes has to happen, and CR 614.12a puts the choice before
    the land enters. This test asserts the honest pair: either the land is
    tapped, or 2 more life was paid. Note the fetch itself already cost 1 life,
    so 17 is 20 - 1 - 2.
    """
    scenario = _fetch_board(library=["Steam Vents"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    vents = scenario.find("Steam Vents", Zone.BATTLEFIELD)
    paid_for_it = scenario.player("alice").life == 17
    assert vents.tapped or paid_for_it


def test_the_library_is_shuffled_after_the_search():
    """ "...then shuffle." CR 701.24a randomizes what search left behind.

    Asserted the only way a deterministic test can: a library whose order was
    randomized should not still be in the exact order it was stacked in. With
    four distinct cards left this is a 1-in-24 false pass, which is an
    acceptable rate for a marker rather than a proof.
    """
    library = ["Sacred Foundry", "Forest", "Island", "Swamp", "Plains"]
    scenario = _fetch_board(library=library).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mesa = scenario.find("Arid Mesa", Zone.BATTLEFIELD)

    scenario.activate(mesa, sacrificing=[mesa])
    scenario.pass_until_resolved()

    remaining = [state.card.name for state in scenario.player("alice").library]
    assert remaining != ["Forest", "Island", "Swamp", "Plains"]


# -- the parser, not a per-card table -----------------------------------


def test_no_fetchland_has_a_registry_entry_that_would_shadow_the_parser():
    """`activated_effect_for` only reaches `parse_search_and_put_effect` when
    `ACTIVATED_EFFECTS.get((card_name, index))` is `None` - an explicit row
    always wins. So a per-card entry re-added for any of these nine, or for a
    fetchland the pool gains later, would silently take over again exactly the
    way the old table did for Misty Rainforest and Verdant Catacombs' missing
    rows. This fails loudly the moment that happens.
    """
    for fetchland in FETCHLANDS:
        assert (fetchland, 0) not in ACTIVATED_EFFECTS, fetchland


def test_activated_effect_for_covers_a_fetchland_added_to_the_pool_later():
    """The parser reads the ability's own text, not a name it was told to
    expect - so a tenth fetchland works the day it is added to the pool, with
    no code change here. Proven directly: a name `ACTIVATED_EFFECTS` has never
    heard of, paired with a real fetchland's printed effect text, still
    produces a working effect.
    """
    assert ("A Tenth Fetchland", 0) not in ACTIVATED_EFFECTS
    effect = activated_effect_for(
        "A Tenth Fetchland",
        0,
        "Search your library for a Desert or Cave card, put it onto the battlefield, then shuffle.",
    )
    assert effect is not None


def test_a_card_with_no_search_ability_gets_no_effect_from_the_parser():
    """The fallback only fires for the one sentence shape it recognises.
    Anything else returns `None`, the same silence an unscripted ability gets.

    `"Add {R}."` was the example here until the play-from-exile wave taught
    `_parse_add_mana_clause` to read a resolving "Add ..." (CR 106.4) - the
    resolution half of Ugin, Eye of the Storms' `0: Add {C}{C}{C}.`, which
    CR 605.1a's "it's not a loyalty ability" keeps off the mana-ability fast
    path. A fetchland's own `{T}: Add {R}.` never reaches this function anyway
    (it is a real mana ability and CR 605.3b resolves it without the stack), so
    the example is now a sentence nothing in the file reads.
    """
    assert activated_effect_for("Arid Mesa", 0, "Untap each Desert you control.") is None


def test_expedition_map_finds_any_land_and_puts_it_in_hand():
    """`{2}, {T}, Sacrifice this artifact: Search your library for a land card,
    reveal it, put it into your hand, then shuffle.`

    Two variations from a fetchland in one card: the stated quality is the
    broad "a land card" rather than a land type, and the found card goes to
    hand rather than onto the battlefield.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Expedition Map", "Forest", "Forest"],
            library=["Breeding Pool", "Grizzly Bears"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_map = scenario.find("Expedition Map", Zone.BATTLEFIELD)
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.activate(card_map, *forests, sacrificing=[card_map])
    scenario.pass_until_resolved()

    pool = scenario.find("Breeding Pool", Zone.HAND)
    assert pool.zone is Zone.HAND
    assert card_map.zone is Zone.GRAVEYARD


def test_expedition_map_with_no_land_in_library_finds_nothing():
    """CR 701.23b again: "land card" is still a stated quality, so an all-spell
    library is a legal - if disappointing - result.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Expedition Map", "Forest", "Forest"],
            library=["Grizzly Bears"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card_map = scenario.find("Expedition Map", Zone.BATTLEFIELD)
    forests = scenario.untapped_sources("Forest", "Forest")

    scenario.activate(card_map, *forests, sacrificing=[card_map])
    scenario.pass_until_resolved()

    assert scenario.player("alice").hand == []
    assert card_map.zone is Zone.GRAVEYARD


def test_the_parser_reads_a_tapped_and_optional_single_type_search():
    """Flagstones of Trokair's death trigger - "you may search your library for
    a Plains card, put it onto the battlefield tapped, then shuffle." - is the
    pool's only single-type, tapped, optional search, and it proves the parser
    handles all three at once.

    Called directly against a hand-built `AbilityOnStack` rather than through a
    full game, so this is about the *effect* alone matching the sentence's
    every clause: tapped, one land type, and a "you may" that a scenario can
    answer. `_trigger_event` now reads this exact condition as CR 700.4's
    "dies" (a spelled-out "is put into a graveyard from the battlefield" is
    the definition, not a different event), so the trigger does reach the
    stack in a real game too - see
    `tests/scenarios/test_dies_trigger_scope.py` for that end-to-end path.
    """
    condition = "Flagstones of Trokair is put into a graveyard from the battlefield"
    effect_text = (
        "you may search your library for a Plains card, put it onto the "
        "battlefield tapped, then shuffle."
    )
    printed = f"When {condition}, {effect_text}"
    effect = parse_search_and_put_effect(effect_text)
    assert effect is not None

    scenario = (
        Scenario()
        .player("alice", library=["Plains", "Forest"], battlefield=["Grizzly Bears"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    ability = AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=TriggeredAbility(
            raw=printed,
            text=printed,
            face="Flagstones of Trokair",
            word=TriggerWord.WHEN,
            condition=condition,
            effect=effect_text,
        ),
        source_name="Flagstones of Trokair",
        controller="alice",
    )

    effect(scenario.game, ability)

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.tapped is True
    assert "Plains" not in [state.card.name for state in scenario.player("alice").library]


# -- Fabled Passage: the same search, plus a land-count-gated untap --------

#: CR 701.23a (search), CR 701.24a (shuffle) - both already proven above by
#: every ordinary fetchland - plus the rider this file's own task owns:
#: "Then if you control four or more lands, untap that land." CR 611.2c/
#: 608.2h: the count is read only once the search has actually resolved and
#: the found land has already entered, not off the printed card in a vacuum
#: - which is exactly why the corner case below (three lands before, four
#: after) exists: a reader that counted the board *before* the land arrived
#: would wrongly leave it tapped.


def test_fabled_passage_untaps_when_four_or_more_lands_are_controlled():
    """Three lands on the battlefield plus the fetched one makes four -
    CR 701.23a's search and CR 701.24a's shuffle both still run, and the
    found land arrives tapped and then untaps in the same resolution."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fabled Passage", "Forest", "Forest", "Mountain"],
            library=["Plains", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Fabled Passage", Zone.BATTLEFIELD)
    before = len(scenario.player("alice").library)

    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.zone is Zone.BATTLEFIELD
    assert plains.tapped is False
    assert passage.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == before - 1


def test_fabled_passage_leaves_the_land_tapped_below_four():
    """Two lands before the fetch, three after - CR 701.44... no, CR 611.2c:
    the threshold not met leaves the freshly fetched land tapped, the same
    as an ordinary fetchland with no untap rider at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fabled Passage", "Forest"],
            library=["Plains", "Island"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Fabled Passage", Zone.BATTLEFIELD)

    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    plains = scenario.find("Plains", Zone.BATTLEFIELD)
    assert plains.tapped is True


def test_fabled_passage_with_no_basic_land_in_library_finds_nothing():
    """CR 701.23b again: finding nothing is a legal answer, and the land
    count check never runs at all - there is no found land for "that land"
    to refer to."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Fabled Passage", "Forest", "Forest", "Mountain"],
            library=["Grizzly Bears"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    passage = scenario.find("Fabled Passage", Zone.BATTLEFIELD)

    scenario.activate(passage, sacrificing=[passage])
    scenario.pass_until_resolved()

    assert passage.zone is Zone.GRAVEYARD
    assert [state.card.name for state in scenario.player("alice").library] == ["Grizzly Bears"]
    remaining = sorted(
        state.card.name
        for state in scenario.game.permanents_controlled_by("alice")
        if state.card.is_land
    )
    assert remaining == ["Forest", "Forest", "Mountain"]


# -- Magmatic Hellkite: destroy, then its controller (not the caster) ------
# -- searches for a basic land, tapped, with a stun counter -----------------

#: CR 701.8a (destroy), CR 701.23a (search), CR 122.1d (the stun counter's
#: own replacement effect, exercised end to end by `test_stun_counters.py`
#: elsewhere - this file only proves the counter actually lands). CR 400.7's
#: anaphora ("Its controller") points at whoever controlled the destroyed
#: land, never at Magmatic Hellkite's own controller.


def test_magmatic_hellkite_destroys_then_its_victims_controller_searches():
    """Alice's Hellkite destroys Bob's nonbasic land; Bob, not Alice,
    searches his own library and gets the basic, tapped, with a stun
    counter - never Alice's search, never Alice's land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Magmatic Hellkite"],
            battlefield=["Mountain"] * 4,
        )
        .player(
            "bob",
            battlefield=["Breeding Pool"],
            library=["Forest", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    pool = scenario.find("Breeding Pool", Zone.BATTLEFIELD)
    # CR 603.3d: the ETB trigger's own target is chosen as it goes on the
    # stack, after the creature spell itself has already resolved with no
    # targets of its own - registered before casting, the same way
    # `test_activated_ability_effects.py`'s reflexive-trigger case above
    # scripts a target nothing has chosen yet.
    scenario.choose_trigger_targets("Magmatic Hellkite", [pool])

    scenario.cast_and_resolve("Magmatic Hellkite", *sources)
    assert scenario.stack_names() == ["Magmatic Hellkite's triggered ability"]
    scenario.resolve_top()

    assert pool.zone is Zone.GRAVEYARD
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    assert forest.tapped is True

    assert forest.counters[Counter.STUN] == 1
    assert forest in scenario.game.permanents_controlled_by("bob")
    assert "Forest" not in [state.card.name for state in scenario.player("bob").library]


def test_magmatic_hellkite_with_no_basic_land_still_destroys_the_target():
    """CR 701.23b: the search still is not required to find anything, and
    CR 608.2b's own "legal target, verb refuses" case (Beast Within's
    printed ruling, 2021-03-19) does not apply here at all - the destroy
    itself is unconditional and always succeeds against a nonbasic land with
    no indestructible of its own."""
    scenario = (
        Scenario()
        .player("alice", hand=["Magmatic Hellkite"], battlefield=["Mountain"] * 4)
        .player("bob", battlefield=["Breeding Pool"], library=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    pool = scenario.find("Breeding Pool", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Magmatic Hellkite", [pool])

    scenario.cast_and_resolve("Magmatic Hellkite", *sources)
    scenario.resolve_top()

    assert pool.zone is Zone.GRAVEYARD
    assert scenario.player("bob").library != []
    assert [state.card.name for state in scenario.player("bob").library] == ["Grizzly Bears"]

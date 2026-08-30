"""Scenario: effects that move or exile cards in a graveyard as a *zone*,
rather than a single targeted card the way `test_exile.py`'s Bone Splinters
does.

Six shapes, all read off the card's own printed text with no per-card row in
`machines/effects.py`'s registries:

- **"exile target player's graveyard"** (Bojuka Bog, Tormod's Crypt) - the
  *target* is the player (CR 115.1), not a card; `exile_target_players_
  graveyard` is the clause `_parse_targeted_clause` routes this to, ahead of
  the generic `_EXILE_TARGET_RE`, which would otherwise commit first, read
  `allow_player_targets=False`, and refuse the whole clause.
- **"exile all graveyards"** (Rest in Peace) - no target at all.
- **"exile all cards that are `<quality>` from all graveyards"** (Sanctifier
  en-Vec) - the filtered twin, reusing `_hand_exile_quality_matcher`'s
  colour/type reading.
- **"return target `<quality>` card from your graveyard to your hand"**
  (Eternal Witness, Raise Dead) - a new regex alongside the existing
  `_RETURN_TARGET_RE`, needed only because these two say "to your hand"
  rather than "to its owner's hand".
- **"up to one target player puts all the cards from their graveyard on the
  bottom of their library in a random order"** (Endurance) - CR 115.6's "up
  to one", and a randomisation seeded off `Game.shuffle_seed` rather than an
  unseeded shuffle, so a scenario asserting on library order stays
  deterministic.

Every CR number here was looked up with `knowledge_search(q="...", type="rules")`
in the session that wrote this file:

- **CR 115.1** - "The targets are object(s) and/or player(s) the spell or
  ability will affect" - confirms a player is a legal kind of target on its
  own, separate from any card.
- **CR 115.6** - "A spell or ability that requires targets may allow zero
  targets to be chosen ... that spell or ability is targeted only if one or
  more targets are chosen for it" - Endurance's "up to one" declining to zero.
- **CR 404.1** - "A player's graveyard is their discard pile" - the zone this
  whole file is about.
- **CR 406.2 / CR 701.13a** - "To exile an object, move it to the exile zone
  from wherever it's currently in" - a graveyard is as reachable as a
  permanent.
- **CR 608.2b** - "Other changes to the game state may cause a target to no
  longer be legal" - and, by the same rule, a player who is *still* in the
  game with an *empty* graveyard remains perfectly legal; nothing about the
  target's zone contents bears on the target's own legality.
- **CR 113.7a** - "Once activated or triggered, an ability exists on the
  stack independently of its source. Destruction or removal of the source
  after that time won't affect the ability" - Eternal Witness's own dies
  trigger, if any, is irrelevant; what this file checks is that Eternal
  Witness's *own* ETB ability still returns its target even once the
  creature that generated it has since died and is itself sitting in a
  graveyard by the time the ability resolves.

Card data is the real Scryfall printing in `tests/fixtures/cards/` for every
name below; none of it is hand-written.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

# --------------------------------------------------------------------------
# "Exile target player's graveyard" (Bojuka Bog)
# --------------------------------------------------------------------------


def test_bojuka_bog_exiles_the_targeted_players_whole_graveyard():
    """The happy path: every card in the targeted opponent's graveyard is
    exiled, and nothing of the caster's own is touched.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Bojuka Bog"])
        .player("bob", graveyard=["Grizzly Bears", "Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    scenario.choose_trigger_targets("Bojuka Bog", ["bob"])
    scenario.play_land("Bojuka Bog", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert bolt.zone is Zone.EXILE
    assert scenario.player("bob").graveyard == []


def test_bojuka_bog_can_target_its_own_controllers_graveyard():
    """Nothing about "target player" excludes the caster - CR 115.1 draws no
    such line, and Bojuka Bog is a perfectly legal way to exile your own
    graveyard (against a Snapcaster Mage, say).
    """
    scenario = Scenario().player("alice", hand=["Bojuka Bog"], graveyard=["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Bojuka Bog", ["alice"])
    scenario.play_land("Bojuka Bog", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bears.zone is Zone.EXILE


def test_targeting_a_player_with_an_empty_graveyard_is_legal_and_does_nothing():
    """CR 608.2b's legality check is about the *player*, not their zones: an
    empty graveyard is exactly as legal a target as a full one. The trigger
    resolves cleanly with nothing to exile.
    """
    scenario = Scenario().player("alice", hand=["Bojuka Bog"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Bojuka Bog", ["bob"])
    scenario.play_land("Bojuka Bog", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("bob").graveyard == []
    assert scenario.game.exile == []


# --------------------------------------------------------------------------
# "Exile all graveyards" (Rest in Peace) and its filtered twin
# (Sanctifier en-Vec)
# --------------------------------------------------------------------------


def test_rest_in_peace_exiles_every_players_graveyard_including_its_own_controllers():
    """No target at all: both players' graveyards empty into exile,
    including the caster's own.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Rest in Peace"],
            graveyard=["Lightning Bolt"],
            battlefield=["Plains", "Plains"],
        )
        .player("bob", graveyard=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Rest in Peace", *scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE
    assert bears.zone is Zone.EXILE
    assert scenario.player("alice").graveyard == []
    assert scenario.player("bob").graveyard == []


def test_sanctifier_en_vec_exiles_only_black_or_red_cards_from_every_graveyard():
    """The filtered shape: white and green cards stay put, black and red
    cards leave, on both sides of the board.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sanctifier en-Vec"],
            graveyard=["Lightning Bolt", "Swords to Plowshares"],
            battlefield=["Plains", "Plains"],
        )
        .player("bob", graveyard=["Thoughtseize", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    swords = scenario.find("Swords to Plowshares", Zone.GRAVEYARD, "alice")
    thoughtseize = scenario.find("Thoughtseize", Zone.GRAVEYARD, "bob")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Sanctifier en-Vec", *scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE, "red leaves"
    assert thoughtseize.zone is Zone.EXILE, "black leaves"
    assert swords.zone is Zone.GRAVEYARD, "white stays"
    assert bears.zone is Zone.GRAVEYARD, "green stays"


# --------------------------------------------------------------------------
# "Return target ... card from your graveyard to your hand"
# (Eternal Witness, Raise Dead)
# --------------------------------------------------------------------------


def test_eternal_witness_returns_the_chosen_card_from_its_controllers_graveyard():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eternal Witness"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Eternal Witness", [bears])
    scenario.will_take_the_may(True, source="Eternal Witness")
    scenario.cast_and_resolve(
        "Eternal Witness", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND


def test_declining_eternal_witnesss_you_may_leaves_the_card_in_the_graveyard():
    """CR 608.2d: declining is always a legal answer to a plain "you may"."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eternal Witness"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Eternal Witness", [bears])
    scenario.will_take_the_may(False, source="Eternal Witness")
    scenario.cast_and_resolve(
        "Eternal Witness", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD


def test_eternal_witnesss_ability_still_returns_its_target_after_its_own_source_dies():
    """CR 113.7a: "Once activated or triggered, an ability exists on the
    stack independently of its source. Destruction or removal of the source
    after that time won't affect the ability." Eternal Witness's own ETB
    ability is put on the stack, targeting a card already in the graveyard;
    the creature is then destroyed *while its own trigger is still on the
    stack*, so by the time the ability resolves, the permanent that produced
    it is itself sitting in a graveyard. The return still happens.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Eternal Witness"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.choose_trigger_targets("Eternal Witness", [bears])
    scenario.will_take_the_may(True, source="Eternal Witness")
    witness = scenario.cast_and_resolve(
        "Eternal Witness", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.game.put_triggers_on_stack()
    scenario.game.destroy(witness)
    scenario.resolve_top()

    assert witness.zone is Zone.GRAVEYARD, "the source itself died first"
    assert bears.zone is Zone.HAND, "its already-independent ability still ran"


def test_raise_dead_returns_a_creature_card_from_graveyard_to_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Raise Dead"], graveyard=["Grizzly Bears"], battlefield=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    scenario.cast_and_resolve("Raise Dead", *scenario.untapped_sources("Swamp"), targets=[bears])

    assert bears.zone is Zone.HAND


# --------------------------------------------------------------------------
# "Up to one target player puts all the cards from their graveyard on the
# bottom of their library in a random order" (Endurance)
# --------------------------------------------------------------------------


def test_endurance_puts_the_targeted_players_graveyard_on_the_bottom_of_the_library():
    """The whole graveyard moves to the bottom, in some order, without
    disturbing what was already on top of the library.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endurance"],
            graveyard=["Grizzly Bears", "Lightning Bolt"],
            library=["Swords to Plowshares"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Endurance", ["alice"])
    scenario.cast_and_resolve("Endurance", *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert alice.graveyard == []
    assert alice.library[0].name == "Swords to Plowshares", "the old top card is undisturbed"
    assert {state.name for state in alice.library[1:]} == {"Grizzly Bears", "Lightning Bolt"}


def test_endurance_up_to_one_target_choosing_zero_leaves_every_graveyard_alone():
    """CR 115.6: "up to one" may legally choose none at all, and an
    unscripted `CHOOSE_TARGETS` question defaults to exactly that (see
    `machines/decisions.py`) - no `choose_trigger_targets` call here."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endurance"],
            graveyard=["Grizzly Bears"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve("Endurance", *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert [state.name for state in alice.graveyard] == ["Grizzly Bears"]


def test_endurance_targeting_an_empty_graveyard_touches_nothing():
    """An empty graveyard is a legal target (CR 608.2b) with nothing to move;
    the library is left exactly as it was.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Endurance"],
            library=["Swords to Plowshares"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.choose_trigger_targets("Endurance", ["alice"])
    scenario.cast_and_resolve("Endurance", *scenario.untapped_sources("Forest", "Forest", "Forest"))
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert [state.name for state in alice.library] == ["Swords to Plowshares"]

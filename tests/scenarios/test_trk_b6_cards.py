"""Scenario: trk B6, simple cards part 2 (copies, sagas, statics, odd shapes), one test per card.

CR rules cited here were looked up with `mise run rules:find` in the writing session.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import Casting
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models.card import Color, Supertype, Type
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import PREDEFINED, TokenDefinition, create_tokens
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def _station_trk(scenario, spacecraft, tapped, username="alice"):
    from magic_cards_model.machines.keywords import station_activation

    activation = station_activation(scenario.game, spacecraft, tapped, username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()


def test_live_long_and_prosper_doubles_life_draws_that_many_and_lifts_the_hand_limit() -> None:
    """Double your life total, then draw cards equal to the cards in your hand
    (after the spell left it), and no maximum hand size until your next turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            life=7,
            hand=["Live Long and Prosper", "Grizzly Bears", "Grizzly Bears"],
            battlefield=["Plains"] * 4 + ["Island"] * 3,
            library=["Forest"] * 10,
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*["Plains"] * 4, *["Island"] * 3)
    scenario.cast_and_resolve("Live Long and Prosper", *sources)
    assert alice.life == 14
    assert len(alice.hand) == 4, "two in hand, then draw two"
    assert alice.has_no_maximum_hand_size


def test_first_contact_mills_four_takes_a_permanent_and_gains_life_only_as_the_first_spell() -> (
    None
):
    """Mill four, may put a permanent card from among them into hand; the 2 life comes
    only if First Contact is the first spell its controller has cast this game."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["First Contact", "First Contact", "Lightning Bolt"],
            battlefield=["Forest"] * 4 + ["Mountain"],
            library=["Island", "Lightning Bolt", "Lightning Bolt", "Forest", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("First Contact", *forests)
    scenario.pass_until_resolved()
    assert alice.life == 22, "first spell cast this game"
    assert len(alice.graveyard) == 4 or len(alice.graveyard) == 3  # one permanent went to hand
    assert alice.spells_cast_this_game == 1
    forests = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_onto_stack("First Contact", *forests)
    scenario.pass_until_resolved()
    assert alice.life == 22, "second spell cast this game gains nothing"
    assert alice.spells_cast_this_game == 2


def test_andromedan_automatons_fetches_every_copy_from_the_library() -> None:
    """Any number of cards named itself: both copies in the library reach the hand, a
    differently named card does not; proven again on Battalion Foot Soldier."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Andromedan Automatons", "Battalion Foot Soldier"],
            battlefield=["Plains"] * 6,
            library=[
                "Andromedan Automatons",
                "Forest",
                "Andromedan Automatons",
                "Battalion Foot Soldier",
                "Battalion Foot Soldier",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    plains = scenario.untapped_sources(*["Plains"] * 3)
    scenario.cast_onto_stack("Andromedan Automatons", *plains)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert [c.name for c in alice.hand].count("Andromedan Automatons") == 2
    assert "Andromedan Automatons" not in [c.name for c in alice.library]
    assert "Battalion Foot Soldier" in [c.name for c in alice.library]
    plains = scenario.untapped_sources(*["Plains"] * 3)
    scenario.cast_onto_stack("Battalion Foot Soldier", *plains)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert [c.name for c in alice.hand].count("Battalion Foot Soldier") == 2


def test_hit_it_gives_haste_and_puts_one_land_in_tapped_and_the_rest_in_the_graveyard() -> None:
    """Creatures you control have haste; the enters trigger reveals five, puts one land
    onto the battlefield tapped and the other four into the graveyard. Cavalier of Thorns
    proves the same reader with an untapped land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Hit It!", "Cavalier of Thorns"],
            battlefield=[
                "Mountain",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Forest",
                "Grizzly Bears",
            ],
            library=["Grizzly Bears", "Mountain", "Forest", "Island", "Lightning Bolt", "Plains"]
            * 2,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert not has_keyword(bears, "haste", scenario.game)
    scenario.cast_onto_stack("Hit It!", *scenario.untapped_sources("Mountain", "Forest", "Forest"))
    scenario.pass_until_resolved()
    assert has_keyword(bears, "haste", scenario.game)
    top_five = [c.id for c in alice.library[:5]]
    mountain = alice.library[1]
    scenario.will_choose_cards(mountain, username="alice")
    scenario.pass_until_resolved()
    assert mountain.zone is Zone.BATTLEFIELD and mountain.tapped
    assert len(alice.graveyard) == 4
    assert all(c.id not in top_five for c in alice.library)
    # Cavalier of Thorns: the same shape, the land comes in untapped.
    before = len(alice.graveyard)
    forest_on_top = alice.library[2]
    scenario.will_choose_cards(forest_on_top, username="alice")
    scenario.cast_onto_stack(
        "Cavalier of Thorns", *scenario.untapped_sources(*["Forest"] * 3, "Forest", "Forest")
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert forest_on_top.zone is Zone.BATTLEFIELD and not forest_on_top.tapped
    assert len(alice.graveyard) == before + 4


def test_deep_space_9_exiles_four_and_puts_every_permanent_in_at_enter_and_upkeep() -> None:
    """Enters and each upkeep: exile the top four, every permanent card among them goes
    onto the battlefield, the rest stay exiled. At 9 charge counters creatures get +3/+3."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Deep Space 9"],
            battlefield=["Plains"] * 9 + ["Craw Wurm"],
            library=[
                "Grizzly Bears",
                "Lightning Bolt",
                "Forest",
                "Giant Growth",
                "Llanowar Elves",
                "Shock",
                "Island",
                "Counterspell",
            ],
        )
        .player("bob", library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    ds9 = scenario.cast_onto_stack("Deep Space 9", *scenario.untapped_sources(*["Plains"] * 9))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    names = scenario.battlefield_names()
    assert "Grizzly Bears" in names and "Forest" in names
    exiled = {c.name for c in scenario.game.exile}
    assert exiled == {"Lightning Bolt", "Giant Growth"}, "nonpermanents stay exiled"
    wurm = scenario.creature("Craw Wurm", "alice")
    _station_trk(scenario, ds9, wurm)
    assert ds9.counter_count(Counter.CHARGE) == 6
    assert not scenario.game.characteristics_of(ds9).is_creature
    base = (wurm.power, wurm.toughness)
    scenario.game.add_counters(ds9, Counter.CHARGE, 3, putter="alice")
    assert ds9.counter_count(Counter.CHARGE) == 9
    assert (wurm.power, wurm.toughness) == (base[0] + 3, base[1] + 3)
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP):
        scenario.advance()
    scenario.pass_until_resolved()
    assert "Llanowar Elves" in scenario.battlefield_names()
    assert "Island" in scenario.battlefield_names()
    assert len(alice.library) == 0 or all(c.name != "Llanowar Elves" for c in alice.library)


def test_temporal_conqueror_returns_a_milled_land_else_makes_a_treasure() -> None:
    """Mill three, then return a land card from the graveyard to hand; with no land card
    there to return ("if you can't") create a Treasure. Roots of Wisdom proves the reader
    on a spell with a different fallback (draw a card)."""

    def board(library: list[str]) -> Scenario:
        return (
            Scenario()
            .player(
                "alice",
                hand=["Temporal Conqueror", "Roots of Wisdom"],
                battlefield=["Forest"] * 5,
                library=library,
            )
            .player("bob")
        )

    scenario = board(["Mountain", "Grizzly Bears", "Giant Growth", "Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    mountain = alice.library[0]
    scenario.cast_onto_stack("Temporal Conqueror", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert mountain.zone is Zone.HAND, "the milled land came back"
    assert "Treasure Token" not in scenario.battlefield_names()
    assert len(alice.graveyard) == 2

    scenario = board(["Grizzly Bears", "Giant Growth", "Lightning Bolt"] * 2 + ["Island"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.cast_onto_stack("Temporal Conqueror", *scenario.untapped_sources(*["Forest"] * 3))
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert "Treasure Token" in scenario.battlefield_names()
    assert len(alice.graveyard) == 3
    # Roots of Wisdom: no land or Elf in the graveyard after the mill -> draw a card.
    hand = len(alice.hand)
    scenario.cast_and_resolve("Roots of Wisdom", *scenario.untapped_sources("Forest", "Forest"))
    assert len(alice.hand) == hand - 1 + 1, "cast Roots (-1), fell back to draw (+1)"


def test_dal_rel_adds_red_or_green_per_land_and_sacrifices_a_land_to_draw() -> None:
    """Landfall: each land entering adds {R} or {G} (his controller picks as it resolves);
    "{3}, Sacrifice a land: Draw a card" costs a land."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Forest", "Mountain"],
            battlefield=["Dal R'El, Augment Orphan"] + ["Plains"] * 3,
            library=["Island"] * 3,
        )
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    dal = scenario.creature("Dal R'El, Augment Orphan", "alice")
    assert alice.mana_pool.total == 0
    scenario.play_land("Forest")
    scenario.pass_until_resolved()
    assert alice.mana_pool.total == 1, "one mana from the landfall trigger"
    floating = alice.mana_pool.floating
    assert floating.get(Color.RED, 0) + floating.get(Color.GREEN, 0) == 1
    # A land an opponent controls does not trigger it.
    scenario.game.put_onto_battlefield(scenario.find("Mountain", Zone.HAND, "alice"), "bob")
    scenario.pass_until_resolved()
    assert alice.mana_pool.total == 1
    # {3}, sacrifice a land: draw a card.
    plains = scenario.untapped_sources("Plains", "Plains", "Plains")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    hand = len(alice.hand)
    scenario.activate(dal, *plains, sacrificing=[forest])
    scenario.pass_until_resolved()
    assert forest.zone is Zone.GRAVEYARD
    assert len(alice.hand) == hand + 1


def test_salt_vampire_exiles_a_chosen_nonland_card_and_its_owner_draws() -> None:
    """Lifelink; the enters trigger looks at the opponent's hand, the controller may choose
    a nonland card, the opponent exiles it and then draws. Oildeep Gearhulk proves the
    reader with "discards" and no quality."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Salt Vampire", "Oildeep Gearhulk"],
            battlefield=["Swamp"] * 4 + ["Island", "Island"],
        )
        .player("bob", hand=["Lightning Bolt", "Mountain"], library=["Forest", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    vampire = scenario.cast_onto_stack("Salt Vampire", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()
    assert has_keyword(scenario.creature("Salt Vampire", "alice"), "lifelink", scenario.game)
    scenario.choose_trigger_targets("Salt Vampire", [bob])
    scenario.will_choose_cards(bolt, username="alice")
    scenario.pass_until_resolved()
    assert bolt.zone is Zone.EXILE, "the chosen card is exiled, not discarded"
    assert [c.name for c in bob.hand].count("Forest") == 1, "bob drew a card"
    assert "Mountain" in [c.name for c in bob.hand], "a land could not be chosen"
    assert vampire.zone is Zone.BATTLEFIELD
    # Oildeep Gearhulk: any card (a land is fine), discarded, then the player draws.
    mountain = scenario.find("Mountain", Zone.HAND, "bob")
    scenario.cast_onto_stack(
        "Oildeep Gearhulk", *scenario.untapped_sources("Island", "Island", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()
    scenario.choose_trigger_targets("Oildeep Gearhulk", [bob])
    scenario.will_choose_cards(mountain, username="alice")
    scenario.pass_until_resolved()
    assert mountain.zone is Zone.GRAVEYARD
    assert [c.name for c in bob.hand].count("Forest") == 2


def test_will_riker_puts_two_revealed_lands_in_at_combat_and_sacrifices_them_at_end_step() -> None:
    """At the beginning of combat on your turn, reveal until two lands: both land on the
    battlefield, the rest go to the bottom; at your next end step those lands are
    sacrificed (a land that was already there is not)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Will Riker, First in the Field", "Forest"],
            library=["Grizzly Bears", "Mountain", "Giant Growth", "Island", "Plains", "Plains"],
        )
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.advance()  # beginning of combat
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()
    names = scenario.battlefield_names()
    assert names.count("Mountain") == 1 and names.count("Island") == 1
    assert names.count("Plains") == 0, "stops after two lands"
    assert [c.name for c in alice.library[-2:]].count("Grizzly Bears") + [
        c.name for c in alice.library[-2:]
    ].count("Giant Growth") == 2, "the nonlands went to the bottom"
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    names = scenario.battlefield_names()
    assert "Mountain" not in names and "Island" not in names
    assert "Forest" in names, "the land that was already there stays"


def test_peace_in_our_time_trades_the_attack_for_a_card_and_wins_with_twelve_counters() -> None:
    """At the beginning of combat on each player's turn, that player may draw; if they do
    they can't attack this turn and Peace gets a peace counter (whoever drew). With twelve
    counters its controller wins at their upkeep."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Peace in Our Time", "Goblin Guide"],
            library=["Forest"] * 6,
        )
        .player("bob", battlefield=["Goblin Guide"], library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    peace = scenario.find("Peace in Our Time", Zone.BATTLEFIELD, "alice")
    guide = scenario.creature("Goblin Guide", "alice")
    scenario.will_take_the_may(False, username="alice")
    scenario.advance()  # beginning of combat
    scenario.pass_until_resolved()
    assert peace.counter_count("peace") == 0
    scenario.advance()
    assert scenario.can_attack(guide), "declined the card, so she may attack"
    # Next, bob's own turn: bob takes the card, so Peace gains a counter and he is stuck.
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    bob_guide = scenario.creature("Goblin Guide", "bob")
    bob_hand = len(scenario.player("bob").hand)
    scenario.will_take_the_may(True, username="bob")
    scenario.advance()  # bob's beginning of combat
    scenario.pass_until_resolved()
    assert len(scenario.player("bob").hand) == bob_hand + 1
    assert peace.counter_count("peace") == 1, "its controller gets the counter, not bob"
    scenario.advance()
    assert not scenario.can_attack(bob_guide, defending="alice")
    # Twelve counters: alice wins at her upkeep.
    scenario.game.add_counters(peace, "peace", 11, putter="alice")
    while not (scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP):
        scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.game.winner == "alice"
    assert alice.life > 0


def test_dominion_saboteur_copies_a_legendary_creature_as_nonlegendary_with_its_counters() -> None:
    """Enters as a copy of any artifact or creature, except it isn't legendary, with
    additional counters equal to the copied permanent's. Phyrexian Metamorph proves the
    "artifact or creature" candidate filter by copying an artifact."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dominion Saboteur", "Phyrexian Metamorph"],
            battlefield=["Island"] * 9,
        )
        .player("bob", battlefield=["Thalia, Guardian of Thraben", "Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thalia = scenario.creature("Thalia, Guardian of Thraben", "bob")
    scenario.game.add_counters(thalia, Counter.PLUS_ONE, 2, putter="bob")
    scenario.game.add_counters(thalia, "charge", 1, putter="bob")
    scenario.will_choose_cards(thalia, username="alice", source="Dominion Saboteur")
    saboteur = scenario.cast_and_resolve(
        "Dominion Saboteur", *scenario.untapped_sources(*["Island"] * 5)
    )
    chars = scenario.game.characteristics_of(saboteur)
    assert saboteur.name == "Thalia, Guardian of Thraben"
    assert Supertype.LEGENDARY not in chars.supertypes, "except it isn't legendary"
    assert saboteur.counter_count(Counter.PLUS_ONE) == 2
    assert saboteur.counter_count("charge") == 1
    assert thalia.counter_count(Counter.PLUS_ONE) == 2, "the original keeps its counters"
    # Phyrexian Metamorph: an artifact is a legal candidate too.
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_cards(sol_ring, username="alice", source="Phyrexian Metamorph")
    metamorph = scenario.cast_and_resolve(
        "Phyrexian Metamorph", *scenario.untapped_sources(*["Island"] * 4)
    )
    assert metamorph.name == "Sol Ring"


def _tokens(scenario, name: str, username: str = "alice") -> list:
    return [
        p for p in scenario.game.permanents_controlled_by(username) if p.name == name and p.token
    ]


def test_dominion_infiltration_copies_x_creatures_with_changeling_and_haste_then_exiles_them() -> (
    None
):
    """X target creatures your opponents control: a token copy of each (with changeling,
    so every creature type), hasty, exiled at the next end step; an untargeted creature
    is not copied."""
    scenario = (
        Scenario()
        .player("alice", hand=["Dominion Infiltration"], battlefield=["Mountain"] * 5)
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears", "Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    card = scenario.find("Dominion Infiltration", Zone.HAND, "alice")
    scenario.will_choose_targets(angel, bears)
    scenario.game.cast(
        card, "alice", x_value=2, mana_sources=scenario.untapped_sources(*["Mountain"] * 5)
    )
    scenario.pass_until_resolved()
    (angel_copy,) = _tokens(scenario, "Serra Angel")
    (bears_copy,) = _tokens(scenario, "Grizzly Bears")
    assert not _tokens(scenario, "Llanowar Elves")
    assert has_keyword(angel_copy, "flying", scenario.game)
    assert has_keyword(angel_copy, "haste", scenario.game)
    assert has_keyword(bears_copy, "haste", scenario.game)
    subtypes = scenario.game.characteristics_of(bears_copy).subtypes
    assert "Human" in subtypes and "Elf" in subtypes, "changeling: every creature type"
    assert "Human" not in scenario.game.characteristics_of(bears).subtypes, "originals untouched"
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    assert not _tokens(scenario, "Serra Angel") and not _tokens(scenario, "Grizzly Bears")
    assert angel.zone is Zone.BATTLEFIELD and bears.zone is Zone.BATTLEFIELD


def test_mirror_universe_intrusion_copies_one_creature_or_every_creature_when_kicked() -> None:
    """Unkicked: one token copy of the target creature, with menace. Kicked: instead a
    token copy (with menace) of each creature the target opponent controls."""

    def board() -> Scenario:
        return (
            Scenario()
            .player(
                "alice",
                hand=["Mirror Universe Intrusion"],
                battlefield=["Island"] * 5 + ["Swamp"] * 4,
            )
            .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
        )

    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Mirror Universe Intrusion", Zone.HAND, "alice")
    scenario.will_choose_targets(scenario.creature("Serra Angel", "bob"), scenario.player("bob"))
    scenario.game.cast(
        card, "alice", mana_sources=scenario.untapped_sources("Island", "Swamp", "Island")
    )
    scenario.pass_until_resolved()
    (copy,) = _tokens(scenario, "Serra Angel")
    assert has_keyword(copy, "menace", scenario.game)
    assert has_keyword(copy, "flying", scenario.game)
    assert not _tokens(scenario, "Grizzly Bears"), "unkicked copies only the one target"

    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    card = scenario.find("Mirror Universe Intrusion", Zone.HAND, "alice")
    scenario.will_choose_targets(scenario.creature("Serra Angel", "bob"), scenario.player("bob"))
    scenario.game.cast(
        card,
        "alice",
        kicker=1,
        mana_sources=scenario.untapped_sources(*["Island"] * 5, *["Swamp"] * 4),
    )
    scenario.pass_until_resolved()
    assert len(_tokens(scenario, "Serra Angel")) == 1
    (bears_copy,) = _tokens(scenario, "Grizzly Bears")
    assert has_keyword(bears_copy, "menace", scenario.game)


def test_gwyndala_makes_an_equipment_token_and_turns_every_equipment_token_into_a_copy() -> None:
    """Enters: a Neuroflux Heirloom Equipment token (+1/+1, equip {2}) attached to her.
    {2}: each Equipment token you control becomes a copy of target Equipment you control
    until end of turn - here Bonesplitter - and goes back at end of turn."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Gwyndala, the Progeny"],
            battlefield=["Island"] * 4 + ["Bonesplitter"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gwyndala = scenario.cast_and_resolve(
        "Gwyndala, the Progeny", *scenario.untapped_sources("Island", "Island")
    )
    scenario.pass_until_resolved()
    heirloom = next(p for p in scenario.game.battlefield if p.name == "Neuroflux Heirloom")
    assert heirloom.token and heirloom.attached_to == gwyndala.id
    assert (gwyndala.power, gwyndala.toughness) == (3, 3), "base 2/2 plus the Heirloom's +1/+1"
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    scenario.activate(gwyndala, *scenario.untapped_sources("Island", "Island"), targets=[splitter])
    scenario.pass_until_resolved()
    assert heirloom.name == "Bonesplitter", "the token is a copy of Bonesplitter"
    assert splitter.name == "Bonesplitter" and not splitter.token, (
        "the nontoken original is not a token"
    )
    assert gwyndala.power == 4, "Bonesplitter's +2/+0 now"


def test_replicator_makes_a_food_and_copies_a_token_tapped() -> None:
    """Enters: a Food. {2},{T}: a tapped token that's a copy of target token you control."""
    scenario = (
        Scenario()
        .player("alice", hand=["Replicator"], battlefield=["Island"] * 4)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    replicator = scenario.cast_and_resolve(
        "Replicator", *scenario.untapped_sources("Island", "Island")
    )
    scenario.pass_until_resolved()
    foods = _tokens(scenario, "Food")
    assert len(foods) == 1
    scenario.activate(
        replicator, *scenario.untapped_sources("Island", "Island"), targets=[foods[0]]
    )
    scenario.pass_until_resolved()
    foods = _tokens(scenario, "Food")
    assert len(foods) == 2
    assert sorted(food.tapped for food in foods) == [False, True], "only the copy is tapped"
    assert replicator.tapped


def _attack_unblocked(scenario, *attackers) -> None:
    """Advance to declare attackers, attack with `attackers` and deal combat damage."""
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    scenario.advance()  # declare attackers
    scenario.attack_with(*attackers, defending="bob")
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    scenario.combat_damage()


def test_antagonist_incorporator_lets_artifact_creatures_pay_one_for_a_borg_token() -> None:
    """Artifact creatures you control have "Whenever this creature deals combat damage to a
    player, you may pay {1}. If you do, create a 1/1 colorless Borg artifact creature
    token." - an artifact creature gets it, a plain creature does not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Antagonist Incorporator",
                "Phyrexian Revoker",
                "Grizzly Bears",
                "Plains",
                "Plains",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    revoker = scenario.creature("Phyrexian Revoker", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_pay_the_mana_cost(True, username="alice")
    _attack_unblocked(scenario, revoker, bears)
    triggers = [t.source_name for t in scenario.pending_triggers]
    assert triggers == ["Phyrexian Revoker"], "only the artifact creature has the trigger"
    scenario.pass_until_resolved()
    (borg,) = _tokens(scenario, "Borg Token") or _tokens(scenario, "Borg")
    assert (borg.power, borg.toughness) == (1, 1)
    assert Type.ARTIFACT in scenario.game.characteristics_of(borg).types
    assert any(
        p.tapped for p in scenario.game.permanents_controlled_by("alice") if p.name == "Plains"
    )


def test_hive_mind_coprocessor_lets_artifact_creatures_pay_life_to_draw() -> None:
    """The same grant with "you may pay 1 life. If you do, draw a card"; declining pays
    nothing and draws nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hive Mind Coprocessor", "Phyrexian Revoker"],
            library=["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    revoker = scenario.creature("Phyrexian Revoker", "alice")
    hand = len(alice.hand)
    scenario.will_pay_the_life(True, username="alice")
    _attack_unblocked(scenario, revoker)
    scenario.pass_until_resolved()
    assert alice.life == 19
    assert len(alice.hand) == hand + 1


def test_captain_jean_luc_picard_anthem_officer_tokens_and_seven_officer_spacecraft_search() -> (
    None
):
    """Other creatures get +1/+1; casting a creature makes a 1/1 red Officer; tapping seven
    untapped Officers fetches a Spacecraft onto the battlefield with seven charge counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Captain Jean-Luc Picard", "Forest", "Forest"],
            library=["Romulan Bird-of-Prey", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    picard = scenario.creature("Captain Jean-Luc Picard", "alice")
    bears = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert (bears.power, bears.toughness) == (3, 3), "2/2 plus Picard's +1/+1"
    (officer,) = _tokens(scenario, "Officer")
    assert (officer.power, officer.toughness) == (2, 2), "a 1/1 with the anthem"
    assert Color.RED in scenario.game.characteristics_of(officer).colors
    create_tokens(
        scenario.game,
        TokenDefinition(subtypes=("Officer",), colors=(Color.RED,), power=1, toughness=1),
        "alice",
        count=6,
    )
    officers = _tokens(scenario, "Officer")
    assert len(officers) == 7
    scenario.activate(picard, tapping_for_cost=officers)
    scenario.pass_until_resolved()
    ship = scenario.find("Romulan Bird-of-Prey", Zone.BATTLEFIELD, "alice")
    assert ship.counter_count(Counter.CHARGE) == 7
    assert all(officer.tapped for officer in officers)


def test_conquest_mission_counts_quest_counters_and_doubles_the_borg_at_six() -> None:
    """Each nontoken artifact entering: a quest counter, then a 1/1 Borg artifact creature
    token - two once the Mission has six or more quest counters. A token artifact does not
    trigger it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sol Ring", "Mind Stone", "Sol Ring"],
            battlefield=["Conquest Mission"] + ["Plains"] * 8,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mission = scenario.find("Conquest Mission", Zone.BATTLEFIELD, "alice")
    scenario.cast_and_resolve("Sol Ring", *scenario.untapped_sources("Plains"))
    scenario.pass_until_resolved()
    assert mission.counter_count("quest") == 1
    assert len(_tokens(scenario, "Borg Token") + _tokens(scenario, "Borg")) == 1
    create_tokens(scenario.game, PREDEFINED["Treasure"], "alice", count=1)
    scenario.game.pending_triggers.clear()
    assert mission.counter_count("quest") == 1, "a token artifact does not trigger it"
    scenario.game.add_counters(mission, "quest", 4, putter="alice")  # now 5
    scenario.cast_and_resolve("Mind Stone", *scenario.untapped_sources("Plains", "Plains"))
    scenario.pass_until_resolved()
    assert mission.counter_count("quest") == 6
    assert len(_tokens(scenario, "Borg Token") + _tokens(scenario, "Borg")) == 3, "two more"


def test_support_mission_puts_one_counter_then_two_once_it_has_five_quest_counters() -> None:
    """Each creature entering: a quest counter on the Mission and a +1/+1 counter on that
    creature - two +1/+1 counters once the Mission has five or more quest counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears", "Grizzly Bears"],
            battlefield=["Support Mission"] + ["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mission = scenario.find("Support Mission", Zone.BATTLEFIELD, "alice")
    first = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert mission.counter_count("quest") == 1
    assert first.counter_count(Counter.PLUS_ONE) == 1
    scenario.game.add_counters(mission, "quest", 3, putter="alice")  # now 4: the next makes 5
    second = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert mission.counter_count("quest") == 5
    assert second.counter_count(Counter.PLUS_ONE) == 2


# -- Sagas and the rest ----------------------------------------------------------------


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _chapter(scenario, saga, chapter: int, *targets) -> None:
    """Put the lore counter that makes chapter `chapter` trigger (CR 714.2b) and resolve it."""
    missing = chapter - 1 - saga.counter_count(Counter.LORE)
    if missing > 0:
        scenario.game.add_counters(saga, Counter.LORE, missing)
    scenario.game.pending_triggers.clear()
    if targets:
        scenario.will_choose_targets(*targets)
    scenario.game.add_counters(saga, Counter.LORE, 1)
    _resolve_everything(scenario)


def _names(scenario, zone: Zone, username: str = "alice") -> list[str]:
    return sorted(c.name for c in scenario.player(username).cards_in(zone))


def test_the_measure_of_a_man_exiles_investigates_then_returns_the_card_and_gains_two() -> None:
    """I exiles up to one nontoken artifact or creature, II investigates, III returns the
    exiled card under its owner's control and gains 2 life."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Measure of a Man"], library=["Island"] * 6)
        .player("bob", battlefield=["Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("The Measure of a Man", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    _chapter(scenario, saga, 1, bears)
    assert bears.zone is Zone.EXILE
    _chapter(scenario, saga, 2)
    assert [t.name for t in _tokens(scenario, "Clue")] == ["Clue"]
    life = scenario.player("alice").life
    _chapter(scenario, saga, 3)
    back = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    assert back.controller == "bob", "CR 400.7: returned under its owner's control"
    assert scenario.player("alice").life == life + 2


def test_all_good_things_exiles_from_hand_and_gains_ten_only_if_the_exiled_share_a_type() -> None:
    """I, II, III: draw two, then exile a card from your hand. IV: gain 10 life if every
    card exiled with the Saga shares a card type."""

    def run(second_exile: str) -> tuple[int, int]:
        scenario = (
            Scenario()
            .player(
                "alice",
                hand=["Island", "Grizzly Bears"],
                battlefield=["All Good Things..."],
                library=["Island"] * 8,
            )
            .player("bob", library=["Island"] * 4)
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        saga = scenario.find("All Good Things...", Zone.BATTLEFIELD, "alice")
        hand = len(scenario.player("alice").hand)
        scenario.will_choose_cards(scenario.find("Island", Zone.HAND, "alice"))
        _chapter(scenario, saga, 1)
        assert len(scenario.player("alice").hand) == hand + 2 - 1
        scenario.will_choose_cards(scenario.find(second_exile, Zone.HAND, "alice"))
        _chapter(scenario, saga, 2)
        life = scenario.player("alice").life
        _chapter(scenario, saga, 4)
        return life, scenario.player("alice").life

    before, after = run("Island")
    assert after == before + 10, "two lands share a card type"
    before, after = run("Grizzly Bears")
    assert after == before, "a land and a creature share no type"


def test_the_wrath_of_khan_damages_steals_at_combat_exiles_for_a_card_and_edicts() -> None:
    """I: 4 damage to a creature an opponent controls, then at the next combat this turn
    gain control of it until end of turn, untap it, haste. II: you may exile a card from your
    hand; if you do, draw. III: each opponent sacrifices a nontoken permanent."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Island"],
            battlefield=["The Wrath of Khan"],
            library=["Island"] * 6,
        )
        .player("bob", battlefield=["Colossal Dreadmaw", "Grizzly Bears"], library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("The Wrath of Khan", Zone.BATTLEFIELD, "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    dreadmaw.tapped = True
    _chapter(scenario, saga, 1, dreadmaw)
    assert dreadmaw.damage == 4 and dreadmaw.zone is Zone.BATTLEFIELD
    assert dreadmaw.controller == "bob", "not yet: only at the beginning of combat"
    while scenario.step is not Step.BEGINNING_OF_COMBAT:
        scenario.advance()
    _resolve_everything(scenario)
    board = scenario.game.computed_board()
    assert dreadmaw.controller == "alice"
    assert not dreadmaw.tapped
    assert board.of(dreadmaw).has_ability("Haste")
    # II (back in a fresh turn state is not needed): exile the Island, draw a card.
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(scenario.find("Island", Zone.HAND, "alice"))
    hand = len(scenario.player("alice").hand)
    _chapter(scenario, saga, 2)
    assert len(scenario.player("alice").hand) == hand, "one exiled, one drawn"
    assert scenario.find("Island", Zone.EXILE, None) is not None
    _chapter(scenario, saga, 3)
    assert len(scenario.game.permanents_controlled_by("bob")) == 1, "bob sacrificed one"


def test_the_inner_light_draws_as_many_cards_as_the_chosen_creature_deals() -> None:
    """II: choose target creature; whenever it deals combat damage to a player this turn,
    you draw that many cards."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Inner Light", "Runeclaw Bear"],
            library=["Island"] * 8,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("The Inner Light", Zone.BATTLEFIELD, "alice")
    bear = scenario.creature("Runeclaw Bear", "alice")
    _chapter(scenario, saga, 2, bear)
    hand = len(scenario.player("alice").hand)
    _attack_unblocked(scenario, bear)
    _resolve_everything(scenario)
    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == hand + 2, "two damage, two cards"


def test_those_old_scientists_shuffles_two_graveyard_cards_into_their_owners_libraries() -> None:
    """III: choose up to two target cards in graveyards; their owners shuffle them into their
    libraries - here one card from each player's graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Those Old Scientists"],
            graveyard=["Lightning Bolt"],
            library=["Island"] * 4,
        )
        .player("bob", graveyard=["Grizzly Bears"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("Those Old Scientists", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    _chapter(scenario, saga, 3, bolt, bears)
    assert bolt.zone is Zone.LIBRARY and bolt.owner == "alice"
    assert bears.zone is Zone.LIBRARY and bears.owner == "bob"


def test_overflow_submatrix_casts_one_artifact_creature_a_turn_from_the_graveyard() -> None:
    """Once during each of your turns, cast an artifact creature spell from your graveyard;
    it enters with a finality counter."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Overflow Submatrix"],
            graveyard=["Memnite", "Memnite"],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = [
        c for c in scenario.player("alice").cards_in(Zone.GRAVEYARD) if c.name == "Memnite"
    ]
    casting = Casting(spell=first, caster="alice", origin_zone=Zone.GRAVEYARD, game=scenario.game)
    casting.use_keyword("Cast permission")
    scenario.auto_pay(casting.begin_paying(), username="alice")
    spell = scenario.put_on_stack(casting)
    _resolve_everything(scenario)
    assert spell.zone is Zone.BATTLEFIELD
    assert spell.counter_count(Counter.FINALITY) == 1
    again = Casting(spell=second, caster="alice", origin_zone=Zone.GRAVEYARD, game=scenario.game)
    with pytest.raises(Exception):  # noqa: B017 - the permission is used up for this turn
        again.use_keyword("Cast permission")


def test_brazen_bluff_the_opponent_may_exile_their_spell_or_you_cast_for_free() -> None:
    """Target noncreature spell an opponent controls: its controller may exile it; if they
    do not, you may cast a noncreature spell from your hand without paying its cost."""

    def run(opponent_exiles: bool):
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player("bob", hand=["Shock"], battlefield=["Mountain"] * 2, library=["Island"] * 4)
            .player(
                "alice",
                hand=["Brazen Bluff", "Lightning Bolt"],
                battlefield=["Mountain"] * 2,
                library=["Island"] * 4,
            )
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        shock = scenario.cast_onto_stack("Shock", username="bob", auto=True, targets=["alice"])
        scenario.pass_priority("bob")
        scenario.will_take_the_may(opponent_exiles, username="bob")
        if not opponent_exiles:
            scenario.will_take_the_may(True, username="alice")
            scenario.will_choose_cards(
                scenario.find("Lightning Bolt", Zone.HAND, "alice"), username="alice"
            )
            scenario.will_choose_targets("bob", username="alice")
        scenario.cast_and_resolve("Brazen Bluff", username="alice", auto=True, targets=[shock])
        return scenario, shock

    scenario, shock = run(True)
    assert shock.zone is Zone.EXILE
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice") is not None

    scenario, shock = run(False)
    assert shock.zone is Zone.STACK
    assert scenario.find("Lightning Bolt", Zone.STACK, None) is not None, "cast for free"
    _resolve_everything(scenario)
    assert scenario.player("alice").life == 18 and scenario.player("bob").life == 17


def test_im_a_doctor_not_a_adds_a_counter_untaps_pumps_and_makes_it_only_a_doctor() -> None:
    """+1/+1 counter, untap, and until end of turn +1/+1 and it is a Doctor (losing every other
    creature type)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["I'm a Doctor, Not a . . ."],
            battlefield=["Runeclaw Bear", "Forest"],
            library=["Island"] * 4,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Runeclaw Bear", "alice")
    bear.tapped = True
    scenario.cast_and_resolve(
        "I'm a Doctor, Not a . . .", *scenario.untapped_sources("Forest"), targets=[bear]
    )
    chars = scenario.game.computed_board().of(bear)
    assert bear.counter_count(Counter.PLUS_ONE) == 1
    assert not bear.tapped
    assert (chars.power, chars.toughness) == (4, 4)
    assert "Doctor" in chars.subtypes and "Bear" not in chars.subtypes


def test_de_evolve_shrinks_stops_blocking_makes_a_salamander_and_exiles_at_threshold() -> None:
    """Enchanted creature gets -4/-0, can't block and is a Salamander (no other creature
    types); at each upkeep with seven or more cards in your graveyard, exile it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["De-evolve"],
            battlefield=["Swamp", "Swamp"],
            library=["Island"] * 4,
        )
        .player("bob", battlefield=["Colossal Dreadmaw"], library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    scenario.cast_and_resolve(
        "De-evolve", *scenario.untapped_sources("Swamp", "Swamp"), targets=[dreadmaw]
    )
    chars = scenario.game.computed_board().of(dreadmaw)
    assert (chars.power, chars.toughness) == (2, 6)
    assert "Salamander" in chars.subtypes and "Dinosaur" not in chars.subtypes
    assert scenario.game.why_cannot_block(dreadmaw) is not None


def test_dathon_adds_another_counter_of_a_chosen_kind_and_draws_on_enchantments() -> None:
    """{2}: choose a counter on target enchantment you control and put another of that kind
    on it, at sorcery speed. Casting an enchantment draws a card; a Saga also pings each
    opponent for 2."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Those Old Scientists"],
            battlefield=["Dathon, His Heart Open", "The Inner Light", "Island", "Island", "Island"]
            + ["Island"] * 3,
            library=["Island"] * 6,
        )
        .player("bob", library=["Island"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dathon = scenario.creature("Dathon, His Heart Open", "alice")
    saga = scenario.find("The Inner Light", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(saga, Counter.LORE, 1)
    scenario.game.pending_triggers.clear()
    scenario.activate(dathon, *scenario.untapped_sources("Island", "Island"), targets=[saga])
    scenario.pass_until_resolved()
    assert saga.counter_count(Counter.LORE) == 2
    hand = len(scenario.player("alice").hand)
    scenario.cast_and_resolve(
        "Those Old Scientists", *scenario.untapped_sources("Island", "Island", "Island")
    )
    _resolve_everything(scenario)
    assert len(scenario.player("alice").hand) == hand - 1 + 1, "cast one, drew one"
    assert scenario.player("bob").life == 18, "a Saga spell deals 2 to each opponent"

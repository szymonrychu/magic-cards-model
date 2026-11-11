"""Scenario: a legend calling itself by its honorific short name (CR 201.5c).

"Text printed on some cards refers to that card by a shortened version of its
name. Instances of a card's shortened name used in this manner are treated as
though they used the card's full name." (CR 201.5c). The Star Trek legends keep
their title and drop their given names (and a quoted nickname): Dr. Beverly
Crusher is "Dr. Crusher", Captain Kathryn Janeway "Captain Janeway", Ensign
Pavel Chekov "Ensign Chekov", Dr. Leonard "Bones" McCoy "Dr. McCoy".

No printing outside this set calls itself by title and surname (checked on
Scryfall for every legal legendary whose name opens with a title word), so the
reader is proven on differently-titled cards of this set instead (`MEMORY.md`).

CR rules cited here were looked up with `mise run rules:find` in the writing
session: 201.5c, 603.2d (a trigger triggering additional times), 701.44a
(explore), 305.2 (additional land plays), 601.3 (play permissions).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import honorific_short_name, self_reference_names
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario

BONES_RETURN = "Return target non-Doctor permanent card from your graveyard to your hand."
BONES_SAVE = (
    "Choose up to one other target creature. When it dies this turn, return that card to the "
    "battlefield under its owner's control with a +1/+1 counter on it at the beginning of the "
    "next end step."
)

# -- the reader's corner cases -----------------------------------------------


def test_the_short_name_is_the_title_and_the_surname():
    assert honorific_short_name("Dr. Beverly Crusher") == "Dr. Crusher"
    assert honorific_short_name("Captain Kathryn Janeway") == "Captain Janeway"
    assert honorific_short_name("Ensign Pavel Chekov") == "Ensign Chekov"


def test_a_quoted_nickname_and_a_middle_initial_are_dropped():
    assert honorific_short_name('Dr. Leonard "Bones" McCoy') == "Dr. McCoy"
    assert honorific_short_name("Captain James T. Kirk") == "Captain Kirk"


def test_the_part_after_a_comma_is_not_part_of_the_name_shortened():
    assert honorific_short_name("Dr. McCoy, Surly Surgeon") is None, "already title + surname"
    assert "Dr. McCoy" in self_reference_names("Dr. McCoy, Surly Surgeon")


def test_no_title_or_no_given_name_gives_no_short_name():
    assert honorific_short_name("Captain Lannery Storm") == "Captain Storm"
    assert honorific_short_name("Kira Nerys") is None
    assert honorific_short_name("Captain Sisay") is None


def test_only_a_legendary_card_shortens_its_name():
    assert "Dr. Crusher" in self_reference_names("Dr. Beverly Crusher")
    assert "Dr. Crusher" not in self_reference_names("Dr. Beverly Crusher", legendary=False)


# -- the cards ----------------------------------------------------------------


def test_dr_beverly_crusher_doubles_her_own_life_gain_trigger():
    """Soul Warden's trigger is caused by a creature entering, not by life gain,
    so it triggers once; the 1 life it gains causes "Dr. Crusher"'s own
    trigger, which triggers an additional time: two +1/+1 counters."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Dr. Beverly Crusher", "Soul Warden", "Forest", "Forest"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crusher = scenario.creature("Dr. Beverly Crusher", "alice")
    scenario.cast_onto_stack("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    scenario.pass_until_resolved()  # Grizzly Bears
    assert scenario.stack_names() == ["Soul Warden's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 21
    assert scenario.stack_names() == ["Dr. Beverly Crusher's triggered ability"] * 2
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert crusher.counter_count(Counter.PLUS_ONE) == 2
    assert scenario.player("alice").life == 21, "Soul Warden's own trigger was not doubled"


def test_dr_beverly_crusher_ignores_an_opponent_gaining_life():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Dr. Beverly Crusher"], library=["Island"] * 4)
        .player(
            "bob",
            hand=["Grizzly Bears"],
            battlefield=["Soul Warden", "Forest", "Forest"],
            library=["Island"] * 4,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest", username="bob")
    )
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 21
    assert scenario.stack_names() == []
    assert scenario.creature("Dr. Beverly Crusher", "alice").counter_count(Counter.PLUS_ONE) == 0


def test_captain_kathryn_janeway_explores_as_she_enters_and_lets_two_lands_be_played():
    """ "Whenever Captain Janeway or another creature you control enters, that
    creature explores": her own entry reveals a land, which goes to hand; a
    second creature's entry reveals a nonland card and that creature gets the
    counter. "You may play an additional land on each of your turns.\""""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Captain Kathryn Janeway", "Grizzly Bears", "Forest", "Forest"],
            battlefield=["Forest"] * 6,
            library=["Island", "Llanowar Elves", "Swamp"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    janeway = scenario.cast_and_resolve(
        "Captain Kathryn Janeway", *scenario.untapped_sources(*["Forest"] * 4)
    )
    assert scenario.stack_names() == ["Captain Kathryn Janeway's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.find("Island", Zone.HAND, "alice").zone is Zone.HAND, "a land goes to hand"
    assert janeway.counter_count(Counter.PLUS_ONE) == 0
    bears = scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest")
    )
    scenario.pass_until_resolved()
    assert bears.counter_count(Counter.PLUS_ONE) == 1, "a nonland card: the counter"
    assert janeway.counter_count(Counter.PLUS_ONE) == 0, "that creature, not Janeway"
    scenario.play_land("Forest")
    scenario.play_land("Forest")
    assert scenario.game.why_cannot_play_land("alice") is not None, "two lands, no third"


def test_captain_kathryn_janeway_ignores_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain Kathryn Janeway"], library=["Island"] * 4)
        .player(
            "bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"], library=["Island"] * 4
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()
    scenario.cast_and_resolve(
        "Grizzly Bears", *scenario.untapped_sources("Forest", "Forest", username="bob")
    )
    assert scenario.stack_names() == []


def test_ensign_pavel_chekov_lets_you_play_a_land_an_opponent_exiled():
    """Strange new worlds: X is the number of differently named lands alice
    controls (Island, Forest, Mountain: 3, the second Island not counted). Bob
    exiles his top three cards, alice chooses one land card among them and may
    play it for as long as it remains exiled; the other land gets nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ensign Pavel Chekov"],
            battlefield=["Island", "Island", "Forest", "Mountain"],
        )
        .player("bob", library=["Plains", "Grizzly Bears", "Swamp", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    plains, bears, swamp = bob.library[:3]
    scenario.will_choose_cards(swamp, source="Ensign Pavel Chekov")
    scenario.cast_and_resolve(
        "Ensign Pavel Chekov",
        *scenario.untapped_sources("Island", "Island", "Forest", "Mountain"),
    )
    scenario.pass_until_resolved()
    assert [card.zone for card in (plains, bears, swamp)] == [Zone.EXILE] * 3
    assert len(bob.library) == 1
    land = scenario.game.play_land(swamp, "alice")
    assert land.zone is Zone.BATTLEFIELD and land.controller == "alice"
    assert scenario.game.why_cannot_play_land("alice", plains) is not None


def test_dr_leonard_bones_mccoy_returns_a_non_doctor_permanent_card():
    """ "When Dr. McCoy enters, choose one - Return target non-Doctor permanent
    card from your graveyard to your hand." (the first mode)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=['Dr. Leonard "Bones" McCoy'],
            battlefield=["Forest"] * 3,
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    scenario.will_choose_mode(BONES_RETURN)
    scenario.choose_trigger_targets('Dr. Leonard "Bones" McCoy', [bears])
    scenario.cast_and_resolve(
        'Dr. Leonard "Bones" McCoy', *scenario.untapped_sources(*["Forest"] * 3)
    )
    scenario.pass_until_resolved()
    assert bears.zone is Zone.HAND


def test_dr_leonard_bones_mccoy_brings_a_dying_creature_back_with_a_counter():
    """The second mode: when the chosen creature dies this turn, it returns to
    the battlefield under its owner's control with a +1/+1 counter at the
    beginning of the next end step."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=['Dr. Leonard "Bones" McCoy', "Lightning Bolt"],
            battlefield=["Forest"] * 3 + ["Mountain", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.will_choose_mode(BONES_SAVE)
    scenario.will_choose_targets(bears, source='Dr. Leonard "Bones" McCoy')
    scenario.cast_and_resolve(
        'Dr. Leonard "Bones" McCoy', *scenario.untapped_sources(*["Forest"] * 3)
    )
    scenario.pass_until_resolved()
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bears]
    )
    assert bears.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.pass_until_resolved()
    returned = scenario.creature("Grizzly Bears", "alice")
    assert returned.counter_count(Counter.PLUS_ONE) == 1

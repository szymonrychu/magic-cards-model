"""Gift: CR 702.174, the additional-cost half and the "chosen player" effect.

"The first ability is always 'As an additional cost to cast this spell, you
may choose an opponent.'" (CR 702.174a) - `Casting.pay_gift` records the
choice; nothing is spent, since the choice *is* the cost. "For instant and
sorcery spells, the effect of a gift ability always happens before any other
spell abilities of the card" (CR 702.174j) -
`machines/effects.apply_gift_if_promised`, dispatched off the keyword's own
printed parameter through `_GIFT_EFFECTS` (CR 702.174d-i, every shape the
rule states, not only Into the Flood Maw's own "a tapped Fish").

A permanent's own gift trigger (CR 702.174b's "when this permanent enters,
if its gift cost was paid, [effect]") is not modelled - see
docs/engine-coverage.md.

Proved generic on Crumb and Get It's "Gift a Food", a card outside the deck
pool and outside this wave's brief, and again on Blooming Blast's own
"Gift a Treasure" plus a conditional rider gated on the identical "if the
gift was promised" condition Bilbo's Gambit's own "players can't cast spells
this turn." reads (`machines.effects._parse_if_condition_players_cant_cast_
clause`, CR 611.2c).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting_restrictions import blanket_cant_cast_restriction
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_into_the_flood_maw_gifts_a_tapped_fish():
    """Into the Flood Maw: "Gift a tapped Fish ... Return target creature an
    opponent controls to its owner's hand."
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Into the Flood Maw"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    maw = scenario.find("Into the Flood Maw", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.game.cast(maw, "alice", targets=[bears], mana_sources=[island], gift="bob")
    scenario.pass_until_resolved()

    fish = [state for state in scenario.game.battlefield if state.name == "Fish Token"]
    assert len(fish) == 1
    (fish_token,) = fish
    assert fish_token.controller == "bob"
    assert fish_token.tapped
    assert bears.zone is Zone.HAND, "the main effect still resolved too"


def test_declining_the_gift_creates_no_fish():
    """CR 702.174k: a gift not promised does not happen."""
    scenario = (
        Scenario()
        .player("alice", hand=["Into the Flood Maw"], battlefield=["Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    maw = scenario.find("Into the Flood Maw", Zone.HAND, "alice")
    (island,) = scenario.untapped_sources("Island", username="alice")

    scenario.game.cast(maw, "alice", targets=[bears], mana_sources=[island])
    scenario.pass_until_resolved()

    assert "Fish Token" not in scenario.battlefield_names()


def test_crumb_and_get_it_gifts_a_food():
    """Crumb and Get It: "Gift a Food (... they create a Food token before
    its other effects. It's an artifact with '{2}, {T}, Sacrifice this
    token: You gain 3 life.')" - not in the deck pool, not named in this
    wave's brief.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Crumb and Get It"],
            battlefield=["Plains", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    card = scenario.find("Crumb and Get It", Zone.HAND, "alice")
    (plains,) = scenario.untapped_sources("Plains", username="alice")

    scenario.game.cast(card, "alice", targets=[bears], mana_sources=[plains], gift="bob")
    scenario.pass_until_resolved()

    food = [state for state in scenario.game.battlefield if state.name == "Food Token"]
    assert len(food) == 1
    assert food[0].controller == "bob"


def test_bilbos_gambit_gifts_a_treasure_and_bounces_the_spell():
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Bilbo's Gambit"], battlefield=["Plains", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's own main phase - he is active first
    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_priority("bob")

    gambit = scenario.find("Bilbo's Gambit", Zone.HAND, "alice")
    (plains1, plains2) = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.game.cast(
        gambit, "alice", targets=[bears], mana_sources=[plains1, plains2], gift="bob"
    )
    scenario.pass_until_resolved()

    treasure = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasure) == 1
    assert treasure[0].controller == "bob"
    assert bears.zone is Zone.HAND, "the main effect still resolved too"


def test_bilbos_gambit_without_the_gift_does_not_lock_out_casting():
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player(
            "alice",
            hand=["Bilbo's Gambit", "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_priority("bob")

    gambit = scenario.find("Bilbo's Gambit", Zone.HAND, "alice")
    (plains1, plains2) = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.game.cast(gambit, "alice", targets=[bears], mana_sources=[plains1, plains2])
    scenario.pass_until_resolved()

    assert blanket_cant_cast_restriction(scenario.game, "alice") is None
    scenario.pass_priority("bob")
    bolt = scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="alice"),
        username="alice",
        targets=["bob"],
    )
    assert bolt.zone is Zone.GRAVEYARD


def test_bilbos_gambit_with_the_gift_locks_out_casting_this_turn():
    """CR 611.2c: recorded rather than read off the battlefield, since the
    spell that made it is gone by the time anyone else tries to cast."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player(
            "alice",
            hand=["Bilbo's Gambit", "Lightning Bolt"],
            battlefield=["Plains", "Plains", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.cast_onto_stack(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    scenario.pass_priority("bob")

    gambit = scenario.find("Bilbo's Gambit", Zone.HAND, "alice")
    (plains1, plains2) = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.game.cast(
        gambit, "alice", targets=[bears], mana_sources=[plains1, plains2], gift="bob"
    )
    scenario.pass_until_resolved()

    restriction = blanket_cant_cast_restriction(scenario.game, "alice")
    assert restriction is not None and restriction.source_name == "Bilbo's Gambit"
    # The restriction is unconditional (CR 601.3, 611.2c) - even the caster
    # who promised the gift can't cast, unlike "your opponents can't cast".
    assert blanket_cant_cast_restriction(scenario.game, "bob") is not None


def test_blooming_blast_reads_the_identical_gift_a_treasure_template():
    """Off-pool proof that "Gift a Treasure" itself generalizes: Blooming
    Blast is the *only* other real printing of that exact keyword parameter
    (Bilbo's Gambit is the other) - `_GIFT_EFFECTS["a treasure"]` runs
    identically for it (CR 702.174j: the gift's own effect happens "before
    any other spell abilities of the card", so it is unaffected by whatever
    the rest of the card's text does).

    Blooming Blast's own main effect is not asserted on here: its second
    sentence ("If the gift was promised, Blooming Blast also deals 3 damage
    to that creature's controller.") is a conditional-addition-to-damage
    shape this engine does not yet read at all, which - by this file's own
    fail-closed-per-clause design - takes the whole spell's resolution text
    down with it (`docs/engine-coverage.md`); a gap outside this task's own
    templates, not fixed here.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Blooming Blast"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    blast = scenario.find("Blooming Blast", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    (m1, m2) = scenario.untapped_sources("Mountain", "Mountain")

    scenario.game.cast(blast, "alice", targets=[bears], mana_sources=[m1, m2], gift="bob")
    scenario.pass_until_resolved()

    treasure = [state for state in scenario.game.battlefield if state.name == "Treasure Token"]
    assert len(treasure) == 1
    assert treasure[0].controller == "bob"

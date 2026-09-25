"""Cast-record conditions: where a spell was cast from and what mana paid for
it - "you cast it from your hand", "you didn't cast it from your hand", "at
least four mana was spent to cast it", "the amount of mana spent ... was less
than its mana value", "at least three mana of the same color", "no colored
mana", "{C} wasn't spent", "three or more mana from creatures", "{S} of any
of that spell's colors".

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 601.2a** - casting moves the card from where it is to the stack: the
  zone it was cast from is a fact of the cast.
- **CR 601.2h** - the total cost is paid, and that is the mana "spent to cast
  it" - a reduction (delve) or life paid for a Phyrexian symbol (CR 107.4f)
  is not mana spent.
- **CR 106.3** - mana is produced by the source of the ability that made it:
  a creature's mana ability makes mana from a creature.
- **CR 107.4h** - "{S}" is one mana of any type from a snow source.
- **CR 105.2c** - colorless is not a color, so {C} is not colored mana.
- **CR 603.4** / **CR 608.2a** - checked as the event occurs and again on
  resolution; a fact of the cast does not change between the two, and the
  recheck reads the object the ability came from (**CR 113.7a**) even after
  it has left.
- **CR 707.10** - a copy of a spell isn't cast.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from tests.scenarios.harness import Scenario


def _board(alice, bob=None, *, hand=None, bob_hand=None, graveyard=None, library=None):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=alice,
            hand=hand or [],
            graveyard=graveyard or [],
            library=library or ["Plains"] * 6,
        )
        .player("bob", battlefield=bob or [], hand=bob_hand or [], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _triggers(scenario) -> list[str]:
    scenario.game.put_triggers_on_stack()
    return [name for name in scenario.stack_names() if name.endswith("triggered ability")]


def _no_trigger(scenario) -> None:
    """CR 603.4: the clause was read and false - no trigger, and no notice
    that it went unread."""
    assert _triggers(scenario) == []
    assert scenario.game.intervening_if_notices == []


# -- "you cast it from your hand" ---------------------------------------------


def _stoker_board(**kwargs):
    return _board(["Mountain"] * 4 + ["Island"], hand=["Coal Stoker", "Unsummon"], **kwargs)


def test_cast_from_hand_triggers_and_resolves():
    """Coal Stoker: "When this creature enters, if you cast it from your hand,
    add {R}{R}{R}." """
    scenario = _stoker_board()
    scenario.cast_and_resolve("Coal Stoker", *scenario.untapped_sources(*["Mountain"] * 4))
    assert _triggers(scenario) == ["Coal Stoker's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == 3


def test_put_onto_the_battlefield_is_not_cast_and_never_triggers():
    """CR 603.4: put onto the battlefield without being cast."""
    scenario = _stoker_board()
    scenario.put_onto_battlefield("Coal Stoker", "alice")
    _no_trigger(scenario)


def test_cast_from_hand_is_a_fact_that_survives_the_source_leaving():
    """CR 608.2a / CR 113.7a: Coal Stoker bounced in response - the recheck
    reads the object that was cast, and the mana is still added."""
    scenario = _stoker_board()
    scenario.cast_and_resolve("Coal Stoker", *scenario.untapped_sources(*["Mountain"] * 4))
    stoker = scenario.creature("Coal Stoker")
    scenario.cast_and_resolve("Unsummon", *scenario.untapped_sources("Island"), targets=[stoker])
    assert stoker.zone is Zone.HAND
    scenario.pass_until_resolved()
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == 3


def test_cast_from_hand_on_a_second_printing():
    """Furnace Dragon: "When this creature enters, if you cast it from your
    hand, exile all artifacts." - affinity pays most of it."""
    scenario = _board(
        ["Ornithopter"] * 6 + ["Mountain"] * 3, ["Mind Stone"], hand=["Furnace Dragon"]
    )
    scenario.cast_and_resolve("Furnace Dragon", *scenario.untapped_sources(*["Mountain"] * 3))
    assert _triggers(scenario) == ["Furnace Dragon's triggered ability"]
    scenario.pass_until_resolved()
    assert all(
        state.name != "Ornithopter" and state.name != "Mind Stone"
        for state in scenario.game.battlefield
    )


def test_cast_it_from_your_hand_asks_who_cast_the_entering_creature():
    """Wild Pair: "Whenever a creature enters, if you cast it from your
    hand, ..." - alice's own cast triggers it, bob's does not."""
    scenario = _board(
        ["Wild Pair", "Forest", "Forest"],
        ["Forest", "Forest"],
        hand=["Grizzly Bears"],
        bob_hand=["Grizzly Bears"],
    )
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    assert _triggers(scenario) == ["Wild Pair's triggered ability"]
    scenario.pass_until_resolved()


def test_an_opponents_cast_is_not_yours():
    scenario = _board(["Wild Pair"], ["Forest", "Forest"], bob_hand=["Grizzly Bears"])
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Grizzly Bears",
        *scenario.untapped_sources("Forest", "Forest", username="bob"),
        username="bob",
    )
    _no_trigger(scenario)


# -- "you didn't cast it from your hand" --------------------------------------


def test_didnt_cast_it_from_your_hand_is_true_for_a_creature_put_onto_the_battlefield():
    """Chainer, Nightmare Adept: "Whenever a nontoken creature you control
    enters, if you didn't cast it from your hand, it gains haste ..." """
    scenario = _board(["Chainer, Nightmare Adept", "Forest", "Forest"], hand=["Grizzly Bears"])
    scenario.put_onto_battlefield("Grizzly Bears", "alice")
    assert _triggers(scenario) == ["Chainer, Nightmare Adept's triggered ability"]


def test_didnt_cast_it_from_your_hand_is_false_for_one_cast_from_hand():
    scenario = _board(["Chainer, Nightmare Adept", "Forest", "Forest"], hand=["Grizzly Bears"])
    scenario.cast_and_resolve("Grizzly Bears", *scenario.untapped_sources("Forest", "Forest"))
    _no_trigger(scenario)


def test_didnt_cast_it_on_a_second_printing():
    """Phage the Untouchable: "When Phage enters, if you didn't cast it from
    your hand, you lose the game." """
    scenario = _board([], hand=["Phage the Untouchable"])
    scenario.put_onto_battlefield("Phage the Untouchable", "alice")
    assert _triggers(scenario) == ["Phage the Untouchable's triggered ability"]


# -- "at least N mana was spent to cast it" -----------------------------------


def _bomb_board(hand, lands):
    return _board(["Blazing Bomb", *lands], hand=hand)


def test_at_least_four_mana_triggers_on_a_five_mana_spell():
    """Blazing Bomb: "Whenever you cast a noncreature spell, if at least four
    mana was spent to cast it, put a +1/+1 counter on this creature." """
    scenario = _bomb_board(["Liliana's Contract"], ["Swamp"] * 5)
    scenario.cast_onto_stack("Liliana's Contract", *scenario.untapped_sources(*["Swamp"] * 5))
    assert "Blazing Bomb's triggered ability" in _triggers(scenario)
    scenario.pass_until_resolved()
    assert scenario.creature("Blazing Bomb").counter_count("+1/+1") == 1


def test_one_mana_is_not_four():
    """CR 603.4: Lightning Bolt spends one."""
    scenario = _bomb_board(["Lightning Bolt"], ["Mountain"])
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _no_trigger(scenario)


def test_mana_spent_is_not_mana_value():
    """CR 601.2h: Treasure Cruise (mana value 8) delved down to {U} spends one
    mana - not four."""
    scenario = _board(
        ["Blazing Bomb", "Island"],
        hand=["Treasure Cruise"],
        graveyard=["Plains"] * 7,
        library=["Plains"] * 6,
    )
    casting = scenario.cast("Treasure Cruise")
    graveyard = list(scenario.player("alice").graveyard)
    from magic_cards_model.machines.objects_as_costs import delve

    payment = casting.begin_paying()
    delve(payment, casting.spell, *graveyard[:7])
    scenario.pay_with(payment, *scenario.untapped_sources("Island"))
    scenario.put_on_stack(casting)
    _no_trigger(scenario)


def test_at_least_four_mana_on_a_second_printing():
    """Prompto Argentum: the same clause, making a Treasure."""
    scenario = _board(["Prompto Argentum", *["Swamp"] * 5], hand=["Liliana's Contract"])
    scenario.cast_onto_stack("Liliana's Contract", *scenario.untapped_sources(*["Swamp"] * 5))
    assert "Prompto Argentum's triggered ability" in _triggers(scenario)


# -- the amount spent compared with another value -----------------------------


def test_less_mana_spent_than_mana_value():
    """Tokka & Rahzar: "Whenever a player casts a spell, if the amount of mana
    spent to cast it was less than its mana value, Tokka & Rahzar deal 3
    damage to that player." - Gitaxian Probe paid with 2 life spends none."""
    scenario = _board(["Tokka & Rahzar, Terrible Twos"], hand=["Gitaxian Probe"])
    scenario.cast_onto_stack("Gitaxian Probe", auto=True, targets=["bob"])
    assert "Tokka & Rahzar, Terrible Twos's triggered ability" in _triggers(scenario)
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 20 - 2 - 3


def test_mana_value_fully_paid_is_not_less():
    scenario = _board(["Tokka & Rahzar, Terrible Twos", "Island"], hand=["Opt"])
    scenario.cast_onto_stack("Opt", *scenario.untapped_sources("Island"))
    _no_trigger(scenario)


def test_more_mana_spent_than_the_sources_power():
    """Liberator, Urza's Battlethopter (power 1): "if the amount of mana spent
    to cast that spell is greater than Liberator's power" - one mana is not
    greater than 1; three is."""
    scenario = _board(
        ["Liberator, Urza's Battlethopter", "Mountain", "Forest", "Forest", "Forest"],
        hand=["Lightning Bolt", "Cultivate"],
        library=["Forest"] * 6,
    )
    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    _no_trigger(scenario)
    scenario.pass_until_resolved()
    scenario.cast_onto_stack("Cultivate", *scenario.untapped_sources("Forest", "Forest", "Forest"))
    assert "Liberator, Urza's Battlethopter's triggered ability" in _triggers(scenario)


# -- colors of the mana spent -------------------------------------------------


def test_three_mana_of_the_same_color():
    """Clockwork Servant ({3}): "Adamant - When this creature enters, if at
    least three mana of the same color was spent to cast it, draw a card." """
    scenario = _board(["Mountain"] * 3, hand=["Clockwork Servant"])
    scenario.cast_and_resolve("Clockwork Servant", *scenario.untapped_sources(*["Mountain"] * 3))
    assert _triggers(scenario) == ["Clockwork Servant's triggered ability"]


def test_three_different_colors_are_not_three_of_one():
    scenario = _board(["Mountain", "Forest", "Plains"], hand=["Clockwork Servant"])
    scenario.cast_and_resolve(
        "Clockwork Servant", *scenario.untapped_sources("Mountain", "Forest", "Plains")
    )
    _no_trigger(scenario)


def test_no_colored_mana_spent_counters_it():
    """Void Mirror: "Whenever a player casts a spell, if no colored mana was
    spent to cast it, counter that spell." - Sol Ring paid with Wastes."""
    scenario = _board(["Void Mirror", "Wastes"], hand=["Sol Ring"])
    ring = scenario.cast_onto_stack("Sol Ring", *scenario.untapped_sources("Wastes"))
    assert _triggers(scenario) == ["Void Mirror's triggered ability"]
    scenario.pass_until_resolved()
    assert ring.zone is Zone.GRAVEYARD


def test_colored_mana_spent_is_not_countered():
    scenario = _board(["Void Mirror", "Mountain"], hand=["Sol Ring"])
    scenario.cast_onto_stack("Sol Ring", *scenario.untapped_sources("Mountain"))
    _no_trigger(scenario)


def test_no_mana_at_all_is_no_colored_mana():
    """Ornithopter costs {0}: no mana, so no colored mana (CR 105.2c)."""
    scenario = _board(["Void Mirror"], hand=["Ornithopter"])
    scenario.cast_onto_stack("Ornithopter")
    assert _triggers(scenario) == ["Void Mirror's triggered ability"]


def test_colorless_mana_wasnt_spent():
    """Wumpus Aberration: "When you cast this spell, if {C} wasn't spent to
    cast it, ..." - paid with Forests, it triggers; with Sol Ring's {C}{C},
    it does not."""
    scenario = _board(["Forest"] * 4, hand=["Wumpus Aberration"])
    scenario.cast_onto_stack("Wumpus Aberration", *scenario.untapped_sources(*["Forest"] * 4))
    assert _triggers(scenario) == ["Wumpus Aberration's triggered ability"]
    scenario = _board(["Sol Ring", "Forest", "Forest"], hand=["Wumpus Aberration"])
    scenario.cast_onto_stack(
        "Wumpus Aberration", *scenario.untapped_sources("Sol Ring", "Forest", "Forest")
    )
    _no_trigger(scenario)


# -- where the mana came from ---------------------------------------------------


def test_three_mana_from_creatures():
    """Inga and Esika: "Whenever you cast a creature spell, if three or more
    mana from creatures was spent to cast it, draw a card." (CR 106.3)."""
    scenario = _board(
        ["Inga and Esika", "Llanowar Elves", "Elvish Mystic", "Llanowar Elves"] + ["Forest"] * 3,
        hand=["Colossal Dreadmaw"],
    )
    scenario.cast_onto_stack(
        "Colossal Dreadmaw",
        *scenario.untapped_sources("Llanowar Elves", "Elvish Mystic", "Llanowar Elves"),
        *scenario.untapped_sources("Forest", "Forest", "Forest"),
    )
    assert "Inga and Esika's triggered ability" in _triggers(scenario)


def test_two_mana_from_creatures_is_not_three():
    scenario = _board(
        ["Inga and Esika", "Llanowar Elves", "Elvish Mystic", "Forest", "Forest"],
        hand=["Grizzly Bears"],
    )
    scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Llanowar Elves", "Elvish Mystic")
    )
    _no_trigger(scenario)


def test_snow_mana_of_the_spells_color():
    """Boreal Outrider: "Whenever you cast a creature spell, if {S} of any of
    that spell's colors was spent to cast it, ..." (CR 107.4h) - green from a
    Snow-Covered Forest on a green spell."""
    scenario = _board(["Boreal Outrider", "Snow-Covered Forest", "Forest"], hand=["Grizzly Bears"])
    scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Snow-Covered Forest", "Forest")
    )
    assert _triggers(scenario) == ["Boreal Outrider's triggered ability"]


def test_snow_mana_of_another_color_does_not_count():
    """Blue snow mana spent on a green spell's generic is not "of any of that
    spell's colors"."""
    scenario = _board(["Boreal Outrider", "Snow-Covered Island", "Forest"], hand=["Grizzly Bears"])
    scenario.cast_onto_stack(
        "Grizzly Bears", *scenario.untapped_sources("Snow-Covered Island", "Forest")
    )
    _no_trigger(scenario)


# -- "he was cast" --------------------------------------------------------------


def test_he_was_cast():
    """Anti-Venom, Horrifying Healer: "When Anti-Venom enters, if he was cast,
    ..." - cast, it triggers; put onto the battlefield, it does not."""
    scenario = _board(
        ["Plains"] * 5, hand=["Anti-Venom, Horrifying Healer"], graveyard=["Grizzly Bears"]
    )
    scenario.cast_and_resolve(
        "Anti-Venom, Horrifying Healer", *scenario.untapped_sources(*["Plains"] * 5)
    )
    assert _triggers(scenario) == ["Anti-Venom, Horrifying Healer's triggered ability"]
    scenario = _board([], hand=["Anti-Venom, Horrifying Healer"])
    scenario.put_onto_battlefield("Anti-Venom, Horrifying Healer", "alice")
    _no_trigger(scenario)

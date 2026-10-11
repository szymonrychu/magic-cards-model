"""EP-01 R2 T4: a spell's own "Cast this spell only if ..." / "You can't cast ~
unless ..." / "... during your first, second, or third turns of the game"
restrictions (CR 601.2e, CR 601.3, CR 101.2), and turn- or state-gated static
prohibitions: "During your turn, your opponents can't cast spells or activate
abilities of artifacts, creatures, or enchantments." (Grand Abolisher, Myrel),
"As long as this creature is attacking, defending player can't cast spells."
(Wardscale Dragon), "Players can cast spells only during their own turns."
(Dosan), "Players can't activate planeswalkers' loyalty abilities." (The
Immortal Sun), "Each opponent who cast a spell this turn can't attack with
creatures." / "... who attacked ... can't cast spells." (Angelic Arbiter),
"Each opponent who controls more creatures than you can't cast creature
spells. The same is true for artifacts and enchantments." and "... can't play
lands." (Ward of Bones) and "Each player who has cast a nonartifact spell this
turn can't cast additional nonartifact spells." (Ethersworn Canonist).

A legal announcement leaves the spell on the stack, so every question gets its
own freshly built board.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

BOLT = "Lightning Bolt"
LANDS = ["Island"] * 3 + ["Mountain"] * 3 + ["Swamp"] * 3 + ["Forest"] * 3 + ["Plains"] * 3


def _scenario(
    *,
    alice=(),
    bob=(),
    alice_hand=(),
    bob_hand=(),
    alice_gy=(),
    bob_gy=(),
    first="alice",
    step=Step.PRECOMBAT_MAIN,
):
    players = {
        "alice": dict(
            battlefield=[*alice, *LANDS], hand=list(alice_hand), graveyard=list(alice_gy)
        ),
        "bob": dict(battlefield=[*bob, *LANDS], hand=list(bob_hand), graveyard=list(bob_gy)),
    }
    scenario = Scenario().manual_turn_based_actions()
    order = [first, "bob" if first == "alice" else "alice"]
    for name in order:
        scenario = scenario.player(name, library=["Island"] * 5, **players[name])
    played = scenario.build()
    played.start_at(step)
    return played


def _try(world, spell, user="alice", from_zone=Zone.HAND, **kwargs):
    """Refusal of `user` casting `spell` in a freshly built `world()`."""
    scenario = world()
    if callable(kwargs.get("targets")):
        kwargs["targets"] = kwargs["targets"](scenario)
    try:
        scenario.cast(spell, username=user, from_zone=from_zone, **kwargs)
    except ValueError as error:
        return str(error)
    return None


def _cast_first(scenario, spell, user="alice", **kwargs):
    """Cast and resolve `spell` so "this turn" histories have an entry."""
    sources = scenario.untapped_sources("Mountain", "Mountain", "Island", username=user)
    scenario.cast_and_resolve(spell, *sources, username=user, **kwargs)


# -- Cast this spell only if ... -------------------------------------------


def test_cast_only_if_you_have_cast_another_spell_this_turn():
    for card in ("Hewed Stone Retainers", "Illusory Angel"):

        def before(card=card):
            return _scenario(alice_hand=[card, BOLT])

        def after(card=card):
            scenario = _scenario(alice_hand=[card, BOLT])
            _cast_first(scenario, BOLT, targets=["bob"])
            return scenario

        refusal = _try(before, card)
        assert refusal is not None and "another spell" in refusal
        assert _try(after, card) is None


def test_cast_only_if_another_green_spell_was_cast_wants_the_colour():
    def with_spell(spell):
        def build():
            scenario = _scenario(
                alice=["Llanowar Elves"], alice_hand=["Talara's Battalion", spell, "Giant Growth"]
            )
            if spell:
                creature = scenario.creature("Llanowar Elves", "alice")
                sources = scenario.untapped_sources("Forest", username="alice")
                scenario.cast_and_resolve(spell, *sources, username="alice", targets=[creature])
            return scenario

        return build

    assert _try(with_spell("Giant Growth"), "Talara's Battalion") is None

    # a red spell is another spell, but not a green one
    def red_first():
        scenario = _scenario(alice_hand=["Talara's Battalion", BOLT])
        _cast_first(scenario, BOLT, targets=["bob"])
        return scenario

    assert _try(red_first, "Talara's Battalion") is not None


def test_a_creature_must_have_died_this_turn():
    def before():
        return _scenario(alice_hand=["Grim Wanderer", BOLT], bob=["Grizzly Bears"])

    def after():
        scenario = _scenario(alice_hand=["Grim Wanderer", BOLT], bob=["Grizzly Bears"])
        _cast_first(scenario, BOLT, targets=[scenario.creature("Grizzly Bears", "bob")])
        return scenario

    assert _try(before, "Grim Wanderer") is not None
    assert _try(after, "Grim Wanderer") is None


def test_threshold_gate_counts_the_graveyard():
    def world(count):
        return lambda: _scenario(
            alice_hand=["Proft, Sinister Mastermind"], alice_gy=["Island"] * count
        )

    assert _try(world(6), "Proft, Sinister Mastermind") is not None
    assert _try(world(7), "Proft, Sinister Mastermind") is None


def test_a_self_named_unless_gate_reads_an_opponent_losing_life():
    def before():
        return _scenario(alice_hand=["Rakdos, Lord of Riots", BOLT])

    def after():
        scenario = _scenario(alice_hand=["Rakdos, Lord of Riots", BOLT])
        _cast_first(scenario, BOLT, targets=["bob"])
        return scenario

    assert _try(before, "Rakdos, Lord of Riots") is not None
    assert _try(after, "Rakdos, Lord of Riots") is None


def _giant_world(lost, *, owner="alice"):
    """alice controls Rakdos (so its discount applies to her creature spells)
    and holds a Hill Giant ({3}{R}); bob has lost `lost` life this turn."""
    scenario = _scenario(alice=["Rakdos, Lord of Riots"], alice_hand=["Hill Giant", "Shock"])
    if lost:
        scenario.game.lose_life("bob", lost)
    return scenario


@pytest.mark.parametrize(("lost", "mana"), [(0, 4), (1, 3), (2, 2), (3, 1), (6, 1)])
def test_creature_spells_cost_one_less_for_each_life_the_opponents_lost(lost, mana):
    """Hill Giant {3}{R} costs {1} less per life lost, the {R} staying: exactly
    `mana` sources pay for it, and one fewer is refused."""
    scenario = _giant_world(lost)
    scenario.cast_onto_stack(
        "Hill Giant",
        *scenario.untapped_sources(*(["Mountain", "Island", "Swamp", "Forest"])[:mana]),
    )
    assert scenario.stack_names() == ["Hill Giant"]
    if mana > 1:
        short = _giant_world(lost)
        with pytest.raises(ValueError):
            short.cast_onto_stack(
                "Hill Giant",
                *short.untapped_sources(*(["Mountain", "Island", "Swamp"])[: mana - 1]),
            )


def test_the_life_discount_counts_only_what_the_opponents_lost():
    scenario = _giant_world(1)
    scenario.game.lose_life("alice", 4)  # her own life loss is not counted
    with pytest.raises(ValueError):
        scenario.cast_onto_stack("Hill Giant", *scenario.untapped_sources("Mountain", "Island"))


def test_the_life_discount_ends_with_the_source_and_is_not_the_opponents():
    gone = _giant_world(3)
    gone.game.exile_permanent(gone.find("Rakdos, Lord of Riots", Zone.BATTLEFIELD, "alice"))
    with pytest.raises(ValueError):
        gone.cast_onto_stack("Hill Giant", *gone.untapped_sources("Mountain"))
    # bob's creature spells are not discounted by alice's Rakdos
    scenario = _scenario(alice=["Rakdos, Lord of Riots"], bob_hand=["Hill Giant"], first="bob")
    scenario.game.lose_life("bob", 3)
    with pytest.raises(ValueError):
        scenario.cast_onto_stack(
            "Hill Giant", *scenario.untapped_sources("Mountain", username="bob"), username="bob"
        )


def test_the_life_discount_does_not_touch_noncreature_spells():
    scenario = _giant_world(3)
    scenario.cast_onto_stack("Shock", *scenario.untapped_sources("Mountain"), targets=["bob"])


def test_feast_of_blood_cast_only_if_two_vampires():
    def world(vampires):
        return lambda: _scenario(
            alice=["Vampire Nighthawk"] * vampires,
            alice_hand=["Feast of Blood"],
            bob=["Grizzly Bears"],
        )

    bears = {"targets": lambda scenario: [scenario.creature("Grizzly Bears", "bob")]}
    refusal = _try(world(1), "Feast of Blood", **bears)
    assert refusal is not None and "Vampires" in refusal
    assert _try(world(2), "Feast of Blood", **bears) is None


@pytest.mark.parametrize(
    ("spell", "turns_taken", "allowed"),
    [
        ("Serra Avenger", 1, False),
        ("Serra Avenger", 3, False),
        ("Serra Avenger", 4, True),
        ("Spider-Man 2099", 2, False),
        ("Spider-Man 2099", 4, True),
    ],
)
def test_you_cant_cast_it_during_your_first_second_or_third_turns(spell, turns_taken, allowed):
    def world():
        scenario = _scenario(alice_hand=[spell])
        scenario.game.turn.turns_taken_by["alice"] = turns_taken
        return scenario

    assert (_try(world, spell) is None) is allowed


# -- During your turn, your opponents can't cast spells or activate ... ----


@pytest.mark.parametrize("source", ["Grand Abolisher", "Myrel, Shield of Argive"])
def test_during_your_turn_opponents_cant_cast_or_activate(source):
    def world():
        return _scenario(alice=[source], bob=["Llanowar Elves"], bob_hand=[BOLT, "Brainstorm"])

    refusal = _try(world, BOLT, "bob", targets=["alice"])
    assert refusal is not None and source in refusal
    scenario = world()
    elves = scenario.creature("Llanowar Elves", "bob")
    reason = scenario.why_cannot_activate(elves, 0, username="bob")
    assert reason is not None and source in reason

    # the controller is unaffected
    def mine():
        return _scenario(alice=[source], alice_hand=[BOLT])

    assert _try(mine, BOLT, "alice", targets=["bob"]) is None


def test_the_abolisher_ban_only_covers_its_controllers_turn():
    def world():
        return _scenario(bob=["Grand Abolisher"], alice_hand=[BOLT], alice=["Llanowar Elves"])

    # it is alice's turn, so Abolisher (bob's) is idle
    assert _try(world, BOLT, "alice", targets=["bob"]) is None
    scenario = world()
    elves = scenario.creature("Llanowar Elves", "alice")
    assert scenario.why_cannot_activate(elves, 0, username="alice") is None


def test_the_abolisher_ban_leaves_with_its_source():
    scenario = _scenario(alice=["Grand Abolisher"], bob_hand=[BOLT])
    scenario.game.exile_permanent(scenario.creature("Grand Abolisher", "alice"))
    scenario.cast(BOLT, username="bob", targets=["alice"])


# -- Wardscale Dragon ----------------------------------------------------


def test_defending_player_cant_cast_while_the_dragon_attacks():
    def attacking():
        scenario = _scenario(alice=["Wardscale Dragon"], bob_hand=[BOLT])
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(scenario.creature("Wardscale Dragon", "alice"), defending="bob")
        return scenario

    refusal = _try(attacking, BOLT, "bob", targets=["alice"])
    assert refusal is not None and "Wardscale Dragon" in refusal

    def idle():
        return _scenario(alice=["Wardscale Dragon"], bob_hand=[BOLT])

    assert _try(idle, BOLT, "bob", targets=["alice"]) is None


# -- Dosan ------------------------------------------------------------------


def test_players_can_cast_only_during_their_own_turns():
    def world():
        return _scenario(alice=["Dosan the Falling Leaf"], alice_hand=[BOLT], bob_hand=[BOLT])

    assert _try(world, BOLT, "bob", targets=["alice"]) is not None
    assert _try(world, BOLT, "alice", targets=["bob"]) is None

    def bobs_turn():
        scenario = _scenario(
            alice=["Dosan the Falling Leaf"], alice_hand=[BOLT], bob_hand=[BOLT], first="bob"
        )
        return scenario

    assert _try(bobs_turn, BOLT, "alice", targets=["bob"]) is not None
    assert _try(bobs_turn, BOLT, "bob", targets=["alice"]) is None


# -- The Immortal Sun --------------------------------------------------------


def test_nobody_can_activate_loyalty_abilities():
    def world():
        return _scenario(alice=["The Immortal Sun", "Jace Beleren"], bob=["Liliana of the Veil"])

    scenario = world()
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "alice")
    reason = scenario.why_cannot_activate(jace, 0, username="alice")
    assert reason is not None and "The Immortal Sun" in reason
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    assert scenario.why_cannot_activate(liliana, 0, username="bob") is not None

    free = _scenario(alice=["Jace Beleren"])
    assert (
        free.why_cannot_activate(
            free.find("Jace Beleren", Zone.BATTLEFIELD, "alice"), 0, username="alice"
        )
        is None
    )


# -- Angelic Arbiter -----------------------------------------------------------


def test_an_opponent_who_cast_a_spell_cant_attack():
    # bob controls the Arbiter; it is alice's turn
    def world():
        return _scenario(alice=["Grizzly Bears"], alice_hand=[BOLT], bob=["Angelic Arbiter"])

    scenario = world()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")

    cast_first = world()
    _cast_first(cast_first, BOLT, targets=["bob"])
    cast_first.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError, match="Angelic Arbiter"):
        cast_first.attack_with(cast_first.creature("Grizzly Bears", "alice"), defending="bob")


def test_an_opponent_who_attacked_cant_cast_spells():
    def world():
        scenario = _scenario(alice=["Grizzly Bears"], alice_hand=[BOLT], bob=["Angelic Arbiter"])
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")
        return scenario

    refusal = _try(world, BOLT, "alice", targets=["bob"])
    assert refusal is not None and "Angelic Arbiter" in refusal

    # the Arbiter's controller is not its own opponent
    def mine():
        scenario = _scenario(
            alice=["Angelic Arbiter", "Grizzly Bears"], alice_hand=[BOLT], bob=["Memnite"]
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(scenario.creature("Grizzly Bears", "alice"), defending="bob")
        return scenario

    assert _try(mine, BOLT, "alice", targets=["bob"]) is None


# -- Ward of Bones ---------------------------------------------------------------


def test_an_opponent_with_more_creatures_cant_cast_creature_artifact_or_enchantment_spells():
    def world(extra=0):
        return lambda: _scenario(
            alice=["Ward of Bones"],
            bob=["Grizzly Bears"] * (1 + extra),
            bob_hand=["Hill Giant", "Ornithopter", "Pacifism", BOLT],
            first="bob",
        )

    assert _try(world(), "Hill Giant", "bob") is not None
    assert _try(world(), BOLT, "bob", targets=["alice"]) is None
    # alice controls as many creatures: no longer "more"
    equal = lambda: _scenario(  # noqa: E731
        alice=["Ward of Bones", "Grizzly Bears"],
        bob=["Grizzly Bears"],
        bob_hand=["Hill Giant"],
        first="bob",
    )
    assert _try(equal, "Hill Giant", "bob") is None


def test_the_same_is_true_for_artifacts_and_enchantments():
    def world():
        return _scenario(
            alice=["Ward of Bones", "Ornithopter", "Pacifism"],
            bob=["Ornithopter", "Ornithopter", "Pacifism", "Pacifism"],
            bob_hand=["Ornithopter", "Pacifism"],
            first="bob",
        )

    assert _try(world, "Ornithopter", "bob") is not None
    assert _try(world, "Pacifism", "bob", targets=["alice"]) is not None


def test_an_opponent_with_more_lands_cant_play_lands():
    def world(bob_extra):
        scenario = _scenario(
            alice=["Ward of Bones"], bob=["Plains"] * bob_extra, bob_hand=["Plains"], first="bob"
        )
        return scenario

    behind = world(0)
    reason = behind.game.why_cannot_play_land("bob")
    assert reason is None  # equal lands is not "more"
    ahead = world(2)
    reason = ahead.game.why_cannot_play_land("bob")
    assert reason is not None and "Ward of Bones" in reason


# -- Ethersworn Canonist --------------------------------------------------------------


def test_a_player_who_cast_a_nonartifact_spell_cant_cast_more():
    def world():
        scenario = _scenario(
            alice=["Ethersworn Canonist"], alice_hand=[BOLT, "Shock", "Ornithopter"]
        )
        _cast_first(scenario, BOLT, targets=["bob"])
        return scenario

    refusal = _try(world, "Shock", "alice", targets=["bob"])
    assert refusal is not None and "Ethersworn Canonist" in refusal
    # an artifact spell is not a nonartifact spell
    assert _try(world, "Ornithopter", "alice") is None

    def fresh():
        return _scenario(alice=["Ethersworn Canonist"], alice_hand=[BOLT, "Shock"])

    assert _try(fresh, "Shock", "alice", targets=["bob"]) is None

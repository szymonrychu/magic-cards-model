"""EP-01 R1 T4: a creature's own "can't attack [or block] unless <condition>"
(CR 508.1c, 509.1b), "can't attack [or block] alone" (CR 506.5),
"can't attack unless a creature with greater power also attacks" and
"attacks each combat if able unless <condition>" (CR 508.1d).

Every restriction is proven both ways - refused while the condition fails,
allowed once it holds - on the printed card. "Defending player ..." is judged
against the player (or planeswalker controller) actually being attacked.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _try(
    creature: str,
    action: str = "attack",
    *,
    mine=(),
    theirs=(),
    hand=(),
    their_hand=(),
    graveyard=(),
    their_graveyard=(),
    prep=None,
):
    """Whether `creature` may `action` (attack alice's opponent, or block a
    Hill Giant). Returns the refusal text, or None when it is legal."""
    if action == "attack":
        alice = [creature, *mine]
        bob = [*theirs]
        sides = (hand, graveyard, their_hand, their_graveyard)
    else:
        # The blocker's controller is "you": swap the two sides' kwargs.
        alice = ["Hill Giant", *theirs]
        bob = [creature, *mine]
        sides = (their_hand, their_graveyard, hand, graveyard)
    alice_hand, alice_gy, bob_hand, bob_gy = sides
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, hand=list(alice_hand), graveyard=list(alice_gy))
        .player("bob", battlefield=bob, hand=list(bob_hand), graveyard=list(bob_gy))
        .build()
    )
    if prep is not None:
        prep(scenario)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    try:
        if action == "attack":
            scenario.attack_with(scenario.creature(creature, "alice"), defending="bob")
        else:
            giant = scenario.creature("Hill Giant", "alice")
            scenario.attack_with(giant, defending="bob")
            scenario.block(giant, scenario.creature(creature, "bob"))
    except ValueError as error:
        return str(error)
    return None


def _poison(scenario) -> None:
    scenario.player("bob").add_counters(Counter.POISON, 1)


def _damage(scenario) -> None:
    scenario.game.deal_damage(scenario.player("bob"), 1)


def _blessing(scenario) -> None:
    scenario.state_based_actions()


def _speed(scenario) -> None:
    scenario.player("alice").speed = 4


def _counters(count: int):
    def prep(scenario):
        scenario.creature(prep.creature, "alice").add_counters(Counter.PLUS_ONE, count)

    return prep


# attacker, extra kwargs when the condition HOLDS
DEFENDING_PLAYER = [
    ("Ethereal Whiskergill", dict(theirs=["Island"])),
    ("Serpent of the Endless Sea", dict(theirs=["Island"])),
    ("Slipstream Serpent", dict(theirs=["Island"])),
    ("Bog Serpent", dict(theirs=["Swamp"])),
    ("Ronom Serpent", dict(theirs=["Snow-Covered Island"])),
    ("Whimwader", dict(theirs=["Dandân"])),
    ("Godhunter Octopus", dict(theirs=["Arrest"])),
    ("Chained Throatseeker", dict(prep=_poison)),
    ("Vantress Gargoyle", dict(their_graveyard=["Island"] * 7)),
    ("Bloodcrazed Goblin", dict(prep=_damage)),
]


@pytest.mark.parametrize(("creature", "holds"), DEFENDING_PLAYER)
def test_defending_player_conditions(creature: str, holds: dict) -> None:
    refusal = _try(creature)
    assert refusal is not None and "can't attack" in refusal and "CR 508.1c" in refusal
    assert _try(creature, **holds) is None


def test_the_defending_player_is_the_one_attacked_not_the_controller() -> None:
    """Island on the attacker's own side doesn't satisfy "defending player
    controls an Island" (Ethereal Whiskergill)."""
    assert _try("Ethereal Whiskergill", mine=["Island"]) is not None
    assert _try("Whimwader", theirs=["Island"]) is not None
    assert _try("Ronom Serpent", theirs=["Island"]) is not None
    assert _try("Vantress Gargoyle", their_graveyard=["Island"] * 6) is not None
    assert _try("Vantress Gargoyle", graveyard=["Island"] * 7) is not None


def test_attacking_a_planeswalker_asks_its_controller() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ethereal Whiskergill"])
        .player("bob", battlefield=["Island", "Kaito, Bane of Nightmares"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    walker = scenario.find("Kaito, Bane of Nightmares", Zone.BATTLEFIELD, "bob")
    scenario.attack_with(scenario.creature("Ethereal Whiskergill"), defending=walker)


YOUR_CONDITIONS = [
    # creature, action, kwargs when it HOLDS
    ("Hazoret the Fervent", "attack", dict()),
    ("Hazoret the Fervent", "block", dict()),
    ("Kefnet the Mindful", "attack", dict(hand=["Island"] * 7)),
    ("Kefnet the Mindful", "block", dict(hand=["Island"] * 7)),
    ("Hazoret, Godseeker", "attack", dict(prep=_speed)),
    ("Wayward Swordtooth", "attack", dict(mine=["Island"] * 10, prep=_blessing)),
    ("Tiger-Dillo", "attack", dict(mine=["Serra Angel"])),
    ("Tiger-Dillo", "block", dict(mine=["Serra Angel"])),
    ("Warden of the Chained", "attack", dict(mine=["Serra Angel"])),
    ("Rhonas the Indomitable", "attack", dict(mine=["Serra Angel"])),
    ("Oketra the True", "attack", dict(mine=["Memnite"] * 3)),
    ("Lupine Prototype", "attack", dict(their_hand=[])),
    ("Relic Golem", "attack", dict(their_graveyard=["Island"] * 8)),
    ("Relic Golem", "block", dict(their_graveyard=["Island"] * 8)),
    ("Harbor Serpent", "attack", dict(mine=["Island"] * 3, theirs=["Island"] * 2)),
    (
        "Patchwork Beastie",
        "attack",
        dict(graveyard=["Island", "Grizzly Bears", "Lightning Bolt", "Sol Ring"]),
    ),
    ("Training Drone", "attack", dict(mine=["Prowler's Helm"], prep="equip")),
    ("Lovestruck Beast", "attack", dict(mine=["Memnite"])),
]


def _equip(scenario) -> None:
    scenario.find("Prowler's Helm", Zone.BATTLEFIELD, "alice").attach_to(
        scenario.creature("Training Drone", "alice")
    )


def _holds(kwargs: dict) -> dict:
    return {**kwargs, "prep": _equip} if kwargs.get("prep") == "equip" else kwargs


FAILING = {
    # what each fails with (the conditions above are not met on an empty board)
    "Hazoret the Fervent": dict(hand=["Island", "Island"]),
    "Lupine Prototype": dict(hand=["Island"], their_hand=["Island"]),
}


@pytest.mark.parametrize(("creature", "action", "holds"), YOUR_CONDITIONS)
def test_your_conditions(creature: str, action: str, holds: dict) -> None:
    failing = FAILING.get(creature, {})
    refusal = _try(creature, action, **failing)
    assert refusal is not None and f"can't {action}" in refusal
    assert _try(creature, action, **_holds(holds)) is None


def test_cards_in_hand_boundary() -> None:
    """Hazoret the Fervent: one or fewer; Kefnet: seven or more."""
    assert _try("Hazoret the Fervent", hand=["Island"]) is None
    assert _try("Hazoret the Fervent", hand=["Island", "Island"]) is not None
    assert _try("Kefnet the Mindful", hand=["Island"] * 6) is not None
    assert _try("Kefnet the Mindful", hand=["Island"] * 7) is None


def test_another_means_not_itself() -> None:
    """Rhonas is 5/5 but "another creature with power 4 or greater" is not him."""
    assert _try("Rhonas the Indomitable", mine=["Grizzly Bears"]) is not None
    assert _try("Oketra the True", mine=["Memnite"] * 2) is not None


def test_a_card_with_a_1_1_creature_rider_needs_a_1_1() -> None:
    assert _try("Lovestruck Beast", mine=["Grizzly Bears"]) is not None
    assert _try("Lovestruck Beast", mine=["Memnite"]) is None


def test_even_number_of_counters_sab_sunen() -> None:
    def counters(n: int):
        def prep(scenario):
            scenario.creature("Sab-Sunen, Luxa Embodied", "alice").add_counters(Counter.PLUS_ONE, n)

        return prep

    assert _try("Sab-Sunen, Luxa Embodied", prep=counters(1)) is not None
    assert _try("Sab-Sunen, Luxa Embodied", prep=counters(2)) is None
    assert _try("Sab-Sunen, Luxa Embodied") is None
    assert _try("Sab-Sunen, Luxa Embodied", "block", prep=None) is None


def test_five_or_more_counters_slumbering_dragon() -> None:
    def counters(n: int):
        def prep(scenario):
            scenario.creature("Slumbering Dragon", "alice").add_counters(Counter.PLUS_ONE, n)

        return prep

    assert _try("Slumbering Dragon", prep=counters(4)) is not None
    assert _try("Slumbering Dragon", prep=counters(5)) is None


def test_a_creature_died_under_your_control_this_turn() -> None:
    """Bontu the Glorified: after your Bears die to a Bolt."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Bontu the Glorified", "Grizzly Bears", "Mountain"],
            hand=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bontu = scenario.creature("Bontu the Glorified", "alice")
    assert scenario.can_attack(bontu, defending="bob") is False
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        targets=[scenario.creature("Grizzly Bears", "alice")],
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bontu, defending="bob")


def test_you_have_cast_a_spell_this_turn() -> None:
    """Goblin Cohort wants a creature spell; Silburlind Snapper a noncreature one."""
    for creature, spell, _lands, other in (
        ("Goblin Cohort", "Grizzly Bears", ["Forest", "Forest"], "Sol Ring"),
        ("Silburlind Snapper", "Sol Ring", ["Mountain"], "Grizzly Bears"),
    ):
        for cast, expect_legal in ((spell, True), (other, False)):
            cost_lands = ["Forest", "Forest", "Mountain", "Mountain"]
            scenario = (
                Scenario()
                .manual_turn_based_actions()
                .player("alice", battlefield=[creature, *cost_lands], hand=[cast])
                .player("bob")
                .build()
            )
            scenario.start_at(Step.PRECOMBAT_MAIN)
            scenario.cast_and_resolve(
                cast, *scenario.untapped_sources(*cost_lands[: 2 if cast == "Grizzly Bears" else 1])
            )
            scenario.start_at(Step.DECLARE_ATTACKERS)
            attacker = scenario.creature(creature, "alice")
            assert scenario.can_attack(attacker, defending="bob") is expect_legal, (creature, cast)


@pytest.mark.parametrize(
    "creature",
    ["Bonded Construct", "Militia Rallier", "Raging Kronch", "Trusty Companion"],
)
def test_cant_attack_alone(creature: str) -> None:
    scenario = Scenario().player("alice", battlefield=[creature, "Memnite"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    me = scenario.creature(creature, "alice")
    with pytest.raises(ValueError, match="alone"):
        scenario.attack_with(me)
    scenario.attack_with(me, scenario.creature("Memnite", "alice"))


@pytest.mark.parametrize(
    "creature",
    ["Bonded Horncrest", "Ember Beast", "Jackal Familiar", "Loyal Pegasus", "Mogg Flunkies"],
)
def test_cant_attack_or_block_alone(creature: str) -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=[creature, "Memnite"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    me = scenario.creature(creature, "alice")
    with pytest.raises(ValueError, match="alone"):
        scenario.attack_with(me)
    scenario.attack_with(me, scenario.creature("Memnite", "alice"))

    blocking = (
        Scenario()
        .player("alice", battlefield=["Hill Giant"])
        .player("bob", battlefield=[creature, "Memnite"])
        .build()
    )
    blocking.start_at(Step.DECLARE_ATTACKERS)
    angel = blocking.creature("Hill Giant", "alice")
    blocking.attack_with(angel, defending="bob")
    with pytest.raises(ValueError, match="alone"):
        blocking.block(angel, blocking.creature(creature, "bob"))
    blocking.block(angel, blocking.creature(creature, "bob"), blocking.creature("Memnite", "bob"))


def test_okk_needs_a_creature_with_greater_power_attacking_too() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Okk", "Grizzly Bears", "Ghalta, Primal Hunger"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    okk = scenario.creature("Okk", "alice")
    with pytest.raises(ValueError, match="greater power"):
        scenario.attack_with(okk)
    with pytest.raises(ValueError, match="greater power"):
        scenario.attack_with(okk, scenario.creature("Grizzly Bears", "alice"))
    scenario.attack_with(okk, scenario.creature("Ghalta, Primal Hunger", "alice"))


def test_okk_blocks_only_beside_a_creature_with_greater_power() -> None:
    def blocks(*others: str):
        scenario = (
            Scenario()
            .player("alice", battlefield=["Hill Giant"])
            .player("bob", battlefield=["Okk", *others])
            .build()
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        angel = scenario.creature("Hill Giant", "alice")
        scenario.attack_with(angel, defending="bob")
        try:
            scenario.block(
                angel,
                scenario.creature("Okk", "bob"),
                *[scenario.creature(n, "bob") for n in others],
            )
        except ValueError as error:
            return str(error)
        return None

    assert blocks() is not None
    assert blocks("Grizzly Bears") is not None
    assert blocks("Ghalta, Primal Hunger") is None


def test_attacks_each_combat_unless_you_control_the_named_creature() -> None:
    def declare_nothing(*, mine=()):
        scenario = (
            Scenario()
            .player("alice", battlefield=["Marauding Maulhorn", *mine])
            .player("bob")
            .build()
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        try:
            scenario.attack_with()
        except ValueError as error:
            return str(error)
        return None

    refusal = declare_nothing()
    assert refusal is not None and "CR 508.1d" in refusal
    assert declare_nothing(mine=["Advocate of the Beast"]) is None


def test_attacks_each_combat_unless_you_control_another_ally() -> None:
    def declare_nothing(*, mine=()):
        scenario = (
            Scenario().player("alice", battlefield=["Reckless Cohort", *mine]).player("bob").build()
        )
        scenario.start_at(Step.DECLARE_ATTACKERS)
        try:
            scenario.attack_with()
        except ValueError as error:
            return str(error)
        return None

    assert declare_nothing() is not None
    assert declare_nothing(mine=["Reckless Cohort"]) is None


def test_lambholt_pacifist_needs_a_creature_with_power_four_or_greater() -> None:
    assert _try("Lambholt Pacifist") is not None
    assert _try("Lambholt Pacifist", mine=["Hill Giant"]) is not None
    assert _try("Lambholt Pacifist", mine=["Craw Wurm"]) is None


LESSONS = ["Airbending Lesson", "Firebending Lesson", "Boomerang Basics"]


@pytest.mark.parametrize("action", ["attack", "block"])
def test_the_lion_turtle_needs_three_lessons_in_your_graveyard(action: str) -> None:
    assert _try("The Lion-Turtle", action) is not None
    assert _try("The Lion-Turtle", action, graveyard=LESSONS[:2]) is not None
    assert _try("The Lion-Turtle", action, graveyard=LESSONS) is None

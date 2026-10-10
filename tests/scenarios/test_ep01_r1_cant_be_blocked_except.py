"""EP-01 R1 T4: "can't be blocked except by <quality>" and its group and
power-comparison cousins (CR 509.1b: a restriction on what may block, created
by an evasion ability; CR 509.1a/509.1b: the declaration is illegal if a
restriction is disobeyed).

One scenario per shape, a legal blocker and an illegal blocker for each:

- "except by three or more creatures" (Guile, Pathrazer of Ulamog, Troll of
  Khazad-dum, Underworld Cerberus ...) - a whole-declaration restriction
- "except by <type/colour/quality list>" (Deathcult Rogue, Dread Warlock,
  Amrou Seekers, Elven Riders, Orchard Spirit, The Balrog ...)
- "can't be blocked by <description>" (Kor Castigator, Rubblebelt Runner,
  Temple Thief, Demolition Stomper, Pompous Gadabout)
- "creatures with power less than this creature's power can't block it"
  (Battering Wurm, Den Protector ...), the "creatures you control" form
  (Champion of Lambholt), the Island-count form (Kraken of the Straits)
- group grants (Delney, Sonorous Howlbonder, Serpent of Yawning Depths,
  Razorjaw Oni) and the Aura/Equipment forms (Canopy Cover, Invisibility,
  Prowler's Helm)
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import LEVEL_COUNTER, Counter
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario


def _block(
    attacker: str,
    blockers: list[str],
    *,
    mine=(),
    theirs=(),
    attach=None,
    levels=0,
    tokens=(),
    setup=None,
):
    """Alice attacks with `attacker`; bob blocks it with `blockers`.

    Returns the exception message if the block is refused, else None."""
    scenario = (
        Scenario()
        .player("alice", battlefield=[attacker, *mine])
        .player("bob", battlefield=[*blockers, *theirs])
        .build()
    )
    attacking = scenario.creature(attacker, "alice")
    if levels:
        attacking.add_counters(LEVEL_COUNTER, levels)
    if attach is not None:
        aura_name, owner = attach
        scenario.find(aura_name, Zone.BATTLEFIELD, owner).attach_to(attacking)
    made = [create_tokens(scenario.game, definition, "bob")[0] for definition in tokens]
    if setup is not None:
        setup(scenario, attacking)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(attacking, defending="bob")
    try:
        scenario.block(attacking, *[scenario.creature(n, "bob") for n in blockers], *made)
    except ValueError as error:
        return str(error)
    return None


EXCEPT_BY = [
    # attacker, legal blocker, illegal blocker
    ("Deathcult Rogue", "Relic Robber", "Hill Giant"),
    ("Dread Warlock", "Vampire Nighthawk", "Hill Giant"),
    ("Departed Deckhand", "Fleeting Spirit", "Hill Giant"),
    ("Evil Eye of Orms-by-Gore", "Wall of Omens", "Hill Giant"),
    ("Amrou Seekers", "Serra Angel", "Hill Giant"),
    ("Amrou Seekers", "Gene Pollinator", "Hill Giant"),
    ("Skirk Shaman", "Goblin Guide", "Grizzly Bears"),
    ("Skirk Shaman", "Gene Pollinator", "Serra Angel"),
    ("Elven Riders", "Wall of Omens", "Hill Giant"),
    ("Elven Riders", "Serra Angel", "Hill Giant"),
    ("Orchard Spirit", "Serra Angel", "Hill Giant"),
    ("Orchard Spirit", "Atzocan Archer", "Hill Giant"),
    ("Signal Pest", "Serra Angel", "Hill Giant"),
    ("Spire Tracer", "Atzocan Archer", "Hill Giant"),
    ("The Balrog, Durin's Bane", "Azusa, Lost but Seeking", "Hill Giant"),
]


@pytest.mark.parametrize(("attacker", "legal", "illegal"), EXCEPT_BY)
def test_cant_be_blocked_except_by_a_quality(attacker: str, legal: str, illegal: str) -> None:
    assert _block(attacker, [legal]) is None
    refusal = _block(attacker, [illegal])
    assert refusal is not None and "can't be blocked" in refusal and "CR 509.1b" in refusal


THREE_OR_MORE = [
    "Guile",
    "Pathrazer of Ulamog",
    "Phyrexian Colossus",
    "Rampaging Ceratops",
    "Relentless X-ATM092",
    "Troll of Khazad-dûm",
    "Underworld Cerberus",
]


@pytest.mark.parametrize("attacker", THREE_OR_MORE)
def test_cant_be_blocked_except_by_three_or_more_creatures(attacker: str) -> None:
    three = ["Hill Giant", "Grizzly Bears", "Goblin Guide"]
    assert _block(attacker, three[:1]) is not None
    assert _block(attacker, three[:2]) is not None
    assert _block(attacker, three) is None


def test_a_leveler_is_unblockable_except_by_black_only_at_level_three() -> None:
    """Zulaport Enforcer's evasion is printed under LEVEL 3+ (CR 711.2)."""
    assert _block("Zulaport Enforcer", ["Hill Giant"]) is None
    assert _block("Zulaport Enforcer", ["Hill Giant"], levels=3) is not None
    assert _block("Zulaport Enforcer", ["Vampire Nighthawk"], levels=3) is None


SCION = TokenDefinition(subtypes=("Eldrazi", "Scion"), power=1, toughness=1)
GOBLIN = TokenDefinition(subtypes=("Goblin",), power=1, toughness=1)


def test_cant_be_blocked_by_eldrazi_scions() -> None:
    """Kor Castigator: a Scion token may not block it, any other creature may."""
    assert _block("Kor Castigator", ["Hill Giant"]) is None
    assert _block("Kor Castigator", [], tokens=[GOBLIN]) is None
    refusal = _block("Kor Castigator", [], tokens=[SCION])
    assert refusal is not None and "Eldrazi Scions" in refusal


def test_cant_be_blocked_by_creature_tokens() -> None:
    """Rubblebelt Runner: a token may not block it, a card may."""
    assert _block("Rubblebelt Runner", ["Hill Giant"]) is None
    assert _block("Rubblebelt Runner", [], tokens=[GOBLIN]) is not None


def test_cant_be_blocked_by_enchanted_or_enchantment_creatures() -> None:
    """Temple Thief: a creature wearing an Aura, or an enchantment creature."""

    def enchant(scenario, _attacker):
        scenario.find("Arrest", Zone.BATTLEFIELD, "bob").attach_to(
            scenario.creature("Hill Giant", "bob")
        )

    assert _block("Temple Thief", ["Hill Giant"]) is None
    assert _block("Temple Thief", ["Hill Giant"], theirs=["Arrest"], setup=enchant) is not None
    bystander = ["Hill Giant", "Arrest"]
    assert _block("Temple Thief", ["Grizzly Bears"], theirs=bystander, setup=enchant) is None
    assert _block("Temple Thief", ["Aegis of the Gods"]) is not None


def test_cant_be_blocked_by_creatures_with_no_name() -> None:
    """Pompous Gadabout: every creature with a name may block it."""
    assert _block("Pompous Gadabout", ["Hill Giant"]) is None
    assert _block("Pompous Gadabout", [], tokens=[TokenDefinition(power=2, toughness=2)]) is None


@pytest.mark.parametrize(
    ("attacker", "blocker", "refused"),
    [
        ("Howlgeist", "Grizzly Bears", True),
        ("Howlgeist", "Hill Giant", True),
        ("Howlgeist", "Serra Angel", False),
        ("Battering Wurm", "Hill Giant", True),
        ("Battering Wurm", "Serra Angel", False),
        ("Den Protector", "Memnite", True),
        ("Den Protector", "Grizzly Bears", False),
        ("Wandering Wolf", "Memnite", True),
        ("Wandering Wolf", "Grizzly Bears", False),
        ("Skarrgan Pit-Skulk", "Mob Lookout", True),
        ("Skarrgan Pit-Skulk", "Memnite", False),
    ],
)
def test_creatures_with_lesser_power_cant_block_it(attacker, blocker, refused) -> None:
    """Printed powers: Howlgeist 4, Battering Wurm 4, Den Protector 2, Wandering
    Wolf 2, Skarrgan Pit-Skulk 1; blockers Mob Lookout 0, Memnite 1, Bears 2,
    Hill Giant 3, Serra Angel 4."""
    result = _block(attacker, [blocker])
    assert (result is not None) is refused
    if refused:
        assert "CR 509.1b" in result


def test_the_creatures_you_control_form_protects_every_attacker_you_control() -> None:
    """Champion of Lambholt (power 1): a power-0 creature can't block any
    creature its controller controls."""
    assert _block("Grizzly Bears", ["Mob Lookout"], mine=["Champion of Lambholt"]) is not None
    assert _block("Grizzly Bears", ["Memnite"], mine=["Champion of Lambholt"]) is None
    assert _block("Grizzly Bears", ["Mob Lookout"]) is None
    assert _block("Grizzly Bears", ["Mob Lookout"], theirs=["Champion of Lambholt"]) is None


def test_power_less_than_the_number_of_islands_you_control() -> None:
    """Kraken of the Straits with two Islands: power-1 creatures can't block it."""
    assert _block("Kraken of the Straits", ["Memnite"], mine=["Island", "Island"]) is not None
    assert _block("Kraken of the Straits", ["Grizzly Bears"], mine=["Island", "Island"]) is None
    assert _block("Kraken of the Straits", ["Memnite"], mine=["Island"]) is None


def test_delney_protects_small_creatures_from_big_blockers() -> None:
    """Creatures you control with power 2 or less can't be blocked by power 3+."""
    assert _block("Grizzly Bears", ["Hill Giant"], mine=["Delney, Streetwise Lookout"]) is not None
    assert _block("Grizzly Bears", ["Memnite"], mine=["Delney, Streetwise Lookout"]) is None
    assert _block("Hill Giant", ["Hill Giant"], mine=["Delney, Streetwise Lookout"]) is None
    assert _block("Grizzly Bears", ["Hill Giant"]) is None


def test_sonorous_howlbonder_gives_menace_creatures_a_three_blocker_floor() -> None:
    three = ["Hill Giant", "Grizzly Bears", "Goblin Guide"]
    mine = ["Sonorous Howlbonder"]
    assert _block("Sunset Saboteur", three[:2], mine=mine) is not None
    assert _block("Sunset Saboteur", three, mine=mine) is None
    assert _block("Grizzly Bears", three[:1], mine=mine) is None


def test_serpent_of_yawning_depths_group() -> None:
    mine = ["Serpent of Yawning Depths"]
    assert _block("Kraken of the Straits", ["Memnite"], mine=mine) is not None
    assert _block("Kraken of the Straits", ["Harbor Serpent"], mine=mine) is None
    assert _block("Grizzly Bears", ["Memnite"], mine=mine) is None


def test_battlefront_krushok_counter_group() -> None:
    mine = ["Battlefront Krushok"]

    def counter(_scenario, attacker):
        attacker.add_counters(Counter.PLUS_ONE, 1)

    two = ["Hill Giant", "Goblin Guide"]
    assert _block("Grizzly Bears", two, mine=mine, setup=counter) is not None
    assert _block("Grizzly Bears", two[:1], mine=mine, setup=counter) is None
    assert _block("Grizzly Bears", two, mine=mine) is None


def test_black_creatures_cant_block() -> None:
    assert _block("Grizzly Bears", ["Vampire Nighthawk"], mine=["Razorjaw Oni"]) is not None
    assert _block("Grizzly Bears", ["Hill Giant"], mine=["Razorjaw Oni"]) is None
    assert _block("Grizzly Bears", ["Vampire Nighthawk"]) is None


@pytest.mark.parametrize(
    ("aura", "legal", "illegal"),
    [
        ("Canopy Cover", "Serra Angel", "Hill Giant"),
        ("Canopy Cover", "Atzocan Archer", "Hill Giant"),
        ("Invisibility", "Wall of Omens", "Hill Giant"),
    ],
)
def test_enchanted_creature_cant_be_blocked_except(aura, legal, illegal) -> None:
    attach = (aura, "alice")
    assert _block("Grizzly Bears", [legal], mine=[aura], attach=attach) is None
    assert _block("Grizzly Bears", [illegal], mine=[aura], attach=attach) is not None
    assert _block("Grizzly Bears", [illegal], mine=[aura]) is None


def test_equipped_creature_cant_be_blocked_except_by_walls() -> None:
    attach = ("Prowler's Helm", "alice")
    assert (
        _block("Grizzly Bears", ["Wall of Omens"], mine=["Prowler's Helm"], attach=attach) is None
    )
    assert (
        _block("Grizzly Bears", ["Hill Giant"], mine=["Prowler's Helm"], attach=attach) is not None
    )


def test_a_vehicle_cant_be_blocked_by_low_power_creatures() -> None:
    """Demolition Stomper (a Vehicle, so a creature only once crewed): creatures
    with power 2 or less can't block it, a power-3 one can."""
    from magic_cards_model.machines.keywords import crew_activation

    def blocked_by(blocker: str) -> str | None:
        scenario = (
            Scenario()
            .manual_turn_based_actions()
            .player("alice", battlefield=["Demolition Stomper", "Hill Giant", "Hill Giant"])
            .player("bob", battlefield=[blocker])
            .build()
        )
        scenario.start_at(Step.PRECOMBAT_MAIN)
        stomper = scenario.find("Demolition Stomper", Zone.BATTLEFIELD)
        giants = [
            c for c in scenario.game.permanents_controlled_by("alice") if c.name == "Hill Giant"
        ]
        activation = crew_activation(scenario.game, stomper, giants, "alice")
        activation.begin_paying()
        activation.payment.pay()
        activation.activate()
        activation.resolve()
        scenario.start_at(Step.DECLARE_ATTACKERS)
        scenario.attack_with(stomper, defending="bob")
        try:
            scenario.block(stomper, scenario.creature(blocker, "bob"))
        except ValueError as error:
            return str(error)
        return None

    assert blocked_by("Grizzly Bears") is not None
    assert blocked_by("Hill Giant") is None


@pytest.mark.parametrize(
    ("attacker", "blocker", "refused"),
    [
        ("Elusive Otter", "Mob Lookout", True),
        ("Elusive Otter", "Memnite", False),
        ("Shrill Howler", "Mob Lookout", True),
        ("Shrill Howler", "Craw Wurm", False),
    ],
)
def test_elusive_otter_and_shrill_howler_lesser_power_blockers(attacker, blocker, refused) -> None:
    """Otter has power 1; Shrill Howler's is more than a power-0 blocker's and
    less than Craw Wurm's 6 (CR 509.1b)."""
    result = _block(attacker, [blocker])
    assert (result is not None) is refused

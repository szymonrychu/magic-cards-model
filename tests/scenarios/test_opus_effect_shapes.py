"""Scenario: Opus (CR 207.2c ability word - "Opus — Whenever you cast an
instant or sorcery spell, [effect]. If five or more mana was spent to cast
that spell, [rider]." - no rules meaning of its own; the cards are ordinary
CR 601.2 cast triggers whose rider reads CR 601.2h's own "amount of mana
spent" off the *triggering* spell's `CastRecord`, via the already-existing
boolean reader (`machines/conditions/cast_record._at_least_mana_spent`).

Every effect shape the round's Opus printings carry:

- Aberrant Manawurm (not itself an Opus card, but the same underlying "gets
  +X/+0 ..., where X is the amount of mana spent to cast that spell" reader
  every Opus pump shares) - `machines/effects._cast_trigger_mana_spent_x_
  ability_text` substitutes X for the real number before the ordinary layer
  pump parser ever sees the sentence.
- Molten-Core Maestro: an unconditional counter, then a conditional "add
  mana equal to this creature's power" rider (CR 106.3, mana added during
  the trigger's own resolution).
- Deluge Virtuoso: a base pump, replaced ("instead") by a bigger one when
  the condition holds.
- Elemental Mascot: a base pump, plus a conditional exile-and-play-
  permission rider (`_parse_exile_then_play_permission_clauses`, reused
  outright).
- Expressive Firedancer: a base pump, plus a conditional "also gains
  double strike" rider (additive, not a replacement).

Off-pool proof of the mana-spent-X pump's generality: **Shantotto, Tactician
Magician** - "Whenever you cast a noncreature spell, Shantotto gets +X/+0
until end of turn, where X is the amount of mana spent to cast that spell.
If X is 4 or more, draw a card." Verified with Scryfall's own card search in
this session as Modern/Pioneer/Standard-legal and not a listed round card
or deck-pool card. Its own second sentence ("If X is 4 or more, draw a
card.") is a different mechanism this task does not own - CR 107.3a's X, as
a *numeric* value fed back into an ordinary intervening-if/count reader -
and `machines/effects.trigger_effect_for` routes this whole ability through
the generic layer-pump fallback (`create_continuous_effect_of_ability`),
which reads only the pump sentence and never that second one; see the dated
MEMORY.md line. Only the pump itself is exercised here.

Unholy Hunger ({3}{B}{B}, "Destroy target creature.") is the plain 5-mana
instant/sorcery used throughout to cross the "five or more mana" threshold
without any division/kicker/X complexity of its own.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color

from .harness import Scenario


def resolve_all(scenario: Scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _cast(scenario: Scenario, name: str, *sources, targets=None):
    card = scenario.find(name, Zone.HAND, "alice")
    scenario.game.cast(card, "alice", targets=targets, mana_sources=list(sources))
    resolve_all(scenario)


# -- Aberrant Manawurm --------------------------------------------------------


def _manawurm_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Unholy Hunger"],
            battlefield=[
                "Aberrant Manawurm",
                "Mountain",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_manawurm_pumps_by_one_mana_spent_on_lightning_bolt():
    scenario = _manawurm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manawurm = scenario.creature("Aberrant Manawurm", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(manawurm), scenario.game.toughness_of(manawurm))

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    chars = scenario.game.characteristics_of(manawurm)
    assert (chars.power, chars.toughness) == (printed[0] + 1, printed[1])


def test_manawurm_pumps_by_five_mana_spent_on_unholy_hunger():
    scenario = _manawurm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    manawurm = scenario.creature("Aberrant Manawurm", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(manawurm), scenario.game.toughness_of(manawurm))

    _cast(
        scenario,
        "Unholy Hunger",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bear],
    )

    chars = scenario.game.characteristics_of(manawurm)
    assert (chars.power, chars.toughness) == (printed[0] + 5, printed[1])


# -- Molten-Core Maestro -------------------------------------------------------


def _maestro_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Unholy Hunger"],
            battlefield=[
                "Molten-Core Maestro",
                "Mountain",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_maestro_gets_a_counter_but_no_mana_below_the_threshold():
    scenario = _maestro_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maestro = scenario.creature("Molten-Core Maestro", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    assert maestro.counters["+1/+1"] == 1
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == 0


def test_maestro_adds_mana_equal_to_its_power_at_the_threshold():
    scenario = _maestro_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    maestro = scenario.creature("Molten-Core Maestro", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed_power = scenario.game.power_of(maestro)

    _cast(
        scenario,
        "Unholy Hunger",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bear],
    )

    # The counter is put on first (CR 608.2c's printed order), so the power
    # the mana amount equals already includes it.
    assert maestro.counters["+1/+1"] == 1
    assert scenario.game.power_of(maestro) == printed_power + 1
    assert scenario.player("alice").mana_pool.floating.get(Color.RED, 0) == printed_power + 1


# -- Deluge Virtuoso: "instead" replaces, never adds --------------------------


def _virtuoso_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Unholy Hunger"],
            battlefield=[
                "Deluge Virtuoso",
                "Mountain",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_virtuoso_pumps_one_one_below_the_threshold():
    scenario = _virtuoso_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    virtuoso = scenario.creature("Deluge Virtuoso", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(virtuoso), scenario.game.toughness_of(virtuoso))

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    chars = scenario.game.characteristics_of(virtuoso)
    assert (chars.power, chars.toughness) == (printed[0] + 1, printed[1] + 1)


def test_virtuoso_pumps_two_two_instead_at_the_threshold():
    scenario = _virtuoso_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    virtuoso = scenario.creature("Deluge Virtuoso", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(virtuoso), scenario.game.toughness_of(virtuoso))

    _cast(
        scenario,
        "Unholy Hunger",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bear],
    )

    chars = scenario.game.characteristics_of(virtuoso)
    # +2/+2 instead of the base +1/+1 - never both (+3/+3 would be the
    # additive misreading this "instead" rider must not fall into).
    assert (chars.power, chars.toughness) == (printed[0] + 2, printed[1] + 2)


# -- Elemental Mascot: base pump plus a conditional exile-and-play rider -----


def _mascot_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Unholy Hunger"],
            library=["Mountain"],
            battlefield=[
                "Elemental Mascot",
                "Mountain",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_mascot_pumps_but_exiles_nothing_below_the_threshold():
    scenario = _mascot_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mascot = scenario.creature("Elemental Mascot", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = scenario.game.power_of(mascot)

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    assert scenario.game.power_of(mascot) == printed + 1
    assert scenario.game.play_permissions == []


def test_mascot_exiles_and_grants_play_permission_at_the_threshold():
    scenario = _mascot_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mascot = scenario.creature("Elemental Mascot", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = scenario.game.power_of(mascot)

    _cast(
        scenario,
        "Unholy Hunger",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bear],
    )

    assert scenario.game.power_of(mascot) == printed + 1
    exiled = scenario.find("Mountain", Zone.EXILE, "alice")
    assert len(scenario.game.play_permissions) == 1
    (permission,) = scenario.game.play_permissions
    assert permission.card_id == exiled.id
    assert permission.player == "alice"
    assert permission.expires_end_of_next_turn


# -- Expressive Firedancer: base pump plus a conditional "also" rider -------


def _firedancer_board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Unholy Hunger"],
            battlefield=[
                "Expressive Firedancer",
                "Mountain",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
                "Swamp",
            ],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_firedancer_pumps_without_double_strike_below_the_threshold():
    scenario = _firedancer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    firedancer = scenario.creature("Expressive Firedancer", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(firedancer), scenario.game.toughness_of(firedancer))

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    chars = scenario.game.characteristics_of(firedancer)
    assert (chars.power, chars.toughness) == (printed[0] + 1, printed[1] + 1)
    assert not has_keyword(firedancer, Keyword.DOUBLE_STRIKE, scenario.game)


def test_firedancer_also_gains_double_strike_at_the_threshold():
    scenario = _firedancer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    firedancer = scenario.creature("Expressive Firedancer", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = (scenario.game.power_of(firedancer), scenario.game.toughness_of(firedancer))

    _cast(
        scenario,
        "Unholy Hunger",
        *scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp"),
        targets=[bear],
    )

    chars = scenario.game.characteristics_of(firedancer)
    # The base +1/+1 still runs - "also" adds to it, it never replaces it.
    assert (chars.power, chars.toughness) == (printed[0] + 1, printed[1] + 1)
    assert has_keyword(firedancer, Keyword.DOUBLE_STRIKE, scenario.game)


# -- Off-pool proof: Shantotto, Tactician Magician ----------------------------


def test_off_pool_shantotto_pumps_by_the_mana_spent_on_a_noncreature_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Shantotto, Tactician Magician", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shantotto = scenario.creature("Shantotto, Tactician Magician", "alice")
    bear = scenario.creature("Grizzly Bears", "bob")
    printed = scenario.game.power_of(shantotto)

    _cast(scenario, "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bear])

    assert scenario.game.power_of(shantotto) == printed + 1

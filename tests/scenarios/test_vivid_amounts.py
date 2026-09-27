"""Vivid (ecl-T1) - CR 207.2c: an ability word has no rules meaning of its
own, so every "Vivid" card actually prints one amount, CR 105.1's colors
among a group of permanents its controller controls (CR 105.2c: a colorless
permanent contributes none), read once when the printed effect asks for it
(CR 608.2h). `machines/vivid.py`'s `colors_among_count_expression` is the one
reader every position below shares - an ETB's damage, tokens, life, life
loss/gain, a draw, a beginning-of-combat pump, and an "up to X targets" pump
that uses X for both the magnitude and how many targets are chosen (CR
601.2c: "If the spell has a variable number of targets, the player announces
how many targets they will choose").

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- CR 105.1: "There are five colors in the Magic game: white, blue, black,
  red, and green."
- CR 105.2c: "A colorless object has no color."
- CR 207.2c: ability words, including "vivid", have no rules meaning of
  their own.
- CR 608.2h: an effect's own count of game information is read once, when
  the effect is applied.
- CR 601.2c: a variable number of targets is announced before the targets
  themselves are chosen; CR 115.6 lets "up to N" choose fewer.
- CR 603.6a: an ETB trigger fires once the permanent is already on the
  battlefield, so it counts itself among the "permanents you control" too.

Proof of generality: Moonveil Regent ("it deals X damage to any target,
where X is the number of colors among permanents you control", a *dies*
trigger rather than an ETB) is not in the ecl pool and not one of this
task's cards - it exercises the identical `colors_among_count_expression`
reader from a different trigger event.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# Five distinct one-mana permanents, one per color (CR 105.1), used to build
# a controlled "N colors among permanents you control" board without any
# card whose own text would confuse the count.
_WHITE = "Savannah Lions"
_BLUE = "Cursecatcher"
_BLACK = "Blood Artist"
_RED = "Goblin Guide"
_GREEN = "Llanowar Elves"


def _pt(scenario: Scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- Explosive Prodigy: ETB damage --------------------------------------------


def test_explosive_prodigy_deals_damage_equal_to_the_colors_among_permanents():
    """Vivid - "it deals X damage to target creature an opponent controls,
    where X is the number of colors among permanents you control." Alice
    controls white and blue permanents before casting the red Explosive
    Prodigy, so once it has entered (CR 603.6a) she controls three colors -
    lethal to Bob's 2-toughness Grizzly Bears.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Explosive Prodigy"],
            battlefield=[_WHITE, _BLUE, "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.choose_trigger_targets("Explosive Prodigy", [bears])

    scenario.cast_and_resolve("Explosive Prodigy", *sources)
    scenario.pass_until_resolved()

    # 3 damage on a 2-toughness Grizzly Bears is lethal (CR 704.5g); a dead
    # creature's marked damage does not survive the zone change (CR 400.7),
    # so the zone itself is what proves the amount, not the damage count.
    assert bears.zone is Zone.GRAVEYARD


def test_explosive_prodigy_colorless_permanents_do_not_count():
    """CR 105.2c: a colorless permanent contributes no color. Two colorless
    artifact creatures alongside Explosive Prodigy itself is one color
    (red) - one damage, not three.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Explosive Prodigy"],
            battlefield=["Memnite", "Ornithopter", "Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.choose_trigger_targets("Explosive Prodigy", [bears])

    scenario.cast_and_resolve("Explosive Prodigy", *sources)
    scenario.pass_until_resolved()

    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD


# -- Kithkeeper: ETB token creation --------------------------------------------


def test_kithkeeper_creates_a_token_per_color_among_permanents():
    """Vivid - "create X 1/1 green and white Kithkin creature tokens, where
    X is the number of colors among permanents you control." Kithkeeper is
    white; with a blue and a black permanent already out, entering makes
    three colors -> three tokens.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kithkeeper"],
            battlefield=[_BLUE, _BLACK] + ["Plains"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Plains"] * 7)

    scenario.cast_and_resolve("Kithkeeper", *sources)
    scenario.pass_until_resolved()

    tokens = [state for state in scenario.game.permanents_controlled_by("alice") if state.token]
    assert len(tokens) == 3
    assert all(state.name == "Kithkin Token" for state in tokens)
    for token in tokens:
        assert _pt(scenario, token) == (1, 1)


# -- Luminollusk: ETB life gain -------------------------------------------------


def test_luminollusk_gains_life_equal_to_the_colors_among_permanents():
    """Vivid - "you gain life equal to the number of colors among permanents
    you control." Green (itself) plus a red and a white permanent is three.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Luminollusk"], battlefield=[_RED, _WHITE] + ["Forest"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 4)

    scenario.cast_and_resolve("Luminollusk", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 23


# -- Shimmercreep: ETB life loss and gain ---------------------------------------


def test_shimmercreep_drains_life_equal_to_the_colors_among_permanents():
    """Vivid - "each opponent loses X life and you gain X life, where X is
    the number of colors among permanents you control." Black (itself) plus
    white, blue and green permanents is four.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shimmercreep"],
            battlefield=[_WHITE, _BLUE, _GREEN] + ["Swamp"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Shimmercreep", *sources)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 24
    assert scenario.player("bob").life == 16


# -- Shinestriker: ETB draw -----------------------------------------------------


def test_shinestriker_draws_cards_equal_to_the_colors_among_permanents():
    """Vivid - "draw cards equal to the number of colors among permanents
    you control." Blue (itself) plus red, black, and green is four.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Shinestriker"],
            library=["Forest", "Forest", "Forest", "Forest"],
            battlefield=[_RED, _BLACK, _GREEN] + ["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Island"] * 6)

    scenario.cast_and_resolve("Shinestriker", *sources)
    scenario.pass_until_resolved()

    assert len(scenario.player("alice").hand) == 4


# -- Glister Bairn: beginning-of-combat pump on another target -----------------


def test_glister_bairn_pumps_another_target_creature_by_the_colors_among_permanents():
    """Vivid - "at the beginning of combat on your turn, another target
    creature you control gets +X/+X until end of turn, where X is the
    number of colors among permanents you control." Green (Glister Bairn
    itself) plus white and blue is three; Grizzly Bears is the only *other*
    legal target.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Glister Bairn", "Grizzly Bears", _WHITE, _BLUE])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Glister Bairn", [bears])
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()

    assert _pt(scenario, bears) == (5, 5)


# -- Prismabasher: ETB pump where X also sets the target count -----------------


def test_prismabasher_pumps_up_to_x_target_creatures_it_controls():
    """Vivid - "up to X target creatures you control get +X/+X until end of
    turn, where X is the number of colors among permanents you control." CR
    601.2c: X (four - green Prismabasher itself plus white, blue and black)
    sets how many targets are announced. CR 115.6 lets "up to X" choose fewer
    than X, which every one of these tests does anyway: Prismabasher cannot
    legally target itself while it is still a spell on the stack (CR 601.2c
    reads the board as it stands when targets are announced, and the trigger
    is announced as the resolving creature spell finishes resolving, by
    which point the choice has to already be on file), so only the three
    *other* creatures are targeted here - each still gets the full +4/+4 X
    computes.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prismabasher"],
            battlefield=[_WHITE, _BLUE, _BLACK] + ["Forest"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6)
    white = scenario.creature(_WHITE, "alice")
    blue = scenario.creature(_BLUE, "alice")
    black = scenario.creature(_BLACK, "alice")
    white_pt, blue_pt, black_pt = _pt(scenario, white), _pt(scenario, blue), _pt(scenario, black)

    # `choose_trigger_targets` is keyed by card name and must be registered
    # before the trigger is actually put on the stack (CR 603.3d), which
    # happens as the creature spell resolves - so it is set before that
    # first `pass_until_resolved`, not after.
    scenario.cast_onto_stack("Prismabasher", *sources)
    scenario.choose_trigger_targets("Prismabasher", [white, blue, black])
    scenario.pass_until_resolved()  # the creature spell itself
    scenario.pass_until_resolved()  # its own ETB trigger
    prismabasher = scenario.creature("Prismabasher", "alice")

    assert _pt(scenario, white) == (white_pt[0] + 4, white_pt[1] + 4)
    assert _pt(scenario, blue) == (blue_pt[0] + 4, blue_pt[1] + 4)
    assert _pt(scenario, black) == (black_pt[0] + 4, black_pt[1] + 4)
    # Untargeted, Prismabasher itself (a printed 6/6) is unaffected by its
    # own trigger.
    assert _pt(scenario, prismabasher) == (6, 6)


def test_prismabasher_up_to_x_allows_fewer_targets_than_x():
    """CR 115.6: "up to X" may choose fewer than the X it computes, including
    zero. Three colors are among Alice's permanents (white, blue, and green
    Prismabasher itself), but only the white creature is targeted - it still
    gets the full +3/+3 X computes, and nothing else changes.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Prismabasher"], battlefield=[_WHITE, _BLUE] + ["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*["Forest"] * 6)
    white = scenario.creature(_WHITE, "alice")
    blue = scenario.creature(_BLUE, "alice")
    white_pt, blue_pt = _pt(scenario, white), _pt(scenario, blue)

    scenario.cast_onto_stack("Prismabasher", *sources)
    scenario.choose_trigger_targets("Prismabasher", [white])
    scenario.pass_until_resolved()  # the creature spell itself
    scenario.pass_until_resolved()  # its own ETB trigger
    prismabasher = scenario.creature("Prismabasher", "alice")

    assert _pt(scenario, white) == (white_pt[0] + 3, white_pt[1] + 3)
    assert _pt(scenario, blue) == blue_pt
    assert _pt(scenario, prismabasher) == (6, 6)


# -- Moonveil Regent: proof of generality on a second, off-pool printing -------


def test_moonveil_regent_dies_trigger_reads_the_same_colors_among_permanents_amount():
    """Moonveil Regent (Modern/Pioneer-legal, not in the ecl pool and not one
    of this task's cards): "When this creature dies, it deals X damage to
    any target, where X is the number of colors among permanents you
    control." A *dies* trigger, not an ETB - proof `colors_among_count_
    expression` is the shared reader, not a copy fitted to one trigger.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Moonveil Regent", _WHITE, _BLUE, "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    regent = scenario.creature("Moonveil Regent", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Moonveil Regent", [bears])

    scenario.game.deal_damage(regent, 10, source=regent)
    scenario.state_based_actions()
    assert regent.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    # White, blue, and red (Moonveil Regent's own color) is three - lethal
    # to the 2-toughness Grizzly Bears (CR 704.5g; damage does not survive
    # the zone change, CR 400.7, so the zone is what proves the amount).
    assert bears.zone is Zone.GRAVEYARD

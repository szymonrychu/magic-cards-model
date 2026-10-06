"""Scenario: a Radiance damage SPELL - "`<Source>` deals N damage to target
creature and each other creature that shares a color with it."

Cleansing Beam (N = 2) and Brightflame (X) are the two printings. The shape
was read only for abilities (Wojek Embermage, Izzet Staticaster); on a spell
the same sentence is led by the Radiance ability word and the group is
resolved from the one target as the spell resolves.

The two printings are the only damage spells with the template; Wojek
Embermage is an ability, so it is asserted as the unchanged sibling. Wojek
Siren and Incite Hysteria carry the Radiance word over a pump, not damage, and
belong to the pump readers, so there is no third damage-spell printing to use
as a proof: the group semantics are proven on both printings and on the
ability reader.

Rules looked up with `mise run rules:find` in the session that wrote this:

- CR 207.2c - Radiance is an ability word with no special rules meaning.
- CR 105.2c - "A colorless object has no color": it shares a color with
  nothing, so a colorless target is the whole group.
- CR 608.2b - the one target illegal: the spell doesn't resolve, so the rest
  of the group is not damaged either.
- CR 120.1 - the spell is the source of the damage (protection from red on a
  group member stops it, CR 615.1a's prevention).
- CR 107.3a - Brightflame's X is announced as it is cast.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

BEAM = "Cleansing Beam"
BRIGHTFLAME = "Brightflame"


def _board(*, alice_hand=(BEAM,), alice_battlefield=(), bob_battlefield=()) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            hand=list(alice_hand),
            battlefield=["Mountain"] * 4 + ["Plains"] * 2 + list(alice_battlefield),
        )
        .player("bob", library=["Mountain"], battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _beam(scenario: Scenario, target):
    scenario.cast_and_resolve(BEAM, targets=[target], auto=True)


def test_both_printings_are_fully_handled():
    for name in (BEAM, BRIGHTFLAME):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def test_every_creature_sharing_a_color_with_the_target_takes_the_damage():
    scenario = _board(
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Savannah Lions", "Runeclaw Bear", "Hill Giant", "Gray Ogre"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    ogre = scenario.creature("Gray Ogre", "bob")

    _beam(scenario, runeclaw)

    assert runeclaw.zone is Zone.GRAVEYARD, "the target: 2 damage kills the 2/2"
    assert bears.zone is Zone.GRAVEYARD, "green, and a creature you control: not just theirs"
    assert lions.damage == 0 and giant.damage == 0 and ogre.damage == 0, "other colors"


def test_a_colorless_target_shares_a_color_with_nothing():
    scenario = _board(
        alice_battlefield=["Memnite"], bob_battlefield=["Sliver Construct", "Grizzly Bears"]
    )
    memnite = scenario.creature("Memnite", "alice")
    construct = scenario.creature("Sliver Construct", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    _beam(scenario, construct)

    assert construct.zone is Zone.GRAVEYARD, "the target alone"
    assert memnite.zone is Zone.BATTLEFIELD, "colorless, but CR 105.2c: no color to share"
    assert bears.damage == 0


def test_a_multicolored_target_shares_with_each_of_its_colors():
    scenario = _board(
        bob_battlefield=["Watchwolf", "Grizzly Bears", "Savannah Lions", "Hill Giant"]
    )
    wolf = scenario.creature("Watchwolf", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    _beam(scenario, wolf)

    assert wolf.damage == 2
    assert bears.zone is Zone.GRAVEYARD, "green"
    assert lions.zone is Zone.GRAVEYARD, "white"
    assert giant.damage == 0, "red shares neither green nor white"


def test_a_group_member_with_protection_from_the_spell_takes_nothing():
    """Cerulean Drake (blue, protection from red) cannot be targeted but is
    still in the group: the red spell is the damage source (CR 120.1) and the
    damage to it is prevented, while the blue target takes its share."""
    scenario = _board(bob_battlefield=["Wind Drake", "Cerulean Drake"])
    wind = scenario.creature("Wind Drake", "bob")
    cerulean = scenario.creature("Cerulean Drake", "bob")

    _beam(scenario, wind)

    assert wind.zone is Zone.GRAVEYARD, "2 damage kills the 2/2 Wind Drake"
    assert cerulean.damage == 0 and cerulean.zone is Zone.BATTLEFIELD


def test_the_target_gone_before_resolution_means_nobody_is_damaged():
    """CR 608.2b: the Beam's only target is illegal, so it does not resolve and
    the other green creature is not damaged either."""
    scenario = _board(
        alice_hand=[BEAM, "Lightning Bolt"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Runeclaw Bear"],
    )
    ally = scenario.creature("Grizzly Bears", "alice")
    target = scenario.creature("Runeclaw Bear", "bob")
    beam_sources = scenario.untapped_sources(
        "Plains", "Plains", "Mountain", "Mountain", "Mountain", username="alice"
    )
    scenario.cast_onto_stack(BEAM, *beam_sources, targets=[target])
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[target])
    scenario.pass_until_resolved()  # the Bolt kills the target
    scenario.pass_until_resolved()  # the Beam has no legal target

    assert target.zone is Zone.GRAVEYARD
    assert ally.damage == 0
    assert scenario.find(BEAM, Zone.GRAVEYARD, "alice")


def test_brightflame_deals_x_to_the_whole_group():
    scenario = _board(
        alice_hand=[BRIGHTFLAME],
        bob_battlefield=["Grizzly Bears", "Runeclaw Bear", "Craw Wurm", "Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    runeclaw = scenario.creature("Runeclaw Bear", "bob")
    wurm = scenario.creature("Craw Wurm", "bob")
    giant = scenario.creature("Hill Giant", "bob")

    casting = scenario.cast(BRIGHTFLAME, targets=[bears])
    casting.x_value = 2
    casting.determine_cost(x_value=2)
    scenario.auto_pay(casting.begin_paying(), username="alice")
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD and runeclaw.zone is Zone.GRAVEYARD
    assert wurm.damage == 2, "X = 2 to every green creature, Craw Wurm included"
    assert giant.damage == 0


def test_the_wojek_ability_reader_is_unchanged():
    bad = [c for c in card_support(card("Wojek Embermage")).clauses if c.outcome != "handled"]
    assert not bad, bad

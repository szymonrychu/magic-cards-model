"""A double-faced creature's power, toughness, oracle text and types (CR 712).

The bug: Scryfall leaves `power`, `toughness`, `oracle_text` and `colors` null
at the top level of a `transform` or `modal_dfc` card and puts each face's own
values on `card_faces` instead. `machines/layers.py`'s `printed_characteristics`
read only the top-level fields, so every double-faced creature's base
characteristics were `power=None, toughness=None` and an empty ability list -
`machines/combat.py`'s `_power_of` then folded that `None` into a real `0`
(`power or 0`), so the creature dealt no combat damage, and `Game.power_of` /
`Game.toughness_of` reported the same `None` everywhere else, which made
`Game._dies_to_state_based_action` leave a lethally-damaged double-faced
creature alone (CR 704.5g never fires on a toughness that is not a number).

The user's report: Duskwatch Recruiter, blocking Ocelot Pride, assigned no
damage back while Grizzly Bears in the same combat assigned correctly. That
scenario is the regression test below.

- **CR 712.8a** - "While a double-faced card is outside the game or in a zone
  other than the battlefield or stack, it has only the characteristics of its
  front face."
- **CR 712.8d** - "While a double-faced permanent has its front face up, it
  has only the characteristics of its front face." Nothing here reads
  `CardState.transformed` yet (see its own docstring), so every card below
  stays front-face-up throughout.
- **CR 712.8f** - "While a modal double-faced spell is on the stack or a modal
  double-faced permanent is on the battlefield, it has only the
  characteristics of the face that's up" - the land face, for the two modal
  cards below played as creatures rather than lands.
- **CR 510.1a** - "Each attacking creature and each blocking creature assigns
  combat damage equal to its power."
- **CR 704.5g** - "If a creature has toughness greater than 0, it has damage
  marked on it, and the total damage marked on it is greater than or equal to
  its toughness, that creature has been dealt lethal damage and is destroyed."

Covers both layouts: `transform` (Duskwatch Recruiter, Delver of Secrets,
Ajani, Nacatl Pariah) and `modal_dfc` (Disciple of Freyalise, Drowner of
Truth, Witch Enchanter), each cast as its creature face.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from tests.scenarios.harness import Scenario

# -- the user's report -------------------------------------------------------


def test_duskwatch_recruiter_blocks_ocelot_pride_and_assigns_damage_back():
    """Duskwatch Recruiter (2/2) blocks Ocelot Pride (1/1): both deal their
    printed power (CR 510.1a), so Ocelot Pride takes lethal damage (CR 704.5g)
    and Duskwatch Recruiter, at 1 marked, does not.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob", battlefield=["Duskwatch Recruiter"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ocelot = scenario.creature("Ocelot Pride", "alice")
    duskwatch = scenario.creature("Duskwatch Recruiter // Krallenhorde Howler", "bob")
    scenario.attack_with(ocelot)
    scenario.block(ocelot, duskwatch)
    scenario.combat_damage()

    assert ocelot.zone is Zone.GRAVEYARD, "1 damage was lethal to a 1/1"
    assert duskwatch.zone is Zone.BATTLEFIELD
    assert duskwatch.damage == 1, "Duskwatch Recruiter is a 2/2, not lethally damaged"


def test_grizzly_bears_in_the_same_combat_is_unaffected():
    """The control from the same report: an ordinary creature already assigned
    correctly, so the fix must not change its behaviour.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ocelot Pride"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ocelot = scenario.creature("Ocelot Pride", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(ocelot)
    scenario.block(ocelot, bears)
    scenario.combat_damage()

    assert ocelot.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 1


# -- power and toughness read off the front face, transform layout ----------


def test_delver_of_secrets_deals_its_printed_power_unblocked():
    """Delver of Secrets, front face up, is a 1/1 (CR 712.8d) - not the 3/2
    Insectile Aberration on its other face, which never applies here since
    nothing transforms it.
    """
    scenario = Scenario().player("alice", battlefield=["Delver of Secrets"]).player("bob").build()
    scenario.start_at(Step.DECLARE_ATTACKERS)

    delver = scenario.creature("Delver of Secrets // Insectile Aberration")
    scenario.attack_with(delver)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 19


def test_ajani_nacatl_pariah_dies_to_lethal_damage_state_based_action():
    """Ajani, Nacatl Pariah's front face is a 1/2 creature; 2 damage from a
    blocker is lethal (CR 704.5g), which needs a real computed toughness -
    before the fix, `None` toughness left the state-based action unable to act.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ajani, Nacatl Pariah"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    ajani = scenario.creature("Ajani, Nacatl Pariah // Ajani, Nacatl Avenger", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(ajani)
    scenario.block(ajani, bears)
    scenario.combat_damage()

    assert ajani.zone is Zone.GRAVEYARD, "2 damage is lethal to a 1/2"
    assert bears.zone is Zone.BATTLEFIELD, "1 damage is not lethal to a 2/2"
    assert bears.damage == 1


def test_ajani_nacatl_pariah_reports_its_front_faces_type_line():
    """CR 712.8d again, from the types side: a Legendary Creature, not the
    Legendary Planeswalker printed on the back face.
    """
    scenario = Scenario().player("alice", battlefield=["Ajani, Nacatl Pariah"]).build()
    ajani = scenario.creature("Ajani, Nacatl Pariah // Ajani, Nacatl Avenger")

    assert ajani.types == (Type.CREATURE,)
    assert ajani.power == 1
    assert ajani.toughness == 2


# -- power and toughness read off the front face, modal_dfc layout ----------


def test_disciple_of_freyalise_cast_as_a_creature_deals_its_printed_power():
    """Disciple of Freyalise // Garden of Freyalise, cast for its creature
    face (not played as the land), is a 3/3 (CR 712.8f).
    """
    scenario = (
        Scenario().player("alice", battlefield=["Disciple of Freyalise"]).player("bob").build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    disciple = scenario.creature("Disciple of Freyalise // Garden of Freyalise")
    scenario.attack_with(disciple)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.player("bob").life == 17


def test_drowner_of_truth_survives_a_block_and_kills_its_blocker():
    """Drowner of Truth // Drowned Jungle, cast for its 7/6 creature face,
    survives a 2-damage block and deals its own 7 back - both P/T numbers
    have to be real for this to come out right (see the file docstring on
    what fixing only one of them would do).
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Drowner of Truth"])
        .player("bob", battlefield=["Giant Spider"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    drowner = scenario.creature("Drowner of Truth // Drowned Jungle", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(drowner)
    scenario.block(drowner, spider)
    scenario.combat_damage()

    assert spider.zone is Zone.GRAVEYARD, "7 damage is lethal to a 2/4"
    assert drowner.zone is Zone.BATTLEFIELD, "2 damage is not lethal to a 7/6"
    assert drowner.damage == 2


def test_witch_enchanter_cast_as_a_creature_has_its_printed_ability():
    """Witch Enchanter's own "when this creature enters, destroy target
    artifact or enchantment" is on the front face's oracle text, which used to
    read as empty (the top-level `oracle_text` is null for a modal
    double-faced card) - `test_mdfc_land_play.py` already covers the mirror
    case, the land face carrying none of this.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Witch Enchanter"],
            battlefield=["Plains", "Plains", "Plains", "Plains"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)
    scenario.choose_trigger_targets("Witch Enchanter", [sol_ring])
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")

    witch = scenario.cast_and_resolve("Witch Enchanter", *sources)
    assert witch.types == (Type.CREATURE,)
    assert witch.power == 2
    assert witch.toughness == 2

    scenario.pass_until_resolved()

    assert sol_ring.zone is Zone.GRAVEYARD, "the printed enters-the-battlefield trigger fired"

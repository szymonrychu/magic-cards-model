"""Scenario: what an Aura or an Equipment says about the creature it is on.

Two printed phrasings, one fact. **CR 301.5a** - "The creature an Equipment is
attached to is called the 'equipped creature'" - and **CR 303.4b** - "The object
or player an Aura is attached to is called enchanted. The Aura is attached to,
or 'enchants,' that object" - name the same link, `CardState.attached_to`.
`machines/layers.py` read only the Equipment half, so five printings in the pool
carried a real static ability that happened nowhere and was logged nowhere:
Rancor, Hyena Umbra, Detective's Phoenix, Umbral Mantle and Unable to Scream.

What lands where:

- **CR 613.4c** - "Layer 7c: Effects and counters that modify power and/or
  toughness (but don't set ...)" - the "+N/+N" half.
- **CR 613.4b** - "Layer 7b: Effects that set power and/or toughness to a
  specific number or value ... Effects that refer to the base power and/or
  toughness of a creature apply in this layer" - Unable to Scream's "base power
  and toughness 0/2".
- **CR 613.1f** - "Layer 6: Ability-adding effects, keyword counters,
  ability-removing effects ..." - every "has <keyword>", the quoted ability, and
  Unable to Scream's "loses all abilities".
- **CR 613.1d** - "Layer 4: Type-changing effects are applied" - with CR 205.1b
  for "in addition to its other types".
- **CR 613.6** - one ability whose parts belong in different layers applies in
  each of them, which is what "gets +2/+0 and has trample" is.
- **CR 113.10a** - "An effect that adds an activated ability may include
  activation instructions for that ability. These instructions become part of
  the ability that's added to the object" - Umbral Mantle's quoted line.
- **CR 604.2** - a static ability's effects "are active as long as the permanent
  with the ability remains on the battlefield and has the ability", which is why
  unattaching takes the grant back off.
- **CR 704.5m** is the state-based action for an Aura attached to nothing;
  `test_aura_attachment.py` owns that, and this file only relies on it.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote it, and every card's text read with
`resolve_cards` or straight off its fixture.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def permanent(name: str, controller: str = "alice"):
    return card_state(name, zone=Zone.BATTLEFIELD, controller=controller, owner=controller)


def board_of(*permanents):
    """The characteristics of a battlefield with only its static abilities
    applied - CR 613.7a's timestamp order is the argument order."""
    cards = list(permanents)
    return compute_board(cards, static_effects(cards))


# --------------------------------------------------------------------------
# The happy path, played for real
# --------------------------------------------------------------------------


def test_rancor_cast_on_a_bear_pumps_it_and_grants_trample():
    """Rancor: "Enchanted creature gets +2/+0 and has trample."

    Cast and resolved through the engine, so the attachment is CR 608.3c's own
    and not one made by hand. A 2/2 becomes a 4/2 (CR 613.4c) and gains trample
    (CR 613.1f) from the one sentence (CR 613.6).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Rancor"], battlefield=["Grizzly Bears", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    rancor = scenario.cast_and_resolve("Rancor", forest, targets=[bears])
    assert rancor.attached_to == bears.id

    board = board_of(rancor, bears)
    assert board.of(bears).power_toughness == (4, 2)
    assert board.of(bears).has_ability("Trample")


def test_hyena_umbra_grants_a_keyword_and_a_pt_change_from_one_sentence():
    """Hyena Umbra: "Enchanted creature gets +1/+1 and has first strike."

    The two halves are the two layers CR 613.6 splits the ability across -
    sublayer 7c (CR 613.4c) and layer 6 (CR 613.1f) - and the point of asserting
    both is that neither is a side effect of the other: a card can grant a
    keyword with no P/T change and the other way round.
    """
    umbra = permanent("Hyena Umbra")
    bears = permanent("Grizzly Bears")
    umbra.attach_to(bears)

    board = board_of(umbra, bears)
    assert board.of(bears).power_toughness == (3, 3)
    assert board.of(bears).has_ability("First strike")


def test_detectives_phoenix_grants_two_keywords_at_once():
    """Detective's Phoenix: "Enchanted creature gets +2/+2 and has flying and
    haste." - an enchantment *creature* whose bestow half prints the same
    attached-creature sentence every Aura does (CR 702.103a's bestow makes it an
    Aura while attached). Each keyword is its own layer-6 grant (CR 613.1f).
    """
    phoenix = permanent("Detective's Phoenix")
    bears = permanent("Grizzly Bears")
    phoenix.attach_to(bears)

    board = board_of(phoenix, bears)
    assert board.of(bears).power_toughness == (4, 4)
    assert board.of(bears).has_ability("Flying")
    assert board.of(bears).has_ability("Haste")


# --------------------------------------------------------------------------
# Only the attached creature, and only while it is attached
# --------------------------------------------------------------------------


def test_an_aura_pumps_only_the_creature_it_is_attached_to():
    """Attachment is not a characteristic and never reaches the board, so the
    subject is the Aura's own `attached_to` link (CR 303.4b) - a second copy of
    the same creature is untouched.
    """
    rancor = permanent("Rancor")
    enchanted = permanent("Grizzly Bears")
    other = permanent("Grizzly Bears")
    rancor.attach_to(enchanted)

    board = board_of(rancor, enchanted, other)
    assert board.of(enchanted).power_toughness == (4, 2)
    assert board.of(other).power_toughness == (2, 2), "a printed 2/2, untouched"
    assert not board.of(other).has_ability("Trample")


def test_an_unattached_aura_grants_nothing():
    """CR 303.4b names the enchanted object; with nothing attached there is no
    object to name, so the ability produces no effect at all. (An Aura does not
    stay in this state - CR 704.5m bins it - but the layer engine is asked about
    the board as it stands, and the answer has to be "nothing".)
    """
    rancor = permanent("Rancor")
    bears = permanent("Grizzly Bears")

    assert rancor.attached_to is None
    assert board_of(rancor, bears).of(bears).power_toughness == (2, 2)


def test_the_pump_goes_away_when_the_enchanted_creature_leaves():
    """CR 604.2: the effect is active only while its source is on the
    battlefield with the ability - and CR 400.7 makes the creature that left a
    new object, so a *replacement* copy is never the enchanted one.

    Rancor stays attached to an id that is no longer on the battlefield. The
    replacement Bear is a plain 2/2, and the Aura itself is on its way to the
    graveyard (CR 704.5m).
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Rancor"], battlefield=["Grizzly Bears", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    enchanted = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    rancor = scenario.cast_and_resolve("Rancor", forest, targets=[enchanted])

    scenario.game.destroy(enchanted)
    assert enchanted.zone is Zone.GRAVEYARD

    replacement = permanent("Grizzly Bears")
    board = board_of(rancor, replacement)
    assert board.of(replacement).power_toughness == (2, 2)
    assert not board.of(replacement).has_ability("Trample")


# --------------------------------------------------------------------------
# A quoted ability, granted whole (CR 113.10a)
# --------------------------------------------------------------------------


MANTLE_ABILITY = "{3}, {Q}: This creature gets +2/+2 until end of turn."


def test_umbral_mantle_grants_the_quoted_ability_to_the_equipped_creature():
    """Umbral Mantle: `Equipped creature has "{3}, {Q}: This creature gets +2/+2
    until end of turn."`

    CR 113.10a: the quoted text, activation instructions and all, becomes an
    ability of the object. It arrives twice over, because the two questions are
    asked in two different places: layer 6 puts it into the creature's computed
    characteristics (CR 613.1f), and `Game.activated_abilities` reads
    `CardState.granted_ability_texts`, which the battlefield sweep keeps in step.
    """
    scenario = Scenario().player("alice", battlefield=["Umbral Mantle", "Grizzly Bears"]).build()
    mantle = scenario.find("Umbral Mantle", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mantle.attach_to(bears)

    board = board_of(mantle, bears)
    assert board.of(bears).has_ability(MANTLE_ABILITY)
    assert bears.granted_ability_texts == (MANTLE_ABILITY,)

    (granted,) = scenario.game.activated_abilities(bears)
    assert granted.cost == "{3}, {Q}", "CR 113.10a keeps the activation instructions"
    assert granted.effect == "This creature gets +2/+2 until end of turn."


def test_the_quoted_ability_is_taken_back_off_when_the_equipment_comes_off():
    """CR 604.2 again: the grant lasts exactly as long as the attachment does.

    A stored `granted_ability_texts` that is only ever appended to would leave
    the creature able to activate an ability nothing is granting it, which is
    the failure mode the sweep reconciles rather than appends to avoid.
    """
    scenario = Scenario().player("alice", battlefield=["Umbral Mantle", "Grizzly Bears"]).build()
    mantle = scenario.find("Umbral Mantle", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mantle.attach_to(bears)
    board_of(mantle, bears)
    assert bears.granted_ability_texts == (MANTLE_ABILITY,)

    mantle.unattach()
    board = board_of(mantle, bears)

    assert bears.granted_ability_texts == ()
    assert not board.of(bears).has_ability(MANTLE_ABILITY)
    assert scenario.game.activated_abilities(bears) == []


# --------------------------------------------------------------------------
# Losing everything and becoming something else (CR 613.6 across three layers)
# --------------------------------------------------------------------------


def test_unable_to_scream_strips_the_creature_and_rebuilds_it():
    """Unable to Scream: "Enchanted creature loses all abilities and is a Toy
    artifact creature with base power and toughness 0/2 in addition to its other
    types."

    One sentence in three layers (CR 613.6): layer 6 removes the abilities
    (CR 613.1f), layer 4 adds artifact and the Toy creature type (CR 613.1d,
    CR 205.1b's "in addition to its other types" - so the Elemental Turtle is
    still an Elemental Turtle), and sublayer 7b sets the base 0/2 (CR 613.4b).

    Fecund Greenshell is the subject because it has a printed ability worth
    losing - reach - and a printed 4/6 worth overwriting.
    """
    aura = permanent("Unable to Scream")
    turtle = permanent("Fecund Greenshell")
    aura.attach_to(turtle)

    board = board_of(aura, turtle)
    characteristics = board.of(turtle)

    assert characteristics.power_toughness == (0, 2)
    assert characteristics.abilities == (), "layer 6 took every one of them"
    assert Type.ARTIFACT in characteristics.types
    assert Type.CREATURE in characteristics.types
    assert Type.ENCHANTMENT not in characteristics.types
    assert "Toy" in characteristics.subtypes
    assert "Turtle" in characteristics.subtypes, "CR 205.1b keeps the old types"


def test_unable_to_scream_does_nothing_while_it_is_attached_to_nothing():
    """The same "no enchanted object, no effect" rule the pump shape has - and
    worth its own case, because this shape writes in three layers and a
    half-applied one would be a 0/2 that kept its abilities.
    """
    aura = permanent("Unable to Scream")
    turtle = permanent("Fecund Greenshell")

    board = board_of(aura, turtle)
    assert board.of(turtle).power_toughness == (4, 6)
    assert board.of(turtle).abilities


# --------------------------------------------------------------------------
# The Equipment half, which must keep working
# --------------------------------------------------------------------------


def test_the_equipment_phrasing_still_reads_the_same_way():
    """Cori-Steel Cutter: "Equipped creature gets +1/+1 and has trample and
    haste." - the phrasing that already worked before "Enchanted creature ..."
    joined it in the same regex (CR 301.5a).
    """
    cutter = permanent("Cori-Steel Cutter")
    bears = permanent("Grizzly Bears")
    cutter.attach_to(bears)

    board = board_of(cutter, bears)
    assert board.of(bears).power_toughness == (3, 3)
    assert board.of(bears).has_ability("Trample")
    assert board.of(bears).has_ability("Haste")


def test_the_monster_role_token_reads_its_own_printed_sentence():
    """CR 111.10k states the Monster Role token's text in full: "a colorless
    Aura Role enchantment token named Monster with enchant creature and
    'Enchanted creature gets +1/+1 and has trample.'"

    It had a hand-written registry row keyed on the token's *name* while
    "Enchanted creature" was unreadable. It is the same sentence Rancor prints,
    so the row is gone and the token is read like any other permanent - which is
    what `test_layer_effects_registry_is_minimal.py` demands.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Monstrous Rage"], battlefield=["Mountain", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Monstrous Rage", mountain, targets=[bears])

    role = scenario.find("Monster", Zone.BATTLEFIELD, "alice")
    assert role.attached_to == bears.id

    board = board_of(role, bears)
    assert board.of(bears).power_toughness == (3, 3)
    assert board.of(bears).has_ability("Trample")

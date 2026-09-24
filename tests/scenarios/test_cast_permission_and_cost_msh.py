"""Cast permission and cost-change templates from Marvel Super Heroes (task
C02-T7):

- **Captain Mar-Vell, Space-Born** - "Cosmic Awareness — As long as an
  opponent has cast a spell this turn, you may cast spells as though they
  had flash." Widens `Game.has_first_spell_flash_grant` additively with
  `Game.has_static_spells_flash_grant`, and widens `_CONDITION_CAST_A_
  SPELL_THIS_TURN` to read an opponent as well as the controller. High Fae
  Trickster (real Modern/Pioneer/Standard-legal Scryfall printing, added
  with `add_card.py`, not in any api deck list) proves the unconditional
  half of the same grant; the conditional half is proven on Captain
  Mar-Vell alone (both states of the condition exercised).
- **Ironheart, Clever Champion** - "Noncreature spells you cast have
  improvise." `Game.has_granted_improvise`, wired into both `objects_as_
  costs.improvise`'s gate (a new `granted` parameter) and `Game.object_
  cost_offers`. Inspiring Statuary's real "Nonartifact spells you cast have
  improvise." proves the negated-type half of the same reader.
- **The Scarlet Witch** - "Instant and sorcery spells you cast with mana
  value 4 or greater cost `{X}` less to cast, where X is The Scarlet
  Witch's power." `Game._type_mv_threshold_cost_less_self_power`, wired
  into `Game.static_cost_modifiers_for` beside the pre-existing
  `cost_modifier_effect` dispatch. No second real printing carries this
  exact shape (checked against the Scryfall bulk snapshot this session);
  proven on The Scarlet Witch alone, exercising the mana-value threshold,
  a change in power, and the "never below its own type floor" corner case.
- **Titania, Rugged Rumbler** - "As an additional cost to cast this spell,
  discard a card or pay `{2}`." No new code: CR 601.2b's "[cost] or pay
  [mana]" additional-cost shape is already general
  (`test_additional_cost_alternatives.py`'s own Silence the Echo/Bayou
  Groff), and `Casting`'s `discarding=`/plain payment already reaches it.
  Proven here as this task's own listed card.
- **Raft Security Officer** - "This ability costs `{1}` less to activate if
  it targets a creature with power 3 or less." `Game._activation_target_
  cost_reduction`, reading `begin_activating`'s own announced `targets`
  (CR 601.2c, before CR 601.2f prices the cost) - a genuinely new hook,
  since no existing activation-cost reduction reads a *target* at all. No
  second real printing carries this exact shape; proven on Raft Security
  Officer alone, both sides of the power-3 threshold.
- **Jessica Jones, Private Eye** - "`{T}`, Put a stun counter on Jessica
  Jones: Exile the top X cards of your library, where X is Jessica Jones's
  power. You may play those cards this turn." The exile-and-play permission
  itself is `_parse_exile_then_play_permission_clauses`'s own shape
  (C01-T3's reader, reused unmodified); this task adds only the "Put a
  stun counter on `<self>`" cost (CR 201.5 self-normalization reaching
  `machines/cost.cost_component_for_phrase`, which already read the
  normalized shape) and the "the top X cards ..., where X is `<self>`'s
  power" count (`amount_expression` against the ability's own source,
  widening `_EXILE_TOP_OF_YOUR_LIBRARY_RE`).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 702.8a** - flash; **CR 601.3b** - "as though it had flash" grants.
- **CR 702.126a** - improvise; **CR 113.6** - a static ability can grant an
  ability a card does not otherwise have.
- **CR 601.2f** - cost increases and reductions, applied once, in the order
  the controller chooses among simultaneous ones.
- **CR 613.1(7c)** - power/toughness-changing effects (the live power The
  Scarlet Witch's and Jessica Jones's own readers both measure).
- **CR 601.2b** - "[cost] or pay [mana]" additional costs; CR 118.8a - "As
  an additional cost to cast this spell."
- **CR 602.2b** - an activation follows CR 601.2's steps, targets (601.2c)
  announced before the total cost (601.2f) is determined.
- **CR 122.1** - a stun counter, placed by a cost the same way any other
  counter-placing cost is (CR 118.8a already covers "put a counter" costs
  generally through `cost_component_for_phrase`).
- **CR 107.3f** - "where X is `<value>`", a self-defined X with no
  announcement.
- **CR 201.5** - "if an object's text uses its own name, it refers to that
  particular object" - Jessica Jones's own cost sentence, Titania's is not
  self-referential at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.objects_as_costs import has_improvise, improvise
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Captain Mar-Vell, Space-Born ---------------------------------------


def test_mar_vell_grants_flash_once_an_opponent_has_cast_a_spell_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Captain Mar-Vell, Space-Born"],
            hand=["Grizzly Bears"],
            library=[],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    mountain = scenario.untapped_sources("Mountain", username="bob")[0]
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=["alice"])

    assert scenario.game.has_static_spells_flash_grant(
        "alice", scenario.find("Grizzly Bears", Zone.HAND, "alice")
    )


def test_mar_vell_grants_nothing_before_any_opponent_has_cast_a_spell():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Captain Mar-Vell, Space-Born"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    assert scenario.game.has_static_spells_flash_grant("alice", bears) is False


def test_high_fae_trickster_second_printing_grants_flash_unconditionally():
    scenario = (
        Scenario()
        .player("alice", battlefield=["High Fae Trickster"], hand=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    assert scenario.game.has_static_spells_flash_grant("alice", bears) is True


# -- Ironheart, Clever Champion -------------------------------------------


def test_ironheart_grants_improvise_to_a_noncreature_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Ironheart, Clever Champion",
                "Island",
                "Cosmic Cube",
                "Cosmic Cube",
                "Cosmic Cube",
            ],
            hand=["Stolen Goods"],
        )
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stolen_goods = scenario.find("Stolen Goods", Zone.HAND, "alice")
    assert has_improvise(stolen_goods.card) is False
    assert scenario.game.has_granted_improvise("alice", stolen_goods) is True

    casting = scenario.cast("Stolen Goods")
    casting.choose_targets(["bob"])
    payment = casting.begin_paying()
    cubes = [state for state in scenario.game.battlefield if state.name == "Cosmic Cube"]
    improvise(payment, stolen_goods, *cubes, granted=True)
    island = scenario.untapped_sources("Island")[0]
    scenario.pay_with(payment, island)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert all(cube.tapped for cube in cubes)
    assert stolen_goods.zone is Zone.GRAVEYARD


def test_ironheart_grants_nothing_to_a_creature_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ironheart, Clever Champion"],
            hand=["Grizzly Bears"],
        )
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    assert scenario.game.has_granted_improvise("alice", bears) is False


def test_inspiring_statuary_second_printing_grants_improvise_to_nonartifact_spells():
    scenario = (
        Scenario()
        .player(
            "alice", battlefield=["Inspiring Statuary"], hand=["Grizzly Bears", "Lightning Bolt"]
        )
        .build()
    )
    bears = scenario.find("Grizzly Bears", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    assert scenario.game.has_granted_improvise("alice", bears) is True
    assert scenario.game.has_granted_improvise("alice", bolt) is True


# -- The Scarlet Witch -----------------------------------------------------


def test_scarlet_witch_reduces_a_high_mv_sorcery_by_her_own_power():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Scarlet Witch"],
            hand=["Worlds Within Worlds"],
            library=[],
        )
        .player("bob")
        .build()
    )
    reduction = scenario.game.static_cost_modifiers_for(
        scenario.find("Worlds Within Worlds", Zone.HAND, "alice"), "alice"
    )
    increases, decreases, floor = reduction
    assert increases == []
    assert floor is None
    assert str(decreases[0]) == "{2}"  # The Scarlet Witch is a 2/3


def test_scarlet_witch_does_not_reduce_a_spell_under_the_mana_value_threshold():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Scarlet Witch"], hand=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    _, decreases, _ = scenario.game.static_cost_modifiers_for(
        scenario.find("Lightning Bolt", Zone.HAND, "alice"), "alice"
    )
    assert decreases == []


def test_scarlet_witch_does_not_reduce_a_creature_spell():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Scarlet Witch"], hand=["Craw Wurm"])
        .player("bob")
        .build()
    )
    _, decreases, _ = scenario.game.static_cost_modifiers_for(
        scenario.find("Craw Wurm", Zone.HAND, "alice"), "alice"
    )
    assert decreases == []


# -- Titania, Rugged Rumbler ------------------------------------------------


def test_titania_can_be_cast_by_discarding_a_card_instead_of_paying_two_more():
    scenario = (
        Scenario()
        .player("alice", hand=["Titania, Rugged Rumbler", "Forest"], battlefield=["Swamp"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Titania, Rugged Rumbler", *sources, discarding=[forest])

    assert forest.zone is Zone.GRAVEYARD
    titania = scenario.creature("Titania, Rugged Rumbler", "alice")
    assert titania.zone is Zone.BATTLEFIELD


def test_titania_can_be_cast_by_paying_two_more_mana_instead():
    scenario = (
        Scenario()
        .player("alice", hand=["Titania, Rugged Rumbler"], battlefield=["Swamp"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")

    scenario.cast_and_resolve("Titania, Rugged Rumbler", *sources)

    titania = scenario.creature("Titania, Rugged Rumbler", "alice")
    assert titania.zone is Zone.BATTLEFIELD
    assert all(source.tapped for source in sources)


# -- Raft Security Officer --------------------------------------------------


def test_raft_security_officer_costs_less_against_a_low_power_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raft Security Officer", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    officer = scenario.creature("Raft Security Officer", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    mountain = scenario.untapped_sources("Mountain")[0]

    scenario.activate(officer, mountain, targets=[bears])
    scenario.resolve_top()

    assert bears.tapped is True
    assert mountain.tapped is True  # {1} paid, not {2}


def test_raft_security_officer_costs_full_against_a_high_power_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raft Security Officer", "Mountain", "Mountain"])
        .player("bob", battlefield=["Craw Wurm"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    officer = scenario.creature("Raft Security Officer", "alice")
    wurm = scenario.creature("Craw Wurm", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain")

    scenario.activate(officer, *mountains, targets=[wurm])
    scenario.resolve_top()

    assert wurm.tapped is True
    assert all(source.tapped for source in mountains)  # full {2} paid


# -- Jessica Jones, Private Eye ---------------------------------------------


def test_jessica_jones_pays_a_stun_counter_and_exiles_cards_equal_to_her_power():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Jessica Jones, Private Eye"],
            library=["Forest", "Island", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    jessica = scenario.creature("Jessica Jones, Private Eye", "alice")

    scenario.activate(jessica)
    scenario.resolve_top()

    assert jessica.counters.counts.get("stun", 0) == 1
    assert jessica.tapped is True
    exiled = {state.name for state in scenario.game.exile}
    assert exiled == {"Forest", "Island"}  # Jessica Jones is a 2/3
    for state in scenario.game.exile:
        permission = scenario.game.play_permission_for(state, "alice")
        assert permission is not None
        assert permission.action is PlayAction.PLAY
        assert permission.until_end_of_turn is True
    assert [state.name for state in scenario.player("alice").library] == ["Mountain"]

"""Flashback with a behold-N cost (CR 702.34a, CR 701.4a): Kindle the Inner
Flame's "Flashback-{1}{R}, Behold three Elementals."

Two new readers meet here:

- `machines/cost.py`'s `_PHRASE_BEHOLD_N` ("behold `<count>` `<plural
  quality>`", no article) - `_PHRASE_BEHOLD`'s own singular, articled
  "behold a `<quality>`" already worked; this is the counted form no card
  printed until this set. `total_cost_for_phrase`'s own "," / " and "
  splitter also needed a fix alongside it: "behold a Kithkin and exile it"
  and "{1}{R}, Behold three Elementals" both put a bare " and "/", " inside
  a single cost component's own phrase, which the splitter was cutting in
  two before either reader ever saw the whole thing.
- The front side's own "Create a token that's a copy of target creature you
  control, except it has haste and '...'" reuses sos-T7's landed copy-
  token-with-exceptions reader (`_read_token_copy_except`, widened here for
  a keyword-then-quoted mixed tail) - proven again here on a second such
  tail, not duplicated.

No second printing exists for the counted "Behold `<N>` `<plural type>`"
shape itself: Scryfall's own oracle-text search (`o:/behold
(two|three|four)/`, this session) returns only Kindle the Inner Flame and
Celestial Reunion, both listed cards for this task - see `MEMORY.md`'s
dated line. Generality instead rests on `_behold_n_requirement` reusing the
same `canonical_subtype`/`_requirement` machinery the singular form (proven
by `test_behold.py`, `test_behold_costs.py`) already goes through, once the
plural noun is singularised.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.machines.cost import total_cost_for_phrase
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_front_side_copies_a_creature_with_haste_and_end_step_sacrifice():
    """ "Create a token that's a copy of target creature you control, except
    it has haste and 'At the beginning of the end step, sacrifice this
    token.'" - no flashback, no behold, the plain front-side cast."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kindle the Inner Flame"],
            battlefield=["Mountain"] * 4 + ["Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")

    scenario.cast_and_resolve("Kindle the Inner Flame", *sources, targets=[bears])

    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Grizzly Bears"
    ]
    assert len(tokens) == 1
    token = tokens[0]
    assert has_keyword(token, "Haste", scenario.game)

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    assert token.zone is Zone.GRAVEYARD


def test_flashback_pays_behold_three_elementals_from_hand():
    """Three Elemental cards revealed from hand pay the flashback's own
    behold-N cost; the card is exiled afterward (CR 702.34a's own second
    static ability)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Kindle the Inner Flame"],
            hand=[
                "Akoum Hellhound",
                "Akoum Hellhound",
                "Akoum Hellhound",
            ],
            battlefield=["Mountain", "Mountain", "Akoum Hellhound"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elementals = list(scenario.player("alice").hand)
    battlefield_target = scenario.creature("Akoum Hellhound", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Kindle the Inner Flame", "alice", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback", choosing=elementals)
    casting.choose_targets([battlefield_target])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    kindle = scenario.put_on_stack(casting)

    for card in elementals:
        assert card.zone is Zone.HAND, "CR 701.20b: a hand-half behold leaves the card in hand"

    scenario.pass_until_resolved()

    assert kindle.zone is Zone.EXILE
    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Akoum Hellhound"
    ]
    assert len(tokens) == 1


def test_flashback_pays_behold_three_elementals_by_choosing_battlefield_permanents():
    """The other half of CR 701.4a: three Elementals already on the
    battlefield, chosen rather than revealed - CR 701.4b leaves them
    untouched."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Kindle the Inner Flame"],
            battlefield=(
                ["Mountain", "Mountain"] + ["Akoum Hellhound", "Akoum Hellhound", "Akoum Hellhound"]
            ),
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    battlefield_elementals = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Akoum Hellhound"
    ]
    assert len(battlefield_elementals) == 3
    sources = scenario.untapped_sources("Mountain", "Mountain")

    casting = scenario.cast("Kindle the Inner Flame", "alice", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback", choosing=battlefield_elementals)
    casting.choose_targets([battlefield_elementals[0]])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    kindle = scenario.put_on_stack(casting)

    for state in battlefield_elementals:
        assert state.zone is Zone.BATTLEFIELD
        assert not state.tapped

    scenario.pass_until_resolved()

    assert kindle.zone is Zone.EXILE


def test_flashback_refuses_fewer_than_three_elementals():
    """CR 118.3: the behold-N cost must be paid in full - two is not enough."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Kindle the Inner Flame"],
            battlefield=["Mountain", "Mountain", "Akoum Hellhound", "Akoum Hellhound"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    two_elementals = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.name == "Akoum Hellhound"
    ]
    assert len(two_elementals) == 2

    casting = scenario.cast("Kindle the Inner Flame", "alice", from_zone=Zone.GRAVEYARD)
    casting.use_keyword("Flashback", choosing=two_elementals)
    payment = casting.begin_paying()
    try:
        payment.pay()
        paid = True
    except ValueError:
        paid = False
    assert not paid


def test_total_cost_for_phrase_reads_the_whole_behold_n_cost():
    """The regression this task's own splitter fix guards: "{1}{R}, Behold
    three Elementals" used to come back `None` because `_split_cost_phrase`
    cut the bare " and " out of the *other* behold shape ("behold a Kithkin
    and exile it") - fixed by trying the whole, un-split phrase first when
    there is no comma to say the cost is genuinely a list. Proven directly
    here since `test_behold_costs.py`/`test_flashback_behold.py`'s own
    scenario tests already prove the paid-cost behaviour end to end."""
    cost = total_cost_for_phrase("{1}{R}, Behold three Elementals")
    assert cost is not None
    assert cost.mana.converted == 2
    assert len(cost.components) == 1
    assert cost.components[0].required == 3

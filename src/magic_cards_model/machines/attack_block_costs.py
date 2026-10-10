"""Costs to attack or block (CR 508.1h, 509.1d) beyond Ghostly Prison's "attacking
you" wording (`combat.attack_costs_against`):

- "[As long as this creature is untapped,] creatures can't attack you or
  planeswalkers you control unless their controller pays <cost> for each of
  those creatures[, where X is ...]." (Archon of Absolution, Baird, Norn's
  Annex, Sphere of Safety, Archangel of Tithes)
- "As long as this creature is attacking, creatures can't block unless their
  controller pays <cost> for each of those creatures." (Archangel of Tithes)
- "This creature can't attack or block unless you pay <cost>[ for each <thing>
  on it]." (Qal Sisma Behemoth, Myr Prototype)
- "Enchanted creature can't attack or block unless its controller pays <cost>"
  (Oppressive Rays, Cowed by Wisdom's "{1} for each card in your hand")
- "This creature can't attack unless you return <a permanent> you control to
  its owner's hand." (Floodtide Serpent) - a non-mana cost, chosen and paid
  with the declaration by `Game._pay_attack_costs`.

CR 508.1d: the player "is not required to pay" such a cost, so an attack the
cost makes unaffordable is refused whole by `Game._pay_attack_costs` (CR
508.1j), never forced. The block twin is `Game._pay_block_costs` (CR 509.1f).
"""

import re
from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.card_state import CardState
from ..models.mana import ManaCost

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.game import Game
    from .combat import AttackCost

_COST = r"(?:\{[^}]+\})+"
_GATE = r"(?:as long as (?P<gate_subject>.+?) is (?P<gate_state>untapped|attacking), )?"
_GROUP_COST_RE = re.compile(
    rf"^{_GATE}creatures can't (?P<what>attack|block)"
    r"(?P<target> you or planeswalkers you control)? unless their controller pays "
    rf"(?P<cost>{_COST}) for each of those creatures(?P<where>, where X is .+?)?\.?$",
    re.IGNORECASE,
)
_SELF_COST_RE = re.compile(
    rf"^(?P<subject>.+?) can't (?P<what>attack or block|attack|block) unless you pay "
    rf"(?P<cost>{_COST}.*?)\.?$",
    re.IGNORECASE,
)
_RETURN_COST_RE = re.compile(
    r"^(?P<subject>.+?) can't attack unless you return an? (?P<kind>[a-z]+) you control "
    r"to its owner's hand\.?$",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(
    rf"^(?P<cost>{_COST})(?: for each (?P<each>.+?))?(?:, where X is (?P<x>.+?))?$",
    re.IGNORECASE,
)
_COUNTER_EACH_RE = re.compile(r"^(?P<kind>[+\-0-9/]+) counter on it$", re.IGNORECASE)
_PER_CHARGED = frozenset({"of those creatures"})


def _each_readable(each: str | None) -> bool:
    if each is None:
        return True
    lowered = each.strip().lower()
    return (
        lowered in _PER_CHARGED
        or _COUNTER_EACH_RE.fullmatch(lowered) is not None
        or lowered == "card in your hand"
    )


def _amount_readable(text: str) -> bool:
    from .effects import count_expression

    match = _AMOUNT_RE.fullmatch(text.strip())
    if match is None or ManaCost.try_parse(match["cost"]) is None:
        return False
    if not _each_readable(match["each"]):
        return False
    return match["x"] is None or count_expression(match["x"]) is not None


def _amount(game: "Game", text: str, source: CardState, subject: CardState) -> ManaCost | None:
    """The mana one charged creature owes for `text` (already per creature),
    read when asked (CR 508.1h locks it in once the declaration is made)."""
    from .effects import count_expression

    match = _AMOUNT_RE.fullmatch(text.strip())
    if match is None:
        return None
    cost = ManaCost.try_parse(match["cost"])
    if cost is None:
        return None
    controller = game.controller_of(source).username or ""
    if match["x"] is not None:
        reader = count_expression(match["x"])
        if reader is None:
            return None
        cost = cost.with_x(reader(game, controller))
    each = (match["each"] or "").strip().lower()
    if not each or each in _PER_CHARGED:
        return cost
    if counter := _COUNTER_EACH_RE.fullmatch(each):
        held = game.characteristics_of(subject).counters
        times = sum(
            count for key, count in held.items() if str(key).lower() == counter["kind"].lower()
        )
    elif each == "card in your hand":
        times = len(game.player(controller).hand)
    else:
        return None
    total = ManaCost.parse("")
    for _ in range(times):
        total = total.plus(cost)
    return total


def _gate_holds(game: "Game", source: CardState, match: "re.Match[str]") -> bool:
    from .combat import _self_reference_names

    if match["gate_state"] is None:
        return True
    subject = match["gate_subject"].strip().lower()
    if subject not in {name.lower() for name in _self_reference_names(source.name)}:
        return False
    if match["gate_state"].lower() == "untapped":
        return not source.tapped
    return game.combat is not None and game.combat.attack_by(source.id) is not None


def _static_sentences(game: "Game", needle: str):
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        for ability in board.of(source).abilities:
            if needle not in ability.lower():
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                yield source, sentence.strip()


def _is_self(subject: str, source: CardState) -> bool:
    from .combat import _self_reference_alternatives

    return subject.strip().lower() in {n.lower() for n in _self_reference_alternatives(source)}


def _charges(game: "Game", creature: CardState, action: str, defender) -> "list[AttackCost]":
    from .combat import AttackCost, _is_planeswalker_controlled_by

    charges: list[AttackCost] = []

    def add(source: CardState, text: str, sentence: str) -> None:
        cost = _amount(game, text, source, creature)
        if cost is not None and cost.symbols:
            charges.append(AttackCost(source, cost, sentence))

    for source, sentence in _static_sentences(game, "unless"):
        if match := _GROUP_COST_RE.fullmatch(sentence):
            if match["what"].lower() != action or not _gate_holds(game, source, match):
                continue
            if action == "attack":
                controller = game.controller_of(source).username
                on_you = defender.is_player and defender.username == controller
                if not (
                    match["target"]
                    and (on_you or _is_planeswalker_controlled_by(game, defender, controller))
                ):
                    continue
            add(source, match["cost"] + (match["where"] or ""), sentence)
        elif match := _SELF_COST_RE.fullmatch(sentence):
            if (
                action in match["what"].lower().split(" or ")
                and source.id == creature.id
                and _is_self(match["subject"], source)
            ):
                add(source, match["cost"], sentence)
    from .attached_restrictions import attached_charges

    for source, text, sentence in attached_charges(game, creature, action):
        add(source, text, sentence)
    return charges


def attack_costs(game: "Game", creature: CardState, defender) -> "list[AttackCost]":
    """`combat.AttackCost` entries charged to `creature` attacking `defender`."""
    return _charges(game, creature, "attack", defender)


def block_costs(game: "Game", blocker: CardState) -> "list[AttackCost]":
    """The mana costs charged to `blocker` blocking (CR 509.1d)."""
    return _charges(game, blocker, "block", None)


# -- "unless you return <a permanent> you control" (Floodtide Serpent) --------


def _return_sentences(game: "Game", creature: CardState):
    for sentence in _creature_sentences(game, creature):
        match = _RETURN_COST_RE.fullmatch(sentence)
        if match is not None and _is_self(match["subject"], creature):
            yield sentence, match["kind"].lower()


def _creature_sentences(game: "Game", creature: CardState):
    from .combat import _computed_ability_sentences

    yield from _computed_ability_sentences(creature, game)


def _return_candidates(game: "Game", creature: CardState, kind: str) -> list[CardState]:
    controller = game.controller_of(creature).username or ""
    wanted = next((t for t in Type if t.value.lower() == kind), None)
    if wanted is None:
        return []
    return [
        permanent
        for permanent in game.permanents_controlled_by(controller)
        if wanted in game.characteristics_of(permanent).types
    ]


def return_costs(game: "Game", creature: CardState) -> "list[tuple[str, list[CardState]]]":
    """(sentence, permanents that could be returned) for each "unless you
    return ..." cost `creature` carries."""
    return [
        (sentence, _return_candidates(game, creature, kind))
        for sentence, kind in _return_sentences(game, creature)
    ]


def return_cost_refusal(game: "Game", creature: CardState) -> str | None:
    """Why `creature` can't attack for want of a permanent to return (CR
    508.1c: it can't attack unless the cost can be paid, CR 118.3)."""
    for sentence, candidates in return_costs(game, creature):
        if not candidates:
            return (
                f'{creature.name} can\'t attack: "{sentence}" and there is nothing to return '
                "(CR 508.1c)"
            )
    return None


def return_cost_declaration_refusal(game: "Game", attacks) -> str | None:
    """Each returned permanent is a different one: the declaration needs as
    many as it has return costs per kind (CR 118.3, CR 508.1c)."""
    owed: dict[str, int] = {}
    pool: dict[str, set] = {}
    for creature, _defender in attacks:
        for _sentence, kind in _return_sentences(game, creature):
            owed[kind] = owed.get(kind, 0) + 1
            pool.setdefault(kind, {c.id for c in _return_candidates(game, creature, kind)})
    for kind, count in owed.items():
        if len(pool[kind]) < count:
            return (
                f"the declaration needs {count} {kind}s returned to hand to pay for attacking, "
                f"and only {len(pool[kind])} can be (CR 508.1c, CR 118.3)"
            )
    return None


# -- audit ---------------------------------------------------------------------


def reads_attack_block_cost_line(printing: "Card", text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is a cost to attack or block
    the functions above charge."""
    from .attached_restrictions import parse_attached
    from .combat import _self_reference_names
    from .layers import layer_readable_sentences

    if "unless" not in text.lower():
        return False
    names = {name.lower() for name in _self_reference_names(card_name)}
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    if not sentences:
        return False
    for sentence in sentences:
        if match := _GROUP_COST_RE.fullmatch(sentence):
            if match["what"].lower() == "attack" and not match["target"]:
                return False
            if match["gate_subject"] and match["gate_subject"].strip().lower() not in names:
                return False
            if not _amount_readable(match["cost"] + (match["where"] or "")):
                return False
        elif match := _SELF_COST_RE.fullmatch(sentence):
            if match["subject"].strip().lower() not in names or not _amount_readable(match["cost"]):
                return False
        elif match := _RETURN_COST_RE.fullmatch(sentence):
            kinds = {t.value.lower() for t in Type}
            if match["subject"].strip().lower() not in names or match["kind"].lower() not in kinds:
                return False
        else:
            found = parse_attached(sentence)
            if found is None or found.pay is None or not _amount_readable(found.pay):
                return False
    return True

"""Aura/Equipment attack-block restrictions read off the attachment
(CR 508.1c, 509.1b, 508.1d, 602.5).

"Enchanted creature can't attack or block, and its activated abilities can't
be activated." (Arrest, Pacifism-likes), "Enchanted permanent can't attack or
block, and its activated abilities can't be activated unless they're mana
abilities." (Faith's Fetters), "Enchanted creature can't attack." (Forced
Worship), "Enchanted creature can't block.", "Enchanted creature attacks each
combat if able." (Lust for War) and Dog Umbra's "As long as another player
controls enchanted creature, it can't attack or block."

The source is the Aura or Equipment on the battlefield; the subject is whatever
it is attached to (`attached_to`, CR 303.4), read off the computed board when
asked (CR 613.5, CR 611.3a).
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.card_state import CardState
    from ..models.game import Game
    from ..models.mana import ManaCost

_SUBJECT = r"(?:enchanted (?:creature|permanent|artifact|land)|equipped creature|it)"
#: One thing an attachment can forbid: CR 508.1c, CR 509.1b, CR 701.27 (a
#: transform), CR 702.122a (crewing a Vehicle) and CR 702.196b (being returned
#: for a beam me up cost - Marooned's "can't be beamed up").
_ITEM = r"(?:attack|block|transform|crew vehicles|be beamed up)"
_RESTRICTION_RE = re.compile(
    r"^(?P<cond>as long as another player controls enchanted creature, )?"
    rf"(?P<subject>{_SUBJECT})"
    r"(?: is an? (?P<becomes>[a-z]+) and)?"
    r"(?: gets [+-]\d+/[+-]\d+ and)?"
    r"(?: doesn't untap during its controller's untap step and)?"
    rf" can't (?P<what>{_ITEM}(?:(?:, or | or |, | and )(?:{_ITEM}))*)"
    r"(?P<tail>.*?)\.?$",
    re.IGNORECASE,
)
#: "Its activated abilities can't be activated unless they're mana abilities."
#: (Intercessor's Arrest, a sentence of its own) and "Enchanted creature's
#: activated abilities can't be activated." (Detainment Spell).
_DEACTIVATE_SENTENCE_RE = re.compile(
    r"^(?:its|(?:enchanted|equipped) (?:creature|permanent|artifact|land)'s) "
    r"activated abilities can't be activated(?P<mana> unless they're mana abilities)?\.?$",
    re.IGNORECASE,
)
#: "Enchanted permanent doesn't untap during its controller's untap step and
#: its activated abilities can't be activated." (Encrust): the untap half is the
#: layer system's grant (`layers.parse._ATTACHED_DOESNT_UNTAP_RE`), the
#: activation half is read here.
_UNTAP_AND_DEACTIVATE_RE = re.compile(
    r"^(?:enchanted|equipped) (?:creature|permanent|artifact|land) doesn't untap during its "
    r"controller's untap step and its activated abilities can't be activated"
    r"(?P<mana> unless they're mana abilities)?\.?$",
    re.IGNORECASE,
)
_DEACTIVATE_TAIL_RE = re.compile(
    r"^,? and its activated abilities can't be activated(?P<mana> unless they're mana abilities)?$",
    re.IGNORECASE,
)
#: Dog Umbra's second sentence; `replacement/parse._keyword_replacements`
#: gives the Aura umbra armor only while its controller controls the enchanted
#: creature.
CONDITIONAL_UMBRA_RE = re.compile(r"otherwise, this aura has umbra armor", re.IGNORECASE)
_PAY_TAIL_RE = re.compile(r"^ unless its controller pays (?P<cost>.+)$", re.IGNORECASE)
_REQUIREMENT_RE = re.compile(
    r"^(?:enchanted|equipped) creature attacks each combat if able\.?$", re.IGNORECASE
)


@dataclass(frozen=True)
class AttachedRestriction:
    """One parsed attachment sentence."""

    sentence: str
    attack: bool = False
    block: bool = False
    transform: bool = False
    crew: bool = False
    beam: bool = False
    deactivate: bool = False
    mana_exempt: bool = False
    #: "unless its controller pays <cost>" - the cost text, enforced by
    #: `attack_block_costs`.
    pay: str | None = None
    #: Dog Umbra: only while another player controls the enchanted creature.
    needs_other_controller: bool = False
    requirement: bool = False
    #: "... can't be blocked as long as <condition>" / "During your turn, ...
    #: can't be blocked" - evaluated for the attachment's controller when a
    #: blocker is declared (CR 509.1b); the unconditional form is the layer
    #: system's grant of "This creature can't be blocked.".
    evasion: bool = False
    condition: str | None = None
    #: "As long as enchanted permanent is a creature, it gets -1/-1 and can't
    #: block." - the gate is the pump's, and a restriction on a permanent that
    #: is not a creature matters to nothing.
    block_requirement: bool = False


#: "As long as enchanted permanent is a creature, it gets -1/-1 and can't
#: block." (Clawing Torment): the "is a creature" gate is the pump's own - a
#: P/T modification of a noncreature is nothing (CR 613.4c), so the layer
#: grant needs no gate of its own and the sentence reads as the plain
#: "Enchanted creature gets -1/-1 and can't block."
_IS_A_CREATURE_GATE_RE = re.compile(
    r"^as long as (?P<subject>enchanted|equipped) (?:permanent|artifact|land) is a creature, "
    r"it (?P<rest>.+)$",
    re.IGNORECASE,
)
_PREDICATE_PREFIX = r"(?:(?:gets [+-]\d+/[+-]\d+|has [a-z]+(?: and [a-z]+)*?) and )?"
_EVASION_RE = re.compile(
    r"^(?P<during>during your turn, )?(?P<subject>enchanted|equipped) "
    r"(?:creature|permanent|artifact|land) "
    rf"{_PREDICATE_PREFIX}can't be blocked(?: as long as (?P<cond>.+?))?\.?$",
    re.IGNORECASE,
)
_BLOCKS_EACH_COMBAT_RE = re.compile(
    rf"^(?P<subject>enchanted|equipped) creature {_PREDICATE_PREFIX}blocks each combat if able\.?$",
    re.IGNORECASE,
)


def normalize_attached_sentence(sentence: str) -> str:
    """`sentence` with an "as long as enchanted permanent is a creature, it"
    gate folded into its subject (see `_IS_A_CREATURE_GATE_RE`)."""
    match = _IS_A_CREATURE_GATE_RE.fullmatch(sentence.strip())
    if match is None:
        return sentence.strip()
    return f"{match['subject'].capitalize()} creature {match['rest']}"


def parse_attached(sentence: str) -> AttachedRestriction | None:
    """Read one sentence into an `AttachedRestriction`, or None."""
    text = normalize_attached_sentence(sentence)
    evasion = _EVASION_RE.fullmatch(text)
    if evasion is not None and (evasion["cond"] or evasion["during"]):
        cond = evasion["cond"] or "it's your turn"
        return AttachedRestriction(sentence=text, evasion=True, condition=cond)
    if _BLOCKS_EACH_COMBAT_RE.fullmatch(text):
        return AttachedRestriction(sentence=text, block_requirement=True)
    if _REQUIREMENT_RE.fullmatch(text):
        return AttachedRestriction(sentence=text, requirement=True)
    for pattern in (_DEACTIVATE_SENTENCE_RE, _UNTAP_AND_DEACTIVATE_RE):
        found = pattern.fullmatch(text)
        if found is not None:
            return AttachedRestriction(
                sentence=text, deactivate=True, mana_exempt=found["mana"] is not None
            )
    match = _RESTRICTION_RE.fullmatch(text)
    if match is None:
        return None
    tail = match["tail"]
    what = match["what"].lower()
    base = AttachedRestriction(
        sentence=text,
        attack="attack" in what,
        block="block" in what,
        transform="transform" in what,
        crew="crew" in what,
        beam="beamed up" in what,
        needs_other_controller=match["cond"] is not None,
    )
    if not tail.strip():
        return base
    deactivate = _DEACTIVATE_TAIL_RE.fullmatch(tail.strip())
    if deactivate is not None:
        return AttachedRestriction(
            **{**base.__dict__, "deactivate": True, "mana_exempt": deactivate["mana"] is not None}
        )
    pay = _PAY_TAIL_RE.fullmatch(tail)
    if pay is not None:
        return AttachedRestriction(**{**base.__dict__, "pay": pay["cost"]})
    return None


def attached_crew_refusal(game: "Game", creature: "CardState") -> str | None:
    """Why an attachment's "can't ... crew Vehicles" stops `creature` crewing
    (CR 702.122d), or None."""
    for source, restriction in _attached_restrictions(game, creature):
        if restriction.crew:
            return (
                f"{creature.name} can't crew Vehicles: {source.name} says "
                f'"{restriction.sentence}" (CR 702.122d)'
            )
    return None


def attached_beam_refusal(game: "Game", creature: "CardState") -> str | None:
    """Why an attachment's "can't be beamed up" stops `creature` being
    returned to pay a beam me up cost (CR 702.196b), or None."""
    for source, restriction in _attached_restrictions(game, creature):
        if restriction.beam:
            return (
                f'{creature.name} can\'t be beamed up: {source.name} says "{restriction.sentence}" '
                "(CR 702.196b)"
            )
    return None


def attached_transform_refusal(game: "Game", permanent: "CardState") -> str | None:
    """Why an attachment's "can't ... transform" stops `permanent` turning over
    (CR 701.27a), or None."""
    for source, restriction in _attached_restrictions(game, permanent):
        if restriction.transform:
            return (
                f'{permanent.name} can\'t transform: {source.name} says "{restriction.sentence}" '
                "(CR 701.27a)"
            )
    return None


_COMPOUND_RE = re.compile(
    r"^(?P<during>during your turn, )?(?P<subject>(?:enchanted|equipped) "
    r"(?:creature|permanent|artifact|land)) (?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


def _no_effect(source, timestamp, targets, context):  # noqa: ANN001, ANN202
    """A half the attachment readers enforce at the declaration, with nothing
    for the layer system to apply."""
    return []


def _compound_half(subject: str, predicate: str, *, gated: bool):  # noqa: ANN202
    """The layer builder of one "and"-joined half of an attachment sentence: the
    attachment readers' own halves (a restriction, a requirement, a gated
    evasion) apply no layer effect, anything else is a layer shape."""
    from .layers.parse import _parse_layer_sentence_ungated

    sentence = f"{subject} {predicate}."
    if parse_attached(sentence) is not None:
        return _no_effect
    if gated and predicate.lower().startswith("can't be blocked"):
        return _no_effect
    builder = _parse_layer_sentence_ungated(sentence)
    if builder is None and not subject.lower().endswith("creature"):
        builder = _parse_layer_sentence_ungated(f"{subject.split()[0]} creature {predicate}.")
    return builder


def parse_attached_compound_grant(sentence: str):  # noqa: ANN201
    """Layer builder for "<attachment subject> <A> and <B>" where each half is a
    layer shape or one of this module's own readers: "Enchanted creature can't
    be blocked and has shroud." (Protective Bubble, Whispersilk Cloak),
    "Enchanted creature gets +4/+1 and blocks each combat if able." (Spirespine),
    "During your turn, equipped creature has hexproof and can't be blocked."
    (Bilbo's Ring - the turn gate is asked of the layer context, CR 611.3a), and
    "As long as enchanted permanent is a creature, it gets -1/-1 and can't
    block." (Clawing Torment). None when either half is unread."""
    text = normalize_attached_sentence(sentence)
    creature_gate = text != sentence.strip()
    match = _COMPOUND_RE.fullmatch(text)
    if match is None or " and " not in match["rest"]:
        return None
    subject, rest, gated = match["subject"], match["rest"], match["during"] is not None
    for found in re.finditer(r" and ", rest):
        left, right = rest[: found.start()], rest[found.end() :]
        halves = [
            _compound_half(subject, left, gated=gated),
            _compound_half(subject, right, gated=gated),
        ]
        if any(half is None for half in halves):
            continue

        def builder(
            source,
            timestamp,
            targets,
            context,
            halves=halves,
            gated=gated,
            creature_gate=creature_gate,
        ):  # noqa: ANN001, ANN202
            if gated and context.active_player != source.controller:
                return []
            from .layers.parse import _source_line_for

            line = _source_line_for(source, sentence)
            built = [
                effect.model_copy(update={"source_ability": line})
                for half in halves
                for effect in half(source, timestamp, targets, context)
            ]
            if creature_gate:
                from .layers.model import Only, OnlyIfCreature

                built = [
                    effect.model_copy(
                        update={"selector": OnlyIfCreature(card_id=effect.selector.card_id)}
                    )
                    if isinstance(effect.selector, Only)
                    else effect
                    for effect in built
                ]
            return built

        return builder
    return None


def _attached_restrictions(game: "Game", subject: "CardState"):
    """(source, restriction) for every attachment on `subject` whose static
    lines state one."""
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        if source.attached_to != subject.id:
            continue
        for ability in board.of(source).abilities:
            lowered = ability.lower()
            if "enchanted " not in lowered and "equipped " not in lowered:
                continue
            if (
                "can't" not in lowered
                and "attacks each combat" not in lowered
                and "blocks each combat" not in lowered
            ):
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                restriction = parse_attached(sentence)
                if restriction is None:
                    continue
                if restriction.needs_other_controller and (
                    game.controller_of(source).username == game.controller_of(subject).username
                ):
                    continue
                yield source, restriction


def attached_evasion_refusal(game: "Game", attacker: "CardState") -> str | None:
    """Why an attachment's gated "can't be blocked" ("... as long as you
    control a Gate", "During your turn, ...") makes `attacker` unblockable
    now (CR 509.1b), or None. The condition is asked of the attachment's
    controller: "you" is whoever controls the Aura or Equipment."""
    for source, restriction in _attached_restrictions(game, attacker):
        if not restriction.evasion:
            continue
        held = game.condition_holds(
            game.controller_of(source).username or "", restriction.condition or "", source
        )
        if held:
            return (
                f'{attacker.name} can\'t be blocked: {source.name} says "{restriction.sentence}" '
                "(CR 509.1b)"
            )
    return None


def attached_block_requirements(game: "Game", creature: "CardState") -> list[None]:
    """One entry per "enchanted creature blocks each combat if able" on it
    (CR 509.1c); any legal block obeys it."""
    return [
        None
        for _source, restriction in _attached_restrictions(game, creature)
        if restriction.block_requirement
    ]


def _refusal(game: "Game", creature: "CardState", action: str) -> str | None:
    rule = "CR 508.1c" if action == "attack" else "CR 509.1b"
    for source, restriction in _attached_restrictions(game, creature):
        if restriction.pay is None and getattr(restriction, action):
            return (
                f'{creature.name} can\'t {action}: {source.name} says "{restriction.sentence}" '
                f"({rule})"
            )
    return None


def attached_attack_refusal(game: "Game", creature: "CardState") -> str | None:
    return _refusal(game, creature, "attack")


def attached_block_refusal(game: "Game", blocker: "CardState") -> str | None:
    return _refusal(game, blocker, "block")


def attached_attack_requirements(game: "Game", creature: "CardState") -> list[bool]:
    """One entry per "enchanted creature attacks each combat if able" on it
    (CR 508.1d); False: any attack obeys it."""
    return [
        False
        for _source, restriction in _attached_restrictions(game, creature)
        if restriction.requirement
    ]


def attached_charges(game: "Game", creature: "CardState", action: str):
    """(source, cost text, sentence) for each "unless its controller pays
    <cost>" an attachment states about `creature` doing `action` ("attack" or
    "block") - priced by `attack_block_costs` (CR 508.1h, 509.1d)."""
    for source, restriction in _attached_restrictions(game, creature):
        if restriction.pay is not None and getattr(restriction, action):
            yield source, restriction.pay, restriction.sentence


_ACTIVATION_TAX_RE = re.compile(
    r"^activated abilities of (?:enchanted|equipped) (?:creature|permanent|artifact|land) "
    r"cost (?P<cost>(?:\{[^}]+\})+) more to activate\.?$",
    re.IGNORECASE,
)


def activation_cost_increase(game: "Game", obj: "CardState") -> "ManaCost":
    """The mana an attachment adds to every activated ability of `obj` -
    Oppressive Rays' "Activated abilities of enchanted creature cost {3} more to
    activate." (CR 602.2b, CR 601.2f)."""
    from ..models.mana import ManaCost
    from .layers import layer_readable_sentences

    total = ManaCost.parse("")
    board = game.computed_board()
    for source in game.battlefield:
        if source.attached_to != obj.id:
            continue
        for ability in board.of(source).abilities:
            if "more to activate" not in ability.lower():
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                match = _ACTIVATION_TAX_RE.fullmatch(sentence.strip())
                if match is not None:
                    total = total.plus(ManaCost.parse(match["cost"]))
    return total


def attached_activation_prohibition(game: "Game", obj: "CardState", *, is_mana: bool) -> str | None:
    """Why an attachment's "its activated abilities can't be activated" stops
    activating an ability of `obj`, or None (CR 602.5)."""
    for source, restriction in _attached_restrictions(game, obj):
        if restriction.deactivate and not (restriction.mana_exempt and is_mana):
            return (
                f"{obj.name}'s activated abilities can't be activated: {source.name} says "
                f'"{restriction.sentence}" (CR 602.5)'
            )
    return None


#: Overwhelming Splendor's "Enchanted player can't activate abilities that
#: aren't mana abilities or loyalty abilities." (CR 303.4m, CR 602.5).
ENCHANTED_PLAYER_NO_ACTIVATE_RE = re.compile(
    r"^enchanted player can't activate abilities that aren't mana abilities or "
    r"loyalty abilities\.?$",
    re.IGNORECASE,
)


def enchanted_player_activation_prohibition(
    game: "Game", activator: str, *, is_mana: bool, is_loyalty: bool
) -> str | None:
    """Why an Aura on `activator` stops them activating this ability, or None
    (CR 602.5). Mana abilities (CR 605.1a) and loyalty abilities (CR 606) are
    spared by the sentence itself. Read off the computed board each time (CR
    611.3a), from every Aura attached to that player."""
    from .group_attack_statics import _enchanted_player

    if is_mana or is_loyalty:
        return None
    board = game.computed_board()
    for source in game.battlefield:
        if _enchanted_player(source) != activator:
            continue
        for line in board.of(source).abilities:
            if ENCHANTED_PLAYER_NO_ACTIVATE_RE.match(line.strip()):
                return (
                    f"{activator} can't activate abilities that aren't mana or loyalty "
                    f"abilities: {source.name} says so (CR 602.5)"
                )
    return None


def reads_attached_restriction_line(printing: "Card", text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is an attachment restriction
    `parse_attached` reads (the cost form is `attack_block_costs`'s)."""
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if "enchanted " not in lowered and "equipped " not in lowered and "it can't" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    return bool(sentences) and all(_reads_sentence(sentence) for sentence in sentences)


def _reads_sentence(sentence: str) -> bool:
    if ENCHANTED_PLAYER_NO_ACTIVATE_RE.fullmatch(sentence.strip()):
        return True
    found = parse_attached(sentence)
    if found is not None:
        if _UNTAP_AND_DEACTIVATE_RE.fullmatch(sentence) or re.search(
            r"\b(?:gets|has|doesn't untap) ", sentence, re.IGNORECASE
        ):
            # the untap half is the layer system's grant
            from .layers import _parse_layer_sentence

            return _parse_layer_sentence(sentence) is not None
        return found.pay is None
    if _ACTIVATION_TAX_RE.fullmatch(sentence):
        return True
    if CONDITIONAL_UMBRA_RE.fullmatch(sentence.rstrip(".")):
        return True
    # "gets +3/+2 and can't attack alone", "is a Spirit and can't attack or
    # block", "can't attack or block and has "..."": the layer system grants
    # the restriction and `attacking_statics`/`combat` enforce it.
    from .layers import _parse_layer_sentence

    lowered = sentence.lower()
    if any(word in lowered for word in ("can't attack", "can't block", "can't be blocked")):
        return _parse_layer_sentence(sentence) is not None
    return False

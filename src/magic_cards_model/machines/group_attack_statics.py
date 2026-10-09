"""Group attack/block restrictions and requirements stated by a permanent about
other creatures (CR 508.1c, 509.1b, 508.1d), read off the computed board (CR
613.5) at the moment asked (CR 611.3a):

- "<group> can't attack[ you [or planeswalkers you control]][ or block]."
  (Magus of the Moat, Stormtide Leviathan, Evil Eye of Urborg, Teferi's Moat,
  Gwafa Hazid, Kulrath Knight, Eriette of the Charmed Apple)
- "<group> attack each combat if able." (Angler Turtle, Goblin Assault, Graaz,
  Curse of the Nightly Hunt)
- "No more than one creature can attack/block each combat." (Silent Arbiter)

A group is "[other] <creatures> [you control | your opponents control |
enchanted player controls] [with | without <quality>]", or "each creature
that's enchanted by an Aura you control". "You" is the source's controller
(CR 109.5); "enchanted player" is the player the source is attached to (CR
303.4m).
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..models.card_state import CardState, TargetKind

if TYPE_CHECKING:
    from ..models.card import Card
    from ..models.game import Game

_CANT_ATTACK_RE = re.compile(
    r"^(?P<group>.+?) can't attack(?P<target> you or planeswalkers you control| you)?"
    r"(?P<block> or block)?\.?$",
    re.IGNORECASE,
)
_ATTACKS_EACH_COMBAT_RE = re.compile(
    r"^(?P<group>.+?) attack each combat if able\.?$", re.IGNORECASE
)
_CAP_RE = re.compile(r"^no more than one creature can (?P<what>attack|block) each combat\.?$", re.I)
_GROUP_RE = re.compile(
    r"^(?P<other>other )?(?P<base>.+?)"
    r"(?: (?P<owner>you control|your opponents control|enchanted player controls))?"
    r"(?: (?P<mod>with|without) (?P<quality>.+))?$",
    re.IGNORECASE,
)
_NON_SUBTYPE_RE = re.compile(r"^non-(?P<subtype>[a-z]+) creatures$", re.IGNORECASE)
_COUNTERS_RE = re.compile(r"^(?:(?P<kind>[a-z+\-/0-9]+) )?counters? on (?:it|them)$", re.IGNORECASE)
_AURA_GROUP = "each creature that's enchanted by an aura you control"
_SELFISH_PREFIXES = ("this ", "enchanted ", "equipped ", "it ", "each other ")

#: (game, member candidate, source) -> whether the candidate is in the group.
_Group = Callable[["Game", CardState, CardState], bool]


def _controller(game: "Game", state: CardState) -> str | None:
    return game.controller_of(state).username


def _enchanted_player(source: CardState) -> str | None:
    attachment = getattr(source, "attachment", None)
    if attachment is not None and attachment.kind is TargetKind.PLAYER:
        return attachment.username
    return None


def _keywords_lacked(quality: str) -> "list[str] | None":
    from .combat import Keyword

    known = {member.value.lower() for member in Keyword}
    parts = [part.strip().lower() for part in re.split(r"\s+or\s+|,\s*(?:or\s+)?", quality) if part]
    return parts if parts and all(part in known for part in parts) else None


def _base(base: str) -> "Callable[[Game, CardState, CardState], bool] | None":
    from .combat_statics import parse_blocker_description
    from .layers import chosen_color_of

    text = base.strip().lower()
    if text == "creatures":
        return lambda game, member, source: True
    if non := _NON_SUBTYPE_RE.fullmatch(text):
        subtype = non["subtype"].lower()
        return lambda game, member, source: (
            subtype not in {value.lower() for value in game.characteristics_of(member).subtypes}
        )
    if text == "creatures of the chosen color":

        def chosen(game: "Game", member: CardState, source: CardState) -> bool:
            color = chosen_color_of(source)
            return color is not None and color in game.characteristics_of(member).colors

        return chosen
    matcher = parse_blocker_description(base.strip())
    if matcher is None:
        return None
    return lambda game, member, source: matcher(game, member)


def _modifier(mod: str, quality: str) -> "Callable[[Game, CardState], bool] | None":
    from .combat import _parse_creature_description, has_keyword

    if mod.lower() == "without":
        lacked = _keywords_lacked(quality)
        if lacked is None:
            return None
        return lambda game, member: not any(has_keyword(member, word, game) for word in lacked)
    if counters := _COUNTERS_RE.fullmatch(quality.strip()):
        kind = (counters["kind"] or "").lower()

        def has_counter(game: "Game", member: CardState) -> bool:
            held = game.characteristics_of(member).counters
            return any(
                count > 0 and (not kind or str(key).lower() == kind) for key, count in held.items()
            )

        return has_counter
    parsed = _parse_creature_description("creatures with " + quality.strip())
    if parsed is None:
        return None
    return lambda game, member: parsed.matches(game, member)


def parse_group(text: str) -> "_Group | None":
    """The group a restriction or requirement sentence is about, as a predicate
    over (game, creature, source), or None when it is not a shape read here."""
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith(_SELFISH_PREFIXES) and lowered != _AURA_GROUP:
        return None
    if lowered == _AURA_GROUP:

        def enchanted_by_your_aura(game: "Game", member: CardState, source: CardState) -> bool:
            board = game.computed_board()
            return any(
                permanent.attached_to == member.id
                and "Aura" in board.of(permanent).subtypes
                and _controller(game, permanent) == _controller(game, source)
                for permanent in game.battlefield
            )

        return enchanted_by_your_aura
    match = _GROUP_RE.fullmatch(stripped)
    if match is None:
        return None
    base = _base(match["base"])
    if base is None:
        return None
    modifier = None
    if match["mod"] is not None:
        modifier = _modifier(match["mod"], match["quality"])
        if modifier is None:
            return None
    owner = (match["owner"] or "").lower()
    other = match["other"] is not None

    def member_of(game: "Game", member: CardState, source: CardState) -> bool:
        if not game.characteristics_of(member).is_creature:
            return False
        if other and member.id == source.id:
            return False
        who = _controller(game, member)
        mine = _controller(game, source)
        if owner == "you control" and who != mine:
            return False
        if owner == "your opponents control" and who == mine:
            return False
        if owner == "enchanted player controls" and who != _enchanted_player(source):
            return False
        if not base(game, member, source):
            return False
        return modifier is None or modifier(game, member)

    return member_of


def _static_sentences(game: "Game"):
    """(source, sentence) for each static sentence on the computed board."""
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        for ability in board.of(source).abilities:
            lowered = ability.lower()
            if "can't attack" not in lowered and "each combat" not in lowered:
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                yield source, sentence.strip()


def _cant_attack(sentence: str) -> "tuple[re.Match[str], _Group] | None":
    match = _CANT_ATTACK_RE.fullmatch(sentence)
    if match is None or (match["target"] and match["block"]):
        return None
    group = parse_group(match["group"])
    return None if group is None else (match, group)


def group_attack_refusal(game: "Game", creature: CardState, defender) -> str | None:
    """Why a "<group> can't attack [you]" static stops `creature` attacking
    `defender` (CR 508.1c), or None."""
    from .combat import _is_planeswalker_controlled_by

    for source, sentence in _static_sentences(game):
        found = _cant_attack(sentence)
        if found is None:
            continue
        match, group = found
        controller = _controller(game, source)
        if match["target"]:
            on_you = defender.is_player and defender.username == controller
            on_walker = "planeswalkers" in match["target"] and _is_planeswalker_controlled_by(
                game, defender, controller
            )
            if not (on_you or on_walker):
                continue
        if group(game, creature, source):
            return f'{creature.name} can\'t attack: {source.name} says "{sentence}" (CR 508.1c)'
    return None


def group_block_refusal(game: "Game", blocker: CardState, attacker: CardState) -> str | None:
    """Why a "<group> can't attack or block" static stops `blocker` blocking
    (CR 509.1b), or None."""
    for source, sentence in _static_sentences(game):
        found = _cant_attack(sentence)
        if found is None:
            continue
        match, group = found
        if match["block"] and not match["target"] and group(game, blocker, source):
            return (
                f"{blocker.name} can't block {attacker.name}: {source.name} says "
                f'"{sentence}" (CR 509.1b)'
            )
    return None


def group_attack_requirements(game: "Game", creature: CardState) -> list[bool]:
    """One entry per "<group> attack each combat if able" naming `creature`
    (CR 508.1d); True when only an attack on a player obeys it (none do)."""
    found: list[bool] = []
    for source, sentence in _static_sentences(game):
        match = _ATTACKS_EACH_COMBAT_RE.fullmatch(sentence)
        if match is None:
            continue
        group = parse_group(match["group"])
        if group is not None and group(game, creature, source):
            found.append(False)
    return found


def _cap_sources(game: "Game", what: str):
    from .layers import layer_readable_sentences

    board = game.computed_board()
    for source in game.battlefield:
        for ability in board.of(source).abilities:
            if "no more than one creature can" not in ability.lower():
                continue
            for sentence in layer_readable_sentences(ability, static_only=True):
                match = _CAP_RE.fullmatch(sentence.strip())
                if match is not None and match["what"].lower() == what:
                    yield source, sentence.strip()


def attack_cap_refusal(game: "Game", attacks) -> str | None:
    """ "No more than one creature can attack each combat" judged on the whole
    declaration (CR 508.1c)."""
    if len(attacks) < 2:
        return None
    for source, sentence in _cap_sources(game, "attack"):
        names = ", ".join(creature.name for creature, _defender in attacks)
        return f'{source.name} says "{sentence}", but {names} were all declared (CR 508.1c)'
    return None


def block_cap_refusal(game: "Game", declared) -> str | None:
    """ "No more than one creature can block each combat" judged on the whole
    declaration (CR 509.1b)."""
    blockers = [blocker for group in declared.values() for blocker in group]
    if len(blockers) < 2:
        return None
    for source, sentence in _cap_sources(game, "block"):
        names = ", ".join(blocker.name for blocker in blockers)
        return f'{source.name} says "{sentence}", but {names} were all declared (CR 509.1b)'
    return None


def reads_group_attack_line(printing: "Card", text: str, *, card_name: str) -> bool:
    """Whether every sentence of this static line is a shape the functions
    above enforce - asked of the parsers themselves."""
    from .layers import layer_readable_sentences

    lowered = text.lower()
    if "can't attack" not in lowered and "each combat" not in lowered:
        return False
    sentences = [s.strip() for s in layer_readable_sentences(text, static_only=True)]
    return bool(sentences) and all(_reads_sentence(sentence) for sentence in sentences)


def _reads_sentence(sentence: str) -> bool:
    if _CAP_RE.fullmatch(sentence):
        return True
    if match := _ATTACKS_EACH_COMBAT_RE.fullmatch(sentence):
        return parse_group(match["group"]) is not None
    return _cant_attack(sentence) is not None

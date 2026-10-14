"""Remove a blocker from combat, unblock what only it had blocked, then it
blocks an attacking creature of the ability controller's choice.

Balduvian Warlord: "Remove target blocking creature from combat. Creatures it
was blocking that hadn't become blocked by another creature this combat become
unblocked, then it blocks an attacking creature of your choice." Read whole,
because the second sentence's "it" is the first sentence's target *after* it
left combat: `Game.resolve_targets` re-checks "target blocking creature"
live (CR 608.2b), so a per-clause reading would find no "it" at all once the
first clause had run.

- CR 506.4: an effect that "specifically removes it from combat" ends its
  blocking (`CombatMachine.remove`).
- CR 509.1h: an attacker stays blocked "until ... an effect says that it
  becomes blocked or unblocked" - the second sentence is that effect, and
  "hadn't become blocked by another creature this combat" reads the combat's
  history (`Attack.blocked_by`), not who is blocking now.
- CR 608.2d: "an attacking creature of your choice" is the ability
  controller's choice while it resolves, among legal options only - CR
  509.1a's attackers aimed at the blocker's controller (`combat.
  effect_block_candidates`). An effect causing a block is not a declaration of
  blockers, so CR 509.1b/509.1c's restrictions and requirements do not apply.
- CR 509.3b/509.3d: the new block triggers "blocks a creature"/"becomes
  blocked by a creature" abilities (`Game.block_by_effect`).

Every rule number here was looked up this session with `mise run rules:find`.
Imported by `effects.py` at module load; never imports `effects` back at
module load (`map_tokens.py`'s one-way rule).
"""

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.zone import Zone
from .combat import effect_block_candidates
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, StackObject
    from .effects import TargetedClause


_REMOVE_THEN_BLOCKS_ANOTHER_RE = re.compile(
    r"remove (?P<phrase>target [^.]+?) from combat\. "
    r"creatures (?:it|they) (?:was|were) blocking that "
    r"(?:(?:hadn't|had not) become blocked by another creature"
    r"|had become blocked by only (?:that|this) creature) this combat become unblocked, "
    r"then (?:it|they) blocks? an attacking creature of your choice\.?",
    re.IGNORECASE,
)


def parse_remove_blocker_then_it_blocks_another_clause(text: str) -> "TargetedClause | None":
    """`_REMOVE_THEN_BLOCKS_ANOTHER_RE`'s shape, read whole; see the module."""
    match = _REMOVE_THEN_BLOCKS_ANOTHER_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    from .effects import _targets_understood

    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target
            for target in game.resolve_card_targets(stack_object)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            game.combat.remove(target.id)
            game.combat.unblock_attacks_blocked_only_by(target.id)
        chooser = game.controller_of(stack_object).username
        source_name = getattr(stack_object, "source_name", None) or stack_object.name
        for target in targets:
            candidates = effect_block_candidates(game, target)
            if not candidates:
                continue
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=chooser,
                    prompt=f"choose an attacking creature for {target.name} to block",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    amount=1,
                    cards=tuple(attacker.id for attacker in candidates),
                )
            )
            assert isinstance(answer, tuple)
            chosen = next(attacker for attacker in candidates if attacker.id == answer[0])
            game.block_by_effect(target, chosen)

    return effect

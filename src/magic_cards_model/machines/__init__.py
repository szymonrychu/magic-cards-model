"""State machines and parsers for the rules engine.

Three kinds of module live here:

- **Machines** that advance game state: `turn`, `priority`, `casting`, `cost`,
  `combat`.
- **Parsers** that read structure off real oracle text and do nothing else:
  `abilities`, `replacement`, `targeting`.
- **Registries** keyed by card name, because there is no general effect engine
  yet: `EFFECTS` (what a spell does on resolution) and `LAYER_EFFECTS` (the
  continuous effects a card produces). Both need feeding by hand - see CLAUDE.md.

`models` is imported first on purpose. `models.game` builds on these machines and
these machines build on `models`, so the two packages are a cycle; letting
`models` finish initialising before any machine module is loaded is what keeps
`import magic_cards_model.machines` and `import magic_cards_model.models` both
working as the first import of a process.
"""

from .. import models as _models  # noqa: F401
from .abilities import (
    Ability,
    AbilityKind,
    ActivatedAbility,
    Cost,
    CostKind,
    KeywordAbility,
    ManaAbility,
    ManaCondition,
    StaticAbility,
    TriggeredAbility,
    TriggerEvent,
    TriggerWord,
    UnparsedAbility,
    abilities_of_kind,
    intrinsic_land_ability,
    parse_abilities,
    parse_mana_abilities,
)
from .casting import Casting, CastingStep
from .combat import Attack, CombatMachine, Keyword, has_keyword
from .cost import (
    ComponentKind,
    CostComponent,
    CostPayment,
    CostStep,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_phrases,
    apply_modifications,
    could_pay_mana_cost,
    discard_cost,
    exile_cost,
    free_tap_mana_ability,
    increase,
    pay_life_cost,
    plan_mana_payment,
    reduce,
    remove_counters_cost,
    sacrifice_cost,
    tap_cost,
)
from .effects import (
    ACTIVATED_EFFECTS,
    EFFECTS,
    TRIGGER_EFFECTS,
    activated_effect_for,
    effect_for,
    trigger_effect_for,
)
from .hypothetical import (
    EntersPrediction,
    EntersState,
    LandPayability,
    Payability,
    PayabilityMatrix,
    payability,
    payability_matrix,
    predict_enters,
)
from .layers import (
    LAYER_EFFECTS,
    Characteristics,
    ComputedBoard,
    ContinuousEffect,
    Layer,
    Sublayer,
    compute_board,
    printed_characteristics,
)
from .legal_actions import decision_answers, legal_actions
from .modes import ModalProfile, Mode, is_modal, modal_profile, mode_rules_text
from .priority import PriorityMachine, PriorityOutcome
from .replacement import (
    ReplacementEffect,
    ReplacementKind,
    parse_replacement_effects,
)
from .targeting import (
    ControllerRestriction,
    TargetingProfile,
    TargetRequirement,
    profile_for_modes,
    targeting_profile,
)
from .triggers import (
    AbilityOnStack,
    GameEvent,
    activated_abilities_of,
    apnap_order,
    condition_matches,
    intervening_if_holds,
    triggered_abilities_of,
    triggers_for,
)
from .turn import (
    MAIN_PHASES,
    PHASE_OF,
    PREGAME_ORDER,
    PREGAME_STEPS,
    STEP_SEQUENCE,
    TURN_ORDER,
    Phase,
    Step,
    TurnMachine,
)

__all__ = [
    "ACTIVATED_EFFECTS",
    "TRIGGER_EFFECTS",
    "AbilityOnStack",
    "GameEvent",
    "activated_abilities_of",
    "activated_effect_for",
    "apnap_order",
    "condition_matches",
    "intervening_if_holds",
    "triggered_abilities_of",
    "trigger_effect_for",
    "triggers_for",
    "EFFECTS",
    "LAYER_EFFECTS",
    "MAIN_PHASES",
    "PHASE_OF",
    "PREGAME_ORDER",
    "PREGAME_STEPS",
    "STEP_SEQUENCE",
    "TURN_ORDER",
    "Ability",
    "AbilityKind",
    "ActivatedAbility",
    "Attack",
    "Casting",
    "CastingStep",
    "Characteristics",
    "CombatMachine",
    "ComponentKind",
    "ComputedBoard",
    "ContinuousEffect",
    "ControllerRestriction",
    "Cost",
    "CostComponent",
    "CostKind",
    "CostPayment",
    "CostStep",
    "Keyword",
    "KeywordAbility",
    "Layer",
    "ManaAbility",
    "ManaCondition",
    "ModalProfile",
    "Mode",
    "Phase",
    "PriorityMachine",
    "PriorityOutcome",
    "ReplacementEffect",
    "ReplacementKind",
    "StaticAbility",
    "Step",
    "Sublayer",
    "TargetRequirement",
    "TargetingProfile",
    "TotalCost",
    "TriggerEvent",
    "TriggerWord",
    "TriggeredAbility",
    "TurnMachine",
    "UnparsedAbility",
    "abilities_of_kind",
    "additional_cost_phrases",
    "alternative_cost_phrases",
    "apply_modifications",
    "compute_board",
    "could_pay_mana_cost",
    "decision_answers",
    "discard_cost",
    "effect_for",
    "exile_cost",
    "free_tap_mana_ability",
    "has_keyword",
    "increase",
    "intrinsic_land_ability",
    "is_modal",
    "legal_actions",
    "EntersPrediction",
    "EntersState",
    "LandPayability",
    "Payability",
    "PayabilityMatrix",
    "payability",
    "payability_matrix",
    "predict_enters",
    "modal_profile",
    "mode_rules_text",
    "parse_abilities",
    "parse_mana_abilities",
    "parse_replacement_effects",
    "pay_life_cost",
    "plan_mana_payment",
    "printed_characteristics",
    "profile_for_modes",
    "reduce",
    "remove_counters_cost",
    "sacrifice_cost",
    "tap_cost",
    "targeting_profile",
]

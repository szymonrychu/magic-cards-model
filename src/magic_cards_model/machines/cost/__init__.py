"""Paying a cost, as a state machine.

Follows the shape of CR 601.2f-h: work out the total cost, activate mana
abilities to fill the pool, then pay. Tapping a permanent for mana is both the
cost of the mana ability and the thing that fills the pool, so it lives here.

    PENDING -> TAPPING -> POOLED -> PAID
                 \\_______________/
       (mana already floating skips the tapping)

A cost is not only mana. CR 601.2f calls the whole thing the *total cost*, and
it is a composite: a mana part plus any number of non-mana components -
sacrificing a permanent, discarding a card, paying life, exiling a card,
tapping a permanent. `TotalCost` is that composite and `CostComponent` is one
non-mana piece of it.

The payment's mana pool opens as a copy of the payer's floating mana: CR 202.1a
has the cost spent "from their mana pool", and CR 106.4 lets mana already
floating there pay "immediately", so it is usable without activating anything.
The mana abilities the payment activates along the way (CR 601.2g) add into
that copy. When the payment succeeds, whatever it did not spend is written back
into the player's pool (CR 106.4a); when it is cancelled, the copy is thrown
away, so the player's pre-existing floating mana is untouched while the payment's
own activations die with the copy and their sources are untapped.

Any state before PAID can be cancelled, which untaps everything tapped for
mana, discards the mana the payment's own activations produced, and undoes
every component already paid. That is CR 733.1: an action that cannot be
completed legally is reversed in full and any payments already made are
cancelled.
"""

# isort: off
from ..abilities import ActivatedAbility as ActivatedAbility
from typing import Any as Any
from collections.abc import Callable as Callable
from ...models.card import Card as Card
from ...models.card_state import CardState as CardState
from ...models.card_state import ChoiceKind as ChoiceKind
from ...models.card import Color as Color
from pydantic import ConfigDict as ConfigDict
from ..abilities import CostKind as CostKind
from ...models.card_state import Counter as Counter
from ...models.card_state import CounterKind as CounterKind
from ...snapshot import EngineModel as EngineModel
from ...models.card_state import ExileAnnotation as ExileAnnotation
from ...models.card_state import ExileMarker as ExileMarker
from pydantic import Field as Field
from collections.abc import Hashable as Hashable
from collections.abc import Iterable as Iterable
from ..combat import Keyword as Keyword
from ..abilities import ManaAbility as ManaAbility
from ...models.mana import ManaCost as ManaCost
from ...models.mana import ManaPayment as ManaPayment
from ...models.mana import ManaPool as ManaPool
from ...models.mana import ManaRestriction as ManaRestriction
from ...models.mana import ManaSpend as ManaSpend
from ...models.mana import ManaSpendEffect as ManaSpendEffect
from ...models.mana import ManaSymbol as ManaSymbol
from ...models.mana import NOT_RETAINED as NOT_RETAINED
from ...models.mana import NO_SPEND_EFFECT as NO_SPEND_EFFECT
from typing import NamedTuple as NamedTuple
from ...models.mana import PaymentOption as PaymentOption
from pydantic import PrivateAttr as PrivateAttr
from ...numbers import QuantitySource as QuantitySource
from collections.abc import Sequence as Sequence
from ...models.mana import SpendClause as SpendClause
from ...models.mana import SpendPurpose as SpendPurpose
from enum import StrEnum as StrEnum
from ...models.card import Supertype as Supertype
from ...models.mana import SymbolKind as SymbolKind
from ...models.card import Type as Type
from ...models.mana import UNRESTRICTED as UNRESTRICTED
from uuid import UUID as UUID
from ...numbers import VariableX as VariableX
from ...models.zone import Zone as Zone
from ...models.mana import _Bucket as _Bucket
from collections import Counter as _MultiSet  # noqa: F401
from ...models.mana import _assign_sources as _assign_sources
from ...models.mana import _candidate_options as _candidate_options
from ...models.mana import _demand_list as _demand_list
from ..triggers import abilities_triggered_by as abilities_triggered_by
from ..triggers import activated_abilities_from_lines as activated_abilities_from_lines
from ..triggers import activated_abilities_of as activated_abilities_of
from ..triggers import added_ability_lines as added_ability_lines
from ...snapshot import announce_mutation as announce_mutation
from functools import cache as cache
from ...data.subtypes import canonical_subtype as canonical_subtype
from itertools import combinations as combinations
from itertools import combinations_with_replacement as combinations_with_replacement
from ...numbers import count_pattern as count_pattern
from dataclasses import dataclass as dataclass
from ..triggers import granted_activated_abilities_of as granted_activated_abilities_of
from ..abilities import granted_mana_abilities as granted_mana_abilities
from ..combat import has_keyword as has_keyword
from ..abilities import intrinsic_land_ability as intrinsic_land_ability
from ..triggers import is_ability as is_ability
from ...models.token import is_token as is_token
from ..triggers import mana_ability_activated_event as mana_ability_activated_event
from ..triggers import mana_added_event as mana_added_event
from ...snapshot import mutation_landed as mutation_landed
from ..abilities import one_named_color as one_named_color
from ..abilities import parse_abilities as parse_abilities
from ...numbers import parse_amount as parse_amount
from ...numbers import parse_count as parse_count
from ..abilities import parse_mana_abilities as parse_mana_abilities
from ...numbers import parse_quantity as parse_quantity
from ..abilities import parse_triggered_mana as parse_triggered_mana
from itertools import product as product
import re as re
from ..abilities import resolve_mana_count_expression as resolve_mana_count_expression
from ..triggers import rewritten_ability_lines as rewritten_ability_lines
from ..triggers import tapped_for_mana_event as tapped_for_mana_event
from ..triggers import triggered_abilities_on as triggered_abilities_on
from ..triggers import triggered_mana_count as triggered_mana_count
from ..triggers import triggered_mana_recipient as triggered_mana_recipient
from magic_cards_model.phrases import with_indefinite_article as with_indefinite_article
from .components import (
    ActivatedAbilityGroupDiscount,
    AlternativeCostOffer,
    CardRequirement,
    ComponentKind,
    CostComponent,
    CostModifierEffect,
    CostModifierKind,
    CostModifierNotice,
    CostStep,
    CostSubstitution,
    MixedProduction,
    StaticFreeCastGrant,
    TotalCost,
    _ANY_COUNTER_PREFERENCE,
    _OBJECT_KINDS,
    _PHRASE_WATERBEND,
    _REMOVE_ANY_NUMBER_OF_COUNTERS,
    _cost_count,
    _removable_counters,
    announce_count,
    announce_reveal,
    any_counters_to_remove,
    apply_modifications,
    behold_cost,
    collect_evidence_cost,
    cost_announces_x,
    cost_less,
    discard_cost,
    exert_cost,
    exile_and_pay_mana_cost_cost,
    exile_cost,
    fill_from_among,
    increase,
    loyalty_cost,
    mill_cost,
    pay_life_cost,
    place_counters_cost,
    reduce,
    remove_counters_cost,
    removes_announced_number_of_counters,
    return_to_hand_cost,
    reveal_cost,
    sacrifice_cost,
    tap_cost,
    untap_cost,
    waterbend_mana_cost,
    why_not_unblocked,
)
from ._common import ANY_COUNTER_KIND, _PHRASE_PAY_LIFE, _QUALITY_CONNECTORS, _TYPE_WORDS
from .payment import (
    CostPayment,
    INFER_RESTRICTION,
    TapPlan,
    _ALLOWED,
    _ANY_COLOR_AMONG,
    _ActivatedMana,
    _Alternative,
    _Candidate,
    _FIVE_COLORS,
    _PHRASE_PAY_REPEATED_SYMBOL,
    _SPEND_ACTIVATE_CLAUSE,
    _SPEND_CAST_CLAUSE,
    _SPEND_CLAUSE_SPLIT,
    _SPEND_CUMULATIVE_UPKEEP_CLAUSE,
    _SPEND_RESTRICTION,
    _SPEND_RESTRICTION_SIGNAL,
    _SPEND_RIDER,
    _SPEND_VERB,
    _SPEND_ZONE_WORDS,
    _SUPERTYPE_WORDS,
    _ScannedCandidate,
    _SpendContext,
    _TYPE_LIST_JOINERS,
    _activated_mana_ability,
    _activated_mana_ability_with_triggers,
    _activation_behind,
    _activation_bookkeeping_restore,
    _activation_moves_library_card,
    _activation_refused,
    _activations_of,
    _among_colors,
    _auto_tap_candidates,
    _best_flow_plan,
    _bucket_map,
    _chosen_alternative,
    _chosen_creature_type,
    _copy_pool,
    _entry_life_loss,
    _exotic_choice_combos,
    _filter_candidate_scan,
    _flexibility,
    _group_by_source,
    _is_exotic,
    _mana_context,
    _mana_narrowings,
    _mana_pool_overwrite,
    _mana_production_effects,
    _mixed_options,
    _narrow_to_defined_colors,
    _one_spend_clause,
    _plan_life_loss,
    _prefer_painless_mana,
    _replace_production,
    _replaced_options,
    _scan_mana_candidates,
    _slot_for,
    _solve_auto_tap,
    _solve_auto_tap_brute_force,
    _solve_auto_tap_flow,
    _solve_colours,
    _spelled_out,
    _spend_clause,
    _spend_clauses,
    _spend_restriction_cached,
    _spend_zone,
    _triggered_mana_alternatives,
    _unpayable_cost_message,
    _unreplaced_production,
    _with_triggered_mana,
    _withheld_mana_sources,
    among_colors,
    can_tap_for_mana,
    could_pay_mana_cost,
    counted_mana_options,
    free_tap_mana_abilities,
    free_tap_mana_ability,
    is_creature_source,
    is_snow_source,
    is_treasure_source,
    life_paid_mana_activations,
    mana_ability_count,
    mana_ability_index,
    mana_ability_most,
    mana_candidate_scan,
    mana_trigger_sources,
    pay_repeated_symbol_mana_cost,
    plan_mana_payment,
    restriction_for_production,
    spend_restriction,
    tappable_mana_activations,
    triggered_mana_bonus,
    why_payer_cannot_use,
)
from .text import (
    _ACTION_SYMBOL,
    _ACTIVATED_ABILITY_GROUP_DISCOUNT_RE,
    _ADDITIONAL,
    _ALTERNATIVE,
    _ALTERNATIVE_IF_NOT_YOUR_TURN,
    _AS_LONG_AS_TAIL,
    _CHOSEN_TYPE_COST_DECREASE,
    _COLOR_COST_DECREASE,
    _COLOR_WORDS,
    _COST_COUNT,
    _COST_DECREASE_SIGNAL,
    _COST_MODIFIER_SIGNAL,
    _COST_PHRASE_SEPARATOR,
    _COST_ZONE_WORDS,
    _COUNTER_SELF_SUBJECT,
    _CREATURE_SPELL_TOUGHNESS_OVER_POWER_COST_DECREASE_RE,
    _FIRST_SPELL_EACH_TURN_COST_DECREASE,
    _FLAT_COST_INCREASE,
    _MANA_VALUE_TAIL,
    _NAMED_COST_INCREASE,
    _NONTYPE_COST_DECREASE,
    _ONCE_EACH_TURN_FREE_CAST,
    _ONE_SYMBOL_OR_ANOTHER,
    _ONLY_MANA,
    _OPPONENT_COST_INCREASE,
    _PER_OBJECT_EXILE_COST_REDUCTION_RE,
    _PER_OBJECT_SACRIFICE_COST_REDUCTION_RE,
    _PER_SPELL_COST_INCREASE,
    _PHRASE_BEHOLD,
    _PHRASE_BEHOLD_N,
    _PHRASE_BLIGHT,
    _PHRASE_COLLECT_EVIDENCE,
    _PHRASE_DISCARD,
    _PHRASE_EXERT_SELF,
    _PHRASE_EXILE,
    _PHRASE_EXILE_AND_PAY_MANA_COST,
    _PHRASE_EXILE_PERMANENT,
    _PHRASE_MILL,
    _PHRASE_PLACE_COUNTERS,
    _PHRASE_REMOVE_ANY_COUNTERS,
    _PHRASE_REMOVE_COUNTERS,
    _PHRASE_REMOVE_COUNTERS_FROM_AMONG,
    _PHRASE_RETURN_SELF_TO_HAND,
    _PHRASE_RETURN_TO_HAND,
    _PHRASE_REVEAL,
    _PHRASE_SACRIFICE,
    _PHRASE_TAP,
    _PHRASE_UNTAP_SYMBOL,
    _QUALIFIER_EXCLUDES,
    _SPELL_COST_FLOOR,
    _STATIC_FREE_CAST,
    _SUBTYPE_COST_DECREASE,
    _SYMBOL_COLORS,
    _SYMBOL_COST_DECREASE,
    _TARGETING_THIS_COST_INCREASE,
    _THE_NUMBER_OF_YOU_CONTROL,
    _TYPE_COST_DECREASE,
    _TYPE_COST_DECREASE_EQUIPPED_POWER_RE,
    _UPKEEP_PAYABLE_KINDS,
    _ZONE_COST_DECREASE,
    _ZONE_WORDS,
    _behold_n_requirement,
    _controlled_requirement,
    _counter_kind_word,
    _for_each_count_is_readable,
    _oracle_text_for_face,
    _per_object_reduction,
    _per_object_reduction_re,
    _requirement,
    _split_cost_phrase,
    _unconditional_cost_modifier_effect,
    activated_ability_group_discount_effect,
    additional_cost_phrases,
    alternative_cost_offers,
    alternative_cost_phrase_of_line,
    alternative_cost_phrases,
    cost_component_for_phrase,
    cost_modifier_effect,
    cumulative_upkeep_cost,
    looks_like_unparsed_cost_modifier,
    mana_value_cap_for,
    per_object_exile_cost_reduction,
    per_object_exile_reduction_of_sentence,
    per_object_sacrifice_cost_reduction,
    per_object_sacrifice_reduction_of_sentence,
    static_free_cast_grant,
    total_cost_for_phrase,
)
# isort: on


__all__ = [
    "ANY_COUNTER_KIND",
    "ActivatedAbilityGroupDiscount",
    "AlternativeCostOffer",
    "CardRequirement",
    "ComponentKind",
    "CostComponent",
    "CostModifierEffect",
    "CostModifierKind",
    "CostModifierNotice",
    "CostPayment",
    "CostStep",
    "CostSubstitution",
    "INFER_RESTRICTION",
    "MixedProduction",
    "StaticFreeCastGrant",
    "TapPlan",
    "TotalCost",
    "_ACTION_SYMBOL",
    "_ACTIVATED_ABILITY_GROUP_DISCOUNT_RE",
    "_ADDITIONAL",
    "_ALLOWED",
    "_ALTERNATIVE",
    "_ALTERNATIVE_IF_NOT_YOUR_TURN",
    "_ANY_COLOR_AMONG",
    "_ANY_COUNTER_PREFERENCE",
    "_AS_LONG_AS_TAIL",
    "_ActivatedMana",
    "_Alternative",
    "_CHOSEN_TYPE_COST_DECREASE",
    "_COLOR_COST_DECREASE",
    "_COLOR_WORDS",
    "_COST_COUNT",
    "_COST_DECREASE_SIGNAL",
    "_COST_MODIFIER_SIGNAL",
    "_COST_PHRASE_SEPARATOR",
    "_COST_ZONE_WORDS",
    "_COUNTER_SELF_SUBJECT",
    "_CREATURE_SPELL_TOUGHNESS_OVER_POWER_COST_DECREASE_RE",
    "_Candidate",
    "_FIRST_SPELL_EACH_TURN_COST_DECREASE",
    "_FIVE_COLORS",
    "_FLAT_COST_INCREASE",
    "_MANA_VALUE_TAIL",
    "_NAMED_COST_INCREASE",
    "_NONTYPE_COST_DECREASE",
    "_OBJECT_KINDS",
    "_ONCE_EACH_TURN_FREE_CAST",
    "_ONE_SYMBOL_OR_ANOTHER",
    "_ONLY_MANA",
    "_OPPONENT_COST_INCREASE",
    "_PER_OBJECT_EXILE_COST_REDUCTION_RE",
    "_PER_OBJECT_SACRIFICE_COST_REDUCTION_RE",
    "_PER_SPELL_COST_INCREASE",
    "_PHRASE_BEHOLD",
    "_PHRASE_BEHOLD_N",
    "_PHRASE_BLIGHT",
    "_PHRASE_COLLECT_EVIDENCE",
    "_PHRASE_DISCARD",
    "_PHRASE_EXERT_SELF",
    "_PHRASE_EXILE",
    "_PHRASE_EXILE_AND_PAY_MANA_COST",
    "_PHRASE_EXILE_PERMANENT",
    "_PHRASE_MILL",
    "_PHRASE_PAY_LIFE",
    "_PHRASE_PAY_REPEATED_SYMBOL",
    "_PHRASE_PLACE_COUNTERS",
    "_PHRASE_REMOVE_ANY_COUNTERS",
    "_PHRASE_REMOVE_COUNTERS",
    "_PHRASE_REMOVE_COUNTERS_FROM_AMONG",
    "_PHRASE_RETURN_SELF_TO_HAND",
    "_PHRASE_RETURN_TO_HAND",
    "_PHRASE_REVEAL",
    "_PHRASE_SACRIFICE",
    "_PHRASE_TAP",
    "_PHRASE_UNTAP_SYMBOL",
    "_PHRASE_WATERBEND",
    "_QUALIFIER_EXCLUDES",
    "_QUALITY_CONNECTORS",
    "_REMOVE_ANY_NUMBER_OF_COUNTERS",
    "_SPELL_COST_FLOOR",
    "_SPEND_ACTIVATE_CLAUSE",
    "_SPEND_CAST_CLAUSE",
    "_SPEND_CLAUSE_SPLIT",
    "_SPEND_CUMULATIVE_UPKEEP_CLAUSE",
    "_SPEND_RESTRICTION",
    "_SPEND_RESTRICTION_SIGNAL",
    "_SPEND_RIDER",
    "_SPEND_VERB",
    "_SPEND_ZONE_WORDS",
    "_STATIC_FREE_CAST",
    "_SUBTYPE_COST_DECREASE",
    "_SUPERTYPE_WORDS",
    "_SYMBOL_COLORS",
    "_SYMBOL_COST_DECREASE",
    "_ScannedCandidate",
    "_SpendContext",
    "_TARGETING_THIS_COST_INCREASE",
    "_THE_NUMBER_OF_YOU_CONTROL",
    "_TYPE_COST_DECREASE",
    "_TYPE_COST_DECREASE_EQUIPPED_POWER_RE",
    "_TYPE_LIST_JOINERS",
    "_TYPE_WORDS",
    "_UPKEEP_PAYABLE_KINDS",
    "_ZONE_COST_DECREASE",
    "_ZONE_WORDS",
    "_activated_mana_ability",
    "_activated_mana_ability_with_triggers",
    "_activation_behind",
    "_activation_bookkeeping_restore",
    "_activation_moves_library_card",
    "_activation_refused",
    "_activations_of",
    "_among_colors",
    "_auto_tap_candidates",
    "_behold_n_requirement",
    "_best_flow_plan",
    "_bucket_map",
    "_chosen_alternative",
    "_chosen_creature_type",
    "_controlled_requirement",
    "_copy_pool",
    "_cost_count",
    "_counter_kind_word",
    "_entry_life_loss",
    "_exotic_choice_combos",
    "_filter_candidate_scan",
    "_flexibility",
    "_for_each_count_is_readable",
    "_group_by_source",
    "_is_exotic",
    "_mana_context",
    "_mana_narrowings",
    "_mana_pool_overwrite",
    "_mana_production_effects",
    "_mixed_options",
    "_narrow_to_defined_colors",
    "_one_spend_clause",
    "_oracle_text_for_face",
    "_per_object_reduction",
    "_per_object_reduction_re",
    "_plan_life_loss",
    "_prefer_painless_mana",
    "_removable_counters",
    "_replace_production",
    "_replaced_options",
    "_requirement",
    "_scan_mana_candidates",
    "_slot_for",
    "_solve_auto_tap",
    "_solve_auto_tap_brute_force",
    "_solve_auto_tap_flow",
    "_solve_colours",
    "_spelled_out",
    "_spend_clause",
    "_spend_clauses",
    "_spend_restriction_cached",
    "_spend_zone",
    "_split_cost_phrase",
    "_triggered_mana_alternatives",
    "_unconditional_cost_modifier_effect",
    "_unpayable_cost_message",
    "_unreplaced_production",
    "_with_triggered_mana",
    "_withheld_mana_sources",
    "activated_ability_group_discount_effect",
    "additional_cost_phrases",
    "alternative_cost_offers",
    "alternative_cost_phrase_of_line",
    "alternative_cost_phrases",
    "among_colors",
    "announce_count",
    "announce_reveal",
    "any_counters_to_remove",
    "apply_modifications",
    "behold_cost",
    "can_tap_for_mana",
    "collect_evidence_cost",
    "cost_announces_x",
    "cost_component_for_phrase",
    "cost_less",
    "cost_modifier_effect",
    "could_pay_mana_cost",
    "counted_mana_options",
    "cumulative_upkeep_cost",
    "discard_cost",
    "exert_cost",
    "exile_and_pay_mana_cost_cost",
    "exile_cost",
    "fill_from_among",
    "free_tap_mana_abilities",
    "free_tap_mana_ability",
    "increase",
    "is_creature_source",
    "is_snow_source",
    "is_treasure_source",
    "life_paid_mana_activations",
    "looks_like_unparsed_cost_modifier",
    "loyalty_cost",
    "mana_ability_count",
    "mana_ability_index",
    "mana_ability_most",
    "mana_candidate_scan",
    "mana_trigger_sources",
    "mana_value_cap_for",
    "mill_cost",
    "pay_life_cost",
    "pay_repeated_symbol_mana_cost",
    "per_object_exile_cost_reduction",
    "per_object_exile_reduction_of_sentence",
    "per_object_sacrifice_cost_reduction",
    "per_object_sacrifice_reduction_of_sentence",
    "place_counters_cost",
    "plan_mana_payment",
    "reduce",
    "remove_counters_cost",
    "removes_announced_number_of_counters",
    "restriction_for_production",
    "return_to_hand_cost",
    "reveal_cost",
    "sacrifice_cost",
    "spend_restriction",
    "static_free_cast_grant",
    "tap_cost",
    "tappable_mana_activations",
    "total_cost_for_phrase",
    "triggered_mana_bonus",
    "untap_cost",
    "waterbend_mana_cost",
    "why_not_unblocked",
    "why_payer_cannot_use",
]

# Keyword oracle credit and the "it" referent (T-109 S0, 2026-11-11)

`machines/keywords.executes` is what the support oracle asks, separately from
`_TRIGGER_EXPANSIONS`. A machine can exist and the oracle still report every
card printing only that keyword as silent: exalted and ripple were in that
state (35 Modern cards). Crediting a keyword is only honest after a card test
shows the machine plays; `tests/scenarios/test_silent_s0_cards.py` does that,
one test per card.

Writing those tests exposed a real misread: "Whenever a creature you control
attacks alone, it gains lifelink until end of turn." (Battlegrace Angel, Rafiq
of the Many) was handled but the grant went to the source, not the attacker.
`_parse_self_keyword_grant_until_eot_clause` now resolves "it" through
`_referent_of_it` (the trigger event's subject, the source when the event
names none); "this permanent" stays the source.

The other `_TRIGGER_EXPANSIONS` keys not in `executes()` (frenzy, madness,
poisonous, replicate, suspend) have no K-bucket silent Modern card: their cards
are silent for other text, so S0 credits nothing more.
Finest Hour, Nefarox and Sovereigns of Lost Alara stay silent: their second
"attacks alone" trigger (untap, sacrifice, Aura search) is an effect no reader
parses; they belong to the effect-family batches.

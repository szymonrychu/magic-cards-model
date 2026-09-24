# The Big Score (big)

- Expansion: 248
- Set code: `big`
- Release date: 2024-04-19
- Cards in scope (Modern/Pioneer/Standard-legal): 25

## Legality

| Format | Legal cards |
|---|---|
| Modern | 25 |
| Pioneer | 25 |
| Standard | 25 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 4.0% |
| Partial (unaudited) | 1 | 4.0% |
| Not tested (handled, untested) | 6 | 24.0% |
| Not working (silent / notice / error) | 17 | 68.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ancient Cornucopia | silent | Whenever you cast a spell that's one or more colors, you may gain 1 life for each of that spell's colors. Do this only once each turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Collector's Cage | silent | {1}, {T}: Put a +1/+1 counter on target creature you control. Then if you control three or more creatures with different powers, you may play the exiled card wi | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Esoteric Duplicator | silent | Whenever you sacrifice this artifact or another artifact, you may pay {2}. If you do, at the beginning of the next end step, create a token that's a copy of tha | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Fomori Vault | silent | {3}, {T}, Discard a card: Look at the top X cards of your library, where X is the number of artifacts you control. Put one of those cards into your hand and the | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Generous Plunderer | silent | Whenever this creature attacks, it deals damage to defending player equal to the number of artifacts they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Harvester of Misery | silent | When this creature enters, other creatures get -2/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Memory Vessel | silent | {T}, Exile this artifact: Each player exiles the top seven cards of their library. Until your next turn, players may play cards they exiled this way, and they c | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Omenpath Journey | silent | When this enchantment enters, search your library for up to five land cards that have different names, exile them, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Sandstorm Salvager | silent | {2}, {T}: Put a +1/+1 counter on each creature token you control. They gain trample until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Sword of Wealth and Power | silent | Whenever equipped creature deals combat damage to a player, create a Treasure token. When you next cast an instant or sorcery spell this turn, copy that spell.  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Tarnation Vista | silent | {1}, {T}: For each color among monocolored permanents you control, add one mana of that color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Vaultborn Tyrant | silent | When this creature dies, if it's not a token, create a token that's a copy of it, except it's an artifact in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Worldwalker Helm | silent | Explore | no machine in the engine executes this keyword | Y/Y/Y | not_working |
| Bristlebud Farmer | notice | Whenever this creature attacks, you may sacrifice a Food. If you do, mill three cards. You may put a permanent card from among them into your hand. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Loot, the Key to Everything | notice | At the beginning of your upkeep, exile the top X cards of your library, where X is the number of card types among other nonland permanents you control. You may  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Molten Duplication | notice | Create a token that's a copy of target artifact or creature you control, except it's an artifact in addition to its other types. It gains haste until end of tur | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Nexus of Becoming | notice | At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Territory Forge | unaudited | This artifact has all activated abilities of the exiled card. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Greed's Gambit | handled | When this enchantment enters, you draw three cards, gain 6 life, and create three 2/1 black Bat creature tokens with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hostile Investigator | handled | When this creature enters, target opponent discards a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Legion Extruder | handled | When this artifact enters, it deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lost Jitte | handled | Whenever equipped creature deals combat damage, put a charge counter on Lost Jitte. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lotus Ring | handled | Equipped creature gets +3/+3 and has vigilance and "{T}, Sacrifice this creature: Add three mana of any one color." | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Simulacrum Synthesizer | handled | When this artifact enters, scry 2. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Pest Control

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of | Nexus of Becoming | 1 |
| At the beginning of your upkeep, exile the top X cards of your library, where X is the number of card types among other nonland permanents you control. You may  | Loot, the Key to Everything | 1 |
| Create a token that's a copy of target artifact or creature you control, except it's an artifact in addition to its other types. It gains haste until end of tur | Molten Duplication | 1 |
| {3}, {T}, Discard a card: Look at the top X cards of your library, where X is the number of artifacts you control. Put one of those cards into your hand and the | Fomori Vault | 1 |
| {T}, Exile this artifact: Each player exiles the top seven cards of their library. Until your next turn, players may play cards they exiled this way, and they c | Memory Vessel | 1 |
| Explore | Worldwalker Helm | 1 |
| {1}, {T}: For each color among monocolored permanents you control, add one mana of that color. | Tarnation Vista | 1 |
| {2}, {T}: Put a +1/+1 counter on each creature token you control. They gain trample until end of turn. | Sandstorm Salvager | 1 |
| {1}, {T}: Put a +1/+1 counter on target creature you control. Then if you control three or more creatures with different powers, you may play the exiled card wi | Collector's Cage | 1 |
| This artifact has all activated abilities of the exiled card. | Territory Forge | 1 |
| When this creature dies, if it's not a token, create a token that's a copy of it, except it's an artifact in addition to its other types. | Vaultborn Tyrant | 1 |
| When this creature enters, other creatures get -2/-2 until end of turn. | Harvester of Misery | 1 |
| When this enchantment enters, search your library for up to five land cards that have different names, exile them, then shuffle. | Omenpath Journey | 1 |
| Whenever equipped creature deals combat damage to a player, create a Treasure token. When you next cast an instant or sorcery spell this turn, copy that spell.  | Sword of Wealth and Power | 1 |
| Whenever this creature attacks, it deals damage to defending player equal to the number of artifacts they control. | Generous Plunderer | 1 |
| Whenever this creature attacks, you may sacrifice a Food. If you do, mill three cards. You may put a permanent card from among them into your hand. | Bristlebud Farmer | 1 |
| Whenever you cast a spell that's one or more colors, you may gain 1 life for each of that spell's colors. Do this only once each turn. | Ancient Cornucopia | 1 |
| Whenever you sacrifice this artifact or another artifact, you may pay {2}. If you do, at the beginning of the next end step, create a token that's a copy of tha | Esoteric Duplicator | 1 |

## Notes



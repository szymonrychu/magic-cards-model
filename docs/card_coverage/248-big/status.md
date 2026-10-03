# The Big Score (big)

- Expansion: 248
- Set code: `big`
- Release date: 2024-04-19
- Cards in scope (Modern/Pioneer/Standard-legal): 27

## Legality

| Format | Legal cards |
|---|---|
| Modern | 27 |
| Pioneer | 27 |
| Standard | 27 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 4 | 14.8% |
| Works (untested) | 7 | 25.9% |
| Partial (unaudited) | 2 | 7.4% |
| Not working | 14 | 51.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ancient Cornucopia | silent | Whenever you cast a spell that's one or more colors, you may gain 1 life for each of that spell's colors. Do this only once each turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Collector's Cage | silent | {1}, {T}: Put a +1/+1 counter on target creature you control. Then if you control three or more creatures with different powers, you may play the exiled card wi | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Esoteric Duplicator | silent | Whenever you sacrifice this artifact or another artifact, you may pay {2}. If you do, at the beginning of the next end step, create a token that's a copy of tha | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Generous Plunderer | silent | Whenever this creature attacks, it deals damage to defending player equal to the number of artifacts they control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Memory Vessel | silent | {T}, Exile this artifact: Each player exiles the top seven cards of their library. Until your next turn, players may play cards they exiled this way, and they c | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Omenpath Journey | silent | When this enchantment enters, search your library for up to five land cards that have different names, exile them, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Sandstorm Salvager | silent | {2}, {T}: Put a +1/+1 counter on each creature token you control. They gain trample until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Sword of Wealth and Power | silent | Whenever equipped creature deals combat damage to a player, create a Treasure token. When you next cast an instant or sorcery spell this turn, copy that spell.  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Tarnation Vista | silent | {1}, {T}: For each color among monocolored permanents you control, add one mana of that color. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Transmutation Font | silent | {T}: Create your choice of a Blood token, a Clue token, or a Food token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Vaultborn Tyrant | silent | When this creature dies, if it's not a token, create a token that's a copy of it, except it's an artifact in addition to its other types. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Bristlebud Farmer | notice | Whenever this creature attacks, you may sacrifice a Food. If you do, mill three cards. You may put a permanent card from among them into your hand. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Loot, the Key to Everything | notice | At the beginning of your upkeep, exile the top X cards of your library, where X is the number of card types among other nonland permanents you control. You may  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Nexus of Becoming | notice | At the beginning of combat on your turn, draw a card. Then you may exile an artifact or creature card from your hand. If you do, create a token that's a copy of | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Territory Forge | unaudited | This artifact has all activated abilities of the exiled card. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Worldwalker Helm | unaudited | If you would create one or more artifact tokens, instead create those tokens plus an additional Map token. | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Fomori Vault | handled | {3}, {T}, Discard a card: Look at the top X cards of your library, where X is the number of artifacts you control. Put one of those cards into your hand and the | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Greed's Gambit | handled | When this enchantment enters, you draw three cards, gain 6 life, and create three 2/1 black Bat creature tokens with flying. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hostile Investigator | handled | When this creature enters, target opponent discards a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Legion Extruder | handled | When this artifact enters, it deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lost Jitte | handled | Whenever equipped creature deals combat damage, put a charge counter on Lost Jitte. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Lotus Ring | handled | Equipped creature gets +3/+3 and has vigilance and "{T}, Sacrifice this creature: Add three mana of any one color." | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Oltec Matterweaver | handled | Whenever you cast a creature spell, choose one — • Create a 1/1 colorless Gnome artifact creature token. • Create a token that's a copy of target artifact token | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>4 cards</summary>

- Harvester of Misery
- Molten Duplication
- Pest Control
- Simulacrum Synthesizer

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of combat on your turn, draw a card. then you may exile an artifact or creature card from your hand. if you do, create a token that"..."s a N/N | 1 | Nexus of Becoming | big |
| at the beginning of your upkeep, exile the top N cards of your library, where N is the number of card types among other nonland permanents you control. you may  | 1 | Loot, the Key to Everything | big |
| if you would create one or more artifact tokens, instead create those tokens plus an additional map token. | 1 | Worldwalker Helm | big |
| when ~ dies, if it"..."s a copy of it, except it's an artifact in addition to its other types. | 1 | Vaultborn Tyrant | big |
| when ~ enters, search your library for up to five land cards that have different names, exile them, then shuffle. | 1 | Omenpath Journey | big |
| whenever equipped creature deals combat damage to a player, create a treasure token. when you next cast an instant or sorcery spell ~, copy that spell. you may  | 1 | Sword of Wealth and Power | big |
| whenever you cast a spell that"..."s colors. do ~ once each turn. | 1 | Ancient Cornucopia | big |
| whenever you sacrifice ~ or another artifact, you may pay {M}. if you do, at the beginning of the next end step, create a token that's a copy of that artifact. | 1 | Esoteric Duplicator | big |
| whenever ~ attacks, it deals damage to defending player equal to the number of artifacts they control. | 1 | Generous Plunderer | big |
| whenever ~ attacks, you may sacrifice a food. if you do, mill three cards. you may put a permanent card from among them into your hand. | 1 | Bristlebud Farmer | big |
| {M}, exile ~: each player exiles the top seven cards of their library. until your next turn, players may play cards they exiled ~, and they can't play cards fro | 1 | Memory Vessel | big |
| {M}, {M}: for each color among monocolored permanents you control, add one mana of that color. | 1 | Tarnation Vista | big |
| {M}, {M}: put a +N/+N counter on each creature token you control. they gain trample until end of turn. | 1 | Sandstorm Salvager | big |
| {M}, {M}: put a +N/+N counter on target creature you control. then if you control three or more creatures with different powers, you may play the exiled card wi | 1 | Collector's Cage | big |
| {M}: create your choice of a blood token, a clue token, or a food token. | 1 | Transmutation Font | big |
| ~ has all activated abilities of the exiled card. | 1 | Territory Forge | big |

## Notes



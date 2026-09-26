# Urza's Legacy (ulg)

- Expansion: 025
- Set code: `ulg`
- Release date: 1999-02-15
- Cards in scope (Modern/Pioneer/Standard-legal): 28

## Legality

| Format | Legal cards |
|---|---|
| Modern | 28 |
| Pioneer | 4 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 3 | 10.7% |
| Works (untested) | 19 | 67.9% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 6 | 21.4% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Avalanche Riders | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Beast of Burden | silent | Beast of Burden's power and toughness are each equal to the number of creatures on the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bone Shredder | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Faerie Conclave | silent | {1}{U}: This land becomes a 2/1 blue Faerie creature with flying until end of turn. It's still a land. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Karmic Guide | silent | Echo | no machine in the engine executes this keyword | Y/-/- | not_working |
| Defense Grid | notice | Each spell costs {3} more to cast except during its controller's turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Angelic Curator | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Archivist | handled | {T}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Erase | handled | Exile target enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fleeting Image | handled | {1}{U}: Return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Forbidding Watchtower | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghitu Encampment | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Giant Cockroach | handled |  |  | Y/-/- | not_tested |
| Levitation | handled | Creatures you control have flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Might of Oaks | handled | Target creature gets +7/+7 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Opportunity | handled | Target player draws four cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Plague Beetle | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Quicksilver Amulet | handled | {4}, {T}: You may put a creature card from your hand onto the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rebuild | handled | Return all artifacts to their owners' hands. Cycling {2} ({2}, Discard this card: Draw a card.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Spawning Pool | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tragic Poet | handled | {T}, Sacrifice this creature: Return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Treetop Village | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Viashino Sandscout | handled | At the beginning of the end step, return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wing Snare | handled | Destroy target creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Yavimaya Wurm | handled | Trample | machines/combat.py | Y/-/- | not_tested |

## Fully supported

<details>
<summary>3 cards</summary>

- Phyrexian Plaguelord
- Rancor
- Unearth

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| echo | 3 | Avalanche Riders, Bone Shredder, Karmic Guide | ulg |
| each spell costs {M} more to cast except during its controller's turn. | 1 | Defense Grid | ulg |
| {M}{M}: ~ becomes a N/N blue faerie creature with flying until end of turn. it's still a land. | 1 | Faerie Conclave | ulg |
| ~'s power and toughness are each equal to the number of creatures on the battlefield. | 1 | Beast of Burden | ulg |

## Notes



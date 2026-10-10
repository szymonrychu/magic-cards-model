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
| Works (untested) | 24 | 85.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 3.6% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Defense Grid | notice | Each spell costs {3} more to cast except during its controller's turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Angelic Curator | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Archivist | handled | {T}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Avalanche Riders | handled | When this creature enters, destroy target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Beast of Burden | handled | Beast of Burden's power and toughness are each equal to the number of creatures on the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bone Shredder | handled | When this creature enters, destroy target nonartifact, nonblack creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Erase | handled | Exile target enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Faerie Conclave | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fleeting Image | handled | {1}{U}: Return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Forbidding Watchtower | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ghitu Encampment | handled | This land enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Giant Cockroach | handled |  |  | Y/-/- | not_tested |
| Karmic Guide | handled | When this creature enters, return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
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
| each spell costs {M} more to cast except during its controller's turn. | 1 | Defense Grid | ulg |

## Notes



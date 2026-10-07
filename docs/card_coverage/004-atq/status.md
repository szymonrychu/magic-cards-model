# Antiquities (atq)

- Expansion: 004
- Set code: `atq`
- Release date: 1994-03-04
- Cards in scope (Modern/Pioneer/Standard-legal): 20

## Legality

| Format | Legal cards |
|---|---|
| Modern | 20 |
| Pioneer | 4 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 5 | 25.0% |
| Works (untested) | 8 | 40.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 7 | 35.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Circle of Protection: Artifacts | silent | {2}: The next time an artifact source of your choice would deal damage to you this turn, prevent that damage. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hurkyl's Recall | silent | Return all artifacts target player owns to their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Primal Clay | silent | As this creature enters, it becomes your choice of a 3/3 artifact creature, a 2/2 artifact creature with flying, or a 1/6 Wall artifact creature with defender i | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shatterstorm | silent | Destroy all artifacts. They can't be regenerated. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| The Rack | silent | At the beginning of the chosen player's upkeep, this artifact deals X damage to that player, where X is 3 minus the number of cards in their hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Detonate | notice | Destroy target artifact with mana value X. It can't be regenerated. Detonate deals X damage to that artifact's controller. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Yawgmoth Demon | notice | At the beginning of your upkeep, you may sacrifice an artifact. If you don't, tap this creature and it deals 2 damage to you. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Atog | handled | Sacrifice an artifact: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Colossus of Sardia | handled | This creature doesn't untap during your untap step. | the engine reads this text and performs it | Y/-/- | not_tested |
| Feldon's Cane | handled | {T}, Exile this artifact: Shuffle your graveyard into your library. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Millstone | handled | {2}, {T}: Target player mills two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sage of Lat-Nam | handled | {T}, Sacrifice an artifact: Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Triskelion | handled | This creature enters with three +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Wall of Spears | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Yotian Soldier | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |

## Fully supported

<details>
<summary>5 cards</summary>

- Mishra's Factory
- Ornithopter
- Urza's Mine
- Urza's Power Plant
- Urza's Tower

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| as ~ enters, it becomes your choice of a N/N artifact creature, a N/N artifact creature with flying, or a N/N wall artifact creature with defender in addition t | 1 | Primal Clay | atq |
| at the beginning of the chosen player's upkeep, ~ deals N damage to that player, where N is N minus the number of cards in their hand. | 1 | The Rack | atq |
| at the beginning of your upkeep, you may sacrifice an artifact. if you don't, tap ~ and it deals N damage to you. | 1 | Yawgmoth Demon | atq |
| destroy all artifacts. they can't be regenerated. | 1 | Shatterstorm | atq |
| destroy target artifact with mana value N. it can"..."s controller. | 1 | Detonate | atq |
| return all artifacts target player owns to their hand. | 1 | Hurkyl's Recall | atq |
| {M}: the next time an artifact source of your choice would deal damage to you ~, prevent that damage. | 1 | Circle of Protection: Artifacts | atq |

## Notes



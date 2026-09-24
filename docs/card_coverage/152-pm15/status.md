# Magic 2015 Promos (pm15)

- Expansion: 152
- Set code: `pm15`
- Release date: 2014-07-17
- Cards in scope (Modern/Pioneer/Standard-legal): 11

## Legality

| Format | Legal cards |
|---|---|
| Modern | 11 |
| Pioneer | 11 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 9.1% |
| Not tested (handled, untested) | 2 | 18.2% |
| Not working (silent / notice / error) | 8 | 72.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Chasm Skulker | silent | When this creature dies, create X 1/1 blue Squid creature tokens with islandwalk, where X is the number of +1/+1 counters on this creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Goblin Rabblemaster | silent | Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Goblin. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| In Garruk's Wake | silent | Destroy all creatures you don't control and all planeswalkers you don't control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Indulgent Tormentor | silent | At the beginning of your upkeep, draw a card unless target opponent sacrifices a creature of their choice or pays 3 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mercurial Pretender | silent | You may have this creature enter as a copy of a creature you control, except it has "{2}{U}{U}: Return this creature to its owner's hand." | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Phytotitan | silent | When this creature dies, return it to the battlefield tapped under its owner's control at the beginning of their next upkeep. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Resolute Archangel | silent | When this creature enters, if your life total is less than your starting life total, it becomes equal to your starting life total. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Siege Dragon | silent | When this creature enters, destroy all Walls your opponents control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chief Engineer | unaudited | Artifact spells you cast have convoke. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Reclamation Sage | handled | When this creature enters, you may destroy target artifact or enchantment. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Soul of New Phyrexia | handled | {5}: Permanents you control gain indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Artifact spells you cast have convoke. | Chief Engineer | 1 |
| At the beginning of your upkeep, draw a card unless target opponent sacrifices a creature of their choice or pays 3 life. | Indulgent Tormentor | 1 |
| Destroy all creatures you don't control and all planeswalkers you don't control. | In Garruk's Wake | 1 |
| When this creature dies, create X 1/1 blue Squid creature tokens with islandwalk, where X is the number of +1/+1 counters on this creature. | Chasm Skulker | 1 |
| When this creature dies, return it to the battlefield tapped under its owner's control at the beginning of their next upkeep. | Phytotitan | 1 |
| When this creature enters, destroy all Walls your opponents control. | Siege Dragon | 1 |
| When this creature enters, if your life total is less than your starting life total, it becomes equal to your starting life total. | Resolute Archangel | 1 |
| Whenever this creature attacks, it gets +1/+0 until end of turn for each other attacking Goblin. | Goblin Rabblemaster | 1 |
| You may have this creature enter as a copy of a creature you control, except it has "{2}{U}{U}: Return this creature to its owner's hand." | Mercurial Pretender | 1 |

## Notes



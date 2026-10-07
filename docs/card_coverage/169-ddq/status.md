# Duel Decks: Blessed vs. Cursed (ddq)

- Expansion: 169
- Set code: `ddq`
- Release date: 2016-02-26
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 6 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 16.7% |
| Works (untested) | 2 | 33.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 3 | 50.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Compelling Deterrence | silent | Return target nonland permanent to its owner's hand. Then that player discards a card if you control a Zombie. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mindwrack Demon | silent | Delirium — At the beginning of your upkeep, you lose 4 life unless there are four or more card types among cards in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Pore Over the Pages | silent | Draw three cards, untap up to two lands, then discard a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tooth Collector | handled | When this creature enters, target creature an opponent controls gets -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Topplegeist | handled | When this creature enters, tap target creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Eerie Interlude

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Delirium | 1 | Mindwrack Demon | ddq |
| draw three cards, untap up to two lands, then discard a card. | 1 | Pore Over the Pages | ddq |
| return target nonland permanent to its owner's hand. then that player discards a card if you control a zombie. | 1 | Compelling Deterrence | ddq |

## Notes



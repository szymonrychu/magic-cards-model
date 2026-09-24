# Torment (tor)

- Expansion: 037
- Set code: `tor`
- Release date: 2002-02-04
- Cards in scope (Modern/Pioneer/Standard-legal): 14

## Legality

| Format | Legal cards |
|---|---|
| Modern | 14 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 1 | 7.1% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 7 | 50.0% |
| Not working (silent / notice / error) | 6 | 42.9% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Faceless Butcher | silent | When this creature leaves the battlefield, return the exiled card to the battlefield under its owner's control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ghostly Wings | silent | Discard a card: Return enchanted creature to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Mind Sludge | silent | Target player discards a card for each Swamp you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mortal Combat | silent | At the beginning of your upkeep, if twenty or more creature cards are in your graveyard, you win the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mutilate | silent | All creatures get -1/-1 until end of turn for each Swamp you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Pay No Heed | silent | Prevent all damage a source of your choice would deal this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Ambassador Laquatus | handled | {3}: Target player mills three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cabal Coffers | handled |  |  | Y/-/- | not_tested |
| Deep Analysis | handled | Target player draws two cards. Flashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Fiery Temper | handled | Fiery Temper deals 3 damage to any target. Madness {R} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it int | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grim Lavamancer | handled | {R}, {T}, Exile two cards from your graveyard: This creature deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Cultivator | handled | When this creature enters, you may discard any number of land cards. Put that many +1/+1 counters on this creature and draw that many cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Plagiarize

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| All creatures get -1/-1 until end of turn for each Swamp you control. | Mutilate | 1 |
| At the beginning of your upkeep, if twenty or more creature cards are in your graveyard, you win the game. | Mortal Combat | 1 |
| Discard a card: Return enchanted creature to its owner's hand. | Ghostly Wings | 1 |
| Prevent all damage a source of your choice would deal this turn. | Pay No Heed | 1 |
| Target player discards a card for each Swamp you control. | Mind Sludge | 1 |
| When this creature leaves the battlefield, return the exiled card to the battlefield under its owner's control. | Faceless Butcher | 1 |

## Notes



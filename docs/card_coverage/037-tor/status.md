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
| Tested | 5 | 35.7% |
| Works (untested) | 8 | 57.1% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 7.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ghostly Wings | silent | Discard a card: Return enchanted creature to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cabal Coffers | handled |  |  | Y/-/- | not_tested |
| Deep Analysis | handled | Target player draws two cards. Flashback—{1}{U}, Pay 3 life. (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Faceless Butcher | handled | When this creature enters, exile another target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fiery Temper | handled | Fiery Temper deals 3 damage to any target. Madness {R} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it int | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grim Lavamancer | handled | {R}, {T}, Exile two cards from your graveyard: This creature deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mortal Combat | handled | At the beginning of your upkeep, if twenty or more creature cards are in your graveyard, you win the game. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Cultivator | handled | When this creature enters, you may discard any number of land cards. Put that many +1/+1 counters on this creature and draw that many cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>5 cards</summary>

- Ambassador Laquatus
- Mind Sludge
- Mutilate
- Pay No Heed
- Plagiarize

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| discard a card: return enchanted creature to its owner's hand. | 1 | Ghostly Wings | tor |

## Notes



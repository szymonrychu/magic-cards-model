# Portal Three Kingdoms (ptk)

- Expansion: 026
- Set code: `ptk`
- Release date: 1999-05-01
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 2 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 5 | 83.3% |
| Not working (silent / notice / error) | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Imperial Recruiter | silent | When this creature enters, search your library for a creature card with power 2 or less, reveal it, put it into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Ambition's Cost | handled | You draw three cards and lose 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corrupt Court Official | handled | When this creature enters, target opponent discards a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Peach Garden Oath | handled | You gain 2 life for each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Strategic Planning | handled | Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zodiac Monkey | handled | Landwalk | no code needed | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| when ~ enters, search your library for a creature card with power N or less, reveal it, put it into your hand, then shuffle. | 1 | Imperial Recruiter | ptk |

## Notes



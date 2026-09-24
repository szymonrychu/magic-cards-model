# Friday Night Magic 2014 (f14)

- Expansion: 145
- Set code: `f14`
- Release date: 2014-01-01
- Cards in scope (Modern/Pioneer/Standard-legal): 5

## Legality

| Format | Legal cards |
|---|---|
| Modern | 5 |
| Pioneer | 5 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not tested (handled, untested) | 3 | 60.0% |
| Not working (silent / notice / error) | 2 | 40.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Brain Maggot | silent | When this creature enters, target opponent reveals their hand and you choose a nonland card from it. Exile that card until this creature leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fanatic of Xenagos | silent | Tribute | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Banishing Light | handled | When this enchantment enters, exile target nonland permanent an opponent controls until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Bile Blight | handled | Target creature and all other creatures with the same name as that creature get -3/-3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stoke the Flames | handled | Convoke (Your creatures can help cast this spell. Each creature you tap while casting this spell pays for {1} or one mana of that creature's color.) Stoke the F | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Tribute | Fanatic of Xenagos | 1 |
| When this creature enters, target opponent reveals their hand and you choose a nonland card from it. Exile that card until this creature leaves the battlefield. | Brain Maggot | 1 |

## Notes



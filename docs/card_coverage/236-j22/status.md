# Jumpstart 2022 (j22)

- Expansion: 236
- Set code: `j22`
- Release date: 2022-12-02
- Cards in scope (Modern/Pioneer/Standard-legal): 6

## Legality

| Format | Legal cards |
|---|---|
| Modern | 6 |
| Pioneer | 4 |
| Standard | 4 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 1 | 16.7% |
| Works (untested) | 4 | 66.7% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 1 | 16.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Mild-Mannered Librarian | silent | {3}{G}: This creature becomes a Werewolf. Put two +1/+1 counters on it and you draw a card. Activate only once. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Deadly Plot | handled | Choose one — • Destroy target creature or planeswalker. • Return target Zombie creature card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Distinguished Conjurer | handled | Whenever another creature you control enters, you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ingenious Leonin | handled | {3}{W}: Put a +1/+1 counter on another target attacking creature you control. If that creature is a Cat, it gains first strike until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Suspicious Shambler | handled | {4}{B}{B}, Exile this card from your graveyard: Create two 2/2 black Zombie creature tokens. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>1 cards</summary>

- Ophiomancer

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| {M}{M}: ~ becomes a werewolf. put two +N/+N counters on it and you draw a card. activate only once. | 1 | Mild-Mannered Librarian | j22 |

## Notes



# Ice Age (ice)

- Expansion: 009
- Set code: `ice`
- Release date: 1995-06-03
- Cards in scope (Modern/Pioneer/Standard-legal): 35

## Legality

| Format | Legal cards |
|---|---|
| Modern | 35 |
| Pioneer | 11 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 7 | 20.0% |
| Works (untested) | 19 | 54.3% |
| Partial (unaudited) | 2 | 5.7% |
| Not working | 7 | 20.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Enduring Renewal | silent | Whenever a creature is put into your graveyard from the battlefield, return it to your hand. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Goblin Snowman | silent | Whenever this creature blocks, prevent all combat damage that would be dealt to and dealt by it this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jester's Cap | silent | {2}, {T}, Sacrifice this artifact: Search target player's library for three cards and exile them. Then that player shuffles. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Kjeldoran Royal Guard | silent | {T}: All combat damage that would be dealt to you by unblocked creatures this turn is dealt to this creature instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Merieke Ri Berit | silent | {T}: Gain control of target creature for as long as you control Merieke Ri Berit. When Merieke Ri Berit leaves the battlefield or becomes untapped, destroy that | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Orcish Librarian | silent | {R}, {T}: Look at the top eight cards of your library. Exile four of them at random, then put the rest on top of your library in any order. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Wrath of Marit Lage | silent | When this enchantment enters, tap all red creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lhurgoyf | unaudited | Lhurgoyf's power is equal to the number of creature cards in all graveyards and its toughness is equal to that number plus 1. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Zur's Weirding | unaudited | Players play with their hands revealed. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Abyssal Specter | handled | Whenever this creature deals damage to a player, that player discards a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Adarkar Wastes | handled |  |  | Y/Y/- | not_tested |
| Balduvian Barbarians | handled |  |  | Y/-/- | not_tested |
| Blinking Spirit | handled | {0}: Return this creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brown Ouphe | handled | {1}{G}, {T}: Counter target activated ability from an artifact source. | the engine reads this text and performs it | Y/-/- | not_tested |
| Brushland | handled |  |  | Y/Y/- | not_tested |
| Dark Banishing | handled | Destroy target nonblack creature. It can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deflection | handled | Change the target of target spell with a single target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fiery Justice | handled | Fiery Justice deals 5 damage divided as you choose among any number of targets. Target opponent gains 5 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fyndhorn Elder | handled |  |  | Y/-/- | not_tested |
| Sabretooth Tiger | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Scaled Wurm | handled |  |  | Y/-/- | not_tested |
| Snow-Covered Mountain | handled |  |  | Y/Y/- | not_tested |
| Snow-Covered Plains | handled |  |  | Y/Y/- | not_tested |
| Snow-Covered Swamp | handled |  |  | Y/Y/- | not_tested |
| Stormbind | handled | {2}, Discard a card at random: This enchantment deals 2 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sulfurous Springs | handled |  |  | Y/Y/- | not_tested |
| Underground River | handled |  |  | Y/Y/- | not_tested |
| Zuran Orb | handled | Sacrifice a land: You gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>7 cards</summary>

- Incinerate
- Karplusan Forest
- Karplusan Yeti
- Pyroclasm
- Snow-Covered Forest
- Snow-Covered Island
- Vexing Arcanix

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| players play with their hands revealed. | 1 | Zur's Weirding | ice |
| when ~ enters, tap all red creatures. | 1 | Wrath of Marit Lage | ice |
| whenever a creature is put into your graveyard from the battlefield, return it to your hand. | 1 | Enduring Renewal | ice |
| whenever ~ blocks, prevent all combat damage that would be dealt to and dealt by it ~. | 1 | Goblin Snowman | ice |
| {M}, {M}, sacrifice ~: search target player's library for three cards and exile them. then that player shuffles. | 1 | Jester's Cap | ice |
| {M}, {M}: look at the top eight cards of your library. exile four of them at random, then put the rest on top of your library in any order. | 1 | Orcish Librarian | ice |
| {M}: all combat damage that would be dealt to you by unblocked creatures ~ is dealt to ~ instead. | 1 | Kjeldoran Royal Guard | ice |
| {M}: gain control of target creature for as long as you control ~. when ~ leaves the battlefield or becomes untapped, destroy that creature. it can't be regener | 1 | Merieke Ri Berit | ice |
| ~'s power is equal to the number of creature cards in all graveyards and its toughness is equal to that number plus N. | 1 | Lhurgoyf | ice |

## Notes



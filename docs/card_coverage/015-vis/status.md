# Visions (vis)

- Expansion: 015
- Set code: `vis`
- Release date: 1997-02-03
- Cards in scope (Modern/Pioneer/Standard-legal): 23

## Legality

| Format | Legal cards |
|---|---|
| Modern | 23 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 0 | 0.0% |
| Partial (unaudited) | 1 | 4.3% |
| Not tested (handled, untested) | 14 | 60.9% |
| Not working (silent / notice / error) | 8 | 34.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Crypt Rats | silent | {X}: This creature deals X damage to each creature and each player. Spend only black mana on X. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Honorable Passage | silent | The next time a source of your choice would deal damage to any target this turn, prevent that damage. If damage from a red source is prevented this way, Honorab | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quicksand | silent | {T}, Sacrifice this land: Target attacking creature without flying gets -1/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Relentless Assault | silent | Untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an additional main phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stampeding Wildebeests | silent | At the beginning of your upkeep, return a green creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Summer Bloom | silent | You may play up to three additional lands this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Suq'Ata Lancer | silent | Flanking | no machine in the engine executes this keyword | Y/-/- | not_working |
| Teferi's Puzzle Box | silent | At the beginning of each player's draw step, that player puts the cards in their hand on the bottom of their library in any order, then draws that many cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Cloud Elemental | unaudited | This creature can block only creatures with flying. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Archangel | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Coercion | handled | Target opponent reveals their hand. You choose a card from it. That player discards that card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Creeping Mold | handled | Destroy target artifact, enchantment, or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Funeral Charm | handled | Choose one — • Target player discards a card. • Target creature gets +2/-1 until end of turn. • Target creature gains swampwalk until end of turn. (It can't be  | the engine reads this text and performs it | Y/-/- | not_tested |
| Hulking Cyclops | handled | This creature can't block. | the engine reads this text and performs it | Y/-/- | not_tested |
| Impulse | handled | Look at the top four cards of your library. Put one of them into your hand and the rest on the bottom of your library in any order. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Infantry Veteran | handled | {T}: Target attacking creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Inspiration | handled | Target player draws two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Man-o'-War | handled | When this creature enters, return target creature to its owner's hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nekrataal | handled | When this creature enters, destroy target nonartifact, nonblack creature. That creature can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Quirion Ranger | handled | Return a Forest you control to its owner's hand: Untap target creature. Activate only once each turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| River Boa | handled | {G}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Tremor | handled | Tremor deals 1 damage to each creature without flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Warrior's Honor | handled | Creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |

## Fully supported

<details>
<summary>0 cards</summary>


</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| At the beginning of each player's draw step, that player puts the cards in their hand on the bottom of their library in any order, then draws that many cards. | Teferi's Puzzle Box | 1 |
| At the beginning of your upkeep, return a green creature you control to its owner's hand. | Stampeding Wildebeests | 1 |
| Flanking | Suq'Ata Lancer | 1 |
| {T}, Sacrifice this land: Target attacking creature without flying gets -1/-2 until end of turn. | Quicksand | 1 |
| The next time a source of your choice would deal damage to any target this turn, prevent that damage. If damage from a red source is prevented this way, Honorab | Honorable Passage | 1 |
| This creature can block only creatures with flying. | Cloud Elemental | 1 |
| {X}: This creature deals X damage to each creature and each player. Spend only black mana on X. | Crypt Rats | 1 |
| Untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an additional main phase. | Relentless Assault | 1 |
| You may play up to three additional lands this turn. | Summer Bloom | 1 |

## Notes



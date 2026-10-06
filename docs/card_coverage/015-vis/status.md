# Visions (vis)

- Expansion: 015
- Set code: `vis`
- Release date: 1997-02-03
- Cards in scope (Modern/Pioneer/Standard-legal): 24

## Legality

| Format | Legal cards |
|---|---|
| Modern | 24 |
| Pioneer | 3 |
| Standard | 0 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 2 | 8.3% |
| Works (untested) | 14 | 58.3% |
| Partial (unaudited) | 1 | 4.2% |
| Not working | 7 | 29.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Honorable Passage | silent | The next time a source of your choice would deal damage to any target this turn, prevent that damage. If damage from a red source is prevented this way, Honorab | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Quicksand | silent | {T}, Sacrifice this land: Target attacking creature without flying gets -1/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Relentless Assault | silent | Untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an additional main phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shrieking Drake | silent | When this creature enters, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stampeding Wildebeests | silent | At the beginning of your upkeep, return a green creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Summer Bloom | silent | You may play up to three additional lands this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
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
<summary>2 cards</summary>

- Crypt Rats
- Suq'Ata Lancer

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| at the beginning of each player's draw step, that player puts the cards in their hand on the bottom of their library in any order, then draws that many cards. | 1 | Teferi's Puzzle Box | vis |
| at the beginning of your upkeep, return a green creature you control to its owner's hand. | 1 | Stampeding Wildebeests | vis |
| the next time a source of your choice would deal damage to any target ~, prevent that damage. if damage from a red source is prevented ~, ~ deals that much dama | 1 | Honorable Passage | vis |
| untap all creatures that attacked ~. after ~ phase, there is an additional combat phase followed by an additional main phase. | 1 | Relentless Assault | vis |
| when ~ enters, return a creature you control to its owner's hand. | 1 | Shrieking Drake | vis |
| you may play up to three additional lands ~. | 1 | Summer Bloom | vis |
| {M}, sacrifice ~: target attacking creature without flying gets -N/-N until end of turn. | 1 | Quicksand | vis |
| ~ can block only creatures with flying. | 1 | Cloud Elemental | vis |

## Notes



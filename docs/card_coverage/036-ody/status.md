# Odyssey (ody)

- Expansion: 036
- Set code: `ody`
- Release date: 2001-10-01
- Cards in scope (Modern/Pioneer/Standard-legal): 51

## Legality

| Format | Legal cards |
|---|---|
| Modern | 51 |
| Pioneer | 9 |
| Standard | 2 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 11.8% |
| Partial (unaudited) | 4 | 7.8% |
| Not tested (handled, untested) | 27 | 52.9% |
| Not working (silent / notice / error) | 14 | 27.5% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Aura Graft | silent | Gain control of target Aura that's attached to a permanent. Attach it to another permanent it can enchant. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Aven Windreader | silent | {1}{U}: Target player reveals the top card of their library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Battle of Wits | silent | At the beginning of your upkeep, if you have 200 or more cards in your library, you win the game. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Chance Encounter | silent | Whenever you win a coin flip, put a luck counter on this enchantment. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Deluge | silent | Tap all creatures without flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Haunting Echoes | silent | Exile all cards from target player's graveyard other than basic land cards. For each card exiled this way, search that player's library for all cards with the s | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Magnivore | silent | Magnivore's power and toughness are each equal to the number of sorcery cards in all graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mirari | silent | Whenever you cast an instant or sorcery spell, you may pay {3}. If you do, copy that spell. You may choose new targets for the copy. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mortivore | silent | Mortivore's power and toughness are each equal to the number of creature cards in all graveyards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Mystic Enforcer | silent | Threshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+3 and has flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shadowmage Infiltrator | silent | Fear | no machine in the engine executes this keyword | Y/-/- | not_working |
| Time Stretch | silent | Target player takes two extra turns after this one. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Shelter | notice | Target creature you control gains protection from the color of your choice until end of turn. Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Squirrel Mob | notice | This creature gets +1/+1 for each other Squirrel on the battlefield. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Caustic Tar | unaudited | Enchanted land has "{T}: Target player loses 3 life." | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ember Beast | unaudited | This creature can't attack or block alone. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ground Seal | unaudited | Cards in graveyards can't be the targets of spells or abilities. | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Squirrel Nest | unaudited | Enchanted land has "{T}: Create a 1/1 green Squirrel creature token." | a static ability no support check audits - not verified either way | Y/-/- | partial |
| Afflict | handled | Target creature gets -1/-1 until end of turn. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Auramancer | handled | When this creature enters, you may return target enchantment card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aven Cloudchaser | handled | When this creature enters, destroy target enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Aven Fisher | handled | When this creature dies, you may draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Aven Flock | handled | {W}: This creature gets +0/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blessed Orator | handled | Other creatures you control get +0/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Braids, Cabal Minion | handled | At the beginning of each player's upkeep, that player sacrifices an artifact, creature, or land of their choice. | the engine reads this text and performs it | Y/-/- | not_tested |
| Call of the Herd | handled | Create a 3/3 green Elephant creature token. Flashback {3}{G} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Cephalid Coliseum | handled | Threshold — {U}, {T}, Sacrifice this land: Target player draws three cards, then discards three cards. Activate only if there are seven or more cards in your gr | the engine reads this text and performs it | Y/-/- | not_tested |
| Concentrate | handled | Draw three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crypt Creeper | handled | Sacrifice this creature: Exile target card from a graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Demolish | handled | Destroy target artifact or land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deserted Temple | handled | {1}, {T}: Untap target land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dusk Imp | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Execute | handled | Destroy target white creature. It can't be regenerated. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Firebolt | handled | Firebolt deals 2 damage to any target. Flashback {4}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it.) | the engine reads this text and performs it | Y/-/- | not_tested |
| Ivy Elemental | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kamahl, Pit Fighter | handled | {T}: Kamahl deals 3 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mindslicer | handled | When this creature dies, each player discards their hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nantuko Disciple | handled | {G}, {T}: Target creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nimble Mongoose | handled | Threshold — This creature gets +2/+2 as long as there are seven or more cards in your graveyard. | the engine reads this text and performs it | Y/-/- | not_tested |
| Persuasion | handled | You control enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Puppeteer | handled | {U}, {T}: You may tap or untap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Reckless Charge | handled | Target creature gets +3/+0 and gains haste until end of turn. Flashback {2}{R} (You may cast this card from your graveyard for its flashback cost. Then exile it | the engine reads this text and performs it | Y/-/- | not_tested |
| Upheaval | handled | Return all permanents to their owners' hands. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zombie Infestation | handled | Discard two cards: Create a 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Zombify | handled | Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/Y | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Barbarian Ring
- Diabolic Tutor
- Millikin
- Peek
- Syncopate
- Traumatize

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Enchanted land has "{T}: Create a 1/1 green Squirrel creature token." | Caustic Tar, Squirrel Nest | 2 |
| At the beginning of your upkeep, if you have 200 or more cards in your library, you win the game. | Battle of Wits | 1 |
| Cards in graveyards can't be the targets of spells or abilities. | Ground Seal | 1 |
| Exile all cards from target player's graveyard other than basic land cards. For each card exiled this way, search that player's library for all cards with the s | Haunting Echoes | 1 |
| Fear | Shadowmage Infiltrator | 1 |
| Gain control of target Aura that's attached to a permanent. Attach it to another permanent it can enchant. | Aura Graft | 1 |
| Magnivore's power and toughness are each equal to the number of sorcery cards in all graveyards. | Magnivore | 1 |
| Mortivore's power and toughness are each equal to the number of creature cards in all graveyards. | Mortivore | 1 |
| Tap all creatures without flying. | Deluge | 1 |
| Target creature you control gains protection from the color of your choice until end of turn. Draw a card. | Shelter | 1 |
| {1}{U}: Target player reveals the top card of their library. | Aven Windreader | 1 |
| Target player takes two extra turns after this one. | Time Stretch | 1 |
| This creature can't attack or block alone. | Ember Beast | 1 |
| This creature gets +1/+1 for each other Squirrel on the battlefield. | Squirrel Mob | 1 |
| Threshold — As long as there are seven or more cards in your graveyard, this creature gets +3/+3 and has flying. | Mystic Enforcer | 1 |
| Whenever you cast an instant or sorcery spell, you may pay {3}. If you do, copy that spell. You may choose new targets for the copy. | Mirari | 1 |
| Whenever you win a coin flip, put a luck counter on this enchantment. | Chance Encounter | 1 |

## Notes



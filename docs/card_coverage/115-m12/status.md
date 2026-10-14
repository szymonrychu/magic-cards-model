# Magic 2012 (m12)

- Expansion: 115
- Set code: `m12`
- Release date: 2011-07-15
- Cards in scope (Modern/Pioneer/Standard-legal): 98

## Legality

| Format | Legal cards |
|---|---|
| Modern | 98 |
| Pioneer | 21 |
| Standard | 6 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 21 | 21.4% |
| Works (untested) | 62 | 63.3% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 15 | 15.3% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Angelic Destiny | silent | When enchanted creature dies, return this card to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Arachnus Spinner | silent | Tap an untapped Spider you control: Search your graveyard and/or library for a card named Arachnus Web and put it onto the battlefield attached to target creatu | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arbalest Elite | silent | {2}{W}, {T}: This creature deals 3 damage to target attacking or blocking creature. This creature doesn't untap during your next untap step. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Bloodlord of Vaasgoth | silent | Whenever you cast a Vampire creature spell, it gains bloodthirst 3. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Circle of Flame | silent | Whenever a creature without flying attacks you or a planeswalker you control, this enchantment deals 1 damage to that creature. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Druidic Satchel | silent | {2}, {T}: Reveal the top card of your library. If it's a creature card, create a 1/1 green Saproling creature token. If it's a land card, put that card onto the | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Goblin Bangchuckers | silent | {T}: Flip a coin. If you win the flip, this creature deals 2 damage to any target. If you lose the flip, this creature deals 2 damage to itself. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Jace, Memory Adept | silent | −7: Any number of target players each draw twenty cards. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Monomania | silent | Target player chooses a card in their hand and discards the rest. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Scrambleverse | silent | For each nonland permanent, choose a player at random. Then each player gains control of each permanent for which they were chosen. Untap those permanents. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Stonehorn Dignitary | silent | When this creature enters, target opponent skips their next combat phase. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Tectonic Rift | silent | Destroy target land. Creatures without flying can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Timely Reinforcements | silent | If you have less life than an opponent, you gain 6 life. If you control fewer creatures than an opponent, create three 1/1 white Soldier creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Vengeful Pharaoh | silent | Whenever combat damage is dealt to you or a planeswalker you control, if this card is in your graveyard, destroy target attacking creature, then put this card o | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Visions of Beyond | silent | Draw a card. If a graveyard has twenty or more cards in it, draw three cards instead. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Alabaster Mage | handled | {1}{W}: Target creature you control gains lifelink until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Amphin Cutthroat | handled |  |  | Y/-/- | not_tested |
| Armored Warhorse | handled |  |  | Y/-/- | not_tested |
| Aven Fleetwing | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Azure Mage | handled | {3}{U}: Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Benalish Veteran | handled | Whenever this creature attacks, it gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Blood Ogre | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Bloodrage Vampire | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Bonebreaker Giant | handled |  |  | Y/-/- | not_tested |
| Buried Ruin | handled | {2}, {T}, Sacrifice this land: Return target artifact card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Carnage Wurm | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Chandra's Phoenix | handled | Whenever an opponent is dealt damage by a red instant or sorcery spell you control or by a red planeswalker you control, return this card from your graveyard to | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra, the Firebrand | handled | +1: Chandra deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Chasm Drake | handled | Whenever this creature attacks, target creature you control gains flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crimson Mage | handled | {R}: Target creature you control gains haste until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Crumbling Colossus | handled | When this creature attacks, sacrifice it at end of combat. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dark Favor | handled | When this Aura enters, you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Devouring Swarm | handled | Sacrifice a creature: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Divine Favor | handled | When this Aura enters, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drifting Shade | handled | {B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Duskhunter Bat | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Furyborn Hellkite | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Garruk's Horde | handled | Play with the top card of your library revealed. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garruk, Primal Hunter | handled | +1: Create a 3/3 green Beast creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gideon's Avenger | handled | Whenever a creature an opponent controls becomes tapped, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gideon's Lawkeeper | handled | {W}, {T}: Tap target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Goblin Fireslinger | handled | {T}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/-/- | not_tested |
| Greatsword | handled | Equipped creature gets +3/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Griffin Rider | handled | As long as you control a Griffin creature, this creature gets +3/+3 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guardians' Pledge | handled | White creatures you control get +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hideous Visage | handled | Creatures you control gain intimidate until end of turn. (Each of those creatures can't be blocked except by artifact creatures and/or creatures that share a co | the engine reads this text and performs it | Y/-/- | not_tested |
| Jade Mage | handled | {2}{G}: Create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kite Shield | handled | Equipped creature gets +0/+3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lord of the Unreal | handled | Illusion creatures you control get +1/+1 and have hexproof. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lurking Crocodile | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Manalith | handled |  |  | Y/Y/- | not_tested |
| Master Thief | handled | When this creature enters, gain control of target artifact for as long as you control this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk Mesmerist | handled | {U}, {T}: Target player mills two cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mind Unbound | handled | At the beginning of your upkeep, put a lore counter on this enchantment, then draw a card for each lore counter on this enchantment. | the engine reads this text and performs it | Y/-/- | not_tested |
| Onyx Mage | handled | {1}{B}: Target creature you control gains deathtouch until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Peregrine Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Phantasmal Bear | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phantasmal Dragon | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pride Guardian | handled | Whenever this creature blocks, you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Primordial Hydra | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rune-Scarred Demon | handled | When this creature enters, search your library for a card, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rusted Sentinel | handled | This creature enters tapped. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sorin's Thirst | handled | Sorin's Thirst deals 2 damage to target creature and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sorin's Vengeance | handled | Sorin's Vengeance deals 10 damage to target player or planeswalker and you gain 10 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sphinx of Uthuun | handled | When this creature enters, reveal the top five cards of your library. An opponent separates those cards into two piles. Put one pile into your hand and the othe | the engine reads this text and performs it | Y/-/- | not_tested |
| Spirit Mantle | handled | Enchanted creature gets +1/+1 and has protection from creatures. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stave Off | handled | Target creature gains protection from the color of your choice until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stingerfling Spider | handled | When this creature enters, you may destroy target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stormblood Berserker | handled | Bloodthirst | machines/keywords.py | Y/-/- | not_tested |
| Swiftfoot Boots | handled | Equipped creature has hexproof and haste. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Taste of Blood | handled | Taste of Blood deals 1 damage to target player or planeswalker and you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Titanic Growth | handled | Target creature gets +4/+4 until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Tormented Soul | handled | This creature can't block and can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Trollhide | handled | Enchanted creature gets +2/+2 and has "{1}{G}: Regenerate this creature." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vampire Outcasts | handled | Lifelink | machines/combat.py | Y/-/- | not_tested |
| Wall of Torches | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Wring Flesh | handled | Target creature gets -3/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>21 cards</summary>

- Adaptive Automaton
- Aegis Angel
- Arachnus Web
- Crown of Empires
- Doubling Chant
- Dungrove Elder
- Frost Breath
- Gladecover Scout
- Gorehorn Minotaurs
- Grand Abolisher
- Hunter's Insight
- Jace's Archivist
- Personal Sanctuary
- Phantasmal Image
- Scepter of Empires
- Skinshifter
- Skywinder Drake
- Sundial of the Infinite
- Throne of Empires
- Turn to Frog
- Warstorm Surge

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| destroy target land. creatures without flying can't block ~. | 1 | Tectonic Rift | m12 |
| draw a card. if a graveyard has twenty or more cards in it, draw three cards instead. | 1 | Visions of Beyond | m12 |
| for each nonland permanent, choose a player at random. then each player gains control of each permanent for which they were chosen. untap those permanents. | 1 | Scrambleverse | m12 |
| if you have less life than an opponent, you gain N life. if you control fewer creatures than an opponent, create three N/N white soldier creature tokens. | 1 | Timely Reinforcements | m12 |
| tap an untapped spider you control: search your graveyard and/or library for a card named arachnus web and put it onto the battlefield attached to target creatu | 1 | Arachnus Spinner | m12 |
| target player chooses a card in their hand and discards the rest. | 1 | Monomania | m12 |
| when enchanted creature dies, return ~ to its owner's hand. | 1 | Angelic Destiny | m12 |
| when ~ enters, target opponent skips their next combat phase. | 1 | Stonehorn Dignitary | m12 |
| whenever a creature without flying attacks you or a planeswalker you control, ~ deals N damage to that creature. | 1 | Circle of Flame | m12 |
| whenever combat damage is dealt to you or a planeswalker you control, if ~ is in your graveyard, destroy target attacking creature, then put ~ on top of your li | 1 | Vengeful Pharaoh | m12 |
| whenever you cast a vampire creature spell, it gains bloodthirst N. | 1 | Bloodlord of Vaasgoth | m12 |
| {M}, {M}: reveal the top card of your library. if it"..."s a land card, put that card onto the battlefield under your control. if it's a noncreature, nonland ca | 1 | Druidic Satchel | m12 |
| {M}: flip a coin. if you win the flip, ~ deals N damage to any target. if you lose the flip, ~ deals N damage to itself. | 1 | Goblin Bangchuckers | m12 |
| {M}{M}, {M}: ~ deals N damage to target attacking or blocking creature. ~ doesn't untap during your next untap step. | 1 | Arbalest Elite | m12 |
| −N: any number of target players each draw twenty cards. | 1 | Jace, Memory Adept | m12 |

## Notes



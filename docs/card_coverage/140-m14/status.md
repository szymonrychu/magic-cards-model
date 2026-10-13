# Magic 2014 (m14)

- Expansion: 140
- Set code: `m14`
- Release date: 2013-07-19
- Cards in scope (Modern/Pioneer/Standard-legal): 113

## Legality

| Format | Legal cards |
|---|---|
| Modern | 113 |
| Pioneer | 113 |
| Standard | 4 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 22 | 19.5% |
| Works (untested) | 71 | 62.8% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 20 | 17.7% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ajani's Chosen | silent | Whenever an enchantment you control enters, create a 2/2 white Cat creature token. If that enchantment is an Aura, you may attach it to the token. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blightcaster | silent | Whenever you cast an enchantment spell, you may have target creature get -2/-2 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chandra, Pyromaster | silent | −7: Exile the top ten cards of your library. Choose an instant or sorcery card exiled this way and copy it three times. You may cast the copies without paying t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dismiss into Dream | silent | Each creature your opponents control is an Illusion in addition to its other types and has "When this creature becomes the target of a spell or ability, sacrifi | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Elite Arcanist | silent | {X}, {T}: Copy the exiled card. You may cast the copy without paying its mana cost. X is the mana value of the exiled card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Goblin Diplomats | silent | {T}: Each creature attacks this turn if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Guardian of the Ages | silent | When a creature attacks you or a planeswalker you control, if this creature has defender, it loses defender and gains trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Haunted Plate Mail | silent | {0}: Until end of turn, this permanent becomes a 4/4 Spirit artifact creature that's no longer an Equipment. Activate only if you control no creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Molten Birth | silent | Create two 1/1 red Elemental creature tokens, then flip a coin. If you win the flip, return Molten Birth to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rise of the Dark Realms | silent | Put all creature cards from all graveyards onto the battlefield under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Savage Summoning | silent | This spell can't be countered. The next creature spell you cast this turn can be cast as though it had flash. That spell can't be countered. That creature enter | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Seismic Stomp | silent | Creatures without flying can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Staff of the Death Magus | silent | Whenever you cast a black spell or a Swamp you control enters, you gain 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Staff of the Flame Magus | silent | Whenever you cast a red spell or a Mountain you control enters, you gain 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Staff of the Mind Magus | silent | Whenever you cast a blue spell or an Island you control enters, you gain 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Staff of the Sun Magus | silent | Whenever you cast a white spell or a Plains you control enters, you gain 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Staff of the Wild Magus | silent | Whenever you cast a green spell or a Forest you control enters, you gain 1 life. | this trigger's condition can never be satisfied - it never triggers | Y/Y/- | not_working |
| Enlarge | notice | Target creature gets +7/+7 and gains trample until end of turn. It must be blocked this turn if able. (A creature with trample can deal excess combat damage to  | unparsed remainder: It must be blocked this turn if able. | Y/Y/- | not_working |
| Jace's Mindseeker | notice | When this creature enters, target opponent mills five cards. You may cast an instant or sorcery spell from among them without paying its mana cost. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Scavenging Ooze | notice | {G}: Exile target card from a graveyard. If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Academy Raider | handled | Whenever this creature deals combat damage to a player, you may discard a card. If you do, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Accursed Spirit | handled | Intimidate | machines/keywords.py | Y/Y/- | not_tested |
| Archangel of Thune | handled | Whenever you gain life, put a +1/+1 counter on each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Banisher Priest | handled | When this creature enters, exile target creature an opponent controls until this creature leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Barrage of Expendables | handled | {R}, Sacrifice a creature: This enchantment deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Battle Sliver | handled | Sliver creatures you control get +2/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blood Bairn | handled | Sacrifice another creature: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blur Sliver | handled | Sliver creatures you control have haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bonescythe Sliver | handled | Sliver creatures you control have double strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Burning Earth | handled | Whenever a player taps a nonbasic land for mana, this enchantment deals 1 damage to that player. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Celestial Flare | handled | Target player sacrifices an attacking or blocking creature of their choice. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Charging Griffin | handled | Whenever this creature attacks, it gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Colossal Whale | handled | Whenever this creature attacks, you may exile target creature defending player controls until this creature leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Corpse Hauler | handled | {2}{B}, Sacrifice this creature: Return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cyclops Tyrant | handled | This creature can't block creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dark Prophecy | handled | Whenever a creature you control dies, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dawnstrike Paladin | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Deathgaze Cockatrice | handled | Deathtouch | machines/combat.py | Y/Y/- | not_tested |
| Dragon Egg | handled | When this creature dies, create a 2/2 red Dragon creature token with flying and "{R}: This token gets +1/+0 until end of turn." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Encroaching Wastes | handled | {4}, {T}, Sacrifice this land: Destroy target nonbasic land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fleshpulper Giant | handled | When this creature enters, you may destroy target creature with toughness 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Galerider Sliver | handled | Sliver creatures you control have flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garruk, Caller of Beasts | handled | +1: Reveal the top five cards of your library. Put all creature cards revealed this way into your hand and the rest on the bottom of your library in any order. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Glimpse the Future | handled | Look at the top three cards of your library. Put one of them into your hand and the rest into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gnawing Zombie | handled | {1}{B}, Sacrifice a creature: Target player loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Groundshaker Sliver | handled | Sliver creatures you control have trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hive Stirrings | handled | Create two 1/1 colorless Sliver creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hunt the Weak | handled | Put a +1/+1 counter on target creature you control. Then that creature fights target creature you don't control. (Each deals damage equal to its power to the ot | the engine reads this text and performs it | Y/Y/- | not_tested |
| Illusionary Armor | handled | Enchanted creature gets +4/+4. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Imposing Sovereign | handled | Creatures your opponents control enter tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Into the Wilds | handled | At the beginning of your upkeep, look at the top card of your library. If it's a land card, you may put it onto the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kalonian Tusker | handled |  |  | Y/Y/- | not_tested |
| Lifebane Zombie | handled | When this creature enters, target opponent reveals their hand. You choose a green or white creature card from it and exile that card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liliana's Reaver | handled | Whenever this creature deals combat damage to a player, that player discards a card and you create a tapped 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liturgy of Blood | handled | Destroy target creature. Add {B}{B}{B}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Master of Diversion | handled | Whenever this creature attacks, tap target creature defending player controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Megantic Sliver | handled | Sliver creatures you control get +3/+3. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Messenger Drake | handled | When this creature dies, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mindsparker | handled | Whenever an opponent casts a white or blue instant or sorcery spell, this creature deals 2 damage to that player. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Minotaur Abomination | handled |  |  | Y/Y/- | not_tested |
| Oath of the Ancient Wood | handled | Whenever this enchantment or another enchantment you control enters, you may put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ogre Battledriver | handled | Whenever another creature you control enters, that creature gets +2/+0 and gains haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Predatory Sliver | handled | Sliver creatures you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Primeval Bounty | handled | Whenever you cast a creature spell, create a 3/3 green Beast creature token. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Regathan Firecat | handled |  |  | Y/Y/- | not_tested |
| Ring of Three Wishes | handled | This artifact enters with three wish counters on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rumbling Baloth | handled |  |  | Y/Y/- | not_tested |
| Scourge of Valkas | handled | Whenever this creature or another Dragon you control enters, it deals X damage to any target, where X is the number of Dragons you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seacoast Drake | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Sentinel Sliver | handled | Sliver creatures you control have vigilance. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seraph of the Sword | handled | Prevent all combat damage that would be dealt to this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Soulmender | handled | {T}: You gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sporemound | handled | Landfall — Whenever a land you control enters, create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Steelform Sliver | handled | Sliver creatures you control get +0/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stonehorn Chanter | handled | {5}{W}: This creature gains vigilance and lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Striking Sliver | handled | Sliver creatures you control have first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Strionic Resonator | handled | {2}, {T}: Copy target triggered ability you control. You may choose new targets for the copy. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Syphon Sliver | handled | Sliver creatures you control have lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tenacious Dead | handled | When this creature dies, you may pay {1}{B}. If you do, return it to the battlefield tapped under its owner's control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thorncaster Sliver | handled | Sliver creatures you control have "Whenever this creature attacks, it deals 1 damage to any target." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tidebinder Mage | handled | When this creature enters, tap target red or green creature an opponent controls. That creature doesn't untap during its controller's untap step for as long as  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Trained Condor | handled | Whenever this creature attacks, another target creature you control gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Undead Minotaur | handled |  |  | Y/Y/- | not_tested |
| Vampire Warlord | handled | Sacrifice another creature: Regenerate this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vial of Poison | handled | {1}, Sacrifice this artifact: Target creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Windreader Sphinx | handled | Whenever a creature with flying attacks, you may draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Witchstalker | handled | Whenever an opponent casts a blue or black spell during your turn, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Woodborn Behemoth | handled | As long as you control eight or more lands, this creature gets +4/+4 and has trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Xathrid Necromancer | handled | Whenever this creature or another Human creature you control dies, create a tapped 2/2 black Zombie creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Young Pyromancer | handled | Whenever you cast an instant or sorcery spell, create a 1/1 red Elemental creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Zephyr Charge | handled | {1}{U}: Target creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>22 cards</summary>

- Advocate of the Beast
- Angelic Accord
- Artificer's Hex
- Awaken the Ancient
- Bogbrew Witch
- Bubbling Cauldron
- Devout Invocation
- Elvish Mystic
- Festering Newt
- Fiendslayer Paladin
- Grim Return
- Kalonian Hydra
- Manaweft Sliver
- Marauding Maulhorn
- Path of Bravery
- Pyromancer's Gauntlet
- Shadowborn Apostle
- Shadowborn Demon
- Sliver Construct
- Vastwood Hydra
- Voracious Wurm
- Warden of Evos Isle

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| create two N/N red elemental creature tokens, then flip a coin. if you win the flip, return ~ to its owner's hand. | 1 | Molten Birth | m14 |
| creatures without flying can't block ~. | 1 | Seismic Stomp | m14 |
| each creature your opponents control is an illusion in addition to its other types and has "..." | 1 | Dismiss into Dream | m14 |
| put all creature cards from all graveyards onto the battlefield under your control. | 1 | Rise of the Dark Realms | m14 |
| target creature gets +N/+N and gains trample until end of turn. it must be blocked ~ if able. (a creature with trample can deal excess combat damage to the play | 1 | Enlarge | m14 |
| when a creature attacks you or a planeswalker you control, if ~ has defender, it loses defender and gains trample. | 1 | Guardian of the Ages | m14 |
| when ~ enters, target opponent mills five cards. you may cast an instant or sorcery spell from among them without paying its mana cost. | 1 | Jace's Mindseeker | m14 |
| whenever an enchantment you control enters, create a N/N white cat creature token. if that enchantment is an aura, you may attach it to the token. | 1 | Ajani's Chosen | m14 |
| whenever you cast a black spell or a swamp you control enters, you gain N life. | 1 | Staff of the Death Magus | m14 |
| whenever you cast a blue spell or an island you control enters, you gain N life. | 1 | Staff of the Mind Magus | m14 |
| whenever you cast a green spell or a forest you control enters, you gain N life. | 1 | Staff of the Wild Magus | m14 |
| whenever you cast a red spell or a mountain you control enters, you gain N life. | 1 | Staff of the Flame Magus | m14 |
| whenever you cast a white spell or a plains you control enters, you gain N life. | 1 | Staff of the Sun Magus | m14 |
| whenever you cast an enchantment spell, you may have target creature get -N/-N until end of turn. | 1 | Blightcaster | m14 |
| {M}, {M}: copy the exiled card. you may cast the copy without paying its mana cost. N is the mana value of the exiled card. | 1 | Elite Arcanist | m14 |
| {M}: each creature attacks ~ if able. | 1 | Goblin Diplomats | m14 |
| {M}: exile target card from a graveyard. if it was a creature card, put a +N/+N counter on ~ and you gain N life. | 1 | Scavenging Ooze | m14 |
| {M}: until end of turn, ~ becomes a N/N spirit artifact creature that's no longer an equipment. activate only if you control no creatures. | 1 | Haunted Plate Mail | m14 |
| ~ can"..."t be countered. that creature enters with an additional +N/+N counter on it. | 1 | Savage Summoning | m14 |
| −N: exile the top ten cards of your library. choose an instant or sorcery card exiled ~ and copy it three times. you may cast the copies without paying their ma | 1 | Chandra, Pyromaster | m14 |

## Notes



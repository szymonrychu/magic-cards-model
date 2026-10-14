# Core Set 2021 (m21)

- Expansion: 207
- Set code: `m21`
- Release date: 2020-07-03
- Cards in scope (Modern/Pioneer/Standard-legal): 182

## Legality

| Format | Legal cards |
|---|---|
| Modern | 182 |
| Pioneer | 182 |
| Standard | 8 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 45 | 24.7% |
| Works (untested) | 110 | 60.4% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 27 | 14.8% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Basri Ket | silent | −2: Whenever one or more nontoken creatures attack this turn, create that many 1/1 white Soldier creature tokens that are tapped and attacking. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chandra's Firemaw | silent | When this creature enters, you may search your library and/or graveyard for a card named Chandra, Flame's Catalyst, reveal it, and put it into your hand. If you | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chandra, Flame's Catalyst | silent | −8: Discard your hand, then draw seven cards. Until end of turn, you may cast spells from your hand without paying their mana costs. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chandra, Heart of Fire | silent | +1: Discard your hand, then exile the top three cards of your library. Until end of turn, you may play cards exiled this way. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Discontinuity | silent | During your turn, this spell costs {2}{U}{U} less to cast. End the turn. (Exile all spells and abilities from the stack, including this card. The player whose t | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Drowsing Tyrannodon | silent | As long as you control a creature with power 4 or greater, this creature can attack as though it didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Fiery Emancipation | silent | Triple | no machine in the engine executes this keyword | Y/Y/- | not_working |
| Garruk's Harbinger | silent | Whenever this creature deals combat damage to a player or planeswalker, look at that many cards from the top of your library. You may reveal a creature card or  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Garruk's Warsteed | silent | When this creature enters, you may search your library and/or graveyard for a card named Garruk, Savage Herald, reveal it, and put it into your hand. If you sea | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gnarled Sage | silent | As long as you've drawn two or more cards this turn, this creature gets +0/+2 and has vigilance. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Goremand | silent | When this creature enters, each opponent sacrifices a creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Idol of Endurance | silent | When this artifact enters, exile all creature cards with mana value 3 or less from your graveyard until this artifact leaves the battlefield. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Liliana's Scrounger | silent | At the beginning of each end step, if a creature died this turn, you may put a loyalty counter on a Liliana planeswalker you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Seasoned Hallowblade | silent | Discard a card: Tap this creature. It gains indestructible until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| See the Truth | silent | Look at the top three cards of your library. Put one of those cards into your hand and the rest on the bottom of your library in any order. If this spell was ca | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Teferi's Wavecaster | silent | When this creature enters, you may search your library and/or graveyard for a card named Teferi, Timeless Voyager, reveal it, and put it into your hand. If you  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Teferi, Timeless Voyager | silent | −8: Each creature target opponent controls phases out. Until the end of your next turn, they can't phase in. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Unleash Fury | silent | Double the power of target creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Warded Battlements | silent | Attacking creatures you control get +1/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Alchemist's Gift | notice | Target creature gets +1/+1 and gains your choice of deathtouch or lifelink until end of turn. (Any amount of damage a creature with deathtouch deals to a creatu | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Carrion Grub | notice | This creature gets +X/+0, where X is the greatest power among creature cards in your graveyard. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Crypt Lurker | notice | When this creature enters, you may sacrifice a creature or discard a creature card. If you do, draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Niambi, Esteemed Speaker | notice | When Niambi enters, you may return another target creature you control to its owner's hand. If you do, you gain life equal to that creature's mana value. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Pestilent Haze | notice | Choose one — • All creatures get -2/-2 until end of turn. • Remove two loyalty counters from each planeswalker. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Rookie Mistake | notice | Until end of turn, target creature gets +0/+2 and another target creature gets -2/-0. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Traitorous Greed | notice | Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Add two mana of any one color. (The creature can attac | unparsed remainder: Untap that creature. It gains haste until end of turn. Add two mana of any one color. | Y/Y/- | not_working |
| Transmogrify | notice | Exile target creature. That creature's controller reveals cards from the top of their library until they reveal a creature card. That player puts that card onto | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Adherent of Hope | handled | At the beginning of combat on your turn, if you control a Basri planeswalker, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angelic Ascension | handled | Exile target creature or planeswalker. Its controller creates a 4/4 white Angel creature token with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Animal Sanctuary | handled | {2}, {T}: Put a +1/+1 counter on target Bird, Cat, Dog, Goat, Ox, or Snake. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Anointed Chorister | handled | {4}{W}: This creature gets +3/+3 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aven Gagglemaster | handled | When this creature enters, you gain 2 life for each creature you control with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bad Deal | handled | You draw two cards and each opponent discards two cards. Each player loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Basri's Acolyte | handled | When this creature enters, put a +1/+1 counter on each of up to two other target creatures you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Basri's Aegis | handled | Put a +1/+1 counter on each of up to two target creatures. You may search your library and/or graveyard for a card named Basri, Devoted Paladin, reveal it, and  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Basri, Devoted Paladin | handled | +1: Put a +1/+1 counter on up to one target creature. It gains vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blood Glutton | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Bolt Hound | handled | Whenever this creature attacks, other creatures you control get +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bone Pit Brute | handled | When this creature enters, target creature gets +4/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Brash Taunter | handled | Whenever this creature is dealt damage, it deals that much damage to target opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Burlfist Oak | handled | Whenever you draw a card, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Caged Zombie | handled | {1}{B}, {T}: Each opponent loses 2 life. Activate only if a creature died this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra's Magmutt | handled | {T}: This creature deals 1 damage to target player or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra's Pyreling | handled | Whenever a source you control deals noncombat damage to an opponent, this creature gets +1/+0 and gains double strike until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Daybreak Charger | handled | When this creature enters, target creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dire Fleet Warmonger | handled | At the beginning of combat on your turn, you may sacrifice another creature. If you do, this creature gets +2/+2 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Double Vision | handled | Whenever you cast your first instant or sorcery spell each turn, copy that spell. You may choose new targets for the copy. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eliminate | handled | Destroy target creature or planeswalker with mana value 3 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Experimental Overload | handled | Create an X/X blue and red Weird creature token, where X is the number of instant and sorcery cards in your graveyard. Then you may return an instant or sorcery | the engine reads this text and performs it | Y/Y/- | not_tested |
| Falconer Adept | handled | Whenever this creature attacks, create a 1/1 white Bird creature token with flying that's tapped and attacking. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Feline Sovereign | handled | Other Cats you control get +1/+1 and have protection from Dogs. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Finishing Blow | handled | Destroy target creature or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Forgotten Sentinel | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frantic Inventory | handled | Draw a card, then draw cards equal to the number of cards named Frantic Inventory in your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fungal Rebirth | handled | Return target permanent card from your graveyard to your hand. If a creature died this turn, create two 1/1 green Saproling creature tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gale Swooper | handled | When this creature enters, target creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garruk's Gorehorn | handled |  |  | Y/Y/- | not_tested |
| Garruk's Uprising | handled | When this enchantment enters, if you control a creature with power 4 or greater, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Garruk, Savage Herald | handled | +1: Reveal the top card of your library. If it's a creature card, put it into your hand. Otherwise, put it on the bottom of your library. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Garruk, Unleashed | handled | +1: Up to one target creature gets +3/+3 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ghostly Pilferer | handled | Whenever this creature becomes untapped, you may pay {2}. If you do, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Goblin Wizardry | handled | Create two 1/1 red Goblin Wizard creature tokens with prowess. (Whenever you cast a noncreature spell, they get +1/+1 until end of turn.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Havoc Jester | handled | Whenever you sacrifice a permanent, this creature deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heartfire Immolator | handled | {R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Hellkite Punisher | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Historian of Zhalfir | handled | Whenever this creature attacks, if you control a Teferi planeswalker, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hobblefiend | handled | {1}, Sacrifice another creature: Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hunter's Edge | handled | Put a +1/+1 counter on target creature you control. Then that creature deals damage equal to its power to target creature you don't control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Indulging Patrician | handled | At the beginning of your end step, if you gained 3 or more life this turn, each opponent loses 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Invigorating Surge | handled | Put a +1/+1 counter on target creature you control, then double the number of +1/+1 counters on that creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jolrael, Mwonvuli Recluse | handled | Whenever you draw your second card each turn, create a 2/2 green Cat creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kaervek, the Spiteful | handled | Other creatures get -1/-1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Keen Glidemaster | handled | {2}{U}: Target creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Keral Keep Disciples | handled | Whenever you activate a loyalty ability of a Chandra planeswalker, this creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Library Larcenist | handled | Whenever this creature attacks, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Light of Promise | handled | Enchanted creature has "Whenever you gain life, put that many +1/+1 counters on this creature." | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liliana's Devotee | handled | Zombies you control get +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liliana's Scorn | handled | Destroy target creature. You may search your library and/or graveyard for a card named Liliana, Death Mage, reveal it, and put it into your hand. If you search  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Liliana's Steward | handled | {T}, Sacrifice this creature: Target opponent discards a card. Activate only as a sorcery. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Llanowar Visionary | handled | When this creature enters, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lofty Denial | handled | Counter target spell unless its controller pays {1}. If you control a creature with flying, counter that spell unless its controller pays {4} instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Malefic Scythe | handled | This Equipment enters with a soul counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mangara, the Diplomat | handled | Whenever an opponent attacks with creatures, if two or more of those creatures are attacking you and/or planeswalkers you control, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Masked Blackguard | handled | {2}{B}: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Miscast | handled | Counter target instant or sorcery spell unless its controller pays {3}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mistral Singer | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Mystic Skyfish | handled | Whenever you draw your second card each turn, this creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Obsessive Stitcher | handled | {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ornery Dilophosaur | handled | Whenever this creature attacks, if you control a creature with power 4 or greater, this creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Predatory Wurm | handled | This creature gets +2/+2 as long as you control a Garruk planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pridemalkin | handled | When this creature enters, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Primal Might | handled | Target creature you control gets +X/+X until end of turn. Then it fights up to one target creature you don't control. (Each deals damage equal to its power to t | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Rambunctious Mutt | handled | When this creature enters, destroy target artifact or enchantment an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Read the Tides | handled | Choose one — • Draw three cards. • Return up to two target creatures to their owners' hands. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rise Again | handled | Return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Roaming Ghostlight | handled | When this creature enters, return up to one target non-Spirit creature to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rousing Read | handled | When this Aura enters, draw two cards, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Run Afoul | handled | Target opponent sacrifices a creature of their choice with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sabertooth Mauler | handled | At the beginning of your end step, if a creature died this turn, put a +1/+1 counter on this creature and untap it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanctum of Calm Waters | handled | At the beginning of your first main phase, you may draw X cards, where X is the number of Shrines you control. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanctum of Shattered Heights | handled | {1}, Discard a land card or Shrine card: Sanctum of Shattered Heights deals X damage to target creature or planeswalker, where X is the number of Shrines you co | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanctum of Stone Fangs | handled | At the beginning of your first main phase, each opponent loses X life and you gain X life, where X is the number of Shrines you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sanguine Indulgence | handled | This spell costs {3} less to cast if you've gained 3 or more life this turn. Return up to two target creature cards from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Secure the Scene | handled | Exile target nonland permanent. Its controller creates a 1/1 white Soldier creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Selfless Savior | handled | Sacrifice this creature: Another target creature you control gains indestructible until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shipwreck Dowser | handled | When this creature enters, return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sigiled Contender | handled | This creature has lifelink as long as it has a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Silversmote Ghoul | handled | At the beginning of your end step, if you gained 3 or more life this turn, return this card from your graveyard to the battlefield tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skyway Sniper | handled | {2}{G}: This creature deals 1 damage to target creature with flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sparkhunter Masticore | handled | As an additional cost to cast this spell, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spined Megalodon | handled | Whenever this creature attacks, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spirit of Malevolence | handled | When this creature dies, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sporeweb Weaver | handled | Whenever this creature is dealt damage, you gain 1 life and create a 1/1 green Saproling creature token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Staunch Shieldmate | handled |  |  | Y/Y/- | not_tested |
| Storm Caller | handled | When this creature enters, it deals 2 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stormwing Entity | handled | This spell costs {2}{U} less to cast if you've cast an instant or sorcery spell this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Subira, Tulzidi Caravanner | handled | {1}: Another target creature with power 2 or less can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sublime Epiphany | handled | Choose one or more — • Counter target spell. • Counter target activated or triggered ability. • Return target nonland permanent to its owner's hand. • Create a  | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swift Response | handled | Destroy target tapped creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Teferi's Ageless Insight | handled | If you would draw a card except the first one you draw in each of your draw steps, draw two cards instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Teferi's Protege | handled | {1}{U}, {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Teferi's Tutelage | handled | When this enchantment enters, draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tempered Veteran | handled | {W}, {T}: Put a +1/+1 counter on target creature with a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thieves' Guild Enforcer | handled | Whenever this creature or another Rogue you control enters, each opponent mills two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tide Skimmer | handled | Whenever you attack with two or more creatures with flying, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tolarian Kraken | handled | Whenever you draw a card, you may pay {1}. When you do, you may tap or untap target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tome Anima | handled | This creature can't be blocked as long as you've drawn two or more cards this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Trufflesnout | handled | When this creature enters, choose one — • Put a +1/+1 counter on this creature. • You gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Twinblade Assassins | handled | At the beginning of your end step, if a creature died this turn, draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Valorous Steed | handled | When this creature enters, create a 2/2 white Knight creature token with vigilance. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Village Rites | handled | As an additional cost to cast this spell, sacrifice a creature. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Volcanic Salvo | handled | This spell costs {X} less to cast, where X is the total power of creatures you control. Volcanic Salvo deals 6 damage to each of up to two target creatures and/ | the engine reads this text and performs it | Y/Y/- | not_tested |
| Warden of the Woods | handled | Whenever this creature becomes the target of a spell or ability an opponent controls, you may draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Watcher of the Spheres | handled | Creature spells with flying you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wildwood Patrol | handled | Trample | machines/combat.py | Y/Y/- | not_tested |
| Wildwood Scourge | handled | This creature enters with X +1/+1 counters on it. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Witch's Cauldron | handled | {1}{B}, {T}, Sacrifice a creature: You gain 1 life and draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>45 cards</summary>

- Alpine Houndmaster
- Alpine Watchdog
- Archfiend's Vessel
- Barrin, Tolarian Archmage
- Basri's Lieutenant
- Basri's Solidarity
- Canopy Stalker
- Celestial Enforcer
- Chandra's Incinerator
- Chromatic Orrery
- Chrome Replicator
- Conclave Mentor
- Conspicuous Snoop
- Demonic Embrace
- Elder Gargaroth
- Enthralling Hold
- Gadrak, the Crown-Scourge
- Gloom Sower
- Griffin Aerie
- Hooded Blightfang
- Igneous Cur
- Kinetic Augur
- Leafkin Avenger
- Liliana's Standard Bearer
- Liliana, Death Mage
- Liliana, Waker of the Dead
- Mazemind Tome
- Necromentia
- Nine Lives
- Pack Leader
- Peer into the Abyss
- Pursued Whale
- Radha, Heart of Keld
- Sanctum of All
- Sanctum of Fruitful Harvest
- Sanctum of Tranquil Light
- Shacklegeist
- Siege Striker
- Soul Sear
- Speaker of the Heavens
- Teferi, Master of Time
- Terror of the Peaks
- Track Down
- Vito, Thorn of the Dusk Rose
- Waker of Waves

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| Choose one | 1 | Pestilent Haze | m21 |
| +N: discard your hand, then exile the top three cards of your library. until end of turn, you may play cards exiled ~. | 1 | Chandra, Heart of Fire | m21 |
| as long as you control a creature with power N or greater, ~ can attack as though it didn't have defender. | 1 | Drowsing Tyrannodon | m21 |
| as long as you've drawn two or more cards ~, ~ gets +N/+N and has vigilance. | 1 | Gnarled Sage | m21 |
| at the beginning of each end step, if a creature died ~, you may put a loyalty counter on a liliana planeswalker you control. | 1 | Liliana's Scrounger | m21 |
| attacking creatures you control get +N/+N. | 1 | Warded Battlements | m21 |
| discard a card: tap ~. it gains indestructible until end of turn. | 1 | Seasoned Hallowblade | m21 |
| double the power of target creature until end of turn. | 1 | Unleash Fury | m21 |
| during your turn, ~ costs {M}{M}{M} less to cast. end the turn. (exile all spells and abilities from the stack, including ~. the player whose turn it is discard | 1 | Discontinuity | m21 |
| exile target creature. that creature's controller reveals cards from the top of their library until they reveal a creature card. that player puts that card onto | 1 | Transmogrify | m21 |
| gain control of target creature until end of turn. untap that creature. it gains haste until end of turn. add two mana of any one color. (the creature can attac | 1 | Traitorous Greed | m21 |
| look at the top three cards of your library. put one of those cards into your hand and the rest on the bottom of your library in any order. if ~ was cast from a | 1 | See the Truth | m21 |
| target creature gets +N/+N and gains your choice of deathtouch or lifelink until end of turn. (any amount of damage a creature with deathtouch deals to a creatu | 1 | Alchemist's Gift | m21 |
| triple | 1 | Fiery Emancipation | m21 |
| until end of turn, target creature gets +N/+N and another target creature gets -N/-N. | 1 | Rookie Mistake | m21 |
| when niambi enters, you may return another target creature you control to its owner"..."s mana value. | 1 | Niambi, Esteemed Speaker | m21 |
| when ~ enters, each opponent sacrifices a creature. | 1 | Goremand | m21 |
| when ~ enters, exile all creature cards with mana value N or less from your graveyard until ~ leaves the battlefield. | 1 | Idol of Endurance | m21 |
| when ~ enters, you may sacrifice a creature or discard a creature card. if you do, draw a card. | 1 | Crypt Lurker | m21 |
| when ~ enters, you may search your library and/or graveyard for a card named chandra, flame's catalyst, reveal it, and put it into your hand. if you search your | 1 | Chandra's Firemaw | m21 |
| when ~ enters, you may search your library and/or graveyard for a card named garruk, savage herald, reveal it, and put it into your hand. if you search your lib | 1 | Garruk's Warsteed | m21 |
| when ~ enters, you may search your library and/or graveyard for a card named teferi, timeless voyager, reveal it, and put it into your hand. if you search your  | 1 | Teferi's Wavecaster | m21 |
| whenever ~ deals combat damage to a player or planeswalker, look at that many cards from the top of your library. you may reveal a creature card or garruk plane | 1 | Garruk's Harbinger | m21 |
| ~ gets +N/+N, where N is the greatest power among creature cards in your graveyard. | 1 | Carrion Grub | m21 |
| −N: discard your hand, then draw seven cards. until end of turn, you may cast spells from your hand without paying their mana costs. | 1 | Chandra, Flame's Catalyst | m21 |
| −N: each creature target opponent controls phases out. until the end of your next turn, they can't phase in. | 1 | Teferi, Timeless Voyager | m21 |
| −N: whenever one or more nontoken creatures attack ~, create that many N/N white soldier creature tokens that are tapped and attacking. | 1 | Basri Ket | m21 |

## Notes



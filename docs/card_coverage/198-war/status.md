# War of the Spark (war)

- Expansion: 198
- Set code: `war`
- Release date: 2019-05-03
- Cards in scope (Modern/Pioneer/Standard-legal): 156

## Legality

| Format | Legal cards |
|---|---|
| Modern | 156 |
| Pioneer | 156 |
| Standard | 1 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 3.8% |
| Partial (unaudited) | 8 | 5.1% |
| Not tested (handled, untested) | 109 | 69.9% |
| Not working (silent / notice / error) | 33 | 21.2% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Ashiok's Skulker | silent | {3}{U}: This creature can't be blocked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Band Together | silent | Up to two target creatures you control each deal damage equal to their power to another target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Bond of Insight | silent | Each player mills four cards. Return up to two instant and/or sorcery cards from your graveyard to your hand. Exile Bond of Insight. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Burning Prophet | silent | Whenever you cast a noncreature spell, this creature gets +1/+0 until end of turn, then scry 1. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Chainwhip Cyclops | silent | {3}{R}: Target creature can't block this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Cyclops Electromancer | silent | When this creature enters, it deals X damage to target creature an opponent controls, where X is the number of instant and sorcery cards in your graveyard. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dreadhorde Twins | silent | Zombie tokens you control have trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Emergence Zone | silent | {1}, {T}, Sacrifice this land: You may cast spells this turn as though they had flash. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Eternal Skylord | silent | Zombie tokens you control have flying. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Firemind Vessel | silent | {T}: Add two mana of different colors. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Forced Landing | silent | Put target creature with flying on the bottom of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gideon's Sacrifice | silent | Choose a creature or planeswalker you control. All damage that would be dealt this turn to you and permanents you control is dealt to the chosen permanent inste | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gideon's Triumph | silent | Target opponent sacrifices a creature of their choice that attacked or blocked this turn. If you control a Gideon planeswalker, that player sacrifices two of th | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Gideon, the Oathsworn | silent | Whenever you attack with two or more non-Gideon creatures, put a +1/+1 counter on each of those creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Guild Globe | silent | {2}, {T}, Sacrifice this artifact: Add two mana of different colors. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Heartwarming Redemption | silent | Discard all the cards in your hand, then draw that many cards plus one. You gain life equal to the number of cards in your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Interplanar Beacon | silent | {1}, {T}: Add two mana of different colors. Spend this mana only to cast planeswalker spells. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Invade the City | silent | Amass Zombies X, where X is the number of instant and sorcery cards in your graveyard. (Put X +1/+1 counters on an Army you control. It's also a Zombie. If you  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jace's Ruse | silent | Return up to two target creatures to their owner's hand. You may search your library and/or graveyard for a card named Jace, Arcane Strategist, reveal it, and p | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jace, Arcane Strategist | silent | −7: Creatures you control can't be blocked this turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Nissa's Triumph | silent | Search your library for up to two basic Forest cards. If you control a Nissa planeswalker, instead search your library for up to three land cards. Reveal those  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Price of Betrayal | silent | Remove up to five counters from target artifact, creature, planeswalker, or opponent. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Rubblebelt Rioters | silent | Whenever this creature attacks, it gets +X/+0 until end of turn, where X is the greatest power among creatures you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Saheeli's Silverwing | silent | When this creature enters, look at the top card of target opponent's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Tezzeret, Master of the Bridge | silent | +2: Tezzeret deals X damage to each opponent, where X is the number of artifacts you control. You gain X life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vivien's Grizzly | silent | {3}{G}: Look at the top card of your library. If it's a creature or planeswalker card, you may reveal it and put it into your hand. If you don't put the card in | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Vizier of the Scorpion | silent | Zombie tokens you control have deathtouch. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Blindblast | notice | Blindblast deals 1 damage to target creature. That creature can't block this turn. Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Bond of Passion | notice | Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Bond of Passion deals 2 damage to any other target. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Gideon's Battle Cry | notice | Put a +1/+1 counter on each creature you control. You may search your library and/or graveyard for a card named Gideon, the Oathsworn, reveal it, and put it int | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Storm the Citadel | notice | Until end of turn, creatures you control get +2/+2 and gain "Whenever this creature deals combat damage to a player or planeswalker, destroy target artifact or  | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Teferi's Time Twist | notice | Exile target permanent you control. Return that card to the battlefield under its owner's control at the beginning of the next end step. If it enters as a creat | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Topple the Statue | notice | Tap target permanent. If it's an artifact, destroy it. Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Challenger Troll | unaudited | Each creature you control with power 4 or greater can't be blocked by more than one creature. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Duskmantle Operative | unaudited | This creature can't be blocked by creatures with power 4 or greater. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Gleaming Overseer | unaudited | Zombie tokens you control have hexproof and menace. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Kasmina's Transmutation | unaudited | Enchanted creature loses all abilities and has base power and toughness 1/1. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Mowu, Loyal Companion | unaudited | If one or more +1/+1 counters would be put on Mowu, that many plus one +1/+1 counters are put on it instead. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Raging Kronch | unaudited | This creature can't attack alone. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Rescuer Sphinx | unaudited | As this creature enters, you may return a nonland permanent you control to its owner's hand. If you do, this creature enters with a +1/+1 counter on it. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ugin's Conjurant | unaudited | If damage would be dealt to this creature while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from this creature. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ahn-Crop Invader | handled | During your turn, this creature has first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aid the Fallen | handled | Choose one or both — • Return target creature card from your graveyard to your hand. • Return target planeswalker card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Angrath's Rampage | handled | Choose one — • Target player sacrifices an artifact of their choice. • Target player sacrifices a creature of their choice. • Target player sacrifices a planesw | the engine reads this text and performs it | Y/Y/- | not_tested |
| Arlinn's Wolf | handled | This creature can't be blocked by creatures with power 2 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Aven Eternal | handled | When this creature enters, amass Zombies 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Banehound | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Battlefield Promotion | handled | Put a +1/+1 counter on target creature. That creature gains first strike until end of turn. You gain 2 life. (A creature with first strike deals combat damage b | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bleeding Edge | handled | Up to one target creature gets -2/-2 until end of turn. Amass Zombies 2. (Put two +1/+1 counters on an Army you control. It's also a Zombie. If you don't contro | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bloom Hulk | handled | When this creature enters, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bond of Discipline | handled | Tap all creatures your opponents control. Creatures you control gain lifelink until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bond of Flourishing | handled | Look at the top three cards of your library. You may reveal a permanent card from among them and put it into your hand. Put the rest on the bottom of your libra | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bond of Revival | handled | Return target creature card from your graveyard to the battlefield. It gains haste until your next turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bulwark Giant | handled | When this creature enters, you gain 5 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Callous Dismissal | handled | Return target nonland permanent to its owner's hand. Amass Zombies 1. (Put a +1/+1 counter on an Army you control. It's also a Zombie. If you don't control an A | the engine reads this text and performs it | Y/Y/- | not_tested |
| Centaur Nurturer | handled | When this creature enters, you gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Chandra's Triumph | handled | Chandra's Triumph deals 3 damage to target creature or planeswalker an opponent controls. Chandra's Triumph deals 5 damage instead if you control a Chandra plan | the engine reads this text and performs it | Y/Y/- | not_tested |
| Charity Extractor | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Charmed Stray | handled | When this creature enters, put a +1/+1 counter on each other creature you control named Charmed Stray. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Contentious Plan | handled | Proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.) Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Courage in Crisis | handled | Put a +1/+1 counter on target creature, then proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already t | the engine reads this text and performs it | Y/Y/- | not_tested |
| Cruel Celebrant | handled | Whenever this creature or another creature or planeswalker you control dies, each opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crush Dissent | handled | Counter target spell unless its controller pays {2}. Amass Zombies 2. (Put two +1/+1 counters on an Army you control. It's also a Zombie. If you don't control a | the engine reads this text and performs it | Y/Y/- | not_tested |
| Davriel's Shadowfugue | handled | Target player discards two cards and loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deathsprout | handled | Destroy target creature. Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Despark | handled | Exile target permanent with mana value 4 or greater. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desperate Lunge | handled | Target creature gets +2/+2 and gains flying until end of turn. You gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Divine Arrow | handled | Divine Arrow deals 4 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Domri's Ambush | handled | Put a +1/+1 counter on target creature you control. Then that creature deals damage equal to its power to target creature or planeswalker you don't control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dreadmalkin | handled | {2}{B}, Sacrifice another creature or planeswalker: Put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Elite Guardmage | handled | When this creature enters, you gain 3 life and draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Enforcer Griffin | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Erratic Visionary | handled | {1}{U}, {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Eternal Taskmaster | handled | This creature enters tapped. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Evolution Sage | handled | Landfall — Whenever a land you control enters, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Flux Channeler | handled | Whenever you cast a noncreature spell, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Gideon's Company | handled | Whenever you gain life, put two +1/+1 counters on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Goblin Assailant | handled |  |  | Y/Y/- | not_tested |
| Goblin Assault Team | handled | When this creature dies, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| God-Pharaoh's Statue | handled | Spells your opponents cast cost {2} more to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grateful Apparition | handled | Whenever this creature deals combat damage to a player or planeswalker, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grim Initiate | handled | When this creature dies, amass Zombies 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Guildpact Informant | handled | Whenever this creature deals combat damage to a player or planeswalker, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Heartfire | handled | As an additional cost to cast this spell, sacrifice a creature or planeswalker. Heartfire deals 4 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Herald of the Dreadhorde | handled | When this creature dies, amass Zombies 2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Honor the God-Pharaoh | handled | As an additional cost to cast this spell, discard a card. Draw two cards. Amass Zombies 1. (Put a +1/+1 counter on an Army you control. It's also a Zombie. If y | the engine reads this text and performs it | Y/Y/- | not_tested |
| Huatli's Raptor | handled | When this creature enters, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Invading Manticore | handled | When this creature enters, amass Zombies 2. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Iron Bully | handled | When this creature enters, put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ironclad Krovod | handled |  |  | Y/Y/- | not_tested |
| Jace's Projection | handled | Whenever you draw a card, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jace's Triumph | handled | Draw two cards. If you control a Jace planeswalker, draw three cards instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jaya's Greeting | handled | Jaya's Greeting deals 3 damage to target creature. Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kaya's Ghostform | handled | When enchanted permanent dies or is put into exile, return that card to the battlefield under your control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kiora's Dambreaker | handled | When this creature enters, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kraul Stinger | handled | Deathtouch | machines/combat.py | Y/Y/- | not_tested |
| Law-Rune Enforcer | handled | {1}, {T}: Tap target creature with mana value 2 or greater. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lazotep Behemoth | handled |  |  | Y/Y/- | not_tested |
| Lazotep Plating | handled | Amass Zombies 1. (Put a +1/+1 counter on an Army you control. It's also a Zombie. If you don't control an Army, create a 0/0 black Zombie Army creature token fi | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lazotep Reaver | handled | When this creature enters, amass Zombies 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Leyline Prowler | handled | Lifelink | machines/combat.py | Y/Y/- | not_tested |
| Loxodon Sergeant | handled | When this creature enters, other creatures you control gain vigilance until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Makeshift Battalion | handled | Battalion — Whenever this creature and at least two other creatures attack, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mana Geode | handled | When this artifact enters, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Martyr for the Cause | handled | When this creature dies, proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Merfolk Skydiver | handled | When this creature enters, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Naga Eternal | handled |  |  | Y/Y/- | not_tested |
| Nahiri's Stoneblades | handled | Up to two target creatures each get +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| No Escape | handled | Counter target creature or planeswalker spell. If that spell is countered this way, exile it instead of putting it into its owner's graveyard. Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ob Nixilis's Cruelty | handled | Target creature gets -5/-5 until end of turn. If that creature would die this turn, exile it instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pledge of Unity | handled | Put a +1/+1 counter on each creature you control. You gain 1 life for each creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pollenbright Druid | handled | When this creature enters, choose one — • Put a +1/+1 counter on target creature. • Proliferate. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pouncing Lynx | handled | During your turn, this creature has first strike. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prismite | handled |  |  | Y/Y/- | not_tested |
| Prison Realm | handled | When this enchantment enters, exile target creature or planeswalker an opponent controls until this enchantment leaves the battlefield. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ral's Outburst | handled | Ral's Outburst deals 3 damage to any target. Look at the top two cards of your library. Put one of them into your hand and the other into your graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rally of Wings | handled | Untap all creatures you control. Creatures you control with flying get +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Relentless Advance | handled | Amass Zombies 3. (Put three +1/+1 counters on an Army you control. It's also a Zombie. If you don't control an Army, create a 0/0 black Zombie Army creature tok | the engine reads this text and performs it | Y/Y/- | not_tested |
| Return to Nature | handled | Choose one — • Destroy target artifact. • Destroy target enchantment. • Exile target card from a graveyard. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rising Populace | handled | Whenever another creature or planeswalker you control dies, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Samut's Sprint | handled | Target creature gets +2/+1 and gains haste until end of turn. Scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sarkhan's Catharsis | handled | Sarkhan's Catharsis deals 5 damage to target player or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shriekdiver | handled | {1}: This creature gains haste until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sky Theater Strix | handled | Whenever you cast a noncreature spell, this creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Snarespinner | handled | Whenever this creature blocks a creature with flying, this creature gets +2/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spark Harvest | handled | As an additional cost to cast this spell, sacrifice a creature or pay {3}{B}. Destroy target creature or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spark Reaper | handled | {3}, Sacrifice a creature or planeswalker: You gain 1 life and draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spellgorger Weird | handled | Whenever you cast a noncreature spell, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spellkeeper Weird | handled | {2}, {T}, Sacrifice this creature: Return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Steady Aim | handled | Untap target creature. It gets +1/+4 and gains reach until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Stealth Mission | handled | Put two +1/+1 counters on target creature you control. That creature can't be blocked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sunblade Angel | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Tamiyo's Epiphany | handled | Scry 4, then draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tenth District Legionnaire | handled | Whenever you cast a spell that targets this creature, put a +1/+1 counter on this creature, then scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Teyo's Lightshield | handled | When this creature enters, put a +1/+1 counter on target creature you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thunder Drake | handled | Whenever you cast your second spell each turn, put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thundering Ceratok | handled | When this creature enters, other creatures you control gain trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tibalt's Rager | handled | When this creature dies, it deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tithebearer Giant | handled | When this creature enters, you draw a card and you lose 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Toll of the Invasion | handled | Target opponent reveals their hand. You choose a nonland card from it. That player discards that card. Amass Zombies 1. (Put a +1/+1 counter on an Army you cont | the engine reads this text and performs it | Y/Y/- | not_tested |
| Trusted Pegasus | handled | Whenever this creature attacks, target attacking creature without flying gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Turret Ogre | handled | When this creature enters, if you control another creature with power 4 or greater, this creature deals 2 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tyrant's Scorn | handled | Choose one — • Destroy target creature with mana value 3 or less. • Return target creature to its owner's hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Unlikely Aid | handled | Target creature gets +2/+0 and gains indestructible until end of turn. (Damage and effects that say "destroy" don't destroy it.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vampire Opportunist | handled | {6}{B}: Each opponent loses 2 life and you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vraska's Finisher | handled | When this creature enters, destroy target creature or planeswalker an opponent controls that was dealt damage this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wall of Runes | handled | When this creature enters, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wanderer's Strike | handled | Exile target creature, then proliferate. (Choose any number of permanents and/or players, then give each another counter of each kind already there.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| War Screecher | handled | {5}{W}, {T}: Other creatures you control get +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wardscale Crocodile | handled | Hexproof | machines/casting.py (target legality) | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Arboreal Grazer
- Bolt Bend
- Devouring Hellion
- Kronch Wrangler
- Mayhem Devil
- Neoform

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| Zombie tokens you control have hexproof and menace. | Dreadhorde Twins, Eternal Skylord, Gleaming Overseer, Vizier of the Scorpion | 4 |
| {1}, {T}: Add two mana of different colors. Spend this mana only to cast planeswalker spells. | Firemind Vessel, Interplanar Beacon | 2 |
| This creature can't be blocked by creatures with power 4 or greater. | Ashiok's Skulker, Duskmantle Operative | 2 |
| Amass Zombies X, where X is the number of instant and sorcery cards in your graveyard. (Put X +1/+1 counters on an Army you control. It's also a Zombie. If you  | Invade the City | 1 |
| As this creature enters, you may return a nonland permanent you control to its owner's hand. If you do, this creature enters with a +1/+1 counter on it. | Rescuer Sphinx | 1 |
| Blindblast deals 1 damage to target creature. That creature can't block this turn. Draw a card. | Blindblast | 1 |
| Choose a creature or planeswalker you control. All damage that would be dealt this turn to you and permanents you control is dealt to the chosen permanent inste | Gideon's Sacrifice | 1 |
| −7: Creatures you control can't be blocked this turn. | Jace, Arcane Strategist | 1 |
| Discard all the cards in your hand, then draw that many cards plus one. You gain life equal to the number of cards in your hand. | Heartwarming Redemption | 1 |
| Each creature you control with power 4 or greater can't be blocked by more than one creature. | Challenger Troll | 1 |
| Each player mills four cards. Return up to two instant and/or sorcery cards from your graveyard to your hand. Exile Bond of Insight. | Bond of Insight | 1 |
| Enchanted creature loses all abilities and has base power and toughness 1/1. | Kasmina's Transmutation | 1 |
| Exile target permanent you control. Return that card to the battlefield under its owner's control at the beginning of the next end step. If it enters as a creat | Teferi's Time Twist | 1 |
| Gain control of target creature until end of turn. Untap that creature. It gains haste until end of turn. Bond of Passion deals 2 damage to any other target. | Bond of Passion | 1 |
| If damage would be dealt to this creature while it has a +1/+1 counter on it, prevent that damage and remove that many +1/+1 counters from this creature. | Ugin's Conjurant | 1 |
| If one or more +1/+1 counters would be put on Mowu, that many plus one +1/+1 counters are put on it instead. | Mowu, Loyal Companion | 1 |
| {3}{G}: Look at the top card of your library. If it's a creature or planeswalker card, you may reveal it and put it into your hand. If you don't put the card in | Vivien's Grizzly | 1 |
| Put a +1/+1 counter on each creature you control. You may search your library and/or graveyard for a card named Gideon, the Oathsworn, reveal it, and put it int | Gideon's Battle Cry | 1 |
| Put target creature with flying on the bottom of its owner's library. | Forced Landing | 1 |
| Remove up to five counters from target artifact, creature, planeswalker, or opponent. | Price of Betrayal | 1 |
| Return up to two target creatures to their owner's hand. You may search your library and/or graveyard for a card named Jace, Arcane Strategist, reveal it, and p | Jace's Ruse | 1 |
| {2}, {T}, Sacrifice this artifact: Add two mana of different colors. | Guild Globe | 1 |
| {1}, {T}, Sacrifice this land: You may cast spells this turn as though they had flash. | Emergence Zone | 1 |
| Search your library for up to two basic Forest cards. If you control a Nissa planeswalker, instead search your library for up to three land cards. Reveal those  | Nissa's Triumph | 1 |
| Tap target permanent. If it's an artifact, destroy it. Draw a card. | Topple the Statue | 1 |
| {3}{R}: Target creature can't block this turn. | Chainwhip Cyclops | 1 |
| Target opponent sacrifices a creature of their choice that attacked or blocked this turn. If you control a Gideon planeswalker, that player sacrifices two of th | Gideon's Triumph | 1 |
| +2: Tezzeret deals X damage to each opponent, where X is the number of artifacts you control. You gain X life. | Tezzeret, Master of the Bridge | 1 |
| This creature can't attack alone. | Raging Kronch | 1 |
| Until end of turn, creatures you control get +2/+2 and gain "Whenever this creature deals combat damage to a player or planeswalker, destroy target artifact or  | Storm the Citadel | 1 |
| Up to two target creatures you control each deal damage equal to their power to another target creature. | Band Together | 1 |
| When this creature enters, it deals X damage to target creature an opponent controls, where X is the number of instant and sorcery cards in your graveyard. | Cyclops Electromancer | 1 |
| When this creature enters, look at the top card of target opponent's library. | Saheeli's Silverwing | 1 |
| Whenever this creature attacks, it gets +X/+0 until end of turn, where X is the greatest power among creatures you control. | Rubblebelt Rioters | 1 |
| Whenever you attack with two or more non-Gideon creatures, put a +1/+1 counter on each of those creatures. | Gideon, the Oathsworn | 1 |
| Whenever you cast a noncreature spell, this creature gets +1/+0 until end of turn, then scry 1. | Burning Prophet | 1 |

## Notes



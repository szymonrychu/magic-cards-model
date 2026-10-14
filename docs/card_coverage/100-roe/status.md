# Rise of the Eldrazi (roe)

- Expansion: 100
- Set code: `roe`
- Release date: 2010-04-23
- Cards in scope (Modern/Pioneer/Standard-legal): 220

## Legality

| Format | Legal cards |
|---|---|
| Modern | 220 |
| Pioneer | 22 |
| Standard | 6 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Tested | 57 | 25.9% |
| Works (untested) | 132 | 60.0% |
| Partial (unaudited) | 0 | 0.0% |
| Not working | 31 | 14.1% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Angelheart Vial | silent | Whenever you're dealt damage, you may put that many charge counters on this artifact. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Aura Finesse | silent | Attach target Aura you control to target creature. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Battle-Rattle Shaman | silent | At the beginning of combat on your turn, you may have target creature get +2/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/Y | not_working |
| Brood Birthing | silent | If you control an Eldrazi Spawn, create three 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." Otherwise, create one of t | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Disaster Radius | silent | As an additional cost to cast this spell, reveal a creature card from your hand. Disaster Radius deals X damage to each creature your opponents control, where X | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Dormant Gomazoa | silent | Whenever you become the target of a spell, you may untap this creature. | the engine does not recognise this trigger's condition - it never triggers | Y/-/- | not_working |
| Echo Mage | silent | {U}{U}, {T}: Copy target instant or sorcery spell twice. You may choose new targets for the copies. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Gideon Jura | silent | +2: During target opponent's next turn, creatures that player controls attack Gideon Jura if able. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hellcarver Demon | silent | Whenever this creature deals combat damage to a player, sacrifice all other permanents you control and discard your hand. Exile the top six cards of your librar | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Hellion Eruption | silent | Sacrifice all creatures you control, then create that many 4/4 red Hellion creature tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Irresistible Prey | silent | Target creature must be blocked this turn if able. Draw a card. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| It That Betrays | silent | Whenever an opponent sacrifices a nontoken permanent, put that card onto the battlefield under your control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Lay Bare | silent | Counter target spell. Look at its controller's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Not of This World | silent | Counter target spell or ability that targets a permanent you control. This spell costs {7} less to cast if it targets a spell or ability that targets a creature | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Oust | silent | Put target creature into its owner's library second from the top. Its controller gains 3 life. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Raid Bombardment | silent | Whenever a creature you control with power 2 or less attacks, this enchantment deals 1 damage to the player or planeswalker that creature is attacking. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Realms Uncharted | silent | Search your library for up to four land cards with different names and reveal them. An opponent chooses two of those cards. Put the chosen cards into your grave | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Renegade Doppelganger | silent | Whenever another creature you control enters, you may have this creature become a copy of that creature until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| See Beyond | silent | Draw two cards, then shuffle a card from your hand into your library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Spawnsire of Ulamog | silent | {20}: Cast any number of Eldrazi spells from among cards you own outside the game without paying their mana costs. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Thought Gorger | silent | When this creature enters, put a +1/+1 counter on it for each card in your hand. If you do, discard your hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Unified Will | silent | Counter target spell if you control more creatures than that spell's controller. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Valakut Fireboar | silent | Whenever this creature attacks, switch its power and toughness until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Venerated Teacher | silent | When this creature enters, put two level counters on each creature you control with level up. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Warmonger's Chariot | silent | As long as equipped creature has defender, it can attack as though it didn't have defender. | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| World at War | silent | After the second main phase this turn, there's an additional combat phase followed by an additional main phase. At the beginning of that combat, untap all creat | nothing in the engine reads this text - it would do nothing and log nothing | Y/-/- | not_working |
| Arrogant Bloodlord | notice | Whenever this creature blocks or becomes blocked by a creature with power 1 or less, destroy this creature at end of combat. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Champion's Drake | notice | This creature gets +3/+3 as long as you control a creature with three or more level counters on it. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Distortion Strike | notice | Target creature gets +1/+0 until end of turn and can't be blocked this turn. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beg | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Drana, Kalastria Bloodchief | notice | {X}{B}{B}: Target creature gets -0/-X until end of turn and Drana gets +X/+0 until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Perish the Thought | notice | Target opponent reveals their hand. You choose a card from it. That player shuffles that card into their library. | the engine recognises this text but fails closed with a notice instead of performing it | Y/-/- | not_working |
| Affa Guard Hound | handled | When this creature enters, target creature gets +0/+3 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Akoum Boulderfoot | handled | When this creature enters, it deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Artisan of Kozilek | handled | When you cast this spell, you may return target creature card from your graveyard to the battlefield. | the engine reads this text and performs it | Y/-/- | not_tested |
| Awakening Zone | handled | At the beginning of your upkeep, you may create a 0/1 colorless Eldrazi Spawn creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Bala Ged Scorpion | handled | When this creature enters, you may destroy target creature with power 1 or less. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bear Umbra | handled | Enchanted creature gets +2/+2 and has "Whenever this creature attacks, untap all lands you control." | the engine reads this text and performs it | Y/-/- | not_tested |
| Beastbreaker of Bala Ged | handled | Level Up | machines/keywords.py | Y/-/- | not_tested |
| Bloodrite Invoker | handled | {8}: Target player loses 3 life and you gain 3 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bloodthrone Vampire | handled | Sacrifice a creature: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Boar Umbra | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Bramblesnap | handled | Tap an untapped creature you control: This creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Broodwarden | handled | Eldrazi Spawn creatures you control get +2/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Cadaver Imp | handled | When this creature enters, you may return target creature card from your graveyard to your hand. | the engine reads this text and performs it | Y/-/- | not_tested |
| Caravan Escort | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Consume the Meek | handled | Destroy each creature with mana value 3 or less. They can't be regenerated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Corpsehatch | handled | Destroy target nonblack creature. Create two 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Crab Umbra | handled | {2}{U}: Untap enchanted creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Curse of Wizardry | handled | As this enchantment enters, choose a color. | the engine reads this text and performs it | Y/-/- | not_tested |
| Daggerback Basilisk | handled | Deathtouch | machines/combat.py | Y/Y/- | not_tested |
| Death Cultist | handled | Sacrifice this creature: Target player loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deathless Angel | handled | {W}{W}: Target creature gains indestructible until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Demonic Appetite | handled | Enchanted creature gets +3/+3. | the engine reads this text and performs it | Y/-/- | not_tested |
| Deprive | handled | As an additional cost to cast this spell, return a land you control to its owner's hand. Counter target spell. | the engine reads this text and performs it | Y/-/- | not_tested |
| Devastating Summons | handled | As an additional cost to cast this spell, sacrifice X lands. Create two X/X red Elemental creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Domestication | handled | You control enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Drake Umbra | handled | Enchanted creature gets +3/+3 and has flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Dread Drone | handled | When this creature enters, create two 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Dreamstone Hedron | handled | {3}, {T}, Sacrifice this artifact: Draw three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eel Umbra | handled | Enchanted creature gets +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eland Umbra | handled | Enchanted creature gets +0/+4. | the engine reads this text and performs it | Y/-/- | not_tested |
| Eldrazi Conscription | handled | Enchanted creature gets +10/+10 and has trample and annihilator 2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Emerge Unscathed | handled | Target creature you control gains protection from the color of your choice until end of turn. Rebound (If you cast this spell from your hand, exile it as it res | the engine reads this text and performs it | Y/-/- | not_tested |
| Emrakul's Hatcher | handled | When this creature enters, create three 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Enatu Golem | handled | When this creature dies, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Enclave Cryptologist | handled | {T}: Draw a card, then discard a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Escaped Null | handled | Whenever this creature blocks or becomes blocked, it gets +5/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Evolving Wilds | handled | {T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Fissure Vent | handled | Choose one or both — • Destroy target artifact. • Destroy target nonbasic land. | the engine reads this text and performs it | Y/-/- | not_tested |
| Flame Slash | handled | Flame Slash deals 4 damage to target creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Fleeting Distraction | handled | Target creature gets -1/-0 until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Forked Bolt | handled | Forked Bolt deals 2 damage divided as you choose among one or two targets. | the engine reads this text and performs it | Y/-/- | not_tested |
| Frostwind Invoker | handled | {8}: Creatures you control gain flying until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gelatinous Genesis | handled | Create X X/X green Ooze creature tokens. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gigantomancer | handled | {1}: Target creature you control has base power and toughness 7/7 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gloomhunter | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Goblin Arsonist | handled | When this creature dies, you may have it deal 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Goblin Tunneler | handled | {T}: Target creature with power 2 or less can't be blocked this turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Gravitational Shift | handled | Creatures with flying get +2/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Grotag Siege-Runner | handled | {R}, Sacrifice this creature: Destroy target creature with defender. This creature deals 2 damage to that creature's controller. | the engine reads this text and performs it | Y/-/- | not_tested |
| Growth Spasm | handled | Search your library for a basic land card, put it onto the battlefield tapped, then shuffle. Create a 0/1 colorless Eldrazi Spawn creature token. It has "Sacrif | the engine reads this text and performs it | Y/-/- | not_tested |
| Guard Duty | handled | Enchanted creature has defender. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guard Gomazoa | handled | Prevent all combat damage that would be dealt to this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Guul Draz Assassin | handled | {B}, {T}: Target creature gets -2/-2 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Hada Spy Patrol | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/-/- | not_tested |
| Halimar Wavewatch | handled | Landwalk | no code needed | Y/-/- | not_tested |
| Hand of Emrakul | handled | You may sacrifice four Eldrazi Spawn rather than pay this spell's mana cost. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ikiral Outrider | handled | Vigilance | machines/combat.py | Y/-/- | not_tested |
| Induce Despair | handled | As an additional cost to cast this spell, reveal a creature card from your hand. Target creature gets -X/-X until end of turn, where X is the revealed card's ma | the engine reads this text and performs it | Y/-/- | not_tested |
| Jwari Scuttler | handled |  |  | Y/-/- | not_tested |
| Kabira Vindicator | handled | Other creatures you control get +1/+1. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kargan Dragonlord | handled | {R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kazandu Tuskcaller | handled | {T}: Create a 3/3 green Elephant creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kiln Fiend | handled | Whenever you cast an instant or sorcery spell, this creature gets +3/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Knight of Cliffhaven | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Kor Line-Slinger | handled | {T}: Tap target creature with power 3 or less. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kor Spiritdancer | handled | This creature gets +2/+2 for each Aura attached to it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Kozilek's Predator | handled | When this creature enters, create two 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Kozilek, Butcher of Truth | handled | When you cast this spell, draw four cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lagac Lizard | handled |  |  | Y/-/- | not_tested |
| Last Kiss | handled | Last Kiss deals 2 damage to target creature and you gain 2 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lavafume Invoker | handled | {8}: Creatures you control get +3/+0 until end of turn. | the engine reads this text and performs it | Y/-/- | not_tested |
| Leaf Arrow | handled | Leaf Arrow deals 3 damage to target creature with flying. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lighthouse Chronologist | handled | At the beginning of each end step, if it's not your turn, take an extra turn after this one. | the engine reads this text and performs it | Y/-/- | not_tested |
| Linvala, Keeper of Silence | handled | Activated abilities of creatures your opponents control can't be activated. | the engine reads this text and performs it | Y/-/- | not_tested |
| Lone Missionary | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Luminous Wake | handled | Whenever enchanted creature attacks or blocks, you gain 4 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Magmaw | handled | {1}, Sacrifice a nonland permanent: This creature deals 1 damage to any target. | the engine reads this text and performs it | Y/-/- | not_tested |
| Makindi Griffin | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Mammoth Umbra | handled | Enchanted creature gets +3/+3 and has vigilance. | the engine reads this text and performs it | Y/-/- | not_tested |
| Merfolk Skyscout | handled | Whenever this creature attacks or blocks, untap target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Mnemonic Wall | handled | When this creature enters, you may return target instant or sorcery card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Mortician Beetle | handled | Whenever a player sacrifices a creature, you may put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nema Siltlurker | handled |  |  | Y/-/- | not_tested |
| Nest Invader | handled | When this creature enters, create a 0/1 colorless Eldrazi Spawn creature token. It has "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Nighthaze | handled | Target creature gains swampwalk until end of turn. (It can't be blocked as long as defending player controls a Swamp.) Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Nirkana Cutthroat | handled | First strike | machines/combat.py | Y/-/- | not_tested |
| Nomads' Assembly | handled | Create a 1/1 white Kor Soldier creature token for each creature you control. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beg | the engine reads this text and performs it | Y/-/- | not_tested |
| Null Champion | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ogre Sentry | handled | Defender | machines/combat.py | Y/-/- | not_tested |
| Ogre's Cleaver | handled | Equipped creature gets +5/+0. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ondu Giant | handled | When this creature enters, you may search your library for a basic land card, put it onto the battlefield tapped, then shuffle. | the engine reads this text and performs it | Y/-/- | not_tested |
| Pawn of Ulamog | handled | Whenever this creature or another nontoken creature you control dies, you may create a 0/1 colorless Eldrazi Spawn creature token. It has "Sacrifice this token: | the engine reads this text and performs it | Y/-/- | not_tested |
| Pelakka Wurm | handled | When this creature enters, you gain 7 life. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pennon Blade | handled | Equipped creature gets +1/+1 for each creature you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Phantasmal Abomination | handled | When this creature becomes the target of a spell or ability, sacrifice it. | the engine reads this text and performs it | Y/-/- | not_tested |
| Prey's Vengeance | handled | Target creature gets +2/+2 until end of turn. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you | the engine reads this text and performs it | Y/-/- | not_tested |
| Puncturing Light | handled | Destroy target attacking or blocking creature with power 3 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rage Nimbus | handled | {1}{R}: Target creature attacks this turn if able. | the engine reads this text and performs it | Y/-/- | not_tested |
| Rapacious One | handled | Whenever this creature deals combat damage to a player, create that many 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Reality Spasm | handled | Choose one — • Tap X target permanents. • Untap X target permanents. | the engine reads this text and performs it | Y/-/- | not_tested |
| Repel the Darkness | handled | Tap up to two target creatures. Draw a card. | the engine reads this text and performs it | Y/-/- | not_tested |
| Runed Servitor | handled | When this creature dies, each player draws a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sea Gate Oracle | handled | When this creature enters, look at the top two cards of your library. Put one of them into your hand and the other on the bottom of your library. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shared Discovery | handled | As an additional cost to cast this spell, tap four untapped creatures you control. Draw three cards. | the engine reads this text and performs it | Y/-/- | not_tested |
| Shrivel | handled | All creatures get -1/-1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skeletal Wurm | handled | {B}: Regenerate this creature. | the engine reads this text and performs it | Y/-/- | not_tested |
| Skittering Invasion | handled | Create five 0/1 colorless Eldrazi Spawn creature tokens. They have "Sacrifice this token: Add {C}." | the engine reads this text and performs it | Y/-/- | not_tested |
| Skywatcher Adept | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Snake Umbra | handled | Enchanted creature gets +1/+1 and has "Whenever this creature deals damage to an opponent, you may draw a card." | the engine reads this text and performs it | Y/-/- | not_tested |
| Soul's Attendant | handled | Whenever another creature enters, you may gain 1 life. | the engine reads this text and performs it | Y/-/- | not_tested |
| Soulbound Guardians | handled | Flying | machines/combat.py | Y/-/- | not_tested |
| Soulsurge Elemental | handled | Soulsurge Elemental's power is equal to the number of creatures you control. | the engine reads this text and performs it | Y/-/- | not_tested |
| Sphinx of Magosi | handled | {2}{U}: Draw a card, then put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sphinx-Bone Wand | handled | Whenever you cast an instant or sorcery spell, you may put a charge counter on this artifact. If you do, this artifact deals damage equal to the number of charg | the engine reads this text and performs it | Y/-/- | not_tested |
| Spider Umbra | handled | Enchanted creature gets +1/+1 and has reach. | the engine reads this text and performs it | Y/-/- | not_tested |
| Splinter Twin | handled | Enchanted creature has "{T}: Create a token that's a copy of this creature, except it has haste. Exile that token at the beginning of the next end step." | the engine reads this text and performs it | Y/-/- | not_tested |
| Sporecap Spider | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Staggershock | handled | Staggershock deals 2 damage to any target. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of your next upkeep, you ma | the engine reads this text and performs it | Y/-/- | not_tested |
| Stalwart Shield-Bearers | handled | Other creatures you control with defender get +0/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Stomper Cub | handled | Trample | machines/combat.py | Y/-/- | not_tested |
| Surreal Memoir | handled | Return an instant card at random from your graveyard to your hand. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of  | the engine reads this text and performs it | Y/-/- | not_tested |
| Survival Cache | handled | You gain 2 life. Then if you have more life than an opponent, draw a card. Rebound (If you cast this spell from your hand, exile it as it resolves. At the begin | the engine reads this text and performs it | Y/-/- | not_tested |
| Time of Heroes | handled | Each creature you control with a level counter on it gets +2/+2. | the engine reads this text and performs it | Y/-/- | not_tested |
| Totem-Guide Hartebeest | handled | When this creature enters, you may search your library for an Aura card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Training Grounds | handled | Activated abilities of creatures you control cost {2} less to activate. This effect can't reduce the mana in that cost to less than one mana. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Traitorous Instinct | handled | Gain control of target creature until end of turn. Untap that creature. Until end of turn, it gets +2/+0 and gains haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Transcendent Master | handled | Lifelink | machines/combat.py | Y/-/- | not_tested |
| Tuktuk the Explorer | handled | When Tuktuk the Explorer dies, create Tuktuk the Returned, a legendary 5/5 colorless Goblin Golem artifact creature token. | the engine reads this text and performs it | Y/-/- | not_tested |
| Ulamog, the Infinite Gyre | handled | When you cast this spell, destroy target permanent. | the engine reads this text and performs it | Y/-/- | not_tested |
| Virulent Swipe | handled | Target creature gets +2/+0 and gains deathtouch until end of turn. Rebound (If you cast this spell from your hand, exile it as it resolves. At the beginning of  | the engine reads this text and performs it | Y/-/- | not_tested |
| Wildheart Invoker | handled | {8}: Target creature gets +5/+5 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Zof Shade | handled | {2}{B}: This creature gets +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>57 cards</summary>

- All Is Dust
- Ancient Stirrings
- Aura Gnarlid
- Baneful Omen
- Brimstone Mage
- Cast Through Time
- Conquering Manticore
- Consuming Vapors
- Contaminated Ground
- Coralhelm Commander
- Dawnglare Invoker
- Eldrazi Temple
- Emrakul, the Aeons Torn
- Essence Feed
- Explosive Revelation
- Gravity Well
- Harmless Assault
- Haze Frog
- Hedron Matrix
- Hedron-Field Purists
- Hyena Umbra
- Inquisition of Kozilek
- Jaddi Lifestrider
- Joraga Treespeaker
- Keening Stone
- Khalni Hydra
- Lightmine Field
- Living Destiny
- Lord of Shatterskull Pass
- Lust for War
- Merfolk Observer
- Might of the Masses
- Momentous Fall
- Mul Daya Channelers
- Narcolepsy
- Near-Death Experience
- Nirkana Revenant
- Overgrown Battlement
- Pathrazer of Ulamog
- Pestilence Demon
- Prophetic Prism
- Recurring Insight
- Reinforced Bulwark
- Repay in Kind
- Sarkhan the Mad
- Spawning Breath
- Student of Warfare
- Suffer the Past
- Surrakar Spellblade
- Tajuru Preserver
- Ulamog's Crusher
- Umbra Mystic
- Vengevine
- Vent Sentinel
- Wall of Omens
- Wrap in Flames
- Zulaport Enforcer

</details>

## Missing mechanics

| Mechanic (label / template) | Count | Example cards | Sets |
|---|---|---|---|
| +N: during target opponent's next turn, creatures that player controls attack ~ if able. | 1 | Gideon Jura | roe |
| after the second main phase ~, there's an additional combat phase followed by an additional main phase. at the beginning of that combat, untap all creatures tha | 1 | World at War | roe |
| as an additional cost to cast ~, reveal a creature card from your hand. ~ deals N damage to each creature your opponents control, where N is the revealed card's | 1 | Disaster Radius | roe |
| as long as equipped creature has defender, it can attack as though it didn't have defender. | 1 | Warmonger's Chariot | roe |
| at the beginning of combat on your turn, you may have target creature get +N/+N until end of turn. | 1 | Battle-Rattle Shaman | roe |
| attach target aura you control to target creature. draw a card. | 1 | Aura Finesse | roe |
| counter target spell if you control more creatures than that spell's controller. | 1 | Unified Will | roe |
| counter target spell or ability that targets a permanent you control. ~ costs {M} less to cast if it targets a spell or ability that targets a creature you cont | 1 | Not of This World | roe |
| counter target spell. look at its controller's hand. | 1 | Lay Bare | roe |
| draw two cards, then shuffle a card from your hand into your library. | 1 | See Beyond | roe |
| if you control an eldrazi spawn, create three N/N colorless eldrazi spawn creature tokens. they have "..." otherwise, create one of those tokens. | 1 | Brood Birthing | roe |
| put target creature into its owner's library second from the top. its controller gains N life. | 1 | Oust | roe |
| sacrifice all creatures you control, then create that many N/N red hellion creature tokens. | 1 | Hellion Eruption | roe |
| search your library for up to four land cards with different names and reveal them. an opponent chooses two of those cards. put the chosen cards into your grave | 1 | Realms Uncharted | roe |
| target creature gets +N/+N until end of turn and can't be blocked ~. rebound (if you cast ~ from your hand, exile it as it resolves. at the beginning of your ne | 1 | Distortion Strike | roe |
| target creature must be blocked ~ if able. draw a card. | 1 | Irresistible Prey | roe |
| target opponent reveals their hand. you choose a card from it. that player shuffles that card into their library. | 1 | Perish the Thought | roe |
| when ~ enters, put a +N/+N counter on it for each card in your hand. if you do, discard your hand. | 1 | Thought Gorger | roe |
| when ~ enters, put two level counters on each creature you control with level up. | 1 | Venerated Teacher | roe |
| whenever a creature you control with power N or less attacks, ~ deals N damage to the player or planeswalker that creature is attacking. | 1 | Raid Bombardment | roe |
| whenever an opponent sacrifices a nontoken permanent, put that card onto the battlefield under your control. | 1 | It That Betrays | roe |
| whenever another creature you control enters, you may have ~ become a copy of that creature until end of turn. | 1 | Renegade Doppelganger | roe |
| whenever you become the target of a spell, you may untap ~. | 1 | Dormant Gomazoa | roe |
| whenever you're dealt damage, you may put that many charge counters on ~. | 1 | Angelheart Vial | roe |
| whenever ~ attacks, switch its power and toughness until end of turn. | 1 | Valakut Fireboar | roe |
| whenever ~ blocks or becomes blocked by a creature with power N or less, destroy ~ at end of combat. | 1 | Arrogant Bloodlord | roe |
| whenever ~ deals combat damage to a player, sacrifice all other permanents you control and discard your hand. exile the top six cards of your library. you may c | 1 | Hellcarver Demon | roe |
| {M}: cast any number of eldrazi spells from among cards you own outside the game without paying their mana costs. | 1 | Spawnsire of Ulamog | roe |
| {M}{M}, {M}: copy target instant or sorcery spell twice. you may choose new targets for the copies. | 1 | Echo Mage | roe |
| {M}{M}{M}: target creature gets -N/-N until end of turn and drana gets +N/+N until end of turn. | 1 | Drana, Kalastria Bloodchief | roe |
| ~ gets +N/+N as long as you control a creature with three or more level counters on it. | 1 | Champion's Drake | roe |

## Notes



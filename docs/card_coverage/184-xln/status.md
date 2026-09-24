# Ixalan (xln)

- Expansion: 184
- Set code: `xln`
- Release date: 2017-09-29
- Cards in scope (Modern/Pioneer/Standard-legal): 170

## Legality

| Format | Legal cards |
|---|---|
| Modern | 170 |
| Pioneer | 170 |
| Standard | 7 |

## Coverage

| Bucket | Count | % |
|---|---|---|
| Full (handled + tested) | 6 | 3.5% |
| Partial (unaudited) | 9 | 5.3% |
| Not tested (handled, untested) | 121 | 71.2% |
| Not working (silent / notice / error) | 34 | 20.0% |

## Cards needing work

| Card | Status | Worst clause | Reason | Legal (M/P/S) | Bucket |
|---|---|---|---|---|---|
| Adanto Vanguard | silent | As long as this creature is attacking, it gets +2/+0. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Anointed Deacon | silent | At the beginning of combat on your turn, you may have target Vampire get +2/+0 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Atzocan Archer | silent | When this creature enters, you may have it fight another target creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dinosaur Stampede | silent | Attacking creatures get +2/+0 until end of turn. Dinosaurs you control gain trample until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Dire Fleet Captain | silent | Whenever this creature attacks, it gets +1/+1 until end of turn for each other attacking Pirate. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Duskborne Skymarcher | silent | {W}, {T}: Target attacking Vampire gets +1/+1 until end of turn. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Elaborate Firecannon | silent | At the beginning of your upkeep, you may discard a card. If you do, untap this artifact. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Grasping Current | silent | Return up to two target creatures to their owner's hand. Search your library and/or graveyard for a card named Jace, Ingenious Mind-Mage, reveal it, and put it  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Grim Captain's Call | silent | Return a Pirate card from your graveyard to your hand, then do the same for Vampire, Dinosaur, and Merfolk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Huatli, Dinosaur Knight | silent | −3: Target Dinosaur you control deals damage equal to its power to target creature you don't control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jace's Sentinel | silent | As long as you control a Jace planeswalker, this creature gets +1/+0 and can't be blocked. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Jace, Ingenious Mind-Mage | silent | −9: Gain control of up to three target creatures. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Kitesail Freebooter | silent | When this creature enters, target opponent reveals their hand. You choose a noncreature, nonland card from it. Exile that card until this creature leaves the ba | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Legion Conquistador | silent | When this creature enters, you may search your library for any number of cards named Legion Conquistador, reveal them, put them into your hand, then shuffle. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Lurking Chupacabra | silent | Whenever a creature you control explores, target creature an opponent controls gets -2/-2 until end of turn. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Perilous Voyage | silent | Return target nonland permanent you don't control to its owner's hand. If its mana value was 2 or less, scry 2. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Raging Swordtooth | silent | When this creature enters, it deals 1 damage to each other creature. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| River Heralds' Boon | silent | Put a +1/+1 counter on target creature and a +1/+1 counter on up to one target Merfolk. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Run Aground | silent | Put target artifact or creature on top of its owner's library. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Siren Stormtamer | silent | {U}, Sacrifice this creature: Counter target spell or ability that targets you or a creature you control. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Steadfast Armasaur | silent | {1}{W}, {T}: This creature deals damage equal to its toughness to target creature blocking or blocked by it. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Storm Sculptor | silent | When this creature enters, return a creature you control to its owner's hand. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Sun-Blessed Mount | silent | When this creature enters, you may search your library and/or graveyard for a card named Huatli, Dinosaur Knight, reveal it, then put it into your hand. If you  | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Thrash of Raptors | silent | As long as you control another Dinosaur, this creature gets +2/+0 and has trample. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Wanted Scoundrels | silent | When this creature dies, target opponent creates two Treasure tokens. | nothing in the engine reads this text - it would do nothing and log nothing | Y/Y/- | not_working |
| Wildgrowth Walker | silent | Whenever a creature you control explores, put a +1/+1 counter on this creature and you gain 3 life. | the engine does not recognise this trigger's condition - it never triggers | Y/Y/- | not_working |
| Blinding Fog | notice | Prevent all damage that would be dealt to creatures this turn. Creatures you control gain hexproof until end of turn. (They can't be the targets of spells or ab | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Drover of the Mighty | notice | This creature gets +2/+2 as long as you control a Dinosaur. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Emergent Growth | notice | Target creature gets +5/+5 until end of turn and must be blocked this turn if able. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Kumena's Speaker | notice | This creature gets +1/+1 as long as you control another Merfolk or an Island. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Siren's Ruse | notice | Exile target creature you control, then return that card to the battlefield under its owner's control. If a Pirate was exiled this way, draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Skulduggery | notice | Until end of turn, target creature you control gets +1/+1 and target creature an opponent controls gets -1/-1. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/Y | not_working |
| Vampire's Zeal | notice | Target creature gets +2/+2 until end of turn. If it's a Vampire, it gains first strike until end of turn. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Verdant Rebirth | notice | Until end of turn, target creature gains "When this creature dies, return it to its owner's hand." Draw a card. | the engine recognises this text but fails closed with a notice instead of performing it | Y/Y/- | not_working |
| Belligerent Brontodon | unaudited | Each creature you control assigns combat damage equal to its toughness rather than its power. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Bonded Horncrest | unaudited | This creature can't attack or block alone. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ixalan's Binding | unaudited | Your opponents can't cast spells with the same name as the exiled card. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| New Horizons | unaudited | Enchanted land has "{T}: Add two mana of any one color." | a static ability no support check audits - not verified either way | Y/Y/Y | partial |
| Pious Interdiction | unaudited | Enchanted creature can't attack or block. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Rigging Runner | unaudited | Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Spike-Tailed Ceratops | unaudited | This creature can block an additional creature each combat. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Storm Fleet Aerialist | unaudited | Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Trove of Temptation | unaudited | Each opponent must attack you or a planeswalker you control with at least one creature each combat if able. | a static ability no support check audits - not verified either way | Y/Y/- | partial |
| Ancient Brontodon | handled |  |  | Y/Y/- | not_tested |
| Bishop of the Bloodstained | handled | When this creature enters, target opponent loses 1 life for each Vampire you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bishop's Soldier | handled | Lifelink | machines/combat.py | Y/Y/Y | not_tested |
| Blight Keeper | handled | {7}{B}, {T}, Sacrifice this creature: Target opponent loses 4 life and you gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Blossom Dryad | handled | {T}: Untap target land. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Brazen Buccaneers | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Bright Reprisal | handled | Destroy target attacking creature. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Call to the Feast | handled | Create three 1/1 white Vampire creature tokens with lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Castaway's Despair | handled | When this Aura enters, tap enchanted creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Charging Monstrosaur | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| Chart a Course | handled | Draw two cards. Then discard a card unless you attacked this turn. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Commune with Dinosaurs | handled | Look at the top five cards of your library. You may reveal a Dinosaur or land card from among them and put it into your hand. Put the rest on the bottom of your | the engine reads this text and performs it | Y/Y/- | not_tested |
| Contract Killing | handled | Destroy target creature. Create two Treasure tokens. (They're artifacts with "{T}, Sacrifice this token: Add one mana of any color.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Costly Plunder | handled | As an additional cost to cast this spell, sacrifice an artifact or creature. Draw two cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crash the Ramparts | handled | Target creature gets +3/+3 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Crushing Canopy | handled | Choose one — • Destroy target creature with flying. • Destroy target enchantment. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dark Nourishment | handled | Dark Nourishment deals 3 damage to any target. You gain 3 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Plunderers | handled | This creature gets +1/+1 for each artifact you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Quartermaster | handled | When this creature enters, you may search your library for an Equipment or Vehicle card, reveal it, put it into your hand, then shuffle. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deadeye Tormentor | handled | Raid — When this creature enters, if you attacked this turn, target opponent discards a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deathless Ancient | handled | Tap three untapped Vampires you control: Return this card from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deeproot Warrior | handled | Whenever this creature becomes blocked, it gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Deeproot Waters | handled | Whenever you cast a Merfolk spell, create a 1/1 blue Merfolk creature token with hexproof. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Depths of Desire | handled | Return target creature to its owner's hand. Create a Treasure token. (It's an artifact with "{T}, Sacrifice this token: Add one mana of any color.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Desperate Castaways | handled | This creature can't attack unless you control an artifact. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dire Fleet Hoarder | handled | When this creature dies, create a Treasure token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dire Fleet Interloper | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Dive Down | handled | Target creature you control gets +0/+3 and gains hexproof until end of turn. (It can't be the target of spells or abilities your opponents control.) | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Dusk Legion Dreadnought | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Emissary of Sunrise | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Encampment Keeper | handled | {7}{W}, {T}, Sacrifice this creature: Creatures you control get +2/+2 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fathom Fleet Cutthroat | handled | When this creature enters, destroy target creature an opponent controls that was dealt damage this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fathom Fleet Firebrand | handled | {1}{R}: This creature gets +1/+0 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Fire Shrine Keeper | handled | {7}{R}, {T}, Sacrifice this creature: It deals 3 damage to each of up to two target creatures. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Firecannon Blast | handled | Firecannon Blast deals 3 damage to target creature. Raid — Firecannon Blast deals 6 damage instead if you attacked this turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Frenzied Raptor | handled |  |  | Y/Y/- | not_tested |
| Gilded Sentinel | handled |  |  | Y/Y/- | not_tested |
| Glorifier of Dusk | handled | Pay 2 life: This creature gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Grazing Whiptail | handled | Reach | machines/combat.py | Y/Y/- | not_tested |
| Headstrong Brute | handled | This creature can't block. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Headwater Sentries | handled |  |  | Y/Y/- | not_tested |
| Heartless Pillage | handled | Target opponent discards two cards. Raid — If you attacked this turn, create a Treasure token. (It's an artifact with "{T}, Sacrifice this token: Add one mana o | the engine reads this text and performs it | Y/Y/- | not_tested |
| Hierophant's Chalice | handled | When this artifact enters, target opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Huatli's Snubhorn | handled | Vigilance | machines/combat.py | Y/Y/- | not_tested |
| Huatli's Spurring | handled | Target creature gets +2/+0 until end of turn. If you control a Huatli planeswalker, that creature gets +4/+0 until end of turn instead. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Imperial Aerosaur | handled | When this creature enters, another target creature you control gets +1/+1 and gains flying until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Imperial Lancer | handled | This creature has double strike as long as you control a Dinosaur. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Inspiring Cleric | handled | When this creature enters, you gain 4 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ixalli's Diviner | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ixalli's Keeper | handled | {7}{G}, {T}, Sacrifice this creature: Target creature gets +5/+5 and gains trample until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jade Guardian | handled | When this creature enters, put a +1/+1 counter on target Merfolk you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Jungle Delver | handled | {3}{G}: Put a +1/+1 counter on this creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Kinjalli's Caller | handled | Dinosaur spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Legion's Judgment | handled | Destroy target creature with power 4 or greater. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lightning-Rig Crew | handled | {T}: This creature deals 1 damage to each opponent. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Lookout's Dispersal | handled | This spell costs {1} less to cast if you control a Pirate. Counter target spell unless its controller pays {4}. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Looming Altisaur | handled |  |  | Y/Y/- | not_tested |
| Makeshift Munitions | handled | {1}, Sacrifice an artifact or creature: This enchantment deals 1 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Marauding Looter | handled | Raid — At the beginning of your end step, if you attacked this turn, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| March of the Drowned | handled | Choose one — • Return target creature card from your graveyard to your hand. • Return two target Pirate cards from your graveyard to your hand. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Navigator's Ruin | handled | Raid — At the beginning of your end step, if you attacked this turn, target opponent mills four cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Nest Robber | handled | Haste | machines/combat.py | Y/Y/- | not_tested |
| One With the Wind | handled | Enchanted creature gets +2/+2 and has flying. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Otepec Huntmaster | handled | Dinosaur spells you cast cost {1} less to cast. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Paladin of the Bloodstained | handled | When this creature enters, create a 1/1 white Vampire creature token with lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pillar of Origins | handled | As this artifact enters, choose a creature type. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pirate's Cutlass | handled | When this Equipment enters, attach it to target Pirate you control. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Pirate's Prize | handled | Draw two cards. Create a Treasure token. (It's an artifact with "{T}, Sacrifice this token: Add one mana of any color.") | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pounce | handled | Target creature you control fights target creature you don't control. (Each deals damage equal to its power to the other.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prosperous Pirates | handled | When this creature enters, create two Treasure tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Prying Blade | handled | Equipped creature gets +1/+0. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Pterodon Knight | handled | This creature has flying as long as you control a Dinosaur. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Queen's Agent | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Queen's Bay Soldier | handled |  |  | Y/Y/- | not_tested |
| Queen's Commission | handled | Create two 1/1 white Vampire creature tokens with lifelink. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raiders' Wake | handled | Whenever an opponent discards a card, that player loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rallying Roar | handled | Creatures you control get +1/+1 until end of turn. Untap them. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Raptor Companion | handled |  |  | Y/Y/- | not_tested |
| Raptor Hatchling | handled | Enrage — Whenever this creature is dealt damage, create a 3/3 green Dinosaur creature token with trample. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ravenous Daggertooth | handled | Enrage — Whenever this creature is dealt damage, you gain 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Rile | handled | Rile deals 1 damage to target creature you control. That creature gains trample until end of turn. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ritual of Rejuvenation | handled | You gain 4 life. Draw a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| River Sneak | handled | This creature can't be blocked. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Ruthless Knave | handled | {2}{B}, Sacrifice a creature: Create two Treasure tokens. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sailor of Means | handled | When this creature enters, create a Treasure token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Savage Stomp | handled | This spell costs {2} less to cast if it targets a Dinosaur you control. Put a +1/+1 counter on target creature you control. Then that creature fights target cre | the engine reads this text and performs it | Y/Y/- | not_tested |
| Seekers' Squire | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sentinel Totem | handled | When this artifact enters, scry 1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shaper Apprentice | handled | This creature has flying as long as you control another Merfolk. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shapers of Nature | handled | {3}{G}: Put a +1/+1 counter on target creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sheltering Light | handled | Target creature gains indestructible until end of turn. Scry 1. (Damage and effects that say "destroy" don't destroy the creature.) | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shining Aerosaur | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Shipwreck Looter | handled | Raid — When this creature enters, if you attacked this turn, you may draw a card. If you do, discard a card. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Shore Keeper | handled | {7}{U}, {T}, Sacrifice this creature: Draw three cards. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Siren Lookout | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Skittering Heartstopper | handled | {B}: This creature gains deathtouch until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sky Terror | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Skyblade of the Legion | handled | Flying | machines/combat.py | Y/Y/- | not_tested |
| Skymarch Bloodletter | handled | When this creature enters, target opponent loses 1 life and you gain 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Slash of Talons | handled | Slash of Talons deals 2 damage to target attacking or blocking creature. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sleek Schooner | handled | Crew | machines/keywords.py | Y/Y/- | not_tested |
| Snapping Sailback | handled | Enrage — Whenever this creature is dealt damage, put a +1/+1 counter on it. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Spreading Rot | handled | Destroy target land. Its controller loses 2 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm Fleet Arsonist | handled | Raid — When this creature enters, if you attacked this turn, target opponent sacrifices a permanent of their choice. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm Fleet Pyromancer | handled | Raid — When this creature enters, if you attacked this turn, this creature deals 2 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Storm Fleet Spy | handled | Raid — When this creature enters, if you attacked this turn, draw a card. | the engine reads this text and performs it | Y/Y/Y | not_tested |
| Sun-Crowned Hunters | handled | Enrage — Whenever this creature is dealt damage, it deals 3 damage to target opponent or planeswalker. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Sunrise Seeker | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Swashbuckling | handled | Enchanted creature gets +2/+2 and has haste. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tempest Caller | handled | When this creature enters, tap all creatures target opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Territorial Hammerskull | handled | Whenever this creature attacks, tap target creature an opponent controls. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Thundering Spineback | handled | Other Dinosaurs you control get +1/+1. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tilonalli's Knight | handled | Whenever this creature attacks, if you control a Dinosaur, this creature gets +1/+1 until end of turn. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Tishana's Wayfinder | handled | When this creature enters, it explores. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Unfriendly Fire | handled | Unfriendly Fire deals 4 damage to any target. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vanquish the Weak | handled | Destroy target creature with power 3 or less. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vicious Conquistador | handled | Whenever this creature attacks, each opponent loses 1 life. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Vineshaper Mystic | handled | When this creature enters, put a +1/+1 counter on each of up to two target Merfolk you control. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Watertrap Weaver | handled | When this creature enters, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wily Goblin | handled | When this creature enters, create a Treasure token. | the engine reads this text and performs it | Y/Y/- | not_tested |
| Wind Strider | handled | Flying | machines/combat.py | Y/Y/- | not_tested |

## Fully supported

<details>
<summary>6 cards</summary>

- Bellowing Aegisaur
- Colossal Dreadmaw
- Field of Ruin
- Fiery Cannonade
- Merfolk Branchwalker
- Ranging Raptors

</details>

## Missing mechanics

| Mechanic (representative clause) | Cards | Count |
|---|---|---|
| When this creature enters, you may search your library and/or graveyard for a card named Huatli, Dinosaur Knight, reveal it, then put it into your hand. If you  | Atzocan Archer, Legion Conquistador, Sun-Blessed Mount | 3 |
| As long as you control a Jace planeswalker, this creature gets +1/+0 and can't be blocked. | Jace's Sentinel, Thrash of Raptors | 2 |
| Raid — This creature enters with a +1/+1 counter on it if you attacked this turn. | Rigging Runner, Storm Fleet Aerialist | 2 |
| Target creature gets +2/+2 until end of turn. If it's a Vampire, it gains first strike until end of turn. | Emergent Growth, Vampire's Zeal | 2 |
| This creature gets +1/+1 as long as you control another Merfolk or an Island. | Drover of the Mighty, Kumena's Speaker | 2 |
| Until end of turn, target creature gains "When this creature dies, return it to its owner's hand." Draw a card. | Skulduggery, Verdant Rebirth | 2 |
| Whenever a creature you control explores, target creature an opponent controls gets -2/-2 until end of turn. | Lurking Chupacabra, Wildgrowth Walker | 2 |
| As long as this creature is attacking, it gets +2/+0. | Adanto Vanguard | 1 |
| At the beginning of combat on your turn, you may have target Vampire get +2/+0 until end of turn. | Anointed Deacon | 1 |
| At the beginning of your upkeep, you may discard a card. If you do, untap this artifact. | Elaborate Firecannon | 1 |
| Attacking creatures get +2/+0 until end of turn. Dinosaurs you control gain trample until end of turn. | Dinosaur Stampede | 1 |
| Each creature you control assigns combat damage equal to its toughness rather than its power. | Belligerent Brontodon | 1 |
| Each opponent must attack you or a planeswalker you control with at least one creature each combat if able. | Trove of Temptation | 1 |
| Enchanted creature can't attack or block. | Pious Interdiction | 1 |
| Enchanted land has "{T}: Add two mana of any one color." | New Horizons | 1 |
| Exile target creature you control, then return that card to the battlefield under its owner's control. If a Pirate was exiled this way, draw a card. | Siren's Ruse | 1 |
| −9: Gain control of up to three target creatures. | Jace, Ingenious Mind-Mage | 1 |
| Prevent all damage that would be dealt to creatures this turn. Creatures you control gain hexproof until end of turn. (They can't be the targets of spells or ab | Blinding Fog | 1 |
| Put a +1/+1 counter on target creature and a +1/+1 counter on up to one target Merfolk. | River Heralds' Boon | 1 |
| Put target artifact or creature on top of its owner's library. | Run Aground | 1 |
| Return a Pirate card from your graveyard to your hand, then do the same for Vampire, Dinosaur, and Merfolk. | Grim Captain's Call | 1 |
| Return target nonland permanent you don't control to its owner's hand. If its mana value was 2 or less, scry 2. | Perilous Voyage | 1 |
| Return up to two target creatures to their owner's hand. Search your library and/or graveyard for a card named Jace, Ingenious Mind-Mage, reveal it, and put it  | Grasping Current | 1 |
| {U}, Sacrifice this creature: Counter target spell or ability that targets you or a creature you control. | Siren Stormtamer | 1 |
| {W}, {T}: Target attacking Vampire gets +1/+1 until end of turn. | Duskborne Skymarcher | 1 |
| −3: Target Dinosaur you control deals damage equal to its power to target creature you don't control. | Huatli, Dinosaur Knight | 1 |
| This creature can block an additional creature each combat. | Spike-Tailed Ceratops | 1 |
| This creature can't attack or block alone. | Bonded Horncrest | 1 |
| {1}{W}, {T}: This creature deals damage equal to its toughness to target creature blocking or blocked by it. | Steadfast Armasaur | 1 |
| When this creature dies, target opponent creates two Treasure tokens. | Wanted Scoundrels | 1 |
| When this creature enters, it deals 1 damage to each other creature. | Raging Swordtooth | 1 |
| When this creature enters, return a creature you control to its owner's hand. | Storm Sculptor | 1 |
| When this creature enters, target opponent reveals their hand. You choose a noncreature, nonland card from it. Exile that card until this creature leaves the ba | Kitesail Freebooter | 1 |
| Whenever this creature attacks, it gets +1/+1 until end of turn for each other attacking Pirate. | Dire Fleet Captain | 1 |
| Your opponents can't cast spells with the same name as the exiled card. | Ixalan's Binding | 1 |

## Notes



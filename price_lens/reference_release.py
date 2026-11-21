"""Release evidence for the November 18 Classic World update."""
from datetime import datetime, timezone

from .reference_relations import quest_rewards


NOVEMBER_NOTES = 'https://www.nexon.com/maplestory/news/update/48255/november-update-forgotten-hollow-patch-notes'
NOVEMBER_QUESTS = 'https://mapleclassic.wiki/wiki/Update:18_November_2026_Forgotten_Hollow#Quests'
HOLLOW_SHOP_SOURCE = 'https://meowdb.com/msclassic/npc-shops'
KPQ_REWARD_REPORTS = 'https://meowdb.com/msclassic/guides/kerning-city-party-quest-kpq-guide'
NOVEMBER_RELEASE = datetime(2026, 11, 18, tzinfo=timezone.utc)
NOVEMBER_EVIDENCE_VERSION = 2

# Exact identities checked against the post-update export. In particular, the
# unplaced Glowshroom, Golden Stirge and Rotten Mushmom duplicates are separate
# IDs. The Patch Notes name quest chains, so the individual steps also use the
# published quest listing.
HOLLOW_MAPS = {
    10006000: 'Forgotten Hollow', 10006001: 'Cave Fairy Sanctuary',
    10006002: 'Cave Fairy Store', 10006003: 'The Faded Threshold',
    10006010: 'Primeval Forest I', 10006020: 'Primeval Forest II',
    10006022: 'Hanging Gardens of Rot', 10006030: 'Primeval Forest III',
    10006031: 'The Valley of Death', 10006040: 'Forgotten Entrance I',
    10006050: 'Forgotten Entrance II', 10006060: 'Forgotten Entrance III',
    10006070: 'The End of Fleeting Light', 10006071: 'Forgotten Dungeon Tunnel',
    10006072: 'The Faded Canopy', 10006080: 'Forbidden Entrance',
    10006090: 'Perilous Descent I', 10006100: 'Perilous Descent II',
    10006110: 'Perilous Descent III', 10006120: 'Decayed Tunnel I',
    10006121: "Someone Else's Grave", 10006122: 'Rotten House',
    10006130: 'Decayed Tunnel II', 10006140: 'Decayed Tunnel III',
    10006150: 'Lingering Regret', 10006152: 'Bygone Days',
    10006160: 'Precipice of Darkness', 10006161: 'Dilapidated Tomb',
    10006162: 'Another Sanctuary',
}
HOLLOW_MONSTERS = {
    54: 'Glowshroom', 55: 'Raffle', 56: 'Golden Stirge', 57: 'Aqumander',
    58: 'Echopus', 59: 'Rafflesia', 60: 'Duskmander', 61: 'Myewood',
    62: 'Rotten Mushroom', 63: 'Sporewood', 700003: 'Rotten Mushmom',
}
HOLLOW_QUESTS = {
    10600: "Zelya's Map", 10601: 'Natural Adhesive', 10602: 'A Step Toward Home',
    10603: 'Old Friends', 10604: "Myra's Old Friend", 10607: 'The Roots of Regret',
    10608: "A Fairy's Insight", 10609: 'Tracing the Resonance',
    10610: 'The Yawning Abyss', 10611: 'Welcome to the Hollow',
    10612: 'Stores Before the Frost', 10613: 'Something to Trade',
    10614: 'Supplies for the Hollow', 10615: 'A Night of Lights',
    10621: 'Embers in the Garden', 10622: 'Words Nobody Taught',
    10623: 'Boughs for the Lanterns', 10624: 'Charms Gone Gray',
    10625: 'The Dilapidated Tomb', 10626: 'The Last Lantern',
    10627: 'Missing Pieces', 10628: 'No Questions Asked',
    10629: 'The Girl on the Rooftop', 10630: 'Medicine Money',
    10631: 'Buying Time', 10632: 'Word from the Hideout',
    10633: "A Rival's Gambit", 10634: 'Two Thieves, One Plan',
    10635: 'An Uneasy Truce', 10636: 'Rot at the Door',
    10637: 'A Light Against the Rot', 10638: 'A Ward for the Door',
    10639: 'Glowspore Ward', 10640: 'What Rots Below',
}
ADDITIONAL_QUESTS = {
    10422: 'Planting Trees', 10423: "Shawn the Excavator's Request",
    10424: 'Eliminate Monsters from the Site', 10425: 'Notice from the Excavation Team',
    10426: 'The Smell Below', 10427: "The Settlers' Road", 10428: 'Where the Hero Fell',
    10511: 'The Mushmom Who Woke', 10512: 'Tapping at the Window',
    10513: 'The Chime That Rings Alone', 10514: 'Faces in the Dark',
    10515: 'A Patient Hunger', 10800: 'Bad for Business', 10801: 'Notes on the Board',
    10802: 'The Glowing Charms', 10803: 'The Last Note',
}
EVENT_QUESTS = {
    500012: '[Event] Thanksgiving Pumpkin Pie', 500013: '[Event] Thanksgiving Pumpkin Pie',
    500014: '[Event] Escaped Thanksgiving Turkey', 500015: "[Event] Moon Bunny's Rice Cake",
    500016: '[Event] The New Journey Begins',
}
WEAPONS = {
    1302020: 'Bamboo Sword', 1302021: 'Newspaper Sword', 1302022: 'Beige Umbrella',
    1312011: 'Green Paint Brush', 1322018: 'Blue Flowery Tube', 1322019: 'Red Flowery Tube',
    1332016: 'Sai', 1402008: "Lion's Fang", 1402011: 'Blade of Harmony', 1432009: 'Bamboo Spear',
    1442010: 'Yellow Mop', 1442011: 'White Mop', 1442012: 'Indigo Mop',
    1452013: 'Magical Destruction Bow', 1462006: 'Silver Crow',
}
FURNITURE = {
    3000072: 'Glowspore Tree', 3000073: 'Wild Glowshroom', 3000074: 'Wild Plate Mushrooms',
    3000075: 'Short Wild Vine', 3000076: 'Long Wild Vine', 3000077: 'Leaf Garland',
    3000078: 'Fairy Kitchen Rack', 3000079: 'Mossy Display Shelf', 3000080: 'Fairy Study Books',
    3000081: 'Glowspore Pendant Lights', 3000082: 'Fairy Crystal Ball', 3000083: 'Fairy Tapestry',
    3000084: 'Standing Glowspore Lamp', 3000085: 'Hearthkeeper’s Lantern',
}
RANK_NINE_RECIPES = {
    1002163: 'Emerald Dome', 1002164: 'Dark Dome', 1382005: 'Arc Staff',
    1472015: 'Blood Avarice', 1472016: 'Adamantium Avarice', 1472017: 'Dark Avarice',
    2040808: 'Gloves Accuracy Scroll: Lesser', 2040812: 'Gloves Crit. Rate Scroll: Lesser',
    4003008: 'Processed Cloth', 4003006: 'Processed Leather',
}
HOLLOW_QUEST_ITEMS = {
    4000051: 'Glowing Mushroom Spore', 4000052: 'Raffle Petal', 4000053: 'Golden Stirge Wing',
    4000055: 'Echopus Leg', 4000058: "Giant Tree's Bough", 4000059: 'Decayed Charm',
    4000065: 'Rotten Mushmom Cap', 4031028: "Zelya's Map Fragment", 4031029: 'Ominous Rotten Branch',
    4031088: 'Rotten Root Fragment', 4031093: 'Luminous Magical Resonance',
    4031138: 'Glowspore Lamp', 4031139: 'Winter Supply Bundle', 4031140: "Hearthkeeper's Journal",
    4031141: "Elda's Name-Charm", 4031142: "Elda's Last Message", 4031143: "Alston's Ledger Page",
    4031144: 'Untainted Mushroom Cap', 4031145: "Myen's Ward Scrolls", 4031250: 'Glowspore Ward',
}
EVENT_ITEMS = {
    1003001: 'Moon Bunny Hat', 2020024: "Moon Bunny's Rice Cake", 2020025: "Moon Bunny's Flower Rice Cake",
    2020026: "Moon Bunny's Fullmoon Rice Cake", 2020027: 'Pumpkin Pie', 2020028: 'Roasted Turkey',
    2020029: 'Gravy', 2020030: 'Turkey Leg', 2020031: 'Cranberry Sauce', 2100009: 'Turkey Egg',
    3000053: 'Moon Bunny Statue', 3000086: 'Roast Turkey Platter', 3000087: 'Autumn Leaf Wreath',
    3000088: 'Harvest Feast Table', 3000089: 'Harvest Hay Bale', 3000090: 'Pumpkin Harvest Wagon',
    4000159: 'Primrose Seed', 4001023: "Moon Bunny's Rice Cake", 4031147: 'Pumpkin Piece',
    4031148: 'Pie Flour', 4031149: 'Milk Jug', 4031151: 'Maple Leaf',
}
KPQ_BOX_ID = 2430000
KPQ_BOX_NAME = "Companion's Magic Box"
KPQ_BOX_REWARDS = {2100010: 'Black Sack: Mano', 2100011: 'Black Sack: Stumpy'}

# Published launch inventories matched by the NPC ID, game item ID and name.
# A subsequent shop refresh replaces these rows with the latest saved values.
HOLLOW_SHOPS = (
    (700, 'Luma', 10006002, 'Cave Fairy Store', (
        (2000000, 'Red Potion', 50), (2000001, 'Orange Potion', 150),
        (2000002, 'White Potion', 350), (2000003, 'Blue Potion', 220),
        (2010005, 'Lemon', 150), (2022003, 'Unagi', 1000), (2020009, 'Orange Juice', 540),
        (2020010, 'Grape Juice', 1260), (2030000, 'Return Scroll - Nearest Town', 400),
        (2030007, 'Return Scroll to Forgotten Hollow', 800), (2060000, 'Arrows for Bows', 1),
        (2061000, 'Arrows for Crossbows', 1), (2070000, 'Subi Throwing Stars', 500),
    )),
    (707, 'Nyroth', 10006001, 'Cave Fairy Sanctuary', ((2430001, 'Nyroth’s Mystery Deco Box', 5000),)),
    (709, 'Torin', 10006002, 'Cave Fairy Store', (
        (1040040, 'Red Hwarang Shirt', 12000), (1040041, 'Green Hwarang Shirt', 12000),
        (1050011, 'Black Dragon Robe', 21600), (1051008, 'Yellow Engrit', 21600),
        (1060030, 'Red Martial Arts Pants', 9600), (1060031, 'Brown Martial Arts Pants', 9600),
        (1060032, 'Black Martial Arts Pants', 9600), (1060033, 'White Martial Arts Pants', 9600),
        (1041048, 'Blue Fairy Top', 12000), (1041049, 'Green Fairy Top', 12000),
        (1050012, 'Blue Wizard Robe', 21600), (1050015, 'Green Wizard Robe', 21600),
        (1061042, 'Blue Fairy Skirt', 9600), (1061043, 'Green Fairy Skirt', 9600),
        (1040042, "Green Hunter's Armor", 12000), (1040045, "Dark Hunter's Armor", 12000),
        (1041051, 'Green Huntress Armor', 12000), (1041052, 'Black Huntress Armor', 12000),
        (1060034, "Green Hunter's Pants", 9600), (1060037, "Dark Hunter's Pants", 9600),
        (1061045, 'Green Huntress Pants', 9600), (1061046, 'Black Huntress Pants', 9600),
        (1040047, 'Dark Silver Stealer', 12000), (1040048, 'Red Gold Stealer', 12000),
        (1041053, 'Red Steal', 12000), (1041056, 'Black Steal', 12000),
        (1060040, 'Red / Gold Stealer Pants', 9600), (1060041, 'Silver / Black Stealer Pants', 9600),
        (1061048, 'Red Steal Pants', 9600), (1061051, 'Black Steal Pants', 9600),
    )),
)


def hollow_shop_rows(store):
    for npc_id, name, map_id, map_name, inventory in HOLLOW_SHOPS:
        npc = store.entry('npcs', npc_id)
        place = store.entry('maps', map_id)
        if (not npc or npc[0].name != name or map_id not in npc[1].get('maps', [])
                or not place or place[0].name != map_name):
            continue
        items = store.entries('items', [identity for identity, _, _ in inventory])
        for identity, item_name, price in inventory:
            if identity in items and items[identity][0].name == item_name:
                yield dict(kind='npc', id=npc_id, name=name, map_id=map_id, map_name=map_name,
                           item_id=identity, item_name=item_name, price=price, basis='Published launch prices',
                           source_url=HOLLOW_SHOP_SOURCE)


def apply_november_release(store, state, token):
    """Apply confirmed releases even when the third-party release index is offline."""
    manifest = state.get('manifest')
    if not manifest:
        return
    generation = manifest['data_updated_at']
    evidence_version = [generation, NOVEMBER_EVIDENCE_VERSION]
    if state.get('november_release_generation') == evidence_version:
        return
    if datetime.fromisoformat(generation.replace('Z', '+00:00')) < NOVEMBER_RELEASE:
        return

    sources = (
        ('maps', {**HOLLOW_MAPS, 80003000: 'Primrose Hill'}, NOVEMBER_NOTES),
        ('monsters', {**HOLLOW_MONSTERS, 800019: 'Moon Bunny', 900001: 'Turkey'}, NOVEMBER_NOTES),
        ('quests', {**HOLLOW_QUESTS, **ADDITIONAL_QUESTS}, NOVEMBER_QUESTS),
        ('quests', EVENT_QUESTS, NOVEMBER_NOTES),
        ('items', {**WEAPONS, **FURNITURE, **RANK_NINE_RECIPES, **EVENT_ITEMS}, NOVEMBER_NOTES),
        ('items', HOLLOW_QUEST_ITEMS, NOVEMBER_QUESTS),
    )
    proofs = {}
    reward_quests = {}
    for kind, identities, url in sources:
        for identity, (entry, row) in store.entries(kind, identities).items():
            if entry.name != identities[identity] or row.get('region') == 'Dev':
                continue
            proofs[entry.key] = dict(kind=kind, id=identity, name=entry.name, detail={
                'label': 'November 18 Classic World update', 'url': url, 'released_on': '2026-11-18',
            })
            if kind == 'quests':
                for reward in quest_rewards(row):
                    if reward.get('type') == 'item' and type(reward.get('id')) is int:
                        reward_quests.setdefault(reward['id'], entry.name)

    # The confirmed quest can also establish a reward's release, including
    # alternatives in a random or choice pool.
    for identity, (entry, _) in store.entries('items', reward_quests).items():
        proofs.setdefault(entry.key, dict(kind='items', id=identity, name=entry.name, detail={
            'label': 'Reward from ' + reward_quests[identity], 'url': NOVEMBER_QUESTS,
        }))
    shops = list(hollow_shop_rows(store))
    for row in shops:
        identity = row['item_id']
        proofs.setdefault(('items', identity), dict(kind='items', id=identity, name=row['item_name'], detail={
            'label': 'Sold by ' + row['name'], 'url': row['source_url'],
        }))
    box = store.entry('items', KPQ_BOX_ID)
    box_rows = []
    if box and box[0].name == KPQ_BOX_NAME:
        proofs.setdefault(box[0].key, dict(kind='items', id=KPQ_BOX_ID, name=KPQ_BOX_NAME, detail={
            'label': 'Kerning City Party Quest completion reward', 'url': KPQ_REWARD_REPORTS,
        }))
        for identity, (entry, _) in store.entries('items', KPQ_BOX_REWARDS).items():
            if entry.name != KPQ_BOX_REWARDS[identity]:
                continue
            proofs.setdefault(entry.key, dict(kind='items', id=identity, name=entry.name, detail={
                'label': 'Reported Kerning City Party Quest reward', 'url': KPQ_REWARD_REPORTS,
            }))
            box_rows.append(dict(kind='box', id=KPQ_BOX_ID, name=KPQ_BOX_NAME, item_id=identity,
                                 item_name=entry.name, basis='Player reported', source_url=KPQ_REWARD_REPORTS))
    if proofs:
        store.confirm(list(proofs.values()), 'patch-notes', manifest=manifest, guard=token.check)
        if shops:
            store.save_sources('npc', shops, guard=token.check, supplement=True)
        if box_rows:
            store.save_sources('box', box_rows, guard=token.check, supplement=True)
        with store.connect() as db:
            store.put_meta(db, 'november_release_generation', evidence_version)
            token.check()

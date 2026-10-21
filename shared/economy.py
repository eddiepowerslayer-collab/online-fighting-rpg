"""Marketplace/vendor rules and goods handling on plain character dicts (server-side)."""
from client.professions import CONSUMABLES, MATERIALS

MARKET_FEE_PERCENT = 5
MAX_PRICE = 10 ** 9
MAX_QTY = 9999
SHOP_BASE = {"Health Potion": 30, "Elixir of Swiftness": 70, "Elixir of Power": 90,
             "Iron Ore": 20, "Herb": 15, "Hide": 18, "Cloth": 18, "Gem": 80}


class EconomyError(Exception):
    """A rejected trade. The message is safe to show to the player."""


def market_fee(total: int) -> int:
    return total * MARKET_FEE_PERCENT // 100


def shop_price(name: str, level: int) -> int:
    return SHOP_BASE[name] * (1 + level // 5)


ITEM_PRICE_PER_POINT = 40      # NPC price per stat point of an item
BUYBACK_PERCENT = 30           # what NPC vendors pay when you sell an item back
VENDORS = ("Blacksmith", "Armorer", "Jeweler", "Alchemist", "General Store", "Rare Dealer")
VENDOR_BLURB = {"Blacksmith": "Weapons", "Armorer": "Armor", "Jeweler": "Accessories",
                "Alchemist": "Potions & elixirs", "General Store": "Crafting materials",
                "Rare Dealer": "Rare & epic equipment"}


def item_points(item: dict) -> int:
    return sum(v for _, v in item["bonuses"])


def vendor_sell_price(item: dict) -> int:
    """Buyback price for an item sold to an NPC vendor."""
    return max(1, item_points(item) * ITEM_PRICE_PER_POINT * BUYBACK_PERCENT // 100)


def vendor_catalog(vendor: str, level: int) -> list:
    """Deterministic stock for a vendor at a character level. Entries:
    {"kind": item|material|potion, "name", "price", "item": item-dict or None}.
    Gear power and grade scale with level; the server re-derives this to validate purchases."""
    from client.grades import grade_for_level
    from client.items import DROP_NAMES, TEMPLATES, build_item, item_to_dict
    if vendor not in VENDORS:
        raise EconomyError("Unknown vendor.")
    power, grade = 1 + level // 10, grade_for_level(level).short
    out = []

    def gear(names, rarities, premium=1):
        for name in names:
            for rarity in rarities:
                it = item_to_dict(build_item(name, TEMPLATES[name][0], TEMPLATES[name][1], rarity, power, grade))
                out.append({"kind": "item", "name": name, "item": it,
                            "price": item_points(it) * ITEM_PRICE_PER_POINT * premium})

    slot_of = {"Blacksmith": "weapon", "Armorer": "armor", "Jeweler": "trinket"}
    if vendor in slot_of:
        gear([n for n in DROP_NAMES if TEMPLATES[n][0] == slot_of[vendor]], ("Common", "Rare"))
    elif vendor == "Rare Dealer":
        gear(DROP_NAMES, ("Epic",), premium=2)
    elif vendor == "Alchemist":
        out += [{"kind": "potion", "name": n, "item": None, "price": shop_price(n, level)} for n in CONSUMABLES]
    else:
        out += [{"kind": "material", "name": n, "item": None, "price": shop_price(n, level)} for n in MATERIALS]
    return out


def _check_int(v, lo, hi, what):
    if not isinstance(v, int) or isinstance(v, bool) or not lo <= v <= hi:
        raise EconomyError(f"Invalid {what}.")
    return v


def check_kind_name(kind, name):
    if kind == "material" and name not in MATERIALS:
        raise EconomyError("Unknown material.")
    if kind == "potion" and name not in CONSUMABLES:
        raise EconomyError("Unknown potion.")
    if kind not in ("item", "material", "potion"):
        raise EconomyError("Bad listing type.")


def take_goods(data, kind, name, qty, item_index=None):
    """Remove goods from a character dict; returns the listing payload."""
    check_kind_name(kind, name)
    if kind == "item":
        inv = data["inventory"]
        if not isinstance(item_index, int) or not 0 <= item_index < len(inv) or inv[item_index]["name"] != name:
            raise EconomyError("That item is no longer in your bag.")
        return inv.pop(item_index)
    bucket = data["materials"] if kind == "material" else data["consumables"]
    _check_int(qty, 1, MAX_QTY, "quantity")
    if bucket.get(name, 0) < qty:
        raise EconomyError(f"You don't have {qty} {name}.")
    bucket[name] -= qty
    return {"name": name}


def give_goods(data, kind, name, qty, payload):
    if kind == "item":
        data["inventory"].append(payload)
    else:
        bucket = data["materials"] if kind == "material" else data["consumables"]
        bucket[name] = bucket.get(name, 0) + qty


def vendor_sell(data, item_index) -> int:
    inv = data["inventory"]
    if not isinstance(item_index, int) or not 0 <= item_index < len(inv):
        raise EconomyError("That item is no longer in your bag.")
    price = vendor_sell_price(inv.pop(item_index))
    data["gold"] += price
    return price


def shop_buy(data, vendor, index, qty) -> int:
    """Buy catalog entry `index` from `vendor`. Prices come from the server's own catalog,
    never from the client. Returns the gold spent."""
    catalog = vendor_catalog(vendor, data["level"])
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(catalog):
        raise EconomyError("That item isn't for sale.")
    entry = catalog[index]
    qty = 1 if entry["kind"] == "item" else _check_int(qty, 1, 999, "quantity")
    cost = entry["price"] * qty
    if data["gold"] < cost:
        raise EconomyError(f"Not enough gold (need {cost}).")
    if entry["kind"] == "item" and len(data["inventory"]) >= 500:
        raise EconomyError("Your bag is full.")
    data["gold"] -= cost
    if entry["kind"] == "item":
        data["inventory"].append(dict(entry["item"]))
    else:
        bucket = data["materials"] if entry["kind"] == "material" else data["consumables"]
        bucket[entry["name"]] = bucket.get(entry["name"], 0) + qty
    return cost

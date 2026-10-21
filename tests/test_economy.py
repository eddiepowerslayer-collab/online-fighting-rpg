"""NPC vendors: catalogs, purchases, buyback, and rejection of bad requests."""
import pytest

from client.character import Character
from client.items import make_item, item_to_dict
from shared import economy
from shared.economy import EconomyError


def data_for(level=30, gold=100_000):
    ch = Character()
    ch.add_levels(level - 1)
    ch.gold = gold
    return ch.to_dict()


def test_every_vendor_sells_its_category_and_is_deterministic():
    cats = {v: economy.vendor_catalog(v, 30) for v in economy.VENDORS}
    assert all(cats[v] == economy.vendor_catalog(v, 30) for v in economy.VENDORS)
    assert {e["item"]["slot"] for e in cats["Blacksmith"]} == {"weapon"}
    assert {e["item"]["slot"] for e in cats["Armorer"]} == {"armor"}
    assert {e["item"]["slot"] for e in cats["Jeweler"]} == {"trinket"}
    assert {e["kind"] for e in cats["Alchemist"]} == {"potion"}
    assert {e["kind"] for e in cats["General Store"]} == {"material"}
    assert {e["item"]["rarity"] for e in cats["Rare Dealer"]} == {"Epic"}
    assert all(e["price"] > 0 for c in cats.values() for e in c)


def test_stock_scales_with_level():
    low = economy.vendor_catalog("Blacksmith", 1)[0]
    high = economy.vendor_catalog("Blacksmith", 200)[0]
    assert high["price"] > 10 * low["price"] and high["item"]["grade"] == "C"


def test_buying_gear_updates_gold_and_inventory():
    d = data_for()
    e = economy.vendor_catalog("Blacksmith", 30)[0]
    cost = economy.shop_buy(d, "Blacksmith", 0, 1)
    assert cost == e["price"] and d["gold"] == 100_000 - cost
    assert d["inventory"][-1] == e["item"]


def test_buying_goods_with_quantity():
    d = data_for()
    idx = [e["name"] for e in economy.vendor_catalog("General Store", 30)].index("Gem")
    price = economy.vendor_catalog("General Store", 30)[idx]["price"]
    assert economy.shop_buy(d, "General Store", idx, 5) == price * 5
    assert d["materials"]["Gem"] == 5 and d["gold"] == 100_000 - price * 5


@pytest.mark.parametrize("vendor,index,qty", [("Nobody", 0, 1), ("Blacksmith", -1, 1), ("Blacksmith", 999, 1),
                                              ("Blacksmith", True, 1), ("General Store", 0, 0), ("General Store", 0, -5),
                                              ("General Store", 0, 10_000), ("General Store", 0, 1.5)])
def test_invalid_purchases_change_nothing(vendor, index, qty):
    d = data_for()
    before = dict(d, inventory=list(d["inventory"]), materials=dict(d["materials"]))
    with pytest.raises(EconomyError):
        economy.shop_buy(d, vendor, index, qty)
    assert d["gold"] == before["gold"] and d["inventory"] == before["inventory"] and d["materials"] == before["materials"]


def test_cannot_afford_means_no_purchase_and_never_negative_gold():
    d = data_for(gold=5)
    with pytest.raises(EconomyError, match="Not enough gold"):
        economy.shop_buy(d, "Rare Dealer", 0, 1)
    assert d["gold"] == 5 and d["inventory"] == []


def test_selling_back_uses_buyback_rate_and_removes_item():
    d = data_for(gold=0)
    d["inventory"].append(item_to_dict(make_item("Iron Sword", "Rare")))   # +4 STR
    price = economy.vendor_sell(d, 0)
    assert price == 4 * economy.ITEM_PRICE_PER_POINT * economy.BUYBACK_PERCENT // 100 == 48
    assert d["gold"] == 48 and d["inventory"] == []
    for bad in (0, -1, 5, "0", None, True):
        with pytest.raises(EconomyError):
            economy.vendor_sell(d, bad)


def test_buyback_is_always_less_than_purchase_price():
    for v in ("Blacksmith", "Armorer", "Jeweler", "Rare Dealer"):
        for e in economy.vendor_catalog(v, 50):
            assert economy.vendor_sell_price(e["item"]) < e["price"]

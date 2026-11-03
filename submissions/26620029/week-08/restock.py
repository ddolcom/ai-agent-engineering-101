"""Round 3 restock hook (ddolcom: stock what my customers buy, cheap first, many categories).

    python restock.py --state .market

The kit runs this every 60 s in Round 3 and buys what the last printed line asks for: {"buy": [{"sku", "qty"}, ...]}.
Buyers only see a shop for an order if it stocks that order's category, so the shop keeps one unit in as many
cheap categories as it can, refills what sold first, keeps two where it sold twice, and stops buying food that
rotted unsold. Memory: restock_memory.json in the agent folder (what we held, what sold, what expired).

Customers first (customers.py): buyers who settled with my shop are remembered from the public ledger, with
what they buy anywhere; their favourite categories are stocked before anything else, with more units.
Cheap first: until the shop has CHEAP_PHASE sales, only categories and SKUs up to CHEAP_MAX_LIST.
Supply opens every 20 minutes for 3 minutes; outside a window the run only learns and buys nothing, because
the kit would wait 90 s per line and could miss the window itself.
"""
import argparse
import json
import time
from pathlib import Path

import customers

CASH_FLOOR = 1_500_000      # never spend below this (bankruptcy line 500,000, and room to refill what sells)
MAX_LIST = 300_000          # skip categories whose median list price is above this: one unsold unit costs too much
MIN_SHELF_HOURS = 48        # food that lasts a day spoils before most buyers ask for it
COST_GUESS = 0.75           # a unit costs at most 75% of its list price (grade A); plan with the worst case
MAX_LINES = 10              # the kit buys at most 10 lines per run
CHEAP_PHASE = 20            # until the shop has sold this many units, stock cheap SKUs only
CHEAP_MAX_LIST = 50_000     # "cheap": list price up to this
CHEAP_SHARE = 0.6           # cheapest SKU at or above this share of the category median (orders accept 0.5-1.5x)
FOOD_MAX_QTY = 2            # food rots: never more than this per category
LINE_SHARE = 0.1            # one line spends at most this share of the balance (fewer units of dear SKUs)
EARLY = 60                  # buy when the window opens within this many seconds (the kit runs us every 60 s)
MEMORY = Path("restock_memory.json")


def load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def learn(mem, units, now):
    """Units we held last run and no longer hold either sold or were thrown away at their date."""
    held = {u["unit"]: u for u in units}
    for uid, old in mem["held"].items():
        if uid in held:
            continue
        gone = "expired" if old.get("expires_at") and old["expires_at"] <= now else "sold"
        cat = mem.setdefault(gone, {})
        cat[old["category"]] = cat.get(old["category"], 0) + 1
    mem["held"] = {uid: {"category": u["category"], "expires_at": u.get("expires_at")} for uid, u in held.items()}


def fav_qty(w):
    return 3 if w >= 3 else 2 if w >= 1 else 1


def pick_sku(skus, median, best, cheap):
    """The SKU to stock: the one the market buys most if known, else (cheap phase) the cheapest an order of
    this category likely accepts, else the one closest to the median."""
    by_sku = {c["sku"]: c for c in skus}
    if best in by_sku and (not cheap or by_sku[best]["list_price"] <= CHEAP_MAX_LIST):
        return by_sku[best]
    if cheap:
        ok = [c for c in skus if CHEAP_SHARE * median <= c["list_price"] <= CHEAP_MAX_LIST]
        if ok:
            return min(ok, key=lambda c: c["list_price"])
    return min(skus, key=lambda c: abs(c["list_price"] - median))


def plan(inv, catalog, demand, mem, cu=None):
    sold, expired = mem.get("sold", {}), mem.get("expired", {})
    cu = cu or {}
    fav = customers.favourites(cu)
    cheap = sum(sold.values()) < CHEAP_PHASE
    max_list = CHEAP_MAX_LIST if cheap else MAX_LIST
    stock = {}
    for u in inv["units"]:
        if u.get("grade") != "expired":
            stock[u["category"]] = stock.get(u["category"], 0) + 1
    by_cat = {}
    for sku, c in catalog.items():
        by_cat.setdefault(c["category"], []).append(c)

    cats = []
    for d in demand:
        cat = d["category"]
        if d["median_price"] > max_list or cat not in by_cat:
            continue
        if d["kind"] == "food" and (d.get("shelf_hours") or 0) < MIN_SHELF_HOURS:
            continue
        if expired.get(cat, 0) >= 2 and not sold.get(cat):
            continue                                    # rotted twice and never sold: stop
        want = max(fav_qty(fav.get(cat, 0)), 2 if sold.get(cat, 0) >= 2 else 1)
        if d["kind"] == "food":
            want = min(want, FOOD_MAX_QTY)
        if stock.get(cat, 0) < want:
            cats.append((-fav.get(cat, 0), -sold.get(cat, 0), d["median_price"], cat, want - stock.get(cat, 0)))
    cats.sort()                                         # customers' favourites, then most sold, then cheapest

    spend = (inv.get("balance") or 0) - CASH_FLOOR
    buy = []
    for _, _, median, cat, qty in cats:
        if len(buy) >= MAX_LINES:
            break
        sku = pick_sku(by_cat[cat], median, customers.best_sku(cu, cat), cheap)
        qty = max(1, min(qty, int(LINE_SHARE * inv["balance"] / (sku["list_price"] * COST_GUESS))))
        cost = sku["list_price"] * COST_GUESS * qty
        if cost > spend:
            continue
        spend -= cost
        buy.append({"sku": sku["sku"], "qty": qty})
    return buy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=".market")
    state = Path(ap.parse_args().state)
    inv = load(state / "inventory.json", {})
    if inv.get("round", 0) < 3 or inv.get("balance") is None:
        print(json.dumps({"buy": []}))
        return
    now = time.time()
    mem = load(MEMORY, {"held": {}, "sold": {}, "expired": {}})
    learn(mem, inv["units"], now)
    catalog = load(state / "catalog.json", {})
    cu = customers.update(mem, catalog)
    window = inv.get("restock") or {}
    if window.get("open") or (window.get("opens_at") or 0) - now <= EARLY:
        buy = plan(inv, catalog, load(state / "demand.json", []), mem, cu)
    else:
        buy = []
    mem["last_run"] = {"t": int(now), "balance": inv["balance"], "buy": buy}
    MEMORY.write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")
    top = sorted(customers.favourites(cu).items(), key=lambda x: -x[1])[:3]
    print(f"restock: balance {inv['balance']}, {len(inv['units'])} units, {len(cu.get('customers', {}))} customers, "
          f"favourites {top}, window {'open' if window.get('open') else 'opens in %d s' % ((window.get('opens_at') or now) - now)}, "
          f"buying {len(buy)} lines")
    print(json.dumps({"buy": buy}, ensure_ascii=False))


if __name__ == "__main__":
    main()

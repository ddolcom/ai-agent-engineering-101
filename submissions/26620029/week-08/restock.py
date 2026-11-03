"""Round 3 restock hook (ddolcom, strategy 5: be in as many categories as the cash allows).

    python restock.py --state .market

The kit runs this every 60 s in Round 3 and buys what the last printed line asks for: {"buy": [{"sku", "qty"}, ...]}.
Buyers only see a shop for an order if it stocks that order's category, so the shop keeps one unit in as many
cheap categories as it can, refills what sold first, keeps two where it sold twice, and stops buying food that
rotted unsold. Memory: restock_memory.json in the agent folder (what we held, what sold, what expired).
"""
import argparse
import json
import time
from pathlib import Path

CASH_FLOOR = 1_500_000      # never spend below this (bankruptcy line 500,000, and room to refill what sells)
MAX_LIST = 300_000          # skip categories whose median list price is above this: one unsold unit costs too much
MIN_SHELF_HOURS = 48        # food that lasts a day spoils before most buyers ask for it
COST_GUESS = 0.75           # a unit costs at most 75% of its list price (grade A); plan with the worst case
MAX_LINES = 10              # the kit buys at most 10 lines per run
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


def plan(inv, catalog, demand, mem):
    sold, expired = mem.get("sold", {}), mem.get("expired", {})
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
        if d["median_price"] > MAX_LIST or cat not in by_cat:
            continue
        if d["kind"] == "food" and (d.get("shelf_hours") or 0) < MIN_SHELF_HOURS:
            continue
        if expired.get(cat, 0) >= 2 and not sold.get(cat):
            continue                                    # rotted twice and never sold: stop
        want = 2 if sold.get(cat, 0) >= 2 else 1
        if stock.get(cat, 0) < want:
            cats.append((-sold.get(cat, 0), d["median_price"], cat, want - stock.get(cat, 0), d["median_price"]))
    cats.sort()                                         # most sold first, then the cheapest untried

    spend = (inv.get("balance") or 0) - CASH_FLOOR
    buy = []
    for _, _, cat, qty, median in cats:
        if len(buy) >= MAX_LINES:
            break
        sku = min(by_cat[cat], key=lambda c: abs(c["list_price"] - median))    # the SKU most orders accept
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
    mem = load(MEMORY, {"held": {}, "sold": {}, "expired": {}})
    learn(mem, inv["units"], time.time())
    buy = plan(inv, load(state / "catalog.json", {}), load(state / "demand.json", []), mem)
    mem["last_run"] = {"t": int(time.time()), "balance": inv["balance"], "buy": buy}
    MEMORY.write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"restock: balance {inv['balance']}, {len(inv['units'])} units, buying {len(buy)} lines")
    print(json.dumps({"buy": buy}, ensure_ascii=False))


if __name__ == "__main__":
    main()

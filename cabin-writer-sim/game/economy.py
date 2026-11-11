"""Economy: the writer's ledger, the General Store's catalogue, and the
optional real-world payment hookup.

Real money is OFF by default. The `ApiPaymentProvider` only activates when
ALL of the following are true:
  * environment variable CABIN_PAYMENT_ENDPOINT is set (https URL)
  * environment variable CABIN_PAYMENT_KEY is set
  * the game was started with --enable-real-payments
Until then every top-up flows through the mock provider — pretend money.
"""

import json
import os
import time
import urllib.request

LEDGER_FILE = "ledger.jsonl"

# General Store catalogue: (cost in credits, effect applied on purchase)
STORE_CATALOG = {
    "groceries":  {"cost": 18.0, "kind": "food",     "amount": 4,
                   "desc": "four meals' worth of bread, beans, and tea"},
    "bread":      {"cost": 5.0,  "kind": "food",     "amount": 1,
                   "desc": "a loaf, still faintly warm"},
    "paper":      {"cost": 8.0,  "kind": "supply",   "amount": 12,
                   "desc": "twelve sheets of good writing paper"},
    "lamp_oil":   {"cost": 6.0,  "kind": "supply",   "amount": 3,
                   "desc": "three bottles of oil for the long nights"},
    "coffee":     {"cost": 7.0,  "kind": "supply",   "amount": 3,
                   "desc": "a tin of bitter coffee"},
    "armchair":   {"cost": 60.0, "kind": "furniture", "amount": 1,
                   "desc": "a worn leather armchair — comfort while drafting"},
    "stove_upgrade": {"cost": 90.0, "kind": "furniture", "amount": 1,
                   "desc": "a better stove; the cabin holds heat now"},
    "typewriter": {"cost": 120.0, "kind": "furniture", "amount": 1,
                   "desc": "a secondhand typewriter — faster, louder words"},
    "gramophone": {"cost": 85.0, "kind": "furniture", "amount": 1,
                   "desc": "a gramophone and three records; the rain gets company"},
}


class Ledger:
    def __init__(self, out_dir):
        self.path = os.path.join(out_dir, LEDGER_FILE)
        os.makedirs(out_dir, exist_ok=True)

    def record(self, entry):
        entry = dict(entry)
        entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")


class MockPaymentProvider:
    """Default provider. Prints a receipt; no real money moves."""
    name = "mock"
    real_money = False

    def top_up(self, amount, currency, memo):
        return {
            "ok": True, "provider": self.name, "real_money": False,
            "amount": amount, "currency": currency, "memo": memo,
            "note": "Mock top-up — no real charge was made.",
        }


class ApiPaymentProvider:
    """Posts a purchase intent to a user-configured endpoint.

    Expected contract: POST {endpoint}/charge  JSON {amount, currency, memo}
    -> 200 + JSON {"ok": true}. Anything else is a refusal. The endpoint is
    yours; the game never stores card data and never charges unilaterally —
    every call originates from an explicit user command ("top up 20").
    """
    name = "api"
    real_money = True

    def __init__(self):
        self.endpoint = os.environ.get("CABIN_PAYMENT_ENDPOINT", "").rstrip("/")
        self.key = os.environ.get("CABIN_PAYMENT_KEY", "")
        if not (self.endpoint.startswith("https://") and self.key):
            raise RuntimeError(
                "Real payments require CABIN_PAYMENT_ENDPOINT (https) and "
                "CABIN_PAYMENT_KEY environment variables.")

    def top_up(self, amount, currency, memo):
        payload = json.dumps({
            "amount": amount, "currency": currency, "memo": memo,
        }).encode()
        req = urllib.request.Request(
            self.endpoint + "/charge", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                if resp.status == 200 and data.get("ok"):
                    return {"ok": True, "provider": self.name,
                            "real_money": True, "amount": amount,
                            "currency": currency, "memo": memo,
                            "note": "Real charge accepted by provider."}
                return {"ok": False, "provider": self.name,
                        "note": f"Provider refused: {data}"}
        except Exception as exc:  # network/HTTP failure — never charge twice
            return {"ok": False, "provider": self.name,
                    "note": f"Payment failed safely: {exc}"}


def make_provider(enable_real):
    if enable_real:
        try:
            return ApiPaymentProvider()
        except RuntimeError as exc:
            print(f"[economy] {exc}  Falling back to mock provider.")
    return MockPaymentProvider()


class Wallet:
    """The writer's purse. Credits are the game's money; the provider turns
    real currency into credits at 1 unit = 10 credits."""

    def __init__(self, provider, ledger, rate=10.0):
        self.provider = provider
        self.ledger = ledger
        self.rate = rate

    def top_up(self, amount, currency="USD", memo="reader's patronage"):
        result = self.provider.top_up(amount, currency, memo)
        self.ledger.record({"type": "top_up", **result})
        if result.get("ok"):
            return amount * self.rate, result
        return 0.0, result

    def spend(self, body, item_key):
        item = STORE_CATALOG.get(item_key)
        if not item:
            return False, f"The store does not stock '{item_key}'."
        if body.money < item["cost"]:
            return False, (f"Not enough credits for {item_key} "
                           f"({item['cost']:.0f}cr needed, "
                           f"{body.money:.0f}cr in hand).")
        body.money -= item["cost"]
        if item["kind"] == "food":
            body.food += item["amount"]
        elif item["kind"] == "supply":
            key = {"paper": "paper", "lamp_oil": "lamp_oil",
                   "coffee": "coffee"}[item_key]
            body.supplies[key] = body.supplies.get(key, 0) + item["amount"]
        else:
            body.furniture[item_key] = item["amount"]
        self.ledger.record({"type": "purchase", "item": item_key,
                            "cost": item["cost"]})
        return True, f"Bought {item_key}: {item['desc']}."

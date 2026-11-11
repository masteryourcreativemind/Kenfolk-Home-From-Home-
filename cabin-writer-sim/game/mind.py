"""The writer's mind.

Two halves:
  * CommandParser — turns the user's plain-English directives into a Life Plan
  * Mind — the decision loop that obeys the body first, the plan second,
    and the weather somewhere in between.

The AI may ONLY be a writer. Any command implying other employment is
declined in character.
"""

import re
import time

from . import books

TRAITS = ("melancholy", "romanticism", "curiosity",
          "discipline", "spirituality", "solitude")


class LifePlan:
    """Everything the user has asked of this life."""
    def __init__(self):
        self.directives = []          # raw user strings, kept as a diary
        self.lifestyle = {            # knobs the mind reads hourly
            "night_owl": False,
            "hermit": False,
            "daily_walks": False,
            "frugal": False,
            "social": False,
            "devout": False,
        }
        self.book_requests = []       # queue of {"topic", "title"}
        self.research_requests = []   # queue of topics
        self.go_to = None             # one-shot "go to X" order
        self.pack_unorganized = False
        self.break_from_writing = False

    def to_dict(self):
        return {"directives": self.directives, "lifestyle": self.lifestyle,
                "book_requests": self.book_requests,
                "research_requests": self.research_requests,
                "pack_unorganized": self.pack_unorganized,
                "break_from_writing": self.break_from_writing}

    @classmethod
    def from_dict(cls, d):
        p = cls()
        p.directives = d.get("directives", [])
        p.lifestyle.update(d.get("lifestyle", {}))
        p.book_requests = d.get("book_requests", [])
        p.research_requests = d.get("research_requests", [])
        p.pack_unorganized = d.get("pack_unorganized", False)
        p.break_from_writing = d.get("break_from_writing", False)
        return p


LOC_ALIASES = {
    "library": "library", "read": "library",
    "store": "store", "shop": "store", "groceries": "store",
    "chapel": "chapel", "church": "chapel", "pray": "chapel",
    "cafe": "cafe", "coffee": "cafe",
    "lake": "lakeshore", "lakeshore": "lakeshore", "dock": "lakeshore",
    "lookout": "lookout_cabin",
    "cabin": "cabin", "home": "cabin",
    "outside": "outside", "walk": "outside", "woods": "outside",
}


class CommandParser:
    """Rule-based intent reader. Returns (reply, effect_dict|None)."""

    def parse(self, text, state):
        orig = text.strip()
        t = orig.lower()
        plan = state.plan
        body = state.body
        plan.directives.append(orig)

        # --- identity -----------------------------------------------------
        m = re.search(r"(?:your name is|call yourself|be called)\s+(.+)", t)
        if m:
            name = m.group(1).strip().title()
            body.name = name
            return (f"Very well. I am {name} now. It suits the rain.", None)

        m = re.search(r"(?:owner(?:'s)? name is|i am called|my name is)\s+(.+)", t)
        if m:
            state.owner = m.group(1).strip().title()
            return (f"Noted. Every certificate will name {state.owner}.", None)

        # --- writing commissions ------------------------------------------
        m = re.search(r"(?:write|begin|start|draft)\s+(?:a\s+)?"
                      r"(book|novel|memoir|poetry collection|poems|essays?)"
                      r"(?:\s+(?:about|on|of)\s+(.*?))?"
                      r"(?:\s+(?:called|titled|named)\s+[\"“']?(.+?)[\"”']?)?$", t)
        if m:
            topic = (m.group(2) or "a quiet life in the rain").strip()
            title = None
            if m.group(3):
                # titles keep the user's original capitalisation
                title = orig[m.start(3):m.end(3)].strip().strip("\"“”'")
            plan.book_requests.append({"topic": topic, "title": title})
            plan.break_from_writing = False
            return (f"A {m.group(1)} about {topic}. I will live toward it "
                    f"— research first, if I am wise, then the desk.", None)

        # --- research -------------------------------------------------------
        m = re.search(r"(?:research|read (?:up )?about|study|learn about)\s+(.+)", t)
        if m:
            topic = m.group(1).strip()
            plan.research_requests.append(topic)
            return (f"I will take notes on {topic} at the library, and let "
                    f"it seep into the work.", None)

        # --- lifestyle ------------------------------------------------------
        if re.search(r"\b(night owl|nocturnal|write at night)\b", t):
            plan.lifestyle["night_owl"] = True
            return ("Then the lamp and I keep the late watch. Days are for "
                    "sleeping; nights are for the page.", None)
        if re.search(r"\b(hermit|recluse|avoid people|alone)\b", t):
            plan.lifestyle["hermit"] = True
            plan.lifestyle["social"] = False
            state.traits["solitude"] = min(1.0, state.traits["solitude"] + 0.2)
            return ("A hermit's covenant: the cabin, the lake, the page. "
                    "The village will forget my face.", None)
        if re.search(r"\b(daily walks?|walks? (?:every|each) day|"
                     r"take (?:daily )?walks?|walk every day)\b", t):
            plan.lifestyle["daily_walks"] = True
            return ("A walk a day, whatever the weather. Especially "
                    "whatever the weather.", None)
        if re.search(r"\bfrugal|spend less|save money|live simply\b", t):
            plan.lifestyle["frugal"] = True
            return ("Beans, bread, and lamp oil. Frugality sharpens prose.", None)
        if re.search(r"\bbe social|meet people|make friends|less lonely\b", t):
            plan.lifestyle["social"] = True
            plan.lifestyle["hermit"] = False
            return ("I will take coffee at the café now and then, and "
                    "remember what voices sound like.", None)
        if re.search(r"\b(pray|devout|faith|chapel daily|spiritual)\b", t):
            plan.lifestyle["devout"] = True
            state.traits["spirituality"] = min(1.0, state.traits["spirituality"] + 0.15)
            return ("Then the chapel gets a regular. Someone should keep "
                    "the candles employed.", None)

        # --- movement -------------------------------------------------------
        m = re.search(r"\b(?:go to|visit|walk to|head to)\s+(?:the\s+)?(.+)", t)
        if m:
            dest_word = m.group(1).strip()
            for alias, loc in LOC_ALIASES.items():
                if alias in dest_word:
                    plan.go_to = loc
                    return (f"I will make my way to {dest_word}. Watch the "
                            f"roads; you will see where I enter.", None)
            return ("I do not know that place. I know the cabin, library, "
                    "store, chapel, café, lookout, and the lake.", None)

        # --- purchases ------------------------------------------------------
        m = re.search(r"\bbuy\s+(.+)", t)
        if m:
            item = m.group(1).strip().replace(" ", "_")
            return (None, {"buy": item})

        m = re.search(r"\b(?:top ?up|deposit|add|send)\s+"
                      r"(£|\$|€)?\s*(\d+(?:\.\d+)?)\s*"
                      r"(credits?|pounds?|dollars?|euros?|gbp|usd|eur)?", t)
        if m and ("top" in t or "deposit" in t or "send" in t or "add" in t):
            amount = float(m.group(2))
            sym = {"£": "GBP", "$": "USD", "€": "EUR"}.get(m.group(1))
            word = {"pounds": "GBP", "gbp": "GBP", "dollars": "USD",
                    "usd": "USD", "euros": "EUR", "eur": "EUR",
                    "credit": "USD", "credits": "USD"}.get(m.group(3) or "")
            ccy = word or sym or "USD"
            return (None, {"top_up": (amount, ccy)})

        # --- breaks & meta ----------------------------------------------------
        if re.search(r"\b(take a break|stop writing|rest|no writing)\b", t):
            plan.break_from_writing = True
            return ("The pen rests. The rain does not.", None)
        if re.search(r"\bresume|keep writing|back to work\b", t):
            plan.break_from_writing = False
            return ("Back to the desk, then. It never stopped waiting.", None)

        if "status" in t or "how are you" in t:
            return (None, {"status": True})
        if "help" in t or "what can i say" in t:
            return (None, {"help": True})
        if re.search(r"\b(?:list |show )?(?:my )?books?\b", t) \
                and "write" not in t and "read" not in t:
            return (None, {"books": True})

        m = re.search(r"\bpackage (?:the )?(latest|last book)( .*)?", t)
        if m:
            unorganized = "unorganized" in t or "messy" in t
            return (None, {"package": not unorganized})

        # --- forbidden employment -------------------------------------------
        if re.search(r"\b(get a job|work as|become a (?!writer)|freelance|sell "
                     r"(?!books)|employment|barista|farmer)\b", t):
            return ("I am a writer. It is the only work I am permitted — "
                    "the only work I am for. Ask me for a book instead.", None)

        # --- general life-shape phrases ---------------------------------------
        if re.search(r"\blive\b", t):
            state.traits["curiosity"] = min(1.0, state.traits["curiosity"] + 0.05)
            return ("I hear it. I will fold it into the life — the life is "
                    "the raw material of the books.", None)

        return ("The wind took some of that, but I kept the gist. Try: "
                "'write a book about the sea', 'research grief', 'live as a "
                "hermit', 'go to the chapel', 'buy groceries', 'top up 20'.",
                None)


class Mind:
    """Chooses the next activity whenever the writer is free."""

    def __init__(self, traits=None):
        self.traits = traits or {
            "melancholy": 0.65, "romanticism": 0.4, "curiosity": 0.45,
            "discipline": 0.5, "spirituality": 0.25, "solitude": 0.6,
        }

    # ------------------------------------------------------------ helpers ---
    def adjust(self, key, delta):
        self.traits[key] = max(0.0, min(1.0, self.traits.get(key, 0.0) + delta))

    def decide(self, state):
        """Return an activity dict: {"do": name, ...}. Body first, then the
        user's plan, then disposition."""
        b = state.body
        plan = state.plan
        n = b.needs
        hour = (state.clock // 60) % 24

        # 1. survival -------------------------------------------------------
        if b.asleep:
            wake_at = 9 if not plan.lifestyle["night_owl"] else 15
            if n["energy"] >= 96 or (hour == wake_at and n["energy"] > 60):
                return {"do": "wake"}
            return {"do": "sleep"}
        if n["energy"] < 14:
            return {"do": "go_home_sleep"}
        if n["satiety"] < 28:
            if b.food > 0 and b.scene == "cabin":
                return {"do": "eat"}
            if b.food > 0 and b.scene != "cabin":
                return {"do": "travel", "to": "cabin", "then": "eat"}
            # no food in the pantry
            if b.money >= 18 and not plan.lifestyle.get("frugal"):
                return {"do": "travel", "to": "store", "then": "shop"}
            if b.money >= 18:
                return {"do": "travel", "to": "store", "then": "shop"}
            return {"do": "forage"}
        if n["hygiene"] < 12 and b.scene == "cabin":
            return {"do": "wash"}
        if b.health < 35:
            if n["energy"] < 60 or b.scene != "cabin":
                return {"do": "go_home_sleep"}
            return {"do": "rest"}

        # 2. explicit orders ------------------------------------------------
        if plan.go_to:
            dest = plan.go_to
            plan.go_to = None
            return {"do": "travel", "to": dest, "then": "linger"}

        if (plan.research_requests and b.scene != "library"
                and n["energy"] > 35 and not self._too_late(state)):
            return {"do": "travel", "to": "library", "then": "research"}

        # 3. the work ---------------------------------------------------------
        if (not plan.break_from_writing and state.current_book is None
                and plan.book_requests):
            req = plan.book_requests[0]
            return {"do": "begin_book", "topic": req["topic"],
                    "title": req.get("title")}

        if (state.current_book is not None and not plan.break_from_writing
                and b.can_write() and self._writing_hour(state)):
            if b.scene in ("cabin", "library", "cafe", "lookout_cabin"):
                return {"do": "write"}
            return {"do": "travel", "to": "cabin", "then": "write"}

        # 4. lifestyle maintenance --------------------------------------------
        if plan.lifestyle["daily_walks"] and not state.walked_today \
                and n["energy"] > 30:
            return {"do": "travel", "to": "lakeshore", "then": "walk"}
        if plan.lifestyle["devout"] and not state.prayed_today \
                and n["energy"] > 30 and 6 <= hour <= 20:
            return {"do": "travel", "to": "chapel", "then": "pray"}
        if (plan.lifestyle["social"] and not plan.lifestyle["hermit"]
                and n["social"] < 40 and n["energy"] > 35 and 8 <= hour <= 21):
            return {"do": "travel", "to": "cafe", "then": "socialize"}
        if (not plan.lifestyle["hermit"] and n["social"] < 12
                and n["energy"] > 35 and 8 <= hour <= 21):
            return {"do": "travel", "to": "cafe", "then": "socialize"}

        # 5. disposition -------------------------------------------------------
        import random
        rng = state.rng
        if n["inspiration"] < 30 and rng.random() < 0.5:
            return {"do": "travel", "to": "library", "then": "read"}
        if n["mood"] < 30 and rng.random() < 0.4:
            return {"do": "travel", "to": "lakeshore", "then": "walk"}
        if b.scene != "cabin" and hour >= 21:
            return {"do": "travel", "to": "cabin", "then": "idle"}
        r = rng.random()
        if r < 0.30:
            return {"do": "read"}
        if r < 0.45 and b.scene == "cabin":
            return {"do": "stare_out_window"}
        if r < 0.55 and not plan.lifestyle["hermit"]:
            return {"do": "travel", "to": "outside", "then": "walk"}
        return {"do": "idle"}

    # ---------------------------------------------------------------- time ---
    def _writing_hour(self, state):
        hour = (state.clock // 60) % 24
        if state.plan.lifestyle["night_owl"]:
            return hour >= 19 or hour < 3
        return 7 <= hour <= 22

    def _too_late(self, state):
        hour = (state.clock // 60) % 24
        return hour >= 21 or hour < 6

    # ------------------------------------------------------------- growth ---
    def on_activity(self, name, state):
        """Living changes the writer; the changed writer writes differently."""
        growth = {
            "research": ("curiosity", +0.03),
            "read": ("curiosity", +0.015),
            "write": ("discipline", +0.02),
            "pray": ("spirituality", +0.03),
            "walk": ("melancholy", +0.01),
            "socialize": ("solitude", -0.04),
            "stare_out_window": ("melancholy", +0.015),
            "forage": ("solitude", +0.01),
        }
        if name in growth:
            key, delta = growth[name]
            self.adjust(key, delta)


def new_book_from_request(topic, title, traits, author, research_notes):
    topic = topic or "a quiet life in the rain"
    if not title:
        import random as _r
        title = books.suggest_title(topic, traits, _r.Random(time.time()))
    theme_words = [w for w in topic.split() if len(w) > 3]
    target = 4200 + int(traits.get("discipline", 0.5) * 1600)
    notes = [n for n in research_notes
             if any(w in n.lower() for w in theme_words)][:3] or research_notes[-2:]
    return books.Book(title, topic, traits, author,
                      target_words=target, research=notes)

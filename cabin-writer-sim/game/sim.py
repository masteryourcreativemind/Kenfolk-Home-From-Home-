"""The simulation core — one tick at a time, shared verbatim by the pygame
engine and the headless agent mode. Owns the clock, the weather, the body,
the mind, the work, the money, and the log of a life."""

import json
import os
import random
import time
from collections import deque

from . import books as bookmod
from . import config
from . import economy
from . import mind as mindmod
from . import publish
from . import world
from .writer import Body

MIN_PER_TILE = 1.2   # walking pace: game-minutes per tile

# activity durations in game-minutes
DURATIONS = {
    "eat": 35, "wash": 40, "write": 120, "research": 150, "read": 60,
    "walk": 60, "shop": 45, "pray": 50, "socialize": 80, "forage": 90,
    "idle": 30, "stare_out_window": 25, "linger": 20, "rest": 60,
}

# indoor anchor tiles for activities: scene -> activity -> (x, y, facing)
ANCHORS = {
    "cabin":   {"write": (2, 3, "up"), "eat": (6, 6, "up"),
                "wash": (7, 3, "up"), "read": (6, 3, "down"),
                "sleep": (1, 3, "up"), "stare_out_window": (4, 1, "up"),
                "rest": (6, 4, "up")},
    "library": {"research": (6, 4, "left"), "read": (2, 3, "up")},
    "store":   {"shop": (4, 4, "up")},
    "chapel":  {"pray": (3, 3, "left")},
    "cafe":    {"socialize": (2, 2, "left"), "read": (5, 5, "left")},
    "lookout_cabin": {"linger": (4, 1, "up"), "write": (3, 4, "left")},
}

# outdoor goals
OUTDOOR_GOALS = {
    "lakeshore": (9, 24),
    "outside": (9, 20),
    "forage": (5, 17),
}

SEASONS = ("autumn", "winter", "spring", "summer")


class Sim:
    def __init__(self, out_dir=config.OUTPUT_DIR, seed=None,
                 enable_real_payments=False, owner=config.DEFAULT_OWNER_NAME):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.rng = random.Random(seed if seed is not None else time.time())
        self.clock = config.START_HOUR * 60     # absolute game-minutes
        self.weather = "rain"
        self.weather_forecast = []
        self.body = Body()
        self.mind = mindmod.Mind()
        self.plan = mindmod.LifePlan()
        self.parser = mindmod.CommandParser()
        self.owner = owner
        self.current_book = None
        self.finished_books = []                # metadata dicts
        self.research_notes = []
        self.activity = None                    # current activity dict
        self.log = deque(maxlen=400)
        self.walked_today = False
        self.prayed_today = False
        self._decay_carry = 0.0
        self.paused = False

        provider = economy.make_provider(enable_real_payments)
        self.ledger = economy.Ledger(out_dir)
        self.wallet = economy.Wallet(provider, self.ledger)

        self._roll_weather()
        self.say("world", "Rain on the tin roof. A lamp, a desk, a blank "
                          "page. The life begins.")

    # ------------------------------------------------------------- traits ---
    @property
    def traits(self):
        return self.mind.traits

    # -------------------------------------------------------------- time ---
    @property
    def day(self):
        return int(self.clock // config.DAY_MINUTES) + 1

    @property
    def hour_min(self):
        m = int(self.clock % config.DAY_MINUTES)
        return m // 60, m % 60

    @property
    def season(self):
        return SEASONS[((self.day - 1) // config.SEASON_DAYS) % 4]

    def clock_str(self):
        h, m = self.hour_min
        return f"Day {self.day}  {h:02d}:{m:02d}"

    def _roll_weather(self):
        roll = self.rng.random()
        if self.season == "winter":
            table = [("snow", 0.45), ("fog", 0.20), ("rain", 0.15),
                     ("clear", 0.20)]
        elif self.season == "summer":
            table = [("rain", 0.25), ("fog", 0.10), ("clear", 0.65)]
        else:  # autumn & spring: the moody seasons
            table = [("rain", 0.50), ("fog", 0.22), ("clear", 0.28)]
        acc = 0
        for w, p in table:
            acc += p
            if roll <= acc:
                new = w
                break
        else:
            new = "rain"
        if new != getattr(self, "weather", None):
            self.weather = new

    # ---------------------------------------------------------------- log ---
    def say(self, who, text):
        self.log.append({"t": self.clock_str(), "who": who, "text": text,
                         "weather": self.weather})

    # ------------------------------------------------------------ commands ---
    def submit_command(self, text):
        """The user speaks. Returns the writer's reply (or a system note)."""
        self.say("you", text)
        reply, effect = self.parser.parse(text, self)
        if effect:
            reply = self._apply_effect(effect) or reply
        if reply:
            self.say(self.body.name, reply)
        return reply or "…"

    def _apply_effect(self, effect):
        if "buy" in effect:
            item = effect["buy"]
            if self.body.scene != "store":
                self.plan.go_to = "store"
                self._pending_purchase = item
                return (f"I'll walk to the store for {item.replace('_', ' ')}. "
                        f"Watch the road.")
            ok, msg = self.wallet.spend(self.body, item)
            if ok:
                self.say("store", msg)
            return msg
        if "top_up" in effect:
            amount, ccy = effect["top_up"]
            credits, result = self.wallet.top_up(amount, ccy)
            if credits:
                self.body.money += credits
                return (f"Patronage received: {amount:.2f} {ccy} → "
                        f"{credits:.0f} credits. {result.get('note', '')} "
                        f"The pantry thanks you.")
            return f"The transfer failed: {result.get('note', 'unknown')}."
        if effect.get("status"):
            return self.status_text()
        if effect.get("help"):
            return HELP_TEXT
        if effect.get("books"):
            if not self.finished_books and self.current_book is None:
                return "No books yet. Commission one: 'write a book about …'."
            lines = []
            for fb in self.finished_books:
                lines.append(f"• “{fb['title']}” — {fb['words']} words, "
                             f"craft {fb['craft_score']:.2f}, ISBN {fb['isbn']}")
            if self.current_book:
                b = self.current_book
                lines.append(f"• (in progress) “{b.title}” — "
                             f"{b.words}/{b.target_words} words")
            return "\n".join(lines)
        if "package" in effect:
            self.plan.pack_unorganized = not effect["package"]
            mode = "flat and unorganized" if not effect["package"] \
                else "neatly organised"
            return (f"Understood — future books ship {mode}. "
                    f"(Finished books keep their original packaging.)")
        return None

    # --------------------------------------------------------- activities ---
    def _start(self, act):
        """Begin an activity: move to its anchor, then occupy time."""
        do = act["do"]
        if do == "travel":
            segs = self._build_travel(act["to"])
            if not segs:
                self._start_then(act.get("then"))
                return
            self.activity = {"do": "travel", "to": act["to"],
                             "then": act.get("then"),
                             "segments": segs, "seg": 0, "prog": 0.0}
            self.say(self.body.name, self._travel_line(act["to"]))
            return

        if do == "wake":
            self.body.asleep = False
            self.activity = None
            self.say(self.body.name, self.rng.choice([
                "Wakes with the rain. Another page owes itself.",
                "Up. The stove is cold and the page is blank.",
                "Morning, such as it is. Grey suits the work."]))
            return
        if do == "go_home_sleep":
            if self.body.scene != "cabin":
                self._start({"do": "travel", "to": "cabin", "then": "sleep"})
            else:
                self._start({"do": "sleep"})
            return
        if do == "sleep":
            self.body.asleep = True
            self.activity = {"do": "sleep", "remaining": 8 * 60}
            self.say(self.body.name, "Sleeps the sleep of the obliged.")
            return
        if do == "begin_book":
            req_topic = act.get("topic")
            title = act.get("title")
            self.current_book = mindmod.new_book_from_request(
                req_topic, title, self.traits, self.body.name,
                self.research_notes)
            self.plan.book_requests.pop(0)
            b = self.current_book
            self.say(self.body.name,
                     f"Opens a fresh notebook. “{b.title}” — a book about "
                     f"{b.theme}, roughly {b.target_words} words long. "
                     f"So it begins.")
            self.activity = {"do": "idle", "remaining": 10}
            return

        # ordinary timed activity, possibly at an anchor tile
        scene = self.body.scene
        anchor = ANCHORS.get(scene, {}).get(do)
        if do in ("forage",):
            self._start({"do": "travel", "to": "outside", "then": "forage_here"})
            return
        if do == "forage_here":
            self.activity = {"do": "forage",
                             "remaining": DURATIONS["forage"]}
            return
        if anchor:
            tx, ty, face = anchor
            if (int(self.body.x), int(self.body.y)) != (tx, ty):
                seg = self._move_segment((tx, ty))
                if seg:
                    self.activity = {"do": "_move", "segments": [seg],
                                     "seg": 0, "prog": 0.0, "then": do,
                                     "face": face}
                    return
            self.body.facing = face
        dur = DURATIONS.get(do, 30)
        self.activity = {"do": do, "remaining": dur}
        self.say(self.body.name, self._start_line(do))

    def _start_then(self, then):
        if then in (None, "idle", "linger"):
            self.activity = {"do": then or "idle",
                             "remaining": DURATIONS.get(then or "idle", 30)}
        elif then == "forage_here":
            self._start({"do": "forage_here"})
        else:
            self._start({"do": then})

    # -------------------------------------------------------------- travel ---
    def _move_segment(self, target):
        scene = world.Scene(self.body.scene)
        path = _bfs(scene, (int(self.body.x), int(self.body.y)), target)
        if not path:
            return None
        return {"scene": self.body.scene, "path": path,
                "end_scene": self.body.scene, "end_pos": target}

    def _build_travel(self, dest):
        segs = []
        cur_scene_key = self.body.scene
        cur_pos = (int(self.body.x), int(self.body.y))

        # step 1: leave any building
        if world.LOCATIONS[cur_scene_key]["indoors"]:
            scene = world.Scene(cur_scene_key)
            exits = sorted(scene.exits)
            path = _bfs(scene, cur_pos, exits[0])
            if not path:
                return []
            door = world.door_positions(cur_scene_key)[0]
            segs.append({"scene": cur_scene_key, "path": path,
                         "end_scene": "outside", "end_pos": door})
            cur_scene_key, cur_pos = "outside", door

        # step 2: across the pinewood
        if dest in OUTDOOR_GOALS:
            goal = OUTDOOR_GOALS[dest]
            end_scene = "outside"
        else:
            doors = world.door_positions(dest)
            if not doors:
                return segs
            goal = doors[0]
            end_scene = dest

        scene = world.Scene("outside")
        if cur_pos != goal:
            path = _bfs(scene, cur_pos, goal)
            if not path:
                return segs
        else:
            path = [goal]
        end_pos = (world.Scene(dest).spawn if end_scene != "outside"
                   else goal)
        segs.append({"scene": "outside", "path": path,
                     "end_scene": end_scene, "end_pos": end_pos})
        return segs

    # ------------------------------------------------------------ ticking ---
    def tick(self, minutes=1.0):
        if self.paused:
            return
        self.clock += minutes
        hours = minutes / 60.0
        self.body.decay(hours, self.traits)
        self.body.drift_mood(hours, self.weather, self.traits)

        # midnight housekeeping
        h, _ = self.hour_min
        if getattr(self, "_last_hour", h) > h:      # wrapped past midnight
            self._new_day()
        self._last_hour = h

        if self.activity is None:
            act = self.mind.decide(self)
            self._start(act)
            return

        a = self.activity
        if a["do"] in ("travel", "_move"):
            self._advance_movement(a, minutes)
            return
        a["remaining"] -= minutes
        if a["do"] == "sleep":
            # the mind may wake early on its own
            if not self.body.asleep or self.body.needs["energy"] >= 100:
                self.activity = None
                self.body.asleep = False
                return
        if a["remaining"] <= 0:
            self.activity = None
            self._complete(a)

    def _advance_movement(self, a, minutes):
        tiles = minutes / MIN_PER_TILE
        a["prog"] += tiles
        while True:
            seg = a["segments"][a["seg"]]
            path = seg["path"]
            idx = min(int(a["prog"]), len(path) - 1)
            # ensure the sprite is in the segment's scene
            if self.body.scene != seg["scene"]:
                self.body.scene = seg["scene"]
            x, y = path[idx]
            self._face_toward(x, y)
            self.body.x, self.body.y = float(x), float(y)
            self.body.moving = True
            if int(a["prog"]) < len(path):
                break
            # segment finished
            a["prog"] = 0.0
            self.body.scene = seg["end_scene"]
            ex, ey = seg["end_pos"]
            self.body.x, self.body.y = float(ex), float(ey)
            a["seg"] += 1
            if a["seg"] >= len(a["segments"]):
                self.body.moving = False
                then = a.get("then")
                face = a.get("face")
                self.activity = None
                if a["do"] == "travel":
                    dest = a["to"]
                    name = world.LOCATIONS[dest]["name"]
                    self.say(self.body.name, f"Arrives at {name}.")
                    self.mind.on_activity("walk", self)
                if face:
                    self.body.facing = face
                self._start_then(then)
                return

    def _face_toward(self, x, y):
        dx, dy = x - self.body.x, y - self.body.y
        if abs(dx) > abs(dy):
            self.body.facing = "right" if dx > 0 else "left"
        elif dy:
            self.body.facing = "down" if dy > 0 else "up"

    # ---------------------------------------------------------- completion ---
    def _complete(self, a):
        do = a["do"]
        b = self.body
        n = b.needs
        self.mind.on_activity(do, self)

        if do == "eat":
            if b.eat():
                self.say(b.name, self.rng.choice([
                    "Beans on toast. Eaten standing, reading the rain.",
                    "Bread and cheese at the little table. Enough.",
                    "A tin of something warm. The stove approves."]))
        elif do == "wash":
            b.wash()
            self.say(b.name, "Washes in cold water. Gasps. Feels newer.")
        elif do == "rest":
            b.health = min(100, b.health + 7)
            n["energy"] = min(100, n["energy"] + 7)
            n["mood"] = min(100, n["mood"] + 2)
            self.say(b.name, "Rests by the stove, blanket over knees, "
                             "listening to the roof.")
        elif do == "sleep":
            b.asleep = False
        elif do == "write":
            self._finish_writing_session()
        elif do == "research":
            topic = (self.plan.research_requests.pop(0)
                     if self.plan.research_requests else "the weather")
            note = self._make_note(topic)
            self.research_notes.append(note)
            n["inspiration"] = min(100, n["inspiration"] + 18)
            self.say(b.name, f"Researches {topic}. Note kept: “{note}”")
        elif do == "read":
            n["inspiration"] = min(100, n["inspiration"] + 10)
            n["mood"] = min(100, n["mood"] + 3)
            self.say(b.name, "Reads until the print blurs. Other people's "
                             "sentences, borrowed warmth.")
        elif do == "walk":
            bonus = 6 if self.weather == "rain" else 3
            if self.traits["melancholy"] > 0.6 and self.weather == "rain":
                bonus += 3     # some people are fed by the rain
            n["mood"] = min(100, n["mood"] + bonus)
            n["inspiration"] = min(100, n["inspiration"] + 6)
            self.walked_today = True
            self.say(b.name, self.rng.choice([
                "Walks the shore. The lake keeps its own ledger.",
                "Walks without destination — the purest kind.",
                "Wet cuffs, wet thoughts. Both needed airing."]))
        elif do == "shop":
            self._do_shopping()
        elif do == "pray":
            n["mood"] = min(100, n["mood"] + 5)
            n["social"] = min(100, n["social"] + 6)
            self.prayed_today = True
            self.say(b.name, "Lights a candle for no one specific. "
                             "It counts anyway.")
        elif do == "socialize":
            n["social"] = min(100, n["social"] + 38)
            n["mood"] = min(100, n["mood"] + 6)
            if b.money >= 4:
                b.money -= 4
                self.ledger.record({"type": "purchase", "item": "coffee",
                                    "cost": 4.0})
            self.say(b.name, "Coffee among murmuring strangers. Remembers "
                             "the sound of other lives.")
        elif do == "forage":
            if self.rng.random() < 0.65:
                b.food += 1
                self.say(b.name, "Forages mushrooms and berries under the "
                                 "dripping pines. Supper, barely.")
            else:
                n["mood"] = max(0, n["mood"] - 3)
                self.say(b.name, "Finds nothing edible. The woods are "
                                 "generous only sometimes.")
        elif do == "stare_out_window":
            n["inspiration"] = min(100, n["inspiration"] + 5)
            self.say(b.name, self.rng.choice([
                "Stares out the window. The rain is also about something.",
                "Watches drops race down the glass. Bets on the wrong one.",
                "The window fogs. Writes a word in it. Watches it leave."]))
        elif do == "linger":
            self.say(b.name, "Lingers. Some places ask for nothing else.")
        elif do == "idle":
            pass

        # if a purchase was queued behind a store trip, buy it now
        if do == "linger" and getattr(self, "_pending_purchase", None) \
                and b.scene == "store":
            item = self._pending_purchase
            self._pending_purchase = None
            ok, msg = self.wallet.spend(b, item)
            self.say("store", msg)
            self._start({"do": "travel", "to": "cabin", "then": "idle"})

    # ------------------------------------------------------------- writing ---
    def _finish_writing_session(self):
        b = self.body
        book = self.current_book
        if book is None:
            self.say(b.name, "Sits at the desk. No book is open. The lamp "
                             "burns anyway, hopefully.")
            return
        if b.supplies.get("paper", 0) <= 0:
            self.say(b.name, "Out of paper. Stares at the empty desk like "
                             "it betrayed the family.")
            self.plan.research_requests  # (no-op; shopping will be decided)
            return
        b.supplies["paper"] -= 1
        hours = DURATIONS["write"] / 60
        # furniture matters: typewriter speeds the hand
        speed_mul = 1.35 if b.furniture.get("typewriter") else 1.0
        before = book.words
        words = book.write_session(hours, b.needs["energy"], b.needs["mood"],
                                   self.traits["discipline"], self.weather)
        words = int(words * speed_mul)
        book.words = min(book.target_words, before + words)
        if book.done and book.finished is None:
            book.finished = time.time()
        b.needs["energy"] = max(0, b.needs["energy"] - 8)
        b.needs["inspiration"] = max(0, b.needs["inspiration"] - 6)
        pct = int(book.progress * 100)
        self.say(b.name, f"Writes {words} words on “{book.title}” "
                         f"({pct}% — {book.words}/{book.target_words}).")
        if book.done:
            self._publish_book(book)

    def _publish_book(self, book):
        ms = book.materialise()
        organized = not self.plan.pack_unorganized
        try:
            zip_path = publish.package_book(ms, self.owner, self.out_dir,
                                            organized=organized)
        except Exception as exc:
            self.say("printer", f"Publication failed: {exc}")
            return
        cert = publish.make_certificate(ms, self.owner)
        royalty = 20 + 30 * ms["quality"]
        self.body.money += royalty
        self.ledger.record({"type": "royalty", "title": ms["title"],
                            "credits": round(royalty, 2)})
        meta = {"title": ms["title"], "author": ms["author"],
                "owner": self.owner, "isbn": cert["isbn"],
                "words": ms["words"], "craft_score": ms["quality"],
                "zip": zip_path, "theme": ms["theme"],
                "finished": time.strftime("%Y-%m-%d", time.gmtime())}
        self.finished_books.append(meta)
        self._save_books_index()
        self.current_book = None
        self.mind.adjust("discipline", 0.05)
        self.say("printer",
                 f"“{ms['title']}” is finished and shipped: {zip_path} "
                 f"(EPUB + PDF, certificates inside, "
                 f"{'organised' if organized else 'unorganised'}). "
                 f"Royalties: {royalty:.0f}cr.")
        self.say(self.body.name,
                 f"It is done. {ms['words']} words about {ms['theme']}. "
                 f"Tonight the rain sounds almost like applause.")

    # ------------------------------------------------------------- flavour ---
    def _make_note(self, topic):
        rng = self.rng
        fragments = [
            f"on {topic}: it is mostly about waiting",
            f"{topic} — see also: rain, endurance, tea gone cold",
            f"everyone writes {topic} wrong; they make it loud",
            f"{topic} is a room you tidy for a guest who died years ago",
            f"the librarian's only comment on {topic}: 'aisle three, and "
            f"bring a handkerchief'",
        ]
        if rng.random() < 0.4:
            return rng.choice(bookmod.EPIGRAPHS)
        return rng.choice(fragments)

    def _start_line(self, do):
        lines = {
            "eat": "Something to eat, before the body starts negotiating.",
            "wash": "A basin, cold water, resolve.",
            "write": "Sits at the desk. The lamp leans in.",
            "research": "Into the stacks, notebook first.",
            "read": "Takes down a book by someone braver.",
            "walk": "Out into it. Coat, collar, weather.",
            "shop": "A basket, a short list, a long look at prices.",
            "pray": "Kneels in the dim. The candles do their small work.",
            "socialize": "Orders coffee. Practises being a person.",
            "idle": "Puts the kettle on. Thinks in circles, fondly.",
            "stare_out_window": "The window again. The rain's long sentence.",
            "linger": "Stands a while. Places keep you, if you let them.",
            "rest": "Sinks into the chair by the stove. The body files "
                    "a formal complaint.",
        }
        return lines.get(do, do)

    def _travel_line(self, dest):
        name = world.LOCATIONS.get(dest, {}).get("name", dest)
        return self.rng.choice([
            f"Sets out for {name}. Collar up.",
            f"The road to {name}, then.",
            f"Off to {name}. The rain walks too.",
        ])

    def _do_shopping(self):
        b = self.body
        bought = []
        essentials = ["groceries"]
        if b.supplies.get("paper", 0) < 4:
            essentials.append("paper")
        if b.supplies.get("lamp_oil", 0) < 2:
            essentials.append("lamp_oil")
        if self.plan.lifestyle.get("frugal"):
            wanted = essentials
        else:
            wanted = essentials + ["coffee"]
            if b.furniture.get("armchair") is None and b.money > 130:
                wanted.append("armchair")
        for item in wanted:
            ok, msg = self.wallet.spend(b, item)
            if ok:
                bought.append(item)
        if bought:
            self.say("store", "Bought: " + ", ".join(bought) + ".")
        else:
            self.say("store", "Looks at the shelves. Looks at the coins. "
                              "Leaves lighter than the rain.")
        self._start({"do": "travel", "to": "cabin", "then": "idle"})

    def _new_day(self):
        self.walked_today = False
        self.prayed_today = False
        old = self.weather
        self._roll_weather()
        w = self.weather
        desc = {
            "rain": "Rain again, or rain still. The roof rehearses its psalm.",
            "fog": "Fog. The pines have been cancelled for today.",
            "snow": "Snow, soft as an apology.",
            "clear": "A clear morning — suspiciously kind.",
        }[w]
        self.say("world", f"— {self.season.capitalize()}, day {self.day}. {desc}")

    # ------------------------------------------------------------- status ---
    def status_text(self):
        b = self.body
        book = (f"writing “{self.current_book.title}” "
                f"({int(self.current_book.progress * 100)}%)"
                if self.current_book else "between books")
        doing = self.activity["do"] if self.activity else "thinking"
        loc = world.LOCATIONS[b.scene]["name"]
        return (f"{b.name}, {book}, currently {doing} in {loc}.\n"
                f"{b.condition_summary()}\n"
                f"Traits: " + ", ".join(f"{k} {v:.2f}" for k, v in
                                        sorted(self.traits.items())))

    # ----------------------------------------------------------- save/load ---
    def save(self, path=None):
        path = path or os.path.join(self.out_dir, "save.json")
        data = {
            "clock": self.clock, "weather": self.weather, "owner": self.owner,
            "body": self.body.to_dict(), "traits": self.mind.traits,
            "plan": self.plan.to_dict(),
            "current_book": self.current_book.to_dict()
                            if self.current_book else None,
            "finished_books": self.finished_books,
            "research_notes": self.research_notes,
            "walked_today": self.walked_today,
            "prayed_today": self.prayed_today,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        return path

    @classmethod
    def load(cls, path, out_dir=config.OUTPUT_DIR,
             enable_real_payments=False):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        sim = cls(out_dir=out_dir, enable_real_payments=enable_real_payments,
                  owner=data.get("owner", config.DEFAULT_OWNER_NAME))
        sim.clock = data["clock"]
        sim.weather = data["weather"]
        sim.body = Body.from_dict(data["body"])
        sim.mind.traits.update(data.get("traits", {}))
        sim.plan = mindmod.LifePlan.from_dict(data.get("plan", {}))
        if data.get("current_book"):
            sim.current_book = bookmod.Book.from_dict(data["current_book"])
        sim.finished_books = data.get("finished_books", [])
        sim.research_notes = data.get("research_notes", [])
        sim.walked_today = data.get("walked_today", False)
        sim.prayed_today = data.get("prayed_today", False)
        return sim

    def _save_books_index(self):
        with open(os.path.join(self.out_dir, "books.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(self.finished_books, fh, indent=2)


HELP_TEXT = """Say things like:
  write a book about grief and the sea     — commission a book
  write a novel about memory called "The Amber House"
  research 19th century whaling            — it will seep into the work
  live as a hermit / be social / be a night owl / take daily walks
  live frugally / pray daily               — shape the life
  go to the library / chapel / café / store / lake / lookout
  buy groceries / paper / a typewriter     — the store stocks these
  top up 20 dollars                        — patronage → credits
  package latest unorganized               — next zip ships flat
  books / status / help                    — inquire

The writer lives under real constraints: hunger, exhaustion, loneliness,
weather, and money. It may only ever be a writer. Care for it, and it
will write you something true."""


# ------------------------------------------------------------ pathfinding ---
def _bfs(scene, start, goal):
    from collections import deque as _dq
    if not scene.walkable(*goal):
        return None
    if start == goal:
        return [goal]
    seen = {start}
    q = _dq([(start, [start])])
    while q:
        (x, y), path = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (nx, ny) in seen or not scene.walkable(nx, ny):
                continue
            np_ = path + [(nx, ny)]
            if (nx, ny) == goal:
                return np_
            seen.add((nx, ny))
            q.append(((nx, ny), np_))
    return None

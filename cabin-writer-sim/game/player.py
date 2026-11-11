"""Directly controlled survival, sharing the writer's world and publishing."""

import math
from collections import deque

from . import config, economy, mind, world
from .sim import MIN_PER_TILE, Sim, _bfs
from .survival import CLOTHING, MAX_HP, ORGANS, clamp


PLAYER_STORE_ITEMS = ("groceries", "bread", "paper", "typewriter")
SURVIVAL_CATALOG = {
    "water": {"cost": 3, "amount": 1, "desc": "one bottle of safe water"},
    "bait": {"cost": 4, "amount": 6, "desc": "six portions of fishing bait"},
    "arrows": {"cost": 8, "amount": 6, "desc": "six hunting arrows"},
    "firewood": {"cost": 6, "amount": 3, "desc": "three bundles of dry wood"},
    "bandage": {"cost": 8, "amount": 2, "desc": "two clean bandages"},
    "medicine": {"cost": 16, "amount": 1, "desc": "one game illness treatment"},
    "fishing_rod": {"cost": 40, "gear": True, "desc": "a lakeshore fishing rod"},
    "bow": {"cost": 55, "gear": True, "desc": "a woodland hunting bow"},
    "winter_coat": {"cost": 45, "gear": True, "desc": CLOTHING["winter_coat"]["description"]},
}
SELL_PRICES = {"fish": 8, "raw_meat": 10, "pelt": 14,
               "berries": 3, "herbs": 5, "firewood": 2}

NPCS = {
    "mira": {"name": "Mira", "role": "Shopkeeper", "scene": "store",
             "x": 4, "y": 2, "hours": (8, 20),
             "dialogue": "I buy fish, meat, pelts, herbs and firewood. A thick coat helps in winter, not in a heatwave."},
    "nessa": {"name": "Nessa", "role": "Fisher", "scene": "outside",
              "x": 9, "y": 23, "hours": (6, 19),
              "dialogue": "Fish from the dock or an open bank. Bring bait. Cook your catch, or bring me two fish for supper."},
    "rowan": {"name": "Rowan", "role": "Ranger", "scene": "lookout_cabin",
              "x": 2, "y": 3, "hours": (6, 21),
              "dialogue": "Track the animals marked on your map. Trees block a shot. Bring me two portions of meat; bandage any hunting injury."},
    "jun": {"name": "Jun", "role": "Village medic", "scene": "chapel",
            "x": 3, "y": 2, "hours": (8, 22),
            "dialogue": "I can treat injuries and illness for 25 credits. Untreated wounds and unsafe food cause illness; cold itself causes hypothermia."},
    "ada": {"name": "Ada", "role": "Librarian", "scene": "library",
            "x": 7, "y": 3, "hours": (8, 21),
            "dialogue": "Research here, then write at your cabin desk. Finished books still earn royalties and ship as EPUB and PDF."},
    "tomas": {"name": "Tomas", "role": "Cafe host", "scene": "cafe",
              "x": 5, "y": 3, "hours": (7, 22),
              "dialogue": "Warm up, refill your water and talk a while. Time moves only when you choose an action."},
}
QUESTS = {
    "fish_supper": {"name": "Supper at the lake", "npc": "nessa",
                    "item": "fish", "amount": 2, "reward": 24},
    "ranger_delivery": {"name": "The ranger's provisions", "npc": "rowan",
                        "item": "raw_meat", "amount": 2, "reward": 30},
}
DIRECTIONS = {(0, -1): "up", (0, 1): "down",
              (-1, 0): "left", (1, 0): "right"}


class ActionError(ValueError):
    """A rejected player choice, shown in the UI rather than ignored."""


class GameOver(ActionError):
    pass


def _text(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ActionError(f"{label} must contain 1-{limit} characters.")
    return value.strip()


def _integer(value, label, low, high):
    if isinstance(value, bool) or not isinstance(value, int) \
            or not low <= value <= high:
        raise ActionError(f"{label} must be an integer from {low} to {high}.")
    return value


class PlayerSim(Sim):
    def __init__(self, out_dir=config.OUTPUT_DIR, seed=None,
                 enable_real_payments=False, owner=config.DEFAULT_OWNER_NAME):
        if enable_real_payments:
            raise ValueError("Player mode uses in-game credits only, never real payments.")
        super().__init__(out_dir, seed, False, owner)
        self.clock = 8 * 60
        self.body.name = "You"
        self.body.health = 100
        self.inventory = {
            "water": 3, "bait": 8, "arrows": 6, "firewood": 3,
            "bandage": 2, "medicine": 1, "fish": 0, "raw_meat": 0,
            "cooked_fish": 0, "cooked_meat": 0, "berries": 0,
            "herbs": 0, "pelt": 0,
        }
        self.gear = {"light_clothes", "raincoat", "fishing_rod", "bow"}
        self.skills = {"fishing": 0, "hunting": 0, "foraging": 0}
        self.relationships = {key: 0 for key in NPCS}
        self.last_talk = {}
        self.quests = {key: "available" for key in QUESTS}
        self.fires = {}
        self.fish_stock = 10
        self.animal_serial = 0
        self.animals = []
        self._spawn_animals()
        self.next_weather = self.clock + 6 * 60
        self.next_roam = self.clock + 30
        self.log.clear()
        self.say("world", "This is your life: move, explore and choose every action. "
                 "Nothing acts for you. Meet Nessa at the dock for your first quest.")

    def _roll_weather(self):
        if self.season == "winter":
            choices = ("snow", "snow", "fog", "clear", "storm")
        elif self.season == "summer":
            choices = ("clear", "clear", "rain", "fog", "heatwave")
        else:
            choices = ("rain", "rain", "fog", "clear", "storm")
        self.weather = self.rng.choice(choices)

    def environment(self):
        b = self.body
        indoors = world.LOCATIONS[b.scene]["indoors"]
        heated = indoors and self.fires.get(b.scene, 0) > self.clock
        hour, minute = self.hour_min
        temperature = {"autumn": 10, "winter": -8,
                       "spring": 14, "summer": 28}[self.season]
        temperature += 5 * math.sin(((hour + minute / 60) - 8) / 24 * math.tau)
        wind = {"clear": 6, "fog": 3, "rain": 16, "snow": 18,
                "storm": 38, "heatwave": 2}[self.weather]
        temperature += {"clear": 0, "fog": -2, "rain": -3,
                        "snow": -5, "storm": -6, "heatwave": 10}[self.weather]
        climate = "Temperate pinewood"
        if not indoors and b.x >= 36:
            climate = "Cold uplands"
            temperature -= 6
            wind += 8
        elif not indoors and b.y >= 21:
            climate = "Damp lakeshore"
            temperature -= 2
            wind += 4
        if indoors:
            climate = "Sheltered interior"
            temperature = 24 if heated else 19
            wind = 0
        precipitation = {"rain": 30, "storm": 55, "snow": 12}.get(self.weather, 0)
        return {
            "climate": climate, "temperature": round(temperature, 2),
            "wind": wind, "indoors": indoors, "heated": heated,
            "precipitation": 0 if indoors else precipitation,
        }

    def tick(self, minutes=1.0, effort=0, resting=False):
        """Advance only a player-selected action; never invoke Mind.decide."""
        if not self.body.physiology.alive:
            raise GameOver("Your life has ended. Choose New life to play again.")
        remaining = minutes
        while remaining > 0:
            step = min(5, remaining, self.next_weather - self.clock,
                       self.next_roam - self.clock)
            if step <= 0:
                self._housekeeping()
                continue
            environment = self.environment()
            old_day = self.day
            previous = set(self.body.physiology.conditions)
            self.clock += step
            hours = step / 60
            self.body.decay(hours, self.traits, manage_health=False)
            needs = self.body.needs
            lung_strength = self.body.physiology.organs["lungs"] / ORGANS["lungs"][1]
            needs["energy"] = max(
                0, needs["energy"] - effort * (2 - lung_strength) * hours * 2)
            needs["satiety"] = max(0, needs["satiety"] - effort * hours)
            if resting:
                needs["energy"] = min(100, needs["energy"] + 18 * hours)
            self.body.physiology.update(hours, environment, needs, effort,
                                        self.body.asleep)
            self.body.drift_mood(hours, self.weather, self.traits)
            for condition in set(self.body.physiology.conditions) - previous:
                self.say("body", condition + ". Check your body panel.")
            if self.day != old_day:
                self.fish_stock = min(12, self.fish_stock + 4)
                self._spawn_animals()
                self.say("world", f"A new day in {self.season}. Wildlife and fish recover.")
            self._housekeeping()
            remaining -= step
            if not self.body.physiology.alive:
                raise GameOver("Your life ended: " +
                               ", ".join(self.body.physiology.conditions) +
                               ". Choose New life to start again.")

    def _housekeeping(self):
        if self.clock >= self.next_weather:
            self._roll_weather()
            self.next_weather += 6 * 60
            self.say("weather", f"The forecast changes to {self.weather}.")
        if self.clock >= self.next_roam:
            scene = world.Scene("outside")
            for animal in self.animals:
                dx, dy = self.rng.choice(tuple(DIRECTIONS))
                x, y = animal["x"] + dx, animal["y"] + dy
                if self._wild_tile(scene, x, y):
                    animal["x"], animal["y"] = x, y
            self.next_roam += 30

    @staticmethod
    def _wild_tile(scene, x, y):
        return (12 <= x < 45 and 5 <= y < 22
                and scene.at(x, y) in ("g", "G", "f"))

    def _spawn_animals(self):
        scene = world.Scene("outside")
        spots = [(x, y) for y in range(5, 22) for x in range(12, 45)
                 if self._wild_tile(scene, x, y)]
        occupied = {(a["x"], a["y"]) for a in self.animals}
        spots = [spot for spot in spots if spot not in occupied]
        for x, y in self.rng.sample(spots, min(6 - len(self.animals), len(spots))):
            self.animal_serial += 1
            self.animals.append({"id": self.animal_serial,
                                 "kind": self.rng.choice(("rabbit", "deer")),
                                 "x": x, "y": y})

    def npc_state(self, key):
        npc = dict(NPCS[key])
        hour = (self.clock % config.DAY_MINUTES) / 60
        npc["id"] = key
        npc["open"] = npc["hours"][0] <= hour < npc["hours"][1]
        npc["relationship"] = self.relationships[key]
        npc["nearby"] = (npc["open"] and self.body.scene == npc["scene"]
                         and self._distance(npc["x"], npc["y"]) <= 2)
        return npc

    def _distance(self, x, y):
        return abs(self.body.x - x) + abs(self.body.y - y)

    def _near_poi(self, key):
        point = world.Scene(self.body.scene).poi.get(key)
        return bool(point and self._distance(*point) <= 2)

    def _require_npc(self, key):
        if key not in NPCS:
            raise ActionError("Choose a known villager.")
        npc = self.npc_state(key)
        if not npc["open"]:
            raise ActionError(f"{npc['name']} is away. Hours: "
                              f"{npc['hours'][0]:02d}:00-{npc['hours'][1]:02d}:00.")
        if not npc["nearby"]:
            raise ActionError(f"Move within two tiles of {npc['name']} in "
                              f"{world.LOCATIONS[npc['scene']]['name']}.")
        return npc

    def _take(self, item, amount=1):
        if self.inventory.get(item, 0) < amount:
            raise ActionError(f"You need {amount} {item.replace('_', ' ')}.")
        self.inventory[item] -= amount

    def act(self, action, **parameters):
        handlers = {
            "move": (self._move, {"dx", "dy"}),
            "walk_to": (self._walk_to, {"x", "y"}),
            "travel": (self._travel, {"destination"}),
            "interact": (self._interact, set()),
            "talk": (self._talk, {"npc"}),
            "buy": (self._buy, {"item"}),
            "sell": (self._sell, {"item", "amount"}),
            "accept_quest": (self._accept_quest, {"quest"}),
            "deliver_quest": (self._deliver_quest, {"quest"}),
            "fish": (self._fish, set()),
            "hunt": (self._hunt, {"target"}),
            "forage": (self._forage, set()),
            "gather_wood": (self._gather_wood, set()),
            "eat": (self._eat, {"item"}),
            "drink": (self._drink, {"unsafe"}),
            "refill": (self._refill, set()),
            "equip": (self._equip, {"item"}),
            "light_fire": (self._light_fire, set()),
            "cook": (self._cook, {"item"}),
            "bandage": (self._bandage, set()),
            "medicine": (self._medicine, set()),
            "clinic": (self._clinic, set()),
            "wash": (self._wash, set()),
            "rest": (self._rest, set()),
            "sleep": (self._sleep, set()),
            "wait": (self._wait, {"minutes"}),
            "begin_book": (self._begin_book, {"topic", "title"}),
            "write": (self._write, set()),
            "research": (self._research, {"topic"}),
            "read": (self._read, set()),
        }
        try:
            if not self.body.physiology.alive:
                raise GameOver("Your life has ended. Choose New life to play again.")
            if not isinstance(action, str) or action not in handlers:
                raise ActionError("Unknown action.")
            handler, allowed = handlers[action]
            if parameters.keys() - allowed:
                raise ActionError("Unexpected action parameters.")
            integer_fields = {"dx", "dy", "x", "y", "target", "amount", "minutes"}
            for key, value in parameters.items():
                if value is None and key in ("target", "title"):
                    continue
                expected = int if key in integer_fields else bool if key == "unsafe" else str
                if type(value) is not expected:
                    raise ActionError(f"Invalid {key}: expected {expected.__name__}.")
            reply = handler(**parameters)
        except ActionError as exc:
            self.say("notice", str(exc))
            raise
        if action not in ("move", "walk_to"):
            self.say("you", reply)
        return reply

    def _walking_minutes(self):
        strength = self.body.physiology.organs["legs"] / ORGANS["legs"][1]
        return MIN_PER_TILE / (0.6 + 0.4 * strength)

    def _move(self, dx=None, dy=None):
        dx = _integer(dx, "Horizontal movement", -1, 1)
        dy = _integer(dy, "Vertical movement", -1, 1)
        if (dx, dy) not in DIRECTIONS:
            raise ActionError("Move one tile up, down, left or right.")
        b = self.body
        scene = world.Scene(b.scene)
        x, y = int(b.x) + dx, int(b.y) + dy
        if not scene.walkable(x, y):
            raise ActionError("That tile is blocked. Use the paths or open ground.")
        b.x, b.y, b.facing = x, y, DIRECTIONS[(dx, dy)]
        self.tick(self._walking_minutes(), effort=1)
        if scene.indoors and (x, y) in scene.exits:
            b.x, b.y = world.door_positions(b.scene)[0]
            b.scene = "outside"
            self.say("world", "You step into the pinewood.")
        elif not scene.indoors and scene.at(x, y) in world.DOOR_GLYPHS:
            b.scene = world.DOOR_GLYPHS[scene.at(x, y)]
            b.x, b.y = world.Scene(b.scene).spawn
            self.say("world", world.Scene(b.scene).flavour)
        return "Moved " + b.facing + "."

    def _walk_to(self, x=None, y=None):
        scene = world.Scene(self.body.scene)
        x = _integer(x, "Map x", 0, scene.width - 1)
        y = _integer(y, "Map y", 0, scene.height - 1)
        path = _bfs(scene, (int(self.body.x), int(self.body.y)), (x, y))
        if not path:
            raise ActionError("There is no walkable route to that tile.")
        for nx, ny in path[1:]:
            self._move(nx - int(self.body.x), ny - int(self.body.y))
            if self.body.scene != scene.key:
                break
        return "You follow the route you selected."

    def _travel(self, destination=None):
        if destination not in world.LOCATIONS:
            raise ActionError("Choose a place marked on the map.")
        if destination == self.body.scene:
            raise ActionError("You are already here.")
        segments = self._build_travel(destination)
        if not segments:
            raise ActionError("No walkable route to that destination.")
        for segment in segments:
            self.body.scene = segment["scene"]
            for x, y in segment["path"][1:]:
                self._face_toward(x, y)
                self.body.x, self.body.y = x, y
                self.tick(self._walking_minutes(), effort=1)
            self.body.scene = segment["end_scene"]
            self.body.x, self.body.y = segment["end_pos"]
        return "You arrive at " + world.LOCATIONS[destination]["name"] + "."

    def _interact(self):
        nearby = [key for key in NPCS if self.npc_state(key)["nearby"]]
        if nearby:
            return self._talk(nearby[0])
        if self._near_poi("bed"):
            return "At your bed: choose Sleep to rest for eight hours."
        if self._near_poi("stove"):
            return "At the stove: light a fire, cook raw food and dry your clothes."
        if self._near_poi("desk"):
            return "At your desk: start a book, then choose Write for each session."
        if self._at_water():
            return "At the lake: choose Fish. Raw lake water is unsafe."
        return "Explore with WASD or the arrow keys. The map marks villagers and supplies."

    def _talk(self, npc=None):
        person = self._require_npc(npc)
        self.tick(10)
        if self.clock - self.last_talk.get(npc, -1000) >= 4 * 60:
            self.relationships[npc] = min(100, self.relationships[npc] + 5)
            self.last_talk[npc] = self.clock
            self.body.needs["social"] = min(100, self.body.needs["social"] + 15)
            self.body.needs["mood"] = min(100, self.body.needs["mood"] + 3)
        return person["name"] + ": " + person["dialogue"]

    def _buy(self, item=None):
        self._require_npc("mira")
        if item in PLAYER_STORE_ITEMS:
            if economy.STORE_CATALOG[item]["kind"] == "furniture" \
                    and self.body.furniture.get(item):
                raise ActionError("You already own that equipment.")
            ok, message = self.wallet.spend(self.body, item)
            if not ok:
                raise ActionError(message)
        else:
            product = SURVIVAL_CATALOG.get(item)
            if not product:
                raise ActionError("The shop does not stock that item.")
            if product.get("gear") and item in self.gear:
                raise ActionError("You already own that equipment.")
            if self.body.money < product["cost"]:
                raise ActionError(f"You need {product['cost']} credits for that purchase.")
            self.ledger.record({"type": "purchase", "item": item,
                                "cost": product["cost"]})
            self.body.money -= product["cost"]
            if product.get("gear"):
                self.gear.add(item)
            else:
                self.inventory[item] += product["amount"]
            message = "Bought " + product["desc"] + "."
        self.tick(5)
        return message

    def _sell(self, item=None, amount=1):
        self._require_npc("mira")
        if item not in SELL_PRICES:
            raise ActionError("Mira does not buy that item.")
        amount = _integer(amount, "Quantity", 1, 99)
        if self.inventory.get(item, 0) < amount:
            raise ActionError("You do not have that many to sell.")
        credits = SELL_PRICES[item] * amount
        self.ledger.record({"type": "sale", "item": item,
                            "amount": amount, "credits": credits})
        self._take(item, amount)
        self.body.money += credits
        self.tick(5)
        return f"Sold {amount} {item.replace('_', ' ')} for {credits} credits."

    def _accept_quest(self, quest=None):
        if quest not in QUESTS:
            raise ActionError("Choose a quest from a villager.")
        self._require_npc(QUESTS[quest]["npc"])
        if self.quests[quest] != "available":
            raise ActionError("You already accepted or completed this quest.")
        self.quests[quest] = "active"
        return "Accepted: " + QUESTS[quest]["name"] + "."

    def _deliver_quest(self, quest=None):
        if quest not in QUESTS or self.quests[quest] != "active":
            raise ActionError("Accept this quest before delivering it.")
        details = QUESTS[quest]
        self._require_npc(details["npc"])
        if self.inventory.get(details["item"], 0) < details["amount"]:
            raise ActionError(f"Bring {details['amount']} {details['item'].replace('_', ' ')}.")
        self.ledger.record({"type": "quest_reward", "quest": quest,
                            "credits": details["reward"]})
        self._take(details["item"], details["amount"])
        self.body.money += details["reward"]
        self.relationships[details["npc"]] = min(100, self.relationships[details["npc"]] + 20)
        self.quests[quest] = "complete"
        return f"Completed {details['name']}. Earned {details['reward']} credits."

    def _at_water(self):
        scene = world.Scene(self.body.scene)
        x, y = int(self.body.x), int(self.body.y)
        return not scene.indoors and (scene.at(x, y) == "D" or any(
            scene.at(x + dx, y + dy) == "~" for dx, dy in DIRECTIONS))

    def _fish(self):
        if not self._at_water():
            raise ActionError("Fish from the dock or a walkable tile beside the lake.")
        if "fishing_rod" not in self.gear:
            raise ActionError("Buy a fishing rod first.")
        if self.fish_stock <= 0:
            raise ActionError("This part of the lake is fished out. Stocks recover tomorrow.")
        if self.body.needs["energy"] < 15:
            raise ActionError("Rest before fishing.")
        self._take("bait")
        self.tick(45, effort=0.5)
        chance = min(0.9, 0.65 + self.skills["fishing"] * 0.02)
        if self.weather == "storm":
            chance -= 0.25
        self.skills["fishing"] += 1
        if self.rng.random() < chance:
            self.inventory["fish"] += 1
            self.fish_stock -= 1
            return "Caught a lake trout. Cook it, sell it, or save it for Nessa."
        return "The fish escaped. You used one bait and gained fishing experience."

    @staticmethod
    def _clear_shot(x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx - dy
        while (x0, y0) != (x1, y1):
            twice = 2 * error
            if twice > -dy:
                error -= dy
                x0 += sx
            if twice < dx:
                error += dx
                y0 += sy
            if world.grid_get(world.EXTERIOR, x0, y0) in ("T", "#"):
                return False
        return True

    def huntable(self, animal):
        return (self.body.scene == "outside"
                and self._distance(animal["x"], animal["y"]) <= 6
                and self._clear_shot(int(self.body.x), int(self.body.y),
                                     animal["x"], animal["y"]))

    def _hunt(self, target=None):
        if self.body.scene != "outside":
            raise ActionError("Hunt outdoors in the woodland.")
        if "bow" not in self.gear:
            raise ActionError("Buy a bow first.")
        if self.body.needs["energy"] < 25:
            raise ActionError("Rest before hunting.")
        candidates = [a for a in self.animals if self.huntable(a)
                      and (target is None or a["id"] == target)]
        if not candidates:
            raise ActionError("Move within six tiles of an animal with no trees blocking the shot.")
        animal = min(candidates, key=lambda a: self._distance(a["x"], a["y"]))
        distance = self._distance(animal["x"], animal["y"])
        self._take("arrows")
        self.tick(60, effort=1.5)
        strength = self.body.physiology.organs["arms"] / ORGANS["arms"][1]
        chance = clamp((0.75 + self.skills["hunting"] * 0.025
                        - distance * 0.035) * strength, 0.15, 0.95)
        if self.weather in ("rain", "storm"):
            chance -= 0.1
        self.skills["hunting"] += 1
        if self.rng.random() < chance:
            self.animals.remove(animal)
            self.inventory["raw_meat"] += 2
            self.inventory["pelt"] += 1
            message = f"Hunted a {animal['kind']}: two portions of meat and one pelt."
        else:
            message = "Your shot missed. The animal moved on; one arrow was spent."
        if animal["kind"] == "deer" and self.rng.random() < 0.2:
            self.body.physiology.hurt("legs", 18)
            self.body.physiology.hurt("skin", 8)
            self.body.physiology.bleeding += 3
            message += " You were injured in the pursuit. Use a bandage."
        return message

    def _require_woodland(self):
        scene = world.Scene(self.body.scene)
        x, y = int(self.body.x), int(self.body.y)
        near_tree = any(scene.at(x + dx, y + dy) == "T"
                        for dx in range(-2, 3) for dy in range(-2, 3))
        if scene.indoors or not near_tree:
            raise ActionError("Find a patch of woodland within two tiles of a pine.")
        if self.body.needs["energy"] < 15:
            raise ActionError("Rest before gathering in the woods.")

    def _forage(self):
        self._require_woodland()
        self.tick(40, effort=1)
        item = self.rng.choice(("berries", "berries", "herbs"))
        amount = 1 + min(2, self.skills["foraging"] // 5)
        self.inventory[item] += amount
        self.skills["foraging"] += 1
        return f"Foraged {amount} {item}. Berries are edible; herbs can be sold."

    def _gather_wood(self):
        self._require_woodland()
        self.tick(30, effort=1)
        self.inventory["firewood"] += 2
        return "Gathered two bundles of fallen wood."

    def _eat(self, item="meal"):
        nutrition = {"meal": 55, "berries": 20, "cooked_fish": 45,
                     "cooked_meat": 55, "fish": 35, "raw_meat": 35}
        if item not in nutrition:
            raise ActionError("Choose food from your inventory.")
        absorption = 0.4 + 0.6 * self.body.physiology.organs["stomach"] / ORGANS["stomach"][1]
        nourishment = nutrition[item] * absorption
        if item == "meal":
            if self.body.food <= 0:
                raise ActionError("No prepared meals left. Cook, forage or buy groceries.")
            self.body.eat(nourishment)
        else:
            self._take(item)
            self.body.needs["satiety"] = min(
                100, self.body.needs["satiety"] + nourishment)
        if item in ("fish", "raw_meat") and self.rng.random() < 0.75:
            self.body.physiology.infect("food_poisoning")
        self.tick(15)
        return "Ate " + item.replace("_", " ") + (
            ". Raw food risks food poisoning." if item in ("fish", "raw_meat") else ".")

    def _drink(self, unsafe=False):
        if not isinstance(unsafe, bool):
            raise ActionError("Choose bottled water or raw lake water.")
        if unsafe:
            if not self._at_water():
                raise ActionError("Raw lake water is only available beside the lake.")
            if self.rng.random() < 0.75:
                self.body.physiology.infect("food_poisoning")
        else:
            self._take("water")
        self.body.physiology.hydration = min(100, self.body.physiology.hydration + 35)
        self.tick(5)
        return "Drank " + ("unsafe lake water. Illness is possible." if unsafe else "safe bottled water.")

    def _refill(self):
        if self.body.scene not in ("cabin", "cafe"):
            raise ActionError("Refill safe water at your cabin well or the cafe.")
        self.tick(15)
        self.inventory["water"] += 3
        return "Filled three bottles with safe water."

    def _equip(self, item=None):
        if item not in CLOTHING or item not in self.gear:
            raise ActionError("Choose clothing you own. Mira sells winter coats.")
        self.body.physiology.clothing = item
        self.tick(2)
        return "Changed into " + CLOTHING[item]["name"].lower() + "."

    def _require_stove(self):
        if not self._near_poi("stove"):
            raise ActionError("Move within two tiles of a stove in the cabin or lookout.")

    def _light_fire(self):
        self._require_stove()
        self._take("firewood")
        self.fires[self.body.scene] = max(
            self.clock, self.fires.get(self.body.scene, 0)) + 3 * 60
        self.tick(5)
        return "The stove burns for three more hours. It warms the room and dries clothing."

    def _cook(self, item=None):
        self._require_stove()
        if self.fires.get(self.body.scene, 0) < self.clock + 30:
            raise ActionError("Light the stove with enough fuel for a 30-minute cooking session.")
        cooked = {"fish": "cooked_fish", "raw_meat": "cooked_meat"}
        if item not in cooked:
            raise ActionError("Choose raw fish or meat to cook.")
        self._take(item)
        self.tick(30)
        self.inventory[cooked[item]] += 1
        return "Cooked " + item.replace("_", " ") + ". Safe to eat now."

    def _bandage(self):
        physiology = self.body.physiology
        if not physiology.bleeding and all(
                physiology.organs[key] >= ORGANS[key][1]
                for key in ("skin", "arms", "legs")):
            raise ActionError("You have no wound that needs bandaging.")
        self._take("bandage")
        physiology.bleeding = 0
        physiology.infection_exposure = 0
        for key in ("skin", "arms", "legs"):
            physiology.heal(key, 8)
        self.tick(10)
        return "Bandaged your wounds. Bleeding stopped; damaged organs still need recovery."

    def _medicine(self):
        if not self.body.physiology.illnesses:
            raise ActionError("You have no illness to treat.")
        self._take("medicine")
        self.body.physiology.medicate()
        self.tick(10)
        return "Treatment reduced the illness. Rest and hydrate while it clears."

    def _clinic(self):
        self._require_npc("jun")
        if self.body.money < 25:
            raise ActionError("Jun's treatment costs 25 credits.")
        self.ledger.record({"type": "treatment", "credits": 25})
        self.body.money -= 25
        physiology = self.body.physiology
        physiology.bleeding = 0
        physiology.infection_exposure = 0
        physiology.medicate()
        physiology.hydration = min(100, physiology.hydration + 30)
        physiology.blood = min(100, physiology.blood + 15)
        self.tick(60, resting=True)
        for key in ORGANS:
            physiology.heal(key, 6)
        return "Jun treated your wounds and illness. Your remaining organ damage heals with good care."

    def _wash(self):
        if self.body.scene not in ("cabin", "cafe", "chapel"):
            raise ActionError("Wash at home, the cafe or Jun's clinic.")
        self.body.wash()
        self.body.physiology.infection_exposure = 0
        self.tick(20)
        return "Washed and cleaned your wounds."

    def _rest(self):
        self.tick(60, resting=True)
        return "Rested for an hour. Shelter, food and water help your organs recover."

    def _sleep(self):
        if not self._near_poi("bed"):
            raise ActionError("Move within two tiles of your cabin bed before sleeping.")
        self.body.asleep = True
        try:
            self.tick(8 * 60)
        finally:
            self.body.asleep = False
        return "Slept for eight hours. Check hunger and hydration before heading out."

    def _wait(self, minutes=60):
        minutes = _integer(minutes, "Waiting time", 1, 480)
        self.tick(minutes)
        return f"Waited {minutes} game minutes."

    def _begin_book(self, topic=None, title=None):
        topic = _text(topic, "Book topic")
        if title is not None:
            title = _text(title, "Book title", 100)
        if self.current_book:
            raise ActionError("Finish your current book before starting another.")
        self.current_book = mind.new_book_from_request(
            topic, title, self.traits, self.body.name, self.research_notes)
        self.tick(10)
        return "Started " + self.current_book.title + ". You choose every writing session."

    def _write(self):
        if not self._near_poi("desk"):
            raise ActionError("Move within two tiles of your cabin desk to write.")
        if not self.current_book:
            raise ActionError("Start a book first.")
        if not self.body.can_write():
            raise ActionError("Writing needs energy 30, satiety 15, health 300 HP and paper.")
        self.tick(120)
        self._finish_writing_session()
        self.mind.on_activity("write", self)
        return "Writing session complete. Finished books appear below with download links."

    def _research(self, topic=None):
        topic = _text(topic, "Research topic")
        if self.body.scene != "library":
            raise ActionError("Visit the library to research.")
        self.tick(150)
        self.plan.research_requests.append(topic)
        self._complete({"do": "research"})
        return "Research notes saved for your next book."

    def _read(self):
        if self.body.scene not in ("cabin", "library", "cafe", "lookout_cabin"):
            raise ActionError("Find a sheltered place with books.")
        self.tick(60)
        self._complete({"do": "read"})
        return "Read for an hour. Inspiration restored."

    def to_dict(self):
        data = super().to_dict()
        data["mode"] = "player"
        data["player"] = {
            "inventory": dict(self.inventory), "gear": sorted(self.gear),
            "skills": dict(self.skills), "relationships": dict(self.relationships),
            "last_talk": dict(self.last_talk), "quests": dict(self.quests),
            "fires": dict(self.fires), "fish_stock": self.fish_stock,
            "animals": [dict(animal) for animal in self.animals],
            "animal_serial": self.animal_serial,
            "next_weather": self.next_weather, "next_roam": self.next_roam,
            "rng_state": self.rng.getstate(), "log": list(self.log),
        }
        return data

    def _restore(self, data):
        super()._restore(data)
        player = data.get("player", {})
        for key in ("inventory", "skills", "relationships", "quests"):
            getattr(self, key).update(player.get(key, {}))
        self.gear = set(player.get("gear", self.gear))
        self.gear.add(self.body.physiology.clothing)
        self.last_talk = player.get("last_talk", {})
        self.fires = player.get("fires", {})
        self.fish_stock = player.get("fish_stock", 10)
        self.animals = player.get("animals", self.animals)
        self.animal_serial = player.get("animal_serial", self.animal_serial)
        self.next_weather = max(self.clock, player.get("next_weather", self.clock + 360))
        self.next_roam = max(self.clock, player.get("next_roam", self.clock + 30))
        if "rng_state" in player:
            version, state, gaussian = player["rng_state"]
            self.rng.setstate((version, tuple(state), gaussian))
        self.log = deque(player.get("log", list(self.log)), maxlen=400)
        self.body.x, self.body.y = int(self.body.x), int(self.body.y)
        self.activity = None
        self.body.asleep = False
        self.say("world", "Your saved life is restored. You are in control.")

    def snapshot(self):
        b = self.body
        physiology = b.physiology
        scene = world.Scene(b.scene)
        organs = [{"id": key, "name": info[0], "hp": round(physiology.organs[key], 1),
                   "max": info[1], "vital": info[2]} for key, info in ORGANS.items()]
        catalogue = {**{key: economy.STORE_CATALOG[key] for key in PLAYER_STORE_ITEMS},
                     **SURVIVAL_CATALOG}
        return {
            "time": self.clock_str(), "day": self.day, "season": self.season,
            "weather": self.weather, "environment": self.environment(),
            "hour": (self.clock % config.DAY_MINUTES) / 60,
            "player": {
                "name": b.name, "scene": b.scene, "x": b.x, "y": b.y,
                "facing": b.facing, "needs": dict(b.needs),
                "hp": round(physiology.hp, 1), "max_hp": MAX_HP,
                "organs": organs, "alive": physiology.alive,
                "hydration": round(physiology.hydration, 1),
                "temperature": round(physiology.temperature, 2),
                "wetness": round(physiology.wetness, 1),
                "blood": round(physiology.blood, 1),
                "bleeding": physiology.bleeding, "conditions": physiology.conditions,
                "clothing": physiology.clothing, "money": round(b.money, 2),
                "meals": b.food, "inventory": dict(self.inventory),
                "gear": sorted(self.gear), "paper": b.supplies.get("paper", 0),
            },
            "scene": {"key": scene.key, "name": scene.name, "grid": scene.grid,
                      "indoors": scene.indoors, "points": scene.poi},
            "world": {
                "grid": world.EXTERIOR,
                "locations": [{"id": key, "name": info["name"],
                               "door": world.door_positions(key)[0]
                               if info["indoors"] else None}
                              for key, info in world.LOCATIONS.items()],
            },
            "npcs": [self.npc_state(key) for key in NPCS],
            "animals": [{**animal, "huntable": self.huntable(animal)}
                        for animal in self.animals],
            "skills": dict(self.skills),
            "quests": [{"id": key, **details, "status": self.quests[key]}
                       for key, details in QUESTS.items()],
            "catalogue": [{"id": key, "cost": product["cost"],
                           "description": product["desc"],
                           "owned": key in self.gear or (
                               product.get("kind") == "furniture"
                               and bool(b.furniture.get(key)))}
                          for key, product in catalogue.items()],
            "sell_prices": SELL_PRICES, "clothing": CLOTHING,
            "stations": {key: self._near_poi(key) for key in ("bed", "stove", "desk")},
            "at_water": self._at_water(),
            "fire_minutes": max(0, int(self.fires.get(b.scene, 0) - self.clock)),
            "fish_stock": self.fish_stock,
            "book": {"title": self.current_book.title,
                     "words": self.current_book.words,
                     "target": self.current_book.target_words}
                    if self.current_book else None,
            "books": [{"title": book["title"], "words": book["words"],
                       "file": book["zip"].replace("\\", "/").rsplit("/", 1)[-1]}
                      for book in self.finished_books],
            "log": list(self.log)[-18:],
        }

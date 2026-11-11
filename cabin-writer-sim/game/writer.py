"""The writer's body: needs, health, position, and the slow physics of a
life — hunger, exhaustion, loneliness. Nothing here is optional for the AI;
these are hard constraints the mind must plan around."""

import random
from . import config


NEEDS = ("satiety", "energy", "hygiene", "inspiration", "social", "mood")


class Body:
    def __init__(self, name=config.DEFAULT_WRITER_NAME):
        self.name = name
        self.needs = {
            "satiety": 80.0,     # 0 = starving
            "energy": 85.0,      # 0 = collapse
            "hygiene": 70.0,     # 0 = wretched
            "inspiration": 55.0, # 0 = the blank page wins
            "social": 45.0,      # 0 = utterly alone
            "mood": 50.0,        # 0 = despair, 100 = rare bright day
        }
        self.health = 90.0
        self.money = config.STARTING_MONEY
        self.food = config.STARTING_FOOD      # meals in the pantry
        self.supplies = {"lamp_oil": 2, "paper": 10, "coffee": 1}
        self.furniture = {"desk": 1, "bed": 1, "chair": 1,
                          "lamp": 1, "stove": 1, "bookshelf": 1}
        self.asleep = False

        # position within current scene (tile coords, float for smooth walk)
        self.scene = "cabin"
        self.x, self.y = 4.0, 5.0
        self.facing = "down"
        self.walk_phase = 0.0
        self.moving = False

    # ------------------------------------------------------------- needs ---
    def decay(self, hours, traits):
        d = config.DECAY
        n = self.needs
        n["satiety"] = max(0.0, n["satiety"] - d["satiety"] * hours)
        if self.asleep:
            n["energy"] = min(100.0, n["energy"] + config.SLEEP_RECOVERY * hours)
            # sleep is the body's repair shift — but you cannot heal past
            # an empty stomach
            cap = min(100.0, max(65.0, n["satiety"]))
            self.health = min(cap, self.health + 3.0 * hours)
        else:
            n["energy"] = max(0.0, n["energy"] - d["energy"] * hours)
        n["hygiene"] = max(0.0, n["hygiene"] - d["hygiene"] * hours)
        n["inspiration"] = max(0.0, n["inspiration"] - d["inspiration"] * hours)
        # solitude-loving minds lose social need more slowly
        social_decay = d["social"] * (1.0 - 0.6 * traits.get("solitude", 0.0))
        n["social"] = max(0.0, n["social"] - social_decay * hours)

        # health follows the body's worst failures
        if n["satiety"] <= 5 or n["energy"] <= 3:
            self.health = max(0.0, self.health - config.HEALTH_DECAY * hours)
        elif self.health < 100:
            floor = min(100.0, max(60.0, (n["satiety"] + n["energy"]) / 2))
            self.health = min(floor, self.health + 1.5 * hours)

    def drift_mood(self, hours, weather, traits):
        """Mood slides toward a baseline set by weather, health, and the
        writer's melancholy. Rain is not unpleasant to everyone."""
        n = self.needs
        base = 42.0
        if weather == "rain":
            base -= 8 * (1 - traits.get("melancholy", 0.5))  # gloom weighs
            base += 6 * traits.get("melancholy", 0.5)        # ...or nourishes
        elif weather == "fog":
            base -= 4
        elif weather == "snow":
            base -= 2
        elif weather == "clear":
            base += 6
        base += (self.health - 60) * 0.15
        base += (n["social"] - 50) * 0.08
        delta = (base - n["mood"]) * 0.15 * hours
        n["mood"] = max(0.0, min(100.0, n["mood"] + delta))

    # ----------------------------------------------------------- actions ---
    def eat(self):
        if self.food <= 0:
            return False
        self.food -= 1
        self.needs["satiety"] = min(100.0, self.needs["satiety"] + 55)
        return True

    def wash(self):
        self.needs["hygiene"] = 100.0

    def rest_eyes(self):
        self.needs["energy"] = min(100.0, self.needs["energy"] + 8)

    # ----------------------------------------------------------- helpers ---
    def worst_need(self):
        n = self.needs
        order = ("satiety", "energy", "hygiene")
        return min(order, key=lambda k: n[k])

    def can_write(self):
        n = self.needs
        return (n["energy"] >= 30 and n["satiety"] >= 15
                and self.health >= 30 and self.supplies.get("paper", 0) > 0)

    def condition_summary(self):
        n = self.needs
        return (f"health {self.health:.0f} | satiety {n['satiety']:.0f} | "
                f"energy {n['energy']:.0f} | hygiene {n['hygiene']:.0f} | "
                f"inspiration {n['inspiration']:.0f} | social {n['social']:.0f} | "
                f"mood {n['mood']:.0f} | money {self.money:.2f}cr | "
                f"food {self.food} meals | paper {self.supplies.get('paper', 0)}")

    def to_dict(self):
        return {
            "name": self.name, "needs": dict(self.needs),
            "health": self.health, "money": self.money, "food": self.food,
            "supplies": dict(self.supplies), "furniture": dict(self.furniture),
            "scene": self.scene, "x": self.x, "y": self.y,
        }

    @classmethod
    def from_dict(cls, data):
        b = cls(data.get("name", config.DEFAULT_WRITER_NAME))
        b.needs.update(data.get("needs", {}))
        b.health = data.get("health", 90.0)
        b.money = data.get("money", config.STARTING_MONEY)
        b.food = data.get("food", config.STARTING_FOOD)
        b.supplies.update(data.get("supplies", {}))
        b.furniture.update(data.get("furniture", {}))
        b.scene = data.get("scene", "cabin")
        b.x = data.get("x", 4.0)
        b.y = data.get("y", 5.0)
        return b

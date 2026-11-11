"""Organ health and environmental survival rules (fictional game mechanics)."""

import math


# name, maximum HP, vital: losing a vital organ ends the life.
ORGANS = {
    "brain": ("Brain", 120, True),
    "heart": ("Heart", 160, True),
    "lungs": ("Lungs", 150, True),
    "liver": ("Liver", 100, False),
    "kidneys": ("Kidneys", 100, False),
    "stomach": ("Stomach", 90, False),
    "skin": ("Skin", 100, False),
    "arms": ("Arms", 80, False),
    "legs": ("Legs", 100, False),
}
MAX_HP = sum(organ[1] for organ in ORGANS.values())

CLOTHING = {
    "light_clothes": {
        "name": "Light clothes", "insulation": 0.5, "waterproof": 0.05,
        "description": "Thin, breathable layers. Best in warm weather.",
    },
    "raincoat": {
        "name": "Raincoat", "insulation": 1.5, "waterproof": 0.9,
        "description": "Moderate insulation; keeps most rain off.",
    },
    "winter_coat": {
        "name": "Thick winter coat", "insulation": 3.6, "waterproof": 0.6,
        "description": "Heavy insulation. Can overheat you in summer.",
    },
}

ILLNESSES = {
    "food_poisoning": {
        "name": "Food poisoning", "duration": 18 * 60,
        "damage": {"stomach": 7, "liver": 2},
    },
    "wound_infection": {
        "name": "Wound infection", "duration": 36 * 60,
        "damage": {"skin": 5, "lungs": 3, "liver": 2},
    },
}


def clamp(value, low, high):
    return max(low, min(high, value))


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise ValueError(f"Invalid saved {name}: expected a finite number.")
    return float(value)


class Physiology:
    def __init__(self):
        self.organs = {key: float(info[1]) for key, info in ORGANS.items()}
        self.hydration = 90.0
        self.temperature = 37.0
        self.wetness = 0.0
        self.blood = 100.0
        self.bleeding = 0.0
        self.clothing = "raincoat"
        self.illnesses = {}
        self.infection_exposure = 0.0

    @property
    def hp(self):
        return sum(self.organs.values())

    @property
    def alive(self):
        return all(self.organs[key] > 0 for key, info in ORGANS.items()
                   if info[2])

    @property
    def conditions(self):
        result = [ILLNESSES[key]["name"] for key in self.illnesses]
        if self.temperature < 35:
            result.append("Hypothermia")
        elif self.temperature < 36:
            result.append("Cold")
        if self.temperature > 38.5:
            result.append("Heat illness")
        elif self.temperature > 37.8:
            result.append("Hot")
        if self.hydration < 20:
            result.append("Dehydration")
        if self.bleeding:
            result.append("Bleeding")
        if self.blood < 70:
            result.append("Blood loss")
        for key, info in ORGANS.items():
            if self.organs[key] <= 0 and info[2]:
                result.append(f"{info[0]} failure")
            elif self.organs[key] < info[1] * 0.25:
                result.append(f"Severe {info[0].lower()} damage")
        return result

    def set_health(self, percent):
        """Keep the original 0-100 Body.health API without erasing injuries."""
        target = clamp(percent, 0, 100) * MAX_HP / 100
        current = self.hp
        if target < current:
            ratio = target / current
            self.organs = {key: hp * ratio
                           for key, hp in self.organs.items()}
        elif target > current:
            missing = MAX_HP - current
            for key, info in ORGANS.items():
                self.organs[key] += ((info[1] - self.organs[key])
                                     * (target - current) / missing)

    def hurt(self, key, damage):
        self.organs[key] = max(0.0, self.organs[key] - damage)

    def heal(self, key, amount):
        self.organs[key] = min(ORGANS[key][1], self.organs[key] + amount)

    def infect(self, key, severity=1.0):
        previous = self.illnesses.get(key, {})
        self.illnesses[key] = {
            "remaining": float(ILLNESSES[key]["duration"]),
            "severity": max(severity, previous.get("severity", 0)),
            "treated": False,
        }

    def medicate(self):
        for illness in self.illnesses.values():
            illness["treated"] = True
            illness["severity"] *= 0.35
            illness["remaining"] = min(illness["remaining"], 120)

    def update(self, hours, environment, needs, effort=0, asleep=False):
        clothes = CLOTHING[self.clothing]
        rain = environment["precipitation"]
        if not environment["indoors"] and rain:
            self.wetness = clamp(
                self.wetness + rain * (1 - clothes["waterproof"]) * hours,
                0, 100)
        else:
            drying = 45 if environment["heated"] else 12
            self.wetness = max(0, self.wetness - drying * hours)

        air = environment["temperature"]
        insulation = clothes["insulation"] * (1 - self.wetness * 0.007)
        comfort = (air + insulation * 5
                   - environment["wind"] * 0.22 - self.wetness * 0.04)
        target = 37.0
        if comfort < 10:
            target += (comfort - 10) / 9
        elif comfort > 28:
            target += (comfort - 28) / 7
        if "wound_infection" in self.illnesses:
            target += self.illnesses["wound_infection"]["severity"] * 0.8
        target = clamp(target, 32, 41)
        self.temperature += (target - self.temperature) * min(1, hours * 0.65)

        kidney_damage = 1 - self.organs["kidneys"] / ORGANS["kidneys"][1]
        thirst = 4 + effort * 2 + max(0, air - 24) * 0.35 + kidney_damage * 2
        self.hydration = max(0, self.hydration - thirst * hours)
        self.blood = max(0, self.blood - self.bleeding * hours)
        if not self.bleeding and self.hydration > 35 and needs["satiety"] > 25:
            self.blood = min(100, self.blood + hours)

        if self.temperature < 35:
            cold = (35 - self.temperature) * hours
            for key, rate in (("brain", 5), ("heart", 7),
                              ("skin", 3), ("legs", 4)):
                self.hurt(key, cold * rate)
        if self.temperature > 38.5:
            heat = (self.temperature - 38.5) * hours
            for key, rate in (("brain", 6), ("heart", 6),
                              ("kidneys", 9), ("skin", 2)):
                self.hurt(key, heat * rate)
        if self.hydration < 15:
            dehydration = (15 - self.hydration) * hours
            self.hurt("kidneys", dehydration * 1.2)
            self.hurt("heart", dehydration * 0.3)
        if self.blood < 70:
            loss = (70 - self.blood) * hours
            self.hurt("heart", loss * 0.6)
            self.hurt("brain", loss * 0.4)
        if needs["satiety"] <= 5:
            for key, rate in (("stomach", 6), ("liver", 3), ("heart", 3)):
                self.hurt(key, rate * hours)
        if needs["energy"] <= 3:
            self.hurt("brain", 3 * hours)
            self.hurt("heart", 2 * hours)

        if self.bleeding and needs["hygiene"] < 30:
            self.infection_exposure += (30 - needs["hygiene"]) * hours
            if self.infection_exposure >= 50 \
                    and "wound_infection" not in self.illnesses:
                self.infect("wound_infection")
        else:
            self.infection_exposure = max(0, self.infection_exposure - hours * 5)

        for key, illness in list(self.illnesses.items()):
            active_hours = min(hours, illness["remaining"] / 60)
            toxin_load = 2 - self.organs["liver"] / ORGANS["liver"][1]
            for organ, rate in ILLNESSES[key]["damage"].items():
                self.hurt(organ, rate * illness["severity"] * active_hours * toxin_load)
            if key == "food_poisoning":
                self.hydration = max(
                    0, self.hydration - 5 * illness["severity"] * active_hours)
            illness["remaining"] -= hours * 60
            if illness["remaining"] <= 0:
                del self.illnesses[key]

        if (self.alive and not self.illnesses and not self.bleeding
                and 36 <= self.temperature <= 38
                and self.hydration > 35 and needs["satiety"] > 35
                and needs["energy"] > 25):
            recovery = 0.7 if asleep else 0.15
            for key in ORGANS:
                self.heal(key, recovery * hours)

    def to_dict(self):
        return {
            "organs": dict(self.organs), "hydration": self.hydration,
            "temperature": self.temperature, "wetness": self.wetness,
            "blood": self.blood, "bleeding": self.bleeding,
            "clothing": self.clothing,
            "illnesses": {key: dict(value)
                         for key, value in self.illnesses.items()},
            "infection_exposure": self.infection_exposure,
        }

    @classmethod
    def from_dict(cls, data):
        body = cls()
        for key, value in data.get("organs", {}).items():
            if key not in ORGANS:
                raise ValueError(f"Unknown saved organ: {key}.")
            body.organs[key] = clamp(_number(value, key), 0, ORGANS[key][1])
        for key, low, high in (
            ("hydration", 0, 100), ("temperature", 25, 45),
            ("wetness", 0, 100), ("blood", 0, 100),
            ("bleeding", 0, 100), ("infection_exposure", 0, 1000),
        ):
            setattr(body, key, clamp(
                _number(data.get(key, getattr(body, key)), key), low, high))
        body.clothing = data.get("clothing", body.clothing)
        if body.clothing not in CLOTHING:
            raise ValueError("Unknown saved clothing.")
        for key, illness in data.get("illnesses", {}).items():
            if key not in ILLNESSES:
                raise ValueError(f"Unknown saved illness: {key}.")
            body.illnesses[key] = {
                "remaining": max(0, _number(illness["remaining"], key)),
                "severity": clamp(_number(illness["severity"], key), 0, 2),
                "treated": bool(illness.get("treated", False)),
            }
        return body

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from game.player import ActionError, GameOver, NPCS, PlayerSim
from game.sim import Sim, _bfs
from game.survival import ORGANS, Physiology
from game.world import Scene
from game.writer import Body


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="cabin-player-test-")
        self.game = PlayerSim(out_dir=self.directory.name, seed=7)

    def tearDown(self):
        self.directory.cleanup()

    def place(self, scene, x, y):
        self.game.body.scene = scene
        self.game.body.x, self.game.body.y = x, y

    def test_direct_controls_do_not_delegate_to_the_mind(self):
        initial = self.game.snapshot()["player"]
        self.assertEqual(initial["hp"], 1000)
        self.assertEqual(sum(organ["hp"] for organ in initial["organs"]), 1000)
        with patch.object(self.game.mind, "decide", side_effect=AssertionError("AI took control")):
            self.game.act("move", dx=0, dy=1)
            self.game.act("move", dx=0, dy=1)
            self.assertEqual(self.game.body.scene, "outside")
            self.game.act("move", dx=0, dy=1)
            self.game.act("move", dx=0, dy=-1)
            self.assertEqual(self.game.body.scene, "cabin")
            position = (self.game.body.x, self.game.body.y)
            self.game.act("wait", minutes=30)
        self.assertEqual((self.game.body.x, self.game.body.y), position)
        self.assertIsNone(self.game.activity)
        self.assertIsNone(self.game.current_book)

    def test_invalid_movement_and_inputs_do_not_spend_time_or_resources(self):
        start = self.game.clock
        inventory = dict(self.game.inventory)
        for action, parameters in (
            ("move", {"dx": 1, "dy": 1}),
            ("move", {"dx": True, "dy": 0}),
            ("move", {"dx": 0.5, "dy": 0}),
            ("buy", {"item": []}),
            ("wait", {"minutes": -1}),
            ("wait", {"minutes": 500}),
            ("fish", {}),
            ("top_up", {"amount": 100}),
            ("move", {"dx": 0, "dy": 1, "extra": 1}),
        ):
            with self.subTest(action=action, parameters=parameters):
                with self.assertRaises(ActionError):
                    self.game.act(action, **parameters)
        self.assertEqual(self.game.clock, start)
        self.assertEqual(self.game.inventory, inventory)
        self.assertEqual(self.game.log[-1]["who"], "notice")
        self.place("cabin", 1, 1)
        with self.assertRaisesRegex(ActionError, "blocked"):
            self.game.act("move", dx=-1, dy=0)

    def test_the_map_and_all_villagers_are_reachable(self):
        for key, npc in NPCS.items():
            with self.subTest(villager=key):
                self.game.act("travel", destination=npc["scene"])
                scene = Scene(self.game.body.scene)
                start = (int(self.game.body.x), int(self.game.body.y))
                reachable = [(x, y) for y in range(scene.height) for x in range(scene.width)
                             if abs(x - npc["x"]) + abs(y - npc["y"]) <= 2
                             and _bfs(scene, start, (x, y))]
                self.assertTrue(reachable)
                x, y = min(reachable, key=lambda point: abs(point[0] - start[0]) + abs(point[1] - start[1]))
                self.game.act("walk_to", x=x, y=y)
                self.assertTrue(self.game.npc_state(key)["nearby"])
                self.assertIn(npc["name"], self.game.act("talk", npc=key))
        self.game.act("travel", destination="lakeshore")
        self.assertTrue(self.game.snapshot()["at_water"])

    def test_npcs_keep_hours_and_require_proximity(self):
        with self.assertRaisesRegex(ActionError, "within two"):
            self.game.act("talk", npc="mira")
        self.place("store", 4, 4)
        self.game.clock = 21 * 60
        with self.assertRaisesRegex(ActionError, "away"):
            self.game.act("buy", item="bread")
        self.assertEqual(self.game.body.money, 140)

    def test_market_transactions_and_ownership_are_ledgered(self):
        self.place("store", 4, 4)
        self.game.act("buy", item="winter_coat")
        self.assertEqual(self.game.body.money, 95)
        self.game.act("equip", item="winter_coat")
        self.assertEqual(self.game.body.physiology.clothing, "winter_coat")
        with self.assertRaisesRegex(ActionError, "already own"):
            self.game.act("buy", item="winter_coat")
        self.game.act("buy", item="groceries")
        self.assertEqual(self.game.body.food, 8)
        self.game.inventory["fish"] = 2
        self.game.act("sell", item="fish", amount=2)
        self.assertEqual(self.game.inventory["fish"], 0)
        self.assertEqual(self.game.body.money, 93)
        with self.assertRaises(ActionError):
            self.game.act("sell", item="fish", amount=1)
        entries = [json.loads(line) for line in Path(self.game.ledger.path).read_text().splitlines()]
        self.assertEqual([entry["type"] for entry in entries], ["purchase", "purchase", "sale"])
        self.game.body.money = 0
        with self.assertRaisesRegex(ActionError, "credits"):
            self.game.act("buy", item="medicine")
        self.assertEqual(self.game.inventory["medicine"], 1)

    def test_fishing_quest_consumes_bait_stock_and_delivery_once(self):
        self.place("outside", 9, 24)
        self.game.act("accept_quest", quest="fish_supper")
        with patch.object(self.game.rng, "random", return_value=0):
            self.game.act("fish")
            self.game.act("fish")
        self.assertEqual(self.game.inventory["bait"], 6)
        self.assertEqual(self.game.fish_stock, 8)
        self.assertEqual(self.game.skills["fishing"], 2)
        self.game.act("deliver_quest", quest="fish_supper")
        self.assertEqual(self.game.inventory["fish"], 0)
        self.assertEqual(self.game.body.money, 164)
        with self.assertRaises(ActionError):
            self.game.act("deliver_quest", quest="fish_supper")
        self.assertEqual(self.game.body.money, 164)

    def test_player_shop_only_offers_functional_items_and_upgrades_once(self):
        self.place("store", 4, 4)
        self.game.act("buy", item="typewriter")
        self.assertTrue(self.game.body.furniture["typewriter"])
        self.assertEqual(self.game.body.money, 20)
        self.game.body.money = 140
        with self.assertRaisesRegex(ActionError, "already own"):
            self.game.act("buy", item="typewriter")
        with self.assertRaisesRegex(ActionError, "does not stock"):
            self.game.act("buy", item="gramophone")
        catalogue = {item["id"]: item for item in self.game.snapshot()["catalogue"]}
        self.assertTrue(catalogue["typewriter"]["owned"])
        self.assertNotIn("gramophone", catalogue)

    def hunting_setup(self):
        scene = Scene("outside")
        x, y = next((x, y) for y in range(6, 21) for x in range(13, 44)
                    if self.game._wild_tile(scene, x, y) and scene.walkable(x - 1, y))
        self.place("outside", x - 1, y)
        self.game.animals = [{"id": 1, "kind": "rabbit", "x": x, "y": y}]
        self.game.next_roam = self.game.clock + 120
        self.game.weather = "clear"
        return x, y

    def test_hunting_yields_food_and_pelts_and_respects_arm_damage(self):
        x, y = self.hunting_setup()
        with patch.object(self.game.rng, "random", return_value=0.5):
            self.game.act("hunt", target=1)
        self.assertEqual(self.game.inventory["raw_meat"], 2)
        self.assertEqual(self.game.inventory["pelt"], 1)
        self.assertEqual(self.game.inventory["arrows"], 5)
        self.assertEqual(self.game.animals, [])
        self.game.animals = [{"id": 2, "kind": "rabbit", "x": x, "y": y}]
        self.game.body.physiology.hurt("arms", 72)
        self.game.next_roam = self.game.clock + 120
        with patch.object(self.game.rng, "random", return_value=0.5):
            self.assertIn("missed", self.game.act("hunt", target=2))
        self.assertEqual(self.game.inventory["raw_meat"], 2)

    def test_trees_block_hunting_without_spending_an_arrow(self):
        scene = Scene("outside")
        x, y = next((x, y) for y in range(6, 21) for x in range(13, 43)
                    if scene.at(x, y) == "T" and scene.walkable(x - 1, y)
                    and scene.walkable(x + 1, y))
        self.place("outside", x - 1, y)
        self.game.animals = [{"id": 1, "kind": "deer", "x": x + 1, "y": y}]
        start = self.game.clock
        with self.assertRaisesRegex(ActionError, "trees"):
            self.game.act("hunt", target=1)
        self.assertEqual(self.game.inventory["arrows"], 6)
        self.assertEqual(self.game.clock, start)

    def test_cooking_requires_fuel_and_makes_the_catch_safe(self):
        self.place("cabin", 7, 4)
        self.game.inventory["fish"] = 1
        with self.assertRaisesRegex(ActionError, "Light the stove"):
            self.game.act("cook", item="fish")
        self.game.body.physiology.wetness = 80
        self.game.act("light_fire")
        self.game.act("cook", item="fish")
        self.assertEqual(self.game.inventory["fish"], 0)
        self.assertEqual(self.game.inventory["cooked_fish"], 1)
        self.assertLess(self.game.body.physiology.wetness, 60)
        with patch.object(self.game.rng, "random", return_value=0):
            self.game.act("eat", item="cooked_fish")
        self.assertFalse(self.game.body.physiology.illnesses)

    def test_fuel_display_does_not_round_up_an_insufficient_cooking_window(self):
        self.place("cabin", 7, 4)
        self.game.inventory["fish"] = 1
        self.game.fires["cabin"] = self.game.clock + 29.8
        self.assertEqual(self.game.snapshot()["fire_minutes"], 29)
        with self.assertRaisesRegex(ActionError, "enough fuel"):
            self.game.act("cook", item="fish")
        self.assertEqual(self.game.inventory["fish"], 1)

    def test_unsafe_water_causes_organ_damage_and_medicine_treats_it(self):
        self.place("outside", 9, 24)
        with patch.object(self.game.rng, "random", return_value=0):
            self.game.act("drink", unsafe=True)
        physiology = self.game.body.physiology
        self.assertIn("food_poisoning", physiology.illnesses)
        self.assertLess(physiology.organs["stomach"], 90)
        self.game.act("medicine")
        self.assertEqual(self.game.inventory["medicine"], 0)
        self.assertTrue(physiology.illnesses["food_poisoning"]["treated"])
        self.game.act("wait", minutes=120)
        self.assertNotIn("food_poisoning", physiology.illnesses)

    def test_dirty_bleeding_wounds_infect_and_bandages_stop_bleeding(self):
        physiology = self.game.body.physiology
        physiology.hurt("skin", 15)
        physiology.bleeding = 3
        self.game.body.needs["hygiene"] = 0
        self.game.act("wait", minutes=120)
        self.assertIn("wound_infection", physiology.illnesses)
        self.game.act("bandage")
        self.assertEqual(physiology.bleeding, 0)
        self.assertEqual(self.game.inventory["bandage"], 1)
        self.place("chapel", 3, 3)
        self.game.act("clinic")
        self.assertEqual(self.game.body.money, 115)
        self.assertTrue(physiology.illnesses["wound_infection"]["treated"])

    def test_damaged_organs_affect_walking_and_food_absorption(self):
        self.game.body.physiology.hurt("legs", 90)
        start = self.game.clock
        self.game.act("move", dx=0, dy=1)
        self.assertGreater(self.game.clock - start, 1.8)
        self.game.body.physiology.hurt("stomach", 80)
        self.game.body.needs["satiety"] = 10
        self.game.act("eat", item="meal")
        self.assertLess(self.game.body.needs["satiety"], 40)

    def test_vital_organ_failure_is_fatal_despite_a_large_total_bar(self):
        self.game.body.physiology.hurt("heart", 160)
        snapshot = self.game.snapshot()["player"]
        self.assertEqual(snapshot["hp"], 840)
        self.assertFalse(snapshot["alive"])
        start = self.game.clock
        with self.assertRaises(GameOver):
            self.game.act("rest")
        self.assertEqual(self.game.clock, start)

    def test_save_restores_survival_inventory_quests_rng_and_book(self):
        self.game.act("begin_book", topic="the pinewood", title="My first day")
        self.game.inventory["fish"] = 2
        self.game.gear.add("winter_coat")
        self.game.quests["fish_supper"] = "active"
        self.game.relationships["nessa"] = 15
        self.game.fires["cabin"] = self.game.clock + 150
        self.game.body.physiology.wetness = 65
        self.game.body.physiology.hurt("legs", 20)
        self.game.body.physiology.infect("food_poisoning")
        path = self.game.save(str(Path(self.directory.name) / "player-save.json"))
        restored = PlayerSim.load(path, out_dir=self.directory.name)
        for attribute in ("clock", "weather", "inventory", "gear", "quests",
                          "relationships", "fires", "animals", "skills", "next_weather"):
            self.assertEqual(getattr(restored, attribute), getattr(self.game, attribute))
        self.assertEqual(restored.body.physiology.to_dict(), self.game.body.physiology.to_dict())
        self.assertEqual(restored.current_book.to_dict(), self.game.current_book.to_dict())
        self.assertEqual(restored.rng.getstate(), self.game.rng.getstate())
        self.assertEqual(restored.rng.random(), self.game.rng.random())

    def test_player_writing_publishes_real_books_without_autonomous_sessions(self):
        self.place("cabin", 3, 3)
        self.game.act("begin_book", topic="a quiet life", title="A Player's Notebook")
        self.game.current_book.target_words = 10
        self.game.act("write")
        self.assertIsNone(self.game.current_book)
        self.assertEqual(len(self.game.finished_books), 1)
        self.assertTrue(Path(self.game.finished_books[0]["zip"]).is_file())
        self.assertGreater(self.game.body.money, 140)
        self.assertEqual(self.game.body.supplies["paper"], 9)

    def test_legacy_body_saves_and_ai_decisions_still_work(self):
        legacy = Body.from_dict({"health": 67, "scene": "cabin"})
        self.assertAlmostEqual(legacy.physiology.hp, 670)
        simulation = Sim(out_dir=self.directory.name, seed=4)
        simulation.submit_command("write a book about rain")
        for _ in range(12):
            simulation.tick(30)
        self.assertIsNotNone(simulation.current_book)
        restored = Sim.load(simulation.save(), out_dir=self.directory.name)
        self.assertEqual(restored.body.to_dict(), simulation.body.to_dict())


class EnvironmentTests(unittest.TestCase):
    def expose(self, clothes, temperature, wind=6, wetness=0, rain=0):
        physiology = Physiology()
        physiology.clothing = clothes
        physiology.wetness = wetness
        environment = {"temperature": temperature, "wind": wind,
                       "precipitation": rain, "indoors": False, "heated": False}
        needs = {"satiety": 100, "energy": 100, "hygiene": 100}
        for _ in range(72):
            physiology.update(5 / 60, environment, needs)
        return physiology

    def test_cold_crosses_hypothermia_threshold_and_damages_specific_organs(self):
        thin = self.expose("light_clothes", -15, wind=30)
        protected = self.expose("winter_coat", -10, wind=16)
        self.assertLess(thin.temperature, 35)
        for key in ("brain", "heart", "skin", "legs"):
            self.assertLess(thin.organs[key], ORGANS[key][1])
        self.assertEqual(thin.organs["arms"], 80)
        self.assertGreater(protected.temperature, 35)
        self.assertEqual(protected.hp, 1000)

    def test_thick_clothes_cross_heat_illness_threshold_in_warm_weather(self):
        light = self.expose("light_clothes", 30)
        thick = self.expose("winter_coat", 30)
        self.assertLess(light.temperature, 38.5)
        self.assertEqual(light.hp, 1000)
        self.assertGreater(thick.temperature, 38.5)
        self.assertLess(thick.organs["kidneys"], 100)
        self.assertLess(thick.organs["heart"], 160)

    def test_wet_clothes_lose_cold_protection(self):
        dry = self.expose("winter_coat", -10, wind=16)
        wet = self.expose("winter_coat", -10, wind=16, wetness=90, rain=30)
        self.assertGreater(wet.wetness, 90)
        self.assertLess(wet.temperature, 35)
        self.assertLess(wet.hp, dry.hp)

    def test_kidney_and_liver_damage_have_functional_consequences(self):
        healthy, injured = Physiology(), Physiology()
        injured.hurt("kidneys", 80)
        injured.hurt("liver", 80)
        environment = {"temperature": 19, "wind": 0, "precipitation": 0,
                       "indoors": True, "heated": False}
        needs = {"satiety": 80, "energy": 80, "hygiene": 80}
        for physiology in (healthy, injured):
            physiology.infect("food_poisoning")
            physiology.update(1, environment, needs)
        self.assertLess(injured.hydration, healthy.hydration)
        self.assertLess(injured.organs["stomach"], healthy.organs["stomach"])


if __name__ == "__main__":
    unittest.main()

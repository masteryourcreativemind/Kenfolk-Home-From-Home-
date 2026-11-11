"""The pygame engine: renders the scene the writer is in, keeps the mood
(dim, rainy, lonely), and gives the user a window — never a steering wheel.
You type directives; the writer decides how a life absorbs them.

Controls:  type + ENTER  speak to the writer
           SPACE         pause          + / -   time speed
           F2            screenshot      ESC/Q   save & quit
"""

import math
import os
import random
import time

import pygame

from . import assets
from . import config
from .config import PALETTE as P
from . import world
from .sim import Sim


class Engine:
    def __init__(self, sim=None, out_dir=config.OUTPUT_DIR,
                 enable_real_payments=False, seed=None):
        pygame.init()
        pygame.display.set_caption(config.TITLE)
        self.screen = pygame.display.set_mode((config.SCREEN_W, config.SCREEN_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 22)
        self.big = pygame.font.Font(None, 30)
        self.sim = sim or Sim(out_dir=out_dir,
                              enable_real_payments=enable_real_payments,
                              seed=seed)
        self.running = True
        self.typing = False
        self.typed = ""
        self.time_scale = config.TIME_SCALE
        self.rng = random.Random()
        self.rain = []          # [x, y, speed]
        self.snow = []
        self.fog_puffs = [(self.rng.randrange(config.SCREEN_W),
                           self.rng.randrange(config.SCREEN_H),
                           self.rng.uniform(60, 130)) for _ in range(7)]
        self.grain_i = 0
        self.frame = 0
        self.cam = (0, 0)
        self._last_save = time.time()
        self._toast = ("Speak to the writer — type and press ENTER. "
                       "Try: write a book about the sea", time.time() + 14)

    # ------------------------------------------------------------ helpers ---
    def scene(self):
        return world.Scene(self.sim.body.scene)

    # -------------------------------------------------------------- render ---
    def draw_scene(self):
        sc = self.scene()
        body = self.sim.body
        rt = config.RTILE

        # camera follows; interiors are smaller than the screen and centre
        vw, vh = sc.width * rt, sc.height * rt
        if vw <= config.SCREEN_W:
            camx = (vw - config.SCREEN_W) // 2
        else:
            camx = int(body.x * rt - config.SCREEN_W / 2)
            camx = max(0, min(vw - config.SCREEN_W, camx))
        if vh <= config.SCREEN_H - 120:
            camy = (vh - (config.SCREEN_H - 120)) // 2
        else:
            camy = int(body.y * rt - (config.SCREEN_H - 120) / 2)
            camy = max(0, min(vh - config.SCREEN_H + 120, camy))
        self.cam = (camx, camy)

        self.screen.fill(P["night"])
        for gy, row in enumerate(sc.grid):
            for gx, ch in enumerate(row):
                below = sc.at(gx, gy + 1)
                t = assets.tile(ch, indoors=sc.indoors, below=below)
                self.screen.blit(pygame.transform.scale(t, (rt, rt)),
                                 (gx * rt - camx, gy * rt - camy))

        # the writer
        frame = int(self.frame / 12) % 2 if body.moving else 0
        spr = assets.sprite(body.facing, frame)
        sw, sh = spr.get_size()
        big = pygame.transform.scale(spr, (sw * config.SCALE, sh * config.SCALE))
        bx = body.x * rt - camx + rt // 2 - big.get_width() // 2
        by = body.y * rt - camy + rt - big.get_height()
        # soft shadow
        sh_surf = pygame.Surface((rt, rt // 3), pygame.SRCALPHA)
        pygame.draw.ellipse(sh_surf, (0, 0, 0, 70), sh_surf.get_rect())
        self.screen.blit(sh_surf, (body.x * rt - camx, body.y * rt - camy
                                   + rt - rt // 4))
        self.screen.blit(big, (bx, by))

        self.draw_weather(sc)
        self.draw_lighting(sc)
        self.draw_thought(sc, bx, by)

    def draw_weather(self, sc):
        w = self.sim.weather
        if w == "rain":
            if not sc.indoors:
                while len(self.rain) < 110:
                    self.rain.append([self.rng.randrange(-40, config.SCREEN_W),
                                      self.rng.randrange(-config.SCREEN_H, 0),
                                      self.rng.uniform(9, 14)])
                for d in self.rain:
                    d[0] -= d[2] * 0.18
                    d[1] += d[2]
                    pygame.draw.line(self.screen, (*P["rain"],),
                                     (d[0], d[1]), (d[0] - 2, d[1] - 7), 1)
                    if d[1] > config.SCREEN_H - 118:
                        d[1] = self.rng.randrange(-80, -5)
                        d[0] = self.rng.randrange(-40, config.SCREEN_W)
            else:
                # rain on the windows
                for gy, row in enumerate(sc.grid):
                    for gx, ch in enumerate(row):
                        if ch == "W":
                            x = gx * config.RTILE - self.cam[0]
                            y = gy * config.RTILE - self.cam[1]
                            for i in range(3):
                                rx = x + (self.frame * 3 + i * 17) % config.RTILE
                                pygame.draw.line(
                                    self.screen, (*P["rain"],),
                                    (rx, y), (rx - 2, y + config.RTILE), 1)
        elif w == "snow" and not sc.indoors:
            while len(self.snow) < 90:
                self.snow.append([self.rng.randrange(config.SCREEN_W),
                                  self.rng.randrange(-config.SCREEN_H, 0),
                                  self.rng.uniform(1, 2.4),
                                  self.rng.uniform(0, math.tau)])
            for d in self.snow:
                d[3] += 0.02
                d[0] += math.sin(d[3]) * 0.6
                d[1] += d[2]
                pygame.draw.circle(self.screen, P["snow"],
                                   (int(d[0]), int(d[1])), 2)
                if d[1] > config.SCREEN_H - 118:
                    d[1] = self.rng.randrange(-60, -5)
        elif w == "fog" and not sc.indoors:
            for i, (fx, fy, fr) in enumerate(self.fog_puffs):
                fx += 0.25
                if fx - fr > config.SCREEN_W:
                    fx = -fr
                    fy = self.rng.randrange(config.SCREEN_H)
                self.fog_puffs[i] = (fx, fy, fr)
                blob = assets.light_blob(int(fr))
                blob = blob.copy()
                blob.fill((*P["fog"], 26), special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(blob, (fx - fr, fy - fr))

    def darkness_level(self):
        h, m = self.sim.hour_min
        t = h + m / 60
        if 7 <= t < 16:
            base = 60
        elif 16 <= t < 19:
            base = 60 + (t - 16) / 3 * 110
        elif 19 <= t or t < 5:
            base = 185
        else:  # dawn 5..7
            base = 185 - (t - 5) / 2 * 125
        if self.sim.weather in ("rain", "fog"):
            base += 25
        elif self.sim.weather == "snow":
            base += 10
        return int(min(215, base))

    def draw_lighting(self, sc):
        dark = self.darkness_level()
        glows = []
        if sc.indoors:
            for gy, row in enumerate(sc.grid):
                for gx, ch in enumerate(row):
                    x = gx * config.RTILE - self.cam[0] + config.RTILE // 2
                    y = gy * config.RTILE - self.cam[1] + config.RTILE // 2
                    if ch == "l":
                        glows.append((x, y, 150, True))
                    elif ch == "n":
                        glows.append((x, y, 95, True))
                    elif ch == "v":
                        glows.append((x, y, 110, True))
                    elif ch == "W" and dark < 150:
                        glows.append((x, y, 120, False))
        else:
            door_x = world.door_positions
            for glyph in "CALSHK":
                for gy, row in enumerate(sc.grid):
                    for gx, ch in enumerate(row):
                        if ch == glyph:
                            x = gx * config.RTILE - self.cam[0] + config.RTILE // 2
                            y = gy * config.RTILE - self.cam[1] + config.RTILE // 2
                            glows.append((x, y + 10, 70, True))
        # the writer carries a faint lantern of presence
        bx = self.sim.body.x * config.RTILE - self.cam[0] + config.RTILE // 2
        by = self.sim.body.y * config.RTILE - self.cam[1] + config.RTILE // 2
        glows.append((bx, by, 95 if dark > 140 else 55, True))

        light = pygame.Surface((config.SCREEN_W, config.SCREEN_H),
                               pygame.SRCALPHA)
        flicker = 1 + 0.05 * math.sin(self.frame * 0.35)
        for x, y, r, warm in glows:
            blob = assets.light_blob(int(r * flicker), warm)
            light.blit(blob, (x - blob.get_width() // 2,
                              y - blob.get_height() // 2),
                       special_flags=pygame.BLEND_RGBA_ADD)
        inv = pygame.Surface((config.SCREEN_W, config.SCREEN_H),
                             pygame.SRCALPHA)
        inv.fill((6, 8, 16, dark))
        inv.blit(light, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        self.screen.blit(inv, (0, 0))

    def draw_thought(self, sc, bx, by):
        a = self.sim.activity
        if not a:
            return
        doing = a["do"]
        if doing == "_move":
            doing = "on the way"
        elif doing == "travel":
            doing = f"walking to {world.LOCATIONS[a['to']]['name']}"
        elif doing == "sleep":
            doing = "sleeping"
        text = doing.replace("_", " ")
        if self.sim.current_book and doing == "write":
            text += f" — {int(self.sim.current_book.progress * 100)}%"
        s = self.font.render(text, True, P["hud_fg"])
        pad = 6
        w_, h_ = s.get_size()
        bx2 = max(4, min(config.SCREEN_W - w_ - 2 * pad - 4, bx - w_ // 2))
        by2 = max(30, by - 34)
        box = pygame.Surface((w_ + 2 * pad, h_ + 2 * pad), pygame.SRCALPHA)
        box.fill((14, 14, 20, 190))
        self.screen.blit(box, (bx2, by2))
        self.screen.blit(s, (bx2 + pad, by2 + pad))

    # ---------------------------------------------------------------- HUD ---
    def draw_hud(self):
        sw = config.SCREEN_W
        top = pygame.Surface((sw, 28), pygame.SRCALPHA)
        top.fill((*P["hud_bg"], 215))
        self.screen.blit(top, (0, 0))
        sim = self.sim
        loc = world.LOCATIONS[sim.body.scene]["name"]
        wicon = {"rain": "rain", "fog": "fog", "snow": "snow",
                 "clear": "clear"}[sim.weather]
        head = (f"  {sim.clock_str()}   {sim.season}   {wicon}   "
                f"{loc}   {sim.body.money:.0f}cr")
        self.screen.blit(self.font.render(head, True, P["hud_fg"]), (4, 6))
        name_s = self.font.render(sim.body.name + "  ", True, P["lamp"])
        self.screen.blit(name_s, (sw - name_s.get_width() - 6, 6))

        # bottom panel
        py0 = config.SCREEN_H - 118
        panel = pygame.Surface((sw, 118), pygame.SRCALPHA)
        panel.fill((*P["hud_bg"], 225))
        self.screen.blit(panel, (0, py0))

        needs = [("health", sim.body.health)] + \
                [(k, sim.body.needs[k]) for k in
                 ("satiety", "energy", "hygiene", "inspiration", "social",
                  "mood")]
        x = 10
        for i, (label, val) in enumerate(needs):
            y = py0 + 10 + i * 15
            col = P["good"] if val > 55 else P["warn"] if val > 25 else P["bad"]
            self.screen.blit(self.font.render(f"{label[:11]:<11}", True,
                                              P["hud_fg"]), (x, y))
            pygame.draw.rect(self.screen, (40, 40, 48), (x + 92, y + 4, 90, 8))
            pygame.draw.rect(self.screen, col, (x + 92, y + 4,
                                                int(90 * val / 100), 8))
        # book panel
        bx = 220
        if sim.current_book:
            b = sim.current_book
            t = b.title if len(b.title) <= 24 else b.title[:21] + "…"
            lines = [f"writing: {t}",
                     f"theme: {b.theme[:26]}",
                     f"words: {b.words}/{b.target_words}",
                     f"sittings: {b.sessions}"]
            for i, ln in enumerate(lines):
                self.screen.blit(self.font.render(ln, True, P["hud_fg"]),
                                 (bx, py0 + 10 + i * 20))
            pygame.draw.rect(self.screen, (40, 40, 48),
                             (bx, py0 + 92, 180, 8))
            pygame.draw.rect(self.screen, P["lamp"],
                             (bx, py0 + 92, int(180 * b.progress), 8))
        else:
            msg = ("no book in progress\n"
                   "commission one:\n"
                   "write a book about …")
            for i, ln in enumerate(msg.split("\n")):
                self.screen.blit(self.font.render(ln, True, P["hud_fg"]),
                                 (bx, py0 + 16 + i * 20))

        # pantry
        p = sim.body
        pan = (f"{p.food} meals · {p.supplies.get('paper', 0)} paper · "
               f"{p.supplies.get('lamp_oil', 0)} oil · "
               f"{len(sim.finished_books)} books")
        self.screen.blit(self.font.render(pan, True, P["hud_fg"]),
                         (bx, py0 + 96))

        # log
        lx = 455
        entries = list(sim.log)[-6:]
        for i, e in enumerate(entries):
            who = {"you": "you", "world": "~", "printer": "post",
                   "store": "till"}.get(e["who"], sim.body.name.split()[0])
            txt = f"{who}: {e['text']}"
            if len(txt) > 74:
                txt = txt[:71] + "…"
            col = P["lamp"] if e["who"] == "you" else P["hud_fg"]
            self.screen.blit(self.font.render(f"{txt}", True, col),
                             (lx, py0 + 8 + i * 17))

        # toast / hint
        if time.time() < self._toast[1]:
            t = self.font.render(self._toast[0], True, P["paper"])
            self.screen.blit(t, (10, 34))

        # command line
        if self.typing:
            s = self.font.render("» " + self.typed + "▌", True, P["paper"])
            bg = pygame.Surface((s.get_width() + 12, 26), pygame.SRCALPHA)
            bg.fill((10, 10, 16, 230))
            self.screen.blit(bg, (8, 30))
            self.screen.blit(s, (12, 34))

    # ---------------------------------------------------------------- loop ---
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.KEYDOWN:
                if self.typing:
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        text = self.typed.strip()
                        self.typed = ""
                        self.typing = False
                        if text:
                            self.sim.submit_command(text)
                    elif ev.key == pygame.K_ESCAPE:
                        self.typing = False
                        self.typed = ""
                    elif ev.key == pygame.K_BACKSPACE:
                        self.typed = self.typed[:-1]
                    elif ev.unicode and ev.unicode.isprintable():
                        self.typed += ev.unicode
                else:
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER,
                                  pygame.K_SLASH, pygame.K_t):
                        self.typing = True
                        self.typed = ""
                    elif ev.key == pygame.K_SPACE:
                        self.sim.paused = not self.sim.paused
                    elif ev.key in (pygame.K_EQUALS, pygame.K_PLUS):
                        self.time_scale = min(32, self.time_scale * 2)
                    elif ev.key == pygame.K_MINUS:
                        self.time_scale = max(0.5, self.time_scale / 2)
                    elif ev.key == pygame.K_F2:
                        self.screenshot()
                    elif ev.key in (pygame.K_q, pygame.K_ESCAPE):
                        self.running = False

    def screenshot(self, path=None):
        path = path or os.path.join(
            self.sim.out_dir,
            f"screenshot_{time.strftime('%H%M%S')}.png")
        os.makedirs(self.sim.out_dir, exist_ok=True)
        pygame.image.save(self.screen, path)
        return path

    def step(self, dt):
        """Advance one frame. Returns False when quitting."""
        self.handle_events()
        if not self.running:
            return False
        if not self.typing:   # typing holds time still, like held breath
            self.sim.tick(dt * self.time_scale)
        self.frame += 1
        self.grain_i += 1
        self.draw_scene()
        self.draw_hud()
        self.screen.blit(assets.vignette(config.SCREEN_W, config.SCREEN_H),
                         (0, 0))
        grain = pygame.transform.scale(
            assets.grain_frame(self.grain_i // 6),
            (config.SCREEN_W, config.SCREEN_H))
        self.screen.blit(grain, (0, 0))
        pygame.display.flip()
        if time.time() - self._last_save > 45:
            self._last_save = time.time()
            self.sim.save()
        return True

    def run(self, max_frames=None, screenshot_at=None, screenshot_path=None):
        frames = 0
        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0
            if not self.step(dt):
                break
            frames += 1
            if screenshot_at and frames == screenshot_at:
                self.screenshot(screenshot_path)
            if max_frames and frames >= max_frames:
                break
        self.sim.save()
        pygame.quit()
        return frames

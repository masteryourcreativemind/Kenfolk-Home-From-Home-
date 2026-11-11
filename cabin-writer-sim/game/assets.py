"""Procedural pixel art — no image files needed. Every tile and sprite is
drawn in code in a muted, rain-washed palette: Stardew-shaped, but the sun
forgot to come up."""

import random

import pygame

from . import config
from .config import PALETTE as P

_cache = {}


def _surf(w=16, h=16):
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _noise(px, base, vary, seed=7):
    rng = random.Random(seed)
    for y in range(16):
        for x in range(16):
            d = rng.randint(-vary, vary)
            px[x, y] = tuple(max(0, min(255, c + d)) for c in base)


def tile(glyph, indoors=False, below=None):
    """Return a 16x16 surface for a map glyph. `indoors` disambiguates
    shared glyphs ('f' flower vs floor, 'r' rock vs rug); `below` lets
    walls know a door sits under them so the roofline reads correctly."""
    key = (glyph, indoors, below)
    if key in _cache:
        return _cache[key]
    s = _surf()
    px = pygame.PixelArray(s)

    if glyph in "gG":
        _noise(px, P["grass"] if glyph == "g" else P["grass_dark"], 8,
               seed=hash(key) & 9999)
        rng = random.Random(hash(key) & 777)
        for _ in range(6):  # grass blades
            x, y = rng.randrange(16), rng.randrange(4, 16)
            px[x, y] = px[x, y - 1] = P["pine_dark"]
    elif glyph == ".":
        _noise(px, P["dirt"], 10, seed=11)
    elif glyph == "D":
        _noise(px, P["wood"], 8, seed=12)
        for y in (3, 7, 11, 15):
            for x in range(16):
                px[x, y] = P["wood_dark"]
    elif glyph == "~":
        _noise(px, P["water"], 6, seed=13)
        rng = random.Random(5)
        for _ in range(4):
            x, y = rng.randrange(12), rng.randrange(16)
            px[x, y] = px[x + 1, y] = px[x + 2, y] = P["water_hi"]
    elif glyph == "T":
        _noise(px, P["grass_dark"], 8, seed=14)
        for i, w in enumerate((5, 7, 9, 11)):  # layered pine
            y = 1 + i * 3
            for x in range(8 - w // 2, 8 + w // 2 + 1):
                if 0 <= x < 16 and 0 <= y < 16:
                    px[x, y] = P["pine"] if (x + y) % 3 else P["pine_dark"]
        for y in range(13, 16):
            px[7, y] = px[8, y] = P["trunk"]
    elif glyph == "r" and not indoors:
        _noise(px, P["grass"], 8, seed=15)
        for y in range(7, 13):
            for x in range(5, 12):
                if (x - 8) ** 2 / 12 + (y - 10) ** 2 / 6 <= 1:
                    px[x, y] = P["day_grey"]
    elif glyph == "f" and not indoors:
        _noise(px, P["grass"], 8, seed=16)
        for cx, cy in ((4, 5), (11, 9), (7, 12)):
            px[cx, cy] = (150, 140, 160)
            px[cx, cy + 1] = P["pine_dark"]
    elif glyph == "#":
        is_roof = below == "#"
        _noise(px, P["roof"] if is_roof else P["wall_log"], 6,
               seed=17 if is_roof else 18)
        if not is_roof:  # log stripes
            for y in (4, 9, 14):
                for x in range(16):
                    px[x, y] = P["wood_dark"]
        else:            # wet roof shine
            for x in range(16):
                px[x, 15] = tuple(min(255, c + 18) for c in P["roof"])
    elif glyph in "CALSHK":
        _noise(px, P["wood_dark"], 5, seed=19)
        for y in range(2, 14):                     # doorway
            for x in range(4, 12):
                px[x, y] = (24, 20, 18)
        for y in (2, 13):                          # warm threshold
            for x in range(3, 13):
                px[x, y] = P["lamp"]
    # --------------------------------------------------------- interiors ---
    elif glyph == "w":
        _noise(px, P["wall_log"], 6, seed=20)
        for y in (5, 11):
            for x in range(16):
                px[x, y] = P["wood_dark"]
    elif glyph == "W":
        _noise(px, P["wall_log"], 6, seed=21)
        for y in range(3, 13):                     # rainy glass
            for x in range(4, 12):
                px[x, y] = (70, 84, 96) if (x + y) % 5 else (92, 106, 118)
        for x in range(4, 12):
            px[x, 3] = px[x, 12] = P["wood_dark"]
        for y in range(3, 13):
            px[4, y] = px[11, y] = P["wood_dark"]
    elif glyph == "o":
        _noise(px, P["floor"], 7, seed=22)
        for y in range(11, 14):
            for x in range(3, 13):
                px[x, y] = (52, 44, 40)
    elif glyph in "fF" and indoors:
        base = P["floor"] if glyph == "f" else P["floor_alt"]
        _noise(px, base, 6, seed=hash(key) & 555)
        for x in range(16):
            px[x, 15] = P["wood_dark"]
    elif glyph == "r" and indoors:   # rug
        _noise(px, P["floor"], 6, seed=36)
        for y in range(16):
            for x in range(16):
                if x in (0, 15) or y in (0, 15):
                    px[x, y] = (96, 54, 52)
                elif (x + y) % 4 < 2:
                    px[x, y] = (112, 74, 64)
    elif glyph == "b":   # bed
        _noise(px, P["floor"], 6, seed=23)
        for y in range(2, 14):
            for x in range(2, 14):
                px[x, y] = (92, 74, 88) if y > 4 else P["paper"]
    elif glyph == "d":   # desk with manuscript
        _noise(px, P["floor"], 6, seed=24)
        for y in range(5, 12):
            for x in range(1, 15):
                px[x, y] = P["wood"]
        for y in range(6, 10):
            for x in range(4, 9):
                px[x, y] = P["paper"]       # the page
        px[12, 6] = px[12, 7] = P["ink"]    # inkwell
    elif glyph == "c":   # chair
        _noise(px, P["floor"], 6, seed=25)
        for y in range(6, 12):
            for x in range(5, 11):
                px[x, y] = P["wood_light"]
    elif glyph == "v":   # stove with ember glow
        _noise(px, P["floor"], 6, seed=26)
        for y in range(3, 14):
            for x in range(3, 13):
                px[x, y] = (44, 42, 46)
        for y in range(8, 11):
            for x in range(6, 10):
                px[x, y] = P["ember"]
    elif glyph == "k":   # bookshelf
        _noise(px, P["wood_dark"], 5, seed=27)
        rng = random.Random(31)
        for row in (2, 7, 12):
            x = 1
            while x < 14:
                wdt = rng.randint(2, 3)
                col = rng.choice([(120, 80, 70), (80, 90, 110), (110, 100, 70),
                                  (90, 70, 90), (70, 95, 85)])
                for y in range(row, row + 4):
                    for xx in range(x, min(15, x + wdt)):
                        px[xx, y] = col
                x += wdt
    elif glyph == "t":   # table
        _noise(px, P["floor"], 6, seed=28)
        for y in range(3, 13):
            for x in range(1, 15):
                px[x, y] = P["wood_light"] if y in (3, 12) else P["wood"]
    elif glyph == "l":   # oil lamp
        _noise(px, P["floor"], 6, seed=29)
        for y in range(4, 9):
            for x in range(6, 10):
                px[x, y] = P["candle"]
        for y in range(9, 13):
            for x in range(5, 11):
                px[x, y] = P["wood_dark"]
    elif glyph == "n":   # candle
        _noise(px, P["floor"], 6, seed=30)
        for y in range(7, 13):
            px[8, y] = P["paper"]
        px[8, 5] = px[8, 6] = P["candle"]
    elif glyph == "p":   # pew
        _noise(px, P["floor"], 6, seed=31)
        for y in range(4, 12):
            for x in range(1, 15):
                px[x, y] = P["wood_dark"] if y == 4 else P["wood"]
    elif glyph == "a":   # altar
        _noise(px, P["floor_alt"], 6, seed=32)
        for y in range(2, 13):
            for x in range(2, 14):
                px[x, y] = (120, 112, 96)
        px[8, 3] = px[8, 4] = P["candle"]
    elif glyph == "u":   # store counter
        _noise(px, P["floor"], 6, seed=33)
        for y in range(2, 14):
            for x in range(0, 16):
                px[x, y] = P["wood"] if y in (2, 3) else P["wood_dark"]
    elif glyph == "s":   # stocked shelf
        _noise(px, P["wood_dark"], 5, seed=34)
        rng = random.Random(41)
        for row in (3, 8, 13):
            for x in range(1, 15, 3):
                col = rng.choice([(150, 140, 100), (120, 120, 130),
                                  (140, 100, 80)])
                for y in range(row - 2, row):
                    for xx in range(x, x + 2):
                        px[xx, y] = col
    else:
        _noise(px, P["floor"], 6, seed=35)

    del px
    _cache[key] = s
    return s


# ----------------------------------------------------------- the writer ---
_SPR = {
    ".": None, "h": P["hair"], "s": P["skin"], "e": (30, 28, 32),
    "c": P["coat"], "C": (58, 60, 74), "p": (52, 48, 52),
    "b": (36, 30, 28),
}

DOWN_A = [
    "....hhhh....",
    "...hhhhhh...",
    "..hhhhhhhh..",
    "..hssssssh..",
    "..hsessesh..",
    "..hssssssh..",
    "...ssssss...",
    "..cccccccc..",
    ".sccccccccs.",
    ".sccccccccs.",
    ".sCccccccCs.",
    "..cccccccc..",
    "..cccccccc..",
    "...pp..pp...",
    "...pp..pp...",
    "...pp..pp...",
    "...bb..bb...",
    "...bb..bb...",
]
DOWN_B = DOWN_A[:13] + [
    "....pppp....",
    "...pp..pp...",
    "....pppp....",
    "...bb..bb...",
    "..bb....bb..",
]
UP_A = [
    "....hhhh....",
    "...hhhhhh...",
    "..hhhhhhhh..",
    "..hhhhhhhh..",
    "..hhhhhhhh..",
    "...hhhhhh...",
    "...hhhhhh...",
    "..cccccccc..",
    ".sccccccccs.",
    ".sccccccccs.",
    ".sCccccccCs.",
    "..cccccccc..",
    "..cccccccc..",
    "...pp..pp...",
    "...pp..pp...",
    "...pp..pp...",
    "...bb..bb...",
    "...bb..bb...",
]
UP_B = UP_A[:13] + DOWN_B[13:]
RIGHT_A = [
    "....hhhh....",
    "...hhhhhh...",
    "..hhhhhhh...",
    "..hssssss...",
    "..hsssese...",
    "..hssssss...",
    "...sssss....",
    "...cccccc...",
    "...ccccccs..",
    "...cccccc...",
    "...cccccc...",
    "...cccccc...",
    "...ppppp....",
    "...pp.pp....",
    "...pp..pp...",
    "...pp...pp..",
    "...bb...bb..",
    "...bb....b..",
]
RIGHT_B = RIGHT_A[:13] + [
    "...ppppp....",
    "....ppp.....",
    "....p.p.....",
    "...bb.bb....",
    "...b...b....",
]


def _flip(rows):
    return [r[::-1] for r in rows]


SPRITES = {
    ("down", 0): DOWN_A, ("down", 1): DOWN_B,
    ("up", 0): UP_A, ("up", 1): UP_B,
    ("right", 0): RIGHT_A, ("right", 1): RIGHT_B,
    ("left", 0): _flip(RIGHT_A), ("left", 1): _flip(RIGHT_B),
}


def sprite(facing, frame):
    key = ("spr", facing, frame)
    if key in _cache:
        return _cache[key]
    rows = SPRITES[(facing, frame)]
    s = _surf(16, 24)
    px = pygame.PixelArray(s)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            col = _SPR.get(ch)
            if col and y < 24 and x + 2 < 16:
                px[x + 2, y + 3] = col
    del px
    _cache[key] = s
    return s


# ------------------------------------------------------------- overlays ---
def vignette(w, h):
    key = ("vig", w, h)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2, h / 2
    max_d = (cx ** 2 + cy ** 2) ** 0.5
    step = 6
    for y in range(0, h, step):
        for x in range(0, w, step):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / max_d
            a = int(max(0, d - 0.45) ** 1.6 * 200)
            if a:
                pygame.draw.rect(s, (8, 8, 14, a), (x, y, step, step))
    _cache[key] = s
    return s


def grain_frame(idx):
    key = ("grain", idx % 8)
    if key in _cache:
        return _cache[key]
    rng = random.Random(idx)
    s = pygame.Surface((160, 96), pygame.SRCALPHA)
    px = pygame.PixelArray(s)
    for _ in range(700):
        x, y = rng.randrange(160), rng.randrange(96)
        v = rng.randint(0, 255)
        px[x, y] = (v, v, v, 14)
    del px
    _cache[key] = s
    return s


def light_blob(radius, warm=True):
    key = ("blob", radius, warm)
    if key in _cache:
        return _cache[key]
    s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    col = P["candle"] if warm else (160, 170, 185)
    for r in range(radius, 0, -2):
        a = int(90 * (1 - r / radius) ** 1.5)
        pygame.draw.circle(s, (*col, a), (radius, radius), r)
    _cache[key] = s
    return s

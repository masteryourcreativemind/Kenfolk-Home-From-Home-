"""The 2D world: an exterior map of pines and cabins, and the interiors of
every building the writer can enter. Maps are ASCII grids; each glyph maps to
a tile drawn procedurally by assets.py.

Legend (exterior):
    g grass      G dark grass   . dirt path    ~ water        D dock
    T pine tree  r rock         f flowers
    C cabin door L library door S store door   H chapel door  A cafe door
    # building wall/roof block

Legend (interior):
    w log wall   W window       o door mat     f plank floor   F alt plank
    b bed        d desk         c chair        v stove         k bookshelf
    t table      l lamp         n candle       p pew           a altar
    r rug        u counter      s shelf goods  e exit mat
"""

# ------------------------------------------------------------- exterior ---
# The map is generated deterministically: paths always connect, doors always
# face open ground, and the pines never block the road.
import random as _random

DOOR_GLYPHS = {
    "C": "cabin",
    "A": "cafe",
    "S": "store",
    "L": "library",
    "H": "chapel",
    "K": "lookout_cabin",
}

# building top-left corners; each building is 4 wide x 2 tall, doors on the
# bottom row in the middle two tiles
_BUILDINGS = {
    "cabin":         ((2, 2),   "C"),
    "library":       ((28, 4),  "L"),
    "store":         ((27, 9),  "S"),
    "chapel":        ((34, 9),  "H"),
    "cafe":          ((2, 14),  "A"),
    "lookout_cabin": ((40, 14), "K"),
}

_EXT_W, _EXT_H = 46, 28


def _build_exterior():
    g = [["g"] * _EXT_W for _ in range(_EXT_H)]
    rng = _random.Random(7)

    # the lake and the dock
    for y in range(22, 27):
        for x in range(1, _EXT_W - 1):
            g[y][x] = "~"
    for y in range(22, 26):
        g[y][9] = "D"

    # paths: main street (row 16), three column roads, cabin stub, lake road
    for x in range(1, _EXT_W - 1):
        g[16][x] = "."
    for y in range(1, 26):
        g[y][9] = g[y][9] if g[y][9] == "D" else "."
    for y in range(1, 17):
        g[y][26] = "."
        g[y][33] = "."
    for x in range(3, 10):
        g[4][x] = "."

    # buildings
    door_cells = set()
    for loc, ((x0, y0), glyph) in _BUILDINGS.items():
        for dx in range(4):
            g[y0][x0 + dx] = "#"
            g[y0 + 1][x0 + dx] = "#"
        g[y0 + 1][x0 + 1] = glyph
        g[y0 + 1][x0 + 2] = glyph
        door_cells.add((x0 + 1, y0 + 1))
        door_cells.add((x0 + 2, y0 + 1))

    def clear_of_door(x, y):
        return all((x + dx, y + dy) not in door_cells
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1))

    # moody dressing: dark grass, flowers, rocks, and many pines
    for _ in range(60):
        x, y = rng.randrange(1, _EXT_W - 1), rng.randrange(1, 22)
        if g[y][x] == "g":
            g[y][x] = "G"
    for _ in range(12):
        x, y = rng.randrange(1, _EXT_W - 1), rng.randrange(1, 22)
        if g[y][x] in "gG" and clear_of_door(x, y):
            g[y][x] = "f"
    for _ in range(8):
        x, y = rng.randrange(1, _EXT_W - 1), rng.randrange(1, 22)
        if g[y][x] in "gG" and clear_of_door(x, y):
            g[y][x] = "r"
    for _ in range(70):
        x, y = rng.randrange(1, _EXT_W - 1), rng.randrange(1, 22)
        if g[y][x] in "gG" and clear_of_door(x, y) and \
                all(g[yy][xx] not in "#" and (xx, yy) not in door_cells
                    for xx, yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1))
                    if 0 <= xx < _EXT_W and 0 <= yy < _EXT_H):
            g[y][x] = "T"

    # the wall of pines that bounds the world
    for x in range(_EXT_W):
        g[0][x] = "T"
        g[_EXT_H - 1][x] = "T"
    for y in range(_EXT_H):
        g[y][0] = "T"
        g[y][_EXT_W - 1] = "T"
    return ["".join(row) for row in g]


EXTERIOR = _build_exterior()


def door_positions(location):
    """All exterior (x, y) tiles that are doors into `location`."""
    out = []
    for y, row in enumerate(EXTERIOR):
        for x, ch in enumerate(row):
            if DOOR_GLYPHS.get(ch) == location:
                out.append((x, y))
    return out

# Friendly display names / descriptions used by the HUD and headless log.
LOCATIONS = {
    "outside":       {"name": "the pinewood",          "indoors": False},
    "lakeshore":     {"name": "the lakeshore",         "indoors": False},
    "cabin":         {"name": "the log cabin",         "indoors": True},
    "library":       {"name": "the Pinewood Library",  "indoors": True},
    "store":         {"name": "the General Store",     "indoors": True},
    "chapel":        {"name": "the Chapel of Rain",    "indoors": True},
    "cafe":          {"name": "the Half-Light Café",   "indoors": True},
    "lookout_cabin": {"name": "the old lookout cabin", "indoors": True},
}

# ------------------------------------------------------------ interiors ---
INTERIORS = {
    "cabin": {
        "map": [
            "wwwwWwwwww",
            "wffffffkfw",
            "wbdfffflfw",
            "wffffcffww",
            "wrrfffffvw",
            "wrrfffttfw",
            "wfffffftfw",
            "wWwwooowWw",
        ],
        "spawn": (4, 6),
        "desk": (2, 2), "bed": (1, 2), "stove": (8, 4),
        "exit": [(4, 7), (5, 7), (6, 7)],
        "flavour": "Home. One room, one lamp, one desk facing the rain.",
    },
    "library": {
        "map": [
            "wwwwWwWwwwww",
            "wkkfwkkfwkkw",
            "wkkfwkkfwkkw",
            "wffffffffffw",
            "wkktftfltkkw",
            "wffffffffffw",
            "wkkfwkkfwkkw",
            "wkkffffffkkw",
            "wwwWwooWWwww",
        ],
        "spawn": (5, 7),
        "table": (5, 4),
        "exit": [(5, 8), (6, 8)],
        "flavour": "Dust and damp paper. The librarian never looks up.",
    },
    "store": {
        "map": [
            "wwwwWwwwww",
            "wssssssssw",
            "wffffffffw",
            "wfuuuuuufw",
            "wffffffffw",
            "wsswffwssw",
            "wffffffffw",
            "wWwwooowWw",
        ],
        "spawn": (4, 6),
        "counter": (4, 3),
        "exit": [(4, 7), (5, 7), (6, 7)],
        "flavour": "Tins, lamp oil, and bread under a low ceiling.",
    },
    "chapel": {
        "map": [
            "wwwWWWWwww",
            "wfffnnfffw",
            "wffaafffww",
            "wppfwwfppw",
            "wppfwwfppw",
            "wppfwwfppw",
            "wffffffffw",
            "wwWWooWWww",
        ],
        "spawn": (4, 6),
        "pew": (1, 3),
        "exit": [(4, 7), (5, 7)],
        "flavour": "Candles for people who ran out of words.",
    },
    "cafe": {
        "map": [
            "wwwwWwwwww",
            "wfffffffkw",
            "wtflwfltfw",
            "wffffffffw",
            "wfuuuuuufw",
            "wtflwfltfw",
            "wffffffffw",
            "wWwwooowWw",
        ],
        "spawn": (4, 6),
        "table": (1, 2),
        "exit": [(4, 7), (5, 7), (6, 7)],
        "flavour": "Weak coffee, steamed windows, strangers' murmurs.",
    },
    "lookout_cabin": {
        "map": [
            "wwwwWwwwww",
            "wkfffffffw",
            "wffflffffw",
            "wftfffffvw",
            "wffffffffw",
            "wrffffffkw",
            "wffffffffw",
            "wWwwooowWw",
        ],
        "spawn": (4, 6),
        "table": (2, 3),
        "exit": [(4, 7), (5, 7), (6, 7)],
        "flavour": "Abandoned. The view of the lake is worth the damp.",
    },
}

WALKABLE_EXT = set("gG.Drf" + "".join(DOOR_GLYPHS))
WALKABLE_INT = set("foFrea")

# Travel time (game-minutes) between locations along the paths.
TRAVEL_MINUTES = {
    frozenset(("cabin", "outside")): 4,
    frozenset(("outside", "library")): 14,
    frozenset(("outside", "store")): 12,
    frozenset(("outside", "chapel")): 16,
    frozenset(("outside", "cafe")): 8,
    frozenset(("outside", "lookout_cabin")): 22,
    frozenset(("outside", "lakeshore")): 10,
}


def grid_get(grid, x, y):
    if 0 <= y < len(grid) and 0 <= x < len(grid[y]):
        return grid[y][x]
    return None


class Scene:
    """A renderable/walkable grid the writer is currently standing in."""

    def __init__(self, key):
        self.key = key
        info = LOCATIONS[key]
        self.name = info["name"]
        self.indoors = info["indoors"]
        if key in INTERIORS:
            data = INTERIORS[key]
            self.grid = data["map"]
            self.spawn = data["spawn"]
            self.exits = set(data["exit"])
            self.flavour = data["flavour"]
            self.poi = {k: v for k, v in data.items()
                        if k not in ("map", "spawn", "exit", "flavour")}
        else:
            self.grid = EXTERIOR
            self.spawn = (4, 4)
            self.exits = set()
            self.flavour = "Wind in the pines. The lake answers nothing."
            self.poi = {"dock": (14, 25)}

    def walkable(self, x, y):
        ch = grid_get(self.grid, x, y)
        if ch is None:
            return False
        return ch in (WALKABLE_INT if self.indoors else WALKABLE_EXT)

    def at(self, x, y):
        return grid_get(self.grid, x, y)

    @property
    def width(self):
        return max(len(r) for r in self.grid)

    @property
    def height(self):
        return len(self.grid)

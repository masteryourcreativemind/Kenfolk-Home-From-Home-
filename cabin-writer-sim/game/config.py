"""Global configuration: display, palette, time, and simulation constants."""

# ---------------------------------------------------------------- display ---
SCREEN_W = 960
SCREEN_H = 576
TILE = 16            # source tile size in pixels
SCALE = 3            # render scale (16 * 3 = 48 px per tile on screen)
RTILE = TILE * SCALE
FPS = 60
TITLE = "The Cabin Writer — a quiet life"

# ------------------------------------------------------------------ time ---
# game-minutes that pass per real second in the graphical engine
TIME_SCALE = 4.0
DAY_MINUTES = 24 * 60
SEASON_DAYS = 30     # days per season
START_HOUR = 6

# -------------------------------------------------------- moody palette ---
# Desaturated, dim, rain-washed. The whole game lives in these colours.
PALETTE = {
    "night":      (10, 12, 18),
    "dusk":       (46, 42, 56),
    "dawn":       (74, 62, 66),
    "day_grey":   (104, 108, 112),
    "grass":      (64, 74, 58),
    "grass_dark": (52, 62, 48),
    "dirt":       (86, 70, 56),
    "water":      (38, 52, 66),
    "water_hi":   (58, 76, 92),
    "pine":       (34, 48, 40),
    "pine_dark":  (26, 38, 32),
    "trunk":      (52, 40, 32),
    "wood":       (94, 72, 52),
    "wood_dark":  (66, 50, 38),
    "wood_light": (118, 94, 68),
    "floor":      (104, 80, 58),
    "floor_alt":  (96, 74, 54),
    "wall_log":   (78, 60, 44),
    "roof":       (56, 44, 40),
    "lamp":       (222, 168, 92),
    "candle":     (240, 190, 110),
    "ember":      (196, 96, 48),
    "paper":      (212, 202, 178),
    "ink":        (32, 30, 34),
    "coat":       (44, 46, 58),
    "skin":       (186, 152, 122),
    "hair":       (58, 46, 40),
    "rain":       (140, 156, 172),
    "fog":        (120, 126, 134),
    "snow":       (196, 202, 208),
    "hud_bg":     (16, 16, 22),
    "hud_fg":     (188, 182, 170),
    "good":       (122, 148, 108),
    "warn":       (196, 156, 84),
    "bad":        (158, 78, 70),
}

# ------------------------------------------------------------- defaults ---
DEFAULT_WRITER_NAME = "Elian Marlowe"
DEFAULT_OWNER_NAME = "The Reader"       # certificate owner until user sets it
STARTING_MONEY = 140.0                  # in-game credits of savings
STARTING_FOOD = 4                       # meals in the pantry

# need decay per game-hour
DECAY = {
    "satiety": 5.0,
    "energy": 7.0,
    "hygiene": 1.6,
    "inspiration": 1.2,
    "social": 1.4,
}
SLEEP_RECOVERY = 13.0        # energy per hour asleep
HEALTH_DECAY = 2.2           # per hour while starving or collapsed

OUTPUT_DIR = "output"        # zip books, saves, ledger live here

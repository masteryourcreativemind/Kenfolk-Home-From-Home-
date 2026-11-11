"""The book engine. Prose is generated from the writer's *becoming*:
personality traits, accumulated research, the weather it lived through, and
the commands the user gave. No two books read alike because no two writers
in this simulation are the same person for long.
"""

import hashlib
import random
import re
import time

# ------------------------------------------------------------- wordbanks ---
# Each theme: nouns, verbs, adjectives, images (concrete sensory phrases),
# and abstractions the prose can lean on.
THEMES = {
    "grief": {
        "nouns": ["grief", "the empty chair", "absence", "the unanswered letter",
                  "mourning", "the cold side of the bed", "a name no one says",
                  "ashes", "the funeral bell", "a coat still hanging by the door"],
        "verbs": ["aches", "endures", "unmakes", "hollows", "lingers",
                  "settles like sediment", "returns uninvited", "quiets"],
        "adjs": ["unspoken", "hollow", "tender", "unbearable", "patient",
                 "wintered", "salt-stung", "unfinished"],
        "images": ["rain on a window at three in the morning",
                   "a teacup washed and put away forever",
                   "footsteps that stop before the door",
                   "the black ribbon on the chapel gate"],
    },
    "sea": {
        "nouns": ["the sea", "brine", "the drowned bell", "driftwood", "tide",
                  "the grey horizon", "salt", "a hull breathing in the swell",
                  "the lighthouse ledger", "undertow"],
        "verbs": ["pulls", "remembers", "drowns", "keeps", "surrenders",
                  "sings low", "takes back", "weathers"],
        "adjs": ["salt-black", "tidal", "fathomless", "grey-green",
                 "storm-written", "cold", "unforgiving"],
        "images": ["foam handwriting erased as fast as it is written",
                   "a gull hanging motionless in the wind",
                   "nets drying like old letters on the fence"],
    },
    "solitude": {
        "nouns": ["solitude", "the one plate", "a single lamp", "silence",
                  "the long table", "footsteps of no one", "the fourth wall",
                  "an echo", "the unwatched road"],
        "verbs": ["settles", "sharpens", "accompanies", "waits", "keeps vigil",
                  "answers nothing", "multiplies in the corners"],
        "adjs": ["unaccompanied", "quiet", "self-sufficient", "distant",
                 "lampless", "unwitnessed", "whole"],
        "images": ["one chair turned toward the stove",
                   "a path with a single set of footprints",
                   "dinner cooked for one, eaten slowly"],
    },
    "memory": {
        "nouns": ["memory", "the yellowed photograph", "a childhood staircase",
                  "the smell of a kitchen", "an old song", "what the body keeps",
                  "the attic box", "a recurring dream"],
        "verbs": ["resurfaces", "revises", "fades at the edges", "flickers",
                  "keeps its own counsel", "rewrites", "haunts gently"],
        "adjs": ["half-remembered", "amber", "unreliable", "dear", "faded",
                 "recurring", "warm at the center"],
        "images": ["a sunbeam full of dust over a staircase",
                   "handwriting on the back of a photograph",
                   "the song the kettle used to sing"],
    },
    "god": {
        "nouns": ["God", "the unanswered prayer", "a candle", "the silence after amen",
                  "providence", "the chapel roof", "a psalm half-remembered",
                  "grace", "the collection plate's single coin"],
        "verbs": ["listens, perhaps", "withholds", "answers in weather",
                  "waits in the rafters", "forgives slowly", "keeps the vigil"],
        "adjs": ["hushed", "candlelit", "unknowable", "merciful", "distant",
                 "psalm-worn"],
        "images": ["rain on the chapel roof like a congregation",
                   "a candle lit for someone whose name is lost",
                   "light through a plain glass window"],
    },
    "love": {
        "nouns": ["love", "a hand on the small of a back", "the shared umbrella",
                  "two cups", "the kept promise", "a letter never sent",
                  "her laugh", "the dance nobody saw"],
        "verbs": ["mends", "risked", "stayed", "trembles", "remembers the steps",
                  "refuses to leave", "waits up"],
        "adjs": ["trembling", "stubborn", "tender", "improbable", "worn smooth",
                 "undefeated"],
        "images": ["two umbrellas leaning together by the door",
                   "a ring left on the windowsill while washing up",
                   "dancing in the kitchen to no music"],
    },
    "default": {
        "nouns": ["the cabin", "the rain", "the long evening", "a notebook",
                  "the stove's small mercy", "the road to the village",
                  "a kerosene lamp", "the unnamed year"],
        "verbs": ["passes", "settles", "endures", "asks little", "keeps",
                  "arrives quietly", "is enough"],
        "adjs": ["quiet", "grey", "unhurried", "plain", "worn", "honest"],
        "images": ["steam rising from a chipped mug",
                   "lamplight pooling on a page",
                   "the path home through wet pines"],
    },
}

# Tone templates keyed by dominant trait. {n} {v} {a} {i} {th} slots.
TONES = {
    "melancholy": [
        "There is a kind of {a} {n} that {v}, and it has moved into this house.",
        "By evening the {n} had become {a}, the way {i} becomes ordinary.",
        "No one warns you that {n} {v}; you simply notice, one Tuesday, that it has.",
        "The {n} was {a} — {i}, and the lamp burning anyway.",
        "What remains is {a}: {i}, and the long practice of saying nothing about it.",
        "It rained, and the {n} {v}, and this counted as an event.",
    ],
    "romanticism": [
        "Even the {a} {n} {v} like something that once hoped to be beautiful.",
        "I have loved few things as faithfully as {i}.",
        "The {n}, {a} and unashamed, {v} — and I let it.",
        "Give me {i} over the company of the sensible, every time.",
        "If {n} {v}, then let it; there are worse altars to kneel at.",
    ],
    "solitude": [
        "I live with {n} now. It {v}. We do not discuss it.",
        "The day was {a}. The {n} {v}. Nothing was required of me, and I of nothing.",
        "{i}. That was the whole of the news.",
        "One learns the house by its {a} sounds; the {n} has its own grammar.",
        "Company would have ruined it: {i}, perfect, unshared.",
    ],
    "spirituality": [
        "Perhaps {n} is only the name we give the part of the dark that {v}.",
        "I lit a candle for the {a} {n}; whether anyone received it is above my pay.",
        "{i} — and for a moment the roof lifted and something vast looked in.",
        "The psalm says nothing about {n}, but the rain on the roof did.",
        "Grace, I suspect, is {a}: {i}, arriving unasked.",
    ],
    "curiosity": [
        "I wanted to know where {n} goes when it {v}, so I followed it to the lake.",
        "Consider {i}. Who decided it should be {a}, and why do we obey?",
        "The {n} {v} according to rules nobody wrote down; I am writing them down.",
        "Every {a} {n} is a question the world is asking back.",
        "I measured the evening in {n}; the results were {a} and, I think, true.",
    ],
    "discipline": [
        "At six, {i}. At seven, the {n}. The day held its shape.",
        "A {a} {n} {v}; this is known, and known things can be borne.",
        "Write it plainly: {i}. Plainness is not poverty.",
        "The work today was {a}. The {n} {v}. Tomorrow, again.",
        "Order is a small lamp: {i}, and the dark kept to its borders.",
    ],
}

CHAPTER_TITLE_PATTERNS = [
    "In Which the {n} {v}",
    "A Note on {a} Evenings",
    "The {n}, Explained to No One",
    "What the {n} Kept",
    "On {a} {n}",
    "The Long {n}",
    "Weather Report for the {n}",
]

EPIGRAPHS = [
    "“We do not remember days; we remember the rain that ended them.” — margin note, Pinewood Library",
    "“A quiet life is still a life examined.” — found pencilled in a returned book",
    "“Every cabin is a ship that decided to stay.” — graffiti, lakeshore dock",
    "“Loneliness is the tuition; the work is the scholarship.” — the librarian, once",
    "“Grief is love with nowhere to go, so it learns to write.” — chapel visitors' book",
]

TITLE_PATTERNS = [
    "The {A} {N}",
    "{N} of {N2}",
    "A {A} {N} for the {N2}",
    "On {N} and {N2}",
    "The {N} {V}",
    "Letters to a {A} {N}",
    "{N}: A Winter Ledger",
]

# short, title-worthy nouns per theme (long phrases read badly on spines)
TITLE_NOUNS = {
    "grief": ["grief", "mourning", "ashes", "absence", "the bell",
              "the empty chair"],
    "sea": ["the sea", "brine", "the tide", "salt", "undertow", "the grey"],
    "solitude": ["solitude", "silence", "one lamp", "the fourth wall",
                 "the unwatched road"],
    "memory": ["memory", "the photograph", "the staircase", "the attic box"],
    "god": ["God", "the candle", "amen", "the vigil", "grace"],
    "love": ["love", "two cups", "the promise", "the unsent letter"],
    "default": ["the rain", "the cabin", "evening", "lamplight",
                "the long road"],
}


def _title_case_pattern(pattern, rng, bank, title_nouns=None):
    pool = title_nouns or [re.sub(r"^the ", "", n) for n in bank["nouns"]]

    def bare_noun():
        return re.sub(r"^the ", "", rng.choice(pool))
    n1, n2 = bare_noun(), bare_noun()
    if n2 == n1:
        n2 = bare_noun()
        if n2 == n1 and len(pool) > 1:
            n2 = re.sub(r"^the ", "", pool[(pool.index(n2) + 1) % len(pool)]
                        if n2 in pool else rng.choice(pool))
    a = rng.choice(bank["adjs"])
    v = rng.choice(bank["verbs"])
    t = (pattern.replace("{N2}", n2).replace("{N}", n1)
                .replace("{A}", a).replace("{V}", v))
    t = t.title()
    for small in (" And ", " A ", " Of ", " For ", " To ", " In ",
                  " The ", " On "):
        t = t.replace(small, small.lower())
    t = re.sub(r"\b[Tt]he [Tt]he\b", "the", t)
    t = re.sub(r"\bA (?=[aeiou])", "An ", t, flags=re.I)
    t = re.sub(r":\s+([a-z])", lambda m: ": " + m.group(1).upper(), t)
    if t.startswith("the "):
        t = "T" + t[1:]
    return t


class Book:
    """A work in progress. Words accrue in writing sessions; the prose is
    materialised at publication time from a seed, so a save file stores the
    book's soul, not its bulk."""

    def __init__(self, title, theme, traits, author,
                 target_words=4200, research=None, seed=None):
        self.title = title
        self.theme = theme
        self.author = author
        self.trait_snapshot = dict(traits)
        self.target_words = target_words
        self.words = 0
        self.sessions = 0
        self.research = list(research or [])
        self.quality = 0.0
        self.started = time.time()
        self.finished = None
        self.seed = seed if seed is not None else int(
            hashlib.sha256(f"{title}|{theme}|{author}|{self.started}".encode()
                           ).hexdigest()[:12], 16)

    # ------------------------------------------------------------ writing ---
    def write_session(self, hours, energy, mood, discipline, weather):
        """One sitting at the desk. Returns words written this session."""
        if self.done:
            return 0
        flow = (0.45 + 0.4 * (energy / 100) + 0.35 * (mood / 100)
                + 0.6 * discipline)
        if weather == "rain":
            flow *= 1.12          # rain is good for the work, usually
        wpm = 9.0 * flow          # longhand, lamplight
        words = int(wpm * 60 * hours)
        words = max(20, min(words, self.target_words - self.words))
        self.words += words
        self.sessions += 1
        q = 0.4 * (energy / 100) + 0.3 * (mood / 100) + 0.3 * discipline
        self.quality = 0.65 * self.quality + 0.35 * q if self.sessions > 1 else q
        if self.done:
            self.finished = time.time()
            if self.research:
                self.quality = min(1.0, self.quality + 0.08 * len(self.research))
        return words

    @property
    def done(self):
        return self.words >= self.target_words

    @property
    def progress(self):
        return min(1.0, self.words / self.target_words)

    # ------------------------------------------------------- publication ---
    def dominant_tones(self):
        order = sorted(self.trait_snapshot.items(), key=lambda kv: -kv[1])
        tones = [k for k, _ in order if k in TONES]
        return tones[:2] or ["melancholy"]

    def _bank(self):
        theme = (self.theme or "").lower()
        for key in THEMES:
            if key != "default" and key in theme:
                return THEMES[key]
        for key in THEMES:  # partial word match ("grieving" -> grief)
            if key != "default" and any(w in theme for w in key.split()):
                return THEMES[key]
        merged = {k: list(v) for k, v in THEMES["default"].items()}
        # the default voice is a life: cabin, rain, evening
        for key in ("solitude", "memory"):
            for slot in merged:
                merged[slot] += THEMES[key][slot][:3]
        return merged

    def _sentence(self, rng, bank):
        tone = rng.choice(self.dominant_tones())
        tpl = rng.choice(TONES[tone])
        sentence = tpl.format(
            n=rng.choice(bank["nouns"]),
            v=rng.choice(bank["verbs"]),
            a=rng.choice(bank["adjs"]),
            i=rng.choice(bank["images"]),
            th=self.theme,
        )
        return sentence[0].upper() + sentence[1:]

    def _paragraph(self, rng, bank):
        return " ".join(self._sentence(rng, bank)
                        for _ in range(rng.randint(3, 6)))

    def materialise(self, weather_log=None):
        """Render the full manuscript. Deterministic for a given seed."""
        rng = random.Random(self.seed)
        bank = self._bank()
        n_chapters = max(5, min(12, self.target_words // 600))
        words_per = max(4, self.target_words // n_chapters // 18)

        chapters = []
        for ci in range(n_chapters):
            pat = rng.choice(CHAPTER_TITLE_PATTERNS)
            title = _title_case_pattern(pat, rng, bank)
            paras = [self._paragraph(rng, bank) for _ in range(words_per)]
            chapters.append({"number": ci + 1, "title": title,
                             "paragraphs": paras})

        preface = [
            f"This book was written in a log cabin, mostly in the rain, "
            f"over {self.sessions} sittings at a desk facing the window.",
            f"It concerns itself with {self.theme}. I did not choose the "
            f"subject so much as it chose the hours I kept. If the prose "
            f"sounds like weather, that is because weather is what I had.",
        ]
        afterword = [
            f"Finished, or abandoned, in the manner of all books. "
            f"— {self.author}",
            "The lamp is low. The rain continues. There will be another.",
        ]
        epigraphs = list(self.research)[:3] or [rng.choice(EPIGRAPHS)]

        return {
            "title": self.title, "author": self.author, "theme": self.theme,
            "preface": preface, "epigraphs": epigraphs,
            "chapters": chapters, "afterword": afterword,
            "quality": round(self.quality, 3), "sessions": self.sessions,
            "words": self.words, "seed": self.seed,
        }

    def to_dict(self):
        return {k: getattr(self, k) for k in
                ("title", "theme", "author", "target_words", "words",
                 "sessions", "quality", "started", "finished", "seed")} | {
                 "trait_snapshot": self.trait_snapshot, "research": self.research}

    @classmethod
    def from_dict(cls, d):
        b = cls(d["title"], d["theme"], d.get("trait_snapshot", {}),
                d.get("author", config_name()), d.get("target_words", 4200),
                d.get("research", []), d.get("seed"))
        b.words = d.get("words", 0)
        b.sessions = d.get("sessions", 0)
        b.quality = d.get("quality", 0.0)
        b.started = d.get("started", time.time())
        b.finished = d.get("finished")
        return b


def config_name():
    from . import config
    return config.DEFAULT_WRITER_NAME


def suggest_title(theme, traits, rng=None):
    rng = rng or random.Random()
    bank = THEMES["default"]
    nouns = TITLE_NOUNS["default"]
    tl = (theme or "").lower()
    for key in THEMES:
        if key != "default" and key in tl:
            bank = THEMES[key]
            nouns = TITLE_NOUNS.get(key, TITLE_NOUNS["default"])
            break
    return _title_case_pattern(rng.choice(TITLE_PATTERNS), rng, bank,
                               title_nouns=nouns)

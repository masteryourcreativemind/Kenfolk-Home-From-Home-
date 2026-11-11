# The Cabin Writer 🌧️

*A lonely writer's life simulation. You don't play the writer — you raise it.*

A small 2D life sim in the shape of a farming game (16×16 pixel tiles,
Stardew-Valley silhouette) but tuned to a different key: dim lamplight, near-
constant rain, fog in the pines, and one writer in a log cabin whose only
permitted profession is **writing books**. You speak general commands; the
writer decides how a life absorbs them. When a book is finished, it is
shipped to you as a neatly organised `.zip` containing a real **EPUB** and a
real **PDF**, each carrying an ownership certificate in your name.

---

## Starting the game

The intended way to play is to **ask an AI agent to start it for you**.

> *"Agent, start my cabin game. Tell the writer to live as a hermit, take
> daily walks, and write a book about grief and the sea."*

The agent runs (see `AGENTS.md`):

```bash
cd cabin-writer-sim
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py                      # graphical window
# …or fully in the terminal (no display needed):
.venv/bin/python main.py --headless --days 10 --speed 30 \
    --script scripts/demo_life.txt
```

Headless mode never imports pygame; the simulation core is pure stdlib
Python, so an agent can run a life, and ship books, from any terminal.

## What the writer lives under

Real constraints, always on:

| Need | Reality |
|---|---|
| satiety | must eat; food costs credits; no credits → foraging in the wet pines |
| energy | writing drains it; collapse comes for the proud |
| hygiene | ignores it and it will not ignore you back |
| inspiration | refilled by reading, research, the lakeshore |
| social | loneliness accrues unless it visits the café (hermits decay slower) |
| mood | weather, health, and isolation bend it; rain feeds some souls |
| health | starve or overwork it and the body files a formal complaint |
| money | spent at the General Store; earned only from book royalties and your patronage |

It **cannot take any other job.** Ask it to and it will decline, in character.

## Talking to the writer

```
write a book about grief and the sea
write a novel about memory called "The Amber House"
research 19th century whaling            → notes seep into the prose
live as a hermit / be social / be a night owl / live frugally
take daily walks / pray daily
go to the library / chapel / café / store / lake / lookout
buy groceries / paper / a typewriter / an armchair
top up 20 dollars                        → patronage, converted to credits
books / status / package latest unorganized / help
```

You only ever see the building the writer is currently inside (or the
rain-soaked exterior as it walks). The rest of the village exists, but you
watch a life, not a map.

## What you receive

`output/<title>_<date>.zip`, organised by default:

```
the-title/
├── the-title.epub          # certificate page inside, owner in metadata
├── the-title.pdf           # certificate first page, same fingerprint
├── certificates/
│   ├── CERTIFICATE.txt     # human-readable ownership certificate
│   └── certificate.json    # ISBN, SHA-256 of manuscript, signature
├── manuscript/             # plain-text chapters
└── manifest.json
```

Say *"package latest unorganized"* and future zips ship flat instead.
The certificate declares the work transferred in full to you, fingerprinted
by the SHA-256 of the complete manuscript.

## Real-world money hookup (optional, off by default)

`top up` commands use a **mock provider** — pretend money — unless you
explicitly arm the real one:

```bash
export CABIN_PAYMENT_ENDPOINT=https://your-provider.example
export CABIN_PAYMENT_KEY=sk_...
python main.py --enable-real-payments
```

The game then POSTs `{amount, currency, memo}` to
`{endpoint}/charge` for each *explicit* `top up` command you give — never
unilaterally, and it never touches card data. Every transaction lands in
`output/ledger.jsonl`. Refusals and network failures fail safe (no charge,
no credits).

## Controls (graphical)

| key | action |
|---|---|
| type + ENTER | speak to the writer (time holds its breath while you type) |
| SPACE | pause |
| + / − | time speed |
| F2 | screenshot to `output/` |
| ESC / Q | save & quit |

Saves live at `output/save.json` (autosaves every 45 s). Resume with
`--load output/save.json`.

## Project layout

```
game/
├── config.py    palette, time, decay constants
├── world.py     generated pinewood map + six interiors
├── writer.py    the body: needs, health, pantry
├── mind.py      command parser, personality traits, life decisions
├── books.py     trait-driven generative prose engine
├── publish.py   dependency-free EPUB + PDF + certificates + zip
├── economy.py   ledger, store catalogue, mock/real payment providers
├── sim.py       the shared simulation core
├── engine.py    pygame rendering: rain, fog, lamplight, grain, HUD
└── headless.py  terminal chronicle for AI agents
```

*It is always raining somewhere over the lake. That is where the books
come from.*

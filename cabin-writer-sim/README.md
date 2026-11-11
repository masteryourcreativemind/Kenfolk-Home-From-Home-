# The Cabin Writer 🌧️

*Play your own life in Pinewood, or raise the original AI writer.*

A small 2D survival and writing game: dim lamplight, rain, fog in the pines,
and a log cabin of your own. **The default is now a game you control
directly in your browser**, not a spectator simulation. Walk, enter
buildings, meet villagers, fish, hunt, trade and keep your body alive.
In the separate AI modes, you speak general commands and the writer
decides how a life absorbs them. In either mode, a finished book is
shipped to you as a neatly organised `.zip` containing a real **EPUB** and a
real **PDF**, each carrying an ownership certificate in your name.

---

## Starting the game

### Play it yourself (recommended)

```bash
cd cabin-writer-sim
python3 main.py
# Or print the URL without trying to launch a desktop browser:
python3 main.py --play --no-browser
```

Open **http://127.0.0.1:8765**. This mode needs only Python's standard
library: **no pygame, package installation, AI agent or payment service**.
The server binds to your own computer only by default. Use `--port 8766`
if that port is occupied.

In GitHub Codespaces, run `python3 main.py --no-browser --host 0.0.0.0`,
forward port **8765** in the Ports panel and open its browser URL. Keep the
port **private**; this is a personal local game host, not a public
multiplayer service.

| Control | Action |
|---|---|
| WASD / arrow keys / on-screen pad | Move your character one tile at a time |
| Click ground | Follow the walkable route you select |
| E | Interact with a nearby villager or workstation |
| M / Map | Full usable map, villagers, wildlife and walk-to destinations |
| B / Body | Individual organ HP, temperature, hydration, wetness and blood |
| I / Bag | Supplies, clothing and Mira's market |
| J / Journal | Quests, skills, events and downloadable books |

Step through marked exterior doors to enter, or the interior exit mat to
leave. Stand within **two tiles** of NPCs, your bed, desk or stove to use
them. Trees, walls and water block movement. Hunting requires an animal
within **six tiles** and a clear shot.

**Time advances only when you act.** Opening menus, reading the map,
closing the browser or stepping away does not advance the simulation.
Walking takes at least 1.2 game-minutes per tile; longer activities display
their duration. An action may spend bait or an arrow without succeeding.
Your character never chooses an activity, walks home, eats or writes for
you.

### Your first day

You start at 08:00 with 140 in-game credits, meals, safe water, a rod, bow,
raincoat, light clothes, bait, arrows, bandages and medicine. Open your map
and walk to the lake dock. Talk to **Nessa**, accept her supper quest, and
catch two fish. Deliver them for credits, or take a catch home to cook.

**Mira** buys fish, meat, pelts, berries, herbs and firewood and sells food,
paper, supplies and winter clothes. **Rowan** has a hunting delivery quest,
**Jun** treats illness and injuries, **Ada** gives writing advice and
**Tomas** hosts the cafe. Villagers keep the hours shown on the map; talking
and completing quests build friendship. Animals roam and replenish each
day; lake stocks recover daily. Gather fallen wood near trees and light
your stove before cooking raw fish or meat.

### A body with consequences

Your full health bar totals **1,000 HP**, split between these systems:

| System | HP | Consequence |
|---|---:|---|
| Brain | 120 | Vital; cold, heat and blood loss can damage it |
| Heart | 160 | Vital; vulnerable to temperature, starvation and dehydration |
| Lungs | 150 | Vital; injury increases exertion's energy cost |
| Liver | 100 | Damage makes illness more harmful |
| Kidneys | 100 | Damage increases water loss |
| Stomach | 90 | Damage reduces food absorption |
| Skin | 100 | Wounds, infection and cold damage the protective barrier |
| Arms | 80 | Damage lowers bow accuracy |
| Legs | 100 | Damage slows walking |

**Zero HP in a vital organ ends your life even with other HP remaining.**
There is no automatic rescue or hidden replenishment of supplies.

Four 30-day seasons, six-hour weather changes, day/night temperature,
wind, cold uplands and the damp lakeshore affect body temperature. Rain
and snow wet clothing; wet layers lose insulation. A raincoat blocks most
rain, a winter coat protects in cold conditions, and heavy clothes can
overheat you in summer or heated rooms. Body temperature below **35 C**
causes hypothermia damage; above **38.5 C** causes heat-illness damage.
Shelter and a fueled stove warm and dry you.

Hydration, hunger, energy, hygiene and blood loss also matter. Raw food
and untreated lake water can cause food poisoning; dirty bleeding wounds
can become infected. Cold exposure causes hypothermia, **not** spontaneous
infection. Bandages stop bleeding; medicine or Jun reduces illness.
Safe water, adequate food and sheltered rest or sleep support gradual
organ recovery. These are **fictional game mechanics, not medical advice**.

Write at your cabin desk and research at the library. Starting a topic
does not trigger automatic writing: choose each two-hour writing session
yourself. Finished books earn royalties and appear in the Journal as
downloadable EPUB/PDF bundles. Player currency is entirely fictional;
**player mode never enables real payments**.

### Saves

Each action atomically autosaves to `output/player-save.json`. Starting
the browser mode again automatically resumes that file, including organ
injuries, illness, gear, inventory, quests, NPC friendship, wildlife,
weather timing, book progress and the random generator state.
Download a backup with **Download save**, or resume a particular file:

```bash
python3 main.py --play --load path/to/player-save.json
```

**New life** asks for confirmation before replacing your current player
save. Published book files are not deleted. AI mode retains its separate
`output/save.json`. Use `--out DIR` for a separate life/output directory.

### Original AI writer modes

You can still ask an agent to run an autonomous writer:

> *"Agent, start my cabin game. Tell the writer to live as a hermit, take
> daily walks, and write a book about grief and the sea."*

The agent runs (see `AGENTS.md`):

```bash
cd cabin-writer-sim
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py --graphical          # graphical AI window
# …or fully in the terminal (no display needed):
.venv/bin/python main.py --headless --days 10 --speed 30 \
    --script scripts/demo_life.txt
```

Headless mode never imports pygame; the simulation core is pure stdlib
Python, so an agent can run a life, and ship books, from any terminal.

## What the AI writer lives under

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

## Talking to the AI writer

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

In graphical AI mode, you only see the building the writer is inside (or the
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
python main.py --headless --enable-real-payments
```

The game then POSTs `{amount, currency, memo}` to
`{endpoint}/charge` for each *explicit* `top up` command you give — never
unilaterally, and it never touches card data. Every transaction lands in
`output/ledger.jsonl`. Refusals and network failures fail safe (no charge,
no credits).

## Controls (graphical AI mode)

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
├── survival.py  1,000-HP organ physiology, illness and thermal exposure
├── player.py    directly chosen movement, survival, NPCs, trading and quests
├── web.py       dependency-free local browser server and player autosaves
├── web/         browser canvas, controls, usable map and organ-health UI
├── mind.py      command parser, personality traits, life decisions
├── books.py     trait-driven generative prose engine
├── publish.py   dependency-free EPUB + PDF + certificates + zip
├── economy.py   ledger, store catalogue, mock/real payment providers
├── sim.py       the shared simulation core
├── engine.py    pygame rendering: rain, fog, lamplight, grain, HUD
└── headless.py  terminal chronicle for AI agents
```

## Development checks

```bash
python3 -m unittest discover -s tests -v
node --check game/web/play.js
```

The tests use only the standard library and cover player control, map
reachability, survival thresholds, NPC economy, fishing/hunting, save
continuity, publishing, legacy AI behavior and the browser API.

*It is always raining somewhere over the lake. That is where the books
come from.*

# Instructions for AI agents

You have been asked to start and steward **The Cabin Writer**, a life
simulation. This file is your complete operating manual.

## Start the game

```bash
cd cabin-writer-sim
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Preferred when you have no display (servers, terminals, CI):
.venv/bin/python main.py --headless --days 10 --speed 30 \
    --script scripts/demo_life.txt

# Interactive terminal life (accepts user directives via stdin):
.venv/bin/python main.py --headless --interactive --speed 60

# Graphical window (only if the user has a display):
.venv/bin/python main.py
```

Headless mode needs **no third-party packages at all** — if `pip install`
is impossible, run the system `python3 main.py --headless …` directly.

Useful flags: `--seed N` (reproducible life), `--owner "Name"` (certificate
owner), `--out DIR` (where zips/saves go), `--load PATH` (resume),
`--quiet` (only print book shipments), `--days N`, `--speed MINUTES_PER_TICK`.

## Passing the user's commands

Translate the user's wishes into directives, either via `--command`
(repeatable), a `--script` file (one directive per line, `#` comments ok),
or stdin in `--interactive` mode. The writer understands plain English;
examples live in `game/mind.py` (`CommandParser`) and in the README. The
writer may only ever be a writer — requests for other employment are
declined in character.

## What to hand back to the user

Finished books appear in the output directory as `<title>_<date>.zip`
(default `output/`). Each zip contains an EPUB and a PDF of the same book,
both embedding an ownership certificate (name from `--owner` or the
user's "owner name is …" / "my name is …" directive), plus a plain-text
manuscript and manifest. Point the user at the zip path printed in the log
line beginning `printer:`.

## Money

Default: mock credits; `top up 20 dollars` just works. Real charges happen
ONLY if the user set `CABIN_PAYMENT_ENDPOINT` + `CABIN_PAYMENT_KEY` and
passed `--enable-real-payments`. Never enable real payments yourself.
All transactions are recorded in `output/ledger.jsonl`.

## Care guide

Watch the 12-hour status lines. If satiety or health trends to zero, the
writer cannot work: tell it to `buy groceries`, or relay a top-up from the
user. A writer that is fed, rested, and rained-upon writes better books
(craft score rises with mood, energy, discipline, and research).

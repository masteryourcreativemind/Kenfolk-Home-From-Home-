"""Headless mode — how an AI agent runs the game from a terminal.

No window, no pygame import: the same simulation, narrated as text.
Commands come from --script files, --command flags, or stdin.

  python main.py --headless --days 5 --speed 60 \
      --command "your name is Elian Marlowe" \
      --command "live as a hermit; take daily walks" \
      --command "write a book about grief and the sea"
"""

import sys
import time

from . import world
from .sim import Sim


def _print_event(ev):
    print(f"[{ev['t']:>14}] [{ev['weather']:<5}] {ev['who']}: {ev['text']}")


def run(sim: Sim, days=None, speed=30, script=None, commands=None,
        interactive=False, verbose=True, save_path=None):
    """Drive the simulation. `speed` = game-minutes per tick."""
    max_minutes = days * 24 * 60 if days else None
    start_clock = sim.clock
    seen = 0

    queued = []
    if commands:
        queued.extend(commands)
    if script:
        with open(script, encoding="utf-8") as fh:
            queued.extend(ln.strip() for ln in fh
                          if ln.strip() and not ln.strip().startswith("#"))

    print("=" * 70)
    print("  THE CABIN WRITER — headless chronicle")
    print("=" * 70)
    for ev in list(sim.log):
        _print_event(ev)
    seen = len(sim.log)

    for cmd in queued:
        print(f"\n>>> {cmd}")
        reply = sim.submit_command(cmd)
        if reply:
            print(f"<<< {reply}")
        for ev in list(sim.log)[seen:]:
            pass
        seen = len(sim.log)

    last_status = 0
    try:
        while True:
            if max_minutes and sim.clock - start_clock >= max_minutes:
                break
            sim.tick(speed)
            if verbose:
                events = list(sim.log)
                for ev in events[seen:]:
                    _print_event(ev)
                seen = len(events)
            if interactive and _stdin_ready():
                line = sys.stdin.readline().strip()
                if line:
                    print(f"\n>>> {line}")
                    print(f"<<< {sim.submit_command(line)}")
                    seen = len(sim.log)
            if sim.clock - last_status >= 12 * 60:
                last_status = sim.clock
                if verbose:
                    print(f"\n--- {sim.clock_str()} — "
                          f"{sim.status_text().splitlines()[1]}\n")
    except KeyboardInterrupt:
        print("\n(interrupted — saving)")

    path = sim.save(save_path)
    print("\n" + "=" * 70)
    print(f"  saved: {path}")
    if sim.finished_books:
        print("  books shipped:")
        for fb in sim.finished_books:
            print(f"   • {fb['zip']}")
    print("=" * 70)
    return sim


def _stdin_ready():
    import select
    try:
        return bool(select.select([sys.stdin], [], [], 0.0)[0])
    except Exception:
        return False

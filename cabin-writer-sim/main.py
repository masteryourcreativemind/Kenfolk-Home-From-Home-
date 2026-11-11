#!/usr/bin/env python3
"""The Cabin Writer — a lonely writer's life simulation.

Graphical (for a human at a screen):
    python main.py

Headless (for an AI agent in a terminal):
    python main.py --headless --days 10 --speed 60 \
        --command "live as a hermit" \
        --command "write a book about grief and the sea"

Real-money hookup is opt-in:
    export CABIN_PAYMENT_ENDPOINT=https://your-provider.example
    export CABIN_PAYMENT_KEY=sk_...
    python main.py --enable-real-payments
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="The Cabin Writer — a writer's life in the rain.")
    ap.add_argument("--headless", action="store_true",
                    help="run without a window (AI-agent mode)")
    ap.add_argument("--days", type=float, default=None,
                    help="stop after N game days (headless; default: forever)")
    ap.add_argument("--speed", type=float, default=30,
                    help="game-minutes per tick in headless mode")
    ap.add_argument("--command", action="append", default=[],
                    help="a directive for the writer (repeatable)")
    ap.add_argument("--script", default=None,
                    help="text file with one directive per line")
    ap.add_argument("--interactive", action="store_true",
                    help="headless: also read directives from stdin")
    ap.add_argument("--quiet", action="store_true",
                    help="headless: only print book shipments")
    ap.add_argument("--out", default="output",
                    help="directory for books, saves, ledger, screenshots")
    ap.add_argument("--seed", type=int, default=None,
                    help="fixed RNG seed for a reproducible life")
    ap.add_argument("--owner", default=None,
                    help="certificate owner name for published books")
    ap.add_argument("--load", default=None, help="path to a save.json")
    ap.add_argument("--enable-real-payments", action="store_true",
                    help="allow the real payment API (needs env vars)")
    ap.add_argument("--screenshot", default=None,
                    help="graphical: save a screenshot to this path after "
                         "N frames (see --frames)")
    ap.add_argument("--frames", type=int, default=None,
                    help="graphical: exit after N frames (testing)")
    args = ap.parse_args(argv)

    from game import config
    from game.sim import Sim

    if args.headless:
        from game.headless import run
        sim = (Sim.load(args.load, out_dir=args.out,
                        enable_real_payments=args.enable_real_payments)
               if args.load else
               Sim(out_dir=args.out, seed=args.seed,
                   enable_real_payments=args.enable_real_payments,
                   owner=args.owner or config.DEFAULT_OWNER_NAME))
        run(sim, days=args.days, speed=args.speed, script=args.script,
            commands=args.command, interactive=args.interactive,
            verbose=not args.quiet)
        return 0

    from game.engine import Engine
    sim = None
    if args.load:
        sim = Sim.load(args.load, out_dir=args.out,
                       enable_real_payments=args.enable_real_payments)
    eng = Engine(sim=sim, out_dir=args.out,
                 enable_real_payments=args.enable_real_payments,
                 seed=args.seed)
    if args.owner:
        eng.sim.owner = args.owner
    eng.run(max_frames=args.frames,
            screenshot_at=args.frames if args.screenshot else None,
            screenshot_path=args.screenshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

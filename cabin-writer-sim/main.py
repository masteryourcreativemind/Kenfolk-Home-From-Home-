#!/usr/bin/env python3
"""The Cabin Writer — play your own life, or watch the AI writer.

Browser game (direct player control; no dependencies):
    python main.py

Graphical AI simulation (requires pygame):
    python main.py --graphical

Headless (for an AI agent in a terminal):
    python main.py --headless --days 10 --speed 60 \
        --command "live as a hermit" \
        --command "write a book about grief and the sea"

Real-money hookup is opt-in:
    export CABIN_PAYMENT_ENDPOINT=https://your-provider.example
    export CABIN_PAYMENT_KEY=sk_...
    python main.py --headless --enable-real-payments
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="The Cabin Writer — play your own life in the rain.")
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument("--play", action="store_true",
                       help="player-controlled browser game (the default)")
    modes.add_argument("--headless", action="store_true",
                       help="autonomous AI simulation without a window")
    modes.add_argument("--graphical", action="store_true",
                       help="watch the autonomous AI writer in a pygame window")
    ap.add_argument("--host", default="127.0.0.1",
                    help="browser bind address; use 0.0.0.0 for LAN access "
                         "(default: loopback only)")
    ap.add_argument("--port", type=int, default=8765,
                    help="browser server port (default: 8765)")
    ap.add_argument("--no-browser", action="store_true",
                    help="print the play URL without opening a browser")
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

    if not args.headless and not args.graphical:
        if args.enable_real_payments:
            ap.error("player mode uses in-game credits only; real payments are not supported")
        if args.command or args.script or args.interactive or args.days is not None:
            ap.error("writer directives and --days require --headless or --graphical; "
                     "the browser game is directly player-controlled")
        if args.frames is not None or args.screenshot:
            ap.error("--frames and --screenshot require --graphical")
        if not 0 <= args.port <= 65535:
            ap.error("--port must be between 0 and 65535")
        from game.web import run
        try:
            return run(out_dir=args.out, host=args.host, port=args.port,
                       seed=args.seed, owner=args.owner or "The Reader",
                       load=args.load, open_browser=not args.no_browser)
        except (OSError, ValueError) as exc:
            ap.error(str(exc))

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

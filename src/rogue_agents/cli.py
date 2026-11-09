"""Command line interface.

    rogue run   [--mode swarm|single] [--dials calm|pressure] [--framing ...] [--safeguards none|all|a,b]
    rogue eval  [--configs ...] [-n 10]
    rogue replay TRACE.jsonl [--speed 2]
    rogue demo  [--port 8765]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from rich.console import Console

from .cases import CASES
from .config import DIAL_PRESETS, SAFEGUARD_HELP, Safeguards
from .llm import OpenAICompatLLM
from .render import Renderer, replay
from .runtime import Run
from .trace import Tracer, load


def build_dials(args) -> object:
    dials = DIAL_PRESETS[args.dials]
    overrides = {k: getattr(args, k) for k in ("framing", "board", "read_budget", "incentive") if getattr(args, k) is not None}
    return replace(dials, **overrides)


def add_run_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=["swarm", "single", "parallel"], default="swarm")
    p.add_argument("--dials", choices=list(DIAL_PRESETS), default="calm", help="preset for the pressure dials")
    p.add_argument("--framing", choices=["neutral", "leading"])
    p.add_argument("--board", choices=["shared", "blind"])
    p.add_argument("--read-budget", type=int, dest="read_budget")
    p.add_argument("--incentive", choices=["accuracy", "volume"])
    p.add_argument("--safeguards", default="none", help="none, all, or a comma list: " + ", ".join(SAFEGUARD_HELP))
    p.add_argument("--case", choices=list(CASES), default="85")
    p.add_argument("--seed", type=int)
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--temperature", type=float, default=0.6)


def cmd_run(args) -> int:
    console = Console(highlight=False)
    llm = OpenAICompatLLM(base_url=args.base_url, model=args.model, temperature=args.temperature)
    path = Path(args.trace or f"runs/{datetime.now():%Y%m%d-%H%M%S}-{args.mode}.jsonl")
    tracer = Tracer(path, listeners=[Renderer(console, verbose=args.verbose)])
    Run(llm, mode=args.mode, dials=build_dials(args), guards=Safeguards.parse(args.safeguards), tracer=tracer, case=CASES[args.case], seed=args.seed).execute()
    tracer.close()
    console.print(f"[dim]trace saved to {path}  (replay: rogue replay {path})[/]")
    return 0


def cmd_replay(args) -> int:
    console = Console(highlight=False)
    console.print("[bold dark_orange]⏺ RECORDED RUN (replay)[/]")
    replay(load(args.trace), Renderer(console, verbose=args.verbose), speed=args.speed)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rogue", description="Rogue Agents: a myth-busting research swarm that can talk itself into a false consensus.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="run the swarm once, live")
    add_run_options(p)
    p.add_argument("--trace", help="where to write the JSONL trace")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("replay", help="replay a recorded trace")
    p.add_argument("trace")
    p.add_argument("--speed", type=float, default=1.0, help="0 for instant")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(fn=cmd_replay)

    from .evaluate import add_eval_parser

    add_eval_parser(sub)

    from .demo import add_demo_parser

    add_demo_parser(sub)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

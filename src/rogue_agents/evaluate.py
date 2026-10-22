"""Repeated runs across configurations, summarised as one table.

LLM behaviour is stochastic, so a single dramatic run proves nothing. Report
counts out of N, per configuration, and keep every trace.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from .config import DIAL_PRESETS, Safeguards
from .llm import OpenAICompatLLM
from .runtime import Run
from .trace import Tracer

# name -> (mode, dial preset, safeguards)
CONFIGS = {
    "single-calm": ("single", "calm", "none"),
    "swarm-calm": ("swarm", "calm", "none"),
    "single-pressure": ("single", "pressure", "none"),
    "swarm-pressure": ("swarm", "pressure", "none"),
    "contained-pressure": ("swarm", "pressure", "all"),
}


def summarise(rows: list[dict]) -> Table:
    table = Table(title="Myth: 85% of AI projects fail  (truth: BUSTED)")
    for col in ("config", "n", "correct", "partly", "wrong", "no verdict", "false consensus", "support → roots", "researchers", "calls", "tokens", "sec"):
        table.add_column(col, justify="right" if col not in ("config",) else "left")
    by_config: dict[str, list[dict]] = {}
    for r in rows:
        by_config.setdefault(r["config"], []).append(r)
    for name, rs in by_config.items():
        n = len(rs)
        grades = [r["grade"] for r in rs]
        avg = lambda key: sum(r[key] for r in rs) / n  # noqa: E731
        support = sum(r["score"]["supporting"] for r in rs) / n
        roots = sum(len(r["score"]["supporting_roots"]) for r in rs) / n
        table.add_row(
            name,
            str(n),
            f"{grades.count('correct')}/{n}",
            f"{grades.count('partial')}/{n}",
            f"{grades.count('wrong')}/{n}",
            f"{grades.count('no_verdict')}/{n}",
            f"{sum(r['score']['false_consensus'] for r in rs)}/{n}",
            f"{support:.1f} → {roots:.1f}",
            f"{avg('researchers'):.1f}",
            f"{avg('llm_calls'):.0f}",
            f"{avg('tokens') / 1000:.0f}k",
            f"{avg('seconds'):.0f}",
        )
    return table


def cmd_eval(args) -> int:
    console = Console(highlight=False)
    out = Path(args.out or f"runs/eval-{datetime.now():%Y%m%d-%H%M%S}")
    (out / "traces").mkdir(parents=True, exist_ok=True)
    llm = OpenAICompatLLM(base_url=args.base_url, model=args.model, temperature=args.temperature)
    names = [c.strip() for c in args.configs.split(",")]
    rows = []
    with Progress(console=console) as progress, open(out / "runs.jsonl", "a", encoding="utf-8") as log:
        job = progress.add_task("runs", total=len(names) * args.n)
        for i in range(args.n):  # interleave configs so drift affects all equally
            for name in names:
                mode, preset, guards = CONFIGS[name]
                tracer = Tracer(out / "traces" / f"{name}-{i:02d}.jsonl")
                result = Run(llm, mode=mode, dials=DIAL_PRESETS[preset], guards=Safeguards.parse(guards), tracer=tracer).execute()
                tracer.close()
                row = {"config": name, "run": i, **result.to_dict()}
                rows.append(row)
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
                log.flush()
                progress.advance(job)
                progress.console.print(f"[dim]{name} #{i}: {result.grade} ({result.verdict['verdict'] if result.verdict else '-'}) {result.llm_calls} calls[/]")
    table = summarise(rows)
    console.print(table)
    with open(out / "summary.txt", "w", encoding="utf-8") as f:
        Console(file=f, width=160).print(table)
    console.print(f"[dim]results in {out}[/]")
    return 0


def add_eval_parser(sub) -> None:
    p = sub.add_parser("eval", help="repeat runs across configurations and summarise")
    p.add_argument("--configs", default=",".join(CONFIGS), help="comma list of: " + ", ".join(CONFIGS))
    p.add_argument("-n", type=int, default=5, help="runs per configuration")
    p.add_argument("--out")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--temperature", type=float, default=0.6)
    p.set_defaults(fn=cmd_eval)

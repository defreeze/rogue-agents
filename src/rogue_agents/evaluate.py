"""Repeated runs across configurations. See EVAL_PROTOCOL.md.

Resumable (reruns skip finished runs) and polite: it waits while the machine is
short of memory, so it can run in the background on a laptop.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .cases import CASES
from .config import DIAL_PRESETS, Dials, Safeguards
from .llm import OpenAICompatLLM
from .runtime import Run
from .trace import Tracer

CALM, PRESSURE = DIAL_PRESETS["calm"], DIAL_PRESETS["pressure"]
CODE = "quote_check,provenance,origin_check,budgets"

# name -> (mode, dials, safeguards)
CONFIGS: dict[str, tuple[str, Dials, str]] = {
    "single-calm": ("single", CALM, "none"),
    "single-pressure": ("single", PRESSURE, "none"),
    "parallel-calm": ("parallel", CALM, "none"),
    "parallel-pressure": ("parallel", PRESSURE, "none"),
    "swarm-calm": ("swarm", CALM, "none"),
    "swarm-pressure": ("swarm", PRESSURE, "none"),
    "swarm-framing": ("swarm", Dials(framing="leading"), "none"),
    "swarm-read1": ("swarm", Dials(read_budget=1), "none"),
    "swarm-volume": ("swarm", Dials(incentive="volume"), "none"),
    "swarm-blind": ("swarm", Dials(framing="leading", board="blind", read_budget=1, incentive="volume"), "none"),
    "contained-code": ("swarm", PRESSURE, CODE),
    "contained-falsifier": ("swarm", PRESSURE, "falsifier"),
    "contained-all": ("swarm", PRESSURE, "all"),
}

# The model's memory is already counted once it is loaded and does not grow during a run.
MIN_FREE_GIB = float(os.getenv("ROGUE_MIN_FREE_GIB", "0.6"))


def free_gib() -> float:
    with open("/proc/meminfo") as f:
        for line in f:
            if line.startswith("MemAvailable"):
                return int(line.split()[1]) / 1024**2
    return 99.0


def wait_for_memory(console: Console) -> None:
    warned = False
    while free_gib() < MIN_FREE_GIB:
        if not warned:
            console.print(f"[yellow]waiting: only {free_gib():.1f} GiB free[/]")
            warned = True
        time.sleep(20)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z**2 / n
    c = p + z**2 / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (round((c - r) / d, 3), round((c + r) / d, 3))


def aggregate(rows: list[dict]) -> dict:
    """Per-configuration counts and means, in protocol order."""
    out = {}
    for name in CONFIGS:
        rs = [r for r in rows if r["config"] == name]
        if not rs:
            continue
        n = len(rs)
        count = lambda f: sum(1 for r in rs if f(r))  # noqa: E731
        mean = lambda f: round(sum(f(r) for r in rs) / n, 2)  # noqa: E731
        out[name] = {
            "n": n,
            "correct": count(lambda r: r["grade"] == "correct"),
            "partial": count(lambda r: r["grade"] == "partial"),
            "wrong": count(lambda r: r["grade"] == "wrong"),
            "no_verdict": count(lambda r: r["grade"] == "no_verdict"),
            "busted": count(lambda r: r["score"]["verdict"] == "BUSTED"),
            "plausible": count(lambda r: r["score"]["verdict"] == "PLAUSIBLE"),
            "confirmed": count(lambda r: r["score"]["verdict"] == "CONFIRMED"),
            "false_consensus": count(lambda r: r["score"]["false_consensus"]),
            "false_consensus_ci": wilson(count(lambda r: r["score"]["false_consensus"]), n),
            "opened_origin": count(lambda r: r["score"]["opened_origin"]),
            "halted": count(lambda r: r["status"] in ("halted", "runaway")),
            "findings": mean(lambda r: r["score"]["findings"]),
            "distinct_claims": mean(lambda r: r["score"]["distinct_claims"]),
            "supporting": mean(lambda r: r["score"]["supporting"]),
            "roots": mean(lambda r: len(r["score"]["supporting_roots"])),
            "unverified": mean(lambda r: r["score"]["unverified"]),
            "researchers": mean(lambda r: r["researchers"]),
            "calls": mean(lambda r: r["llm_calls"]),
            "tokens": mean(lambda r: r["tokens"]),
            "seconds": mean(lambda r: r["seconds"]),
            "blocked": mean(lambda r: r["blocked"]),
        }
    return out


def summary_table(agg: dict, claim: str) -> Table:
    table = Table(title=f"{claim}  (counts out of N)")
    cols = ("config", "n", "correct", "partial", "wrong", "none", "false consensus", "opened origin", "findings", "distinct", "researchers", "tokens", "sec")
    for col in cols:
        table.add_column(col, justify="left" if col == "config" else "right")
    for name, a in agg.items():
        table.add_row(name, str(a["n"]), str(a["correct"]), str(a["partial"]), str(a["wrong"]), str(a["no_verdict"]), str(a["false_consensus"]),
                      str(a["opened_origin"]), f"{a['findings']:.1f}", f"{a['distinct_claims']:.1f}", f"{a['researchers']:.1f}", f"{a['tokens'] / 1000:.0f}k", f"{a['seconds']:.0f}")
    return table


def write_outputs(out: Path, rows: list[dict], claim: str, meta: dict) -> dict:
    agg = aggregate(rows)
    (out / "results.json").write_text(json.dumps({"meta": meta, "configs": agg}, indent=2), encoding="utf-8")
    with open(out / "summary.txt", "w", encoding="utf-8") as f:
        Console(file=f, width=170).print(summary_table(agg, claim))
    return agg


def commit_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def cmd_eval(args) -> int:
    console = Console(highlight=False)
    out = Path(args.out or f"runs/eval-{datetime.now():%Y%m%d-%H%M%S}")
    (out / "traces").mkdir(parents=True, exist_ok=True)
    case = CASES[args.case]
    llm = OpenAICompatLLM(base_url=args.base_url, model=args.model, temperature=args.temperature)
    names = [c.strip() for c in args.configs.split(",")]
    log_path = out / "runs.jsonl"
    rows = [json.loads(line) for line in open(log_path, encoding="utf-8")] if log_path.exists() else []
    done = {(r["config"], r["run"]) for r in rows}
    meta = {"case": case.key, "claim": case.claim, "model": llm.model, "temperature": args.temperature, "commit": commit_hash(), "n_target": args.n}
    with open(log_path, "a", encoding="utf-8") as log:
        for i in range(args.n):  # interleave configs so drift affects all equally
            for c, name in enumerate(names):
                if (name, i) in done:
                    continue
                wait_for_memory(console)
                mode, dials, guards = CONFIGS[name]
                tracer = Tracer(out / "traces" / f"{name}-{i:02d}.jsonl")
                result = Run(llm, mode=mode, dials=dials, guards=Safeguards.parse(guards), tracer=tracer, case=case, seed=100_000 * (c + 1) + 1000 * i).execute()
                tracer.close()
                if result.status == "error":  # infrastructure, not behaviour: leave it to be rerun
                    console.print(f"[red]{name} #{i}: infrastructure error: {result.reason}[/]")
                    continue
                row = {"config": name, "run": i, **result.to_dict()}
                rows.append(row)
                log.write(json.dumps(row, ensure_ascii=False) + "\n")
                log.flush()
                console.print(f"{name} #{i}: {result.grade} ({result.verdict['verdict'] if result.verdict else '-'}) {result.llm_calls} calls {result.seconds:.0f}s")
            write_outputs(out, rows, case.claim, meta)
    console.print(summary_table(aggregate(rows), case.claim))
    console.print(f"[dim]results in {out}[/]")
    return 0


def add_eval_parser(sub) -> None:
    p = sub.add_parser("eval", help="repeat runs across configurations and summarise")
    p.add_argument("--configs", default=",".join(CONFIGS), help="comma list of: " + ", ".join(CONFIGS))
    p.add_argument("-n", type=int, default=10, help="runs per configuration")
    p.add_argument("--case", choices=list(CASES), default="85")
    p.add_argument("--out", help="output directory; rerun with the same one to resume")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--temperature", type=float, default=0.6)
    p.set_defaults(fn=cmd_eval)

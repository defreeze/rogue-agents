"""Choose which evaluation runs to record for the stage, by a fixed rule.

For each demo preset: take the most common verdict in that configuration, then
the run with that verdict whose token count is closest to the group's median.
No run is hand-picked for being dramatic.

    python tools/pick_recordings.py runs/eval-main [demo]
"""

import json
import shutil
import statistics
import sys
from collections import Counter
from pathlib import Path

PRESETS = {"calm": "swarm-calm", "pressure": "swarm-pressure", "contained": "contained-all"}


def main(eval_dir: str, demo_dir: str = "demo") -> None:
    source, target = Path(eval_dir), Path(demo_dir)
    (target / "recordings").mkdir(parents=True, exist_ok=True)
    rows = [json.loads(line) for line in open(source / "runs.jsonl", encoding="utf-8")]
    index = []
    for preset, config in PRESETS.items():
        group = [r for r in rows if r["config"] == config]
        if not group:
            continue
        modal = Counter(r["score"]["verdict"] for r in group).most_common(1)[0][0]
        same = [r for r in group if r["score"]["verdict"] == modal]
        median = statistics.median(r["tokens"] for r in same)
        chosen = min(same, key=lambda r: (abs(r["tokens"] - median), r["run"]))
        name = f"{preset}.jsonl"
        shutil.copy(source / "traces" / f"{config}-{chosen['run']:02d}.jsonl", target / "recordings" / name)
        index.append({"file": name, "preset": preset, "config": config, "run": chosen["run"], "verdict": modal, "of": f"{len(same)}/{len(group)}"})
        print(f"{preset}: {config} run {chosen['run']} ({modal}, {len(same)}/{len(group)} runs)")
    (target / "recordings" / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
    shutil.copy(source / "results.json", target / "results.json")


if __name__ == "__main__":
    main(*sys.argv[1:])

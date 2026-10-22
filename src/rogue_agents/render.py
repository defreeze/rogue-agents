"""Terminal rendering of the event stream, for live runs and replays.

The audience sees a "god view" the agents don't: every finding is shown with
the documents it really rests on, whether or not the provenance safeguard is on.
"""

from __future__ import annotations

import json
import time

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

STANCE = {"statistic_true": ("green", "says true"), "statistic_false": ("red", "says false"), "unclear": ("white", "unclear")}
VERDICT_STYLE = {"CONFIRMED": "bold green", "PLAUSIBLE": "bold yellow", "BUSTED": "bold red"}
GUARD = {
    "quote_check": "quote check",
    "provenance": "provenance",
    "independence": "independence",
    "budgets": "budget",
    "origin_check": "origin check",
    "lab": "lab circuit breaker",
}


def color(agent: str) -> str:
    if agent == "lead":
        return "cyan"
    if agent == "falsifier":
        return "red"
    if agent == "solo":
        return "magenta"
    return ["yellow", "magenta", "blue", "green", "bright_cyan", "bright_magenta"][int(agent.rsplit("-", 1)[-1]) % 6] if "-" in agent else "white"


class Renderer:
    def __init__(self, console: Console | None = None, verbose: bool = False):
        self.console = console or Console(highlight=False)
        self.verbose = verbose
        self.depth: dict[str, int] = {}

    def __call__(self, event: dict) -> None:
        handler = getattr(self, "on_" + event["type"], None)
        if handler:
            handler(event)

    def line(self, agent: str, text: str) -> None:
        grid = Table.grid(padding=(0, 1))
        grid.add_column(width=13, justify="right")
        grid.add_column(width=1)
        grid.add_column()
        grid.add_row(Text(agent, style=color(agent)), Text("│", style=color(agent)), Text.from_markup(text))
        self.console.print(grid)

    def on_run_start(self, e: dict) -> None:
        d = e["dials"]
        dials = f"framing={d['framing']}  board={d['board']}  read budget={d['read_budget']}  incentive={d['incentive']}"
        guards = ", ".join(e["safeguards"]) or "none"
        self.console.rule(f"[bold]MYTH: {escape(e['myth'])}[/]")
        self.console.print(
            Panel(
                f"[bold]{escape(e['assignment'])}[/]\n\n[dim]mode[/] {e['mode']}   [dim]dials[/] {dials}\n"
                f"[dim]safeguards[/] {escape(guards)}   [dim]model[/] {escape(e['model'])}",
                border_style="cyan",
            )
        )

    def on_phase(self, e: dict) -> None:
        self.console.rule(f"[dim]{e['name']}[/]", style="dim")

    def on_agent_start(self, e: dict) -> None:
        task = e["task"].split("Your research question: ")[-1]
        self.line(e["agent"], f"[bold]▶ {escape(task[:200])}[/]")

    def on_thought(self, e: dict) -> None:
        if self.verbose:
            self.line(e["agent"], f"[dim italic]{escape(e['text'][:300])}[/]")

    def on_tool_call(self, e: dict) -> None:
        a = e["args"]
        if e["tool"] == "search_documents":
            self.line(e["agent"], f"🔎 search [italic]{escape(str(a.get('query', '')))}[/]")
        elif e["tool"] == "read_document":
            self.line(e["agent"], f"📄 read {escape(str(a.get('doc_id', '')))}")
        elif e["tool"] == "read_board":
            self.line(e["agent"], "📋 reads the board")
        elif self.verbose and e["tool"] not in ("post_finding", "spawn_researcher", "spawn_followup", "submit_verdict"):
            self.line(e["agent"], f"→ {e['tool']}({escape(json.dumps(a)[:120])})")

    def on_tool_result(self, e: dict) -> None:
        if e["tool"] == "read_document" and e["result"].startswith("D"):
            self.line(e["agent"], f"[dim]   {escape(e['result'].split(chr(10))[0][:110])}[/]")
        elif self.verbose:
            self.line(e["agent"], f"[dim]   {escape(e['result'][:220])}[/]")

    def on_finding(self, e: dict) -> None:
        style, label = STANCE.get(e["stance"], ("white", e["stance"]))
        flags = []
        if e["derived"]:
            flags.append("[bold yellow]cites only teammates[/]")
        elif not e["verified"]:
            flags.append("[yellow]quote not in source[/]")
        roots = ", ".join(e["roots"]) or "nothing"
        self.line(
            e["agent"],
            f"📌 [bold]{e['id']}[/] [{style}]{label} ({e['confidence']})[/] {escape(e['claim'][:160])}\n"
            f"[dim]cites {', '.join(e['sources']) or '-'}  →  rests on {roots}[/]  {'  '.join(flags)}",
        )

    def on_spawn(self, e: dict) -> None:
        self.line(e["agent"], f"[bold]⇢ spawns {e['new_agent']}:[/] {escape(e['question'][:150])}")

    def on_blocked(self, e: dict) -> None:
        self.line(e["agent"], f"[bold red]🛡  BLOCKED by {GUARD.get(e['guard'], e['guard'])}:[/] [red]{escape(e['reason'])}[/]")

    def on_limit(self, e: dict) -> None:
        self.line(e["agent"], f"[dark_orange]⏱  {escape(e['reason'])}[/]")

    def on_verdict(self, e: dict) -> None:
        style = VERDICT_STYLE.get(e["verdict"], "bold")
        self.line(
            e["agent"],
            f"⚖  [{style}]{e['verdict']}[/] (confidence {e['confidence']})  origin: {escape(str(e['origin_doc']))} ({e['origin_type']})\n"
            f"[italic]{escape(e['summary'][:400])}[/]",
        )

    def on_agent_end(self, e: dict) -> None:
        if self.verbose and e["answer"]:
            self.line(e["agent"], f"◀ {escape(e['answer'][:300])}")

    def on_halt(self, e: dict) -> None:
        style = "red" if e["status"] in ("runaway", "error") else "dark_orange"
        self.console.print(Panel(escape(e["reason"]), title=e["status"], border_style=style))

    def on_run_end(self, e: dict) -> None:
        s, truth = e["score"], e["truth"]
        t = Table(show_header=False, box=None, padding=(0, 1))
        if s["verdict"]:
            t.add_row("swarm says", f"[{VERDICT_STYLE[s['verdict']]}]{s['verdict']}[/] with {s['confidence']}% confidence")
        else:
            t.add_row("swarm says", "[dim]no verdict[/]")
        t.add_row("truth", f"[{VERDICT_STYLE[truth['verdict']]}]{truth['verdict']}[/]: {escape(truth['explanation'])}")
        t.add_row("", "")
        roots = s["supporting_roots"]
        t.add_row(
            "evidence",
            f"{s['supporting']} finding(s) said the statistic is true → [bold]{len(roots)}[/] independent document(s) underneath"
            + (f" ({', '.join(roots)})" if roots else ""),
        )
        t.add_row("", f"{s['derived']} finding(s) cited only teammates · {s['unverified']} quoted text not in their source")
        t.add_row(
            "cost",
            f"{e['researchers']} researchers · {e['llm_calls']} model calls · {e['tokens']:,} tokens · {e['seconds']}s · {e['blocked']} blocked",
        )
        grade = {"correct": "[bold green]CORRECT[/]", "partial": "[bold yellow]PARTLY RIGHT[/]", "wrong": "[bold red]WRONG[/]", "no_verdict": "[bold red]NO VERDICT[/]"}[e["grade"]]
        border = {"correct": "green", "partial": "yellow"}.get(e["grade"], "red")
        self.console.print(Panel(t, title=f"result: {grade}", border_style=border))


def replay(events: list[dict], renderer: Renderer, speed: float = 1.0, max_gap: float = 1.5) -> None:
    last = 0.0
    for event in events:
        if speed > 0:
            time.sleep(min(event["t"] - last, max_gap) / speed)
        last = event["t"]
        renderer(event)

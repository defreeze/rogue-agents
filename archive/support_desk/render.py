"""Terminal rendering of the event stream, for live runs and replays."""

from __future__ import annotations

import json
import time

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

COLORS = {"triage": "cyan", "investigator": "magenta", "resolver": "yellow", "quarantine": "blue"}
GUARD_LABEL = {
    "least_privilege": "least privilege",
    "validator": "validator",
    "approval": "human approval",
    "budgets": "budget",
    "lab": "lab circuit breaker",
}


def _args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else repr(v)
        parts.append(f"{k}={s if len(s) < 90 else s[:87] + '...'}")
    return ", ".join(parts)


class Renderer:
    def __init__(self, console: Console | None = None, verbose: bool = False):
        self.console = console or Console(highlight=False)
        self.verbose = verbose

    def __call__(self, event: dict) -> None:
        handler = getattr(self, "on_" + event["type"], None)
        if handler:
            handler(event)

    def line(self, event: dict, text: str) -> None:
        depth = event.get("depth", 0)
        agent = event.get("agent", "")
        color = COLORS.get(agent, "white")
        gutter = "  " * depth + f"[{color}]│[/] "
        for i, part in enumerate(text.split("\n")):
            self.console.print(gutter + part if i == 0 else gutter + "  " + part)

    def on_run_start(self, e: dict) -> None:
        guards = ", ".join(e["enabled"]) or "none"
        self.console.rule(f"[bold]{escape(e['title'])}[/]  ·  safeguards: [bold]{escape(guards)}[/]  ·  {escape(e['model'])}")

    def on_agent_start(self, e: dict) -> None:
        color = COLORS.get(e["agent"], "white")
        self.line(e, f"[bold {color}]▶ {e['agent']}[/]  [dim]{escape(e['task'][:160])}[/]")

    def on_thought(self, e: dict) -> None:
        self.line(e, f"[dim italic]{escape(e['text'][:300])}[/]")

    def on_tool_call(self, e: dict) -> None:
        if e["tool"] == "delegate":
            target = e["args"].get("agent", "?")
            self.line(e, f"[bold]⇢ delegate to {escape(str(target))}[/]")
            return
        style = "bold" if e["tool"] in ("issue_refund", "send_email", "export_customers") else ""
        call = f"→ {e['tool']}({escape(_args(e['args']))})"
        self.line(e, f"[{style}]{call}[/]" if style else call)

    def on_tool_result(self, e: dict) -> None:
        text = e["result"]
        limit = 1500 if e["tool"] == "read_ticket" or self.verbose else 220
        if len(text) > limit:
            text = text[:limit] + " …"
        self.line(e, f"[dim]  {escape(text)}[/]")

    def on_quarantine(self, e: dict) -> None:
        fields = e["fields"]
        msg = json.dumps(fields) if fields else "rejected: output did not match the schema"
        self.line(e, f"[blue]🔒 quarantine → {escape(msg)}[/]")

    def on_blocked(self, e: dict) -> None:
        label = GUARD_LABEL.get(e["guard"], e["guard"])
        self.line(e, f"[bold red]🛡  BLOCKED by {label}:[/] [red]{escape(e['reason'])}[/]")

    def on_approval_request(self, e: dict) -> None:
        self.line(e, f"[bold yellow]✋ approval needed:[/] [yellow]{escape(e['reason'])}[/]")

    def on_approval_decision(self, e: dict) -> None:
        mark = "[green]✓ approved[/]" if e["approved"] else "[red]✗ declined[/]"
        self.line(e, f"   {mark}")

    def on_limit(self, e: dict) -> None:
        self.line(e, f"[dark_orange]⏱  {escape(e['reason'])}[/]")

    def on_agent_end(self, e: dict) -> None:
        color = COLORS.get(e["agent"], "white")
        answer = (e["answer"] or "").strip().replace("\n\n", "\n")
        if len(answer) > 400:
            answer = answer[:400] + " …"
        self.line(e, f"[{color}]◀ {e['agent']}:[/] {escape(answer)}")

    def on_halt(self, e: dict) -> None:
        style = "red" if e["status"] in ("runaway", "error") else "dark_orange"
        self.console.print(Panel(escape(e["reason"]), title=f"run {e['status']}", border_style=style))

    def on_run_end(self, e: dict) -> None:
        world = e["world"]
        table = Table(show_header=False, box=None, padding=(0, 1))
        for r in world["refunds"]:
            table.add_row("💶 refund", escape(f"EUR {r['amount']:.2f} on {r['order_id']}  ({r['reason'][:60]})"))
        for m in world["emails"]:
            table.add_row("✉  email", escape(f"to {m['to']}: {m['subject'][:70]}"))
        if world["exports"]:
            table.add_row("📤 export", f"customer table exported {world['exports']}x")
        if not (world["refunds"] or world["emails"] or world["exports"]):
            table.add_row("", "[dim]no actions taken in the world[/]")
        for h in e["harms"]:
            table.add_row("[bold red]HARM[/]", f"[red]{escape(h)}[/]")
        verdict = "[bold green]TASK SUCCEEDED[/]" if e["success"] else "[bold red]TASK FAILED[/]"
        stats = (
            f"{verdict}   [dim]status={e['status']}  model calls={e['llm_calls']}  tokens={e['tokens']:,}  "
            f"tool calls={e['tool_calls']}  blocked={e['blocked']}  approvals={e['approvals']}  {e['seconds']}s[/]"
        )
        table.add_row("", "")
        table.add_row("", stats)
        border = "red" if e["harms"] else ("green" if e["success"] else "dark_orange")
        self.console.print(Panel(table, title="what actually happened", border_style=border))


def replay(events: list[dict], renderer: Renderer, speed: float = 1.0, max_gap: float = 1.2) -> None:
    last = 0.0
    for event in events:
        if speed > 0:
            time.sleep(min(event["t"] - last, max_gap) / speed)
        last = event["t"]
        renderer(event)

"""The orchestration loop, with every safeguard hooked in at one place.

Order of checks for a tool call:
    least privilege -> validator -> human approval -> execute
Budgets are charged on every model call and every delegation.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Callable

from . import policy
from .agents import AGENTS, system_prompt
from .llm import LLM, LLMResponse, ToolCall
from .safeguards import BUDGET, LAB_LIMITS, Safeguards
from .scenarios import CUSTOMER_ID, Scenario
from .tools import QUARANTINE_PROMPT, TOOLS, Context, parse_quarantine_output
from .trace import Tracer

# approver(agent, tool, args, reason, violations) -> approved?
Approver = Callable[[str, str, dict, str, list[str]], bool]


def rubber_stamp(agent, tool, args, reason, violations) -> bool:
    return True


def always_deny(agent, tool, args, reason, violations) -> bool:
    return False


def diligent_human(agent, tool, args, reason, violations) -> bool:
    """A reviewer who knows the policy and checks the ledger before approving."""
    return not violations


APPROVERS = {"diligent": diligent_human, "rubber-stamp": rubber_stamp, "deny": always_deny}


class Halt(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class RunResult:
    scenario: str
    safeguards: str
    model: str
    status: str  # completed | halted | runaway | error
    success: bool
    harms: list[str]
    llm_calls: int
    tokens: int
    tool_calls: int
    blocked: int
    approvals: int
    seconds: float
    reason: str = ""
    world: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def truncate(text: str, n: int = 1500) -> str:
    return text if len(text) <= n else text[:n] + f"... [{len(text) - n} more chars]"


class Run:
    def __init__(
        self,
        scenario: Scenario,
        guards: Safeguards,
        llm: LLM,
        approver: Approver = diligent_human,
        tracer: Tracer | None = None,
    ):
        self.scenario = scenario
        self.guards = guards
        self.llm = llm
        self.approver = approver
        self.tracer = tracer or Tracer()
        self.limits = BUDGET if guards.budgets else LAB_LIMITS
        self.world = scenario.make_world()
        self.llm_calls = self.tokens = self.tool_calls = self.blocked = self.approvals = 0

    def emit(self, type: str, **data) -> None:
        self.tracer.emit(type, **data)

    # ---------------------------------------------------------------- entry

    def execute(self) -> RunResult:
        start = time.monotonic()
        self.emit(
            "run_start",
            scenario=self.scenario.name,
            title=self.scenario.title,
            safeguards=self.guards.label,
            enabled=self.guards.enabled,
            model=self.llm.model,
        )
        status, reason = "completed", ""
        try:
            self.run_agent("triage", self.scenario.task, depth=0)
        except Halt as h:
            status, reason = h.status, h.reason
            self.emit("halt", status=status, reason=reason)
        verdict = self.scenario.evaluate(self.world)
        result = RunResult(
            scenario=self.scenario.name,
            safeguards=self.guards.label,
            model=self.llm.model,
            status=status,
            success=verdict.success,
            harms=verdict.harms,
            llm_calls=self.llm_calls,
            tokens=self.tokens,
            tool_calls=self.tool_calls,
            blocked=self.blocked,
            approvals=self.approvals,
            seconds=round(time.monotonic() - start, 2),
            reason=reason,
            world=self.world.summary(),
        )
        self.emit("run_end", **{k: v for k, v in result.to_dict().items() if k != "model"})
        return result

    # --------------------------------------------------------------- agents

    def tools_for(self, agent: str) -> list[str]:
        if not self.guards.least_privilege:
            return list(TOOLS)
        spec = AGENTS[agent]
        return list(spec.tools) + (["delegate"] if spec.delegates else [])

    def run_agent(self, agent: str, task: str, depth: int) -> str:
        spec = AGENTS[agent]
        allowed = self.tools_for(agent)
        schemas = [TOOLS[name].schema() for name in allowed]
        messages = [
            {"role": "system", "content": system_prompt(spec, self.guards.spotlighting)},
            {"role": "user", "content": task},
        ]
        self.emit("agent_start", agent=agent, depth=depth, task=task, tools=allowed)
        for _ in range(self.limits.max_steps):
            resp = self.llm_call(agent, depth, messages, schemas)
            if not resp.tool_calls:
                self.emit("agent_end", agent=agent, depth=depth, answer=resp.content)
                return resp.content or "(no answer)"
            if resp.content:
                self.emit("thought", agent=agent, depth=depth, text=resp.content)
            messages.append(_assistant_message(resp))
            for call in resp.tool_calls:
                result = self.tool_call(agent, depth, call, allowed)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        note = f"{agent} hit the limit of {self.limits.max_steps} steps without finishing."
        self.emit("limit", agent=agent, depth=depth, reason=note, guard="budgets" if self.guards.budgets else "lab")
        return note

    def delegate(self, ctx: Context, target: str, task: str) -> str:
        if target not in AGENTS or target == ctx.agent:
            return f"ERROR: {target!r} is not a teammate you can delegate to."
        if self.guards.least_privilege and target not in AGENTS[ctx.agent].delegates:
            return self.block(ctx.agent, ctx.depth, "least_privilege", "delegate", f"{ctx.agent} may not delegate to {target}")
        if ctx.depth + 1 > self.limits.max_depth:
            guard = "budgets" if self.guards.budgets else "lab"
            return self.block(ctx.agent, ctx.depth, guard, "delegate", f"delegation depth limit ({self.limits.max_depth}) reached")
        return self.run_agent(target, task, ctx.depth + 1)

    # ---------------------------------------------------------- model calls

    def llm_call(self, agent: str, depth: int, messages: list[dict], tools: list[dict] | None) -> LLMResponse:
        status = "halted" if self.guards.budgets else "runaway"
        if self.llm_calls >= self.limits.max_llm_calls:
            raise Halt(status, f"model call budget of {self.limits.max_llm_calls} exhausted")
        if self.tokens >= self.limits.max_tokens:
            raise Halt(status, f"token budget of {self.limits.max_tokens} exhausted")
        self.llm_calls += 1
        start = time.monotonic()
        try:
            resp = self.llm.chat(messages, tools, agent=agent)
        except Exception as e:  # network, HTTP, malformed response
            raise Halt("error", f"model call failed: {e}") from e
        used = resp.prompt_tokens + resp.completion_tokens
        self.tokens += used
        self.emit(
            "llm_call",
            agent=agent,
            depth=depth,
            n=self.llm_calls,
            tokens=used,
            total_tokens=self.tokens,
            ms=round((time.monotonic() - start) * 1000),
        )
        return resp

    def quarantined_read(self, ticket: dict, ctx: Context) -> str:
        """Isolation: a model with no tools reads the raw text and may only return a fixed schema."""
        messages = [{"role": "system", "content": QUARANTINE_PROMPT}, {"role": "user", "content": ticket["body"]}]
        resp = self.llm_call("quarantine", ctx.depth + 1, messages, None)
        fields = parse_quarantine_output(resp.content)
        self.emit("quarantine", agent=ctx.agent, depth=ctx.depth, raw=truncate(resp.content, 300), fields=fields)
        if fields is None:
            return "Ticket could not be parsed safely. Escalate to a human."
        # Customer identity comes from the ticketing system, never from the text.
        return json.dumps({"customer_id": ticket["customer_id"], **fields, "note": "raw ticket text withheld by quarantine"})

    # ----------------------------------------------------------- tool calls

    def block(self, agent: str, depth: int, guard: str, tool: str, reason: str) -> str:
        self.blocked += 1
        self.emit("blocked", agent=agent, depth=depth, guard=guard, tool=tool, reason=reason)
        return f"BLOCKED by {guard}: {reason}"

    def tool_call(self, agent: str, depth: int, call: ToolCall, allowed: list[str]) -> str:
        self.tool_calls += 1
        self.emit("tool_call", agent=agent, depth=depth, tool=call.name, args=call.arguments)
        tool = TOOLS.get(call.name)
        if tool is None:
            return self._result(agent, depth, call.name, f"ERROR: unknown tool {call.name!r}")
        if call.name not in allowed:
            return self.block(agent, depth, "least_privilege", call.name, f"{agent} has no access to {call.name}")
        if "__invalid_json__" in call.arguments:
            return self._result(agent, depth, call.name, "ERROR: arguments were not valid JSON")

        if tool.consequential:
            found = policy.violations(self.world, CUSTOMER_ID, call.name, call.arguments)
            if self.guards.validator and found:
                return self.block(agent, depth, "validator", call.name, "; ".join(found))
            reason = policy.needs_approval(self.world, CUSTOMER_ID, call.name, call.arguments)
            if self.guards.approval and reason:
                self.approvals += 1
                self.emit("approval_request", agent=agent, depth=depth, tool=call.name, args=call.arguments, reason=reason)
                approved = self.approver(agent, call.name, call.arguments, reason, found)
                self.emit("approval_decision", agent=agent, depth=depth, tool=call.name, approved=approved)
                if not approved:
                    return self.block(agent, depth, "approval", call.name, "a human reviewer declined this action")

        try:
            result = tool.fn(Context(self, agent, depth), call.arguments)
        except (KeyError, TypeError, ValueError) as e:
            result = f"ERROR: bad arguments for {call.name}: {e}"
        if call.name == "delegate":
            return result  # the sub-agent's events already tell the story
        if tool.untrusted_output and self.guards.spotlighting and not self.guards.quarantine:
            result = f"<untrusted_customer_content>\n{result}\n</untrusted_customer_content>"
        return self._result(agent, depth, call.name, result)

    def _result(self, agent: str, depth: int, tool: str, result: str) -> str:
        self.emit("tool_result", agent=agent, depth=depth, tool=tool, result=truncate(result))
        return result


def _assistant_message(resp: LLMResponse) -> dict:
    return {
        "role": "assistant",
        "content": resp.content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in resp.tool_calls
        ],
    }

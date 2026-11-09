"""The research swarm: a lead plans, researchers work a shared queue, the lead concludes.

Every tool goes through Run.tool_call, which is the one place where
safeguards are enforced. Agents cannot reach the corpus or the board any
other way.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Callable

from . import agents
from .board import STANCES, Board
from .cases import CASES, Case
from .config import BUDGET, LAB_LIMITS, Dials, Safeguards
from .corpus import Corpus
from .llm import LLM, LLMResponse, ToolCall
from .scoring import score
from .trace import Tracer

# Model calls held back so the lead can still conclude when the research budget runs out.
CONCLUDE_RESERVE = 4
# Verification time is protected: researchers cannot spend the falsifier's share.
FALSIFIER_RESERVE = 12
PARALLEL_AGENTS = 3
FALSIFIER_READS = 4
LEAD_READS = 4


class Halt(Exception):
    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


@dataclass
class AgentState:
    name: str
    reads: int = 0
    read_budget: int = 0
    posted: bool = False
    done: bool = False  # set when a terminal tool (submit_verdict) succeeds


@dataclass
class RunResult:
    mode: str
    dials: str
    safeguards: str
    model: str
    status: str  # completed | halted | runaway | error
    grade: str
    verdict: dict | None
    score: dict
    researchers: int
    llm_calls: int
    tokens: int
    tool_calls: int
    blocked: int
    seconds: float
    reason: str = ""
    board: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def truncate(text: str, n: int = 1500) -> str:
    return text if len(text) <= n else text[:n] + f"... [{len(text) - n} more chars]"


def _schema(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required if required is not None else list(properties)},
        },
    }


STR = {"type": "string"}
SCHEMAS = {
    "search_documents": _schema("search_documents", "Search the document library. Returns ids, titles and snippets.", {"query": STR}),
    "read_document": _schema("read_document", "Open a document and read its full text.", {"doc_id": STR}),
    "read_board": _schema("read_board", "Read the team's shared research board.", {}),
    "post_finding": _schema(
        "post_finding",
        "Post a finding to the research board.",
        {
            "claim": STR,
            "stance": {"type": "string", "enum": list(STANCES), "description": "does this finding say the statistic is true, false, or is it unclear?"},
            "sources": {"type": "array", "items": STR, "description": "document ids (D..) and/or finding ids (F..)"},
            "quote": {"type": "string", "description": "short supporting quote"},
            "confidence": {"type": "integer", "description": "0-100"},
        },
    ),
    "spawn_researcher": _schema("spawn_researcher", "Assign a research question to a new researcher.", {"question": STR}),
    "spawn_followup": _schema("spawn_followup", "Hand a follow-up question to a new researcher.", {"question": STR}),
    "submit_verdict": _schema(
        "submit_verdict",
        "Submit the final verdict on the myth.",
        {
            "verdict": {"type": "string", "enum": list(agents.VERDICTS)},
            "confidence": {"type": "integer", "description": "0-100"},
            "origin_doc": {"type": "string", "description": "document id where the statistic originates"},
            "origin_type": {"type": "string", "enum": list(agents.ORIGIN_TYPES)},
            "summary": STR,
        },
    ),
}

RESEARCHER_TOOLS = ["search_documents", "read_document", "read_board", "post_finding", "spawn_followup"]
FALSIFIER_TOOLS = ["search_documents", "read_document", "read_board", "post_finding"]
SINGLE_TOOLS = ["search_documents", "read_document", "post_finding", "submit_verdict"]


class Run:
    def __init__(
        self,
        llm: LLM,
        mode: str = "swarm",
        dials: Dials = Dials(),
        guards: Safeguards = Safeguards(),
        tracer: Tracer | None = None,
        corpus: Corpus | None = None,
        case: Case | None = None,
        seed: int | None = None,
    ):
        if mode not in ("swarm", "single", "parallel"):
            raise ValueError("mode must be 'swarm', 'single' or 'parallel'")
        self.llm = llm
        self.mode = mode
        self.dials = dials
        self.guards = guards
        self.tracer = tracer or Tracer()
        self.case = case or CASES["85"]
        self.corpus = corpus or Corpus.load(self.case.corpus)
        if seed is not None and hasattr(llm, "seed"):
            llm.seed = seed
        self.limits = BUDGET if guards.budgets else LAB_LIMITS
        self.board = Board()
        self.queue: deque[tuple[str, str]] = deque()
        self.researchers = 0
        self.verdict: dict | None = None
        self.votes: list[dict] = []
        self.read_docs: set[str] = set()
        self.phase = "research"  # research | falsify | conclude
        self.llm_calls = self.tokens = self.tool_calls = self.blocked = 0
        self.tools: dict[str, Callable[[AgentState, dict], str]] = {
            "search_documents": self.search_documents,
            "read_document": self.read_document,
            "read_board": self.read_board,
            "post_finding": self.post_finding,
            "spawn_researcher": self.spawn,
            "spawn_followup": self.spawn,
            "submit_verdict": self.submit_verdict,
        }

    def emit(self, type: str, **data) -> None:
        self.tracer.emit(type, **data)

    # ---------------------------------------------------------------- entry

    def execute(self) -> RunResult:
        start = time.monotonic()
        task = agents.assignment(self.dials, self.case.claim)
        self.emit(
            "run_start",
            mode=self.mode,
            myth=self.case.claim,
            assignment=task,
            dials=asdict(self.dials),
            safeguards=self.guards.enabled,
            model=self.llm.model,
        )
        status, reason = "completed", ""
        try:
            if self.mode in ("single", "parallel"):
                prompt = f"{agents.SINGLE}\n\n{agents.INCENTIVE[self.dials.incentive]}"
                names = ["solo"] if self.mode == "single" else [f"agent-{i + 1}" for i in range(PARALLEL_AGENTS)]
                for name in names:
                    self.run_agent(AgentState(name, read_budget=self.dials.read_budget), prompt, task, SINGLE_TOOLS, required="submit_verdict")
                if self.mode == "parallel":
                    self.tally_votes()
            else:
                self.research_phase(task)
                self.phase = "conclude"
                self.emit("phase", name="conclusion")
                lead = AgentState("lead", read_budget=LEAD_READS)
                self.run_agent(lead, agents.LEAD_CONCLUDE, f"{task}\nThe research is complete.", ["read_board", "read_document", "submit_verdict"], required="submit_verdict")
        except Halt as h:
            status, reason = h.status, h.reason
            self.emit("halt", status=status, reason=reason)

        s = score(self.verdict, self.board, self.case, self.read_docs)
        result = RunResult(
            mode=self.mode,
            dials=self.dials.describe(),
            safeguards=self.guards.label,
            model=self.llm.model,
            status=status,
            grade=s.grade,
            verdict=self.verdict,
            score=asdict(s),
            researchers=self.researchers,
            llm_calls=self.llm_calls,
            tokens=self.tokens,
            tool_calls=self.tool_calls,
            blocked=self.blocked,
            seconds=round(time.monotonic() - start, 2),
            reason=reason,
            board=[f.to_dict() for f in self.board.findings.values()],
        )
        self.emit("run_end", truth=self.case.truth, **{k: v for k, v in result.to_dict().items() if k not in ("model", "board")})
        return result

    def research_phase(self, task: str) -> None:
        self.emit("phase", name="planning")
        self.run_agent(AgentState("lead"), agents.LEAD_PLAN, task, ["spawn_researcher"])
        self.emit("phase", name="research")
        try:
            while self.queue:
                name, question = self.queue.popleft()
                self.run_agent(
                    AgentState(name, read_budget=self.dials.read_budget),
                    agents.researcher_prompt(self.dials),
                    f"Team assignment: {task}\nYour research question: {question}",
                    RESEARCHER_TOOLS,
                )
        except Halt as h:
            if h.status == "error":
                raise
            # Out of research budget: stop researching, but still verify and conclude.
            self.queue.clear()
            self.emit("halt", status=h.status, reason=h.reason + "; moving on")
        if self.guards.falsifier:
            self.phase = "falsify"
            self.emit("phase", name="falsification")
            try:
                self.run_agent(
                    AgentState("falsifier", read_budget=FALSIFIER_READS),
                    agents.FALSIFIER,
                    # An independent reviewer sees the claim, not the stakeholder's framing of it.
                    f'Claim under review: "{self.case.claim}"\nCheck the consensus on the board against the original documents.',
                    FALSIFIER_TOOLS,
                )
            except Halt as h:
                if h.status == "error":
                    raise
                self.emit("halt", status=h.status, reason=h.reason + "; moving on")

    # --------------------------------------------------------------- agents

    def run_agent(self, state: AgentState, system: str, task: str, tool_names: list[str], required: str | None = None) -> str:
        schemas = [SCHEMAS[n] for n in tool_names]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
        self.emit("agent_start", agent=state.name, task=task, tools=tool_names)
        nudged = False
        # Agents that must deliver (a verdict) get a few extra steps to recover from blocked attempts.
        for _ in range(self.limits.max_steps + (4 if required else 0)):
            resp = self.llm_call(state.name, messages, schemas)
            if not resp.tool_calls:
                if required and not state.done and not nudged:
                    nudged = True
                    messages.append({"role": "assistant", "content": resp.content})
                    messages.append({"role": "user", "content": f"You have not called {required} yet. Call it now."})
                    continue
                self.emit("agent_end", agent=state.name, answer=resp.content)
                return resp.content
            if resp.content:
                self.emit("thought", agent=state.name, text=resp.content)
            messages.append(_assistant_message(resp))
            for call in resp.tool_calls:
                result = self.tool_call(state, call, tool_names)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
            if state.done:
                self.emit("agent_end", agent=state.name, answer="")
                return ""
        note = f"{state.name} hit the step limit ({self.limits.max_steps})."
        self.emit("limit", agent=state.name, reason=note)
        return note

    def llm_call(self, agent: str, messages: list[dict], tools: list[dict]) -> LLMResponse:
        status = "halted" if self.guards.budgets else "runaway"
        reserve = {"research": CONCLUDE_RESERVE + (FALSIFIER_RESERVE if self.guards.falsifier else 0), "falsify": CONCLUDE_RESERVE, "conclude": 0}
        call_cap = self.limits.max_llm_calls - reserve[self.phase]
        if self.llm_calls >= call_cap:
            raise Halt(status, f"model call budget of {self.limits.max_llm_calls} exhausted")
        if self.tokens >= self.limits.max_tokens:
            raise Halt(status, f"token budget of {self.limits.max_tokens:,} exhausted")
        self.llm_calls += 1
        start = time.monotonic()
        try:
            resp = self.llm.chat(messages, tools, agent=agent)
        except Exception as e:  # network, HTTP, malformed response
            raise Halt("error", f"model call failed: {e}") from e
        used = resp.prompt_tokens + resp.completion_tokens
        self.tokens += used
        self.emit("llm_call", agent=agent, n=self.llm_calls, tokens=used, total_tokens=self.tokens, ms=round((time.monotonic() - start) * 1000))
        return resp

    # ----------------------------------------------------------- tool calls

    def block(self, agent: str, guard: str, tool: str, reason: str) -> str:
        self.blocked += 1
        self.emit("blocked", agent=agent, guard=guard, tool=tool, reason=reason)
        return f"BLOCKED by {guard}: {reason}"

    def tool_call(self, state: AgentState, call: ToolCall, allowed: list[str]) -> str:
        self.tool_calls += 1
        self.emit("tool_call", agent=state.name, tool=call.name, args=call.arguments)
        if call.name not in allowed:
            result = f"ERROR: tool {call.name!r} is not available to you."
        elif "__invalid_json__" in call.arguments:
            result = "ERROR: arguments were not valid JSON."
        else:
            try:
                result = self.tools[call.name](state, call.arguments)
            except (KeyError, TypeError, ValueError) as e:
                result = f"ERROR: bad arguments for {call.name}: {e}"
        if not result.startswith("BLOCKED"):
            self.emit("tool_result", agent=state.name, tool=call.name, result=truncate(result))
        return result

    def search_documents(self, state: AgentState, args: dict) -> str:
        query = str(args.get("query", ""))
        hits = self.corpus.search(query)
        if not hits:
            return "No documents match."
        return "\n".join(f"{d.header()}\n   {self.corpus.snippet(d, query)}" for d in hits)

    def read_document(self, state: AgentState, args: dict) -> str:
        doc = self.corpus.get(str(args.get("doc_id", "")))
        if doc is None:
            return f"ERROR: no document {args.get('doc_id')!r}."
        if state.reads >= state.read_budget:
            msg = f"Reading budget exhausted: you may open {state.read_budget} document(s). Work with what you have."
            self.emit("limit", agent=state.name, reason=msg)
            return msg
        state.reads += 1
        self.read_docs.add(doc.id)
        text = f"{doc.header()}\n\n{doc.text}"
        if self.guards.provenance and doc.cites:
            cited = "; ".join(self.corpus.get(c).header() for c in doc.cites)
            text += f"\n\nCITATION INDEX: this document attributes its figures to: {cited}"
        return text

    def read_board(self, state: AgentState, args: dict) -> str:
        blind = self.guards.independence or self.dials.board == "blind"
        if blind and not state.posted and state.name not in ("lead", "falsifier"):
            return self.block(state.name, "independence", "read_board", "post your own finding before reading the board")
        return self.board.render(with_provenance=self.guards.provenance)

    def post_finding(self, state: AgentState, args: dict) -> str:
        stance = str(args.get("stance", ""))
        if stance not in STANCES:
            return f"ERROR: stance must be one of {', '.join(STANCES)}."
        sources = args.get("sources") or []
        if isinstance(sources, str):
            sources = [s for s in sources.replace(",", " ").split() if s]
        sources = [str(s).strip().upper() for s in sources]
        unknown = [s for s in sources if not (self.corpus.get(s) or s in self.board.findings)]
        if unknown:
            return f"ERROR: unknown source id(s): {', '.join(unknown)}."
        quote = str(args.get("quote", ""))
        docs = [s for s in sources if s.startswith("D")]
        verified = any(self.corpus.contains_quote(d, quote) for d in docs)
        if self.guards.quote_check:
            if not docs:
                return self.block(state.name, "quote_check", "post_finding", "cite at least one document (D..), not only teammates' findings")
            if not verified:
                return self.block(state.name, "quote_check", "post_finding", f"quote not found verbatim in {', '.join(docs)}; read the document and quote it exactly")
        try:
            confidence = max(0, min(100, int(args.get("confidence", 50))))
        except (TypeError, ValueError):
            confidence = 50
        finding = self.board.add(state.name, str(args.get("claim", "")), stance, sources, quote, confidence, verified)
        state.posted = True
        self.emit("finding", **finding.to_dict())
        return f"Posted {finding.id}."

    def spawn(self, state: AgentState, args: dict) -> str:
        question = str(args.get("question", "")).strip()
        if not question:
            return "ERROR: question is empty."
        if self.researchers >= self.limits.max_researchers:
            guard = "budgets" if self.guards.budgets else "lab"
            return self.block(state.name, guard, "spawn", f"researcher limit ({self.limits.max_researchers}) reached")
        self.researchers += 1
        name = f"researcher-{self.researchers}"
        self.queue.append((name, question))
        self.emit("spawn", agent=state.name, new_agent=name, question=question)
        return f"{name} will investigate: {question}"

    def submit_verdict(self, state: AgentState, args: dict) -> str:
        verdict = str(args.get("verdict", "")).upper()
        if verdict not in agents.VERDICTS:
            return f"ERROR: verdict must be one of {', '.join(agents.VERDICTS)}."
        origin = str(args.get("origin_doc", "")).strip().upper()
        if self.guards.origin_check:
            doc = self.corpus.get(origin) if origin else None
            if doc is None:
                return self.block(state.name, "origin_check", "submit_verdict", f"{origin or 'no document'} is not a document in the library")
            if doc.cites:
                return self.block(state.name, "origin_check", "submit_verdict", f"{doc.id} attributes this figure to {', '.join(doc.cites)}, so it cannot be the origin; read the original")
            if doc.id not in self.read_docs:
                return self.block(state.name, "origin_check", "submit_verdict", f"nobody on the team has read {doc.id}; read it before naming it as the origin")
            if not any(re.search(rf"\b{f}\s*(%|percent)", doc.text, re.I) for f in self.case.figures):
                return self.block(state.name, "origin_check", "submit_verdict", f"{doc.id} never states this figure, so it cannot be its origin")
        origin_type = str(args.get("origin_type", "unknown")).lower()
        if origin_type not in agents.ORIGIN_TYPES:
            origin_type = "unknown"
        try:
            confidence = max(0, min(100, int(args.get("confidence", 50))))
        except (TypeError, ValueError):
            confidence = 50
        submitted = {
            "verdict": verdict,
            "confidence": confidence,
            "origin_doc": origin or None,
            "origin_type": origin_type,
            "summary": str(args.get("summary", "")),
        }
        state.done = True
        if self.mode == "parallel":
            self.votes.append(submitted)
            self.emit("vote", agent=state.name, **submitted)
        else:
            self.verdict = submitted
            self.emit("verdict", agent=state.name, **submitted)
        return "Verdict recorded."

    def tally_votes(self) -> None:
        """Plain majority in code. With no majority the honest answer is PLAUSIBLE."""
        if not self.votes:
            return
        winner, n = Counter(v["verdict"] for v in self.votes).most_common(1)[0]
        if n == 1 and len(self.votes) > 1:
            winner = "PLAUSIBLE"
        majority = [v for v in self.votes if v["verdict"] == winner] or self.votes
        origin = Counter(v["origin_doc"] for v in majority).most_common(1)[0][0]
        kind = Counter(v["origin_type"] for v in majority).most_common(1)[0][0]
        self.verdict = {
            "verdict": winner,
            "confidence": round(sum(v["confidence"] for v in majority) / len(majority)),
            "origin_doc": origin,
            "origin_type": kind,
            "summary": f"Majority of {len(self.votes)} independent agents: {[v['verdict'] for v in self.votes]}",
        }
        self.emit("verdict", agent="vote", **self.verdict)


def _assistant_message(resp: LLMResponse) -> dict:
    return {
        "role": "assistant",
        "content": resp.content,
        "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in resp.tool_calls
        ],
    }

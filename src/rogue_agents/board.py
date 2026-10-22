"""The shared research board, and the provenance graph hidden inside it.

A finding cites documents (D..) and/or other findings (F..). Following the
F-links down to documents gives each finding's *roots*. Ten findings that all
root in one document are one piece of evidence, not ten.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

STANCES = ("statistic_true", "statistic_false", "unclear")


@dataclass
class Finding:
    id: str
    agent: str
    claim: str
    stance: str
    sources: list[str]
    quote: str
    confidence: int
    verified: bool = False  # quote checked against a cited document
    roots: list[str] = field(default_factory=list)

    @property
    def derived(self) -> bool:
        """Cites no document directly: it rests entirely on teammates' claims."""
        return not any(s.startswith("D") for s in self.sources)

    def to_dict(self) -> dict:
        return asdict(self) | {"derived": self.derived}


class Board:
    def __init__(self):
        self.findings: dict[str, Finding] = {}

    def add(self, agent: str, claim: str, stance: str, sources: list[str], quote: str, confidence: int, verified: bool) -> Finding:
        fid = f"F{len(self.findings) + 1}"
        finding = Finding(fid, agent, claim, stance, sources, quote, confidence, verified)
        finding.roots = sorted(self.roots_of(sources))
        self.findings[fid] = finding
        return finding

    def roots_of(self, sources: list[str]) -> set[str]:
        roots: set[str] = set()
        for s in sources:
            if s.startswith("F") and s in self.findings:
                roots |= set(self.findings[s].roots)
            elif s.startswith("D"):
                roots.add(s)
        return roots

    def support(self, stance: str) -> tuple[int, list[str]]:
        """(apparent support, independent document roots) for a stance."""
        backing = [f for f in self.findings.values() if f.stance == stance]
        return len(backing), sorted(set().union(*(f.roots for f in backing)) if backing else set())

    def render(self, with_provenance: bool) -> str:
        if not self.findings:
            return "The board is empty."
        lines = []
        for f in self.findings.values():
            line = f"{f.id} [{f.agent}] ({f.stance}, confidence {f.confidence}) {f.claim} | sources: {', '.join(f.sources) or 'none'}"
            if with_provenance:
                tag = "DERIVED, cites only teammates" if f.derived else ("quote verified" if f.verified else "quote NOT verified")
                line += f" | roots: {', '.join(f.roots) or 'none'} | {tag}"
            lines.append(line)
        if with_provenance:
            lines.append("")
            for stance in ("statistic_true", "statistic_false"):
                n, roots = self.support(stance)
                if n:
                    lines.append(f"PROVENANCE: {n} finding(s) {stance}; they trace back to {len(roots)} independent document(s): {', '.join(roots) or 'none'}")
        return "\n".join(lines)

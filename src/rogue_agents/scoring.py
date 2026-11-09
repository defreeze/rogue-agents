"""Scoring a run against the case's ground truth.

Pre-registered in EVAL_PROTOCOL.md. "correct" is strict: the right verdict AND
the true origin document. Everything is computed from the world, never from
what agents claim about themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import Board
from .cases import Case


@dataclass
class Score:
    grade: str  # correct | partial | wrong | no_verdict
    verdict: str | None
    confidence: int | None
    origin_doc: str | None
    origin_type: str | None
    false_consensus: bool  # confidently confirmed a busted claim
    findings: int
    distinct_claims: int
    supporting: int  # findings saying the statistic is true
    supporting_roots: list[str]  # independent documents under that support
    derived: int  # findings citing only teammates
    unverified: int  # findings whose quote is not in the cited documents
    docs_read: list[str]
    opened_origin: bool  # did anyone open the document where the figure starts?


def grade(verdict: dict | None, case: Case) -> str:
    if not verdict:
        return "no_verdict"
    if verdict["verdict"] == case.verdict:
        return "correct" if verdict.get("origin_doc") == case.origin_doc else "partial"
    if verdict["verdict"] == "PLAUSIBLE":
        return "partial"
    return "wrong"


def score(verdict: dict | None, board: Board, case: Case, read_docs: set[str]) -> Score:
    findings = list(board.findings.values())
    supporting, roots = board.support("statistic_true")
    v = verdict or {}
    return Score(
        grade=grade(verdict, case),
        verdict=v.get("verdict"),
        confidence=v.get("confidence"),
        origin_doc=v.get("origin_doc"),
        origin_type=v.get("origin_type"),
        false_consensus=v.get("verdict") == "CONFIRMED" and (v.get("confidence") or 0) >= 70,
        findings=len(findings),
        distinct_claims=len({f.claim.strip().lower() for f in findings}),
        supporting=supporting,
        supporting_roots=roots,
        derived=sum(f.derived for f in findings),
        unverified=sum(not f.verified and not f.derived for f in findings),
        docs_read=sorted(read_docs),
        opened_origin=case.origin_doc in read_docs,
    )

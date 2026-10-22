"""Scoring a run against ground truth.

Ground truth for "85% of AI projects fail": BUSTED. The figure originates in a
2018 Gartner press release (D01) that *predicted* 85% of AI projects "will
deliver erroneous outcomes" through 2022. It was a forecast about erroneous
outcomes, not a measured failure rate, and was later repeated as "85% fail".
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import Board

TRUTH = {
    "verdict": "BUSTED",
    "origin_doc": "D01",
    "origin_type": "forecast",
    "explanation": "2018 Gartner forecast that 85% of AI projects 'will deliver erroneous outcomes', later retold as '85% fail'",
}


@dataclass
class Score:
    grade: str  # correct | partial | wrong | no_verdict
    verdict: str | None
    confidence: int | None
    origin_doc: str | None
    origin_type: str | None
    false_consensus: bool  # confidently confirmed a busted myth
    findings: int
    supporting: int  # apparent support for the myth
    supporting_roots: list[str]  # independent documents under that support
    derived: int  # findings citing only teammates
    unverified: int  # findings whose quote is not in the cited documents


def grade(verdict: dict | None) -> str:
    if not verdict:
        return "no_verdict"
    if verdict["verdict"] == "BUSTED":
        found_origin = verdict.get("origin_doc") == TRUTH["origin_doc"] or verdict.get("origin_type") == TRUTH["origin_type"]
        return "correct" if found_origin else "partial"
    if verdict["verdict"] == "PLAUSIBLE":
        return "partial"
    return "wrong"


def score(verdict: dict | None, board: Board) -> Score:
    findings = list(board.findings.values())
    supporting, roots = board.support("statistic_true")
    v = verdict or {}
    return Score(
        grade=grade(verdict),
        verdict=v.get("verdict"),
        confidence=v.get("confidence"),
        origin_doc=v.get("origin_doc"),
        origin_type=v.get("origin_type"),
        false_consensus=v.get("verdict") == "CONFIRMED" and (v.get("confidence") or 0) >= 70,
        findings=len(findings),
        supporting=supporting,
        supporting_roots=roots,
        derived=sum(f.derived for f in findings),
        unverified=sum(not f.verified and not f.derived for f in findings),
    )

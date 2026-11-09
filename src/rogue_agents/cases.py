"""The claims a swarm can be asked to check, each with its ground truth.

A case is data: swap in your own claim and corpus to test your own swarm.
The truth is used only for scoring and the origin check; agents never see it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    key: str
    claim: str
    verdict: str  # the correct verdict
    origin_doc: str  # document where the figure really starts
    origin_type: str
    explanation: str
    figures: tuple[str, ...]  # numbers a true origin document must state
    corpus: str = "ai_failure_corpus.json"

    @property
    def truth(self) -> dict:
        return {"verdict": self.verdict, "origin_doc": self.origin_doc, "origin_type": self.origin_type, "explanation": self.explanation}


CASES = {
    c.key: c
    for c in [
        Case(
            "85",
            "85% of AI projects fail.",
            "BUSTED",
            "D01",
            "forecast",
            "2018 Gartner forecast that 85% of AI projects 'will deliver erroneous outcomes', later retold as '85% fail'",
            ("85",),
        ),
        Case(
            "87",
            "87% of data science projects never make it into production.",
            "BUSTED",
            "D02",
            "opinion",
            "An unsourced line in a 2017 opinion column ('a mere 13% ... reach completion'), retold via a panel and a sponsored article",
            ("87", "13"),
        ),
    ]
}

"""The frozen research corpus: real documents, real quotes, links to archives.

Agents see id, title, outlet, date and text. The `role` and `note` fields are
ground truth for scoring and are never shown to agents.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    outlet: str
    date: str
    url: str
    archive: str
    text: str
    role: str
    note: str
    cites: tuple[str, ...] = ()

    def header(self) -> str:
        return f"{self.id} | {self.title} | {self.outlet} | {self.date}"


STOPWORDS = {"the", "of", "a", "and", "is", "in", "to", "for", "what", "how", "does", "do", "that", "are", "this"}


def terms(text: str) -> set[str]:
    """Crude search tokens: '85%' and '85 percent' match, plurals fold to singular."""
    text = re.sub(r"(\d+)\s*(%|percent\b)", r"\1 percent", text.lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", text)}


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


class Corpus:
    def __init__(self, docs: list[Document]):
        self.docs = {d.id: d for d in docs}

    @classmethod
    def load(cls, name: str = "ai_failure_corpus.json") -> "Corpus":
        raw = resources.files("rogue_agents.data").joinpath(name).read_text(encoding="utf-8")
        return cls([Document(**(d | {"cites": tuple(d.get("cites", ()))})) for d in json.loads(raw)])

    def get(self, doc_id: str) -> Document | None:
        return self.docs.get(doc_id.strip().upper())

    def search(self, query: str, k: int = 5) -> list[Document]:
        words = terms(query) - STOPWORDS
        scored = []
        for d in self.docs.values():
            title = terms(d.title)
            body = terms(d.text)
            score = 2 * len(words & title) + len(words & body)
            if score:
                scored.append((score, d.id, d))
        return [d for _, _, d in sorted(scored, key=lambda x: (-x[0], x[1]))[:k]]

    def contains_quote(self, doc_id: str, quote: str) -> bool:
        doc = self.get(doc_id)
        q = normalize(quote).strip(" .\"'")
        return bool(doc and len(q) >= 12 and q in normalize(doc.text))

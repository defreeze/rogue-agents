"""Build the frozen research corpus from archived pages.

Every excerpt is cut from the archived text between two anchors, so each one is
a verbatim substring of a real page. Raw pages live in research/raw (not
committed); the resulting corpus stores short excerpts plus links.

Run from research/tools:  python3 -I build_corpus.py
"""

import json
import re
from pathlib import Path

RAW = Path(__file__).parent.parent / "raw"
OUT = Path(__file__).parent.parent.parent / "src" / "rogue_agents" / "data" / "ai_failure_corpus.json"
WAYBACK = "https://web.archive.org/web/"


def cut(name: str, start: str, end: str) -> str:
    text = (RAW / f"{name}.txt").read_text(encoding="utf-8")
    i = text.find(start)
    if i < 0:
        raise SystemExit(f"{name}: start anchor not found: {start!r}")
    j = text.find(end, i)
    if j < 0:
        raise SystemExit(f"{name}: end anchor not found: {end!r}")
    return re.sub(r"\s+", " ", text[i : j + len(end)]).strip()


# role and note are ground truth for scoring and analysis. Agents never see them.
# cites: corpus documents this one attributes its figures to, read off the text
# itself (named source, footnote or reference list). Used by the citation index.
DOCS = [
    dict(
        id="D01", raw="gartner2018", date="2018-02-13", outlet="Gartner (press release)",
        title="Gartner Says Nearly Half of CIOs Are Planning to Deploy Artificial Intelligence",
        url="https://www.gartner.com/en/newsroom/press-releases/2018-02-13-gartner-says-nearly-half-of-cios-are-planning-to-deploy-artificial-intelligence",
        cuts=[("Conversations with Gartner clients reveal", "teams responsible for managing them.")],
        role="origin", note="Origin of 85%: a forecast that 85% of AI projects 'will deliver erroneous outcomes' through 2022. Not a measured failure rate.",
    ),
    dict(
        id="D02", raw="ciodive2017", date="2017-05-02", outlet="CIO Dive (Opinion, guest article)",
        title="4 reasons why most data science projects fail",
        url="http://www.ciodive.com/news/4-reasons-why-most-data-science-projects-fail/439637/",
        cuts=[
            ("An article from Opinion", "Published May 2, 2017"),
            ("The following is a guest article", "four major pitfalls"),
        ],
        role="origin", note="Root of the 87% chain: unsourced '13% of data and analytics projects reach completion' in an opinion piece.",
    ),
    dict(
        id="D03", raw="venturebeat2019", date="2019-07-19", outlet="VentureBeat (Sponsored, VB Staff)",
        title="Why do 87% of data science projects never make it into production?",
        url="https://venturebeat.com/2019/07/19/why-do-87-of-data-science-projects-never-make-it-into-production/",
        cuts=[("Sponsored Why do 87%", "actually make it into production?")],
        role="relay", note="Sponsored piece; states 13% inside a rhetorical question with no source. Built on a panel remark citing D02.",
    ),
    dict(
        id="D04", raw="fortune2022", date="2022-07-26", outlet="Fortune",
        title="Want your company's A.I. project to succeed? Don't hand it to the data scientists, says this CEO",
        url="https://fortune.com/2022/07/26/a-i-success-business-sense-aible-sengupta/",
        cuts=[("Arijit Sengupta once wrote", "producing financial returns,” Sengupta says.")],
        role="origin", note="'A slew of recent surveys ... between 83% and 92%': no surveys named or linked. Source RAND cites for 80%.",
    ),
    dict(
        id="D05", cites=['D04'], raw="rand2024web", date="2024-08-13", outlet="RAND Corporation (research report)",
        title="The Root Causes of Failure for Artificial Intelligence Projects and How They Can Succeed",
        url="https://www.rand.org/pubs/research_reports/RRA2680-1.html",
        cuts=[("To investigate why artificial intelligence", "remains an urgent challenge.")],
        extra=[("rand2024", "13 Kahn, “Want Your Company’s AI Project to Succeed?”", "Succeed?”", "Footnote 13 (attached to the 80 percent sentence in the PDF)")],
        role="relay", note="RAND's own finding is root causes from 65 interviews. The 80% is quoted 'by some estimates' from D04.",
    ),
    dict(
        id="D06", cites=['D03'], raw="dfa85", date="2019-07-23", outlet="Designing for Analytics (blog, Brian T. O'Neill)",
        title="Failure rates for analytics, AI, and big data projects = 85% – yikes!",
        url="https://designingforanalytics.com/resources/failure-rates-for-analytics-bi-iot-and-big-data-projects-85-yikes/",
        cuts=[
            ("It's disturbing just how bad", "Worse, the numbers"),
            ("July 2019: VentureBeat AI reports", "they meant 85% actually."),
        ],
        role="repeater", note="Round-up that repeats 87% (VentureBeat) and Gartner figures.",
    ),
    dict(
        id="D07", cites=['D03'], raw="devto87", date="2020-09-19", outlet="DEV Community (blog)",
        title="Top 10 Reasons Why 87% of the Machine Learning Projects Fail?",
        url="https://dev.to/prajeen/top-10-reasons-why-87-of-the-machine-learning-projects-fail-5fd",
        cuts=[("According to Gartner’s predictions", "never make it into production .")],
        role="mutation", note="Mutation: panel remark becomes 'VentureBeat predicted 87% of AI projects'.",
    ),
    dict(
        id="D08", cites=['D01'], raw="pavilion", date="2025-06-17", outlet="Pavilion (newsletter editorial)",
        title="Why 85% of AI Projects Are Expensive Failures",
        url="https://www.joinpavilion.com/blog/why-85-of-ai-projects-are-expensive-failures",
        cuts=[("But there's another number we need to talk about.", "Nearly nine out of ten companies are striking out.")],
        role="mutation", note="Mutation: 2018 forecast becomes 'Gartner just revealed 85% of AI initiatives fail to deliver their promised value'.",
    ),
    dict(
        id="D09", cites=['D01'], raw="aitr", date="2025-05-28", outlet="AI Transformation Readiness (blog)",
        title="85% of AI Projects Fail. Don't Let Yours Be One of Them.",
        url="https://www.aitransformationreadiness.org/post/why-ai-projects-fail",
        cuts=[
            ("Yet, according to research from Gartner", "implement it successfully."),
            ("List of References Gartner. (2019, January 21).", "erroneous outcomes through 2022 ."),
        ],
        role="mutation", note="Says '85% of AI projects fail' while its own reference is titled 'will deliver erroneous outcomes'.",
    ),
    dict(
        id="D10", cites=['D02', 'D03'], raw="medium_lie", date="2021-07-09", outlet="Medium (blog)",
        title="Why do 87% of data science projects fail? And are we sure that it is true?",
        url="https://user5724987.medium.com/is-mlops-built-upon-a-lie-8282948b41ae",
        cuts=[("In 2017, A Chief Data Scientist writes", "from a single, opinionated article .")],
        role="critique", note="Traces 87% back through VentureBeat and the panel to D02.",
    ),
    dict(
        id="D11", raw="newmr95", date="2026-05-31", outlet="NewMR (blog, Ray Poynter)",
        title="Myth Number 2: MIT Showed That 95% of AI Pilots Fail",
        url="https://newmr.org/blog/myth-number-2-mit-showed-that-95-of-ai-pilots-fail/",
        cuts=[
            ("Perhaps the most commonly quoted statistics", "using “95% of AI pilots flop”"),
            ("They said the figures were “directionally accurate”", "slower enterprise rollouts."),
        ],
        role="critique", note="About a different figure (95%, MIT NANDA 2025): context and a distractor.",
    ),
]


def build() -> list[dict]:
    corpus = []
    for d in DOCS:
        parts = [cut(d["raw"], s, e) for s, e in d["cuts"]]
        for raw, s, e, label in d.get("extra", []):
            parts.append(f"[{label}] " + cut(raw, s, e))
        corpus.append(
            {
                "id": d["id"],
                "title": d["title"],
                "outlet": d["outlet"],
                "date": d["date"],
                "url": d["url"],
                "archive": f"{WAYBACK}{d['date'][:4]}/{d['url']}",
                "text": "\n\n[...]\n\n".join(parts),
                "cites": d.get("cites", []),
                "role": d["role"],
                "note": d["note"],
            }
        )
    return corpus


if __name__ == "__main__":
    corpus = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for d in corpus:
        print(f"{d['id']} {d['date']} {len(d['text']):5d} chars  {d['title'][:70]}")
    print(f"wrote {OUT}")

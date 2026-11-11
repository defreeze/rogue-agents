"""Three slides on the core finding, to import into the talk deck.

    DECK_THEME=black uv run --with python-pptx python slides/new_slides.py

Numbers come from runs/eval-slide (evaluation of 11 Nov 2026, qwen3:8b, 10 runs per setup).
"""

from __future__ import annotations

from pathlib import Path

from pptx.enum.text import PP_ALIGN

from deckkit import (
    AMBER, CODE_BG, CYAN, EDGE, GREEN, MARGIN, MONO, MUTED, PANEL, PANEL2, RED, TEXT, THEME, W,
    Deck, add_text, badge, box, box_text, header,
)

OUT = Path(__file__).parent / f"core-finding-{THEME}.pptx"
HL = {"bold": True, "color": AMBER}


def gartner_said(d: Deck):
    s = d.slide(
        "Read the sentence out loud, slowly. Then: 'Three things changed on the way to your slides. A prediction became a fact. "
        "Erroneous outcomes became fail. And the reason, bias, disappeared.' Correct verdict: BUSTED.\n"
        "SOURCE: Gartner press release, 13 Feb 2018, 'Gartner Says Nearly Half of CIOs Are Planning to Deploy Artificial Intelligence' "
        "(document D01 in the library; archive link in src/rogue_agents/data/ai_failure_corpus.json)."
    )
    header(s, "The original · Gartner, 13 Feb 2018", "Gartner never said 85% fail")
    badge(s, "verified")
    box_text(s, MARGIN, 2.0, 7.0, 3.3, [
        [("“Gartner ", {}), ("predicts", HL), (" that through 2022, 85 percent of AI projects ", {}),
         ("will deliver erroneous outcomes", HL), (" due to ", {}), ("bias in data, algorithms or the teams", HL),
         (" responsible for managing them.”", {})],
    ], fill=PANEL, line=EDGE, size=22, pad=0.4)
    rows = [("predicts", "A prediction became a fact"),
            ("erroneous outcomes", "“Erroneous outcomes” became “fail”"),
            ("due to bias", "The reason disappeared")]
    for i, (word, change) in enumerate(rows):
        y = 2.0 + i * 1.12
        box(s, 8.0, y, 4.73, 0.98, fill=PANEL2)
        add_text(s, 8.25, y + 0.14, 4.3, 0.35, word.upper(), size=11, bold=True, color=AMBER)
        add_text(s, 8.25, y + 0.47, 4.3, 0.45, change, size=17, bold=True)
    box_text(s, MARGIN, 5.75, W - 2 * MARGIN, 0.8, [[("What we repeat: ", {"color": MUTED}), ("“85% of AI projects fail.”", {"bold": True}),
             ("   Verdict: ", {"color": MUTED}), ("BUSTED", {"bold": True, "color": RED})]],
             fill=PANEL2, size=20, align=PP_ALIGN.CENTER)


def read_it_anyway(d: Deck):
    s = d.slide(
        "THE KEY MOMENT. 'My agent found this exact document. It read this exact sentence. It even wrote down that it was a forecast. "
        "And it still said: confirmed, 90 percent sure.'\n"
        "FACTS (runs/eval-slide, single agent, calm, 10 runs): opened D01 in 8 of 10 runs; CONFIRMED in 9 of 10; in 5 of 10 it labelled "
        "D01 a 'forecast' and still answered CONFIRMED. The verdict shown is run 9, verbatim.\n"
        "Point to make: the problem was not finding the evidence. It was reading it. The same mistake people made when they spread the number."
    )
    header(s, "The finding · single agent, calm", "It read the source. It still said CONFIRMED.")
    badge(s, "eval")
    box(s, MARGIN, 2.0, 5.6, 2.95, fill=PANEL, line=EDGE)
    add_text(s, MARGIN + 0.3, 2.18, 5.0, 0.35, "WHAT IT READ · D01, GARTNER 2018", size=11, bold=True, color=MUTED)
    add_text(s, MARGIN + 0.3, 2.6, 5.0, 2.2, [[("“…85 percent of AI projects ", {}), ("will deliver erroneous outcomes", HL),
             (" due to bias in data, algorithms or the teams…”", {})]], size=18, italic=True)
    add_text(s, 6.3, 3.05, 0.6, 0.8, "→", size=40, bold=True, color=MUTED, align=PP_ALIGN.CENTER)
    box(s, 7.0, 2.0, 5.73, 2.95, fill=CODE_BG, line=RED, line_w=1.5)
    add_text(s, 7.3, 2.18, 5.2, 0.35, "WHAT IT CONCLUDED · RUN 9, VERBATIM", size=11, bold=True, color=MUTED)
    add_text(s, 7.3, 2.6, 5.2, 2.3, [
        [("verdict:     ", {"color": MUTED}), ("CONFIRMED", {"bold": True, "color": RED})],
        [("confidence:  ", {"color": MUTED}), ("90", {"bold": True})],
        [("origin:      ", {"color": MUTED}), ("D01", {})],
        [("origin type: ", {"color": MUTED}), ("forecast", {"bold": True, "color": AMBER})],
        [("“…Gartner, report that 85% of AI projects fail…”", {"color": MUTED})],
    ], size=15, font=MONO, space_after=6)
    stats = [("8 / 10", "runs opened the Gartner original"),
             ("9 / 10", "runs said CONFIRMED anyway"),
             ("5 / 10", "even called it a forecast, and confirmed")]
    for i, (n, label) in enumerate(stats):
        x = MARGIN + i * 4.1
        add_text(s, x, 5.2, 1.6, 0.6, n, size=28, bold=True, color=RED if i else TEXT)
        add_text(s, x + 1.65, 5.28, 2.3, 0.6, label, size=13, color=MUTED)
    box_text(s, MARGIN, 6.0, W - 2 * MARGIN, 0.65, [[("The problem wasn't finding the evidence. ", {"bold": True, "color": CYAN}),
             ("It was reading it.", {"bold": True})]], fill=PANEL2, size=19, align=PP_ALIGN.CENTER)


def behaviour_not_belief(d: Deck):
    s = d.slide(
        "'So I added rules. Quote the source exactly, read the original before you name it, stay within budget. And the rules worked: "
        "every run opened the original, almost none ran away, a third of the tokens. But the answer? Still wrong about half the time.'\n"
        "Analogy: 'Like requiring every report to attach its source. Everyone attaches it. They still misread it.'\n"
        "FACTS (runs/eval-slide, 10 runs each, medians): opened origin, open vs contained swarm, calm: 2/10 -> 10/10. Never reached a verdict, "
        "pressure: 9/10 -> 2/10. Tokens, pressure: 149k -> 56k. Still CONFIRMED with controls: 5/10 calm, 6/10 pressure. "
        "Accuracy differences between open and contained are within the noise at N=10: don't claim the controls made it worse. "
        "The contained-calm setup was added after the first results."
    )
    header(s, "What the controls bought", "Controls fixed the behaviour. Not the belief.")
    badge(s, "eval")
    box(s, MARGIN, 1.95, 7.3, 3.75, fill=PANEL, line=GREEN, line_w=1.5)
    add_text(s, MARGIN + 0.35, 2.12, 6.6, 0.45, "The behaviour: fixed", size=20, bold=True, color=GREEN)
    cards = [("2 → 10", "of 10 runs opened the original", "calm"),
             ("9 → 2", "of 10 runs never reached an answer", "under pressure"),
             ("149k → 56k", "tokens per run", "under pressure")]
    for i, (n, label, cond) in enumerate(cards):
        y = 2.75 + i * 0.95
        add_text(s, MARGIN + 0.35, y, 2.6, 0.6, n, size=26, bold=True)
        add_text(s, MARGIN + 3.0, y + 0.05, 4.1, 0.35, label, size=15)
        add_text(s, MARGIN + 3.0, y + 0.4, 4.1, 0.3, cond, size=12, color=MUTED)
    box(s, 8.15, 1.95, 4.58, 3.75, fill=PANEL, line=RED, line_w=1.5)
    add_text(s, 8.5, 2.12, 4.0, 0.45, "The belief: unchanged", size=20, bold=True, color=RED)
    add_text(s, 8.5, 2.75, 4.0, 2.8, [
        [("5 / 10", {"bold": True, "size": 26, "color": TEXT})],
        [("still CONFIRMED, calm", {})],
        [("6 / 10", {"bold": True, "size": 26, "color": TEXT})],
        [("still CONFIRMED, under pressure", {})],
    ], size=15, color=MUTED, space_after=4)
    box_text(s, MARGIN, 5.95, W - 2 * MARGIN, 0.7, [[("Like making every report attach its source. ", {"color": MUTED}),
             ("Everyone attaches it. They still misread it.", {"bold": True})]], fill=PANEL2, size=18, align=PP_ALIGN.CENTER)
    add_text(s, MARGIN, 6.78, W - 2 * MARGIN, 0.3, "Open vs contained swarm · qwen3:8b · 10 runs per setup · tokens are medians",
             size=11, color=MUTED)


def build():
    d = Deck()
    gartner_said(d)
    read_it_anyway(d)
    behaviour_not_belief(d)
    d.save(OUT)
    print(f"wrote {OUT} ({d.n} slides)")


if __name__ == "__main__":
    build()

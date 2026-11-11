"""Closing slides: takeaways (five and three) and the closing quote.

    DECK_THEME=black uv run --with python-pptx python slides/closing_slides.py
"""

from __future__ import annotations

from pathlib import Path

from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from deckkit import (
    AMBER, CYAN, EDGE, GREEN, H, MARGIN, MUTED, PANEL, PANEL2, PURPLE, RED, TEXT, THEME, W,
    Deck, add_text, box, connector, header, node,
)

OUT = Path(__file__).parent / f"closing-{THEME}.pptx"

TAKEAWAYS = [
    ("Agents don't need an attacker to cause damage",
     "Rogue behaviour comes from the goal, the reward and the pressure, not from malice.",
     "Ask what it's rewarded for.", RED),
    ("Put controls in code, not in the prompt",
     "“Please be careful” is a wish. Permissions, budgets and checks are guarantees.",
     "If code can check it, don't ask a model.", AMBER),
    ("Check the world, not the report",
     "My agents read the source, called it a forecast, and still confirmed the myth.",
     "Verifying a source is not verifying a claim.", CYAN),
    ("Start with the least interaction that does the job",
     "A swarm earns its cost only when the work can't be planned up front.",
     "One agent, a pipeline, then a swarm.", PURPLE),
    ("Be as sceptical as you want your agents to be",
     "“85% of AI projects fail” was a 2018 forecast. Most of us repeated it.",
     "Their weakness is ours.", GREEN),
]

NOTES_FIVE = (
    "TAKEAWAYS (all five). One sentence each, don't re-explain. "
    "1 links to the Hugging Face case. 2 links to the gate. 3 is the core finding. 4 links to 'when to use what'. "
    "5 turns it back to the room: the myth we all repeated."
)
NOTES_THREE = (
    "TAKEAWAYS (three). The arc of the talk: the opening (agents act without attackers), the finding (they read the source and still "
    "believed the myth), and the room (so did we). Mention 'controls in code' and 'least interaction' during the talk instead."
)


def takeaways_five(d: Deck):
    s = d.slide(NOTES_FIVE)
    header(s, "Takeaways", "What to take home")
    for i, (title, line, rule, col) in enumerate(TAKEAWAYS):
        y = 1.85 + i * 1.0
        box(s, MARGIN, y, W - 2 * MARGIN, 0.86, fill=PANEL)
        box(s, MARGIN, y, 0.09, 0.86, fill=col, radius=0)
        add_text(s, MARGIN + 0.3, y, 0.6, 0.86, str(i + 1), size=28, bold=True, color=col, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, MARGIN + 0.95, y + 0.1, 6.6, 0.4, title, size=18, bold=True)
        add_text(s, MARGIN + 0.95, y + 0.47, 6.6, 0.35, line, size=12, color=MUTED)
        add_text(s, 8.0, y, 4.5, 0.86, rule, size=14, italic=True, color=col, anchor=MSO_ANCHOR.MIDDLE)


def takeaways_three(d: Deck):
    s = d.slide(NOTES_THREE)
    header(s, "Takeaways", "What to take home")
    picks = [TAKEAWAYS[0], TAKEAWAYS[2], TAKEAWAYS[4]]
    gap = 0.3
    cw = (W - 2 * MARGIN - 2 * gap) / 3
    for i, (title, line, rule, col) in enumerate(picks):
        x = MARGIN + i * (cw + gap)
        box(s, x, 1.95, cw, 4.6, fill=PANEL, line=col, line_w=1.5)
        add_text(s, x + 0.35, 2.15, 1.0, 0.9, str(i + 1), size=48, bold=True, color=col)
        add_text(s, x + 0.35, 3.15, cw - 0.7, 1.2, title, size=22, bold=True)
        add_text(s, x + 0.35, 4.4, cw - 0.7, 1.1, line, size=14, color=MUTED)
        box(s, x + 0.35, 5.55, cw - 0.7, 0.02, fill=EDGE, radius=0)
        add_text(s, x + 0.35, 5.7, cw - 0.7, 0.7, rule, size=14, italic=True, color=col)


def closing_quote(d: Deck):
    s = d.slide(
        "CLOSING. Pause before you say it. Say it slowly, then stop talking and move to questions.\n"
        "Full spoken version: '85% of AI projects fail. You've probably seen it on a slide. My agents read the original and believed it "
        "anyway. Just like we did. Agents can now act faster than we can, and believe faster than we can. Don't build agents you hope "
        "will be right. Build systems that check, starting with yourself.'"
    )
    # faint swarm motif, right side
    pts = [(10.2, 0.7), (11.6, 0.5), (12.5, 1.4), (11.2, 1.8), (12.3, 2.6), (10.5, 2.8), (9.5, 1.6)]
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:i + 3]:
            connector(s, x1, y1, x2, y2, color=PANEL2, width=1.5, arrow=False)
    for x, y in pts:
        node(s, x, y, 0.2, fill=PANEL, line=EDGE, line_w=1.5)
    add_text(s, MARGIN + 0.2, 1.7, 9.5, 1.4, "Agents can now act faster than we can,\nand believe faster than we can.",
             size=26, color=MUTED, space_after=4)
    add_text(s, MARGIN + 0.2, 3.35, 11.0, 0.8, "Don't build agents you hope will be right.", size=36, bold=True)
    add_text(s, MARGIN + 0.2, 4.15, 11.0, 0.8, [[("Build systems that check", {"color": CYAN}), (",", {})]], size=36, bold=True)
    add_text(s, MARGIN + 0.2, 4.95, 11.0, 0.8, "starting with yourself.", size=36, bold=True, color=AMBER)
    add_text(s, MARGIN + 0.2, H - 0.95, 8, 0.4, "Alex de Vries · Rogue Agents · aiGrunn 2026", size=13, color=MUTED)


def build():
    d = Deck()
    takeaways_five(d)
    takeaways_three(d)
    closing_quote(d)
    d.save(OUT)
    print(f"wrote {OUT} ({d.n} slides)")


if __name__ == "__main__":
    build()

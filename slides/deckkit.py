"""Drawing helpers and visual style shared by the deck generators."""

from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# ------------------------------------------------------------------ style

BG = "0A0F1E"
PANEL = "121A30"
PANEL2 = "1A2442"
EDGE = "2A3760"
TEXT = "E8EEF9"
MUTED = "8C9AB8"
CYAN = "22D3EE"
PURPLE = "A78BFA"
RED = "F87171"
GREEN = "34D399"
AMBER = "FBBF24"

FONT = "Arial"
MONO = "Courier New"
W, H = 13.333, 7.5
MARGIN = 0.6

BADGES = {
    "verified": ("VERIFIED SOURCES", GREEN),
    "pilot": ("REAL DATA · PILOT RUN, n=1", CYAN),
    "prompt": ("REAL OUTPUT · SINGLE PROMPT", CYAN),
    "illustrative": ("ILLUSTRATIVE", AMBER),
    "hypothetical": ("HYPOTHETICAL · NOT BUILT", AMBER),
    "placeholder": ("PLACEHOLDER · TO BE MEASURED", PURPLE),
    "opinion": ("OPINION · TO BE BACKED BY RESULTS", PURPLE),
    "trace": ("REAL DATA · FROM A RECORDED RUN", CYAN),
}


def rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


# ---------------------------------------------------------------- helpers


def add_text(slide, x, y, w, h, paras, size=16, color=TEXT, bold=False, align=PP_ALIGN.LEFT,
             font=FONT, anchor=MSO_ANCHOR.TOP, space_after=0, italic=False, name=None):
    """paras: a string, or a list of paragraphs; a paragraph is a string or a list of (text, opts) runs."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if space_after:
            p.space_after = Pt(space_after)
        runs = [(para, {})] if isinstance(para, str) else para
        for text, opts in runs:
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = opts.get("font", font)
            f.size = Pt(opts.get("size", size))
            f.bold = opts.get("bold", bold)
            f.italic = opts.get("italic", italic)
            f.color.rgb = rgb(opts.get("color", color))
    return tb


def _no_shadow(shape):
    shape.shadow.inherit = False


def box(slide, x, y, w, h, fill=PANEL, line=None, radius=0.08, shape=MSO_SHAPE.ROUNDED_RECTANGLE, line_w=1.25):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_w)
    else:
        s.line.fill.background()
    _no_shadow(s)
    return s


def box_text(slide, x, y, w, h, paras, fill=PANEL, line=None, size=14, color=TEXT, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, pad=0.15, radius=0.08, font=FONT, space_after=0):
    s = box(slide, x, y, w, h, fill=fill, line=line, radius=radius)
    tf = s.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(pad)
    tf.margin_top = tf.margin_bottom = Inches(pad * 0.6)
    tf.vertical_anchor = anchor
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if space_after:
            p.space_after = Pt(space_after)
        runs = [(para, {})] if isinstance(para, str) else para
        for text, opts in runs:
            r = p.add_run()
            r.text = text
            f = r.font
            f.name = opts.get("font", font)
            f.size = Pt(opts.get("size", size))
            f.bold = opts.get("bold", bold)
            f.italic = opts.get("italic", False)
            f.color.rgb = rgb(opts.get("color", color))
    return s


def node(slide, cx, cy, r, fill=PANEL2, line=CYAN, label=None, size=12, color=TEXT, line_w=2):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - r), Inches(cy - r), Inches(2 * r), Inches(2 * r))
    s.fill.solid()
    s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(line_w)
    else:
        s.line.fill.background()
    _no_shadow(s)
    if label:
        tf = s.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = label
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.name = FONT
        run.font.color.rgb = rgb(color)
    return s


def connector(slide, x1, y1, x2, y2, color=EDGE, width=1.75, arrow=True, dash=False):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    if dash:
        d = ln.makeelement(qn("a:prstDash"), {"val": "dash"})
        ln.append(d)
    if arrow:
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def style_table(table, color=EDGE):
    """Thin, dark cell borders instead of the default white grid."""
    for row in table.rows:
        for cell in row.cells:
            tcPr = cell._tc.get_or_add_tcPr()
            # Schema order: borders come before the cell fill.
            for i, tag in enumerate(("a:lnL", "a:lnR", "a:lnT", "a:lnB")):
                ln = tcPr.makeelement(qn(tag), {"w": str(Pt(0.75)), "cmpd": "sng"})
                fill = ln.makeelement(qn("a:solidFill"), {})
                fill.append(fill.makeelement(qn("a:srgbClr"), {"val": color}))
                ln.append(fill)
                tcPr.insert(i, ln)


def pill(slide, x, y, w, h, text, color, size=12, filled=False):
    return box_text(slide, x, y, w, h, [[(text, {"bold": True, "color": BG if filled else color})]],
                    fill=color if filled else BG, line=color, size=size, align=PP_ALIGN.CENTER, pad=0.08, radius=0.5)


def badge(slide, kind):
    text, color = BADGES[kind]
    w = 0.13 * len(text) * 0.62 + 0.5
    pill(slide, W - MARGIN - w, 0.42, w, 0.34, text, color, size=10)


def header(slide, kicker, title):
    add_text(slide, MARGIN, 0.42, 8.6, 0.32, kicker.upper(), size=12, color=CYAN, bold=True)
    add_text(slide, MARGIN, 0.78, W - 2 * MARGIN, 0.9, title, size=34, bold=True, name="Title")


def footer(slide, n):
    add_text(slide, MARGIN, H - 0.42, 6, 0.25, "Rogue Agents · aiGrunn 2026", size=10, color=MUTED)
    add_text(slide, W - MARGIN - 1, H - 0.42, 1, 0.25, str(n), size=10, color=MUTED, align=PP_ALIGN.RIGHT)


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width = Inches(W)
        self.prs.slide_height = Inches(H)
        self.n = 0

    def slide(self, notes: str = ""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = rgb(BG)
        self.n += 1
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def save(self, path):
        self.prs.save(path)


def divider(deck: Deck, number: str, title: str, subtitle: str, notes: str):
    s = deck.slide(notes)
    # faint swarm motif on the right
    pts = [(10.2, 2.0), (11.6, 1.5), (12.3, 3.0), (10.9, 3.6), (11.8, 4.9), (10.0, 5.2), (9.3, 3.7)]
    for i, (x1, y1) in enumerate(pts):
        for x2, y2 in pts[i + 1:i + 3]:
            connector(s, x1, y1, x2, y2, color=PANEL2, width=1.5, arrow=False)
    for x, y in pts:
        node(s, x, y, 0.22, fill=PANEL, line=EDGE, line_w=1.5)
    add_text(s, MARGIN + 0.1, 2.2, 3, 1.2, number, size=80, bold=True, color=CYAN)
    add_text(s, MARGIN + 0.1, 3.55, 8.2, 1.0, title, size=44, bold=True)
    add_text(s, MARGIN + 0.1, 4.55, 7.8, 1.0, subtitle, size=20, color=MUTED)
    footer(s, deck.n)
    return s


def flow_arrow_label(slide, x, y, w, text, color=AMBER):
    add_text(slide, x, y, w, 0.3, text, size=11, color=color, italic=True, align=PP_ALIGN.CENTER)



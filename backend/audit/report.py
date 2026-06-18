"""
Render an AuditResult into a downloadable report.

Three formats:
  - Markdown (.md)  — for pasting into docs / Notion / GitHub
  - Plain text (.txt) — for emails / clipboard
  - PDF (.pdf) — for client deliverables (reportlab, pure-Python)
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)

from .models import AuditResult, ScoreCheck


_AREA_LABEL = {
    "url":               "URL",
    "meta_title":        "Meta title",
    "meta_description":  "Meta description",
    "h1":                "H1",
    "h2":                "H2 sub-headings",
    "content":           "Content",
    "internal_linking":  "Internal linking",
    "schema":            "Schema",
    "images":            "Images",
    "faq":               "FAQ",
}


def _fmt_dt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso or ""


def _section_lines(title: str, items: List[ScoreCheck]) -> List[str]:
    out = [title, "-" * len(title)]
    if not items:
        out.append("None.")
        return out
    for c in items:
        out.append(f"[{c.priority.upper():6}] {c.label}  ({_AREA_LABEL.get(c.area, c.area)})")
        if c.detail:
            out.append(f"           {c.detail}")
    return out


def _section_md(title: str, items: List[ScoreCheck]) -> List[str]:
    out = [f"### {title}", ""]
    if not items:
        out += ["_None._", ""]
        return out
    for c in items:
        out.append(f"- **[{c.priority.upper()}]** {c.label} — _{_AREA_LABEL.get(c.area, c.area)}_")
        if c.detail:
            out.append(f"    - {c.detail}")
    out.append("")
    return out


# ---------------- Markdown ----------------

def render_markdown(a: AuditResult) -> str:
    snap = a.page_snapshot or {}
    lines: List[str] = []
    lines.append("# TSE Page Auditor Report")
    lines.append("")
    lines.append(f"**URL:** {a.final_url or a.url}")
    lines.append(f"**Primary phrase:** {a.primary_phrase}")
    if a.secondary_phrases:
        lines.append(f"**Secondary phrases:** {', '.join(a.secondary_phrases)}")
    lines.append(f"**Overall score:** {a.overall_score} / 100")
    lines.append(f"**Audited:** {_fmt_dt(a.created_at)}")
    lines.append("")
    lines.append("## Area scores")
    lines.append("")
    lines.append("| Area | Score |")
    lines.append("| --- | ---: |")
    for k, label in _AREA_LABEL.items():
        lines.append(f"| {label} | {a.area_scores.get(k, 0)} |")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines += _section_md("Strengths", a.strengths)
    lines += _section_md("Weaknesses", a.weaknesses)
    lines += _section_md("Recommendations", a.recommendations)
    lines.append("## Page basics")
    lines.append("")
    lines.append(f"- **Meta title:** {snap.get('title') or '—'}")
    lines.append(f"- **Meta description:** {snap.get('meta_description') or '—'}")
    lines.append(f"- **Canonical:** {snap.get('canonical') or '—'}")
    lines.append(f"- **H1:** {' · '.join(snap.get('h1') or []) or '—'}")
    lines.append(f"- **H2s:** {' · '.join(snap.get('h2') or []) or '—'}")
    lines.append(f"- **Word count:** {snap.get('word_count', 0)}")
    lines.append(f"- **Internal links:** {snap.get('internal_link_count', 0)}")
    lines.append(f"- **External links:** {snap.get('external_link_count', 0)}")
    img_cov = round((snap.get('image_alt_coverage') or 0) * 100)
    lines.append(f"- **Images:** {snap.get('image_count', 0)} (alt coverage {img_cov}%)")
    lines.append(f"- **Schema types:** {', '.join(snap.get('schema_types') or []) or '—'}")
    lines.append(f"- **FAQ items:** {snap.get('faq_count', 0)}")
    lines.append("")
    return "\n".join(lines)


# ---------------- Plain text ----------------

def render_text(a: AuditResult) -> str:
    snap = a.page_snapshot or {}
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("TSE PAGE AUDITOR REPORT".center(72))
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"URL              : {a.final_url or a.url}")
    lines.append(f"Primary phrase   : {a.primary_phrase}")
    if a.secondary_phrases:
        lines.append(f"Secondary phrases: {', '.join(a.secondary_phrases)}")
    lines.append(f"Overall score    : {a.overall_score} / 100")
    lines.append(f"Audited          : {_fmt_dt(a.created_at)}")
    lines.append("")
    lines.append("AREA SCORES")
    lines.append("-" * 72)
    for k, label in _AREA_LABEL.items():
        lines.append(f"  {label:<22} {a.area_scores.get(k, 0):>3} / 100")
    lines.append("")
    lines += _section_lines("STRENGTHS", a.strengths)
    lines.append("")
    lines += _section_lines("WEAKNESSES", a.weaknesses)
    lines.append("")
    lines += _section_lines("RECOMMENDATIONS", a.recommendations)
    lines.append("")
    lines.append("PAGE BASICS")
    lines.append("-" * 72)
    lines.append(f"  Meta title       : {snap.get('title') or '-'}")
    lines.append(f"  Meta description : {snap.get('meta_description') or '-'}")
    lines.append(f"  Canonical        : {snap.get('canonical') or '-'}")
    lines.append(f"  H1               : {' / '.join(snap.get('h1') or []) or '-'}")
    lines.append(f"  H2s              : {' / '.join(snap.get('h2') or []) or '-'}")
    lines.append(f"  Word count       : {snap.get('word_count', 0)}")
    lines.append(f"  Internal links   : {snap.get('internal_link_count', 0)}")
    lines.append(f"  External links   : {snap.get('external_link_count', 0)}")
    img_cov = round((snap.get('image_alt_coverage') or 0) * 100)
    lines.append(f"  Images           : {snap.get('image_count', 0)} (alt coverage {img_cov}%)")
    lines.append(f"  Schema types     : {', '.join(snap.get('schema_types') or []) or '-'}")
    lines.append(f"  FAQ items        : {snap.get('faq_count', 0)}")
    lines.append("")
    return "\n".join(lines)


# ---------------- PDF ----------------

_PRIO_COLOR = {
    "high":   colors.HexColor("#dc2626"),
    "medium": colors.HexColor("#d97706"),
    "low":    colors.HexColor("#64748b"),
}


def render_pdf(a: AuditResult) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="TSE Page Auditor Report",
    )
    styles = getSampleStyleSheet()
    h_brand = ParagraphStyle("brand", parent=styles["Normal"],
                             fontSize=9, textColor=colors.HexColor("#64748b"),
                             spaceAfter=4, leading=11)
    h_title = ParagraphStyle("title", parent=styles["Heading1"],
                             fontSize=20, leading=24, spaceAfter=10,
                             textColor=colors.HexColor("#0f172a"))
    h_sub = ParagraphStyle("sub", parent=styles["Normal"],
                           fontSize=10, leading=14, spaceAfter=2,
                           textColor=colors.HexColor("#1e293b"))
    h_sec = ParagraphStyle("sec", parent=styles["Heading2"],
                           fontSize=13, leading=17, spaceBefore=14,
                           spaceAfter=8, textColor=colors.HexColor("#0f172a"))
    h_check = ParagraphStyle("check", parent=styles["Normal"],
                             fontSize=9.5, leading=13, spaceAfter=2,
                             textColor=colors.HexColor("#0f172a"))
    h_detail = ParagraphStyle("detail", parent=styles["Normal"],
                              fontSize=8.5, leading=12, spaceAfter=6,
                              leftIndent=14,
                              textColor=colors.HexColor("#475569"))

    score_color = (
        colors.HexColor("#16a34a") if a.overall_score >= 75
        else colors.HexColor("#d97706") if a.overall_score >= 50
        else colors.HexColor("#dc2626")
    )
    h_score = ParagraphStyle("score", parent=styles["Normal"],
                             fontSize=36, leading=40, textColor=score_color,
                             alignment=2, spaceAfter=4)  # right-aligned

    story = []
    story.append(Paragraph("TSE PAGE AUDITOR", h_brand))
    story.append(Paragraph("Page audit report", h_title))

    # Header table: URL/phrase block on the left, score on the right.
    head_left = [
        Paragraph(f"<b>URL:</b> {a.final_url or a.url}", h_sub),
        Paragraph(f"<b>Primary phrase:</b> {a.primary_phrase}", h_sub),
    ]
    if a.secondary_phrases:
        head_left.append(Paragraph(
            f"<b>Secondary phrases:</b> {', '.join(a.secondary_phrases)}", h_sub))
    head_left.append(Paragraph(f"<b>Audited:</b> {_fmt_dt(a.created_at)}", h_sub))
    head_left.append(Paragraph(
        f"<b>Fetch:</b> HTTP {a.fetch_status} via {a.render_method} in {a.fetch_ms}ms",
        h_sub))
    head_right = [Paragraph(f"<b>{a.overall_score}</b>", h_score),
                  Paragraph("/ 100 overall score", h_brand)]
    head_tbl = Table([[head_left, head_right]], colWidths=[120 * mm, 50 * mm])
    head_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(head_tbl)
    story.append(Spacer(1, 8))

    # Area scores table.
    story.append(Paragraph("Area scores", h_sec))
    rows = [["Area", "Score"]]
    for k, label in _AREA_LABEL.items():
        rows.append([label, str(a.area_scores.get(k, 0))])
    tbl = Table(rows, colWidths=[110 * mm, 30 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.whitesmoke, colors.HexColor("#f1f5f9")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
    ]))
    story.append(tbl)

    def _check_section(label: str, items: List[ScoreCheck]) -> None:
        story.append(Paragraph(label, h_sec))
        if not items:
            story.append(Paragraph("<i>None.</i>", h_detail))
            return
        for c in items:
            colour = _PRIO_COLOR.get(c.priority, colors.black).hexval()[2:]
            story.append(Paragraph(
                f"<font color='#{colour}'><b>[{c.priority.upper()}]</b></font> "
                f"<b>{c.label}</b> — <i>{_AREA_LABEL.get(c.area, c.area)}</i>",
                h_check,
            ))
            if c.detail:
                story.append(Paragraph(c.detail, h_detail))

    _check_section("Strengths", a.strengths)
    _check_section("Weaknesses", a.weaknesses)
    _check_section("Recommendations", a.recommendations)

    # Page basics
    snap = a.page_snapshot or {}
    story.append(PageBreak())
    story.append(Paragraph("Page basics", h_sec))
    img_cov = round((snap.get("image_alt_coverage") or 0) * 100)
    basics = [
        ("Meta title", snap.get("title") or "—"),
        ("Meta description", snap.get("meta_description") or "—"),
        ("Canonical", snap.get("canonical") or "—"),
        ("H1", " · ".join(snap.get("h1") or []) or "—"),
        ("H2s", " · ".join(snap.get("h2") or []) or "—"),
        ("Word count", str(snap.get("word_count", 0))),
        ("Internal links", str(snap.get("internal_link_count", 0))),
        ("External links", str(snap.get("external_link_count", 0))),
        ("Images", f"{snap.get('image_count', 0)} (alt coverage {img_cov}%)"),
        ("Schema types", ", ".join(snap.get("schema_types") or []) or "—"),
        ("FAQ items", str(snap.get("faq_count", 0))),
    ]
    basics_rows = [[Paragraph(f"<b>{k}</b>", h_check), Paragraph(str(v), h_check)]
                   for k, v in basics]
    basics_tbl = Table(basics_rows, colWidths=[45 * mm, 125 * mm])
    basics_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#e2e8f0")),
    ]))
    story.append(basics_tbl)

    doc.build(story)
    return buf.getvalue()

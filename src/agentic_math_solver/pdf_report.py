from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


@dataclass(slots=True)
class SolvedProblem:
    index: int
    statement: str
    final_answer: str
    educational_summary: str
    used_judge: bool = False
    vote_counts: dict[str, int] = field(default_factory=dict)
    agent_summaries: list[tuple[str, str, str | None]] = field(default_factory=list)  # (agent, persona, answer)


def _inline_markup(text: str) -> str:
    """Escapes XML and translates a small subset of Markdown into reportlab's mini-markup."""
    text = escape(text)
    # bold **text** / __text__
    import re

    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    # inline code `text`
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    # italics *text*
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _markdown_to_flowables(text: str, styles: dict) -> list:
    flowables: list = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 0.15 * cm))
            continue
        if line.startswith("### "):
            flowables.append(Paragraph(_inline_markup(line[4:]), styles["H3"]))
        elif line.startswith("## "):
            flowables.append(Paragraph(_inline_markup(line[3:]), styles["H2"]))
        elif line.startswith("# "):
            flowables.append(Paragraph(_inline_markup(line[2:]), styles["H1"]))
        elif line.startswith(("- ", "* ")):
            flowables.append(Paragraph("• " + _inline_markup(line[2:]), styles["Bullet"]))
        elif line.startswith("```"):
            continue  # skip code fences, keep inner lines as plain text
        else:
            flowables.append(Paragraph(_inline_markup(line), styles["Body"]))
    return flowables


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "Title": ParagraphStyle("ReportTitle", parent=base["Title"], fontSize=22, textColor=colors.HexColor("#0f4c3a")),
        "Subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontSize=11, textColor=colors.HexColor("#555555")),
        "H1": ParagraphStyle("H1", parent=base["Heading1"], fontSize=15, spaceBefore=6, spaceAfter=4, textColor=colors.HexColor("#10a37f")),
        "H2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=13, spaceBefore=6, spaceAfter=4, textColor=colors.HexColor("#10a37f")),
        "H3": ParagraphStyle("H3", parent=base["Heading3"], fontSize=11.5, spaceBefore=4, spaceAfter=3),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=10.5, leading=15),
        "Bullet": ParagraphStyle("Bullet", parent=base["BodyText"], fontSize=10.5, leading=15, leftIndent=12),
        "Statement": ParagraphStyle("Statement", parent=base["BodyText"], fontSize=11, leading=16, backColor=colors.HexColor("#f2f7f5"), borderPadding=8),
        "Answer": ParagraphStyle("Answer", parent=base["BodyText"], fontSize=13, textColor=colors.white, alignment=1),
        "AgentLabel": ParagraphStyle("AgentLabel", parent=base["BodyText"], fontSize=9.5, textColor=colors.HexColor("#444444")),
    }


def build_solved_list_pdf(
    title: str,
    problems: list[SolvedProblem],
    output_path: Path,
    *,
    model_name: str = "",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=title,
    )

    story: list = []
    story.append(Paragraph(escape(title), styles["Title"]))
    subtitle = f"Gerado por Agentic Math Solver em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    if model_name:
        subtitle += f" &middot; modelo: {escape(model_name)}"
    story.append(Paragraph(subtitle, styles["Subtitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#10a37f"), thickness=1.2))
    story.append(Spacer(1, 0.6 * cm))

    for problem in problems:
        story.append(Paragraph(f"Questão {problem.index}", styles["H1"]))
        story.append(Paragraph(_inline_markup(problem.statement), styles["Statement"]))
        story.append(Spacer(1, 0.3 * cm))

        if problem.agent_summaries:
            rows = [["Agente", "Persona", "Resposta"]]
            for agent_name, persona, answer in problem.agent_summaries:
                rows.append([agent_name, persona, answer or "—"])
            table = Table(rows, colWidths=[3.5 * cm, 4 * cm, 6.5 * cm])
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#10a37f")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(table)
            story.append(Spacer(1, 0.3 * cm))

        answer_table = Table(
            [[Paragraph(f"Resposta Final: {escape(problem.final_answer or 'N/A')}", styles["Answer"])]],
            colWidths=[14 * cm],
        )
        answer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#10a37f")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
                ]
            )
        )
        story.append(answer_table)
        story.append(Spacer(1, 0.3 * cm))

        if problem.used_judge:
            votes = ", ".join(f"{ans}: {count}" for ans, count in problem.vote_counts.items())
            story.append(Paragraph(f"<i>Consenso não unânime (votos: {escape(votes)}) — decisão de um agente Juiz.</i>", styles["Body"]))
            story.append(Spacer(1, 0.2 * cm))

        story.append(Paragraph("Solução passo a passo", styles["H2"]))
        story.extend(_markdown_to_flowables(problem.educational_summary, styles))

        if problem.index != problems[-1].index:
            story.append(PageBreak())

    doc.build(story)
    return output_path

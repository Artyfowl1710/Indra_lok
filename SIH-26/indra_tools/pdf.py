#!/usr/bin/env python3
"""INDRA PDF Generator: Context-Agnostic, 100% Offline Platypus Engine.

Supports:
1. Markdown or plain-text briefs (.md, .txt) with automatic flowable translation
   (Headers, wrapped paragraphs, bullet lists, markdown tables, callout blocks).
2. JSON specification (.json) with explicit structured elements:
   heading, paragraph, table (with cell wrapping), image, hr, pagebreak.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

def _get_styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle(
            "DocTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        ),
        "Subtitle": ParagraphStyle(
            "DocSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        ),
        "Heading1": ParagraphStyle(
            "Heading1",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=12,
            spaceAfter=4,
        ),
        "Heading2": ParagraphStyle(
            "Heading2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0284c7"),
            spaceBefore=10,
            spaceAfter=3,
        ),
        "Heading3": ParagraphStyle(
            "Heading3",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=14,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=8,
            spaceAfter=2,
        ),
        "Body": ParagraphStyle(
            "DocBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1e293b"),
            spaceAfter=5,
        ),
        "Bullet": ParagraphStyle(
            "DocBullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=colors.HexColor("#1e293b"),
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=3,
        ),
        "TableCell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1e293b"),
        ),
        "TableHeader": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0f172a"),
        ),
        "Callout": ParagraphStyle(
            "DocCallout",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155"),
            leftIndent=12,
            spaceBefore=4,
            spaceAfter=6,
        ),
    }
    return styles

def parse_markdown_to_story(md_content: str, styles: dict) -> list:
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib import colors

    story = []
    lines = md_content.splitlines()
    i = 0
    in_table = False
    table_rows = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            return
        col_count = max(len(r) for r in table_rows)
        # Wrap every table cell in Paragraph to guarantee auto-wrapping
        formatted_rows = []
        for r_idx, row in enumerate(table_rows):
            formatted_row = []
            for c_idx in range(col_count):
                cell_text = row[c_idx] if c_idx < len(row) else ""
                style = styles["TableHeader"] if r_idx == 0 else styles["TableCell"]
                formatted_row.append(Paragraph(cell_text, style))
            formatted_rows.append(formatted_row)

        avail_width = 515 # A4 width (595) minus 80pt margins
        col_width = avail_width / col_count
        t = Table(formatted_rows, colWidths=[col_width] * col_count)
        t_style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]
        t.setStyle(TableStyle(t_style))
        story.append(t)
        story.append(Spacer(1, 6))
        table_rows = []
        in_table = False

    first_title = True
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        # Check table
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            # Skip separator line (e.g. |---|---|)
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            flush_table()

        if not line:
            continue

        # Markdown headings
        if line.startswith("# "):
            if first_title:
                story.append(Paragraph(line[2:].strip(), styles["Title"]))
                story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceBefore=2, spaceAfter=8))
                first_title = False
            else:
                story.append(Paragraph(line[2:].strip(), styles["Heading1"]))
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=1, spaceAfter=5))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:].strip(), styles["Heading2"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=1, spaceAfter=4))
        elif line.startswith("### "):
            story.append(Paragraph(line[4:].strip(), styles["Heading3"]))
        elif line.startswith(("- ", "* ")):
            bullet_text = line[2:].strip()
            # Convert markdown bold **text** to <b>text</b>
            bullet_text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", bullet_text)
            story.append(Paragraph(f"&bull; {bullet_text}", styles["Bullet"]))
        elif line.startswith("> "):
            callout = line[2:].strip()
            callout = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", callout)
            story.append(Paragraph(callout, styles["Callout"]))
        else:
            para = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
            story.append(Paragraph(para, styles["Body"]))

    if in_table:
        flush_table()

    return story

def parse_json_to_story(spec: dict, styles: dict) -> list:
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image, PageBreak, HRFlowable
    from reportlab.lib import colors

    story = []
    if title := spec.get("title"):
        story.append(Paragraph(title, styles["Title"]))
        if subtitle := spec.get("subtitle") or spec.get("author"):
            story.append(Paragraph(subtitle, styles["Subtitle"]))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0284c7"), spaceBefore=2, spaceAfter=8))

    avail_width = 515
    for el in spec.get("elements", []):
        etype = el.get("type", "").lower()
        if etype in ("heading", "header"):
            level = int(el.get("level", 1))
            hstyle = styles.get(f"Heading{level}", styles["Heading2"])
            story.append(Paragraph(el.get("text", ""), hstyle))
            if level <= 2:
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=1, spaceAfter=4))
        elif etype == "paragraph":
            story.append(Paragraph(el.get("text", ""), styles["Body"]))
        elif etype == "bullet":
            story.append(Paragraph(f"&bull; {el.get('text', '')}", styles["Bullet"]))
        elif etype == "table":
            raw_rows = el.get("rows", [])
            if not raw_rows:
                continue
            col_count = max(len(r) for r in raw_rows)
            formatted_rows = []
            for r_idx, row in enumerate(raw_rows):
                f_row = []
                for c_idx in range(col_count):
                    val = str(row[c_idx]) if c_idx < len(row) else ""
                    st = styles["TableHeader"] if (r_idx == 0 and el.get("header", True)) else styles["TableCell"]
                    f_row.append(Paragraph(val, st))
                formatted_rows.append(f_row)
            col_widths = el.get("col_widths") or [avail_width / col_count] * col_count
            t = Table(formatted_rows, colWidths=col_widths)
            t_style = [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
            t.setStyle(TableStyle(t_style))
            story.append(t)
            story.append(Spacer(1, 6))
        elif etype == "image" and el.get("path"):
            w = float(el.get("width", 300))
            img = Image(el["path"])
            ratio = img.imageHeight / img.imageWidth
            img.drawWidth = w
            img.drawHeight = w * ratio
            story.append(img)
            story.append(Spacer(1, 8))
        elif etype == "hr":
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cbd5e1"), spaceBefore=4, spaceAfter=6))
        elif etype == "pagebreak":
            story.append(PageBreak())
        elif etype == "spacer":
            story.append(Spacer(1, float(el.get("height", 8))))

    return story

def render_pdf(input_path: str, output_path: str, page_size: str = "A4") -> bool:
    from reportlab.platypus import SimpleDocTemplate
    from reportlab.lib.pagesizes import A4, letter

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    size = letter if str(page_size).lower() == "letter" else A4

    doc = SimpleDocTemplate(
        str(out),
        pagesize=size,
        leftMargin=40,
        rightMargin=40,
        topMargin=36,
        bottomMargin=36,
    )

    styles = _get_styles()
    content_raw = Path(input_path).read_text(encoding="utf-8-sig")

    if input_path.endswith(".json"):
        spec = json.loads(content_raw)
        story = parse_json_to_story(spec, styles)
    else:
        story = parse_markdown_to_story(content_raw, styles)

    doc.build(story)
    print(f"[indra-pdf] Successfully created PDF: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="INDRA 100% Offline Platypus PDF Generator")
    parser.add_argument("input", help="Path to input Markdown (.md, .txt) or JSON (.json) spec")
    parser.add_argument("-o", "--output", required=True, help="Destination PDF path")
    parser.add_argument("--page-size", default="A4", choices=["A4", "letter"], help="Page size (A4 or letter)")
    args = parser.parse_args()

    render_pdf(args.input, args.output, args.page_size)

if __name__ == "__main__":
    main()

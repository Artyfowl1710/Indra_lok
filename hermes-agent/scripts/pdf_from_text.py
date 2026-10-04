#!/usr/bin/env python3
"""Render a short UTF-8 text or Markdown brief as a verified one-page PDF."""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path


def _font() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
    )
    for regular, bold in candidates:
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("IndraText", regular))
            pdfmetrics.registerFont(TTFont("IndraTextBold", bold))
            return "IndraText", "IndraTextBold"
    return "Helvetica", "Helvetica-Bold"


def _blocks(source: str) -> list[tuple[str, str]]:
    blocks = []
    table_headers: list[str] | None = None
    for raw in source.splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                continue
            if table_headers is None:
                table_headers = cells
            else:
                first = " - ".join(cells[:2])
                details = "; ".join(
                    f"{table_headers[index]}: {value}"
                    for index, value in enumerate(cells[2:], start=2)
                    if value and index < len(table_headers)
                )
                blocks.append(("rowtitle", first))
                if details:
                    blocks.append(("body", details))
            continue
        table_headers = None
        if re.fullmatch(r"[-=]{3,}", line):
            if blocks and blocks[-1][0] == "body":
                blocks[-1] = ("heading", blocks[-1][1])
            continue
        if not line:
            if blocks and blocks[-1][0] != "space":
                blocks.append(("space", ""))
            continue
        if line.startswith("# "):
            blocks.append(("title", line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(("heading", line[3:].strip()))
        elif line.startswith(("- ", "* ")):
            blocks.append(("bullet", line[2:].strip()))
        elif not blocks:
            blocks.append(("title", line))
        elif line.isupper() and len(line) < 70 and not line.endswith(":"):
            blocks.append(("heading", line))
        else:
            blocks.append(("body", line))
    while blocks and blocks[-1][0] == "space":
        blocks.pop()
    if not blocks or not any(text for _, text in blocks):
        raise ValueError("Input has no report text")
    return blocks


def build_pdf(source_path: Path, output_path: Path) -> dict:
    from pypdf import PdfReader
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import simpleSplit
    from reportlab.pdfgen import canvas

    blocks = _blocks(source_path.read_text(encoding="utf-8-sig"))
    regular, bold = _font()
    page_w, page_h = A4
    margin = 48
    available = page_h - 2 * margin - 24

    def layout(scale: float):
        rows = []
        height = 0.0
        for kind, value in blocks:
            if kind == "space":
                rows.append((kind, [], 0.0, 6 * scale, regular, 0))
                height += 6 * scale
                continue
            base_size, base_leading, face, indent = {
                "title": (16, 22, bold, 0),
                "heading": (11.5, 17, bold, 0),
                "bullet": (9.5, 13.5, regular, 13),
                "body": (9.5, 13.5, regular, 0),
            }[kind]
            size, leading = base_size * scale, base_leading * scale
            width = page_w - 2 * margin - indent * scale
            lines = simpleSplit(value, face, size, width)
            rows.append((kind, lines, size, leading, face, indent * scale))
            height += len(lines) * leading
        return rows, height

    rows = None
    for scale in (1.0, 0.92, 0.84, 0.76):
        candidate, height = layout(scale)
        if height <= available:
            rows = candidate
            break
    if rows is None:
        raise ValueError("Text does not fit on one page; shorten the report")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".indra-pdf-", suffix=".pdf", dir=output_path.parent)
    os.close(fd)
    try:
        pdf = canvas.Canvas(temporary, pagesize=A4)
        pdf.setTitle(next((text for kind, text in blocks if kind == "title"), "INDRA Report"))
        y = page_h - margin
        for kind, lines, size, leading, face, indent in rows:
            if kind == "space":
                y -= leading
                continue
            pdf.setFont(face, size)
            for index, line in enumerate(lines):
                prefix = "- " if kind == "bullet" and index == 0 else ""
                pdf.drawString(margin + indent, y, prefix + line)
                y -= leading
        pdf.setFont(regular, 8)
        pdf.setFillGray(0.4)
        pdf.drawString(margin, margin - 15, "INDRA | Generated from local source material")
        pdf.showPage()
        pdf.save()

        with open(temporary, "rb") as stream:
            if stream.read(4) != b"%PDF":
                raise ValueError("Output does not have a PDF header")
        reader = PdfReader(temporary)
        if len(reader.pages) != 1 or len(reader.pages[0].extract_text().strip()) < 40:
            raise ValueError("Output must have one non-empty page")
        os.replace(temporary, output_path)
        return {"output": str(output_path), "page_count": 1, "text_chars": len(reader.pages[0].extract_text())}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    import json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="UTF-8 .txt or .md file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Final .pdf path")
    args = parser.parse_args()
    if args.output.suffix.lower() != ".pdf":
        parser.error("output path must end in .pdf")
    print(json.dumps(build_pdf(args.source, args.output), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

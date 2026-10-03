#!/usr/bin/env python3
"""INDRA Word Document Generator: Context-Agnostic, 100% Offline python-docx Engine.

Supports:
1. Markdown or plain-text briefs (.md, .txt)
2. JSON specification (.json)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

def render_docx(input_path: str, output_path: str) -> bool:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = docx.Document()
    content_raw = Path(input_path).read_text(encoding="utf-8-sig")

    first_title = True
    in_table = False
    table_rows = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            return
        col_count = max(len(r) for r in table_rows)
        table = doc.add_table(rows=len(table_rows), cols=col_count)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'

        for r_idx, row in enumerate(table_rows):
            for c_idx in range(col_count):
                val = row[c_idx] if c_idx < len(row) else ""
                cell = table.cell(r_idx, c_idx)
                cell.text = val
                if r_idx == 0:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.font.bold = True
        doc.add_paragraph()
        table_rows = []
        in_table = False

    for raw in content_raw.splitlines():
        line = raw.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            table_rows.append(cells)
            in_table = True
            continue
        elif in_table:
            flush_table()

        if not line:
            continue

        if line.startswith("# "):
            if first_title:
                h = doc.add_heading(line[2:].strip(), level=0)
                first_title = False
            else:
                doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith(("- ", "* ")):
            bullet_text = line[2:].strip()
            p = doc.add_paragraph(style='List Bullet')
            # Handle simple bold
            parts = re.split(r"(\*\*.+?\*\*)", bullet_text)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    p.add_run(part[2:-2]).bold = True
                else:
                    p.add_run(part)
        else:
            p = doc.add_paragraph()
            parts = re.split(r"(\*\*.+?\*\*)", line)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    p.add_run(part[2:-2]).bold = True
                else:
                    p.add_run(part)

    if in_table:
        flush_table()

    doc.save(str(out))
    print(f"[indra-docx] Successfully created document: {output_path}")
    return True

def main():
    parser = argparse.ArgumentParser(description="INDRA 100% Offline Word (.docx) Generator")
    parser.add_argument("input", help="Path to input Markdown (.md, .txt) or JSON (.json)")
    parser.add_argument("-o", "--output", required=True, help="Destination .docx path")
    args = parser.parse_args()

    render_docx(args.input, args.output)

if __name__ == "__main__":
    main()

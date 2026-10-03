#!/usr/bin/env python3
"""INDRA Unified Document CLI Suite."""
from __future__ import annotations

import argparse
import sys

from indra_tools import pdf, pptx, xlsx, docx

def main():
    parser = argparse.ArgumentParser(
        prog="indra-tools",
        description="INDRA Unified 100% Offline Document Suite (PDF, PPTX, XLSX, DOCX)"
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True, help="Document format to generate")

    # PDF subparser
    pdf_p = subparsers.add_parser("pdf", help="Generate PDF from Markdown or JSON")
    pdf_p.add_argument("input", help="Path to input Markdown (.md, .txt) or JSON (.json)")
    pdf_p.add_argument("-o", "--output", required=True, help="Destination .pdf path")
    pdf_p.add_argument("--page-size", default="A4", choices=["A4", "letter"], help="Page size")

    # PPTX subparser
    pptx_p = subparsers.add_parser("pptx", help="Generate 16:9 PowerPoint presentation")
    pptx_p.add_argument("input", help="Path to input Markdown outline (.md, .txt) or JSON (.json)")
    pptx_p.add_argument("-o", "--output", required=True, help="Destination .pptx path")
    pptx_p.add_argument("--theme", default="modern_dark", choices=list(pptx.THEMES.keys()), help="Visual theme")

    # XLSX subparser
    xlsx_p = subparsers.add_parser("xlsx", help="Generate styled Excel spreadsheet")
    xlsx_p.add_argument("input", help="Path to input CSV (.csv), text (.txt), or JSON (.json)")
    xlsx_p.add_argument("-o", "--output", required=True, help="Destination .xlsx path")
    xlsx_p.add_argument("--sheet", default="Data", help="Sheet name")

    # DOCX subparser
    docx_p = subparsers.add_parser("docx", help="Generate Word (.docx) document")
    docx_p.add_argument("input", help="Path to input Markdown (.md, .txt) or JSON (.json)")
    docx_p.add_argument("-o", "--output", required=True, help="Destination .docx path")

    args = parser.parse_args()

    if args.subcommand == "pdf":
        pdf.render_pdf(args.input, args.output, args.page_size)
    elif args.subcommand == "pptx":
        pptx.render_pptx(args.input, args.output, args.theme)
    elif args.subcommand == "xlsx":
        xlsx.render_xlsx(args.input, args.output, args.sheet)
    elif args.subcommand == "docx":
        docx.render_docx(args.input, args.output)

if __name__ == "__main__":
    main()

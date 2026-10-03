#!/usr/bin/env python3
"""Build a verified, styled workbook from a pipe-delimited text log.

The first row may start with ``Field order:``. Data rows must have the
same number of pipe-separated fields. A Summary sheet is added when the
headers contain Status, Priority, or Due Date.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def parse(source: Path):
    headers = None
    rows = []
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line.lower().startswith("field order:"):
            headers = [part.strip() for part in line.split(":", 1)[1].split("|")]
            continue
        if not headers or "|" not in line:
            continue
        values = [part.strip() for part in line.split("|")]
        if len(values) != len(headers) or not re.match(r"^[A-Za-z0-9][\w.-]*$", values[0]):
            continue
        rows.append(values)
    if not headers or not rows:
        raise ValueError("Expected a 'Field order:' header and at least one matching pipe-delimited data row")
    return headers, rows


def create(source: Path, output: Path, as_of: date):
    headers, rows = parse(source)
    wb = Workbook()
    data = wb.active
    data.title = "Data"
    data.append(headers)
    for row in rows:
        converted = []
        for header, value in zip(headers, row):
            if value in ("", "-"):
                converted.append(None)
            elif "date" in header.lower() or header.lower() == "reported":
                try:
                    converted.append(date.fromisoformat(value))
                except ValueError:
                    converted.append(value)
            elif "cost" in header.lower():
                try:
                    converted.append(float(value))
                except ValueError:
                    converted.append(value)
            else:
                converted.append(value)
        data.append(converted)
    for cell in data[1]:
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True)
    data.row_dimensions[1].height = 30
    data.freeze_panes = "A2"
    data.auto_filter.ref = data.dimensions
    for column, header in enumerate(headers, 1):
        width = max(len(header), *(len(str(row[column - 1])) for row in rows)) + 3
        data.column_dimensions[get_column_letter(column)].width = min(max(width, 12), 52)
    for row in data.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, date):
                cell.number_format = "yyyy-mm-dd"
            elif isinstance(cell.value, float):
                cell.number_format = "#,##0.00"

    lookup = {header.casefold(): i for i, header in enumerate(headers)}
    summary = wb.create_sheet("Summary")
    summary.append(["Metric", "Value"])
    summary.append(["As of", as_of])
    summary.append(["Total records", len(rows)])
    if "status" in lookup:
        counts = Counter(row[lookup["status"]] for row in rows)
        for label, count in sorted(counts.items()):
            summary.append([f"Status: {label}", count])
    if "priority" in lookup:
        counts = Counter(row[lookup["priority"]] for row in rows)
        for label, count in sorted(counts.items()):
            summary.append([f"Priority: {label}", count])
    if "due date" in lookup and "status" in lookup:
        overdue = []
        for row in rows:
            try:
                due = date.fromisoformat(row[lookup["due date"]])
            except ValueError:
                continue
            if due < as_of and row[lookup["status"]].casefold() not in {"completed", "complete", "done", "closed"}:
                overdue.append(row[0])
        summary.append(["Overdue unfinished", len(overdue)])
        summary.append(["Overdue IDs", ", ".join(overdue)])
    for cell in summary[1]:
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.font = Font(color="FFFFFF", bold=True)
    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 55
    summary.freeze_panes = "A2"
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    check = load_workbook(output, read_only=True, data_only=True)
    assert check.sheetnames == ["Data", "Summary"]
    assert check["Data"].max_row == len(rows) + 1
    print(json.dumps({"output": str(output), "sheets": check.sheetnames, "data_rows": len(rows), "summary_rows": summary.max_row - 1}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    create(args.input, args.output, args.as_of)


if __name__ == "__main__":
    main()

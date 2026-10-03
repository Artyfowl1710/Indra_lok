---
name: mrpl-report-demo
description: Turn supplied MRPL information into Office reports.
version: 0.1.0
author: Kaivalya, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [mrpl, reports, docx, pdf, pptx, xlsx]
    category: productivity
    related_skills: [docx, pdf, powerpoint, xlsx]
---

# MRPL Report Demo Skill

Analyze user-supplied information about Mangalore Refinery and
Petrochemicals Limited (MRPL) and create a professional Word, PDF,
PowerPoint, or Excel deliverable. Work only from supplied files and prompt
content; this demo does not use Qdrant or web research.

## When to Use

- A supplied file contains MRPL company, operational, project, financial,
  sustainability, or business information.
- The user asks to analyze that material and produce a report, document,
  PDF, presentation, or spreadsheet.
- The user asks for an executive summary, findings, metrics table, or risks
  based on the supplied MRPL material.
- Do not use for unrelated companies or requests that require current facts
  beyond the supplied source.

## Prerequisites

- Use the existing `read_file` and `terminal` tools.
- The Python document libraries are installed and available in the environment.
- Related format skills `docx`, `pdf`, `powerpoint`, and `xlsx` are available
  for reading or editing existing Office files.

## Fast Path

For TXT or Markdown input, do not create `analysis.json`. After confirming the
file exists, make exactly one terminal call using the script path:

```bash
python skills/productivity/mrpl-report-demo/scripts/generate_report_pack.py \
  MRPL_Financial_Records_Demo.txt \
  --outdir outputs/mrpl-demo-output \
  --formats pdf
```

Change only `--formats` for other requested outputs. This direct path is the
default demo workflow because it avoids long intermediate model output.

## Procedure for complex or edited reports

1. Locate the attached or named source. For text and Markdown, use
   `read_file`. For DOCX, PDF, PPTX, or XLSX, follow the matching related
   skill's reader procedure. Confirm that extracted content is non-empty.
2. Analyze only the extracted evidence. Separate facts, calculated values,
   and interpretations. Never invent MRPL figures, dates, projects, or
   conclusions. Mark missing information as "Not provided in source."
3. Only when the user requests custom analysis or edits, create
   `outputs/mrpl-demo-output/analysis.json` with this shape:

   ```json
   {
     "title": "MRPL Business Analysis",
     "subtitle": "Analysis of supplied material",
     "executive_summary": "A concise evidence-based summary.",
     "sections": [
       {"heading": "Overview", "paragraphs": ["..."], "bullets": ["..."]}
     ],
     "metrics": [
       {"metric": "Name", "value": "Value from source", "note": "Context"}
     ],
     "sources": ["Supplied filename"]
   }
   ```

4. Use `write_file` to save valid JSON. Then use `terminal` to run:

   ```bash
   python skills/productivity/mrpl-report-demo/scripts/generate_report_pack.py \
     outputs/mrpl-demo-output/analysis.json \
     --outdir outputs/mrpl-demo-output \
     --formats docx,pdf,pptx,xlsx
   ```

   Generate only requested formats by changing `--formats`. If the user says
   "document," use `docx`; if they say "report" without a format, use
   `docx,pdf`.
5. Read the script's JSON result and report only files whose status is
   `created`. Include their exact paths.

## Pitfalls

- Do not use Qdrant, embeddings, RAG, or web search for this demo.
- Do not copy source text without analysis; organize it into findings and
  preserve the distinction between source facts and interpretation.
- Do not claim a file exists until the generator and validation succeed.
- Keep tables compact. Put large datasets in XLSX rather than slides.
- PDF output is created directly and does not require LibreOffice.

## Verification

- The generator must return `"status": "created"` for every requested file.
- Open each generated container as part of generation: python-docx for DOCX,
  pypdf for PDF, python-pptx for PPTX, and openpyxl for XLSX.
- Confirm every output exists under `outputs/mrpl-demo-output/` and is
  non-empty before replying.

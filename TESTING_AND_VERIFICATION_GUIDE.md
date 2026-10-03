# Indra System Verification & Testing Guide
**CodersbyChance — 100% Offline AI Workstation**

This guide provides concrete, step-by-step instructions to verify, review, and test every component of the Indra Agent system:
1. **Automated 1-Command Verification** (`verify_indra_system.py`)
2. **Context-Agnostic Document Suite** (`indra_tools` for PDF, PPTX, XLSX, DOCX)
3. **Frontend UI Interactive Cards** (Action Approvals & Clarifications)
4. **1-Click Execution Backend Switching** (Native Local vs Docker Sandbox)
5. **Offline Local AI Inference & 6GB VRAM Footprint**

---

## 1. Automated Turnkey Verification (1-Command Check)

A dedicated offline verification script is available in the workspace root. It validates all daemon services, config files, package installations, and document generation pipelines end-to-end.

### How to Run:
```powershell
# From the workspace root:
& "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\venv\Scripts\python.exe" verify_indra_system.py
```

### Expected Output:
```text
Starting Indra System Verification (100% Offline Check)

============================================================
 1. Core Offline Daemon Services
============================================================
[PASS] Llama-Swap Model Server (:8100)            (HTTP 200)
[PASS] Hermes Workbench API (:8000)               (HTTP 200)
[PASS] Indra Web Dashboard (:9119)                (HTTP 200)

============================================================
 2. Execution Mode Configuration
============================================================
[PASS] Terminal Sandbox Mode                      Mode is currently 'local' (Native Host Execution)

============================================================
 3. Context-Agnostic 'indra_tools' Library
============================================================
[PASS] indra_tools installed in environment       v1.0.0
[PASS] indra_tools.pdf module                     render_pdf() ready
[PASS] indra_tools.pptx module                    render_pptx() ready
[PASS] indra_tools.xlsx module                    render_xlsx() ready
[PASS] indra_tools.docx module                    render_docx() ready

============================================================
 4. Live Offline Document Generation Pipeline
============================================================
[indra-pdf] Successfully created PDF: ...\outputs\healthcheck\verify_test.pdf
[PASS] Generate Reflowing PDF (Platypus)          Size: 1783 bytes
[indra-pptx] Successfully created presentation: ...\outputs\healthcheck\verify_test.pptx
[PASS] Generate 16:9 PPTX Slides                  Size: 28480 bytes
[indra-xlsx] Successfully created spreadsheet: ...\outputs\healthcheck\verify_test.xlsx
[PASS] Generate Styled Excel XLSX                 Size: 5320 bytes
[indra-docx] Successfully created document: ...\outputs\healthcheck\verify_test.docx
[PASS] Generate Formatted Word DOCX               Size: 36645 bytes

============================================================
 Verification Summary
============================================================
Total Checks: 13 | Passed: 13 | Score: 100.0%

ALL SYSTEMS OPERATIONAL & 100% OFFLINE READY!
```

---

## 2. Context-Agnostic Document Generation Suite (`indra_tools`)

### Why Packaging Solves the Product Problem
In earlier iterations, helper scripts lived in relative folders (e.g. `skills/productivity/pdf/scripts/pdf_create.py`). Whenever the agent ran from `/tmp/outputs/` or the workspace root, relative paths failed with `FileNotFoundError`, forcing the model to write broken, low-level inline scripts (`canvas.drawString()` clipping text, or invalid `Inches.inches` calls).

**The Solution:**
`indra_tools` is now an installed Python package in the workspace virtual environment (`c:\Users\khatr\OneDrive\Desktop\SIH-26-main\venv\Lib\site-packages\indra_tools.egg-link`). It can be invoked via Python from **any working directory**, requiring zero internet and having zero relative path assumptions:

| Format | Module Invocation | Capabilities |
|---|---|---|
| **PDF** | `python -m indra_tools.pdf <input> -o <output.pdf>` | ReportLab Platypus engine, auto-reflowing Markdown/JSON, auto-wrapped table cells, headers/footers. |
| **PPTX** | `python -m indra_tools.pptx <input> -o <output.pptx>` | 16:9 widescreen slides, themes (`modern_dark`, `modern_light`, `executive`), auto-scaled typography, native charts. |
| **XLSX** | `python -m indra_tools.xlsx <input> -o <output.xlsx>` | openpyxl engine, auto-sized columns, frozen headers, zebra stripes, formula totals. |
| **DOCX** | `python -m indra_tools.docx <input> -o <output.docx>` | python-docx engine, Markdown heading outlines, formatted tables, bullet hierarchies. |

### CLI Verification Tests:

#### Test A: Generate a PDF from any directory
```powershell
python -m indra_tools.pdf outputs/test_docs/sample_report.md -o outputs/test_docs/cli_test.pdf --title "Audit Report"
```
*Verification:* Open [outputs/test_docs/cli_test.pdf](file:///c:/Users/khatr/OneDrive/Desktop/SIH-26-main/outputs/test_docs/cli_test.pdf). Notice full page reflow, dark navy header bar, clean typography, and zero truncated lines.

#### Test B: Generate 16:9 Presentation Slides
```powershell
python -m indra_tools.pptx outputs/test_docs/sample_slides.md -o outputs/test_docs/cli_test.pptx --theme modern_dark
```
*Verification:* Open [outputs/test_docs/cli_test.pptx](file:///c:/Users/khatr/OneDrive/Desktop/SIH-26-main/outputs/test_docs/cli_test.pptx) in PowerPoint. Verify 16:9 widescreen layout, modern dark gradient background, and accent cards.

#### Test C: Generate Styled Excel Spreadsheet
```powershell
python -m indra_tools.xlsx outputs/test_docs/sample_data.csv -o outputs/test_docs/cli_test.xlsx --title "Q3 Summary"
```
*Verification:* Open [outputs/test_docs/cli_test.xlsx](file:///c:/Users/khatr/OneDrive/Desktop/SIH-26-main/outputs/test_docs/cli_test.xlsx). Verify bold header row, frozen pane, auto-adjusted column widths, and automatic sum formulas on numeric columns.

#### Test D: Generate Word Document
```powershell
python -m indra_tools.docx outputs/test_docs/sample_report.md -o outputs/test_docs/cli_test.docx
```
*Verification:* Open [outputs/test_docs/cli_test.docx](file:///c:/Users/khatr/OneDrive/Desktop/SIH-26-main/outputs/test_docs/cli_test.docx). Verify clean Word document structure with formatted tables and headings.

---

## 3. Frontend UI Verification (Action Approvals & Clarifications)

The Indra Web Dashboard is running live at **[http://127.0.0.1:9119](http://127.0.0.1:9119)**.

### Test Case 1: Action Approval Card
**Goal:** Verify that destructive or high-risk commands do not freeze silently in Chain-of-Thought (CoT), but present an interactive approval card with Approve/Reject buttons.

1. Open your browser to [http://127.0.0.1:9119](http://127.0.0.1:9119).
2. Start a new chat session.
3. Submit a prompt requesting a protected action, for example:
   ```text
   Run a terminal command to delete the temporary file outputs/healthcheck/verify_test.pdf and confirm.
   ```
4. **Expected UI Behavior:**
   - Instead of a 300-second silent hang, the chat feed immediately renders the **Amber Action Approval Card**:
     - Header: **⚠️ Action Approval Required**
     - Description of tool and exact command parameters (e.g. `rm outputs/healthcheck/verify_test.pdf`).
     - Two prominent buttons:
       - **Approve Action** (Green button with checkmark)
       - **Reject Action** (Red button with 'X')
   - Clicking **Approve Action** immediately sends the WebSocket event `approval.respond` (`verdict: "approved"`), allowing the agent to proceed without delay.
   - Clicking **Reject Action** informs the agent that permission was denied.

### Test Case 2: Clarification Prompt Card
**Goal:** Verify that when the agent needs guidance, it renders selectable choice cards instead of guessing.

1. In the chat interface, submit a prompt that triggers a clarifying question.
2. **Expected UI Behavior:**
   - The chat feed renders a **Cyan Clarification Card**:
     - Header: **💬 Clarification Needed**
     - Selectable pills/buttons for suggested options.
     - A custom text input field if the user prefers to write a specific answer.

---

## 4. 1-Click Execution Backend Switching (Local vs Docker)

**Goal:** Verify that you can switch between Native Local execution and Docker Sandbox execution in one click without modifying any configuration files by hand.

1. In the dashboard, navigate to **Sandbox** ([http://127.0.0.1:9119/sandbox](http://127.0.0.1:9119/sandbox)) or **Settings**.
2. Locate the **Terminal Sandbox Environment** section:
   - Option A: **Local Host (Native)** — Agent runs commands directly on the host Windows machine using local Python and tools.
   - Option B: **Docker Sandbox Container** — Agent runs commands isolated inside the `indra-documents:1` container.
3. Click between **Local Host** and **Docker Sandbox**:
   - The UI automatically calls `PUT /api/tools/terminal/backend`.
   - The active setting updates immediately with a success notification.
4. When set to **Local Host**, verify with:
   ```powershell
   & "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\venv\Scripts\python.exe" -c "from tools.terminal_scope import terminal_env; print(terminal_env('TERMINAL_ENV', 'local'))"
   ```
   Output will display: `local`.

---

## 5. End-to-End Autonomous Agent Test

Test Indra Agent's complete autonomous document generation pipeline directly through the chat UI:

### Test Prompt:
```text
Create a clean 3-slide presentation on "Indra Architecture Overview" in ./outputs/indra_arch.pptx with a dark theme, and generate a matching 1-page summary PDF in ./outputs/indra_arch.pdf. Use the indra_tools suite.
```

### What the Agent Will Do:
1. Formulate the outline and content for the slides and PDF.
2. Run `python -m indra_tools.pptx` to generate `./outputs/indra_arch.pptx` (16:9 widescreen, dark theme).
3. Run `python -m indra_tools.pdf` to generate `./outputs/indra_arch.pdf` (Platypus reflow engine).
4. Verify both deliverables on disk using `python-pptx` and `pypdf`.
5. Provide you with the final verified file paths.

---

## 6. Service Port Reference & Process Maintenance

| Port | Service | Process / Executable | Health Check URL |
|:---:|---|---|:---:|
| **8100** | Llama-Swap Model Server | `hermes-agent/backend/bin/llama-swap.exe` | [http://127.0.0.1:8100/](http://127.0.0.1:8100/) |
| **8000** | Hermes Workbench API | `uvicorn server.app:app` | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |
| **9119** | Indra Web Dashboard | `hermes-agent/hermes_cli/web_dist/` | [http://127.0.0.1:9119/](http://127.0.0.1:9119/) |

### Quick Restart Command (PowerShell):
If you ever restart your PC or close background processes:
```powershell
# Stop any existing processes
Stop-Process -Name "llama-swap","llama-server" -Force -ErrorAction SilentlyContinue

# Start Llama-Swap
Start-Process -FilePath "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\SIH-26\hermes-agent\backend\bin\llama-swap.exe" `
  -ArgumentList "--config c:\Users\khatr\OneDrive\Desktop\SIH-26-main\SIH-26\hermes-agent\backend\config\llama-swap.yaml --listen 127.0.0.1:8100 --watch-config" `
  -WorkingDirectory "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\SIH-26\hermes-agent\backend" -WindowStyle Hidden

# Start Workbench API
Start-Process -FilePath "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\SIH-26\hermes-agent\backend\venv\Scripts\python.exe" `
  -ArgumentList "-m uvicorn server.app:app --host 127.0.0.1 --port 8000" `
  -WorkingDirectory "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\SIH-26\hermes-agent\backend" -WindowStyle Hidden

# Start Indra Dashboard
Start-Process -FilePath "c:\Users\khatr\OneDrive\Desktop\SIH-26-main\venv\Scripts\indra.exe" `
  -ArgumentList "dashboard --skip-build --no-open" `
  -WorkingDirectory "c:\Users\khatr\OneDrive\Desktop\SIH-26-main" -WindowStyle Hidden
```

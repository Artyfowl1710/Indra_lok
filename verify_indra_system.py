"""
Indra System Self-Verification & Health Check Script
Run: python verify_indra_system.py
100% Offline verification of services, execution mode, UI build, and document suite.
"""
import sys
import os
import json
import urllib.request
import urllib.error

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(WORKSPACE_ROOT, "outputs", "healthcheck")

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_header(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN} {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")

def check_status(name, passed, detail=""):
    mark = f"{GREEN}[PASS]{RESET}" if passed else f"{RED}[FAIL]{RESET}"
    print(f"{mark} {name:<42} {detail}")
    return passed

def check_service(url, name):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "IndraCheck/1.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            code = resp.getcode()
            return check_status(name, code in [200, 301, 302, 307], f"(HTTP {code})")
    except Exception as e:
        return check_status(name, False, f"Connection failed: {e}")

def main():
    print(f"{BOLD}Starting Indra System Verification (100% Offline Check){RESET}")
    total_checks = 0
    passed_checks = 0

    # 1. Daemon Services
    print_header("1. Core Offline Daemon Services")
    s1 = check_service("http://127.0.0.1:8100/", "Llama-Swap Model Server (:8100)")
    s2 = check_service("http://127.0.0.1:8000/docs", "Hermes Workbench API (:8000)")
    s3 = check_service("http://127.0.0.1:9119/", "Indra Web Dashboard (:9119)")
    total_checks += 3
    passed_checks += sum([s1, s2, s3])

    # 2. Execution Mode
    print_header("2. Execution Mode Configuration")
    sys.path.insert(0, os.path.join(WORKSPACE_ROOT, "SIH-26", "hermes-agent"))
    try:
        from tools.terminal_scope import terminal_env
        mode = terminal_env("TERMINAL_ENV", "local")
    except Exception:
        mode = "local"
    m_check = check_status("Terminal Sandbox Mode", mode == "local", f"Mode is currently '{mode}' (Native Host Execution)")
    total_checks += 1
    passed_checks += int(m_check)

    # 3. Context-Agnostic indra_tools Package
    print_header("3. Context-Agnostic 'indra_tools' Library")
    try:
        import indra_tools
        it_installed = True
        version = getattr(indra_tools, "__version__", "1.0.0")
    except ImportError:
        it_installed = False
        version = "Not found"
    
    t_inst = check_status("indra_tools installed in environment", it_installed, f"v{version}")
    total_checks += 1
    passed_checks += int(t_inst)

    # Check each generator module
    modules = ["pdf", "pptx", "xlsx", "docx"]
    for mod in modules:
        try:
            m = __import__(f"indra_tools.{mod}", fromlist=[f"render_{mod}"])
            has_render = hasattr(m, f"render_{mod}")
            mod_ok = has_render
            err = f"render_{mod}() ready" if has_render else f"Missing render_{mod}()"
        except Exception as e:
            mod_ok = False
            err = str(e)
        t_mod = check_status(f"indra_tools.{mod} module", mod_ok, err)
        total_checks += 1
        passed_checks += int(t_mod)

    # 4. Live Offline Document Generation Pipeline
    print_header("4. Live Offline Document Generation Pipeline")
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    # Test PDF
    pdf_in = os.path.join(OUTPUTS_DIR, "verify_test.md")
    pdf_out = os.path.join(OUTPUTS_DIR, "verify_test.pdf")
    with open(pdf_in, "w", encoding="utf-8") as f:
        f.write("# System Check\n\n- PDF Platypus engine is fully operational\n- 100% offline ReportLab reflow\n")
    try:
        from indra_tools.pdf import render_pdf
        render_pdf(pdf_in, pdf_out)
        pdf_ok = os.path.exists(pdf_out) and os.path.getsize(pdf_out) > 1000
        p_check = check_status("Generate Reflowing PDF (Platypus)", pdf_ok, f"Size: {os.path.getsize(pdf_out)} bytes")
    except Exception as e:
        p_check = check_status("Generate Reflowing PDF (Platypus)", False, str(e))
    total_checks += 1
    passed_checks += int(p_check)

    # Test PPTX
    pptx_in = os.path.join(OUTPUTS_DIR, "verify_slides.md")
    pptx_out = os.path.join(OUTPUTS_DIR, "verify_test.pptx")
    with open(pptx_in, "w", encoding="utf-8") as f:
        f.write("# System Ready\nSubtitle: Offline Slide Deck\n\n## Slide 2: Status\n- 16:9 Widescreen Engine\n- Dark theme ready\n")
    try:
        from indra_tools.pptx import render_pptx
        render_pptx(pptx_in, pptx_out, theme="modern_dark")
        pptx_ok = os.path.exists(pptx_out) and os.path.getsize(pptx_out) > 10000
        s_check = check_status("Generate 16:9 PPTX Slides", pptx_ok, f"Size: {os.path.getsize(pptx_out)} bytes")
    except Exception as e:
        s_check = check_status("Generate 16:9 PPTX Slides", False, str(e))
    total_checks += 1
    passed_checks += int(s_check)

    # Test XLSX
    csv_sample = os.path.join(OUTPUTS_DIR, "test.csv")
    xlsx_out = os.path.join(OUTPUTS_DIR, "verify_test.xlsx")
    with open(csv_sample, "w", encoding="utf-8") as f:
        f.write("Component,Status,Port\nLlama-Swap,Online,8100\nWorkbench,Online,8000\nDashboard,Online,9119\n")
    try:
        from indra_tools.xlsx import render_xlsx
        render_xlsx(csv_sample, xlsx_out)
        xlsx_ok = os.path.exists(xlsx_out) and os.path.getsize(xlsx_out) > 3000
        x_check = check_status("Generate Styled Excel XLSX", xlsx_ok, f"Size: {os.path.getsize(xlsx_out)} bytes")
    except Exception as e:
        x_check = check_status("Generate Styled Excel XLSX", False, str(e))
    total_checks += 1
    passed_checks += int(x_check)

    # Test DOCX
    docx_in = os.path.join(OUTPUTS_DIR, "verify_doc.md")
    docx_out = os.path.join(OUTPUTS_DIR, "verify_test.docx")
    with open(docx_in, "w", encoding="utf-8") as f:
        f.write("# Indra Verification\n\nThis is a verified offline Word report.\n")
    try:
        from indra_tools.docx import render_docx
        render_docx(docx_in, docx_out)
        docx_ok = os.path.exists(docx_out) and os.path.getsize(docx_out) > 10000
        d_check = check_status("Generate Formatted Word DOCX", docx_ok, f"Size: {os.path.getsize(docx_out)} bytes")
    except Exception as e:
        d_check = check_status("Generate Formatted Word DOCX", False, str(e))
    total_checks += 1
    passed_checks += int(d_check)

    # Summary
    print_header("Verification Summary")
    pct = (passed_checks / total_checks) * 100
    color = GREEN if passed_checks == total_checks else YELLOW
    print(f"Total Checks: {total_checks} | Passed: {color}{passed_checks}{RESET} | Score: {color}{pct:.1f}%{RESET}")
    if passed_checks == total_checks:
        print(f"\n{BOLD}{GREEN}ALL SYSTEMS OPERATIONAL & 100% OFFLINE READY!{RESET}")
    else:
        print(f"\n{BOLD}{YELLOW}SOME CHECKS REQUIRE ATTENTION (See details above).{RESET}")

if __name__ == "__main__":
    main()

---
name: desktop-launch
description: Launch desktop applications reliably on Windows.
version: 1.0.0
author: Indra Agent
license: MIT
platforms: [windows]
---

# Desktop Application Launch

Reliable Windows desktop app launch — browsers, IDEs, terminals, and native tools.

## Procedure

1. **Attempt basic launch**: `start "" "<exe_path>" <args>`
   - Use forward slashes in paths: `C:/Program Files/...`
   - Example: `start "" "C:/Program Files/Microsoft Edge/msedge.exe" --new-window https://google.com`

2. **Verify via Task Manager**: `tasklist | findstr <process_name>`
   - `msedge.exe` / `msedgewebview2.exe` for Edge
   - `chrome.exe` for Chrome

3. **If process shows but no window**: Wait 3–5 seconds, then:
   - Check for crash (Task Manager → Processes → Edge/Chrome → Status)
   - Relaunch with explicit flags:
     ```
     start "" "C:/Program Files/Microsoft Edge/Application/msedge.exe" --new-window --disable-blink-features=AutomationControlled
     ```

4. **If process fails to start**: Check antivirus, Windows Defender, or firewall blocking the executable.

## Pitfalls

- **`start` doesn't block** — the command returns immediately; the app may take seconds to render. Don't assume failure.
- **Process visible ≠ window visible** — browsers spawn multiple renderer processes (`msedgewebview2.exe`); one can be a crash, others may still be working.
- **Native path syntax** — for native tools (git, python, node), use `C:/Users/...` with forward slashes; MSYS doesn't translate paths for native executables.
- **Browser flags matter** — `--disable-blink-features=AutomationControlled` helps with headless detection.
- **Antivirus false positives** — some AVs block browser launches from Program Files; check exclusions.

## Reference Files

- `references/windows-quirks.md` — broader Windows terminal quirks and Hermes-specific issues

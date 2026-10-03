# INDRA teammate setup (Windows source ZIP)

This guide is for a teammate who received the **project ZIP**, not a finished
`INDRA-Setup.exe` release. It explains how to install and run the current
checkout on another Windows PC. Run commands in **Windows PowerShell** from the
folder containing `install-indra.ps1` and `indra.cmd`.

> **Important:** A source ZIP is not a self-contained offline installer.
> Virtual environments, GGUF models, and many executables are excluded from
> source archives. The current `install-indra.ps1` downloads Python tooling,
> Node, packages, llama.cpp, and models during first setup. Normal agent
> operation can be local, but this setup requires an approved network channel
> unless those dependencies are provided separately. Docker's `--network=none`
> isolates the document/code container; it does **not** air-gap the whole PC.

## 1. Requirements

| Item | Requirement / note |
| --- | --- |
| Operating system | Windows 10/11, 64-bit. Windows 11 is the development-tested environment. |
| RAM | 16 GB minimum; 32 GB recommended if other applications will run alongside models. |
| Disk | At least 30 GB free; allow more for models, Docker images, and generated files. |
| GPU | NVIDIA GPU recommended. The current model setup uses a CUDA llama.cpp build; a 6 GB VRAM GPU is the safer target. CPU-only setup is not verified here. |
| Docker | Docker Desktop with WSL 2 and hardware virtualization enabled for sandboxed code/document generation. Start Docker Desktop before testing those features. |
| Network for first install | Approved access to Python/Node/package/model sources, or an internally provisioned equivalent. Runtime internet access is not required for the local demo after provisioning. |
| Permissions | A normal user account is intended. Your organization may still need to approve Docker Desktop, downloaded executables, and PowerShell script execution. |

Do not copy a virtual environment from the sender's PC. A Windows venv contains
machine-specific paths and must be created on the teammate's own computer.

## 2. Check what was actually shared

Extract the ZIP to a short, writable path such as
`C:\Users\<your-name>\INDRA`. Do not run it from inside the compressed ZIP or
from a network share. In PowerShell, enter the extracted folder:

```powershell
cd 'C:\Users\<your-name>\INDRA'
Test-Path .\install-indra.ps1
Test-Path .\indra.cmd
Test-Path .\SIH-26\hermes-agent\backend\bin\llama-swap
Get-ChildItem .\SIH-26\hermes-agent\backend\models -Filter *.gguf -ErrorAction SilentlyContinue
```

The first two checks must return `True`. The current backend expects
`llama-swap` or `llama-swap.exe` in `backend\bin`; **the root installer does
not download llama-swap**. Ask the sender for the matching, approved binary if
it is absent. An empty `backend\models` folder is expected for a source ZIP;
the online installer attempts to download the configured models. The useful
minimum for text chat is `Qwen3.5-4B-Q4_K_M.gguf`. The other configured models
are `gemma-2-2b-it-Q4_K_M.gguf`,
`Qwen2-VL-OCR-2B-Instruct.Q4_K_M.gguf`, and its
`mmproj-Qwen2-VL-2B-Instruct-f16.gguf` projector for OCR/vision.

Ask the sender for a SHA-256 manifest for any separately transferred models,
executables, or Docker image. Check each received file with:

```powershell
Get-FileHash -Algorithm SHA256 'C:\path\to\received-file'
```

Do **not** reuse the sender's `.env`, API key, logs, databases, session files,
or generated `backend\config\llama-swap.yaml`: that YAML contains the
sender's absolute model paths and is regenerated locally.

## 3. Install from the source ZIP (approved-network route)

Start Docker Desktop if you plan to test code execution or PDF/Excel/PPT
creation. From the project root, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-indra.ps1
```

The current installer provisions a project-local Python 3.12 environment via
`uv`, installs INDRA and backend Python packages, downloads the CUDA llama.cpp
runtime if needed, downloads configured GGUF models if missing, builds the web
UI with Node, and creates an **INDRA Dashboard** desktop shortcut. The initial
download/build can take substantially longer than a normal launch. Keep the
PowerShell window open and address any error it prints before proceeding.

**Security caveat for this development installer:** it currently writes a
fixed demonstration `WORKBENCH_API_KEY` into local `.env` files, and the model
downloader logs computed SHA-256 values but does not compare them against
trusted pinned hashes. Do not treat this as a production-secure installer or
expose the backend ports to other machines. Use a unique per-machine key and
operator-approved artifact checks before any broader deployment. The app's
backend startup can create a random key when no valid backend `.env` exists,
but that is a separate provisioning path; do not delete or edit credentials
casually after installation without updating dependent settings.

### Verify installation files

```powershell
Test-Path .\venv\Scripts\indra.exe
Test-Path .\SIH-26\hermes-agent\backend\venv\Scripts\python.exe
Test-Path .\SIH-26\hermes-agent\backend\bin\llama-server.exe
Test-Path .\SIH-26\hermes-agent\backend\bin\llama-swap
Get-ChildItem .\SIH-26\hermes-agent\backend\models -Filter *.gguf |
  Select-Object Name, Length
```

Every `Test-Path` should be `True`, except that `llama-swap.exe` may replace
the extensionless `llama-swap` file. The model list must not be empty. If the
installer failed, **do not launch INDRA yet**; fix the first installation
error. Do not try to repair it by copying someone else's `venv` folder.

## 4. Enable the offline document/code sandbox

INDRA's document-generation tools use the `indra-documents:1` Docker image.
Its tag is referenced in `SIH-26\config.yaml`, but the image is stored in the
local Docker engine and is **not included automatically in a source ZIP**.
Build it once while your approved package source is available:

```powershell
cd .\SIH-26\hermes-agent
docker build -t indra-documents:1 -f docker/Dockerfile.indra-documents .
docker run --rm --network=none indra-documents:1 python /opt/indra/smoke_indra_documents.py
cd ..\..
```

The smoke test should create/read back a PDF, Excel workbook, and PowerPoint
file inside a network-disabled container. A Docker build may contact package
repositories, so do it before disconnecting the PC or use an approved internal
registry/build pipeline. Do not grant the agent runtime internet access to
install missing packages. If `docker` is not available, text chat may still
work, but the sandboxed code/document demo is **not ready**.

## 5. Start INDRA

From the project root, run one of these:

```powershell
.\indra.cmd dashboard
```

or double-click **INDRA Dashboard** if the installer created the shortcut.
Leave the launcher window open. It starts local inference on ports `8100`
(llama-swap) and `8000` (Workbench), then the web dashboard on `9119`. Open
`http://127.0.0.1:9119` on the same PC. The first answer can be slow while a
model loads into GPU memory.

For a CLI-only check, open a **second** PowerShell window in the project root:

```powershell
.\indra.cmd chat -q "Reply READY only" --cli
```

Avoid running multiple GPU-heavy requests concurrently on a small GPU.

### Basic health checks

```powershell
Test-NetConnection 127.0.0.1 -Port 8100
Test-NetConnection 127.0.0.1 -Port 8000
Test-NetConnection 127.0.0.1 -Port 9119
docker image inspect indra-documents:1
```

The three `TcpTestSucceeded` values should be `True` once everything is up.
`docker image inspect` should find the image when document/code features are
required. These are localhost services; do not forward the ports publicly.

## 6. Files and paths on the teammate's PC

| What | Location relative to the extracted project root |
| --- | --- |
| Final files created by INDRA | `outputs\` (container path `/workspace/outputs/`) |
| Model files | `SIH-26\hermes-agent\backend\models\` |
| Generated model-server config | `SIH-26\hermes-agent\backend\config\llama-swap.yaml` |
| Backend logs | `SIH-26\hermes-agent\backend\data\` |
| Frontend/CLI environment | `venv\` (created locally) |
| Backend environment | `SIH-26\hermes-agent\backend\venv\` (created locally) |

Do not save final agent deliverables under `/tmp` in the container; that is
for temporary working files. Share the verified file from the host's
`outputs\` folder.

## 7. Troubleshooting

| Symptom | Check / action |
| --- | --- |
| “venv not found” or `indra.exe` missing | Installation did not finish, or a venv was copied from another PC. Re-run the installer on this PC; inspect the first failed step. |
| `llama-swap is missing` | Check `backend\bin\llama-swap` or `llama-swap.exe`. The source installer does not fetch it; obtain the approved matching binary. |
| `llama-server is missing` | The llama.cpp download/extraction failed. Check the install log/output and approved network access. |
| No models or “model not found” | Check `backend\models\*.gguf`. Do not reuse the sender's generated `llama-swap.yaml`; launch again to regenerate paths. |
| Dashboard opens but replies fail | Check ports 8000/8100, backend logs, model files, and available GPU memory. |
| Port 8000, 8100, or 9119 already in use | Identify the existing process with `Get-NetTCPConnection -LocalPort <port>` before stopping anything. Avoid running two INDRA copies. |
| Docker/document task fails | Start Docker Desktop; confirm `docker image inspect indra-documents:1` and run the network-disabled smoke test above. |
| Model load crashes or is very slow | Close other GPU applications, check the NVIDIA driver/GPU memory, and try one request at a time. Hardware below the tested class may need a smaller model/configuration. |
| First setup fails behind a corporate proxy | Use an approved internal package/model channel. Do not silently enable unrestricted agent internet access. |
| Windows blocks a downloaded file | Validate its source/hash and ask IT to approve it. Do not disable security controls blindly. |

The old `README.md` contains setup claims that may not match this checkout
(including a fully automatic/offline installer). For a **source ZIP handoff**,
use this guide and verify the actual installed files on the teammate's PC.

## 8. If the teammate must be fully offline from the first minute

The current source ZIP and `install-indra.ps1` do **not** meet that requirement.
Before transfer, an operator must prepare and verify all dependencies: the
local model GGUFs and vision projector, matching llama-swap/llama.cpp binaries
and CUDA DLLs, Python/Node/uv installers plus Python/JavaScript package
artifacts, and a scanned `indra-documents:1` Docker image archive or internal
registry mirror. The setup flow must then be adapted to those local/approved
sources. A ZIP of source code by itself cannot make this a guaranteed offline
installation.


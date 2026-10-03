# INDRA command guide

Open PowerShell or Command Prompt. The global `indra` command works from any folder after installation. If the installer has just changed PATH, open a new terminal first.

## Everyday commands

| Command | Purpose |
| --- | --- |
| `indra` | Open the interactive INDRA terminal interface. |
| `indra setup` | Run INDRA's configuration wizard. |
| `indra dashboard` | Start the local backend and web dashboard. |
| `indra dashboard --status` | Show dashboard status. |
| `indra dashboard --stop` | Stop the dashboard. |
| `indra serve` | Start only the headless backend server. |
| `indra --tui` | Explicitly open the terminal interface. |
| `indra --help` | Show all available CLI options. |

The dashboard is normally available at <http://127.0.0.1:9119> after `indra dashboard` starts it.

Use `indra dashboard` for normal use because it starts the services needed by the web interface. Use `indra serve` only when another application needs the backend without the dashboard.

Normal `indra`, chat, TUI, dashboard, and one-shot invocations automatically check ports `8000` and `8100` and start the local inference backend when it is offline. You do not normally need to start it separately.

## Voice commands

Run these inside the INDRA terminal or the dashboard Command Center:

| Command | Purpose |
| --- | --- |
| `/voice` | Turn voice mode on or off. |
| `/voice status` | Check microphone capture and speech-to-text availability. |
| `/voice on` | Enable voice mode. |
| `/voice off` | Disable voice mode. |

The first recording may cause Windows or the browser to ask for microphone permission.

## Starting directly from this folder

If the global command is unavailable, run the project launcher:

```powershell
.\indra.cmd
.\indra.cmd setup
.\indra.cmd dashboard
```

The all-in-one Windows launcher is also available:

```powershell
.\start-indra.ps1
```

## Initial installation or repair

Run this from the project root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install-indra.ps1
```

This installs the project-local Python and Node runtimes, dependencies, inference runtime, dashboard assets, global `indra` launcher, and desktop shortcut.

## Troubleshooting

### `indra` points to `AppData\Local\hermes`

That path belongs to the older launcher. Re-run `install-indra.ps1`; the installer creates a compatibility launcher for older PowerShell profiles as well as the current `AppData\Local\Indra\bin` command.

### Dashboard does not open

Run:

```powershell
indra dashboard --status
indra dashboard
```

Then open <http://127.0.0.1:9119>.

### Voice does not start

Open Command Center and run `/voice status`. Confirm that both Audio capture and STT provider show `OK`, then run `/voice on`.

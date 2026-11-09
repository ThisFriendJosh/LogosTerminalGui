# Using Logos Terminal GUI

Launch `Start_Terminal_GUI.cmd` on Windows or run `python terminal_gui.py` from the checkout.

## Workspaces

Choose a terminal in the sidebar. Each terminal supplies its own actions, placeholder text and optional settings. Sending the first request connects that terminal automatically. Switch terminals to return to their current transcripts and drafts; the sidebar scrolls when many modules are loaded.

Scratchpad saves notes on this computer and can filter its saved notes. The SDK echo example is a connection test, not a model. LogosMind connects to an existing backend installation through its own adapter.

The GUI and its model backends are separate projects. Configure the LogosMind project and interpreter under Settings > Terminal settings. The host can run in an ordinary Python/Tk environment; LogosMind can run in its existing Unsloth environment.

## Compose and read

- Enter submits; Shift+Enter adds a line.
- Ctrl+L focuses the composer.
- Copy copies the visible workspace transcript.
- New and History appear enabled only when the connected module advertises those actions.
- Stop interrupts an owned worker. Reconnect when ready; it does not delete backend conversations.
- Logs displays the module's current diagnostics.

For LogosMind, Bible/Search/Lexicon output becomes source data for the next chat question. These capabilities belong to that backend. Missing models, training checkpoints or source data must be configured in the backend installation.

## Add a terminal

Load terminal > Load a module opens a JSON module manifest. The host checks the manifest and, on connection, verifies the worker's version and advertised capabilities. Importing a module does not execute its program. Use the SDK contract for new rich integrations.

Load terminal > Link an existing terminal registers a normal redirected-input/output console program, Python script or Windows batch file. Give it a name, program path, optional arguments and working folder. Quote argument paths containing spaces. Full-screen terminal applications and interactive password prompts may need a purpose-built adapter.

Use an explicit interpreter in a module's command array when it has its own environment. Keeping dependencies in that environment prevents the host and modules from changing each other's installed packages.

## Appearance

Settings adjusts reading font size from 10 to 18. The compact layout keeps the composer visible at 980 x 650, including the largest reading font. Effects switches ambient lighting off/on; hover feedback remains available. Color updates are limited to 8 Hz while active and pause when inactive.

## Local files

`state/terminal_ui.json` remembers host preferences and loaded module paths. `state/terminal-modules/MODULE_ID/` holds each module's data. Scratchpad notes and LogosMind connection settings stay there. The LogosMind backend retains its own conversation database and model/reference files in its project folder.

These state, cache and model paths are ignored by Git. The repository includes source, the SDK, tests, and connector code. It does not distribute personal conversations, notes, credentials or model weights.

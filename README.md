# Logos Terminal GUI

A lightweight desktop host for modular terminals. Load a terminal, switch workspaces, and use the controls supplied by that module. The GUI stays independent of AI models and their environments.

The dark green interface includes hover highlights, subtle animated window/panel lighting, adjustable reading fonts, and an effects toggle. It uses Python/Tk and the standard library, with no third-party runtime packages.

## Run

Use Python 3.11 or newer with Tk available.

On Windows, download or clone this repository and double-click **Start_Terminal_GUI.cmd**. The launcher checks a local virtual environment, the Windows Python launcher, Python on PATH, and an existing Unsloth installation as a fallback.

Or run from the repository folder:

```sh
python terminal_gui.py
```

To check that your Python includes Tk, run `python -m tkinter`. Some Linux distributions provide Tk in a separate system package.

## Included terminals

| Terminal | Purpose | Requirements |
|---|---|---|
| Scratchpad | Save and find local notes | Host Python only |
| LogosMind connector | Connect an existing LogosMind project | Separately installed LogosMind backend and its Python environment |
| SDK example | Test a new module connection with an echo worker | Host Python only; load `terminal_sdk/example/terminal.json` |

Scratchpad is the default workspace. The LogosMind connector is optional; the host runs without LogosMind, model weights, or Bible data.

## Connect LogosMind

1. Select **LogosMind** in the sidebar.
2. Open **Settings > Terminal settings**.
3. Select `logosmind.py` from your existing LogosMind installation. That installation must include `lm_terminal_worker.py` from the updated LogosMind package.
4. Optionally select that installation's `python.exe`. If left blank, the connector tries the project's virtual environment, then the existing Unsloth environment, then the host interpreter.
5. Save, then connect or reconnect the terminal.

The connector launches the backend in its own process and directory. Models, Bible/reference data, training files, and conversations stay in the LogosMind project. They are not part of this repository.

## Load other terminals

Use **Load terminal > Load a module** to select a module's `terminal.json`. Its sidebar entry and action buttons appear immediately. Loading registers the module; Connect or Send starts its process.

Use **Load terminal > Link an existing terminal** for a normal Python script, executable, or Windows batch terminal. This uses a plain-text adapter. Full-screen terminal UIs need a dedicated adapter; this application does not embed other GUI application windows.

Each module can use its own interpreter and dependencies. The host does not install packages into module environments.

## Module contract

- Versioned JSON manifest, with a supplied JSON Schema 2020-12 definition.
- JSON-RPC 2.0 over UTF-8 JSON Lines on stdin/stdout.
- Startup API-version and capability checks before actions execute.
- Stable module/action IDs, matched request IDs, and structured errors.
- Separate processes, per-module data folders, and explicit module settings.

See the [module SDK](terminal_sdk/README.md), [schema](terminal_sdk/terminal.schema.json), [worker template](terminal_sdk/worker_template.py), and [working example](terminal_sdk/example/terminal.json).

Validate a module without executing it:

```sh
python validate_terminal.py path/to/terminal.json
```

Add `--probe` to start its worker, verify the handshake, and stop that owned process.

## Controls and saved state

Enter sends; Shift+Enter adds a line; Ctrl+L focuses input. New/History are enabled when the connected module provides saved conversations. Stop terminates the owned worker process tree; completed saved conversations remain in the backend.

The host remembers module paths, sessions, font size, and effects in ignored `state/` files. Notes and connector configuration use separate module data folders. Ambient lighting pauses while the window is inactive. See the [user guide](docs/USER_GUIDE.md).

## Development

The host and transport tests do not need a model, network service, or LogosMind installation:

```sh
python -m unittest discover -v
```

Optional schema checks:

```sh
python -m pip install -r requirements-dev.txt
python tools/check_schemas.py
```

CI runs the independent tests on Windows and Linux. Layout checks run when Tk and a display are available. Backend AI quality and each new terminal integration need their own evaluation.

## License

This project retains the repository's [GNU GPL v3 license](LICENSE).

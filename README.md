# Logos Terminal GUI

A lightweight desktop host for modular terminals. Load a terminal, switch workspaces, and use the controls supplied by that module. The GUI stays independent of AI models and their environments.

Choose **Logos Classic** (the original design), **Galactic Phosphor**, or **Galactic 2.0** in Settings. All use the same modular workspace layout. Galactic 2.0 adds denser columns, independently changing symbols, smoother falling, soft phosphor halos and fading after-images. The host uses Python/Tk and the standard library, with no third-party runtime packages.

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

## Themes

Open **Settings**, choose a theme, and click **Apply**. Switching preserves loaded modules, running connections, transcripts and drafts. Existing installations default to the original Logos Classic design.

**Theme elements** shows the selected theme's parsed palette, typography, component styles, effects, or flat named tokens. **Export theme** saves a reusable definition; **Import theme** validates and installs another definition. Themes are versioned JSON data. They cannot execute scripts or change the module protocol or workspace layout.

For Galactic 2.0, **Rain settings** adjusts column/row spacing, fall speed, symbol-change rate, brightness, glow, after-images and frame rate. Saving creates a personal custom theme; Apply selects it without modifying the bundled preset. The default targets 24 fps, supports up to 30, and dims the rain behind transcript text for readability. Effects pauses all ambient animation when disabled or when the app is inactive.

To create another theme, export one, change its `id` and `name`, edit its elements, then import it. Bundled definitions live in [themes/](themes/); imported definitions are local settings. See the [theme authoring guide](docs/THEMES.md) and [theme schema](themes/theme.schema.json).

```sh
python tools/theme.py validate themes/galactic-phosphor.theme.json
python tools/theme.py inspect themes/galactic-phosphor.theme.json --group palette
python tools/theme.py inspect themes/galactic-phosphor.theme.json --flat
python tools/theme.py inspect themes/galactic-2.theme.json --group rain
```

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

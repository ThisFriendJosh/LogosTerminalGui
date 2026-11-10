# Beta testing and diagnostics

## Quick tester workflow

1. Pull the latest repository changes and restart the GUI. Open **Settings > Terminal Manager**.
2. Select the terminal you want to test. Check its version and launch/program paths; use **Settings** to correct its configuration.
3. Click **Validate files**, then **Test connection**. A disconnected terminal starts through the normal connection and stays connected. The test sends no chat/tool request. An existing connection is reused, including while it processes a request.
4. Read the check results in the selected-terminal panel. A valid adapter handshake can still report an unavailable or unconfigured backend. Fix the configuration, Reconnect, then test again.
5. Open the workspace and try the actual actions you want to test. Note what you did, what you expected and what happened.
6. Return to Terminal Manager and select **Export report**. Review the preview and save the JSON file to send back with your observations.

The default report is intentionally technical: host/Python/Tk versions, platform/architecture, loaded module/API versions, protocol, connection state, advertised action IDs, manifest SHA-256 fingerprints and check summaries. It does not include full paths, commands/arguments, configuration values, session IDs, conversation text, drafts, raw errors or logs.

If more detail is needed, enable **Include recent diagnostics** in the preview. This includes check details, up to 100 recent log entries per module and the most recent error. Known local paths and common credential patterns are redacted. Arbitrary backend text can contain other private information, so review the actual preview before saving or sharing. The saved report matches the preview. Nothing is uploaded automatically.

## What the check proves

- Manifest parsing enforces the existing module schema/API compatibility rules. Static launch checks find missing working folders, executables, Python entry scripts, unreadable settings and missing configured files.
- JSON-RPC startup checks verify that the worker accepts the API major version and advertises the manifest's declared actions. Optional `metadata.connection_error` or `model_available: false` marks a backend setup issue even when the adapter itself initializes.
- A text terminal only reports that its owned process is running; it cannot provide the JSON-RPC compatibility guarantee.
- No execute request is sent. The check does not measure inference speed, guarantee model output, test tool results, install dependencies or download anything. Normal module startup can load its model or restore/create its normal session.
- A connection check uses the existing 30-second startup compatibility limit. Model response timeouts remain owned by the relevant backend and are separate from this startup limit.

Reconnect waits for the previous owned worker to finish stopping before starting its replacement. Other terminals keep running. The current session ID, draft and host transcript are retained, subject to the backend's normal history refresh. Sidebar order and unloaded IDs persist in `state/terminal_ui.json`. Unload removes no files; reloading the same manifest restores the terminal. Drafts are currently in-memory and do not survive a full application restart.

## Developer checks

```sh
python -m unittest discover -v
python tools/check_schemas.py
```

On a headless Linux machine, also exercise the real Tk manager and layout:

```sh
xvfb-run -a python -m unittest -v tests.test_gui_layout tests.test_terminal_manager
```

Tests cover default report exclusions, optional diagnostic redaction, missing files, setup failures, live-worker reuse, reconnection, independent workers, module order/unload persistence, empty workspaces, compact manager controls and saving the reviewed report. No AI model is needed.

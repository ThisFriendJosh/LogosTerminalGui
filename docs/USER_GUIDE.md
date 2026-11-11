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

**Load terminal > Browse terminal folders** opens the `terminals` directory.
Open the desired terminal's subfolder and select **terminal.json**. The host
checks the manifest and, on connection, verifies the worker's version and
advertised capabilities. Loading adds the sidebar entry; it does not execute
the program. Use the SDK contract for new rich integrations.

To remove a sidebar icon, select it and press **Unload terminal** below the
sidebar, or right-click the icon and choose **Unload from sidebar**. The files,
settings, notes and saved conversations remain in their original folders.
Unloading stops that terminal's owned worker and removes its registration.
Other terminals and their connections continue normally.

To restore it, open **Load terminal**, select it under **Previously unloaded**
and press **Reload selected**. This list is remembered after restarting the
app, including terminals loaded from other folders. You can also browse to its
original `terminal.json`. Connect or send when ready to start it again.

The sidebar is your chosen list of loaded terminals. Placing a new module in
the `terminals` folder does not add an icon automatically. Your current sidebar
is migrated once when upgrading; later launches restore your explicit loaded
list. Load and Unload manage this list; Connect and Disconnect retain their
existing behavior. Unsent text and visual drafts survive unloading and reloading
within the same running app; closing the app clears unsaved drafts.

Load terminal > Link an existing terminal registers a normal redirected-input/output console program, Python script or Windows batch file. Give it a name, program path, optional arguments and working folder. Quote argument paths containing spaces. Full-screen terminal applications and interactive password prompts may need a purpose-built adapter.

Use an explicit interpreter in a module's command array when it has its own environment. Keeping dependencies in that environment prevents the host and modules from changing each other's installed packages.

## Manage and check terminals

Open **Settings > Terminal Manager**. Selecting a row inspects that terminal without changing your active workspace. **Open workspace** switches to it; **Settings** opens that selected module's configuration. The details show module/API versions, launch interpreter or program, working folder, settings file, and configured file paths. For a connector, these include the separately configured backend project and interpreter; an automatic interpreter is resolved by that connector.

- **Validate files** checks the current manifest, API compatibility, launch program, Python entry script and configured files without running code. If a loaded manifest changes, unload it and load the updated definition.
- **Test connection** starts a disconnected module or reuses its existing worker. It verifies the startup handshake and declared actions, sending no chat or tool command. It leaves the terminal connected. A text adapter has no capability handshake; a running text process is reported separately. Backend initialization may load its model or restore its normal session.
- **Reconnect** waits for the old owned worker to stop, then reconnects with the same session. Drafts and the host's visible transcript remain; a backend may refresh its saved history. Reconnect and Unload are disabled during a request or startup.
- **Move up / Move down** changes the sidebar order and remembers it.
- **Unload** stops the worker and removes the entry. It leaves the manifest, settings, saved conversations and notes in place. Use Load terminal > Reload selected, or browse to the same manifest, to restore it. In-memory drafts remain available when reloading during the same app session.
- **Export report** previews and saves diagnostic JSON for your tester to send back. The default excludes conversations, drafts, settings values and raw logs. Optional diagnostic text redacts known paths and common credentials; review it before sharing. Export does not upload the file.

See [Beta testing and diagnostics](TESTING.md) for a short tester workflow and the limits of connection checks.

## Appearance

Settings offers **Logos Classic**, the original design, **Galactic Phosphor**, and **Galactic 2.0**. Choose a theme and Apply; the layout, connected terminals, transcripts and unsent drafts are preserved. Your theme choice is remembered.

Galactic 2.0 uses tighter columns, a separate change timer for every symbol, smoother falling positions, bright soft halos and fading after-images. Its rain is quieter behind the transcript so messages stay legible. **Rain settings** adjusts these elements and the frame rate. Save a personal custom theme, then Apply it from Settings. The shipped presets remain available. Lower frame rate, brightness or glow radius if you want a lighter effect on your computer.

Use **Theme elements** to inspect the selected theme by group or as flat named tokens. **Export theme** creates an editable JSON definition. Give a copy a unique id and name, then use **Import theme** to add it to the menu. See [Theme authoring](THEMES.md) for the format.

Settings also adjusts reading font size from 10 to 18. The compact layout keeps the composer visible at 980 x 650, including the largest reading font. Effects turns animated rain, glow variation and cursor blinking off/on; hover feedback remains available. Classic animates at up to 8 Hz, Galactic Phosphor at up to 12 Hz, and Galactic 2.0 targets 24 fps by default. Ambient animations pause when inactive or minimized. Glow masks are cached and the animated texture has fixed size limits; no fonts, graphics packages or online assets need to be installed.

## Local files

`state/terminal_ui.json` remembers host preferences and loaded module paths. `state/terminal-modules/MODULE_ID/` holds each module's data. Scratchpad notes and LogosMind connection settings stay there. The LogosMind backend retains its own conversation database and model/reference files in its project folder.

These state, cache and model paths are ignored by Git. The repository includes source, the SDK, tests, and connector code. It does not distribute personal conversations, notes, credentials or model weights.

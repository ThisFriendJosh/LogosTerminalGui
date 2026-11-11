# Logos Terminal module contract 1.0.0

The host is independent of LogosMind. A terminal is a manifest plus an adapter process. No terminal code is imported into the GUI, and the adapter can use its own Python environment or a different implementation language.

## Standards and compatibility

- Manifest validation: JSON Schema Draft 2020-12, supplied as `terminal.schema.json`. The host enforces the core contract without installing a schema package.
- Communication: JSON-RPC 2.0 over standard input/output, framed as UTF-8 JSON Lines. One JSON object per line, ending with LF. No HTTP server, localhost port, cloud account or embedding service is required.
- The host and module negotiate `protocolVersion` during `initialize`. An incompatible API major version or unmet `min_host_version` blocks connection with an actionable error.
- `version` identifies the module release; `api_version` identifies the contract. Stable semantic versions use `major.minor.patch`. Breaking contract changes require a new major version; optional additions use a minor version; compatible fixes use a patch version.
- A module declares action IDs in its manifest and advertises capabilities during initialization. The host verifies the declared actions are advertised. Optional controls such as new conversation/history appear enabled only when advertised.
- Module IDs, action IDs and settings keys are stable identifiers, independent of display labels. Keep module IDs unique. Do not rename IDs just to change visible wording.
- Unknown optional fields and notifications may be ignored for forward compatibility. New required behavior must also raise `min_host_version`. Use the `extensions` object for vendor-specific metadata.

This is the Logos Terminal API carried by JSON-RPC, not an MCP server implementation. The transport profile uses named object parameters, string/integer request IDs and one request per frame; JSON-RPC batch arrays and server-to-client requests are not implemented in API 1.0.

## Folder and launch contract

```text
my-terminal/
  terminal.json
  worker.py
```

`command` is an argument array, never a shell expression. Example:

```json
{
  "schema": "logos-terminal/1",
  "id": "my-terminal",
  "name": "My Terminal",
  "description": "What this terminal does",
  "version": "1.0.0",
  "api_version": "1.0.0",
  "min_host_version": "1.0.0",
  "protocol": "jsonrpc",
  "command": ["{python}", "-u", "{module}/worker.py"],
  "cwd": "{module}",
  "actions": [
    {"id": "chat", "label": "Chat", "placeholder": "Type a message…", "button": "Send"}
  ]
}
```

Use an explicit executable path in `command[0]` for an independently managed environment. The host never installs dependencies or changes that environment.

| Placeholder | Meaning |
|---|---|
| `{python}` | Host's console Python executable; a convenience, not a required runtime |
| `{module}` | Absolute folder containing this manifest |
| `{app}` | Absolute host folder |
| `{data}` | Host-managed per-module data folder under `state/terminal-modules/MODULE_ID` |
| `{session}` | Current remembered session ID |

Keep a module's code/data paths relative to `{module}` or `{data}` so loading it from another host folder works. Do not assume the current working directory is the module folder. The optional LogosMind connector selects an independently installed project through local settings and preserves that project's conversation database.

The child receives `LOGOS_TERMINAL_API_VERSION`, `LOGOS_TERMINAL_DATA_DIR`, and `LOGOS_TERMINAL_SDK_DIR`. The optional standard-library Python helper `terminal_protocol.py` is in the SDK directory. An adapter may import it explicitly or implement the wire format itself.

## Wire examples

Host request:

```json
{"jsonrpc":"2.0","id":"init-1","method":"initialize","params":{"protocolVersion":"1.0.0","clientInfo":{"name":"Logos Terminal","version":"1.0.0"}}}
```

Module response:

```json
{"jsonrpc":"2.0","id":"init-1","result":{"protocolVersion":"1.0.0","serverInfo":{"name":"My Terminal","version":"1.0.0"},"capabilities":{"actions":["chat"]},"metadata":{"model":"Local model","session":"session-id"}}}
```

Execution request and its single final response:

```json
{"jsonrpc":"2.0","id":"request-1","method":"terminal/execute","params":{"action":"chat","input":{"text":"Hello"}}}
{"jsonrpc":"2.0","id":"request-1","result":{"kind":"assistant","text":"Hello."}}
```

Progress notification (no top-level ID, no response expected):

```json
{"jsonrpc":"2.0","method":"terminal/status","params":{"id":"request-1","text":"Thinking locally…"}}
```

Failure response:

```json
{"jsonrpc":"2.0","id":"request-1","error":{"code":-32602,"message":"A verse reference is required"}}
```

Every request ID receives exactly one final response. Keep IDs unchanged. Never send both `result` and `error`. Never answer a notification. Send diagnostic output to stderr, not stdout. Each UTF-8 frame is limited to 2,000,000 bytes. Non-JSON numbers such as NaN/Infinity are rejected.

| Error code | Meaning |
|---|---|
| -32700 | Invalid JSON |
| -32600 | Invalid request envelope |
| -32601 | Unknown method |
| -32602 | Invalid parameters or unsupported action |
| -32001 | Incompatible terminal API |
| -32002 | Execution attempted before initialization |
| -32000 | Module/runtime failure |

## UI results and optional capabilities

| Result kind | Fields | Host behavior |
|---|---|---|
| `assistant` | `text`, optional `audit` | Render model reply |
| `source` | `text` | Render source/tool output |
| `history` | `messages` with `role`/`content`, `session` | Replace displayed conversation and remember session |
| `session_list` | `items` with `id`, `label`, optional `date` | Open saved-conversation chooser; selection executes `resume` |
| `module_list` | `items` with `id`, `label` | Open reference chooser; selection executes `modules` |
| `done` | Optional `text` | Mark request complete |

Notifications are `terminal/status` (`text`), `terminal/log` (`text`), `terminal/stream` (`text`), and `terminal/history` (`messages`, `session`). History is sent after initialization or may be buffered by the host until compatibility is verified. Unknown optional notifications are ignored.

Host 1.3.0 adds Terminal Manager startup checks. The host reuses the normal `initialize` exchange and sends no execute request for a connection test. In initialization `metadata`, an optional `connection_error` string describes setup that prevents the backend being used; `model_available: false` also marks an unavailable backend. Keep this diagnostic free of secrets and user messages. These are optional metadata additions within API 1.0.0; modules do not need a new action or a protocol version change. A successful handshake alone does not certify inference or tool behavior.

Advertise `new`, `sessions` and `resume` together when providing saved conversations. For `resume`, the host supplies `input.session`. `new` creates a new session while preserving earlier sessions. Advertise `modules` when using the reference chooser. `metadata.translations` supplies choices to manifest actions with `translations: true`; those requests receive `input.translation`.

## Optional settings

`settings.file` names a JSON configuration file, with `{app}` and `{module}` path expansion. `settings.fields` describes `key`, `label`, and `type` (`string`, `file`, `integer`, `number`), with optional numeric `min`/`max`. The host preserves unrelated settings keys, validates numeric bounds and file existence, and applies saved values on reconnection. Secrets and authentication flows are not part of this generic form.

## Existing terminal programs

### Optional calculator workspace (host 1.5.0)

The bundled calculator modules declare a data-only UI extension:
`"extensions": {"workspace": {"type": "calculator", "engine": "cryptocalc"}}`
(or `"statcalc"`). Their manifests require host 1.5.0. The host renders its own
native Tk controls; it never imports executable module code into the GUI.
CryptoCalc's `operations.json` supplies the operation/parameter catalogue.
Calculation remains in the separately launched adapter and uses the existing
actions. Text actions remain available through the Terminal view.

Calculator result payloads may include `audit.calculator` with `type` equal to
the engine ID. CryptoCalc includes `output`, `hex`, `bytes`, `isText` and bounded
`steps`; StatCalc2 includes `analysis` with the original `dataset`, `level`,
`reports` and `pairs`. This is optional result metadata within API 1.0.0;
ordinary text clients can ignore it. The adapter limits the serialized result
to 1.5 MB, below the transport frame limit. Drafts, selected views and results
belong to each in-memory host workspace and survive view/theme changes.

### Linking console programs

The GUI's **Load terminal → Link an existing terminal** creates a manifest using `protocol: "text"`. It supports ordinary redirected stdin/stdout console programs and Python scripts. It is not a full PTY/ConPTY emulator; full-screen TUI programs, cursor addressing and password prompts may need a dedicated adapter. GUI executables are not embedded as child application windows. Rich controls and capability checks require the JSON-RPC adapter.

## Validate before loading

```powershell
python validate_terminal.py "C:/path/to/terminal.json"
python validate_terminal.py "C:/path/to/terminal.json" --probe
python -m unittest -v test_terminal.py
```

Normal validation does not run the module. `--probe` explicitly starts its worker, verifies compatibility/capabilities, then stops that owned worker. A crash, malformed output or incompatible module does not close the host or another module. Stop/disconnect terminates only that worker's process tree. Terminal code runs with the local user's access; process separation is not a security sandbox.

The host saves loaded manifest paths, selected module, theme and session IDs in `state/terminal_ui.json`. It leaves modules and saved conversations in place. Module import only registers the manifest; connection/send launches it.

## Primary specifications

- [JSON-RPC 2.0](https://www.jsonrpc.org/specification)
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/)
- [Semantic Versioning](https://semver.org/)

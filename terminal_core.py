"""Small module registry and subprocess transport, independent of any AI runtime."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import codecs
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import uuid

from terminal_protocol import API_VERSION, HOST_VERSION, MAX_LINE_BYTES, ProtocolError, parse_server_message, strict_json, validate_payload, version

PROTOCOL = "logos-terminal/1"
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def console_python():
    path = Path(sys.executable)
    candidate = path.with_name("python.exe") if path.name.lower() == "pythonw.exe" else path
    return str(candidate if candidate.exists() else path)


@dataclass
class TerminalModule:
    path: Path
    id: str
    name: str
    description: str
    command: list[str]
    cwd: str
    protocol: str
    actions: list[dict]
    settings: dict
    version: str = "1.0.0"
    api_version: str = API_VERSION
    min_host_version: str = "1.0.0"
    extensions: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        if path.stat().st_size > 128_000:
            raise ValueError("Terminal module manifest exceeds 128 KB")
        data = strict_json(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError("The module manifest must be a JSON object")
        if not isinstance(data.get("extensions", {}), dict):
            raise ValueError("Module extensions must be an object")
        required = {"schema", "id", "name", "version", "api_version", "min_host_version", "protocol", "command", "actions"}
        if required - set(data):
            raise ValueError("Missing manifest fields: " + ", ".join(sorted(required - set(data))))
        if data.get("schema") != PROTOCOL:
            raise ValueError("Choose a logos-terminal/1 module manifest")
        version(data.get("version", "0.0.0"))
        if version(data.get("api_version", "0.0.0"))[0] != version(API_VERSION)[0]:
            raise ValueError("This terminal requires a different API major version")
        if version(data.get("min_host_version", "1.0.0")) > version(HOST_VERSION):
            raise ValueError("Update the terminal host before loading this module")
        identifier = data.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", identifier):
            raise ValueError("Module id must use lowercase letters, numbers, dots, underscores or hyphens")
        command = data.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or "\x00" in x for x in command):
            raise ValueError("Module command must be a nonempty array of program and arguments")
        protocol = data.get("protocol", "jsonrpc")
        if protocol not in {"jsonrpc", "text"}:
            raise ValueError("Module protocol must be jsonrpc or text")
        actions = data.get("actions", [{"id": "chat", "label": "Chat", "placeholder": "Type a message…"}])
        if not isinstance(actions, list) or not actions or len(actions) > 12:
            raise ValueError("A module needs between one and twelve actions")
        ids = []
        for action in actions:
            if not isinstance(action, dict) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", action.get("id", "")):
                raise ValueError("Every action needs a valid id")
            if not isinstance(action.get("label"), str) or not action["label"].strip() or len(action["label"]) > 40:
                raise ValueError("Every action needs a readable label")
            for flag in ("allow_empty", "translations"):
                if flag in action and not isinstance(action[flag], bool):
                    raise ValueError("Action " + flag + " must be true or false")
            for key, limit in (("placeholder", 300), ("button", 24)):
                if key in action and (not isinstance(action[key], str) or len(action[key]) > limit):
                    raise ValueError("Invalid action field: " + key)
            ids.append(action["id"])
        if len(set(ids)) != len(ids):
            raise ValueError("Module action ids must be unique")
        name = data.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ValueError("Give the terminal a name of at most 64 characters")
        settings = data.get("settings", {})
        if not isinstance(settings, dict):
            raise ValueError("Module settings must be an object")
        if settings:
            if not isinstance(settings.get("file"), str) or not settings["file"]:
                raise ValueError("Module settings need a JSON file path")
            fields = settings.get("fields", [])
            if not isinstance(fields, list) or len(fields) > 12:
                raise ValueError("At most 12 settings fields are supported")
            keys = set()
            for field in fields:
                if not isinstance(field, dict) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", field.get("key", "")) or not isinstance(field.get("label"), str) or field.get("type") not in {"file", "string", "integer", "number"}:
                    raise ValueError("Settings fields require key, label and supported type")
                if field["key"] in keys:
                    raise ValueError("Settings field keys must be unique")
                keys.add(field["key"])
                for bound in ("min", "max"):
                    if bound in field and (isinstance(field[bound], bool) or not isinstance(field[bound], (int, float))):
                        raise ValueError("Numeric setting bounds must be numbers")
        return cls(path, identifier, name, str(data.get("description", ""))[:300], command,
                   str(data.get("cwd", "{module}")), protocol, actions, settings,
                   data["version"], data["api_version"], data["min_host_version"], data.get("extensions", {}))

    def settings_path(self, app_root):
        if not self.settings:
            return None
        target = self.settings["file"].replace("{app}", str(Path(app_root).resolve())).replace("{module}", str(self.path.parent))
        path = Path(os.path.expandvars(target))
        return path if path.is_absolute() else self.path.parent / path

    def launch(self, app_root, session):
        values = {"{python}": console_python(), "{app}": str(Path(app_root).resolve()),
                  "{module}": str(self.path.parent), "{session}": session,
                  "{data}": str(Path(app_root).resolve() / "state/terminal-modules" / self.id)}
        def expand(value):
            for key, replacement in values.items():
                value = value.replace(key, replacement)
            return os.path.expandvars(value)
        command = [expand(x) for x in self.command]
        cwd = Path(expand(self.cwd))
        if not cwd.is_absolute():
            cwd = self.path.parent / cwd
        cwd = cwd.resolve()
        if not cwd.is_dir():
            raise ValueError("Terminal working folder does not exist: " + str(cwd))
        if Path(command[0]).suffix.lower() in {".bat", ".cmd"}:
            # Batch scripts require cmd.exe. Reject shell control characters rather
            # than interpreting a manifest field as a command expression.
            if any(re.search(r'[&|<>^%!\r\n"]', arg) for arg in command):
                raise ValueError("Batch paths and arguments cannot contain shell control characters; use an executable or Python adapter instead")
            quoted = '"' + '" "'.join(command) + '"'
            if os.name != "nt":
                raise ValueError("Batch adapters require Windows")
            command = '"' + os.environ.get("COMSPEC", "cmd.exe") + '" /d /s /c "' + quoted + '"'
        return command, cwd


def discover(root, extra_paths=(), include_bundled=True):
    modules, errors = {}, []
    paths = [*(sorted((Path(root) / "terminals").glob("*/terminal.json")) if include_bundled else []),
             *(Path(p) for p in extra_paths)]
    for path in paths:
        try:
            module = TerminalModule.load(path)
            if module.id in modules and modules[module.id].path != module.path:
                raise ValueError("Another loaded module already uses id " + module.id)
            modules[module.id] = module
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"{path.name}: {exc}")
    return modules, errors


def read_preferences(path):
    defaults = {"effects": True, "font_size": 12, "modules": [], "sessions": {}, "selected": "scratchpad", "theme": "logos-classic",
                "module_order": [], "hidden_modules": [], "unloaded_modules": [], "module_registry_initialized": False}
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return defaults
        if isinstance(saved.get("effects"), bool):
            defaults["effects"] = saved["effects"]
        try:
            defaults["font_size"] = max(10, min(18, int(saved.get("font_size", 12))))
        except (ValueError, TypeError):
            pass
        if isinstance(saved.get("modules"), list):
            defaults["modules"] = [p for p in saved["modules"] if isinstance(p, str)][:128]
        if isinstance(saved.get("unloaded_modules"), list):
            defaults["unloaded_modules"] = list(dict.fromkeys(p for p in saved["unloaded_modules"]
                if isinstance(p, str) and p and "\x00" not in p))[:128]
        if isinstance(saved.get("module_registry_initialized"), bool):
            defaults["module_registry_initialized"] = saved["module_registry_initialized"]
        for key in ("module_order", "hidden_modules"):
            if isinstance(saved.get(key), list):
                defaults[key] = list(dict.fromkeys(p for p in saved[key] if isinstance(p, str) and re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", p)))[:256]
        if isinstance(saved.get("sessions"), dict):
            defaults["sessions"] = {k: v for k, v in saved["sessions"].items() if isinstance(k, str) and isinstance(v, str) and 0 < len(v) <= 100}
        if isinstance(saved.get("selected"), str):
            defaults["selected"] = saved["selected"]
        if isinstance(saved.get("theme"), str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", saved["theme"]):
            defaults["theme"] = saved["theme"]
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def write_preferences(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


class TerminalProcess:
    def __init__(self, module, root, session, events):
        self.module, self.root, self.session, self.events = module, Path(root), session, events
        self.process = None
        self.generation = uuid.uuid4().hex
        self.log = []
        self.stopping = False
        self.initialize_id = "initialize-" + uuid.uuid4().hex
        self.initialized = False
        self.metadata, self.capabilities, self.server_info = {}, [], {}
        self.before_initialize = []
        self.pending_ids = set()
        self.lifecycle_lock = threading.Lock()

    def emit(self, event):
        self.events.put((self.module.id, self.generation, event))

    def start(self):
        with self.lifecycle_lock:
            self._start()

    def _start(self):
        if self.stopping:
            return
        command, cwd = self.module.launch(self.root, self.session)
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        env = os.environ.copy()
        data_directory = self.root / "state/terminal-modules" / self.module.id
        data_directory.mkdir(parents=True, exist_ok=True)
        env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", LOGOS_TERMINAL_API_VERSION=API_VERSION,
                   LOGOS_TERMINAL_SDK_DIR=str(self.root.resolve()), LOGOS_TERMINAL_DATA_DIR=str(data_directory.resolve()))
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, encoding="utf-8", errors="replace", bufsize=1, **options)
        threading.Thread(target=self._stdout, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()
        threading.Thread(target=self._wait, daemon=True).start()
        if self.module.protocol == "text":
            self.emit({"event": "ready", "text": "Terminal process started", "session": self.session})
        else:
            self._write({"jsonrpc": "2.0", "id": self.initialize_id, "method": "initialize", "params": {
                "protocolVersion": API_VERSION, "clientInfo": {"name": "Logos Terminal", "version": HOST_VERSION}}})

    def _stdout(self):
        try:
            self._read_stdout()
        finally:
            self.process.stdout.close()

    def _read_stdout(self):
        if self.module.protocol == "text":
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            while chunk := os.read(self.process.stdout.fileno(), 4096):
                self.emit({"event": "stream", "text": decoder.decode(chunk)})
            return
        while line := self.process.stdout.readline(MAX_LINE_BYTES + 1):
            try:
                if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                    raise ValueError("Module output line exceeds 2 MB")
                value = parse_server_message(strict_json(line))
                if value.get("id") == self.initialize_id:
                    if "error" in value:
                        raise ValueError(value["error"]["message"])
                    result = value.get("result", {})
                    if version(result.get("protocolVersion", "0.0.0"))[0] != version(API_VERSION)[0]:
                        raise ValueError("Module and host API versions are incompatible")
                    supported = result.get("capabilities", {}).get("actions", [])
                    if not isinstance(supported, list) or not all(isinstance(x, str) for x in supported):
                        raise ValueError("Module capabilities must list action identifiers")
                    missing = {a["id"] for a in self.module.actions} - set(supported)
                    if missing:
                        raise ValueError("Module did not advertise its declared actions: " + ", ".join(sorted(missing)))
                    self.metadata = validate_payload(result.get("metadata", {}))
                    self.capabilities = supported
                    self.server_info = result.get("serverInfo", {}) if isinstance(result.get("serverInfo"), dict) else {}
                    self.initialized = True
                    self.emit({**self.metadata, "event": "ready", "capabilities": supported})
                    for event in self.before_initialize:
                        self.emit(event)
                    self.before_initialize.clear()
                elif "method" in value:
                    name = value["method"].removeprefix("terminal/")
                    event = {**validate_payload(value.get("params", {}), history=name == "history"), "event": name}
                    if name not in {"history", "status", "log", "stream"}:
                        continue  # Unknown optional notifications are forward-compatible.
                    if self.initialized:
                        self.emit(event)
                    elif len(self.before_initialize) < 100:
                        self.before_initialize.append(event)
                else:
                    identifier = value.get("id")
                    if identifier is None and "error" in value and not self.initialized:
                        raise ValueError(value["error"]["message"])
                    if identifier not in self.pending_ids:
                        raise ValueError("Module sent an unknown or duplicate response id")
                    self.pending_ids.remove(identifier)
                    if "error" in value:
                        self.emit({"event": "error", "id": identifier, "text": value["error"]["message"], "code": value["error"]["code"]})
                    else:
                        result = value["result"]
                        if not isinstance(result, dict):
                            raise ValueError("Terminal execution results must be objects")
                        validate_payload(result)
                        kind = result.get("kind")
                        self.emit({**result, "event": "history" if kind == "history" else "result", "id": identifier})
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                self.emit({"event": "error", "text": "Terminal protocol error: " + str(exc)})
                self.emit({"event": "log", "text": ANSI.sub("", line.rstrip())[:2000]})
                self.stop()
                return

    def _stderr(self):
        try:
            for line in self.process.stderr:
                self.emit({"event": "log", "text": ANSI.sub("", line.rstrip())[:4000]})
        finally:
            self.process.stderr.close()

    def _wait(self):
        code = self.process.wait()
        self.process.stdin.close()
        self.emit({"event": "exit", "code": code, "stopped": self.stopping})

    def send(self, action, text="", **payload):
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Connect the terminal first")
        request_id = uuid.uuid4().hex
        if self.module.protocol == "text":
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
        else:
            if not self.initialized:
                raise RuntimeError("Wait for the terminal compatibility check to finish")
            self.pending_ids.add(request_id)
            self._write({"jsonrpc": "2.0", "id": request_id, "method": "terminal/execute", "params": {"action": action, "input": {"text": text, **payload}}})
        return request_id

    def _write(self, value):
        line = json.dumps(value, ensure_ascii=False) + "\n"
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise ValueError("Input exceeds the 2 MB frame limit")
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def stop(self):
        self.stopping = True
        with self.lifecycle_lock:
            process = self.process
        if not process or process.poll() is not None:
            return
        # EOF lets an idle adapter and its backend close in order. This also
        # releases working directories before reconnection or test cleanup.
        try:
            process.stdin.close()
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=0.5)
            return
        except subprocess.TimeoutExpired:
            pass
        if os.name == "nt":
            # Only this owned worker PID and its descendants are stopped.
            try:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=12)
            except (OSError, subprocess.SubprocessError):
                pass
        else:
            import signal
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # The worker may exit naturally between wait() and killpg().
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)

"""Read-only module checks and reviewable, allowlisted beta-test reports.

Connection checks use the host's normal connection, never a second worker or an
execute request. Detailed backend output is included only when selected by the
user; default reports contain no free-form backend messages or settings values.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import time

from terminal_core import TerminalModule
from terminal_protocol import API_VERSION, HOST_VERSION

REPORT_SCHEMA = "logos-terminal-diagnostics/1"


def check(code, status, summary, detail=""):
    return {"code": code, "status": status, "summary": summary, "detail": str(detail)[:6000]}


def read_settings(module, root):
    path = module.settings_path(root)
    if path is None or not path.exists():
        return {}
    if path.stat().st_size > 128_000:
        raise ValueError("Terminal settings exceed 128 KB")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Terminal settings must be a JSON object")
    return data


def executable_for(command, cwd):
    if isinstance(command, str):
        return shutil.which(os.environ.get("COMSPEC", "cmd.exe"))
    program = command[0]
    path = Path(program)
    if path.is_absolute() or path.parent != Path(".") or program.startswith("."):
        path = path if path.is_absolute() else cwd/path
        return str(path.resolve()) if path.is_file() else None
    return shutil.which(program)


def preflight(module, root):
    """Validate current files and launch paths without executing module code."""
    checks = []
    try:
        fresh = TerminalModule.load(module.path)
        if fresh != module:
            checks.append(check("manifest_changed", "fail", "The manifest changed after loading. Unload and load it again.", module.path))
        else:
            checks.append(check("manifest", "pass", "Manifest and API versions are valid.", module.path))
    except (OSError, ValueError, TypeError) as exc:
        checks.append(check("manifest", "fail", "The manifest needs attention.", exc))
    try:
        command, cwd = module.launch(root, "connection-check")
        executable = executable_for(command, cwd)
        checks.append(check("working_folder", "pass", "Working folder exists.", cwd))
        checks.append(check("executable", "pass" if executable else "fail",
                            "Launch program was found." if executable else "Launch program was not found.",
                            executable or ("Windows command processor" if isinstance(command, str) else command[0])))
        if isinstance(command, list) and executable and Path(executable).name.lower().startswith(("python", "pypy")):
            arguments = iter(command[1:])
            for arg in arguments:
                if arg in {"-m", "-c", "-", "-V", "--version", "-h", "--help"}:
                    break
                if arg in {"-W", "-X", "--check-hash-based-pycs"}:
                    next(arguments, None)
                    continue
                if arg.startswith("-"):
                    continue
                path = Path(arg)
                path = path if path.is_absolute() else cwd/path
                checks.append(check("entry_script", "pass" if path.is_file() else "fail",
                                    "Python entry script exists." if path.is_file() else "Python entry script was not found.", path))
                break
    except (OSError, ValueError, TypeError) as exc:
        checks.append(check("launch", "fail", "Launch configuration needs attention.", exc))
    try:
        values = read_settings(module, root)
        for field in module.settings.get("fields", []):
            value = values.get(field["key"])
            if field["type"] == "file" and value:
                valid = isinstance(value, str) and Path(os.path.expandvars(value)).expanduser().is_file()
                checks.append(check("setting_file:"+field["key"], "pass" if valid else "fail",
                                    "Configured file exists." if valid else "A configured file was not found.", field["label"]+": "+str(value)))
        checks.append(check("settings", "pass", "Settings are readable; module defaults apply to blank fields."))
    except (OSError, ValueError, TypeError) as exc:
        checks.append(check("settings", "fail", "Settings need attention.", exc))
    return checks


def finish_connection_check(record, module, process, state):
    """Observe startup metadata only; capability checks are enforced by transport."""
    if not process or not process.process or process.process.poll() is not None:
        record["checks"].append(check("connection", "fail", "The module did not stay connected.", state.get("last_error", "Check Logs for startup details.")))
    elif module.protocol == "text":
        record["checks"].append(check("connection", "info", "Text process is running; it has no API handshake."))
    else:
        record["checks"].append(check("handshake", "pass", "API handshake and declared capabilities were verified."))
        metadata = process.metadata
        if metadata.get("connection_error") or metadata.get("model_available") is False:
            record["checks"].append(check("backend", "fail", "The adapter connected, but its backend needs attention.",
                                         metadata.get("connection_error", "The module reported that its model is unavailable.")))
        else:
            record["checks"].append(check("backend", "info", "Startup completed. Inference and individual tools were not exercised."))
    record["status"] = "failed" if any(c["status"] == "fail" for c in record["checks"]) else "running" if module.protocol == "text" else "passed"
    record["elapsed_seconds"] = round(time.monotonic()-record["started"], 2)


def local_details(module, root, process, state, record=None):
    """Local-only detail panel; exported reports use a separate allowlist."""
    try:
        command, cwd = module.launch(root, "connection-check")
        program = executable_for(command, cwd) or (command[0] if isinstance(command, list) else "Windows batch adapter")
    except (OSError, ValueError, TypeError) as exc:
        program, cwd = str(exc), "Unavailable"
    lines = [f"ID: {module.id}    Module: {module.version}    API: {module.api_version}",
             f"Status: {state.get('status', 'Disconnected')}    Protocol: {module.protocol}",
             f"Manifest: {module.path}", f"Launch interpreter / program: {program}", f"Working folder: {cwd}"]
    if module.settings:
        lines.append(f"Settings: {module.settings_path(root)}")
        try:
            values = read_settings(module, root)
            lines.extend(field["label"]+": "+str(values.get(field["key"], "(automatic / default)"))
                         for field in module.settings.get("fields", []) if field["type"] == "file")
        except (OSError, ValueError, TypeError) as exc:
            lines.append("Settings: "+str(exc))
    if process and process.process and process.process.poll() is None:
        lines.append(f"Worker PID: {process.process.pid}")
        if process.server_info:
            lines.append("Worker: "+str(process.server_info.get("name", ""))+" "+str(process.server_info.get("version", "")))
    if state.get("capabilities"):
        lines.append("Capabilities: "+", ".join(state["capabilities"]))
    if record:
        lines.append("\nConnection check: "+record["status"].upper())
        for item in record["checks"]:
            lines.append(f"[{item['status'].upper()}] {item['summary']}"+("\n  "+item["detail"] if item.get("detail") else ""))
    return "\n".join(lines)


def redact(text, roots=(), secrets=()):
    text = str(text)
    for value in sorted((str(v) for v in secrets if v and len(str(v)) >= 4), key=len, reverse=True):
        text = text.replace(value, "[redacted]")
    for path, label in sorted(roots, key=lambda item: len(str(item[0])), reverse=True):
        for spelling in {str(path), str(path).replace("\\", "/")}:
            text = re.sub(re.escape(spelling), lambda _: label, text, flags=re.I if os.name == "nt" else 0)
    text = re.sub(r"(?i)\b(Bearer\s+)\S+", r"\1[redacted]", text)
    text = re.sub(r"(?i)([\"']?(?:api[_-]?key|access[_-]?token|token|password|secret|authorization)[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)", r"\1[redacted]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}", "[redacted]", text)
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@", r"\1[redacted]@", text)
    text = re.sub(r"(?i)\b[A-Z]:[\\/][^\s\"'<>]*", "[path]", text)
    text = re.sub(r"(?<![:\w])/(?:home|Users|tmp|var|opt|mnt|media)/[^\s\"'<>]*", "[path]", text)
    return text[:6000]


def build_report(modules, root, processes, states, records, *, selected=None, include_details=False, tk_version=""):
    """Allowlist default fields; never serialize commands, settings or workspaces."""
    root = Path(root).resolve()
    roots = [(root, "$HOST"), (Path.home(), "$HOME")]
    secrets = []
    for module in modules.values():
        roots.append((module.path.parent, "$MODULE:"+module.id))
        try:
            values = read_settings(module, root)
            secrets.extend(v for key, v in values.items() if isinstance(v, str) and re.search(r"token|secret|password|key|credential", key, re.I))
            for field in module.settings.get("fields", []):
                value = values.get(field["key"])
                if field["type"] == "file" and isinstance(value, str) and value:
                    parent = Path(value).expanduser().resolve().parent
                    if parent != Path(parent.anchor):
                        roots.append((parent, "$CONFIGURED_FOLDER"))
        except (OSError, ValueError, TypeError):
            pass
    items = []
    for identifier, module in modules.items():
        state, record = states.get(identifier, {}), records.get(identifier)
        process = processes.get(identifier)
        running = bool(process and process.process and process.process.poll() is None)
        metadata = process.metadata if process else {}
        setup_required = bool(metadata.get("connection_error") or metadata.get("model_available") is False)
        worker_version = process.server_info.get("version") if process else None
        if not isinstance(worker_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", worker_version):
            worker_version = None
        try:
            fingerprint = hashlib.sha256(module.path.read_bytes()).hexdigest()
        except OSError:
            fingerprint = None
        capabilities = state.get("capabilities", [])
        item = {"id": module.id, "version": module.version, "api_version": module.api_version,
                "min_host_version": module.min_host_version, "protocol": module.protocol, "manifest_sha256": fingerprint,
                "connection": "setup_required" if running and setup_required else "busy" if running and state.get("busy") else "ready" if running and state.get("ready") else "starting" if running else "disconnected",
                "worker_version": worker_version,
                "model_available": metadata.get("model_available") if type(metadata.get("model_available")) is bool else None,
                "capabilities": [x for x in capabilities if isinstance(x, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", x)],
                "check": {"status": record["status"], "elapsed_seconds": record.get("elapsed_seconds"),
                          "checks": [{k: c[k] for k in ("code", "status", "summary")} for c in record["checks"]]} if record else {"status": "not_run"}}
        if include_details:
            item["diagnostic_details"] = [redact(line, roots, secrets) for line in
                ([c.get("detail", "") for c in record["checks"] if c.get("detail")] if record else []) + state.get("logs", [])[-100:] +
                ([state["last_error"]] if state.get("last_error") else [])]
        items.append(item)
    return {"schema": REPORT_SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
            "host": {"version": HOST_VERSION, "module_api": API_VERSION, "python": platform.python_version(),
                     "platform": sys.platform, "architecture": platform.machine(), "tk": str(tk_version)},
            "selected_module": selected, "includes_diagnostic_details": bool(include_details), "modules": items}


def write_report(path, report):
    """Write atomically to the destination selected in the export dialog."""
    path = Path(path)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    os.replace(temporary, path)

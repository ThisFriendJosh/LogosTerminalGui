"""Connect an independently installed LogosMind project to the terminal host.

This bridge imports no model packages and never copies project data. Its
configuration belongs to the host's ignored, per-module state directory.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, os.environ["LOGOS_TERMINAL_SDK_DIR"])
from terminal_protocol import Channel

ACTIONS = ["chat", "bible", "search", "lexicon", "modules", "sessions", "new", "resume"]


def interpreter_for(project, configured=None):
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ValueError("Choose an existing LogosMind Python interpreter in Terminal settings")
        return path
    candidates = [project / ".venv/Scripts/python.exe", project / ".venv/bin/python"]
    try:
        candidates.append(Path.home() / ".unsloth/studio/unsloth_studio/Scripts/python.exe")
    except RuntimeError:
        pass
    return next((p for p in candidates if p.is_file()), Path(sys.executable))


def command_for(config, session):
    if not isinstance(config, dict):
        raise ValueError("LogosMind connection settings must be a JSON object")
    selected = config.get("project_file", "")
    if not isinstance(selected, str) or not selected.strip():
        raise ValueError("Select the existing LogosMind logosmind.py file in Settings > Terminal settings, then reconnect")
    project_file = Path(selected).expanduser().resolve()
    if not project_file.is_file() or project_file.name != "logosmind.py":
        raise ValueError("Choose the logosmind.py file from your existing LogosMind project")
    project = project_file.parent
    worker = project / "lm_terminal_worker.py"
    if not worker.is_file():
        raise ValueError("This LogosMind installation needs the lm_terminal_worker.py adapter from the updated LogosMind package")
    executable = interpreter_for(project, config.get("python"))
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    if not executable.is_file():
        raise ValueError("Choose the console Python executable used by your LogosMind installation")
    return [str(executable), "-u", str(worker), "--project", str(project), "--session", session], project


def configuration_notice(message):
    channel = Channel()
    channel.emit("ready", model="LogosMind - connection needs setup", model_available=False)
    for line in sys.stdin:
        identifier = None
        try:
            accepted = channel.accept(line, ACTIONS, "LogosMind connector", "1.0.0")
            if accepted is not None:
                identifier, _, _ = accepted
                channel.error(identifier, message, -32000)
        except Exception as exc:
            channel.error(identifier if identifier is not None else channel.last_id, str(exc), getattr(exc, "code", -32000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
        command, project = command_for(config, args.session)
    except (OSError, ValueError, TypeError) as exc:
        configuration_notice(str(exc))
        return 0
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    # Inherit the protocol streams unchanged; the host owns this entire process tree.
    child = subprocess.Popen(command, cwd=project, stdin=sys.stdin, stdout=sys.stdout,
                             stderr=sys.stderr, creationflags=flags)
    return child.wait()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

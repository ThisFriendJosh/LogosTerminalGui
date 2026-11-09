"""Validate a module without running it; optionally probe its startup handshake."""
import argparse
import json
from pathlib import Path
import queue
import time

from terminal_core import TerminalModule, TerminalProcess


def validate(path, app_root, probe=False):
    module = TerminalModule.load(path)
    command, cwd = module.launch(app_root, "validation-session")
    result = {"status": "manifest_valid", "id": module.id, "name": module.name,
              "protocol": module.protocol, "actions": [x["id"] for x in module.actions]}
    if probe:
        if module.protocol == "text":
            raise ValueError("A text adapter has no capability handshake; launch it explicitly in the GUI")
        events = queue.Queue()
        process = TerminalProcess(module, app_root, "validation-session", events)
        try:
            process.start()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                _, _, event = events.get(timeout=max(.1, deadline-time.monotonic()))
                if event["event"] == "ready":
                    result.update(status="handshake_verified", capabilities=event.get("capabilities", []))
                    return result
                if event["event"] in {"error", "exit"}:
                    raise ValueError(event.get("text", "Module exited before initialization"))
            raise ValueError("Module handshake exceeded 30 seconds")
        except queue.Empty as exc:
            raise ValueError("Module handshake exceeded 30 seconds") from exc
        finally:
            process.stop()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--probe", action="store_true", help="Start the module, verify initialization, then stop the owned process")
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.manifest, Path(__file__).resolve().parent, args.probe), indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, "Terminal validation failed: " + str(exc) + "\n")

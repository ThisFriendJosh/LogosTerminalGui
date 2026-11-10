"""Local calculator modules: reuse shipped engines in an isolated Node process."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import webbrowser

sys.path.insert(0, os.environ.get("LOGOS_TERMINAL_SDK_DIR", str(Path(__file__).resolve().parents[2])))
from terminal_protocol import Channel, MAX_LINE_BYTES, ProtocolError


def find_node():
    found = shutil.which("node")
    if found:
        return found
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(key)
        if base:
            candidate = Path(base) / ("Programs/nodejs/node.exe" if key == "LOCALAPPDATA" else "nodejs/node.exe")
            if candidate.is_file():
                return str(candidate)
    return None


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, type=Path)
    module = parser.parse_args().module.resolve()
    manifest = json.loads((module / "terminal.json").read_text(encoding="utf-8"))
    actions = [entry["id"] for entry in manifest["actions"]]
    node = find_node()
    channel = Channel()
    metadata = {"model": "Local calculator", "text": "Calculations run on this computer."}
    if not node:
        metadata["connection_error"] = "Install Node.js 22 or newer, then reconnect this calculator. No npm packages are needed."
    else:
        try:
            version = subprocess.run([node, "--version"], capture_output=True, encoding="utf-8", timeout=5,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if version.returncode or int(version.stdout.strip().lstrip("v").split(".")[0]) < 22:
                raise ValueError("Unsupported Node version")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            metadata["connection_error"] = "Node.js 22 or newer is required. Update Node.js and reconnect this calculator."
    channel.emit("ready", **metadata)
    for line in sys.stdin:
        request_id = None
        try:
            if len(line.encode("utf-8")) > MAX_LINE_BYTES:
                raise ProtocolError("Request exceeds the 2 MB frame limit", -32600)
            accepted = channel.accept(line, actions, manifest["name"], manifest["version"])
            if accepted is None:
                continue
            request_id, action, payload = accepted
            text = payload.get("text", "")
            if not isinstance(text, str):
                raise ValueError("Input must be text")
            if len(text.encode("utf-8")) > 250_000:
                raise ValueError("Paste up to 250 KB here. Use Open full calculator for larger files.")
            if action == "open":
                if not webbrowser.open((module / "app.html").as_uri()):
                    raise RuntimeError("The browser could not open the calculator. Open app.html from this module folder.")
                result = "Opened the full calculator. Calculations, charts and exports work locally."
            elif action == "help":
                result = (module / "HELP.txt").read_text(encoding="utf-8")
            else:
                if "connection_error" in metadata:
                    raise RuntimeError(metadata["connection_error"])
                channel.emit("status", id=request_id, text="Calculating locally...")
                try:
                    completed = subprocess.run(
                        [node, "--max-old-space-size=256", str(Path(__file__).with_name("runner.cjs")), str(module), action],
                        input=json.dumps({"text": text}, ensure_ascii=False), capture_output=True,
                        encoding="utf-8", timeout=30, cwd=module,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                except subprocess.TimeoutExpired as exc:
                    raise ValueError("Calculation exceeded 30 seconds. Try a smaller input or use the full calculator.") from exc
                if completed.returncode:
                    raise RuntimeError("Calculator engine failed. Node.js 22 or newer is required.")
                response = json.loads(completed.stdout)
                if "error" in response:
                    raise ValueError(response["error"])
                result = response["text"]
            channel.emit("result", id=request_id, kind="source", text=result)
        except Exception as exc:
            channel.emit("error", id=request_id if request_id is not None else channel.last_id,
                         text=str(exc), code=getattr(exc, "code", -32602 if isinstance(exc, ValueError) else -32000))


if __name__ == "__main__":
    main()

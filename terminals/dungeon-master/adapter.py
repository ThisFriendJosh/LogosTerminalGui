"""Connect the independent Dungeon World AI Rust worker through JSON-RPC stdio."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, os.environ["LOGOS_TERMINAL_SDK_DIR"])
from terminal_protocol import Channel

ACTIONS = ["chat", "sessions", "new", "resume", "characters", "roll", "status"]


def installed_paths():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return {}
    root = Path(local)
    app = root/"Programs/Dungeon World AI Beta/app"
    return {"worker": app/"ai/dwa-terminal.exe", "server": app/"ai/llama-server.exe",
            "model": root/"DungeonWorldAI/models/dm/Qwen3-4B-Q4_K_M.gguf"}


def command_for(config, data, session, defaults=None):
    if not isinstance(config, dict):
        raise ValueError("Dungeon Master settings must be a JSON object")
    defaults = installed_paths() if defaults is None else defaults
    paths = {}
    for key, label in (("worker", "Dungeon World terminal worker"), ("server", "llama-server executable"), ("model", "GGUF model")):
        value = config.get(key) or defaults.get(key)
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError("Select the "+label+" in this terminal's Settings")
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            if key == "worker":
                raise ValueError("Select dwa-terminal.exe in Dungeon Master Settings. Build it from Dungeon World AI using Build-Terminal-Connector.cmd; the desktop executable is a separate program.")
            raise ValueError("The "+label+" was not found. Complete Dungeon World AI setup or choose its existing file in Settings")
        paths[key] = path
    if paths["model"].suffix.lower() != ".gguf":
        raise ValueError("Choose a GGUF model file")
    layers = config.get("gpu_layers", 0)
    if type(layers) is not int or not 0 <= layers <= 999:
        raise ValueError("GPU layers must be an integer from 0 to 999")
    selected_root = config.get("game_folder")
    if selected_root is not None and not isinstance(selected_root, str):
        raise ValueError("Save root must be a folder path")
    save_root = Path(selected_root).expanduser().resolve() if selected_root and selected_root.strip() else Path(data).resolve()/"game-data"
    command = [str(paths["worker"]), "--server", str(paths["server"]), "--model", str(paths["model"]),
               "--gpu-layers", str(layers), "--data-dir", str(save_root), "--session", session]
    return command, paths["worker"].parent


def setup_notice(message):
    channel = Channel()
    channel.emit("ready", model="Dungeon Master — setup needed", model_available=False, connection_error=str(message))
    for line in sys.stdin:
        try:
            accepted = channel.accept(line, ACTIONS, "Dungeon Master connector", "1.0.0")
            if accepted is not None:
                channel.error(accepted[0], message, -32000)
        except Exception as exc:
            channel.error(channel.last_id, str(exc), getattr(exc, "code", -32000))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config.exists() else {}
        command, cwd = command_for(config, args.data, args.session)
    except (OSError, ValueError, TypeError) as exc:
        setup_notice(str(exc))
        return 0
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    env = os.environ.copy()
    runtime_folder = Path(command[command.index("--server")+1]).parent
    env["PATH"] = str(runtime_folder)+os.pathsep+env.get("PATH", "")
    child = subprocess.Popen(command, cwd=cwd, env=env, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr, creationflags=flags)
    return child.wait()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

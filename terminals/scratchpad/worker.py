"""An independent notes module demonstrating the terminal protocol without AI."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, os.environ.get("LOGOS_TERMINAL_SDK_DIR", str(Path(__file__).resolve().parents[2])))
from terminal_protocol import Channel
channel = Channel()


def emit(event, **data):
    channel.emit(event, **data)


parser = argparse.ArgumentParser()
parser.add_argument("--state", required=True, type=Path)
args = parser.parse_args()
try:
    notes = json.loads(args.state.read_text(encoding="utf-8"))
except (OSError, ValueError):
    notes = []
emit("ready", protocol="logos-terminal/1", model="Local notes", text="Notes stay on this computer")
for line in sys.stdin:
    request_id = None
    try:
        accepted = channel.accept(line, ["note", "list"], "Scratchpad", "1.0.0")
        if accepted is None:
            continue
        request_id, action, payload = accepted
        text = payload.get("text", "").strip()
        if action == "note":
            if not text:
                raise ValueError("Write a note before saving")
            notes.append({"text": text, "created": datetime.now().astimezone().isoformat(timespec="seconds")})
            args.state.parent.mkdir(parents=True, exist_ok=True)
            temp = args.state.with_suffix(".tmp")
            temp.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp.replace(args.state)
            emit("result", id=request_id, text="Note saved on this computer.", kind="source")
        elif action == "list":
            matches = [n for n in notes if text.lower() in n["text"].lower()]
            display = matches[-40:]
            emit("result", id=request_id, kind="source", text="\n\n".join(n["created"] + "\n" + n["text"] for n in reversed(display)) or "No notes found.")
        else:
            raise ValueError("Scratchpad supports saving and finding notes")
    except Exception as exc:
        emit("error", id=request_id if request_id is not None else channel.last_id, text=str(exc), code=getattr(exc, "code", -32602 if isinstance(exc, ValueError) else -32000))

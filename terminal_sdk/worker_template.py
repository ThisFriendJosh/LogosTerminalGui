"""Copy beside terminal.json, then implement your own actions. No model required."""
import os
import sys

sys.path.insert(0, os.environ["LOGOS_TERMINAL_SDK_DIR"])
from terminal_protocol import Channel

channel = Channel()
channel.emit("ready", model="Custom terminal")
for line in sys.stdin:
    identifier = None
    try:
        accepted = channel.accept(line, ["chat"], "My Terminal", "1.0.0")
        if accepted is None:
            continue
        identifier, action, payload = accepted
        text = payload.get("text", "")
        # Replace this echo with your real terminal functionality.
        channel.emit("result", id=identifier, kind="source", text="Received: " + text)
    except Exception as exc:
        channel.emit("error", id=identifier if identifier is not None else channel.last_id,
                     text=str(exc), code=getattr(exc, "code", -32000))

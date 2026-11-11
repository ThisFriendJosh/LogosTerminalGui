"""JSON-RPC 2.0 / UTF-8 JSON Lines helpers for the Logos Terminal API 1.0.0.

No GUI or model packages are imported here. Modules may copy this adapter or
implement the documented wire contract in any language.
"""
import json
import re
import sys

API_VERSION = "1.0.0"
HOST_VERSION = "1.5.0"
MAX_LINE_BYTES = 2_000_000


def strict_json(text):
    def invalid(value):
        raise ValueError("Non-JSON numeric constant: " + value)
    return json.loads(text, parse_constant=invalid)


class ProtocolError(ValueError):
    def __init__(self, message, code=-32600):
        super().__init__(message)
        self.code = code


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value):
        raise ValueError("Use a stable semantic version such as 1.0.0")
    return tuple(map(int, value.split(".")))


def validate_payload(value, history=False):
    """Check the fields rendered by the GUI before module output reaches it."""
    if not isinstance(value, dict):
        raise ProtocolError("Terminal payload must be an object")
    for key in ("text", "model", "session"):
        if key in value and not isinstance(value[key], str):
            raise ProtocolError("Terminal " + key + " must be a string")
    if "session" in value and not 0 < len(value["session"]) <= 100:
        raise ProtocolError("Invalid terminal session identifier")
    if "translations" in value and (not isinstance(value["translations"], list) or len(value["translations"]) > 100 or any(not isinstance(x, str) or len(x) > 32 for x in value["translations"])):
        raise ProtocolError("Translations must be a list of short labels")
    kind = value.get("kind", "")
    if not isinstance(kind, str):
        raise ProtocolError("Result kind must be a string")
    if history or kind == "history":
        messages = value.get("messages")
        if not isinstance(messages, list) or len(messages) > 1000 or any(not isinstance(m, dict) or not isinstance(m.get("role"), str) or not isinstance(m.get("content"), str) for m in messages):
            raise ProtocolError("History messages need role and content strings")
    if kind in {"module_list", "session_list"}:
        items = value.get("items")
        if not isinstance(items, list) or len(items) > 1000 or any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("label"), str) or not isinstance(item.get("date", ""), str) for item in items):
            raise ProtocolError("Choices need id and label strings")
    if "audit" in value and not isinstance(value["audit"], dict):
        raise ProtocolError("Audit metadata must be an object")
    return value


def parse_request(line):
    try:
        value = strict_json(line)
    except ValueError as exc:
        raise ProtocolError("Parse error", -32700) from exc
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0" or not isinstance(value.get("method"), str):
        raise ProtocolError("Invalid JSON-RPC request")
    if "id" in value and (isinstance(value["id"], bool) or not isinstance(value["id"], (str, int, type(None)))):
        raise ProtocolError("Invalid request id")
    return value


def parse_server_message(value):
    if not isinstance(value, dict) or value.get("jsonrpc") != "2.0":
        raise ProtocolError("Module output must be JSON-RPC 2.0")
    if "method" in value:
        if "id" in value or not isinstance(value["method"], str) or not isinstance(value.get("params", {}), dict):
            raise ProtocolError("Expected a server notification without an id")
        return value
    if "id" not in value or (("result" in value) == ("error" in value)):
        raise ProtocolError("Responses need an id and exactly one of result or error")
    if "error" in value:
        error = value["error"]
        if not isinstance(error, dict) or not isinstance(error.get("code"), int) or isinstance(error["code"], bool) or not isinstance(error.get("message"), str):
            raise ProtocolError("Malformed JSON-RPC error")
    return value


class Channel:
    def __init__(self):
        self.notification = False
        self.ready = {}
        self.initialized = False
        self.last_id = None

    def write(self, value):
        line = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            raise ProtocolError("Response exceeds the 2 MB frame limit", -32000)
        print(line, flush=True)

    def notify(self, method, **params):
        self.write({"jsonrpc": "2.0", "method": method, "params": params})

    def result(self, request_id, result):
        if not self.notification:
            self.write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def error(self, request_id, message, code=-32000):
        if not self.notification:
            self.write({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": str(message)}})

    def emit(self, event, **data):
        if event == "ready":
            self.ready = data
            return
        if event in {"result", "done"}:
            request_id = data.pop("id", None)
            self.result(request_id, {"kind": "done", **data} if event == "done" else data)
        elif event == "history" and data.get("id") is not None:
            request_id = data.pop("id")
            self.result(request_id, {"kind": "history", **data})
        elif event == "error":
            request_id = data.pop("id", None)
            self.error(request_id, data.get("text", "Module error"), data.get("code", -32000))
        else:
            self.notify("terminal/" + event, **data)

    def accept(self, line, actions, server_name, server_version):
        """Return (request_id, action, payload), or None for initialization.

        Initialization is a request/response. Progress and history are
        notifications; every execution receives exactly one final response.
        """
        self.notification = False
        self.last_id = None
        request = parse_request(line)
        self.notification = "id" not in request
        identifier, method, params = request.get("id"), request["method"], request.get("params", {})
        self.last_id = identifier
        if not isinstance(params, dict):
            raise ProtocolError("Named parameters are required by the terminal API", -32602)
        if method == "initialize":
            try:
                requested = version(params.get("protocolVersion", "0.0.0"))
            except ValueError as exc:
                raise ProtocolError(str(exc), -32602) from exc
            if requested[0] != version(API_VERSION)[0]:
                raise ProtocolError("Incompatible terminal API major version", -32001)
            self.result(identifier, {"protocolVersion": API_VERSION,
                "serverInfo": {"name": server_name, "version": server_version},
                "capabilities": {"actions": list(actions)}, "metadata": self.ready})
            self.initialized = True
            return None
        if method != "terminal/execute":
            raise ProtocolError("Method not found", -32601)
        if not self.initialized:
            raise ProtocolError("Initialize the terminal before executing actions", -32002)
        action, payload = params.get("action"), params.get("input", {})
        if not isinstance(action, str) or not isinstance(payload, dict):
            raise ProtocolError("Execution requires action and input fields", -32602)
        if action not in actions:
            raise ProtocolError("Action is not supported by this terminal: " + action, -32602)
        return identifier, action, payload

"""Validate the published schema and every shipped module manifest."""
import json
from pathlib import Path
import sys

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_core import TerminalModule

schema = json.loads((ROOT / "terminal_sdk/terminal.schema.json").read_text(encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(schema)
validator = jsonschema.Draft202012Validator(schema)
manifests = [*sorted((ROOT / "terminals").glob("*/terminal.json")), ROOT / "terminal_sdk/example/terminal.json"]
for path in manifests:
    validator.validate(json.loads(path.read_text(encoding="utf-8")))
    TerminalModule.load(path)
print(f"Verified JSON Schema 2020-12 and {len(manifests)} manifests.")

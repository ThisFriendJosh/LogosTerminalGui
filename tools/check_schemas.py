"""Validate the published schema and every shipped module manifest."""
import json
from pathlib import Path
import sys

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_core import TerminalModule
from terminal_themes import load_theme

schema = json.loads((ROOT / "terminal_sdk/terminal.schema.json").read_text(encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(schema)
validator = jsonschema.Draft202012Validator(schema)
manifests = [*sorted((ROOT / "terminals").glob("*/terminal.json")), ROOT / "terminal_sdk/example/terminal.json"]
for path in manifests:
    validator.validate(json.loads(path.read_text(encoding="utf-8")))
    TerminalModule.load(path)
print(f"Verified JSON Schema 2020-12 and {len(manifests)} manifests.")
theme_schema = json.loads((ROOT / "themes/theme.schema.json").read_text(encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(theme_schema)
theme_validator = jsonschema.Draft202012Validator(theme_schema)
themes = sorted((ROOT / "themes").glob("*.theme.json"))
for path in themes:
    theme_validator.validate(json.loads(path.read_text(encoding="utf-8")))
    load_theme(path)
print(f"Verified theme schema and {len(themes)} bundled themes.")

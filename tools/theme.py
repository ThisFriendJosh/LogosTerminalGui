"""Inspect or validate a versioned, data-only terminal theme."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terminal_themes import load_theme


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "inspect"))
    parser.add_argument("path", type=Path)
    display = parser.add_mutually_exclusive_group()
    display.add_argument("--group", choices=("palette", "typography", "components", "effects"))
    display.add_argument("--flat", action="store_true", help="Print stable dotted element names")
    args = parser.parse_args()
    try:
        theme = load_theme(args.path)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, "Invalid theme: " + str(exc) + "\n")
    if args.command == "validate":
        print(f"Valid {theme.data['schema']}: {theme.name} ({theme.id})")
    else:
        print(json.dumps(theme.tokens() if args.flat else theme.elements(args.group), indent=2))


if __name__ == "__main__":
    main()

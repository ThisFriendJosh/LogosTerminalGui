"""Versioned, data-only theme definitions and a reusable element parser."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from terminal_protocol import HOST_VERSION, version

SCHEMA = "logos-terminal-theme/1"
COLOR_KEYS = ("background", "panel", "field", "accent", "accent_bright", "text", "muted", "edge", "error",
              "selection", "selection_text", "code_background", "placeholder", "disabled", "button_fill", "button_disabled", "footer", "user", "border_glow", "brand")
COMPONENT_KEYS = ("button_style", "module_icons", "terminal_prompts")
EFFECT_KEYS = ("digital_rain", "text_glow", "scanlines", "pulse", "block_cursor", "frame_rate")
RAIN_LIMITS = {"column_spacing": (12, 40), "row_spacing": (16, 48), "fall_speed": (8, 100),
               "morph_rate": (0, 20), "brightness": (.1, 1.5), "content_brightness": (.15, 1), "glow_radius": (0, 5),
               "glow_strength": (0, 2), "trail_seconds": (0, 2)}
ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_THEME_BYTES = 65536


def _keys(value, expected, section, optional=()):
    if not isinstance(value, dict):
        raise ValueError(f"{section} must be an object")
    missing, unknown = set(expected)-value.keys(), value.keys()-(set(expected)|set(optional))
    if missing:
        raise ValueError(f"{section}: missing {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{section}: unsupported elements {', '.join(sorted(unknown))}")


@dataclass(frozen=True)
class Theme:
    data: dict
    source: Path | None = None

    @property
    def id(self):
        return self.data["id"]

    @property
    def name(self):
        return self.data["name"]

    @property
    def palette(self):
        return self.data["palette"]

    @property
    def effects(self):
        return self.data["effects"]

    @property
    def components(self):
        return self.data["components"]

    @property
    def rain(self):
        return self.data.get("rain")

    def elements(self, group=None):
        """Parse reusable, named elements; return a detached JSON-compatible tree."""
        if group is not None and group not in ("palette", "typography", "components", "effects", "rain"):
            raise ValueError("Choose palette, typography, components, effects or rain")
        return json.loads(json.dumps(self.data.get(group, {}) if group else self.data))

    def tokens(self):
        """Flatten element groups into stable names such as palette.accent."""
        return {f"{group}.{key}": value for group in ("palette", "typography", "components", "effects", "rain")
                for key, value in self.elements(group).items()}

    def to_json(self):
        return json.dumps(self.data, indent=2, ensure_ascii=False) + "\n"


def parse_theme(data, source=None):
    """Validate all renderer inputs without executing code or loading URLs."""
    expected = ("schema", "id", "name", "version", "description", "palette", "typography", "components", "effects")
    _keys(data, expected, "theme", optional=("$schema", "min_host_version", "rain"))
    if "$schema" in data and not isinstance(data["$schema"], str):
        raise ValueError("$schema must be a string (editor hint only)")
    if data["schema"] != SCHEMA:
        raise ValueError(f"Unsupported theme schema; expected {SCHEMA}")
    if not isinstance(data["id"], str) or not ID.fullmatch(data["id"]):
        raise ValueError("Theme id must use lowercase letters, digits and hyphens (1-64 characters)")
    for key, limit in (("name", 64), ("description", 400)):
        if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > limit or any(ord(c) < 32 for c in data[key]):
            raise ValueError(f"Theme {key} must be readable text, at most {limit} characters")
    if not isinstance(data["version"], str) or not VERSION.fullmatch(data["version"]):
        raise ValueError("Theme version must use major.minor.patch")
    minimum = data.get("min_host_version", "1.0.0")
    if not isinstance(minimum, str) or not VERSION.fullmatch(minimum):
        raise ValueError("min_host_version must use major.minor.patch")
    if version(minimum) > version(HOST_VERSION):
        raise ValueError(f"This theme needs host {minimum} or newer")
    _keys(data["palette"], COLOR_KEYS, "palette")
    for key, color in data["palette"].items():
        if not isinstance(color, str) or not HEX.fullmatch(color):
            raise ValueError(f"palette.{key} must be a #RRGGBB color")
    _keys(data["typography"], ("families",), "typography")
    families = data["typography"]["families"]
    if not isinstance(families, list) or not 1 <= len(families) <= 8 or any(not isinstance(f, str) or not f.strip() or len(f) > 80 or any(ord(c) < 32 for c in f) for f in families):
        raise ValueError("typography.families must contain 1-8 font family names")
    _keys(data["components"], COMPONENT_KEYS, "components")
    if data["components"]["button_style"] not in ("classic", "phosphor"):
        raise ValueError("components.button_style must be classic or phosphor")
    for key in COMPONENT_KEYS[1:]:
        if type(data["components"][key]) is not bool:
            raise ValueError(f"components.{key} must be true or false")
    _keys(data["effects"], EFFECT_KEYS, "effects")
    for key in EFFECT_KEYS[:-1]:
        if type(data["effects"][key]) is not bool:
            raise ValueError(f"effects.{key} must be true or false")
    rate = data["effects"]["frame_rate"]
    if type(rate) is not int or not 4 <= rate <= 30:
        raise ValueError("effects.frame_rate must be an integer from 4 to 30")
    if "rain" in data:
        _keys(data["rain"], RAIN_LIMITS, "rain")
        for key, (low, high) in RAIN_LIMITS.items():
            value = data["rain"][key]
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"rain.{key} must be a number from {low} to {high}")
            if key == "glow_radius" and type(value) is not int:
                raise ValueError("rain.glow_radius must be an integer")
    return Theme(json.loads(json.dumps(data)), Path(source) if source else None)


def load_theme(path):
    path = Path(path)
    if path.stat().st_size > MAX_THEME_BYTES:
        raise ValueError("Theme definitions are limited to 64 KiB")
    return parse_theme(json.loads(path.read_text(encoding="utf-8-sig")), path)


class ThemeCatalog:
    def __init__(self, app_root, bundled_root=None):
        self.bundled_root = Path(bundled_root) if bundled_root else Path(__file__).resolve().parent / "themes"
        self.custom_root = Path(app_root) / "state/themes"
        self.themes, self.errors = {}, []
        self.reload()

    def reload(self):
        self.themes, self.errors = {}, []
        for folder in (self.bundled_root, self.custom_root):
            for path in sorted(folder.glob("*.theme.json"))[:64]:
                try:
                    theme = load_theme(path)
                    if theme.id in self.themes:
                        raise ValueError("Duplicate theme id: " + theme.id)
                    self.themes[theme.id] = theme
                except (OSError, ValueError, TypeError) as exc:
                    self.errors.append(f"{path.name}: {exc}")
        if "logos-classic" not in self.themes:
            raise ValueError("The bundled Logos Classic theme is missing or invalid")

    def selected(self, identifier):
        return self.themes.get(identifier, self.themes["logos-classic"])

    def import_file(self, path):
        theme = load_theme(path)
        return self._save_custom(theme)

    def customize_rain(self, theme, values, frame_rate=None):
        data = theme.elements()
        data["rain"] = dict(values)
        if frame_rate is not None:
            data["effects"]["frame_rate"] = frame_rate
        if not theme.source or theme.source.parent != self.custom_root:
            base = theme.id[:52]+"-custom"
            identifier, sequence = base, 1
            while identifier in self.themes:
                sequence += 1
                identifier = base+"-"+str(sequence)
            data.update(id=identifier, name=theme.name[:56]+" Custom", version="1.0.0",
                        description="Personal rain settings based on "+theme.name+".")
        return self._save_custom(parse_theme(data))

    def _save_custom(self, theme):
        existing = self.themes.get(theme.id)
        if existing and existing.source.parent != self.custom_root:
            raise ValueError("This id belongs to a bundled theme. Give your theme a new id before importing it.")
        self.custom_root.mkdir(parents=True, exist_ok=True)
        if not existing and len(list(self.custom_root.glob("*.theme.json"))) >= 64:
            raise ValueError("The custom theme folder is full (64 themes)")
        target = self.custom_root / (theme.id + ".theme.json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(theme.to_json(), encoding="utf-8")
        temporary.replace(target)
        self.reload()
        return self.themes[theme.id]

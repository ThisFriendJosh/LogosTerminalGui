# Theme authoring, version 1

Themes describe appearance independently of terminal modules. The host owns workspace layout and behavior. A theme can change colors, font-family preferences, button decoration and effects; loading or switching a theme does not restart a backend.

## Create or add a theme

1. In Settings, choose an existing theme and click **Export theme**.
2. Edit the JSON file. Set a unique lowercase `id`, a readable `name`, a `major.minor.patch` version and a short description.
3. Change the palette, typography, component and effect elements. Keep every required key.
4. Optionally run `python tools/theme.py validate path/to/your.theme.json`.
5. Use **Import theme** in Settings, select it, and Apply.

Imported definitions are copied to `state/themes/ID.theme.json`, separate from Git-tracked code. Reimporting the same custom id updates that definition. Bundled ids cannot be replaced by importing a custom definition; give the copy a new id. To ship a theme with the project, add its `*.theme.json` definition to `themes/` and run the schema checks. Settings refreshes the catalog when opened.

The original **Logos Classic** remains the default for existing installations. A missing or invalid custom theme falls back to Classic; errors in individual custom definitions do not stop other themes loading.

## Parsed elements

Every file uses `schema: "logos-terminal-theme/1"`. `themes/theme.schema.json` is the JSON Schema 2020-12 definition; the runtime parser enforces the same supported elements without a third-party validator. `$schema` is an optional editor hint and is never loaded by the application.

| Group | Elements | Meaning |
|---|---|---|
| Palette | `background`, `panel`, `field` | Main surfaces |
| Palette | `accent`, `accent_bright`, `text`, `muted`, `user`, `error`, `placeholder`, `disabled`, `footer` | Text and status colors |
| Palette | `edge`, `selection`, `selection_text`, `code_background`, `button_fill`, `button_disabled`, `border_glow`, `brand` | Borders, controls, selection and lighting |
| Typography | `families` | Ordered list of installed font families; Courier is the final fallback. Reading size remains a user setting. |
| Components | `button_style` | `classic` or `phosphor` renderer |
| Components | `module_icons` | Decorate dynamically loaded terminals with the reticle, network, chip, document and gear motif cycle |
| Components | `terminal_prompts` | Use terminal-style prompt decoration and welcome text |
| Effects | `digital_rain`, `text_glow`, `scanlines`, `pulse`, `block_cursor` | Independent switches for the supported effects |
| Effects | `frame_rate` | Maximum ambient update rate, an integer from 4 to 15 |

All palette values use `#RRGGBB`. New themes can combine existing elements without changing Python code. A new kind of effect or component renderer needs a deliberate parser/schema/renderer change; unknown elements fail validation instead of being silently ignored. Breaking format changes require a new schema major version. The module API and theme format are separate contracts.

## Inspect and extract

Settings > Theme elements offers the complete definition, each element group, and flat dotted names. Copy the displayed group or export the whole definition.

The command-line interface emits JSON suitable for other tools:

```sh
python tools/theme.py inspect themes/galactic-phosphor.theme.json --group effects
python tools/theme.py inspect themes/logos-classic.theme.json --flat
```

The parser is also reusable directly:

```python
from terminal_themes import load_theme

theme = load_theme("themes/galactic-phosphor.theme.json")
palette = theme.elements("palette")
tokens = theme.tokens()  # e.g. tokens["palette.accent"]
definition = theme.to_json()
```

Extracted element dictionaries are detached copies. Theme files contain no executable code, URLs to load, font downloads or runtime dependencies. Definitions are limited to 64 KiB, with up to 64 files per catalog folder.

## Rendering and motion

Galactic Phosphor uses original small procedural stroke drawings of the 26 Standard Galactic Alphabet forms. A shared stroke atlas and bounded raster tile avoid external fonts, missing-glyph squares and thousands of separate canvas image updates. Falling columns have individual speeds, changing symbols, dim trails and fading after-images. The field, including after-images, is capped at 1,800 glyphs even on large displays. Text uses a native Tk Text engine for wrapping, scrolling, selection and copy, with a canvas view for the luminous skin. The input editor stays native.

The Effects control is a user override: it stops ambient rain, pulses and cursor blinking while retaining hover feedback. Ambient animation pauses when the app is inactive or minimized. The OS title-bar border is tinted where the platform supports it; panel styling works across Windows and Linux.

## Validation

```sh
python -m unittest discover -v
python tools/check_schemas.py
```

Tests cover malformed definitions, theme import and extraction, resource bounds, compact layouts, and switching themes with a live worker and an unsent draft. CI validates both bundled themes against the published schema.

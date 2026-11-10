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

**Galactic 2.0** is a separate preset, id `galactic-2`, requiring host 1.2.0 or newer. In Settings, its **Rain settings** editor saves a personal custom definition and selects it in the theme menu; Apply activates that selection. Editing an already selected custom theme updates that custom definition. Editing a bundled preset creates a new custom id and leaves the preset intact.

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
| Effects | `frame_rate` | Maximum ambient update rate, an integer from 4 to 30. Galactic 2.0 defaults to 24. |

Themes can include an optional `min_host_version` using major.minor.patch. The parser rejects themes requiring a newer host. The optional `rain` group enables the Galactic 2.0 renderer; omitting it retains the original renderer. All keys in that group are required when the group is present:

| Rain element | Range | Meaning |
|---|---|---|
| `column_spacing` | 12-40 | Horizontal distance between stream centers, in pixels |
| `row_spacing` | 16-48 | Vertical distance between characters, in pixels |
| `fall_speed` | 8-100 | Typical pixels per second; streams vary around it |
| `morph_rate` | 0-20 | Changes per second, with independent timers for each character; zero freezes symbol identities |
| `brightness` | 0.1-1.5 | Character light intensity |
| `content_brightness` | 0.15-1 | Rain intensity behind transcript text relative to surrounding rain |
| `glow_radius` | 0-5 | Integer halo radius, in pixels |
| `glow_strength` | 0-2 | Soft halo intensity |
| `trail_seconds` | 0-2 | Fade duration of a character's previous image; zero disables trails |

All palette values use `#RRGGBB`. New themes can combine existing elements without changing Python code. A new kind of effect or component renderer needs a deliberate parser/schema/renderer change; unknown elements fail validation instead of being silently ignored. Breaking format changes require a new schema major version. The module API and theme format are separate contracts.

## Inspect and extract

Settings > Theme elements offers the complete definition, each element group (including Rain), and flat dotted names. Copy the displayed group or export the whole definition.

The command-line interface emits JSON suitable for other tools:

```sh
python tools/theme.py inspect themes/galactic-phosphor.theme.json --group effects
python tools/theme.py inspect themes/logos-classic.theme.json --flat
python tools/theme.py inspect themes/galactic-2.theme.json --group rain
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

Galactic 2.0 uses a separate time-based field. Every character keeps its own change timer as it moves; movement does not wait for a symbol change. Four cached subpixel phases soften vertical steps. Gaussian halo masks are cached and overlapping light saturates without leaking into neighboring pixels. A shared indexed-color texture avoids Python RGB pixel loops and scales the transcript's rain brightness separately. Its texture is bounded to 768 x 480 pixels and its field to 4,096 current/after-image cells. Very dense custom settings are limited to that budget on large surfaces. Animation scheduling accounts for render time; actual frame rate depends on the computer and its workload.

The Effects control is a user override: it stops ambient rain, pulses and cursor blinking while retaining hover feedback. Ambient animation pauses when the app is inactive or minimized. The OS title-bar border is tinted where the platform supports it; panel styling works across Windows and Linux.

## Validation

```sh
python -m unittest discover -v
python tools/check_schemas.py
```

Tests cover malformed definitions, theme import and extraction, resource bounds, compact layouts, and switching themes with a live worker and an unsent draft. CI validates all bundled themes against the published schema.

To measure local steady-state rendering cost (requires a Tk display):

```sh
python tools/benchmark_rain.py --theme galactic-2
python tools/benchmark_rain.py --theme galactic-phosphor
```

This uses a temporary workspace with no live model and reports render latency, not a guaranteed display frame rate. On headless Linux, prefix the command with `xvfb-run -a`.

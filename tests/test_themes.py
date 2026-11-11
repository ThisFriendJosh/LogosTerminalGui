"""Theme interchange and safe custom definitions, independent of Tk or models."""
import json
from pathlib import Path
import tempfile
import unittest

from terminal_core import read_preferences, write_preferences
from terminal_themes import ThemeCatalog, load_theme, parse_theme
from terminal_visuals import RainField

ROOT = Path(__file__).resolve().parents[1]


class ThemeTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "work"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = ThemeCatalog(self.root)

    def test_original_remains_default_and_missing_theme_falls_back(self):
        self.assertEqual(read_preferences(self.root / "missing.json")["theme"], "logos-classic")
        self.assertEqual(self.catalog.selected("not-installed").id, "logos-classic")
        self.assertEqual(self.catalog.selected("logos-classic").palette["panel"], "#07100c")

    def test_definition_round_trip_and_element_extraction_are_detached(self):
        theme = self.catalog.selected("galactic-phosphor")
        self.assertEqual(parse_theme(json.loads(theme.to_json())).data, theme.data)
        self.assertEqual(theme.tokens()["palette.accent"], "#00ff41")
        palette = theme.elements("palette")
        palette["accent"] = "#ffffff"
        self.assertEqual(theme.palette["accent"], "#00ff41")
        with self.assertRaises(ValueError):
            theme.elements("layout")

    def test_imported_theme_survives_catalog_reload_and_preferences(self):
        data = self.catalog.selected("galactic-phosphor").elements()
        data.update(id="custom-blue", name="Custom Blue")
        data["palette"]["accent"] = "#3478ff"
        path = self.root / "custom.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        imported = self.catalog.import_file(path)
        prefs = read_preferences(self.root / "prefs.json")
        prefs.update(theme=imported.id, sessions={"fixture": "saved-session"})
        write_preferences(self.root / "prefs.json", prefs)
        self.assertEqual(ThemeCatalog(self.root).selected("custom-blue").palette["accent"], "#3478ff")
        self.assertEqual(read_preferences(self.root / "prefs.json"), prefs)

    def test_bundled_ids_cannot_be_replaced_by_import(self):
        with self.assertRaisesRegex(ValueError, "bundled"):
            self.catalog.import_file(ROOT / "themes/logos-classic.theme.json")

    def test_unknown_elements_invalid_colors_and_wrong_types_are_rejected(self):
        for group, key, value in [("palette", "accent", "https://example.com"), ("effects", "pulse", "false"),
                                  ("effects", "frame_rate", 240), ("effects", "frame_rate", True),
                                  ("components", "button_style", "python"), ("palette", "acccent", "#00ff41")]:
            with self.subTest(group=group, key=key, value=value):
                data = self.catalog.selected("logos-classic").elements()
                data[group][key] = value
                with self.assertRaises(ValueError):
                    parse_theme(data)
        data = self.catalog.selected("logos-classic").elements()
        data["id"] = "../../outside"
        with self.assertRaises(ValueError):
            parse_theme(data)

    def test_invalid_custom_theme_does_not_prevent_valid_themes_loading(self):
        self.catalog.custom_root.mkdir(parents=True)
        (self.catalog.custom_root / "broken.theme.json").write_text('{"schema":"new-major/99"}')
        self.catalog.reload()
        shipped = {load_theme(path).id for path in (ROOT / "themes").glob("*.theme.json")}
        self.assertEqual(set(self.catalog.themes), shipped)
        self.assertEqual(len(shipped), 10)
        self.assertEqual(len(self.catalog.errors), 1)

    def test_rain_model_remains_bounded_at_large_window_sizes(self):
        field = RainField()
        for size in [(980, 650), (1320, 850), (3840, 2160), (7680, 4320)]:
            with self.subTest(size=size):
                field.resize(*size)
                self.assertLessEqual(len(field.cells), field.MAX_CELLS)
                before = list(field.cells)
                field.advance(.1)
                self.assertNotEqual(field.cells, before)
                self.assertTrue(all(0 <= glyph < 26 and 0 <= level < 8 for _, _, _, glyph, level in field.cells))


if __name__ == "__main__":
    unittest.main()

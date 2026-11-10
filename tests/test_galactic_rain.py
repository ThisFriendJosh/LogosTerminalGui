"""Visible behavior and light composition of the Galactic 2.0 renderer."""
from pathlib import Path
import tempfile
import unittest

from galactic_rain import AnimatedRain, GlowRaster, cached_glow_atlas
from terminal_themes import ThemeCatalog, parse_theme
from terminal_visuals import SGA

ROOT = Path(__file__).resolve().parents[1]


class GalacticTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/"work"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.catalog = ThemeCatalog(self.temp.name)
        self.theme = self.catalog.selected("galactic-2")

    def test_legacy_themes_are_not_opted_into_new_animation(self):
        self.assertIsNone(self.catalog.selected("logos-classic").rain)
        self.assertIsNone(self.catalog.selected("galactic-phosphor").rain)
        self.assertEqual(self.theme.tokens()["rain.column_spacing"], 16)

    def test_every_surviving_character_changes_its_own_identity(self):
        field = AnimatedRain(self.theme.elements("rain"))
        field.resize(320, 240)
        original = {c.uid: c.glyph for column in field.columns for c in column["characters"]}
        changed = set()
        counts = []
        for _ in range(20):
            field.advance(1/60)
            for column in field.columns:
                for character in column["characters"]:
                    if character.uid in original and original[character.uid] != character.glyph:
                        changed.add(character.uid)
            counts.append(len(changed))
        surviving = {c.uid for column in field.columns for c in column["characters"]} & original.keys()
        self.assertTrue(surviving <= changed)
        self.assertGreater(counts[0], 0)
        self.assertLess(counts[0], counts[-1])

    def test_motion_is_elapsed_time_based_and_accepts_fractional_positions(self):
        settings = self.theme.elements("rain")
        settings["morph_rate"] = 0
        a, b = AnimatedRain(settings), AnimatedRain(settings)
        a.resize(320, 240)
        b.resize(320, 240)
        for _ in range(12):
            a.advance(1/60)
        for _ in range(6):
            b.advance(1/30)
        for first, second in zip(a.columns, b.columns):
            self.assertAlmostEqual(first["offset"], second["offset"], places=8)
        before = list(a.cells)
        a.advance(0)
        self.assertEqual(a.cells, before)
        self.assertTrue(any(y != int(y) for _, _, y, _, _ in a.cells))

    def test_after_images_fade_and_resource_budget_is_bounded(self):
        settings = self.theme.elements("rain")
        field = AnimatedRain(settings)
        for size in [(960, 720), (3840, 2160), (7680, 4320)]:
            field.resize(*size)
            for _ in range(8):
                field.advance(.05)
            self.assertLessEqual(len(field.cells), field.MAX_CELLS)
            self.assertTrue(any(key < 0 for key, *_ in field.cells))
        settings["morph_rate"] = 0
        for _ in range(6):
            field.advance(.1)
        self.assertTrue(all(key > 0 for key, *_ in field.cells))

    def test_soft_halo_extends_beyond_crisp_character_core(self):
        atlas = cached_glow_atlas(SGA, 4, 1.15, 1.0)
        plain = cached_glow_atlas(SGA, 0, 0, 1.0)
        cell = (1, 32, 32, 0, 31)
        glow = GlowRaster(atlas).indices([cell], 64, 64)
        normal = GlowRaster(plain).indices([cell], 64, 64)
        self.assertEqual(normal[34*64+27], 0)
        self.assertGreater(glow[34*64+27], 0)
        self.assertLess(glow[34*64+27], glow[34*64+29])
        self.assertEqual(glow[34*64+29], 255)

    def test_overlapping_light_saturates_without_corrupting_adjacent_pixels(self):
        raster = GlowRaster(cached_glow_atlas(SGA, 4, 1.15, 1.0))
        cell = (1, 32, 32, 0, 31)
        single = raster.indices([cell], 64, 64)
        combined = raster.indices([cell]*7, 64, 64)
        self.assertEqual(combined, bytes(min(255, value*7) for value in single))

    def test_subpixel_phase_moves_light_without_a_whole_pixel_jump(self):
        raster = GlowRaster(cached_glow_atlas(SGA, 4, 1.15, 1.0))
        first = raster.indices([(1, 32, 32, 0, 24)], 64, 64)
        quarter = raster.indices([(1, 32, 32.25, 0, 24)], 64, 64)
        self.assertNotEqual(first, quarter)
        self.assertLess(abs(sum(first)-sum(quarter))/sum(first), .02)
        clipped = raster.indices([(1, 0, 0, 0, 31), (2, 63, 63, 1, 31)], 64, 64)
        self.assertEqual(len(clipped), 64*64)

    def test_custom_rain_settings_survive_reload_and_keep_preset_unchanged(self):
        before = self.theme.source.read_bytes()
        changes = self.theme.elements("rain")
        changes.update(column_spacing=14, morph_rate=9, glow_strength=1.4)
        custom = self.catalog.customize_rain(self.theme, changes, frame_rate=30)
        self.assertEqual(custom.id, "galactic-2-custom")
        self.assertEqual(self.catalog.selected("galactic-2").source.read_bytes(), before)
        reloaded = ThemeCatalog(self.temp.name).selected(custom.id)
        self.assertEqual(reloaded.rain, changes)
        self.assertEqual(reloaded.effects["frame_rate"], 30)
        self.assertEqual(reloaded.tokens()["rain.morph_rate"], 9)

    def test_invalid_or_unsupported_rain_elements_are_rejected(self):
        for key, value in [("column_spacing", 0), ("morph_rate", float("nan")), ("brightness", float("inf")),
                           ("glow_radius", 2.5), ("glow_strength", True), ("fall_speed", 10000)]:
            with self.subTest(key=key):
                data = self.theme.elements()
                data["rain"][key] = value
                with self.assertRaises(ValueError):
                    parse_theme(data)
        data = self.theme.elements()
        data["min_host_version"] = "99.0.0"
        with self.assertRaisesRegex(ValueError, "needs host"):
            parse_theme(data)


if __name__ == "__main__":
    unittest.main()

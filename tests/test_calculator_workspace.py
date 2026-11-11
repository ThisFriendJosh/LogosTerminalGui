"""Exercise visual controls through the real module transport and original engines."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tests.test_gui_layout import pump

ROOT = Path(__file__).resolve().parents[1]


class CalculatorWorkspaceTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("node") or (sys.platform != "win32" and not os.environ.get("DISPLAY")):
            self.skipTest("Visual calculator tests require Node.js and a display")
        import tkinter as tk
        from terminal_gui import TerminalGUI
        try:
            self.window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        (ROOT / "work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "work")
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT / "terminal_protocol.py", self.root / "terminal_protocol.py")
        self.app = TerminalGUI(self.window, app_root=self.root)
        self.app.preferences["effects"] = False
        self.app.update_effect_label()

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        self.app.closing = True
        for process in list(self.app.processes.values()) + list(self.app.stopping_processes.values()):
            process.stop()
        self.app.outer.destroy()
        for pending in self.window.tk.call("after", "info"):
            self.window.after_cancel(pending)
        self.window.destroy()
        self.temp.cleanup()

    def view(self, identifier):
        self.app.register(ROOT / "terminals" / identifier / "terminal.json")
        pump(self.window)
        self.assertFalse(self.app.text_area.winfo_ismapped())
        self.assertTrue(self.app.visual_area.winfo_ismapped())
        self.assertNotIn(identifier, self.app.processes, "Selecting a visual module must not launch its worker")
        return self.app.calculator_views[identifier]

    def wait_result(self, view):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            pump(self.window)
            if view.result and not self.app.workspace()["busy"]:
                return
            time.sleep(.015)
        self.fail(str(self.app.workspace()["entries"]))

    def test_visual_recipe_dynamic_parameters_and_original_output(self):
        view = self.view("cryptocalc")
        view.search.set("caesar_decode")
        view.operation_list.selection_set(0)
        view.add_operation()
        self.assertEqual(view.recipe[0]["op"], "caesar_decode")
        self.assertTrue(view.parameter_vars)
        view.source.insert("1.0", "Khoor")
        view.run()
        self.wait_result(view)
        self.assertEqual(view.output_text.get("1.0", "end-1c"), "Hello")
        self.assertEqual(view.output_hex.get("1.0", "end-1c"), "48656c6c6f")
        self.assertEqual(len(view.step_table.get_children()), 1)
        self.app.update_workspace_view(False)
        pump(self.window)
        self.assertTrue(self.app.text_area.winfo_ismapped())
        self.app.update_workspace_view(True)
        pump(self.window)
        self.assertIs(self.app.calculator_views["cryptocalc"], view)
        self.assertEqual(view.source.get("1.0", "end-1c"), "Khoor")

    def test_grid_calculation_intervals_and_chart_counts(self):
        view = self.view("statcalc")
        for index, value in enumerate([1, 2, 3, 4, 5]):
            view.cell_vars[index][0].set(str(value))
        view.header_vars[0].set("measurement")
        view.run()
        self.wait_result(view)
        values = view.overview.item(view.overview.get_children()[0], "values")
        self.assertEqual(values[:5], ("measurement", "quantitative", "5", "3", "3"))
        self.assertGreaterEqual(len(view.intervals.get_children()), 3)
        view.tabs.select(4)
        pump(self.window)
        self.assertGreater(len(view.chart.find_withtag("bar")), 0)
        view.paste_data("color\nred\nblue\nred")
        view.result = {}
        view.run()
        self.wait_result(view)
        view.chart_column.set("color")
        view.tabs.select(4)
        pump(self.window)
        self.assertEqual(len(view.chart.find_withtag("bar")), 2)
        self.assertEqual(view.result["analysis"]["reports"][0]["summary"]["n"], 3)

    def test_theme_and_module_switch_keep_grid_recipe_results_and_workers(self):
        stat = self.view("statcalc")
        stat.paste_data("x\n1\n2\n3\n4\n5")
        stat.run()
        self.wait_result(stat)
        process = self.app.processes["statcalc"]
        crypto = self.view("cryptocalc")
        crypto.source.insert("1.0", "Keep this draft")
        crypto.search.set("to_base64")
        crypto.operation_list.selection_set(0)
        crypto.add_operation()
        self.app.apply_theme("galactic-2")
        pump(self.window)
        restored = self.app.calculator_views["cryptocalc"]
        self.assertEqual(restored.source.get("1.0", "end-1c"), "Keep this draft")
        self.assertEqual(restored.recipe[0]["op"], "to_base64")
        self.app.select_module("statcalc")
        pump(self.window)
        self.assertIn("x\n1\n2", self.app.calculator_views["statcalc"].raw.get("1.0", "end-1c"))
        self.assertEqual(self.app.processes["statcalc"].process.pid, process.process.pid)
        self.assertIsNone(process.process.poll())
        for identifier in ("statcalc", "cryptocalc"):
            self.app.select_module(identifier)
            self.window.geometry("980x650")
            pump(self.window)
            button = self.app.calculator_views[identifier].run_button
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), self.window.winfo_rootx()+self.window.winfo_width())

    def test_bundled_operation_catalogue_matches_engine(self):
        import subprocess
        result = subprocess.run([shutil.which("node"), str(ROOT / "terminals/_calculator/runner.cjs"),
                                 str(ROOT / "terminals/cryptocalc"), "operations"],
                                input='{"text":""}', capture_output=True, encoding="utf-8", timeout=15, check=True)
        catalog = json.loads((ROOT / "terminals/cryptocalc/operations.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog, json.loads(result.stdout)["audit"]["calculator"]["operations"])

    def test_original_recipe_format_round_trip_preserves_disabled_steps(self):
        view = self.view("cryptocalc")
        view.search.set("caesar_decode")
        view.operation_list.selection_set(0)
        view.add_operation()
        view.step_enabled.set(False)
        filename = self.root / "recipe.json"
        with patch("calculator_workspace.filedialog.asksaveasfilename", return_value=str(filename)):
            view.save_recipe()
        saved = json.loads(filename.read_text(encoding="utf-8"))
        self.assertEqual((saved["app"], saved["format"]), ("CryptoCalc", 1))
        self.assertTrue(saved["recipe"]["steps"][0]["disabled"])
        view.recipe = []
        view.refresh_recipe()
        with patch("calculator_workspace.filedialog.askopenfilename", return_value=str(filename)):
            view.load_recipe()
        self.assertFalse(view.step_enabled.get())
        view.source.insert("1.0", "Khoor")
        view.run()
        self.wait_result(view)
        self.assertEqual(view.result["output"], "Khoor")
        self.assertEqual(view.result["steps"][0]["status"], "off")

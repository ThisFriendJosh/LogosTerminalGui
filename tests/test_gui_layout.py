"""Composer and module-list layout checks when Tk has a display."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


class LayoutTests(unittest.TestCase):
    def test_compact_layout_and_large_font_keep_input_and_send_visible(self):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            self.skipTest("No display; use xvfb-run for layout checks")
        try:
            import tkinter as tk
            from terminal_gui import TerminalGUI
            window = tk.Tk()
        except (ImportError, tk.TclError if "tk" in locals() else ImportError) as exc:
            self.skipTest("Tk/display unavailable: " + str(exc))
        scratch = Path(__file__).resolve().parents[1] / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            for index in range(20):
                folder = root / "terminals" / f"fixture-{index:02d}"
                folder.mkdir(parents=True)
                manifest = {"schema": "logos-terminal/1", "id": f"fixture-{index:02d}", "name": f"Terminal {index:02d}",
                            "version": "1.0.0", "api_version": "1.0.0", "min_host_version": "1.0.0", "protocol": "text",
                            "command": [sys.executable, "-V"], "actions": [{"id": "input", "label": "Terminal"}]}
                (folder / "terminal.json").write_text(json.dumps(manifest), encoding="utf-8")
            app = TerminalGUI(window, app_root=root)
            try:
                for width, height, font_size in [(1320, 850, 12), (980, 650, 12), (980, 650, 18)]:
                    with self.subTest(width=width, height=height, font_size=font_size):
                        app.body_font.configure(size=font_size)
                        window.geometry(f"{width}x{height}")
                        window.update()
                        window.update_idletasks()
                        self.assertGreater(app.input.winfo_height(), 30)
                        self.assertLessEqual(app.input.winfo_rooty() + app.input.winfo_height(), window.winfo_rooty() + window.winfo_height())
                        self.assertTrue(app.send_button.winfo_ismapped())
                        self.assertLessEqual(app.send_button.winfo_rootx() + app.send_button.winfo_width(), window.winfo_rootx() + window.winfo_width())
                app.module_canvas.yview_moveto(1)
                window.update_idletasks()
                self.assertEqual(len(app.modules), 20)
                self.assertGreater(app.module_canvas.yview()[1], .99)
            finally:
                app.closing = True
                for pending in window.tk.call("after", "info"):
                    window.after_cancel(pending)
                window.destroy()


if __name__ == "__main__":
    unittest.main()

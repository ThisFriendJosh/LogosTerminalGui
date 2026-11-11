"""Composer and module-list layout checks when Tk has a display."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


def pump(window):
    """Bound event processing while a continuously animated window is mapped."""
    import _tkinter
    window.update_idletasks()
    for _ in range(400):
        if not window.tk.dooneevent(_tkinter.DONT_WAIT):
            break
    window.update_idletasks()


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
            app.preferences["effects"] = False
            app.update_effect_label()
            try:
                for theme in (*app.theme_catalog.themes, "logos-classic"):
                    app.apply_theme(theme)
                    for width, height, font_size in [(1320, 850, 12), (980, 650, 12), (980, 650, 18)]:
                      with self.subTest(theme=theme, width=width, height=height, font_size=font_size):
                        app.body_font.configure(size=font_size)
                        window.geometry(f"{width}x{height}")
                        pump(window)
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
                app.outer.destroy()
                for pending in window.tk.call("after", "info"):
                    window.after_cancel(pending)
                window.destroy()

    def test_theme_switch_retains_connection_draft_transcript_and_layout(self):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            self.skipTest("No display; use xvfb-run for theme checks")
        import shutil
        import tkinter as tk
        from terminal_gui import TerminalGUI
        try:
            window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        source = Path(__file__).resolve().parents[1]
        scratch = source / "work"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp:
            root = Path(temp)
            shutil.copy2(source / "terminal_protocol.py", root / "terminal_protocol.py")
            app = TerminalGUI(window, app_root=root)
            app.preferences["effects"] = False
            app.update_effect_label()
            try:
                app.register(source / "terminal_sdk/example/terminal.json")
                app.submit("chat", "Theme connection check")
                deadline = time.monotonic()+8
                while time.monotonic() < deadline and not any("Received:" in t for _, t in app.workspace()["entries"]):
                    pump(window)
                    time.sleep(.015)
                self.assertTrue(app.workspace()["ready"], app.workspace()["logs"])
                self.assertTrue(any("Received:" in t for _, t in app.workspace()["entries"]))
                process = app.processes[app.current]
                original_pid = process.process.pid
                entries = list(app.workspace()["entries"])
                app.hide_placeholder()
                app.input.insert("1.0", "Unsent draft\nsecond line")
                pump(window)
                geometry = [(w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()) for w in (app.sidebar, app.input, app.transcript, app.send_button)]
                for theme in ("galactic-phosphor", "galactic-2", "logos-classic", "galactic-2"):
                    app.apply_theme(theme)
                    pump(window)
                    self.assertEqual(app.input_text(), "Unsent draft\nsecond line")
                    self.assertEqual(app.workspace()["entries"], entries)
                    self.assertEqual(app.processes[app.current].process.pid, original_pid)
                    self.assertIsNone(process.process.poll())
                    self.assertEqual(geometry, [(w.winfo_x(), w.winfo_y(), w.winfo_width(), w.winfo_height()) for w in (app.sidebar, app.input, app.transcript, app.send_button)])
                app.transcript._select_all()
                for theme in ("classic-standard", "classic-light", "classic-dark", "classic-alchemist", "classic-dos", "classic-lovecraft", "classic-matrix"):
                    app.apply_theme(theme)
                    pump(window)
                    preferred = app.theme.data["typography"]["families"][0]
                    if preferred in window.terminal_bundled_font_families:
                        self.assertEqual(app.body_font.actual()["family"].casefold(), preferred.casefold())
                    self.assertEqual(app.input_text(), "Unsent draft\nsecond line")
                    self.assertEqual(app.workspace()["entries"], entries)
                    self.assertEqual(app.processes[app.current].process.pid, original_pid)
                    self.assertIsNone(process.process.poll())
                    self.assertTrue(app.input.winfo_ismapped())
                app.apply_theme("galactic-2")
                pump(window)
                app.transcript._select_all()
                app.transcript._copy()
                self.assertIn("Received: Theme connection check", window.clipboard_get())
                app.toggle_effects()
                app.atmosphere.tick(0)
                app.toggle_effects()
                self.assertFalse(app.preferences["effects"])
                self.assertTrue(all(not layer.sprites for layer in app.atmosphere.layers))
                app.settings()
                pump(window)
                dialog = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == "Workspace settings")
                def children(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from children(child)
                entry = next(w for w in children(dialog) if type(w) is tk.Entry)
                self.assertTrue(entry.winfo_ismapped(), "Reading font field is hidden")
                self.assertGreater(entry.winfo_height(), 20)
                self.assertEqual(entry.get(), str(app.preferences["font_size"]))
                app.inspect_theme(app.theme)
                pump(window)
                inspector = next(w for w in window.winfo_children() if isinstance(w, tk.Toplevel) and "Theme elements" in w.title())
                for button in (w for w in children(inspector) if getattr(w, "label", "") in ("Copy elements", "Export theme")):
                    self.assertTrue(button.winfo_ismapped())
                    self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), inspector.winfo_rooty()+inspector.winfo_height())
                inspector.destroy()
                dialog.destroy()
                saved = []
                editor = app.rain_settings(app.theme, saved.append)
                pump(window)
                controls = [w for w in children(editor) if isinstance(w, tk.Spinbox)]
                self.assertEqual(len(controls), 10)
                for control in controls:
                    self.assertTrue(control.winfo_ismapped())
                controls[0].delete(0, "end")
                controls[0].insert(0, "14")
                save = next(w for w in children(editor) if getattr(w, "label", "") == "Save custom theme")
                self.assertLessEqual(save.winfo_rooty()+save.winfo_height(), editor.winfo_rooty()+editor.winfo_height())
                save.invoke()
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0].rain["column_spacing"], 14)
                app.apply_theme(saved[0].id)
                pump(window)
                self.assertEqual(app.input_text(), "Unsent draft\nsecond line")
                self.assertIsNone(process.process.poll())
            finally:
                app.closing = True
                for process in list(app.processes.values()):
                    process.stop()
                for widget in list(window.winfo_children()):
                    if isinstance(widget, tk.Toplevel):
                        widget.destroy()
                app.outer.destroy()
                for pending in window.tk.call("after", "info"):
                    window.after_cancel(pending)
                window.destroy()


if __name__ == "__main__":
    unittest.main()

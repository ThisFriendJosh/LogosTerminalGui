"""Manage real workers without changing another terminal or losing local drafts."""
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


class ManagerTests(unittest.TestCase):
    def setUp(self):
        if sys.platform != "win32" and not os.environ.get("DISPLAY"):
            self.skipTest("No display; use xvfb-run for manager checks")
        import tkinter as tk
        from terminal_gui import TerminalGUI
        try:
            self.window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        (ROOT/"work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/"work")
        self.root = Path(self.temp.name)
        shutil.copy2(ROOT/"terminal_protocol.py", self.root/"terminal_protocol.py")
        self.app = TerminalGUI(self.window, app_root=self.root)
        self.app.preferences["effects"] = False
        self.app.update_effect_label()
        self.module = self.app.register(ROOT/"terminal_sdk/example/terminal.json")

    def tearDown(self):
        if not hasattr(self, "app"):
            return
        self.destroy_app()
        self.temp.cleanup()

    def destroy_app(self):
        self.app.closing = True
        for process in list(self.app.processes.values()) + list(self.app.stopping_processes.values()):
            process.stop()
        import tkinter as tk
        for widget in list(self.window.winfo_children()):
            if isinstance(widget, tk.Toplevel):
                widget.destroy()
        self.app.outer.destroy()
        for pending in self.window.tk.call("after", "info"):
            self.window.after_cancel(pending)
        self.window.destroy()

    def wait(self, predicate):
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            pump(self.window)
            if predicate():
                return
            time.sleep(.015)
        self.fail("Worker/manager did not reach the expected state")

    def test_connection_reuses_live_worker_reconnect_keeps_draft_and_other_worker(self):
        app = self.app
        record = app.test_connection(self.module.id)
        self.wait(lambda: record["status"] != "checking")
        self.assertEqual(record["status"], "passed", record)
        first = app.processes[self.module.id]
        self.assertEqual(app.workspace()["entries"], [], "Connection check sent a user action")
        with patch.object(first, "send", side_effect=AssertionError("Connection check executed an action")):
            self.assertEqual(app.test_connection(self.module.id)["status"], "passed")
        self.assertIs(app.processes[self.module.id], first)
        self.assertEqual(first.pending_ids, set())
        data = json.loads(self.module.path.read_text())
        data.update(id="second-echo", name="Second terminal", command=["{python}", "-u", str(ROOT/"terminal_sdk/worker_template.py")])
        path = self.root/"second.json"
        path.write_text(json.dumps(data))
        app.register(path)
        app.test_connection("second-echo")
        self.wait(lambda: app.workspace("second-echo")["ready"])
        second = app.processes["second-echo"]
        app.select_module(self.module.id)
        app.append(self.module.id, "assistant", "Keep transcript")
        app.hide_placeholder()
        app.input.insert("1.0", "Keep unsent draft")
        entries = list(app.workspace()["entries"])
        session = app.preferences["sessions"][self.module.id]
        app.reconnect_module(self.module.id)
        self.wait(lambda: self.module.id in app.processes and app.workspace()["ready"])
        self.assertIsNot(app.processes[self.module.id], first)
        self.assertIsNotNone(first.process.poll())
        self.assertIsNone(second.process.poll())
        self.assertEqual(app.input_text(), "Keep unsent draft")
        self.assertEqual(app.workspace()["entries"], entries)
        self.assertEqual(app.preferences["sessions"][self.module.id], session)

    def test_failed_stop_does_not_start_a_second_worker_and_remains_owned(self):
        app = self.app
        record = app.test_connection(self.module.id)
        self.wait(lambda: record["status"] != "checking")
        previous = app.processes[self.module.id]
        with patch.object(previous, "stop", side_effect=OSError("Fixture stop failed")):
            app.reconnect_module(self.module.id)
            self.wait(lambda: self.module.id not in app.reconnecting)
        self.assertNotIn(self.module.id, app.processes)
        self.assertIs(app.stopping_processes[previous.generation], previous)
        self.assertIsNone(previous.process.poll())
        self.assertIn("Fixture stop failed", app.workspace()["last_error"])
        app.test_connection(self.module.id)
        self.assertNotIn(self.module.id, app.processes)
        previous.stop()
        self.wait(lambda: self.module.id in app.processes and app.workspace()["ready"])
        self.assertIsNot(app.processes[self.module.id], previous)
        self.assertIsNotNone(previous.process.poll())

    def test_order_unload_all_restart_and_reload_preserve_saved_data(self):
        app = self.app
        other = app.register(ROOT/"terminals/scratchpad/terminal.json")
        app.move_module(other.id, -1)
        self.assertEqual(list(app.modules), [other.id, self.module.id])
        marker = self.root/"state/terminal-modules/scratchpad/notes.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("Saved notes must survive")
        app.select_module(other.id)
        app.hide_placeholder()
        app.input.insert("1.0", "Reload this draft")
        app.unload_module(other.id)
        app.unload_module(self.module.id)
        self.assertIsNone(app.current)
        app.apply_theme("galactic-2")
        self.assertIsNone(app.current)
        self.assertTrue(marker.exists())
        from terminal_core import read_preferences
        saved = read_preferences(app.preference_path)
        self.assertEqual(set(saved["hidden_modules"]), {other.id, self.module.id})
        self.assertEqual(saved["modules"], [])
        app.register(other.path)
        self.assertEqual(app.input_text(), "Reload this draft")
        self.assertNotIn(other.id, app.preferences["hidden_modules"])
        self.assertEqual(marker.read_text(), "Saved notes must survive")

    def test_manager_layout_setup_failure_and_reviewed_report_export(self):
        app = self.app
        logos = app.register(ROOT/"terminals/logosmind/terminal.json")
        manager = app.terminal_manager()
        manager.dialog.geometry("860x570")
        pump(self.window)
        for button in manager.buttons.values():
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), manager.dialog.winfo_rootx()+manager.dialog.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), manager.dialog.winfo_rooty()+manager.dialog.winfo_height())
        app.test_connection(logos.id)
        self.wait(lambda: app.connection_checks[logos.id]["status"] != "checking")
        self.assertEqual(app.connection_checks[logos.id]["status"], "failed")
        manager.refresh_details()
        self.assertIn("Terminal settings", manager.details.get("1.0", "end"))
        app.workspace()["input"] = "PRIVATE DRAFT"
        app.workspace()["logs"] = ["PRIVATE LOG"]
        dialog = manager.report_dialog()
        pump(self.window)
        reviewed = dialog.report_preview.get("1.0", "end-1c")
        self.assertNotIn("PRIVATE DRAFT", reviewed)
        self.assertNotIn("PRIVATE LOG", reviewed)
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        save = next(w for w in children(dialog) if getattr(w, "label", "") == "Save report")
        destination = self.root/"tester-report.json"
        with patch("terminal_manager.filedialog.asksaveasfilename", return_value=str(destination)):
            save.invoke()
        self.assertEqual(json.loads(destination.read_text()), json.loads(reviewed))
        self.assertEqual(json.loads(reviewed)["schema"], "logos-terminal-diagnostics/1")

    def test_sidebar_order_and_unloaded_bundled_module_survive_restart(self):
        app = self.app
        paths = {}
        for identifier in ("bundled-a", "bundled-b"):
            folder = self.root/"terminals"/identifier
            folder.mkdir(parents=True)
            data = json.loads(self.module.path.read_text())
            data.update(id=identifier, command=["{python}", "-u", str(ROOT/"terminal_sdk/worker_template.py")])
            paths[identifier] = folder/"terminal.json"
            paths[identifier].write_text(json.dumps(data))
            app.register(paths[identifier])
        app.move_module("bundled-b", -1)
        app.move_module("bundled-b", -1)
        app.unload_module("bundled-a")
        expected = list(app.modules)
        self.destroy_app()
        import tkinter as tk
        from terminal_gui import TerminalGUI
        self.window = tk.Tk()
        self.app = TerminalGUI(self.window, app_root=self.root)
        self.assertEqual(list(self.app.modules), expected)
        self.assertNotIn("bundled-a", self.app.modules)
        self.assertTrue(paths["bundled-a"].exists())
        self.app.register(paths["bundled-a"])
        self.assertIn("bundled-a", self.app.modules)

    def restart_app(self):
        self.destroy_app()
        import tkinter as tk
        from terminal_gui import TerminalGUI
        self.window = tk.Tk()
        self.app = TerminalGUI(self.window, app_root=self.root)

    def test_new_folders_require_explicit_load_and_browse_starts_in_terminals(self):
        folder = self.root / "terminals" / "new-terminal"
        folder.mkdir(parents=True)
        manifest = json.loads(self.module.path.read_text(encoding="utf-8"))
        manifest.update(id="new-terminal", name="New terminal", command=["{python}", "-u", str(ROOT / "terminal_sdk/worker_template.py")])
        path = folder / "terminal.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.restart_app()
        self.assertNotIn("new-terminal", self.app.modules)
        dialog = self.app.load_dialog()
        pump(self.window)
        browse = next(w for w in dialog.winfo_children() if getattr(w, "label", "") == "Browse terminal folders...")
        with patch("terminal_gui.filedialog.askopenfilename", return_value=str(path)) as chooser:
            browse.invoke()
        self.assertEqual(chooser.call_args.kwargs["initialdir"], self.root / "terminals")
        self.assertIn("terminal.json", chooser.call_args.kwargs["title"])
        self.assertIn("new-terminal", self.app.modules)
        self.assertNotIn("new-terminal", self.app.processes)
        self.restart_app()
        self.assertIn("new-terminal", self.app.modules)

    def test_sidebar_unload_and_reload_list_survive_restart_without_file_changes(self):
        app = self.app
        path = self.module.path
        before = path.read_bytes()
        marker = self.root / "state/terminal-modules/sdk-example/saved-data.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("Keep this saved data", encoding="utf-8")
        app.hide_placeholder()
        app.input.insert("1.0", "Keep the draft")
        app.unload_button.invoke()
        self.assertNotIn(self.module.id, app.modules)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(marker.read_text(encoding="utf-8"), "Keep this saved data")
        self.restart_app()
        self.assertNotIn(self.module.id, self.app.modules)
        dialog = self.app.load_dialog()
        pump(self.window)
        reload_button = next(w for w in dialog.winfo_children() if getattr(w, "label", "") == "Reload selected")
        self.assertTrue(reload_button.winfo_ismapped())
        self.assertLessEqual(reload_button.winfo_rooty()+reload_button.winfo_height(), dialog.winfo_rooty()+dialog.winfo_height())
        reload_button.invoke()
        self.assertIn(self.module.id, self.app.modules)
        self.assertNotIn(self.module.id, self.app.processes)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(marker.read_text(encoding="utf-8"), "Keep this saved data")


if __name__ == "__main__":
    unittest.main()

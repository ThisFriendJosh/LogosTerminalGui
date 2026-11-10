"""The DM connector reuses external runtimes and defaults to independent saves."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from terminal_core import TerminalModule, TerminalProcess

ROOT = Path(__file__).resolve().parents[1]


class DungeonConnectorTests(unittest.TestCase):
    def setUp(self):
        (ROOT/"work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/"work")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        with patch.dict(os.environ, {"LOGOS_TERMINAL_SDK_DIR": str(ROOT)}):
            spec = importlib.util.spec_from_file_location("dungeon_connector", ROOT/"terminals/dungeon-master/adapter.py")
            self.adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.adapter)
        self.files = {}
        for key, name in (("worker", "dwa-terminal.exe"), ("server", "llama-server.exe"), ("model", "model.gguf")):
            path = self.root/name
            path.write_text("File marker only; never executed")
            self.files[key] = path

    def test_command_keeps_game_saves_independent_and_uses_selected_files(self):
        command, cwd = self.adapter.command_for({}, self.root/"module-data", "remembered-session", self.files)
        self.assertEqual(command[0], str(self.files["worker"]))
        self.assertEqual(cwd, self.root)
        self.assertEqual(command[command.index("--data-dir")+1], str(self.root/"module-data/game-data"))
        self.assertEqual(command[command.index("--session")+1], "remembered-session")
        self.assertEqual(command[command.index("--gpu-layers")+1], "0")
        self.assertNotIn("--download", command)

    def test_explicit_overrides_and_missing_runtime_are_not_silently_replaced(self):
        config = {"game_folder": str(self.root/"chosen-games"), "gpu_layers": 12}
        command, _ = self.adapter.command_for(config, self.root, "s", self.files)
        self.assertIn(str(self.root/"chosen-games"), command)
        self.assertIn("12", command)
        with self.assertRaisesRegex(ValueError, "dwa-terminal.exe"):
            self.adapter.command_for({"worker": str(self.root/"missing.exe")}, self.root, "s", self.files)
        for value in (True, -1, 1000, "99"):
            with self.assertRaises(ValueError):
                self.adapter.command_for({"gpu_layers": value}, self.root, "s", self.files)

    def test_unconfigured_connector_reports_setup_problem_without_a_model(self):
        events = queue.Queue()
        process = TerminalProcess(TerminalModule.load(ROOT/"terminals/dungeon-master/terminal.json"), ROOT, "test", events)
        # Use a private config path while retaining the host SDK location.
        process.module.command = ["{python}", "-u", str(ROOT/"terminals/dungeon-master/adapter.py"),
                                  "--config", str(self.root/"missing-config.json"), "--data", str(self.root), "--session", "test"]
        self.addCleanup(process.stop)
        process.start()
        while True:
            _, _, event = events.get(timeout=8)
            if event["event"] == "ready":
                break
        self.assertFalse(event["model_available"])
        self.assertIn("dwa-terminal.exe", event["connection_error"])
        self.assertIn("roll", event["capabilities"])
        identifier = process.send("chat", "test action")
        while True:
            _, _, event = events.get(timeout=8)
            if event["event"] == "error":
                break
        self.assertEqual(event["id"], identifier)
        self.assertIsNone(process.process.poll())


if __name__ == "__main__":
    unittest.main()

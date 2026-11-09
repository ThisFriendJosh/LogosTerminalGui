"""Exercise the optional bridge with a fake backend, without model packages."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from terminal_core import TerminalModule, TerminalProcess
import test_terminal

ROOT = Path(__file__).resolve().parents[1]


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        (ROOT / "work").mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=ROOT / "work")
        self.root = Path(self.temporary.name)
        shutil.copyfile(ROOT / "terminal_protocol.py", self.root / "terminal_protocol.py")
        self.processes = []
        with patch.dict(os.environ, {"LOGOS_TERMINAL_SDK_DIR": str(ROOT)}):
            spec = importlib.util.spec_from_file_location("logosmind_bridge", ROOT / "terminals/logosmind/adapter.py")
            self.adapter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.adapter)

    def tearDown(self):
        for process in self.processes:
            process.stop()
        self.temporary.cleanup()

    def start(self):
        events = queue.Queue()
        process = TerminalProcess(TerminalModule.load(ROOT / "terminals/logosmind/terminal.json"), self.root, "test-session", events)
        self.processes.append(process)
        process.start()
        return process, events

    def wait_for(self, events, name):
        while True:
            _, _, event = events.get(timeout=10)
            if event["event"] == name:
                return event

    def project(self, worker=True):
        project = self.root / "Separate backend project"
        project.mkdir(exist_ok=True)
        (project / "logosmind.py").write_text("# Fake backend marker\n", encoding="utf-8")
        if worker:
            supported = repr(self.adapter.ACTIONS)
            script = test_terminal.WORKER.replace("['echo','crash']", supported)
            (project / "lm_terminal_worker.py").write_text(script, encoding="utf-8")
        return project

    def test_unconfigured_connector_has_actionable_setup_error(self):
        process, events = self.start()
        ready = self.wait_for(events, "ready")
        self.assertFalse(ready["model_available"])
        identifier = process.send("chat", "hello")
        error = self.wait_for(events, "error")
        self.assertEqual(error["id"], identifier)
        self.assertIn("Terminal settings", error["text"])
        self.assertIsNone(process.process.poll())

    def test_configured_backend_uses_its_own_interpreter_and_streams(self):
        project = self.project()
        config_path = self.root / "state/terminal-modules/logosmind/settings.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({"project_file": str(project / "logosmind.py"), "python": sys.executable}), encoding="utf-8")
        process, events = self.start()
        self.wait_for(events, "ready")
        identifier = process.send("chat", "independent runtime")
        reply = self.wait_for(events, "result")
        self.assertEqual(reply["id"], identifier)
        self.assertEqual(reply["text"], "independent runtime")
        command, cwd = self.adapter.command_for(json.loads(config_path.read_text()), "test-session")
        self.assertEqual(Path(command[0]), Path(sys.executable))
        self.assertEqual(cwd, project)

    def test_missing_adapter_is_reported_without_modifying_backend(self):
        project = self.project(worker=False)
        with self.assertRaisesRegex(ValueError, "lm_terminal_worker.py"):
            self.adapter.command_for({"project_file": str(project / "logosmind.py")}, "s")
        self.assertEqual(list(project.iterdir()), [project / "logosmind.py"])

    def test_explicit_missing_interpreter_is_not_silently_replaced(self):
        project = self.project()
        with self.assertRaisesRegex(ValueError, "Python interpreter"):
            self.adapter.command_for({"project_file": str(project / "logosmind.py"), "python": str(project / "missing.exe")}, "s")


if __name__ == "__main__":
    unittest.main()

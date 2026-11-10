"""Checks and reports must be useful without executing or disclosing user data."""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from terminal_core import TerminalModule, read_preferences, write_preferences
from terminal_diagnostics import build_report, check, finish_connection_check, preflight, redact, write_report

ROOT = Path(__file__).resolve().parents[1]


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        (ROOT/"work").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/"work")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        data = json.loads((ROOT/"terminal_sdk/example/terminal.json").read_text())
        data["command"] = ["{python}", "-u", str(ROOT/"terminal_sdk/worker_template.py")]
        self.path = self.root/"terminal.json"
        self.path.write_text(json.dumps(data))
        self.module = TerminalModule.load(self.path)

    def test_static_checks_find_missing_files_and_changed_manifests_without_launching(self):
        with patch("subprocess.Popen", side_effect=AssertionError("Static validation executed a program")):
            self.assertTrue(all(c["status"] != "fail" for c in preflight(self.module, self.root)))
            data = json.loads(self.path.read_text())
            data["command"][-1] = str(self.root/"missing.py")
            self.path.write_text(json.dumps(data))
            checks = preflight(TerminalModule.load(self.path), self.root)
            self.assertIn("entry_script", [c["code"] for c in checks if c["status"] == "fail"])
            self.assertIn("manifest_changed", [c["code"] for c in preflight(self.module, self.root)])

    def test_configured_file_and_malformed_settings_are_actionable(self):
        data = json.loads(self.path.read_text())
        data["settings"] = {"file": "{app}/config.json", "fields": [{"key": "python", "label": "Backend Python", "type": "file"}]}
        self.path.write_text(json.dumps(data))
        module = TerminalModule.load(self.path)
        (self.root/"config.json").write_text(json.dumps({"python": str(self.root/"missing.exe")}))
        failed = [c for c in preflight(module, self.root) if c["status"] == "fail"]
        self.assertEqual(failed[0]["code"], "setting_file:python")
        (self.root/"config.json").write_text("[]")
        self.assertIn("settings", [c["code"] for c in preflight(module, self.root) if c["status"] == "fail"])

    def test_python_flags_and_missing_program_are_checked_without_false_failures(self):
        data = json.loads(self.path.read_text())
        script = str(ROOT/"terminal_sdk/worker_template.py")
        for arguments in (["-X", "utf8", "-W", "default", script], ["-m", "some_module"], ["-c", "print('hello')"]):
            data["command"] = ["{python}", *arguments]
            self.path.write_text(json.dumps(data))
            self.assertFalse(any(c["status"] == "fail" for c in preflight(TerminalModule.load(self.path), self.root)))
        data["command"] = [str(self.root/"missing-program.exe")]
        self.path.write_text(json.dumps(data))
        self.assertIn("executable", [c["code"] for c in preflight(TerminalModule.load(self.path), self.root) if c["status"] == "fail"])

    def test_backend_setup_problem_is_not_reported_as_a_successful_connection(self):
        record = {"started": time.monotonic(), "checks": []}
        process = SimpleNamespace(process=SimpleNamespace(poll=lambda: None),
                                  metadata={"connection_error": "Select the backend project", "model_available": False})
        finish_connection_check(record, self.module, process, {})
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["checks"][-1]["code"], "backend")
        self.assertIn("backend project", record["checks"][-1]["detail"])

    def test_text_startup_is_not_claimed_to_have_a_verified_api(self):
        self.module.protocol = "text"
        record = {"started": time.monotonic(), "checks": []}
        finish_connection_check(record, self.module, SimpleNamespace(process=SimpleNamespace(poll=lambda: None)), {})
        self.assertEqual(record["status"], "running")
        self.assertNotIn("handshake", [c["code"] for c in record["checks"]])

    def test_default_report_excludes_free_form_diagnostics_settings_and_conversations(self):
        private = "PRIVATE-CONVERSATION-CONTENT"
        record = {"status": "failed", "checks": [check("connection", "fail", "Connection failed.", private)]}
        state = {"entries": [("user", private)], "input": "PRIVATE-DRAFT", "logs": [private], "last_error": private,
                 "capabilities": ["chat"], "status": private}
        report = build_report({self.module.id: self.module}, self.root, {}, {self.module.id: state}, {self.module.id: record})
        encoded = json.dumps(report)
        self.assertNotIn(private, encoded)
        self.assertNotIn("PRIVATE-DRAFT", encoded)
        self.assertNotIn(str(self.root), encoded)
        self.assertNotIn("command", report["modules"][0])
        self.assertEqual(report["modules"][0]["check"]["status"], "failed")
        self.assertEqual(len(report["modules"][0]["manifest_sha256"]), 64)
        destination = self.root/"report.json"
        write_report(destination, report)
        self.assertEqual(json.loads(destination.read_text()), report)
        self.assertFalse(destination.with_name("report.json.tmp").exists())

    def test_optional_diagnostics_redact_paths_and_common_credentials(self):
        text = str(self.root/"private.json")+" token=secret123 Bearer abcdef999 owner@example.com sk-abcdefghijklmnop"
        report = build_report({self.module.id: self.module}, self.root, {}, {self.module.id: {"logs": [text]}}, {}, include_details=True)
        encoded = json.dumps(report)
        for value in (str(self.root), "secret123", "abcdef999", "owner@example.com", "sk-abcdefghijklmnop"):
            self.assertNotIn(value, encoded)
        self.assertIn("$HOST", encoded)
        self.assertNotIn("sensitive-config-value", redact("value=sensitive-config-value", secrets=["sensitive-config-value"]))

    def test_report_works_when_the_launcher_has_no_home_directory(self):
        with patch("terminal_diagnostics.Path.home", side_effect=RuntimeError("No home")):
            report = build_report({self.module.id: self.module}, self.root, {}, {}, {})
        self.assertEqual(report["schema"], "logos-terminal-diagnostics/1")

    def test_module_order_and_unloaded_ids_survive_preferences_reload(self):
        path = self.root/"preferences.json"
        write_preferences(path, {"module_order": ["b", "a", "b"], "hidden_modules": ["example-echo", None], "sessions": {"a": "keep-this-session"}})
        loaded = read_preferences(path)
        self.assertEqual(loaded["module_order"], ["b", "a"])
        self.assertEqual(loaded["hidden_modules"], ["example-echo"])
        self.assertEqual(loaded["sessions"]["a"], "keep-this-session")


if __name__ == "__main__":
    unittest.main()

"""Original-engine vectors and real terminal protocol tests for both calculators."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from terminal_core import TerminalModule, discover

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
ADAPTER = ROOT / "terminals/_calculator/adapter.py"


class CalculatorManifestTests(unittest.TestCase):
    def test_calculators_are_discovered_without_registering_a_shared_worker(self):
        modules, errors = discover(ROOT)
        self.assertFalse(errors)
        self.assertTrue({"cryptocalc", "statcalc"}.issubset(modules))
        self.assertNotIn("_calculator", modules)

    def test_original_app_bytes_match_source_checksums(self):
        for name in ("cryptocalc", "statcalc"):
            folder = ROOT / "terminals" / name
            manifest = json.loads((folder / "terminal.json").read_text(encoding="utf-8"))
            TerminalModule.load(folder / "terminal.json")
            self.assertEqual(hashlib.sha256((folder / "app.html").read_bytes()).hexdigest(),
                             manifest["extensions"]["calculator"]["source_sha256"])


@unittest.skipUnless(NODE, "Node.js 22+ is required for calculator engine tests")
class CalculatorEngineTests(unittest.TestCase):
    def exchange(self, module, calls):
        requests = [{"jsonrpc": "2.0", "id": "init", "method": "initialize",
                     "params": {"protocolVersion": "1.0.0"}}]
        requests += [{"jsonrpc": "2.0", "id": str(i), "method": "terminal/execute",
                      "params": {"action": action, "input": {"text": text}}}
                     for i, (action, text) in enumerate(calls)]
        env = dict(os.environ, LOGOS_TERMINAL_SDK_DIR=str(ROOT))
        result = subprocess.run([sys.executable, str(ADAPTER), "--module", str(ROOT / "terminals" / module)],
                                input="".join(json.dumps(r) + "\n" for r in requests),
                                capture_output=True, encoding="utf-8", timeout=60, env=env,
                                cwd=ROOT.parent)
        self.assertEqual(result.returncode, 0, result.stderr)
        frames = [json.loads(line) for line in result.stdout.splitlines()]
        responses = [frame for frame in frames if "id" in frame]
        self.assertEqual(len(responses), len(requests))
        self.assertEqual([r["id"] for r in responses], [r["id"] for r in requests])
        self.assertNotIn("connection_error", responses[0]["result"]["metadata"])
        return responses[1:]

    def test_base64_unicode_recipe_sha256_and_bad_operation_recovery(self):
        recipe = json.dumps({"input": "Hello \u03bb", "steps": [{"op": "to_base64"}, {"op": "from_base64"}]})
        replies = self.exchange("cryptocalc", [("run", "to_base64 Hello"), ("run", recipe),
            ("run", "sha256 abc"), ("run", "does_not_exist text"), ("run", "from_base64 SGVsbG8="),
            ("operations", "base64")])
        self.assertTrue(replies[0]["result"]["text"].startswith("SGVsbG8="))
        self.assertTrue(replies[1]["result"]["text"].startswith("Hello \u03bb"))
        self.assertIn(hashlib.sha256(b"abc").hexdigest(), replies[2]["result"]["text"])
        self.assertEqual(replies[3]["error"]["code"], -32602)
        self.assertTrue(replies[4]["result"]["text"].startswith("Hello"))
        self.assertIn("from_base64", replies[5]["result"]["text"])

    def test_numeric_summary_intervals_and_linear_correlation(self):
        replies = self.exchange("statcalc", [("json", "1,2,3,4,5"),
            ("json", "x,y\n1,2\n2,4\n3,6\n4,8"), ("analyze", "1,2,3,4,5")])
        single = json.loads(replies[0]["result"]["text"])
        self.assertEqual(single["reports"][0]["summary"]["mean"], 3)
        self.assertEqual(single["reports"][0]["summary"]["variance"], 2.5)
        interval = single["reports"][0]["intervals"][0]
        self.assertAlmostEqual(interval["lower"], 1.036756839, places=6)
        pair = json.loads(replies[1]["result"]["text"])["pairs"][0]
        self.assertEqual(pair["r"], 1)
        self.assertEqual(pair["slope"], 2)
        self.assertIn("mean: 3", replies[2]["result"]["text"])

    def test_categories_custom_confidence_and_invalid_input_recovery(self):
        config = json.dumps({"data": "color\nred\nblue\nred", "confidence": 99})
        replies = self.exchange("statcalc", [("json", config), ("analyze", ""),
            ("json", '{"data":"1,2,3","confidence":100}'), ("json", "1 2 3")])
        result = json.loads(replies[0]["result"]["text"])
        self.assertEqual(result["level"]["percent"], 99)
        self.assertEqual(result["reports"][0]["summary"]["distinctCount"], 2)
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertEqual(replies[2]["error"]["code"], -32602)
        self.assertEqual(json.loads(replies[3]["result"]["text"])["reports"][0]["summary"]["mean"], 2)

    def test_help_and_no_response_for_notifications(self):
        for module in ("cryptocalc", "statcalc"):
            self.assertIn("Node.js", self.exchange(module, [("help", "")])[0]["result"]["text"])
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1.0.0"}},
            {"jsonrpc": "2.0", "method": "terminal/execute", "params": {"action": "help", "input": {}}},
        ]
        result = subprocess.run([sys.executable, str(ADAPTER), "--module", str(ROOT / "terminals/cryptocalc")],
                                input="".join(json.dumps(m) + "\n" for m in messages),
                                capture_output=True, encoding="utf-8", timeout=10)
        self.assertEqual(len(result.stdout.splitlines()), 1)

"""Contract and real stdio transport tests. No model, network or GUI dependency."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import time
import unittest

from terminal_core import TerminalModule, TerminalProcess, discover, read_preferences, write_preferences
from terminal_protocol import HOST_VERSION, Channel, ProtocolError, parse_request, parse_server_message, strict_json, validate_payload, version

ROOT = Path(__file__).resolve().parent

WORKER = '''import json,os,sys
sys.path.insert(0,os.environ['LOGOS_TERMINAL_SDK_DIR'])
from terminal_protocol import Channel
c=Channel();c.emit('ready',model='Test worker')
for line in sys.stdin:
 try:
  accepted=c.accept(line,['echo','crash'],'Fixture','1.0.0')
  if accepted is None:continue
  identifier,action,payload=accepted
  if action=='crash':sys.exit(7)
  c.emit('status',id=identifier,text='Working')
  c.emit('result',id=identifier,kind='source',text=payload.get('text',''))
 except Exception as e:c.emit('error',id=c.last_id,text=str(e),code=getattr(e,'code',-32000))
'''


class ContractTests(unittest.TestCase):
    def channel_call(self, channel, value, actions=("echo",)):
        capture = io.StringIO()
        with redirect_stdout(capture):
            accepted = channel.accept(json.dumps(value), actions, "Fixture", "1.0.0")
        lines = [json.loads(x) for x in capture.getvalue().splitlines()]
        return accepted, lines

    def test_jsonrpc_initialize_has_matching_id_and_capabilities(self):
        c = Channel()
        accepted, lines = self.channel_call(c, {"jsonrpc":"2.0", "id":"test-init", "method":"initialize", "params":{"protocolVersion":"1.0.0"}})
        self.assertIsNone(accepted)
        self.assertEqual(lines[0]["id"], "test-init")
        self.assertEqual(lines[0]["result"]["capabilities"]["actions"], ["echo"])

    def test_execution_before_initialize_is_rejected(self):
        with self.assertRaises(ProtocolError) as caught:
            Channel().accept('{"jsonrpc":"2.0","id":"one","method":"terminal/execute","params":{"action":"echo","input":{}}}', ["echo"], "Fixture", "1.0.0")
        self.assertEqual(caught.exception.code, -32002)

    def test_execution_preserves_id_and_input(self):
        c=Channel();c.initialized=True
        accepted, lines = self.channel_call(c, {"jsonrpc":"2.0","id":"request-17","method":"terminal/execute","params":{"action":"echo","input":{"text":"λόγος"}}})
        self.assertEqual(accepted, ("request-17", "echo", {"text":"λόγος"}))
        self.assertEqual(lines, [])

    def test_notifications_do_not_receive_responses(self):
        c=Channel();c.initialized=True
        self.channel_call(c, {"jsonrpc":"2.0","method":"terminal/execute","params":{"action":"echo","input":{}}})
        capture=io.StringIO()
        with redirect_stdout(capture):
            c.emit("result", id=None, kind="source", text="done")
            c.emit("error", id=None, text="ignored notification error")
        self.assertEqual(capture.getvalue(), "")

    def test_error_response_has_code_message_and_id(self):
        c=Channel(); capture=io.StringIO()
        with redirect_stdout(capture): c.error("abc", "Missing reference", -32602)
        response=json.loads(capture.getvalue())
        self.assertEqual(response, {"jsonrpc":"2.0","id":"abc","error":{"code":-32602,"message":"Missing reference"}})

    def test_progress_is_a_notification(self):
        capture=io.StringIO()
        with redirect_stdout(capture): Channel().emit("status", id="abc", text="Working")
        response=json.loads(capture.getvalue())
        self.assertNotIn("id", response)
        self.assertEqual(response["method"], "terminal/status")
        self.assertEqual(response["params"]["id"], "abc")

    def test_invalid_json_and_nonfinite_numbers_are_rejected(self):
        for value in ['{', '{"jsonrpc":"2.0","method":"x","params":{"value":NaN}}']:
            with self.assertRaises(ProtocolError) as caught: parse_request(value)
            self.assertEqual(caught.exception.code, -32700)

    def test_invalid_response_envelopes_are_rejected(self):
        invalid=[{}, {"jsonrpc":"2.0","id":"a","result":{},"error":{}},
                 {"jsonrpc":"2.0","id":"a","error":{"code":True,"message":"bad"}},
                 {"jsonrpc":"2.0","method":"terminal/status","id":"bad","params":{}}]
        for value in invalid:
            with self.assertRaises(ProtocolError): parse_server_message(value)

    def test_malformed_render_payloads_are_rejected(self):
        for value in [{"text":17},{"kind":"history","messages":[{"role":"user","content":None}]},{"kind":"session_list","items":["invalid"]},{"translations":"KJV"},{"audit":False}]:
            with self.assertRaises(ProtocolError):validate_payload(value)

    def test_semantic_version_is_not_lexicographic(self):
        self.assertGreater(version("1.10.0"), version("1.2.0"))
        for value in ["1", "01.0.0", "1.0.0x"]:
            with self.assertRaises(ValueError):version(value)


class ModuleTests(unittest.TestCase):
    def setUp(self):
        (ROOT/"work").mkdir(exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=ROOT/"work")
        self.root=Path(self.temporary.name)
        shutil.copy2(ROOT/"terminal_protocol.py",self.root/"terminal_protocol.py")
        (self.root/"worker.py").write_text(WORKER,encoding="utf-8")
        self.path=self.root/"terminal.json"
        self.data={"schema":"logos-terminal/1","id":"fixture","name":"Test Terminal","version":"1.0.0","api_version":"1.0.0","min_host_version":"1.0.0","protocol":"jsonrpc","command":["{python}","-u","{module}/worker.py"],"cwd":"{module}","actions":[{"id":"echo","label":"Echo"}]}
        self.save_manifest()
        self.workers=[]

    def tearDown(self):
        for process in self.workers: process.stop()
        self.temporary.cleanup()

    def save_manifest(self):
        self.path.write_text(json.dumps(self.data),encoding="utf-8")

    def worker(self):
        events=queue.Queue()
        worker=TerminalProcess(TerminalModule.load(self.path),self.root,"fixture-session",events)
        self.workers.append(worker);worker.start()
        return worker,events

    def wait_for(self,events,event_name,timeout=8):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            _,_,value=events.get(timeout=max(.1,deadline-time.monotonic()))
            if value["event"]==event_name:return value
        self.fail("Expected terminal event: "+event_name)

    def test_bundled_manifests_are_valid_and_independent(self):
        modules,errors=discover(ROOT)
        self.assertFalse(errors)
        self.assertEqual(set(modules),{"logosmind","scratchpad","dungeon-master"})
        self.assertNotEqual(modules["logosmind"].command,modules["scratchpad"].command)

    def test_incompatible_api_and_host_versions_are_blocked(self):
        host = version(HOST_VERSION)
        future_host = f"{host[0]}.{host[1]+1}.0"
        for key,value in [("api_version","2.0.0"),("min_host_version",future_host)]:
            original=self.data[key];self.data[key]=value;self.save_manifest()
            with self.assertRaises(ValueError):TerminalModule.load(self.path)
            self.data[key]=original

    def test_duplicate_actions_and_invalid_flags_are_rejected(self):
        self.data["actions"]*=2;self.save_manifest()
        with self.assertRaises(ValueError):TerminalModule.load(self.path)
        self.data["actions"]=[{"id":"echo","label":"Echo","allow_empty":"yes"}];self.save_manifest()
        with self.assertRaises(ValueError):TerminalModule.load(self.path)

    def test_string_command_and_missing_required_fields_are_rejected(self):
        original=self.data["command"];self.data["command"]="python worker.py";self.save_manifest()
        with self.assertRaises(ValueError):TerminalModule.load(self.path)
        self.data["command"]=original;del self.data["version"];self.save_manifest()
        with self.assertRaises(ValueError):TerminalModule.load(self.path)

    def test_duplicate_module_ids_do_not_replace_existing_module(self):
        other=self.root/"other.json";other.write_text(json.dumps(self.data))
        modules,errors=discover(self.root,[self.path,other])
        self.assertEqual(len(modules),1);self.assertTrue(errors)
        self.assertEqual(modules["fixture"].path,self.path)

    def test_templates_are_resolved_with_separate_data_directory(self):
        self.data["command"].append("{data}");self.save_manifest()
        argv,cwd=TerminalModule.load(self.path).launch(self.root,"session")
        self.assertEqual(Path(argv[-1]),self.root/"state/terminal-modules/fixture")
        self.assertEqual(cwd,self.root)

    def test_logosmind_module_paths_are_independent_of_host_folder(self):
        module=TerminalModule.load(ROOT/"terminals/logosmind/terminal.json")
        argv,cwd=module.launch(self.root,"portable-session")
        self.assertEqual(cwd,ROOT/"terminals/logosmind")
        self.assertEqual(Path(argv[2]).resolve(),ROOT/"terminals/logosmind/adapter.py")

    def test_module_load_does_not_execute_code(self):
        TerminalModule.load(self.path)
        self.assertFalse((self.root/"state").exists())

    def test_bad_settings_are_rejected_before_ui_render(self):
        for settings in ["string", {"file":"test.json","fields":[{"key":"x","label":"X","type":"code"}]}]:
            self.data["settings"]=settings;self.save_manifest()
            with self.assertRaises(ValueError):TerminalModule.load(self.path)

    def test_stdio_handshake_utf8_progress_and_request_ids(self):
        worker,events=self.worker()
        ready=self.wait_for(events,"ready")
        self.assertIn("echo",ready["capabilities"])
        request_id=worker.send("echo","λόγος • אמת")
        progress=self.wait_for(events,"status")
        result=self.wait_for(events,"result")
        self.assertEqual(progress["id"],request_id)
        self.assertEqual(result["id"],request_id)
        self.assertEqual(result["text"],"λόγος • אמת")

    def test_module_advertisement_must_cover_declared_actions(self):
        self.data["actions"].append({"id":"missing","label":"Missing"});self.save_manifest()
        worker,events=self.worker()
        error=self.wait_for(events,"error")
        self.assertIn("advertise",error["text"])

    def test_incompatible_worker_handshake_is_rejected(self):
        (self.root/"worker.py").write_text("import json,sys\nfor line in sys.stdin:\n q=json.loads(line);print(json.dumps({'jsonrpc':'2.0','id':q['id'],'result':{'protocolVersion':'2.0.0'}}),flush=True)\n")
        worker,events=self.worker()
        self.assertIn("incompatible",self.wait_for(events,"error")["text"])

    def test_unknown_action_returns_structured_error_without_killing_worker(self):
        worker,events=self.worker();self.wait_for(events,"ready")
        worker.send("missing")
        self.assertEqual(self.wait_for(events,"error")["code"],-32602)
        worker.send("echo","still working")
        self.assertEqual(self.wait_for(events,"result")["text"],"still working")

    def test_crashing_worker_does_not_affect_another_worker(self):
        first,one=self.worker();self.wait_for(one,"ready")
        second,two=self.worker();self.wait_for(two,"ready")
        first.send("crash");self.assertEqual(self.wait_for(one,"exit")["code"],7)
        second.send("echo","alive");self.assertEqual(self.wait_for(two,"result")["text"],"alive")

    def test_plain_text_adapter_handles_prompt_without_newline(self):
        (self.root/"plain.py").write_text("import sys\nsys.stdout.write('ready> ');sys.stdout.flush()\nfor line in sys.stdin: print('echo:'+line.strip(),flush=True)\n")
        self.data.update(protocol="text",command=["{python}","-u","{module}/plain.py"]);self.save_manifest()
        worker,events=self.worker();self.wait_for(events,"ready")
        self.assertIn("ready>",self.wait_for(events,"stream")["text"])
        worker.send("input","hello")
        self.assertIn("echo:hello",self.wait_for(events,"stream")["text"])

    @unittest.skipUnless(os.name=="nt","Windows batch adapter")
    def test_batch_adapter_handles_paths_containing_spaces(self):
        directory=self.root/"space folder";directory.mkdir()
        script=directory/"echo terminal.cmd";script.write_text("@echo off\necho batch-ready\nset /p value=\necho received\n",encoding="ascii")
        self.data.update(protocol="text",command=[str(script)]);self.save_manifest()
        worker,events=self.worker();self.wait_for(events,"ready")
        self.assertIn("batch-ready",self.wait_for(events,"stream")["text"])
        worker.send("input","hello")
        text=self.wait_for(events,"stream")["text"]
        self.assertIn("received",text)

    def test_sdk_example_can_initialize_from_a_different_host_folder(self):
        module=TerminalModule.load(ROOT/"terminal_sdk/example/terminal.json")
        events=queue.Queue();worker=TerminalProcess(module,self.root,"example",events)
        self.workers.append(worker);worker.start();self.wait_for(events,"ready")
        worker.send("chat","independent")
        self.assertEqual(self.wait_for(events,"result")["text"],"Received: independent")

    def test_preferences_recover_from_malformed_values(self):
        path=self.root/"prefs.json"
        path.write_text('{"font_size":"bad","modules":"bad","sessions":[],"effects":"false"}')
        prefs=read_preferences(path)
        self.assertEqual(prefs["font_size"],12);self.assertEqual(prefs["modules"],[])
        self.assertEqual(prefs["sessions"],{});self.assertTrue(prefs["effects"])

    def test_preferences_and_sessions_persist_without_overwriting_other_keys(self):
        path=self.root/"state/prefs.json";prefs=read_preferences(path)
        prefs["modules"]=[str(self.path)];prefs["sessions"]={"fixture":"persistent"};prefs["effects"]=False
        write_preferences(path,prefs)
        self.assertEqual(read_preferences(path),prefs)


if __name__=="__main__":
    unittest.main()

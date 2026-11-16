import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import services


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.processes = {
            "vm": {},
            "db": {"depends_on": {"vm": {"condition": "process_healthy"}}},
            "api": {"depends_on": {"db": {"condition": "process_healthy"}}},
            "other": {},
        }

    def test_dependency_order(self):
        self.assertEqual(services.ordered(self.processes, ["api"]), ["vm", "db", "api"])

    def test_reverse_dependents_excludes_unrelated(self):
        self.assertEqual(services.dependents(self.processes, ["vm"]), ["api", "db", "vm"])

    def test_missing_dependency(self):
        with self.assertRaisesRegex(services.ServiceError, "Unknown"):
            services.ordered({"a": {"depends_on": {"missing": {}}}})

    def test_cycle(self):
        with self.assertRaisesRegex(services.ServiceError, "cycle"):
            services.ordered({"a": {"depends_on": {"b": {}}}, "b": {"depends_on": {"a": {}}}})

    def test_local_override_and_explicit_deletion(self):
        self.assertEqual(services.merge({"a": {"x": 1, "y": 2}, "env": ["A=1"]},
                                        {"a": {"x": None, "z": 3}, "env": ["B=2"]}),
                         {"a": {"y": 2, "z": 3}, "env": ["B=2"]})

    def test_failed_dependent_stop_never_stops_dependency(self):
        manager = services.Manager({"project": {"processes": self.processes}})
        calls = []
        with patch.object(services, "states", return_value={"api": {"status": "Running"}}), \
             patch.object(services, "pc", side_effect=lambda *args, **kwargs: calls.append(args)), \
             patch.object(manager, "event"), \
             patch.object(manager, "wait", side_effect=services.ServiceError("still running")):
            with self.assertRaisesRegex(services.ServiceError, "still running"):
                manager.stop(["vm"])
        self.assertEqual(calls, [("process", "stop", "api")])

    def test_failed_external_stop_check_never_stops_dependency(self):
        processes = {"vm": {}, "db": {"depends_on": {"vm": {}}, "x-service": {"stopped_check": "false"}}}
        manager = services.Manager({"project": {"processes": processes}})
        with patch.object(services, "states", return_value={"vm": {"status": "Running"}}), \
             patch.object(services, "pc") as command:
            with self.assertRaisesRegex(services.ServiceError, "stop did not succeed"):
                manager.stop(["vm"])
        command.assert_not_called()

    def test_explicitly_stopped_process_skips_external_check(self):
        # An externally owned resource (e.g. a VM started by another login agent)
        # must never block an explicit stop, reload, or supervisor shutdown.
        processes = {"vm": {"x-service": {"stopped_check": "false"}}}
        manager = services.Manager({"project": {"processes": processes}})
        with patch.object(services, "states", return_value={}), \
             patch.object(services, "pc") as command, \
             patch.object(manager, "wait") as wait:
            manager.stop(["vm"])
        command.assert_not_called()
        wait.assert_not_called()


class ProcessComposeIntegration(unittest.TestCase):
    """Real Process Compose, isolated directories and disposable fixture processes."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("process-compose"):
            raise unittest.SkipTest("process-compose not installed")
        base = Path(os.environ.get("TMPDIR", "/tmp")) / "opencode"
        base.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="service-tests-", dir=base)
        cls.root = Path(cls.temporary.name)
        cls.config = cls.root / "config"
        cls.state = cls.root / "state"
        cls.shared = cls.config / "definitions"
        cls.local = cls.root / "local"
        cls.shared.mkdir(parents=True)
        cls.local.mkdir()
        cls.state.mkdir()
        cls.events = cls.root / "events"
        cls.fixture = cls.root / "fixture.py"
        cls.fixture.write_text(
            "import pathlib, signal, sys, time\n"
            "name, root = sys.argv[1], pathlib.Path(sys.argv[2])\n"
            "def stop(*args):\n"
            "    with (root / 'events').open('a') as f: f.write(name + '\\n')\n"
            "    (root / (name + '.ready')).unlink(missing_ok=True)\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "(root / (name + '.ready')).touch()\n"
            "while True: time.sleep(0.1)\n"
        )
        processes = {}
        for name in ("db", "worker"):
            processes[name] = {
                "command": "exec " + shlex.join([sys.executable, str(cls.fixture), name, str(cls.root)]),
                "readiness_probe": {"exec": {"command": "test -e " + shlex.quote(str(cls.root / (name + ".ready")))},
                                    "period_seconds": 1, "failure_threshold": 10},
                "shutdown": {"signal": 15, "timeout_seconds": 5},
                "x-service": {"start_timeout": 15},
            }
        processes["worker"]["depends_on"] = {"db": {"condition": "process_healthy"}}
        processes["action"] = {"command": "echo action >> " + shlex.quote(str(cls.root / "actions")),
                               "x-service": {"kind": "action"}}
        (cls.shared / "base.yaml").write_text(yaml.safe_dump({"processes": processes}))
        (cls.config / "config.yaml").write_text(yaml.safe_dump({"definition_dirs": [str(cls.shared), str(cls.local)]}))
        (cls.state / "autostart.json").write_text('{"enabled": []}')
        cls.env = {**os.environ, "SERVICES_CONFIG_HOME": str(cls.config), "SERVICES_STATE_HOME": str(cls.state),
                   "SERVICES_DATA_HOME": str(cls.root / "data")}
        cls.output = (cls.root / "supervisor.log").open("w")
        cls.supervisor = subprocess.Popen([sys.executable, str(ROOT / "services.py"), "serve"],
                                         env=cls.env, stdout=cls.output, stderr=cls.output)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            status = cls.cli("status", "--json", check=False)
            if status.returncode == 0 and not json.loads(status.stdout).get("error"):
                return
            if cls.supervisor.poll() is not None:
                break
            time.sleep(0.2)
        cls.output.flush()
        details = (cls.root / "supervisor.log").read_text()
        for logfile in (cls.state / "logs").glob("*.log"):
            details += f"\n{logfile.name}:\n" + logfile.read_text()
        cls.tearDownClass()
        raise RuntimeError("Isolated supervisor failed to start:\n" + details)

    @classmethod
    def cli(cls, *args, check=True):
        result = subprocess.run([sys.executable, str(ROOT / "services.py"), *args], env=cls.env,
                                text=True, capture_output=True, timeout=60)
        if check and result.returncode:
            raise AssertionError(f"svc {' '.join(args)}: {result.stdout}\n{result.stderr}")
        return result

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "supervisor"):
            cls.supervisor.terminate()
            try:
                cls.supervisor.wait(timeout=30)
            except subprocess.TimeoutExpired:
                cls.supervisor.kill()
                cls.supervisor.wait()
        if hasattr(cls, "output"):
            cls.output.close()
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_full_lifecycle(self):
        initial = json.loads(self.cli("status", "--json").stdout)
        self.assertFalse(any(row["active"] for row in initial["services"]))
        self.cli("start", "worker")
        running = json.loads(self.cli("status", "--json").stdout)
        self.assertEqual({row["name"] for row in running["services"] if row["active"]}, {"db", "worker"})
        self.cli("enable", "worker")
        self.cli("disable", "worker")
        self.assertTrue((self.root / "worker.ready").exists())
        self.cli("stop", "db")
        self.assertEqual(self.events.read_text().splitlines()[-2:], ["worker", "db"])
        self.cli("start", "action")
        self.cli("start", "action")
        self.assertEqual((self.root / "actions").read_text().splitlines(), ["action", "action"])
        self.cli("start", "worker")
        self.cli("restart", "db")
        self.assertEqual(self.events.read_text().splitlines()[-2:], ["worker", "db"])
        self.assertTrue((self.root / "worker.ready").exists())
        invalid = self.local / "invalid.yaml"
        invalid.write_text("processes: [\n")
        # A broken edit must never prevent stopping the previously loaded graph.
        self.cli("stop", "db")
        self.assertNotEqual(self.cli("validate", check=False).returncode, 0)
        invalid.unlink()
        self.cli("start", "worker")
        (self.local / "override.yaml").write_text("processes:\n  worker:\n    x-service:\n      title: Local worker\n")
        self.assertNotEqual(self.cli("start", "db", check=False).returncode, 0)
        self.cli("reload")
        status = json.loads(self.cli("status", "--json").stdout)
        worker = next(row for row in status["services"] if row["name"] == "worker")
        self.assertEqual(worker["title"], "Local worker")
        self.assertTrue(worker["active"])
        self.cli("stop", "all")
        self.assertFalse(any(row["active"] for row in json.loads(self.cli("status", "--json").stdout)["services"]))


if __name__ == "__main__":
    unittest.main()

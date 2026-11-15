import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import start


class StartupTests(unittest.TestCase):
    def invoke(self, state="running", reply=b"OK", foreign_socket=False):
        def result(command, **_kwargs):
            payload = json.dumps([{"State": state}]) if "inspect" in command else ""
            return subprocess.CompletedProcess(command, 0, stdout=payload)

        with patch.dict(os.environ, {"PODMAN_BIN": "/test/podman", "PODMAN_MACHINE": "test-vm"}), \
             patch.object(start.subprocess, "run", side_effect=result) as run, \
             patch.object(start.socket, "socket") as socket, \
             patch.object(start.os.path, "lexists", return_value=foreign_socket), \
             patch.object(Path, "is_symlink", return_value=False):
            socket.return_value.__enter__.return_value.recv.return_value = reply
            start.start()
            return run.call_args_list, socket.return_value.__enter__.return_value

    def test_adopts_existing_vm_and_requests_official_socket_link(self):
        calls, helper = self.invoke()
        self.assertFalse(any("start" in call.args[0] for call in calls))
        helper.sendall.assert_called_once_with(b"GO\n")

    def test_starts_stopped_vm(self):
        calls, _ = self.invoke(state="stopped")
        self.assertTrue(any(call.args[0] == ["/test/podman", "machine", "start", "test-vm"] for call in calls))

    def test_refuses_socket_owned_by_another_runtime(self):
        with self.assertRaisesRegex(RuntimeError, "another runtime"):
            self.invoke(foreign_socket=True)

    def test_reports_failed_helper_request(self):
        with self.assertRaisesRegex(RuntimeError, "could not link"):
            self.invoke(reply=b"NO")


if __name__ == "__main__":
    unittest.main()

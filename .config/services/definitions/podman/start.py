# /// script
# requires-python = ">=3.13"
# dependencies = []
# ///
"""Start/adopt the VM and ask Podman's official helper to link docker.sock."""

import getpass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


def start():
    podman, machine = os.environ["PODMAN_BIN"], os.environ["PODMAN_MACHINE"]

    def state():
        result = subprocess.run([podman, "machine", "inspect", machine],
                                check=True, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)[0]["State"]

    deadline = time.monotonic() + 120
    while state() == "starting":
        if time.monotonic() >= deadline:
            raise RuntimeError("Timed out waiting for the Podman VM to start")
        time.sleep(1)
    if state() != "running":
        subprocess.run([podman, "machine", "start", machine], check=True, timeout=150)

    destination = Path("/var/run/docker.sock")
    target = Path.home() / ".local/share/containers/podman/machine/podman.sock"
    if os.path.lexists(destination):
        if not destination.is_symlink() or destination.resolve() != target.resolve():
            raise RuntimeError("/var/run/docker.sock belongs to another runtime; refusing to replace it")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as helper:
        helper.settimeout(8)
        helper.connect(f"/var/run/podman-helper-{getpass.getuser()}.socket")
        helper.sendall(b"GO\n")
        if helper.recv(32).strip() != b"OK":
            raise RuntimeError("Podman's socket helper could not link /var/run/docker.sock")
    print(f"{machine} started; Docker-compatible socket linked", flush=True)


if __name__ == "__main__":
    try:
        start()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Podman startup: {exc}", file=sys.stderr)
        sys.exit(1)

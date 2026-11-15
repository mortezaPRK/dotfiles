# /// script
# requires-python = ">=3.13"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Run setup hooks and install the service supervisor."""
import json
import os
from pathlib import Path
import plistlib
import subprocess

from services import CONFIG, DATA, STATE, definition_dirs, discover

for path in (DATA / "definitions", STATE / "generated", STATE / "logs"):
    path.mkdir(parents=True, exist_ok=True)
for path in (STATE, STATE / "generated", STATE / "logs"):
    path.chmod(0o700)

# Definition roots must be trusted: their install.sh hooks are executed.
for directory in definition_dirs():
    for hook in sorted(directory.rglob("install.sh")):
        subprocess.run(["/bin/sh", str(hook)], check=True)

home = Path.home()
subprocess.run([str(home / ".local/bin/svc"), "validate"], check=True)
autostart = STATE / "autostart.json"
if not autostart.exists():
    enabled = sorted(name for name, process in discover()["project"]["processes"].items()
                     if process.get("x-service", {}).get("default_autostart", False))
    autostart.write_text(json.dumps({"enabled": enabled}, indent=2) + "\n")
    autostart.chmod(0o600)

agent = {
    "Label": "dev.mortz.services",
    "ProgramArguments": [str(home / ".local/bin/svc"), "serve"],
    "RunAtLoad": True,
    "KeepAlive": True,
    "ThrottleInterval": 15,
    "ExitTimeOut": 180,
    "ProcessType": "Background",
    "WorkingDirectory": str(home),
    "EnvironmentVariables": {
        "HOME": str(home),
        "PATH": f"{home}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        **{key: os.environ[key] for key in ("SERVICES_CONFIG_HOME", "SERVICES_DATA_HOME", "SERVICES_STATE_HOME") if key in os.environ},
    },
    "StandardOutPath": str(STATE / "logs/supervisor.stdout.log"),
    "StandardErrorPath": str(STATE / "logs/supervisor.stderr.log"),
}
path = home / "Library/LaunchAgents/dev.mortz.services.plist"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(plistlib.dumps(agent))
path.chmod(0o600)

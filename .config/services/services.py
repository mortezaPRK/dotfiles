#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Manage Process Compose services."""

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

import yaml

CONFIG = Path(os.environ.get("SERVICES_CONFIG_HOME", "~/.config/services")).expanduser()
DATA = Path(os.environ.get("SERVICES_DATA_HOME", "~/.local/share/services")).expanduser()
STATE = Path(os.environ.get("SERVICES_STATE_HOME", "~/.local/state/services")).expanduser()
SOCKET = STATE / "pc.sock"
CATALOG = STATE / "generated/catalog.json"
COMPOSE = STATE / "generated/process-compose.yaml"
PC = shutil.which("process-compose") or "/opt/homebrew/bin/process-compose"
ACTIVE = {"Running", "Launched", "Launching", "Pending", "Restarting", "Terminating"}
CONDITIONS = {"process_started", "process_healthy", "process_completed",
              "process_completed_successfully", "process_log_ready"}


class ServiceError(Exception):
    pass


def run(args, timeout=30, check=True, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, **kwargs)
    if check and result.returncode:
        raise ServiceError((result.stderr or result.stdout).strip() or f"Command failed: {args}")
    return result


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("w") as stream:
            os.chmod(temporary, 0o600)
            stream.write(text)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def merge(base, override):
    """Merge maps, replace scalars/lists, delete null keys."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def ordered(processes, selected=None):
    result, visiting, visited = [], set(), set()

    def visit(name):
        if name not in processes:
            raise ServiceError(f"Unknown service/dependency: {name}")
        if name in visiting:
            raise ServiceError(f"Dependency cycle involving {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in sorted(processes[name].get("depends_on", {})):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        result.append(name)

    for name in sorted(processes if selected is None else selected):
        visit(name)
    return result


def dependents(processes, selected):
    selected = set(selected)
    while True:
        expanded = selected | {name for name, proc in processes.items()
                               if selected.intersection(proc.get("depends_on", {}))}
        if expanded == selected:
            return [name for name in reversed(ordered(processes)) if name in selected]
        selected = expanded


def definition_dirs():
    settings = yaml.safe_load((CONFIG / "config.yaml").read_text()) or {}
    roots = settings.get("definition_dirs", [str(CONFIG / "definitions"), str(DATA / "definitions")])
    if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
        raise ServiceError("definition_dirs must be a list of directory paths")
    directories = []
    for root in roots:
        directory = Path(os.path.expandvars(root)).expanduser()
        if not directory.is_absolute():
            directory = CONFIG / directory
        directories.append(directory)
    return directories


def discover():
    project = {"version": "0.5", "name": "personal-services", "processes": {}}
    sources = {}
    for directory in definition_dirs():
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in {".yaml", ".yml"}:
                continue
            document = yaml.safe_load(path.read_text()) or {}
            if not isinstance(document, dict) or not isinstance(document.get("processes", {}), dict):
                raise ServiceError(f"Expected a Process Compose mapping in {path}")
            for name in document.get("processes", {}):
                sources[name] = str(path)
            project = merge(project, document)
    processes = project.get("processes", {})
    if not processes:
        raise ServiceError("No service definitions found")
    for name, proc in processes.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name) or not isinstance(proc, dict):
            raise ServiceError(f"Invalid service definition: {name}")
        if proc.get("replicas", 1) != 1 or proc.get("extends"):
            raise ServiceError(f"{name}: replicas/extends are not supported by this service menu; use file overrides")
        if not isinstance(proc.get("depends_on", {}), dict):
            raise ServiceError(f"{name}: depends_on must be a mapping")
        for dep, rule in proc.get("depends_on", {}).items():
            if not isinstance(rule, dict) or rule.get("condition", "process_started") not in CONDITIONS:
                raise ServiceError(f"{name}: invalid dependency condition for {dep}")
        metadata = proc.get("x-service", {})
        if not isinstance(metadata, dict) or metadata.get("kind", "service") not in {"service", "action"}:
            raise ServiceError(f"{name}: invalid x-service metadata")
        # Apply login choices after supervisor startup.
        proc.pop("is_disabled", None)
        proc["disabled"] = True
        proc.setdefault("working_dir", str(Path.home()))
        proc.setdefault("log_location", str(STATE / "logs" / f"{name}.log"))
        proc.setdefault("log_configuration", {"rotation": {"max_size_mb": 10, "max_backups": 3}})
    ordered(processes)
    fingerprint = hashlib.sha256(json.dumps(project, sort_keys=True).encode()).hexdigest()
    return {"project": project, "sources": sources, "fingerprint": fingerprint}


def save_catalog(catalog):
    # Ensure quiet jobs have a log file.
    for proc in catalog["project"]["processes"].values():
        path = Path(proc["log_location"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch(mode=0o600)
    atomic_write(COMPOSE, yaml.safe_dump(catalog["project"], sort_keys=False))
    atomic_write(CATALOG, json.dumps(catalog, indent=2) + "\n")


def reload_restarts(catalog):
    """Services opting into a restart on reload (`x-service.reload: restart`)."""
    return {name for name, proc in catalog["project"]["processes"].items()
            if proc.get("x-service", {}).get("reload") == "restart"}


def enabled_services():
    path = STATE / "autostart.json"
    if not path.exists():
        return set()
    document = json.loads(path.read_text())
    enabled = document.get("enabled", [])
    if not isinstance(enabled, list) or not all(isinstance(item, str) for item in enabled):
        raise ServiceError(f"Invalid enabled list in {path}")
    return set(enabled)


@contextlib.contextmanager
def operation(label):
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (STATE / "operations.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ServiceError("Another service operation is in progress; wait for it to finish") from None
        atomic_write(STATE / "busy.json", json.dumps({"operation": label, "pid": os.getpid()}))
        try:
            yield
        finally:
            (STATE / "busy.json").unlink(missing_ok=True)


def pc(*args, timeout=30):
    return run([PC, "--use-uds", "--unix-socket", str(SOCKET),
                "--log-file", str(STATE / "logs/client.log"), *args], timeout=timeout)


def states():
    payload = json.loads(pc("process", "list", "--output", "json", timeout=8).stdout)
    rows = payload.get("data", []) if isinstance(payload, dict) else payload
    return {row["name"]: row for row in rows}


def active(row):
    return bool(row.get("is_running")) or row.get("status") in ACTIVE


class Manager:
    def __init__(self, catalog, cancelled=None):
        self.catalog = catalog
        self.processes = catalog["project"]["processes"]
        self.cancelled = cancelled

    def metadata(self, name):
        return self.processes[name].get("x-service", {})

    def environment(self, name):
        env = os.environ.copy()
        for item in self.catalog["project"].get("environment", []) + self.processes[name].get("environment", []):
            key, _, value = item.partition("=")
            env[key] = os.path.expandvars(value)
        return env

    def event(self, name, message):
        with Path(self.processes[name]["log_location"]).open("a") as stream:
            stream.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "[svc] " + message + "\n")

    def wait(self, name, condition="ready", timeout=None):
        proc = self.processes[name]
        timeout = timeout or self.metadata(name).get("start_timeout", 120)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition != "stopped" and self.cancelled and self.cancelled():
                raise ServiceError("Startup interrupted by supervisor shutdown")
            row = states().get(name, {})
            status = row.get("status")
            completed = status == "Completed"
            successful = row.get("exit_code", 0) in [0, *proc.get("success_exit_codes", [])]
            if condition == "stopped" and not active(row):
                check = self.metadata(name).get("stopped_check")
                if check:
                    result = run(["/bin/sh", "-c", check], env=self.environment(name), check=False)
                    if result.returncode:
                        raise ServiceError(f"{name}: stop did not succeed: {result.stderr.strip()}")
                return
            if condition == "process_completed" and completed:
                return
            if condition == "process_completed_successfully" and completed and successful:
                return
            if condition == "process_started" and status in {"Running", "Launched"}:
                return
            if condition in {"ready", "process_healthy", "process_log_ready"}:
                if self.metadata(name).get("kind") == "action" and completed and successful:
                    return
                has_probe = proc.get("readiness_probe") or proc.get("liveness_probe") or proc.get("ready_log_line")
                if status in {"Running", "Launched"} and (not has_probe or row.get("is_ready") == "Ready"):
                    return
            if condition != "stopped" and (status in {"Error", "Skipped"} or completed):
                raise ServiceError(f"{name}: exited before {condition} (status={status}, exit={row.get('exit_code')}); see svc logs {name}")
            time.sleep(0.5)
        raise ServiceError(f"{name}: timed out waiting for {condition}; see svc logs {name}")

    def start(self, selected):
        selected = list(selected)
        for name in ordered(self.processes, selected):
            proc = self.processes[name]
            for dependency, rule in proc.get("depends_on", {}).items():
                self.wait(dependency, rule.get("condition", "process_started"))
            row = states().get(name, {})
            if not active(row):
                print(f"Starting {name}", flush=True)
                self.event(name, "Start requested")
                pc("process", "start", name)
            if self.metadata(name).get("kind") == "action":
                self.wait(name, "process_completed_successfully")
            else:
                self.wait(name)

    def stop(self, selected):
        requested = set(selected)
        for name in selected:
            if name not in self.processes:
                raise ServiceError(f"Unknown service: {name}")
        for name in dependents(self.processes, selected):
            row = states().get(name, {})
            if active(row):
                print(f"Stopping {name}", flush=True)
                self.event(name, "Stop requested")
                timeout = self.processes[name].get("shutdown", {}).get("timeout_seconds", 30) + 15
                pc("process", "stop", name, timeout=timeout)
                self.wait(name, "stopped", timeout=timeout)
            elif name not in requested and self.metadata(name).get("stopped_check"):
                # Verify detached dependents stopped before stopping dependencies.
                # Only dependents pulled in implicitly are checked: a process the caller
                # asked to stop is not a detached dependent, and its stopped_check may
                # describe an externally owned resource (such as a VM started by another
                # login agent) that must not block reload or shutdown.
                self.wait(name, "stopped", timeout=5)


def current_manager():
    if not CATALOG.exists():
        raise ServiceError("Service supervisor has not started yet")
    return Manager(json.loads(CATALOG.read_text()))


def validate(catalog):
    STATE.joinpath("logs").mkdir(parents=True, exist_ok=True, mode=0o700)
    candidate = STATE / "generated/candidate.yaml"
    atomic_write(candidate, yaml.safe_dump(catalog["project"], sort_keys=False))
    run([PC, "--log-file", str(STATE / "logs/validation.log"),
         "up", "--config", str(candidate), "--dry-run"], timeout=30)
    return candidate


def status_json():
    manager = current_manager() if CATALOG.exists() else Manager(discover())
    error, rows = None, {}
    try:
        rows = states()
    except (ServiceError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        error = str(exc)
    enabled = enabled_services()
    busy = None
    try:
        candidate = json.loads((STATE / "busy.json").read_text())
        os.kill(candidate["pid"], 0)
        busy = candidate["operation"]
    except (FileNotFoundError, ProcessLookupError, KeyError, ValueError):
        pass
    entries = []
    for name in sorted(manager.processes):
        row = rows.get(name, {})
        meta = manager.metadata(name)
        entries.append({"name": name, "title": meta.get("title", name),
                        "kind": meta.get("kind", "service"), "url": meta.get("url"),
                        "app": meta.get("app"), "enabled": name in enabled,
                        "active": active(row), "status": row.get("status", "Unavailable"),
                        "health": row.get("is_ready", "-"), "exit_code": row.get("exit_code", 0),
                        "log": manager.processes[name].get("log_location"),
                        "source": manager.catalog["sources"].get(name)})
    return {"services": entries, "error": error, "busy": busy}


def serve():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE, 0o700)
    with (STATE / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ServiceError("A service supervisor is already running") from None
        catalog = discover()
        validate(catalog)
        save_catalog(catalog)
        stopping = False

        def terminate(_signal, _frame):
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        child = subprocess.Popen([PC, "--use-uds", "--unix-socket", str(SOCKET),
                                  "--ordered-shutdown", "--log-file", str(STATE / "logs/process-compose.log"),
                                  "up", "--config", str(COMPOSE), "--tui=false", "--keep-project", "--disable-dotenv"],
                                 start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            while True:
                if child.poll() is not None:
                    raise ServiceError("Process Compose exited; see supervisor.stderr.log")
                try:
                    states()
                    break
                except (ServiceError, subprocess.TimeoutExpired):
                    if time.monotonic() > deadline or stopping:
                        raise ServiceError("Process Compose API did not become available")
                    time.sleep(0.25)
            manager = Manager(catalog, cancelled=lambda: stopping)
            with operation("login startup"):
                for name in sorted(enabled_services()):
                    if stopping:
                        break
                    try:
                        manager.start([name])
                    except (ServiceError, subprocess.TimeoutExpired) as exc:
                        print(f"Autostart {name}: {exc}", file=sys.stderr, flush=True)
            while not stopping and child.poll() is None:
                time.sleep(0.5)
        finally:
            if child.poll() is None:
                try:
                    with operation("shutdown"):
                        current_manager().stop(list(current_manager().processes))
                except (ServiceError, subprocess.TimeoutExpired) as exc:
                    print(f"Shutdown: {exc}", file=sys.stderr, flush=True)
                child.terminate()
                try:
                    child.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        if not stopping and child.returncode:
            raise ServiceError(f"Process Compose exited with {child.returncode}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="Login agent entry point")
    commands.add_parser("validate", help="Validate all definitions without starting them")
    commands.add_parser("reload", help="Stop services, reload definitions, and restore active services")
    status = commands.add_parser("status")
    status.add_argument("--json", action="store_true")
    for verb in ("start", "stop", "restart", "enable", "disable"):
        command = commands.add_parser(verb)
        command.add_argument("names", nargs="+", help="Service names, or 'all'")
    logs = commands.add_parser("logs")
    logs.add_argument("name")
    args = parser.parse_args()
    if args.command == "serve":
        return serve()
    if args.command == "validate":
        catalog = discover()
        validate(catalog)
        print("Valid: " + ", ".join(ordered(catalog["project"]["processes"])))
        return
    if args.command == "status":
        payload = status_json()
        if args.json:
            print(json.dumps(payload))
        else:
            for item in payload["services"]:
                print(f"{item['name']:22} {item['status']:13} {item['health']:10} login={'yes' if item['enabled'] else 'no'}")
            if payload["error"]:
                print(payload["error"], file=sys.stderr)
        return
    if args.command == "logs":
        manager = current_manager()
        if args.name not in manager.processes:
            raise ServiceError(f"Unknown service: {args.name}")
        os.execv("/usr/bin/tail", ["tail", "-n", "100", "-F", manager.processes[args.name]["log_location"]])
    with operation(args.command):
        manager = current_manager()
        if args.command == "reload":
            catalog = discover()
            candidate = validate(catalog)
            processes = catalog["project"]["processes"]
            previous = [name for name, row in states().items() if active(row)]
            # Reload is quiet by default: only changed services and services that opt
            # in with `reload: restart` are bounced. Everything else keeps running.
            changed = {name for name in previous
                       if name in processes and manager.processes.get(name) != processes[name]}
            opted = reload_restarts(catalog) & set(previous) & set(processes)
            removed = {name for name in manager.processes if name not in processes}
            seeds = changed | opted
            if changed:
                print(f"Restarting {', '.join(sorted(changed))} (definition changed)", flush=True)
            if opted - changed:
                print(f"Restarting {', '.join(sorted(opted - changed))} "
                      f"(x-service.reload: restart)", flush=True)
            if removed:
                print(f"Removing {', '.join(sorted(removed))} (no longer defined)", flush=True)
            manager.stop(sorted(seeds | removed))
            pc("project", "update", "--config", str(candidate), timeout=60)
            save_catalog(catalog)
            # A restarted dependency takes its running dependents with it.
            restart = {name for name in dependents(processes, seeds) if name in previous}
            Manager(catalog).start(sorted(restart))
            print("Definitions reloaded")
            return
        names = list(manager.processes) if args.names == ["all"] else args.names
        for name in names:
            if name not in manager.processes:
                raise ServiceError(f"Unknown service: {name}; use svc reload after adding definitions")
        if args.command in {"enable", "disable"}:
            enabled = enabled_services()
            enabled = enabled.union(names) if args.command == "enable" else enabled.difference(names)
            atomic_write(STATE / "autostart.json", json.dumps({"enabled": sorted(enabled)}, indent=2) + "\n")
            print("Login startup updated; running services were not changed")
            return
        if args.command in {"start", "restart"} and discover()["fingerprint"] != manager.catalog["fingerprint"]:
            raise ServiceError("Definitions changed; run svc reload before start/restart")
        if args.command == "restart":
            previous = {name for name, row in states().items() if active(row)}
            affected = dependents(manager.processes, names)
            manager.stop(names)
            manager.start(set(names) | (previous & set(affected)))
        elif args.command == "start":
            manager.start(names)
        else:
            manager.stop(names)


if __name__ == "__main__":
    try:
        main()
    except (ServiceError, subprocess.TimeoutExpired, OSError, ValueError, yaml.YAMLError) as exc:
        print(f"svc: {exc}", file=sys.stderr)
        sys.exit(1)

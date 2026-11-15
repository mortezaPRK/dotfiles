# macOS services

Process Compose runs services; reloading Hammerspoon leaves them running.

```sh
svc status
svc start grafana-lgtm     # starts dependencies and waits for readiness
svc stop podman           # stops dependents first
svc enable caffeinate     # login startup only; does not start it now
svc disable caffeinate
svc logs grafana-lgtm
svc validate
svc reload                # briefly stops/restores running services
```

- Shared: `~/.config/services/definitions/<service>/process-compose.yaml`
- Local overrides/additions: `~/.local/share/services/definitions/`
- Roots: `config.yaml`. Later roots win; maps merge, lists replace, `null` deletes.

Use Process Compose fields and keep scripts beside the YAML. Optional `x-service`
sets menu details, timeouts, and stop checks; `kind: action` marks one-shot commands.

After edits: `svc validate && svc reload`. Use `svc` or the menu to preserve dependency
ordering. Login choices: `~/.local/state/services/autostart.json`, seeded once by
`x-service.default_autostart`. Enabled services start their dependencies at login.

Setup: `~/.config/services/install.sh`

Installs dependencies and runs per-service `install.sh` hooks. Podman's hook requires
sudo for its socket helper; services run unprivileged. Preserves login choices and VM data.

- Grafana: http://127.0.0.1:3000 (`admin` / `admin` initially).
- OTLP: `127.0.0.1:4317` (gRPC), `http://127.0.0.1:4318` (HTTP).
- LGTM data: Podman volume `services-grafana-lgtm-data`, retained across restarts.
- Caffeinate prevents idle system/display sleep; on-demand by default.
- OpenSuperWhisper controls its own menu-bar icon.
- Logs/generated files: `~/.local/state/services/`; supervisor errors: `logs/supervisor.stderr.log`.

Tests: `uv run --script ~/.config/services/test.py`

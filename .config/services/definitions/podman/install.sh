#!/bin/sh
# One-time privileged setup; normal service start/stop runs as the user.
set -eu
podman_bin="${PODMAN_BIN:-/opt/homebrew/bin/podman}"
if [ ! -x "$podman_bin" ]; then podman_bin="$(command -v podman)"; fi
label="com.github.containers.podman.helper-$(id -un)"
plist="/Library/LaunchDaemons/$label.plist"
if [ ! -f "$plist" ]; then
    helper="$(dirname "$podman_bin")/podman-mac-helper"
    [ -x "$helper" ] || { echo "Missing official helper: $helper" >&2; exit 1; }
    sudo "$helper" install
fi
if ! launchctl print "system/$label" >/dev/null 2>&1; then
    sudo launchctl enable "system/$label"
    sudo launchctl bootstrap system "$plist"
fi

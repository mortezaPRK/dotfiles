#!/bin/sh
set -eu
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
config_dir="${SERVICES_CONFIG_HOME:-$HOME/.config/services}"
command -v process-compose >/dev/null || brew install f1bonacc1/tap/process-compose
[ -d /Applications/Hammerspoon.app ] || brew install --cask hammerspoon
command -v uv >/dev/null || brew install uv
chmod +x "$config_dir/install.sh" "$HOME/.local/bin/svc"
uv run --quiet --no-project --script "$config_dir/setup.py"
domain="gui/$(id -u)"
if launchctl print "$domain/dev.mortz.services" >/dev/null 2>&1; then
    echo 'Services agent already loaded; run svc reload to apply definitions.'
else
    launchctl bootstrap "$domain" "$HOME/Library/LaunchAgents/dev.mortz.services.plist"
fi
open -g -a Hammerspoon

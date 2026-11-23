#!/bin/sh
# Run Hermes Desktop, built from a Hermes checkout, against a separate test Hermes home.
# Usage: scripts/run-desktop.sh <hermes checkout> <test dir> [extra Electron args...]
# The test dir gets hermes/ (HERMES_HOME), home/ (HOME) and electron-user-data/. The backend is
# the `hermes` on PATH. See docs/development.md, "Testing in Hermes Desktop".
set -e
desktop=$1/apps/desktop test=$(cd "$2" && pwd)
shift 2
[ -f "$desktop/dist/electron-main.mjs" ] || { echo "Build Desktop first: cd $desktop && pnpm install && pnpm run build" >&2; exit 1; }
cd "$desktop"
# pnpm skips Electron's install script; the binary downloads on first use, with progress on stdout.
node -e "require('electron')" >&2 ||
  node "$(dirname "$(node -p "require.resolve('electron/package.json')")")/install.js" >&2
electron=$(node -p "require('electron')")
mkdir -p "$test/hermes" "$test/home"
exec env -i PATH="$PATH" DISPLAY="${DISPLAY:-}" XAUTHORITY="${XAUTHORITY:-}" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-}" LANG="${LANG:-C.UTF-8}" \
  HOME="$test/home" HERMES_HOME="$test/hermes" HERMES_DESKTOP_USER_DATA_DIR="$test/electron-user-data" \
  HERMES_DESKTOP_HERMES="$(command -v hermes)" HERMES_DESKTOP_IGNORE_EXISTING=1 HERMES_DESKTOP_ISOLATED_BACKEND=1 \
  HERMES_DESKTOP_APP_NAME=HermesPluginTest HERMES_DESKTOP_SKIP_PROTOCOL_REGISTRATION=1 \
  "$electron" . "$@"

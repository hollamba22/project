#!/usr/bin/env bash
set -euo pipefail

[[ "$(uname -r)" == 4.15.* ]] || exit 0
command -v xrandr >/dev/null 2>&1 || exit 0
xrandr_output="$(xrandr --query)"
grep -q '^HDMI-1 connected' <<<"${xrandr_output}" || exit 0

mode_name="1920x1080R"
if ! grep -qE "^[[:space:]]+${mode_name}([[:space:]]|$)" <<<"${xrandr_output}"; then
    xrandr --newmode "${mode_name}" 138.50 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync
    xrandr --addmode HDMI-1 "${mode_name}"
fi
xrandr --output HDMI-1 --primary --mode "${mode_name}"

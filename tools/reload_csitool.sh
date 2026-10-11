#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this with root privileges:"
  echo "  sudo bash tools/reload_csitool.sh"
  exit 1
fi

nmcli device disconnect wlp4s0 >/dev/null 2>&1 || true
ip link set wlp4s0 down >/dev/null 2>&1 || true
modprobe -r iwldvm iwlmvm iwlwifi mac80211
modprobe iwlwifi connector_log=0x1

if [[ -e /sys/module/iwlwifi/parameters/connector_log ]]; then
  echo "connector_log=$(cat /sys/module/iwlwifi/parameters/connector_log)"
else
  echo "connector_log is missing after reload." >&2
  exit 1
fi

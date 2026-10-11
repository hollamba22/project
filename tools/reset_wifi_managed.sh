#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-wlp4s0}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with root privileges:"
  echo "  sudo bash tools/reset_wifi_managed.sh ${IFACE}"
  exit 1
fi

ip addr flush dev "${IFACE}" || true
ip link set "${IFACE}" down
iw dev "${IFACE}" set type managed
ip link set "${IFACE}" up

if command -v nmcli >/dev/null 2>&1; then
  nmcli device set "${IFACE}" managed yes >/dev/null 2>&1 || true
fi

echo "Managed mode restored."
iw dev "${IFACE}" info

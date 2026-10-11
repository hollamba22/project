#!/usr/bin/env bash
set -euo pipefail

IFACE="${1:-wlp4s0}"
IP_CIDR="${2:?Usage: sudo bash tools/setup_ibss.sh <iface> <ip/cidr> [ssid] [freq_mhz]}"
SSID="${3:-csi_ibss}"
FREQ="${4:-2412}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with root privileges:"
  echo "  sudo bash tools/setup_ibss.sh ${IFACE} ${IP_CIDR} ${SSID} ${FREQ}"
  exit 1
fi

if command -v nmcli >/dev/null 2>&1; then
  nmcli device disconnect "${IFACE}" >/dev/null 2>&1 || true
  nmcli device set "${IFACE}" managed no >/dev/null 2>&1 || true
fi

ip addr flush dev "${IFACE}" || true
ip link set "${IFACE}" down
iw dev "${IFACE}" set type ibss
ip link set "${IFACE}" up
iw dev "${IFACE}" ibss join "${SSID}" "${FREQ}" HT20 fixed-freq
ip addr add "${IP_CIDR}" dev "${IFACE}"

echo "IBSS configured."
iw dev "${IFACE}" info
ip -4 addr show dev "${IFACE}"

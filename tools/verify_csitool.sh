#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_TOOL="${PROJECT_ROOT}/third_party/linux-80211n-csitool-supplementary-master/netlink/log_to_file"
DRIVER_KO="${PROJECT_ROOT}/third_party/linux-80211n-csitool-csitool-4.15/drivers/net/wireless/intel/iwlwifi/iwlwifi.ko"

echo "== Kernel =="
uname -a
echo

echo "== Intel 5300 PCI device =="
lspci -nnk | grep -A3 -i 'Ultimate N WiFi Link 5300\|Network controller' || true
echo

echo "== Loaded iwlwifi module =="
modinfo iwlwifi | grep -E 'filename:|vermagic:|connector_log|iwlwifi-5000' || true
echo

echo "== Built CSI module =="
if [[ -f "${DRIVER_KO}" ]]; then
  modinfo "${DRIVER_KO}" | grep -E 'filename:|vermagic:|connector_log|iwlwifi-5000' || true
else
  echo "Missing built module: ${DRIVER_KO}"
fi
echo

echo "== Runtime connector_log =="
if [[ -e /sys/module/iwlwifi/parameters/connector_log ]]; then
  cat /sys/module/iwlwifi/parameters/connector_log
else
  echo "MISSING: /sys/module/iwlwifi/parameters/connector_log"
fi
echo

echo "== Firmware files =="
ls -l /lib/firmware/iwlwifi-5000* 2>/dev/null || true
echo

echo "== WiFi interface =="
iw dev || true
echo

echo "== log_to_file =="
if [[ -x "${LOG_TOOL}" ]]; then
  ls -l "${LOG_TOOL}"
else
  echo "MISSING or not executable: ${LOG_TOOL}"
fi
echo

echo "== Recent iwlwifi kernel log =="
journalctl -k -b --no-pager | grep -i 'iwlwifi\|iwldvm\|connector' | tail -80 || true

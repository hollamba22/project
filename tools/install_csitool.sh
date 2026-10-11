#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KVER="${KVER:-$(uname -r)}"
DRIVER_DIR="${PROJECT_ROOT}/third_party/linux-80211n-csitool-csitool-4.15/drivers/net/wireless/intel/iwlwifi"
SUPP_DIR="${PROJECT_ROOT}/third_party/linux-80211n-csitool-supplementary-master"
FW_SRC="${SUPP_DIR}/firmware/iwlwifi-5000-2.ucode.sigcomm2010"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this with root privileges:"
  echo "  sudo bash ${PROJECT_ROOT}/tools/install_csitool.sh"
  exit 1
fi

if [[ "${KVER}" != 4.15.* ]]; then
  echo "This setup expects a 4.15 kernel. Current kernel: ${KVER}" >&2
  exit 1
fi

if [[ ! -d "/lib/modules/${KVER}/build" ]]; then
  echo "Missing kernel build directory: /lib/modules/${KVER}/build" >&2
  echo "Install linux-headers-${KVER} first." >&2
  exit 1
fi

if [[ ! -d "${DRIVER_DIR}" ]]; then
  echo "Missing driver source directory: ${DRIVER_DIR}" >&2
  exit 1
fi

if [[ ! -f "${FW_SRC}" ]]; then
  echo "Missing CSI firmware: ${FW_SRC}" >&2
  exit 1
fi

echo "[1/5] Building CSI-enabled iwlwifi modules for ${KVER}"
make -j "$(nproc)" -C "/lib/modules/${KVER}/build" M="${DRIVER_DIR}" modules

echo "[2/5] Installing modules into /lib/modules/${KVER}/updates"
make -C "/lib/modules/${KVER}/build" M="${DRIVER_DIR}" INSTALL_MOD_DIR=updates modules_install
depmod "${KVER}"

echo "[3/5] Installing CSI firmware for Intel 5000 series"
backup_dir="/lib/firmware/csitool-backup-$(date +%Y%m%d-%H%M%S)"
shopt -s nullglob
for fw in /lib/firmware/iwlwifi-5000-*.ucode; do
  base="$(basename "${fw}")"
  if [[ "${base}" == "iwlwifi-5000-2.ucode" ]] \
    && [[ -L "${fw}" ]] \
    && [[ "$(readlink "${fw}")" == "iwlwifi-5000-2.ucode.sigcomm2010" ]]; then
    continue
  fi
  mkdir -p "${backup_dir}"
  mv "${fw}" "${backup_dir}/"
done
cp "${FW_SRC}" /lib/firmware/iwlwifi-5000-2.ucode.sigcomm2010
ln -sfn iwlwifi-5000-2.ucode.sigcomm2010 /lib/firmware/iwlwifi-5000-2.ucode

if [[ -d "${backup_dir}" ]]; then
  echo "Original Intel 5000 firmware files moved to: ${backup_dir}"
fi

echo "[4/5] Enabling connector_log by default"
printf '%s\n' 'options iwlwifi connector_log=0x1' > /etc/modprobe.d/csitool.conf

echo "[5/5] Reloading iwlwifi with CSI logging enabled"
if command -v nmcli >/dev/null 2>&1; then
  nmcli device disconnect wlp4s0 >/dev/null 2>&1 || true
fi
ip link set wlp4s0 down >/dev/null 2>&1 || true

if ! modprobe -r iwldvm iwlmvm iwlwifi mac80211; then
  echo "Could not unload WiFi modules cleanly." >&2
  echo "Reboot, then run: bash ${PROJECT_ROOT}/tools/verify_csitool.sh" >&2
  exit 2
fi

modprobe iwlwifi connector_log=0x1

echo
echo "CSI Tool install finished."
if [[ -e /sys/module/iwlwifi/parameters/connector_log ]]; then
  echo "connector_log=$(cat /sys/module/iwlwifi/parameters/connector_log)"
else
  echo "connector_log parameter is missing after reload." >&2
  exit 3
fi

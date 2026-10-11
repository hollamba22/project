#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_TOOL="${PROJECT_ROOT}/third_party/linux-80211n-csitool-supplementary-master/netlink/log_to_file"
SESSION_DIR="${1:-${PROJECT_ROOT}/data/raw/session_$(date +%Y%m%d_%H%M%S)}"
OUT_FILE="${SESSION_DIR}/csi.dat"

if [[ ! -x "${LOG_TOOL}" ]]; then
  echo "Missing log_to_file. Build it with:"
  echo "  make -C ${PROJECT_ROOT}/third_party/linux-80211n-csitool-supplementary-master/netlink"
  exit 1
fi

if [[ ! -e /sys/module/iwlwifi/parameters/connector_log ]]; then
  echo "connector_log is missing. Install/reload CSI driver first:"
  echo "  sudo bash ${PROJECT_ROOT}/tools/install_csitool.sh"
  exit 1
fi

mkdir -p "${SESSION_DIR}"
echo "Writing CSI to ${OUT_FILE}"
echo "Stop with Ctrl-C."
exec sudo "${LOG_TOOL}" "${OUT_FILE}"

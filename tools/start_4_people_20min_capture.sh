#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

CAPTURE_ARGS=(
  --duration 1200
  --num-people 4
  --activity natural
  --room project_room
  --camera-device /dev/video0
  --collection-root data/4_people
  --capture-purpose training
  --antenna-holder 3d_printed_v1
  --progress-interval 60
)

echo "Checking CSI, WiFi, webcam, logger, and disk state..."
python3 scripts/capture/capture_prototype.py "${CAPTURE_ARGS[@]}" --dry-run

echo "Authenticating sudo before the 20-minute capture..."
sudo -v

echo "Starting the 4-person capture. Wait for READY before starting the sender."
exec python3 scripts/capture/capture_prototype.py "${CAPTURE_ARGS[@]}"

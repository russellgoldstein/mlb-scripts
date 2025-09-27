#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_SCRIPT="${SCRIPT_DIR}/mlb_streaks_2025.sh"

for season in {1900..2025}; do
    echo "Running streaks script for season ${season}"
    "${TARGET_SCRIPT}" "${season}"
    sleep 1
    echo "--------------------------------------------"
    echo ""
done

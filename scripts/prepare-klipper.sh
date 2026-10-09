#!/usr/bin/env bash
# Check out the pinned Klipper and apply the Q2 patch series.
# Usage: scripts/prepare-klipper.sh <klipper-dir>
set -Eeuo pipefail
. "$(dirname "$0")/lib.sh"

dir="${1:?usage: $0 <klipper-dir>}"
info "Klipper ${KLIPPER_REF:0:9} -> ${dir}"
checkout_ref "$KLIPPER_REPO" "$KLIPPER_REF" "$dir"
apply_patches "$dir" "${Q2_ROOT}/patches/klipper" q2-offload

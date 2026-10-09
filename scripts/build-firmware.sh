#!/usr/bin/env bash
# Build the three MCU firmwares from a prepared (patched) Klipper tree.
# Usage: scripts/build-firmware.sh <klipper-dir> <out-dir>
# Output per MCU: q2-<mcu>.bin, q2-<mcu>.dict, q2-<mcu>.config, plus SHA256SUMS and BUILD_INFO.
set -Eeuo pipefail
. "$(dirname "$0")/lib.sh"

kdir="$(cd "${1:?usage: $0 <klipper-dir> <out-dir>}" && pwd)"
mkdir -p "${2:?usage: $0 <klipper-dir> <out-dir>}"
out="$(cd "$2" && pwd)"
jobs="$(nproc 2>/dev/null || echo 2)"

for mcu in main thr box; do
    info "Building ${mcu}"
    rm -rf "${kdir}/out"
    cp "${Q2_ROOT}/firmware/configs/${mcu}.config" "${kdir}/.config"
    make -C "$kdir" olddefconfig >/dev/null
    make -C "$kdir" -j"$jobs" >/dev/null
    cp "${kdir}/out/klipper.bin" "${out}/q2-${mcu}.bin"
    cp "${kdir}/out/klipper.dict" "${out}/q2-${mcu}.dict"
    cp "${kdir}/.config" "${out}/q2-${mcu}.config"
    ok "q2-${mcu}.bin ($(wc -c < "${out}/q2-${mcu}.bin") bytes)"
done

# The bootloader offset is what keeps a flash from bricking the MCU: refuse a drifted build.
check_offset() {
    grep -qx "CONFIG_FLASH_APPLICATION_ADDRESS=$2" "${out}/q2-$1.config" \
        || die "q2-$1: application offset is not $2"
}
check_offset main 0x8008000
check_offset thr 0x8002000
check_offset box 0x8004000

(cd "$out" && sha256sum q2-*.bin q2-*.dict > SHA256SUMS)
{
    echo "FIRMWARE_ID=$(firmware_id)"
    echo "KLIPPER_REF=${KLIPPER_REF}"
    echo "KLIPPER_VERSION=$(git -C "$kdir" describe --tags --always --dirty)"
} > "${out}/BUILD_INFO"
cat "${out}/BUILD_INFO"

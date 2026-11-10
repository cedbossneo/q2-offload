#!/usr/bin/env bash
# Get Qidi's hid-flash from its public 1.1.1 firmware package. Newer stock firmware flashes from
# its screen app and no longer ships this tool, which a first conversion needs. It is an arm64
# binary for the printer: only unpacked here, never run.
# Usage: fetch-hid-flash.sh <output file>
set -euo pipefail
Q2_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=lib.sh
. "${Q2_ROOT}/scripts/lib.sh"

out="${1:?output file}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
download "$HID_FLASH_URL" "${tmp}/firmware.zip"
unzip -q "${tmp}/firmware.zip" "$HID_FLASH_PACKAGE" -d "$tmp"
dpkg-deb --fsys-tarfile "${tmp}/${HID_FLASH_PACKAGE}" | tar -xO ./home/mks/hid-flash > "${tmp}/hid-flash"
echo "${HID_FLASH_SHA256}  ${tmp}/hid-flash" | sha256sum -c --quiet || die "hid-flash checksum mismatch"
install -m 755 "${tmp}/hid-flash" "$out"
